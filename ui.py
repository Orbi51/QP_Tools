# ui.py
import bpy
import sys
from importlib import reload

# Import the module helper
from .module_helper import ModuleManager

# Import main module for state checking
from .module_state import is_module_enabled

# Module state variables
module_enabled = True  # UI module is always enabled
_is_registered = False  # Tracks registration state

# This function is commented out to remove the button from the top bar
# def view3d_asset_menu_func(self, context):
#     if is_module_enabled("assetlibs"):
#         self.layout.separator()
#         self.layout.menu("QP_MT_AssetLibraries", icon='ASSET_MANAGER')

class QP_MT_AssetLibraries(bpy.types.Menu):
    """QP Asset Libraries menu"""
    bl_label = "QP Asset Libraries"
    bl_idname = "QP_MT_AssetLibraries"

    def draw(self, context):
        layout = self.layout
        
        # If we have asset libraries in preferences, list them
        prefs = context.preferences.addons[__package__].preferences
        if hasattr(prefs, "asset_libraries"):
            libraries = prefs.asset_libraries
            
            if len(libraries) == 0:
                layout.label(text="No asset libraries available")
                layout.operator("assetlib.install_library", icon='IMPORT')
                return
            
            # Add install button at the top
            layout.operator("assetlib.install_library", icon='IMPORT')
            layout.separator()
            
            # List all libraries
            for library in libraries:
                op = layout.operator("assetlib.call_library_pie", text=library.name)
                op.library_name = library.name
        else:
            layout.label(text="Asset library system not initialized")
            layout.operator("assetlib.install_library", icon='IMPORT')

def shader_editor_menu_func(self, context):
    self.layout.separator()
    self.layout.menu("QP_MT_ShaderTools", icon='SHADERFX')

def view3d_menu_func(self, context):
    self.layout.separator()
    self.layout.menu("QP_MT_MeshTools", icon='MESH_DATA')

def object_menu_func(self, context):
    """Add QP Tools to the Object menu"""
    self.layout.separator()
    self.layout.menu("QP_MT_MeshTools", icon='MESH_DATA')

def context_menu_func(self, context):
    """Add QP Tools to the right-click context menu"""
    if context.active_object:
        self.layout.separator()
        self.layout.menu("QP_MT_MeshTools", icon='MESH_DATA')

class QP_MT_ShaderTools(bpy.types.Menu):
    """QP Shader Tools menu"""
    bl_label = "QP Shader Tools"
    bl_idname = "QP_MT_ShaderTools"

    def draw(self, context):
        layout = self.layout
        
        # Check which modules are enabled using the helper function
        if is_module_enabled("Project_Box_Flat"):
            layout.operator("qp.box_or_flat_mapping", icon='TEXTURE_DATA')
            layout.operator("qp.colorspace_menu", icon='COLOR')
            
        if is_module_enabled("TextureSet_builder"):
            layout.operator("node.pack_image_textures", icon='DOCUMENTS')
            
        if is_module_enabled("LinkNodeGroups"):
            layout.operator("node.node_group_linker", icon='NETWORK_DRIVE')
            
        layout.separator()

class QP_MT_MeshTools(bpy.types.Menu):
    """QP Mesh Tools menu"""
    bl_label = "QP Mesh Tools"
    bl_idname = "QP_MT_MeshTools"

    def draw(self, context):
        layout = self.layout
        
        # Check which modules are enabled using the helper function
        if is_module_enabled("EdgeSelect"):
            layout.operator("object.qp_assign_vgroup", icon='GROUP_VERTEX')
            
        if is_module_enabled("CollectionOffset"):
            layout.operator("object.set_collection_offset", icon='OBJECT_ORIGIN')
            
        if is_module_enabled("BevelWeight"):
            layout.operator("qp.bevel_weight", icon='MOD_BEVEL')
            
        if is_module_enabled("LatticeSetup"):
            layout.operator("qp.lattice_setup", icon='MOD_LATTICE')

        layout.separator()

def register():
    # Use ModuleManager to handle registration state
    if not ModuleManager.register_module(sys.modules[__name__]):
        return
    
    # Register classes
    ModuleManager.safe_register_class(QP_MT_ShaderTools)
    ModuleManager.safe_register_class(QP_MT_MeshTools)
    ModuleManager.safe_register_class(QP_MT_AssetLibraries)
    
    # Define menu functions list
    menu_functions = [
        (bpy.types.NODE_MT_context_menu, shader_editor_menu_func),
        (bpy.types.NODE_MT_node, shader_editor_menu_func),
        (bpy.types.VIEW3D_MT_edit_mesh_context_menu, view3d_menu_func),
        (bpy.types.VIEW3D_MT_object_context_menu, context_menu_func),
        (bpy.types.VIEW3D_MT_object, object_menu_func),
        # Removed the line below to remove the button from the top bar
        # (bpy.types.VIEW3D_MT_editor_menus, view3d_asset_menu_func),
    ]
    
    # Add menu functions
    for menu_type, func in menu_functions:
        ModuleManager.safe_append_menu(menu_type, func)
    

def unregister():
    # Use ModuleManager to handle unregistration state
    if not ModuleManager.unregister_module(sys.modules[__name__]):
        return
    
    # Define menu functions list
    menu_functions = [
        (bpy.types.NODE_MT_context_menu, shader_editor_menu_func),
        (bpy.types.NODE_MT_node, shader_editor_menu_func),
        (bpy.types.VIEW3D_MT_edit_mesh_context_menu, view3d_menu_func),
        (bpy.types.VIEW3D_MT_object_context_menu, context_menu_func),
        (bpy.types.VIEW3D_MT_object, object_menu_func),
        # Removed the line below to remove the button from the top bar
        # (bpy.types.VIEW3D_MT_editor_menus, view3d_asset_menu_func),
    ]
    
    # Remove menu functions
    for menu_type, func in menu_functions:
        ModuleManager.safe_remove_menu(menu_type, func)
    
    # Unregister classes in reverse order
    ModuleManager.safe_unregister_class(QP_MT_AssetLibraries)
    ModuleManager.safe_unregister_class(QP_MT_MeshTools)
    ModuleManager.safe_unregister_class(QP_MT_ShaderTools)
    
