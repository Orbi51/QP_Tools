import bpy
import sys
import bmesh
from bpy.types import Operator
from bpy.props import FloatProperty, IntProperty

from .module_helper import ModuleManager

# Module state variables
module_enabled = True
_is_registered = False

class QP_OT_BevelWeight(Operator):
    """Set bevel weight for selected vertices/edges with interactive feedback"""
    bl_idname = "qp.bevel_weight"
    bl_label = "QP Bevel Weight"
    bl_options = {'REGISTER', 'UNDO'}

    weight: FloatProperty(
        name="Weight",
        description="Bevel weight value",
        min=0.0,
        max=1.0,
        default=0.5,
        subtype='FACTOR'
    )

    segments: IntProperty(
        name="Segments",
        description="Number of segments for the bevel modifier",
        min=1,
        max=100,
        default=1
    )

    initial_weight = 0.0
    initial_mouse_x = 0
    obj = None
    bm = None
    selected_vert_indices = []
    selected_edge_indices = []
    active_mode = 'EDGE'  # Will be set to VERT or EDGE based on selection
    bevel_modifier = None  # Store the associated bevel modifier

    @classmethod
    def poll(cls, context):
        return module_enabled and context.active_object is not None and context.active_object.type == 'MESH' and context.mode == 'EDIT_MESH'

    def invoke(self, context, event):
        self.obj = context.active_object
        mesh = self.obj.data
        
        # Get BMesh to find selected elements
        self.bm = bmesh.from_edit_mesh(mesh)
        self.bm.verts.ensure_lookup_table()
        self.bm.edges.ensure_lookup_table()
        
        # Store indices of selected vertices and edges
        self.selected_vert_indices = [vert.index for vert in self.bm.verts if vert.select]
        self.selected_edge_indices = [edge.index for edge in self.bm.edges if edge.select]
        
        # Determine which mode to use based on current edit mode
        current_mode = context.tool_settings.mesh_select_mode[:]
        if current_mode[0]:  # Vertex mode
            self.active_mode = 'VERT'
        else:
            # Edge or Face mode (both use edge bevel weights)
            self.active_mode = 'EDGE'
            
        # Check if we have a valid selection based on the active mode
        if self.active_mode == 'VERT':
            if not self.selected_vert_indices:
                self.report({'WARNING'}, "No vertices selected")
                return {'CANCELLED'}
        else:  # EDGE mode
            if not self.selected_edge_indices:
                self.report({'WARNING'}, "No edges selected")
                return {'CANCELLED'}
        
        # Ensure the appropriate attribute exists
        attr_name = "bevel_weight_vert" if self.active_mode == 'VERT' else "bevel_weight_edge"
        domain = 'POINT' if self.active_mode == 'VERT' else 'EDGE'
        
        if attr_name not in mesh.attributes:
            mesh.attributes.new(name=attr_name, type='FLOAT', domain=domain)
        
        # We need to briefly switch to object mode to sample the attribute
        bpy.ops.object.mode_set(mode='OBJECT')
        
        # Get the initial weight
        attr = mesh.attributes[attr_name]
        indices = self.selected_vert_indices if self.active_mode == 'VERT' else self.selected_edge_indices
        
        if len(attr.data) > 0 and indices:
            self.initial_weight = attr.data[indices[0]].value
        else:
            self.initial_weight = 0.0
            
        # Switch back to edit mode
        bpy.ops.object.mode_set(mode='EDIT')
        
        self.weight = self.initial_weight
        self.initial_mouse_x = event.mouse_x
        
        # Add a header message with instruction
        mode_text = "vertex" if self.active_mode == 'VERT' else "edge"
        context.workspace.status_text_set(f"Move mouse left/right to change {mode_text} bevel weight. "
                                           f"Mouse wheel to adjust segments. "
                                           f"LMB: Confirm, RMB/ESC: Cancel, Left/Right arrows: Adjust")
        
        # Check and add bevel modifier if needed
        self.bevel_modifier = self.add_bevel_modifier(context)
        
        # Set initial segments from the modifier
        if self.bevel_modifier:
            self.segments = self.bevel_modifier.segments
        
        # Update the bevel weight once at the start
        self.update_bevel_weight(context)
        
        # Begin modal operation
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}
    
    def update_bevel_weight(self, context):
        mesh = self.obj.data
        
        # We need to switch to object mode to update attributes
        bpy.ops.object.mode_set(mode='OBJECT')
        
        # Update the appropriate attribute
        attr_name = "bevel_weight_vert" if self.active_mode == 'VERT' else "bevel_weight_edge"
        attr = mesh.attributes[attr_name]
        
        indices = self.selected_vert_indices if self.active_mode == 'VERT' else self.selected_edge_indices
        for idx in indices:
            if idx < len(attr.data):
                attr.data[idx].value = self.weight
        
        # Switch back to edit mode
        bpy.ops.object.mode_set(mode='EDIT')
        
        # Update the mesh to see changes
        self.bm = bmesh.from_edit_mesh(mesh)
        bmesh.update_edit_mesh(mesh)

    def add_bevel_modifier(self, context):
        """Add a bevel modifier if one matching the current mode doesn't already exist
        
        Returns:
            The bevel modifier (either existing or newly created)
        """
        obj = self.obj
        
        # Determine the affect mode based on active_mode
        affect_mode = 'VERTICES' if self.active_mode == 'VERT' else 'EDGES'
        
        # Check if object already has a bevel modifier with the right affect mode
        for mod in obj.modifiers:
            if mod.type == 'BEVEL':
                # Check if this is a matching bevel modifier
                if mod.affect == affect_mode:
                    # Ensure it's set to use weights
                    if mod.limit_method != 'WEIGHT':
                        mod.limit_method = 'WEIGHT'
                        self.report({'INFO'}, f"Updated existing {affect_mode.lower()} Bevel modifier to use Weight mode")
                    return mod
        
        # Add a bevel modifier if no matching one exists
        # Create a name based on the affect mode
        name = "Bevel_Vertices" if affect_mode == 'VERTICES' else "Bevel_Edges"
        
        bevel_mod = obj.modifiers.new(name=name, type='BEVEL')
        bevel_mod.limit_method = 'WEIGHT'
        bevel_mod.affect = affect_mode
        bevel_mod.width = 0.5
        bevel_mod.segments = 1
        bevel_mod.profile = 0.5
            
        self.report({'INFO'}, f"Added {affect_mode.lower()} Bevel modifier set to Weight mode")
        return bevel_mod
    
    def update_segments(self):
        """Update the segments count in the active bevel modifier"""
        if self.bevel_modifier:
            self.bevel_modifier.segments = self.segments
    
    def modal(self, context, event):
        if event.type == 'MOUSEMOVE':
            # Adjust weight based on mouse movement
            delta = event.mouse_x - self.initial_mouse_x
            self.weight = max(0.0, min(1.0, self.initial_weight + delta * 0.005))
            
            # Update UI
            type_text = "Vertex" if self.active_mode == 'VERT' else "Edge"
            context.area.header_text_set(f"{type_text} Bevel Weight: {self.weight:.2f} | Segments: {self.segments}")
            
            # Update the mesh
            self.update_bevel_weight(context)
            
            return {'RUNNING_MODAL'}
            
        # Keyboard adjustment for more precise control
        elif event.type in {'LEFT_ARROW', 'RIGHT_ARROW'} and event.value == 'PRESS':
            increment = 0.1 if event.shift else 0.01
            if event.type == 'LEFT_ARROW':
                self.weight = max(0.0, self.weight - increment)
            else:
                self.weight = min(1.0, self.weight + increment)
                
            # Update UI
            type_text = "Vertex" if self.active_mode == 'VERT' else "Edge"
            context.area.header_text_set(f"{type_text} Bevel Weight: {self.weight:.2f} | Segments: {self.segments}")
            
            # Update the mesh
            self.update_bevel_weight(context)
            
            return {'RUNNING_MODAL'}
            
        # Mouse wheel to adjust segments
        elif event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'} and event.value == 'PRESS':
            if event.type == 'WHEELUPMOUSE':
                self.segments = min(100, self.segments + 1)
            else:
                self.segments = max(1, self.segments - 1)
            
            # Update UI
            type_text = "Vertex" if self.active_mode == 'VERT' else "Edge"
            context.area.header_text_set(f"{type_text} Bevel Weight: {self.weight:.2f} | Segments: {self.segments}")
            
            # Update the modifier
            self.update_segments()
            
            return {'RUNNING_MODAL'}
            
        elif event.type == 'LEFTMOUSE':
            # Accept and finish
            context.area.header_text_set(None)
            context.workspace.status_text_set(None)
            return {'FINISHED'}
            
        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            # Restore original weight and cancel
            self.weight = self.initial_weight
            self.update_bevel_weight(context)
            
            context.area.header_text_set(None)
            context.workspace.status_text_set(None)
            return {'CANCELLED'}
        
        return {'RUNNING_MODAL'}

    def execute(self, context):
        # This gets called when using redo/undo
        self.update_bevel_weight(context)
        self.update_segments()
        return {'FINISHED'}

def register():
    if not ModuleManager.register_module(sys.modules[__name__]):
        return
        
    ModuleManager.safe_register_class(QP_OT_BevelWeight)

def unregister():
    if not ModuleManager.unregister_module(sys.modules[__name__]):
        return
        
    ModuleManager.safe_unregister_class(QP_OT_BevelWeight)

if __name__ == "__main__":
    register()