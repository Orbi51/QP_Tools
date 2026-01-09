# qp_product_installer.py - This standalone file will be imported directly in preferences.py
import bpy
import os
import sys
import zipfile
import tempfile
import shutil
from bpy.props import StringProperty, BoolProperty, EnumProperty
from bpy.types import Operator, AddonPreferences
from bpy_extras.io_utils import ImportHelper

# Global constants
CUSTOM_PATHS_PREF_NAME = "custom_module_paths"

class QP_OT_InstallProduct(Operator, ImportHelper):
    """Install a zipped QP_Tools product module"""
    bl_idname = "qp.install_product"
    bl_label = "Install Product"
    bl_description = "Install a zipped QP_Tools product module"
    
    filename_ext = ".zip"
    filter_glob: StringProperty(
        default="*.zip",
        options={'HIDDEN'}
    )
    
    install_location: EnumProperty(
        name="Install Location",
        description="Where to install the product",
        items=[
            ('DEFAULT', "Default Location", "Install in the addon's directory"),
            ('CUSTOM', "Custom Location", "Choose a custom install location")
        ],
        default='DEFAULT'
    )
    
    def invoke(self, context, event):
        # First show the file browser
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
    
    def execute(self, context):
        # Get the selected zip file
        if not self.filepath or not os.path.exists(self.filepath):
            self.report({'ERROR'}, f"Invalid file: {self.filepath}")
            return {'CANCELLED'}
        
        # Show location options dialog
        return context.window_manager.invoke_props_dialog(self, width=400)
    
    def draw(self, context):
        layout = self.layout
        layout.prop(self, "install_location")
    
    def invoke_after_dialog(self, context):
        """Called after the dialog is confirmed"""
        try:
            # Get addon preferences
            addon_prefs = self.get_addon_preferences(context)
            if not addon_prefs:
                self.report({'ERROR'}, "Could not find addon preferences")
                return {'CANCELLED'}
                
            # Get target directory
            if self.install_location == 'DEFAULT':
                target_dir = self.get_addon_directory()
                if not target_dir:
                    self.report({'ERROR'}, "Could not determine addon directory")
                    return {'CANCELLED'}
            else:
                # Show directory browser
                bpy.ops.qp.select_install_directory('INVOKE_DEFAULT', zipfile_path=self.filepath)
                return {'FINISHED'}  # The other operator will handle the rest
            
            # Install to default location
            success, message = self.install_zip(self.filepath, target_dir)
            if success:
                self.report({'INFO'}, message)
                # Reload addon to apply changes
                bpy.ops.script.reload()
                return {'FINISHED'}
            else:
                self.report({'ERROR'}, message)
                return {'CANCELLED'}
                
        except Exception as e:
            self.report({'ERROR'}, f"Installation failed: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}
    
    def get_addon_preferences(self, context):
        """Get the QP_Tools addon preferences"""
        addon_name = __package__.split('.')[0]
        try:
            return context.preferences.addons[addon_name].preferences
        except KeyError:
            return None  # Addon not registered
    
    def get_addon_directory(self):
        """Get the root directory of the addon"""
        # Handle the case where this is imported directly
        if __name__ == "__main__":
            return os.path.dirname(os.path.abspath(__file__))
            
        # Get from __package__ if available
        if hasattr(self, "__package__") and self.__package__:
            addon_name = self.__package__.split('.')[0]
        else:
            # Try to get the addon name from context
            for addon_name in bpy.context.preferences.addons.keys():
                if "QP_Tools" in addon_name:
                    break
            else:
                # Fallback to fixed name
                addon_name = "QP_Tools"
                
        # Get from current file path
        script_path = os.path.abspath(__file__)
        if os.path.exists(script_path):
            addon_dir = os.path.dirname(script_path)
            # Check if we're in the root directory or a subdirectory
            if not os.path.exists(os.path.join(addon_dir, "__init__.py")):
                # We're already in the root directory
                return addon_dir
            else:
                # We're in a subdirectory, go up one level
                return os.path.dirname(addon_dir)
        
        # Fallback to module path
        try:
            module = sys.modules.get(addon_name)
            if module:
                path = os.path.dirname(os.path.abspath(module.__file__))
                return path
        except (AttributeError, TypeError):
            pass  # Module path not accessible
            
        return None

    def install_zip(self, zip_path, target_dir):
        """
        Install the zip file into the target directory
        Returns (success, message)
        """
        try:
            # Check if zip file is valid
            if not zipfile.is_zipfile(zip_path):
                return False, f"Not a valid zip file: {zip_path}"
            
            # Create a temporary directory for extraction
            with tempfile.TemporaryDirectory() as temp_dir:
                # Extract the zip to the temp directory
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_dir)
                
                # Look for module directories (containing a DrawScatter_Script.py or similar)
                module_dirs = []
                for root, dirs, files in os.walk(temp_dir):
                    for file in files:
                        if file.endswith("_Script.py"):
                            # Found a script file, add its directory
                            module_dir = os.path.basename(root)
                            module_dirs.append((root, module_dir))
                            break
                
                if not module_dirs:
                    return False, "No valid QP module found in the zip file"
                
                # Copy each module directory to the target
                installed_modules = []
                for src_dir, module_name in module_dirs:
                    dst_dir = os.path.join(target_dir, module_name)
                    
                    # Check if module already exists
                    if os.path.exists(dst_dir):
                        # Create a backup
                        backup_dir = dst_dir + "_backup"
                        if os.path.exists(backup_dir):
                            shutil.rmtree(backup_dir)
                        shutil.copytree(dst_dir, backup_dir)
                        
                        # Remove existing module
                        shutil.rmtree(dst_dir)
                    
                    # Copy the module
                    shutil.copytree(src_dir, dst_dir)
                    installed_modules.append(module_name)
                
                return True, f"Successfully installed modules: {', '.join(installed_modules)}"
                
        except Exception as e:
            import traceback
            traceback.print_exc()
            return False, f"Installation failed: {str(e)}"

class QP_OT_SelectInstallDirectory(Operator, ImportHelper):
    """Select directory to install the product"""
    bl_idname = "qp.select_install_directory"
    bl_label = "Select Install Directory"
    
    directory: StringProperty(
        name="Install Directory",
        description="Directory to install the product",
        subtype='DIR_PATH'
    )
    
    zipfile_path: StringProperty(
        name="Zip File Path",
        description="Path to the zip file to install",
        default=""
    )
    
    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
    
    def execute(self, context):
        # Validate directory
        if not self.directory or not os.path.isdir(self.directory):
            self.report({'ERROR'}, f"Invalid directory: {self.directory}")
            return {'CANCELLED'}
        
        # Validate zip file
        if not self.zipfile_path or not os.path.exists(self.zipfile_path):
            self.report({'ERROR'}, f"Invalid zip file: {self.zipfile_path}")
            return {'CANCELLED'}
        
        # Install the zip file
        installer = QP_OT_InstallProduct.bl_idname
        success, message = self.install_zip(self.zipfile_path, self.directory)
        
        if success:
            # Save custom path to preferences
            self.save_custom_path(context, self.directory)
            
            self.report({'INFO'}, message)
            # Reload addon to apply changes
            bpy.ops.script.reload()
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, message)
            return {'CANCELLED'}
    
    def install_zip(self, zip_path, target_dir):
        """Use the installer's method to install the zip"""
        installer = QP_OT_InstallProduct
        return installer.install_zip(self, zip_path, target_dir)
    
    def save_custom_path(self, context, path):
        """Save custom installation path to addon preferences"""
        try:
            # Get addon preferences
            addon_name = __package__.split('.')[0]
            addon_prefs = context.preferences.addons[addon_name].preferences
            
            # Get current custom paths
            custom_paths = getattr(addon_prefs, CUSTOM_PATHS_PREF_NAME, "")
            paths = custom_paths.split(os.pathsep) if custom_paths else []
            
            # Add new path if not already in the list
            if path not in paths:
                paths.append(path)
                setattr(addon_prefs, CUSTOM_PATHS_PREF_NAME, os.pathsep.join(paths))
        except Exception as e:
            print(f"Error saving custom path: {str(e)}")    
    
# Draw helper for preferences panel
def draw_install_product(preferences, context, layout):
    box = layout.box()
    box.label(text="Product Installation", icon='PACKAGE')
    
    row = box.row()
    row.scale_y = 1.5
    row.operator(QP_OT_InstallProduct.bl_idname, icon='IMPORT')
    
    # Show custom module paths if any
    custom_paths = getattr(preferences, CUSTOM_PATHS_PREF_NAME, "")
    if custom_paths:
        path_box = box.box()
        path_box.label(text="Custom Module Paths:", icon='FILE_FOLDER')
        for path in custom_paths.split(os.pathsep):
            path_box.label(text=path)