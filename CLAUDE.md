# QP_Tools - Utility Toolkit Addon

Blender Python addon developed by Quentin Pointillart.

## Project Info

- **Version:** 2.2.1
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

## Packaging for Distribution

### Naming Convention
Distribution packages should follow this naming format:
- **Format**: `QP_Tools_V#.#.#.zip` where `#.#.#` is the version number
- **Example**: `QP_Tools_V2.2.0.zip`

### Creating Distribution Package
Use `git archive` with the `--prefix` flag to create a properly structured zip:

```bash
git archive -o ../QP_Tools_V#.#.#.zip --prefix=QP_Tools/ HEAD
```

This will automatically exclude all non-essential files defined in `.gitattributes`:
- `.git/` folder
- `.claude/` folder
- `__pycache__/` folders
- `.md` files (README.md, CLAUDE.md, etc.)
- `.gitignore`, `.gitattributes`
- `tmpclaude-*` temporary files
- Any other files marked with `export-ignore`

The resulting zip will contain all addon files inside a `QP_Tools/` folder, ready for Blender installation.

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
