# QP_Tools - Utility Toolkit Addon

Blender Python addon developed by Quentin Pointillart.

## Project Info

- **Version:** 2.1.2
- **Requires:** Blender 4.2.0+
- **Purpose:** Modular production tools for modeling, texturing, and asset management

## Key Features

- BevelWeight, CleanUp, LatticeSetup tools
- Quick Asset Library browser
- TextureSet builder
- Image Texture Auto-Updater with recursive node group support
- Modular enable/disable per tool

## Development Guidelines

- Follow the `blender-python-development` skill for all Python code
- Use `__package__` instead of hardcoded addon names
- Test changes in Blender before committing
- Folder name must match `id` in `blender_manifest.toml`

## File Structure

```
QP_Tools/
├── __init__.py              # Main addon entry with module loading
├── blender_manifest.toml    # Blender extension manifest
├── preferences.py           # Addon preferences
├── module_helper.py         # Module registration helper
├── CleanUp.py               # Cleanup tools
├── BevelWeight.py           # Bevel weight tools
├── LatticeSetup.py          # Lattice setup tools
├── qp_image_updater.py      # Image texture auto-updater
├── installer.py             # Product installation
└── ...
```
