# QP Tools — Blender Production Addon

A modular toolkit for Blender artists who want to move faster. Each tool solves a specific friction point in everyday modeling, texturing, and asset management workflows.

**Requires Blender 4.2+** · [Download latest release](https://github.com/Orbi51/QP_Tools/releases/latest)

---

## Features

### 🎛️ Global Controls
Control the output values of any node group named `CTRL_*` directly from the sidebar — no need to dig into the node editor. Sliders, color pickers, checkboxes, and angle/factor/vector inputs all appear automatically with the correct widget type, units, and min/max range based on what sockets the group exposes. Works in both the 3D View and the Node Editor.
**Linked library support** — When CTRL_ groups are linked from an external `.blend`, use the **Make Local** button (library icon) in the panel header to create local editable copies. Local copies persist across save/reload with a fake user, and the sidebar controls become fully interactive.

### 📦 Quick Asset Library
Manage your assets easily. Add, update, override assets to the selected library, set the correct catalog or create a new one then click Add to Library. This helps keep your libraries and .blend files clean, well organized and up to date.

### 🧹 Clean Up
One-click cleanup for stale data: duplicate materials, orphan node groups, and unused images. Shows a clear conflict list before making any changes, so you stay in control of what gets merged or removed.

### 🖼️ Image Texture Auto-Updater
Adding a texture to the image socket of the TB_Texture node group, or linking its input with the image output of another TB_Texture node group will update every linked nodes with the selected texture. Very useful before blender 5.0 and the closure nodes. 

### 📐 Lattice Setup
Select any objects and instantly wrap them in a perfectly fitted lattice with the modifier already applied. Saves several manual steps every time you need to do a non-destructive deformation.

### ⚖️ Bevel Weight
Set bevel weight and segment count on selected edges or vertices in one shot, with an interactive preview. Works with both the legacy Bevel Weight attribute and the modern Bevel modifier workflow.

### 🗂️ Material List
See the list of materials present in your scene. You can open any material as a pop-up window without having to hunt for the object holding it. You can also apply materials to the selected objects or select the objects using the material.

### 🔗 Link Node Groups
Automatically wire multiple node groups together based on matching socket names. Select the nodes, run the operator, and compatible sockets are connected instantly.

### 🗃️ Collection Offset
Set a collection's offset origin to the center, bottom, active object, or 3D cursor — whichever makes the most sense for how the collection will be instanced.

### 🔺 Edge Select & Vertex Groups
Assign selected edges or vertices to a vertex group and automatically update any modifier (like Bevel or Solidify) that references that group — all in one step.

### 🗺️ Box or Flat Mapping
A quick popup in the node editor to switch image texture nodes between Box and Flat projection without hunting for the property in the node panel. Works with nodes in node groups.

### 🧩 Texture Set Builder
Pack multiple image texture files into a node setup and wire them to a material in one go. Speeds up the repetitive part of building PBR material setups from a texture set.

### 🥧 Custom Pie Menus
Build your own pie menus with a visual editor and assign them to any shortcut you want. Smart actions adapt automatically to context — the same pie entry runs the right operator whether you're in Object mode, Edit mode, or the Node Editor.

### 🪟 Floating Panel
Detach the N-panel sidebar into its own floating window. Useful on multi-monitor setups or when you want to keep tool options visible without sacrificing viewport space.

### 🔄 AOV Manager
Scan all materials for AOV Output nodes — including inside nested node groups — and sync them to the active View Layer with one button.

---

## Installation

1. Go to the [latest release](https://github.com/Orbi51/QP_Tools/releases/latest) and download `QP_Tools_V*.zip`
2. In Blender: **Edit → Preferences → Add-ons → Install from Disk…**
3. Select the zip and enable **QP Tools**

Each feature can be toggled on or off individually in the addon preferences.

---

## Updates

QP Tools has a built-in auto-updater. When a new version is available you'll see a notice in the sidebar. You can also check manually in **Preferences → Add-ons → QP Tools → Check for Updates**.
