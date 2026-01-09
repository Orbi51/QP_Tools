# module_helper.py
import bpy
import inspect
import sys

class ModuleManager:
    """Helper class to manage module registration state"""
    
    @staticmethod
    def get_addon_preferences(context=None):
        """Get addon preferences with fallback to bpy.context"""
        if context is None:
            context = bpy.context
        prefs = context.preferences.addons.get(__package__, {}).preferences
        if not prefs:
            print(f"Warning: Could not find addon preferences for {__package__}")
        return prefs

    @staticmethod
    def get_module_state(module_name):
        """Get the enabled state of a module from preferences"""
        prefs = ModuleManager.get_addon_preferences()
        if not prefs:
            return True  # Default to enabled if preferences not available
            
        # Map module names to preference properties
        prop_name = f"{module_name.lower()}_enabled"
        return getattr(prefs, prop_name, True)

    @staticmethod
    def ensure_module_state(module_obj):
        """Ensure the module has the required state attributes"""
        if not hasattr(module_obj, "_is_registered"):
            module_obj._is_registered = False
        if not hasattr(module_obj, "module_enabled"):
            module_obj.module_enabled = True
    
    @staticmethod
    def is_enabled(module_name):
        """Check if module is enabled in the main package"""
        # Get the parent package
        frame = inspect.currentframe().f_back
        calling_module = inspect.getmodule(frame)
        
        if calling_module:
            # Get the package name
            package_parts = calling_module.__name__.split('.')
            package_name = package_parts[0]
            
            # Access package's module states
            package_module = sys.modules.get(package_name)
            if package_module and hasattr(package_module, "module_states"):
                return package_module.module_states.get(module_name, True)
        
        # Default to enabled if we couldn't determine state
        return True
    
    @staticmethod
    def register_module(module_obj, skip_if_registered=True):
        """Register a module and track its state"""
        # Ensure module has state attributes
        if not hasattr(module_obj, "_is_registered"):
            module_obj._is_registered = False
        if not hasattr(module_obj, "module_enabled"):
            module_obj.module_enabled = True
            
        # Check module state
        if module_obj._is_registered and skip_if_registered:
            return False
        if not module_obj.module_enabled:
            return False
            
        # Update registration state
        module_obj._is_registered = True
        return True

    @staticmethod
    def unregister_module(module_obj, skip_if_not_registered=True):
        """Unregister a module and track its state"""
        # Ensure module has state attributes
        ModuleManager.ensure_module_state(module_obj)
        
        # Check if module is already unregistered - DISABLE THIS CHECK for dynamic updates
        if skip_if_not_registered and not module_obj._is_registered:
            print(f"{module_obj.__name__}: Not registered, skipping unregistration")
            return False
        
        module_obj._is_registered = False
        return True
    
    @staticmethod
    def safe_register_class(cls, report_errors=True):
        """Safely register a class"""
        try:
            bpy.utils.register_class(cls)
            return True
        except Exception as e:
            if report_errors:
                print(f"Error registering {cls.__name__}: {str(e)}")
            return False
    
    @staticmethod
    def safe_unregister_class(cls, report_errors=True):
        """Safely unregister a class"""
        try:
            bpy.utils.unregister_class(cls)
            return True
        except Exception as e:
            if report_errors:
                print(f"Error unregistering {cls.__name__}: {str(e)}")
            return False
    
    @staticmethod
    def safe_append_menu(menu_type, func, check_existing=True):
        """Safely append a menu function"""
        try:
            # Avoid duplicate menu items by simply appending
            # The __annotations__ and iteration approach doesn't work
            # We simply append without checking for duplicates
            menu_type.append(func)
            return True
        except Exception as e:
            print(f"Error appending menu function: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

    @staticmethod
    def safe_remove_menu(menu_type, func):
        """Safely remove a menu function"""
        try:
            menu_type.remove(func)
            return True
        except Exception as e:
            print(f"Error removing menu function: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
        

    @staticmethod
    def safe_file_operation(operation, *args, **kwargs):
        """Safely perform a file operation with proper error handling
        
        Args:
            operation: Function to call (like open, read, write)
            *args, **kwargs: Arguments to pass to the operation
            
        Returns:
            Result of operation or None if failed
        """
        try:
            return operation(*args, **kwargs)
        except Exception as e:
            print(f"File operation error: {e}")
            import traceback
            traceback.print_exc()
            return None
        
    
    @staticmethod
    def report_error(operator, message, log=True, error_type='ERROR'):
        """Standardized error reporting function
        
        Args:
            operator: The operator to report through, or None
            message: Error message
            log: Whether to log to console
            error_type: Type of error report ('ERROR', 'WARNING', etc.)
        """
        if log:
            print(f"{error_type}: {message}")
            
        if operator and hasattr(operator, 'report'):
            operator.report({error_type}, message)



    @staticmethod
    def connect_object_to_modifier(imported_obj, source_obj):
        """Connect source_obj to the imported_obj's geometry nodes modifier
        
        Unified version to be used across multiple modules
        
        Args:
            imported_obj: The newly imported object with Geometry Nodes modifiers
            source_obj: The source object to connect to the modifier
            
        Returns:
            bool: True if connection was successful, False otherwise
        """
        if not imported_obj or not source_obj:
            return False
            
        # Find Geometry Nodes modifiers on the imported object
        for mod in imported_obj.modifiers:
            if mod.type != 'NODES':
                continue
                
            # Skip if no node group
            if not hasattr(mod, 'node_group') or not mod.node_group:
                continue
                
            # Find the Group Input node
            input_node = None
            for node in mod.node_group.nodes:
                if node.type == 'GROUP_INPUT':
                    input_node = node
                    break
                    
            if not input_node:
                continue
            
            # Find the best socket for connection
            socket_info = ModuleManager.find_best_object_socket(input_node)
            if not socket_info:
                continue
                
            # Try to make the connection with the found socket
            try:
                socket_id, socket = socket_info
                
                # Check if it's already connected to something
                if hasattr(mod, socket_id) and mod[socket_id] is not None:
                    # Skip if already connected to a different object
                    if mod[socket_id] != source_obj:
                        continue
                
                # Make the connection
                mod[socket_id] = source_obj
                
                # Force viewport update to ensure the connection is displayed
                if hasattr(mod, 'show_viewport'):
                    last_state = mod.show_viewport
                    mod.show_viewport = not last_state
                    mod.show_viewport = last_state
                
                print(f"Connected {source_obj.name} to {imported_obj.name}'s {mod.name} modifier via socket: {socket.name}")
                return True
                
            except Exception as e:
                print(f"Connection error: {e}")
                try:
                    # Alternative method for some Blender versions
                    setattr(mod, f"Input_{socket_id}", source_obj)
                    return True
                except (AttributeError, TypeError):
                    pass  # Could not set property
        
        return False

    @staticmethod
    def find_best_object_socket(input_node):
        """Find the best object socket in a node
        
        Args:
            input_node: The node to search for object sockets
            
        Returns:
            tuple: (socket_id, socket) or None if not found
        """
        object_socket = None
        first_object_socket = None
        named_object_socket = None
        fallback_socket = None
        
        # Search all output sockets
        for socket in input_node.outputs:
            is_object_socket = False
            
            # Method 1: Check by type
            if hasattr(socket, 'type') and socket.type == 'OBJECT':
                is_object_socket = True
            # Method 2: Check by bl_idname
            elif hasattr(socket, 'bl_idname') and any(obj_type in socket.bl_idname.lower() 
                                                for obj_type in ['object', 'nodeobject']):
                is_object_socket = True
            # Method 3: Check by common names
            elif socket.name.lower() in ['object', 'target', 'target object']:
                is_object_socket = True
                named_object_socket = socket
            
            # Track first object socket found
            if is_object_socket and not first_object_socket:
                first_object_socket = socket
            
            # Preferred match: Socket named exactly "Object"
            if socket.name.lower() == "object" and is_object_socket:
                object_socket = socket
                break
            
            # Track fallback socket with related names
            if not fallback_socket and socket.name.lower() in [
                'instance', 'instances', 'target', 'input', 'mesh', 'geometry',
                'points', 'curve', 'curves', 'target_object', 'input_object'
            ]:
                fallback_socket = socket
        
        # Select the best socket using this priority order
        socket = object_socket or named_object_socket or first_object_socket or fallback_socket
        
        if socket:
            # Get the socket identifier
            socket_id = getattr(socket, 'identifier', socket.name)
            return (socket_id, socket)
        
        return None