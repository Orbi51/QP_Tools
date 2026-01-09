import bpy
import sys
import time
from bpy.props import StringProperty, BoolProperty
from bpy.types import Operator, PropertyGroup

from .module_helper import ModuleManager

# Module state variables
module_enabled = True
_is_registered = False

# Module-level cache for node group materials
_node_group_materials_cache = {}  # {node_group_name: {"materials": set(), "timestamp": time.time()}}
_cache_lifetime = 60  # Cache lifetime in seconds

def invalidate_node_group_cache():
    """Invalidate the node group materials cache"""
    global _node_group_materials_cache
    _node_group_materials_cache.clear()

def find_materials_in_node_group(node_group, processed_groups=None):
    """Find all materials referenced in a node group and its nested groups
    
    Args:
        node_group: The node group to search
        processed_groups: Set of already processed groups to avoid infinite recursion
        
    Returns:
        Set of materials referenced in the node group
    """
    global _node_group_materials_cache
    
    # Check if result is in cache and still fresh
    if node_group.name in _node_group_materials_cache:
        cache_entry = _node_group_materials_cache[node_group.name]
        if time.time() - cache_entry["timestamp"] < _cache_lifetime:
            # If cache is still valid, check if node group has been modified 
            # (we could add modification timestamp check here)
            return cache_entry["materials"].copy()
    
    if processed_groups is None:
        processed_groups = set()
    
    # Avoid processing the same group multiple times (prevents infinite recursion)
    if node_group in processed_groups:
        return set()
    
    processed_groups.add(node_group)
    materials = set()
    
    # Check all nodes in the group
    for node in node_group.nodes:
        # Case 1: Material nodes (like Set Material, Material Output, etc.)
        node_name = node.name.lower() if hasattr(node, "name") else ""
        node_type = node.type.lower() if hasattr(node, "type") else ""
        
        # Check for various material nodes by type and name
        if (node_type == 'set_material' or 
            'material' in node_type or 
            'set_material' in node_name or 
            'material' in node_name):
            
            # Try various ways to get material references
            if hasattr(node, "material") and node.material:
                materials.add(node.material)
            
            # Check inputs for material references
            for input in node.inputs:
                if ('material' in input.name.lower() and
                    hasattr(input, "default_value") and 
                    input.default_value and
                    hasattr(input.default_value, "__class__") and
                    "Material" in input.default_value.__class__.__name__):
                    materials.add(input.default_value)
        
        # Case 2: Nested node groups - recursive search
        elif node.type == 'GROUP' and node.node_tree:
            nested_materials = find_materials_in_node_group(node.node_tree, processed_groups)
            materials.update(nested_materials)
    
    # Cache the result
    _node_group_materials_cache[node_group.name] = {
        "materials": materials.copy(),
        "timestamp": time.time()
    }
    
    return materials


def invalidate_material_caches(self, context):
    """Invalidate caches when materials change"""
    global _node_group_materials_cache
    _node_group_materials_cache.clear()




def draw_materials(layout, materials, search_term="", hide_linked=False, with_actions=True, active_object=None):
    """Centralized function for drawing material lists
    
    Args:
        layout: UI layout to draw in
        materials: List of materials to display
        search_term: Optional filter text
        hide_linked: Whether to hide linked materials
        with_actions: Whether to include action buttons
        active_object: Active object to check for assigned materials
    """
    if not materials:
        layout.label(text="No materials found")
        return
        
    # Filter materials by search term and linked status
    filtered_materials = []
    for mat in materials:
        # Skip if doesn't match search term
        if search_term and search_term.lower() not in mat.name.lower():
            continue
            
        # Skip linked materials if requested
        if hide_linked and mat.library is not None:
            continue
            
        filtered_materials.append(mat)
    
    # Show count and empty message if needed
    if filtered_materials:
        layout.label(text=f"Found {len(filtered_materials)} materials")
    else:
        layout.label(text="No materials match filter")
        return
        
    # Get expanded state from properties
    show_all = False
    if hasattr(bpy.context.scene, "material_manager_props"):
        props = bpy.context.scene.material_manager_props
        if hasattr(props, "show_all_materials"):
            show_all = props.show_all_materials
    
    # Create a scrollable list if there are many materials
    max_display = len(filtered_materials) if show_all else min(len(filtered_materials), 20)
    scroll_col = layout.column()
    
    # Collect materials assigned to active object if provided
    assigned_materials = {}  # Map material to usage info: "object", "geonodes", or "both"
    
    if active_object:
        # 1. Check regular material slots (object usage)
        if hasattr(active_object, "material_slots"):
            for slot in active_object.material_slots:
                if slot.material:
                    assigned_materials[slot.material] = "object"
        
        # 2. Check geometry nodes modifiers for nodes using materials
        for mod in active_object.modifiers:
            if mod.type == 'NODES' and hasattr(mod, 'node_group') and mod.node_group:
                # Find material nodes inside the node group
                node_group_materials = find_materials_in_node_group(mod.node_group)
                for mat in node_group_materials:
                    if mat in assigned_materials:
                        # If already marked as "object", now mark as "both"
                        if assigned_materials[mat] == "object":
                            assigned_materials[mat] = "both"
                    else:
                        assigned_materials[mat] = "geonodes"
        
        # 3. Enhanced detection of materials directly assigned to modifier inputs
        for mod in active_object.modifiers:
            if mod.type == 'NODES' and hasattr(mod, 'node_group') and mod.node_group:
                # METHOD 1: Examine all properties of the modifier
                for prop_name in dir(mod):
                    # Skip methods, private properties and common non-material properties
                    if (prop_name.startswith('__') or 
                        prop_name in {'name', 'type', 'rna_type', 'node_group', 'bl_idname'}):
                        continue
                    
                    try:
                        # Get property value
                        prop_value = getattr(mod, prop_name)
                        
                        # Check if the property is a material
                        if (prop_value and 
                            hasattr(prop_value, 'name') and 
                            hasattr(prop_value, 'use_nodes')):
                            # We found a material reference
                            if prop_value in assigned_materials:
                                if assigned_materials[prop_value] == "object":
                                    assigned_materials[prop_value] = "both"
                            else:
                                assigned_materials[prop_value] = "geonodes"
                    except (AttributeError, TypeError):
                        # Skip properties that can't be accessed or cause errors
                        pass
                
                # METHOD 2: Check specific socket identifiers
                for node in mod.node_group.nodes:
                    if node.type == 'GROUP_INPUT':
                        for socket in node.outputs:
                            # Look for material sockets
                            if socket.type == 'MATERIAL' or 'material' in socket.name.lower():
                                socket_id = socket.identifier
                                
                                # Try three different ways to access the material
                                
                                # 1. Direct property access
                                try:
                                    if hasattr(mod, socket_id):
                                        mat = getattr(mod, socket_id)
                                        if (mat and
                                            hasattr(mat, 'name') and
                                            hasattr(mat, 'use_nodes')):
                                            if mat in assigned_materials:
                                                if assigned_materials[mat] == "object":
                                                    assigned_materials[mat] = "both"
                                            else:
                                                assigned_materials[mat] = "geonodes"
                                except (AttributeError, TypeError):
                                    pass  # Property access failed

                                # 2. Dictionary-style access
                                try:
                                    mat = mod[socket_id]
                                    if (mat and
                                        hasattr(mat, 'name') and
                                        hasattr(mat, 'use_nodes')):
                                        if mat in assigned_materials:
                                            if assigned_materials[mat] == "object":
                                                assigned_materials[mat] = "both"
                                        else:
                                            assigned_materials[mat] = "geonodes"
                                except (KeyError, TypeError):
                                    pass  # Dictionary access failed

                                # 3. Input_ prefix (common in Blender API)
                                try:
                                    input_prop = f"Input_{socket_id}"
                                    if hasattr(mod, input_prop):
                                        mat = getattr(mod, input_prop)
                                        if (mat and
                                            hasattr(mat, 'name') and
                                            hasattr(mat, 'use_nodes')):
                                            if mat in assigned_materials:
                                                if assigned_materials[mat] == "object":
                                                    assigned_materials[mat] = "both"
                                            else:
                                                assigned_materials[mat] = "geonodes"
                                except (AttributeError, TypeError):
                                    pass  # Property access failed
    
    # Draw material entries
    for mat in filtered_materials[:max_display]:
        is_assigned = mat in assigned_materials
        usage = assigned_materials.get(mat, "")
        
        # Create a box for each material
        box = scroll_col.box()
        
        # Create row inside the box
        row = box.row(align=True)
        
        # Material icon
        row.label(text="", icon='MATERIAL')
        
        # Check if it's a Grease Pencil material
        is_gp_material = hasattr(mat, "is_grease_pencil") and mat.is_grease_pencil
        
        # Material name
        if is_gp_material:
            # Just display the name without making it clickable
            row.label(text=mat.name)
        else:
            # Material name and open button for regular materials
            op = row.operator("material.open_shader_window", text=mat.name)
            op.material_name = mat.name
        
        # Add link indicator if material is linked
        if mat.library is not None:
            row.label(text="", icon='LINKED')
        
        # Add an icon to indicate assigned materials with different icons for different usages
        if is_assigned:
            if usage == "object":
                row.label(text="", icon='LAYER_ACTIVE')
            elif usage == "geonodes":
                row.label(text="", icon='NODETREE')
            elif usage == "both":
                row.label(text="", icon='DUPLICATE')
        
        # Action buttons
        if with_actions:
            # Apply material button (existing)
            op = row.operator("material.apply_to_selected", text="", icon='CHECKMARK')
            op.material_name = mat.name
            
            # NEW: Select Linked Objects button
            op = row.operator("material.select_linked_objects", text="", icon='RESTRICT_SELECT_OFF')
            op.material_name = mat.name
    
    # "Show more" indicator if there are more than we displayed
    if len(filtered_materials) > max_display:
        row = scroll_col.row()
        row.alignment = 'CENTER'
        op = row.operator("material.toggle_show_all", 
                       text=f"... and {len(filtered_materials) - max_display} more", 
                       icon='DISCLOSURE_TRI_RIGHT')
    elif len(filtered_materials) > 20 and show_all:
        # Add "show less" button when showing expanded list
        row = scroll_col.row()
        row.alignment = 'CENTER'
        op = row.operator("material.toggle_show_all", 
                       text="Show fewer materials", 
                       icon='TRIA_UP')

class MaterialManagerProperties(PropertyGroup):
    """Properties for the material manager"""
    search_term: StringProperty(
        name="Search",
        description="Filter materials by name",
        default=""
    )
    
    # Properties to track expanded state of material categories
    object_materials_expanded: BoolProperty(
        name="Expand Object Materials",
        description="Show/hide object materials list",
        default=True
    )
    
    grease_pencil_materials_expanded: BoolProperty(
        name="Expand Grease Pencil Materials",
        description="Show/hide grease pencil materials list",
        default=True
    )
    
    hide_linked_materials: BoolProperty(
        name="Hide Linked Materials", 
        description="Hide linked materials that may cause duplicates with Grease Pencil brush assets",
        default=True
    )

    show_all_materials: BoolProperty(
        name="Show All Materials",
        description="Show all materials instead of just the first few",
        default=False
    )

class MATERIAL_OT_toggle_show_all(Operator):
    """Toggle showing all materials in the list"""
    bl_idname = "material.toggle_show_all"
    bl_label = "Toggle Show All Materials"
    
    @classmethod
    def poll(cls, context):
        return module_enabled
    
    def execute(self, context):
        props = context.scene.material_manager_props
        props.show_all_materials = not props.show_all_materials
        return {'FINISHED'}

class MATERIAL_OT_create_new(Operator):
    """Create a new material and open it in the shader editor"""
    bl_idname = "material.create_new"
    bl_label = "New Material"
    bl_options = {'REGISTER', 'UNDO'}
    
    material_name: bpy.props.StringProperty(
        name="Material Name",
        description="Name for the new material",
        default="New Material"
    )
    
    @classmethod
    def poll(cls, context):
        return module_enabled
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context):
        layout = self.layout
        layout.prop(self, "material_name")
    
    def execute(self, context):
        # Create a new material with the user-provided name
        new_material = bpy.data.materials.new(name=self.material_name)
        
        # Set up nodes
        new_material.use_nodes = True
        
        # If there are selected objects, apply the material to them
        selected_objects = [obj for obj in context.selected_objects 
                          if obj.type in {'MESH', 'CURVE', 'SURFACE', 'META', 'FONT', 'VOLUME'}]
        
        geonodes_count = 0  # Track connections to geometry nodes modifiers
        object_count = 0    # Track material assignments to objects
        
        if selected_objects:
            for obj in selected_objects:
                # First check for Geometry Nodes modifiers with material sockets
                has_geonodes_mat_socket = False
                
                # Look for Geometry Nodes modifiers with material sockets
                for mod in obj.modifiers:
                    if mod.type == 'NODES' and hasattr(mod, 'node_group') and mod.node_group:
                        # Check if the modifier has material inputs
                        material_assigned_to_mod = False
                        for node in mod.node_group.nodes:
                            if node.type == 'GROUP_INPUT':
                                for socket in node.outputs:
                                    if socket.type == 'MATERIAL' or socket.name.lower() == 'material':
                                        # Found a material socket, assign the material
                                        socket_id = socket.identifier
                                        mod[socket_id] = new_material
                                        has_geonodes_mat_socket = True
                                        material_assigned_to_mod = True
                                        
                                        # Force viewport update
                                        mod.show_viewport = not mod.show_viewport
                                        mod.show_viewport = not mod.show_viewport
                                        
                                        # Only break from the socket loop to ensure all material sockets get the material
                                        break
                                
                        # Only increment counter once per modifier, not per socket
                        if material_assigned_to_mod:
                            geonodes_count += 1
                
                # If no Geometry Nodes material socket was found OR in addition to it,
                # apply to the object normally
                if len(obj.material_slots) == 0:
                    obj.data.materials.append(new_material)
                    object_count += 1
                else:
                    obj.active_material = new_material
                    object_count += 1
            
            # Create appropriate status message
            if geonodes_count > 0 and object_count > 0:
                self.report({'INFO'}, f"Created '{new_material.name}', applied to {object_count} object(s) and {geonodes_count} Geometry Nodes modifier(s)")
            elif geonodes_count > 0:
                self.report({'INFO'}, f"Created '{new_material.name}' and connected to {geonodes_count} Geometry Nodes modifier(s)")
            else:
                self.report({'INFO'}, f"Created and applied '{new_material.name}' to {object_count} object(s)")
        else:
            self.report({'INFO'}, f"Created material: {new_material.name}")
        
        # Open the shader editor for this new material
        bpy.ops.material.open_shader_window(material_name=new_material.name)
        
        return {'FINISHED'}


class MATERIAL_OT_select_linked_objects(Operator):
    """Select all objects that use this material"""
    bl_idname = "material.select_linked_objects"
    bl_label = "Select Objects Using Material"
    bl_options = {'REGISTER', 'UNDO'}
    
    material_name: StringProperty(
        name="Material Name",
        description="Name of the material to find linked objects for"
    )
    
    @classmethod
    def poll(cls, context):
        return module_enabled and context.mode == 'OBJECT'
    
    def is_grease_pencil_object(self, obj):
        """Check if an object is a Grease Pencil object in any Blender version"""
        # Traditional check for older Blender versions
        if obj.type == 'GPENCIL':
            return True
            
        # Check for renamed object type in Blender 4.3+
        if obj.type == 'GREASEPENCIL':
            return True
            
        # In Blender 4.3+, grease pencil became a specialized curve type
        if obj.type == 'CURVES':
            # Additional checks for curves that are grease pencil
            if hasattr(obj, 'data') and hasattr(obj.data, 'curve_type'):
                if getattr(obj.data, 'curve_type', '') == 'GREASE_PENCIL':
                    return True
        
        # Additional checks for newer Blender versions (4.3+)
        if hasattr(obj, 'data') and obj.data:
            # Check by data type name
            data_type = getattr(type(obj.data), '__name__', '').lower()
            
            # Various possible data type names
            gp_type_names = ['gpencil', 'greasepencil', 'grease_pencil', 'curves_gpencil']
            
            for name in gp_type_names:
                if name in data_type:
                    return True
                    
            # Check for specific attributes that might indicate a grease pencil
            if hasattr(obj.data, 'layers') and hasattr(obj.data, 'strokes'):
                return True
        
        return False

    def execute(self, context):
        # Get the material
        material = bpy.data.materials.get(self.material_name)
        if not material:
            self.report({'ERROR'}, f"Material '{self.material_name}' not found")
            return {'CANCELLED'}
        
        # Check if this is a grease pencil material
        is_gp_material = hasattr(material, "is_grease_pencil") and material.is_grease_pencil
        
        # Clear current selection
        bpy.ops.object.select_all(action='DESELECT')
        
        selected_objects = []
        
        # Find all objects using this material
        for obj in bpy.data.objects:
            object_uses_material = False
            
            # Check grease pencil objects
            if self.is_grease_pencil_object(obj):
                # Check material slots for grease pencil objects
                if hasattr(obj, 'material_slots'):
                    for slot in obj.material_slots:
                        if slot.material == material:
                            object_uses_material = True
                            break
                
                # For grease pencil, also check stroke material assignments
                if not object_uses_material and hasattr(obj.data, "layers"):
                    for layer in obj.data.layers:
                        if hasattr(layer, 'frames') and layer.frames:
                            try:
                                # For older versions (pre-4.3)
                                if hasattr(layer.frames[-1], 'strokes'):
                                    for stroke in layer.frames[-1].strokes:
                                        if (hasattr(stroke, 'material_index') and 
                                            stroke.material_index < len(obj.material_slots) and
                                            obj.material_slots[stroke.material_index].material == material):
                                            object_uses_material = True
                                            break
                                # For newer Blender 4.3+ versions
                                elif hasattr(layer.frames[-1], 'strokes_info'):
                                    for stroke_info in layer.frames[-1].strokes_info:
                                        if (hasattr(stroke_info, 'material_index') and 
                                            stroke_info.material_index < len(obj.material_slots) and
                                            obj.material_slots[stroke_info.material_index].material == material):
                                            object_uses_material = True
                                            break
                                # Try with drawing elements for Blender 4.0+
                                elif hasattr(layer, 'active_frame') and hasattr(layer.active_frame, 'drawing_elements'):
                                    for element in layer.active_frame.drawing_elements:
                                        if (hasattr(element, 'material_index') and 
                                            element.material_index < len(obj.material_slots) and
                                            obj.material_slots[element.material_index].material == material):
                                            object_uses_material = True
                                            break
                            except (IndexError, AttributeError):
                                # Continue if we encounter issues with a layer's frames
                                continue
                        
                        if object_uses_material:
                            break
            
            # Check regular objects (mesh, curve, surface, etc.)
            elif obj.type in {'MESH', 'CURVE', 'SURFACE', 'META', 'FONT', 'VOLUME'}:
                # Check material slots
                if hasattr(obj, 'material_slots'):
                    for slot in obj.material_slots:
                        if slot.material == material:
                            object_uses_material = True
                            break
                
                # Also check geometry nodes modifiers for material usage
                if not object_uses_material:
                    for mod in obj.modifiers:
                        if mod.type == 'NODES' and hasattr(mod, 'node_group') and mod.node_group:
                            # Find material nodes inside the node group
                            node_group_materials = find_materials_in_node_group(mod.node_group)
                            if material in node_group_materials:
                                object_uses_material = True
                                break
                            
                            # Also check modifier input sockets for direct material assignment
                            for node in mod.node_group.nodes:
                                if node.type == 'GROUP_INPUT':
                                    for socket in node.outputs:
                                        if socket.type == 'MATERIAL' or socket.name.lower() == 'material':
                                            socket_id = socket.identifier
                                            try:
                                                input_prop = f"Input_{socket_id}"
                                                if hasattr(mod, input_prop):
                                                    mat = getattr(mod, input_prop)
                                                    if mat == material:
                                                        object_uses_material = True
                                                        break
                                            except (AttributeError, TypeError):
                                                pass  # Property access failed
                                if object_uses_material:
                                    break
            
            # Select the object if it uses the material
            if object_uses_material:
                obj.select_set(True)
                selected_objects.append(obj.name)
        
        # Set active object to the first selected if any
        if selected_objects:
            first_obj = bpy.data.objects.get(selected_objects[0])
            if first_obj:
                context.view_layer.objects.active = first_obj
        
        # Report results
        if selected_objects:
            count = len(selected_objects)
            obj_type = "Grease Pencil" if is_gp_material else "regular"
            if count == 1:
                self.report({'INFO'}, f"Selected 1 {obj_type} object using material '{material.name}'")
            else:
                self.report({'INFO'}, f"Selected {count} {obj_type} objects using material '{material.name}'")
        else:
            obj_type = "Grease Pencil" if is_gp_material else "regular"
            self.report({'INFO'}, f"No {obj_type} objects found using material '{material.name}'")
        
        return {'FINISHED'}


class MATERIAL_OT_open_material_list(Operator):
    """Open Material List in the sidebar"""
    bl_idname = "material.open_material_list"
    bl_label = "Open Material List"
    
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
                
                # Set panel tab to MaterialList
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        try:
                            # Try to set UI category directly
                            space.ui_sidebar_category = 'QPTools'
                        except AttributeError:
                            # Fallback method - user will need to click the tab manually
                            self.report({'INFO'}, "Please select the QPTools tab in the sidebar")
                break
                
        return {'FINISHED'}

class MATERIAL_OT_apply_to_selected(Operator):
    """Apply material to selected objects\nShift-click: Duplicate material\nCtrl-click: Rename material"""
    bl_idname = "material.apply_to_selected"
    bl_label = "Apply Material"
    bl_options = {'REGISTER', 'UNDO'}
    
    material_name: StringProperty(
        name="Material Name",
        description="Name of the material to apply"
    )
    
    material_new_name: StringProperty(
        name="New Material Name",
        description="New name for the material",
        default=""
    )
    
    # Add property to store original name for restore after operations
    original_material_name: StringProperty(
        name="Original Material Name",
        description="Original material name before operations",
        default=""
    )
    
    @classmethod
    def poll(cls, context):
        return module_enabled
    
    def invoke(self, context, event):
        # Clear any lingering state from previous runs
        self.material_new_name = ""
        
        # Get the material
        material = bpy.data.materials.get(self.material_name)
        if not material:
            self.report({'ERROR'}, f"Material '{self.material_name}' not found")
            return {'CANCELLED'}
        
        # Store original name for reference
        self.original_material_name = self.material_name
        
        # Check for modifier keys
        if event.shift:
            # Duplicate material functionality
            duplicate_mat = material.copy()
            # Create a more descriptive name
            duplicate_mat.name = f"{material.name}.copy"
            
            # Update material name property to use the new one
            self.material_name = duplicate_mat.name
            self.report({'INFO'}, f"Duplicated material: {material.name} â†’ {duplicate_mat.name}")
            
            # Execute with duplicated material
            result = self.execute(context)
            
            # Reset material_name back to original for future operations
            self.material_name = self.original_material_name
            
            return result
        elif event.ctrl:
            # Initialize the new name with the current name
            self.material_new_name = material.name
            # Open dialog for renaming
            return context.window_manager.invoke_props_dialog(self)
        else:
            # Default behavior - just execute
            return self.execute(context)
    
    def draw(self, context):
        layout = self.layout
        layout.prop(self, "material_new_name", text="New Name")
    
    def execute(self, context):
        # Clear any lingering state if this is called directly
        if not hasattr(self, "original_material_name") or not self.original_material_name:
            self.original_material_name = self.material_name
            
        # Get the material with fresh reference
        material = bpy.data.materials.get(self.material_name)
        if not material:
            self.report({'ERROR'}, f"Material '{self.material_name}' not found")
            return {'CANCELLED'}
        
        # If material_new_name is set and different from the current name, rename the material
        if self.material_new_name and self.material_new_name != material.name:
            old_name = material.name
            material.name = self.material_new_name
            # Update our property to the new name for subsequent code
            self.material_name = material.name
            self.report({'INFO'}, f"Renamed material: {old_name} â†’ {material.name}")
            
            # Get a fresh reference to the material after renaming
            material = bpy.data.materials.get(self.material_name)
            if not material:
                self.report({'ERROR'}, f"Material '{self.material_name}' not found after renaming")
                return {'CANCELLED'}
        
        # Clear the rename property to prevent it affecting future runs
        self.material_new_name = ""
        
        # Check selected objects
        selected_objects = context.selected_objects
        if not selected_objects:
            self.report({'WARNING'}, "No objects selected")
            return {'CANCELLED'}
        
        # Determine if this is a Grease Pencil material
        is_gp_material = False
        if hasattr(material, "is_grease_pencil"):
            is_gp_material = material.is_grease_pencil
            
        # Apply to all selected objects
        count = 0
        geonodes_count = 0
        
        for obj in selected_objects:
            # First check for Geometry Nodes modifiers with material sockets
            has_geonodes_mat_socket = False
            
            # Look for Geometry Nodes modifiers with material sockets
            for mod in obj.modifiers:
                if mod.type == 'NODES' and hasattr(mod, 'node_group') and mod.node_group:
                    # Check if the modifier has material inputs
                    material_assigned_to_mod = False
                    for node in mod.node_group.nodes:
                        if node.type == 'GROUP_INPUT':
                            for socket in node.outputs:
                                if socket.type == 'MATERIAL' or socket.name.lower() == 'material':
                                    # Found a material socket, assign the material
                                    socket_id = socket.identifier
                                    mod[socket_id] = material
                                    has_geonodes_mat_socket = True
                                    material_assigned_to_mod = True
                                    
                                    # Force viewport update
                                    mod.show_viewport = not mod.show_viewport
                                    mod.show_viewport = not mod.show_viewport
                                    
                                    # Only break from the socket loop to ensure all material sockets get the material
                                    break
                    
                    # Only increment counter once per modifier, not per socket
                    if material_assigned_to_mod:
                        geonodes_count += 1
            
            # If no Geometry Nodes material socket was found OR in addition to it,
            # apply to the object normally
            if not has_geonodes_mat_socket:
                # For Grease Pencil materials, apply to Grease Pencil objects
                if is_gp_material:
                    if self.is_grease_pencil_object(obj):
                        self.assign_material(obj, material)
                        count += 1
                # For regular materials, apply to compatible objects (mesh, curve, surface, etc.)
                else:
                    # Apply to mesh and other compatible object types
                    if obj.type in {'MESH', 'CURVE', 'SURFACE', 'META', 'FONT', 'VOLUME'}:
                        self.assign_material(obj, material)
                        count += 1
        
        
        
        # Report results and ensure viewport is updated
        if count > 0 or geonodes_count > 0:
            message = f"Applied {self.material_name} to "
            parts = []
            
            if count > 0:
                parts.append(f"{count} object{'s' if count > 1 else ''}")
            
            if geonodes_count > 0:
                parts.append(f"{geonodes_count} Geometry Nodes modifier{'s' if geonodes_count > 1 else ''}")
            
            # Force viewport update
            context.view_layer.update()
                
            self.report({'INFO'}, message + " and ".join(parts))
        else:
            if is_gp_material:
                self.report({'WARNING'}, "No compatible Grease Pencil objects found. Select a Grease Pencil object first.")
            else:
                self.report({'WARNING'}, "No compatible objects or Geometry Nodes modifiers found")
            
        return {'FINISHED'}
    
    
    def is_grease_pencil_object(self, obj):
        """Check if an object is a Grease Pencil object in any Blender version"""
        # Traditional check for older Blender versions
        if obj.type == 'GPENCIL':
            return True
            
        # Check for renamed object type in Blender 4.3+
        if obj.type == 'GREASEPENCIL':
            return True
            
        # In Blender 4.3+, grease pencil became a specialized curve type
        if obj.type == 'CURVES':
            # Additional checks for curves that are grease pencil
            if hasattr(obj, 'data') and hasattr(obj.data, 'curve_type'):
                if getattr(obj.data, 'curve_type', '') == 'GREASE_PENCIL':
                    return True
        
        # Additional checks for newer Blender versions (4.3+)
        if hasattr(obj, 'data') and obj.data:
            # Check by data type name
            data_type = getattr(type(obj.data), '__name__', '').lower()
            
            # Various possible data type names
            gp_type_names = ['gpencil', 'greasepencil', 'grease_pencil', 'curves_gpencil']
            
            for name in gp_type_names:
                if name in data_type:
                    return True
                    
            # Check for specific attributes that might indicate a grease pencil
            if hasattr(obj.data, 'layers') and hasattr(obj.data, 'strokes'):
                return True
        
        return False
    
    def assign_material(self, obj, material):
        """Assign material to an object"""
        # Handle different object types
        if self.is_grease_pencil_object(obj):
            # For Grease Pencil objects
            if len(obj.material_slots) == 0:
                # No slots, so add one
                obj.data.materials.append(material)
            else:
                # Get the active slot index and ensure it's valid
                active_slot_index = obj.active_material_index
                if active_slot_index < len(obj.material_slots):
                    # Direct assignment to the active slot by index
                    obj.material_slots[active_slot_index].material = material
                else:
                    # Fallback if the active slot is somehow invalid
                    obj.active_material = material
            
            # For Grease Pencil, we may also need to assign to strokes
            if hasattr(obj.data, "layers"):
                for layer in obj.data.layers:
                    if hasattr(layer, 'frames') and layer.frames:
                        # Handle different Blender versions
                        try:
                            # For older versions (pre-4.3)
                            if hasattr(layer.frames[-1], 'strokes'):
                                for stroke in layer.frames[-1].strokes:
                                    stroke.material_index = obj.active_material_index
                            # For newer Blender 4.3+ versions
                            elif hasattr(layer.frames[-1], 'strokes_info'):
                                for stroke_info in layer.frames[-1].strokes_info:
                                    stroke_info.material_index = obj.active_material_index
                            # Try with drawing elements for Blender 4.0+
                            elif hasattr(layer, 'active_frame') and hasattr(layer.active_frame, 'drawing_elements'):
                                for element in layer.active_frame.drawing_elements:
                                    element.material_index = obj.active_material_index
                        except (IndexError, AttributeError) as e:
                            # Just continue if we encounter issues with a layer's frames
                            print(f"Note: Could not assign material to some strokes: {e}")
        else:
            # For regular objects (mesh, etc.)
            if len(obj.material_slots) == 0:
                # No slots, so add one
                obj.data.materials.append(material)
            else:
                # Get the active slot index and ensure it's valid
                active_slot_index = obj.active_material_index
                if active_slot_index < len(obj.material_slots):
                    # Direct assignment to the active slot by index
                    obj.material_slots[active_slot_index].material = material
                else:
                    # Fallback if the active slot is somehow invalid
                    obj.active_material = material

class MATERIAL_OT_open_shader_window(Operator):
    """Open a new window with the shader editor for the selected material"""
    bl_idname = "material.open_shader_window"
    bl_label = "Open Material Window"
    bl_options = {'REGISTER'}
    
    material_name: StringProperty(
        name="Material Name",
        description="Name of the material to edit"
    )

    @classmethod
    def poll(cls, context):
        return module_enabled

    def execute(self, context):
        # Store current state
        active_obj = context.active_object
        selected_objects = context.selected_objects.copy()
        current_mode = context.mode
        
        # Get the material
        material = bpy.data.materials.get(self.material_name)
        if not material:
            self.report({'ERROR'}, f"Material '{self.material_name}' not found")
            return {'CANCELLED'}
        
        # Create temporary object and assign material
        # Use different object type depending on material type
        is_gp_material = False
        if hasattr(material, "is_grease_pencil"):
            is_gp_material = material.is_grease_pencil
            
        if is_gp_material:
            # Create a temporary grease pencil object
            temp_obj = bpy.data.objects.new("temp_material_preview", bpy.data.grease_pencils.new("temp_gpencil"))
        else:
            # Create a temporary mesh object
            temp_obj = bpy.data.objects.new("temp_material_preview", bpy.data.meshes.new("temp_mesh"))
            
        bpy.context.scene.collection.objects.link(temp_obj)
        temp_obj.data.materials.append(material)
        
        # Set as active and select
        bpy.context.view_layer.objects.active = temp_obj
        temp_obj.select_set(True)
        
        # Create new window
        bpy.ops.screen.userpref_show('INVOKE_DEFAULT')
        new_window = context.window_manager.windows[-1]
        new_screen = new_window.screen
        
        # Set up shader editor
        area = new_screen.areas[0]
        area.type = 'NODE_EDITOR'
        space = area.spaces[0]
        space.tree_type = 'ShaderNodeTree'
        
        # Set the right shader type based on material type
        if is_gp_material:
            space.shader_type = 'LINESTYLE'  # For Grease Pencil materials
        else:
            space.shader_type = 'OBJECT'     # For regular materials
            
        # Assign node tree first
        space.node_tree = material.node_tree
        
        # Ensure the N-panel is closed using the show_region_ui property
        space.show_region_ui = False
        
        # Set window title
        new_screen.name = f"Material: {self.material_name}"
        
        # Clean up temporary object
        bpy.data.objects.remove(temp_obj, do_unlink=True)
        
        # Pin AFTER cleanup so reference is stable and not tied to temp object
        space.pin = True
        
        # Restore previous state
        bpy.context.view_layer.objects.active = active_obj
        for obj in selected_objects:
            obj.select_set(True)
            
        if current_mode != 'OBJECT':
            # Map the mode string to the appropriate mode_set value
            mode_map = {
                'EDIT_MESH': 'EDIT',
                'EDIT_CURVE': 'EDIT',
                'EDIT_SURFACE': 'EDIT',
                'EDIT_TEXT': 'EDIT',
                'EDIT_ARMATURE': 'EDIT',
                'EDIT_METABALL': 'EDIT',
                'EDIT_LATTICE': 'EDIT',
                'EDIT_GPENCIL': 'EDIT',
                'PAINT_GPENCIL': 'VERTEX_PAINT',
                'PAINT_VERTEX': 'VERTEX_PAINT',
                'PAINT_WEIGHT': 'WEIGHT_PAINT',
                'PAINT_TEXTURE': 'TEXTURE_PAINT',
                'SCULPT': 'SCULPT',
                'SCULPT_GPENCIL': 'SCULPT',
                'POSE': 'POSE',
            }
            
            # Get the mapped mode or use current_mode if not found
            mapped_mode = mode_map.get(current_mode, current_mode)
            
            try:
                bpy.ops.object.mode_set(mode=mapped_mode)
            except Exception as e:
                # If the mode_set fails, at least try to go back to object mode
                self.report({'WARNING'}, f"Could not restore previous mode: {e}")
                try:
                    bpy.ops.object.mode_set(mode='OBJECT')
                except RuntimeError:
                    pass  # Could not set object mode
        
        return {'FINISHED'}

class MATERIAL_OT_purge_unused(Operator):
    """Remove all unused materials from the blend file"""
    bl_idname = "material.purge_unused"
    bl_label = "Purge Unused Materials"
    bl_options = {'REGISTER', 'UNDO'}
    
    check_orphaned_data: BoolProperty(
        name="Check Orphaned Mesh Data",
        description="Check for materials assigned to mesh data with no users",
        default=True
    )
    
    @classmethod
    def poll(cls, context):
        return module_enabled
    
    def is_grease_pencil_object(self, obj):
        """Check if an object is a Grease Pencil object in any Blender version"""
        # Traditional check for older Blender versions
        if obj.type == 'GPENCIL':
            return True
            
        # Check for renamed object type in Blender 4.3+
        if obj.type == 'GREASEPENCIL':
            return True
            
        # In Blender 4.3+, grease pencil became a specialized curve type
        if obj.type == 'CURVES':
            # Additional checks for curves that are grease pencil
            if hasattr(obj, 'data') and hasattr(obj.data, 'curve_type'):
                if getattr(obj.data, 'curve_type', '') == 'GREASE_PENCIL':
                    return True
        
        # Additional checks for newer Blender versions (4.3+)
        if hasattr(obj, 'data') and obj.data:
            # Check by data type name
            data_type = getattr(type(obj.data), '__name__', '').lower()
            
            # Various possible data type names
            gp_type_names = ['gpencil', 'greasepencil', 'grease_pencil', 'curves_gpencil']
            
            for name in gp_type_names:
                if name in data_type:
                    return True
                    
            # Check for specific attributes that might indicate a grease pencil
            if hasattr(obj.data, 'layers') and hasattr(obj.data, 'strokes'):
                return True
        
        return False
        
    def is_grease_pencil_data(self, data):
        """Check if data is a Grease Pencil data block in any Blender version"""
        # Check data type name
        data_type = getattr(type(data), '__name__', '').lower()
        
        # Various possible data type names
        gp_type_names = ['gpencil', 'greasepencil', 'grease_pencil', 'curves_gpencil']
        if any(name in data_type for name in gp_type_names):
            return True
            
        # Check for Blender 4.3+ curve type
        if hasattr(data, 'curve_type') and data.curve_type == 'GREASE_PENCIL':
            return True
            
        # Check for specific attributes
        if hasattr(data, 'layers') and hasattr(data, 'strokes'):
            return True
            
        return False

    def check_orphaned_mesh_data(self):
        """Check for materials assigned to orphaned data"""
        orphaned_mat_count = 0
        orphaned_data_count = 0
        
        # Check standard data types
        for data_collection in [bpy.data.meshes, bpy.data.curves, bpy.data.metaballs, bpy.data.volumes]:
            for data in data_collection:
                if data.users == 0 and hasattr(data, "materials") and len(data.materials) > 0:
                    orphaned_data_count += 1
                    orphaned_mat_count += len(data.materials)
        
        # Loop through all objects and check if they're grease pencil with no users
        for obj in bpy.data.objects:
            if obj.users == 0 and self.is_grease_pencil_object(obj):
                if hasattr(obj, "material_slots") and len(obj.material_slots) > 0:
                    orphaned_data_count += 1
                    mat_count = sum(1 for slot in obj.material_slots if slot.material is not None)
                    orphaned_mat_count += mat_count
        
        # Check data collections for grease pencil data
        for collection_name in dir(bpy.data):
            if collection_name.startswith('__'):
                continue
                
            try:
                collection = getattr(bpy.data, collection_name)
                # Skip non-collection attributes
                if not hasattr(collection, '__iter__'):
                    continue
                    
                # Check items in the collection
                for data in collection:
                    # Skip if it has users
                    if not hasattr(data, 'users') or data.users > 0:
                        continue
                        
                    # Check if it's grease pencil data
                    if self.is_grease_pencil_data(data):
                        if hasattr(data, "materials") and len(data.materials) > 0:
                            orphaned_data_count += 1
                            orphaned_mat_count += len(data.materials)
            except Exception:
                pass
        
        return orphaned_mat_count, orphaned_data_count
    
    def execute(self, context):
        # Get count of materials before purging
        initial_count = len(bpy.data.materials)
        
        # Check for materials assigned to orphaned mesh data
        if self.check_orphaned_data:
            orphaned_mat_count, orphaned_data_count = self.check_orphaned_mesh_data()
            if orphaned_mat_count > 0:
                return context.window_manager.invoke_props_dialog(self, width=400)
        
        # Purge unused materials using Blender's built-in user counting
        for material in bpy.data.materials:
            if material.users == 0:
                bpy.data.materials.remove(material)
        
        # Calculate how many were removed
        removed_count = initial_count - len(bpy.data.materials)
        
        if removed_count > 0:
            self.report({'INFO'}, f"Removed {removed_count} unused material{'s' if removed_count > 1 else ''}")
        else:
            self.report({'INFO'}, "No unused materials found")
            
        return {'FINISHED'}
    
    def draw(self, context):
        layout = self.layout
        orphaned_mat_count, orphaned_data_count = self.check_orphaned_mesh_data()
        
        layout.label(text=f"Found {orphaned_mat_count} materials on {orphaned_data_count} orphaned data blocks")
        layout.label(text="These materials cannot be purged directly as they're still assigned")
        layout.label(text="to mesh data that isn't in use.")
        layout.separator()
        layout.label(text="Would you like to purge all unused data blocks?")
        layout.label(text="(This will remove unused meshes, curves, etc.)")
        
        # Create button row with only the purge and cancel buttons (no OK/Cancel at bottom)
        row = layout.row()
        op1 = row.operator("material.purge_orphaned_data", text="Purge All Unused Data", icon='TRASH')
        op2 = row.operator("material.purge_unused", text="Cancel")
        op2.check_orphaned_data = False
        
    def invoke(self, context, event):
        if self.check_orphaned_data:
            orphaned_mat_count, orphaned_data_count = self.check_orphaned_mesh_data()
            if orphaned_mat_count > 0:
                # Use custom dialog with custom draw function to completely replace default UI
                wm = context.window_manager
                return wm.invoke_popup(self, width=400)
        
        return self.execute(context)

class MATERIAL_OT_purge_orphaned_data(Operator):
    """Remove all unused data blocks from the blend file"""
    bl_idname = "material.purge_orphaned_data"
    bl_label = "Purge Orphaned Data"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        return module_enabled
    
    def execute(self, context):
        # Store counts before purging
        initial_materials = len(bpy.data.materials)
        initial_meshes = len(bpy.data.meshes)
        initial_curves = len(bpy.data.curves)
        initial_volumes = len(bpy.data.volumes)
        initial_metaballs = len(bpy.data.metaballs)
        initial_nodes = len(bpy.data.node_groups)
        
        # Purge unused data
        bpy.ops.outliner.orphans_purge(do_local_ids=True, do_linked_ids=False, do_recursive=True)
        
        # Calculate what was removed
        removed_materials = initial_materials - len(bpy.data.materials)
        removed_meshes = initial_meshes - len(bpy.data.meshes)
        removed_curves = initial_curves - len(bpy.data.curves)
        removed_volumes = initial_volumes - len(bpy.data.volumes)
        removed_metaballs = initial_metaballs - len(bpy.data.metaballs)
        removed_nodes = initial_nodes - len(bpy.data.node_groups)
        
        # Build report message
        report_parts = []
        total_removed = 0
        
        if removed_materials > 0:
            report_parts.append(f"{removed_materials} material{'s' if removed_materials != 1 else ''}")
            total_removed += removed_materials
            
        if removed_meshes > 0:
            report_parts.append(f"{removed_meshes} mesh{'es' if removed_meshes != 1 else ''}")
            total_removed += removed_meshes
            
        if removed_curves > 0:
            report_parts.append(f"{removed_curves} curve{'s' if removed_curves != 1 else ''}")
            total_removed += removed_curves
            
        if removed_volumes > 0:
            report_parts.append(f"{removed_volumes} volume{'s' if removed_volumes != 1 else ''}")
            total_removed += removed_volumes
            
        if removed_metaballs > 0:
            report_parts.append(f"{removed_metaballs} metaball{'s' if removed_metaballs != 1 else ''}")
            total_removed += removed_metaballs
            
        if removed_nodes > 0:
            report_parts.append(f"{removed_nodes} node group{'s' if removed_nodes != 1 else ''}")
            total_removed += removed_nodes
        
        if total_removed > 0:
            if len(report_parts) > 1:
                report_message = f"Removed {', '.join(report_parts[:-1])} and {report_parts[-1]}"
            else:
                report_message = f"Removed {report_parts[0]}"
            self.report({'INFO'}, report_message)
        else:
            self.report({'INFO'}, "No unused data found")
        
        return {'FINISHED'}

# Update the register function to include our new operators
def register():
    if not ModuleManager.register_module(sys.modules[__name__]):
        return
    
    ModuleManager.safe_register_class(MaterialManagerProperties)
    ModuleManager.safe_register_class(MATERIAL_OT_apply_to_selected)
    ModuleManager.safe_register_class(MATERIAL_OT_open_shader_window)
    ModuleManager.safe_register_class(MATERIAL_OT_open_material_list)
    ModuleManager.safe_register_class(MATERIAL_OT_purge_unused)
    ModuleManager.safe_register_class(MATERIAL_OT_purge_orphaned_data)
    ModuleManager.safe_register_class(MATERIAL_OT_create_new)
    ModuleManager.safe_register_class(MATERIAL_OT_select_linked_objects)
    ModuleManager.safe_register_class(MATERIAL_OT_toggle_show_all)
    
    # Register property group
    bpy.types.Scene.material_manager_props = bpy.props.PointerProperty(type=MaterialManagerProperties)
    

def unregister():
    if not ModuleManager.unregister_module(sys.modules[__name__]):
        return
    
    # Unregister classes
    ModuleManager.safe_unregister_class(MATERIAL_OT_open_material_list)
    ModuleManager.safe_unregister_class(MATERIAL_OT_open_shader_window)
    ModuleManager.safe_unregister_class(MATERIAL_OT_apply_to_selected)
    ModuleManager.safe_unregister_class(MATERIAL_OT_purge_unused)
    ModuleManager.safe_unregister_class(MATERIAL_OT_purge_orphaned_data)
    ModuleManager.safe_unregister_class(MATERIAL_OT_create_new)
    ModuleManager.safe_unregister_class(MATERIAL_OT_select_linked_objects)
    ModuleManager.safe_unregister_class(MATERIAL_OT_toggle_show_all)
    ModuleManager.safe_unregister_class(MaterialManagerProperties)