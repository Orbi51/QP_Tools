import bpy
import sys
from bpy.types import Operator
from bpy.props import StringProperty, EnumProperty, BoolProperty

from .module_helper import ModuleManager

# Module state variables
module_enabled = True
_is_registered = False

def get_vertex_groups(self, context):
    obj = context.object
    return [(group.name, group.name, "") for group in obj.vertex_groups]

def get_unused_vertex_groups(obj):
    unused_groups = []
    for group in obj.vertex_groups:
        if not any(group.index in [g.group for g in v.groups] for v in obj.data.vertices):
            unused_groups.append(group.name)
    return unused_groups

class QP_OT_AssignVGroup(Operator):
    """Assign or remove selected vertices/edges to/from a vertex group, and update related modifiers if found"""
    bl_idname = "object.qp_assign_vgroup"
    bl_label = "Assign VGroup"
    bl_options = {'REGISTER', 'UNDO'}

    vertex_group_name: StringProperty(
        name="Vertex Group Name",
        description="Name of the vertex group to use",
        default="VGroup"
    )

    vertex_group_enum: EnumProperty(
        name="Existing Vertex Groups",
        description="Choose an existing vertex group",
        items=get_vertex_groups,
    )

    use_existing_group: BoolProperty(
        name="Use Existing Group",
        description="Choose an existing vertex group instead of creating a new one",
        default=False
    )

    remove_unused_groups: BoolProperty(
        name="Remove Unused Vertex Groups",
        description="Remove all vertex groups with no assigned vertices",
        default=False
    )

    @classmethod
    def poll(cls, context):
        return module_enabled and context.object is not None and context.object.type == 'MESH' and context.mode == 'EDIT_MESH'

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "use_existing_group")
        if self.use_existing_group:
            layout.prop(self, "vertex_group_enum")
        else:
            layout.prop(self, "vertex_group_name")
        layout.prop(self, "remove_unused_groups")

    def execute(self, context):
        obj = context.object

        # Get current selection mode
        sel_mode = context.tool_settings.mesh_select_mode[:]
        is_vert_mode = sel_mode[0]
        is_edge_mode = sel_mode[1]
        
        # Get or create the vertex group
        if self.use_existing_group:
            vg_name = self.vertex_group_enum
            vg = obj.vertex_groups.get(vg_name)
            if vg is None:
                self.report({'ERROR'}, f"Vertex group '{vg_name}' not found.")
                return {'CANCELLED'}
        else:
            vg_name = self.vertex_group_name
            vg = obj.vertex_groups.get(vg_name)
            if vg is None:
                vg = obj.vertex_groups.new(name=vg_name)

        # Switch to object mode to modify vertex groups
        bpy.ops.object.mode_set(mode='OBJECT')

        # Handle assignment
        mesh = obj.data
        assigned_verts = set(v.index for v in mesh.vertices if vg.index in [g.group for g in v.groups])
        
        if is_edge_mode:
            # Process edges
            selected_edges = [e for e in mesh.edges if e.select]
            
            to_assign = []
            to_remove = []
            all_assigned = True

            for edge in selected_edges:
                v1, v2 = edge.vertices
                if v1 in assigned_verts and v2 in assigned_verts:
                    to_remove.extend([v1, v2])
                else:
                    all_assigned = False
                    if v1 not in assigned_verts or v2 not in assigned_verts:
                        to_assign.extend([v1, v2])

            if not all_assigned and to_assign:
                vg.add(to_assign, 1.0, 'REPLACE')
                self.report({'INFO'}, f"Assigned {len(to_assign)//2} edges to {vg_name} group")
            elif all_assigned and to_remove:
                vg.remove(to_remove)
                self.report({'INFO'}, f"Removed {len(to_remove)//2} edges from {vg_name} group")
            else:
                self.report({'INFO'}, f"No changes made to {vg_name} group")
                
        elif is_vert_mode:
            # Process vertices
            selected_verts = [v.index for v in mesh.vertices if v.select]
            
            to_assign = []
            to_remove = []
            all_assigned = True
            
            for v_idx in selected_verts:
                if v_idx in assigned_verts:
                    to_remove.append(v_idx)
                else:
                    all_assigned = False
                    to_assign.append(v_idx)
                    
            if not all_assigned and to_assign:
                vg.add(to_assign, 1.0, 'REPLACE')
                self.report({'INFO'}, f"Assigned {len(to_assign)} vertices to {vg_name} group")
            elif all_assigned and to_remove:
                vg.remove(to_remove)
                self.report({'INFO'}, f"Removed {len(to_remove)} vertices from {vg_name} group")
            else:
                self.report({'INFO'}, f"No changes made to {vg_name} group")
        else:
            # Face selection or other - not supported
            self.report({'INFO'}, "Please use vertex or edge selection mode")

        # Update the selected modifier's vertex group if exists
        selected_modifier = obj.modifiers.active
        if selected_modifier:
            if selected_modifier.type == 'NODES':
                if hasattr(selected_modifier, 'node_group') and selected_modifier.node_group:
                    for node in selected_modifier.node_group.nodes:
                        if node.type == 'GROUP_INPUT':
                            for socket in node.outputs:
                                if socket.name == "Vertex Group" or socket.bl_label == "Vertex Group":
                                    socket_id = socket.identifier
                                    selected_modifier[socket_id] = vg_name
                                    self.report({'INFO'}, f"Updated Vertex Group for Geometry Nodes socket: {socket.name}")
                                    break
            else:
                # Handle other modifier types
                if hasattr(selected_modifier, 'vertex_group'):
                    selected_modifier.vertex_group = vg_name
                    self.report({'INFO'}, f"Updated vertex group for {selected_modifier.type} modifier.")

        # Remove unused vertex groups if option is selected
        if self.remove_unused_groups:
            unused_groups = get_unused_vertex_groups(obj)
            for group_name in unused_groups:
                group = obj.vertex_groups.get(group_name)
                if group:
                    obj.vertex_groups.remove(group)
            self.report({'INFO'}, f"Removed {len(unused_groups)} unused vertex groups.")

        # Switch back to edit mode
        bpy.ops.object.mode_set(mode='EDIT')

        return {'FINISHED'}

def register():
    if not ModuleManager.register_module(sys.modules[__name__]):
        return
        
    ModuleManager.safe_register_class(QP_OT_AssignVGroup)

def unregister():
    if not ModuleManager.unregister_module(sys.modules[__name__]):
        return
        
    ModuleManager.safe_unregister_class(QP_OT_AssignVGroup)

if __name__ == "__main__":
    register()