# pie_menu_builder.py
# Custom Pie Menu Builder for QP_Tools
# Allows users to create unlimited custom pie menus with dynamic shortcuts

import bpy
import sys
import uuid
import json
import rna_keymap_ui
from bpy.types import Menu, Operator
from bpy.props import StringProperty, BoolProperty, IntProperty, EnumProperty
from bpy_extras.io_utils import ExportHelper, ImportHelper

from .module_helper import ModuleManager


# =============================================================================
# Smart Action Definitions
# =============================================================================

# Smart actions map a single action concept to multiple context-specific operators
SMART_ACTIONS = {
    'DUPLICATE': {
        'name': "Duplicate",
        'description': "Duplicate selected elements",
        'icon': 'DUPLICATE',
        'contexts': {
            'OBJECT': {'operator': 'object.duplicate_move', 'label': "Object Mode"},
            'EDIT_MESH': {'operator': 'mesh.duplicate_move', 'label': "Edit Mesh"},
            'EDIT_CURVE': {'operator': 'curve.duplicate_move', 'label': "Edit Curve"},
            'EDIT_SURFACE': {'operator': 'surface.duplicate_move', 'label': "Edit Surface"},
            'EDIT_ARMATURE': {'operator': 'armature.duplicate_move', 'label': "Edit Armature"},
            'EDIT_METABALL': {'operator': 'mball.duplicate_move', 'label': "Edit Metaball"},
            'EDIT_GPENCIL': {'operator': 'gpencil.duplicate_move', 'label': "Edit Grease Pencil"},
            'POSE': {'operator': 'pose.copy', 'label': "Pose Mode"},
            'NODE_EDITOR': {'operator': 'node.duplicate_move', 'label': "Node Editor"},
        }
    },
    'DELETE': {
        'name': "Delete",
        'description': "Delete selected elements",
        'icon': 'X',
        'contexts': {
            'OBJECT': {'operator': 'object.delete', 'label': "Object Mode"},
            'EDIT_MESH': {'operator': 'mesh.delete', 'label': "Edit Mesh"},
            'EDIT_CURVE': {'operator': 'curve.delete', 'label': "Edit Curve"},
            'EDIT_SURFACE': {'operator': 'surface.delete', 'label': "Edit Surface"},
            'EDIT_ARMATURE': {'operator': 'armature.delete', 'label': "Edit Armature"},
            'EDIT_METABALL': {'operator': 'mball.delete_metaelems', 'label': "Edit Metaball"},
            'EDIT_GPENCIL': {'operator': 'gpencil.delete', 'label': "Edit Grease Pencil"},
            'POSE': {'operator': 'pose.delete', 'label': "Pose Mode"},
            'NODE_EDITOR': {'operator': 'node.delete', 'label': "Node Editor"},
        }
    },
    'EXTRUDE': {
        'name': "Extrude",
        'description': "Extrude selected elements",
        'icon': 'ORIENTATION_NORMAL',
        'contexts': {
            'EDIT_MESH': {'operator': 'mesh.extrude_region_move', 'label': "Edit Mesh"},
            'EDIT_CURVE': {'operator': 'curve.extrude_move', 'label': "Edit Curve"},
            'EDIT_ARMATURE': {'operator': 'armature.extrude_move', 'label': "Edit Armature"},
        }
    },
    'SELECT_ALL': {
        'name': "Select All",
        'description': "Select/Deselect all elements",
        'icon': 'SELECT_SET',
        'contexts': {
            'OBJECT': {'operator': 'object.select_all', 'label': "Object Mode"},
            'EDIT_MESH': {'operator': 'mesh.select_all', 'label': "Edit Mesh"},
            'EDIT_CURVE': {'operator': 'curve.select_all', 'label': "Edit Curve"},
            'EDIT_SURFACE': {'operator': 'surface.select_all', 'label': "Edit Surface"},
            'EDIT_ARMATURE': {'operator': 'armature.select_all', 'label': "Edit Armature"},
            'EDIT_METABALL': {'operator': 'mball.select_all', 'label': "Edit Metaball"},
            'EDIT_LATTICE': {'operator': 'lattice.select_all', 'label': "Edit Lattice"},
            'EDIT_GPENCIL': {'operator': 'gpencil.select_all', 'label': "Edit Grease Pencil"},
            'POSE': {'operator': 'pose.select_all', 'label': "Pose Mode"},
            'SCULPT': {'operator': 'sculpt.face_set_change_visibility', 'label': "Sculpt Mode"},
            'NODE_EDITOR': {'operator': 'node.select_all', 'label': "Node Editor"},
        }
    },
    'HIDE': {
        'name': "Hide",
        'description': "Hide selected elements",
        'icon': 'HIDE_ON',
        'contexts': {
            'OBJECT': {'operator': 'object.hide_view_set', 'label': "Object Mode"},
            'EDIT_MESH': {'operator': 'mesh.hide', 'label': "Edit Mesh"},
            'EDIT_CURVE': {'operator': 'curve.hide', 'label': "Edit Curve"},
            'EDIT_ARMATURE': {'operator': 'armature.hide', 'label': "Edit Armature"},
            'EDIT_GPENCIL': {'operator': 'gpencil.hide', 'label': "Edit Grease Pencil"},
            'POSE': {'operator': 'pose.hide', 'label': "Pose Mode"},
            'NODE_EDITOR': {'operator': 'node.hide_toggle', 'label': "Node Editor"},
        }
    },
    'REVEAL': {
        'name': "Reveal/Unhide",
        'description': "Reveal hidden elements",
        'icon': 'HIDE_OFF',
        'contexts': {
            'OBJECT': {'operator': 'object.hide_view_clear', 'label': "Object Mode"},
            'EDIT_MESH': {'operator': 'mesh.reveal', 'label': "Edit Mesh"},
            'EDIT_CURVE': {'operator': 'curve.reveal', 'label': "Edit Curve"},
            'EDIT_ARMATURE': {'operator': 'armature.reveal', 'label': "Edit Armature"},
            'EDIT_GPENCIL': {'operator': 'gpencil.reveal', 'label': "Edit Grease Pencil"},
            'POSE': {'operator': 'pose.reveal', 'label': "Pose Mode"},
        }
    },
    'SEPARATE': {
        'name': "Separate",
        'description': "Separate selected elements",
        'icon': 'MOD_EXPLODE',
        'contexts': {
            'EDIT_MESH': {'operator': 'mesh.separate', 'label': "Edit Mesh"},
            'EDIT_CURVE': {'operator': 'curve.separate', 'label': "Edit Curve"},
            'EDIT_GPENCIL': {'operator': 'gpencil.stroke_separate', 'label': "Edit Grease Pencil"},
        }
    },
    'JOIN': {
        'name': "Join",
        'description': "Join selected objects",
        'icon': 'MOD_BOOLEAN',
        'contexts': {
            'OBJECT': {'operator': 'object.join', 'label': "Object Mode"},
        }
    },
    'SUBDIVIDE': {
        'name': "Subdivide",
        'description': "Subdivide selected elements",
        'icon': 'MOD_SUBSURF',
        'contexts': {
            'EDIT_MESH': {'operator': 'mesh.subdivide', 'label': "Edit Mesh"},
            'EDIT_CURVE': {'operator': 'curve.subdivide', 'label': "Edit Curve"},
        }
    },
    'MERGE': {
        'name': "Merge",
        'description': "Merge selected elements",
        'icon': 'AUTOMERGE_OFF',
        'contexts': {
            'EDIT_MESH': {'operator': 'mesh.merge', 'label': "Edit Mesh"},
        }
    },
    'INSET': {
        'name': "Inset",
        'description': "Inset faces",
        'icon': 'FULLSCREEN_EXIT',
        'contexts': {
            'EDIT_MESH': {'operator': 'mesh.inset', 'label': "Edit Mesh"},
        }
    },
    'BEVEL': {
        'name': "Bevel",
        'description': "Bevel edges/vertices",
        'icon': 'MOD_BEVEL',
        'contexts': {
            'EDIT_MESH': {'operator': 'mesh.bevel', 'label': "Edit Mesh"},
            'EDIT_CURVE': {'operator': 'curve.tilt_clear', 'label': "Edit Curve"},  # Approximate
        }
    },
    'LOOP_CUT': {
        'name': "Loop Cut",
        'description': "Add loop cuts",
        'icon': 'MOD_EDGESPLIT',
        'contexts': {
            'EDIT_MESH': {'operator': 'mesh.loopcut_slide', 'label': "Edit Mesh"},
        }
    },
    'KNIFE': {
        'name': "Knife",
        'description': "Knife tool",
        'icon': 'SCULPTMODE_HLT',
        'contexts': {
            'EDIT_MESH': {'operator': 'mesh.knife_tool', 'label': "Edit Mesh"},
        }
    },
    'FILL': {
        'name': "Fill",
        'description': "Fill faces",
        'icon': 'SNAP_FACE',
        'contexts': {
            'EDIT_MESH': {'operator': 'mesh.fill', 'label': "Edit Mesh"},
        }
    },
    'SMOOTH': {
        'name': "Smooth",
        'description': "Smooth vertices",
        'icon': 'MOD_SMOOTH',
        'contexts': {
            'EDIT_MESH': {'operator': 'mesh.vertices_smooth', 'label': "Edit Mesh"},
        }
    },
    'FLIP_NORMALS': {
        'name': "Flip Normals",
        'description': "Flip face normals",
        'icon': 'NORMALS_FACE',
        'contexts': {
            'EDIT_MESH': {'operator': 'mesh.flip_normals', 'label': "Edit Mesh"},
        }
    },
    'RECALC_NORMALS': {
        'name': "Recalculate Normals",
        'description': "Recalculate normals",
        'icon': 'ORIENTATION_NORMAL',
        'contexts': {
            'EDIT_MESH': {'operator': 'mesh.normals_make_consistent', 'label': "Edit Mesh"},
        }
    },
    'APPLY_MENU': {
        'name': "Apply Menu",
        'description': "Open the Apply menu with all transform options",
        'icon': 'CHECKMARK',
        'contexts': {
            'OBJECT': {'menu': 'VIEW3D_MT_object_apply', 'label': "Object Mode"},
        }
    },
    'CONVERT_MENU': {
        'name': "Convert Menu",
        'description': "Open the Convert To menu",
        'icon': 'FILE_REFRESH',
        'contexts': {
            'OBJECT': {'menu': 'VIEW3D_MT_object_convert', 'label': "Object Mode"},
        }
    },
    'ORIGIN_MENU': {
        'name': "Set Origin Menu",
        'description': "Open the Set Origin menu",
        'icon': 'OBJECT_ORIGIN',
        'contexts': {
            'OBJECT': {'menu': 'VIEW3D_MT_object_origin', 'label': "Object Mode"},
        }
    },
    'SNAP_MENU': {
        'name': "Snap Menu",
        'description': "Open the Snap menu",
        'icon': 'SNAP_ON',
        'contexts': {
            'OBJECT': {'menu': 'VIEW3D_MT_snap', 'label': "Object Mode"},
            'EDIT_MESH': {'menu': 'VIEW3D_MT_snap', 'label': "Edit Mesh"},
            'EDIT_CURVE': {'menu': 'VIEW3D_MT_snap', 'label': "Edit Curve"},
            'POSE': {'menu': 'VIEW3D_MT_snap', 'label': "Pose Mode"},
        }
    },
    'MIRROR_MENU': {
        'name': "Mirror Menu",
        'description': "Open the Mirror menu",
        'icon': 'MOD_MIRROR',
        'contexts': {
            'OBJECT': {'menu': 'VIEW3D_MT_mirror', 'label': "Object Mode"},
            'EDIT_MESH': {'menu': 'VIEW3D_MT_mirror', 'label': "Edit Mesh"},
        }
    },
    'ADD_MENU': {
        'name': "Add Menu",
        'description': "Open the Add menu",
        'icon': 'ADD',
        'contexts': {
            'OBJECT': {'menu': 'VIEW3D_MT_add', 'label': "Object Mode"},
            'EDIT_MESH': {'menu': 'VIEW3D_MT_mesh_add', 'label': "Edit Mesh"},
            'EDIT_CURVE': {'menu': 'VIEW3D_MT_curve_add', 'label': "Edit Curve"},
        }
    },
    'SPECIALS_MENU': {
        'name': "Context Menu",
        'description': "Open the context-sensitive specials menu",
        'icon': 'COLLAPSEMENU',
        'contexts': {
            'OBJECT': {'menu': 'VIEW3D_MT_object_context_menu', 'label': "Object Mode"},
            'EDIT_MESH': {'menu': 'VIEW3D_MT_edit_mesh_context_menu', 'label': "Edit Mesh"},
            'EDIT_CURVE': {'menu': 'VIEW3D_MT_edit_curve_context_menu', 'label': "Edit Curve"},
            'EDIT_ARMATURE': {'menu': 'VIEW3D_MT_armature_context_menu', 'label': "Edit Armature"},
            'POSE': {'menu': 'VIEW3D_MT_pose_context_menu', 'label': "Pose Mode"},
        }
    },
    'APPLY_TRANSFORMS': {
        'name': "Apply All Transforms",
        'description': "Apply all transforms directly",
        'icon': 'CHECKMARK',
        'contexts': {
            'OBJECT': {'operator': 'object.transform_apply', 'label': "Object Mode", 'props': {'location': True, 'rotation': True, 'scale': True}},
        }
    },
    'ORIGIN_TO_GEOMETRY': {
        'name': "Origin to Geometry",
        'description': "Set origin to geometry center",
        'icon': 'OBJECT_ORIGIN',
        'contexts': {
            'OBJECT': {'operator': 'object.origin_set', 'label': "Object Mode", 'props': {'type': 'ORIGIN_GEOMETRY'}},
        }
    },
    'ORIGIN_TO_CURSOR': {
        'name': "Origin to 3D Cursor",
        'description': "Set origin to 3D cursor",
        'icon': 'PIVOT_CURSOR',
        'contexts': {
            'OBJECT': {'operator': 'object.origin_set', 'label': "Object Mode", 'props': {'type': 'ORIGIN_CURSOR'}},
        }
    },
    'SET_PARENT': {
        'name': "Set Parent",
        'description': "Set parent relationship",
        'icon': 'LINKED',
        'contexts': {
            'OBJECT': {'operator': 'object.parent_set', 'label': "Object Mode"},
        }
    },
    'CLEAR_PARENT': {
        'name': "Clear Parent",
        'description': "Clear parent relationship",
        'icon': 'UNLINKED',
        'contexts': {
            'OBJECT': {'operator': 'object.parent_clear', 'label': "Object Mode"},
        }
    },
    'SHADE_SMOOTH': {
        'name': "Shade Smooth",
        'description': "Set smooth shading",
        'icon': 'MESH_UVSPHERE',
        'contexts': {
            'OBJECT': {'operator': 'object.shade_smooth', 'label': "Object Mode"},
            'EDIT_MESH': {'operator': 'mesh.faces_shade_smooth', 'label': "Edit Mesh"},
        }
    },
    'SHADE_FLAT': {
        'name': "Shade Flat",
        'description': "Set flat shading",
        'icon': 'MESH_ICOSPHERE',
        'contexts': {
            'OBJECT': {'operator': 'object.shade_flat', 'label': "Object Mode"},
            'EDIT_MESH': {'operator': 'mesh.faces_shade_flat', 'label': "Edit Mesh"},
        }
    },
}


# =============================================================================
# Smart Toggles - Predefined property toggles
# =============================================================================

SMART_TOGGLES = {
    # Tool Settings
    'SNAP': {
        'name': "Snapping",
        'description': "Toggle snapping on/off",
        'icon': 'SNAP_ON',
        'context': 'TOOL_SETTINGS',
        'property': 'use_snap',
    },
    'PROPORTIONAL': {
        'name': "Proportional Editing",
        'description': "Toggle proportional editing",
        'icon': 'PROP_ON',
        'context': 'TOOL_SETTINGS',
        'property': 'use_proportional_edit',
    },
    'PROPORTIONAL_CONNECTED': {
        'name': "Proportional Connected",
        'description': "Toggle connected-only proportional editing",
        'icon': 'PROP_CON',
        'context': 'TOOL_SETTINGS',
        'property': 'use_proportional_connected',
    },
    'AUTOMERGE': {
        'name': "Auto Merge",
        'description': "Toggle auto merge vertices",
        'icon': 'AUTOMERGE_ON',
        'context': 'TOOL_SETTINGS',
        'property': 'use_mesh_automerge',
    },
    'LOCK_OBJECT_MODE': {
        'name': "Lock Object Modes",
        'description': "Toggle lock object modes",
        'icon': 'LOCKED',
        'context': 'TOOL_SETTINGS',
        'property': 'lock_object_mode',
    },
    # Overlay Settings
    'WIREFRAME_OVERLAY': {
        'name': "Wireframe Overlay",
        'description': "Toggle wireframe overlay on objects",
        'icon': 'SHADING_WIRE',
        'context': 'SPACE',
        'property': 'overlay.show_wireframes',
    },
    'XRAY': {
        'name': "X-Ray",
        'description': "Toggle X-Ray mode",
        'icon': 'XRAY',
        'context': 'SPACE',
        'property': 'shading.show_xray',
    },
    'FACE_ORIENTATION': {
        'name': "Face Orientation",
        'description': "Toggle face orientation overlay",
        'icon': 'NORMALS_FACE',
        'context': 'SPACE',
        'property': 'overlay.show_face_orientation',
    },
    'SHOW_OVERLAYS': {
        'name': "Show Overlays",
        'description': "Toggle all overlays",
        'icon': 'OVERLAY',
        'context': 'SPACE',
        'property': 'overlay.show_overlays',
    },
    'SHOW_FLOOR': {
        'name': "Show Floor",
        'description': "Toggle floor grid",
        'icon': 'MESH_GRID',
        'context': 'SPACE',
        'property': 'overlay.show_floor',
    },
    'SHOW_AXIS_X': {
        'name': "Show X Axis",
        'description': "Toggle X axis line",
        'icon': 'EVENT_X',
        'context': 'SPACE',
        'property': 'overlay.show_axis_x',
    },
    'SHOW_AXIS_Y': {
        'name': "Show Y Axis",
        'description': "Toggle Y axis line",
        'icon': 'EVENT_Y',
        'context': 'SPACE',
        'property': 'overlay.show_axis_y',
    },
    'SHOW_AXIS_Z': {
        'name': "Show Z Axis",
        'description': "Toggle Z axis line",
        'icon': 'EVENT_Z',
        'context': 'SPACE',
        'property': 'overlay.show_axis_z',
    },
    'SHOW_CURSOR': {
        'name': "Show 3D Cursor",
        'description': "Toggle 3D cursor visibility",
        'icon': 'PIVOT_CURSOR',
        'context': 'SPACE',
        'property': 'overlay.show_cursor',
    },
    'SHOW_OBJECT_ORIGINS': {
        'name': "Show Origins",
        'description': "Toggle object origins",
        'icon': 'OBJECT_ORIGIN',
        'context': 'SPACE',
        'property': 'overlay.show_object_origins',
    },
    'SHOW_RELATIONSHIP_LINES': {
        'name': "Relationship Lines",
        'description': "Toggle relationship lines",
        'icon': 'CONSTRAINT',
        'context': 'SPACE',
        'property': 'overlay.show_relationship_lines',
    },
    'SHOW_OUTLINE_SELECTED': {
        'name': "Outline Selected",
        'description': "Toggle outline on selected objects",
        'icon': 'SELECT_SET',
        'context': 'SPACE',
        'property': 'overlay.show_outline_selected',
    },
    'SHOW_BONES': {
        'name': "Show Bones",
        'description': "Toggle bone visibility",
        'icon': 'BONE_DATA',
        'context': 'SPACE',
        'property': 'overlay.show_bones',
    },
    'SHOW_MOTION_PATHS': {
        'name': "Motion Paths",
        'description': "Toggle motion paths",
        'icon': 'ANIM_DATA',
        'context': 'SPACE',
        'property': 'overlay.show_motion_paths',
    },
    # Edit Mode Overlays
    'SHOW_EDGE_CREASE': {
        'name': "Edge Crease",
        'description': "Toggle edge crease display",
        'icon': 'EDGESEL',
        'context': 'SPACE',
        'property': 'overlay.show_edge_crease',
    },
    'SHOW_EDGE_SHARP': {
        'name': "Edge Sharp",
        'description': "Toggle sharp edge display",
        'icon': 'MOD_EDGESPLIT',
        'context': 'SPACE',
        'property': 'overlay.show_edge_sharp',
    },
    'SHOW_EDGE_BEVEL_WEIGHT': {
        'name': "Edge Bevel Weight",
        'description': "Toggle bevel weight display",
        'icon': 'MOD_BEVEL',
        'context': 'SPACE',
        'property': 'overlay.show_edge_bevel_weight',
    },
    'SHOW_EDGE_SEAMS': {
        'name': "Edge Seams",
        'description': "Toggle UV seam display",
        'icon': 'UV_DATA',
        'context': 'SPACE',
        'property': 'overlay.show_edge_seams',
    },
    'SHOW_FACE_NORMALS': {
        'name': "Face Normals",
        'description': "Toggle face normals display",
        'icon': 'NORMALS_FACE',
        'context': 'SPACE',
        'property': 'overlay.show_face_normals',
    },
    'SHOW_VERTEX_NORMALS': {
        'name': "Vertex Normals",
        'description': "Toggle vertex normals display",
        'icon': 'NORMALS_VERTEX',
        'context': 'SPACE',
        'property': 'overlay.show_vertex_normals',
    },
    'SHOW_STATVIS': {
        'name': "Mesh Analysis",
        'description': "Toggle mesh analysis overlay",
        'icon': 'VIEWZOOM',
        'context': 'SPACE',
        'property': 'overlay.show_statvis',
    },
    # Gizmos
    'SHOW_GIZMO': {
        'name': "Show Gizmos",
        'description': "Toggle gizmos visibility",
        'icon': 'GIZMO',
        'context': 'SPACE',
        'property': 'show_gizmo',
    },
    'SHOW_GIZMO_NAVIGATE': {
        'name': "Navigation Gizmo",
        'description': "Toggle navigation gizmo",
        'icon': 'VIEW_PAN',
        'context': 'SPACE',
        'property': 'show_gizmo_navigate',
    },
    'SHOW_GIZMO_TOOL': {
        'name': "Tool Gizmo",
        'description': "Toggle active tool gizmo",
        'icon': 'TOOL_SETTINGS',
        'context': 'SPACE',
        'property': 'show_gizmo_tool',
    },
    'SHOW_GIZMO_CONTEXT': {
        'name': "Context Gizmo",
        'description': "Toggle context gizmo",
        'icon': 'OBJECT_DATA',
        'context': 'SPACE',
        'property': 'show_gizmo_context',
    },
    # Shading
    'USE_SCENE_LIGHTS': {
        'name': "Scene Lights",
        'description': "Toggle scene lights in viewport",
        'icon': 'LIGHT',
        'context': 'SPACE',
        'property': 'shading.use_scene_lights',
    },
    'USE_SCENE_WORLD': {
        'name': "Scene World",
        'description': "Toggle scene world in viewport",
        'icon': 'WORLD',
        'context': 'SPACE',
        'property': 'shading.use_scene_world',
    },
    'SHOW_BACKFACE_CULLING': {
        'name': "Backface Culling",
        'description': "Toggle backface culling",
        'icon': 'FACESEL',
        'context': 'SPACE',
        'property': 'shading.show_backface_culling',
    },
    'SHOW_CAVITY': {
        'name': "Cavity",
        'description': "Toggle cavity shading",
        'icon': 'MATSPHERE',
        'context': 'SPACE',
        'property': 'shading.show_cavity',
    },
    'SHOW_SHADOWS': {
        'name': "Shadows",
        'description': "Toggle viewport shadows",
        'icon': 'LIGHT_SUN',
        'context': 'SPACE',
        'property': 'shading.show_shadows',
    },
    # Scene Settings
    'USE_GRAVITY': {
        'name': "Use Gravity",
        'description': "Toggle gravity in physics",
        'icon': 'FORCE_FORCE',
        'context': 'SCENE',
        'property': 'use_gravity',
    },
}


def get_smart_action_items(self, context):
    """Return smart actions as enum items"""
    items = [('NONE', "Select Action...", "Choose a smart action")]
    for action_id, action_data in SMART_ACTIONS.items():
        items.append((action_id, action_data['name'], action_data['description']))
    return items


def get_current_context_key(context):
    """Get the context key for smart action lookup"""
    # Check for node editor first
    if context.space_data and context.space_data.type == 'NODE_EDITOR':
        return 'NODE_EDITOR'
    # Then check mode
    return context.mode if hasattr(context, 'mode') else 'OBJECT'

# Module state
module_enabled = True
_is_registered = False

# Store dynamically created menu classes
_dynamic_menu_classes = {}


# =============================================================================
# Keymap Manager
# =============================================================================

class PieMenuKeymapManager:
    """Manages keymaps for custom pie menus"""

    _registered_keymaps = {}  # menu_id -> (keymap, keymap_item)

    @classmethod
    def get_keymap_name(cls, space_type):
        """Get Blender keymap name from space type"""
        keymap_names = {
            'VIEW_3D': '3D View',
            'NODE_EDITOR': 'Node Editor',
            'IMAGE_EDITOR': 'Image',
            'EMPTY': 'Window',
        }
        return keymap_names.get(space_type, '3D View')

    @classmethod
    def register_pie_menu_keymap(cls, pie_menu):
        """Register keymap for a single pie menu"""
        if not pie_menu.enabled or pie_menu.keymap_key == 'NONE':
            return False

        if not pie_menu.id:
            return False

        wm = bpy.context.window_manager
        kc = wm.keyconfigs.addon

        if not kc:
            print(f"QP_Tools: Addon keyconfig not available")
            return False

        km_name = cls.get_keymap_name(pie_menu.keymap_space)
        space_type = pie_menu.keymap_space if pie_menu.keymap_space != 'EMPTY' else 'EMPTY'

        # Get or create keymap
        km = kc.keymaps.get(km_name)
        if not km:
            try:
                km = kc.keymaps.new(name=km_name, space_type=space_type)
            except Exception as e:
                print(f"QP_Tools: Failed to create keymap '{km_name}': {e}")
                return False

        # Check if already registered
        if pie_menu.id in cls._registered_keymaps:
            cls.unregister_pie_menu_keymap(pie_menu.id)

        # Create keymap item
        try:
            kmi = km.keymap_items.new(
                "qp.call_custom_pie_menu",
                pie_menu.keymap_key,
                'PRESS',
                ctrl=pie_menu.keymap_ctrl,
                alt=pie_menu.keymap_alt,
                shift=pie_menu.keymap_shift,
                oskey=pie_menu.keymap_oskey
            )
            kmi.properties.menu_id = pie_menu.id

            cls._registered_keymaps[pie_menu.id] = (km, kmi)
            return True

        except Exception as e:
            print(f"QP_Tools: Failed to create keymap item for '{pie_menu.name}': {e}")
            return False

    @classmethod
    def unregister_pie_menu_keymap(cls, menu_id):
        """Unregister keymap for a specific pie menu"""
        if menu_id in cls._registered_keymaps:
            km, kmi = cls._registered_keymaps[menu_id]
            try:
                km.keymap_items.remove(kmi)
            except:
                pass
            del cls._registered_keymaps[menu_id]

    @classmethod
    def refresh_pie_menu_keymap(cls, pie_menu):
        """Refresh keymap for a single pie menu"""
        cls.unregister_pie_menu_keymap(pie_menu.id)
        if pie_menu.enabled:
            cls.register_pie_menu_keymap(pie_menu)

    @classmethod
    def ensure_addon_keymaps(cls):
        """Create addon keyconfig entries for all pie menus.

        This creates keymap items with key='NONE' in kc_addon so that
        Blender's keymap system can overlay the user-configured shortcuts
        from kc_user.  Without these entries, shortcuts only appear after
        the preferences UI is drawn (which is where they were previously
        created on-demand).
        """
        try:
            prefs = bpy.context.preferences.addons[__package__].preferences
            if not hasattr(prefs, 'custom_pie_menus'):
                return
        except Exception:
            return

        wm = bpy.context.window_manager
        kc = wm.keyconfigs.addon
        if not kc:
            return

        for pie_menu in prefs.custom_pie_menus:
            if not pie_menu.id or not pie_menu.enabled:
                continue
            if pie_menu.id in cls._registered_keymaps:
                continue

            km_name = cls.get_keymap_name(pie_menu.keymap_space)
            space_type = pie_menu.keymap_space if pie_menu.keymap_space != 'EMPTY' else 'EMPTY'
            km = kc.keymaps.get(km_name)
            if not km:
                try:
                    km = kc.keymaps.new(name=km_name, space_type=space_type)
                except Exception:
                    continue

            # Check if already exists in addon keyconfig
            already_exists = False
            for kmi in km.keymap_items:
                if (kmi.idname == "qp.call_custom_pie_menu" and
                    hasattr(kmi.properties, 'menu_id') and
                    kmi.properties.menu_id == pie_menu.id):
                    already_exists = True
                    cls._registered_keymaps[pie_menu.id] = (km, kmi)
                    break

            if not already_exists:
                try:
                    kmi = km.keymap_items.new(
                        "qp.call_custom_pie_menu",
                        'NONE', 'PRESS',
                    )
                    kmi.properties.menu_id = pie_menu.id
                    cls._registered_keymaps[pie_menu.id] = (km, kmi)
                except Exception:
                    pass

    @classmethod
    def unregister_all(cls):
        """Unregister all keymaps"""
        for menu_id in list(cls._registered_keymaps.keys()):
            cls.unregister_pie_menu_keymap(menu_id)


# =============================================================================
# Context Evaluation
# =============================================================================

def evaluate_context_rules(context, item):
    """Evaluate if an item should be shown based on context rules"""

    if not item.context_rules:
        return True  # No rules = always show

    results = []

    for rule in item.context_rules:
        if not rule.enabled:
            continue

        result = False

        if rule.rule_type == 'MODE':
            result = context.mode == rule.mode_filter

        elif rule.rule_type == 'OBJECT_TYPE':
            if context.active_object:
                result = context.active_object.type == rule.object_type_filter
            else:
                result = False

        elif rule.rule_type == 'SPACE_TYPE':
            if context.space_data:
                result = context.space_data.type == rule.space_type_filter
            else:
                result = False

        if rule.invert:
            result = not result

        results.append(result)

    if not results:
        return True

    if item.context_match_mode == 'ANY':
        return any(results)
    else:  # ALL
        return all(results)


def get_property_data_object(context, context_type):
    """Get the data object for a property context"""
    if context_type == 'SCENE':
        return context.scene
    elif context_type == 'OBJECT':
        return context.active_object
    elif context_type == 'TOOL_SETTINGS':
        return context.tool_settings
    elif context_type == 'SPACE':
        return context.space_data
    return None


# =============================================================================
# Dynamic Menu Drawing
# =============================================================================

def draw_pie_item(pie, item, context):
    """Draw a single pie item based on its action type"""

    icon = item.icon if item.icon and item.icon != 'NONE' else 'DOT'

    if item.action_type == 'SMART_ACTION':
        if not item.smart_action_id or item.smart_action_id not in SMART_ACTIONS:
            pie.separator()
            return

        action_data = SMART_ACTIONS[item.smart_action_id]
        context_key = get_current_context_key(context)

        # Check if action is available in current context
        if item.smart_action_contexts:
            enabled = set(item.smart_action_contexts.split(','))
        else:
            enabled = set(action_data['contexts'].keys())

        if context_key not in enabled or context_key not in action_data['contexts']:
            # Action not available in this context - hide the slot
            pie.separator()
            return

        # Use action's default icon if item doesn't have one
        if icon == 'DOT':
            icon = action_data.get('icon', 'DOT')

        try:
            op = pie.operator("qp.execute_smart_action", text=item.name, icon=icon)
            op.action_id = item.smart_action_id
            op.enabled_contexts = item.smart_action_contexts
        except Exception as e:
            pie.separator()

    elif item.action_type == 'OPERATOR':
        if not item.operator_idname:
            pie.separator()
            return

        try:
            op = pie.operator(item.operator_idname, text=item.name, icon=icon)
            # Apply operator properties from JSON
            if item.operator_props and item.operator_props != "{}":
                try:
                    props = json.loads(item.operator_props)
                    for key, value in props.items():
                        if hasattr(op, key):
                            setattr(op, key, value)
                except json.JSONDecodeError:
                    pass
        except Exception as e:
            pie.separator()

    elif item.action_type == 'SHORTCUT':
        if not item.shortcut_key or item.shortcut_key == 'NONE':
            pie.separator()
            return

        try:
            op = pie.operator("qp.simulate_shortcut", text=item.name, icon=icon)
            op.key = item.shortcut_key
            op.ctrl = item.shortcut_ctrl
            op.alt = item.shortcut_alt
            op.shift = item.shortcut_shift
        except Exception as e:
            pie.separator()

    elif item.action_type == 'PROPERTY_TOGGLE':
        if not item.property_data_path:
            pie.separator()
            return

        try:
            data_obj = get_property_data_object(context, item.property_context)
            if data_obj:
                pie.prop(data_obj, item.property_data_path, text=item.name, icon=icon, toggle=True)
            else:
                pie.separator()
        except Exception as e:
            pie.separator()

    elif item.action_type == 'PROPERTY_ENUM':
        if not item.property_data_path:
            pie.separator()
            return

        try:
            op = pie.operator("qp.cycle_enum_property", text=item.name, icon=icon)
            op.data_path = item.property_data_path
            op.context_type = item.property_context
        except Exception as e:
            pie.separator()


def create_dynamic_pie_menu_class(pie_menu_id):
    """Create a Menu class for a custom pie menu"""

    class DynamicPieMenu(bpy.types.Menu):
        bl_idname = f"QP_MT_custom_pie_{pie_menu_id}"
        bl_label = "Custom Pie Menu"

        _pie_menu_id = pie_menu_id

        def draw(self, context):
            layout = self.layout
            pie = layout.menu_pie()

            # Get the pie menu definition from preferences
            try:
                prefs = context.preferences.addons[__package__].preferences
            except:
                pie.label(text="Error: Preferences not found")
                return

            pie_menu = None
            for pm in prefs.custom_pie_menus:
                if pm.id == self._pie_menu_id:
                    pie_menu = pm
                    break

            if not pie_menu:
                pie.label(text="Menu not found")
                return

            # Keep label in sync with the user-facing name
            if self.bl_label != pie_menu.name:
                self.__class__.bl_label = pie_menu.name

            # Build position map (8 positions in standard pie)
            position_items = {i: None for i in range(8)}
            unpositioned = []

            for item in pie_menu.items:
                if not item.enabled:
                    continue
                if not evaluate_context_rules(context, item):
                    continue

                if 0 <= item.pie_position <= 7:
                    if position_items[item.pie_position] is None:
                        position_items[item.pie_position] = item
                    else:
                        # Position taken, add to unpositioned
                        unpositioned.append(item)
                else:
                    unpositioned.append(item)

            # Fill empty positions with unpositioned items
            for i in range(8):
                if position_items[i] is None and unpositioned:
                    position_items[i] = unpositioned.pop(0)

            # Draw items in pie order (West, East, South, North, NW, NE, SW, SE)
            # Blender pie positions: 0=W, 1=E, 2=S, 3=N, 4=NW, 5=NE, 6=SW, 7=SE
            for i in range(8):
                item = position_items[i]
                if item is None:
                    pie.separator()
                else:
                    draw_pie_item(pie, item, context)

    return DynamicPieMenu


def register_dynamic_menu(pie_menu):
    """Register a dynamic menu class for a pie menu"""
    if not pie_menu.id:
        return

    menu_id = pie_menu.id

    # Unregister if exists
    if menu_id in _dynamic_menu_classes:
        unregister_dynamic_menu(menu_id)

    # Create and register
    menu_class = create_dynamic_pie_menu_class(menu_id)
    menu_class.bl_label = pie_menu.name

    try:
        bpy.utils.register_class(menu_class)
        _dynamic_menu_classes[menu_id] = menu_class
    except Exception as e:
        print(f"QP_Tools: Failed to register menu class for '{pie_menu.name}': {e}")


def unregister_dynamic_menu(menu_id):
    """Unregister a dynamic menu class"""
    if menu_id in _dynamic_menu_classes:
        try:
            bpy.utils.unregister_class(_dynamic_menu_classes[menu_id])
        except:
            pass
        del _dynamic_menu_classes[menu_id]


def refresh_all_dynamic_menus():
    """Refresh all dynamic menu classes"""
    # Unregister all existing
    for menu_id in list(_dynamic_menu_classes.keys()):
        unregister_dynamic_menu(menu_id)

    # Re-register from preferences
    try:
        prefs = bpy.context.preferences.addons[__package__].preferences
        if hasattr(prefs, 'custom_pie_menus'):
            for pie_menu in prefs.custom_pie_menus:
                if pie_menu.id:
                    register_dynamic_menu(pie_menu)
    except Exception as e:
        print(f"QP_Tools: Error refreshing dynamic menus: {e}")


# =============================================================================
# Operators
# =============================================================================

class QP_OT_AddCustomPieMenu(Operator):
    """Add a new custom pie menu"""
    bl_idname = "qp.add_custom_pie_menu"
    bl_label = "Add Custom Pie Menu"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences

        # Create new pie menu
        pie_menu = prefs.custom_pie_menus.add()
        pie_menu.id = str(uuid.uuid4())[:8]
        pie_menu.name = f"Pie Menu {len(prefs.custom_pie_menus)}"

        # Register dynamic menu
        register_dynamic_menu(pie_menu)

        # Save preferences
        bpy.ops.wm.save_userpref()

        self.report({'INFO'}, f"Created pie menu: {pie_menu.name}")
        return {'FINISHED'}


class QP_OT_RemoveCustomPieMenu(Operator):
    """Remove a custom pie menu"""
    bl_idname = "qp.remove_custom_pie_menu"
    bl_label = "Remove Custom Pie Menu"
    bl_options = {'REGISTER', 'UNDO'}

    menu_id: StringProperty(name="Menu ID")

    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences

        # Find and remove
        for i, pie_menu in enumerate(prefs.custom_pie_menus):
            if pie_menu.id == self.menu_id:
                # Unregister keymap and menu
                PieMenuKeymapManager.unregister_pie_menu_keymap(self.menu_id)
                unregister_dynamic_menu(self.menu_id)

                # Remove from collection
                prefs.custom_pie_menus.remove(i)

                # Save preferences
                bpy.ops.wm.save_userpref()

                self.report({'INFO'}, "Pie menu removed")
                return {'FINISHED'}

        self.report({'WARNING'}, "Pie menu not found")
        return {'CANCELLED'}


class QP_OT_DuplicateCustomPieMenu(Operator):
    """Duplicate a custom pie menu"""
    bl_idname = "qp.duplicate_custom_pie_menu"
    bl_label = "Duplicate Custom Pie Menu"
    bl_options = {'REGISTER', 'UNDO'}

    menu_id: StringProperty(name="Menu ID")

    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences

        # Find source
        source = None
        for pie_menu in prefs.custom_pie_menus:
            if pie_menu.id == self.menu_id:
                source = pie_menu
                break

        if not source:
            self.report({'WARNING'}, "Pie menu not found")
            return {'CANCELLED'}

        # Create duplicate
        new_menu = prefs.custom_pie_menus.add()
        new_menu.id = str(uuid.uuid4())[:8]
        new_menu.name = f"{source.name} (Copy)"
        new_menu.enabled = False  # Start disabled to avoid shortcut conflict
        new_menu.icon = source.icon
        new_menu.keymap_key = source.keymap_key
        new_menu.keymap_ctrl = source.keymap_ctrl
        new_menu.keymap_alt = source.keymap_alt
        new_menu.keymap_shift = source.keymap_shift
        new_menu.keymap_space = source.keymap_space

        # Copy items
        for src_item in source.items:
            new_item = new_menu.items.add()
            new_item.id = str(uuid.uuid4())[:8]
            new_item.name = src_item.name
            new_item.enabled = src_item.enabled
            new_item.icon = src_item.icon
            new_item.action_type = src_item.action_type
            new_item.smart_action_id = src_item.smart_action_id
            new_item.smart_action_contexts = src_item.smart_action_contexts
            new_item.operator_idname = src_item.operator_idname
            new_item.operator_props = src_item.operator_props
            new_item.shortcut_key = src_item.shortcut_key
            new_item.shortcut_ctrl = src_item.shortcut_ctrl
            new_item.shortcut_alt = src_item.shortcut_alt
            new_item.shortcut_shift = src_item.shortcut_shift
            new_item.smart_toggle_id = src_item.smart_toggle_id
            new_item.property_data_path = src_item.property_data_path
            new_item.property_context = src_item.property_context
            new_item.pie_position = src_item.pie_position
            new_item.context_match_mode = src_item.context_match_mode

            # Copy context rules
            for src_rule in src_item.context_rules:
                new_rule = new_item.context_rules.add()
                new_rule.enabled = src_rule.enabled
                new_rule.rule_type = src_rule.rule_type
                new_rule.mode_filter = src_rule.mode_filter
                new_rule.object_type_filter = src_rule.object_type_filter
                new_rule.space_type_filter = src_rule.space_type_filter
                new_rule.invert = src_rule.invert

        # Register dynamic menu
        register_dynamic_menu(new_menu)

        # Save preferences
        bpy.ops.wm.save_userpref()

        self.report({'INFO'}, f"Created copy: {new_menu.name}")
        return {'FINISHED'}


class QP_OT_MoveCustomPieMenu(Operator):
    """Move a pie menu up or down in the list"""
    bl_idname = "qp.move_custom_pie_menu"
    bl_label = "Move Custom Pie Menu"
    bl_options = {'REGISTER', 'UNDO'}

    menu_id: StringProperty(name="Menu ID")
    direction: EnumProperty(
        name="Direction",
        items=[('UP', "Up", ""), ('DOWN', "Down", "")]
    )

    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences

        # Find index
        index = -1
        for i, pie_menu in enumerate(prefs.custom_pie_menus):
            if pie_menu.id == self.menu_id:
                index = i
                break

        if index < 0:
            return {'CANCELLED'}

        if self.direction == 'UP' and index > 0:
            prefs.custom_pie_menus.move(index, index - 1)
        elif self.direction == 'DOWN' and index < len(prefs.custom_pie_menus) - 1:
            prefs.custom_pie_menus.move(index, index + 1)

        return {'FINISHED'}


class QP_OT_AddPieMenuItem(Operator):
    """Add a new item to a pie menu"""
    bl_idname = "qp.add_pie_menu_item"
    bl_label = "Add Pie Menu Item"
    bl_options = {'REGISTER', 'UNDO'}

    menu_id: StringProperty(name="Menu ID")

    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences

        # Find pie menu
        pie_menu = None
        for pm in prefs.custom_pie_menus:
            if pm.id == self.menu_id:
                pie_menu = pm
                break

        if not pie_menu:
            self.report({'WARNING'}, "Pie menu not found")
            return {'CANCELLED'}

        # Add item
        item = pie_menu.items.add()
        item.id = str(uuid.uuid4())[:8]
        item.name = f"Item {len(pie_menu.items)}"
        item.expanded = True  # Auto-expand new items

        # Save preferences
        bpy.ops.wm.save_userpref()

        return {'FINISHED'}


class QP_OT_RemovePieMenuItem(Operator):
    """Remove an item from a pie menu"""
    bl_idname = "qp.remove_pie_menu_item"
    bl_label = "Remove Pie Menu Item"
    bl_options = {'REGISTER', 'UNDO'}

    menu_id: StringProperty(name="Menu ID")
    item_id: StringProperty(name="Item ID")

    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences

        # Find pie menu
        pie_menu = None
        for pm in prefs.custom_pie_menus:
            if pm.id == self.menu_id:
                pie_menu = pm
                break

        if not pie_menu:
            return {'CANCELLED'}

        # Find and remove item
        for i, item in enumerate(pie_menu.items):
            if item.id == self.item_id:
                pie_menu.items.remove(i)
                bpy.ops.wm.save_userpref()
                return {'FINISHED'}

        return {'CANCELLED'}


class QP_OT_MovePieMenuItem(Operator):
    """Move a pie menu item up or down"""
    bl_idname = "qp.move_pie_menu_item"
    bl_label = "Move Pie Menu Item"
    bl_options = {'REGISTER', 'UNDO'}

    menu_id: StringProperty(name="Menu ID")
    item_id: StringProperty(name="Item ID")
    direction: EnumProperty(
        name="Direction",
        items=[('UP', "Up", ""), ('DOWN', "Down", "")]
    )

    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences

        # Find pie menu
        pie_menu = None
        for pm in prefs.custom_pie_menus:
            if pm.id == self.menu_id:
                pie_menu = pm
                break

        if not pie_menu:
            return {'CANCELLED'}

        # Find item index
        index = -1
        for i, item in enumerate(pie_menu.items):
            if item.id == self.item_id:
                index = i
                break

        if index < 0:
            return {'CANCELLED'}

        if self.direction == 'UP' and index > 0:
            pie_menu.items.move(index, index - 1)
        elif self.direction == 'DOWN' and index < len(pie_menu.items) - 1:
            pie_menu.items.move(index, index + 1)

        return {'FINISHED'}


class QP_OT_AddContextRule(Operator):
    """Add a context rule to a pie menu item"""
    bl_idname = "qp.add_context_rule"
    bl_label = "Add Context Rule"
    bl_options = {'REGISTER', 'UNDO'}

    menu_id: StringProperty(name="Menu ID")
    item_id: StringProperty(name="Item ID")

    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences

        # Find item
        for pie_menu in prefs.custom_pie_menus:
            if pie_menu.id == self.menu_id:
                for item in pie_menu.items:
                    if item.id == self.item_id:
                        item.context_rules.add()
                        bpy.ops.wm.save_userpref()
                        return {'FINISHED'}

        return {'CANCELLED'}


class QP_OT_RemoveContextRule(Operator):
    """Remove a context rule from a pie menu item"""
    bl_idname = "qp.remove_context_rule"
    bl_label = "Remove Context Rule"
    bl_options = {'REGISTER', 'UNDO'}

    menu_id: StringProperty(name="Menu ID")
    item_id: StringProperty(name="Item ID")
    rule_index: IntProperty(name="Rule Index")

    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences

        # Find item
        for pie_menu in prefs.custom_pie_menus:
            if pie_menu.id == self.menu_id:
                for item in pie_menu.items:
                    if item.id == self.item_id:
                        if 0 <= self.rule_index < len(item.context_rules):
                            item.context_rules.remove(self.rule_index)
                            bpy.ops.wm.save_userpref()
                            return {'FINISHED'}

        return {'CANCELLED'}


class QP_OT_CallCustomPieMenu(Operator):
    """Call a custom pie menu by ID"""
    bl_idname = "qp.call_custom_pie_menu"
    bl_label = "Call Custom Pie Menu"

    menu_id: StringProperty(name="Menu ID")

    def execute(self, context):
        menu_class_name = f"QP_MT_custom_pie_{self.menu_id}"
        try:
            bpy.ops.wm.call_menu_pie(name=menu_class_name)
        except Exception as e:
            self.report({'WARNING'}, f"Failed to open pie menu: {e}")
            return {'CANCELLED'}
        return {'FINISHED'}


class QP_OT_CycleEnumProperty(Operator):
    """Cycle through enum property values"""
    bl_idname = "qp.cycle_enum_property"
    bl_label = "Cycle Enum Property"
    bl_options = {'REGISTER', 'UNDO'}

    data_path: StringProperty(name="Data Path")
    context_type: StringProperty(name="Context Type")

    def execute(self, context):
        data_obj = get_property_data_object(context, self.context_type)

        if not data_obj:
            self.report({'WARNING'}, "Context not available")
            return {'CANCELLED'}

        try:
            # Get current value and enum items
            current = getattr(data_obj, self.data_path)

            # Get enum items from RNA
            rna_prop = data_obj.bl_rna.properties.get(self.data_path)
            if not rna_prop or rna_prop.type != 'ENUM':
                self.report({'WARNING'}, "Not an enum property")
                return {'CANCELLED'}

            items = [item.identifier for item in rna_prop.enum_items]

            # Find next value
            try:
                current_index = items.index(current)
                next_index = (current_index + 1) % len(items)
                setattr(data_obj, self.data_path, items[next_index])
            except ValueError:
                if items:
                    setattr(data_obj, self.data_path, items[0])

            return {'FINISHED'}

        except Exception as e:
            self.report({'WARNING'}, f"Error cycling property: {e}")
            return {'CANCELLED'}


class QP_OT_TogglePieItemExpanded(Operator):
    """Toggle item expanded state"""
    bl_idname = "qp.toggle_pie_item_expanded"
    bl_label = "Toggle Item Expanded"

    menu_id: StringProperty()
    item_id: StringProperty()

    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences

        for pie_menu in prefs.custom_pie_menus:
            if pie_menu.id == self.menu_id:
                for item in pie_menu.items:
                    if item.id == self.item_id:
                        item.expanded = not item.expanded
                        return {'FINISHED'}

        return {'CANCELLED'}


# Icon categories for the visual picker
ICON_CATEGORIES = {
    'Common': ['NONE', 'DOT', 'CHECKMARK', 'X', 'ADD', 'REMOVE', 'DUPLICATE',
               'CHECKBOX_HLT', 'CHECKBOX_DEHLT', 'HIDE_OFF', 'HIDE_ON'],
    'Objects': ['OBJECT_DATA', 'MESH_DATA', 'CURVE_DATA', 'SURFACE_DATA',
                'EMPTY_DATA', 'FONT_DATA', 'LIGHT_DATA', 'CAMERA_DATA',
                'ARMATURE_DATA', 'LATTICE_DATA', 'SPEAKER', 'VOLUME_DATA'],
    'Modes': ['EDITMODE_HLT', 'OBJECT_DATAMODE', 'SCULPTMODE_HLT',
              'WPAINT_HLT', 'VPAINT_HLT', 'TPAINT_HLT', 'POSE_HLT'],
    'Modifiers': ['MODIFIER', 'MOD_SUBSURF', 'MOD_MIRROR', 'MOD_BEVEL',
                  'MOD_SOLIDIFY', 'MOD_ARRAY', 'MOD_BOOLEAN', 'MOD_DECIM',
                  'MOD_LATTICE', 'MOD_SHRINKWRAP', 'MOD_SMOOTH', 'MOD_SIMPLEDEFORM'],
    'Transform': ['ORIENTATION_GLOBAL', 'ORIENTATION_LOCAL', 'ORIENTATION_NORMAL',
                  'PIVOT_CURSOR', 'PIVOT_ACTIVE', 'PIVOT_INDIVIDUAL', 'PIVOT_MEDIAN'],
    'Selection': ['VERTEXSEL', 'EDGESEL', 'FACESEL', 'SELECT_SET', 'SELECT_EXTEND',
                  'SELECT_SUBTRACT', 'SELECT_INTERSECT', 'SELECT_DIFFERENCE'],
    'Snapping': ['SNAP_ON', 'SNAP_OFF', 'SNAP_VERTEX', 'SNAP_EDGE', 'SNAP_FACE',
                 'SNAP_GRID', 'SNAP_INCREMENT', 'SNAP_VOLUME'],
    'Shading': ['SHADING_SOLID', 'SHADING_TEXTURE', 'SHADING_RENDERED', 'SHADING_WIRE',
                'OVERLAY', 'XRAY', 'MATERIAL', 'TEXTURE'],
    'Animation': ['PLAY', 'PAUSE', 'FF', 'REW', 'FRAME_PREV', 'FRAME_NEXT',
                  'REC', 'KEYFRAME', 'KEYFRAME_HLT'],
    'Files': ['FILE', 'FILE_FOLDER', 'FILE_BLEND', 'FILE_IMAGE', 'FILE_NEW',
              'FILE_TICK', 'FILE_REFRESH', 'IMPORT', 'EXPORT'],
    'UI': ['TRIA_RIGHT', 'TRIA_DOWN', 'TRIA_LEFT', 'TRIA_UP',
           'ARROW_LEFTRIGHT', 'PLUS', 'INFO', 'ERROR', 'QUESTION', 'CANCEL'],
}

# Extended icon list for search
ALL_ICONS = [
    'NONE', 'DOT', 'CHECKMARK', 'X', 'ADD', 'REMOVE', 'DUPLICATE', 'PANEL_CLOSE',
    'CHECKBOX_HLT', 'CHECKBOX_DEHLT', 'HIDE_OFF', 'HIDE_ON', 'BLANK1',
    'RESTRICT_SELECT_OFF', 'RESTRICT_SELECT_ON', 'RESTRICT_RENDER_OFF', 'RESTRICT_RENDER_ON',
    'OBJECT_DATA', 'MESH_DATA', 'CURVE_DATA', 'SURFACE_DATA', 'EMPTY_DATA', 'FONT_DATA',
    'LIGHT_DATA', 'CAMERA_DATA', 'ARMATURE_DATA', 'LATTICE_DATA', 'SPEAKER', 'VOLUME_DATA',
    'OUTLINER_OB_MESH', 'OUTLINER_OB_CURVE', 'OUTLINER_OB_LATTICE', 'OUTLINER_OB_CAMERA',
    'OUTLINER_OB_LIGHT', 'OUTLINER_OB_ARMATURE', 'OUTLINER_OB_EMPTY', 'OUTLINER_OB_FONT',
    'EDITMODE_HLT', 'OBJECT_DATAMODE', 'SCULPTMODE_HLT', 'WPAINT_HLT', 'VPAINT_HLT',
    'TPAINT_HLT', 'POSE_HLT', 'PARTICLE_DATA', 'PARTICLES',
    'MODIFIER', 'MOD_SUBSURF', 'MOD_MIRROR', 'MOD_BEVEL', 'MOD_SOLIDIFY', 'MOD_ARRAY',
    'MOD_BOOLEAN', 'MOD_DECIM', 'MOD_LATTICE', 'MOD_SHRINKWRAP', 'MOD_SMOOTH',
    'MOD_SIMPLEDEFORM', 'MOD_ARMATURE', 'MOD_BUILD', 'MOD_CAST', 'MOD_CLOTH',
    'MOD_CURVE', 'MOD_DATA_TRANSFER', 'MOD_DISPLACE', 'MOD_DYNAMICPAINT', 'MOD_EDGESPLIT',
    'MOD_EXPLODE', 'MOD_FLUID', 'MOD_HUE_SATURATION', 'MOD_INSTANCE', 'MOD_MASK',
    'MOD_MESHDEFORM', 'MOD_MULTIRES', 'MOD_NOISE', 'MOD_NORMALEDIT', 'MOD_OCEAN',
    'MOD_OFFSET', 'MOD_PARTICLE_INSTANCE', 'MOD_PHYSICS', 'MOD_REMESH', 'MOD_SCREW',
    'MOD_SKIN', 'MOD_SOFT', 'MOD_THICKNESS', 'MOD_TIME', 'MOD_TRIANGULATE',
    'MOD_UVPROJECT', 'MOD_VERTEX_WEIGHT', 'MOD_WARP', 'MOD_WAVE', 'MOD_WIREFRAME',
    'ORIENTATION_GLOBAL', 'ORIENTATION_LOCAL', 'ORIENTATION_NORMAL', 'ORIENTATION_GIMBAL',
    'ORIENTATION_VIEW', 'ORIENTATION_CURSOR', 'ORIENTATION_PARENT',
    'PIVOT_CURSOR', 'PIVOT_ACTIVE', 'PIVOT_INDIVIDUAL', 'PIVOT_MEDIAN', 'PIVOT_BOUNDBOX',
    'VERTEXSEL', 'EDGESEL', 'FACESEL', 'UV_VERTEXSEL', 'UV_EDGESEL', 'UV_FACESEL',
    'SELECT_SET', 'SELECT_EXTEND', 'SELECT_SUBTRACT', 'SELECT_INTERSECT', 'SELECT_DIFFERENCE',
    'SNAP_ON', 'SNAP_OFF', 'SNAP_VERTEX', 'SNAP_EDGE', 'SNAP_FACE', 'SNAP_GRID',
    'SNAP_INCREMENT', 'SNAP_VOLUME', 'SNAP_MIDPOINT', 'SNAP_PERPENDICULAR', 'SNAP_NORMAL',
    'SHADING_SOLID', 'SHADING_TEXTURE', 'SHADING_RENDERED', 'SHADING_WIRE', 'SHADING_BBOX',
    'OVERLAY', 'XRAY', 'LIGHT_SUN', 'LIGHT_POINT', 'LIGHT_SPOT', 'LIGHT_HEMI', 'LIGHT_AREA',
    'MATERIAL', 'MATERIAL_DATA', 'NODE_MATERIAL', 'TEXTURE', 'TEXTURE_DATA',
    'IMAGE_DATA', 'IMAGE', 'IMAGE_PLANE', 'IMAGE_RGB', 'IMAGE_RGB_ALPHA',
    'WORLD', 'WORLD_DATA', 'SCENE', 'SCENE_DATA', 'RENDER_RESULT', 'RENDER_ANIMATION',
    'PLAY', 'PAUSE', 'FF', 'REW', 'FRAME_PREV', 'FRAME_NEXT', 'REC',
    'KEYFRAME', 'KEYFRAME_HLT', 'KEY_DEHLT', 'KEYINGSET', 'DRIVER', 'NLA', 'ACTION',
    'FILE', 'FILE_FOLDER', 'FILE_BLEND', 'FILE_IMAGE', 'FILE_MOVIE', 'FILE_SCRIPT',
    'FILE_NEW', 'FILE_TICK', 'FILE_REFRESH', 'FILE_BACKUP', 'FILE_HIDDEN', 'FILE_FONT',
    'IMPORT', 'EXPORT', 'DISK_DRIVE', 'EXTERNAL_DRIVE', 'NETWORK_DRIVE',
    'TRIA_RIGHT', 'TRIA_DOWN', 'TRIA_LEFT', 'TRIA_UP', 'ARROW_LEFTRIGHT',
    'PLUS', 'DISCLOSURE_TRI_RIGHT', 'DISCLOSURE_TRI_DOWN', 'INFO', 'ERROR', 'QUESTION', 'CANCEL',
    'BRUSH_DATA', 'BRUSH_BLOB', 'BRUSH_BLUR', 'BRUSH_CLAY', 'BRUSH_CLONE', 'BRUSH_CREASE',
    'BRUSH_FILL', 'BRUSH_FLATTEN', 'BRUSH_GRAB', 'BRUSH_INFLATE', 'BRUSH_MASK', 'BRUSH_MIX',
    'BRUSH_NUDGE', 'BRUSH_PINCH', 'BRUSH_SCRAPE', 'BRUSH_SCULPT_DRAW', 'BRUSH_SMEAR',
    'BRUSH_SMOOTH', 'BRUSH_SNAKE_HOOK', 'BRUSH_SOFTEN', 'BRUSH_TEXFILL', 'BRUSH_THUMB',
    'CONSTRAINT', 'CONSTRAINT_BONE', 'CON_ACTION', 'CON_ARMATURE', 'CON_CAMERASOLVER',
    'CON_CHILDOF', 'CON_CLAMPTO', 'CON_DISTLIMIT', 'CON_FLOOR', 'CON_FOLLOWPATH',
    'CON_KINEMATIC', 'CON_LOCLIKE', 'CON_LOCKTRACK', 'CON_PIVOT', 'CON_ROTLIKE',
    'CON_ROTLIMIT', 'CON_SIZELIKE', 'CON_SIZELIMIT', 'CON_STRETCHTO', 'CON_TRACKTO',
    'WINDOW', 'WORKSPACE', 'FULLSCREEN_ENTER', 'FULLSCREEN_EXIT', 'SCREEN_BACK',
    'VIEW3D', 'VIEW_CAMERA', 'VIEW_ORTHO', 'VIEW_PERSPECTIVE', 'VIEW_PAN', 'VIEW_ZOOM',
    'ZOOM_IN', 'ZOOM_OUT', 'ZOOM_ALL', 'ZOOM_PREVIOUS', 'ZOOM_SELECTED',
    'TOOL_SETTINGS', 'PROPERTIES', 'PREFERENCES', 'NODE', 'NODE_SEL', 'NODETREE',
    'CONSOLE', 'TRACKER', 'SEQUENCE', 'ASSET_MANAGER', 'UV', 'GRAPH', 'OUTLINER',
    'FILEBROWSER', 'HAND', 'ZOOM_SET', 'PRESET', 'SETTINGS', 'LINKED', 'UNLINKED',
    'COLOR', 'COLOR_RED', 'COLOR_GREEN', 'COLOR_BLUE', 'COPY_ID', 'EYEDROPPER', 'AUTO',
    'OBJECT_ORIGIN', 'OBJECT_HIDDEN', 'BONE_DATA', 'MESH_PLANE', 'MESH_CUBE', 'MESH_CIRCLE',
    'MESH_UVSPHERE', 'MESH_ICOSPHERE', 'MESH_GRID', 'MESH_MONKEY', 'MESH_CYLINDER',
    'MESH_TORUS', 'MESH_CONE', 'MESH_CAPSULE', 'NORMALS_FACE', 'NORMALS_VERTEX',
    'NORMALS_VERTEX_FACE', 'AUTOMERGE_OFF', 'AUTOMERGE_ON', 'DECORATE', 'DECORATE_KEYFRAME',
    'DECORATE_ANIMATE', 'DECORATE_DRIVER', 'DECORATE_LINKED', 'DECORATE_LIBRARY_OVERRIDE',
    'DECORATE_OVERRIDE', 'DECORATE_UNLOCKED', 'DECORATE_LOCKED', 'SORT_DESC', 'SORT_ASC',
    'FORWARD', 'BACK', 'PASTEDOWN', 'COPYDOWN', 'LOOP_BACK', 'LOOP_FORWARDS',
    'TEMP', 'LOCKED', 'UNLOCKED', 'PINNED', 'UNPINNED', 'ALIGN_LEFT', 'ALIGN_CENTER',
    'ALIGN_RIGHT', 'ALIGN_JUSTIFY', 'ALIGN_FLUSH', 'ALIGN_TOP', 'ALIGN_MIDDLE', 'ALIGN_BOTTOM',
    'BOLD', 'ITALIC', 'UNDERLINE', 'SMALL_CAPS', 'STYLUS_PRESSURE', 'GHOST_ENABLED',
    'GHOST_DISABLED', 'ONIONSKIN_ON', 'ONIONSKIN_OFF', 'GREASEPENCIL', 'GP_SELECT_STROKES',
    'GP_SELECT_POINTS', 'GP_MULTIFRAME_EDITING', 'GP_ONLY_SELECTED', 'GP_SELECT_BETWEEN_STROKES',
]


class QP_OT_PickIcon(Operator):
    """Pick an icon from a visual popup"""
    bl_idname = "qp.pick_icon"
    bl_label = "Pick Icon"
    bl_options = {'REGISTER', 'INTERNAL'}

    menu_id: StringProperty()
    item_id: StringProperty()
    target: StringProperty(default="item")  # "item" or "menu"
    icon_value: StringProperty(default="")
    search: StringProperty(name="Search", default="", description="Search for icons by name")

    def execute(self, context):
        if not self.icon_value:
            return {'CANCELLED'}

        prefs = context.preferences.addons[__package__].preferences

        if self.target == "menu":
            for pie_menu in prefs.custom_pie_menus:
                if pie_menu.id == self.menu_id:
                    pie_menu.icon = self.icon_value
                    bpy.ops.wm.save_userpref()
                    return {'FINISHED'}
        else:
            for pie_menu in prefs.custom_pie_menus:
                if pie_menu.id == self.menu_id:
                    for item in pie_menu.items:
                        if item.id == self.item_id:
                            item.icon = self.icon_value
                            bpy.ops.wm.save_userpref()
                            return {'FINISHED'}

        return {'CANCELLED'}

    def invoke(self, context, event):
        # Store operator properties in window manager for the popup
        wm = context.window_manager
        wm['qp_icon_picker_menu_id'] = self.menu_id
        wm['qp_icon_picker_item_id'] = self.item_id
        wm['qp_icon_picker_target'] = self.target
        self.search = ""
        return context.window_manager.invoke_popup(self, width=450)

    def draw(self, context):
        layout = self.layout

        # Search field
        layout.prop(self, "search", text="", icon='VIEWZOOM')

        search_term = self.search.upper().strip()

        if search_term:
            # Show search results
            matching_icons = [icon for icon in ALL_ICONS if search_term in icon]
            if matching_icons:
                box = layout.box()
                box.label(text=f"Search Results ({len(matching_icons)})")
                grid = box.grid_flow(columns=12, even_columns=True, align=True)
                for icon_name in matching_icons[:60]:  # Limit to 60 results
                    try:
                        op = grid.operator("qp.set_icon_value", text="", icon=icon_name)
                        op.menu_id = self.menu_id
                        op.item_id = self.item_id
                        op.target = self.target
                        op.icon_value = icon_name
                    except:
                        pass
                if len(matching_icons) > 60:
                    box.label(text=f"...and {len(matching_icons) - 60} more")
            else:
                layout.label(text="No icons found matching search", icon='INFO')
        else:
            # Show categories
            for category, icons in ICON_CATEGORIES.items():
                box = layout.box()
                box.label(text=category)
                grid = box.grid_flow(columns=12, even_columns=True, align=True)
                for icon_name in icons:
                    try:
                        op = grid.operator("qp.set_icon_value", text="", icon=icon_name)
                        op.menu_id = self.menu_id
                        op.item_id = self.item_id
                        op.target = self.target
                        op.icon_value = icon_name
                    except:
                        pass  # Skip invalid icons


class QP_OT_SetIconValue(Operator):
    """Set the icon value"""
    bl_idname = "qp.set_icon_value"
    bl_label = "Set Icon"
    bl_options = {'REGISTER', 'INTERNAL'}

    menu_id: StringProperty()
    item_id: StringProperty()
    target: StringProperty(default="item")
    icon_value: StringProperty()

    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences

        if self.target == "menu":
            for pie_menu in prefs.custom_pie_menus:
                if pie_menu.id == self.menu_id:
                    pie_menu.icon = self.icon_value
                    bpy.ops.wm.save_userpref()
                    return {'FINISHED'}
        else:
            for pie_menu in prefs.custom_pie_menus:
                if pie_menu.id == self.menu_id:
                    for item in pie_menu.items:
                        if item.id == self.item_id:
                            item.icon = self.icon_value
                            bpy.ops.wm.save_userpref()
                            return {'FINISHED'}

        return {'CANCELLED'}


class QP_OT_SearchOperator(Operator):
    """Search for a Blender operator"""
    bl_idname = "qp.search_operator"
    bl_label = "Search Operator"
    bl_property = "operator"

    menu_id: StringProperty()
    item_id: StringProperty()

    operator: EnumProperty(
        name="Operator",
        items=lambda self, context: QP_OT_SearchOperator.get_operator_items(self, context)
    )

    @staticmethod
    def get_operator_items(self, context):
        """Return available operators as enum items"""
        items = []

        # Get all operators from bpy.ops modules
        for module_name in dir(bpy.ops):
            if module_name.startswith('_'):
                continue

            try:
                module = getattr(bpy.ops, module_name)
                for op_name in dir(module):
                    if op_name.startswith('_'):
                        continue

                    try:
                        op = getattr(module, op_name)
                        if hasattr(op, 'get_rna_type'):
                            rna_type = op.get_rna_type()
                            idname = f"{module_name}.{op_name}"
                            label = rna_type.name if rna_type else op_name
                            desc = rna_type.description if rna_type else ""
                            items.append((idname, f"{label} ({idname})", desc))
                    except:
                        pass
            except:
                pass

        # Sort alphabetically by label
        items.sort(key=lambda x: x[1].lower())

        return items

    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences

        for pie_menu in prefs.custom_pie_menus:
            if pie_menu.id == self.menu_id:
                for item in pie_menu.items:
                    if item.id == self.item_id:
                        item.operator_idname = self.operator
                        # Update name from operator if empty or default
                        if item.name in ("New Item", f"Item {len(pie_menu.items)}"):
                            try:
                                op = getattr(getattr(bpy.ops, self.operator.split('.')[0]), self.operator.split('.')[1])
                                rna_type = op.get_rna_type()
                                if rna_type and rna_type.name:
                                    item.name = rna_type.name
                            except:
                                pass
                        bpy.ops.wm.save_userpref()
                        return {'FINISHED'}

        return {'CANCELLED'}

    def invoke(self, context, event):
        context.window_manager.invoke_search_popup(self)
        return {'FINISHED'}


class QP_OT_SelectSmartAction(Operator):
    """Select a smart action for a pie menu item"""
    bl_idname = "qp.select_smart_action"
    bl_label = "Select Smart Action"
    bl_property = "action"

    menu_id: StringProperty()
    item_id: StringProperty()

    action: EnumProperty(
        name="Action",
        items=lambda self, context: QP_OT_SelectSmartAction.get_action_items(self, context)
    )

    @staticmethod
    def get_action_items(self, context):
        """Return smart actions as enum items"""
        items = []
        for action_id, action_data in SMART_ACTIONS.items():
            items.append((action_id, action_data['name'], action_data['description'], action_data.get('icon', 'DOT'), len(items)))
        items.sort(key=lambda x: x[1])  # Sort alphabetically by name
        return items

    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences

        for pie_menu in prefs.custom_pie_menus:
            if pie_menu.id == self.menu_id:
                for item in pie_menu.items:
                    if item.id == self.item_id:
                        item.smart_action_id = self.action
                        # Update name from action if default
                        if item.name in ("New Item", f"Item {len(pie_menu.items)}"):
                            action_data = SMART_ACTIONS.get(self.action)
                            if action_data:
                                item.name = action_data['name']
                        # Enable all contexts by default
                        item.smart_action_contexts = ""
                        bpy.ops.wm.save_userpref()
                        return {'FINISHED'}

        return {'CANCELLED'}

    def invoke(self, context, event):
        context.window_manager.invoke_search_popup(self)
        return {'FINISHED'}


class QP_OT_SelectSmartToggle(Operator):
    """Select a smart toggle for a pie menu item"""
    bl_idname = "qp.select_smart_toggle"
    bl_label = "Select Smart Toggle"
    bl_property = "toggle"

    menu_id: StringProperty()
    item_id: StringProperty()

    toggle: EnumProperty(
        name="Toggle",
        items=lambda self, context: QP_OT_SelectSmartToggle.get_toggle_items(self, context)
    )

    @staticmethod
    def get_toggle_items(self, context):
        """Return smart toggles as enum items"""
        items = []
        for toggle_id, toggle_data in SMART_TOGGLES.items():
            items.append((toggle_id, toggle_data['name'], toggle_data['description'], toggle_data.get('icon', 'DOT'), len(items)))
        items.sort(key=lambda x: x[1])  # Sort alphabetically by name
        return items

    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences

        for pie_menu in prefs.custom_pie_menus:
            if pie_menu.id == self.menu_id:
                for item in pie_menu.items:
                    if item.id == self.item_id:
                        item.smart_toggle_id = self.toggle
                        # Get toggle data
                        toggle_data = SMART_TOGGLES.get(self.toggle)
                        if toggle_data:
                            # Update name from toggle if default
                            if item.name in ("New Item", f"Item {len(pie_menu.items)}"):
                                item.name = toggle_data['name']
                            # Set the property context and path from toggle data
                            item.property_context = toggle_data['context']
                            item.property_data_path = toggle_data['property']
                            # Set icon if not already set
                            if not item.icon or item.icon == 'NONE':
                                item.icon = toggle_data.get('icon', 'NONE')
                        bpy.ops.wm.save_userpref()
                        return {'FINISHED'}

        return {'CANCELLED'}

    def invoke(self, context, event):
        context.window_manager.invoke_search_popup(self)
        return {'FINISHED'}


class QP_OT_ToggleSmartActionContext(Operator):
    """Toggle a context for a smart action"""
    bl_idname = "qp.toggle_smart_action_context"
    bl_label = "Toggle Context"

    menu_id: StringProperty()
    item_id: StringProperty()
    context_key: StringProperty()

    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences

        for pie_menu in prefs.custom_pie_menus:
            if pie_menu.id == self.menu_id:
                for item in pie_menu.items:
                    if item.id == self.item_id:
                        # Get current enabled contexts
                        if item.smart_action_contexts:
                            enabled = set(item.smart_action_contexts.split(','))
                        else:
                            # Empty means all enabled - get all from action
                            action_data = SMART_ACTIONS.get(item.smart_action_id, {})
                            enabled = set(action_data.get('contexts', {}).keys())

                        # Toggle this context
                        if self.context_key in enabled:
                            enabled.discard(self.context_key)
                        else:
                            enabled.add(self.context_key)

                        item.smart_action_contexts = ','.join(sorted(enabled))
                        bpy.ops.wm.save_userpref()
                        return {'FINISHED'}

        return {'CANCELLED'}


class QP_OT_ExecuteSmartAction(Operator):
    """Execute a context-aware smart action"""
    bl_idname = "qp.execute_smart_action"
    bl_label = "Execute Smart Action"

    action_id: StringProperty(name="Action ID")
    enabled_contexts: StringProperty(name="Enabled Contexts", default="")  # Comma-separated

    def execute(self, context):
        if not self.action_id or self.action_id not in SMART_ACTIONS:
            self.report({'WARNING'}, f"Unknown smart action: {self.action_id}")
            return {'CANCELLED'}

        action_data = SMART_ACTIONS[self.action_id]
        context_key = get_current_context_key(context)

        # Parse enabled contexts (if empty, all are enabled)
        if self.enabled_contexts:
            enabled = set(self.enabled_contexts.split(','))
        else:
            enabled = set(action_data['contexts'].keys())

        # Check if current context is enabled
        if context_key not in enabled:
            self.report({'INFO'}, f"{action_data['name']} not available in this context")
            return {'CANCELLED'}

        # Get the action data for this context
        if context_key not in action_data['contexts']:
            self.report({'INFO'}, f"{action_data['name']} not available in {context_key}")
            return {'CANCELLED'}

        ctx_data = action_data['contexts'][context_key]

        # Check if this is a menu call
        if 'menu' in ctx_data:
            menu_name = ctx_data['menu']
            try:
                bpy.ops.wm.call_menu(name=menu_name)
                return {'FINISHED'}
            except Exception as e:
                self.report({'WARNING'}, f"Failed to open menu {menu_name}: {e}")
                return {'CANCELLED'}

        # Otherwise, execute operator
        op_idname = ctx_data.get('operator')
        if not op_idname:
            self.report({'WARNING'}, f"No operator or menu defined for {context_key}")
            return {'CANCELLED'}

        try:
            parts = op_idname.split('.')
            if len(parts) != 2:
                self.report({'WARNING'}, f"Invalid operator: {op_idname}")
                return {'CANCELLED'}

            op_module = getattr(bpy.ops, parts[0], None)
            if not op_module:
                self.report({'WARNING'}, f"Operator module not found: {parts[0]}")
                return {'CANCELLED'}

            op_func = getattr(op_module, parts[1], None)
            if not op_func:
                self.report({'WARNING'}, f"Operator not found: {op_idname}")
                return {'CANCELLED'}

            # Execute with any predefined properties
            props = ctx_data.get('props', {})
            if props:
                op_func('INVOKE_DEFAULT', **props)
            else:
                op_func('INVOKE_DEFAULT')

            return {'FINISHED'}

        except Exception as e:
            self.report({'WARNING'}, f"Failed to execute {op_idname}: {e}")
            return {'CANCELLED'}


class QP_OT_CaptureShortcut(Operator):
    """Press any key combination to set the shortcut"""
    bl_idname = "qp.capture_shortcut"
    bl_label = "Press a key..."
    bl_options = {'REGISTER', 'INTERNAL'}

    menu_id: StringProperty()
    item_id: StringProperty()

    def execute(self, context):
        return {'FINISHED'}

    def modal(self, context, event):
        # Ignore modifier-only events and mouse events
        if event.type in {'LEFT_SHIFT', 'RIGHT_SHIFT', 'LEFT_CTRL', 'RIGHT_CTRL',
                          'LEFT_ALT', 'RIGHT_ALT', 'OSKEY', 'MOUSEMOVE',
                          'LEFTMOUSE', 'RIGHTMOUSE', 'MIDDLEMOUSE',
                          'WHEELUPMOUSE', 'WHEELDOWNMOUSE', 'TIMER', 'TIMER_REPORT',
                          'INBETWEEN_MOUSEMOVE', 'WINDOW_DEACTIVATE'}:
            return {'RUNNING_MODAL'}

        if event.value == 'PRESS':
            # Capture the key
            prefs = context.preferences.addons[__package__].preferences

            for pie_menu in prefs.custom_pie_menus:
                if pie_menu.id == self.menu_id:
                    for item in pie_menu.items:
                        if item.id == self.item_id:
                            # Handle ESC to cancel/clear
                            if event.type == 'ESC':
                                item.shortcut_key = 'NONE'
                                item.shortcut_ctrl = False
                                item.shortcut_alt = False
                                item.shortcut_shift = False
                                self.report({'INFO'}, "Shortcut cleared")
                            else:
                                item.shortcut_key = event.type
                                item.shortcut_ctrl = event.ctrl
                                item.shortcut_alt = event.alt
                                item.shortcut_shift = event.shift

                                # Format for display
                                parts = []
                                if event.ctrl: parts.append("Ctrl")
                                if event.alt: parts.append("Alt")
                                if event.shift: parts.append("Shift")
                                parts.append(event.type)
                                self.report({'INFO'}, f"Shortcut set: {'+'.join(parts)}")

                            bpy.ops.wm.save_userpref()
                            # Force UI redraw
                            for area in context.screen.areas:
                                area.tag_redraw()
                            return {'FINISHED'}

            return {'CANCELLED'}

        return {'RUNNING_MODAL'}

    def invoke(self, context, event):
        context.window_manager.modal_handler_add(self)
        self.report({'INFO'}, "Press a key combination (ESC to clear)...")
        return {'RUNNING_MODAL'}


class QP_OT_SimulateShortcut(Operator):
    """Simulate a keyboard shortcut by finding and executing the bound operator"""
    bl_idname = "qp.simulate_shortcut"
    bl_label = "Simulate Shortcut"

    key: StringProperty(name="Key")
    ctrl: BoolProperty(name="Ctrl", default=False)
    alt: BoolProperty(name="Alt", default=False)
    shift: BoolProperty(name="Shift", default=False)

    def execute(self, context):
        if self.key == 'NONE' or not self.key:
            self.report({'WARNING'}, "No key assigned")
            return {'CANCELLED'}

        wm = context.window_manager

        # Search through all keyconfigs (user, addon, blender)
        keyconfigs = [wm.keyconfigs.user, wm.keyconfigs.addon, wm.keyconfigs.default]

        # Determine current context to find the most relevant keymap
        space_type = context.space_data.type if context.space_data else 'EMPTY'
        mode = context.mode if hasattr(context, 'mode') else 'OBJECT'

        # Priority keymaps based on context
        priority_km_names = []
        if space_type == 'VIEW_3D':
            if mode == 'EDIT_MESH':
                priority_km_names.extend(['Mesh', 'Edit Mode'])
            elif mode == 'SCULPT':
                priority_km_names.append('Sculpt')
            elif mode in ('PAINT_WEIGHT', 'PAINT_VERTEX', 'PAINT_TEXTURE'):
                priority_km_names.append('Weight Paint' if mode == 'PAINT_WEIGHT' else
                                         'Vertex Paint' if mode == 'PAINT_VERTEX' else 'Image Paint')
            elif mode == 'POSE':
                priority_km_names.append('Pose')
            else:
                priority_km_names.append('Object Mode')
            priority_km_names.append('3D View')
        elif space_type == 'NODE_EDITOR':
            priority_km_names.append('Node Editor')
        elif space_type == 'IMAGE_EDITOR':
            priority_km_names.append('Image')

        priority_km_names.extend(['Screen', 'Window'])

        # Search for matching keymap item
        for kc in keyconfigs:
            if not kc:
                continue

            # First search priority keymaps
            for km_name in priority_km_names:
                km = kc.keymaps.get(km_name)
                if not km:
                    continue

                for kmi in km.keymap_items:
                    if not kmi.active:
                        continue
                    if (kmi.type == self.key and
                        kmi.ctrl == self.ctrl and
                        kmi.alt == self.alt and
                        kmi.shift == self.shift and
                        kmi.value == 'PRESS'):

                        result = self._execute_keymap_item(context, kmi)
                        if result == {'FINISHED'}:
                            return result

            # Then search all keymaps
            for km in kc.keymaps:
                if km.name in priority_km_names:
                    continue  # Already searched

                for kmi in km.keymap_items:
                    if not kmi.active:
                        continue
                    if (kmi.type == self.key and
                        kmi.ctrl == self.ctrl and
                        kmi.alt == self.alt and
                        kmi.shift == self.shift and
                        kmi.value == 'PRESS'):

                        result = self._execute_keymap_item(context, kmi)
                        if result == {'FINISHED'}:
                            return result

        # Format shortcut for error message
        parts = []
        if self.ctrl: parts.append("Ctrl")
        if self.alt: parts.append("Alt")
        if self.shift: parts.append("Shift")
        parts.append(self.key)
        shortcut_str = "+".join(parts)

        self.report({'WARNING'}, f"No operator found for shortcut: {shortcut_str}")
        return {'CANCELLED'}

    def _execute_keymap_item(self, context, kmi):
        """Execute the operator from a keymap item"""
        if not kmi.idname:
            return {'CANCELLED'}

        try:
            parts = kmi.idname.split('.')
            if len(parts) != 2:
                return {'CANCELLED'}

            op_module = getattr(bpy.ops, parts[0], None)
            if not op_module:
                return {'CANCELLED'}

            op_func = getattr(op_module, parts[1], None)
            if not op_func:
                return {'CANCELLED'}

            # Check if operator is available in current context
            if not op_func.poll():
                return {'CANCELLED'}

            # Build properties dict from keymap item
            # Only include simple value types (not pointers or collections)
            props = {}
            if kmi.properties:
                for prop in kmi.properties.bl_rna.properties:
                    if prop.identifier == 'rna_type':
                        continue
                    # Skip pointer and collection properties - they can't be passed as kwargs
                    if prop.type in ('POINTER', 'COLLECTION'):
                        continue
                    try:
                        value = getattr(kmi.properties, prop.identifier)
                        # Only include if it's a simple type
                        if isinstance(value, (bool, int, float, str)) or \
                           (hasattr(value, '__iter__') and not isinstance(value, str) and len(value) <= 4):
                            props[prop.identifier] = value
                    except:
                        pass

            # Execute with INVOKE_DEFAULT for modal operators
            if props:
                op_func('INVOKE_DEFAULT', **props)
            else:
                op_func('INVOKE_DEFAULT')

            return {'FINISHED'}

        except Exception as e:
            print(f"QP_Tools: Could not execute operator {kmi.idname}: {e}")
            return {'CANCELLED'}


# =============================================================================
# UI Drawing Functions
# =============================================================================

def format_keymap_shortcut(pie_menu):
    """Format keymap shortcut for display"""
    if pie_menu.keymap_key == 'NONE':
        return "No shortcut"

    parts = []
    if pie_menu.keymap_ctrl:
        parts.append("Ctrl")
    if pie_menu.keymap_alt:
        parts.append("Alt")
    if pie_menu.keymap_shift:
        parts.append("Shift")
    if pie_menu.keymap_oskey:
        parts.append("OS")
    parts.append(pie_menu.keymap_key)

    return "+".join(parts)


def draw_context_rules_ui(layout, pie_menu, item):
    """Draw the context rules editor for an item"""

    rules_box = layout.box()
    rules_header = rules_box.row()
    rules_header.label(text="Context Rules", icon='FILTER')

    op = rules_header.operator("qp.add_context_rule", text="", icon='ADD')
    op.menu_id = pie_menu.id
    op.item_id = item.id

    if not item.context_rules:
        rules_box.label(text="No rules (always visible)", icon='INFO')
        return

    rules_box.prop(item, "context_match_mode", text="Match")

    for i, rule in enumerate(item.context_rules):
        rule_box = rules_box.box()
        rule_row = rule_box.row(align=True)

        rule_row.prop(rule, "enabled", text="")
        rule_row.prop(rule, "rule_type", text="")

        if rule.rule_type == 'MODE':
            rule_row.prop(rule, "mode_filter", text="")
        elif rule.rule_type == 'OBJECT_TYPE':
            rule_row.prop(rule, "object_type_filter", text="")
        elif rule.rule_type == 'SPACE_TYPE':
            rule_row.prop(rule, "space_type_filter", text="")

        rule_row.prop(rule, "invert", text="", icon='ARROW_LEFTRIGHT', toggle=True)

        op = rule_row.operator("qp.remove_context_rule", text="", icon='X')
        op.menu_id = pie_menu.id
        op.item_id = item.id
        op.rule_index = i


class QP_OT_SetPieItemPosition(Operator):
    """Set the pie menu position for this item"""
    bl_idname = "qp.set_pie_item_position"
    bl_label = "Set Pie Position"
    bl_options = {'REGISTER', 'UNDO'}
    bl_property = "position"

    menu_id: StringProperty(name="Menu ID")
    item_id: StringProperty(name="Item ID")
    position: EnumProperty(
        name="Position",
        items=[
            ('-1', "Auto", "Automatically assign position"),
            ('0', "West", "Left"),
            ('1', "East", "Right"),
            ('2', "South", "Bottom"),
            ('3', "North", "Top"),
            ('4', "NW", "Top-Left"),
            ('5', "NE", "Top-Right"),
            ('6', "SW", "Bottom-Left"),
            ('7', "SE", "Bottom-Right"),
        ],
        default='-1',
    )

    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences
        for pie_menu in prefs.custom_pie_menus:
            if pie_menu.id == self.menu_id:
                for item in pie_menu.items:
                    if item.id == self.item_id:
                        item.pie_position = int(self.position)
                        return {'FINISHED'}
        self.report({'WARNING'}, "Item not found")
        return {'CANCELLED'}

    def invoke(self, context, event):
        context.window_manager.invoke_search_popup(self)
        return {'CANCELLED'}


_PIE_POSITION_ICONS = {
    0: 'TRIA_LEFT',      # W
    1: 'TRIA_RIGHT',     # E
    2: 'TRIA_DOWN',      # S
    3: 'TRIA_UP',        # N
    4: 'TRIA_LEFT',      # NW
    5: 'TRIA_RIGHT',     # NE
    6: 'TRIA_LEFT',      # SW
    7: 'TRIA_RIGHT',     # SE
}

_PIE_POSITION_NAMES = {
    -1: "Auto", 0: "W", 1: "E", 2: "S", 3: "N",
    4: "NW", 5: "NE", 6: "SW", 7: "SE",
}


def _compute_item_positions(pie_menu):
    """Return a dict mapping item.id -> effective pie position index."""
    position_items = {i: None for i in range(8)}
    unpositioned = []

    for item in pie_menu.items:
        if 0 <= item.pie_position <= 7:
            if position_items[item.pie_position] is None:
                position_items[item.pie_position] = item.id
            else:
                unpositioned.append(item.id)
        else:
            unpositioned.append(item.id)

    for i in range(8):
        if position_items[i] is None and unpositioned:
            position_items[i] = unpositioned.pop(0)

    # Invert: id -> position
    return {item_id: pos for pos, item_id in position_items.items() if item_id is not None}


def draw_pie_item_editor(layout, pie_menu, item, index, effective_position=None):
    """Draw the editor for a single pie menu item"""

    item_box = layout.box()

    # Header row
    header = item_box.row(align=True)

    # Expand toggle
    icon = 'TRIA_DOWN' if item.expanded else 'TRIA_RIGHT'
    op = header.operator("qp.toggle_pie_item_expanded", text="", icon=icon, emboss=False)
    op.menu_id = pie_menu.id
    op.item_id = item.id

    header.prop(item, "enabled", text="")

    # Position button — shows current direction, click to change
    if effective_position is not None:
        pos_name = _PIE_POSITION_NAMES.get(item.pie_position, "Auto")
        sub = header.row(align=True)
        sub.scale_x = 0.5
        op = sub.operator("qp.set_pie_item_position", text=pos_name)
        op.menu_id = pie_menu.id
        op.item_id = item.id

    header.prop(item, "name", text="")

    # Icon picker button (visual popup)
    item_icon = item.icon if item.icon and item.icon != 'NONE' else 'DOT'
    op = header.operator("qp.pick_icon", text="", icon=item_icon)
    op.menu_id = pie_menu.id
    op.item_id = item.id
    op.target = "item"

    # Move buttons only (no position number)
    op = header.operator("qp.move_pie_menu_item", text="", icon='TRIA_UP')
    op.menu_id = pie_menu.id
    op.item_id = item.id
    op.direction = 'UP'

    op = header.operator("qp.move_pie_menu_item", text="", icon='TRIA_DOWN')
    op.menu_id = pie_menu.id
    op.item_id = item.id
    op.direction = 'DOWN'

    # Remove button
    op = header.operator("qp.remove_pie_menu_item", text="", icon='X')
    op.menu_id = pie_menu.id
    op.item_id = item.id

    if not item.expanded:
        return

    # Action type
    item_box.prop(item, "action_type")

    # Action-specific settings
    if item.action_type == 'SMART_ACTION':
        # Smart action selector
        row = item_box.row(align=True)
        action_data = SMART_ACTIONS.get(item.smart_action_id)
        action_name = action_data['name'] if action_data else "Select Action..."
        action_icon = action_data.get('icon', 'DOT') if action_data else 'DOT'
        op = row.operator("qp.select_smart_action", text=action_name, icon=action_icon)
        op.menu_id = pie_menu.id
        op.item_id = item.id

        # Show available contexts with toggles
        if item.smart_action_id and action_data:
            ctx_box = item_box.box()
            ctx_box.label(text="Enabled Modes:", icon='FILTER')

            # Parse current enabled contexts
            if item.smart_action_contexts:
                enabled_contexts = set(item.smart_action_contexts.split(','))
            else:
                enabled_contexts = set(action_data['contexts'].keys())

            # Show toggles for each available context
            ctx_col = ctx_box.column(align=True)
            for ctx_key, ctx_data in action_data['contexts'].items():
                row = ctx_col.row(align=True)
                is_enabled = ctx_key in enabled_contexts
                icon = 'CHECKBOX_HLT' if is_enabled else 'CHECKBOX_DEHLT'
                op = row.operator("qp.toggle_smart_action_context", text=ctx_data['label'],
                                  icon=icon, depress=is_enabled)
                op.menu_id = pie_menu.id
                op.item_id = item.id
                op.context_key = ctx_key

    elif item.action_type == 'OPERATOR':
        row = item_box.row(align=True)
        row.prop(item, "operator_idname", text="Operator")
        # Search operator button
        op = row.operator("qp.search_operator", text="", icon='VIEWZOOM')
        op.menu_id = pie_menu.id
        op.item_id = item.id

        if item.operator_idname:
            item_box.prop(item, "operator_props", text="Properties (JSON)")

    elif item.action_type == 'SHORTCUT':
        # Shortcut settings - native-style key capture
        row = item_box.row(align=True)

        # Format current shortcut for display
        if item.shortcut_key and item.shortcut_key != 'NONE':
            parts = []
            if item.shortcut_ctrl: parts.append("Ctrl")
            if item.shortcut_alt: parts.append("Alt")
            if item.shortcut_shift: parts.append("Shift")
            parts.append(item.shortcut_key)
            shortcut_text = " + ".join(parts)
        else:
            shortcut_text = "Click to set..."

        # Key capture button
        op = row.operator("qp.capture_shortcut", text=shortcut_text, icon='EVENT_RETURN')
        op.menu_id = pie_menu.id
        op.item_id = item.id

        # Clear button
        if item.shortcut_key and item.shortcut_key != 'NONE':
            clear_op = row.operator("qp.capture_shortcut", text="", icon='X')
            clear_op.menu_id = pie_menu.id
            clear_op.item_id = item.id

    elif item.action_type == 'PROPERTY_TOGGLE':
        # Smart toggle selector
        row = item_box.row(align=True)
        toggle_data = SMART_TOGGLES.get(item.smart_toggle_id)
        toggle_name = toggle_data['name'] if toggle_data else "Select Toggle..."
        toggle_icon = toggle_data.get('icon', 'DOT') if toggle_data else 'DOT'
        op = row.operator("qp.select_smart_toggle", text=toggle_name, icon=toggle_icon)
        op.menu_id = pie_menu.id
        op.item_id = item.id

        # Show manual configuration option
        manual_box = item_box.box()
        manual_box.label(text="Manual Override:", icon='PREFERENCES')
        manual_box.prop(item, "property_context", text="Context")
        manual_box.prop(item, "property_data_path", text="Property")

    # Context rules
    draw_context_rules_ui(item_box, pie_menu, item)


def draw_pie_menu_editor(layout, pie_menu, context):
    """Draw the editor UI for a single pie menu"""

    main_box = layout.box()

    # Header row
    header = main_box.row(align=True)

    # Expand/collapse toggle
    icon = 'TRIA_DOWN' if pie_menu.expanded else 'TRIA_RIGHT'
    header.prop(pie_menu, "expanded", text="", icon=icon, emboss=False)

    # Enabled toggle
    header.prop(pie_menu, "enabled", text="")

    # Menu name
    header.prop(pie_menu, "name", text="")

    # Actions
    exp_op = header.operator("qp.export_pie_menus", text="", icon='EXPORT')
    exp_op.export_mode = 'SELECTED'
    exp_op.menu_id = pie_menu.id

    op = header.operator("qp.duplicate_custom_pie_menu", text="", icon='DUPLICATE')
    op.menu_id = pie_menu.id

    op = header.operator("qp.move_custom_pie_menu", text="", icon='TRIA_UP')
    op.menu_id = pie_menu.id
    op.direction = 'UP'

    op = header.operator("qp.move_custom_pie_menu", text="", icon='TRIA_DOWN')
    op.menu_id = pie_menu.id
    op.direction = 'DOWN'

    op = header.operator("qp.remove_custom_pie_menu", text="", icon='X')
    op.menu_id = pie_menu.id

    if not pie_menu.expanded:
        return

    # Keymap settings - use native Blender keymap UI
    keymap_box = main_box.box()
    keymap_box.label(text="Shortcut", icon='KEYINGSET')

    # Try to find or create the keymap item
    wm = context.window_manager
    kc_user = wm.keyconfigs.user
    kc_addon = wm.keyconfigs.addon

    kmi_found = None
    km_found = None

    if pie_menu.id:
        # Get the keymap name based on space type
        km_name = PieMenuKeymapManager.get_keymap_name(pie_menu.keymap_space)

        # First check user keyconfig
        if kc_user:
            km_user = kc_user.keymaps.get(km_name)
            if km_user:
                for kmi in km_user.keymap_items:
                    if (kmi.idname == "qp.call_custom_pie_menu" and
                        hasattr(kmi.properties, 'menu_id') and
                        kmi.properties.menu_id == pie_menu.id):
                        kmi_found = kmi
                        km_found = km_user
                        break

        # If not found in user, check/create in addon keyconfig
        if not kmi_found and kc_addon:
            km_addon = kc_addon.keymaps.get(km_name)
            if not km_addon:
                space_type = pie_menu.keymap_space if pie_menu.keymap_space != 'EMPTY' else 'EMPTY'
                try:
                    km_addon = kc_addon.keymaps.new(name=km_name, space_type=space_type)
                except:
                    km_addon = None

            if km_addon:
                # Look for existing keymap item
                for kmi in km_addon.keymap_items:
                    if (kmi.idname == "qp.call_custom_pie_menu" and
                        hasattr(kmi.properties, 'menu_id') and
                        kmi.properties.menu_id == pie_menu.id):
                        kmi_found = kmi
                        km_found = km_addon
                        break

                # Create one if not found
                if not kmi_found:
                    try:
                        kmi = km_addon.keymap_items.new(
                            "qp.call_custom_pie_menu",
                            'NONE',  # Start with no key assigned
                            'PRESS'
                        )
                        kmi.properties.menu_id = pie_menu.id
                        kmi_found = kmi
                        km_found = km_addon
                        # Also store reference
                        PieMenuKeymapManager._registered_keymaps[pie_menu.id] = (km_addon, kmi)
                    except Exception as e:
                        print(f"QP_Tools: Failed to create keymap item: {e}")

    if kmi_found and km_found:
        # Draw using native keymap UI
        col = keymap_box.column()
        col.context_pointer_set('keymap', km_found)
        # Use user keyconfig for drawing if available, otherwise addon
        kc_for_draw = kc_user if kc_user else kc_addon
        rna_keymap_ui.draw_kmi([], kc_for_draw, km_found, kmi_found, col, 0)
    else:
        # Ultimate fallback - should rarely happen
        keymap_box.label(text="Could not create keymap. Try restarting Blender.", icon='ERROR')

    # Items section
    items_box = main_box.box()
    items_header = items_box.row()
    items_header.label(text="Menu Items", icon='PRESET')

    add_row = items_header.row()
    add_row.enabled = len(pie_menu.items) < 8
    op = add_row.operator("qp.add_pie_menu_item", text="", icon='ADD')
    op.menu_id = pie_menu.id

    if not pie_menu.items:
        items_box.label(text="No items. Click + to add one.")
    else:
        # Compute effective pie positions for all items
        item_positions = _compute_item_positions(pie_menu)
        for i, item in enumerate(pie_menu.items):
            draw_pie_item_editor(items_box, pie_menu, item, i, item_positions.get(item.id))

    # Preview button
    if pie_menu.items:
        preview_row = main_box.row()
        preview_row.scale_y = 1.3
        preview_row.operator(
            "wm.call_menu_pie",
            text="Preview Menu",
            icon='PLAY'
        ).name = f"QP_MT_custom_pie_{pie_menu.id}"


def draw_pie_builder_preferences(preferences, context, layout):
    """Draw the Pie Menu Builder preferences UI"""

    if not preferences.pie_menu_builder_enabled:
        layout.label(text="Pie Menu Builder is disabled.", icon='INFO')
        layout.label(text="Enable it in the Core Modules tab first.")
        layout.operator("qp.show_core_modules_tab", text="Go to Core Modules Tab")
        return

    # Header with Add / Import / Export buttons
    header = layout.row()
    header.label(text="Custom Pie Menus", icon='MENU_PANEL')
    header.operator("qp.add_custom_pie_menu", text="Add New", icon='ADD')
    header.operator("qp.import_pie_menus", text="Import", icon='IMPORT')
    op = header.operator("qp.export_pie_menus", text="Export", icon='EXPORT')
    op.export_mode = 'ALL'

    # List of pie menus
    if not preferences.custom_pie_menus:
        box = layout.box()
        box.label(text="No custom pie menus. Click 'Add New' to create one.")
        return

    for pie_menu in preferences.custom_pie_menus:
        draw_pie_menu_editor(layout, pie_menu, context)


# =============================================================================
# Import / Export
# =============================================================================

def _serialize_pie_menu(pie_menu):
    """Serialize a single QP_CustomPieMenu to a dict."""
    items = []
    for item in pie_menu.items:
        rules = []
        for rule in item.context_rules:
            rules.append({
                'enabled': rule.enabled,
                'rule_type': rule.rule_type,
                'mode_filter': rule.mode_filter,
                'object_type_filter': rule.object_type_filter,
                'space_type_filter': rule.space_type_filter,
                'invert': rule.invert,
            })
        items.append({
            'name': item.name,
            'icon': item.icon,
            'enabled': item.enabled,
            'action_type': item.action_type,
            'pie_position': item.pie_position,
            'smart_action_id': item.smart_action_id,
            'smart_action_contexts': item.smart_action_contexts,
            'operator_idname': item.operator_idname,
            'operator_props': item.operator_props,
            'shortcut_key': item.shortcut_key,
            'shortcut_ctrl': item.shortcut_ctrl,
            'shortcut_alt': item.shortcut_alt,
            'shortcut_shift': item.shortcut_shift,
            'smart_toggle_id': item.smart_toggle_id,
            'property_data_path': item.property_data_path,
            'property_context': item.property_context,
            'context_match_mode': item.context_match_mode,
            'context_rules': rules,
        })
    return {
        'name': pie_menu.name,
        'icon': pie_menu.icon,
        'enabled': pie_menu.enabled,
        'keymap': {
            'key': pie_menu.keymap_key,
            'ctrl': pie_menu.keymap_ctrl,
            'alt': pie_menu.keymap_alt,
            'shift': pie_menu.keymap_shift,
            'oskey': pie_menu.keymap_oskey,
            'space': pie_menu.keymap_space,
        },
        'items': items,
    }


def _deserialize_pie_menu(data, target_menu):
    """Populate a QP_CustomPieMenu from a dict."""
    target_menu.id = str(uuid.uuid4())[:8]
    target_menu.name = data.get('name', 'Imported Menu')
    target_menu.icon = data.get('icon', 'NONE')
    target_menu.enabled = data.get('enabled', True)

    km = data.get('keymap', {})
    target_menu.keymap_key = km.get('key', 'NONE')
    target_menu.keymap_ctrl = km.get('ctrl', False)
    target_menu.keymap_alt = km.get('alt', False)
    target_menu.keymap_shift = km.get('shift', False)
    target_menu.keymap_oskey = km.get('oskey', False)
    target_menu.keymap_space = km.get('space', 'VIEW_3D')

    for item_data in data.get('items', []):
        new_item = target_menu.items.add()
        new_item.id = str(uuid.uuid4())[:8]
        new_item.name = item_data.get('name', 'Item')
        new_item.icon = item_data.get('icon', 'NONE')
        new_item.enabled = item_data.get('enabled', True)
        new_item.action_type = item_data.get('action_type', 'SMART_ACTION')
        new_item.pie_position = item_data.get('pie_position', -1)
        new_item.smart_action_id = item_data.get('smart_action_id', '')
        new_item.smart_action_contexts = item_data.get('smart_action_contexts', '')
        new_item.operator_idname = item_data.get('operator_idname', '')
        new_item.operator_props = item_data.get('operator_props', '{}')
        new_item.shortcut_key = item_data.get('shortcut_key', 'NONE')
        new_item.shortcut_ctrl = item_data.get('shortcut_ctrl', False)
        new_item.shortcut_alt = item_data.get('shortcut_alt', False)
        new_item.shortcut_shift = item_data.get('shortcut_shift', False)
        new_item.smart_toggle_id = item_data.get('smart_toggle_id', '')
        new_item.property_data_path = item_data.get('property_data_path', '')
        new_item.property_context = item_data.get('property_context', 'TOOL_SETTINGS')
        new_item.context_match_mode = item_data.get('context_match_mode', 'ANY')

        for rule_data in item_data.get('context_rules', []):
            new_rule = new_item.context_rules.add()
            new_rule.enabled = rule_data.get('enabled', True)
            new_rule.rule_type = rule_data.get('rule_type', 'MODE')
            new_rule.mode_filter = rule_data.get('mode_filter', 'OBJECT')
            new_rule.object_type_filter = rule_data.get('object_type_filter', 'MESH')
            new_rule.space_type_filter = rule_data.get('space_type_filter', 'VIEW_3D')
            new_rule.invert = rule_data.get('invert', False)


class QP_OT_ExportPieMenus(Operator, ExportHelper):
    """Export pie menus to a JSON file"""
    bl_idname = "qp.export_pie_menus"
    bl_label = "Export Pie Menus"

    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={'HIDDEN'})

    export_mode: EnumProperty(
        name="Export",
        items=[
            ('ALL', "All Menus", "Export all custom pie menus"),
            ('SELECTED', "Selected Menu", "Export only the currently selected menu"),
        ],
        default='ALL',
    )

    menu_id: StringProperty(name="Menu ID", options={'HIDDEN'})

    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences
        menus = []

        if self.export_mode == 'SELECTED' and self.menu_id:
            for pie_menu in prefs.custom_pie_menus:
                if pie_menu.id == self.menu_id:
                    menus.append(_serialize_pie_menu(pie_menu))
                    break
            if not menus:
                self.report({'WARNING'}, "Selected pie menu not found")
                return {'CANCELLED'}
        else:
            for pie_menu in prefs.custom_pie_menus:
                menus.append(_serialize_pie_menu(pie_menu))

        if not menus:
            self.report({'WARNING'}, "No pie menus to export")
            return {'CANCELLED'}

        payload = {
            'version': '1.0',
            'addon_version': '2.2.0',
            'pie_menus': menus,
        }

        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.report({'ERROR'}, f"Failed to write file: {e}")
            return {'CANCELLED'}

        count = len(menus)
        self.report({'INFO'}, f"Exported {count} pie menu{'s' if count != 1 else ''}")
        return {'FINISHED'}


class QP_OT_ImportPieMenus(Operator, ImportHelper):
    """Import pie menus from a JSON file"""
    bl_idname = "qp.import_pie_menus"
    bl_label = "Import Pie Menus"

    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={'HIDDEN'})

    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences

        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                payload = json.load(f)
        except Exception as e:
            self.report({'ERROR'}, f"Failed to read file: {e}")
            return {'CANCELLED'}

        if not isinstance(payload, dict) or 'pie_menus' not in payload:
            self.report({'ERROR'}, "Invalid pie menu file format")
            return {'CANCELLED'}

        imported = 0
        for menu_data in payload['pie_menus']:
            new_menu = prefs.custom_pie_menus.add()
            _deserialize_pie_menu(menu_data, new_menu)
            register_dynamic_menu(new_menu)
            PieMenuKeymapManager.refresh_pie_menu_keymap(new_menu)
            imported += 1

        if imported:
            bpy.ops.wm.save_userpref()

        self.report({'INFO'}, f"Imported {imported} pie menu{'s' if imported != 1 else ''}")
        return {'FINISHED'}


# =============================================================================
# Registration
# =============================================================================

classes = [
    QP_OT_AddCustomPieMenu,
    QP_OT_RemoveCustomPieMenu,
    QP_OT_DuplicateCustomPieMenu,
    QP_OT_MoveCustomPieMenu,
    QP_OT_AddPieMenuItem,
    QP_OT_RemovePieMenuItem,
    QP_OT_MovePieMenuItem,
    QP_OT_AddContextRule,
    QP_OT_RemoveContextRule,
    QP_OT_CallCustomPieMenu,
    QP_OT_CycleEnumProperty,
    QP_OT_TogglePieItemExpanded,
    QP_OT_PickIcon,
    QP_OT_SetIconValue,
    QP_OT_SearchOperator,
    QP_OT_SelectSmartAction,
    QP_OT_SelectSmartToggle,
    QP_OT_ToggleSmartActionContext,
    QP_OT_ExecuteSmartAction,
    QP_OT_CaptureShortcut,
    QP_OT_SimulateShortcut,
    QP_OT_SetPieItemPosition,
    QP_OT_ExportPieMenus,
    QP_OT_ImportPieMenus,
]


@bpy.app.handlers.persistent
def _on_load_post(_):
    """Re-register pie menu keymaps after a file is loaded (including startup file)."""
    refresh_all_dynamic_menus()
    PieMenuKeymapManager.ensure_addon_keymaps()


def register():
    global _is_registered

    if not ModuleManager.register_module(sys.modules[__name__]):
        return

    # Register operators
    for cls in classes:
        ModuleManager.safe_register_class(cls)

    _is_registered = True

    # After a short delay, create addon keymap entries for all pie menus
    # so Blender can apply saved user shortcuts from kc_user.
    def delayed_init():
        refresh_all_dynamic_menus()
        PieMenuKeymapManager.ensure_addon_keymaps()
        return None

    bpy.app.timers.register(delayed_init, first_interval=0.5)

    # Also register a load_post handler so keymaps are restored
    # after every file load (including the initial startup file)
    if _on_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_load_post)


def unregister():
    global _is_registered

    if not ModuleManager.unregister_module(sys.modules[__name__]):
        return

    # Remove load_post handler
    if _on_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load_post)

    # Unregister keymaps
    PieMenuKeymapManager.unregister_all()

    # Unregister dynamic menus
    for menu_id in list(_dynamic_menu_classes.keys()):
        unregister_dynamic_menu(menu_id)

    # Unregister classes in reverse order
    for cls in reversed(classes):
        ModuleManager.safe_unregister_class(cls)

    _is_registered = False


if __name__ == "__main__":
    register()
