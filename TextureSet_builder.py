import bpy
import sys
import bpy_extras
import os
import re
from mathutils import Vector

from .module_helper import ModuleManager

# Module state variables
module_enabled = True
_is_registered = False

# Get the addon directory and construct the node group path once during registration
addon_directory = os.path.dirname(__file__)
node_group_path = os.path.join(addon_directory, "assets", "TextureBlendAssist_Nodes.blend")

class PackImageTexturesOperator(bpy.types.Operator, bpy_extras.io_utils.ImportHelper):
    bl_idname = "node.pack_image_textures"
    bl_label = "Pack Image Textures"

    files : bpy.props.CollectionProperty(name='Filepaths', type=bpy.types.PropertyGroup)

    @classmethod
    def poll(cls, context):
        return module_enabled and context.area.type == 'NODE_EDITOR'

    def execute(self, context):
        try:
            filepaths = []
            images = []
            print("Starting Pack Image Textures operator")

            selected_nodes = bpy.context.selected_nodes
            image_texture_nodes = [node for node in selected_nodes if node.type == 'TEX_IMAGE']
            if image_texture_nodes:
                for node in image_texture_nodes:
                    if node.image:
                        # Store the image itself instead of just the filepath
                        images.append(node.image)
                        # Also store filepath for compatibility with existing code
                        filepaths.append(node.image.filepath)
            else:
                # Check for files from file browser
                dirname = os.path.dirname(self.filepath)
                for f in self.files:
                    img_path = os.path.join(dirname, f.name)
                    filepaths.append(img_path)
                    
            # If we have image references directly, prioritize those. Otherwise fall back to filepaths.
            if images:
                pack_image_textures(filepaths=filepaths, images=images)
            else:
                pack_image_textures(filepaths=filepaths)

        except ValueError as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        except Exception as e:
            self.report({'ERROR'}, f"Unexpected error: {e}")
            return {'CANCELLED'}

        return {'FINISHED'}

    def invoke(self, context, event):
        # If no image texture nodes are selected, open the file explorer
        if not any(node for node in context.selected_nodes if node.type == 'TEX_IMAGE'):
            # Open the file browser and set the directory property
            context.window_manager.fileselect_add(self)
            return {'RUNNING_MODAL'}
        else:
            return self.execute(context)

def get_existing_image(filepath):
    """
    Check if an image with the given filepath already exists in the blend file.
    If so, return the existing image. Otherwise, return None.
    """
    if not filepath:
        return None
        
    filename = os.path.basename(filepath)
    for img in bpy.data.images:
        if img.filepath.endswith(filename):
            return img
    return None

def get_image_name(image_or_filepath):
    """Get image name from either an image object or a filepath"""
    if isinstance(image_or_filepath, bpy.types.Image):
        return image_or_filepath.name
    elif isinstance(image_or_filepath, str):
        return os.path.basename(image_or_filepath)
    return ""

def extract_tokens(name):
    """Extract meaningful words from a texture name, removing separators and extensions"""
    # Remove file extension
    name = name.rsplit('.', 1)[0]
    # Split by common separators and filter out very short/numeric tokens
    tokens = re.split(r'[_\-\s.]+', name.lower())
    # Filter tokens: keep short acronyms (2 chars uppercase-like) or longer tokens (>2 chars), exclude numeric
    return [t for t in tokens if (len(t) == 2 or len(t) > 2) and not t.isdigit()]

def find_matching_texture_type(image_identifier, suffix_map):
    """
    Find the best matching texture type using token-based analysis.
    Prioritizes matches at the end of the filename (after last separator).
    Returns (output_name, matched_suffix) or (None, None) if no match found.
    """
    # Remove file extension first for proper matching
    name_without_ext = image_identifier.rsplit('.', 1)[0]
    
    # Extract tokens from the image name/path
    image_tokens = extract_tokens(image_identifier)
    image_normalized = name_without_ext.lower().replace('_', '').replace(' ', '').replace('-', '')
    
    # Get the last token (most likely to be the texture type)
    last_token = image_tokens[-1] if image_tokens else ""
    
    best_match = None
    best_suffix = None
    best_score = 0
    
    for output_name, suffixes in suffix_map.items():
        # Sort suffixes by length (longest first) to match more specific terms first
        sorted_suffixes = sorted(suffixes, key=len, reverse=True)
        
        for suffix in sorted_suffixes:
            suffix_normalized = suffix.replace('_', '').replace(' ', '').replace('-', '')
            suffix_tokens = set(extract_tokens(suffix))
            
            score = 0
            
            # Check if this suffix matches the last token (highest priority)
            # This catches the actual texture type suffix like "_Alpha", "_Normal", etc.
            if suffix_normalized == last_token.replace('_', '').replace(' ', '').replace('-', ''):
                # HIGHEST PRIORITY: exact match with last token
                score = 10000 + len(suffix_normalized)
            
            # Check if suffix appears at the end of the normalized name (without extension)
            elif image_normalized.endswith(suffix_normalized):
                # HIGH PRIORITY: suffix at end of filename
                score = 5000 + len(suffix_normalized)
            
            # Priority 3: Suffix appears somewhere in normalized name (but not at end)
            elif suffix_normalized in image_normalized:
                # LOWER PRIORITY: suffix in middle/start of name (likely part of base name)
                score = 1000 + len(suffix_normalized)
            
            # Priority 4: All suffix tokens present in image tokens
            elif suffix_tokens and suffix_tokens.issubset(set(image_tokens)):
                score = 100 + len(suffix_tokens) * 10
            
            # Priority 5: Partial token overlap
            else:
                overlap = set(image_tokens).intersection(suffix_tokens)
                if overlap:
                    score = len(overlap) * 10
            
            # Keep the best match
            if score > best_score:
                best_score = score
                best_match = output_name
                best_suffix = suffix
    
    return (best_match, best_suffix) if best_match else (None, None)

def pack_image_textures(filepaths=[], images=[]):
    global node_group_path

    # 1. Get Selected Nodes
    selected_nodes = bpy.context.selected_nodes
    material = bpy.context.active_object.active_material
    node_tree = material.node_tree

    # 2. Validate Node Types
    image_texture_nodes = [node for node in selected_nodes if node.type == 'TEX_IMAGE']

    try:
        # 4. Import Node Group
        with bpy.data.libraries.load(node_group_path) as (data_from, data_to):
            data_to.node_groups = ["QP_TextureSet"]
        texture_set_group = data_to.node_groups[0]

        if "QP_TextureSet" not in bpy.data.node_groups:
            raise ImportError("Node group 'QP_TextureSet' not found in the imported file.")

    except ImportError as e:
        print(f"Error importing node group: {e}")
        # You can optionally display an error message to the user here

    # 3. Suffix Matching - keywords ordered by specificity (longest first within each type)
    # This prevents partial matches like "metal" matching before "metallic"
    suffix_map = {
        "Color": ["basecolor", "base color", "albedo", "diffuse", "colour", "color", "diff", "dif", "col"],
        "AO": ["ambientocclusion", "ambient occlusion", "ao"],
        "Metallic": ["metallic", "metal", "met"],
        "Roughness": ["roughness", "rough"],
        "Height": ["displacement", "displace", "height", "disp"],
        "Normal": ["normal", "norm", "nor"],
        "Alpha": ["opacity", "alpha"],
        "Curvature": ["curvature", "curv"],
        # ... (add more suffixes as needed)
    }

    # Color Space Mapping
    color_space_map = {
        "Color": 'sRGB',
        "AO": 'Non-Color',
        "Metallic": 'Non-Color',
        "Roughness": 'Non-Color',
        "Height": 'Non-Color',
        "Normal": 'Non-Color',
        "Alpha": 'Non-Color',
        "Curvature": 'Non-Color',
    }

    texture_info = {}
    base_name = None

    # If no image texture nodes are selected but we have images from filepaths, create nodes
    if not image_texture_nodes:
        # Priority to direct image references
        if images:
            for img in images:
                # Create a new image texture node
                node = node_tree.nodes.new("ShaderNodeTexImage")
                node.image = img
                image_texture_nodes.append(node)
        # Fall back to filepaths if no images
        elif filepaths:
            for filepath in filepaths:
                # Use improved matching to identify texture type
                output_name, _ = find_matching_texture_type(filepath, suffix_map)
                if output_name:
                    node = node_tree.nodes.new("ShaderNodeTexImage")
                    existing_image = get_existing_image(filepath)
                    if existing_image:
                        node.image = existing_image
                    else:
                        node.image = bpy.data.images.load(filepath)
                    image_texture_nodes.append(node)

    # Process all image texture nodes
    for node in image_texture_nodes:
        if not node.image:
            continue
            
        # Check if image is packed or has a filepath
        image = node.image
        is_packed = image.packed_file is not None
        
        # Get either the filepath or image name to detect texture type
        image_identifier = image.name if is_packed else image.filepath
        if not image_identifier:
            image_identifier = image.name  # Always fallback to name if filepath is empty
            
        # Use improved matching to identify texture type
        output_name, matched_suffix = find_matching_texture_type(image_identifier, suffix_map)
        
        if output_name:
            # Store both the node output and the detected texture type
            # Use a unique key that works for both packed and unpacked textures
            key = f"{id(image)}_{image.name}"
            texture_info[key] = (node.outputs[0], output_name, image)
            
            # Derive base name from the image name
            name_base = image.name
            # Remove the matching suffix (case-insensitive) if found
            if matched_suffix:
                name_base = re.sub(f'(?i){re.escape(matched_suffix)}', '', name_base)
            # Remove file extension if present
            name_base = os.path.splitext(name_base)[0]
            
            # Only update base_name if it's not set yet
            if base_name is None:
                base_name = name_base
        else:
            # If no match found, print a message
            print(f"  No matching suffix found for: {image_identifier}")
    
    # Ensure you're operating within the context of the active material's node tree
    if not material or not material.use_nodes:
        raise ValueError("Active object doesn't have a material or doesn't use nodes.")
    
    if not image_texture_nodes:
        raise ValueError("No Image Texture Node found.")
    
    # 5. Place the imported Node Group at Average Location
    if image_texture_nodes:
        # If image textures were selected, use the average location
        avg_location = sum((node.location for node in image_texture_nodes), Vector((0, 0))) / len(image_texture_nodes)
        new_node_location = avg_location
    else:
        # If no image textures were selected, use the cursor location
        for area in bpy.context.screen.areas:
            if area.type == 'NODE_EDITOR':
                new_node_location = area.spaces.active.cursor_location
                break
        else:
            # Fallback to center of view if cursor location can't be determined
            new_node_location = Vector((0, 0))

    # Add the imported node group to the node tree
    new_node = node_tree.nodes.new("ShaderNodeGroup")  
    new_node.node_tree = texture_set_group  
    
    # Set the location of the new node
    new_node.location = new_node_location

    # Center the new node on its position
    new_node.location.x -= new_node.width / 2
    new_node.location.y -= new_node.height / 2

    # Rename the node group if a base name was found
    if base_name:
        new_node.node_tree.name = base_name

    # 6. Replace Paths Inside the Node Group and Set Color Space
    for node in new_node.node_tree.nodes:  
        if node.type == 'TEX_IMAGE':
            for output_name in suffix_map.keys(): 
                if node.name.lower() == output_name.lower():  
                    # Find a matching texture for this output type
                    for key, (_, output_name_info, img) in texture_info.items():
                        if output_name_info == output_name:
                            # Directly assign the image - works for both packed and unpacked
                            node.image = img
                            
                            # Set the color space of the image data
                            if node.image:
                                node.image.colorspace_settings.name = color_space_map.get(output_name, 'sRGB')
                            break
        
    # 7. Reconnect External Links
    for key, (output_link, output_name, _) in texture_info.items():
        if output_name not in new_node.outputs:
            print(f"Warning: Output '{output_name}' not found in node group. Skipping reconnect.")
            continue
    
        for link in output_link.links:
            bpy.context.active_object.active_material.node_tree.links.new(new_node.outputs[output_name], link.to_socket)

            
    # 8. Delete Original Nodes
    for node in image_texture_nodes:
        bpy.context.active_object.active_material.node_tree.nodes.remove(node)

def register():
    if not ModuleManager.register_module(sys.modules[__name__]):
        return
        
    ModuleManager.safe_register_class(PackImageTexturesOperator)

def unregister():
    if not ModuleManager.unregister_module(sys.modules[__name__]):
        return
        
    ModuleManager.safe_unregister_class(PackImageTexturesOperator)

if __name__ == "__main__":
    register()