# Fix UV Maps Dialog - UX Design

## Visual Layout Diagram

```
┌──────────────────────────────────────────────────────┐
│  Fix UV Maps                                    [X]  │
├──────────────────────────────────────────────────────┤
│                                                      │
│  ℹ  Adjusting      
│                                                      │                                
│  ┌────────────────────────────────────────────────┐ │
│  │ UV:     map1                                   │ │
│  │ Image:  Character_Color_Layer1                │ │
│  │ UDIM:   3 tiles                                │ │
│  └────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────┤
│  🔧 New UV Update                                    │
│  ┌────────────────────────────────────────────────┐ │
│  │  ┌─────────────────┐  ┌──────────────────┐    │ │
│  │  │ Auto UV Unwrap  │  │ UV Map           │    │ │
│  │  └─────────────────┘  └──────────────────┘    │ │
│  │                                                │ │
│  │  New UV Name:  [map2___________________]      │ │
│  │                                                │ │
│  │  ⚙️  Smart Unwrap Settings                     │
│  │  Angle Limit      66.00°                      │ │
│  │  Island Margin    0.00                        │ │
│  └────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────┤
│  🎯 Object Scope                                     │
│  ┌────────────────────────────────────────────────┐ │
│  │  [ ] Selected Objects Only                     │ │
│  │                                                │ │
│  │  All objects: 15 object(s)                    │ │
│  └────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────┤
│  📊 Layer Scope                                      │
│  ┌────────────────────────────────────────────────┐ │
│  │  Will bake all 12 IMAGE layer(s) across all   │ │
│  │  channels to maintain alignment                │ │
│  └────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────┤
│  🖼️  UDIM                                             │
│  ┌────────────────────────────────────────────────┐ │
│  │  [Enable Tiles___________________________]     │ │
│  │  [Auto-detect Tiles______________________]     │ │
│  │                                                │ │
│  │  Will create 1 tile(s)                        │ │
│  └────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────┤
│  📐 Resolution                                       │
│  ┌────────────────────────────────────────────────┐ │
│  │  [ 1024 ][ 2048 ][ 4096 ][ 8192 ][ Custom ]   │ │
│  │                                                │ │
│  │  2048 x 2048 per tile                         │ │
│  └────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────┤
│                                                      │
│            [      OK      ]  [    Cancel    ]       │
│                                                      │
└──────────────────────────────────────────────────────┘
```

## Natural User Flow (Top to Bottom)

### 1. **Current Layer** (Context)
- Shows what you're working with
- Read-only information for reference
- User doesn't need to interact here

**Tooltips:**
- UV: "Current UV map used by this layer"
- Image: "Current texture being painted"
- UDIM: "Number of UDIM tiles detected"

---

### 2. **New UV Update** (Primary Action)
- First decision: How to create the new UV?
- Auto UV Unwrap = Generate fresh layout
- UV Map = Copy existing and edit it

**Tooltips:**
- Auto UV Unwrap: "Generate a new UV layout using Smart UV Project. Best for completely new unwraps."
- UV Map: "Copy the current UV layout. Best for making small adjustments to existing UVs."
- New UV Name: "Name for the new UV map. Will be created on objects during the session."
- Angle Limit: "Angles above this will create seams (66° recommended)"
- Island Margin: "Space between UV islands (0.00 = packed tight)"

---

### 3. **Object Scope** (Targeting)
- Second decision: Which objects?
- Default = All (full material fix)
- Selected Only = Tile-specific work

**Tooltips:**
- Selected Objects Only: "Only fix UV for selected objects. Useful when working on a single UDIM tile region. Leave off to fix the entire material."
- Object count: "Number of mesh objects that will receive the new UV map"

---

### 4. **Layer Scope** (Safety Info)
- Read-only confirmation
- Explains what will happen
- No interaction needed

**Tooltips:**
- Layer count: "All IMAGE layers will be baked to the new UV to prevent misalignment between layers"

---

### 5. **UDIM** (Image Setup)
- Image tile configuration
- Auto-detects from selection
- Only relevant for multi-tile workflows

**Tooltips:**
- Enable Tiles: "Create a UDIM image with multiple tiles. Turn off for single tile textures."
- Auto-detect Tiles: "Automatically detect which UDIM tiles are needed based on UV layout"
- Tile count: "Number of 1001, 1002, 1003... tiles that will be created"

---

### 6. **Resolution** (Image Quality)
- Image size per tile
- Standard presets + custom
- Inherits from current layer by default

**Tooltips:**
- Resolution buttons: "Texture resolution per tile. Higher = more detail but slower baking."
- Per tile note: "Each UDIM tile will be this resolution (4K tiles = 4096x4096 each)"

---

### 7. **OK / Cancel** (Execute)
- OK: Creates UV maps, enters EDIT mode, starts session
- Cancel: Abort dialog

**Tooltips:**
- OK: "Create new UV map(s) and enter UV editing session. You'll be able to adjust UVs before applying changes."
- Cancel: "Close dialog without making changes"

---

## Intelligent Defaults (No User Decision Needed)

| Situation | Auto-Detected Behavior |
|-----------|------------------------|
| UDIM image detected | Enable "Auto-detect Tiles" |
| 1-5 objects selected | Enable "Selected Objects Only" |
| Single tile image | Disable UDIM options |
| Multiple material users | Show object count, default to All |
| Layer has specific UV | Pre-fill "New UV Name" with next number |

---

## Progressive Disclosure

**Collapsed by default:**
- Smart Unwrap Settings (only show if "Auto UV Unwrap" selected)

**Always visible:**
- Current Layer (context)
- New UV Update (primary action)
- Object Scope (targeting)
- Layer Scope (safety)

**Conditionally visible:**
- UDIM section (only if current image has UDIM)
- Resolution (standard Paint System mixin)

---

## Color/Visual Hierarchy

```
High Priority (User Must Act):
  - New UV Update toggle buttons (blue/purple)
  - New UV Name field (editable)
  - OK button (primary action color)

Medium Priority (Optional Decisions):
  - Object Scope toggle
  - UDIM Enable/Auto-detect buttons
  - Resolution buttons

Low Priority (Information Only):
  - Current Layer box (neutral gray)
  - Layer Scope text (light gray)
  - Object/Tile counts (secondary text)
```

---

## Error Prevention

**Before OK enabled:**
- ✓ New UV Name is not empty
- ✓ At least one object has the material
- ✓ If "Selected Only", at least one selected object has material

**Visual feedback:**
- Selected Only + 0 objects = "⚠ No selected objects with this material" (red)
- Layer count = 0 = "⚠ No IMAGE layers to process" (red)
- Valid state = All boxes have checkmark/info icons (blue/green)

---

## Accessibility

- All icons have text labels
- All controls have tooltips
- Logical tab order (top to bottom)
- Visual grouping with boxes
- Clear section headers with emoji icons
- Read-only info uses different visual style
