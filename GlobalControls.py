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
_dirty_bases = set()  # {(base_name, source_ng_name), ...}


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
        return None  # one-shot, no repeat

    to_process = set(_dirty_bases)
    _dirty_bases.clear()

    _syncing = True
    try:
        for base_name, source_ng_name in to_process:
            _sync_cluster(base_name, source_ng_name)
    except Exception:
        pass
    finally:
        _syncing = False

    return None  # one-shot


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
    """Re-write all CTRL_ output socket values to force a depsgraph update."""
    for ng in bpy.data.node_groups:
        if not ng.name.startswith(_CTRL_PREFIX):
            continue
        for node in ng.nodes:
            if node.type != 'GROUP_OUTPUT':
                continue
            for inp in node.inputs:
                if not hasattr(inp, 'default_value'):
                    continue
                try:
                    val = inp.default_value
                    if hasattr(val, '__len__'):
                        inp.default_value = tuple(val)
                    else:
                        inp.default_value = val
                except (AttributeError, TypeError, ReferenceError):
                    pass


@bpy.app.handlers.persistent
def _ctrl_refresh_pre_render(scene, depsgraph=None):
    """Push CTRL_ node group values before every render."""
    try:
        _push_ctrl_values()
    except Exception:
        pass


class QP_OT_refresh_ctrl_groups(bpy.types.Operator):
    bl_idname = "qp.refresh_ctrl_groups"
    bl_label = "Refresh All"
    bl_description = (
        "Push all CTRL_ node group output values into the dependency graph. "
        "Use this if the viewport or render does not reflect recent changes"
    )
    bl_options = {'REGISTER'}

    def execute(self, context):
        _push_ctrl_values()
        for area in context.screen.areas:
            area.tag_redraw()
        self.report({'INFO'}, "Global Controls: values refreshed")
        return {'FINISHED'}


# ── Registration ──────────────────────────────────────────────────────────────

def register():
    if not ModuleManager.register_module(sys.modules[__name__]):
        return
    ModuleManager.safe_register_class(QP_OT_refresh_ctrl_groups)
    if _ctrl_refresh_pre_render not in bpy.app.handlers.render_pre:
        bpy.app.handlers.render_pre.append(_ctrl_refresh_pre_render)
    if _ctrl_mark_dirty not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_ctrl_mark_dirty)


def unregister():
    if not ModuleManager.unregister_module(sys.modules[__name__]):
        return
    if _ctrl_mark_dirty in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_ctrl_mark_dirty)
    if _ctrl_refresh_pre_render in bpy.app.handlers.render_pre:
        bpy.app.handlers.render_pre.remove(_ctrl_refresh_pre_render)
    ModuleManager.safe_unregister_class(QP_OT_refresh_ctrl_groups)


if __name__ == "__main__":
    register()
