# Blender Python Development Skill - Installation Guide

This is a custom Claude Skill for expert Blender Python addon/extension development.

## What This Skill Provides

- **Performance optimization**: msgbus over timers (7-12x faster), avoiding bpy.ops (75-200x faster)
- **Modern extension patterns**: Blender 4.2+ manifest structure, proper architecture
- **API migration guides**: Complete breaking changes for versions 4.2, 4.3, 4.5 LTS, and 5.0
- **Memory management**: Proper cleanup patterns to prevent leaks
- **Best practices**: Operators, panels, properties, modal operations, BMesh
- **Anti-patterns**: Common mistakes to avoid

## Files in This Package

```
blender-python-development/
├── Skill.md         # Main skill file with core instructions
├── REFERENCE.md     # Detailed API changes across versions
└── README.md        # This file
```

## Installation Instructions

### Step 1: Download or Create the Skill Package

If you received this as separate files, create the folder structure:

1. Create a folder named **`blender-python-development`**
2. Place `Skill.md`, `REFERENCE.md`, and `README.md` inside this folder

### Step 2: Create the ZIP File

**IMPORTANT:** The ZIP must contain the folder as its root, not the files directly.

#### ✅ Correct Structure:
```
blender-python-development.zip
└── blender-python-development/
    ├── Skill.md
    ├── REFERENCE.md
    └── README.md
```

#### ❌ Incorrect Structure (will fail):
```
blender-python-development.zip
├── Skill.md
├── REFERENCE.md
└── README.md
```

#### How to Create the ZIP:

**On Windows:**
1. Navigate to the folder CONTAINING `blender-python-development` (not inside it)
2. Right-click on the `blender-python-development` folder
3. Select "Send to" → "Compressed (zipped) folder"
4. Rename to `blender-python-development.zip`

**On Mac:**
1. Navigate to the folder CONTAINING `blender-python-development`
2. Right-click on the `blender-python-development` folder
3. Select "Compress blender-python-development"
4. This creates `blender-python-development.zip`

**On Linux:**
```bash
# From the directory CONTAINING the skill folder
zip -r blender-python-development.zip blender-python-development/
```

### Step 3: Upload to Claude

1. Go to Claude: https://claude.ai
2. Click on your **profile icon** (bottom left)
3. Select **"Settings"**
4. Navigate to **"Capabilities"** in the left sidebar
5. Click **"Add Skill"** button
6. Upload your `blender-python-development.zip` file
7. Click **"Save"**

### Step 4: Enable the Skill

After uploading:
1. Go to **Settings → Capabilities**
2. Find **"Blender Python Development"** in your skills list
3. Toggle it **ON** (enabled)

### Step 5: Test the Skill

Start a new conversation and try:

```
"I need to monitor when an object's location changes in Blender 4.5. 
What's the best approach?"
```

Claude should reference the msgbus pattern from the skill and explain why it's better than timers.

Or try:

```
"I'm creating a Blender addon for version 4.3. 
What do I need to know about the Grease Pencil changes?"
```

Claude should reference the GPv3 rewrite and provide migration guidance.

## When Claude Uses This Skill

Claude will automatically invoke this skill when you:
- Ask about Blender Python development
- Need help with Blender addons or extensions
- Request performance optimization advice
- Ask about migrating code between Blender versions
- Need help with operators, panels, or UI
- Work with Grease Pencil, meshes, or geometry
- Debug Blender Python code
- Need event-driven patterns or memory management help

## Checking if the Skill is Working

You can verify the skill is active by:

1. **Looking at Claude's response**: It should follow the patterns from Skill.md
2. **Asking directly**: "Are you using the Blender Python Development skill?"
3. **Checking the thinking process**: Claude may reference the skill in extended thinking

## Updating the Skill

As Blender evolves with new versions:

1. Download the updated skill package
2. Create a new ZIP following the same structure
3. Go to Settings → Capabilities
4. Remove the old skill (click trash icon)
5. Upload the new version
6. Enable it again

## Troubleshooting

**Problem:** Claude doesn't seem to use the skill

**Solutions:**
- Make sure the skill is **enabled** in Settings → Capabilities
- Check that your question is about Blender Python development
- Try being more explicit: "Use the Blender Python Development skill to help me..."
- Start a new conversation (skills are loaded per conversation)

**Problem:** Upload fails or skill doesn't appear

**Solutions:**
- Verify the ZIP structure is correct (folder contains files, not files in root)
- Check that Skill.md has the YAML frontmatter at the top
- Ensure the ZIP is under 100MB (this skill is ~50KB)
- Try a different browser if upload fails

**Problem:** Skill gives outdated information

**Solution:**
- Check the official Blender documentation for the latest changes
- Update REFERENCE.md with new version information
- Re-package and re-upload the skill

## Version History

- **v1.0.0** (Current): Initial release
  - Covers Blender 4.2, 4.3, 4.5 LTS, and 5.0
  - Focuses on msgbus, performance, and modern patterns
  - Complete API migration guides

## Support and Resources

- **Blender Python API Docs**: https://docs.blender.org/api/current/
- **Developer Release Notes**: https://developer.blender.org/docs/release_notes/
- **Extensions Platform**: https://extensions.blender.org
- **Blender Stack Exchange**: https://blender.stackexchange.com

## License

This skill documentation is provided as-is for educational purposes. Blender is licensed under GPL v3+.

## Credits

Created based on official Blender documentation, community best practices, and performance benchmarks from the Blender development community.