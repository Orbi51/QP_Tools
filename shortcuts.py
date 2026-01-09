import bpy
from bpy.props import StringProperty
import rna_keymap_ui # Import for drawing native keymap UI

# Keymap definitions
KEYMAP_DEFS = [
    {
        "idname": "qp.call_asset_menu",
        "name": "Tools Asset Pie Menu (QP)", 
        "km_name": "3D View", 
        "space_type": "VIEW_3D", 
        "region_type": "WINDOW", 
        "key": "ONE", 
        "ctrl": True, 
        "alt": True,  
        "shift": False, 
        "oskey": False, 
    },
    {
        "idname": "qp.call_asset_library_menu",
        "name": "Asset Browser Pie Menu (QP)", 
        "km_name": "3D View",
        "space_type": "VIEW_3D",
        "region_type": "WINDOW",
        "key": "TWO",
        "ctrl": True,
        "alt": True,
        "shift": False,
        "oskey": False,
    },
]

def register_keymaps():
    """
    Registers keymap items defined in KEYMAP_DEFS to the ADDON's keyconfig
    if they don't already exist there. This establishes the addon's defaults.
    """
    wm = bpy.context.window_manager
    kc_addon = wm.keyconfigs.addon 
    
    if not kc_addon:
        # This is a critical failure for the addon's keymap setup.
        print("QP_Tools: CRITICAL - Addon keyconfig (wm.keyconfigs.addon) not available. Cannot register default keymaps.")
        return
    
    for keymap_def in KEYMAP_DEFS:
        km_name = keymap_def["km_name"]
        
        km = kc_addon.keymaps.get(km_name)
        if not km:
            try:
                km = kc_addon.keymaps.new(name=km_name, space_type=keymap_def["space_type"])
                # print(f"QP_Tools: Created keymap '{km_name}' in ADDON keyconfigs.") # Informational
            except Exception as e:
                print(f"QP_Tools: ERROR - Failed to create keymap '{km_name}' in ADDON keyconfigs: {e}")
                continue # Skip to next keymap_def if keymap creation fails

        found_existing_kmi_in_addon_config = False
        if km: #Proceed only if keymap 'km' exists or was successfully created
            for kmi in km.keymap_items:
                if kmi.idname == keymap_def["idname"]:
                    if (kmi.type == keymap_def["key"] and
                        kmi.ctrl == keymap_def.get("ctrl", False) and
                        kmi.alt == keymap_def.get("alt", False) and
                        kmi.shift == keymap_def.get("shift", False) and
                        kmi.oskey == keymap_def.get("oskey", False)):
                        # print(f"QP_Tools: Default keymap item for '{keymap_def['name']}' already exists in ADDON keyconfig ('{km_name}').") # Informational
                        found_existing_kmi_in_addon_config = True
                        break 
            
            if not found_existing_kmi_in_addon_config:
                try:
                    kmi = km.keymap_items.new(
                        keymap_def["idname"],
                        keymap_def["key"],
                        'PRESS', 
                        ctrl=keymap_def.get("ctrl", False),
                        alt=keymap_def.get("alt", False),
                        shift=keymap_def.get("shift", False),
                        oskey=keymap_def.get("oskey", False)
                    )
                    # print(f"QP_Tools: Created default keymap item for operator '{keymap_def['idname']}' in ADDON keyconfig ('{km_name}').") # Informational
                except Exception as e:
                    print(f"QP_Tools: ERROR - Failed to create keymap item for '{keymap_def['name']}' in ADDON keyconfig: {e}")

def unregister_keymaps():
    """
    Called when the addon is unregistered.
    Does not remove keymaps from user's active config to preserve customizations.
    """
    # print("QP_Tools: unregister_keymaps called.") # Informational

def format_key_combination(keymap_def):
    """Helper to format a key combination string from a keymap definition."""
    parts = []
    if keymap_def.get("ctrl"): parts.append("Ctrl")
    if keymap_def.get("alt"): parts.append("Alt")
    if keymap_def.get("shift"): parts.append("Shift")
    if keymap_def.get("oskey"): parts.append("Cmd" if bpy.app.platform == 'DARWIN' else "Win")
    parts.append(keymap_def.get("key", "UNKNOWN_KEY"))
    return "+".join(parts)

# Removed format_key_from_kmi as it's not strictly needed for the current functionality
# If it were needed for display purposes elsewhere, it could be kept.

def draw_keymap_ui(context, layout, shortcut_id=None):
    """
    Draws the UI for managing keymaps. It queries the USER's keyconfig
    and displays items using Blender's native rna_keymap_ui.draw_kmi().
    """
    wm = context.window_manager
    kc_user = wm.keyconfigs.user 

    if not kc_user:
        layout.label(text="USER keyconfig not available.", icon='ERROR')
        return

    keymap_defs_to_draw = []
    if shortcut_id:
        op_idname_for_shortcut = None
        if shortcut_id == "asset_pie":
            op_idname_for_shortcut = "qp.call_asset_menu"
        elif shortcut_id == "asset_library_pie":
            op_idname_for_shortcut = "qp.call_asset_library_menu"
        
        if op_idname_for_shortcut:
            for km_def in KEYMAP_DEFS:
                if km_def["idname"] == op_idname_for_shortcut:
                    keymap_defs_to_draw.append(km_def)
                    break
    else: # If no specific shortcut_id, prepare to draw all
        keymap_defs_to_draw = KEYMAP_DEFS

    if not keymap_defs_to_draw and shortcut_id: # Only show error if a specific (but unknown) shortcut_id was given
        layout.label(text=f"Unknown shortcut ID: {shortcut_id}", icon='ERROR')
        return
    if not KEYMAP_DEFS: # If there are no definitions at all
        layout.label(text="No keymap definitions found in the addon.", icon='INFO')
        return


    # Only show this label if we are drawing UI for specific shortcuts (not the general "Reset All" view)
    if shortcut_id:
        layout.label(text=f"Keybinding from USER keyconfig: '{kc_user.name}'") 

    for keymap_def in keymap_defs_to_draw:
        descriptive_op_name = keymap_def['name']
        km_user = kc_user.keymaps.get(keymap_def["km_name"])
        
        op_ui_container = layout
        # If drawing for a single shortcut, use the passed layout directly.
        # If drawing all (shortcut_id is None), create a box for each.
        if not shortcut_id: 
            op_ui_container = layout.box()
            op_ui_container.label(text=f"Operator: {descriptive_op_name}") 
        
        found_kmis_for_this_operator_in_user = []
        if km_user: 
            for kmi in km_user.keymap_items:
                if kmi.idname == keymap_def["idname"]:
                    found_kmis_for_this_operator_in_user.append(kmi)
        
        if found_kmis_for_this_operator_in_user:
            if not shortcut_id: # Only add this label if we are in the "all shortcuts" view inside a box
                 op_ui_container.label(text=f"Current Binding(s) for '{descriptive_op_name}':")
            for kmi_to_draw in found_kmis_for_this_operator_in_user:
                col = op_ui_container.column() 
                col.context_pointer_set('keymap', km_user) 
                rna_keymap_ui.draw_kmi([], kc_user, km_user, kmi_to_draw, col, 0)
        else:
            no_kmi_box = op_ui_container.box()
            no_kmi_box.alert = True 
            no_kmi_box.label(text=f"No active keybinding for '{descriptive_op_name}' found in USER keyconfig ('{kc_user.name}').", icon='INFO')
            no_kmi_box.label(text=f"Addon Default: {format_key_combination(keymap_def)}")
            add_op = no_kmi_box.operator(QP_OT_RecreateShortcuts.bl_idname, text=f"Add Default for '{descriptive_op_name}'", icon='ADD')
            add_op.operator_idname_filter = keymap_def["idname"]
            add_op.force_add_if_missing = True 

    # Only show "Reset All" button if we are drawing the UI for all shortcuts (shortcut_id is None)
    # and if there are keymap definitions to reset.
    if not shortcut_id and KEYMAP_DEFS: 
        reset_op_layout = layout.row(align=True)
        reset_op_layout.scale_y = 1.2 
        op = reset_op_layout.operator(QP_OT_RecreateShortcuts.bl_idname, text="Reset All Addon Shortcuts in User Config to Defaults", icon='FILE_REFRESH')
        op.operator_idname_filter = "" # Empty filter means all
        op.force_add_if_missing = False # Standard reset behavior

class QP_OT_RecreateShortcuts(bpy.types.Operator):
    bl_idname = "qp.recreate_shortcuts"
    bl_label = "Reset/Add Addon Shortcut(s) in User Config" 
    bl_description = "Resets existing or adds missing keybindings for this addon's operators in your USER keyconfig to the addon's defaults."
    bl_options = {'REGISTER', 'UNDO'}

    operator_idname_filter: StringProperty(
        name="Operator IDName Filter",
        description="If set, only reset/add keymap for this specific operator IDName. If empty, reset/add all addon keymaps.",
        default="" 
    )
    force_add_if_missing: bpy.props.BoolProperty(
        name="Force Add if Missing",
        description="If true, this operation will add the keymap if it's missing, rather than just resetting an existing one.",
        default=False
    )

    @classmethod
    def description(cls, context, properties):
        action = "Add default for" if properties.force_add_if_missing else "Reset"
        if properties.operator_idname_filter:
            op_name = properties.operator_idname_filter
            for km_def in KEYMAP_DEFS:
                if km_def["idname"] == properties.operator_idname_filter:
                    op_name = km_def["name"] 
                    break
            return f"{action} '{op_name}' in your USER keyconfig to addon's default."
        return f"{action} all defined QP_Tools shortcuts in your USER keyconfig to addon's defaults."

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)
    
    def draw(self, context):
        layout = self.layout
        action_text = "add the default keybinding" if self.force_add_if_missing else "reset the keybinding(s)"
        
        layout.label(text=f"Are you sure you want to {action_text}?", icon='QUESTION')
        if self.operator_idname_filter:
            op_name = self.operator_idname_filter
            for km_def in KEYMAP_DEFS: 
                if km_def["idname"] == self.operator_idname_filter:
                    op_name = km_def["name"] 
                    break
            layout.label(text=f"This will affect '{op_name}' ({self.operator_idname_filter}) in your USER keyconfig.")
        else:
            layout.label(text="This will affect all QP_Tools shortcuts in your USER keyconfig.")
        layout.separator()
        if not self.force_add_if_missing:
            layout.label(text="Any user customizations for the targeted shortcut(s) in your USER keyconfig will be lost!")
        else:
            layout.label(text="The addon's default binding will be added to your USER keyconfig.")

    def execute(self, context):
        wm = context.window_manager
        kc_user = wm.keyconfigs.user 
        if not kc_user:
            self.report({'WARNING'}, "USER keyconfig not available. Cannot perform operation.")
            return {'CANCELLED'}

        defs_to_process = []
        if self.operator_idname_filter:
            for keymap_def in KEYMAP_DEFS:
                if keymap_def["idname"] == self.operator_idname_filter:
                    defs_to_process.append(keymap_def)
                    break
            if not defs_to_process:
                self.report({'WARNING'}, f"Operator ID '{self.operator_idname_filter}' not found in KEYMAP_DEFS.")
                return {'CANCELLED'}
        else:
            defs_to_process = KEYMAP_DEFS

        if not defs_to_process: # Should not happen if KEYMAP_DEFS is not empty and filter logic is correct
            self.report({'INFO'}, "No keymap definitions to process.")
            return {'FINISHED'}

        modified_count = 0
        added_count = 0

        for keymap_def_to_apply in defs_to_process:
            km_user = kc_user.keymaps.get(keymap_def_to_apply["km_name"])
            if not km_user:
                try:
                    km_user = kc_user.keymaps.new(name=keymap_def_to_apply["km_name"], 
                                                  space_type=keymap_def_to_apply["space_type"],
                                                  region_type=keymap_def_to_apply.get("region_type", "WINDOW")) 
                    # print(f"QP_Tools: Created keymap '{keymap_def_to_apply['km_name']}' in USER keyconfig as it was missing.") # Informational
                except Exception as e:
                    print(f"QP_Tools: ERROR - Failed to create keymap '{keymap_def_to_apply['km_name']}' in USER keyconfig: {e}")
                    continue


            existing_kmis = [kmi for kmi in km_user.keymap_items if kmi.idname == keymap_def_to_apply["idname"]]
            
            if existing_kmis:
                if self.force_add_if_missing:
                    # self.report({'INFO'}, f"Keybinding for '{keymap_def_to_apply['name']}' already exists in USER config. Not adding again.") # Can be verbose
                    continue 

                kmi_to_reset = existing_kmis[0]
                kmi_to_reset.type = keymap_def_to_apply["key"]
                kmi_to_reset.value = 'PRESS' 
                kmi_to_reset.ctrl = keymap_def_to_apply.get("ctrl", False)
                kmi_to_reset.alt = keymap_def_to_apply.get("alt", False)
                kmi_to_reset.shift = keymap_def_to_apply.get("shift", False)
                kmi_to_reset.oskey = keymap_def_to_apply.get("oskey", False)
                modified_count += 1
                # print(f"QP_Tools: Reset keybinding for '{keymap_def_to_apply['name']}' in USER keyconfig.") # Informational

                for i in range(len(existing_kmis) -1, 0, -1): 
                    try:
                        km_user.keymap_items.remove(existing_kmis[i])
                        # print(f"QP_Tools: Removed a duplicate user keybinding for '{keymap_def_to_apply['name']}'.") # Informational
                    except Exception as e:
                        print(f"QP_Tools: ERROR - Failed to remove duplicate KMI for '{keymap_def_to_apply['name']}': {e}")


            else: 
                try:
                    kmi_new = km_user.keymap_items.new(
                        keymap_def_to_apply["idname"],
                        keymap_def_to_apply["key"],
                        'PRESS',
                        ctrl=keymap_def_to_apply.get("ctrl", False),
                        alt=keymap_def_to_apply.get("alt", False),
                        shift=keymap_def_to_apply.get("shift", False),
                        oskey=keymap_def_to_apply.get("oskey", False)
                    )
                    added_count += 1
                    # print(f"QP_Tools: Added default keybinding for '{keymap_def_to_apply['name']}' to USER keyconfig.") # Informational
                except Exception as e:
                    print(f"QP_Tools: ERROR - Failed to add keymap item for '{keymap_def_to_apply['name']}' to USER keyconfig: {e}")
        
        register_keymaps() # Ensure addon defaults are also consistent

        report_parts = []
        if modified_count > 0: report_parts.append(f"{modified_count} item(s) reset")
        if added_count > 0: report_parts.append(f"{added_count} item(s) added")
        
        if not report_parts:
            final_message = "No relevant keybindings found in USER config to reset or add."
            if self.force_add_if_missing :
                final_message = "No new keybindings to add; defaults may already exist or were not defined."
            self.report({'INFO'}, final_message)

        else:
            self.report({'INFO'}, f"Operation complete for USER keyconfig: {', '.join(report_parts)}.")
        
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'PREFERENCES':
                    area.tag_redraw()
        return {'FINISHED'}



classes = (
    QP_OT_RecreateShortcuts,
)

def register():
    for cls in classes:
        try:
            bpy.utils.register_class(cls)
        except Exception as e: # Catch generic Exception, or be more specific if needed
            print(f"QP_Tools: Error registering class {cls.__name__} from shortcuts.py: {e}")


def unregister():
    unregister_keymaps() 
    for cls in reversed(classes): 
        try:
            bpy.utils.unregister_class(cls)
        except Exception as e: # Catch generic Exception
            print(f"QP_Tools: Error unregistering class {cls.__name__} from shortcuts.py: {e}")
