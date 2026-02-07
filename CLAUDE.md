# QP_Tools - Utility Toolkit Addon

Blender Python addon developed by Quentin Pointillart.

## Project Info

- **Version:** 2.2.2
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

## Workflow Orchestration

### 1. Plan Mode Default
- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- Write detailed specs upfront to reduce ambiguity

### 2. Subagent Strategy
- Use subagents to keep main context window clean
- Offload research, exploration, and parallel analysis to subagents
- One task per subagent for focused execution

### 3. Self-Improvement Loop
- At the start of every session, read `tasks/lessons.md` before doing any work
- After ANY correction from the user: update `tasks/lessons.md` with the pattern
- Write rules for yourself that prevent the same mistake
- Format each lesson as: **mistake** → **rule** → **example**

### 4. Verification Before Done
- Never mark a task complete without running tests or demonstrating correctness
- Run `git diff` to review your own changes before presenting them

### 5. Keep It Simple
- Do exactly what was asked — no extra features, no speculative abstractions
- Three similar lines of code is better than a premature helper function
- Don't add error handling for scenarios that can't happen
- If a solution feels complex, step back and find the simpler path
- No comments, docstrings, or type annotations on code you didn't change

### Core Principles
- **Simplicity First**: Make every change as simple as possible. Impact minimal code.
- **No Laziness**: Find root causes. No temporary fixes. Senior developer standards.
- **Minimal Impact**: Changes should only touch what's necessary. Avoid introducing bugs.

## Auto-Updater & Release Workflow

### Architecture
- Updates are hosted on `github.com/Orbi51/QP_Tools` (same repo as the addon source)
- A single `update_info.json` manifest at repo root is the source of truth
- The addon fetches this manifest to check versions; download URLs point to GitHub release assets
- `updater.py` handles all updater logic (check, download, install, UI)
- Version is read from `blender_manifest.toml` at import time using `tomllib`
- `update_info.json` is excluded from distribution zips via `.gitattributes` (`export-ignore`)

### Version Bump & Release Process
When the user requests a version bump:

1. **Bump version** in `blender_manifest.toml` (`version`), `__init__.py` (`bl_info.version`), and `CLAUDE.md`
2. **Package the addon zip** using `git archive -o ../QP_Tools_V{version}.zip --prefix=QP_Tools/ HEAD`
3. **Create a GitHub release** on `Orbi51/QP_Tools` via `gh`:
   - Tag: `v{version}`
   - Attach: addon zip (`QP_Tools_V{version}.zip`)
   - Body: changelog in markdown
4. **Update `update_info.json`** in the repo with new version, download URL, and changelog text
5. **Commit and push** the manifest update

### Key Files
- `blender_manifest.toml` — `version` field (single source of truth for addon version)
- `updater.py` — All updater logic (operators, background check, UI draw functions)
- `preferences.py` — `auto_check_updates` preference, `draw_updates_section()` call in `draw()`
- `qp_tools_panel.py` — `draw_sidebar_update_notice()` call at top of `QP_PT_main_panel.draw()`
- `update_info.json` — Remote manifest with version, changelog, and download URL
- `.gitattributes` — `update_info.json export-ignore` to exclude from packaging

### Dismiss Behavior
- **Preferences**: dismissed updates are hidden; manual "Check for Updates" shows them again
- **Sidebar**: dismissed updates stay hidden until a genuinely new version (reads persistent `dismissed_addon_version` from `updater_state.json`)
