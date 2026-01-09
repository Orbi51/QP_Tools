# Blender API Version Changes Reference

Complete breaking changes and migration guide for Blender 4.2, 4.3, 4.5 LTS, and 5.0.

## Documentation URLs

**Always check these official sources for the latest API changes:**

- **Python API Change Log**: https://docs.blender.org/api/current/change_log.html
- **Developer Release Notes**: https://developer.blender.org/docs/release_notes/
- **Version-specific API docs**: https://docs.blender.org/api/{version}/

---

## Blender 4.2 (Extensions Platform Introduction)

**Release Date:** July 16, 2024

**Official Docs:**
- Release Notes: https://developer.blender.org/docs/release_notes/4.2/
- Python API: https://developer.blender.org/docs/release_notes/4.2/python_api/

### Key Changes

**Extensions Platform Introduction**
- New `blender_manifest.toml` replaces `bl_info` dictionary
- Extensions use `bl_ext.{repository}.{addon_name}` namespacing
- Self-contained with bundled dependencies

**Context Override Deprecation (3.2+)**
```python
# OLD (deprecated)
bpy.ops.object.modifier_apply({"object": obj}, modifier="Boolean")

# NEW (3.2+)
with bpy.context.temp_override(object=obj):
    bpy.ops.object.modifier_apply(modifier="Boolean")
```

**EEVEE Material Changes**
```python
# OLD
material.blend_method
material.show_transparent_back
material.use_screen_refraction

# NEW
material.surface_render_method
material.use_transparency_overlap
material.use_raytrace_refraction
```

---

## Blender 4.3 (Grease Pencil v3 Rewrite)

**Release Date:** November 19, 2024

**Official Docs:**
- Release Notes: https://developer.blender.org/docs/release_notes/4.3/
- Python API: https://developer.blender.org/docs/release_notes/4.3/python_api/
- GP Migration: https://developer.blender.org/docs/release_notes/4.3/grease_pencil_migration/

### 🔥 CRITICAL: Complete Grease Pencil Rewrite (GPv3)

The old `frame.strokes` API is completely replaced.

**Migration Paths:**

**Option 1: Compatibility API (Quick)**
```python
# OLD (pre-4.3) - BROKEN
for stroke in frame.strokes:
    stroke.line_width = 10

# COMPATIBILITY (4.3+)
for stroke in frame.drawing.strokes:
    stroke.line_width = 10
```

**Option 2: New Attributes API (Performance)**
```python
# NEW API (4.3+) - Best performance
drawing = frame.drawing
line_widths = drawing.attributes["radius"].data
for i, width in enumerate(line_widths):
    line_widths[i] = 10
```

**Key Changes:**
- Frames now reference drawings containing stroke data
- All data stored as attributes on CURVE and POINT domains
- Layer groups support added
- Geometry nodes integration enabled
- Materials and vertex colors work differently

### Brush Assets System

All brushes converted to assets stored in asset libraries.

```python
# Must be in paint mode first
bpy.context.scene.tool_settings.image_paint.brush = brush_asset

# May need explicit activation
bpy.ops.brush.asset_activate(
    asset_library_reference='LOCAL',
    relative_asset_identifier=identifier
)
```

### AttributeGroup Type Split

```python
# OLD (pre-4.3)
mesh.attributes.active_color

# NEW (4.3+) - Type-specific
mesh.attributes_mesh.active_color  # AttributeGroupMesh only

# New types:
# - AttributeGroupMesh
# - AttributeGroupPointCloud
# - AttributeGroupCurves
# - AttributeGroupGreasePencil
```

### Other Breaking Changes

**Embedded ID Pointer Assignment**
```python
# Now raises RuntimeError (4.3+)
pointer_prop = embedded_id  # WILL FAIL
```

**Reroute Nodes**
```python
# OLD
reroute_node.inputs[0].type = 'VALUE'

# NEW (4.3+)
reroute_node.socket_idname = 'NodeSocketFloat'
```

### New Features

- `bpy.app.handlers.blend_import_pre` and `blend_import_post`
- `ID.rename()` function for complex renaming
- `domain_size()` added to all AttributeGroup types
- `uiLayout.template_search()` gained `text` argument
- `bpy.app.python_args` for environment matching

---

## Blender 4.5 LTS (GeometrySet API & GPU Changes)

**Release Date:** July 15, 2025  
**LTS Support:** Until July 2027

**Official Docs:**
- Release Notes: https://developer.blender.org/docs/release_notes/4.5/
- Python API: https://developer.blender.org/docs/release_notes/4.5/python_api/
- Geometry Nodes: https://developer.blender.org/docs/release_notes/4.5/geometry_nodes/
- Compatibility: https://developer.blender.org/docs/release_notes/compatibility/

### 🔥 CRITICAL: GPU Drawing API Changes

**Wide lines and smooth lines require POLYLINE shaders**
**Points require POINT shaders**

```python
# OLD (pre-4.5) - WILL FAIL IN 5.0
shader = gpu.shader.from_builtin('UNIFORM_COLOR')
batch = batch_for_shader(shader, 'LINES', {"pos": coords})

# NEW (4.5+) - Required
shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
batch = batch_for_shader(
    shader, 
    'LINES', 
    {"pos": coords, "arcLength": arc_lengths}
)

# For points
shader = gpu.shader.from_builtin('POINT_UNIFORM_COLOR')
```

**These will be REMOVED in 5.0:**
- Wide lines without POLYLINE shader
- Smooth lines without POLYLINE shader
- Points without POINT shader

### ImageFormatSettings Change

```python
# NEW REQUIREMENT (4.5+)
settings = scene.render.image_settings
settings.media_type = 'IMAGE'  # MUST set first
settings.file_format = 'PNG'    # Then format
```

### Video Sequencer Parameter Rename

```python
# OLD (pre-4.5)
strip = strips.new_effect(
    name="Effect",
    type='TRANSFORM',
    seq1=strip1,
    seq2=strip2
)

# NEW (4.5+)
strip = strips.new_effect(
    name="Effect",
    type='TRANSFORM',
    input1=strip1,
    input2=strip2
)
```

### frame_path() Can Now Fail

```python
# Must wrap in try-except (4.5+)
try:
    path = scene.render.frame_path(frame=1)
except RuntimeError as e:
    print(f"Path template error: {e}")
```

### New GeometrySet API

```python
# NEW in 4.5 - Direct geometry access
from bpy_types import GeometrySet

obj = bpy.context.object
depsgraph = bpy.context.evaluated_depsgraph_get()
obj_eval = obj.evaluated_get(depsgraph)

# Access geometry directly
geometry_set = obj_eval.to_geometry_set()
mesh = geometry_set.to_mesh()
```

### Other Enhancements

- `calc_smooth_groups()` can account for boundary vertices
- `GIZMO_GT_button_2d` gained `icon_value` property
- `Event.ndof_motion` exposes 3D-mouse motion data
- BLF image buffer drawing: `blf.bind_imbuf()` and `blf.draw_buffer()`

### Deprecations (Removed in 5.0)

- Intel Mac support ends with 4.5 (last version)
- Collada import/export removed in 5.0
- Old GPU attributes deprecated

---

## Blender 5.0 (File Format & Major Breaking Changes)

**Release Date:** November 11, 2025 (Beta available)

**Official Docs:**
- Release Notes: https://developer.blender.org/docs/release_notes/5.0/
- Python API: https://developer.blender.org/docs/release_notes/5.0/python_api/
- Core Changes: https://developer.blender.org/docs/release_notes/5.0/core/

### 🔥 CRITICAL: .blend File Format Changed

**Files saved in 5.0 cannot be opened in versions before 4.5 LTS**

- Blender 4.5 can read 5.0 files (with limitations)
- Earlier versions cannot read 5.0 files at all
- File header and block header modified for larger buffers
- Supports meshes with hundreds of millions of vertices

### Data-block Names: 64 → 255 Bytes

```python
# NEW in 5.0 - Names can be much longer
obj.name = "VeryLongObjectName_WithManyCharacters_UpTo255Bytes_" * 3

# Limitations when opening 5.0 files in 4.5:
# - Names truncate to 63 bytes
# - Linking data-blocks with long names not supported
```

⚠️ **Warning:** Longer names can hit Windows' 255-character path limit more easily.

### Compositor Workflow Breaking Change

```python
# OLD (pre-5.0) - PROPERTY REMOVED
scene.use_nodes = True  # DELETED IN 5.0

# NEW (5.0+) - Explicit creation
comp_tree = bpy.data.node_groups.new("My Compositor", "CompositorNodeTree")
scene.compositing_node_group = comp_tree
```

### EEVEE Engine Identifier Changed

```python
# OLD (pre-5.0)
if scene.render.engine == 'BLENDER_EEVEE_NEXT':

# NEW (5.0+)
if scene.render.engine == 'BLENDER_EEVEE':
```

### Render Pass Names Changed

Many passes renamed to avoid abbreviations:

| Old Name | New Name (5.0+) |
|----------|-----------------|
| `DiffCol` | `Diffuse Color` |
| `IndexMA` | `Material Index` |
| `Z` | `Depth` |
| `Emit` | `Emission` |
| `AO` | `Ambient Occlusion` |
| `GlossCol` | `Glossy Color` |
| `TransCol` | `Transmission Color` |

### Animation & Rigging Changes

```python
# OLD (pre-5.0)
action = context.space_data.action

# NEW (5.0+)
action = context.active_action

# Bone visibility
bone.hide = True  # Now affects edit bone visibility
```

**Legacy Action API completely removed** (introduced in 4.4)

### GPU Shader API Deprecation

```python
# DEPRECATED (5.0)
shader = gpu.types.GPUShader(vertex_shader, fragment_shader)

# NEW (5.0+)
shader = gpu.shader.create_from_info(shader_info)
```

**Also deprecated in 5.0:**
- `INT_TO_FLOAT` in `GPUVertFormat.attr_add()`
- Non-4-bytes-aligned vertex formats

### Video Sequencer Context

```python
# NEW in 5.0 - Separate contexts
vse_scene = context.workspace.sequencer_scene
active_scene = context.scene  # May differ from VSE scene
```

### IDProperty Changes

- Split between system-defined and user-defined storage
- Removed unsupported runtime property access
- New `_ensure()` functions for attribute creation

### Complete Logging System Rewrite

**New command-line arguments:**
```bash
blender --log-level info
blender --log-level debug
blender --log-level trace
blender --log-show-memory
```

Output format changed - affects render farms and log parsing automation.

### Platform Support Removed

- **Big endian support removed**
- **Intel Mac support removed** (Apple Silicon required)
- Pre-2.50 animation data incompatible
- LZMA and LZO point cache support removed
- CUDA minimum: sm_50 (GeForce 900 series+)
- TMP environment variable removed on UNIX (use TMPDIR)

### Other Changes

- Blendfile compression enabled by default on save
- Collection Exporters API with new RNA functions
- `path_from_module()` for querying Python module paths
- New node socket accessors: `is_inactive`, `is_icon_visible`
- Light controls expanded: energy, exposure, normalize, temperature
- Theme settings: 300+ removed or unified

---

## Version Compatibility Matrix

| Feature | 4.2 | 4.3 | 4.5 LTS | 5.0 |
|---------|-----|-----|---------|-----|
| Extensions Platform | ✅ | ✅ | ✅ | ✅ |
| Grease Pencil v3 | ❌ | ✅ | ✅ | ✅ |
| Brush Assets | ❌ | ✅ | ✅ | ✅ |
| GeometrySet API | ❌ | ❌ | ✅ | ✅ |
| GPU POLYLINE required | ❌ | ❌ | ⚠️ | ✅ |
| Old GPU attributes | ✅ | ✅ | ⚠️ | ❌ |
| scene.use_nodes | ✅ | ✅ | ⚠️ | ❌ |
| 255-byte names | ❌ | ❌ | Read only | ✅ |
| Intel Mac | ✅ | ✅ | ⚠️ Last | ❌ |
| File format | Old | Old | Can read 5.0 | New |

**Legend:**
- ✅ Fully supported
- ⚠️ Deprecated or limited support
- ❌ Not supported/removed

---

## Migration Checklists

### Migrating to 4.3
- [ ] Update all Grease Pencil code to GPv3 API
- [ ] Migrate to Brush Assets system  
- [ ] Update AttributeGroup type references
- [ ] Remove embedded ID pointer assignments
- [ ] Test reroute node operations

### Migrating to 4.5 LTS
- [ ] Update GPU drawing to POLYLINE/POINT shaders
- [ ] Add try-except around `frame_path()` calls
- [ ] Update Video Sequencer parameters
- [ ] Set `media_type` before `file_format`
- [ ] Test with Vulkan backend enabled
- [ ] Plan for Intel Mac support ending

### Migrating to 5.0
- [ ] Replace `scene.use_nodes` with explicit creation
- [ ] Change EEVEE checks to `'BLENDER_EEVEE'`
- [ ] Update all render pass name references
- [ ] Replace deprecated GPU shader API
- [ ] Handle data-block names up to 255 bytes
- [ ] Update log parsing for new format
- [ ] Test file compatibility with 4.5 LTS
- [ ] Update compositor workflows
- [ ] Test cross-version workflows

---

## Testing Priorities by Version

### 4.3 Testing
1. **Grease Pencil operations** (highest priority)
2. Brush selection and manipulation
3. Geometry Nodes modifier inputs
4. Attribute access patterns
5. EEVEE material properties

### 4.5 Testing
1. **GPU drawing** with OpenGL and Vulkan
2. Video Sequencer operations
3. Image format export
4. File path template processing
5. GeometrySet API adoption

### 5.0 Testing
1. **Compositor node tree creation**
2. EEVEE engine detection
3. Render pass names
4. GPU shader API calls
5. Cross-version file compatibility
6. Theme settings (300+ removed)
7. Data-block naming edge cases
8. Log output parsing

---

## Additional Resources

- **GitHub Examples**: https://github.com/blender/blender-addons
- **Stack Exchange**: https://blender.stackexchange.com
- **Developer Forum**: https://devtalk.blender.org
- **Blender Artists**: https://blenderartists.org

---

**Last Updated:** Based on Blender 5.0 Beta (October 2025)  
**Next Major Release:** Blender 6.0 expected ~2027