import bpy
import sys
from bpy.types import Operator

from .module_helper import ModuleManager

# Module state variables
module_enabled = True
_is_registered = False

class QP_OT_BoxOrFlatMapping(Operator):
    """Provides a popup to set image texture projection to Box or Flat."""
    bl_idname = "qp.box_or_flat_mapping"
    bl_label = "Box or Flat Mapping"
    
    @classmethod
    def poll(cls, context):
        return module_enabled and context.area.type == 'NODE_EDITOR'

    def execute(self, context):
        context.window_manager.popup_menu(self.draw_menu, title="Projection Method", icon='NODE_SEL')
        return {'FINISHED'}

    def draw_menu(self, menu, context):
        menu.layout.operator(
            QP_OT_SetProjection.bl_idname, text="Box", icon='CUBE'
        ).projection = 'BOX'  
        menu.layout.operator(
            QP_OT_SetProjection.bl_idname, text="Flat", icon='MESH_PLANE'
        ).projection = 'FLAT'  

class QP_OT_SetProjection(Operator):
    """Sets the projection method of selected image texture nodes."""
    bl_idname = "qp.set_projection"
    bl_label = "Set Projection"
    bl_options = {'REGISTER', 'UNDO'}

    projection: bpy.props.StringProperty(  
        name="Projection",
        default='BOX',
        options={'HIDDEN'}  
    )

    @classmethod
    def poll(cls, context):
        return module_enabled and context.area.type == 'NODE_EDITOR'

    def execute(self, context):
        nodes = set()
        for node in context.selected_nodes:
            nodes.add(node)
            if node.type == 'GROUP':
                nodes.update(node.node_tree.nodes) 

        image_nodes = [n for n in nodes if n.type == 'TEX_IMAGE']

        if not image_nodes:
            self.report({'WARNING'}, "No image texture nodes selected or found in groups.")
            return {'CANCELLED'}

        for node in image_nodes:
            node.projection = self.projection

        return {'FINISHED'}

class QP_OT_ColorSpaceMenu(Operator):
    """Provides a popup to set image texture color space."""
    bl_idname = "qp.colorspace_menu"
    bl_label = "Color Space"
    
    @classmethod
    def poll(cls, context):
        return module_enabled and context.area.type == 'NODE_EDITOR'

    def execute(self, context):
        context.window_manager.popup_menu(self.draw_menu, title="Color Space", icon='NODE_SEL')
        return {'FINISHED'}

    def draw_menu(self, menu, context):
        menu.layout.operator(
            QP_OT_SetColorSpace.bl_idname, text="sRGB", icon='COLOR'
        ).colorspace = 'sRGB'  
        menu.layout.operator(
            QP_OT_SetColorSpace.bl_idname, text="Non-Color", icon='TEXTURE'
        ).colorspace = 'Non-Color'

class QP_OT_SetColorSpace(Operator):
    """Sets the color space of selected image texture nodes."""
    bl_idname = "qp.set_colorspace"
    bl_label = "Set Color Space"
    bl_options = {'REGISTER', 'UNDO'}

    colorspace: bpy.props.StringProperty(  
        name="Color Space",
        default='sRGB',
        options={'HIDDEN'}  
    )

    @classmethod
    def poll(cls, context):
        return module_enabled and context.area.type == 'NODE_EDITOR'

    def execute(self, context):
        nodes = set()
        for node in context.selected_nodes:
            nodes.add(node)
            if node.type == 'GROUP':
                nodes.update(node.node_tree.nodes) 

        image_nodes = [n for n in nodes if n.type == 'TEX_IMAGE' and n.image]

        if not image_nodes:
            self.report({'WARNING'}, "No image texture nodes with images selected or found in groups.")
            return {'CANCELLED'}

        for node in image_nodes:
            node.image.colorspace_settings.name = self.colorspace

        return {'FINISHED'}

def register():
    if not ModuleManager.register_module(sys.modules[__name__]):
        return
    
    ModuleManager.safe_register_class(QP_OT_BoxOrFlatMapping)
    ModuleManager.safe_register_class(QP_OT_SetProjection)
    ModuleManager.safe_register_class(QP_OT_ColorSpaceMenu)
    ModuleManager.safe_register_class(QP_OT_SetColorSpace)

def unregister():
    if not ModuleManager.unregister_module(sys.modules[__name__]):
        return
    
    ModuleManager.safe_unregister_class(QP_OT_SetColorSpace)
    ModuleManager.safe_unregister_class(QP_OT_ColorSpaceMenu)
    ModuleManager.safe_unregister_class(QP_OT_SetProjection)
    ModuleManager.safe_unregister_class(QP_OT_BoxOrFlatMapping)

if __name__ == "__main__":
    register()