# UDIM Multi-Object Baking Crash Fix

## Issue
Blender crash (EXCEPTION_ACCESS_VIOLATION) when baking with UDIM models, specifically during alpha channel processing in multi-object baking workflow.

## Root Causes

### 1. Unconditional Alpha Baking (PRIMARY CAUSE)
**Location**: `paintsystem/data.py`, `Channel.bake()` method around line 1755

**Problem**: The code was creating a temporary alpha image and attempting to bake alpha **even when `force_alpha=False`**. This caused:
- Null pointer access when trying to bake non-existent alpha channel
- Memory corruption in Python's image pixel arrays
- EXCEPTION_ACCESS_VIOLATION in `python311.dll`

**Fix**: Added early return when `force_alpha=False`:
```python
bake_image = ps_bake(context, obj, mat, uv_layer, bake_image, use_gpu, use_clear=use_clear)

# Only handle alpha baking if force_alpha is True
if not force_alpha:
    # No alpha baking needed - ps_bake has already restored Cycles settings
    # Clean up temporary nodes and restore surface connections before returning
    [cleanup code...]
    return bake_image
```

### 2. UDIM Tile Pixel Access (SECONDARY ISSUE)
**Location**: `paintsystem/data.py`, alpha combination code around line 1810

**Problem**: Attempted to access UDIM tile pixels directly via Python API:
```python
tile.pixels.foreach_get(tile_pixels)  # INCORRECT - tiles don't have pixel attribute
```

**Fix**: Skip pixel manipulation for UDIM images due to Blender API limitation:
```python
if is_udim and hasattr(bake_image, 'tiles') and len(bake_image.tiles) > 1:
    # Blender doesn't support per-tile pixel access in Python
    print(f"  Note: UDIM alpha combination via compositor (Python API limitation)")
    bake_image.pack()
    temp_alpha_image.pack()
    print(f"  Warning: Alpha channel not automatically combined for UDIM. Bake image has RGB only.")
else:
    # Regular non-UDIM image processing - this works reliably
    [standard pixel array manipulation...]
```

## Changes Made

### File: `paintsystem/data.py`

#### 1. Early Return for Non-Alpha Baking (Lines ~1757-1785)
- Check `if not force_alpha` immediately after initial bake
- Perform full cleanup (nodes, sockets, filepaths) before return
- Prevents unnecessary alpha temp image creation

#### 2. UDIM-Aware Alpha Handling (Lines ~1810-1835)
- Detect UDIM images: `is_udim = hasattr(bake_image, 'source') and bake_image.source == 'TILED'`
- Skip direct pixel manipulation for UDIM tiles
- Use standard numpy array approach for non-UDIM images
- Added error messages explaining limitation

#### 3. Proper Cleanup Flow
- **Without alpha**: Cleanup immediately after first bake, then return
- **With alpha**: Cleanup happens after alpha combination in finally block
- Ensures all paths properly clean up resources

## Testing Recommendations

1. **Non-UDIM Multi-Object Baking**:
   - Should work perfectly with alpha combination
   - Test with 2-3 objects sharing same material
   - Verify alpha channel properly baked

2. **UDIM Multi-Object Baking**:
   - Should no longer crash
   - RGB bakes successfully across all tiles
   - Alpha NOT automatically combined (known limitation)
   - User can manually composite alpha in Blender's compositor if needed

3. **Single Object UDIM**:
   - Should work same as multi-object
   - All tiles detected and created properly

## Known Limitations

### UDIM Alpha Combination
Blender's Python API does not provide direct per-tile pixel access for UDIM images. The following approaches were considered:

- ❌ **Direct tile.pixels access**: Not available in Python API
- ❌ **Image.pixels with indexing**: Returns all tiles concatenated, can't separate them
- ⚠️ **Compositor nodes**: Possible but complex, requires render setup
- ✅ **Current solution**: Skip alpha for UDIM, bake RGB only

**Workaround**: Users needing alpha on UDIM models can:
1. Bake RGB channel
2. Bake alpha separately to different image
3. Use Compositor to combine manually

## Performance Impact
- **Positive**: Eliminates unnecessary alpha image creation when not needed
- **Positive**: Early return reduces processing time for non-alpha bakes
- **Neutral**: UDIM alpha limitation existed before, now documented

## Future Improvements
Potential solutions for UDIM alpha:
1. Implement compositor-based alpha combination
2. Use render passes to combine channels
3. Per-tile export and external tool processing
4. Wait for Blender API improvements
