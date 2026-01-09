# template_module.py
import bpy
from bpy.types import Operator, Panel

# Import the ModuleManager helper
from .module_helper import ModuleManager

# Module state variables - don't modify these directly
module_enabled = True  # Will be set by __init__.py
_is_registered = False  # Tracks registration state

# Module classes
class TEMPLATE_OT_sample_operator(Operator):
    """Sample operator demonstrating module_enabled check"""
    bl_idname = "template.sample_operator"
    bl_label = "Sample Operator"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        # Always check if module is enabled
        if not module_enabled:
            return False
        # Continue with normal polling logic
        return context.object is not None

    def execute(self, context):
        # Your code here
        return {'FINISHED'}

class TEMPLATE_PT_sample_panel(Panel):
    """Sample panel demonstrating module_enabled check"""
    bl_label = "Sample Panel"
    bl_idname = "TEMPLATE_PT_sample_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Template"

    @classmethod
    def poll(cls, context):
        # Always check if module is enabled
        return module_enabled

    def draw(self, context):
        layout = self.layout
        layout.operator(TEMPLATE_OT_sample_operator.bl_idname)

# Menu integration function - always checks module_enabled
def sample_menu_func(self, context):
    # Only add menu items if module is enabled
    if module_enabled:
        self.layout.operator(TEMPLATE_OT_sample_operator.bl_idname)

# Preferences UI function
def draw_preferences(preferences, context, layout):
    """Draw module preferences in the addon preferences panel"""
    row = layout.row()
    row.prop(preferences, "template_module_enabled", text="Enable Template Module")

# Standard Register function with ModuleManager
def register():
    # Use ModuleManager to track registration
    if not ModuleManager.register_module(sys.modules[__name__]):
        return
    
    # Register classes
    ModuleManager.safe_register_class(TEMPLATE_OT_sample_operator)
    ModuleManager.safe_register_class(TEMPLATE_PT_sample_panel)
    
    # Add menu integration
    ModuleManager.safe_append_menu(bpy.types.VIEW3D_MT_object_context_menu, sample_menu_func)
    

# Standard Unregister function with ModuleManager
def unregister():
    # Use ModuleManager to track unregistration
    if not ModuleManager.unregister_module(sys.modules[__name__]):
        return
    
    # Remove menu integration
    ModuleManager.safe_remove_menu(bpy.types.VIEW3D_MT_object_context_menu, sample_menu_func)
    
    # Unregister classes in reverse order
    ModuleManager.safe_unregister_class(TEMPLATE_PT_sample_panel)
    ModuleManager.safe_unregister_class(TEMPLATE_OT_sample_operator)
    

# For testing as standalone module
if __name__ == "__main__":
    register()