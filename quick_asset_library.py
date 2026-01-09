import bpy
import os
import tempfile
import json
import subprocess
import threading
from bpy.props import (StringProperty, 
                      EnumProperty, 
                      BoolProperty,
                      PointerProperty)
from bpy.types import (Panel,
                      Operator,
                      PropertyGroup)

from .module_helper import ModuleManager
import sys

_conflict_cache = None
_conflict_cache_params = None
_file_scan_cache = {}
_file_scan_status = {}  # (filepath, data_type): "pending" | "done" | "error"
_file_scan_lock = threading.Lock()

# Load handler function
@bpy.app.handlers.persistent
def load_handler(dummy):
    """Handler to update library path when a new file is loaded"""
    update_library_path_from_preferences()

# Module state variables
module_enabled = True
_is_registered = False

# Function definitions from the original addon
def get_temp_file_path():
    """Get a unique temporary file path for status tracking"""
    return os.path.join(tempfile.gettempdir(), "quickasset_status.json")

def is_background_process_running():
    """Check if a background process is currently running"""
    status_file = get_temp_file_path()
    if os.path.exists(status_file):
        try:
            with open(status_file, 'r') as f:
                status = json.load(f)
                return status.get('running', False)
        except (OSError, json.JSONDecodeError):
            return False
    return False

def update_library_paths(self, context):
    """Update all library paths when preferences change"""
    default_path = context.preferences.addons[__package__].preferences.quick_asset_library_path
    
    # Only update empty paths
    if not context.scene.asset_library_settings.library_path:
        context.scene.asset_library_settings.library_path = default_path

def update_library_path_from_preferences():
    """Update the library path from preferences if it's empty"""
    try:
        context = bpy.context
        if hasattr(context.scene, "asset_library_settings") and not context.scene.asset_library_settings.library_path:
            prefs = context.preferences.addons[__package__].preferences
            if prefs and prefs.quick_asset_library_path:
                context.scene.asset_library_settings.library_path = prefs.quick_asset_library_path
    except (AttributeError, KeyError):
        pass  # Preferences or scene not available

def get_active_node_tree(context):
    space = context.space_data
    if not space.edit_tree:
        return None
        
    # For material nodes
    if space.tree_type == 'ShaderNodeTree':
        if context.active_object and context.active_object.active_material:
            return context.active_object.active_material.node_tree
    # For geometry nodes
    elif space.tree_type == 'GeometryNodeTree':
        return space.edit_tree
    # For compositor nodes
    elif space.tree_type == 'CompositorNodeTree':
        return space.edit_tree
    
    return None

def create_background_script():
    """Create a temporary script for the background Blender process"""
    script = '''
import bpy
import os
import json
import sys
import time
import tempfile

def log_message(msg):
    """Print a message and also write it to a log file"""
    print(msg)
    log_file = os.path.join(tempfile.gettempdir(), "quickasset_log.txt")
    try:
        with open(log_file, 'a') as f:
            f.write(msg + "\\n")
    except OSError:
        pass  # Could not write to log file

def update_status(status):
    """Update the status file"""
    status_file = os.path.join(tempfile.gettempdir(), "quickasset_status.json")
    try:
        with open(status_file, 'w') as f:
            json.dump(status, f)
    except Exception as e:
        log_message(f"Failed to update status: {str(e)}")

def process_assets():
    try:
        # Get arguments
        args = sys.argv[sys.argv.index("--") + 1:]
        params = json.loads(args[0])
        source_file = params["source_file"]
        target_file = params["target_file"]
        data_type = params["data_type"]
        asset_names = params["asset_names"]
        conflict_action = params.get("conflict_action", "OVERRIDE")
        catalog_uuid = params.get("catalog_uuid", "NONE")
        
        update_status({"running": True, "status": "Starting..."})
        
        # Create new file or open existing
        if os.path.exists(target_file):
            bpy.ops.wm.open_mainfile(filepath=target_file)
            
            # If overriding, remove existing assets first
            if conflict_action == 'OVERRIDE':
                if data_type == "objects":
                    for obj in bpy.data.objects[:]:  # Use slice to avoid modification during iteration
                        if obj.name in asset_names:
                            if obj.data:
                                bpy.data.meshes.remove(obj.data, do_unlink=True)
                            bpy.data.objects.remove(obj, do_unlink=True)
                elif data_type == "materials":
                    for mat in bpy.data.materials[:]:
                        if mat.name in asset_names:
                            bpy.data.materials.remove(mat, do_unlink=True)
                elif data_type == "node_groups":
                    for ng in bpy.data.node_groups[:]:
                        if ng.name in asset_names:
                            bpy.data.node_groups.remove(ng, do_unlink=True)
        else:
            bpy.ops.wm.read_factory_settings(use_empty=True)
            
        # Import assets from source file
        update_status({"running": True, "status": "Importing assets..."})
        
        with bpy.data.libraries.load(source_file) as (data_from, data_to):
            if data_type == "objects":
                data_to.objects = [name for name in asset_names if name in data_from.objects]
            elif data_type == "materials":
                data_to.materials = [name for name in asset_names if name in data_from.materials]
            elif data_type == "node_groups":
                data_to.node_groups = [name for name in asset_names if name in data_from.node_groups]
        
        # Link objects to scene if needed
        if data_type == "objects":
            for obj in bpy.data.objects:
                if obj.name in asset_names:
                    if obj.name not in bpy.context.scene.objects:
                        bpy.context.scene.collection.objects.link(obj)
        
        # Mark as assets and generate previews
        update_status({"running": True, "status": "Processing assets..."})
        
        def process_asset(data_block):
            """Helper function to process a single asset"""
            data_block.asset_mark()
            if catalog_uuid != "NONE":
                data_block.asset_data.catalog_id = catalog_uuid
            
            # Add tags if provided
            if "tags" in params and params["tags"]:
                tags = [tag.strip() for tag in params["tags"].split(",")]
                for tag in tags:
                    if tag:
                        data_block.asset_data.tags.new(tag, skip_if_exists=True)
                        
            data_block.asset_generate_preview()
        
        if data_type == "objects":
            for obj in bpy.data.objects:
                if obj.name in asset_names:
                    process_asset(obj)
        elif data_type == "materials":
            for mat in bpy.data.materials:
                if mat.name in asset_names:
                    process_asset(mat)
        elif data_type == "node_groups":
            for ng in bpy.data.node_groups:
                if ng.name in asset_names:
                    process_asset(ng)
        
        # Wait for preview generation
        while bpy.app.is_job_running("RENDER_PREVIEW"):
            time.sleep(0.1)
        
        # Save file
        update_status({"running": True, "status": "Saving..."})
        bpy.ops.wm.save_mainfile(filepath=target_file)
        
        update_status({"running": False, "status": "Complete"})
        
    except Exception as e:
        log_message(f"Error in process_assets: {str(e)}")
        update_status({"running": False, "status": f"Error: {str(e)}"})
        raise

# Run the process
try:
    process_assets()
except Exception as e:
    print(f"Background process failed: {str(e)}")
'''
    script_file = tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False)
    script_file.write(script)
    script_file.close()
    return script_file.name

# --- Helper functions for selection logic ---
def get_selected_objects(context):
    return list(context.selected_objects) if context.selected_objects else []

def get_selected_node_groups(context):
    selected_groups = []
    tree = get_active_node_tree(context)
    if tree:
        for node in tree.nodes:
            if node.select and node.type == 'GROUP' and node.node_tree:
                selected_groups.append(node.node_tree)
    return selected_groups

def get_active_material(context):
    if context.active_object and context.active_object.active_material:
        return context.active_object.active_material
    return None

def get_active_geonode_tree(context):
    return get_active_node_tree(context)

# --- Unified panel draw helper ---
def draw_asset_library_panel(self, context, asset_type, get_selection_fn):
    layout = self.layout
    settings = context.scene.asset_library_settings

    # Status indicator
    if is_background_process_running():
        status_file = get_temp_file_path()
        try:
            with open(status_file, 'r') as f:
                status = json.load(f)
                status_box = layout.box()
                status_box.label(text=f"Status: {status.get('status', 'Processing...')}", icon='SORTTIME')
        except (OSError, json.JSONDecodeError):
            pass  # Could not read status file

    # Library Path
    path_box = layout.box()
    path_box.label(text="Library Location:", icon='FILE_FOLDER')
    path_box.prop(settings, "library_path", text="")

    if not settings.library_path:
        return

    # Target File
    file_box = layout.box()
    file_box.label(text="Target File:", icon='FILE_BLEND')
    file_box.prop(settings, "create_new_library")
    if settings.create_new_library:
        file_box.prop(settings, "new_file_name", text="File Name")
    else:
        file_box.prop(settings, "existing_file")

    can_proceed = settings.create_new_library or settings.existing_file != 'NONE'

    # Show scan status if needed
    if not settings.create_new_library and settings.existing_file != 'NONE':
        filepath = os.path.join(settings.library_path, settings.existing_file)
        for dtype in ('objects', 'materials', 'node_groups'):
            cache_key = (filepath, dtype)
            status = _file_scan_status.get(cache_key)
            if status == "pending":
                layout.label(text=f"Scanning {settings.existing_file} for {dtype}...", icon='TIME')
            elif status == "error":
                layout.label(text=f"Error scanning {settings.existing_file} for {dtype}", icon='ERROR')

    # Metadata
    metadata_box = layout.box()
    metadata_box.label(text="Asset Metadata:", icon='PROPERTIES')
    metadata_box.active = can_proceed
    metadata_box.label(text="Catalog:")
    metadata_box.prop(settings, "selected_catalog", text="")
    metadata_box.label(text="Tags (comma-separated):")
    metadata_box.prop(settings, "tags", text="")

    # Rename
    rename_box = layout.box()
    rename_box.label(text="Naming Options:", icon='SORTALPHA')
    rename_box.active = can_proceed
    rename_box.prop(settings, "rename_viewport_assets")
    if settings.rename_viewport_assets:
        rename_box.prop(settings, "asset_base_name")

    # Selection Info
    selection_box = layout.box()
    selection_box.label(text="What will be saved:", icon='EXPORT')
    selection_box.active = can_proceed
    selected_items = get_selection_fn(context)
    if selected_items:
        selection_box.label(text=f"{len(selected_items)} items selected")
        for i, item in enumerate(selected_items):
            name = item.name
            if settings.rename_viewport_assets and settings.asset_base_name:
                new_name = settings.asset_base_name
                if i > 0:
                    new_name += f".{str(i+1).zfill(3)}"
                selection_box.label(text=f"â€¢ {name} â†’ {new_name}")
            else:
                selection_box.label(text=f"â€¢ {name}")
    else:
        selection_box.label(text="No items selected")

    # Add to Library Button
    row = layout.row(align=True)
    row.scale_y = 1.5
    row.enabled = can_proceed and not is_background_process_running()
    op = row.operator(ASSET_OT_add_to_library.bl_idname, text="Add to Library", icon='ASSET_MANAGER')
    op.asset_type = asset_type

# Property groups
class AssetLibrarySettings(PropertyGroup):
    def get_catalogs_callback(self, context):
        """Get all available catalogs from the nearest catalog file"""
        items = [('NONE', "No Catalog", "Don't add to a catalog")]
        
        if not self.library_path or not os.path.exists(self.library_path):
            return items
            
        def find_nearest_catalog_file(start_path):
            """Search up through parent directories for the nearest catalog file"""
            current_path = start_path
            while True:
                catalog_path = os.path.join(current_path, "blender_assets.cats.txt")
                if os.path.exists(catalog_path):
                    return catalog_path
                    
                # Get parent directory
                parent_path = os.path.dirname(current_path)
                # If we're already at the root directory, stop searching
                if parent_path == current_path:
                    return None
                current_path = parent_path
        
        # Find the nearest catalog file
        catalog_path = find_nearest_catalog_file(self.library_path)
        
        if not catalog_path:
            return items
            
        try:
            catalog_items = []  # Create separate list for catalog items
            with open(catalog_path, 'r') as f:
                lines = f.readlines()
                
            # Parse catalog file
            for line in lines:
                if line.startswith("#") or not line.strip():
                    continue
                    
                # Split line into UUID and path
                parts = line.strip().split(":", 1)
                if len(parts) == 2:
                    uuid = parts[0].strip()
                    path = parts[1].strip()
                    
                    # Add to catalog items list
                    catalog_items.append((uuid, path, f"Add to catalog: {path}"))
            
            # Sort only the catalog items
            catalog_items.sort(key=lambda x: x[1].lower())
            
            # Combine lists with "No Catalog" always first
            items.extend(catalog_items)
            
        except Exception as e:
            print(f"Error reading catalog file: {str(e)}")
            
        return items

    def get_library_files(self, context):
        """Get all .blend files from the current library folder (non-recursive)"""
        if not self.library_path or not os.path.exists(self.library_path):
            return [('NONE', "No Library Selected", "")]
        
        files = []
        
        # Only look in the current directory (no walk)
        for filename in os.listdir(self.library_path):
            if filename.endswith('.blend'):
                files.append((
                    filename,  # identifier
                    filename,  # display name
                    f"Save to: {filename}"  # description
                ))
        
        if not files:
            return [('NONE', "No Blend Files Found", "")]
        
        # Sort files by name
        files.sort(key=lambda x: x[1].lower())
        
        return files

    def scan_conflicts(self, context, filepath, data_blocks, data_type=None):
        """Scan target file for naming conflicts using persistent cache."""
        conflicts = []
        if not os.path.exists(filepath):
            return conflicts
        existing_names = scan_names_cached(filepath, data_type)
        for data in data_blocks:
            if data.name in existing_names:
                conflicts.append(data.name)
        return conflicts

    def get_conflicts_cached(self, context, filepath, data_blocks, data_type):
        global _conflict_cache, _conflict_cache_params
        # Only use names for cache key, not the objects themselves
        names = tuple(sorted([d.name for d in data_blocks]))
        params = (filepath, names, data_type)
        if params == _conflict_cache_params:
            return _conflict_cache if _conflict_cache is not None else []
        conflicts = self.scan_conflicts(context, filepath, data_blocks, data_type)
        _conflict_cache = conflicts
        _conflict_cache_params = params
        return conflicts

    def invalidate_conflict_cache(self):
        global _conflict_cache, _conflict_cache_params
        _conflict_cache_params = None
        _conflict_cache = None

    def update_existing_file(self, context):
        self.invalidate_conflict_cache()

    # Property Definitions
    library_path: StringProperty(
        name="Library Path",
        description="Path to the asset library",
        default="",
        subtype='DIR_PATH'
    )

    create_new_library: BoolProperty(
        name="Create new .Blend file",
        description="Create a new library instead of using existing one",
        default=False
    )
    
    new_file_name: StringProperty(
        name="File Name",
        description="Name for the new blend file",
        default="new_asset"
    )

    existing_file: EnumProperty(
        name="Existing File",
        description="Choose existing blend file",
        items=get_library_files,
        update=update_existing_file
    )

    selected_catalog: EnumProperty(
        name="Catalog",
        description="Choose a catalog to add the assets to",
        items=get_catalogs_callback,
        default=0
    )

    tags: StringProperty(
        name="Tags",
        description="Add tags to the assets (comma-separated)",
        default=""
    )

    rename_viewport_assets: BoolProperty(
        name="Rename Assets",
        description="Rename objects when adding them to the asset library",
        default=False
    )

    asset_base_name: StringProperty(
        name="New Name",
        description="Base name for the assets (numbers will be added automatically)",
        default=""
    )

    conflict_action: EnumProperty(
        name="If asset name exists",
        description="How to handle naming conflicts",
        items=[
            ('OVERRIDE', "Override", "Replace the existing asset"),
            ('SKIP', "Skip", "Don't import this asset"),
        ],
        default='OVERRIDE'
    )

# Operators and Panels
class ASSET_OT_add_to_library(Operator):
    bl_idname = "asset.add_to_library"
    bl_label = "Add to Library"
    bl_description = "Add selected elements to asset library"
    bl_options = {'REGISTER', 'UNDO'}

    asset_type: EnumProperty(
        name="Asset Type",
        items=[
            ('OBJECTS', "Objects", "Save selected objects"),
            ('MATERIAL', "Material", "Save active material"),
            ('GEONODES', "Geometry Nodes", "Save active geometry nodes"),
        ],
        default='OBJECTS'
    )

    @classmethod
    def poll(cls, context):
        return module_enabled

    def create_empty_blend(self, filepath):
        """Create an empty blend file using background process"""
        try:
            blender_path = bpy.app.binary_path
            
            # Create script string
            script = '''
import bpy
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.wm.save_mainfile(filepath=r"{}")
'''.format(filepath)
            
            # Create temporary script file
            script_file = tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False)
            script_file.write(script)
            script_file.close()
            
            # Run the script
            subprocess.run([
                blender_path,
                "--background",
                "--factory-startup",
                "--python", script_file.name
            ], check=True)
            
            # Clean up
            os.unlink(script_file.name)
            
            return os.path.exists(filepath)
            
        except Exception as e:
            self.report({'ERROR'}, f"Failed to create file: {str(e)}")
            return False

    def get_selected_node_groups(self, context):
        selected_groups = set()
        
        if context.space_data.tree_type in {'ShaderNodeTree', 'GeometryNodeTree', 'CompositorNodeTree'}:
            tree = get_active_node_tree(context)
            if tree:
                for node in tree.nodes:
                    if node.select and node.type == 'GROUP' and node.node_tree:
                        selected_groups.add(node.node_tree)
        
        return selected_groups

    def start_background_process(self, context, source_file, target_file, data_type, asset_names, conflict_action=None):
        """Start the background Blender process"""
        try:
            # Create parameters for background script
            params = {
                "source_file": source_file,
                "target_file": target_file,
                "data_type": data_type,
                "asset_names": list(asset_names),
                "catalog_uuid": context.scene.asset_library_settings.selected_catalog,
                "tags": context.scene.asset_library_settings.tags
            }
            if conflict_action:
                params["conflict_action"] = conflict_action
                
            # Create background script
            script_file = create_background_script()
            
            # Get Blender executable path
            blender_path = bpy.app.binary_path
            
            # Initialize status file
            status_file = get_temp_file_path()
            with open(status_file, 'w') as f:
                json.dump({"running": True, "status": "Starting..."}, f)
            
            # Run Blender in background mode
            print("Starting background process...")
            process = subprocess.Popen([
                blender_path,
                "--background",
                "--factory-startup",
                "--python", script_file,
                "--",
                json.dumps(params)
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
               universal_newlines=True)  # This makes the output readable
            
            # Read output in a non-blocking way
            def read_output():
                while True:
                    output = process.stdout.readline()
                    if output:
                        print("Background process:", output.strip())
                    if process.poll() is not None:
                        break
                return None
            
            # Register the output reading function
            bpy.app.timers.register(read_output)
            
            # Start the timer to monitor the process
            bpy.app.timers.register(self.check_process_status)
            
            return True
            
        except Exception as e:
            self.report({'ERROR'}, f"Failed to start background process: {str(e)}")
            if os.path.exists(script_file):
                os.unlink(script_file)
            return False

    def check_process_status(self):
        """Check the status of the background process"""
        # Initialize static variable if not exists
        if not hasattr(self.check_process_status, "last_status"):
            self.check_process_status.last_status = ""
        
        status_file = get_temp_file_path()
        if not os.path.exists(status_file):
            # Process completed or file removed
            bpy.context.workspace.status_text_set(None)  # Clear status
            return None
        
        try:
            with open(status_file, 'r') as f:
                status = json.load(f)
                
            current_status = status.get('status', 'Processing...')
            running = status.get('running', False)
            
            # Only update UI when status changes to minimize redraws
            if current_status != self.check_process_status.last_status:
                self.check_process_status.last_status = current_status
                bpy.context.workspace.status_text_set(f"Asset Library: {current_status}")
            
            if not running:
                # Process is complete - clean up
                try:
                    os.unlink(status_file)
                except Exception as e:
                    print(f"Error removing status file: {e}")
                
                bpy.context.workspace.status_text_set("Asset processing complete!")
                return None
        except Exception as e:
            print(f"Error checking process status: {e}")
        
        return 0.5

    def add_to_existing(self, context, filepath, data_blocks, data_type, main_data_names):
        """Add assets to existing library using background process"""
        settings = context.scene.asset_library_settings
        
        # Create temporary file with assets
        temp_dir = tempfile.gettempdir()
        temp_file = os.path.join(temp_dir, "temp_asset.blend")
        
        try:
            # Save only selected data blocks to temporary file
            bpy.data.libraries.write(
                temp_file,
                data_blocks,  # Only save the selected data blocks
                fake_user=True,
                compress=True
            )
            
            # Start background process
            success = self.start_background_process(
                context,
                temp_file,
                filepath,
                data_type,
                main_data_names,
                settings.conflict_action
            )
            
            if not success:
                if os.path.exists(temp_file):
                    os.unlink(temp_file)
                return {'CANCELLED'}
            
            self.report({'INFO'}, "Asset processing started in background")
            return {'FINISHED'}
            
        except Exception as e:
            if os.path.exists(temp_file):
                try:
                    os.unlink(temp_file)
                except OSError:
                    pass  # Could not remove temp file
            self.report({'ERROR'}, f"Failed to process assets: {str(e)}")
            return {'CANCELLED'}

    def execute(self, context):
        settings = context.scene.asset_library_settings
        
        # Validate library selection
        if not settings.library_path:
            self.report({'ERROR'}, "Please select a library path")
            return {'CANCELLED'}
        
        # Validate that the library path exists
        if not os.path.exists(settings.library_path):
            self.report({'ERROR'}, "Selected library path does not exist")
            return {'CANCELLED'}

        # Handle renaming validation
        if settings.rename_viewport_assets and not settings.asset_base_name:
            self.report({'ERROR'}, "Please enter a base name for the assets")
            return {'CANCELLED'}

        data_blocks = set()
        main_data_names = set()
        data_type = 'objects'
            
        if self.asset_type == 'OBJECTS':
            if not context.selected_objects:
                self.report({'ERROR'}, "No objects selected")
                return {'CANCELLED'}
                
            # Rename objects if option is enabled
            if settings.rename_viewport_assets and settings.asset_base_name:
                for i, obj in enumerate(context.selected_objects):
                    if i == 0:
                        obj.name = settings.asset_base_name
                    else:
                        obj.name = f"{settings.asset_base_name}.{str(i+1).zfill(3)}"
            
            data_blocks = set(context.selected_objects)
            main_data_names = {obj.name for obj in data_blocks}
            data_type = 'objects'
            
        elif self.asset_type == 'MATERIAL':
            selected_groups = self.get_selected_node_groups(context)
            
            if selected_groups:
                if settings.rename_viewport_assets and settings.asset_base_name:
                    for i, ng in enumerate(selected_groups):
                        if i == 0:
                            ng.name = settings.asset_base_name
                        else:
                            ng.name = f"{settings.asset_base_name}.{str(i+1).zfill(3)}"
                
                data_blocks = selected_groups
                main_data_names = {ng.name for ng in selected_groups}
                data_type = 'node_groups'
            else:
                if not context.active_object or not context.active_object.active_material:
                    self.report({'ERROR'}, "No active material")
                    return {'CANCELLED'}
                
                mat = context.active_object.active_material
                
                # Rename material if option is enabled
                if settings.rename_viewport_assets and settings.asset_base_name:
                    mat.name = settings.asset_base_name
                
                data_blocks.add(mat)
                main_data_names = {mat.name}
                
                # Add dependent node groups but don't rename them
                if mat.node_tree:
                    for node in mat.node_tree.nodes:
                        if node.type == 'GROUP' and node.node_tree:
                            data_blocks.add(node.node_tree)
                data_type = 'materials'
            
        elif self.asset_type == 'GEONODES':
            selected_groups = self.get_selected_node_groups(context)
            
            if selected_groups:
                if settings.rename_viewport_assets and settings.asset_base_name:
                    for i, ng in enumerate(selected_groups):
                        if i == 0:
                            ng.name = settings.asset_base_name
                        else:
                            ng.name = f"{settings.asset_base_name}.{str(i+1).zfill(3)}"
                
                data_blocks = selected_groups
                main_data_names = {ng.name for ng in selected_groups}
                data_type = 'node_groups'
            else:
                tree = get_active_node_tree(context)
                if not tree:
                    self.report({'ERROR'}, "No active geometry node tree")
                    return {'CANCELLED'}
                
                # Rename tree if option is enabled
                if settings.rename_viewport_assets and settings.asset_base_name:
                    tree.name = settings.asset_base_name
                
                data_blocks = {tree}
                main_data_names = {tree.name}
                
                # Add dependent node groups but don't rename them
                for node in tree.nodes:
                    if node.type == 'GROUP' and node.node_tree:
                        data_blocks.add(node.node_tree)
                data_type = 'node_groups'

        # Get target filepath
        if settings.create_new_library:
            filepath = os.path.join(settings.library_path, settings.new_file_name + ".blend")
            
            if os.path.exists(filepath):
                self.report({'ERROR'}, "A file with this name already exists")
                return {'CANCELLED'}
        else:
            filepath = os.path.join(settings.library_path, settings.existing_file)

        # Add conflict check
        cache_key = (filepath, data_type)
        if _file_scan_status.get(cache_key) == "pending":
            self.report({'WARNING'}, "Please wait: conflict scan is still running.")
            return {'CANCELLED'}

        conflicts = settings.scan_conflicts(context, filepath, data_blocks, data_type)
        if conflicts:
            if settings.conflict_action == 'SKIP':
                self.report({'WARNING'}, f"Name conflicts: {', '.join(conflicts)} - Operation cancelled (Skip selected)")
                return {'CANCELLED'}
            else:  # OVERRIDE
                self.report({'INFO'}, f"Name conflicts: {', '.join(conflicts)} - Will override existing assets")
                # Continue with the operation

        # Process assets
        return self.add_to_existing(context, filepath, data_blocks, data_type, main_data_names)


class QP_OT_open_asset_list(Operator):
    """Open Asset List in the sidebar"""
    bl_idname = "qp.open_asset_list"
    bl_label = "Open Asset List"
    
    @classmethod
    def poll(cls, context):
        return module_enabled
    
    def execute(self, context):
        # Find 3D View area
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                # Ensure sidebar is open
                if not any(region.type == 'UI' and region.width > 1 for region in area.regions):
                    override = {'area': area}
                    bpy.ops.view3d.sidebar_toggle(override)
                
                # Set panel tab to QuickAsset
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        try:
                            # Try to set UI category directly
                            space.ui_sidebar_category = 'QuickAsset'
                        except AttributeError:
                            # Fallback method - user will need to click the tab manually
                            self.report({'INFO'}, "Please select the QuickAsset tab in the sidebar")
                break
                
        return {'FINISHED'}

# Draw function for the preferences panel
def draw_preferences(preferences, context, layout):
    """Draw module preferences in the addon preferences panel"""
    row = layout.row()
    row.prop(preferences, "quick_asset_library_enabled", text="Enable Quick Asset Library")
    
    # Only show the path field if the module is enabled
    if preferences.quick_asset_library_enabled:
        row = layout.row()
        row.prop(preferences, "quick_asset_library_path", text="Default Library Path")

# Register and unregister functions
def register():
    """Register the QuickAssetLibrary module"""
    if not ModuleManager.register_module(sys.modules[__name__]):
        return
    
    # Register classes
    ModuleManager.safe_register_class(AssetLibrarySettings)
    ModuleManager.safe_register_class(ASSET_OT_add_to_library)
    
    # Register property group for Scene
    bpy.types.Scene.asset_library_settings = PointerProperty(type=AssetLibrarySettings)
    
    # Clean up status file
    status_file = get_temp_file_path()
    if os.path.exists(status_file):
        try:
            os.unlink(status_file)
        except OSError:
            pass  # Could not remove status file

    # Register load handler
    bpy.app.handlers.load_post.append(load_handler)
    
    # Update library path from preferences
    update_library_path_from_preferences()

    ModuleManager.safe_register_class(QP_OT_open_asset_list)
    

def unregister():
    """Unregister the QuickAssetLibrary module"""
    if not ModuleManager.unregister_module(sys.modules[__name__]):
        return
    
    # Remove load handler
    if load_handler in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(load_handler)
    
    # Clean up status file
    status_file = get_temp_file_path()
    if os.path.exists(status_file):
        try:
            os.unlink(status_file)
        except OSError:
            pass  # Could not remove status file

    # Unregister classes in reverse order
    ModuleManager.safe_unregister_class(ASSET_OT_add_to_library)
    ModuleManager.safe_unregister_class(AssetLibrarySettings)
    
    # Remove property group
    if hasattr(bpy.types.Scene, "asset_library_settings"):
        del bpy.types.Scene.asset_library_settings

def scan_names_cached(filepath, data_type):
    """Return set of names for the given file and data_type, using cache if possible. Start background scan if needed."""
    global _file_scan_cache, _file_scan_status
    try:
        mtime = os.path.getmtime(filepath)
    except Exception:
        return set()
    cache_key = (filepath, data_type)
    cache_entry = _file_scan_cache.get(cache_key)
    if cache_entry and cache_entry['mtime'] == mtime:
        return cache_entry['names']
    # Not cached or file changed: start background scan
    scan_names_background(filepath, data_type)
    return set()  # Return empty until scan is done

def scan_names_background(filepath, data_type):
    """Start a background thread to scan names if not already running."""
    cache_key = (filepath, data_type)
    with _file_scan_lock:
        if _file_scan_status.get(cache_key) == "pending":
            return  # Already scanning
        _file_scan_status[cache_key] = "pending"
    def worker():
        names = set()
        status = "done"
        try:
            with bpy.data.libraries.load(filepath) as (data_from, data_to):
                if data_type == "objects":
                    names = set(data_from.objects)
                elif data_type == "materials":
                    names = set(data_from.materials)
                elif data_type == "node_groups":
                    names = set(data_from.node_groups)
        except Exception as e:
            print(f"Error scanning {filepath}: {e}")
            status = "error"
        with _file_scan_lock:
            _file_scan_cache[cache_key] = {'mtime': os.path.getmtime(filepath), 'names': names}
            _file_scan_status[cache_key] = status
    threading.Thread(target=worker, daemon=True).start()

