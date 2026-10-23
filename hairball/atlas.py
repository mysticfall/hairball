"""Deterministic, size-aware shelf packing of independent padded card islands."""
from dataclasses import dataclass
import math
from statistics import median

from mathutils import Vector

from .evaluation import HairballError


@dataclass(frozen=True)
class Tile:
    x: int
    y: int
    width: int
    height: int
    size: int

    def uv(self, coordinate):
        # Island edges are at texel centers, leaving the surrounding gutter free.
        return ((self.x + 0.5 + coordinate[0] * (self.width - 1)) / self.size,
                (self.y + 0.5 + coordinate[1] * (self.height - 1)) / self.size)


def pack(ribbons, size, padding=3):
    if not ribbons or size < 64 or padding < 2:
        raise HairballError("Atlas packing needs cards, at least 64 pixels, and a two-pixel gutter.")
    # Bound working memory before allocating two maps and raster buffers.
    if size > 2048:
        raise HairballError("This baker currently supports atlases up to 2048 pixels to bound working memory.")
    count = len(ribbons)
    ceiling = (size // (8 + 2 * padding)) ** 2
    if count > ceiling:
        raise HairballError(f"{count:,} cards exceed this {size}px atlas's {ceiling:,}-card packing ceiling "
                            f"(8px minimum tiles, {padding}px gutters). Reduce Density, group more strands, "
                            "or increase Atlas Size (maximum 2048).")
    dimensions = []
    for ribbon in ribbons:
        length = sum((Vector(b) - Vector(a)).length for a, b in zip(ribbon.centers, ribbon.centers[1:]))
        width = 2 * max(ribbon.half_widths)
        if not all(math.isfinite(v) and v > 0 for v in (width, length)):
            raise HairballError("Atlas packing needs finite, non-zero card dimensions.")
        # Multiple thin strands compete primarily across the card, while their
        # root-to-tip paths are smooth. Equal world-space density spends most
        # texels along long hair and collapses those strands into shared columns.
        # Shift, rather than enlarge, the requested area toward across-strand
        # resolution for populated bundles. This bounded heuristic is not a
        # strand-separation guarantee; report actual diameter pressure below.
        across_priority = min(4, math.sqrt(max(1, len(ribbon.strands) / 4)))
        dimensions.append((width * across_priority, length / across_priority))

    def place(density):
        rectangles = [(max(8, math.ceil(w * density)), max(8, math.ceil(h * density)), i)
                      for i, (w, h) in enumerate(dimensions)]
        rectangles.sort(key=lambda item: (-item[1], -item[0], item[2]))
        shelves, tiles, top = [], [None] * count, 0
        for width, height, index in rectangles:
            outer_width, outer_height = width + 2 * padding, height + 2 * padding
            if max(outer_width, outer_height) > size:
                return None
            candidates = [(size - x - outer_width, i) for i, (y, x, h) in enumerate(shelves)
                          if h >= outer_height and x + outer_width <= size]
            if candidates:
                _, shelf = min(candidates)
                y, x, h = shelves[shelf]
                shelves[shelf] = (y, x + outer_width, h)
            else:
                if top + outer_height > size:
                    return None
                y, x = top, 0
                shelves.append((top, outer_width, outer_height))
                top += outer_height
            tiles[index] = Tile(x + padding, y + padding, width, height, size)
        return tuple(tiles)

    # Common density after the explicit directional-priority adjustment lets
    # large/wide clumps use larger islands than a narrow singleton.
    # Minimum tiles still fit by the explicit ceiling above. Keep a known-valid
    # result throughout the bounded search; never shrink strands to make it fit.
    low, high = 0.0, (size - 2 * padding) / max(max(w, h) for w, h in dimensions)
    best = place(low)
    for _ in range(24):
        density = (low + high) / 2
        candidate = place(density)
        if candidate is None:
            high = density
        else:
            low, best = density, candidate
    return best


def _pattern_key(ribbon, source, turn_divisor, population_octaves, profile_buckets):
    centers = [Vector(c) for c in ribbon.centers]
    turn = 0.0
    for a, b, c in zip(centers, centers[1:], centers[2:]):
        first, second = b - a, c - b
        lengths = first.length * second.length
        if lengths > 1e-24:
            turn += math.acos(max(-1.0, min(1.0, first.dot(second) / lengths)))
    widths = ribbon.half_widths
    profile = 1.0 if not widths else sum(widths) / len(widths) / max(widths)
    buckets = (round(turn / turn_divisor),
               round(math.log2(1 + len(ribbon.strands)) / population_octaves))
    if profile_buckets:
        buckets += (round(profile * profile_buckets),)
    return (source,) + buckets


def pack_patterns(ribbons, size, padding=3, sources=None):
    """Group similar cards onto shared large patches instead of tiny islands.

    Every card keeps its own geometry, anchors and UV mapping; cards in one
    group display the baked pattern of the group's densest member (the donor).
    This trades exact per-card strand data for far higher across-strand
    resolution, matching ordinary hand-authored hair-card workflows. Groups
    never mix grooms; coarsening stays deterministic and bounded.
    """
    if not ribbons or size < 64 or padding < 2:
        raise HairballError("Pattern packing needs cards, at least 64 pixels, and a two-pixel gutter.")
    if size > 2048:
        raise HairballError("This baker currently supports atlases up to 2048 pixels to bound working memory.")
    sources = sources or [0] * len(ribbons)
    patch_width, patch_height = size // 8, size // 4
    columns = size // (patch_width + 2 * padding)
    rows = size // (patch_height + 2 * padding)
    limit = columns * rows
    schedule = ((0.8, 1.0, 4), (1.6, 2.0, 2), (3.2, 4.0, 1), (6.4, 8.0, 0), (12.8, 16.0, 0))
    for turn_divisor, population_octaves, profile_buckets in schedule:
        keys = [_pattern_key(ribbon, source, turn_divisor, population_octaves, profile_buckets)
                for ribbon, source in zip(ribbons, sources)]
        groups = {}
        for index, key in enumerate(keys):
            groups.setdefault(key, []).append(index)
        if len(groups) <= limit:
            break
    else:  # pragma: no cover - schedule is chosen to converge for real inputs
        raise HairballError("Pattern grouping does not converge; reduce card count or atlas diversity.")
    ordered = sorted(groups.items(), key=lambda item: (-len(item[1]), item[1][0]))
    tiles, metadata = [None] * len(ribbons), []
    for group_id, (key, members) in enumerate(ordered):
        donor = max(members, key=lambda i: (len(ribbons[i].strands), -i))
        slot = group_id
        tile = Tile((slot % columns) * (patch_width + 2 * padding) + padding,
                    (slot // columns) * (patch_height + 2 * padding) + padding,
                    patch_width, patch_height, size)
        for member in members:
            tiles[member] = tile
        metadata.append({"tile": [tile.x, tile.y, tile.width, tile.height],
                         "key": list(key), "donor": donor, "members": list(members)})
    return tuple(tiles), metadata


def resolution_report(ribbons, tiles):
    """Report sampling pressure separately from the purely geometric capacity.

    A quarter-texel representative strand diameter is a diagnostic threshold,
    not a production-quality guarantee. Use each strand's maximum radius so
    ordinary tip taper does not make every card appear under-resolved.
    """
    diameters = [median(2 * max(s.radii) for s in ribbon.strands)
                 / (2 * max(ribbon.half_widths)) * (tile.width - 1)
                 for ribbon, tile in zip(ribbons, tiles)]
    return {"atlas_tile_width_min": min(t.width for t in tiles),
            "atlas_tile_width_max": max(t.width for t in tiles),
            "atlas_tile_height_min": min(t.height for t in tiles),
            "atlas_tile_height_max": max(t.height for t in tiles),
            "strand_diameter_texels_median": round(median(diameters), 4),
            "underresolved_cards": sum(d < 0.25 for d in diameters)}
