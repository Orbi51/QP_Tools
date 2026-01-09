"""
Production-Ready Enhanced CleanUp Module - Content-Aware Optimizer
Fixed node group identification and added new resolution strategies
"""

import bpy
from bpy.types import Operator, PropertyGroup
from bpy.props import StringProperty, BoolProperty, IntProperty, EnumProperty, CollectionProperty
import sys
import re
import os
from .module_helper import ModuleManager

# Module state
module_enabled = True
try:
    prefs = bpy.context.preferences.addons[__package__.split('.')[0]].preferences
    module_enabled = prefs.cleanup_enabled
except (KeyError, AttributeError):
    pass  # Preferences not available yet

# Centralized conflict selections storage
_conflict_selections = {
    'materials': {},
    'node_groups': {},
    'images': {}
}

# ============================================================================
# DATA TYPE CONFIGURATIONS
# ============================================================================

class DataTypeConfig:
    """Configuration for different data types"""
    def __init__(self, name, collection_attr, icon, linked_icon='LINKED'):
        self.name = name
        self.collection_attr = collection_attr
        self.icon = icon
        self.linked_icon = linked_icon

DATA_CONFIGS = {
    'materials': DataTypeConfig('Material', 'materials', 'MATERIAL'),
    'node_groups': DataTypeConfig('Node Group', 'node_groups', 'NODETREE'),
    'images': DataTypeConfig('Image', 'images', 'IMAGE_DATA')
}

# ============================================================================
# CORE UTILITIES
# ============================================================================

def is_linked_data(data_block):
    """Check if data block is linked from another blend file"""
    return hasattr(data_block, 'library') and data_block.library is not None

def get_linked_file_name(data_block):
    """Get linked file name (basename only)"""
    if is_linked_data(data_block):
        return os.path.basename(data_block.library.name)
    return None

def get_base_name(name):
    """Extract base name from duplicated name (Material.001 -> Material)"""
    match = re.match(r'^(.+?)\.(\d{3})$', name)
    return match.group(1) if match and 1 <= int(match.group(2)) <= 999 else name

def are_materials_identical(mat1, mat2):
    """Check if materials are functionally identical"""
    if not mat1 or not mat2 or mat1.use_nodes != mat2.use_nodes:
        return False
    
    if not mat1.use_nodes:
        return (mat1.diffuse_color[:3] == mat2.diffuse_color[:3] and
                mat1.metallic == mat2.metallic and
                mat1.roughness == mat2.roughness)
    
    if not mat1.node_tree or not mat2.node_tree:
        return mat1.node_tree == mat2.node_tree
    
    nodes1, nodes2 = mat1.node_tree.nodes, mat2.node_tree.nodes
    if len(nodes1) != len(nodes2):
        return False
    
    types1 = sorted([n.type for n in nodes1])
    types2 = sorted([n.type for n in nodes2])
    return types1 == types2

def are_node_groups_identical(ng1, ng2):
    """Fixed node group comparison for different Blender versions"""
    if not ng1 or not ng2:
        return False
    
    # Compare number of nodes
    if len(ng1.nodes) != len(ng2.nodes):
        return False
    
    # Compare number of links
    if len(ng1.links) != len(ng2.links):
        return False
    
    # Handle different Blender versions for interface comparison
    try:
        # Try modern Blender 4.0+ interface system first
        if hasattr(ng1, 'interface') and hasattr(ng2, 'interface'):
            interface1 = ng1.interface
            interface2 = ng2.interface
            
            # Get input and output items
            inputs1 = []
            outputs1 = []
            inputs2 = []
            outputs2 = []
            
            # Filter items_tree to only get socket items
            for item in interface1.items_tree:
                if hasattr(item, 'in_out'):
                    if item.in_out == 'INPUT':
                        inputs1.append((item.name, item.socket_type))
                    elif item.in_out == 'OUTPUT':
                        outputs1.append((item.name, item.socket_type))
            
            for item in interface2.items_tree:
                if hasattr(item, 'in_out'):
                    if item.in_out == 'INPUT':
                        inputs2.append((item.name, item.socket_type))
                    elif item.in_out == 'OUTPUT':
                        outputs2.append((item.name, item.socket_type))
            
            # Compare interfaces
            if len(inputs1) != len(inputs2) or len(outputs1) != len(outputs2):
                return False
            
            # Sort and compare
            inputs1.sort()
            inputs2.sort()
            outputs1.sort()
            outputs2.sort()
            
            if inputs1 != inputs2 or outputs1 != outputs2:
                return False
        
        # Try legacy Blender interface system (pre-4.0)
        elif hasattr(ng1, 'inputs') and hasattr(ng2, 'inputs'):
            if len(ng1.inputs) != len(ng2.inputs) or len(ng1.outputs) != len(ng2.outputs):
                return False
            
            for inp1, inp2 in zip(ng1.inputs, ng2.inputs):
                if inp1.name != inp2.name or inp1.type != inp2.type:
                    return False
            
            for out1, out2 in zip(ng1.outputs, ng2.outputs):
                if out1.name != out2.name or out1.type != out2.type:
                    return False
        
        else:
            # If we can't access interface info, just compare nodes
            print(f"Warning: Could not access node group interface for {ng1.name} and {ng2.name}")
    
    except Exception as e:
        print(f"Warning: Node group interface comparison failed: {e}")
        # Fall back to basic comparison
    
    # Compare node types as basic check
    types1 = sorted([n.type for n in ng1.nodes])
    types2 = sorted([n.type for n in ng2.nodes])
    
    return types1 == types2

def are_images_identical(img1, img2):
    """Check if images are identical (same file path or properties)"""
    if not img1 or not img2:
        return False
    
    # Both have no filepath (generated images)
    if not img1.filepath and not img2.filepath:
        return (img1.size[:] == img2.size[:] and 
                img1.depth == img2.depth and
                img1.channels == img2.channels)
    
    # One has filepath and other doesn't
    if bool(img1.filepath) != bool(img2.filepath):
        return False
    
    # Compare file paths
    if img1.filepath and img2.filepath:
        try:
            path1 = bpy.path.abspath(img1.filepath) if not os.path.isabs(img1.filepath) else img1.filepath
            path2 = bpy.path.abspath(img2.filepath) if not os.path.isabs(img2.filepath) else img2.filepath
            return os.path.normpath(path1) == os.path.normpath(path2)
        except (OSError, ValueError):
            return img1.filepath == img2.filepath  # Fallback to string comparison
    
    return False

def are_items_identical_by_type(item1, item2, data_collection):
    """Check if two items are identical based on data collection type"""
    try:
        if data_collection == bpy.data.materials:
            return are_materials_identical(item1, item2)
        elif data_collection == bpy.data.node_groups:
            return are_node_groups_identical(item1, item2)
        elif data_collection == bpy.data.images:
            return are_images_identical(item1, item2)
        else:
            return item1 == item2
    except Exception as e:
        print(f"Warning: Could not compare items: {e}")
        return False

# ============================================================================
# ENHANCED CONFLICT ANALYSIS WITH IDENTITY GROUPING
# ============================================================================

def group_items_by_identity(items, data_collection):
    """Group items by their actual content/structure identity"""
    identity_groups = []
    
    for item in items:
        # Find if this item belongs to an existing group
        placed_in_group = False
        
        for group in identity_groups:
            representative = group['representative']
            
            if are_items_identical_by_type(item, representative, data_collection):
                group['members'].append(item)
                placed_in_group = True
                break
        
        # If not placed in any existing group, create a new group
        if not placed_in_group:
            identity_groups.append({
                'representative': item,  # First item becomes the representative
                'members': [item]
            })
    
    return identity_groups

def analyze_data_conflicts_with_grouping(data_collection):
    """Enhanced conflict analysis that groups identical items together"""
    base_groups = {}
    
    # First, group by base name
    for item in data_collection:
        base_name = get_base_name(item.name)
        base_groups.setdefault(base_name, []).append(item)
    
    conflicts = {}
    
    for base_name, items in base_groups.items():
        if len(items) <= 1:
            continue
        
        # Group items by their actual content/structure
        identity_groups = group_items_by_identity(items, data_collection)
        
        local_items = [i for i in items if not is_linked_data(i)]
        linked_items = [i for i in items if is_linked_data(i)]
        
        # Determine conflict types with improved descriptions
        conflict_types = []
        if len(local_items) > 1:
            conflict_types.append("Local Duplicates")
        if len(linked_items) > 1:
            conflict_types.append("Multiple Linked")
        if local_items and linked_items:
            conflict_types.append("Local and Linked")
        if len(identity_groups) > 1:
            conflict_types.append("Non Identical")
        
        # Always include conflicts even if only identical groups (for Auto Clean mode)
        conflicts[base_name] = {
            'items': items,
            'local_items': local_items,
            'linked_items': linked_items,
            'conflict_types': conflict_types,
            'identity_groups': identity_groups
        }
    
    return conflicts

# ============================================================================
# PROPERTY GROUPS
# ============================================================================

class CLEANUP_DataOption(PropertyGroup):
    """Unified data option for any data type"""
    data_name: StringProperty(name="Data Name")
    user_count: IntProperty(name="User Count", default=0)
    is_selected: BoolProperty(name="Selected", default=False)
    is_linked: BoolProperty(name="Is Linked", default=False)
    linked_file: StringProperty(name="Linked File", default="")
    filepath: StringProperty(name="File Path", default="")  # For images
    group_info: StringProperty(name="Group Info", default="")  # For displaying group size

class CLEANUP_ConflictItem(PropertyGroup):
    """Unified conflict item for any data type"""
    base_name: StringProperty(name="Base Name")
    conflict_types: StringProperty(name="Conflict Types", default="")
    skip_this_conflict: BoolProperty(name="Skip This Conflict", default=False)
    data_type: StringProperty(name="Data Type", default="")
    
    data_options: CollectionProperty(type=CLEANUP_DataOption)

# ============================================================================
# UNIFIED SELECTION OPERATOR
# ============================================================================

class CLEANUP_OT_select_data_option(Operator):
    """Unified selection operator for all data types"""
    bl_idname = "cleanup.select_data_option"
    bl_label = "Select Data Option"
    
    conflict_base_name: StringProperty()
    data_name: StringProperty()
    data_type: StringProperty()
    
    def execute(self, context):
        global _conflict_selections
        
        # Update global selections
        _conflict_selections[self.data_type][self.conflict_base_name] = self.data_name
        
        # Find and update the cleanup operator's conflict data
        cleanup_op = self._find_cleanup_operator(context)
        
        if cleanup_op:
            for conflict in cleanup_op.conflicts:
                if conflict.base_name == self.conflict_base_name:
                    # Clear all selections in this conflict
                    for option in conflict.data_options:
                        option.is_selected = False
                    
                    # Set the selected one (only if it's local)
                    for option in conflict.data_options:
                        if (option.data_name == self.data_name and not option.is_linked):
                            option.is_selected = True
                            break
                    break
        
        # Force immediate UI refresh
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()
        
        return {'FINISHED'}
    
    def _find_cleanup_operator(self, context):
        """Find the active cleanup operator"""
        operator_map = {
            'materials': 'cleanup.clean_materials',
            'node_groups': 'cleanup.clean_node_groups', 
            'images': 'cleanup.clean_images'
        }
        
        target_idname = operator_map.get(self.data_type)
        if not target_idname:
            return None
        
        for op in context.window_manager.operators:
            if (hasattr(op, 'bl_idname') and 
                op.bl_idname == target_idname and 
                hasattr(op, 'conflicts') and
                hasattr(op, 'has_conflicts') and
                op.has_conflicts):
                return op
        return None

# ============================================================================
# BASE CLEANUP OPERATOR CLASS
# ============================================================================

class BaseCleanupOperator(Operator):
    """Base class for all cleanup operators - content-aware optimizer"""
    
    force_remap: BoolProperty(name="Force Remap", default=False)
    conflicts: CollectionProperty(type=CLEANUP_ConflictItem)
    has_conflicts: BoolProperty(default=False)
    
    # Updated global resolution strategy with new default
    global_resolution: EnumProperty(
        name="Resolution Strategy",
        items=[
            ('AUTO_CLEAN', "Auto Clean Identical", "Automatically clean identical duplicates (recommended)"),
            ('CHOOSE_DATA', "Choose Data", "Select which data version to keep for each conflict (remaps all)"),
            ('KEEP_LINKED', "Replace with Linked", "Keep linked data, remove local duplicates"), 
        ],
        default='AUTO_CLEAN'  # New default
    )
    
    # Abstract properties that subclasses must define
    DATA_TYPE = None
    
    @property
    def config(self):
        """Get configuration for this data type"""
        return DATA_CONFIGS[self.DATA_TYPE]
    
    @property
    def data_collection(self):
        """Get the Blender data collection for this data type"""
        return getattr(bpy.data, self.config.collection_attr)
    
    @classmethod
    def poll(cls, context):
        if not module_enabled:
            return False
        if cls.DATA_TYPE is None:
            return False
        return bool(getattr(bpy.data, DATA_CONFIGS[cls.DATA_TYPE].collection_attr, None))
    
    def invoke(self, context, event):
        global _conflict_selections
        _conflict_selections[self.DATA_TYPE].clear()
        
        self.force_remap = event.shift
        if self.force_remap:
            return self.execute(context)
        
        # Use enhanced conflict analysis with grouping
        conflicts = analyze_data_conflicts_with_grouping(self.data_collection)
        
        if conflicts:
            self.has_conflicts = True
            self.conflicts.clear()
            
            # Always collect ALL conflicts, then filter during display
            for base_name, info in conflicts.items():
                conflict_item = self.conflicts.add()
                conflict_item.base_name = base_name
                conflict_item.conflict_types = ", ".join(info['conflict_types'])
                conflict_item.data_type = self.DATA_TYPE
                
                # Store all items for later filtering in draw methods
                local_items = [item for item in info['items'] if not is_linked_data(item)]
                linked_items = [item for item in info['items'] if is_linked_data(item)]
                
                # Initialize selection for Choose Data mode
                if self.global_resolution == 'CHOOSE_DATA' and local_items:
                    selected_option_name = local_items[0].name
                    _conflict_selections[self.DATA_TYPE][base_name] = selected_option_name
                
                # Add ALL items (both local and linked) to data_options
                for item in info['items']:
                    option = conflict_item.data_options.add()
                    option.data_name = item.name
                    option.user_count = item.users
                    option.is_linked = is_linked_data(item)
                    
                    if option.is_linked:
                        option.linked_file = get_linked_file_name(item) or "Unknown"
                    
                    if self.DATA_TYPE == 'images' and hasattr(item, 'filepath'):
                        option.filepath = item.filepath
                    
                    # Set selection for Choose Data mode
                    if (self.global_resolution == 'CHOOSE_DATA' and 
                        not option.is_linked and 
                        local_items and 
                        item.name == local_items[0].name):
                        option.is_selected = True
                    else:
                        option.is_selected = False
                
                # Store identity groups info for Auto Clean mode
                if self.global_resolution == 'AUTO_CLEAN':
                    # Only calculate group info for items that actually have duplicates to clean
                    for group in info['identity_groups']:
                        representative = group['representative']
                        local_members = [m for m in group['members'] if not is_linked_data(m)]
                        
                        # Only process groups with multiple local members (actual duplicates)
                        if len(local_members) > 1:
                            group_size = len(group['members'])
                            
                            # Update the representative option with group info
                            for option in conflict_item.data_options:
                                if (option.data_name == representative.name and 
                                    option.is_linked == is_linked_data(representative)):
                                    if group_size > 1:
                                        option.group_info = f"(+{group_size-1} identical will be remapped)"
                                    else:
                                        option.group_info = "(unique)"
                                    option.user_count = sum(member.users for member in group['members'])
                                    break
            
            # Always show dialog if there are any conflicts
            if self.conflicts:
                dialog_width = 800 if self.global_resolution == 'AUTO_CLEAN' else 700
                return context.window_manager.invoke_props_dialog(self, width=dialog_width)
        
        return self.execute(context)
    
    def _get_local_identity_groups(self, identity_groups):
        """Get identity groups that contain local (non-linked) items"""
        local_groups = []
        for group in identity_groups:
            local_members = [member for member in group['members'] if not is_linked_data(member)]
            if local_members:
                local_representative = next((member for member in group['members'] if not is_linked_data(member)), group['representative'])
                local_groups.append({
                    'representative': local_representative,
                    'members': group['members']
                })
        return local_groups
    
    def draw(self, context):
        """Unified draw method for all cleanup operators"""
        layout = self.layout
        
        if self.has_conflicts:
            # Header
            header = layout.box()
            header.label(text=f"{self.config.name} Conflicts with Linked Data", icon='ERROR')
            
            # Global resolution strategy
            strategy_box = layout.box()
            strategy_box.label(text="Resolution Strategy:", icon='SETTINGS')
            strategy_box.prop(self, "global_resolution", text="")
            
            layout.separator()
            
            # Show conflicts based on global strategy
            for conflict in self.conflicts:
                self._draw_conflict(layout, conflict)
        else:
            layout.label(text="No conflicts found. Processing...")
    
    def _draw_conflict(self, layout, conflict):
        """Draw individual conflict UI"""
        # For Auto Clean, check if this conflict has meaningful duplicates before drawing
        if self.global_resolution == 'AUTO_CLEAN':
            meaningful_options = [opt for opt in conflict.data_options 
                                if not opt.is_linked and opt.group_info and 
                                "(+" in opt.group_info and "identical will be remapped)" in opt.group_info]
            
            if not meaningful_options:
                return  # Don't draw conflicts with no meaningful duplicates
        
        box = layout.box()
        
        # Conflict header
        header_row = box.row()
        header_row.label(text=f"'{conflict.base_name}'", icon=self.config.icon)
        header_row.label(text=f"({conflict.conflict_types})")
        
        # Individual skip option (not for AUTO_CLEAN)
        if self.global_resolution != 'AUTO_CLEAN':
            skip_row = box.row()
            skip_row.prop(conflict, "skip_this_conflict", text="Skip this conflict")
        
        if not conflict.skip_this_conflict:
            if self.global_resolution == 'AUTO_CLEAN':
                self._draw_auto_clean_summary(box, conflict)
            elif self.global_resolution == 'CHOOSE_DATA':
                self._draw_choose_data_options(box, conflict)
            elif self.global_resolution == 'KEEP_LINKED':
                self._draw_preview_options(box, conflict)
        elif conflict.skip_this_conflict:
            skip_box = box.box()
            skip_box.label(text="This conflict will be skipped", icon='PAUSE')
    
    def _draw_auto_clean_summary(self, box, conflict):
        """Draw Auto Clean summary showing what will be done"""
        # Filter to only show items that actually have duplicates to clean
        meaningful_options = [opt for opt in conflict.data_options 
                            if not opt.is_linked and opt.group_info and 
                            "(+1 identical will be remapped)" in opt.group_info or 
                            "(+2 identical will be remapped)" in opt.group_info or
                            "(+3 identical will be remapped)" in opt.group_info or
                            "(+4 identical will be remapped)" in opt.group_info or
                            "(+5 identical will be remapped)" in opt.group_info or
                            "(+" in opt.group_info and "identical will be remapped)" in opt.group_info]
        
        if not meaningful_options:
            # This conflict has no actual duplicates to clean - don't show it
            return
        
        summary_box = box.box()
        summary_box.label(text="Auto Clean Summary:", icon='INFO')
        
        for option in meaningful_options:
            row = summary_box.row()
            row.scale_y = 1.1
            
            # Show what will happen
            row.label(text=f"✓ {option.data_name} will be kept {option.group_info}", icon='LOOP_FORWARDS')
            
            # Add user count info
            details_col = row.column()
            details_col.scale_y = 0.8
            details_col.alignment = 'RIGHT'
            details_col.label(text=f"Users: {option.user_count}")
    
    def _draw_choose_data_options(self, box, conflict):
        """Enhanced Choose Data mode - shows all items for selection"""
        options_box = box.box()
        
        # Filter to only show local data
        local_options = [opt for opt in conflict.data_options if not opt.is_linked]
        
        if len(local_options) < 2:
            # Compact display for no choice needed
            row = options_box.row()
            row.label(text=f"No choice needed for {self.config.name.lower()}:", icon='INFO')
            
            # Show linked versions in a compact format
            linked_options = [opt for opt in conflict.data_options if opt.is_linked]
            if linked_options:
                linked_row = options_box.row()
                linked_names = ", ".join([opt.data_name for opt in linked_options])
                linked_row.label(text=f"Linked versions found: {linked_names}", icon='LINKED')
            elif len(local_options) == 1:
                local_row = options_box.row()
                local_row.label(text=f"Only local version: {local_options[0].data_name}", icon=self.config.icon)
        else:
            selection_text = f"Select {self.config.name} version to keep (all others will be remapped to this):"
            options_box.label(text=selection_text)
            
            # Get current selection from global state
            global _conflict_selections
            current_selection = _conflict_selections[self.DATA_TYPE].get(conflict.base_name)
            
            # Sync selection state
            for option in local_options:
                option.is_selected = (option.data_name == current_selection)
            
            for option in local_options:
                row = options_box.row()
                row.scale_y = 1.2
                
                is_selected = option.is_selected
                
                # Button text (no group info in choose mode)
                button_text = f"{'●' if is_selected else '○'} {option.data_name}"
                
                op = row.operator("cleanup.select_data_option", 
                                text=button_text, 
                                icon=self.config.icon,
                                depress=is_selected,
                                emboss=True)
                
                op.conflict_base_name = conflict.base_name
                op.data_name = option.data_name
                op.data_type = self.DATA_TYPE
                
                # Details showing individual users
                details = f"Users: {option.user_count} | Local"
                if self.DATA_TYPE == 'images' and option.filepath:
                    details += f" | {os.path.basename(option.filepath)}"
                
                details_col = row.column()
                details_col.scale_y = 0.8
                details_col.alignment = 'LEFT'  
                details_col.label(text=details)
    
    def _draw_preview_options(self, box, conflict):
        """Draw preview for KEEP_LINKED mode with proper icons"""
        # Separate linked and local options
        linked_options = [opt for opt in conflict.data_options if opt.is_linked]
        local_options = [opt for opt in conflict.data_options if not opt.is_linked]
        
        # Show what will be kept (linked data)
        if linked_options:
            preview_box = box.box()
            preview_box.label(text="Will be kept (Linked):", icon='LINKED')
            
            for option in linked_options:
                row = preview_box.row()
                row.scale_y = 1.2
                row.alert = True
                
                row.label(text=f"● {option.data_name}", icon=self.config.linked_icon)
                
                # Show linked file info
                details_col = row.column()
                details_col.scale_y = 0.8
                details_col.alignment = 'RIGHT'
                details_col.label(text=f"Users: {option.user_count} | {option.linked_file}")
        
        # Show what will be removed (local data)
        if local_options:
            remove_box = box.box()
            remove_box.label(text="Will be removed (Local):")
            
            for option in local_options:
                row = remove_box.row()
                row.scale_y = 0.9
                row.label(text=f"✗ {option.data_name}", icon=self.config.icon)
                
                # Show user count
                details_col = row.column()
                details_col.scale_y = 0.8
                details_col.alignment = 'RIGHT'
                details_col.label(text=f"Users: {option.user_count}")
    
    def execute(self, context):
        """Execute cleanup with enhanced strategies"""
        if not self.has_conflicts:
            return self._standard_cleanup_with_grouping()
        
        if self.global_resolution == 'AUTO_CLEAN':
            return self._auto_clean_execution()
        elif self.global_resolution == 'CHOOSE_DATA':
            return self._choose_data_execution()
        elif self.global_resolution == 'KEEP_LINKED':
            return self._keep_linked_execution()
        else:
            return self._conflict_cleanup_with_grouping()
    
    def _auto_clean_execution(self):
        """Auto Clean execution - automatically clean identical groups"""
        processed = 0
        skipped = 0
        
        # Use the standard cleanup logic but only process meaningful duplicates
        conflicts = analyze_data_conflicts_with_grouping(self.data_collection)
        
        for conflict_base_name, info in conflicts.items():
            # Check if this conflict has meaningful duplicates to clean
            has_meaningful_duplicates = False
            for group in info['identity_groups']:
                local_members = [m for m in group['members'] if not is_linked_data(m)]
                if len(local_members) > 1:  # This group has local duplicates
                    has_meaningful_duplicates = True
                    break
            
            if not has_meaningful_duplicates:
                # Count items that would be skipped for reporting
                all_items = [i for i in self.data_collection if get_base_name(i.name) == conflict_base_name]
                skipped += len(all_items) - 1
                continue
            
            # Process the meaningful duplicates using standard grouping logic
            base_groups = {}
            for item in self.data_collection:
                base_name = get_base_name(item.name)
                if base_name == conflict_base_name:
                    base_groups.setdefault(base_name, []).append(item)
            
            for base_name, items in base_groups.items():
                if len(items) <= 1:
                    continue
                
                # Group by identity
                identity_groups = group_items_by_identity(items, self.data_collection)
                
                # Process each identity group
                for group in identity_groups:
                    members = group['members']
                    if len(members) <= 1:
                        continue
                    
                    # Choose representative (prefer local, then alphabetically first)
                    local_members = [m for m in members if not is_linked_data(m)]
                    representative = local_members[0] if local_members else members[0]
                    
                    # Remap all other members to the representative
                    for member in members:
                        if member == representative:
                            continue
                        
                        # Safety check: never remove linked data
                        if is_linked_data(member):
                            continue
                        
                        # Safe to remap since we're only processing identical items
                        self._remap_data(member, representative)
                        self.data_collection.remove(member)
                        processed += 1
        
        message = f"Processed {processed} {self.config.collection_attr}"
        if skipped:
            message += f", skipped {skipped} (no duplicates)"
        
        self.report({'INFO'}, message)
        return {'FINISHED'}
    
    def _choose_data_execution(self):
        """Choose Data execution - remap everything to chosen item regardless of identity"""
        global _conflict_selections
        processed = 0
        skipped = 0
        no_choice_needed = 0
        
        for conflict in self.conflicts:
            if conflict.skip_this_conflict:
                base_name = conflict.base_name
                all_items = [i for i in self.data_collection if get_base_name(i.name) == base_name]
                skipped += len(all_items) - 1
                continue
            
            base_name = conflict.base_name
            all_items = [i for i in self.data_collection if get_base_name(i.name) == base_name]
            local_items = [i for i in all_items if not is_linked_data(i)]
            
            # Check if there's actually a choice to make
            if len(local_items) < 2:
                no_choice_needed += len(all_items) - 1 if all_items else 0
                continue
            
            selected_name = _conflict_selections[self.DATA_TYPE].get(base_name)
            
            if not selected_name:
                continue
            
            # Find the selected target
            target = None
            for item in all_items:
                if item.name == selected_name:
                    target = item
                    break
            
            if not target:
                continue
            
            # Remap ALL other items to the selected target (regardless of identity)
            for item in all_items:
                if item != target and not is_linked_data(item):
                    self._remap_data(item, target)
                    self.data_collection.remove(item)
                    processed += 1
        
        _conflict_selections[self.DATA_TYPE].clear()
        
        message = f"Processed {processed} {self.config.collection_attr}"
        if skipped:
            message += f", skipped {skipped}"
        if no_choice_needed:
            message += f", no choice needed for {no_choice_needed} items"
        
        self.report({'INFO'}, message)
        return {'FINISHED'}
    
    def _keep_linked_execution(self):
        """Keep Linked execution - remap local data to linked versions"""
        processed = 0
        skipped = 0
        no_linked_available = 0
        
        # Re-analyze conflicts to get fresh data
        conflicts = analyze_data_conflicts_with_grouping(self.data_collection)
        
        for conflict in self.conflicts:
            if conflict.skip_this_conflict:
                base_name = conflict.base_name
                all_items = [i for i in self.data_collection if get_base_name(i.name) == base_name]
                skipped += len(all_items) - 1
                continue
            
            base_name = conflict.base_name
            conflict_info = conflicts.get(base_name)
            
            if not conflict_info:
                continue
            
            # Find linked and local items
            all_items = conflict_info['items']
            linked_items = [item for item in all_items if is_linked_data(item)]
            local_items = [item for item in all_items if not is_linked_data(item)]
            
            if not linked_items:
                no_linked_available += len(local_items)
                continue  # No linked data to remap to
            
            # Choose the first linked item as target
            target_linked = linked_items[0]
            
            # Remap all local items to the linked target
            for local_item in local_items:
                try:
                    self._remap_data(local_item, target_linked)
                    self.data_collection.remove(local_item)
                    processed += 1
                except Exception as e:
                    print(f"Warning: Could not remap {local_item.name} to {target_linked.name}: {e}")
                    skipped += 1
        
        message = f"Processed {processed} {self.config.collection_attr}"
        if skipped:
            message += f", skipped {skipped}"
        if no_linked_available:
            message += f", no linked versions available for {no_linked_available} items"
        
        self.report({'INFO'}, message)
        return {'FINISHED'}
    
    def _standard_cleanup_with_grouping(self):
        """Enhanced standard cleanup that respects identity groups"""
        base_groups = {}
        for item in self.data_collection:
            base_name = get_base_name(item.name)
            base_groups.setdefault(base_name, []).append(item)
        
        processed = 0
        skipped_linked = 0
        
        for base_name, items in base_groups.items():
            if len(items) <= 1:
                continue
            
            # Group by identity
            identity_groups = group_items_by_identity(items, self.data_collection)
            
            # Process each identity group
            for group in identity_groups:
                members = group['members']
                if len(members) <= 1:
                    continue
                
                # Choose representative (prefer local, then alphabetically first)
                local_members = [m for m in members if not is_linked_data(m)]
                representative = local_members[0] if local_members else members[0]
                
                # Remap all other members to the representative
                for member in members:
                    if member == representative:
                        continue
                    
                    # Safety check: never remove linked data
                    if is_linked_data(member):
                        skipped_linked += 1
                        continue
                    
                    # Safe to remap since we're only processing identical items
                    self._remap_data(member, representative)
                    self.data_collection.remove(member)
                    processed += 1
        
        message = f"Processed {processed} {self.config.collection_attr}"
        if skipped_linked > 0:
            message += f", skipped {skipped_linked} linked"
        
        self.report({'INFO'}, message)
        return {'FINISHED'}
    
    def _conflict_cleanup_with_grouping(self):
        """Enhanced conflict cleanup with identity group awareness"""
        global _conflict_selections
        processed = 0
        skipped = 0
        
        # Re-analyze conflicts to get fresh identity groups
        conflicts = analyze_data_conflicts_with_grouping(self.data_collection)
        
        for conflict in self.conflicts:
            if conflict.skip_this_conflict:
                base_name = conflict.base_name
                all_items = [i for i in self.data_collection if get_base_name(i.name) == base_name]
                skipped += len(all_items) - 1
                continue
            
            base_name = conflict.base_name
            conflict_info = conflicts.get(base_name)
            
            if not conflict_info:
                continue
            
            identity_groups = conflict_info['identity_groups']
            selected_name = _conflict_selections[self.DATA_TYPE].get(base_name)
            
            if not selected_name:
                continue
            
            # Find which group the selected representative belongs to
            target_group = None
            for group in identity_groups:
                if group['representative'].name == selected_name:
                    target_group = group
                    break
            
            if not target_group:
                continue
            
            target_representative = target_group['representative']
            
            # Process each identity group
            for group in identity_groups:
                representative = group['representative']
                
                if group == target_group:
                    # Selected group - remap all members to selected representative
                    for member in group['members']:
                        if member != target_representative and not is_linked_data(member):
                            self._remap_data(member, target_representative)
                            self.data_collection.remove(member)
                            processed += 1
                else:
                    # Non-selected group - keep representative, remap identical duplicates
                    for member in group['members']:
                        if member != representative and not is_linked_data(member):
                            self._remap_data(member, representative)
                            self.data_collection.remove(member)
                            processed += 1
        
        _conflict_selections[self.DATA_TYPE].clear()
        
        message = f"Processed {processed} {self.config.collection_attr}"
        if skipped:
            message += f", skipped {skipped}"
        
        self.report({'INFO'}, message)
        return {'FINISHED'}
    
    def _remap_data(self, old_data, new_data):
        """Remap data usage throughout scene - implemented by subclasses"""
        raise NotImplementedError("Subclasses must implement _remap_data method")

# ============================================================================
# CONCRETE CLEANUP OPERATORS
# ============================================================================

class CLEANUP_OT_clean_materials(BaseCleanupOperator):
    """Clean duplicate materials with content-aware optimization"""
    bl_idname = "cleanup.clean_materials"
    bl_label = "Clean Duplicate Materials"
    bl_description = "Clean duplicate materials with intelligent grouping\nShift+Click: Force remap identical materials only"
    bl_options = {'REGISTER', 'UNDO'}
    
    DATA_TYPE = 'materials'
    
    def _remap_data(self, old_mat, new_mat):
        """Remap material usage throughout scene"""
        # Object slots
        for obj in bpy.data.objects:
            if hasattr(obj, 'material_slots'):
                for slot in obj.material_slots:
                    if slot.material == old_mat:
                        slot.material = new_mat
        
        # Node groups  
        for ng in bpy.data.node_groups:
            for node in ng.nodes:
                if hasattr(node, 'material') and node.material == old_mat:
                    node.material = new_mat

class CLEANUP_OT_clean_node_groups(BaseCleanupOperator):
    """Clean duplicate node groups with content-aware optimization"""
    bl_idname = "cleanup.clean_node_groups"
    bl_label = "Clean Duplicate Node Groups"
    bl_description = "Clean duplicate node groups with intelligent grouping\nShift+Click: Force remap identical node groups only"
    bl_options = {'REGISTER', 'UNDO'}
    
    DATA_TYPE = 'node_groups'
    
    def _remap_data(self, old_ng, new_ng):
        """Safely remap node group usage throughout scene"""
        # Remap in other node groups
        for ng in bpy.data.node_groups:
            if ng == old_ng:
                continue
            for node in ng.nodes:
                if node.type == 'GROUP' and hasattr(node, 'node_tree') and node.node_tree == old_ng:
                    node.node_tree = new_ng
        
        # Remap in geometry node modifiers
        for obj in bpy.data.objects:
            for mod in obj.modifiers:
                if (mod.type == 'NODES' and 
                    hasattr(mod, 'node_group') and 
                    mod.node_group == old_ng):
                    mod.node_group = new_ng
        
        # Remap in material node trees
        for mat in bpy.data.materials:
            if mat.node_tree:
                for node in mat.node_tree.nodes:
                    if node.type == 'GROUP' and hasattr(node, 'node_tree') and node.node_tree == old_ng:
                        node.node_tree = new_ng
        
        # Remap in world node trees
        for world in bpy.data.worlds:
            if world.node_tree:
                for node in world.node_tree.nodes:
                    if node.type == 'GROUP' and hasattr(node, 'node_tree') and node.node_tree == old_ng:
                        node.node_tree = new_ng

class CLEANUP_OT_clean_images(BaseCleanupOperator):
    """Clean duplicate images with content-aware optimization"""
    bl_idname = "cleanup.clean_images"
    bl_label = "Clean Duplicate Images"
    bl_description = "Clean duplicate images with intelligent grouping\nShift+Click: Force remap identical images only"
    bl_options = {'REGISTER', 'UNDO'}
    
    DATA_TYPE = 'images'
    
    def _remap_data(self, old_img, new_img):
        """Safely remap image usage throughout scene"""
        # Remap in materials
        for mat in bpy.data.materials:
            if mat.node_tree:
                for node in mat.node_tree.nodes:
                    if (node.type == 'TEX_IMAGE' and 
                        hasattr(node, 'image') and 
                        node.image == old_img):
                        node.image = new_img
        
        # Remap in node groups
        for ng in bpy.data.node_groups:
            for node in ng.nodes:
                if (node.type == 'TEX_IMAGE' and 
                    hasattr(node, 'image') and 
                    node.image == old_img):
                    node.image = new_img
        
        # Remap in world shaders
        for world in bpy.data.worlds:
            if world.node_tree:
                for node in world.node_tree.nodes:
                    if (node.type == 'TEX_IMAGE' and 
                        hasattr(node, 'image') and 
                        node.image == old_img):
                        node.image = new_img

# ============================================================================
# REGISTRATION
# ============================================================================

def register():
    if not ModuleManager.register_module(sys.modules[__name__]):
        return
    
    classes = [
        CLEANUP_DataOption,
        CLEANUP_ConflictItem,
        CLEANUP_OT_select_data_option,
        CLEANUP_OT_clean_materials,
        CLEANUP_OT_clean_node_groups,
        CLEANUP_OT_clean_images,
    ]
    
    for cls in classes:
        ModuleManager.safe_register_class(cls)

def unregister():
    if not ModuleManager.unregister_module(sys.modules[__name__]):
        return
    
    classes = [
        CLEANUP_OT_clean_images,
        CLEANUP_OT_clean_node_groups,
        CLEANUP_OT_clean_materials,
        CLEANUP_OT_select_data_option,
        CLEANUP_ConflictItem,
        CLEANUP_DataOption,
    ]
    
    for cls in classes:
        ModuleManager.safe_unregister_class(cls)

if __name__ == "__main__":
    register()