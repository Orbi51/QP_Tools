---
name: blender-python-development
description: Expert guidance for developing Blender 4.2+ and 5.0 Python extensions with performance optimization, msgbus patterns, critical API migration strategies, and best practices for addon architecture.
---

# Blender Python Development Skill

## AI Agent Instructions

**Response Style:**
- Be concise. Explain changes briefly, not exhaustively.
- State what was done and why in 1-2 sentences max per change.
- Don't over-explain logic the user can read in the code.
- If multiple changes, use a short bullet list.

**Code Principles (MANDATORY):**
- **Maintainability first**: Write clear, self-documenting code with meaningful names.
- **Code reuse**: Extract repeated logic into helper functions. Never duplicate code.
- **Single responsibility**: One function = one job. Keep functions small and focused.
- **DRY (Don't Repeat Yourself)**: If you write similar code twice, refactor it.
- **Type hints + docstrings**: Required on all public functions/classes.
- **Testable**: Structure code so functions can be tested in isolation.

**When Generating Code:**
1. Check if a helper already exists before writing new code.
2. Prefer pure functions over stateful ones where possible.
3. Group related functionality into classes or modules.
4. Use descriptive variable names (no single letters except loop indices).

---

## Quick Reference (Read First)

### Critical Performance Rules
| Pattern | Performance | Use When |
|---------|-------------|----------|
| `bpy.msgbus` | Zero CPU idle | Monitoring property changes |
| `bpy.app.timers` | Constant CPU | Time-based/scheduled tasks ONLY |
| Direct API | 75-200x faster | Batch object creation/modification |
| `bpy.ops` | Very slow | Single user-initiated actions only |
| NumPy + `foreach_get/set` | 7-12x faster | Bulk mesh data operations |

### Critical Gotchas (Memory Safety)
```python
# ❌ CRASHES - References invalidated by undo/mode switch
mesh = bpy.context.active_object.data
vertices = mesh.vertices  # Stored reference
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.object.mode_set(mode='OBJECT')
print(vertices[0].co)  # CRASH - memory freed

# ✅ SAFE - Re-fetch after any operation that may invalidate
mesh = bpy.context.active_object.data
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.object.mode_set(mode='OBJECT')
mesh = bpy.context.active_object.data  # Re-fetch
vertices = mesh.vertices  # Fresh reference
print(vertices[0].co)  # Safe
```

### String Quote Convention (Blender Standard)
```python
# Single quotes for enums/identifiers
obj.type == 'MESH'
context.mode == 'OBJECT'
self.report({'INFO'}, message)

# Double quotes for user-facing strings
obj.name = "My Object"
self.report({'INFO'}, "Operation complete")
```

---

## Overview

This Skill provides comprehensive guidance for developing Blender Python extensions (addons) with a focus on performance, modern patterns, and proper architecture. Use this Skill when:

- Creating new Blender addons or extensions
- Migrating addons across Blender versions (4.2, 4.3, 4.5, 5.0)
- **Migrating to Blender 5.0** (critical breaking changes require immediate action)
- Debugging performance issues in Blender Python code
- Implementing event-driven patterns with msgbus
- Working with Grease Pencil, operators, panels, or modal operations
- Optimizing mesh operations with NumPy and BMesh
- Setting up proper memory management and cleanup

**⚠️ Blender 5.0 Note:** This version introduces the most significant Python API changes in years. The legacy Action API is completely removed, compositor is restructured, and Video Sequencer types are renamed. See the API Version Changes section and REFERENCE.md for critical migration information.

---

## Core Principles

### 1. 🔥 CRITICAL: Always Prefer msgbus Over Timers

**Most important performance rule**: Use `bpy.msgbus` (event-driven) instead of `bpy.app.timers` (polling) for monitoring property changes. This provides **7-12x better performance** and **zero CPU when idle**.

```python
# ✅ CORRECT - Event-driven, zero CPU idle
owner = object()

def on_property_change(*args):
    print("Property changed")

bpy.msgbus.subscribe_rna(
    key=(bpy.types.Object, "location"),
    owner=owner,
    args=(),
    notify=on_property_change,
    options={'PERSISTENT'}
)

# Clean up in unregister()
bpy.msgbus.clear_by_owner(owner)
```

```python
# ❌ WRONG - Continuous polling, constant CPU usage
def check_property():
    print("Checking...")
    return 1.0  # Runs every second

bpy.app.timers.register(check_property)
```

**Use timers ONLY for:**
- Time-based operations (scheduled tasks)
- Delayed actions
- Thread coordination
- Progressive animations

### 2. Avoid bpy.ops in Loops (75-200x Slower)

Operators are **75-200x slower** than direct API access.

```python
# ❌ WRONG - Extremely slow (6-60 seconds for 1000 objects)
for i in range(1000):
    bpy.ops.mesh.primitive_cube_add(location=(i, 0, 0))

# ✅ CORRECT - Fast (0.08-0.3 seconds for 1000 objects)
mesh = bpy.data.meshes.new("CubeMesh")
# Create mesh data once
mesh.from_pydata(vertices, edges, faces)

for i in range(1000):
    obj = bpy.data.objects.new(f"Cube_{i}", mesh)
    obj.location = (i % 100, i // 100, 0)
    bpy.context.scene.collection.objects.link(obj)

bpy.context.view_layer.update()  # Single update at end
```

### 3. Use NumPy + foreach_get/foreach_set (7-12x Faster)

```python
import numpy as np

def scale_mesh_numpy(obj: bpy.types.Object, factor: float) -> None:
    """Scale mesh vertices using NumPy (7x faster than Python loops)."""
    me = obj.data
    count = len(me.vertices)
    
    # Pre-allocate array
    coords = np.empty(count * 3, dtype=np.float64)
    
    # Fast bulk operations
    me.vertices.foreach_get('co', coords)
    coords.shape = (count, 3)
    coords *= factor
    coords.shape = count * 3
    me.vertices.foreach_set('co', coords)
    
    me.update()
```

---

## Blender API Gotchas (Critical)

### Undo Invalidates All ID References

After undo, **all** bpy.types.ID references (Object, Mesh, Scene, Material, etc.) become invalid.

```python
# ❌ WRONG - Reference invalid after undo
obj = bpy.context.active_object
# ... user presses Ctrl+Z ...
print(obj.name)  # May crash or give garbage data

# ✅ CORRECT - Store names, re-fetch when needed
obj_name = bpy.context.active_object.name
# ... user presses Ctrl+Z ...
obj = bpy.data.objects.get(obj_name)
if obj:
    print(obj.name)
```

**Rule:** Never store `bpy_struct` references long-term. Store names/keys and re-fetch.

### Mode Switching Invalidates Mesh Data

`mode_set()` re-allocates mesh data. All vertex/polygon/edge references become invalid.

```python
# ❌ WRONG - vertices reference invalid after mode switch
mesh = obj.data
verts = mesh.vertices
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.object.mode_set(mode='OBJECT')
print(verts[0].co)  # CRASH

# ✅ CORRECT - Re-fetch after mode switch
mesh = obj.data
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.object.mode_set(mode='OBJECT')
mesh = obj.data  # Re-fetch
verts = mesh.vertices
print(verts[0].co)  # Safe
```

### Deferred Updates (matrix_world Not Immediate)

Blender defers recalculations until needed. After changing `location`, `matrix_world` isn't updated until you force it.

```python
obj.location = (1, 2, 3)
print(obj.matrix_world)  # Still shows OLD value!

# Force update
bpy.context.view_layer.update()
print(obj.matrix_world)  # Now correct
```

### Handler Infinite Loops

Modifying data inside `depsgraph_update_post` triggers another update, causing infinite loops.

```python
# ❌ WRONG - Infinite loop
@bpy.app.handlers.persistent
def on_update(scene, depsgraph):
    bpy.context.active_object.location.x += 0.1  # Triggers another update!

# ✅ CORRECT - Use flag to prevent recursion
_updating = False

@bpy.app.handlers.persistent
def on_update(scene, depsgraph):
    global _updating
    if _updating:
        return
    _updating = True
    try:
        # Your logic here
        pass
    finally:
        _updating = False
```

### Never Use bpy.context in Handlers/Drivers

Handlers and drivers receive their own context. Using `bpy.context` can give wrong results.

```python
# ❌ WRONG
@bpy.app.handlers.persistent
def handler(scene, depsgraph):
    obj = bpy.context.active_object  # May be wrong/outdated

# ✅ CORRECT - Use passed depsgraph
@bpy.app.handlers.persistent
def handler(scene, depsgraph):
    for update in depsgraph.updates:
        obj = update.id  # Use depsgraph data
```

### @persistent Decorator Required for File Load Survival

Handlers without `@persistent` are removed when loading a new file.

```python
from bpy.app.handlers import persistent

@persistent  # Required!
def my_handler(scene, depsgraph):
    pass

def register():
    bpy.app.handlers.depsgraph_update_post.append(my_handler)
```

---

## Python Code Quality Standards

### Type Hints (MANDATORY)

**MUST** use type hints for all function signatures.

```python
from typing import Optional

def get_selected_objects(context: bpy.types.Context) -> list[bpy.types.Object]:
    """Return list of selected objects."""
    return [obj for obj in context.selected_objects]

def create_material(
    name: str, 
    color: tuple[float, float, float, float]
) -> Optional[bpy.types.Material]:
    """Create a new material with specified color.
    
    Args:
        name: Material name
        color: RGBA color tuple (values 0.0-1.0)
    
    Returns:
        Created material or None if creation failed
    """
    mat = bpy.data.materials.new(name)
    if mat:
        mat.diffuse_color = color
    return mat
```

**Never use `Any` type** unless absolutely necessary. Be specific about Blender types.

### Docstrings (MANDATORY)

**MUST** include docstrings for all public functions, classes, and operators.

```python
def apply_modifier(
    obj: bpy.types.Object, 
    modifier_name: str, 
    keep_modifier: bool = False
) -> bool:
    """Apply a modifier to an object.
    
    Args:
        obj: Target object
        modifier_name: Name of modifier to apply
        keep_modifier: If True, keep modifier after applying
    
    Returns:
        True if successful, False otherwise
    
    Raises:
        RuntimeError: If modifier doesn't exist or can't be applied
    """
    if modifier_name not in obj.modifiers:
        raise RuntimeError(f"Modifier '{modifier_name}' not found on object '{obj.name}'")
    
    # Implementation here
    return True
```

### Error Handling

**NEVER** silently swallow exceptions. Always log or report errors.

```python
# ✅ CORRECT - Proper error handling in operators
def execute(self, context):
    try:
        obj = context.active_object
        if obj is None:
            self.report({'ERROR'}, "No active object")
            return {'CANCELLED'}
        
        apply_modifier(obj, "Subdivision")
        
    except RuntimeError as e:
        self.report({'ERROR'}, f"Failed to apply modifier: {e}")
        return {'CANCELLED'}
    except Exception as e:
        self.report({'ERROR'}, f"Unexpected error: {e}")
        return {'CANCELLED'}
    
    return {'FINISHED'}

# ❌ WRONG - Bare except hides bugs
def execute(self, context):
    try:
        apply_modifier(context.active_object, "Subdivision")
    except:
        pass  # Silent failure!
    return {'FINISHED'}
```

**Use context managers** for resource cleanup:

```python
import bmesh

def edit_mesh(obj: bpy.types.Object) -> None:
    """Edit mesh with proper cleanup."""
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        for v in bm.verts:
            v.co.z += 1.0
        bm.to_mesh(obj.data)
    finally:
        bm.free()  # Always cleanup
```

### Reusable Helper Pattern

**Always extract repeated logic:**

```python
# ✅ CORRECT - Reusable helpers
def set_object_visibility(
    obj: bpy.types.Object, 
    viewport: bool, 
    render: bool
) -> None:
    """Set object visibility in viewport and render."""
    obj.hide_viewport = not viewport
    obj.hide_render = not render

def get_mesh_objects(context: bpy.types.Context) -> list[bpy.types.Object]:
    """Get all mesh objects in selection."""
    return [obj for obj in context.selected_objects if obj.type == 'MESH']

def ensure_object_mode(context: bpy.types.Context) -> None:
    """Switch to object mode if not already."""
    if context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
```

### Function Design

**Single Responsibility** - Each function should do one thing well.

```python
# ✅ CORRECT - Focused functions
def get_mesh_volume(obj: bpy.types.Object) -> float:
    """Calculate mesh volume using BMesh."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    volume = bm.calc_volume()
    bm.free()
    return volume

def report_volume_to_user(operator: bpy.types.Operator, obj: bpy.types.Object) -> None:
    """Display volume in UI."""
    volume = get_mesh_volume(obj)
    operator.report({'INFO'}, f"Volume: {volume:.4f}")

# ❌ WRONG - Function does too much
def calculate_and_display_volume(operator, obj):
    """Calculate and display - mixed concerns"""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    volume = bm.calc_volume()
    bm.free()
    operator.report({'INFO'}, f"Volume: {volume:.4f}")
    return volume
```

**Limit function parameters** to 5 or fewer. Use dataclasses for complex parameter sets.

```python
from dataclasses import dataclass

@dataclass
class MaterialSettings:
    base_color: tuple[float, float, float, float]
    metallic: float = 0.0
    roughness: float = 0.5
    emission_strength: float = 0.0

def create_pbr_material(name: str, settings: MaterialSettings) -> bpy.types.Material:
    """Create PBR material with settings."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    principled = nodes.get("Principled BSDF")
    
    principled.inputs["Base Color"].default_value = settings.base_color
    principled.inputs["Metallic"].default_value = settings.metallic
    principled.inputs["Roughness"].default_value = settings.roughness
    principled.inputs["Emission Strength"].default_value = settings.emission_strength
    
    return mat
```

**Never use mutable default arguments:**

```python
# ✅ CORRECT
def create_collection(
    name: str, 
    objects: Optional[list[bpy.types.Object]] = None
) -> bpy.types.Collection:
    if objects is None:
        objects = []
    
    collection = bpy.data.collections.new(name)
    for obj in objects:
        collection.objects.link(obj)
    return collection

# ❌ WRONG - Mutable default creates shared state
def create_collection(
    name: str, 
    objects: list[bpy.types.Object] = []
) -> bpy.types.Collection:
    # Bug: objects list shared across all calls!
    pass
```

### Code Style

**Use f-strings** for string formatting:

```python
# ✅ CORRECT
obj_name = context.active_object.name
self.report({'INFO'}, f"Processing object: {obj_name}")

# ❌ WRONG
self.report({'INFO'}, "Processing object: " + obj_name)
self.report({'INFO'}, "Processing object: %s" % obj_name)
```

**Use `is` for comparing** with `None`, `True`, `False`:

```python
# ✅ CORRECT
if obj is None:
    return
if modifier.show_viewport is True:
    pass

# ❌ WRONG  
if obj == None:
    return
```

### Imports Organization

Organize imports in three groups: standard library, third-party, Blender API.

```python
# Standard library
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Third-party (if needed)
import numpy as np

# Blender API
import bpy
import bmesh
from bpy.types import Context, Object, Operator
from bpy.props import FloatProperty, StringProperty
```

**Never use wildcard imports:**

```python
# ✅ CORRECT
from bpy.types import Operator, Panel, Object

# ❌ WRONG
from bpy.types import *
```

---

## Extension Structure (Blender 4.2+)

### Manifest File (blender_manifest.toml)

**CRITICAL:** Folder name MUST match the `id` field.

```toml
schema_version = "1.0.0"

id = "my_extension"  # Folder MUST be named "my_extension"
version = "1.0.0"
name = "My Extension"
tagline = "Short description under 64 characters"
maintainer = "Your Name <email@example.com>"
type = "add-on"
blender_version_min = "4.2.0"

license = ["SPDX:GPL-3.0-or-later"]

[permissions]
files = "Import and export files"
network = "Download updates"
```

### Modern Coding Patterns

```python
# Always use __package__ (never hardcode names)
class MyPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

# Check online access before network calls
if bpy.app.online_access:
    import requests
    response = requests.get(url)

# Use extension user data path
from pathlib import Path
user_data = Path(bpy.utils.extension_path_user(__package__, create=True))
```

---

## Operator Best Practices

```python
class OBJECT_OT_MyOperator(bpy.types.Operator):
    """Tooltip shown to users"""
    bl_idname = "object.my_operator"
    bl_label = "My Operator"
    bl_options = {'REGISTER', 'UNDO'}  # CRITICAL for undo
    
    my_value: bpy.props.FloatProperty(default=1.0)
    
    @classmethod
    def poll(cls, context):
        """Validate context."""
        if context.object is None:
            return False
        if context.object.type != 'MESH':
            cls.poll_message_set("Active object must be a mesh")
            return False
        return True
    
    def execute(self, context):
        """Main logic."""
        context.object.location.x += self.my_value
        return {'FINISHED'}
    
    def invoke(self, context, event):
        """Initialize from UI."""
        return self.execute(context)
```

---

## Memory Management - CRITICAL Cleanup Pattern

**Unregister in REVERSE order:**

```python
def register():
    bpy.utils.register_class(OperatorClass)
    bpy.utils.register_class(PanelClass)
    bpy.types.VIEW3D_MT_mesh_add.append(menu_func)
    bpy.types.Scene.my_prop = bpy.props.StringProperty()

def unregister():
    # REVERSE order!
    del bpy.types.Scene.my_prop
    bpy.types.VIEW3D_MT_mesh_add.remove(menu_func)
    bpy.utils.unregister_class(PanelClass)
    bpy.utils.unregister_class(OperatorClass)
```

**Always clean up:**
- msgbus subscriptions: `bpy.msgbus.clear_by_owner(owner)`
- Handlers: Remove from `bpy.app.handlers.*`
- Timers: `bpy.app.timers.unregister()`
- BMesh: `bm.free()` (CRITICAL - memory leak without this)
- Draw handlers: `bpy.types.SpaceView3D.draw_handler_remove()`

---

## API Version Changes

### 🔥 CRITICAL Blender 5.0 Breaking Changes

**These changes will break most existing addons:**

1. **Legacy Action API Removed** - `action.fcurves`, `action.groups`, `action.id_root` NO LONGER EXIST
   - Must use slotted Actions with channelbags
   - See REFERENCE.md for migration examples

2. **Compositor Restructured** - `scene.node_tree` REMOVED
   - Use `scene.compositing_node_group` instead
   - Compositor trees now reusable data blocks

3. **Video Sequencer Rename** - All `Sequence` types → `Strip`
   - `SequenceColorBalance` → `StripColorBalance`, etc.
   - Parameters: `seq1`/`seq2` → `input1`/`input2`

4. **IDProperties Static Typing** - Cannot change types from Python
   - Direct storage access blocked
   - Must use RNA properties

5. **Mathematical Precision** - Vectors now float32 (was float64)
   - Faster but less precise
   - Test precision-sensitive calculations

See REFERENCE.md for complete breaking changes in:
- **Blender 4.3**: Grease Pencil v3 rewrite, Brush Assets
- **Blender 4.5 LTS**: GPU API changes, GeometrySet API
- **Blender 5.0**: Action API removal, Compositor restructure, 255-byte names

### Quick Version Checks

```python
# Version detection for multi-version support
def is_blender_5_or_later() -> bool:
    return bpy.app.version >= (5, 0, 0)

# Context override (3.2+)
with bpy.context.temp_override(object=obj):
    bpy.ops.object.modifier_apply(modifier="Boolean")

# EEVEE engine check (5.0+)
if scene.render.engine == 'BLENDER_EEVEE':  # Changed from EEVEE_NEXT
    pass

# Compositor (5.0+)
if is_blender_5_or_later():
    tree = scene.compositing_node_group
else:
    tree = scene.node_tree
```

---

## Modal Operators

```python
class OBJECT_OT_ModalOperator(bpy.types.Operator):
    bl_idname = "object.modal_operator"
    bl_label = "Modal Operator"
    bl_options = {'REGISTER', 'UNDO'}
    
    def modal(self, context, event):
        if event.type in {'RIGHTMOUSE', 'ESC'}:
            self.cancel(context)
            return {'CANCELLED'}
        
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            return {'FINISHED'}
        
        if event.type == 'MOUSEMOVE':
            # Handle mouse movement
            pass
        
        return {'RUNNING_MODAL'}
    
    def invoke(self, context, event):
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}
    
    def cancel(self, context):
        # Cleanup here
        pass
```

---

## BMesh Operations

```python
import bmesh

obj = bpy.context.active_object
bm = bmesh.new()
bm.from_mesh(obj.data)

# Modify geometry
for v in bm.verts:
    v.co.x += 1.0

bmesh.ops.subdivide_edges(bm, edges=bm.edges, cuts=2)

# Write back
bm.to_mesh(obj.data)
bm.free()  # CRITICAL - always free
```

---

## Common Anti-Patterns to Avoid

❌ Never use timers for property monitoring (use msgbus)  
❌ Never create GPU resources at module level  
❌ Never use `sys.exit()` in addons  
❌ Never store `bpy_struct` references long-term (store names instead)  
❌ Never skip cleanup in `unregister()`  
❌ Never use hardcoded paths (use relative paths)  
❌ Never forget `bm.free()` after BMesh operations  
❌ Never use bare `except:` clauses (catch specific exceptions)  
❌ Never use mutable default arguments (lists, dicts)  
❌ Never silently swallow exceptions without logging  
❌ Never use wildcard imports (`from module import *`)  
❌ Never skip type hints on function signatures  
❌ Never skip docstrings on public functions and classes  
❌ Never use `bpy.context` inside handlers/drivers (use passed depsgraph)  
❌ Never modify data inside depsgraph handlers without recursion guard  
❌ Never forget `@persistent` decorator on handlers that should survive file load

---

## Quick Checklist

**Performance:**
- ✅ Use msgbus for property monitoring (NOT timers)
- ✅ Avoid bpy.ops in loops
- ✅ Use NumPy + foreach_get/foreach_set for bulk data
- ✅ Use BMesh for mesh editing
- ✅ Batch operations, update view layer once

**Code Quality:**
- ✅ Add type hints to all function signatures
- ✅ Write docstrings for all public functions/classes
- ✅ Use specific exception handling (no bare `except:`)
- ✅ Use context managers for resource cleanup
- ✅ Follow single responsibility principle
- ✅ Limit function parameters to 5 or fewer
- ✅ Never use mutable default arguments
- ✅ Use f-strings for string formatting
- ✅ Organize imports (stdlib, third-party, Blender)
- ✅ Single quotes for enums, double quotes for strings
- ✅ Extract reusable helper functions (DRY)

**Memory Safety:**
- ✅ Store names/keys, not object references
- ✅ Re-fetch data after mode switches
- ✅ Use recursion guards in depsgraph handlers
- ✅ Use `@persistent` on handlers
- ✅ Use passed depsgraph in handlers, not `bpy.context`

**Extensions (4.2+):**
- ✅ Create blender_manifest.toml
- ✅ Folder name matches manifest `id`
- ✅ Use `__package__` everywhere
- ✅ Use relative imports
- ✅ Check `bpy.app.online_access` before network

**Memory Cleanup:**
- ✅ Unregister in reverse order
- ✅ Clear msgbus subscriptions
- ✅ Remove handlers, timers, draw handlers
- ✅ Call `bm.free()` after BMesh
- ✅ Delete custom properties

---

## Documentation Resources

- Python API: https://docs.blender.org/api/current/
- API Gotchas: https://docs.blender.org/api/current/info_gotcha.html
- API Change Log: https://docs.blender.org/api/current/change_log.html
- Release Notes: https://developer.blender.org/docs/release_notes/
- Extensions Platform: https://extensions.blender.org

---

## When to Use This Skill

Apply this Skill whenever working on:
- Blender addon/extension development
- Python scripting for Blender automation
- Performance optimization of Blender tools
- Migrating addons between Blender versions
- Debugging Blender Python code
- Creating custom operators, panels, or UI
- Working with geometry, meshes, or Grease Pencil
- Implementing event-driven workflows

For detailed API changes across versions, refer to REFERENCE.md in this Skill package.
