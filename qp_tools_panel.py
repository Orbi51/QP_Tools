import bpy
from bpy.types import Panel
import sys
import os
import json
import tempfile

# Import required modules
from .module_helper import ModuleManager

# Module state variables
module_enabled = True
_is_registered = False

# Utility functions for QuickAsset module
def get_temp_file_path():
    """Get the temporary status file path"""
    return os.path.join(tempfile.gettempdir(), "quickasset_status.json")

def is_background_process_running():
    """Check if a background process is running"""
    status_file = get_temp_file_path()
    if os.path.exists(status_file):
        try:
            with open(status_file, 'r') as f:
                status = json.load(f)
                return status.get('running', False)
        except (OSError, json.JSONDecodeError):
            return False
    return False

def draw_node_asset_panel(panel_self, context, tree_type_name, asset_type, get_selection_func, icon='NODETREE'):
    """
    Shared draw function for node editor asset panels to reduce code duplication.
    
    Args:
        panel_self: The panel instance (self)
        context: Blender context
        tree_type_name: Display name for tree type (e.g., "shader node", "compositor node")
        asset_type: Asset type for operator ('MATERIAL', 'GEONODES')
        get_selection_func: Function returning (items_list, data_type_string, no_selection_message)
        icon: Icon to display items in selection list
    """
    layout = panel_self.layout
    settings = context.scene.asset_library_settings

    # Status indicator for background process
    if is_background_process_running():
        status_file = get_temp_file_path()
        try:
            with open(status_file, 'r') as f:
                status = json.load(f)
                status_box = layout.box()
                status_box.label(text=f"Status: {status.get('status', 'Processing...')}", icon='SORTTIME')
        except (OSError, json.JSONDecodeError):
            pass  # Could not read status file

    # Library Path Box
    path_box = layout.box()
    path_box.label(text="Library Location:", icon='FILE_FOLDER')
    path_box.prop(settings, "library_path", text="")

    if not settings.library_path:
        return

    # Target File Box
    file_box = layout.box()
    file_box.label(text="Target File:", icon='FILE_BLEND')
    file_box.prop(settings, "create_new_library")
    
    if settings.create_new_library:
        file_box.prop(settings, "new_file_name", text="File Name")
    else:
        file_box.prop(settings, "existing_file")
        
        # Show conflicts only if a valid file is selected
        if settings.existing_file != 'NONE':
            filepath = os.path.join(settings.library_path, settings.existing_file)
            
            # Get selection for conflict checking
            selected_items, data_type, _ = get_selection_func(context)
            
            if selected_items:
                conflicts = settings.scan_conflicts(context, filepath, selected_items, data_type)
                if conflicts:
                    _draw_conflicts_helper(layout, conflicts, settings)

    # Check if we can proceed
    can_proceed = settings.create_new_library or settings.existing_file != 'NONE'

    # Asset Metadata Box
    metadata_box = layout.box()
    metadata_box.label(text="Asset Metadata:", icon='PROPERTIES')
    metadata_box.active = can_proceed
    
    metadata_box.label(text="Catalog:")
    metadata_box.prop(settings, "selected_catalog", text="")
    
    metadata_box.label(text="Tags (comma-separated):")
    metadata_box.prop(settings, "tags", text="")

    # Rename Options Box
    rename_box = layout.box()
    rename_box.label(text="Naming Options:", icon='SORTALPHA')
    rename_box.active = can_proceed
    rename_box.prop(settings, "rename_viewport_assets")
    if settings.rename_viewport_assets:
        rename_box.prop(settings, "asset_base_name")
    
    # Selection Info Box
    selection_box = layout.box()
    selection_box.label(text="What will be saved:", icon='EXPORT')
    selection_box.active = can_proceed
    
    # Get selection for display
    selected_items, _, no_selection_msg = get_selection_func(context)
    
    if selected_items:
        # Display count
        item_count = len(selected_items)
        item_label = f"{item_count} {tree_type_name} "
        item_label += "group" if item_count == 1 else "groups"
        item_label += " selected"
        selection_box.label(text=item_label)
        
        # Display each item
        for i, item in enumerate(selected_items):
            if settings.rename_viewport_assets and settings.asset_base_name:
                new_name = settings.asset_base_name if i == 0 else f"{settings.asset_base_name}.{str(i+1).zfill(3)}"
                selection_box.label(text=f"• {item.name} → {new_name}", icon=icon)
            else:
                selection_box.label(text=f"• {item.name}", icon=icon)
    else:
        selection_box.label(text=no_selection_msg)
    
    # Add to Library Button
    row = layout.row(align=True)
    row.scale_y = 1.5
    row.enabled = can_proceed and not is_background_process_running()
    op = row.operator("asset.add_to_library", text="Add to Library", icon='ASSET_MANAGER')
    op.asset_type = asset_type


def _draw_conflicts_helper(layout, conflicts, settings):
    """Helper to draw conflict warnings - shared by all panels"""
    conflict_box = layout.box()
    conflict_box.alert = True
    
    row = conflict_box.row()
    row.label(text="", icon='ERROR')
    row.label(text="Name Conflicts Detected!")
    
    for name in conflicts:
        row = conflict_box.row()
        row.label(text="", icon='DUPLICATE')
        row.label(text=name)
    
    conflict_box.separator()
    conflict_box.label(text="If asset name exists:")
    conflict_box.prop(settings, "conflict_action", text="")

# Main QPTools panel
class QP_PT_main_panel(Panel):
    """Main QPTools Panel in 3D View"""
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'QPTools'
    bl_label = "QPTools"
    bl_idname = "QP_PT_main_panel"
    
    @classmethod
    def poll(cls, context):
        # Show panel if either module is enabled
        materiallist_enabled = False
        quickasset_enabled = False
        
        # Check MaterialList
        material_list_module = sys.modules.get(f"{__package__}.MaterialList")
        if material_list_module and hasattr(material_list_module, "module_enabled"):
            materiallist_enabled = material_list_module.module_enabled
        
        # Check QuickAsset
        quick_asset_module = sys.modules.get(f"{__package__}.quick_asset_library")
        if quick_asset_module and hasattr(quick_asset_module, "module_enabled"):
            quickasset_enabled = quick_asset_module.module_enabled
        
        return module_enabled and (materiallist_enabled or quickasset_enabled)
    
    def draw(self, context):
        layout = self.layout
        from . import updater
        updater.draw_sidebar_update_notice(layout)
        layout.label(text="Activated Modules")

# Materials sub-panel
class QP_PT_materials_panel(Panel):
    """Materials Panel in QPTools"""
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'QPTools'
    bl_label = "Material List"
    bl_parent_id = "QP_PT_main_panel"
    bl_idname = "QP_PT_materials_panel"
    
    @classmethod
    def poll(cls, context):
        # Only show if MaterialList module is enabled
        material_list_module = sys.modules.get(f"{__package__}.MaterialList")
        return (module_enabled and 
                material_list_module and 
                hasattr(material_list_module, "module_enabled") and 
                material_list_module.module_enabled and
                hasattr(context.scene, "material_manager_props"))
    
    def draw(self, context):
        layout = self.layout
        props = context.scene.material_manager_props
        
        # Add purge button at the top
        purge_row = layout.row(align=True)
        purge_row.operator("material.purge_unused", icon='TRASH')
        
        # Add hide linked materials option
        options_row = layout.row(align=True)
        options_row.prop(props, "hide_linked_materials")
        
        # Search field
        layout.prop(props, "search_term", icon='VIEWZOOM')
        
        # Object Materials collapsible section
        object_box = layout.box()
        object_header = object_box.row(align=True)
        object_header.alignment = 'LEFT'
        
        icon = 'TRIA_DOWN' if props.object_materials_expanded else 'TRIA_RIGHT'
        object_header.prop(props, "object_materials_expanded", text="Object Materials", 
                        icon=icon, emboss=False)
        
        # Show object materials if expanded
        if props.object_materials_expanded:
            # Get all regular materials (non-grease-pencil)
            object_materials = [mat for mat in bpy.data.materials 
                            if not (hasattr(mat, "is_grease_pencil") and mat.is_grease_pencil)]
            
            # Add New Material button at the top of the materials list
            new_mat_row = object_box.row(align=True)
            new_mat_row.scale_y = 1.25  # Make button slightly larger for emphasis
            new_mat_row.operator("material.create_new", icon='ADD', text="New Material")
            
            # Import MaterialList module to use our enhanced draw_materials function
            material_list_module = sys.modules.get(f"{__package__}.MaterialList")
            if material_list_module and hasattr(material_list_module, "draw_materials"):
                material_list_module.draw_materials(
                    object_box, 
                    object_materials, 
                    props.search_term, 
                    props.hide_linked_materials, 
                    True,  # with_actions
                    context.active_object  # Pass the active object
                )
        
        # Grease Pencil Materials collapsible section
        gp_box = layout.box()
        gp_header = gp_box.row(align=True)
        gp_header.alignment = 'LEFT'
        
        icon = 'TRIA_DOWN' if props.grease_pencil_materials_expanded else 'TRIA_RIGHT'
        gp_header.prop(props, "grease_pencil_materials_expanded", text="Grease Pencil Materials", 
                    icon=icon, emboss=False)
        
        # Show grease pencil materials if expanded
        if props.grease_pencil_materials_expanded:
            # Filter just grease pencil materials
            gp_materials = [m for m in bpy.data.materials 
                        if hasattr(m, "is_grease_pencil") and m.is_grease_pencil]
                        
            # Import MaterialList module to use our enhanced draw_materials function
            material_list_module = sys.modules.get(f"{__package__}.MaterialList")
            if material_list_module and hasattr(material_list_module, "draw_materials"):
                material_list_module.draw_materials(
                    gp_box, 
                    gp_materials, 
                    props.search_term, 
                    props.hide_linked_materials, 
                    True,  # with_actions
                    context.active_object  # Pass the active object
                )
                
# QuickAsset Library sub-panel for 3D View
class QP_PT_quickasset_panel(Panel):
    """Quick Asset Library Panel in QPTools"""
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'QPTools'
    bl_label = "Quick Asset Library"
    bl_parent_id = "QP_PT_main_panel"
    bl_idname = "QP_PT_quickasset_panel"
    
    @classmethod
    def poll(cls, context):
        # Only show if QuickAsset module is enabled
        quick_asset_module = sys.modules.get(f"{__package__}.quick_asset_library")
        return (module_enabled and 
                quick_asset_module and 
                hasattr(quick_asset_module, "module_enabled") and 
                quick_asset_module.module_enabled and
                hasattr(context.scene, "asset_library_settings"))
    
    def draw(self, context):
        layout = self.layout
        settings = context.scene.asset_library_settings

        # Status indicator for background process
        if is_background_process_running():
            status_file = get_temp_file_path()
            try:
                with open(status_file, 'r') as f:
                    status = json.load(f)
                    status_box = layout.box()
                    status_box.label(text=f"Status: {status.get('status', 'Processing...')}", icon='SORTTIME')
            except (OSError, json.JSONDecodeError):
                pass  # Could not read status file

        # Library Path Box
        path_box = layout.box()
        path_box.label(text="Library Location:", icon='FILE_FOLDER')
        path_box.prop(settings, "library_path", text="")

        if not settings.library_path:
            return

        # Target File Box
        file_box = layout.box()
        file_box.label(text="Target File:", icon='FILE_BLEND')
        file_box.prop(settings, "create_new_library")
        
        if settings.create_new_library:
            file_box.prop(settings, "new_file_name", text="File Name")
        else:
            file_box.prop(settings, "existing_file")
            
            # Show conflicts only if a valid file is selected
            if settings.existing_file != 'NONE':
                filepath = os.path.join(settings.library_path, settings.existing_file)
                if context.selected_objects:
                    conflicts = settings.scan_conflicts(context, filepath, context.selected_objects, "objects")
                    
                    if conflicts:
                        self._draw_conflicts(layout, conflicts, settings)

        # Check if we can proceed (either creating new file or valid existing file selected)
        can_proceed = settings.create_new_library or settings.existing_file != 'NONE'

        # Asset Metadata Box
        metadata_box = layout.box()
        metadata_box.label(text="Asset Metadata:", icon='PROPERTIES')
        metadata_box.active = can_proceed
        
        # Catalog selection
        metadata_box.label(text="Catalog:")
        metadata_box.prop(settings, "selected_catalog", text="")
        
        # Tags
        metadata_box.label(text="Tags (comma-separated):")
        metadata_box.prop(settings, "tags", text="")

        # Rename Options Box
        rename_box = layout.box()
        rename_box.label(text="Naming Options:", icon='SORTALPHA')
        rename_box.active = can_proceed
        rename_box.prop(settings, "rename_viewport_assets")
        if settings.rename_viewport_assets:
            rename_box.prop(settings, "asset_base_name")
        
        # Selection Info Box
        selection_box = layout.box()
        selection_box.label(text="What will be saved:", icon='EXPORT')
        selection_box.active = can_proceed
        
        # Get selected objects
        selected_objects = []
        if context.selected_objects:
            selected_objects = context.selected_objects
            selection_box.label(text=f"{len(selected_objects)} objects selected")
            for obj in selected_objects:
                if settings.rename_viewport_assets and settings.asset_base_name:
                    index = list(context.selected_objects).index(obj)
                    new_name = settings.asset_base_name
                    if index > 0:
                        new_name += f".{str(index+1).zfill(3)}"
                    selection_box.label(text=f"• {obj.name} → {new_name}", icon='OBJECT_DATA')
                else:
                    selection_box.label(text=f"• {obj.name}", icon='OBJECT_DATA')
        else:
            selection_box.label(text="No objects selected")
        
        # Add to Library Button
        row = layout.row(align=True)
        row.scale_y = 1.5
        row.enabled = can_proceed and not is_background_process_running()
        op = row.operator("asset.add_to_library", 
                         text="Add to Library",
                         icon='ASSET_MANAGER')
        op.asset_type = 'OBJECTS'
    
    def _draw_conflicts(self, layout, conflicts, settings):
        """Helper method to draw conflict warnings consistently"""
        conflict_box = layout.box()
        conflict_box.alert = True
        
        row = conflict_box.row()
        row.label(text="", icon='ERROR')
        row.label(text="Name Conflicts Detected!")
        
        for name in conflicts:
            row = conflict_box.row()
            row.label(text="", icon='DUPLICATE')
            row.label(text=name)
        
        conflict_box.separator()
        conflict_box.label(text="If asset name exists:")
        conflict_box.prop(settings, "conflict_action", text="")

# Main panel for Node Editor
class QP_PT_node_main_panel(Panel):
    """Main QPTools Panel in Node Editor"""
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'QPTools'
    bl_label = "QPTools"
    bl_idname = "QP_PT_node_main_panel"
    
    @classmethod
    def poll(cls, context):
        # Show panel if QuickAsset module is enabled
        quick_asset_module = sys.modules.get(f"{__package__}.quick_asset_library")
        return (module_enabled and 
                quick_asset_module and 
                hasattr(quick_asset_module, "module_enabled") and 
                quick_asset_module.module_enabled)
    
    def draw(self, context):
        layout = self.layout
        layout.label(text="Activated Modules")

# Shader Editor Asset Library panel
class QP_PT_shader_asset_panel(Panel):
    """Quick Asset Library Panel for Shader Editor"""
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'QPTools'
    bl_label = "Quick Asset Library"
    bl_parent_id = "QP_PT_node_main_panel"
    bl_idname = "QP_PT_shader_asset_panel"
    
    @classmethod
    def poll(cls, context):
        quick_asset_module = sys.modules.get(f"{__package__}.quick_asset_library")
        return (module_enabled and 
                quick_asset_module and 
                hasattr(quick_asset_module, "module_enabled") and 
                quick_asset_module.module_enabled and
                hasattr(context.scene, "asset_library_settings") and
                context.space_data.tree_type == 'ShaderNodeTree')
    
    def draw(self, context):
        def get_shader_selection(ctx):
            """Returns (items, data_type, no_selection_message)"""
            space = ctx.space_data
            selected_groups = []
            
            # Get active node tree
            if space.edit_tree:
                tree = None
                if space.tree_type == 'ShaderNodeTree':
                    if ctx.active_object and ctx.active_object.active_material:
                        tree = ctx.active_object.active_material.node_tree
                
                if tree:
                    # Check for selected node groups
                    for node in tree.nodes:
                        if node.select and node.type == 'GROUP' and node.node_tree:
                            selected_groups.append(node.node_tree)
                    
                    if selected_groups:
                        return (selected_groups, "node_groups", "No node groups selected")
                    
                    # Fallback to active material
                    if ctx.active_object and ctx.active_object.active_material:
                        mat = ctx.active_object.active_material
                        return ([mat], "materials", "No material selected")
            
            return ([], "materials", "No material or node groups selected")
        
        draw_node_asset_panel(self, context, "shader node", 'MATERIAL', get_shader_selection, 'NODETREE')

# Geometry Nodes Asset Library panel
class QP_PT_geometry_asset_panel(Panel):
    """Quick Asset Library Panel for Geometry Nodes"""
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'QPTools'
    bl_label = "Quick Asset Library"
    bl_parent_id = "QP_PT_node_main_panel"
    bl_idname = "QP_PT_geometry_asset_panel"
    
    @classmethod
    def poll(cls, context):
        quick_asset_module = sys.modules.get(f"{__package__}.quick_asset_library")
        
        basic_check = (module_enabled and 
                quick_asset_module and 
                hasattr(quick_asset_module, "module_enabled") and 
                quick_asset_module.module_enabled and
                hasattr(context.scene, "asset_library_settings"))
        
        if not basic_check:
            return False
            
        if hasattr(context.space_data, 'tree_type'):
            return context.space_data.tree_type == 'GeometryNodeTree'
        
        if context.space_data.type == 'NODE_EDITOR':
            return True
            
        return False
    
    def draw(self, context):
        def get_geonode_selection(ctx):
            """Returns (items, data_type, no_selection_message)"""
            space = ctx.space_data
            selected_groups = []
            tree = space.edit_tree if space.edit_tree else None
            
            if tree:
                # Check for selected node groups
                for node in tree.nodes:
                    if node.select and node.type == 'GROUP' and node.node_tree:
                        selected_groups.append(node.node_tree)
                
                if selected_groups:
                    return (selected_groups, "node_groups", "No node groups selected")
                
                # Fallback to active tree
                return ([tree], "node_groups", "No geometry node tree active")
            
            return ([], "node_groups", "No geometry node tree active")
        
        draw_node_asset_panel(self, context, "geometry node", 'GEONODES', get_geonode_selection, 'NODETREE')

# Compositor Asset Library panel
class QP_PT_compositor_asset_panel(Panel):
    """Quick Asset Library Panel for Compositor"""
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'QPTools'
    bl_label = "Quick Asset Library"
    bl_parent_id = "QP_PT_node_main_panel"
    bl_idname = "QP_PT_compositor_asset_panel"
    
    @classmethod
    def poll(cls, context):
        quick_asset_module = sys.modules.get(f"{__package__}.quick_asset_library")
        
        basic_check = (module_enabled and 
                quick_asset_module and 
                hasattr(quick_asset_module, "module_enabled") and 
                quick_asset_module.module_enabled and
                hasattr(context.scene, "asset_library_settings"))
        
        if not basic_check:
            return False
        
        if hasattr(context.space_data, 'tree_type'):
            return context.space_data.tree_type == 'CompositorNodeTree'
        
        return False
    
    def draw(self, context):
        def get_compositor_selection(ctx):
            """Returns (items, data_type, no_selection_message)"""
            space = ctx.space_data
            selected_groups = []
            tree = space.edit_tree if space.edit_tree else None
            
            if tree:
                # Check for selected node groups
                for node in tree.nodes:
                    if node.select and node.type == 'GROUP' and node.node_tree:
                        selected_groups.append(node.node_tree)
                
                if selected_groups:
                    return (selected_groups, "node_groups", "No node groups selected")

                # Fallback to active tree
                return ([tree], "node_groups", "No compositor node tree active")
            
            return ([], "node_groups", "No compositor node groups selected")
        
        draw_node_asset_panel(self, context, "compositor node", 'GEONODES', get_compositor_selection, 'NODETREE')

# CleanUp sub-panel
class QP_PT_cleanup_panel(Panel):
    """CleanUp Panel in QPTools"""
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'QPTools'
    bl_label = "CleanUp"
    bl_parent_id = "QP_PT_main_panel"
    bl_idname = "QP_PT_cleanup_panel"
    
    @classmethod
    def poll(cls, context):
        # Only show if CleanUp module is enabled
        cleanup_module = sys.modules.get(f"{__package__}.CleanUp")
        return (module_enabled and 
                cleanup_module and 
                hasattr(cleanup_module, "module_enabled") and 
                cleanup_module.module_enabled)
    
    def draw(self, context):
        layout = self.layout
        
        # Materials cleanup section
        materials_box = layout.box()
        materials_box.label(text="Materials", icon='MATERIAL')
        
        # Check if there are materials with duplicates
        materials = bpy.data.materials
        material_groups = {}
        for mat in materials:
            # Use the same get_base_name function logic
            parts = mat.name.split('.')
            base_name = mat.name
            for i in range(len(parts) - 1, 0, -1):
                if parts[i].isdigit():
                    base_name = '.'.join(parts[:i])
                    break
            
            if base_name not in material_groups:
                material_groups[base_name] = []
            material_groups[base_name].append(mat)
        
        # Count duplicates
        duplicate_materials = sum(len(mats) - 1 for mats in material_groups.values() if len(mats) > 1)
        
        if duplicate_materials > 0:
            materials_box.label(text=f"Found {duplicate_materials} duplicate materials")
            row = materials_box.row(align=True)
            row.scale_y = 1.5
            row.operator("cleanup.clean_materials", text="Clean Duplicate Materials", icon='BRUSH_DATA')
        else:
            materials_box.label(text="No duplicate materials found", icon='CHECKMARK')
        
        # Node groups cleanup section
        nodegroups_box = layout.box()
        nodegroups_box.label(text="Node Groups", icon='NODETREE')
        
        # Check if there are node groups with duplicates
        node_groups = bpy.data.node_groups
        ng_groups = {}
        for ng in node_groups:
            # Use the same get_base_name function logic
            parts = ng.name.split('.')
            base_name = ng.name
            for i in range(len(parts) - 1, 0, -1):
                if parts[i].isdigit():
                    base_name = '.'.join(parts[:i])
                    break
            
            if base_name not in ng_groups:
                ng_groups[base_name] = []
            ng_groups[base_name].append(ng)
        
        # Count duplicates
        duplicate_node_groups = sum(len(ngs) - 1 for ngs in ng_groups.values() if len(ngs) > 1)
        
        if duplicate_node_groups > 0:
            nodegroups_box.label(text=f"Found {duplicate_node_groups} duplicate node groups")
            row = nodegroups_box.row(align=True)
            row.scale_y = 1.5
            row.operator("cleanup.clean_node_groups", text="Clean Duplicate Node Groups", icon='BRUSH_DATA')
        else:
            nodegroups_box.label(text="No duplicate node groups found", icon='CHECKMARK')
        
        # ADD THIS MISSING SECTION FOR IMAGES:
        # Images cleanup section
        images_box = layout.box()
        images_box.label(text="Images", icon='IMAGE_DATA')
        
        # Check if there are images with duplicates
        images = bpy.data.images
        image_groups = {}
        for img in images:
            # Use the same get_base_name function logic
            parts = img.name.split('.')
            base_name = img.name
            for i in range(len(parts) - 1, 0, -1):
                if parts[i].isdigit():
                    base_name = '.'.join(parts[:i])
                    break
            
            if base_name not in image_groups:
                image_groups[base_name] = []
            image_groups[base_name].append(img)
        
        # Count duplicates
        duplicate_images = sum(len(imgs) - 1 for imgs in image_groups.values() if len(imgs) > 1)
        
        if duplicate_images > 0:
            images_box.label(text=f"Found {duplicate_images} duplicate images")
            row = images_box.row(align=True)
            row.scale_y = 1.5
            row.operator("cleanup.clean_images", text="Clean Duplicate Images", icon='BRUSH_DATA')
        else:
            images_box.label(text="No duplicate images found", icon='CHECKMARK')

def register():
    """Register the QPTools panel module"""
    if not ModuleManager.register_module(sys.modules[__name__]):
        return
    
    # Register classes
    ModuleManager.safe_register_class(QP_PT_main_panel)
    ModuleManager.safe_register_class(QP_PT_materials_panel)
    ModuleManager.safe_register_class(QP_PT_cleanup_panel)
    ModuleManager.safe_register_class(QP_PT_quickasset_panel)
    ModuleManager.safe_register_class(QP_PT_node_main_panel)
    ModuleManager.safe_register_class(QP_PT_shader_asset_panel)
    ModuleManager.safe_register_class(QP_PT_geometry_asset_panel)
    ModuleManager.safe_register_class(QP_PT_compositor_asset_panel)
    
    # Add a handler to redraw areas when switching editors
    if hasattr(bpy.app, 'handlers'):
        def force_redraw_on_switch(*args):
            for window in bpy.context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == 'NODE_EDITOR':
                        area.tag_redraw()
            return None  # Remove timer after one execution
            
        # Register a one-time timer for UI refresh
        bpy.app.timers.register(force_redraw_on_switch, first_interval=0.5)
    

def unregister():
    """Unregister the QPTools panel module"""
    if not ModuleManager.unregister_module(sys.modules[__name__]):
        return
    
    # Unregister classes in reverse order
    ModuleManager.safe_unregister_class(QP_PT_compositor_asset_panel)
    ModuleManager.safe_unregister_class(QP_PT_geometry_asset_panel)
    ModuleManager.safe_unregister_class(QP_PT_shader_asset_panel)
    ModuleManager.safe_unregister_class(QP_PT_node_main_panel)
    ModuleManager.safe_unregister_class(QP_PT_quickasset_panel)
    ModuleManager.safe_unregister_class(QP_PT_cleanup_panel)
    ModuleManager.safe_unregister_class(QP_PT_materials_panel)
    ModuleManager.safe_unregister_class(QP_PT_main_panel)
    

if __name__ == "__main__":
    register()