"""UV boundary detection and seam-aware painting support.

Provides functions to analyze a mesh's UV layout, identify seam edges where
UV islands meet, and compute continuation positions so brush strokes that
overlap a seam can be replicated on the matching edge of the adjacent island.

The core idea: for each mesh edge shared by two faces with different UV
coordinates (a UV seam), we decompose the brush's position into an
along-edge parametric coordinate and a perpendicular offset vector.  The
offset vector is then rotated by the angle difference between the two edge
directions (+180 degrees for winding reversal) and reconstructed on the
destination edge.  This avoids relying on face normals entirely.
"""

import math
import numpy as np
import bmesh
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Set, Tuple


@dataclass
class SeamEdgePair:
    """A pair of UV edges sharing the same mesh edge but on different UV islands.

    Each side stores pixel-space endpoints, a unit direction vector along the
    edge, the edge length, and a direction angle in degrees.  An AABB per side
    is kept for fast brush-proximity checks.
    """
    edge_index: int

    # Side A
    uv_a_start: np.ndarray   # (2,) pixel coords
    uv_a_end: np.ndarray
    length_a: float
    dir_a: np.ndarray         # unit tangent along edge A
    angle_a: float            # degrees, atan2(dir_a)

    # Side B
    uv_b_start: np.ndarray
    uv_b_end: np.ndarray
    length_b: float
    dir_b: np.ndarray
    angle_b: float

    # Precomputed
    length_ratio: float       # length_b / length_a
    bbox_a: Tuple[float, float, float, float]   # (min_x, min_y, max_x, max_y)
    bbox_b: Tuple[float, float, float, float]


@dataclass
class SeamOverlap:
    """Mirror transform for a single brush stroke crossing a UV seam.

    Contains the *absolute* pixel position where the mirrored stroke should
    be placed, plus the rotation correction and scale ratio.
    """
    mirror_x: float           # absolute pixel x of the mirror position
    mirror_y: float           # absolute pixel y of the mirror position
    length_ratio: float       # scale factor for the brush
    rotation_diff: float      # angular correction in degrees


class SeamSpatialIndex:
    """Uniform-grid spatial hash for fast seam-edge proximity queries.

    Each edge side's AABB is inserted into every grid cell it overlaps.
    A query with a brush AABB returns only the ``(pair_index, side)``
    entries whose cells overlap the brush, avoiding a full linear scan.
    """

    def __init__(self, seam_map: List[SeamEdgePair], cell_size: int = 64) -> None:
        self.seam_map = seam_map
        self.cell_size = cell_size
        # Map from (cell_x, cell_y) -> set of (pair_index, side)
        self._grid: Dict[Tuple[int, int], List[Tuple[int, str]]] = defaultdict(list)
        for idx, pair in enumerate(seam_map):
            self._insert(idx, 'a', pair.bbox_a)
            self._insert(idx, 'b', pair.bbox_b)

    def _insert(self, pair_index: int, side: str,
                bbox: Tuple[float, float, float, float]) -> None:
        min_cx = int(math.floor(bbox[0] / self.cell_size))
        min_cy = int(math.floor(bbox[1] / self.cell_size))
        max_cx = int(math.floor(bbox[2] / self.cell_size))
        max_cy = int(math.floor(bbox[3] / self.cell_size))
        entry = (pair_index, side)
        for cx in range(min_cx, max_cx + 1):
            for cy in range(min_cy, max_cy + 1):
                self._grid[(cx, cy)].append(entry)

    def query(self, brush_bbox: Tuple[float, float, float, float]
              ) -> Set[Tuple[int, str]]:
        """Return the set of ``(pair_index, side)`` candidates near *brush_bbox*."""
        min_cx = int(math.floor(brush_bbox[0] / self.cell_size))
        min_cy = int(math.floor(brush_bbox[1] / self.cell_size))
        max_cx = int(math.floor(brush_bbox[2] / self.cell_size))
        max_cy = int(math.floor(brush_bbox[3] / self.cell_size))
        result: Set[Tuple[int, str]] = set()
        for cx in range(min_cx, max_cx + 1):
            for cy in range(min_cy, max_cy + 1):
                cell = self._grid.get((cx, cy))
                if cell:
                    result.update(cell)
        return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _aabb_overlap(a: Tuple[float, float, float, float],
                  b: Tuple[float, float, float, float]) -> bool:
    """True when two axis-aligned bounding boxes overlap."""
    return not (a[2] < b[0] or b[2] < a[0] or
                a[3] < b[1] or b[3] < a[1])


# ---------------------------------------------------------------------------
# Build the seam map
# ---------------------------------------------------------------------------

def build_uv_seam_map(obj, uv_layer_name: str,
                      image_width: int, image_height: int
                      ) -> Tuple[List[SeamEdgePair], SeamSpatialIndex]:
    """Scan *obj*'s UV layout and return seam edges plus a spatial index.

    A seam edge is a manifold mesh edge (exactly 2 adjacent faces) whose UV
    coordinates differ on each side.

    Returns:
        ``(seam_pairs, spatial_index)`` where *spatial_index* accelerates
        per-brush overlap queries from O(n) to ~O(1).
    """
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

    uv_layer = bm.loops.layers.uv.get(uv_layer_name)
    if uv_layer is None:
        bm.free()
        return [], SeamSpatialIndex([])

    seam_pairs: List[SeamEdgePair] = []
    eps = 1e-5

    for edge in bm.edges:
        if len(edge.link_faces) != 2:
            continue

        face_a, face_b = edge.link_faces[0], edge.link_faces[1]
        v0, v1 = edge.verts[0], edge.verts[1]

        # Gather UV coords from both faces --------------------------------
        uv_a_v0 = uv_a_v1 = None
        for loop in face_a.loops:
            if loop.vert == v0:
                uv_a_v0 = loop[uv_layer].uv.copy()
            elif loop.vert == v1:
                uv_a_v1 = loop[uv_layer].uv.copy()

        uv_b_v0 = uv_b_v1 = None
        for loop in face_b.loops:
            if loop.vert == v0:
                uv_b_v0 = loop[uv_layer].uv.copy()
            elif loop.vert == v1:
                uv_b_v1 = loop[uv_layer].uv.copy()

        if uv_a_v0 is None or uv_a_v1 is None or uv_b_v0 is None or uv_b_v1 is None:
            continue

        # Skip non-seam edges (same UVs on both sides) --------------------
        if (abs(uv_a_v0.x - uv_b_v0.x) < eps and abs(uv_a_v0.y - uv_b_v0.y) < eps and
            abs(uv_a_v1.x - uv_b_v1.x) < eps and abs(uv_a_v1.y - uv_b_v1.y) < eps):
            continue

        # Pixel-space coordinates (top-left origin after flipud) -----------
        a_start = np.array([uv_a_v0.x * image_width, (1.0 - uv_a_v0.y) * image_height], dtype=np.float32)
        a_end   = np.array([uv_a_v1.x * image_width, (1.0 - uv_a_v1.y) * image_height], dtype=np.float32)
        b_start = np.array([uv_b_v0.x * image_width, (1.0 - uv_b_v0.y) * image_height], dtype=np.float32)
        b_end   = np.array([uv_b_v1.x * image_width, (1.0 - uv_b_v1.y) * image_height], dtype=np.float32)

        length_a = float(np.linalg.norm(a_end - a_start))
        length_b = float(np.linalg.norm(b_end - b_start))
        if length_a < 1e-6 or length_b < 1e-6:
            continue
        
        print(f"Face A {face_a.index} Face B {face_b.index}")
        print(f"V0 {v0.index} V1 {v1.index}")
        print(f"UV A V0 {uv_a_v0} UV A V1 {uv_a_v1} UV B V0 {uv_b_v0} UV B V1 {uv_b_v1}")
        print(f"A Start {a_start} A End {a_end} B Start {b_start} B End {b_end}")
        print(f"Image Width {image_width} Image Height {image_height}")
        print(f"Length A {length_a} Length B {length_b}")
        print(f"Length Ratio {length_b / length_a}")
        
        # Test
        a_start_test = np.array([uv_a_v0.x, (1.0 - uv_a_v0.y)], dtype=np.float32)
        a_end_test   = np.array([uv_a_v1.x, (1.0 - uv_a_v1.y)], dtype=np.float32)
        b_start_test = np.array([uv_b_v0.x, (1.0 - uv_b_v0.y)], dtype=np.float32)
        b_end_test   = np.array([uv_b_v1.x, (1.0 - uv_b_v1.y)], dtype=np.float32)
        length_a_test = float(np.linalg.norm(a_end_test - a_start_test))
        length_b_test = float(np.linalg.norm(b_end_test - b_start_test))
        print(f"Test Length A {length_a_test} Test Length B {length_b_test}")
        print(f"Test Length Ratio {length_b_test / length_a_test}")

        # Unit direction vectors -------------------------------------------
        dir_a = (a_end - a_start) / length_a
        dir_b = (b_end - b_start) / length_b

        # Direction angles in degrees
        angle_a = float(np.degrees(np.arctan2(dir_a[1], dir_a[0])))
        angle_b = float(np.degrees(np.arctan2(dir_b[1], dir_b[0])))

        # Axis-aligned bounding boxes -------------------------------------
        bbox_a = (
            min(a_start[0], a_end[0]), min(a_start[1], a_end[1]),
            max(a_start[0], a_end[0]), max(a_start[1], a_end[1]),
        )
        bbox_b = (
            min(b_start[0], b_end[0]), min(b_start[1], b_end[1]),
            max(b_start[0], b_end[0]), max(b_start[1], b_end[1]),
        )

        seam_pairs.append(SeamEdgePair(
            edge_index=edge.index,
            uv_a_start=a_start, uv_a_end=a_end, length_a=length_a,
            dir_a=dir_a, angle_a=angle_a,
            uv_b_start=b_start, uv_b_end=b_end, length_b=length_b,
            dir_b=dir_b, angle_b=angle_b,
            length_ratio=length_b / length_a,
            bbox_a=bbox_a, bbox_b=bbox_b,
        ))

    bm.free()
    return seam_pairs, SeamSpatialIndex(seam_pairs)


# ---------------------------------------------------------------------------
# Mirror-position computation
# ---------------------------------------------------------------------------

def _compute_mirror_position(
    brush_x: float, brush_y: float,
    src_start: np.ndarray, src_dir: np.ndarray, src_length: float,
    dst_start: np.ndarray, dst_end: np.ndarray,
    angle_diff_deg: float,
) -> Tuple[float, float, float, float]:
    """Map a brush position from one side of a seam to the continuation side.

    1. Express the brush position in the *source* edge's local frame:
       ``t`` = parametric position along the edge (0..1),
       ``offset`` = perpendicular offset vector (2D).
    2. Rotate the offset vector by *angle_diff_deg* (the angular difference
       between source and destination edges, including the 180-degree winding
       reversal) so it points in the correct direction on the destination side.
    3. Reconstruct on the destination edge at the same parametric ``t``.

    Returns ``(cont_x, cont_y, t_param, d_perp)`` where *d_perp* is the
    unsigned perpendicular distance from the source edge (for filtering).
    """
    brush_pos = np.array([brush_x, brush_y], dtype=np.float32)
    to_brush = brush_pos - src_start

    # Decompose into edge-local coordinates
    t_along = float(np.dot(to_brush, src_dir))          # pixel distance along edge
    t_param = t_along / src_length if src_length > 1e-8 else 0.5  # parametric [0,1]

    # Perpendicular offset vector (everything not along the edge)
    offset = to_brush - t_along * src_dir
    d_perp = float(np.linalg.norm(offset))               # unsigned distance for filtering

    # Rotate offset by the angle difference between the two edges
    angle_rad = np.radians(angle_diff_deg)
    cos_a = float(np.cos(angle_rad))
    sin_a = float(np.sin(angle_rad))
    rotated_offset = np.array([
        offset[0] * cos_a - offset[1] * sin_a,
        offset[0] * sin_a + offset[1] * cos_a,
    ], dtype=np.float32)

    # Reconstruct on the destination side
    point_on_dst = dst_start + t_param * (dst_end - dst_start)
    continuation = point_on_dst - rotated_offset

    return float(continuation[0]), float(continuation[1]), t_param, d_perp


# ---------------------------------------------------------------------------
# Overlap detection
# ---------------------------------------------------------------------------

def find_seam_overlaps(
    seam_map: List[SeamEdgePair],
    brush_bbox: Tuple[float, float, float, float],
    brush_x: float,
    brush_y: float,
    brush_radius: float = 0.0,
    spatial_index: 'SeamSpatialIndex | None' = None,
) -> List[SeamOverlap]:
    """Find the nearest UV seam edge overlapping the brush.

    Uses a spatial index (when provided) to avoid scanning every seam edge.
    Among all edges that pass the AABB + distance filter, only the **nearest**
    one (by distance from brush centre to the edge midpoint) is returned.

    Args:
        seam_map: Pre-built list of :class:`SeamEdgePair`.
        brush_bbox: ``(min_x, min_y, max_x, max_y)`` of the brush.
        brush_x: Brush centre x in pixel space.
        brush_y: Brush centre y in pixel space.
        brush_radius: Half-extent of the brush (pixels).  Used for the fine
            distance filter.  When ``0`` the fine filter is skipped.
        spatial_index: Optional :class:`SeamSpatialIndex` for fast candidate
            retrieval.  Falls back to a full linear scan when *None*.

    Returns:
        List with at most one :class:`SeamOverlap` (the nearest edge).
    """
    # Determine which (pair_index, side) candidates to check
    if spatial_index is not None:
        candidates = spatial_index.query(brush_bbox)
    else:
        # Fallback: generate all (index, side) pairs for a linear scan
        candidates = set()
        for i in range(len(seam_map)):
            candidates.add((i, 'a'))
            candidates.add((i, 'b'))

    best_overlap: SeamOverlap | None = None
    best_dist_sq = float('inf')

    for pair_idx, side in candidates:
        pair = seam_map[pair_idx]

        if side == 'a':
            if not _aabb_overlap(brush_bbox, pair.bbox_a):
                continue
            rot = pair.angle_b - pair.angle_a + 180.0
            mx, my, t_param, d_perp = _compute_mirror_position(
                brush_x, brush_y,
                pair.uv_a_start, pair.dir_a, pair.length_a,
                pair.uv_b_start, pair.uv_b_end,
                rot,
            )
            src_length = pair.length_a
            length_ratio = pair.length_ratio
            mid = (pair.uv_a_start + pair.uv_a_end) * 0.5
        else:
            if not _aabb_overlap(brush_bbox, pair.bbox_b):
                continue
            rot = pair.angle_a - pair.angle_b + 180.0
            mx, my, t_param, d_perp = _compute_mirror_position(
                brush_x, brush_y,
                pair.uv_b_start, pair.dir_b, pair.length_b,
                pair.uv_a_start, pair.uv_a_end,
                rot,
            )
            src_length = pair.length_b
            length_ratio = 1.0 / pair.length_ratio if pair.length_ratio > 0 else 1.0
            mid = (pair.uv_b_start + pair.uv_b_end) * 0.5

        # Fine distance filter
        if brush_radius > 0:
            if d_perp > brush_radius:
                continue
            t_pixel = t_param * src_length
            if t_pixel < -brush_radius or t_pixel > src_length + brush_radius:
                continue

        # Distance from brush centre to edge midpoint (squared, avoid sqrt)
        dx = brush_x - float(mid[0])
        dy = brush_y - float(mid[1])
        dist_sq = dx * dx + dy * dy

        if dist_sq < best_dist_sq:
            best_dist_sq = dist_sq
            best_overlap = SeamOverlap(
                mirror_x=mx, mirror_y=my,
                length_ratio=length_ratio,
                rotation_diff=rot,
            )

    if best_overlap is not None:
        return [best_overlap]
    return []
