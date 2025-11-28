# UV Transfer with UDIM Support - Example Workflow

## Scenario: Fix UV Layout with UDIM Tiles

You have a material with **multiple objects** and **UDIM UVs** that need to be transferred to a new UV layout.

---

## Setup Example

**Initial State:**
- Material: "Character_Material"
- Objects using material: "Body", "Head", "Arms" (3 objects)
- Current UV: "UVMap_Old" (broken/wrong layout)
- Target UV: "UVMap_UDIM" (correct UDIM layout with 4 tiles: 1001, 1002, 1003, 1004)
- Channel: "Color" with 5 layers:
  - Base Color (image layer)
  - Detail (image layer)
  - Weathering (image layer) 
  - Highlights (adjustment layer)
  - Folder with 2 sub-layers

---

## Step-by-Step: Transfer UV with All Layers Baked

### 1. **Open UV Editor**
   - Switch to UV Editor workspace
   - Select any object with the material ("Body", "Head", or "Arms")

### 2. **Open Transfer UV Dialog**
   - In Paint System UV panel, click **"Transfer UV"** button
   - Dialog opens with all settings

### 3. **Configure Multi-Object Processing**
   ```
   ┌─ Multi-Object Transfer ────────────┐
   │ ☑ Process All 3 Objects            │
   │   • Body                            │
   │   • Head                            │
   │   • Arms                            │
   └─────────────────────────────────────┘
   ```
   - **Enabled**: Processes all 3 objects
   - **Disabled**: Only processes active object

### 4. **Configure Layer Baking**
   ```
   ┌─ Layer Options ─────────────────────┐
   │ ☑ Bake All Layers (5 visible)      │
   │ ℹ Will flatten all visible layers   │
   │   into transfer                     │
   └─────────────────────────────────────┘
   ```
   - **Enabled**: Bakes entire channel (all 5 layers combined)
   - **Disabled**: Only bakes active layer

### 5. **Set UV Transfer Mode**
   ```
   ┌─ UV Transfer Mode ──────────────────┐
   │ Mode: [Use Existing ▼]              │
   │ Target UV: [UVMap_UDIM]             │
   └─────────────────────────────────────┘
   ```
   Options:
   - **Use Existing**: Use existing "UVMap_UDIM"
   - **Create New**: Create new UV map with specified name
   - **Auto UV**: Smart UV project (no UDIM)

### 6. **Configure Image Output**
   ```
   ┌─ Image Output ──────────────────────┐
   │ Resolution: [2048] [4096] [8192]    │
   │                                      │
   │ ⚠ UDIM Tiles Detected: 4 tiles      │
   │   Tiles: 1001, 1002, 1003, 1004     │
   │ ☑ Create UDIM Image                 │
   └─────────────────────────────────────┘
   ```
   - System auto-detects UDIM tiles in target UV
   - Shows tile numbers found
   - **Create UDIM Image**: Creates proper UDIM image with all tiles

### 7. **Advanced Settings (Optional)**
   ```
   ┌─ Advanced Settings ─────────────────┐
   │ Format:                             │
   │   Color Space: [sRGB ▼]            │
   │   ☑ Alpha  ☑ 32-bit                │
   │                                      │
   │ Workflow:                            │
   │   ☑ Pack in .blend                  │
   │   ☐ Gen Coords Fallback             │
   └─────────────────────────────────────┘
   ```

### 8. **Click OK to Execute**

---

## What Happens During Transfer

### Phase 1: Processing Object "Body"
```
1. Detect UDIM tiles in "UVMap_UDIM" → Found: 1001, 1002, 1003, 1004
2. Create UDIM image: "Base Color_Transferred_Body.1001.png" + 3 more tiles
3. Disable all other layers (only if bake_all_layers=False)
4. Bake all 5 layers to UDIM image at 4096x4096 per tile
5. Update layer: image = transferred image, UV = "UVMap_UDIM"
6. Pack image into .blend
✓ Body: Transferred from UVMap_Old to UVMap_UDIM (UDIM) (all layers)
```

### Phase 2: Processing Object "Head"
```
1. Detect UDIM tiles in "UVMap_UDIM" → Found: 1001, 1002, 1003, 1004
2. Create UDIM image: "Base Color_Transferred_Head.1001.png" + 3 more tiles
3. Bake all 5 layers to UDIM image at 4096x4096 per tile
4. Update layer: image = transferred image, UV = "UVMap_UDIM"
5. Pack image into .blend
✓ Head: Transferred from UVMap_Old to UVMap_UDIM (UDIM) (all layers)
```

### Phase 3: Processing Object "Arms"
```
1. Detect UDIM tiles in "UVMap_UDIM" → Found: 1001, 1002, 1003, 1004
2. Create UDIM image: "Base Color_Transferred_Arms.1001.png" + 3 more tiles
3. Bake all 5 layers to UDIM image at 4096x4096 per tile
4. Update layer: image = transferred image, UV = "UVMap_UDIM"
5. Pack image into .blend
✓ Arms: Transferred from UVMap_Old to UVMap_UDIM (UDIM) (all layers)
```

### Completion
```
Info: UV Transfer completed for 3 objects
```

---

## Result

### Created Images (12 total UDIM tiles):
```
Base Color_Transferred_Body.1001.png   (4096x4096, UDIM tile)
Base Color_Transferred_Body.1002.png   (4096x4096, UDIM tile)
Base Color_Transferred_Body.1003.png   (4096x4096, UDIM tile)
Base Color_Transferred_Body.1004.png   (4096x4096, UDIM tile)

Base Color_Transferred_Head.1001.png   (4096x4096, UDIM tile)
Base Color_Transferred_Head.1002.png   (4096x4096, UDIM tile)
Base Color_Transferred_Head.1003.png   (4096x4096, UDIM tile)
Base Color_Transferred_Head.1004.png   (4096x4096, UDIM tile)

Base Color_Transferred_Arms.1001.png   (4096x4096, UDIM tile)
Base Color_Transferred_Arms.1002.png   (4096x4096, UDIM tile)
Base Color_Transferred_Arms.1003.png   (4096x4096, UDIM tile)
Base Color_Transferred_Arms.1004.png   (4096x4096, UDIM tile)
```

### Per-Object Updates:
- **Body**: Active layer now uses "Base Color_Transferred_Body" with 4 UDIM tiles
- **Head**: Active layer now uses "Base Color_Transferred_Head" with 4 UDIM tiles
- **Arms**: Active layer now uses "Base Color_Transferred_Arms" with 4 UDIM tiles

### Material Node Tree:
Each object's image texture node updated to use its unique transferred UDIM image.

---

## Alternative Workflow: Single Layer Only

If you **uncheck "Bake All Layers"**:

```
┌─ Layer Options ─────────────────────┐
│ ☐ Bake All Layers (5 visible)      │
│ ℹ Only: Base Color                  │
└─────────────────────────────────────┘
```

**Result:**
- Only the "Base Color" layer is baked
- Other layers (Detail, Weathering, etc.) are NOT included
- Faster processing, smaller file size
- Good for fixing UV of one specific layer

---

## Comparison: Before vs After

### Before (BROKEN):
```
Material: Character_Material
├─ Body: Uses shared "Base Color" image → WRONG UV → Stretched/broken
├─ Head: Uses shared "Base Color" image → WRONG UV → Stretched/broken
└─ Arms: Uses shared "Base Color" image → WRONG UV → Stretched/broken

Problem: All objects share one image but have different UV layouts!
```

### After (FIXED):
```
Material: Character_Material
├─ Body: Uses "Base Color_Transferred_Body" (UDIM, 4 tiles) → Correct UV ✓
├─ Head: Uses "Base Color_Transferred_Head" (UDIM, 4 tiles) → Correct UV ✓
└─ Arms: Uses "Base Color_Transferred_Arms" (UDIM, 4 tiles) → Correct UV ✓

Solution: Each object has its own transferred UDIM image!
```

---

## Key Benefits

### 1. **Multi-Object Support**
   - Processes all objects using the material in one operation
   - Each object gets unique transferred image (no texture breakage)
   - Proper `temp_override` ensures correct context per object

### 2. **UDIM Auto-Detection**
   - Automatically detects UDIM tiles (1001-1100 range)
   - Creates proper UDIM images with all detected tiles
   - Shows tile count and numbers in dialog
   - Falls back to regular image if no UDIMs detected

### 3. **Flexible Layer Baking**
   - **All Layers**: Flattens entire channel (like "Export Merged")
   - **Single Layer**: Only bakes active layer
   - Preserves layer blend modes and opacity during bake
   - Useful for consolidating complex layer stacks

### 4. **Complete Settings Control**
   - Resolution: 1024/2048/4096/8192 or custom
   - Format: Color space, alpha, 32-bit float
   - Workflow: Pack in .blend, generated coords fallback
   - UV Mode: Use existing, create new, or auto-unwrap

---

## Common Use Cases

### Use Case 1: Character with UDIM UVs
- **Problem**: Multiple body parts, each needs different UV islands in UDIM tiles
- **Solution**: Transfer with "Bake All Layers" + "Create UDIM Image"
- **Result**: Each body part has correct texture in its UDIM tiles

### Use Case 2: Props with Mixed UV
- **Problem**: Some objects have UDIM, some don't
- **Solution**: System auto-detects per object, creates UDIM only where needed
- **Result**: UDIM objects get UDIM images, regular objects get regular images

### Use Case 3: Layer Stack Consolidation
- **Problem**: 10+ layers causing performance issues
- **Solution**: Transfer with "Bake All Layers" to flatten to single image
- **Result**: Faster rendering, smaller file, same visual result

### Use Case 4: UV Layout Changes
- **Problem**: Artist rewrapped UVs, need to transfer painted textures
- **Solution**: Transfer from old UV to new UV with all layer data
- **Result**: All painting preserved on new UV layout

---

## Troubleshooting

### Issue: "No mesh objects found using this material"
**Cause**: Material not assigned to any mesh objects
**Fix**: Assign material to at least one mesh object

### Issue: "No target UV map selected"
**Cause**: Target UV field empty in "Use Existing" mode
**Fix**: Select a UV map from dropdown or switch to "Create New" mode

### Issue: "UDIM tiles detected but image is regular"
**Cause**: "Create UDIM Image" checkbox unchecked
**Fix**: Enable "Create UDIM Image" checkbox in Image Output section

### Issue: Texture appears black after transfer
**Cause**: Wrong color space (Non-Color for color texture)
**Fix**: Set Color Space to "sRGB" in Advanced Settings

### Issue: Some objects failed to transfer
**Cause**: Objects may have invalid UV data or no UV layers
**Fix**: Check console for per-object error messages, fix UV data

---

## Performance Notes

- **Single object**: ~5-10 seconds (depending on resolution)
- **3 objects, no UDIM**: ~15-30 seconds
- **3 objects, UDIM (4 tiles)**: ~60-90 seconds (4x more tiles to bake)
- **10 objects, UDIM (4 tiles)**: ~5-10 minutes

**Tips for faster processing:**
- Use lower resolution for testing (1024 or 2048)
- Disable "Bake All Layers" if only fixing one layer
- Process in batches if you have 20+ objects
- Use SSD for faster file I/O

---

## Summary

The UV Transfer feature now provides:
- ✅ Multi-object processing (all objects using material)
- ✅ Per-object unique images (no texture breakage)
- ✅ UDIM auto-detection and proper tile creation
- ✅ Flexible layer baking (single layer or all layers)
- ✅ Complete control over image format and workflow
- ✅ Comprehensive error handling and reporting

Perfect for fixing UV layouts on complex characters and props with UDIM workflows!
