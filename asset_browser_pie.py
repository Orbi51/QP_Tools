# asset_browser_pie.py
import bpy
import sys
from bpy.types import Operator, Menu
from bpy.props import StringProperty

from .module_helper import ModuleManager
from .preferences import QP_LibraryPG

# Module state variables
module_enabled = True
_is_registered = False

class QP_MT_AssetLibraryPie(Menu):
    """Pie menu for opening asset libraries in new windows"""
    bl_idname = "QP_MT_asset_library_pie"
    bl_label = "Asset Libraries"
    
    def draw(self, context):
        layout = self.layout
        pie = layout.menu_pie()
        
        prefs = context.preferences.addons[__package__].preferences
        libraries = context.preferences.filepaths.asset_libraries
        
        if hasattr(prefs, "asset_browser_libraries"):
            # Apply filters
            search_term = prefs.asset_browser_search.lower() if hasattr(prefs, "asset_browser_search") else ""
            show_active_only = prefs.asset_browser_show_active_only if hasattr(prefs, "asset_browser_show_active_only") else False
            
            # Filter libraries based on search and active state
            filtered_lib_prefs = []
            for lib_pref in prefs.asset_browser_libraries:
                # Skip if not enabled and we're showing only active
                if show_active_only and not lib_pref.enabled:
                    continue
                
                try:
                    lib_index = int(lib_pref.index)
                    if lib_index < len(libraries):
                        # Skip if doesn't match search term
                        if search_term and search_term not in libraries[lib_index].name.lower():
                            continue
                        
                        # Add to filtered list
                        if lib_pref.enabled:
                            filtered_lib_prefs.append(lib_pref)
                except (ValueError, IndexError, AttributeError):
                    continue  # Invalid library preference

            # Handle if no libraries match filters
            if not filtered_lib_prefs:
                pie.label(text="No libraries match filters")
                return

            # Add the filtered libraries to the pie menu
            for lib_pref in filtered_lib_prefs:
                try:
                    lib_index = int(lib_pref.index)
                    if lib_index < len(libraries):
                        op = pie.operator(
                            "qp.open_asset_library_window",
                            text=libraries[lib_index].name
                        )
                        op.library_index = lib_pref.index
                except (ValueError, IndexError, AttributeError):
                    continue  # Invalid library index

class QP_OT_OpenAssetLibrary(Operator):
    """Open a new window with the Asset Browser for the selected library"""
    bl_idname = "qp.open_asset_library_window"
    bl_label = "Open Asset Library Window"
    
    library_index: StringProperty()
    
    @classmethod
    def poll(cls, context):
        return module_enabled
    
    def execute(self, context):
        try:
            lib_idx = int(self.library_index)
            library = context.preferences.filepaths.asset_libraries[lib_idx]
            
            # Create new window
            bpy.ops.screen.userpref_show('INVOKE_DEFAULT')
            new_window = context.window_manager.windows[-1]
            new_screen = new_window.screen
            
            # Change the area type to File Browser
            area = new_screen.areas[0]
            area.type = 'FILE_BROWSER'
            space = area.spaces.active
            area.ui_type = 'ASSETS'
            space.browse_mode = 'ASSETS'
            
            # Set up the asset browser
            def setup_params():
                if hasattr(space, 'params') and space.params is not None:
                    params = space.params
                    params.asset_library_reference = library.name
                    area.tag_redraw()
                    return None
                return 0.1
            
            bpy.app.timers.register(setup_params, first_interval=0.2)
            
        except Exception as e:
            self.report({'ERROR'}, f"Error opening library window: {str(e)}")
            return {'CANCELLED'}
        
        return {'FINISHED'}

class QP_OT_CallAssetLibraryMenu(Operator):
    """Call the asset library pie menu"""
    bl_idname = "qp.call_asset_library_menu"
    bl_label = "Asset Browser Pie Menu"
    
    @classmethod
    def poll(cls, context):
        return module_enabled
    
    def execute(self, context):
        bpy.ops.wm.call_menu_pie(name=QP_MT_AssetLibraryPie.bl_idname)
        return {'FINISHED'}

class QP_OT_UpdateAssetBrowserLibraries(Operator):
    """Update asset browser libraries list"""
    bl_idname = "qp.update_asset_browser_libraries"
    bl_label = "Update Asset Libraries"
    
    def execute(self, context):
        update_asset_browser_libraries(context)
        self.report({'INFO'}, "Asset browser libraries updated")
        return {'FINISHED'}

def update_asset_browser_libraries(context):
    """Update the asset browser libraries list in preferences"""
    if __package__ in context.preferences.addons:
        preferences = context.preferences.addons[__package__].preferences
        if hasattr(preferences, "asset_browser_libraries"):
            current_indices = {lib.index for lib in preferences.asset_browser_libraries}
            
            for i, _ in enumerate(context.preferences.filepaths.asset_libraries):
                if str(i) not in current_indices:
                    lib = preferences.asset_browser_libraries.add()
                    lib.index = str(i)

def draw_asset_browser_preferences(preferences, context, layout):
    """Draw the asset browser preferences UI"""
    if preferences.asset_browser_pie_enabled:
        # Shortcut section - use native keymap UI
        shortcut_box = layout.box()
        shortcut_box.label(text="Asset Browser Pie Menu Shortcut", icon='KEYINGSET')
        
        # Draw the keymap UI using the simplified system
        from . import shortcuts
        shortcuts.draw_keymap_ui(context, shortcut_box, "asset_library_pie")
        

        # Libraries UI
        libraries_box = layout.box()
        libraries_box.label(text="Asset Libraries", icon='ASSET_MANAGER')
        
        # Add search filter and active only toggle
        filter_row = libraries_box.row(align=True)
        
        # Search filter
        filter_row.prop(preferences, "asset_browser_search", icon='VIEWZOOM')
        
        # Show active only toggle
        filter_row.prop(preferences, "asset_browser_show_active_only", 
                      text="Only Active", icon='FILTER', toggle=True)
        
        # Refresh button
        row = libraries_box.row()
        row.label(text="Libraries to include in pie menu:", icon='OUTLINER_OB_GROUP_INSTANCE')
        row.operator("qp.update_asset_browser_libraries", text="", icon='FILE_REFRESH')
        
        libraries = context.preferences.filepaths.asset_libraries
        
        if hasattr(preferences, "asset_browser_libraries"):
            # Apply search filter
            search_term = preferences.asset_browser_search.lower() if hasattr(preferences, "asset_browser_search") else ""
            show_active_only = preferences.asset_browser_show_active_only if hasattr(preferences, "asset_browser_show_active_only") else False
            
            filtered_libs = []
            for lib_pref in preferences.asset_browser_libraries:
                try:
                    lib_index = int(lib_pref.index)
                    if lib_index < len(libraries):
                        # Skip if showing only active and this is not active
                        if show_active_only and not lib_pref.enabled:
                            continue
                            
                        # Skip if it doesn't match search
                        if search_term and search_term not in libraries[lib_index].name.lower():
                            continue
                            
                        filtered_libs.append(lib_pref)
                except (ValueError, IndexError, AttributeError):
                    continue  # Invalid library preference

            # Show filtered libraries
            if not filtered_libs:
                libraries_box.label(text="No libraries match search")
            else:
                for lib_pref in filtered_libs:
                    try:
                        lib_index = int(lib_pref.index)
                        if lib_index < len(libraries):
                            # Create stylized toggle button for each library
                            row = libraries_box.row(align=True)
                            row.scale_y = 1.5
                            is_enabled = lib_pref.enabled

                            # Create toggle-style button
                            op = row.operator(
                                "qp.toggle_asset_browser_library",
                                text=libraries[lib_index].name,
                                depress=is_enabled,
                                icon='CHECKBOX_HLT' if is_enabled else 'CHECKBOX_DEHLT'
                            )
                            op.library_index = lib_pref.index

                            # Set appearance based on state
                            if is_enabled:
                                row.active = True
                            else:
                                row.active = False
                    except (ValueError, IndexError, AttributeError):
                        continue  # Invalid library index
    else:
        # Show message when disabled
        layout.label(text="Asset Browser Pie Menu is disabled.", icon='INFO')
        layout.label(text="Enable it in the Core Modules tab first.")
        layout.operator("qp.show_core_modules_tab", text="Go to Core Modules Tab")


class QP_OT_ToggleAssetBrowserLibrary(Operator):
    """Toggle an asset browser library's enabled state"""
    bl_idname = "qp.toggle_asset_browser_library"
    bl_label = "Toggle Asset Browser Library"
    
    library_index: StringProperty(name="Library Index")
    
    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences
        
        # Find the library by index
        for lib_pref in prefs.asset_browser_libraries:
            if lib_pref.index == self.library_index:
                # Toggle the enabled state
                lib_pref.enabled = not lib_pref.enabled
                
                # Save preferences
                bpy.ops.wm.save_userpref()
                break
        
        return {'FINISHED'}

def register():
    if not ModuleManager.register_module(sys.modules[__name__]):
        return
    
    # Register classes
    ModuleManager.safe_register_class(QP_MT_AssetLibraryPie)
    ModuleManager.safe_register_class(QP_OT_OpenAssetLibrary)
    ModuleManager.safe_register_class(QP_OT_CallAssetLibraryMenu)
    ModuleManager.safe_register_class(QP_OT_UpdateAssetBrowserLibraries)
    ModuleManager.safe_register_class(QP_OT_ToggleAssetBrowserLibrary)
    
    # Initialize library list
    update_asset_browser_libraries(bpy.context)
    

def unregister():
    if not ModuleManager.unregister_module(sys.modules[__name__]):
        return
    
    # Unregister classes in reverse order
    ModuleManager.safe_unregister_class(QP_OT_ToggleAssetBrowserLibrary)
    ModuleManager.safe_unregister_class(QP_OT_UpdateAssetBrowserLibraries)
    ModuleManager.safe_unregister_class(QP_OT_CallAssetLibraryMenu)
    ModuleManager.safe_unregister_class(QP_OT_OpenAssetLibrary)
    ModuleManager.safe_unregister_class(QP_MT_AssetLibraryPie)
    

if __name__ == "__main__":
    register()