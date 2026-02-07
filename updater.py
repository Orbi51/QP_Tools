import bpy
import urllib.request
import urllib.error
import json
import threading
import tempfile
import shutil
import zipfile
import os
import tomllib
from pathlib import Path


# --------------- Constants ---------------

def _read_addon_version() -> str:
    manifest = Path(__file__).resolve().parent / "blender_manifest.toml"
    try:
        with open(manifest, 'rb') as f:
            data = tomllib.load(f)
        return data.get("version", "0.0.0")
    except (OSError, tomllib.TOMLDecodeError):
        return "0.0.0"


CURRENT_ADDON_VERSION = _read_addon_version()
MANIFEST_URL = "https://raw.githubusercontent.com/Orbi51/QP_Tools/main/update_info.json"

# --------------- Persistent State File ---------------

def _get_state_file() -> Path:
    config_dir = Path(bpy.utils.user_resource('CONFIG')) / "QP_Tools"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "updater_state.json"


def _load_updater_state() -> dict:
    path = _get_state_file()
    if path.exists():
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "last_check": "",
        "dismissed_addon_version": "",
    }


def _save_updater_state(data: dict):
    path = _get_state_file()
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except OSError:
        pass

# --------------- Module-level State ---------------

_update_state = {
    "checked": False,
    "checking": False,
    "addon_update_available": False,
    "addon_remote_version": "",
    "addon_changelog": "",
    "addon_download_url": "",
    "error": "",
    "download_progress": 0.0,
    "download_status": "",       # "", "downloading", "installing", "done", "error"
    "addon_dismissed": False,
}

_pending_timer = None
_manual_check = False

# --------------- Version Utilities ---------------

def _is_newer(remote: str, local: str) -> bool:
    try:
        r = tuple(int(x) for x in remote.split('.'))
        l = tuple(int(x) for x in local.split('.'))
        return r > l
    except (ValueError, AttributeError):
        return False

# --------------- Background Update Check ---------------

def _do_check():
    global _manual_check
    _update_state["checking"] = True
    _update_state["error"] = ""

    try:
        req = urllib.request.Request(
            MANIFEST_URL,
            headers={"User-Agent": "QP_Tools-Updater"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))

        persistent = _load_updater_state()

        addon_info = data.get("addon", {})
        remote_ver = addon_info.get("version", "")
        if remote_ver and _is_newer(remote_ver, CURRENT_ADDON_VERSION):
            _update_state["addon_update_available"] = True
            _update_state["addon_remote_version"] = remote_ver
            _update_state["addon_changelog"] = addon_info.get("changelog", "")
            _update_state["addon_download_url"] = addon_info.get("download_url", "")
            if _manual_check:
                _update_state["addon_dismissed"] = False
            else:
                _update_state["addon_dismissed"] = (
                    remote_ver == persistent.get("dismissed_addon_version", "")
                )
        else:
            _update_state["addon_update_available"] = False
            _update_state["addon_dismissed"] = False

        import datetime
        persistent["last_check"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        _save_updater_state(persistent)

    except (urllib.error.URLError, TimeoutError, OSError) as e:
        _update_state["error"] = f"Network error: {e}"
    except json.JSONDecodeError:
        _update_state["error"] = "Invalid update manifest"
    except Exception as e:
        _update_state["error"] = str(e)
    finally:
        _update_state["checked"] = True
        _update_state["checking"] = False
        _manual_check = False
        try:
            bpy.app.timers.register(_trigger_redraw, first_interval=0.0)
        except Exception:
            pass


def _trigger_redraw():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type in ('PREFERENCES', 'VIEW_3D'):
                area.tag_redraw()
    return None


def _delayed_check():
    global _pending_timer
    _pending_timer = None

    if not bpy.app.online_access:
        return None

    try:
        prefs = bpy.context.preferences.addons[__package__].preferences
        if not prefs.auto_check_updates:
            return None
    except (KeyError, AttributeError):
        return None

    if _update_state["checked"] or _update_state["checking"]:
        return None

    thread = threading.Thread(target=_do_check, daemon=True)
    thread.start()
    return None

# --------------- Progress Redraw Timer ---------------

_progress_timer_running = False


def _progress_redraw_timer():
    global _progress_timer_running
    if _update_state["download_status"] not in ("downloading", "installing"):
        _progress_timer_running = False
        _trigger_redraw()
        return None
    _trigger_redraw()
    return 0.5

# --------------- Operators ---------------

class QP_OT_check_updates(bpy.types.Operator):
    """Manually check for QP_Tools updates"""
    bl_idname = "qp.check_updates"
    bl_label = "Check for Updates"
    bl_options = {'REGISTER'}

    def execute(self, context):
        global _manual_check

        if not bpy.app.online_access:
            self.report({'WARNING'}, "Online access is disabled in Blender Preferences > System > Network")
            return {'CANCELLED'}

        if _update_state["checking"]:
            self.report({'INFO'}, "Already checking for updates...")
            return {'CANCELLED'}

        _update_state["checked"] = False
        _update_state["checking"] = False
        _update_state["error"] = ""
        _update_state["download_status"] = ""
        _manual_check = True

        thread = threading.Thread(target=_do_check, daemon=True)
        thread.start()

        self.report({'INFO'}, "Checking for updates...")
        return {'FINISHED'}


class QP_OT_update_addon(bpy.types.Operator):
    """Download and install the latest QP_Tools addon version"""
    bl_idname = "qp.update_addon"
    bl_label = "Update Addon"
    bl_options = {'REGISTER'}

    def execute(self, context):
        if not bpy.app.online_access:
            self.report({'WARNING'}, "Online access is disabled in Blender Preferences")
            return {'CANCELLED'}

        url = _update_state.get("addon_download_url", "")
        if not url:
            self.report({'ERROR'}, "No download URL available")
            return {'CANCELLED'}

        if _update_state["download_status"] in ("downloading", "installing"):
            self.report({'WARNING'}, "A download is already in progress")
            return {'CANCELLED'}

        _update_state["download_status"] = "downloading"
        _update_state["download_progress"] = 0.0

        global _progress_timer_running
        if not _progress_timer_running:
            _progress_timer_running = True
            bpy.app.timers.register(_progress_redraw_timer, first_interval=0.5)

        thread = threading.Thread(
            target=self._download_addon, args=(url,), daemon=True
        )
        thread.start()

        return {'FINISHED'}

    @staticmethod
    def _download_addon(url):
        tmp_path = None
        try:
            tmp_fd, tmp_path = tempfile.mkstemp(suffix=".zip", prefix="qp_tools_addon_")
            os.close(tmp_fd)

            def _progress(block_count, block_size, total_size):
                if total_size > 0:
                    _update_state["download_progress"] = min(
                        block_count * block_size / total_size, 1.0
                    )

            urllib.request.urlretrieve(url, tmp_path, reporthook=_progress)
            _update_state["download_progress"] = 1.0

            def _install_callback():
                QP_OT_update_addon._install_addon(tmp_path)
                return None
            bpy.app.timers.register(_install_callback, first_interval=0.1)

        except Exception as e:
            _update_state["download_status"] = "error"
            _update_state["error"] = f"Download failed: {e}"
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

    @staticmethod
    def _install_addon(zip_path):
        addon_dir = Path(__file__).resolve().parent
        backup_path = None
        tmp_extract = None

        try:
            _update_state["download_status"] = "installing"

            config_dir = Path(bpy.utils.user_resource('CONFIG')) / "QP_Tools"
            config_dir.mkdir(parents=True, exist_ok=True)
            backup_path = config_dir / "addon_backup.zip"

            with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as backup_zip:
                for file_path in addon_dir.rglob('*'):
                    if file_path.is_file() and '__pycache__' not in str(file_path):
                        backup_zip.write(file_path, file_path.relative_to(addon_dir))

            tmp_extract = Path(tempfile.mkdtemp(prefix="qp_tools_install_"))
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(tmp_extract)

            extracted_items = list(tmp_extract.iterdir())
            source_dir = tmp_extract
            if len(extracted_items) == 1 and extracted_items[0].is_dir():
                source_dir = extracted_items[0]

            for item in addon_dir.iterdir():
                if item.name == '__pycache__':
                    continue
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)

            for item in source_dir.iterdir():
                dest = addon_dir / item.name
                if item.is_file():
                    shutil.copy2(item, dest)
                elif item.is_dir():
                    if dest.exists():
                        shutil.rmtree(dest, ignore_errors=True)
                    shutil.copytree(item, dest)

            _update_state["download_status"] = "done"
            _update_state["addon_update_available"] = False

        except Exception as e:
            _update_state["download_status"] = "error"
            _update_state["error"] = f"Install failed: {e}"

            if backup_path and backup_path.exists():
                try:
                    with zipfile.ZipFile(backup_path, 'r') as backup_zip:
                        backup_zip.extractall(addon_dir)
                except Exception:
                    pass

        finally:
            try:
                os.remove(zip_path)
            except OSError:
                pass
            if tmp_extract:
                shutil.rmtree(tmp_extract, ignore_errors=True)


class QP_OT_dismiss_update(bpy.types.Operator):
    """Dismiss this update notification"""
    bl_idname = "qp.dismiss_update"
    bl_label = "Dismiss"
    bl_options = {'REGISTER'}

    def execute(self, context):
        persistent = _load_updater_state()
        persistent["dismissed_addon_version"] = _update_state["addon_remote_version"]
        _update_state["addon_dismissed"] = True
        _save_updater_state(persistent)
        return {'FINISHED'}


class QP_OT_open_addon_prefs(bpy.types.Operator):
    """Open QP_Tools addon preferences"""
    bl_idname = "qp.open_addon_prefs"
    bl_label = "Open QP_Tools Preferences"
    bl_options = {'REGISTER'}

    def execute(self, context):
        bpy.ops.preferences.addon_show(module=__package__)
        return {'FINISHED'}

# --------------- UI Draw Functions ---------------

def draw_updates_section(prefs, layout, context):
    state = _update_state

    show_addon = state["addon_update_available"] and not state["addon_dismissed"]

    # --- Download in progress ---
    if state["download_status"] == "downloading":
        box = layout.box()
        pct = int(state["download_progress"] * 100)
        box.label(text=f"Downloading update... {pct}%", icon='IMPORT')
        return

    # --- Installing ---
    if state["download_status"] == "installing":
        box = layout.box()
        box.label(text="Installing update...", icon='IMPORT')
        return

    # --- Install done ---
    if state["download_status"] == "done":
        box = layout.box()
        row = box.row()
        row.alert = True
        row.label(text="Update installed! Please restart Blender.", icon='CHECKMARK')
        row = box.row()
        row.operator("qp.check_updates", icon='FILE_REFRESH')
        row.prop(prefs, "auto_check_updates", text="Auto")
        return

    # --- Download error ---
    if state["download_status"] == "error":
        box = layout.box()
        box.alert = True
        box.label(text=f"Error: {state['error']}", icon='ERROR')
        row = box.row()
        row.operator("qp.check_updates", text="Retry", icon='FILE_REFRESH')
        row.prop(prefs, "auto_check_updates", text="Auto")
        return

    # --- Update available ---
    if show_addon:
        box = layout.box()
        box.alert = True
        box.label(text="Update Available", icon='INFO')

        sub = box.box()
        sub.label(
            text=f"Addon: {CURRENT_ADDON_VERSION}  \u2192  {state['addon_remote_version']}",
            icon='PACKAGE'
        )
        if state["addon_changelog"]:
            col = sub.column(align=True)
            col.scale_y = 0.8
            for line in state["addon_changelog"].split('\n'):
                col.label(text=line)
        row = sub.row(align=True)
        row.operator("qp.update_addon", text="Update Addon", icon='IMPORT')
        row.operator("qp.dismiss_update", text="Dismiss", icon='X')

        row = box.row()
        row.operator("qp.check_updates", icon='FILE_REFRESH')
        row.prop(prefs, "auto_check_updates", text="Auto")

        persistent = _load_updater_state()
        last = persistent.get("last_check", "")
        if last:
            box.label(text=f"Last checked: {last}")
        return

    # --- Checking ---
    if state["checking"]:
        box = layout.box()
        row = box.row()
        row.label(text=f"QP_Tools v{CURRENT_ADDON_VERSION} \u2014 Checking for updates...", icon='FILE_REFRESH')
        row.prop(prefs, "auto_check_updates", text="Auto")
        return

    # --- Up to date / default state ---
    box = layout.box()
    row = box.row()
    if state["checked"] and not state["error"]:
        row.label(text=f"QP_Tools v{CURRENT_ADDON_VERSION} \u2014 Up to date", icon='CHECKMARK')
    elif state["error"]:
        row.label(text=f"QP_Tools v{CURRENT_ADDON_VERSION} \u2014 Check failed", icon='ERROR')
    else:
        row.label(text=f"QP_Tools v{CURRENT_ADDON_VERSION}", icon='PACKAGE')
    row.operator("qp.check_updates", text="Check", icon='FILE_REFRESH')
    row.prop(prefs, "auto_check_updates", text="Auto")


def draw_sidebar_update_notice(layout) -> None:
    if not _update_state["checked"]:
        return

    persistent = _load_updater_state()

    addon_notify = (
        _update_state["addon_update_available"]
        and _update_state["addon_remote_version"] != persistent.get("dismissed_addon_version", "")
    )

    if not addon_notify:
        return

    box = layout.box()
    box.alert = True
    row = box.row(align=True)
    row.label(text="QP_Tools update available!", icon='ERROR')
    row.operator("qp.open_addon_prefs", text="", icon='PREFERENCES')

# --------------- Registration ---------------

_classes = (
    QP_OT_check_updates,
    QP_OT_update_addon,
    QP_OT_dismiss_update,
    QP_OT_open_addon_prefs,
)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)

    global _pending_timer
    _pending_timer = True
    bpy.app.timers.register(_delayed_check, first_interval=3.0)


def unregister():
    global _pending_timer
    if _pending_timer is not None:
        try:
            bpy.app.timers.unregister(_delayed_check)
        except Exception:
            pass
        _pending_timer = None

    for cls in reversed(_classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
