# FloatingPanel.py
"""
Floating Panel - Create floating viewport windows.

Simple workflow:
1. Split active area to sidebar width + padding
2. Wait for UI refresh
3. Duplicate the new area (areas[-1])
4. Configure the duplicated viewport (hide tools, show N panel, etc.)
5. Wait for UI refresh
6. Close the split area
"""
import bpy
import sys
from bpy.types import Operator
from bpy.props import IntProperty

from .module_helper import ModuleManager

# Module state variables
module_enabled = True
_is_registered = False

# Padding to add to sidebar width
SIDEBAR_PADDING = 20


def get_sidebar_width(area):
    """Get the width of the sidebar (N-panel) in the given area."""
    for region in area.regions:
        if region.type == 'UI' and region.width > 1:
            return region.width
    return 0


def get_window_region(area):
    """Get the WINDOW region from an area."""
    for region in area.regions:
        if region.type == 'WINDOW':
            return region
    return area.regions[0] if area.regions else None


def configure_floating_viewport(window):
    """Configure the viewport in the floating window.

    - Hide tool panel (T)
    - Show N panel
    - Hide overlays
    - Hide gizmos
    - Hide header
    - Hide asset shelf
    """
    if not window or not window.screen:
        return False

    for area in window.screen.areas:
        if area.type == 'VIEW_3D':
            space = area.spaces.active
            if space and space.type == 'VIEW_3D':
                # Hide tool panel (T)
                space.show_region_toolbar = False
                # Show N panel (sidebar)
                space.show_region_ui = True
                # Hide overlays
                space.overlay.show_overlays = False
                # Hide gizmos
                space.show_gizmo = False
                # Hide header
                space.show_region_header = False
                # Hide asset shelf
                if hasattr(space, 'show_region_asset_shelf'):
                    space.show_region_asset_shelf = False
                return True
    return False


class QP_OT_FloatingPanel(Operator):
    """Create a floating viewport window from the current 3D View"""
    bl_idname = "qp.floating_panel"
    bl_label = "Floating Panel"
    bl_description = "Create a floating viewport sized to the N-panel width"
    bl_options = {'REGISTER'}

    width_override: IntProperty(
        name="Window Width",
        description="Width for the split (0 = use sidebar width + padding)",
        min=0,
        max=4096,
        default=0,
    )

    # Modal state
    _timer = None
    _main_window = None
    _new_area_index = -1
    _step = 0  # 1=duplicate, 2=configure, 3=close
    _windows_before = None

    @classmethod
    def poll(cls, context):
        if not module_enabled:
            return False
        return context.area and context.area.type == 'VIEW_3D'

    def invoke(self, context, event):
        active_area = context.area
        if not active_area or active_area.type != 'VIEW_3D':
            self.report({'ERROR'}, "Must be invoked from a 3D View")
            return {'CANCELLED'}

        # Store main window and window count before duplicate
        self._main_window = context.window
        self._windows_before = set(w.as_pointer() for w in context.window_manager.windows)

        # Get split width (sidebar + padding)
        sidebar_width = get_sidebar_width(active_area)
        if self.width_override > 0:
            split_width = self.width_override
        elif sidebar_width > 1:
            split_width = sidebar_width + SIDEBAR_PADDING
        else:
            split_width = 300 + SIDEBAR_PADDING

        # Calculate split factor (left portion keeps this fraction)
        split_factor = 1.0 - (split_width / active_area.width)
        split_factor = max(0.1, min(0.95, split_factor))

        # STEP 1: Split the active area
        region = get_window_region(active_area)
        try:
            with context.temp_override(area=active_area, region=region):
                bpy.ops.screen.area_split(
                    direction='VERTICAL',
                    factor=split_factor,
                    cursor=(0, 0)
                )
        except Exception as e:
            self.report({'ERROR'}, f"Split failed: {e}")
            return {'CANCELLED'}

        # Store index of the new area (last one after split)
        self._new_area_index = len(context.screen.areas) - 1
        self._step = 1  # Next step: duplicate

        # Start modal with timer - delay before duplicate
        self._timer = context.window_manager.event_timer_add(0.1, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        if self._step == 1:
            # STEP 2: Duplicate the new area
            return self._duplicate_area(context)
        elif self._step == 2:
            # STEP 3: Configure the floating viewport
            return self._configure_viewport(context)
        elif self._step == 3:
            # STEP 4: Close the split area
            return self._close_split_area(context)

        return {'PASS_THROUGH'}

    def _duplicate_area(self, context):
        """Duplicate the new area to a floating window."""
        screen = self._main_window.screen if self._main_window else context.screen

        if self._new_area_index < 0 or self._new_area_index >= len(screen.areas):
            self.report({'ERROR'}, "Could not find new area")
            self._cleanup(context)
            return {'CANCELLED'}

        new_area = screen.areas[self._new_area_index]
        new_region = get_window_region(new_area)

        try:
            with context.temp_override(
                window=self._main_window,
                area=new_area,
                region=new_region
            ):
                bpy.ops.screen.area_dupli('INVOKE_DEFAULT')
        except Exception as e:
            self.report({'WARNING'}, f"Duplicate failed: {e}")
            self._cleanup(context)
            return {'FINISHED'}

        self._step = 2  # Next step: configure viewport
        return {'RUNNING_MODAL'}

    def _configure_viewport(self, context):
        """Configure the floating viewport settings."""
        # Find the new window (wasn't in windows_before)
        new_window = None
        for window in context.window_manager.windows:
            if window.as_pointer() not in self._windows_before:
                new_window = window
                break

        if new_window:
            configure_floating_viewport(new_window)

        self._step = 3  # Next step: close
        return {'RUNNING_MODAL'}

    def _close_split_area(self, context):
        """Close the split area in the main window."""
        self._cleanup(context)

        screen = self._main_window.screen if self._main_window else context.screen

        if self._new_area_index < 0 or self._new_area_index >= len(screen.areas):
            self.report({'WARNING'}, "Could not find area to close")
            return {'FINISHED'}

        area_to_close = screen.areas[self._new_area_index]
        close_region = get_window_region(area_to_close)

        try:
            with context.temp_override(
                window=self._main_window,
                area=area_to_close,
                region=close_region
            ):
                bpy.ops.screen.area_close()
            self.report({'INFO'}, "Floating panel created")
        except Exception as e:
            self.report({'WARNING'}, f"Could not close area: {e}")

        return {'FINISHED'}

    def _cleanup(self, context):
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None

    def cancel(self, context):
        self._cleanup(context)


class QP_OT_FloatingPanelSimple(Operator):
    """Duplicate the current 3D View to a new floating window"""
    bl_idname = "qp.floating_panel_simple"
    bl_label = "Floating Panel (Simple)"
    bl_description = "Just duplicate this viewport to a new window"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        if not module_enabled:
            return False
        return context.area and context.area.type == 'VIEW_3D'

    def execute(self, context):
        try:
            bpy.ops.screen.area_dupli('INVOKE_DEFAULT')
            self.report({'INFO'}, "Floating viewport created")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Failed: {e}")
            return {'CANCELLED'}


def menu_func(self, context):
    """Add to View menu in 3D View"""
    self.layout.separator()
    self.layout.operator(QP_OT_FloatingPanel.bl_idname, icon='WINDOW')
    self.layout.operator(QP_OT_FloatingPanelSimple.bl_idname, icon='DUPLICATE')


def register():
    if not ModuleManager.register_module(sys.modules[__name__]):
        return

    ModuleManager.safe_register_class(QP_OT_FloatingPanel)
    ModuleManager.safe_register_class(QP_OT_FloatingPanelSimple)
    ModuleManager.safe_append_menu(bpy.types.VIEW3D_MT_view, menu_func)


def unregister():
    if not ModuleManager.unregister_module(sys.modules[__name__]):
        return

    ModuleManager.safe_remove_menu(bpy.types.VIEW3D_MT_view, menu_func)
    ModuleManager.safe_unregister_class(QP_OT_FloatingPanelSimple)
    ModuleManager.safe_unregister_class(QP_OT_FloatingPanel)


if __name__ == "__main__":
    register()
