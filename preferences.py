# preferences.py
import bpy
import os
import zipfile
import json
import time
import re
from bpy.types import AddonPreferences, PropertyGroup, Operator
from bpy.props import BoolProperty, StringProperty, CollectionProperty, IntProperty, EnumProperty
from . import shortcuts
from .module_helper import ModuleManager
from . import asset_cache
from .qp_tools_assets import QP_OT_AppendAsset
from bpy.types import Operator


# Add update callback for library enabled state
def library_enabled_update(self, context):
    try:
        if self.enabled:
            # Try to load from cache
            cache = asset_cache.load_asset_cache()
            
            # Check if library exists in cache
            if "libraries" in cache and self.name in cache["libraries"]:
                lib_cache = cache["libraries"][self.name]
                cached_assets = lib_cache.get("assets", [])
                
                if cached_assets:
                    # Clear and load from cache
                    self.assets.clear()
                    for asset in cached_assets:
                        new_asset = self.assets.add()
                        new_asset.name = asset["name"]
                        new_asset.filepath = asset["filepath"]
                        new_asset.category = asset.get("category", "Default")
                        # Use saved enabled state or default to True
                        new_asset.enabled = asset.get("enabled", True)
                    
                else:
                    # Scan for new assets
                    bpy.ops.qp.scan_library_assets(library_name=self.name)
            else:
                # Scan for new assets
                bpy.ops.qp.scan_library_assets(library_name=self.name)
        
        # bpy.ops.wm.save_userpref()
        
    except Exception as e:
        print(f"Error updating library {self.name}: {str(e)}")
        import traceback
        traceback.print_exc()

class QP_OT_toggle_module(Operator):
    bl_idname = "qp.toggle_module"
    bl_label = "Toggle Module"
    bl_description = "Toggle the module on/off"  # Default fallback description
    bl_options = {'REGISTER', 'INTERNAL'}
    
    module_prop: StringProperty(
        name="Module Property",
        description="Name of the property to toggle"
    )
    
    @classmethod
    def description(cls, context, properties):
        # Look up the description based on module property
        module_tooltips = {
            "link_node_groups_enabled": "Link node groups to nodes based on matching socket names",
            "texture_set_builder_enabled": "Create texture sets from individual texture maps",
            "project_box_flat_enabled": "Set projection method (Box/Flat) and color space (sRGB/Non-Color) for texture nodes",
            "edge_select_enabled": "Mark edges for Draw Array EdgeSelect and manage vertex groups",
            "collection_offset_enabled": "Set the offset for collections based on selection",
            "bevel_weight_enabled": "Set bevel weight for selected vertex or edges",
            "floating_panel_enabled": "Create floating viewport windows from the 3D View",
            "lattice_setup_enabled": "Create a lattice around selected objects and add modifiers",
            "materiallist_enabled": "Browse and apply materials from a searchable list",
            "cleanup_enabled": "Clean up and organize duplicate materials and node groups",
            "asset_browser_pie_enabled": "Access asset libraries via a pie menu",
            "qp_tools_pie_menu_enabled": "Access tools and assets via a pie menu",
            "quick_asset_library_enabled": "Quickly create and manage asset libraries",
            "pie_menu_builder_enabled": "Create custom pie menus with context-sensitive actions"
        }
        return module_tooltips.get(properties.module_prop, "Toggle the module on/off")
    
        
    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences
        if hasattr(prefs, self.module_prop):
            # Toggle the property value
            setattr(prefs, self.module_prop, not getattr(prefs, self.module_prop))
            # Save preferences
            bpy.ops.wm.save_userpref()
            
            # Signal that preferences have changed
            prefs.module_settings_changed = True
            
        return {'FINISHED'}

class QP_OT_ShowCoreModulesTab(Operator):
    """Show addon preferences with Core Modules tab active"""
    bl_idname = "qp.show_core_modules_tab"
    bl_label = "Show Core Modules Tab"
    
    def execute(self, context):
        # Access addon preferences
        prefs = context.preferences.addons[__package__].preferences
        
        # Set active tab to CORE
        prefs.active_tab = 'CORE'
        
        # Open addon preferences
        bpy.ops.preferences.addon_show(module=__package__)
        
        return {'FINISHED'}

# Asset property groups
class QP_AssetItem(PropertyGroup):
    name: StringProperty(name="Asset Name")
    filepath: StringProperty(name="File Path")
    enabled: BoolProperty(name="Enabled", default=True)
    category: StringProperty(name="Category", default="Default")

class QP_AssetLibrary(PropertyGroup):
    name: StringProperty(name="Library Name")
    path: StringProperty(name="Library Path")
    enabled: BoolProperty(
        name="Enabled", 
        default=False,
        update=library_enabled_update
    )
    assets: CollectionProperty(type=QP_AssetItem)
    expanded_categories: StringProperty(default="")  # Comma-separated list of expanded categories

def update_module_state(self, context):
    """Update module state when preferences change"""
    self.module_settings_changed = True

    for window in context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()

class QP_OT_ToggleCategory(Operator):
    """Toggle the expanded state of a category"""
    bl_idname = "qp.toggle_category"
    bl_label = "Toggle Category"
    
    library_name: StringProperty(name="Library Name")
    category: StringProperty(name="Category")
    
    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences
        lib = next((l for l in prefs.asset_libraries if l.name == self.library_name), None)
        
        if not lib:
            return {'CANCELLED'}
        
        # Get the current expanded categories
        expanded = lib.expanded_categories.split(",") if lib.expanded_categories else []
        
        # Toggle the category
        if self.category in expanded:
            expanded.remove(self.category)
        else:
            expanded.append(self.category)
        
        # Update the property
        lib.expanded_categories = ",".join(expanded)
        
        return {'FINISHED'}

class QP_OT_ToggleCategoryAssets(Operator):
    """Toggle all assets in a category"""
    bl_idname = "qp.toggle_category_assets"
    bl_label = "Toggle Category Assets"
    
    library_name: StringProperty(name="Library Name")
    category: StringProperty(name="Category")
    
    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences
        lib = next((l for l in prefs.asset_libraries if l.name == self.library_name), None)
        
        if not lib:
            self.report({'WARNING'}, f"Library {self.library_name} not found")
            return {'CANCELLED'}
        
        # Get all assets in this category
        assets = [a for a in lib.assets if a.category == self.category]
        
        if not assets:
            self.report({'WARNING'}, f"No assets found in category {self.category}")
            return {'CANCELLED'}
        
        # Determine current state (enable all if any are disabled)
        has_disabled = any(not asset.enabled for asset in assets)
        
        # Set all to new state
        for asset in assets:
            asset.enabled = has_disabled
        
        # Update the cache
        from . import asset_cache
        asset_cache.update_category_assets_enabled_state(
            self.library_name,
            self.category,
            has_disabled
        )
        
        # Save preferences
        bpy.ops.wm.save_userpref()
        
        return {'FINISHED'}

class QP_LibraryPG(PropertyGroup):
    """Property group for asset browser libraries"""
    enabled: BoolProperty(
        name="Enabled",
        default=False
    )
    index: StringProperty()


# =============================================================================
# Pie Menu Builder PropertyGroups
# =============================================================================

def get_key_items(self, context):
    """Return available keyboard keys for shortcuts"""
    keys = [
        ('NONE', "None", "No key assigned"),
        ('A', "A", ""), ('B', "B", ""), ('C', "C", ""), ('D', "D", ""),
        ('E', "E", ""), ('F', "F", ""), ('G', "G", ""), ('H', "H", ""),
        ('I', "I", ""), ('J', "J", ""), ('K', "K", ""), ('L', "L", ""),
        ('M', "M", ""), ('N', "N", ""), ('O', "O", ""), ('P', "P", ""),
        ('Q', "Q", ""), ('R', "R", ""), ('S', "S", ""), ('T', "T", ""),
        ('U', "U", ""), ('V', "V", ""), ('W', "W", ""), ('X', "X", ""),
        ('Y', "Y", ""), ('Z', "Z", ""),
        ('ZERO', "0", ""), ('ONE', "1", ""), ('TWO', "2", ""), ('THREE', "3", ""),
        ('FOUR', "4", ""), ('FIVE', "5", ""), ('SIX', "6", ""), ('SEVEN', "7", ""),
        ('EIGHT', "8", ""), ('NINE', "9", ""),
        ('F1', "F1", ""), ('F2', "F2", ""), ('F3', "F3", ""), ('F4', "F4", ""),
        ('F5', "F5", ""), ('F6', "F6", ""), ('F7', "F7", ""), ('F8', "F8", ""),
        ('F9', "F9", ""), ('F10', "F10", ""), ('F11', "F11", ""), ('F12', "F12", ""),
        ('SPACE', "Space", ""), ('TAB', "Tab", ""),
        ('ACCENT_GRAVE', "` (Accent)", ""),
    ]
    return keys


class QP_ContextRule(PropertyGroup):
    """Context rule for conditional item visibility"""

    enabled: BoolProperty(
        name="Enabled",
        default=True,
        description="Enable this rule"
    )

    rule_type: EnumProperty(
        name="Rule Type",
        items=[
            ('MODE', "Mode", "Filter by Blender mode (Object, Edit, Sculpt, etc.)"),
            ('OBJECT_TYPE', "Object Type", "Filter by active object type"),
            ('SPACE_TYPE', "Space Type", "Filter by current editor type"),
        ],
        default='MODE',
        description="Type of context rule"
    )

    mode_filter: EnumProperty(
        name="Mode",
        items=[
            ('OBJECT', "Object Mode", ""),
            ('EDIT_MESH', "Edit Mode (Mesh)", ""),
            ('EDIT_CURVE', "Edit Mode (Curve)", ""),
            ('EDIT_SURFACE', "Edit Mode (Surface)", ""),
            ('EDIT_ARMATURE', "Edit Mode (Armature)", ""),
            ('EDIT_METABALL', "Edit Mode (Metaball)", ""),
            ('EDIT_LATTICE', "Edit Mode (Lattice)", ""),
            ('EDIT_GPENCIL', "Edit Mode (Grease Pencil)", ""),
            ('SCULPT', "Sculpt Mode", ""),
            ('PAINT_WEIGHT', "Weight Paint", ""),
            ('PAINT_VERTEX', "Vertex Paint", ""),
            ('PAINT_TEXTURE', "Texture Paint", ""),
            ('POSE', "Pose Mode", ""),
            ('SCULPT_GPENCIL', "Sculpt (Grease Pencil)", ""),
            ('PAINT_GPENCIL', "Draw (Grease Pencil)", ""),
            ('WEIGHT_GPENCIL', "Weight Paint (Grease Pencil)", ""),
            ('VERTEX_GPENCIL', "Vertex Paint (Grease Pencil)", ""),
        ],
        default='OBJECT',
        description="Blender mode to match"
    )

    object_type_filter: EnumProperty(
        name="Object Type",
        items=[
            ('MESH', "Mesh", ""),
            ('CURVE', "Curve", ""),
            ('SURFACE', "Surface", ""),
            ('META', "Metaball", ""),
            ('FONT', "Text", ""),
            ('ARMATURE', "Armature", ""),
            ('LATTICE', "Lattice", ""),
            ('EMPTY', "Empty", ""),
            ('GPENCIL', "Grease Pencil", ""),
            ('CAMERA', "Camera", ""),
            ('LIGHT', "Light", ""),
            ('SPEAKER', "Speaker", ""),
            ('LIGHT_PROBE', "Light Probe", ""),
            ('VOLUME', "Volume", ""),
        ],
        default='MESH',
        description="Object type to match"
    )

    space_type_filter: EnumProperty(
        name="Space Type",
        items=[
            ('VIEW_3D', "3D Viewport", ""),
            ('NODE_EDITOR', "Node Editor", ""),
            ('IMAGE_EDITOR', "Image Editor", ""),
            ('SEQUENCE_EDITOR', "Video Sequencer", ""),
            ('CLIP_EDITOR', "Movie Clip Editor", ""),
            ('DOPESHEET_EDITOR', "Dope Sheet", ""),
            ('GRAPH_EDITOR', "Graph Editor", ""),
            ('NLA_EDITOR', "NLA Editor", ""),
            ('TEXT_EDITOR', "Text Editor", ""),
        ],
        default='VIEW_3D',
        description="Editor type to match"
    )

    invert: BoolProperty(
        name="Invert",
        default=False,
        description="Invert the rule result (NOT)"
    )


class QP_PieMenuItem(PropertyGroup):
    """Single item in a custom pie menu"""

    name: StringProperty(
        name="Name",
        default="New Item",
        description="Display name for this item"
    )

    id: StringProperty(
        name="ID",
        default="",
        description="Unique identifier for this item"
    )

    enabled: BoolProperty(
        name="Enabled",
        default=True,
        description="Enable this item"
    )

    icon: StringProperty(
        name="Icon",
        default="NONE",
        description="Blender icon name"
    )

    action_type: EnumProperty(
        name="Item Type",
        items=[
            ('SMART_ACTION', "Smart Action", "Context-aware action that adapts to current mode"),
            ('OPERATOR', "Operator", "Execute a specific Blender operator"),
            ('SHORTCUT', "Shortcut", "Simulate a keyboard shortcut (e.g., Shift+D)"),
            ('PROPERTY_TOGGLE', "Toggle", "Toggle a boolean property on/off"),
        ],
        default='SMART_ACTION',
        description="Type of action this item performs"
    )

    # Smart action settings
    smart_action_id: StringProperty(
        name="Smart Action",
        default="",
        description="ID of the smart action to execute"
    )

    smart_action_contexts: StringProperty(
        name="Enabled Contexts",
        default="",
        description="Comma-separated list of enabled contexts (empty = all)"
    )

    # Operator action settings
    operator_idname: StringProperty(
        name="Operator",
        default="",
        description="Blender operator identifier (e.g., mesh.subdivide)"
    )

    operator_props: StringProperty(
        name="Operator Properties",
        default="{}",
        description="JSON string of operator properties"
    )

    # Shortcut action settings
    shortcut_key: EnumProperty(
        name="Key",
        items=get_key_items,
        default=0,
        description="Key to simulate"
    )

    shortcut_ctrl: BoolProperty(
        name="Ctrl",
        default=False,
        description="Include Ctrl modifier"
    )

    shortcut_alt: BoolProperty(
        name="Alt",
        default=False,
        description="Include Alt modifier"
    )

    shortcut_shift: BoolProperty(
        name="Shift",
        default=False,
        description="Include Shift modifier"
    )

    # Property action settings
    smart_toggle_id: StringProperty(
        name="Smart Toggle",
        default="",
        description="ID of the smart toggle preset"
    )

    property_data_path: StringProperty(
        name="Property",
        default="",
        description="Property data path (e.g., use_snap)"
    )

    property_context: EnumProperty(
        name="Context",
        items=[
            ('TOOL_SETTINGS', "Tool Settings", "Tool settings property"),
            ('SCENE', "Scene", "Scene property"),
            ('OBJECT', "Active Object", "Active object property"),
            ('SPACE', "Space Data", "Current space/editor property"),
        ],
        default='TOOL_SETTINGS',
        description="Where to find the property"
    )

    # Pie position (0-7 for 8 directions: W, E, S, N, NW, NE, SW, SE)
    pie_position: IntProperty(
        name="Position",
        default=-1,
        min=-1,
        max=7,
        description="Position in the pie menu (-1 = auto)"
    )

    # Context rules
    context_rules: CollectionProperty(type=QP_ContextRule)

    context_match_mode: EnumProperty(
        name="Match Mode",
        items=[
            ('ANY', "Any", "Show if any rule matches"),
            ('ALL', "All", "Show only if all rules match"),
        ],
        default='ANY',
        description="How to combine multiple rules"
    )

    # UI state
    expanded: BoolProperty(name="Expanded", default=False)


def update_custom_pie_keymap(self, context):
    """Callback when pie menu keymap settings change"""
    try:
        from . import pie_menu_builder
        pie_menu_builder.PieMenuKeymapManager.refresh_pie_menu_keymap(self)
    except Exception as e:
        print(f"QP_Tools: Error updating pie menu keymap: {e}")
    # Save preferences
    try:
        bpy.ops.wm.save_userpref()
    except:
        pass


class QP_CustomPieMenu(PropertyGroup):
    """A user-defined pie menu"""

    name: StringProperty(
        name="Menu Name",
        default="New Pie Menu",
        description="Name of this pie menu"
    )

    id: StringProperty(
        name="Menu ID",
        default="",
        description="Unique identifier for this menu"
    )

    enabled: BoolProperty(
        name="Enabled",
        default=True,
        update=update_custom_pie_keymap,
        description="Enable this pie menu"
    )

    icon: StringProperty(
        name="Icon",
        default="NONE",
        description="Icon for this menu"
    )

    # Keymap settings
    keymap_key: EnumProperty(
        name="Key",
        items=get_key_items,
        default=0,  # NONE
        update=update_custom_pie_keymap,
        description="Keyboard key to trigger this menu"
    )

    keymap_ctrl: BoolProperty(
        name="Ctrl",
        default=False,
        update=update_custom_pie_keymap,
        description="Require Ctrl modifier"
    )

    keymap_alt: BoolProperty(
        name="Alt",
        default=False,
        update=update_custom_pie_keymap,
        description="Require Alt modifier"
    )

    keymap_shift: BoolProperty(
        name="Shift",
        default=False,
        update=update_custom_pie_keymap,
        description="Require Shift modifier"
    )

    keymap_oskey: BoolProperty(
        name="OS Key",
        default=False,
        update=update_custom_pie_keymap,
        description="Require OS/Windows/Command modifier"
    )

    keymap_space: EnumProperty(
        name="Editor",
        items=[
            ('VIEW_3D', "3D Viewport", "Works in 3D Viewport"),
            ('NODE_EDITOR', "Node Editor", "Works in Node Editor"),
            ('IMAGE_EDITOR', "Image Editor", "Works in Image Editor"),
            ('EMPTY', "Global", "Works in all editors"),
        ],
        default='VIEW_3D',
        update=update_custom_pie_keymap,
        description="Editor where this shortcut works"
    )

    # Menu items
    items: CollectionProperty(type=QP_PieMenuItem)
    active_item_index: IntProperty(name="Active Item", default=0)

    # UI state
    expanded: BoolProperty(name="Expanded", default=True)
    show_keymap_settings: BoolProperty(name="Show Keymap Settings", default=True)


# Install library operator
class QP_OT_InstallLibrary(Operator):
    bl_idname = "qp.install_library"
    bl_label = "Install Library"
    bl_description = "Install a new asset library from a zip file"
    filepath: StringProperty(name="Zip File", subtype='FILE_PATH')
    directory: StringProperty(name="Extract Location", subtype='DIR_PATH')
    step: IntProperty(default=0, options={'HIDDEN'})
    library_name: StringProperty(options={'HIDDEN'})
    zip_path: StringProperty(name="Zip File Path", options={'HIDDEN'})
    filter_glob: StringProperty(
        default="*.zip",
        options={'HIDDEN'},
    )
    
    def invoke(self, context, event):
        self.step = 0
        self.zip_path = ""  # Reset zip path
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
    
    def execute(self, context):
        if self.step == 0:
            # First step - zip file selected
            if not self.filepath or not os.path.exists(self.filepath):
                self.report({'ERROR'}, "Invalid zip file")
                return {'CANCELLED'}
                
            # Store zip path and library name
            self.zip_path = self.filepath  # Store the filepath
            self.library_name = os.path.splitext(os.path.basename(self.filepath))[0]
            
            # Move to step 2 - select destination folder
            self.step = 1
            self.directory = ""
            context.window_manager.fileselect_add(self)
            return {'RUNNING_MODAL'}
            
        elif self.step == 1:
            # Second step - destination folder selected
            if not self.directory:
                self.report({'ERROR'}, "No directory selected")
                return {'CANCELLED'}
                
            # Verify zip file exists
            if not self.zip_path or not os.path.exists(self.zip_path):
                self.report({'ERROR'}, f"Zip file not found: {self.zip_path}")
                return {'CANCELLED'}
                
            # Use the selected directory directly as the extract path
            extract_dir = self.directory
            
            try:
                # Extract files directly to the selected directory
                with zipfile.ZipFile(self.zip_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)
                
                # Find the root folder from the zip to use as library name
                with zipfile.ZipFile(self.zip_path, 'r') as zip_ref:
                    root_dirs = {path.split('/')[0] for path in zip_ref.namelist() if path != '/' and '/' in path}
                
                # If we found a single root dir, use it as the library name
                if len(root_dirs) == 1:
                    library_name = list(root_dirs)[0]
                    # Create the full path that includes the root folder
                    library_path = os.path.join(extract_dir, library_name)
                else:
                    # Otherwise fall back to zip filename without extension
                    library_name = self.library_name
                    library_path = extract_dir
                
                # Add to Blender's asset libraries
                asset_libs = context.preferences.filepaths.asset_libraries
                
                # Check if library already exists
                existing_lib = None
                for lib in asset_libs:
                    if lib.name == library_name:
                        existing_lib = lib
                        break

                if existing_lib:
                    # Update existing library
                    existing_lib.path = library_path
                    self.report({'INFO'}, f"Updated library: {library_name}")
                else:
                    # Add new library with the path that includes the root folder
                    pre_count = len(asset_libs)
                    bpy.ops.preferences.asset_library_add(directory=library_path)
                    
                    # Find the newly added library
                    if len(asset_libs) > pre_count:
                        # The new library is the last one added
                        new_lib = asset_libs[-1]
                        new_lib.name = library_name
                    else:
                        self.report({'WARNING'}, "Library added but couldn't be renamed")
                
                # Sync with our preferences
                sync_asset_libraries(context)
                
                # Save user preferences
                bpy.ops.wm.save_userpref()
                
                self.report({'INFO'}, f"Installed library: {library_name}")
                return {'FINISHED'}
                
            except Exception as e:
                self.report({'ERROR'}, f"Installation failed: {str(e)}")
                import traceback
                traceback.print_exc()
                return {'CANCELLED'}
                
        return {'CANCELLED'}

def sync_asset_libraries(context):
    """Sync Blender's asset libraries with our preferences"""
    prefs = context.preferences.addons[__package__].preferences
    blender_libs = context.preferences.filepaths.asset_libraries
    
    # Remember enabled libraries
    enabled_libs = {lib.name: lib.enabled for lib in prefs.asset_libraries}
    
    # Clear our libraries
    prefs.asset_libraries.clear()
    
    # Add each Blender library to our preferences
    for lib in blender_libs:
        new_lib = prefs.asset_libraries.add()
        new_lib.name = lib.name
        new_lib.path = lib.path
        # Keep enabled state if previously set, otherwise default to disabled
        new_lib.enabled = enabled_libs.get(lib.name, False)


class QP_OT_SyncAssetLibraries(Operator):
    bl_idname = "qp.sync_asset_libraries"
    bl_label = "Sync Libraries"
    bl_description = "Sync the Tools Asset Pie Menu with Blender's asset libraries"
    
    def execute(self, context):
        sync_asset_libraries(context)
        return {'FINISHED'}

class QP_OT_ToggleAllAssets(Operator):
    """Toggle all assets in a library"""
    bl_idname = "qp.toggle_all_assets"
    bl_label = "Toggle All Assets"
    
    library_name: StringProperty(name="Library Name")
    
    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences
        lib = next((l for l in prefs.asset_libraries if l.name == self.library_name), None)
        
        if not lib:
            self.report({'ERROR'}, f"Library {self.library_name} not found")
            return {'CANCELLED'}
        
        # Determine current state (enabled if any are disabled)
        has_disabled = any(not asset.enabled for asset in lib.assets)
        
        # Set all to new state
        for asset in lib.assets:
            asset.enabled = has_disabled
        
        # Save preferences
        bpy.ops.wm.save_userpref()
        
        action = "Enabled" if has_disabled else "Disabled"
        self.report({'INFO'}, f"{action} all assets in {self.library_name}")
        return {'FINISHED'}

class QP_OT_ToggleAsset(Operator):
    """Toggle an asset's enabled state"""
    bl_idname = "qp.toggle_asset"
    bl_label = "Toggle Asset"
    
    library_name: StringProperty(name="Library Name")
    asset_name: StringProperty(name="Asset Name")
    filepath: StringProperty(name="File Path")
    
    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences
        lib = next((l for l in prefs.asset_libraries if l.name == self.library_name), None)
        
        if not lib:
            self.report({'ERROR'}, f"Library {self.library_name} not found")
            return {'CANCELLED'}
        
        # Find the asset by name and filepath (to handle duplicate names)
        asset = next((a for a in lib.assets 
                     if a.name == self.asset_name and a.filepath == self.filepath), None)
        
        if not asset:
            self.report({'ERROR'}, f"Asset {self.asset_name} not found")
            return {'CANCELLED'}
        
        # Toggle the enabled state
        asset.enabled = not asset.enabled
        
        # Update the cache
        from . import asset_cache
        asset_cache.update_asset_enabled_state(
            self.library_name,
            self.asset_name,
            self.filepath,
            asset.enabled
        )
        
        # Save preferences
        bpy.ops.wm.save_userpref()
        
        return {'FINISHED'}

class QP_OT_ShowLibraryAssets(Operator):
    """Show assets from a specific library"""
    bl_idname = "qp.show_library_assets"
    bl_label = "Library Assets"
    
    library_name: StringProperty(name="Library Name")
    
    def execute(self, context):
        # Store library name for the popup
        context.window_manager.library_name = self.library_name
        bpy.ops.wm.call_menu(name="QP_MT_library_assets_menu")
        return {'FINISHED'}

def connect_object_to_node_modifier(imported_obj, source_obj):
    """Connect source_obj to the imported_obj's geometry nodes modifier
    
    Improved to handle any object type and maintain compatibility with Blender 4.1-4.3+
    
    Args:
        imported_obj: The newly imported object with Geometry Nodes modifiers
        source_obj: The source object to connect to the modifier
        
    Returns:
        bool: True if connection was successful, False otherwise
    """
    if not imported_obj or not source_obj:
        return False
        
    # Find Geometry Nodes modifiers on the imported object
    for mod in imported_obj.modifiers:
        if mod.type != 'NODES':
            continue
            
        # Handle earlier Blender versions where node_group might not exist
        if not hasattr(mod, 'node_group') or not mod.node_group:
            continue
            
        # Find the Group Input node
        input_node = None
        for node in mod.node_group.nodes:
            if node.type == 'GROUP_INPUT':
                input_node = node
                break
                
        if not input_node:
            continue
        
        # Different approaches to find suitable sockets
        object_socket = None
        first_object_socket = None
        named_object_socket = None
        fallback_socket = None
        
        # Scan all sockets to find the best match
        for socket in input_node.outputs:
            # Check socket type (across different Blender versions)
            is_object_socket = False
            
            # Method 1: Check by type name (most reliable)
            if hasattr(socket, 'type') and socket.type == 'OBJECT':
                is_object_socket = True
            # Method 2: Check by bl_idname (for newer versions)
            elif hasattr(socket, 'bl_idname') and ('object' in socket.bl_idname.lower() or 'nodeobject' in socket.bl_idname.lower()):
                is_object_socket = True
            # Method 3: Check by name for versions that don't expose types properly
            elif socket.name.lower() in ['object', 'target', 'target object']:
                is_object_socket = True
                named_object_socket = socket
            
            # Keep track of first object socket for fallback
            if is_object_socket and not first_object_socket:
                first_object_socket = socket
            
            # Priority 1: Socket named exactly "Object" (case insensitive)
            if socket.name.lower() == "object" and is_object_socket:
                object_socket = socket
                break
            
            # Track a fallback socket that seems appropriate
            if not fallback_socket and socket.name.lower() in [
                'instance', 'instances', 'target', 'input', 'mesh', 'geometry',
                'points', 'curve', 'curves', 'target_object', 'input_object'
            ]:
                fallback_socket = socket
        
        # Choose best socket with priority order
        target_socket = object_socket or named_object_socket or first_object_socket or fallback_socket
        
        if target_socket:
            # Get the socket identifier (might be different across versions)
            if hasattr(target_socket, 'identifier'):
                socket_id = target_socket.identifier
            else:
                # Fallback for older versions - use name or index
                socket_id = target_socket.name
            
            # Try different methods to assign object to socket
            try:
                # Method 1: Direct assignment (most common)
                mod[socket_id] = source_obj
                
                # For some Blender versions, we may need to trigger a viewport update
                if hasattr(mod, 'show_viewport'):
                    # Toggle to force update
                    last_state = mod.show_viewport
                    mod.show_viewport = not last_state
                    mod.show_viewport = last_state
                
                print(f"Connected {source_obj.name} to {imported_obj.name}'s {mod.name} modifier via socket: {target_socket.name}")
                return True
            except Exception as e:
                print(f"Direct assignment failed: {e}")
                try:
                    # Method 2: For some versions, use a different property format
                    setattr(mod, f"Input_{socket_id}", source_obj)
                    print(f"Alternative connection method successful for {source_obj.name}")
                    return True
                except Exception as e2:
                    print(f"Alternative connection method failed: {e2}")
    
    return False

def find_asset_browser_area():
    """Find the asset browser area and window if it exists"""
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.ui_type == 'ASSETS':
                return window, area
    return None, None

def get_selected_assets_from_browser(context):
    """Get selected assets from the asset browser using temp_override"""
    window, area = find_asset_browser_area()
    if not window or not area:
        return []
        
    assets = []
    try:
        with context.temp_override(window=window, area=area):
            if context.selected_assets:
                assets = context.selected_assets
    except Exception as e:
        print(f"Error getting selected assets: {e}")
        
    return assets

def quick_asset_path_update(self, context):
    """Save preferences when the Quick Asset Library path is changed"""
    # Validate the path exists
    if self.quick_asset_library_path and os.path.exists(self.quick_asset_library_path):
        # Auto-save user preferences
        bpy.ops.wm.save_userpref()
        # Update library paths in current scene if it exists
        update_library_path_from_preferences()
    

class QP_Tools_Preferences(AddonPreferences):
    bl_idname = __package__
    
    module_settings_changed: BoolProperty(default=False)

    # Active tab property
    active_tab: EnumProperty(
        name="Tabs",
        description="Choose tab to view",
        items=[
            ('CORE', "Core Modules", "Core module settings"),
            ('ASSETS', "Tool Assets Pie Menu", "Asset library and shortcut settings"),
            ('ASSETBROWSER', "Asset Browser Pie Menu", "Asset browser pie menu settings"),
            ('PIE_BUILDER', "Pie Menu Builder", "Create custom pie menus"),
        ],
        default='CORE'
    )
    
    # Asset library search and filtering
    asset_library_search: StringProperty(
        name="Filter Libraries",
        description="Filter asset libraries and assets",
        update=lambda self, context: None  # Trigger UI update
    )

    # Core module activation properties
    link_node_groups_enabled: BoolProperty(
        name="Link Node Groups",
        default=True,
        update=update_module_state
    )
    texture_set_builder_enabled: BoolProperty(
        name="TextureSet Builder",
        default=True,
        update=update_module_state
    )
    project_box_flat_enabled: BoolProperty(
        name="Project Box/Flat",
        default=True,
        update=update_module_state
    )
    edge_select_enabled: BoolProperty(
        name="Edge Select",
        default=True,
        update=update_module_state
    )
    collection_offset_enabled: BoolProperty(
        name="Collection Offset",
        default=True,
        update=update_module_state
    )
    bevel_weight_enabled: BoolProperty(
        name="Bevel Weight",
        default=True,
        update=update_module_state
    )
    floating_panel_enabled: BoolProperty(
        name="Floating Panel",
        default=True,
        update=update_module_state
    )
    lattice_setup_enabled: BoolProperty(
        name="Lattice Setup",
        default=True,
        update=update_module_state
    )
    materiallist_enabled: BoolProperty(
        name="Material List",
        default=True,
        update=update_module_state
    )
    cleanup_enabled: BoolProperty(
        name="CleanUp",
        default=True,
        update=update_module_state
    )

    show_advanced_cache_options: BoolProperty(
        name="Show Advanced Cache Options",
        description="Show advanced cache management options",
        default=False
    )

    # Asset browser and tools pie menu properties
    asset_browser_pie_enabled: BoolProperty(
        name="Asset Browser Pie Menu",
        default=True,
        update=update_module_state
    )

    asset_browser_libraries: CollectionProperty(type=QP_LibraryPG)

    qp_tools_pie_menu_enabled: BoolProperty(
        name="Tool Assets Pie Menu",
        default=True,
        update=update_module_state
    )

    asset_library_show_active_only: BoolProperty(
        name="Show Active Only",
        description="Show only active libraries in the tool assets pie menu",
        default=False
    )

    asset_browser_search: StringProperty(
        name="Filter Libraries",
        description="Filter asset browser libraries by name",
        update=lambda self, context: None  # Trigger UI update
    )

    asset_browser_show_active_only: BoolProperty(
        name="Show Active Only",
        description="Show only active libraries in the asset browser pie menu",
        default=False
    )

    # Quick Asset Library properties
    quick_asset_library_enabled: BoolProperty(
        name="Quick Asset Library",
        default=True,
        update=update_module_state
    )

    # Pie Menu Builder properties
    pie_menu_builder_enabled: BoolProperty(
        name="Pie Menu Builder",
        default=True,
        update=update_module_state
    )

    quick_asset_library_path: StringProperty(
        name="Default Library Path",
        description="Default path for the asset library",
        default="",
        subtype='DIR_PATH',
        update=quick_asset_path_update
    )

    # Add columns property for asset display
    assets_columns: IntProperty(
        name="Asset Columns",
        description="Number of columns to display assets (useful if you have many assets)",
        default=3,
        min=1,
        max=4
    )
    
    # Asset libraries collection property
    asset_libraries: CollectionProperty(type=QP_AssetLibrary)

    # Custom pie menus collection property
    custom_pie_menus: CollectionProperty(type=QP_CustomPieMenu)

    def draw(self, context):
        layout = self.layout
        
        # Add restart message only if changes were made in this session
        if self.module_settings_changed:
            box = layout.box()
            box.alert = True
            box.label(text="Restart Blender to apply module changes", icon='ERROR')
        
        # Tab selector
        row = layout.row()
        row.prop(self, "active_tab", expand=True)
        row.scale_y = 2
        
        # Create box for tab content
        box = layout.box()
        
        # CORE MODULES TAB
        if self.active_tab == 'CORE':
            box.label(text="Core QP Tools Settings", icon='TOOL_SETTINGS')
            
            # Asset Library Installation Box
            lib_box = box.box()
            lib_box.scale_y = 1.5
            lib_box.label(text="Asset Library Management", icon='ASSET_MANAGER')
            lib_box.operator("qp.install_library", icon='IMPORT')
            
            # Module Activation Box
            module_box = box.box()
            module_box.label(text="Module Activation (Changes require restart)", icon='PRESET')
            
            # Create a grid for the toggle buttons - 2 columns
            grid = module_box.grid_flow(row_major=True, columns=2, even_columns=True)
            
            # Helper function to create a stylized toggle button
            def draw_toggle_button(layout, prop_name, label):
                row = layout.row(align=True)
                row.scale_y = 1.5
                is_enabled = getattr(self, prop_name)
                
                # Create stylized button that looks like a toggle
                op = row.operator(
                    "qp.toggle_module",
                    text=label,
                    depress=is_enabled,
                    icon='CHECKBOX_HLT' if is_enabled else 'CHECKBOX_DEHLT'
                )
                op.module_prop = prop_name
                
                # Set appearance based on state
                if is_enabled:
                    row.active = True
                else:
                    row.active = False

            # 3D View modules
            col2 = grid.column(align=True)
            col2.label(text="3D View Tools:", icon='VIEW3D')
            draw_toggle_button(col2, "edge_select_enabled", "Assign VGroup")
            draw_toggle_button(col2, "collection_offset_enabled", "Collection Offset")
            draw_toggle_button(col2, "bevel_weight_enabled", "Bevel Weight")
            draw_toggle_button(col2, "floating_panel_enabled", "Floating Panel")
            draw_toggle_button(col2, "lattice_setup_enabled", "Lattice Setup")
            draw_toggle_button(col2, "materiallist_enabled", "Material List")
            draw_toggle_button(col2, "cleanup_enabled", "CleanUp")

            # Node editor modules
            col1 = grid.column(align=True)
            col1.label(text="Node Editor Tools:", icon='NODETREE')
            draw_toggle_button(col1, "link_node_groups_enabled", "Link Node Groups")
            draw_toggle_button(col1, "texture_set_builder_enabled", "TextureSet Builder")
            draw_toggle_button(col1, "project_box_flat_enabled", "Project Box/Flat")

            # UX modules
            ux_col = module_box.column(align=True)
            ux_col.label(text="User Experience Tools:", icon='WINDOW')
            draw_toggle_button(ux_col, "quick_asset_library_enabled", "Quick Asset Library")
            draw_toggle_button(ux_col, "qp_tools_pie_menu_enabled", "Tool Assets Pie Menu")
            draw_toggle_button(ux_col, "asset_browser_pie_enabled", "Asset Browser Pie Menu")
            draw_toggle_button(ux_col, "pie_menu_builder_enabled", "Pie Menu Builder")
                        
            # Quick Asset Library settings (properly indented inside the CORE tab condition)
            if self.quick_asset_library_enabled:
                qal_box = module_box.box()
                qal_box.label(text="Quick Asset Library Settings", icon='LIBRARY_DATA_DIRECT')
                qal_box.prop(self, "quick_asset_library_path")

        # ASSETS TAB
        elif self.active_tab == 'ASSETS':
            from . import qp_tools_pie_menu
            qp_tools_pie_menu.draw_tool_assets_preferences(self, context, box)

        # ASSETBROWSER tab
        elif self.active_tab == 'ASSETBROWSER':
            from . import asset_browser_pie
            asset_browser_pie.draw_asset_browser_preferences(self, context, box)

        # PIE_BUILDER tab
        elif self.active_tab == 'PIE_BUILDER':
            from . import pie_menu_builder
            pie_menu_builder.draw_pie_builder_preferences(self, context, box)


def update_library_path_from_preferences():
    """Update the library path from preferences"""
    try:
        context = bpy.context
        if hasattr(context.scene, "asset_library_settings") and not context.scene.asset_library_settings.library_path:
            prefs = context.preferences.addons[__package__].preferences
            if prefs and prefs.quick_asset_library_path:
                context.scene.asset_library_settings.library_path = prefs.quick_asset_library_path
    except Exception as e:
        print(f"Error updating library path: {e}")
        import traceback
        traceback.print_exc()

@bpy.app.handlers.persistent
def reset_module_changes(_):
    """Reset the module_settings_changed flag on file load"""
    if __package__ in bpy.context.preferences.addons:
        prefs = bpy.context.preferences.addons[__package__].preferences
        prefs.module_settings_changed = False       


# Initial sync of asset libraries
@bpy.app.handlers.persistent
def sync_on_load(_):
    if bpy.context.preferences.addons.get(__package__):
        bpy.ops.qp.sync_asset_libraries()

def register():
    # Ensure old handlers are removed first
    for handler in bpy.app.handlers.load_post:
        if handler == sync_on_load or handler == reset_module_changes:
            bpy.app.handlers.load_post.remove(handler)
            
    # Register property for passing data between operators
    bpy.types.WindowManager.library_name = StringProperty()
    
    bpy.utils.register_class(QP_OT_ShowCoreModulesTab)
    bpy.utils.register_class(QP_OT_toggle_module)

    # Register property groups first (in dependency order)
    bpy.utils.register_class(QP_AssetItem)
    bpy.utils.register_class(QP_AssetLibrary)

    ModuleManager.safe_register_class(QP_LibraryPG)

    # Register pie menu builder property groups (in dependency order)
    bpy.utils.register_class(QP_ContextRule)
    bpy.utils.register_class(QP_PieMenuItem)
    bpy.utils.register_class(QP_CustomPieMenu)

    # Register operators
    bpy.utils.register_class(QP_OT_ToggleAsset)
    bpy.utils.register_class(QP_OT_ToggleCategory)
    bpy.utils.register_class(QP_OT_ToggleCategoryAssets)
    bpy.utils.register_class(QP_OT_InstallLibrary)
    bpy.utils.register_class(QP_OT_SyncAssetLibraries)
    
    # Register enhanced asset cache operators
    try:
        from . import asset_cache_operators
        ModuleManager.safe_register_class(asset_cache_operators.QP_OT_ScanLibraryAssets)
        ModuleManager.safe_register_class(asset_cache_operators.QP_OT_RefreshAssetCache)
        ModuleManager.safe_register_class(asset_cache_operators.QP_OT_AssetCacheStats)
        ModuleManager.safe_register_class(asset_cache_operators.QP_OT_ForceRefreshLibrary)
        ModuleManager.safe_register_class(asset_cache_operators.QP_OT_ShowCacheHealth)
        ModuleManager.safe_register_class(asset_cache_operators.QP_OT_ValidateLibrary)
    except Exception as e:
        print(f"Error registering asset cache operators: {e}")
    
    bpy.utils.register_class(QP_OT_ToggleAllAssets)
    bpy.utils.register_class(QP_OT_ShowLibraryAssets)
    bpy.utils.register_class(QP_OT_AppendAsset)
    
    # Register preferences with new property
    bpy.utils.register_class(QP_Tools_Preferences)
    
    # Add load handler
    if sync_on_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(sync_on_load)
    
    # Store current module states and reset change flag
    if reset_module_changes not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(reset_module_changes)


def unregister():
    # First remove handlers (keep references to avoid garbage collection)
    handlers_to_remove = []
    for handler in bpy.app.handlers.load_post:
        if handler == sync_on_load or handler == reset_module_changes:
            handlers_to_remove.append(handler)
    
    for handler in handlers_to_remove:
        bpy.app.handlers.load_post.remove(handler)
    
    # Clean up property before unregistering preferences
    if hasattr(bpy.types.WindowManager, "library_name"):
        del bpy.types.WindowManager.library_name
    
    # Unregister enhanced asset cache operators
    try:
        from . import asset_cache_operators
        ModuleManager.safe_unregister_class(asset_cache_operators.QP_OT_ValidateLibrary)
        ModuleManager.safe_unregister_class(asset_cache_operators.QP_OT_ShowCacheHealth)
        ModuleManager.safe_unregister_class(asset_cache_operators.QP_OT_ForceRefreshLibrary)
        ModuleManager.safe_unregister_class(asset_cache_operators.QP_OT_AssetCacheStats)
        ModuleManager.safe_unregister_class(asset_cache_operators.QP_OT_RefreshAssetCache)
        ModuleManager.safe_unregister_class(asset_cache_operators.QP_OT_ScanLibraryAssets)
    except Exception as e:
        print(f"Error unregistering asset cache operators: {e}")

    # Unregister operators
    bpy.utils.unregister_class(QP_OT_toggle_module)
    bpy.utils.unregister_class(QP_OT_AppendAsset)
    bpy.utils.unregister_class(QP_OT_ShowLibraryAssets)
    bpy.utils.unregister_class(QP_OT_ToggleAllAssets)
    bpy.utils.unregister_class(QP_OT_SyncAssetLibraries)
    bpy.utils.unregister_class(QP_OT_InstallLibrary)
    bpy.utils.unregister_class(QP_OT_ToggleCategoryAssets)
    bpy.utils.unregister_class(QP_OT_ToggleCategory)
    bpy.utils.unregister_class(QP_OT_ToggleAsset)
    bpy.utils.unregister_class(QP_OT_ShowCoreModulesTab)
    
    # Unregister property groups (in reverse dependency order)
    # Pie menu builder property groups first
    bpy.utils.unregister_class(QP_CustomPieMenu)
    bpy.utils.unregister_class(QP_PieMenuItem)
    bpy.utils.unregister_class(QP_ContextRule)

    ModuleManager.safe_unregister_class(QP_LibraryPG)
    bpy.utils.unregister_class(QP_AssetLibrary)
    bpy.utils.unregister_class(QP_AssetItem)

    # Unregister preferences last
    bpy.utils.unregister_class(QP_Tools_Preferences)