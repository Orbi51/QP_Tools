# __init__.py
bl_info = {
    "name": "QP_Tools",
    "author": "Quentin Pointillart",
    "description": "Set of tools to speed up time consuming tasks",
    "blender": (4, 2, 0),
    "version": (2, 2, 2),
    "location": "Right-click menu", 
    "category": "Node, Mesh" 
}

import bpy
import importlib

# Import required modules
from . import module_state
from . import module_helper
from . import preferences
from . import shortcuts
from . import qp_tools_pie_menu
from . import qp_tools_assets
from . import qp_tools_panel
from . import ui
from . import asset_cache
from . import qp_image_updater
from . import updater

# Main modules
modules = [
    "BevelWeight",
    "CleanUp",
    "CollectionOffset",
    "EdgeSelect",
    "FloatingPanel",
    "LatticeSetup",
    "LinkNodeGroups",
    "MaterialList",
    "Project_Box_Flat",
    "TextureSet_builder",
    "asset_browser_pie",
    "pie_menu_builder",
    "quick_asset_library",
    "qp_tools_panel",
]

# Import modules
imported_modules = []
for module_name in modules:
    try:
        if module_name in locals():
            imported_modules.append(importlib.reload(locals()[module_name]))
        else:
            imported_modules.append(importlib.import_module(f".{module_name}", package=__package__))
    except ImportError as e:
        print(f"Could not import {module_name}: {e}")


# Module-level variable to track recursion
_is_loading_libraries = False

def load_module(module_name):
    """Load a single module with better error handling
    
    Args:
        module_name: Name of the module to load
        
    Returns:
        The loaded module or None
    """
    try:
        if module_name in globals():
            # If already imported, reload it
            module = globals()[module_name]
            return importlib.reload(module)
        else:
            # Import for the first time
            module = importlib.import_module(f".{module_name}", package=__package__)
            return module
    except ImportError as e:
        print(f"Could not import {module_name}: {e}")
        return None
    except Exception as e:
        print(f"Error loading {module_name}: {e}")
        import traceback
        traceback.print_exc()
        return None
    
@bpy.app.handlers.persistent
def load_libraries_and_save_prefs(_):
    """Load all enabled libraries and then save preferences once"""
    global _is_loading_libraries
    
    # Avoid recursive call during loading
    if _is_loading_libraries:
        return
    
    try:
        # Set flag to prevent recursive calls
        _is_loading_libraries = True
        
        # Get addon preferences
        addon_prefs = bpy.context.preferences.addons.get(__package__)
        if not addon_prefs:
            return
            
        prefs = addon_prefs.preferences
        
        # Load assets for all enabled libraries
        libraries_loaded = False
        for lib in prefs.asset_libraries:
            if lib.enabled:
                # This will trigger library_enabled_update but won't save prefs
                libraries_loaded = True
        
        # Only save preferences once after all libraries have been loaded
        if libraries_loaded:
            bpy.ops.wm.save_userpref()
    
    finally:
        # Reset flag
        _is_loading_libraries = False


def register():
    qp_tools_assets.register()
    preferences.register()
    
    # Register shortcut functionality first, but don't set up keymaps yet
    shortcuts.register()  
    
    # Get module state from the module file directly
    from . import module_state
    
    # Register qp_tools_pie_menu only if enabled
    if module_state.is_module_enabled("qp_tools_pie_menu"):
        qp_tools_pie_menu.register()
    
    # Register modules, respecting enabled state
    imported_modules.clear()  # Clear the list first
    for module_name in modules:
        try:
            if module_name in locals():
                module = importlib.reload(locals()[module_name])
            else:
                module = importlib.import_module(f".{module_name}", package=__package__)
                
            # Add to imported_modules only if successfully loaded
            imported_modules.append(module)
            
            # Register module if it's enabled
            if hasattr(module, "register") and module_state.is_module_enabled(module_name):
                module.register()
        except Exception as e:
            print(f"Error loading module {module_name}: {e}")
            import traceback
            traceback.print_exc()
    
    
    qp_tools_panel.register()
    ui.register()
    qp_image_updater.register()
    updater.register()

    # Register the new handler after all other initializations
    if load_libraries_and_save_prefs not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(load_libraries_and_save_prefs)

    shortcuts.register_keymaps()

def unregister():
    # Remove handlers FIRST
    if load_libraries_and_save_prefs in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(load_libraries_and_save_prefs)
    
    # Unregister keymaps before modules
    shortcuts.unregister_keymaps()
    
    # Unregister in EXACT reverse order of register()
    updater.unregister()
    ui.unregister()
    qp_image_updater.unregister()
    qp_tools_panel.unregister()
    
    # Modules in reverse
    for module in reversed(imported_modules):
        if hasattr(module, "unregister"):
            module.unregister()
    
    # Pie menu
    if module_state.is_module_enabled("qp_tools_pie_menu"):
        qp_tools_pie_menu.unregister()
    
    # Core systems last
    shortcuts.unregister()
    preferences.unregister()
    qp_tools_assets.unregister()