import bpy
import sys
import re
from .module_helper import ModuleManager

module_enabled = True
_is_registered = False

_CTRL_PREFIX = "CTRL_"
_SUFFIX_RE = re.compile(r'\.\d+$')

# Guards and deferred work
_syncing = False
_initializing = False
_dirty_bases = set()  # {(base_name, source_ng_name), ...}

# Socket type → PropertyGroup field name
_SOCKET_TYPE_PROPS = {
    'VALUE':   'v_float',
    'INT':     'v_int',
    'BOOLEAN': 'v_bool',
    'RGBA':    'v_color',
    'VECTOR':  'v_vector',
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _ctrl_base_name(ng_name):
    """'CTRL_cube shading.001' → 'cube shading'"""
    return _SUFFIX_RE.sub('', ng_name[len(_CTRL_PREFIX):])


def _group_output_sockets(ng):
    """{socket_name: inp} for valid output sockets on the Group Output node."""
    for node in ng.nodes:
        if node.type == 'GROUP_OUTPUT':
            return {inp.name: inp for inp in node.inputs if hasattr(inp, 'default_value')}
    return {}


def _entry_prop(socket_type):
    return _SOCKET_TYPE_PROPS.get(socket_type, 'v_float')


# ── Scene-level value storage ─────────────────────────────────────────────────

def _push_entry_to_ngs(entry):
    """Write one scene socket entry into all matching CTRL_ node groups."""
    if _syncing:
        return
    base  = entry.base_name
    sname = entry.socket_name
    stype = entry.socket_type
    prop  = _entry_prop(stype)
    val   = getattr(entry, prop)
    if hasattr(val, '__len__'):
        val = tuple(val)

    for ng in bpy.data.node_groups:
        if not ng.name.startswith(_CTRL_PREFIX):
            continue
        if _ctrl_base_name(ng.name) != base:
            continue
        for node in ng.nodes:
            if node.type != 'GROUP_OUTPUT':
                continue
            for inp in node.inputs:
                if inp.name != sname or not hasattr(inp, 'default_value'):
                    continue
                try:
                    if stype in ('RGBA', 'VECTOR'):
                        for i, v in enumerate(val):
                            inp.default_value[i] = v
                    else:
                        inp.default_value = val
                except (AttributeError, TypeError, ReferenceError):
                    pass


def push_all_scene_to_ngs(scene):
    """Push all scene socket entries into their CTRL_ node groups."""
    if scene is None or not hasattr(scene, 'qp_ctrl_sockets'):
        return
    for entry in scene.qp_ctrl_sockets:
        _push_entry_to_ngs(entry)


def _cleanup_stale_entries(scene):
    """Remove scene socket entries whose CTRL_ base name no longer exists."""
    if scene is None or not hasattr(scene, 'qp_ctrl_sockets'):
        return
    existing_bases = {
        _ctrl_base_name(ng.name)
        for ng in bpy.data.node_groups
        if ng.name.startswith(_CTRL_PREFIX)
    }
    stale_keys = [
        entry.name for entry in scene.qp_ctrl_sockets
        if entry.base_name not in existing_bases
    ]
    for key in stale_keys:
        idx = scene.qp_ctrl_sockets.find(key)
        if idx >= 0:
            scene.qp_ctrl_sockets.remove(idx)


def _create_scene_entry(scene, base_name, socket_name, inp):
    """Create and initialise a scene entry from a node socket. Must NOT be called from draw."""
    global _initializing
    key   = f"{base_name}||{socket_name}"
    entry = scene.qp_ctrl_sockets.get(key)
    if entry is not None:
        return entry

    entry             = scene.qp_ctrl_sockets.add()
    entry.name        = key
    entry.base_name   = base_name
    entry.socket_name = socket_name
    stype             = getattr(inp, 'type', 'VALUE')
    entry.socket_type = stype
    prop              = _entry_prop(stype)

    _initializing = True
    try:
        val = inp.default_value
        if hasattr(val, '__len__'):
            setattr(entry, prop, tuple(val))
        else:
            setattr(entry, prop, val)
    except (AttributeError, TypeError, ReferenceError):
        pass
    finally:
        _initializing = False

    return entry


def ensure_scene_entries():
    """Timer callback: create any missing scene socket entries from current CTRL_ node groups.
    Safe to call from a timer (main thread, between frames) — never from draw."""
    scene = getattr(bpy.context, 'scene', None)
    if scene is None or not hasattr(scene, 'qp_ctrl_sockets'):
        return None
    created = False
    for ng in bpy.data.node_groups:
        if not ng.name.startswith(_CTRL_PREFIX):
            continue
        base = _ctrl_base_name(ng.name)
        for node in ng.nodes:
            if node.type != 'GROUP_OUTPUT':
                continue
            for inp in node.inputs:
                if not hasattr(inp, 'default_value'):
                    continue
                if getattr(inp, 'type', 'VALUE') not in _SOCKET_TYPE_PROPS:
                    continue
                key = f"{base}||{inp.name}"
                if scene.qp_ctrl_sockets.get(key) is None:
                    _create_scene_entry(scene, base, inp.name, inp)
                    created = True
    if created:
        try:
            for window in bpy.context.window_manager.windows:
                for area in window.screen.areas:
                    area.tag_redraw()
        except Exception:
            pass
    return None  # one-shot


def _on_ctrl_value_change(self, context):
    if _syncing or _initializing:
        return
    _push_entry_to_ngs(self)


class QP_CtrlSocketValue(bpy.types.PropertyGroup):
    base_name:    bpy.props.StringProperty()
    socket_name:  bpy.props.StringProperty()
    socket_type:  bpy.props.StringProperty()
    v_float: bpy.props.FloatProperty(update=_on_ctrl_value_change)
    v_int:   bpy.props.IntProperty(update=_on_ctrl_value_change)
    v_bool:  bpy.props.BoolProperty(update=_on_ctrl_value_change)
    v_color: bpy.props.FloatVectorProperty(
        size=4, subtype='COLOR_GAMMA', min=0.0, max=1.0,
        default=(0.0, 0.0, 0.0, 1.0),
        update=_on_ctrl_value_change,
    )
    v_vector: bpy.props.FloatVectorProperty(
        size=3,
        update=_on_ctrl_value_change,
    )


# ── Sibling sync ─────────────────────────────────────────────────────────────

def _sync_cluster(base_name, source_ng_name):
    """Copy output socket values from source_ng to all siblings with the same base name."""
    source_ng = bpy.data.node_groups.get(source_ng_name)
    if source_ng is None:
        return

    siblings = [
        g for g in bpy.data.node_groups
        if g is not source_ng
        and g.name.startswith(_CTRL_PREFIX)
        and _ctrl_base_name(g.name) == base_name
    ]
    if not siblings:
        return

    source_sockets = _group_output_sockets(source_ng)
    for sibling in siblings:
        sibling_sockets = _group_output_sockets(sibling)
        for name, src_inp in source_sockets.items():
            if name not in sibling_sockets:
                continue
            tgt_inp = sibling_sockets[name]
            if type(src_inp) is not type(tgt_inp):
                continue
            try:
                val = src_inp.default_value
                if hasattr(val, '__len__'):
                    val = tuple(val)
                    if tuple(tgt_inp.default_value) == val:
                        continue
                else:
                    if tgt_inp.default_value == val:
                        continue
                tgt_inp.default_value = val
            except (AttributeError, TypeError, ReferenceError):
                pass


def _ctrl_do_sync():
    """Timer callback: flush pending sibling syncs."""
    global _syncing, _dirty_bases
    if _syncing or not _dirty_bases:
        _dirty_bases.clear()
        return None

    to_process = set(_dirty_bases)
    _dirty_bases.clear()

    _syncing = True
    try:
        for base_name, source_ng_name in to_process:
            _sync_cluster(base_name, source_ng_name)
        scene = getattr(bpy.context, 'scene', None)
        _cleanup_stale_entries(scene)
    except Exception:
        pass
    finally:
        _syncing = False

    return None


@bpy.app.handlers.persistent
def _ctrl_mark_dirty(scene, depsgraph):
    """Depsgraph update handler: schedule sibling sync when a CTRL_ group changes."""
    if _syncing:
        return
    changed = False
    for update in depsgraph.updates:
        if not isinstance(update.id, bpy.types.NodeTree):
            continue
        ng = update.id
        if ng.name.startswith(_CTRL_PREFIX):
            _dirty_bases.add((_ctrl_base_name(ng.name), ng.name))
            changed = True
    if changed and not bpy.app.timers.is_registered(_ctrl_do_sync):
        bpy.app.timers.register(_ctrl_do_sync, first_interval=0.0)


# ── Refresh ───────────────────────────────────────────────────────────────────

def _push_ctrl_values():
    """Push scene socket entries into CTRL_ node groups."""
    scene = getattr(bpy.context, 'scene', None)
    push_all_scene_to_ngs(scene)


@bpy.app.handlers.persistent
def _ctrl_refresh_pre_render(scene, depsgraph=None):
    """Push CTRL_ node group values before every render."""
    try:
        push_all_scene_to_ngs(scene)
    except Exception:
        pass


@bpy.app.handlers.persistent
def _ctrl_load_post(filepath, *args):
    """After file load: push saved scene values, remove stale entries, create missing ones."""
    try:
        for scene in bpy.data.scenes:
            _cleanup_stale_entries(scene)
            push_all_scene_to_ngs(scene)
    except Exception:
        pass
    if not bpy.app.timers.is_registered(ensure_scene_entries):
        bpy.app.timers.register(ensure_scene_entries, first_interval=0.1)


class QP_OT_refresh_ctrl_groups(bpy.types.Operator):
    bl_idname = "qp.refresh_ctrl_groups"
    bl_label = "Refresh All"
    bl_description = (
        "Push all CTRL_ node group output values into the dependency graph. "
        "Use this if the viewport or render does not reflect recent changes"
    )
    bl_options = {'REGISTER'}

    def execute(self, context):
        _cleanup_stale_entries(context.scene)
        _push_ctrl_values()
        for area in context.screen.areas:
            area.tag_redraw()
        self.report({'INFO'}, "Global Controls: values refreshed")
        return {'FINISHED'}


# ── Registration ──────────────────────────────────────────────────────────────

def register():
    if not ModuleManager.register_module(sys.modules[__name__]):
        return
    ModuleManager.safe_register_class(QP_CtrlSocketValue)
    ModuleManager.safe_register_class(QP_OT_refresh_ctrl_groups)
    if not hasattr(bpy.types.Scene, 'qp_ctrl_sockets'):
        bpy.types.Scene.qp_ctrl_sockets = bpy.props.CollectionProperty(type=QP_CtrlSocketValue)
    if not bpy.app.timers.is_registered(ensure_scene_entries):
        bpy.app.timers.register(ensure_scene_entries, first_interval=0.1)
    if _ctrl_refresh_pre_render not in bpy.app.handlers.render_pre:
        bpy.app.handlers.render_pre.append(_ctrl_refresh_pre_render)
    if _ctrl_mark_dirty not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_ctrl_mark_dirty)
    if _ctrl_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_ctrl_load_post)


def unregister():
    if not ModuleManager.unregister_module(sys.modules[__name__]):
        return
    if _ctrl_mark_dirty in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_ctrl_mark_dirty)
    if _ctrl_refresh_pre_render in bpy.app.handlers.render_pre:
        bpy.app.handlers.render_pre.remove(_ctrl_refresh_pre_render)
    if _ctrl_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_ctrl_load_post)
    if hasattr(bpy.types.Scene, 'qp_ctrl_sockets'):
        del bpy.types.Scene.qp_ctrl_sockets
    ModuleManager.safe_unregister_class(QP_OT_refresh_ctrl_groups)
    ModuleManager.safe_unregister_class(QP_CtrlSocketValue)


if __name__ == "__main__":
    register()
