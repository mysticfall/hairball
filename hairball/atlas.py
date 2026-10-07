"""Deterministic unrotated grid atlas with independent padded card islands."""
from dataclasses import dataclass
import math

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
    aspects = []
    for ribbon in ribbons:
        length = sum((Vector(b) - Vector(a)).length for a, b in zip(ribbon.centers, ribbon.centers[1:]))
        aspects.append(sum(ribbon.half_widths) * 2 / len(ribbon.half_widths) / length)
    aspect = sorted(aspects)[len(aspects) // 2]
    options = []
    for columns in range(1, count + 1):
        rows = math.ceil(count / columns)
        width, height = size // columns - 2 * padding, size // rows - 2 * padding
        if min(width, height) >= 8:
            options.append((abs(math.log(width / height / aspect)) + (columns * rows - count) / count,
                            columns, rows))
    if not options:
        raise HairballError("Too many cards for this atlas; increase Atlas Size or cluster fewer cards.")
    _, columns, rows = min(options)
    cell_width, cell_height = size // columns, size // rows
    return tuple(Tile((i % columns) * cell_width + padding, (i // columns) * cell_height + padding,
                      cell_width - 2 * padding, cell_height - 2 * padding, size)
                 for i in range(count))
