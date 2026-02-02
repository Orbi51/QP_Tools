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
