import bpy
import json
from bpy.app.handlers import persistent
from bpy.props import StringProperty


_pending_update = False


class QP_AOVManagerState(bpy.types.PropertyGroup):
    managed_aovs: StringProperty(default="[]")


def find_aov_nodes_recursive(node_tree, visited=None):
    if visited is None:
        visited = set()

    tree_id = id(node_tree)
    if tree_id in visited:
        return {}
    visited.add(tree_id)

    result = {}
    for node in node_tree.nodes:
        if node.type == 'OUTPUT_AOV':
            name = node.aov_name
            if name:
                aov_type = 'VALUE' if node.inputs[1].is_linked else 'COLOR'
                if name not in result or aov_type == 'VALUE':
                    result[name] = aov_type
        elif node.type == 'GROUP' and node.node_tree:
            nested = find_aov_nodes_recursive(node.node_tree, visited)
            for name, aov_type in nested.items():
                if name not in result or aov_type == 'VALUE':
                    result[name] = aov_type
    return result


def scan_all_materials():
    found = {}
    for mat in bpy.data.materials:
        if not mat.use_nodes or not mat.node_tree:
            continue
        mat_aovs = find_aov_nodes_recursive(mat.node_tree)
        for name, aov_type in mat_aovs.items():
            if name not in found or aov_type == 'VALUE':
                found[name] = aov_type
    return found


def sync_aovs(scene, found_aovs):
    state = scene.qp_aov_state
    try:
        managed = set(json.loads(state.managed_aovs))
    except (json.JSONDecodeError, AttributeError):
        managed = set()

    for vl in scene.view_layers:
        existing = {aov.name: (i, aov.type) for i, aov in enumerate(vl.aovs)}

        for name, aov_type in found_aovs.items():
            if name not in existing:
                new_aov = vl.aovs.add()
                new_aov.name = name
                new_aov.type = aov_type
                managed.add(name)
            elif name in managed and existing[name][1] != aov_type:
                vl.aovs[existing[name][0]].type = aov_type

        for name in list(managed):
            if name not in found_aovs:
                aov = vl.aovs.get(name)
                if aov:
                    vl.aovs.remove(aov)

    managed = (managed - {n for n in managed if n not in found_aovs}) | set(found_aovs.keys())
    state.managed_aovs = json.dumps(sorted(managed))


class QP_AOVManager:
    @staticmethod
    def is_enabled():
        try:
            prefs = bpy.context.preferences.addons[__package__].preferences
            return getattr(prefs, "aov_manager_enabled", True)
        except (KeyError, AttributeError):
            return True

    @classmethod
    def run_sync(cls):
        if not cls.is_enabled():
            return
        scene = bpy.context.scene
        if scene is None:
            return
        found = scan_all_materials()
        sync_aovs(scene, found)


@persistent
def _aov_depsgraph_handler(scene, depsgraph):
    global _pending_update
    if _pending_update:
        return
    if not any(update.id.__class__.__name__ in ('Material', 'ShaderNodeTree') for update in depsgraph.updates):
        return
    _pending_update = True
    bpy.app.timers.register(_deferred_sync, first_interval=0.2)


def _deferred_sync():
    global _pending_update
    _pending_update = False
    try:
        QP_AOVManager.run_sync()
    except Exception as e:
        print(f"[QP AOV Manager] Sync error: {e}")
    return None


@persistent
def _aov_load_post_handler(dummy):
    global _pending_update
    _pending_update = False
    QP_AOVManager.run_sync()


class QP_AOV_MANAGER_OT_sync(bpy.types.Operator):
    bl_idname = "qp.sync_aovs"
    bl_label = "Sync AOVs"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        found = scan_all_materials()
        sync_aovs(context.scene, found)
        self.report({'INFO'}, f"Synced {len(found)} AOV(s)")
        return {'FINISHED'}


classes = (
    QP_AOVManagerState,
    QP_AOV_MANAGER_OT_sync,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    if not hasattr(bpy.types.Scene, 'qp_aov_state'):
        bpy.types.Scene.qp_aov_state = bpy.props.PointerProperty(type=QP_AOVManagerState)

    if _aov_depsgraph_handler not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_aov_depsgraph_handler)
    if _aov_load_post_handler not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_aov_load_post_handler)

    bpy.app.timers.register(lambda: _deferred_sync() or None, first_interval=0.3)


def unregister():
    if _aov_depsgraph_handler in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_aov_depsgraph_handler)
    if _aov_load_post_handler in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_aov_load_post_handler)

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
