"""
QP Image Texture Auto-Updater with Recursive Node Group Support
Automatically updates internal Image Texture nodes in custom node groups
that follow the naming pattern for image texture wrappers, including nested groups.
"""

import bpy
from bpy.app.handlers import persistent


# ============================================================================
# Property Group to store metadata on node groups
# ============================================================================

class QP_NodeInfo(bpy.types.PropertyGroup):
    """Property group to store node metadata for image texture tracking"""
    is_tracked: bpy.props.BoolProperty(
        name="Is Tracked",
        description="Marks this node as tracked by the image updater",
        default=False
    )
    current_image: bpy.props.PointerProperty(
        type=bpy.types.Image,
        name="Current Image",
        description="Last known image connected to this node"
    )


# ============================================================================
# Main Updater Class
# ============================================================================

class QP_ImageTextureUpdater:
    """Handler for updating Image Texture nodes inside custom image node groups"""
    
    # Node group name patterns to watch (case-insensitive)
    NODE_PATTERNS = ["_image texture", "_image"]
    
    @staticmethod
    def should_print():
        """Check if console output is enabled in preferences"""
        try:
            prefs = bpy.context.preferences.addons[__package__].preferences
            return getattr(prefs, "image_updater_console_output", False)
        except (KeyError, AttributeError):
            return False  # Preferences not available
    
    @classmethod
    def log(cls, message):
        """Print message if console output is enabled"""
        if cls.should_print():
            print(f"[QP Image Updater] {message}")
    
    @classmethod
    def get_connected_image(cls, node, socket_name="Image", parent_chain=None):
        """
        Get the image connected to or set on an input socket.
        Resolves Group Input connections by walking up the full parent chain.

        Args:
            node: The node to check
            socket_name: Name of the input socket
            parent_chain: List of ancestor GROUP nodes (outermost first) containing this node

        Returns:
            Image datablock or None
        """
        if socket_name not in node.inputs:
            return None

        socket = node.inputs[socket_name]

        # Check if socket is linked
        if socket.is_linked and socket.links:
            linked_node = socket.links[0].from_node
            from_socket = socket.links[0].from_socket

            # If it's an Image Texture node, get its image
            if linked_node.type == 'TEX_IMAGE':
                return linked_node.image

            # If connected to Group Input, trace back up the parent chain
            if linked_node.type == 'GROUP_INPUT':
                if parent_chain:
                    immediate_parent = parent_chain[-1]
                    if from_socket.name in immediate_parent.inputs:
                        return cls.get_connected_image(immediate_parent, from_socket.name, parent_chain[:-1])
                return None

            # Handle if it's another node group that outputs an image
            if linked_node.type == 'GROUP' and linked_node.outputs:
                return cls.get_connected_image(linked_node, from_socket.name, None)
        else:
            # Socket is not linked - check for direct image assignment
            try:
                if hasattr(socket, 'default_value'):
                    default_val = socket.default_value
                    # Check if it's an Image datablock
                    if isinstance(default_val, bpy.types.Image):
                        return default_val
            except (AttributeError, TypeError):
                pass

        return None
    
    @classmethod
    def make_node_tree_unique(cls, node):
        """
        Make a node group's tree unique if it has multiple users.
        Prevents affecting other instances of the same node group.
        """
        if node.node_tree and node.node_tree.users > 1:
            # Create a copy of the node tree
            original_tree = node.node_tree
            new_tree = original_tree.copy()
            node.node_tree = new_tree
            return True
        return False
    
    @classmethod
    def ensure_chain_unique(cls, material, parent_chain, trackable_node):
        """
        Walk the parent chain outermost-first, making each GROUP's node tree unique
        if it has multiple users. Refreshes node references via name lookup after
        each copy, so subsequent lookups are always in the current (fresh) tree.

        Returns (fresh_parent_chain, fresh_trackable_node), or (None, None) on failure.
        """
        current_tree = material.node_tree
        fresh_chain = []

        for group_node in parent_chain:
            fresh_node = current_tree.nodes.get(group_node.name)
            if fresh_node is None:
                return None, None

            if fresh_node.node_tree and fresh_node.node_tree.users > 1:
                new_tree = fresh_node.node_tree.copy()
                fresh_node.node_tree = new_tree
                cls.log(f"Made parent group unique: {fresh_node.name}")

            fresh_chain.append(fresh_node)
            current_tree = fresh_node.node_tree

        fresh_trackable = current_tree.nodes.get(trackable_node.name)
        return fresh_chain, fresh_trackable

    @classmethod
    def update_internal_image_texture(cls, node_group, target_image, depth=0, visited=None):
        """
        Recursively update all Image Texture nodes inside the node group and nested groups.
        
        Args:
            node_group: The node group to process
            target_image: The image to set on texture nodes
            depth: Current recursion depth (for logging)
            visited: Set of visited node trees to prevent infinite loops
        """
        if not node_group.node_tree:
            return False
        
        # Initialize visited set on first call
        if visited is None:
            visited = set()
        
        # Prevent infinite loops from circular references
        if id(node_group.node_tree) in visited:
            return False
        
        visited.add(id(node_group.node_tree))
        updated = False
        indent = "  " * (depth + 1)
        
        for node in node_group.node_tree.nodes:
            # Update direct Image Texture nodes
            if node.type == 'TEX_IMAGE':
                if node.image != target_image:
                    node.image = target_image
                    updated = True
                    cls.log(f"{indent}└─ Updated Image Texture: {target_image.name if target_image else 'None'}")
            
            # Recursively process nested node groups
            elif node.type == 'GROUP' and node.node_tree:
                cls.log(f"{indent}├─ Entering nested group: {node.node_tree.name}")
                nested_updated = cls.update_internal_image_texture(
                    node, target_image, depth + 1, visited
                )
                if nested_updated:
                    updated = True
        
        return updated
    
    @classmethod
    def initialize_node_metadata(cls, node, parent_chain=None):
        """Initialize metadata for a tracked node"""
        if not hasattr(node, 'qp_node_info'):
            return False

        node.qp_node_info.is_tracked = True
        current_image = cls.get_connected_image(node, "Image", parent_chain)
        node.qp_node_info.current_image = current_image
        return True
    
    @classmethod
    def is_image_texture_node(cls, node):
        """Check if a node is a custom image texture node group that should be tracked"""
        if node.type != 'GROUP' or not node.node_tree:
            return False
        
        # Check node tree name against patterns
        node_tree_name = node.node_tree.name.lower()
        return any(pattern in node_tree_name for pattern in cls.NODE_PATTERNS)
    
    @classmethod
    def find_trackable_nodes_recursive(cls, node_tree, parent_chain=None, parent_path="", visited=None):
        """
        Recursively find all trackable image texture nodes in a node tree and nested groups.

        Args:
            node_tree: The node tree to search
            parent_chain: List of ancestor GROUP nodes (outermost first)
            parent_path: String representing the path to this node tree
            visited: Set of visited node trees to prevent infinite loops

        Returns:
            List of tuples: (node, parent_chain, path_string)
        """
        if not node_tree:
            return []

        if visited is None:
            visited = set()

        if parent_chain is None:
            parent_chain = []

        # Prevent infinite loops
        if id(node_tree) in visited:
            return []

        visited.add(id(node_tree))
        found_nodes = []

        for node in node_tree.nodes:
            current_path = f"{parent_path} > {node.name}" if parent_path else node.name

            # Check if this is a trackable image texture node
            if cls.is_image_texture_node(node):
                found_nodes.append((node, parent_chain, current_path))
                cls.log(f"Found trackable node: {current_path}")

            # Recursively search nested node groups, extending the parent chain
            if node.type == 'GROUP' and node.node_tree:
                nested_nodes = cls.find_trackable_nodes_recursive(
                    node.node_tree, parent_chain + [node], current_path, visited
                )
                found_nodes.extend(nested_nodes)

        return found_nodes
    
    @classmethod
    def process_material_nodes(cls, material):
        """Process all tracked image texture nodes in a material, including nested ones"""
        if not material.use_nodes or not material.node_tree:
            return
        
        # Find all trackable nodes recursively
        trackable_nodes = cls.find_trackable_nodes_recursive(material.node_tree)
        
        if not trackable_nodes:
            return
        
        cls.log(f"Processing material: {material.name} ({len(trackable_nodes)} trackable nodes)")
        
        # Process each found node
        for node, parent_chain, path in trackable_nodes:
            # Initialize metadata if not already done
            if hasattr(node, 'qp_node_info') and not node.qp_node_info.is_tracked:
                cls.initialize_node_metadata(node, parent_chain)

            # Check for updates
            cls.check_and_update_node(material, node, parent_chain, path)
    
    @classmethod
    def check_and_update_node(cls, material, node, parent_chain, node_path=""):
        """Check if a node needs updating and update it if necessary"""
        if not hasattr(node, 'qp_node_info'):
            return

        current_image = cls.get_connected_image(node, "Image", parent_chain)
        
        # Get last known state from metadata
        last_image = node.qp_node_info.current_image
        
        # Check if image changed
        if current_image != last_image:
            path_info = f" at {node_path}" if node_path else ""
            cls.log(f"Image changed on {node.name}{path_info} in {material.name}")
            cls.log(f"  Old: {last_image.name if last_image else 'None'}")
            cls.log(f"  New: {current_image.name if current_image else 'None'}")
            
            # Ensure all parent groups are unique first (outermost to innermost),
            # then get fresh node references after any copies
            if parent_chain:
                fresh_chain, fresh_node = cls.ensure_chain_unique(material, parent_chain, node)
                if fresh_node is not None:
                    node = fresh_node

            # Make trackable node's own tree unique
            was_made_unique = cls.make_node_tree_unique(node)

            if was_made_unique:
                cls.log(f"  └─ Made node tree unique (was shared)")

            # Update internal Image Texture nodes recursively
            cls.update_internal_image_texture(node, current_image)

            # Store new state on the (possibly refreshed) node
            node.qp_node_info.current_image = current_image


# ============================================================================
# Handlers
# ============================================================================

@persistent
def update_on_depsgraph(scene, depsgraph):
    """Handler that runs on depsgraph updates"""
    try:
        # Check if we're in node editing context
        for area in bpy.context.screen.areas:
            if area.type == 'NODE_EDITOR':
                space = area.spaces.active
                if space.tree_type == 'ShaderNodeTree' and space.node_tree:
                    # Process only the active material's node tree
                    for material in bpy.data.materials:
                        if material.node_tree == space.node_tree:
                            QP_ImageTextureUpdater.process_material_nodes(material)
                            break
                break
        else:
            # If no node editor is active, process all materials
            for material in bpy.data.materials:
                QP_ImageTextureUpdater.process_material_nodes(material)
    except Exception as e:
        # Only show errors if console output is enabled
        if QP_ImageTextureUpdater.should_print():
            print(f"QP Image Updater Error: {e}")
            import traceback
            traceback.print_exc()


@persistent
def update_on_load(dummy):
    """Handler for when file is loaded"""
    QP_ImageTextureUpdater.log("=" * 60)
    QP_ImageTextureUpdater.log("Processing nodes after load (with nested Group Input support)")
    QP_ImageTextureUpdater.log("=" * 60)
    
    for material in bpy.data.materials:
        QP_ImageTextureUpdater.process_material_nodes(material)


@persistent
def update_on_save_pre(dummy):
    """Handler before saving - optional cleanup"""
    pass


# ============================================================================
# Operator (Optional - for manual updates)
# ============================================================================

class QP_IMAGE_UPDATER_OT_manual_update(bpy.types.Operator):
    """Manually trigger update of all tracked image texture nodes (including nested)"""
    bl_idname = "node.qp_image_updater_manual"
    bl_label = "Update Image Textures"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        total_count = 0
        for material in bpy.data.materials:
            if material.use_nodes and material.node_tree:
                trackable_nodes = QP_ImageTextureUpdater.find_trackable_nodes_recursive(
                    material.node_tree
                )
                count = len(trackable_nodes)
                total_count += count
                
                if count > 0:
                    for node, parent_chain, path in trackable_nodes:
                        QP_ImageTextureUpdater.check_and_update_node(material, node, parent_chain, path)
        
        self.report({'INFO'}, f"Processed {total_count} image texture node(s) including nested groups")
        return {'FINISHED'}


# ============================================================================
# Registration
# ============================================================================

classes = (
    QP_NodeInfo,
    QP_IMAGE_UPDATER_OT_manual_update,
)


def register():
    """Register the image updater components"""
    # Register classes
    for cls in classes:
        bpy.utils.register_class(cls)
    
    # Attach property to ShaderNodeGroup
    if not hasattr(bpy.types.ShaderNodeGroup, 'qp_node_info'):
        bpy.types.ShaderNodeGroup.qp_node_info = bpy.props.PointerProperty(
            type=QP_NodeInfo
        )
    
    # Register handlers
    handlers = [
        (bpy.app.handlers.depsgraph_update_post, update_on_depsgraph),
        (bpy.app.handlers.load_post, update_on_load),
        (bpy.app.handlers.save_pre, update_on_save_pre),
    ]
    
    for handler_list, handler_func in handlers:
        if handler_func not in handler_list:
            handler_list.append(handler_func)
    
    print("=" * 60)
    print("QP Image Texture Auto-Updater: ENABLED")
    print("  - Recursive nested node group support active")
    print("  - Group Input connection resolution enabled")
    print("=" * 60)
    
    # Initial processing with a small delay
    bpy.app.timers.register(lambda: update_on_load(None) or None, first_interval=0.1)


def unregister():
    """Unregister the image updater components"""
    # Remove handlers
    handlers = [
        (bpy.app.handlers.depsgraph_update_post, update_on_depsgraph),
        (bpy.app.handlers.load_post, update_on_load),
        (bpy.app.handlers.save_pre, update_on_save_pre),
    ]
    
    for handler_list, handler_func in handlers:
        if handler_func in handler_list:
            handler_list.remove(handler_func)
    
    # Unregister timer if still active
    if bpy.app.timers.is_registered(update_on_load):
        bpy.app.timers.unregister(update_on_load)
    
    # Unregister classes
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    
    # Note: We deliberately do NOT remove qp_node_info property
    # to preserve data in .blend files
    
    print("=" * 60)
    print("QP Image Texture Auto-Updater: DISABLED")
    print("=" * 60)


if __name__ == "__main__":
    register()