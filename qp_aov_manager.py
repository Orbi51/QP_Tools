import bpy
import json
from bpy.props import StringProperty


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
        try:
            node_type = node.type
        except (ReferenceError, SystemError, AttributeError):
            continue
        if node_type == 'OUTPUT_AOV':
            try:
                name = node.aov_name
                if name:
                    aov_type = 'VALUE' if node.inputs[1].is_linked else 'COLOR'
                    if name not in result or aov_type == 'VALUE':
                        result[name] = aov_type
            except (ReferenceError, SystemError, AttributeError):
                continue
        elif node_type == 'GROUP':
            try:
                sub_tree = node.node_tree
            except (ReferenceError, SystemError, AttributeError):
                continue
            if sub_tree:
                nested = find_aov_nodes_recursive(sub_tree, visited)
                for name, aov_type in nested.items():
                    if name not in result or aov_type == 'VALUE':
                        result[name] = aov_type
    return result


def scan_all_materials():
    found = {}
    for mat in bpy.data.materials:
        try:
            if not mat.use_nodes or not mat.node_tree:
                continue
            mat_aovs = find_aov_nodes_recursive(mat.node_tree)
        except (ReferenceError, SystemError, AttributeError):
            continue
        for name, aov_type in mat_aovs.items():
            if name not in found or aov_type == 'VALUE':
                found[name] = aov_type
    return found


def sync_aovs(scene, found_aovs):
    try:
        state = scene.qp_aov_state
        managed = set(json.loads(state.managed_aovs))
    except (ReferenceError, SystemError, AttributeError, json.JSONDecodeError):
        return

    try:
        view_layers = list(scene.view_layers)
    except (ReferenceError, SystemError, AttributeError):
        return

    for vl in view_layers:
        try:
            existing = {aov.name: (i, aov.type) for i, aov in enumerate(vl.aovs)}
        except (ReferenceError, SystemError, AttributeError):
            continue

        for name, aov_type in found_aovs.items():
            try:
                if name not in existing:
                    new_aov = vl.aovs.add()
                    new_aov.name = name
                    new_aov.type = aov_type
                    managed.add(name)
                elif name in managed and existing[name][1] != aov_type:
                    vl.aovs[existing[name][0]].type = aov_type
            except (ReferenceError, SystemError, AttributeError):
                continue

        for name in list(managed):
            if name not in found_aovs:
                try:
                    aov = vl.aovs.get(name)
                    if aov:
                        vl.aovs.remove(aov)
                except (ReferenceError, SystemError, AttributeError):
                    continue

    try:
        managed = (managed - {n for n in managed if n not in found_aovs}) | set(found_aovs.keys())
        state.managed_aovs = json.dumps(sorted(managed))
    except (ReferenceError, SystemError, AttributeError):
        pass


class QP_AOV_MANAGER_OT_sync(bpy.types.Operator):
    bl_idname = "qp.sync_aovs"
    bl_label = "Sync AOVs from Materials"
    bl_description = "Scan all materials for AOV Output nodes and sync them to view layer AOVs"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            prefs = context.preferences.addons[__package__].preferences
            if not getattr(prefs, "aov_manager_enabled", True):
                self.report({'WARNING'}, "AOV Manager is disabled in preferences")
                return {'CANCELLED'}
        except (KeyError, AttributeError):
            pass

        found = scan_all_materials()
        sync_aovs(context.scene, found)
        self.report({'INFO'}, f"Synced {len(found)} AOV(s)")
        return {'FINISHED'}


class VIEW_LAYER_PT_qp_aov_sync(bpy.types.Panel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'view_layer'
    bl_label = ""
    bl_parent_id = "VIEWLAYER_PT_layer_passes_aov"
    bl_options = {'HIDE_HEADER'}

    def draw(self, context):
        self.layout.operator("qp.sync_aovs", icon='FILE_REFRESH')


classes = (
    QP_AOVManagerState,
    QP_AOV_MANAGER_OT_sync,
    VIEW_LAYER_PT_qp_aov_sync,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    if not hasattr(bpy.types.Scene, 'qp_aov_state'):
        bpy.types.Scene.qp_aov_state = bpy.props.PointerProperty(type=QP_AOVManagerState)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
