# qp_tools_pie_menu.py
import bpy
import os
from bpy.types import Menu, Operator
from bpy.props import StringProperty
import bmesh
import sys

# Import required modules
from . import module_helper
from . import qp_tools_assets
from .module_helper import ModuleManager

# Module state variables
module_enabled = True
_is_registered = False

def get_temp_file_path():
    """Get the temporary status file path"""
    from . import asset_cache
    return asset_cache.get_cache_path()

def is_background_process_running():
    """Check if a background process is running"""
    import os
    import json
    status_file = get_temp_file_path()
    if os.path.exists(status_file):
        try:
            with open(status_file, 'r') as f:
                status = json.load(f)
                return status.get('running', False)
        except (OSError, json.JSONDecodeError):
            return False
    return False

def get_asset_categories(library, force_refresh=False):
    """Get categories from a library with caching
    
    Args:
        library: The library object
        force_refresh: Whether to bypass cache
        
    Returns:
        dict: Mapping of category names to lists of assets
    """
    # Create a static cache property
    if not hasattr(get_asset_categories, "cache"):
        get_asset_categories.cache = {}
    
    cache_key = library.name
    if force_refresh or cache_key not in get_asset_categories.cache:
        # Group assets by category
        categories = {}
        for asset in library.assets:
            if asset.enabled:
                if asset.category not in categories:
                    categories[asset.category] = []
                categories[asset.category].append(asset)
        
        # Store in cache
        get_asset_categories.cache[cache_key] = categories
    
    return get_asset_categories.cache[cache_key]

# Reset asset categories cache when assets change
def clear_asset_categories_cache():
    """Clear the asset categories cache when assets are updated"""
    if hasattr(get_asset_categories, "cache"):
        get_asset_categories.cache = {}
        

class QP_OT_open_library_in_browser(Operator):
    """Open a new window with the Asset Browser for the selected library"""
    bl_idname = "qp.open_library_in_browser"
    bl_label = "Open Library in Asset Browser"
    
    library_name: StringProperty(name="Library Name")
    
    @classmethod
    def poll(cls, context):
        return module_enabled
    
    def execute(self, context):
        try:
            # Find the library by name
            library = None
            for lib in context.preferences.filepaths.asset_libraries:
                if lib.name == self.library_name:
                    library = lib
                    break
            
            if not library:
                self.report({'ERROR'}, f"Library {self.library_name} not found")
                return {'CANCELLED'}
            
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

class QP_MT_pie_menu_assets(Menu):
    """Enhanced pie menu for displaying assets from a library"""
    bl_label = "QP Assets"
    bl_idname = "QP_MT_pie_menu_assets"

    def draw(self, context):
        layout = self.layout
        pie = layout.menu_pie()
        
        # Get access to preferences
        prefs = context.preferences.addons[__package__].preferences
        
        # Filter only enabled libraries
        enabled_libraries = [lib for lib in prefs.asset_libraries if lib.enabled]
        
        # If no enabled libraries, show a message
        if not enabled_libraries:
            pie.label(text="No enabled asset libraries")
            return
        
        # Group libraries by asset count
        small_libraries = []  # 1-4 assets
        medium_libraries = [] # 5-8 assets
        large_libraries = []  # 9+ assets
        
        for lib in enabled_libraries:
            assets = [a for a in lib.assets if a.enabled]
            asset_count = len(assets)
            
            if asset_count <= 4:
                small_libraries.append(lib)
            elif asset_count <= 8:
                medium_libraries.append(lib)
            else:
                large_libraries.append(lib)
        
        # Define pie positions and placeholders
        pie_positions = [None] * 8
        
        # TOP position (0) - Small libraries
        if small_libraries:
            if len(small_libraries) == 1:
                pie_positions[0] = {"type": "single", "libraries": [small_libraries[0]]}
            elif len(small_libraries) <= 4:
                pie_positions[0] = {"type": "group", "libraries": small_libraries[:4]}
            else:
                pie_positions[0] = {"type": "group", "libraries": small_libraries[:4]}
        
        # RIGHT position (1) and LEFT position (3) - Medium libraries
        if medium_libraries:
            if len(medium_libraries) == 1:
                pie_positions[1] = {"type": "single", "libraries": [medium_libraries[0]]}
            elif len(medium_libraries) == 2:
                pie_positions[1] = {"type": "single", "libraries": [medium_libraries[0]]}
                pie_positions[3] = {"type": "single", "libraries": [medium_libraries[1]]}
            elif len(medium_libraries) <= 4:
                pie_positions[1] = {"type": "group", "libraries": medium_libraries[:2]}
                pie_positions[3] = {"type": "group", "libraries": medium_libraries[2:4]}
            else:
                pie_positions[1] = {"type": "group", "libraries": medium_libraries[:2]}
                pie_positions[3] = {"type": "group", "libraries": medium_libraries[2:4]}
        
        # BOTTOM position (2) - Large libraries
        if large_libraries:
            if len(large_libraries) == 1:
                pie_positions[2] = {"type": "single", "libraries": [large_libraries[0]]}
            elif len(large_libraries) <= 3:
                pie_positions[2] = {"type": "group", "libraries": large_libraries[:3]}
            else:
                pie_positions[2] = {"type": "group", "libraries": large_libraries[:3]}
        
        # Now populate the pie based on our layout plan
        for i, position in enumerate(pie_positions):
            if position is None:
                # Empty position
                pie.separator()
            elif position["type"] == "single":
                # Single library in this position
                self.draw_library_section(pie, position["libraries"][0], context, 1.0)
            elif position["type"] == "group":
                # Group of libraries
                if len(position["libraries"]) == 1:
                    # Just one library, draw directly
                    self.draw_library_section(pie, position["libraries"][0], context, 1.0)
                elif len(position["libraries"]) == 2:
                    # Split layout for 2 libraries
                    row = pie.split(factor=0.5)
                    col_left = row.column()
                    box_left = col_left.box()
                    self.draw_library_section(box_left, position["libraries"][0], context, 1.0, in_box=True)
                    
                    col_right = row.column()
                    box_right = col_right.box()
                    self.draw_library_section(box_right, position["libraries"][1], context, 1.0, in_box=True)
                elif len(position["libraries"]) == 3:
                    # Split layout for 3 libraries
                    row = pie.split(factor=0.5)
                    
                    # Left side
                    col_left = row.column()
                    box_left = col_left.box()
                    self.draw_library_section(box_left, position["libraries"][0], context, 1.0, in_box=True)
                    
                    # Right side, stacked vertically
                    col_right = row.column()
                    box_right_top = col_right.box()
                    self.draw_library_section(box_right_top, position["libraries"][1], context, 1.0, in_box=True)
                    
                    box_right_bottom = col_right.box()
                    self.draw_library_section(box_right_bottom, position["libraries"][2], context, 1.0, in_box=True)
                elif len(position["libraries"]) == 4:
                    # Grid layout for 4 libraries (2x2)
                    row1 = pie.split(factor=0.5)
                    
                    # Top row
                    col_left = row1.column()
                    col_right = row1.column()
                    
                    # Libraries in a 2x2 grid
                    box_top_left = col_left.box()
                    self.draw_library_section(box_top_left, position["libraries"][0], context, 0.9, in_box=True)
                    
                    box_top_right = col_right.box()
                    self.draw_library_section(box_top_right, position["libraries"][1], context, 0.9, in_box=True)
                    
                    box_bottom_left = col_left.box()
                    self.draw_library_section(box_bottom_left, position["libraries"][2], context, 0.9, in_box=True)
                    
                    box_bottom_right = col_right.box()
                    self.draw_library_section(box_bottom_right, position["libraries"][3], context, 0.9, in_box=True)

    def draw_library_section(self, layout, lib, context, scale=1.0, in_box=False):
        """Draw a library section with enhanced visual layout
        
        Args:
            layout: The layout to draw in (pie or box)
            lib: The library to draw
            context: The context
            scale: Scale factor for the layout
            in_box: Whether this is already inside a box
        """
        # If not already in a box, create one
        if not in_box:
            container = layout.column()
            container.scale_y = scale
            box = container.box()
        else:
            # Already in a box
            box = layout
            box.scale_y = scale
        
        # Make library name stand out more with a colored header
        header = box.column()
        header.label(text=lib.name, icon="ASSET_MANAGER")
        
        # Get enabled assets
        assets = [a for a in lib.assets if a.enabled]
        
        if not assets:
            box.label(text="No enabled assets")
            return
        
        # Group assets by category
        categories = {}
        for asset in assets:
            if asset.category not in categories:
                categories[asset.category] = []
            categories[asset.category].append(asset)
        
        # Determine library size
        total_assets = len(assets)
        is_small_library = total_assets <= 4
        is_medium_library = 5 <= total_assets <= 8
        is_large_library = total_assets >= 9
        
        # Set max assets to show based on library size
        if is_small_library:
            max_assets_to_show = total_assets  # Show all for small libraries
        elif is_medium_library:
            max_assets_to_show = total_assets  # Show all for medium libraries
        else:
            # Large libraries show a limited number
            max_assets_to_show = 10
            
        # Adjust for box display if needed
        if in_box and is_large_library:
            max_assets_to_show = min(max_assets_to_show, 8)
            
        assets_shown = 0
        
        # Decide on layout strategy
        if len(categories) == 1:
            # Single category - compact layout
            category, cat_assets = list(categories.items())[0]
            
            # Use a grid with columns
            num_columns = 2
            if len(cat_assets) > 6:
                num_columns = 3
                
            grid = box.grid_flow(row_major=True, columns=num_columns, even_columns=True)
            
            # For small and medium libraries, show all assets
            assets_to_display = cat_assets[:max_assets_to_show]
                
            # Display assets with previews
            for asset in assets_to_display:
                cell = grid.column().box()
                # Set increased scale_y for the button (first change)
                cell.scale_y = 1.5
                
                # Get asset type icon (second change)
                icon_name = get_asset_type_icon(asset)
                
                # Use icon based on asset type
                op = cell.operator("qp.append_asset", text=asset.name, icon=icon_name)
                    
                op.filepath = asset.filepath
                op.asset_name = asset.name
                assets_shown += 1
                    
        elif len(categories) <= 2:
            # Few categories - show each with its own header
            sorted_categories = sorted(categories.items(), key=lambda x: len(x[1]), reverse=True)
            
            for category, cat_assets in sorted_categories[:2]:
                if assets_shown >= max_assets_to_show:
                    break
                    
                # Add category header
                cat_box = box.box()
                cat_box.label(text=category)
                
                # Calculate how many assets to show
                to_show = min(max_assets_to_show - assets_shown, min(3, len(cat_assets)))
                
                # Display assets with preview icons
                col = cat_box.column(align=True)
                for asset in cat_assets[:to_show]:
                    # Set increased scale_y for the button (first change)
                    row = col.row()
                    row.scale_y = 1.5
                    
                    # Get asset type icon (second change)
                    icon_name = self.get_asset_type_icon(asset)
                    
                    # Try to get preview icon_id
                    preview_id = self.get_asset_preview_id(asset)
                    
                    if preview_id:
                        # If we have a preview, use it
                        op = row.operator("qp.append_asset", text=asset.name, icon_value=preview_id)
                    else:
                        # Use icon based on asset type
                        op = row.operator("qp.append_asset", text=asset.name, icon=icon_name)
                        
                    op.filepath = asset.filepath
                    op.asset_name = asset.name
                    assets_shown += 1
                
        else:
            # Many categories - compact layout with top category
            sorted_categories = sorted(categories.items(), key=lambda x: len(x[1]), reverse=True)
            top_category, cat_assets = sorted_categories[0]
            
            cat_box = box.box()
            cat_box.label(text=top_category)
                
            # Simple grid for compact display
            grid = cat_box.grid_flow(row_major=True, columns=2, even_columns=True)
            
            # Determine how many assets to show
            to_show = min(max_assets_to_show, len(cat_assets))
                
            for asset in cat_assets[:to_show]:
                # Set increased scale_y for the button (first change)
                row = grid.row()
                row.scale_y = 1.5
                
                # Get asset type icon (second change)
                icon_name = get_asset_type_icon(asset)
                
                # Try to get preview icon_id
                preview_id = self.get_asset_preview_id(asset)
                
                if preview_id:
                    # If we have a preview, use it
                    op = row.operator("qp.append_asset", text=asset.name, icon_value=preview_id)
                else:
                    # Use icon based on asset type
                    op = row.operator("qp.append_asset", text=asset.name, icon=icon_name)
                    
                op.filepath = asset.filepath
                op.asset_name = asset.name
                assets_shown += 1
                    
        # Add "See All" button for large libraries if there are more assets than shown
        if is_large_library and total_assets > assets_shown:
            row = box.row()
            row.scale_y = 1.5  # Also make this button larger
            op = row.operator("qp.open_library_in_browser", 
                           text=f"See All Assets ({total_assets - assets_shown} more)")
            op.library_name = lib.name
            
    def get_asset_preview_id(self, asset):
        """Get the preview icon_id for an asset
        
        Args:
            asset: The asset to get the preview for
            
        Returns:
            int or None: The icon_id if available, otherwise None
        """
        # First check if the asset has a preview directly
        if hasattr(asset, 'preview') and asset.preview:
            return asset.preview.icon_id
        
        # Try to get from bpy.types references
        if hasattr(bpy.data, 'objects') and hasattr(asset, 'name'):
            # Try to find the object with this name
            obj = bpy.data.objects.get(asset.name)
            if obj and hasattr(obj, 'preview') and obj.preview:
                return obj.preview.icon_id
        
        # No preview found
        return None
    
# Function moved outside of class to be accessible from other functions
def get_asset_type_icon(asset):
    """Get the appropriate icon based on asset type
    
    Args:
        asset: The asset to get the icon for
        
    Returns:
        str: Icon name to use
    """
    # Default icon for objects
    default_icon = "OBJECT_DATA"
    
    # If no filepath or asset name, return default
    if not hasattr(asset, 'filepath') or not hasattr(asset, 'name'):
        return default_icon
        
    # Try to determine the asset type by looking for clues in the filename
    filepath = asset.filepath.lower() if hasattr(asset, 'filepath') else ""
    name = asset.name.lower() if hasattr(asset, 'name') else ""
    
    # Check for common keywords in filepath or name
    if any(kw in filepath or kw in name for kw in ["curve", "bezier", "nurbs", "spline"]):
        return "CURVE_DATA"
    elif any(kw in filepath or kw in name for kw in ["grease", "gpencil", "pencil", "sketch", "drawing"]):
        return "GREASEPENCIL"
    elif any(kw in filepath or kw in name for kw in ["surface", "nurbs_surface"]):
        return "SURFACE_DATA"
    elif any(kw in filepath or kw in name for kw in ["font", "text", "type"]):
        return "FONT_DATA"
    elif any(kw in filepath or kw in name for kw in ["lattice", "deform"]):
        return "LATTICE_DATA"
    elif any(kw in filepath or kw in name for kw in ["armature", "bone", "skeleton", "rig"]):
        return "ARMATURE_DATA"
    elif any(kw in filepath or kw in name for kw in ["light", "lamp", "emission"]):
        return "LIGHT_DATA"
    elif any(kw in filepath or kw in name for kw in ["camera", "view"]):
        return "CAMERA_DATA"
    elif any(kw in filepath or kw in name for kw in ["material", "mat", "shader"]):
        return "MATERIAL"
    
    # Try to check if the object exists in the current file and get its type
    obj = bpy.data.objects.get(asset.name)
    if obj:
        if obj.type == 'MESH':
            return "MESH_DATA"
        elif obj.type == 'CURVE':
            return "CURVE_DATA"
        elif obj.type in ['GPENCIL', 'GREASEPENCIL']:
            return "GREASEPENCIL"
        elif obj.type == 'SURFACE':
            return "SURFACE_DATA"
        elif obj.type == 'FONT':
            return "FONT_DATA"
        elif obj.type == 'LATTICE':
            return "LATTICE_DATA"
        elif obj.type == 'ARMATURE':
            return "ARMATURE_DATA"
        elif obj.type == 'LIGHT':
            return "LIGHT_DATA"
        elif obj.type == 'CAMERA':
            return "CAMERA_DATA"
        return "OBJECT_DATA"

    return default_icon
    
# Operator to call the pie menu
class QP_OT_call_asset_menu(Operator):
    bl_idname = "qp.call_asset_menu"
    bl_label = "Tool Asset Pie Menu"
    
    def execute(self, context):
        bpy.ops.wm.call_menu_pie(name="QP_MT_pie_menu_assets")
        return {'FINISHED'}
                                 
def draw_tool_assets_preferences(preferences, context, layout):
    """Draw the tool assets preferences UI with enhanced cache management"""
    if preferences.qp_tools_pie_menu_enabled:
        # Shortcut section - use native keymap UI
        shortcut_box = layout.box()
        shortcut_box.label(text="Tools Pie Menu Shortcut", icon='KEYINGSET')
        
        # Draw the keymap UI using the simplified system
        from . import shortcuts
        shortcuts.draw_keymap_ui(context, shortcut_box, "asset_pie")
        

        # Asset libraries section
        assets_box = layout.box()
        assets_box.label(text="Asset Libraries", icon='ASSET_MANAGER')

        # Enhanced cache management row
        cache_row = assets_box.row(align=True)
        cache_row.scale_y = 1.5
        cache_row.operator("qp.sync_asset_libraries", icon='FILE_REFRESH', text="Sync Libraries")
        
        # Enhanced cache management tools
        cache_tools = assets_box.row(align=True)
        cache_tools.operator("qp.refresh_asset_cache", icon='BRUSH_DATA', text="Refresh Cache")
        cache_tools.operator("qp.asset_cache_stats", icon='INFO', text="Cache Stats")
        
        # Advanced cache options (collapsible)
        advanced_box = assets_box.box()
        advanced_header = advanced_box.row()
        advanced_header.prop(preferences, "show_advanced_cache_options", 
                           icon='TRIA_DOWN' if preferences.show_advanced_cache_options else 'TRIA_RIGHT',
                           text="Advanced Cache Options", emboss=False)
        
        if preferences.show_advanced_cache_options:
            # Force refresh all button
            force_row = advanced_box.row(align=True)
            force_op = force_row.operator("qp.refresh_asset_cache", 
                                        text="Force Refresh All", icon='FILE_REFRESH')
            force_op.force_rescan = True
            
            # Cache health info
            health_row = advanced_box.row(align=True)
            health_row.operator("qp.show_cache_health", text="Cache Health", icon='HEART')
            
            # Individual library refresh options
            if preferences.asset_libraries:
                advanced_box.label(text="Per-Library Actions:")
                for lib in preferences.asset_libraries:
                    if lib.enabled:
                        lib_row = advanced_box.row(align=True)
                        lib_row.label(text=f"  {lib.name}:")
                        refresh_op = lib_row.operator("qp.force_refresh_library", 
                                                    text="Refresh", icon='FILE_REFRESH')
                        refresh_op.library_name = lib.name
                        
                        validate_op = lib_row.operator("qp.validate_library", 
                                                     text="Validate", icon='CHECKMARK')
                        validate_op.library_name = lib.name

        # Add filter controls in a row
        filter_row = assets_box.row(align=True)
        
        # Search filter
        filter_row.prop(preferences, "asset_library_search", icon='VIEWZOOM')
        
        # Show active only toggle
        filter_row.prop(preferences, "asset_library_show_active_only", 
                       text="Only Active", icon='FILTER', toggle=True)
        
        # List libraries with enhanced status information
        if not preferences.asset_libraries:
            assets_box.label(text="No asset libraries found")
        else:
            # Filter libraries based on search term and active state
            search_term = preferences.asset_library_search.lower()
            show_active_only = preferences.asset_library_show_active_only
            
            filtered_libraries = [
                lib for lib in preferences.asset_libraries 
                if search_term in lib.name.lower() and
                   (not show_active_only or lib.enabled)
            ]

            # Show filtered libraries
            if not filtered_libraries:
                assets_box.label(text="No libraries match filters")
            else:
                for lib in filtered_libraries:
                    lib_box = assets_box.box()
                    
                    # Create main library header row
                    header_row = lib_box.row(align=True)
                    header_row.scale_y = 1.5 
                    
                    # Library toggle - clean checkbox only
                    header_row.prop(lib, "enabled", text="")
                    header_row.separator(factor=2)  # Add spacing between checkbox and name
                    header_row.label(text=lib.name)
                    
                    # Add library status info
                    asset_count = len([a for a in lib.assets if a.enabled]) if lib.enabled else 0
                    if lib.enabled and asset_count > 0:
                        header_row.label(text=f"({asset_count} assets)")
                    elif lib.enabled:
                        header_row.label(text="(empty)", icon='INFO')
                    
                    # Set appearance based on enabled state
                    if lib.enabled:  # FIXED: was 'is_enabled'
                        header_row.active = True
                    else:
                        header_row.active = False
                    
                    # Add Refresh Assets button to the same row if library is enabled
                    if lib.enabled:  # FIXED: was 'is_enabled'
                        # Add spacer to push the button to the right
                        header_row.separator(factor=2)
                        refresh_op = header_row.operator(
                            "qp.scan_library_assets", 
                            text="Refresh Assets", 
                            icon='FILE_REFRESH'
                        )
                        refresh_op.library_name = lib.name
                    
                    # If library is enabled, show its assets
                    if lib.enabled:
                        if len(lib.assets) > 0:
                            # Group assets by category
                            categories = {}
                            for asset in lib.assets:
                                if asset.category not in categories:
                                    categories[asset.category] = []
                                categories[asset.category].append(asset)
                            
                            # Get expanded categories
                            expanded_categories = lib.expanded_categories.split(",") if lib.expanded_categories else []
                            
                            # Display categories
                            for category, assets in sorted(categories.items()):
                                category_box = lib_box.box()
                                category_row = category_box.row(align=True)
                                
                                # Check if category is expanded
                                is_expanded = category in expanded_categories
                                
                                # Create the toggle button
                                icon = 'TRIA_DOWN' if is_expanded else 'TRIA_RIGHT'
                                op = category_row.operator("qp.toggle_category", text="", icon=icon, emboss=False)
                                op.library_name = lib.name
                                op.category = category
                                
                                # Count enabled assets
                                enabled_count = sum(1 for asset in assets if asset.enabled)
                                
                                # Display category name and counts (enabled/total)
                                category_row.label(text=f"{category} ({enabled_count}/{len(assets)})")
                                category_row.scale_y = 1.2
                                
                                # Toggle all button
                                toggle_op = category_row.operator("qp.toggle_category_assets", text="Toggle All")
                                toggle_op.library_name = lib.name
                                toggle_op.category = category
                                
                                # Display assets if category is expanded
                                if is_expanded:
                                    # Add column settings 
                                    num_columns = preferences.assets_columns
                                    grid = category_box.grid_flow(row_major=False, columns=num_columns, even_columns=True)

                                    # Calculate assets per column
                                    assets_per_column = (len(assets) + num_columns - 1) // num_columns
                                    
                                    # Create columns and distribute assets
                                    for col_idx in range(num_columns):
                                        column = grid.column(align=True)
                                        column.scale_y = 1
                                        
                                        # Calculate slice for this column
                                        start_idx = col_idx * assets_per_column
                                        end_idx = min(start_idx + assets_per_column, len(assets))
                                        
                                        # Add assets to this column
                                        for asset in assets[start_idx:end_idx]:
                                            asset_row = column.row(align=True)
                                            # Add checkbox for selection
                                            asset_row.prop(asset, "enabled", text="")
                                            
                                            # Get asset type icon
                                            icon_name = get_asset_type_icon(asset)
                                            
                                            # Add the asset name with appropriate styling and icon
                                            if asset.enabled:
                                                # When enabled: depressed appearance
                                                op = asset_row.operator("qp.toggle_asset", text=asset.name, depress=True, icon=icon_name)
                                            else:
                                                # When disabled: normal appearance
                                                op = asset_row.operator("qp.toggle_asset", text=asset.name, depress=False, icon=icon_name)
                                                
                                            op.library_name = lib.name
                                            op.asset_name = asset.name
                                            op.filepath = asset.filepath
                        else:
                            lib_box.label(text="No assets found")
    else:
        # Show message when disabled
        layout.label(text="Tool Assets Pie Menu is disabled.", icon='INFO')
        layout.label(text="Enable it in the Core Modules tab first.")
        layout.operator("qp.show_core_modules_tab", text="Go to Core Modules Tab")


class QP_OT_ToggleLibrary(Operator):
    """Toggle a library's enabled state"""
    bl_idname = "qp.toggle_library"
    bl_label = "Toggle Library"
    
    library_name: StringProperty(name="Library Name")
    
    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences
        
        # Find the library by name
        for lib in prefs.asset_libraries:
            if lib.name == self.library_name:
                # Toggle the enabled state
                lib.enabled = not lib.enabled
                
                # Save preferences
                bpy.ops.wm.save_userpref()
                break
        
        return {'FINISHED'}



# Registration
classes = [
    QP_MT_pie_menu_assets,
    QP_OT_call_asset_menu,
    QP_OT_ToggleLibrary,
    QP_OT_open_library_in_browser,
]

def register():
    # Check if module should be registered
    if not ModuleManager.register_module(sys.modules[__name__]):
        return
    
    # Register classes
    for cls in classes:
        module_helper.ModuleManager.safe_register_class(cls)

def unregister():
    # Check if module should be unregistered
    if not ModuleManager.unregister_module(sys.modules[__name__]):
        return
    
    # Unregister classes in reverse order
    for cls in reversed(classes):
        module_helper.ModuleManager.safe_unregister_class(cls)