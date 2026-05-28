import bpy
import sys
import re
from .module_helper import ModuleManager

module_enabled = True

_CTRL_PREFIX = "CTRL_"
_SUFFIX_RE = re.compile(r'\.\d+$')

_syncing = False
_dirty_bases = set()
_msgbus_owner = object()

_MAT_NAME = "_QP_CTRL_host_mat"

_TREE_GROUP_NODE = {
    'ShaderNodeTree':     'ShaderNodeGroup',
    'GeometryNodeTree':   'GeometryNodeGroup',
    'CompositorNodeTree': 'CompositorNodeGroup',
}


def _get_host_tree(ng):
    """Return a local node tree that can host ng as a group node."""
    if ng.bl_idname == 'ShaderNodeTree':
        mat = bpy.data.materials.get(_MAT_NAME)
        if mat is None:
            mat = bpy.data.materials.new(_MAT_NAME)
            mat.use_fake_user = True
        mat.use_nodes = True
        return mat.node_tree
    host_name = f"_QP_CTRL_host_{ng.bl_idname}"
    host = bpy.data.node_groups.get(host_name)
    if host is None:
        host = bpy.data.node_groups.new(host_name, ng.bl_idname)
        host.use_fake_user = True
    return host


# ── Msgbus: detect socket edits without needing scene users ──────────────────

def _on_ctrl_socket_changed(ng_name):
    if _syncing:
        return
    ng = bpy.data.node_groups.get(ng_name)
    if ng is None or ng.library is not None:
        return
    _dirty_bases.add((_ctrl_base_name(ng_name), ng_name))
    if not bpy.app.timers.is_registered(_ctrl_do_sync):
        bpy.app.timers.register(_ctrl_do_sync, first_interval=0.0)


def _subscribe_ctrl_sockets():
    try:
        bpy.msgbus.clear_by_owner(_msgbus_owner)
    except Exception:
        pass
    for ng in bpy.data.node_groups:
        if not ng.name.startswith(_CTRL_PREFIX) or ng.library is not None:
            continue
        for node in ng.nodes:
            if node.type == 'GROUP_OUTPUT':
                for inp in node.inputs:
                    if not hasattr(inp, 'default_value'):
                        continue
                    try:
                        bpy.msgbus.subscribe_rna(
                            key=inp,
                            owner=_msgbus_owner,
                            args=(ng.name,),
                            notify=_on_ctrl_socket_changed,
                            options={'PERSISTENT'},
                        )
                    except Exception:
                        pass
    return None


# ── Helpers ──────────────────────────────────────────────────────────────────

def _ctrl_base_name(ng_name):
    return _SUFFIX_RE.sub('', ng_name[len(_CTRL_PREFIX):])


def _group_output_sockets(ng):
    for node in ng.nodes:
        if node.type == 'GROUP_OUTPUT':
            return {inp.name: inp for inp in node.inputs if hasattr(inp, 'default_value')}
    return {}


def _socket_signature(ng):
    """Frozenset of (socket_name, socket_type) for the GROUP_OUTPUT node."""
    return frozenset(
        (name, type(inp).__name__)
        for name, inp in _group_output_sockets(ng).items()
    )


def _cluster_has_local(base_name):
    """Return True if any CTRL_ group with this base name is local (not linked)."""
    return any(
        g.library is None
        for g in bpy.data.node_groups
        if g.name.startswith(_CTRL_PREFIX) and _ctrl_base_name(g.name) == base_name
    )


# ── Sibling sync ─────────────────────────────────────────────────────────────

def _sync_cluster(base_name, source_ng_name):
    """Copy output socket values from the source group to all siblings.
    If the cluster has any local group, only local groups may act as source —
    this prevents library values from overwriting user-edited local values."""
    source_ng = bpy.data.node_groups.get(source_ng_name)
    if source_ng is None:
        return

    # Local groups always win: if source is linked but a local sibling exists, skip.
    if source_ng.library is not None and _cluster_has_local(base_name):
        return

    siblings = [
        g for g in bpy.data.node_groups
        if g is not source_ng
        and g.name.startswith(_CTRL_PREFIX)
        and _ctrl_base_name(g.name) == base_name
    ]
    if not siblings:
        return

    written = []
    source_sockets = _group_output_sockets(source_ng)
    for sibling in siblings:
        sibling_sockets = _group_output_sockets(sibling)
        sibling_wrote = False
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
                sibling_wrote = True
            except (AttributeError, TypeError, ReferenceError):
                pass
        if sibling_wrote:
            written.append(sibling)
    return written


def _ctrl_do_sync():
    global _syncing, _dirty_bases
    if _syncing or not _dirty_bases:
        _dirty_bases.clear()
        return None

    to_process = set(_dirty_bases)
    _dirty_bases.clear()

    written_ngs = []
    _syncing = True
    try:
        for base_name, source_ng_name in to_process:
            written_ngs.extend(_sync_cluster(base_name, source_ng_name))
    except Exception:
        pass
    finally:
        _syncing = False

    for ng in written_ngs:
        try:
            ng.update_tag()
        except Exception:
            pass

    return None


@bpy.app.handlers.persistent
def _ctrl_mark_dirty(scene, depsgraph):
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


@bpy.app.handlers.persistent
def _ctrl_load_post(filepath, *args):
    """After file load: sync FROM local groups TO linked siblings only.
    Local values always win — linked groups revert to library state on load,
    so we must re-push from the local (user-edited) copies."""
    try:
        for ng in bpy.data.node_groups:
            if not ng.name.startswith(_CTRL_PREFIX):
                continue
            if ng.library is not None:
                continue  # Only local groups initiate sync after load
            _dirty_bases.add((_ctrl_base_name(ng.name), ng.name))
        if _dirty_bases and not bpy.app.timers.is_registered(_ctrl_do_sync):
            bpy.app.timers.register(_ctrl_do_sync, first_interval=0.1)
        if not bpy.app.timers.is_registered(_subscribe_ctrl_sockets):
            bpy.app.timers.register(_subscribe_ctrl_sockets, first_interval=0.2)
    except Exception:
        pass


# ── Operators ─────────────────────────────────────────────────────────────────

class QP_OT_make_ctrl_local(bpy.types.Operator):
    bl_idname = "qp.make_ctrl_local"
    bl_label = "Make CTRL Groups Local"
    bl_description = (
        "Create local editable copies of any linked CTRL_ node groups. "
        "Required for sidebar controls to be editable when groups are linked from a library"
    )
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        linked = [
            ng for ng in bpy.data.node_groups
            if ng.name.startswith(_CTRL_PREFIX) and ng.library is not None
        ]
        if not linked:
            self.report({'INFO'}, "All CTRL_ groups are already local")
            return {'FINISHED'}

        made_local = []
        for ng in linked:
            host_tree = _get_host_tree(ng)
            group_node_type = _TREE_GROUP_NODE.get(ng.bl_idname)
            if group_node_type:
                host_tree.nodes.new(group_node_type).node_tree = ng
            local_ng = ng.make_local()
            if local_ng is not None:
                local_ng.use_fake_user = True
                made_local.append(local_ng.name)

        if made_local:
            # Trigger an immediate sync so local values push to any remaining linked siblings
            for base_name, _ in {(_ctrl_base_name(n), n) for n in made_local}:
                for ng in bpy.data.node_groups:
                    if ng.name.startswith(_CTRL_PREFIX) and _ctrl_base_name(ng.name) == base_name and ng.library is None:
                        _dirty_bases.add((base_name, ng.name))
            if not bpy.app.timers.is_registered(_ctrl_do_sync):
                bpy.app.timers.register(_ctrl_do_sync, first_interval=0.0)
            _subscribe_ctrl_sockets()
            for window in context.window_manager.windows:
                for area in window.screen.areas:
                    area.tag_redraw()
            self.report({'INFO'}, f"Made local: {', '.join(made_local)}")
        else:
            self.report({'WARNING'}, "make_local() returned nothing — groups may already be local")

        return {'FINISHED'}


class QP_OT_refresh_ctrl_groups(bpy.types.Operator):
    bl_idname = "qp.refresh_ctrl_groups"
    bl_label = "Refresh All"
    bl_description = (
        "Re-sync all CTRL_ node group siblings and remake local any whose "
        "socket structure changed in the linked library"
    )
    bl_options = {'REGISTER'}

    def execute(self, context):
        # ── Step 1: detect structure changes ─────────────────────────────────
        clusters = {}
        for ng in bpy.data.node_groups:
            if not ng.name.startswith(_CTRL_PREFIX):
                continue
            base = _ctrl_base_name(ng.name)
            clusters.setdefault(base, {'local': [], 'linked': []})
            if ng.library is None:
                clusters[base]['local'].append(ng)
            else:
                clusters[base]['linked'].append(ng)

        # Pairs where the local socket structure differs from the linked one
        to_remake = []
        for base, data in clusters.items():
            if not data['local'] or not data['linked']:
                continue
            linked_sig = _socket_signature(data['linked'][0])
            for local_ng in data['local']:
                if _socket_signature(local_ng) != linked_sig:
                    to_remake.append((local_ng, data['linked'][0]))

        # ── Step 2: delete outdated locals and remake from linked ─────────────
        remade = []
        if to_remake:
            for local_ng, _ in to_remake:
                bpy.data.node_groups.remove(local_ng)

            for _, linked_ng in to_remake:
                host_tree = _get_host_tree(linked_ng)
                group_node_type = _TREE_GROUP_NODE.get(linked_ng.bl_idname)
                if group_node_type:
                    host_tree.nodes.new(group_node_type).node_tree = linked_ng
                new_local = linked_ng.make_local()
                if new_local is not None:
                    new_local.use_fake_user = True
                    remade.append(new_local.name)

            _subscribe_ctrl_sockets()

        # ── Step 3: normal sibling sync ───────────────────────────────────────
        for ng in bpy.data.node_groups:
            if not ng.name.startswith(_CTRL_PREFIX) or ng.library is not None:
                continue
            _dirty_bases.add((_ctrl_base_name(ng.name), ng.name))
        _ctrl_do_sync()

        for area in context.screen.areas:
            area.tag_redraw()

        if remade:
            self.report({'INFO'}, f"Remade (structure changed): {', '.join(remade)}")
        else:
            self.report({'INFO'}, "Global Controls: synced")
        return {'FINISHED'}


# ── Registration ──────────────────────────────────────────────────────────────

def register():
    if not ModuleManager.register_module(sys.modules[__name__]):
        return
    ModuleManager.safe_register_class(QP_OT_make_ctrl_local)
    ModuleManager.safe_register_class(QP_OT_refresh_ctrl_groups)
    if _ctrl_mark_dirty not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_ctrl_mark_dirty)
    if _ctrl_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_ctrl_load_post)
    bpy.app.timers.register(_subscribe_ctrl_sockets, first_interval=0.1)


def unregister():
    if not ModuleManager.unregister_module(sys.modules[__name__]):
        return
    bpy.msgbus.clear_by_owner(_msgbus_owner)
    if _ctrl_mark_dirty in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_ctrl_mark_dirty)
    if _ctrl_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_ctrl_load_post)
    ModuleManager.safe_unregister_class(QP_OT_refresh_ctrl_groups)
    ModuleManager.safe_unregister_class(QP_OT_make_ctrl_local)


if __name__ == "__main__":
    register()
