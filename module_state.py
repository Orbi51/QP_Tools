# module_state.py
import bpy

def is_module_enabled(module_name):
    """Check if a module is enabled by querying the addon preferences"""
    try:
        # Get addon preferences
        prefs = bpy.context.preferences.addons[__package__].preferences
        
        # Map module names to preference property names
        preference_map = {
            "LinkNodeGroups": "link_node_groups_enabled",
            "TextureSet_builder": "texture_set_builder_enabled",
            "Project_Box_Flat": "project_box_flat_enabled",
            "EdgeSelect": "edge_select_enabled",
            "CollectionOffset": "collection_offset_enabled",
            "BevelWeight": "bevel_weight_enabled",
            "LatticeSetup": "lattice_setup_enabled",
            "MaterialList": "materiallist_enabled",
            "CleanUp": "cleanup_enabled",
            "asset_browser_pie": "asset_browser_pie_enabled",
            "qp_tools_pie_menu": "qp_tools_pie_menu_enabled",
            "quick_asset_library": "quick_asset_library_enabled",
            "ui": True  # UI is always enabled
        }
        
        # Get preference property for this module
        prop_name = preference_map.get(module_name)
        
        # Check module enabled state
        if isinstance(prop_name, str) and hasattr(prefs, prop_name):
            return getattr(prefs, prop_name)
        elif isinstance(prop_name, bool):
            return prop_name
        else:
            return True
    except Exception as e:
        print(f"Error checking module state for {module_name}: {e}")
        # Default to enabled if preferences not available
        return True