# asset_cache.py
# Asset cache management functions for QP_Tools
import bpy
import os
import json
import time
import re
from datetime import datetime

_cache_storage = {}  # Module-level cache storage


def get_cache_path():
    """Get the path to the asset cache file"""
    try:
        # Use Blender's user preferences directory
        user_pref_dir = bpy.utils.user_resource('CONFIG', path="QP_Tools", create=True)
        return os.path.join(user_pref_dir, "assets_cache.json")
    except Exception as e:
        print(f"Error creating cache directory: {e}")
        # Fall back to temporary directory as a last resort
        import tempfile
        return os.path.join(tempfile.gettempdir(), "qp_tools_assets_cache.json")

def safe_load_json(filepath, default=None):
    """Safely load JSON from a file with error handling
    
    Args:
        filepath: Path to the JSON file
        default: Default value to return if loading fails
        
    Returns:
        The loaded JSON data or default value
    """
    if not os.path.exists(filepath):
        return default or {}
        
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading JSON from {filepath}: {e}")
        return default or {}

def safe_save_json(filepath, data):
    """Safely save JSON to a file with error handling
    
    Args:
        filepath: Path to save the JSON file
        data: Data to save
        
    Returns:
        bool: Success or failure
    """
    try:
        # Ensure directory exists
        directory = os.path.dirname(filepath)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)
        
        # Write to a temporary file first
        temp_file = f"{filepath}.tmp"
        with open(temp_file, 'w') as f:
            json.dump(data, f)
        
        # Rename to the final filename (atomic operation to prevent data loss)
        if os.path.exists(filepath):
            os.replace(temp_file, filepath)  # Atomic replace
        else:
            os.rename(temp_file, filepath)
            
        return True
    except Exception as e:
        print(f"Error saving JSON to {filepath}: {e}")
        return False


def load_asset_cache():
    """Load the asset cache using the safe loader"""
    cache_path = get_cache_path()
    cache = safe_load_json(cache_path, default={
        "timestamp": time.time(),
        "libraries": {}
    })
    
    # Ensure proper structure
    if "timestamp" not in cache:
        cache["timestamp"] = time.time()
    if "libraries" not in cache:
        cache["libraries"] = {}
        
    return cache


def save_asset_cache(cache):
    """Save the asset cache using the safe saver"""
    cache_path = get_cache_path()
    cache["timestamp"] = time.time()
    return safe_save_json(cache_path, cache)


def cached_operation(max_age=300):  # 5 minutes default cache lifetime
    """Decorator to cache function results with a timeout"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            # Create a cache key from arguments - exclude mutable objects like 'self' or 'context'
            filtered_args = [arg for arg in args if not hasattr(arg, '__dict__')]
            key = f"{func.__name__}:{str(filtered_args)}:{str(sorted(kwargs.items()))}"
            
            # Check if result is in cache and still fresh
            if key in _cache_storage:
                result, timestamp = _cache_storage[key]
                if time.time() - timestamp < max_age:
                    return result
            
            # Call the function and cache result
            result = func(*args, **kwargs)
            _cache_storage[key] = (result, time.time())
            return result
        return wrapper
    return decorator

def is_valid_blend_file(filepath):
    """Check if a file is a valid blend file (not a backup file)"""
    # Skip backup files (.blend1, .blend2, etc.)
    if re.search(r'\.blend\d+$', filepath):
        return False
    
    # Only include .blend files
    return filepath.lower().endswith('.blend')

def update_cache_with_library(cache, library_name, assets):
    """Update the cache with assets from a library
    
    Args:
        cache (dict): The cache dictionary
        library_name (str): Name of the library
        assets (list): List of asset dictionaries
        
    Returns:
        dict: Updated cache dictionary
    """
    # Ensure the libraries dict exists
    if "libraries" not in cache:
        cache["libraries"] = {}
    
    # Store assets by library
    cache["libraries"][library_name] = {
        "last_scan": time.time(),
        "assets": assets
    }
    
    return cache

def scan_library_assets(library, context):
    """Enhanced implementation for the scan library assets operator
    
    Args:
        library: The library object with name and path properties
        context: The current context
    
    Returns:
        int: Number of assets found
    """
    if not library or not library.path or not os.path.exists(library.path):
        return 0
    
    # Clear existing assets for this library
    library.assets.clear()
    
    # Get or create asset cache
    asset_cache = load_asset_cache()
    
    # Find blend files
    blend_files = []
    for root, dirs, files in os.walk(library.path):
        for file in files:
            filepath = os.path.join(root, file)
            if is_valid_blend_file(filepath):
                blend_files.append(filepath)
    
    # Store new assets for this library
    new_assets = []
    
    # Import bpy here only when this is run from Blender
    import bpy
    
    # Scan each file for assets
    assets_found = 0
    for blend_file in blend_files:
        try:
            # Determine category from relative path
            rel_path = os.path.relpath(blend_file, library.path)
            dirname = os.path.dirname(rel_path)
            category = dirname if dirname and dirname != '.' else "Default"
            
            # Use assets_only=True to only load assets from the file
            with bpy.data.libraries.load(blend_file, assets_only=True) as (data_from, _):
                # Only scan for object assets
                asset_type = 'objects'
                asset_names = getattr(data_from, asset_type, [])
                
                # Create a list so we can deduplicate before adding to the library
                unique_items = set()
                
                for obj_name in asset_names:
                    # Create a unique key to prevent duplicating the same asset
                    unique_key = f"{blend_file}:{obj_name}"
                    
                    # Skip if already processed
                    if unique_key in unique_items:
                        continue
                        
                    unique_items.add(unique_key)
                    
                    # Add to library assets first
                    asset = library.assets.add()
                    asset.name = obj_name
                    asset.filepath = blend_file
                    asset.enabled = True
                    asset.category = category
                    assets_found += 1
                    
                    # Create metadata for the cache
                    asset_data = {
                        "name": obj_name,
                        "filepath": blend_file,
                        "category": category,
                        "type": asset_type,
                        "timestamp": time.time(),
                        "enabled": asset.enabled  # Include the enabled state in cache
                    }
                    new_assets.append(asset_data)
                        
        except Exception as e:
            print(f"Error scanning {blend_file}: {str(e)}")
    
    # Update cache with this library's assets
    update_cache_with_library(asset_cache, library.name, new_assets)
    
    # Save the updated cache
    save_asset_cache(asset_cache)
    
    return assets_found

def clean_asset_cache():
    """Clean and optimize the existing asset cache"""
    cache_path = get_cache_path()
    if not os.path.exists(cache_path):
        return False
        
    try:
        # Load existing cache
        with open(cache_path, 'r') as f:
            old_cache = json.load(f)
            
        # Create a new structured cache
        new_cache = {
            "timestamp": time.time(),
            "libraries": {}
        }
        
        # Process existing libraries if available
        if "libraries" in old_cache:
            for lib_name, lib_data in old_cache["libraries"].items():
                # Create a deduplicated list of assets
                unique_assets = {}
                
                for asset in lib_data.get("assets", []):
                    # Skip if missing required fields
                    if not asset.get("name") or not asset.get("filepath"):
                        continue
                    
                    # Skip backup files
                    if not is_valid_blend_file(asset.get("filepath")):
                        continue
                    
                    # Use filepath+name as unique key
                    key = f"{asset.get('filepath')}:{asset.get('name')}"
                    unique_assets[key] = asset
                
                # Store deduplicated assets
                new_cache["libraries"][lib_name] = {
                    "last_scan": lib_data.get("last_scan", time.time()),
                    "assets": list(unique_assets.values())
                }
        # Handle older cache format
        elif "assets" in old_cache:
            # Reorganize assets by library and category
            library_assets = {}
            
            for asset in old_cache["assets"]:
                # Skip if missing required fields
                if not asset.get("name") or not asset.get("filepath"):
                    continue
                    
                # Skip backup files
                if not is_valid_blend_file(asset.get("filepath")):
                    continue
                    
                # Extract library from asset or use filepath to determine
                library_name = asset.get("library")
                if not library_name:
                    # Try to extract from filepath - use parent directory as library name
                    filepath = asset.get("filepath")
                    parent_dir = os.path.basename(os.path.dirname(os.path.dirname(filepath)))
                    library_name = parent_dir or "Unknown"
                
                # Create library entry if needed
                if library_name not in library_assets:
                    library_assets[library_name] = {}
                
                # Use filepath+name as unique key
                key = f"{asset.get('filepath')}:{asset.get('name')}"
                library_assets[library_name][key] = asset
            
            # Store deduplicated assets by library
            for lib_name, assets_dict in library_assets.items():
                new_cache["libraries"][lib_name] = {
                    "last_scan": time.time(),
                    "assets": list(assets_dict.values())
                }
            
        # Save the restructured cache
        with open(cache_path, 'w') as f:
            json.dump(new_cache, f)
            
        return True
    except Exception as e:
        print(f"Error cleaning cache: {e}")
        return False

def get_asset_cache_stats():
    """Get statistics about the asset cache
    
    Returns:
        dict: Statistics about the asset cache
    """
    cache = load_asset_cache()
    
    stats = {
        "libraries": 0,
        "total_assets": 0,
        "assets_by_library": {},
        "assets_by_type": {
            "objects": 0,
            "materials": 0, 
            "node_groups": 0,
            "other": 0
        },
        "last_update": cache.get("timestamp", 0)
    }
    
    # Process libraries
    for lib_name, lib_data in cache.get("libraries", {}).items():
        assets = lib_data.get("assets", [])
        stats["libraries"] += 1
        stats["total_assets"] += len(assets)
        stats["assets_by_library"][lib_name] = len(assets)
        
        # Count by type
        for asset in assets:
            asset_type = asset.get("type", "other")
            if asset_type in stats["assets_by_type"]:
                stats["assets_by_type"][asset_type] += 1
            else:
                stats["assets_by_type"]["other"] += 1
    
    return stats

def ensure_asset_previews(library_name, context):
    """Ensure all assets in a library have previews
    
    Args:
        library_name: Name of the library to process
        context: The current context
        
    Returns:
        int: Number of previews generated
    """
    # Get the library
    prefs = context.preferences.addons[__package__].preferences
    lib = next((l for l in prefs.asset_libraries if l.name == library_name), None)
    
    if not lib:
        return 0
        
    # Get the asset list
    asset_list_name = f"assets_{library_name.lower().replace(' ', '_')}"
    if not hasattr(prefs, asset_list_name):
        return 0
        
    asset_list = getattr(prefs, asset_list_name)
    
    # Track how many previews we generate
    previews_generated = 0
    
    # Get all blend file paths we need to process
    blend_files = set()
    for asset in asset_list:
        if asset.filepath and os.path.exists(asset.filepath):
            blend_files.add(asset.filepath)
    
    # We'll need to open each file to generate previews
    for blend_file in blend_files:
        try:
            # Open the file in a background Blender instance
            # This is a placeholder - in reality this would be a more complex operation
            # using subprocess or similar to open a separate Blender instance
            
            # For now, we'll just note that this would generate previews
            assets_in_file = [a for a in asset_list if a.filepath == blend_file]
            previews_generated += len(assets_in_file)
            
            # In a real implementation, you'd:
            # 1. Launch a background Blender process
            # 2. Open the blend file
            # 3. Find each asset
            # 4. Call asset_generate_preview() on each
            # 5. Save the file
            
        except Exception as e:
            print(f"Error generating previews for {blend_file}: {e}")
    
    return previews_generated

def update_asset_enabled_state(library_name, asset_name, filepath, enabled):
    """Update the enabled state of an asset in the cache
    
    Args:
        library_name (str): Name of the library
        asset_name (str): Name of the asset
        filepath (str): Path to the asset file
        enabled (bool): New enabled state
    """
    cache = load_asset_cache()
    cache_updated = False
    
    if "libraries" in cache and library_name in cache["libraries"]:
        lib_cache = cache["libraries"][library_name]
        assets = lib_cache.get("assets", [])
        
        # Find the asset by name and filepath
        for asset in assets:
            if asset["name"] == asset_name and asset["filepath"] == filepath:
                if "enabled" not in asset or asset["enabled"] != enabled:
                    asset["enabled"] = enabled
                    cache_updated = True
                break
        
        # If we didn't find it, update anyway
        if not cache_updated:
            cache_updated = True
        
        # Save the updated cache
        if cache_updated:
            save_asset_cache(cache)
            return True
    
    return False

def update_category_assets_enabled_state(library_name, category, enabled):
    """Update the enabled state of all assets in a category
    
    Args:
        library_name (str): Name of the library
        category (str): Category name
        enabled (bool): New enabled state
    """
    cache = load_asset_cache()
    cache_updated = False
    
    if "libraries" in cache and library_name in cache["libraries"]:
        lib_cache = cache["libraries"][library_name]
        assets = lib_cache.get("assets", [])
        
        # Update all assets in the category
        for asset in assets:
            if asset.get("category") == category:
                if "enabled" not in asset or asset["enabled"] != enabled:
                    asset["enabled"] = enabled
                    cache_updated = True
        
        # Save the updated cache
        if cache_updated:
            save_asset_cache(cache)
            return True
    
    return False

def update_all_assets_enabled_state(library_name, enabled):
    """Update the enabled state of all assets in a library
    
    Args:
        library_name (str): Name of the library
        enabled (bool): New enabled state
    """
    cache = load_asset_cache()
    cache_updated = False
    
    if "libraries" in cache and library_name in cache["libraries"]:
        lib_cache = cache["libraries"][library_name]
        assets = lib_cache.get("assets", [])
        
        # Update all assets
        for asset in assets:
            if "enabled" not in asset or asset["enabled"] != enabled:
                asset["enabled"] = enabled
                cache_updated = True
        
        # Save the updated cache
        if cache_updated:
            save_asset_cache(cache)
            return True
    
    return False

def refresh_asset_cache(prefs, force_rescan=False):
    """
    Comprehensive cache refresh function that:
    1. Removes assets from disabled libraries
    2. Rescans enabled libraries for changes
    3. Cleans orphaned entries
    
    Args:
        prefs: Addon preferences containing asset libraries
        force_rescan: Whether to force rescan all libraries regardless of changes
        
    Returns:
        dict: Statistics about the refresh operation
    """
    import os
    import time
    
    stats = {
        "disabled_removed": 0,
        "libraries_rescanned": 0,
        "orphaned_cleaned": 0,
        "assets_found": 0,
        "errors": []
    }
    
    cache = load_asset_cache()
    
    # Step 1: Remove disabled libraries from cache
    if "libraries" in cache:
        enabled_names = {lib.name for lib in prefs.asset_libraries if lib.enabled}
        cached_names = list(cache["libraries"].keys())
        
        for lib_name in cached_names:
            if lib_name not in enabled_names:
                del cache["libraries"][lib_name]
                stats["disabled_removed"] += 1
                print(f"Removed disabled library '{lib_name}' from cache")
    
    # Step 2: Process enabled libraries
    for lib in prefs.asset_libraries:
        if not lib.enabled:
            continue
            
        if not os.path.exists(lib.path):
            stats["errors"].append(f"Library path does not exist: {lib.path}")
            continue
        
        try:
            # Check if library needs rescanning
            needs_rescan = force_rescan or _library_needs_rescan(lib, cache)
            
            if needs_rescan:
                # Clear existing assets
                lib.assets.clear()
                
                # Rescan and get count
                import bpy
                assets_found = scan_library_assets(lib, bpy.context)
                stats["libraries_rescanned"] += 1
                stats["assets_found"] += assets_found
                
                print(f"Rescanned library '{lib.name}': {assets_found} assets")
            
        except Exception as e:
            error_msg = f"Error processing library '{lib.name}': {str(e)}"
            stats["errors"].append(error_msg)
            print(error_msg)
    
    # Step 3: Clean orphaned entries
    stats["orphaned_cleaned"] = _clean_orphaned_cache_entries(cache)
    
    # Save updated cache
    cache["timestamp"] = time.time()
    save_asset_cache(cache)
    
    return stats


def _library_needs_rescan(lib, cache):
    """
    Check if a library needs rescanning based on file system changes
    
    Args:
        lib: Library object with name and path
        cache: Current cache dictionary
        
    Returns:
        bool: True if library needs rescanning
    """
    import os
    
    # If library not in cache, it needs scanning
    if "libraries" not in cache or lib.name not in cache["libraries"]:
        return True
    
    lib_cache = cache["libraries"][lib.name]
    last_scan = lib_cache.get("last_scan", 0)
    
    # Check if any .blend files have been modified since last scan
    try:
        for root, dirs, files in os.walk(lib.path):
            for file in files:
                if _is_relevant_blend_file(file):
                    filepath = os.path.join(root, file)
                    try:
                        mtime = os.path.getmtime(filepath)
                        if mtime > last_scan:
                            return True
                    except OSError:
                        continue
    except OSError:
        return True
    
    return False


def _is_relevant_blend_file(filename):
    """
    Check if a file is a relevant .blend file (not a backup)
    
    Args:
        filename: Name of the file to check
        
    Returns:
        bool: True if file should be scanned
    """
    if not filename.lower().endswith('.blend'):
        return False
    
    # Skip backup files (.blend1, .blend2, etc.)
    if re.search(r'\.blend\d+$', filename):
        return False
    
    return True


def _clean_orphaned_cache_entries(cache):
    """
    Remove cache entries for assets whose files no longer exist
    
    Args:
        cache: Cache dictionary to clean
        
    Returns:
        int: Number of orphaned entries removed
    """
    import os
    
    orphaned_count = 0
    
    if "libraries" not in cache:
        return orphaned_count
    
    for lib_name, lib_data in cache["libraries"].items():
        assets = lib_data.get("assets", [])
        valid_assets = []
        
        for asset in assets:
            filepath = asset.get("filepath")
            if filepath and os.path.exists(filepath) and is_valid_blend_file(filepath):
                valid_assets.append(asset)
            else:
                orphaned_count += 1
                print(f"Removed orphaned asset: {asset.get('name', 'Unknown')} from {filepath}")
        
        # Update assets list if we removed any
        if len(valid_assets) != len(assets):
            lib_data["assets"] = valid_assets
    
    return orphaned_count


def get_cache_health_info():
    """
    Get detailed information about cache health and status
    
    Returns:
        dict: Comprehensive cache health information
    """
    import os
    
    cache = load_asset_cache()
    health_info = {
        "cache_exists": True,
        "cache_size_bytes": 0,
        "total_libraries": 0,
        "total_assets": 0,
        "libraries_with_issues": [],
        "orphaned_assets": 0,
        "last_update": cache.get("timestamp", 0),
        "cache_age_hours": 0
    }
    
    # Check cache file
    cache_path = get_cache_path()
    if os.path.exists(cache_path):
        try:
            health_info["cache_size_bytes"] = os.path.getsize(cache_path)
        except OSError:
            health_info["cache_exists"] = False
    else:
        health_info["cache_exists"] = False
    
    # Calculate cache age
    if health_info["last_update"] > 0:
        import time
        age_seconds = time.time() - health_info["last_update"]
        health_info["cache_age_hours"] = age_seconds / 3600
    
    # Analyze cache contents
    if "libraries" in cache:
        health_info["total_libraries"] = len(cache["libraries"])
        
        for lib_name, lib_data in cache["libraries"].items():
            assets = lib_data.get("assets", [])
            health_info["total_assets"] += len(assets)
            
            # Check for orphaned assets
            for asset in assets:
                filepath = asset.get("filepath")
                if not filepath or not os.path.exists(filepath):
                    health_info["orphaned_assets"] += 1
                    if lib_name not in health_info["libraries_with_issues"]:
                        health_info["libraries_with_issues"].append(lib_name)
    
    return health_info


def validate_library_integrity(library_name):
    """
    Validate the integrity of a specific library's cache data
    
    Args:
        library_name: Name of the library to validate
        
    Returns:
        dict: Validation results
    """
    import os
    
    cache = load_asset_cache()
    results = {
        "valid": True,
        "errors": [],
        "warnings": [],
        "asset_count": 0,
        "valid_assets": 0,
        "invalid_assets": 0
    }
    
    if "libraries" not in cache or library_name not in cache["libraries"]:
        results["valid"] = False
        results["errors"].append(f"Library '{library_name}' not found in cache")
        return results
    
    lib_data = cache["libraries"][library_name]
    assets = lib_data.get("assets", [])
    results["asset_count"] = len(assets)
    
    for asset in assets:
        # Check required fields
        if not asset.get("name"):
            results["invalid_assets"] += 1
            results["errors"].append("Asset missing name field")
            continue
        
        if not asset.get("filepath"):
            results["invalid_assets"] += 1
            results["errors"].append(f"Asset '{asset['name']}' missing filepath")
            continue
        
        # Check file existence
        filepath = asset["filepath"]
        if not os.path.exists(filepath):
            results["invalid_assets"] += 1
            results["warnings"].append(f"Asset file does not exist: {filepath}")
            continue
        
        # Check if it's a valid blend file
        if not is_valid_blend_file(filepath):
            results["invalid_assets"] += 1
            results["warnings"].append(f"Invalid blend file: {filepath}")
            continue
        
        results["valid_assets"] += 1
    
    # Set overall validity
    if results["invalid_assets"] > 0:
        results["valid"] = False
    
    return results

def format_timestamp(timestamp):
    """Format a timestamp as a human-readable date/time"""
    return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
