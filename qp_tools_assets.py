# qp_tools_assets.py
import bpy
import os
from bpy.types import Menu, Operator
from bpy.props import StringProperty, BoolProperty

# Import the module helper
from .module_helper import ModuleManager


class QP_MT_library_assets_menu(Menu):
    """Menu for displaying assets from a specific library"""
    bl_label = "Library Assets"
    bl_idname = "QP_MT_library_assets_menu"
    
    def draw(self, context):
        layout = self.layout
        
        # Get the library name from window_manager
        library_name = getattr(context.window_manager, "library_name", "")
        if not library_name:
            layout.label(text="No library selected")
            return
        
        # Get preferences
        prefs = context.preferences.addons[__package__].preferences
        
        # Find the library
        lib = next((l for l in prefs.asset_libraries if l.name == library_name), None)
        if not lib:
            layout.label(text=f"Library {library_name} not found")
            return
        
        # Show enabled assets by category
        categories = {}
        for asset in lib.assets:
            if asset.enabled:
                category = asset.category
                if category not in categories:
                    categories[category] = []
                categories[category].append(asset)
        
        if not categories:
            layout.label(text="No enabled assets in this library")
            return
            
        # Show all categories and their assets in multi-column layout
        for category, assets in sorted(categories.items()):
            layout.label(text=category)
            
            # Create a multi-column grid for assets
            num_columns = min(3, max(1, len(assets) // 8))  # Scale columns with asset count
            
            # Use grid_flow for multi-column layout
            grid = layout.grid_flow(row_major=True, columns=num_columns, even_columns=True)
            
            # Add assets to the grid
            for asset in assets:
                op = grid.operator("qp.append_asset", text=asset.name)
                op.filepath = asset.filepath
                op.asset_name = asset.name
            
            # Add separator after each category
            layout.separator()

class QP_OT_show_category_assets(Operator):
    """Show assets in a specific category"""
    bl_idname = "qp.show_category_assets"
    bl_label = "Show Category Assets"
    
    library_name: StringProperty()
    category: StringProperty()
    
    def execute(self, context):
        context.window_manager.library_name = self.library_name
        context.window_manager.category_name = self.category
        bpy.ops.wm.call_menu(name="QP_MT_library_assets_menu")
        return {'FINISHED'}

class QP_OT_show_library_assets(Operator):
    """Show assets from a specific library"""
    bl_idname = "qp.show_library_assets"
    bl_label = "Library Assets"
    
    library_name: StringProperty(name="Library Name")
    
    def execute(self, context):
        context.window_manager.library_name = self.library_name
        bpy.ops.wm.call_menu(name="QP_MT_library_assets_menu")
        return {'FINISHED'}


def connect_object_to_node_modifier(imported_obj, source_obj):
    """Connect source_obj to the imported_obj's geometry nodes modifier
    
    Improved to handle any object type and maintain compatibility with Blender 4.1-4.3+
    Now checks if socket already has an object connected
    
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
            
            # Check if there's already an object connected to this socket
            already_connected = False
            try:
                current_object = mod.get(socket_id)
                if current_object is not None and hasattr(current_object, 'type') and current_object.type != 'NONE':
                    print(f"Socket {target_socket.name} already has {current_object.name} connected, skipping")
                    already_connected = True
                    return False
            except Exception as e:
                # If we can't get the current value, assume it's not connected
                print(f"Could not check existing connection: {e}")
            
            # Skip if already connected
            if already_connected:
                return False
            
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


class QP_OT_AppendAsset(Operator):
    """Append an asset at the cursor position with selective data import and reuse of existing materials/modifiers"""
    bl_idname = "qp.append_asset"
    bl_label = "Append Asset"
    bl_options = {'REGISTER', 'UNDO'}
    
    filepath: StringProperty(name="File Path")
    asset_name: StringProperty(name="Asset Name")
    
    def get_base_name(self, name):
        """Extract base name from a name with potential numeric suffix"""
        # Handle cases like "Material.001" or "Material.002.001"
        parts = name.split('.')
        # Find the last part that's purely numeric
        for i in range(len(parts) - 1, 0, -1):
            if parts[i].isdigit():
                return '.'.join(parts[:i])
        return name
    
    def execute(self, context):
        if not self.filepath or not os.path.exists(self.filepath):
            self.report({'ERROR'}, f"File not found: {self.filepath}")
            return {'CANCELLED'}
        
        try:
            # Store cursor location
            cursor_loc = context.scene.cursor.location.copy()
            
            # Store selected objects before appending for geometry nodes connection
            source_obj = None
            selected_objects = context.selected_objects.copy()
            active_object = context.active_object
            
            # Prioritize active object for geometry nodes connection
            if active_object and active_object in selected_objects:
                source_obj = active_object
            elif selected_objects:
                # Just use the first selected object as source
                source_obj = selected_objects[0]
            
            # Record data block counts before appending
            initial_images = len(bpy.data.images)
            
            # IMPORTANT: Store a snapshot of existing objects and materials BEFORE importing
            existing_objects = set(obj for obj in bpy.data.objects)
            
            # Create mappings of base names to existing data blocks
            existing_materials = {}
            for mat in bpy.data.materials:
                base_name = self.get_base_name(mat.name)
                if base_name not in existing_materials:
                    existing_materials[base_name] = mat
            
            existing_node_groups = {}
            for ng in bpy.data.node_groups:
                base_name = self.get_base_name(ng.name)
                if base_name not in existing_node_groups:
                    existing_node_groups[base_name] = ng
            
            # Build name mappings and determine what to load
            material_mapping = {}  # Maps source material names to target materials
            node_group_mapping = {}  # Maps source node group names to target node groups
            materials_to_load = []
            node_groups_to_load = []
            
            # Pre-scan the file to determine what's inside and what needs to be loaded
            with bpy.data.libraries.load(self.filepath) as (data_from, _):
                # Check if asset exists
                if self.asset_name not in data_from.objects:
                    self.report({'ERROR'}, f"Asset '{self.asset_name}' not found in file")
                    return {'CANCELLED'}
                
                # Process materials - decide what to load vs reuse
                for mat_name in data_from.materials:
                    # Get base name of the material
                    base_name = self.get_base_name(mat_name)
                    if base_name in existing_materials:
                        # Map to existing material
                        material_mapping[mat_name] = existing_materials[base_name]
                    else:
                        # Mark for loading
                        materials_to_load.append(mat_name)
                
                # Process node groups - decide what to load vs reuse
                for ng_name in data_from.node_groups:
                    # Get base name of the node group
                    base_name = self.get_base_name(ng_name)
                    if base_name in existing_node_groups:
                        # Map to existing node group
                        node_group_mapping[ng_name] = existing_node_groups[base_name]
                    else:
                        # Mark for loading
                        node_groups_to_load.append(ng_name)
            
            # First run: Load the object and materials/node groups that need to be loaded
            with bpy.data.libraries.load(self.filepath) as (data_from, data_to):
                data_to.objects = [self.asset_name]
                data_to.materials = materials_to_load
                data_to.node_groups = node_groups_to_load

            # IMMEDIATELY unmark all imported data as assets before processing
            # Process the appended object first
            for obj in data_to.objects:
                if obj is not None:
                    # Unmark object as asset
                    if hasattr(obj, 'asset_data') and obj.asset_data is not None:
                        if hasattr(obj, 'asset_clear'):
                            obj.asset_clear()
                        elif hasattr(obj.asset_data, 'clear'):
                            obj.asset_data.clear()

            # Unmark imported materials
            for mat in data_to.materials:
                if mat is not None:
                    # Unmark as asset
                    if hasattr(mat, 'asset_data') and mat.asset_data is not None:
                        if hasattr(mat, 'asset_clear'):
                            mat.asset_clear()
                        elif hasattr(mat.asset_data, 'clear'):
                            mat.asset_data.clear()

            # Unmark imported node groups
            for ng in data_to.node_groups:
                if ng is not None:
                    # Unmark as asset
                    if hasattr(ng, 'asset_data') and ng.asset_data is not None:
                        if hasattr(ng, 'asset_clear'):
                            ng.asset_clear()
                        elif hasattr(ng.asset_data, 'clear'):
                            ng.asset_data.clear()
            
            # Process the appended object
            appended_obj = None
            for obj in data_to.objects:
                if obj is not None:
                    appended_obj = obj
                    # Link to scene
                    context.scene.collection.objects.link(obj)
                    # Set main asset position to cursor location
                    obj.location = cursor_loc
                    
            
            if not appended_obj:
                self.report({'WARNING'}, "Object was appended but couldn't be placed in scene")
                return {'CANCELLED'}
            
            # Update material mappings with newly loaded materials
            for i, mat_name in enumerate(materials_to_load):
                if i < len(data_to.materials) and data_to.materials[i] is not None:
                    new_mat = data_to.materials[i]
                    # Map the original name to the newly loaded material
                    material_mapping[mat_name] = new_mat
                    
                    # If Blender renamed it, also map the renamed version
                    if new_mat.name != mat_name:
                        material_mapping[new_mat.name] = new_mat

                    
                    # Check if this is a duplicate we can replace
                    new_base_name = self.get_base_name(new_mat.name)
                    if new_base_name in existing_materials and new_mat != existing_materials[new_base_name]:
                        # Replace references to the newly loaded material with the existing one
                        material_mapping[new_mat.name] = existing_materials[new_base_name]
                        material_mapping[mat_name] = existing_materials[new_base_name]
                        
                        # Mark the new material for deletion
                        bpy.data.materials.remove(new_mat, do_unlink=True)

            # Update node group mappings with newly loaded node groups
            for i, ng_name in enumerate(node_groups_to_load):
                if i < len(data_to.node_groups) and data_to.node_groups[i] is not None:
                    new_ng = data_to.node_groups[i]
                    # Map the original name to the newly loaded node group
                    node_group_mapping[ng_name] = new_ng
                    
                    # If Blender renamed it, also map the renamed version
                    if new_ng.name != ng_name:
                        node_group_mapping[new_ng.name] = new_ng
                    
                    
                    # Check if this is a duplicate we can replace
                    new_base_name = self.get_base_name(new_ng.name)
                    if new_base_name in existing_node_groups and new_ng != existing_node_groups[new_base_name]:
                        # Replace references to the newly loaded node group with the existing one
                        node_group_mapping[new_ng.name] = existing_node_groups[new_base_name]
                        node_group_mapping[ng_name] = existing_node_groups[new_base_name]
                        
                        # Mark the new node group for deletion
                        bpy.data.node_groups.remove(new_ng, do_unlink=True)
            
            # Fix material references on the appended object
            reused_materials_count = 0
            if hasattr(appended_obj, 'material_slots'):
                for slot in appended_obj.material_slots:
                    # Only process slots with materials
                    if not slot.material:
                        continue
                    
                    mat_name = slot.material.name
                    
                    # Find the correct material to use
                    replacement_mat = None
                    if mat_name in material_mapping:
                        replacement_mat = material_mapping[mat_name]
                    else:
                        # Check by base name
                        base_name = self.get_base_name(mat_name)
                        if base_name in existing_materials:
                            replacement_mat = existing_materials[base_name]
                    
                    if replacement_mat and replacement_mat != slot.material:
                        slot.material = replacement_mat
                        reused_materials_count += 1
            
            # IMPROVED: Find and link new objects that were imported during the process
            # This includes any implicit dependencies that may have been loaded
            newly_imported_objects = []
            for obj in bpy.data.objects:
                # Check if it's a new object (not in our initial snapshot)
                if obj not in existing_objects:
                    # Skip the main appended object as it's already handled
                    if obj != appended_obj:
                        newly_imported_objects.append(obj)
            
            # Add all newly imported objects to the scene
            linked_count = 0
            for obj in newly_imported_objects:
                # Check if the object has any users and isn't already linked to a collection
                if obj.users > 0 and not obj.users_collection:
                    try:
                        # Add it to the scene collection
                        context.scene.collection.objects.link(obj)
                        linked_count += 1
                        
                        # Fix material references on dependency object
                        if hasattr(obj, 'material_slots'):
                            for slot in obj.material_slots:
                                if not slot.material:
                                    continue
                                
                                # Check if material is in our mapping or exists in scene
                                mat_name = slot.material.name
                                base_name = mat_name.split('.')[0]
                                
                                if mat_name in material_mapping:
                                    if slot.material != material_mapping[mat_name]:
                                        slot.material = material_mapping[mat_name]
                                        reused_materials_count += 1
                                elif base_name in existing_materials:
                                    if slot.material != existing_materials[base_name]:
                                        slot.material = existing_materials[base_name]
                                        reused_materials_count += 1
                    except RuntimeError as e:
                        # This happens if the object is already linked
                        print(f"Could not link {obj.name} to scene: {e}")
            
            # Process node groups in modifiers - replace with existing ones where possible
            reused_node_groups_count = 0
            reused_modifiers_count = 0
            
            def process_modifiers(obj):
                """Process all modifiers on an object to reuse existing node groups and settings"""
                nonlocal reused_node_groups_count, reused_modifiers_count
                
                for mod in obj.modifiers:
                    # Special handling for Geometry Nodes modifiers
                    if mod.type == 'NODES' and hasattr(mod, 'node_group') and mod.node_group:
                        # Get the modifier's node group
                        node_group = mod.node_group
                        node_group_name = node_group.name
                        base_name = node_group_name.split('.')[0]
                        
                        # Check if we should replace with an existing node group
                        replacement = None
                        if node_group_name in node_group_mapping:
                            replacement = node_group_mapping[node_group_name]
                        elif base_name in existing_node_groups:
                            replacement = existing_node_groups[base_name]
                        
                        if replacement and replacement != node_group:
                            # Find similar modifiers in the scene to copy settings from
                            similar_found = False
                            for scene_obj in context.scene.objects:
                                # Skip the object itself
                                if scene_obj == obj:
                                    continue
                                
                                for scene_mod in scene_obj.modifiers:
                                    if (scene_mod.type == 'NODES' and
                                        hasattr(scene_mod, 'node_group') and 
                                        scene_mod.node_group and
                                        (scene_mod.node_group == replacement or
                                         scene_mod.node_group.name.split('.')[0] == base_name)):
                                        
                                        # Found a similar modifier - copy its settings
                                        # Store the node_group and any important inputs
                                        stored_settings = {}
                                        
                                        # Detect inputs from modifier
                                        for prop_name in dir(scene_mod):
                                            if prop_name.startswith('__') or prop_name in {'name', 'type', 'rna_type', 'node_group'}:
                                                continue
                                                
                                            # Special handling for input properties
                                            if prop_name.startswith('Input_'):
                                                try:
                                                    stored_settings[prop_name] = getattr(scene_mod, prop_name)
                                                except (AttributeError, TypeError):
                                                    pass  # Property access failed

                                        # Copy node group and restore settings
                                        mod.node_group = replacement

                                        # Restore saved inputs
                                        for prop_name, value in stored_settings.items():
                                            try:
                                                setattr(mod, prop_name, value)
                                            except (AttributeError, TypeError):
                                                pass  # Property setting failed
                                                
                                        reused_node_groups_count += 1
                                        reused_modifiers_count += 1
                                        similar_found = True
                                        break
                                        
                                if similar_found:
                                    break
                            
                            # If no similar modifier found, just update the node group
                            if not similar_found:
                                mod.node_group = replacement
                                reused_node_groups_count += 1
                                
                    # Look for other modifier types that could be reused
                    elif mod.type in {'BEVEL', 'SUBSURF', 'SOLIDIFY', 'ARRAY', 'MIRROR'}:
                        # These modifiers have settings we'd want to match with existing ones
                        for scene_obj in context.scene.objects:
                            # Skip self
                            if scene_obj == obj:
                                continue
                                
                            # Look for matching modifiers
                            for scene_mod in scene_obj.modifiers:
                                if scene_mod.type == mod.type:
                                    # For BEVEL modifiers, match key settings
                                    if mod.type == 'BEVEL':
                                        if (getattr(scene_mod, 'width', 0) == getattr(mod, 'width', 1) and
                                            getattr(scene_mod, 'segments', 0) == getattr(mod, 'segments', 1) and
                                            getattr(scene_mod, 'limit_method', '') == getattr(mod, 'limit_method', '')):
                                            # Copy other settings
                                            for prop in dir(scene_mod):
                                                if prop.startswith('__') or prop in {'name', 'type', 'rna_type'}:
                                                    continue
                                                try:
                                                    setattr(mod, prop, getattr(scene_mod, prop))
                                                except (AttributeError, TypeError):
                                                    pass  # Property copy failed
                                            reused_modifiers_count += 1
                                            break

                                    # For SUBSURF modifiers
                                    elif mod.type == 'SUBSURF':
                                        if getattr(scene_mod, 'levels', 0) == getattr(mod, 'levels', 1):
                                            # Copy all settings
                                            for prop in dir(scene_mod):
                                                if prop.startswith('__') or prop in {'name', 'type', 'rna_type'}:
                                                    continue
                                                try:
                                                    setattr(mod, prop, getattr(scene_mod, prop))
                                                except (AttributeError, TypeError):
                                                    pass  # Property copy failed
                                            reused_modifiers_count += 1
                                            break
            
            # Process modifiers on the main imported object
            process_modifiers(appended_obj)
            
            # Process modifiers on dependency objects
            for obj in newly_imported_objects:
                process_modifiers(obj)
            
            # Try to connect source object to appended object's geometry node modifier
            connection_made = False
            if source_obj:
                # Try connecting the source object to appended object's modifier
                if connect_object_to_node_modifier(appended_obj, source_obj):
                    connection_made = True
            
            # Select appended object
            bpy.ops.object.select_all(action='DESELECT')
            appended_obj.select_set(True)
            context.view_layer.objects.active = appended_obj
            
            # Report how many images were imported as a result
            new_images = len(bpy.data.images) - initial_images
            
            msg = f"Appended {self.asset_name}"
            
            if connection_made:
                msg += f" and connected to {source_obj.name}"
            
            if linked_count > 0:
                msg += f" with {linked_count} dependency objects"
                
            if new_images > 0:
                msg += f" ({new_images} texture images)"
                
            if reused_materials_count > 0:
                msg += f" | Reused {reused_materials_count} materials"
                
            if reused_node_groups_count > 0:
                msg += f" | Reused {reused_node_groups_count} node groups"
                
            if reused_modifiers_count > 0:
                msg += f" | Reused {reused_modifiers_count} modifier settings"
                
            self.report({'INFO'}, msg)

            # Force cleanup of all unused data blocks - especially important for GPSketch
            bpy.ops.outliner.orphans_purge(do_local_ids=True, do_linked_ids=False, do_recursive=True)

            # For Grease Pencil data specifically (GPSketch objects)
            for ng in bpy.data.node_groups:
                # If it's already in our mapping, skip
                if ng.name in node_group_mapping.values():
                    continue
                    
                # Check if it's a duplicate we missed (like GPSketch_V01.001)
                base_name = self.get_base_name(ng.name)
                # Only proceed if it's not the original
                if base_name != ng.name and base_name in existing_node_groups:
                    # Ensure it's unmarked as asset
                    if hasattr(ng, 'asset_data') and ng.asset_data is not None:
                        if hasattr(ng, 'asset_clear'):
                            ng.asset_clear()
                        elif hasattr(ng.asset_data, 'clear'):
                            ng.asset_data.clear()
                            
                    # Force removal of the duplicate
                    if ng.users == 0:
                        bpy.data.node_groups.remove(ng)

            # Final orphans purge
            bpy.ops.outliner.orphans_purge(do_local_ids=True, do_linked_ids=False, do_recursive=True)

            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Error appending asset: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}
                                        
# Registration
classes = [
    QP_MT_library_assets_menu,
    QP_OT_show_category_assets,
    QP_OT_show_library_assets,
]

def register():
    # Register property for passing data between operators
    bpy.types.WindowManager.category_name = StringProperty()
    
    # Register classes
    for cls in classes:
        ModuleManager.safe_register_class(cls)

def unregister():
    # Unregister classes in reverse order
    for cls in reversed(classes):
        ModuleManager.safe_unregister_class(cls)
    
    # Remove property
    if hasattr(bpy.types.WindowManager, "category_name"):
        del bpy.types.WindowManager.category_name