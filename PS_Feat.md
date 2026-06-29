# Paint System — Feature Summary

**Version:** 2.1.14
**Requires:** Blender 4.2.0+
**Category:** Paint · **Support:** Community
**Render engines:** EEVEE (full) · Cycles (full, except the *Paint Over* template)
**Location:** View3D → Sidebar (N) → **Paint System** tab
**Repo:** https://github.com/natapol2547/paintsystem · **Docs:** [Notion documentation](https://www.notion.so/Paint-System-Documentation-2b02d71289d680f68ff9ef712d33716f)

Paint System is a flexible, layer-based painting system for Blender focused on **non-photorealistic rendering (NPR)** and stylized texturing. It gives you a Photoshop-style layer stack, node-based channels, and direct 3D painting — all generated automatically as shader node trees, with no manual node wiring required.

---

## 1. Layer System

A nested, non-destructive layer stack (folders within folders) with **11 layer types**:

| Layer Type | What it does |
|------------|--------------|
| **Image** | Paintable bitmap layer (new, imported, or linked image) |
| **Solid Color** | Flat procedural color fill |
| **Gradient** | Gradient Map, Linear, Radial, Distance, or Fake Light gradients |
| **Adjustment** | Non-destructive color correction (see below) |
| **Texture** | Procedural texture (8 types — see below) |
| **Geometry** | Geometry data: normals, position, AO, backfacing, vector transform |
| **Attribute** | Visualize mesh vertex colors / attributes |
| **Random Color** | Procedural random color with seed + HSV offsets |
| **Node Group** | Use any compatible custom shader node group as a layer |
| **Folder** | Organizational container (Pass-Through blending) |
| **Blank** | Empty placeholder for organization |

**Per-layer controls:** 25+ blend modes (Mix, Add, Multiply, Screen, Overlay, Soft/Hard Light, Difference, Hue/Sat/Color, Pass Through, etc.), opacity (0–100%), visibility toggle, layer lock, alpha lock, and clipping masks (clip to layer below).

**Layer operations:** add, delete, move up/down, **merge up / merge down**, copy/paste single layer, copy/paste all layers, convert procedural layers to image (bake), and **layer linking** — reference one layer across multiple channels, with an unlink option to break the reference.

**Adjustment types (7):** Brightness/Contrast, Gamma, Hue-Saturation-Value, Invert, RGB Curves, RGB→Grayscale, Map Range.

**Procedural texture types (8):** Brick, Checker, Gradient, Magic, Noise, Voronoi, Wave, White Noise.

**Geometry types (8):** World/Object-space Normal, World True Normal, World/Object-space Position, Backfacing, Vector Transform, Ambient Occlusion (with sample/distance/color controls).

---

## 2. Masking

Add masks to any layer to control where it shows:

- **Value Mask** — direct float/opacity value
- **Image Mask** — bitmap (alpha-based) mask
- **Attribute Mask** — driven by mesh vertex colors/attributes
- **Texture Mask** — procedural texture mask

Mask blend modes: Add, Subtract, Multiply.

---

## 3. Channels

Each Paint System group can output multiple **channels**, each compiling its own layer stack into the material:

- **Color** — RGBA output
- **Vector** — normals, position, displacement (with input/output space transforms: Object, Tangent, World, Texture)
- **Float** — single-value data such as roughness, metallic, or height

Channel features: add / delete / reorder channels, **channel isolation** (preview a single channel), per-channel baked-image assignment, and quick-start channel templates (Color, Metallic, Roughness, Normal).

---

## 4. Setup Templates

When adding Paint System to a material, pick a starting template:

- **Basic** — blank Color channel with a solid color + image layer
- **Paint Over** — blend on top of an existing material *(EEVEE only)*
- **PBR** — pre-built Color / Roughness / Metallic / Normal channels
- **Normal** — dedicated normal-map painting setup
- **None** — just inserts the node group, no preset structure

Group options include alpha blend vs. alpha clip, backface culling, view-transform standardization, and automatic UV map creation. Multiple independent Paint System groups can live on one material.

---

## 5. Painting & Brushes

- Full integration with Blender's brush system (size, strength, blend modes, falloff, textures)
- **Toggle Paint Mode** — auto-switches between Object and Texture Paint and sets the right canvas/shading for the active layer
- **Preset brushes** — import bundled `PS_` brushes
- Color tools: primary/secondary swatches, color picker with optional HSV sliders and hex display, palette support
- **Erase Alpha** toggle for painting transparency
- Advanced options: occlude faces, backface culling, normal falloff angle

**Keyboard shortcuts:** `I` color sample (eyedropper) · `E` toggle erase alpha · `F` brush size · `Shift+F` brush strength · `RMB` Paint System context menu.

---

## 6. Image Coordinates & Mapping

Image layers support a wide range of coordinate/projection modes:

- **Auto UV** (auto-generates a UV map) and existing **UV** maps
- **Object**, **Camera**, **Window**, **Reflection**, **Generated/Texture**, **Position** spaces
- **Decal** — empty-driven placement with depth clipping
- **Projection** — view/camera projection with falloff, scale, and view reset/capture
- **Parallax** — UV- or Object-space parallax with depth control
- Per-layer transform (mapping, position, rotation, scale)

---

## 7. Baking & Export

- **Bake Channel** — bake the active channel to an image or layer
- **Bake All Channels** — bake an entire group at once
- Options: multi-object baking, GPU acceleration, margin size/type, tangent-space normal conversion, custom UV-map naming, float (HDR) or integer (LDR) output, custom resolution
- **Export** baked images individually or **export all** at once
- Toggle between live layers and the baked result; select all objects using a baked material; delete baked images

---

## 8. Image Filters & Editing

Built-in operators that act directly on image layers:

- Gaussian Blur, Sharpen, Invert Colors, Fill, Clear
- Resize image (with aspect handling)
- Transfer image-layer UVs from the mesh
- **Quick Edit / External Edit** — round-trip an image (or view capture) to an external editor and re-apply

---

## 9. Node & Shader Integration

- Automatic generation of layer, channel, and group node trees — no manual setup
- Implements blend modes, alpha compositing, clipping/masking, folder pass-through, and vector-space transforms as nodes
- Use any compatible node group as a layer (with socket remapping)
- Shader-editor helpers: focus/open the Paint System node group, inspect a layer's node tree, exit all node groups

---

## 10. Grease Pencil Support

Full Layers panel for Grease Pencil objects: layer tree, groups, add/remove/move, blend modes, opacity, visibility, locking, masks, lights, and onion-skinning settings — plus GP brush and color tools.

---

## 11. Layer Actions (Timeline)

Animate layer visibility by enabling/disabling layers at specific **frames** or **timeline markers**, with ordered actions per layer.

---

## 12. Quick Tools (optional sidebar panels)

- **Display:** wireframe toggle, transform gizmo controls (translate/rotate/scale)
- **Mesh:** add primitives (plane, cube, circle, UV sphere, camera plane), normal display, recalculate/flip normals, apply transforms, set origin, non-uniform scale warnings
- **Paint:** edit externally (context-aware for image or view capture)

---

## 13. Material & Rendering

- Per-object multi-material slot support
- Render method selector, backface culling, transparent-back, alpha blend/clip
- Auto viewport shading adjustment for painting
- Full PBR workflow via the PBR template (Principled BSDF channels)

---

## 14. Preferences & Settings

- **UI:** tooltips, compact design, opacity in layer list, legacy UI, inline panel quick-access, hex color, HSV sliders
- **Brush:** color-picker scale, RMB color-wheel scale, RMB menu contents (HSV, palette, brush controls)
- **Tips:** hide normal-painting and color-attribute tips
- **Advanced:** developer mode (verbose logging), preferred default coordinate type
- **Updates:** built-in version check with configurable interval and in-panel update notifications

---

## 15. Versioning, Utilities & Support

- Automatic legacy Paint System detection and **data migration**
- Layer warning system for missing/broken resources (e.g. fix missing gradient empty)
- Fix duplicated node-tree data; select gradient/projection empties
- In-app **support/donation** links (Gumroad), recent-donations display, and credits
- Supported image formats: JPG/JPEG, PNG, TIF/TIFF, BMP

---

### Feature totals at a glance

| Category | Count |
|----------|-------|
| Layer types | 11 |
| Blend modes | 25+ |
| Adjustment types | 7 |
| Procedural texture types | 8 |
| Geometry data types | 8 |
| Mask types | 4 |
| Channel types | 3 |
| Setup templates | 5 |
| Coordinate/mapping modes | 10+ |
| Operators (actions) | 70+ |
| Keyboard shortcuts | 5 |

*Generated for Paint System v2.1.14.*
