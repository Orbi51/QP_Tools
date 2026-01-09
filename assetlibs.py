import bpy
import os
import sys
import zipfile
import tempfile
import shutil
import json
from pathlib import Path
from bpy.types import Operator, Menu, Panel, PropertyGroup
from bpy.props import StringProperty, EnumProperty, BoolProperty, CollectionProperty, IntProperty

from .module_helper import ModuleManager

# Module state variables
module_enabled = True
_is_registered = False

# Global variables to store library information
asset_libraries = {}  # Dictionary to store library information
library_shortcuts = {}  # Dictionary to store shortcut info for each library

# Dictionary to store keymap items for unregistration
addon_keymaps = []

# Data structure for asset library tracking
class QPAssetLibrary(PropertyGroup):
    """Property group for tracking asset libraries"""
    name: StringProperty(
        name="Library Name",
        description="Name of the asset library"
    )
    filepath: StringProperty(
        name="Library Path",
        description="Path to the asset library",
        subtype='DIR_PATH'
    )
    shortcut_key: StringProperty(
        name="Shortcut Key",
        description="Shortcut key to access this library",
        default="ONE"
    )
    is_managed: BoolProperty(
        name="Managed by QP_Tools",
        description="Whether this library was installed by QP_Tools",
        default=True
    )
    active_index: IntProperty(
        name="Active Asset Index",
        default=0
    )
    expanded: BoolProperty(
        name="Expanded",
        description="Whether this library's assets are shown in the UI",
        default=False
    )
    is_enabled: BoolProperty(
        name="Scan Library",
        description="Enable scanning this library for assets (may impact performance)",
        default=False
    )

class QPAssetItem(PropertyGroup):
    """Property group for tracking assets within libraries"""
    name: StringProperty(
        name="Asset Name",
        description="Name of the asset"
    )
    filepath: StringProperty(
        name="Asset Path",
        description="Path to the asset file"
    )
    category: StringProperty(
        name="Category",
        description="Asset category"
    )
    is_object: BoolProperty(
        name="Is Object",
        description="Whether this asset is an object type",
        default=True
    )
    enabled: BoolProperty(
        name="Enabled",
        description="Whether this specific asset is enabled in menus and pie charts",
        default=False
    )
    thumbnail: StringProperty(
        name="Thumbnail Path",
        description="Path to asset thumbnail",
        default=""
    )

# Utility functions
def get_next_shortcut_key(context):
    """Get the next available shortcut key"""
    prefs = context.preferences.addons[__package__].preferences
    libraries = prefs.asset_libraries
    
    # Numeric keys from 1 to 9
    numeric_keys = ["ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT", "NINE"]
    
    # Find which keys are already used
    used_keys = [lib.shortcut_key for lib in libraries]
    
    # Find the first available key
    for key in numeric_keys:
        if key not in used_keys:
            return key
    
    # If all numeric keys are used, return ZERO as fallback
    return "ZERO"

def extract_zip_to_directory(zip_path, extract_path):
    """Extract a zip file to the specified directory"""
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_path)
    
    # Return the list of extracted top-level directories
    files = os.listdir(extract_path)
    dirs = [f for f in files if os.path.isdir(os.path.join(extract_path, f))]
    return dirs

def scan_for_assets(library_path, library_name=None):
    """Scan a directory for Blender assets"""
    import bpy
    from pathlib import Path
    
    # Check if library is enabled in preferences
    prefs = bpy.context.preferences.addons[__package__].preferences
    
    # If library_name is provided, check its enabled status
    if library_name:
        library = next((lib for lib in prefs.asset_libraries if lib.name == library_name), None)
        
        # If library found and disabled, return empty list
        if library and not library.is_enabled:
            print(f"Skipping library {library_name} as it is disabled")
            return []
    
    assets = []
    library_path = Path(library_path)
    
    # Find all .blend files
    blend_files = list(library_path.glob("**/*.blend"))
    
    if not blend_files:
        print(f"No .blend files found in {library_path}")
        return assets
    
    # Process each blend file
    for blend_file in blend_files:
        try:
            # Load only assets
            with bpy.data.libraries.load(str(blend_file), assets_only=True) as (data_from, _):
                # Determine category from path
                relative_path = blend_file.relative_to(library_path)
                category = relative_path.parent.name if relative_path.parent.name != '.' else 'Default'
                
                # Collect objects
                for obj_name in data_from.objects:
                    assets.append({
                        'name': obj_name,
                        'filepath': str(blend_file),
                        'category': category,
                        'is_object': True,
                        'thumbnail': ""
                    })
                
                # Collect collections
                for coll_name in data_from.collections:
                    assets.append({
                        'name': coll_name,
                        'filepath': str(blend_file),
                        'category': category,
                        'is_object': False,
                        'thumbnail': ""
                    })
        
        except Exception as e:
            print(f"Error scanning assets in {blend_file}: {e}")
    
    return assets

def update_library_list(context):
    """Update the list of asset libraries in the preferences"""
    prefs = context.preferences.addons[__package__].preferences
    libraries = prefs.asset_libraries
    
    # Clear existing items
    libraries.clear()
    
    # Add Blender's built-in asset libraries from preferences
    for lib in context.preferences.filepaths.asset_libraries:
        # Check if this library is already managed by us
        is_managed = False
        
        # Create new entry in our preferences
        new_lib = libraries.add()
        new_lib.name = lib.name
        new_lib.filepath = lib.path
        new_lib.is_managed = is_managed
        new_lib.is_enabled = False  # Disabled by default
        
        # Assign a shortcut key if this is a new managed library
        if is_managed and not lib.name in library_shortcuts:
            new_lib.shortcut_key = get_next_shortcut_key(context)
            library_shortcuts[lib.name] = new_lib.shortcut_key
        elif lib.name in library_shortcuts:
            new_lib.shortcut_key = library_shortcuts[lib.name]
    
    # Save user preferences
    bpy.ops.wm.save_userpref()

def update_asset_list(context, library_name):
    """Update the list of assets for a specific library"""
    try:
        prefs = context.preferences.addons[__package__].preferences
        prefs_cls = type(prefs)
        
        # Find the library
        library = next((lib for lib in context.preferences.filepaths.asset_libraries 
                        if lib.name == library_name), None)
        
        if not library:
            print(f"Library {library_name} not found")
            return
        
        # Prepare property name
        prop_name = f"assets_{library_name.lower().replace(' ', '_')}"
        
        # Ensure property exists on class
        if not hasattr(prefs_cls, prop_name):
            setattr(prefs_cls, prop_name, CollectionProperty(type=QPAssetItem))
        
        # Force property initialization
        if not hasattr(prefs, prop_name):
            setattr(prefs, prop_name, CollectionProperty(type=QPAssetItem)())
        
        # Get the asset list
        asset_list = getattr(prefs, prop_name)
        
        # Ensure it's not a deferred property
        if not hasattr(asset_list, 'add'):
            # Forcibly create a new collection property
            asset_list = CollectionProperty(type=QPAssetItem)()
            setattr(prefs, prop_name, asset_list)
        
        # Safely clear existing items
        if hasattr(asset_list, '__len__'):
            while len(asset_list) > 0:
                asset_list.remove(0)
        
        # Scan assets
        assets = scan_for_assets(library.path, library_name)
        
        # Populate asset list
        for asset in assets:
            new_asset = asset_list.add()
            new_asset.name = asset['name']
            new_asset.filepath = asset['filepath']
            new_asset.category = asset['category']
            new_asset.is_object = asset['is_object']
            new_asset.enabled = True
            new_asset.thumbnail = asset.get('thumbnail', "")
        
    
    except Exception as e:
        print(f"Error updating asset list for {library_name}: {e}")
        import traceback
        traceback.print_exc()

class ASSETLIB_OT_install_library(Operator):
    """Install an asset library from a zip file"""
    bl_idname = "assetlib.install_library"
    bl_label = "Install Asset Library"
    bl_options = {'REGISTER', 'UNDO'}
    
    filepath: StringProperty(
        name="Library Zip File",
        description="Path to the library zip file",
        subtype='FILE_PATH',
        default="",
    )
    
    directory: StringProperty(
        name="Installation Directory",
        description="Directory to install the library",
        subtype='DIR_PATH',
        default="",
    )
    
    # Store zip file path separately to avoid it being reset during directory selection
    zip_path: StringProperty(
        name="Zip File Path",
        description="Path to the zip file to install",
        default=""
    )
    
    filter_glob: StringProperty(
        default="*.zip",
        options={'HIDDEN'}
    )
    
    step: IntProperty(
        name="Step",
        description="Current installation step",
        default=0,
        options={'HIDDEN'}
    )
    
    def invoke(self, context, event):
        # Reset state
        self.step = 0
        self.zip_path = ""
        
        # Step 1: Choose a zip file
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
    
    def execute(self, context):
        if self.step == 0:
            # First step - zip file selection
            if not self.filepath or not os.path.exists(self.filepath):
                self.report({'ERROR'}, "Invalid zip file")
                return {'CANCELLED'}
            
            # Save zip file path
            self.zip_path = self.filepath
            
            # Move to next step - directory selection
            self.step = 1
            
            # Reset directory field and open directory selector
            self.directory = ""
            context.window_manager.fileselect_add(self)
            return {'RUNNING_MODAL'}
            
        elif self.step == 1:
            # Second step - directory selection complete
            if not self.directory:
                self.report({'ERROR'}, "No directory selected")
                return {'CANCELLED'}
                
            if not self.zip_path or not os.path.exists(self.zip_path):
                self.report({'ERROR'}, f"Zip file not found: {self.zip_path}")
                return {'CANCELLED'}
                
            # Execute the installation
            try:
                # Get the directory to extract to
                extract_path = self.directory
                
                # Create the directory if it doesn't exist
                os.makedirs(extract_path, exist_ok=True)
                
                # Extract the zip file directly into the directory
                with zipfile.ZipFile(self.zip_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_path)
                
                # Use the zip filename (without extension) for the library name
                zip_filename = os.path.basename(self.zip_path)
                library_name = os.path.splitext(zip_filename)[0]
                
                # Set library path to include the extracted folder with same name as the zip
                library_path = os.path.join(extract_path, library_name)
                
                # Add the library to Blender's asset libraries
                asset_libs = context.preferences.filepaths.asset_libraries
                
                # Check if library already exists
                library_exists = False
                for lib in asset_libs:
                    if lib.name == library_name:
                        self.report({'WARNING'}, f"Library '{library_name}' already exists, updating path")
                        lib.path = library_path
                        library_exists = True
                        break
                        
                # Create a new library if it doesn't exist
                if not library_exists:
                    # Use proper Blender API method
                    bpy.ops.preferences.asset_library_add(directory=library_path)
                    # Find the new library and rename it
                    for lib in asset_libs:
                        if lib.path == library_path:
                            lib.name = library_name
                            break
                
                # Update our library list
                update_library_list(context)
                
                # Create dynamic properties for the asset lists
                prefs = context.preferences.addons[__package__].preferences
                prefs_cls = prefs.__class__
                
                # Create a unique property name
                prop_name = f"assets_{library_name.lower().replace(' ', '_')}"
                
                # Check if property already exists
                if not hasattr(prefs_cls, prop_name):
                    # Create the property
                    setattr(prefs_cls, prop_name, CollectionProperty(type=QPAssetItem))
                
                # Now update the asset list
                update_asset_list(context, library_name)
                
                # Save user preferences
                bpy.ops.wm.save_userpref()
                
                self.report({'INFO'}, f"Asset library '{library_name}' installed successfully")
                return {'FINISHED'}
            
            except Exception as e:
                self.report({'ERROR'}, f"Error installing library: {e}")
                import traceback
                traceback.print_exc()
                return {'CANCELLED'}
                
        return {'CANCELLED'}

class ASSETLIB_OT_refresh_libraries(Operator):
    """Refresh the list of asset libraries"""
    bl_idname = "assetlib.refresh_libraries"
    bl_label = "Refresh Libraries"
    
    def execute(self, context):
        update_library_list(context)
        self.report({'INFO'}, "Asset libraries refreshed")
        return {'FINISHED'}

class ASSETLIB_OT_refresh_assets(Operator):
    """Refresh the list of assets for a specific library"""
    bl_idname = "assetlib.refresh_assets"
    bl_label = "Refresh Assets"
    
    library_name: StringProperty(
        name="Library Name",
        description="Name of the library to refresh"
    )
    
    def execute(self, context):
        update_asset_list(context, self.library_name)
        self.report({'INFO'}, f"Assets for '{self.library_name}' refreshed")
        return {'FINISHED'}

class ASSETLIB_MT_AssetLibraryPie(Menu):
    """Pie menu for displaying assets from a library"""
    bl_label = "Asset Library"
    bl_idname = "ASSETLIB_MT_AssetLibraryPie"
    
    library_name: StringProperty(
        name="Library Name",
        description="Name of the library to display"
    )
    
    def draw(self, context):
        layout = self.layout
        pie = layout.menu_pie()
        
        prefs = context.preferences.addons[__package__].preferences
        
        # Get the library from our list
        library = None
        for lib in prefs.asset_libraries:
            if lib.name == self.library_name:
                library = lib
                break
        
        if not library:
            pie.label(text=f"Library {self.library_name} not found")
            return
        
        # Get the asset list property name
        asset_list_name = f"assets_{self.library_name.lower().replace(' ', '_')}"
        
        # Check if the asset list exists
        if not hasattr(prefs, asset_list_name):
            pie.label(text=f"Asset list for {self.library_name} not found")
            return
        
        asset_list = getattr(prefs, asset_list_name)
        
        if len(asset_list) == 0:
            pie.label(text=f"No assets found in {self.library_name}")
            # Add refresh button
            pie.operator("assetlib.refresh_assets", text="Refresh Assets").library_name = self.library_name
            return
        
        # Get enabled assets that are objects
        enabled_assets = [asset for asset in asset_list if asset.enabled and asset.is_object]
        
        if not enabled_assets:
            pie.label(text=f"No enabled object assets in {self.library_name}")
            return
        
        # Group assets by category
        categories = {}
        for asset in enabled_assets:
            if asset.category not in categories:
                categories[asset.category] = []
            categories[asset.category].append(asset)
        
        # If there are 8 or fewer categories, show them in the pie menu
        if len(categories) <= 8:
            # Sort categories by name
            sorted_categories = sorted(categories.keys())
            
            # Add buttons for each category
            for category in sorted_categories:
                assets = categories[category]
                if len(assets) == 1:
                    # If only one asset in category, show direct append button
                    asset = assets[0]
                    op = pie.operator("assetlib.append_asset", text=f"{category}: {asset.name}")
                    op.filepath = asset.filepath
                    op.asset_name = asset.name
                else:
                    # If multiple assets, show submenu
                    submenu = pie.operator_menu_enum(
                        "assetlib.append_asset_from_list", 
                        "asset_enum",
                        text=f"{category} ({len(assets)})"
                    )
                    # Populate the enum dynamically
                    enum_items = []
                    for i, asset in enumerate(assets):
                        enum_items.append((f"{i}:{asset.name}:{asset.filepath}", asset.name, ""))
                    
                    # Store enum items temporarily
                    bpy.types.ASSETLIB_OT_append_asset_from_list.asset_enum_items = enum_items
        else:
            # Too many categories, show a flattened list
            pie.label(text=f"{len(enabled_assets)} assets available")
            # Show the first few assets directly
            for i, asset in enumerate(enabled_assets[:7]):
                op = pie.operator("assetlib.append_asset", text=asset.name)
                op.filepath = asset.filepath
                op.asset_name = asset.name
            
            # Add a "More..." button for additional assets
            pie.operator("assetlib.show_asset_browser", text=f"Show All {len(enabled_assets)} Assets...")

class ASSETLIB_OT_call_library_pie(Operator):
    """Open the pie menu for a specific library"""
    bl_idname = "assetlib.call_library_pie"
    bl_label = "Asset Library Menu"
    
    library_name: StringProperty(
        name="Library Name",
        description="Name of the library to display"
    )
    
    def execute(self, context):
        # Create a temporary operator to show the pie menu
        bpy.types.ASSETLIB_MT_AssetLibraryPie.library_name = self.library_name
        bpy.ops.wm.call_menu_pie(name="ASSETLIB_MT_AssetLibraryPie")
        return {'FINISHED'}

class ASSETLIB_OT_append_asset(Operator):
    """Append an asset from a library"""
    bl_idname = "assetlib.append_asset"
    bl_label = "Append Asset"
    bl_options = {'REGISTER', 'UNDO'}
    
    filepath: StringProperty(
        name="File Path",
        description="Path to the asset file"
    )
    
    asset_name: StringProperty(
        name="Asset Name",
        description="Name of the asset to append"
    )
    
    def execute(self, context):
        if not os.path.exists(self.filepath):
            self.report({'ERROR'}, f"File not found: {self.filepath}")
            return {'CANCELLED'}
        
        try:
            # Store cursor location
            cursor_loc = context.scene.cursor.location.copy()
            
            # Load asset
            with bpy.data.libraries.load(self.filepath) as (data_from, data_to):
                # Check if the asset exists in the file
                if self.asset_name in data_from.objects:
                    data_to.objects = [self.asset_name]
                else:
                    self.report({'ERROR'}, f"Asset '{self.asset_name}' not found in file")
                    return {'CANCELLED'}
            
            # Link to scene
            for obj in data_to.objects:
                if obj is not None:
                    context.scene.collection.objects.link(obj)
                    # Position at cursor
                    obj.location = cursor_loc
                    
                    # Select the object and make it active
                    bpy.ops.object.select_all(action='DESELECT')
                    obj.select_set(True)
                    context.view_layer.objects.active = obj
                    
                    self.report({'INFO'}, f"Asset '{obj.name}' appended at cursor location")
            
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Error appending asset: {e}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}

class ASSETLIB_OT_append_asset_from_list(Operator):
    """Append an asset from a predefined list (used by menu_enum)"""
    bl_idname = "assetlib.append_asset_from_list"
    bl_label = "Append Asset From List"
    bl_options = {'REGISTER', 'UNDO'}
    
    # This will be populated dynamically
    asset_enum_items = []
    
    def asset_enum_items_cb(self, context):
        return ASSETLIB_OT_append_asset_from_list.asset_enum_items
    
    asset_enum: EnumProperty(
        name="Asset",
        description="Asset to append",
        items=asset_enum_items_cb
    )
    
    def execute(self, context):
        # Parse the selected enum value
        parts = self.asset_enum.split(":", 2)
        if len(parts) < 3:
            self.report({'ERROR'}, "Invalid asset selection")
            return {'CANCELLED'}
        
        asset_name = parts[1]
        filepath = parts[2]
        
        # Call the regular append operator
        bpy.ops.assetlib.append_asset(filepath=filepath, asset_name=asset_name)
        return {'FINISHED'}

class ASSETLIB_OT_show_asset_browser(Operator):
    """Open the asset browser focused on the specified library"""
    bl_idname = "assetlib.show_asset_browser"
    bl_label = "Show Asset Browser"
    
    library_name: StringProperty(
        name="Library Name",
        description="Name of the library to focus on"
    )
    
    def execute(self, context):
        # Try to find existing asset browser
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'FILE_BROWSER':
                    for space in area.spaces:
                        if space.type == 'FILE_BROWSER' and hasattr(space, 'params'):
                            if hasattr(space, 'ui_type') and space.ui_type == 'ASSETS':
                                # Found asset browser, set the active library
                                if self.library_name:
                                    space.params.asset_library_reference = self.library_name
                                return {'FINISHED'}
        
        # If no asset browser found, create a new area
        try:
            # Get the largest area to split
            max_area = None
            max_size = 0
            for window in context.window_manager.windows:
                for area in window.screen.areas:
                    size = area.width * area.height
                    if size > max_size:
                        max_size = size
                        max_area = area
            
            if max_area:
                # Split the area
                bpy.ops.screen.area_split(direction='HORIZONTAL', factor=0.5)
                
                # Set the new area to asset browser
                new_area = context.screen.areas[-1]
                new_area.type = 'FILE_BROWSER'
                
                # Set to asset browser mode
                for space in new_area.spaces:
                    if space.type == 'FILE_BROWSER':
                        space.ui_type = 'ASSETS'
                        if self.library_name:
                            space.params.asset_library_reference = self.library_name
                        break
            
            return {'FINISHED'}
        
        except Exception as e:
            self.report({'ERROR'}, f"Error opening asset browser: {e}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}

def draw_preferences(preferences, context, layout):
    """Draw asset library settings in the preferences panel"""
    libraries_box = layout.box()
    libraries_box.label(text="Asset Libraries", icon='ASSET_MANAGER')
    
    row = libraries_box.row()
    row.operator("assetlib.install_library", icon='IMPORT')
    row.operator("assetlib.refresh_libraries", icon='FILE_REFRESH')
    
    # Directly use Blender's asset libraries
    asset_libraries = context.preferences.filepaths.asset_libraries
    
    if len(asset_libraries) == 0:
        libraries_box.label(text="No asset libraries installed yet", icon='INFO')
        return
    
    # List existing libraries
    for library in asset_libraries:
        lib_box = libraries_box.box()
        
        # Library header
        header_row = lib_box.row()
        
        # Find the corresponding library in our preferences
        qp_library = next((lib for lib in preferences.asset_libraries if lib.name == library.name), None)
        
        if qp_library:
            header_row.prop(qp_library, "is_enabled", text="")  # Add checkbox for library scanning
        
        header_row.label(text=f"{library.name}", icon='ASSET_MANAGER')
        
        if not qp_library or qp_library.is_enabled:
            # Scan and display assets directly
            assets = scan_for_assets(library.path, library.name)
            
            if assets:
                for asset in assets:
                    asset_row = lib_box.row()
                    asset_row.label(text=asset['name'], icon='OBJECT_DATA')
                    asset_row.label(text=asset['filepath'])
            else:
                lib_box.label(text="No assets found", icon='INFO')
        else:
            lib_box.label(text="Library scanning disabled", icon='CANCEL')

def register_library_keymap(library_name, shortcut_key="ONE"):
    """Register a keymap for a specific library"""
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    
    if kc:
        km = kc.keymaps.new(name='3D View', space_type='VIEW_3D')
        kmi = km.keymap_items.new(
            "assetlib.call_library_pie",
            shortcut_key, 'PRESS',
            ctrl=True,
            alt=True
        )
        kmi.properties.library_name = library_name
        addon_keymaps.append((km, kmi))
        return True
    
    return False

def update_keymaps():
    """Update keymaps for all libraries"""
    # Clear existing keymaps
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()
    
    # Get libraries from preferences
    prefs = bpy.context.preferences.addons[__package__].preferences
    
    for library in prefs.asset_libraries:
        if library.is_managed:
            register_library_keymap(library.name, library.shortcut_key)

def create_asset_list_properties():
    """Create dynamic properties for asset libraries"""
    if not hasattr(bpy, 'context') or bpy.context is None:
        return 1.0  # Try again in 1 second
    
    prefs = bpy.context.preferences.addons[__package__].preferences
    prefs_cls = type(prefs)
    
    # Iterate through Blender's asset libraries
    for lib in bpy.context.preferences.filepaths.asset_libraries:
        prop_name = f"assets_{lib.name.lower().replace(' ', '_')}"
        
        # Ensure property exists on class and instance
        if not hasattr(prefs_cls, prop_name):
            setattr(prefs_cls, prop_name, CollectionProperty(type=QPAssetItem))
        
        if not hasattr(prefs, prop_name):
            setattr(prefs, prop_name, CollectionProperty(type=QPAssetItem)())
    
    return None

def register():
    if not ModuleManager.register_module(sys.modules[__name__]):
        return
    
    # Only register QPAssetItem if it's not already registered
    try:
        ModuleManager.safe_register_class(QPAssetItem)
    except Exception as e:
        print(f"QPAssetItem registration warning: {e}")
    ModuleManager.safe_register_class(ASSETLIB_OT_install_library)
    ModuleManager.safe_register_class(ASSETLIB_OT_refresh_libraries)
    ModuleManager.safe_register_class(ASSETLIB_OT_refresh_assets)
    ModuleManager.safe_register_class(ASSETLIB_MT_AssetLibraryPie)
    ModuleManager.safe_register_class(ASSETLIB_OT_call_library_pie)
    ModuleManager.safe_register_class(ASSETLIB_OT_append_asset)
    ModuleManager.safe_register_class(ASSETLIB_OT_append_asset_from_list)
    ModuleManager.safe_register_class(ASSETLIB_OT_show_asset_browser)
    
    
    # Register delayed init function to create properties after other addon init
    bpy.app.timers.register(create_asset_list_properties, first_interval=2.0)
    
    # Update library list
    if hasattr(bpy, 'context') and bpy.context is not None:
        bpy.app.timers.register(lambda: update_library_list(bpy.context), first_interval=3.0)
    


def unregister():
    if not ModuleManager.unregister_module(sys.modules[__name__]):
        return
    
    # Remove keymaps
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()
    
    # Unregister classes in reverse order
    ModuleManager.safe_unregister_class(ASSETLIB_OT_show_asset_browser)
    ModuleManager.safe_unregister_class(ASSETLIB_OT_append_asset_from_list)
    ModuleManager.safe_unregister_class(ASSETLIB_OT_append_asset)
    ModuleManager.safe_unregister_class(ASSETLIB_OT_call_library_pie)
    ModuleManager.safe_unregister_class(ASSETLIB_MT_AssetLibraryPie)
    ModuleManager.safe_unregister_class(ASSETLIB_OT_refresh_assets)
    ModuleManager.safe_unregister_class(ASSETLIB_OT_refresh_libraries)
    ModuleManager.safe_unregister_class(ASSETLIB_OT_install_library)
    ModuleManager.safe_unregister_class(QPAssetLibrary)
    ModuleManager.safe_unregister_class(QPAssetItem)
    
    # Remove collection property from preferences
    if hasattr(bpy.types.Preferences, "asset_libraries"):
        delattr(bpy.types.Preferences, "asset_libraries")
    

if __name__ == "__main__":
    register()