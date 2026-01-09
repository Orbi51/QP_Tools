import bpy
import sys
from bpy.types import Operator
from mathutils import Vector

from .module_helper import ModuleManager

# Global module state, will be set by __init__.py
module_enabled = True
_is_registered = False

class QP_OT_LatticeSetup(Operator):
    """Create a lattice around selected objects and add lattice modifiers"""
    bl_idname = "qp.lattice_setup"
    bl_label = "Add Lattice"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return module_enabled and context.selected_objects and context.mode == 'OBJECT'

    def get_bounds(self, objects):
        """Calculate the bounding box for all selected objects"""
        min_co = Vector((float('inf'),) * 3)
        max_co = Vector((float('-inf'),) * 3)
        
        for obj in objects:
            if hasattr(obj, 'bound_box') and obj.bound_box:
                for v in obj.bound_box:
                    world_co = obj.matrix_world @ Vector(v)
                    min_co = Vector(min(a, b) for a, b in zip(min_co, world_co))
                    max_co = Vector(max(a, b) for a, b in zip(max_co, world_co))
            else:
                loc = obj.matrix_world.translation
                min_co = Vector(min(a, b) for a, b in zip(min_co, loc))
                max_co = Vector(max(a, b) for a, b in zip(max_co, loc))
        
        return min_co, max_co

    def is_compatible(self, obj):
        """Check if object can have a lattice modifier"""
        standard_types = {'MESH', 'CURVE', 'SURFACE', 'FONT', 'LATTICE'}
        
        # Standard objects
        if obj.type in standard_types:
            return True
            
        # Grease Pencil objects (any naming)
        if obj.type in {'GREASEPENCIL', 'GPENCIL'}:
            return True
            
        # Blender 4.3+ Grease Pencil strokes
        if obj.type == 'CURVES':
            return True
            
        return False

    def add_lattice_modifier(self, obj, lattice_obj):
        """Add lattice modifier based on object type and Blender version"""
        is_blender_4_3_plus = bpy.app.version >= (4, 3, 0)
        
        # Store the current active object to restore later
        current_active = bpy.context.view_layer.objects.active
        
        # Set this object as active to ensure modifier operators work correctly
        bpy.context.view_layer.objects.active = obj
        
        # Find the index of the first Geometry Nodes modifier, if any
        geo_node_index = -1
        for i, mod in enumerate(obj.modifiers):
            if mod.type == 'NODES':
                geo_node_index = i
                break
        
        try:
            # Standard objects - consistent across versions
            if obj.type in {'MESH', 'CURVE', 'SURFACE', 'FONT', 'LATTICE'}:
                try:
                    modifier = obj.modifiers.new(name="Lattice", type='LATTICE')
                    if modifier:
                        modifier.object = lattice_obj
                        
                        # Move before geometry nodes if needed
                        if geo_node_index >= 0:
                            # For each position after the geo nodes, move up once
                            for i in range(len(obj.modifiers) - 1, geo_node_index, -1):
                                if obj.modifiers[i].name == modifier.name:
                                    bpy.ops.object.modifier_move_up(modifier=modifier.name)
                        
                        return True
                except Exception as e:
                    print(f"Error adding standard lattice modifier: {e}")
                    return False
            
            # Grease Pencil in Blender 4.3+
            elif is_blender_4_3_plus and obj.type == 'GREASEPENCIL':
                try:
                    # For Grease Pencil in 4.3+, use 'GREASE_PENCIL_LATTICE' type
                    modifier = obj.modifiers.new(name="Lattice", type='GREASE_PENCIL_LATTICE')
                    if modifier:
                        modifier.object = lattice_obj
                        
                        # Move before geometry nodes if needed
                        if geo_node_index >= 0:
                            # For each position after the geo nodes, move up once
                            for i in range(len(obj.modifiers) - 1, geo_node_index, -1):
                                if obj.modifiers[i].name == modifier.name:
                                    bpy.ops.object.modifier_move_up(modifier=modifier.name)
                        
                        return True
                except Exception as e:
                    print(f"Error adding Blender 4.3+ GP lattice modifier: {e}")
                    return False
                    
            # Curves or other objects in 4.3+
            elif is_blender_4_3_plus and obj.type == 'CURVES':
                try:
                    modifier = obj.modifiers.new(name="Lattice", type='LATTICE')
                    if modifier:
                        modifier.object = lattice_obj
                        
                        # Move before geometry nodes if needed
                        if geo_node_index >= 0:
                            # For each position after the geo nodes, move up once
                            for i in range(len(obj.modifiers) - 1, geo_node_index, -1):
                                if obj.modifiers[i].name == modifier.name:
                                    bpy.ops.object.modifier_move_up(modifier=modifier.name)
                        
                        return True
                except Exception as e:
                    print(f"Error adding Blender 4.3+ CURVES lattice modifier: {e}")
                    return False
                    
            # Legacy Grease Pencil (4.1-4.2)
            elif obj.type in {'GPENCIL'} and hasattr(obj, 'grease_pencil_modifiers'):
                try:
                    modifier = obj.grease_pencil_modifiers.new(name="Lattice", type='GREASE_PENCIL_LATTICE')
                    if modifier:
                        modifier.object = lattice_obj
                        
                        # For GP modifiers we need to check the grease_pencil_modifiers collection
                        gp_geo_node_index = -1
                        for i, mod in enumerate(obj.grease_pencil_modifiers):
                            if mod.type == 'GP_MODIFIER_LINEART' or "NODES" in mod.type:
                                gp_geo_node_index = i
                                break
                        
                        if gp_geo_node_index >= 0:
                            # Move modifier up in GP stack
                            for i in range(len(obj.grease_pencil_modifiers) - 1, gp_geo_node_index, -1):
                                if obj.grease_pencil_modifiers[i].name == modifier.name:
                                    bpy.ops.object.gpencil_modifier_move_up(modifier=modifier.name)
                        
                        return True
                except Exception as e:
                    print(f"Error adding legacy GP lattice modifier: {e}")
                    return False
                    
            return False
        
        finally:
            # Restore the original active object
            bpy.context.view_layer.objects.active = current_active

    def execute(self, context):
        selected_objects = context.selected_objects
        
        if not selected_objects:
            self.report({'ERROR'}, "No objects selected")
            return {'CANCELLED'}

        # Find compatible objects
        compatible_objects = [obj for obj in selected_objects if self.is_compatible(obj)]
        incompatible_objects = [obj for obj in selected_objects if obj not in compatible_objects]
        
        if not compatible_objects:
            self.report({'ERROR'}, "No compatible objects selected. Lattices can be applied to Mesh, Curve, Surface, Text, Lattice, and Grease Pencil objects.")
            return {'CANCELLED'}

        # Calculate bounds of all compatible objects
        min_co, max_co = self.get_bounds(compatible_objects)
        
        # Create lattice object
        lattice_data = bpy.data.lattices.new(name="Deform_Lattice")
        lattice_obj = bpy.data.objects.new(name="Deform_Lattice", object_data=lattice_data)
        context.scene.collection.objects.link(lattice_obj)
        
        # Calculate dimensions
        dimensions = max_co - min_co
        
        # Handle zero or near-zero dimensions
        min_dimension = 0.001  # Minimum dimension to prevent zero scale
        original_dimensions = dimensions.copy()  # Store original dimensions for center calculation
        
        # Track which axes were adjusted for centering calculation
        adjusted_axes = [False, False, False]  # x, y, z
        
        # Check for near-zero dimensions and set appropriate resolution
        if dimensions.x < min_dimension:
            lattice_data.points_u = 1  # Set resolution to 1 for x-axis
            dimensions.x = 1.0  # Set dimension to 1.0 instead of zero/near-zero
            adjusted_axes[0] = True
        else:
            lattice_data.points_u = 2  # Default resolution for x-axis
            
        if dimensions.y < min_dimension:
            lattice_data.points_v = 1  # Set resolution to 1 for y-axis
            dimensions.y = 1.0  # Set dimension to 1.0 instead of zero/near-zero
            adjusted_axes[1] = True
        else:
            lattice_data.points_v = 2  # Default resolution for y-axis
            
        if dimensions.z < min_dimension:
            lattice_data.points_w = 1  # Set resolution to 1 for z-axis
            dimensions.z = 1.0  # Set dimension to 1.0 instead of zero/near-zero
            adjusted_axes[2] = True
        else:
            lattice_data.points_w = 2  # Default resolution for z-axis
        
        # Apply dimensions
        lattice_obj.dimensions = dimensions
        
        # Calculate center position correctly for adjusted axes
        center_position = Vector((0, 0, 0))
        
        for i, axis in enumerate(['x', 'y', 'z']):
            if adjusted_axes[i]:
                # For adjusted axes, use the average of min and max
                center_position[i] = (getattr(min_co, axis) + getattr(max_co, axis)) / 2
            else:
                # For normal axes, use the standard calculation
                center_position[i] = getattr(min_co, axis) + getattr(original_dimensions, axis) / 2
        
        # Handle rotation - if only one compatible object is selected, match its rotation
        if len(compatible_objects) == 1:
            single_obj = compatible_objects[0]
            
            # Set rotation to match the object's rotation
            lattice_obj.rotation_euler = single_obj.rotation_euler.copy()
            
            # If object has rotation, we need to adjust the center position
            # to account for the object's local space
            if (single_obj.rotation_euler.x != 0 or 
                single_obj.rotation_euler.y != 0 or 
                single_obj.rotation_euler.z != 0):
                
                # Get object's world matrix to convert from local to world space
                obj_matrix = single_obj.matrix_world
                
                # Get object's center in world space
                obj_center = obj_matrix @ Vector((0, 0, 0))
                
                # Set lattice position to object's center
                lattice_obj.location = obj_center
                
                # Calculate and set lattice dimensions based on object's local scale
                # This ensures the lattice covers the object in local space
                if hasattr(single_obj, 'dimensions'):
                    # Add margin around the object (10% on each side)
                    margin = 1.1
                    
                    local_dims = single_obj.dimensions
                    
                    # Handle zero dimensions
                    if local_dims.x < min_dimension:
                        lattice_data.points_u = 1
                        local_dims.x = 1.0
                    
                    if local_dims.y < min_dimension:
                        lattice_data.points_v = 1
                        local_dims.y = 1.0
                    
                    if local_dims.z < min_dimension:
                        lattice_data.points_w = 1
                        local_dims.z = 1.0
                    
                    # Apply scaled dimensions
                    lattice_obj.dimensions = local_dims * margin
                else:
                    # If we can't get object dimensions, use the calculated dimensions
                    lattice_obj.location = center_position
            else:
                # No rotation, use the calculated center position
                lattice_obj.location = center_position
        else:
            # Multiple objects selected, just use the calculated center position
            lattice_obj.location = center_position
        
        # Add lattice modifier to all compatible objects
        success_objects = []
        failed_objects = []
        
        for obj in compatible_objects:
            if self.add_lattice_modifier(obj, lattice_obj):
                success_objects.append(obj)
            else:
                failed_objects.append(obj)
        
        # Select the lattice for easier manipulation
        for obj in context.selected_objects:
            obj.select_set(False)
        lattice_obj.select_set(True)
        context.view_layer.objects.active = lattice_obj
        
        # Report results
        message_parts = []
        
        if incompatible_objects:
            names = ", ".join([obj.name for obj in incompatible_objects[:3]])
            if len(incompatible_objects) > 3:
                names += f" and {len(incompatible_objects) - 3} more"
            message_parts.append(f"Skipped incompatible objects: {names}")
            
        if failed_objects:
            names = ", ".join([obj.name for obj in failed_objects[:3]])
            if len(failed_objects) > 3:
                names += f" and {len(failed_objects) - 3} more"
            message_parts.append(f"Failed to add lattice to: {names}")
        
        if message_parts:
            self.report({'WARNING' if failed_objects else 'INFO'}, 
                        f"Lattice setup complete. {' '.join(message_parts)}")
        else:
            self.report({'INFO'}, "Lattice setup complete")
        
        return {'FINISHED'}


def register():
    if not ModuleManager.register_module(sys.modules[__name__]):
        return
    
    ModuleManager.safe_register_class(QP_OT_LatticeSetup)

def unregister():
    if not ModuleManager.unregister_module(sys.modules[__name__]):
        return
    
    ModuleManager.safe_unregister_class(QP_OT_LatticeSetup)

if __name__ == "__main__":
    register()