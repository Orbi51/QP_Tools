# Enhanced asset_cache_operators.py
import bpy
import os
import time
from bpy.types import Operator
from bpy.props import StringProperty, BoolProperty

from . import asset_cache

class QP_OT_ScanLibraryAssets(Operator):
    """Scan library for assets with improved caching"""
    bl_idname = "qp.scan_library_assets"
    bl_label = "Scan Library Assets"
    
    library_name: StringProperty(name="Library Name")
    
    def execute(self, context):
        # Get the library
        prefs = context.preferences.addons[__package__].preferences
        lib = next((l for l in prefs.asset_libraries if l.name == self.library_name), None)
        
        if not lib:
            self.report({'ERROR'}, f"Library {self.library_name} not found")
            return {'CANCELLED'}
        
        # Use the enhanced scan function
        assets_found = asset_cache.scan_library_assets(lib, context)
        
        self.report({'INFO'}, f"Found {assets_found} assets in {self.library_name}")
        return {'FINISHED'}


class QP_OT_RefreshAssetCache(Operator):
    """Refresh the asset cache - remove disabled libraries and rescan enabled ones"""
    bl_idname = "qp.refresh_asset_cache"
    bl_label = "Refresh Cache"
    bl_description = "Remove cached assets from disabled libraries and rescan enabled libraries for changes"
    
    force_rescan: BoolProperty(
        name="Force Rescan",
        description="Force rescan all enabled libraries even if they haven't changed",
        default=False
    )
    
    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences
        
        if not prefs.asset_libraries:
            self.report({'WARNING'}, "No asset libraries found")
            return {'CANCELLED'}
        
        # Step 1: Remove cached assets from disabled libraries
        disabled_removed = self._remove_disabled_libraries_from_cache(prefs)
        
        # Step 2: Rescan enabled libraries
        enabled_rescanned = self._rescan_enabled_libraries(prefs, context)
        
        # Step 3: Clean up orphaned cache entries
        orphaned_cleaned = self._clean_orphaned_cache_entries(prefs)
        
        # Report results
        total_changes = disabled_removed + enabled_rescanned + orphaned_cleaned
        if total_changes > 0:
            message_parts = []
            if disabled_removed > 0:
                message_parts.append(f"Removed {disabled_removed} disabled libraries")
            if enabled_rescanned > 0:
                message_parts.append(f"Rescanned {enabled_rescanned} enabled libraries")
            if orphaned_cleaned > 0:
                message_parts.append(f"Cleaned {orphaned_cleaned} orphaned entries")
            
            self.report({'INFO'}, f"Cache refreshed: {', '.join(message_parts)}")
        else:
            self.report({'INFO'}, "Cache is up to date")
            
        return {'FINISHED'}
    
    def _remove_disabled_libraries_from_cache(self, prefs):
        """Remove cached assets from libraries that are disabled"""
        cache = asset_cache.load_asset_cache()
        libraries_removed = 0
        
        if "libraries" not in cache:
            return libraries_removed
        
        # Get list of enabled library names
        enabled_library_names = {lib.name for lib in prefs.asset_libraries if lib.enabled}
        
        # Find libraries in cache that are not enabled
        cached_library_names = list(cache["libraries"].keys())
        
        for lib_name in cached_library_names:
            if lib_name not in enabled_library_names:
                # Remove this library from cache
                del cache["libraries"][lib_name]
                libraries_removed += 1
                print(f"Removed disabled library '{lib_name}' from cache")
        
        # Save the updated cache if changes were made
        if libraries_removed > 0:
            cache["timestamp"] = time.time()
            asset_cache.save_asset_cache(cache)
        
        return libraries_removed
    
    def _rescan_enabled_libraries(self, prefs, context):
        """Rescan enabled libraries for new/changed assets"""
        libraries_rescanned = 0
        
        for lib in prefs.asset_libraries:
            if lib.enabled:
                # Check if library path exists
                if not os.path.exists(lib.path):
                    print(f"Warning: Library path does not exist: {lib.path}")
                    continue
                
                # Check if rescan is needed
                if self.force_rescan or self._library_needs_rescan(lib):
                    try:
                        # Clear existing assets for this library
                        lib.assets.clear()
                        
                        # Rescan the library
                        assets_found = asset_cache.scan_library_assets(lib, context)
                        libraries_rescanned += 1
                        
                        print(f"Rescanned library '{lib.name}': found {assets_found} assets")
                        
                    except Exception as e:
                        print(f"Error rescanning library '{lib.name}': {str(e)}")
        
        return libraries_rescanned
    
    def _library_needs_rescan(self, lib):
        """Check if a library needs rescanning based on file system changes"""
        cache = asset_cache.load_asset_cache()
        
        # If library not in cache, it needs scanning
        if "libraries" not in cache or lib.name not in cache["libraries"]:
            return True
        
        lib_cache = cache["libraries"][lib.name]
        last_scan = lib_cache.get("last_scan", 0)
        
        # Check if any .blend files in the library have been modified since last scan
        try:
            for root, dirs, files in os.walk(lib.path):
                for file in files:
                    if file.lower().endswith('.blend') and not file.endswith('.blend1'):
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
    
    def _clean_orphaned_cache_entries(self, prefs):
        """Clean up cache entries for assets whose files no longer exist"""
        cache = asset_cache.load_asset_cache()
        orphaned_cleaned = 0
        
        if "libraries" not in cache:
            return orphaned_cleaned
        
        for lib_name, lib_data in cache["libraries"].items():
            assets = lib_data.get("assets", [])
            valid_assets = []
            
            for asset in assets:
                filepath = asset.get("filepath")
                if filepath and os.path.exists(filepath) and asset_cache.is_valid_blend_file(filepath):
                    valid_assets.append(asset)
                else:
                    orphaned_cleaned += 1
                    print(f"Removed orphaned asset: {asset.get('name', 'Unknown')} from {filepath}")
            
            # Update the assets list if we removed any
            if len(valid_assets) != len(assets):
                lib_data["assets"] = valid_assets
        
        # Save the updated cache if changes were made
        if orphaned_cleaned > 0:
            cache["timestamp"] = time.time()
            asset_cache.save_asset_cache(cache)
        
        return orphaned_cleaned


class QP_OT_AssetCacheStats(Operator):
    """Show statistics about the asset cache"""
    bl_idname = "qp.asset_cache_stats"
    bl_label = "Cache Stats"
    bl_description = "Show detailed statistics about the asset cache"
    
    def execute(self, context):
        stats = asset_cache.get_asset_cache_stats()
        
        # Format timestamp
        timestamp = asset_cache.format_timestamp(stats["last_update"])
        
        # Build detailed statistics
        info_lines = [
            "=== Asset Cache Statistics ===",
            f"Libraries: {stats['libraries']}",
            f"Total Assets: {stats['total_assets']}",
            "",
            "Assets by Type:",
            f"  • Objects: {stats['assets_by_type']['objects']}",
            f"  • Materials: {stats['assets_by_type']['materials']}",
            f"  • Node Groups: {stats['assets_by_type']['node_groups']}",
            f"  • Other: {stats['assets_by_type']['other']}",
            "",
            f"Last Updated: {timestamp}",
            "",
            "Library Details:"
        ]
        
        # Add per-library statistics
        if "assets_by_library" in stats:
            for lib_name, count in stats["assets_by_library"].items():
                info_lines.append(f"  • {lib_name}: {count} assets")
        
        # Show in console and as popup
        info_text = "\n".join(info_lines)
        print(info_text)
        
        # Show key stats in the operator report
        summary = f"Cache: {stats['libraries']} libraries, {stats['total_assets']} assets (last updated: {timestamp})"
        self.report({'INFO'}, summary)
        
        return {'FINISHED'}


class QP_OT_ForceRefreshLibrary(Operator):
    """Force refresh a specific library"""
    bl_idname = "qp.force_refresh_library"
    bl_label = "Force Refresh Library"
    bl_description = "Force a complete refresh of a specific library"
    
    library_name: StringProperty(name="Library Name")
    
    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences
        lib = next((l for l in prefs.asset_libraries if l.name == self.library_name), None)
        
        if not lib:
            self.report({'ERROR'}, f"Library {self.library_name} not found")
            return {'CANCELLED'}
        
        if not lib.enabled:
            self.report({'WARNING'}, f"Library {self.library_name} is disabled")
            return {'CANCELLED'}
        
        try:
            # Clear existing assets
            lib.assets.clear()
            
            # Remove from cache
            cache = asset_cache.load_asset_cache()
            if "libraries" in cache and self.library_name in cache["libraries"]:
                del cache["libraries"][self.library_name]
                asset_cache.save_asset_cache(cache)
            
            # Rescan the library
            assets_found = asset_cache.scan_library_assets(lib, context)
            
            self.report({'INFO'}, f"Force refreshed {self.library_name}: found {assets_found} assets")
            
        except Exception as e:
            self.report({'ERROR'}, f"Failed to refresh {self.library_name}: {str(e)}")
            return {'CANCELLED'}
        
        return {'FINISHED'}
    
class QP_OT_ShowCacheHealth(Operator):
    """Show detailed cache health information"""
    bl_idname = "qp.show_cache_health"
    bl_label = "Show Cache Health"
    bl_description = "Display detailed information about cache health and status"
    
    def execute(self, context):
        health_info = asset_cache.get_cache_health_info()
        
        # Build health report
        lines = ["=== Asset Cache Health Report ==="]
        
        if not health_info["cache_exists"]:
            lines.append("❌ Cache file does not exist")
        else:
            lines.append("✅ Cache file exists")
            
            # File size
            size_mb = health_info["cache_size_bytes"] / (1024 * 1024)
            lines.append(f"📁 Cache size: {size_mb:.2f} MB")
            
            # Age
            if health_info["cache_age_hours"] < 1:
                age_text = f"{health_info['cache_age_hours'] * 60:.0f} minutes"
            elif health_info["cache_age_hours"] < 24:
                age_text = f"{health_info['cache_age_hours']:.1f} hours"
            else:
                age_text = f"{health_info['cache_age_hours'] / 24:.1f} days"
            lines.append(f"⏰ Cache age: {age_text}")
            
            # Content summary
            lines.append(f"📚 Libraries: {health_info['total_libraries']}")
            lines.append(f"📦 Total assets: {health_info['total_assets']}")
            
            # Issues
            if health_info["orphaned_assets"] > 0:
                lines.append(f"⚠️  Orphaned assets: {health_info['orphaned_assets']}")
            
            if health_info["libraries_with_issues"]:
                lines.append(f"⚠️  Libraries with issues: {', '.join(health_info['libraries_with_issues'])}")
            
            if health_info["orphaned_assets"] == 0 and not health_info["libraries_with_issues"]:
                lines.append("✅ No issues detected")
        
        # Show in console and report summary
        health_report = "\n".join(lines)
        print(health_report)
        
        # Short summary for UI
        if health_info["cache_exists"]:
            summary = f"Cache: {health_info['total_libraries']} libraries, {health_info['total_assets']} assets"
            if health_info["orphaned_assets"] > 0:
                summary += f", {health_info['orphaned_assets']} orphaned"
        else:
            summary = "Cache file missing"
        
        self.report({'INFO'}, summary)
        return {'FINISHED'}


class QP_OT_ValidateLibrary(Operator):
    """Validate a specific library's cache integrity"""
    bl_idname = "qp.validate_library"
    bl_label = "Validate Library"
    bl_description = "Check the integrity of a specific library's cache data"
    
    library_name: StringProperty(name="Library Name")
    
    def execute(self, context):
        results = asset_cache.validate_library_integrity(self.library_name)
        
        if results["valid"]:
            message = f"✅ Library '{self.library_name}' is valid: {results['valid_assets']} assets"
        else:
            message = f"❌ Library '{self.library_name}' has issues: {results['invalid_assets']} invalid assets"
        
        # Print detailed results
        print(f"\n=== Library Validation: {self.library_name} ===")
        print(f"Total assets: {results['asset_count']}")
        print(f"Valid assets: {results['valid_assets']}")
        print(f"Invalid assets: {results['invalid_assets']}")
        
        if results["errors"]:
            print("Errors:")
            for error in results["errors"]:
                print(f"  - {error}")
        
        if results["warnings"]:
            print("Warnings:")
            for warning in results["warnings"]:
                print(f"  - {warning}")
        
        self.report({'INFO' if results["valid"] else 'WARNING'}, message)
        return {'FINISHED'}