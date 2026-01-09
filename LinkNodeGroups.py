import bpy
import sys
import re
from bpy.types import Operator

from .module_helper import ModuleManager

# Module state variables
module_enabled = True
_is_registered = False

class NodeGroupLinker(Operator):
    """Link node groups to nodes based on matching socket names"""
    bl_idname = "node.node_group_linker"  
    bl_label = "Link Node Groups"

    @classmethod
    def poll(cls, context):
        return module_enabled and context.area.type == 'NODE_EDITOR' and context.selected_nodes

    def execute(self, context):
        nodes = context.selected_nodes
        active_node = context.active_node

        if not active_node:
            self.report({'ERROR'}, "Please select a node as the active node.")
            return {'CANCELLED'}

        # Remove the active node from the list of nodes to link
        other_nodes = [node for node in nodes if node != active_node]

        # Define the suffix map for image texture matching
        self.suffix_map = {
            "Color": ["albedo", "color", "col", "colour", "base color", "diffuse", "diff", "dif"],
            "AO": ["ao", "ambientocclusion"],
            "Metallic": ["metallic", "metal", "met"],
            "Roughness": ["roughness", "rough"],
            "Height": ["displacement", "height", "disp"],
            "Normal": ["normal", "nor", "norm"],
            "Alpha": ["opacity", "alpha"],
            "Curvature": ["curvature", "curv"],
        }

        links_made = False

        for node in other_nodes:
            if node.type == 'TEX_IMAGE':
                links_made |= self.link_image_texture(context, node, active_node)
            else:
                links_made |= self.link_nodes(context, active_node, [node])

        if not links_made:
            self.report({'INFO'}, "No matching or available sockets found for linking.")
        else:
            self.report({'INFO'}, "Nodes linked successfully.")

        return {'FINISHED'}

    def extract_tokens(self, name):
        """Extract meaningful words from a name, removing separators and extensions"""
        # Remove file extension
        name = name.rsplit('.', 1)[0]
        # Split by common separators and filter out very short/numeric tokens
        tokens = re.split(r'[_\-\s.]+', name.lower())
        # Filter out short tokens (likely IDs) and purely numeric
        return [t for t in tokens if len(t) > 2 and not t.isdigit()]

    def find_best_socket_match(self, output_name, active_node):
        """Find the best matching input socket with strict matching rules"""
        # Common alternative mappings for PBR workflows
        name_alternatives = {
            "color": ["base color", "basecolor", "diffuse"],
            "base color": ["color", "basecolor"],
            "basecolor": ["color", "base color"],
            "height": ["displacement"],
            "displacement": ["height"],
        }
        
        output_tokens = set(self.extract_tokens(output_name))
        output_normalized = output_name.lower().replace('_', '').replace(' ', '').replace('-', '')
        
        # Get alternative names to check
        search_names = [output_name.lower()]
        if output_normalized in name_alternatives:
            search_names.extend(name_alternatives[output_normalized])
        
        best_match = None
        best_score = 0
        
        for input_socket in active_node.inputs:
            if input_socket.is_linked:
                continue
                
            input_tokens = set(self.extract_tokens(input_socket.name))
            input_normalized = input_socket.name.lower().replace('_', '').replace(' ', '').replace('-', '')
            
            score = 0
            
            # Priority 1: Exact normalized match or in alternatives
            if input_normalized in [n.replace(' ', '').replace('_', '').replace('-', '') for n in search_names]:
                score = 1000
            
            # Priority 2: Input name tokens are ALL contained in output tokens
            elif input_tokens and input_tokens.issubset(output_tokens):
                score = 100 + (10 - len(input_tokens)) + len(input_tokens) * 5
            
            # Priority 3: Partial token overlap
            else:
                overlap = output_tokens.intersection(input_tokens)
                if overlap:
                    extra_tokens = len(input_tokens - overlap)
                    score = len(overlap) * 10 - extra_tokens * 20
                    if score <= 0:
                        continue
            
            if score > best_score:
                best_score = score
                best_match = input_socket
        
        return best_match

    def link_image_texture(self, context, image_node, active_node):
        if not image_node.image:
            return False
        
        image_name = image_node.image.name
        
        # Try suffix matching first (for common PBR maps)
        output_name = self.find_matching_suffix(image_name.lower())
        
        if output_name:
            color_output = image_node.outputs.get('Color')
            if color_output:
                return self.link_output_to_input(context, color_output, active_node, output_name)
        
        # Fallback: use the image name directly for token-based matching
        # This catches textures like "Curvature" that aren't in suffix_map
        color_output = image_node.outputs.get('Color')
        if color_output:
            return self.link_output_to_input(context, color_output, active_node, image_name)

        return False

    def find_matching_suffix(self, name):
        for output_name, suffixes in self.suffix_map.items():
            if any(suffix.lower() in name for suffix in suffixes):
                return output_name
        return None

    def link_nodes(self, context, active_node, nodes):
        links_made = False
        for node in nodes:
            for output in node.outputs:
                links_made |= self.link_output_to_input(context, output, active_node, output.name)
        return links_made

    def link_output_to_input(self, context, output, active_node, output_name):
        edit_tree = context.space_data.edit_tree
        is_bsdf_node = active_node.bl_idname.lower().startswith("shadernodebsdf")

        # Skip Alpha to BSDF shader connections
        if output_name == "Alpha" and is_bsdf_node:
            print(f"Skipping Alpha to BSDF shader connection for {active_node.name}")
            return False

        # Try to find best matching socket
        matched_input = self.find_best_socket_match(output_name, active_node)
        
        if matched_input:
            # Handle Normal map special case
            if "normal" in output_name.lower() and is_bsdf_node:
                normal_map_node = edit_tree.nodes.new('ShaderNodeNormalMap')
                normal_map_node.location = ((output.node.location.x + active_node.location.x) / 2,
                                            (output.node.location.y + active_node.location.y) / 2)
                edit_tree.links.new(output, normal_map_node.inputs['Color'])
                edit_tree.links.new(normal_map_node.outputs['Normal'], matched_input)
            else:
                edit_tree.links.new(output, matched_input)
            return True

        return False

def register():
    if not ModuleManager.register_module(sys.modules[__name__]):
        return
        
    ModuleManager.safe_register_class(NodeGroupLinker)

def unregister():
    if not ModuleManager.unregister_module(sys.modules[__name__]):
        return
        
    ModuleManager.safe_unregister_class(NodeGroupLinker)

if __name__ == "__main__":
    register()