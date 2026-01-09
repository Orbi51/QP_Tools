import bpy
import sys
from bpy.types import Operator, Panel
from bpy.props import EnumProperty, StringProperty
from mathutils import Vector

from .module_helper import ModuleManager

# Module state variables
module_enabled = True
_is_registered = False

class OBJECT_OT_set_collection_offset(Operator):
    bl_idname = "object.set_collection_offset"
    bl_label = "Set Collection Offset"
    bl_options = {'REGISTER', 'UNDO'}
    
    offset_type: EnumProperty(
        items=[
            ('CENTER', "Center of Selection", "Set offset to center of selected objects"),
            ('BOTTOM', "Bottom of Selection", "Set offset to bottom center of selected objects"),
            ('ACTIVE', "Active Object", "Set offset to active object's position"),
            ('CURSOR', "3D Cursor", "Set offset to 3D cursor position")
        ],
        name="Offset Type",
        description="Choose the type of offset",
        default='CENTER'
    )

    collection_to_update: StringProperty(
        name="Collection to Update",
        description="Name of the collection to update",
        default=""
    )

    @classmethod
    def poll(cls, context):
        return module_enabled and context.selected_objects

    def execute(self, context):
        selected_objects = context.selected_objects
        active_object = context.active_object
        
        if not selected_objects:
            self.report({'ERROR'}, "No objects selected")
            return {'CANCELLED'}
        
        if self.offset_type == 'ACTIVE' and not active_object:
            self.report({'ERROR'}, "No active object")
            return {'CANCELLED'}
        
        # Get unique collections of selected objects
        collections = set(coll for obj in selected_objects for coll in obj.users_collection)
        
        if len(collections) > 1 and not self.collection_to_update:
            # Multiple collections found, but no collection specified yet
            return context.window_manager.invoke_props_dialog(self)
        
        if self.collection_to_update:
            # Use the specified collection
            collection = bpy.data.collections.get(self.collection_to_update)
        else:
            # Use the single collection found
            collection = list(collections)[0]
        
        if not collection:
            self.report({'ERROR'}, "Invalid collection")
            return {'CANCELLED'}
        
        if self.offset_type == 'ACTIVE':
            offset = active_object.location
        elif self.offset_type == 'CURSOR':
            offset = context.scene.cursor.location
        elif len(selected_objects) == 1:
            offset = selected_objects[0].location
        else:
            if self.offset_type == 'CENTER':
                offset = self.get_selection_center(selected_objects)
            else:  # BOTTOM
                offset = self.get_selection_bottom(selected_objects)
        
        # Set the collection offset
        collection.instance_offset = offset
        
        self.report({'INFO'}, f"Collection '{collection.name}' offset set to {offset}")
        return {'FINISHED'}

    def invoke(self, context, event):
        # Always show the popup dialog to let users choose the offset type
        # and collection (if multiple collections are present)
        return context.window_manager.invoke_props_dialog(self, width=200)

    def draw(self, context):
        layout = self.layout
        selected_objects = context.selected_objects
        collections = set(coll for obj in selected_objects for coll in obj.users_collection)
        
        if len(collections) > 1:
            layout.prop_search(self, "collection_to_update", bpy.data, "collections", text="Collection")
        
        layout.prop(self, "offset_type")

    def get_selection_center(self, objects):
        bounds = self.get_bounds(objects)
        return (bounds[0] + bounds[1]) / 2

    def get_selection_bottom(self, objects):
        bounds = self.get_bounds(objects)
        center = (bounds[0] + bounds[1]) / 2
        return Vector((center.x, center.y, bounds[0].z))

    def get_bounds(self, objects):
        min_co = Vector((float('inf'),) * 3)
        max_co = Vector((float('-inf'),) * 3)
        
        for obj in objects:
            for v in obj.bound_box:
                world_co = obj.matrix_world @ Vector(v)
                min_co = Vector(min(a, b) for a, b in zip(min_co, world_co))
                max_co = Vector(max(a, b) for a, b in zip(max_co, world_co))
        
        return min_co, max_co

def register():
    if not ModuleManager.register_module(sys.modules[__name__]):
        return
        
    ModuleManager.safe_register_class(OBJECT_OT_set_collection_offset)

def unregister():
    if not ModuleManager.unregister_module(sys.modules[__name__]):
        return
        
    ModuleManager.safe_unregister_class(OBJECT_OT_set_collection_offset)

if __name__ == "__main__":
    register()