"""CPU strand projection/rasterization using Blender's bundled NumPy.

Coverage is a four-sample union; data comes from the shallowest contributing
strand, never an average of seed/direction channels. Depth is local projection.
"""
from bisect import bisect_right
import hashlib
import math

import bpy
import numpy as np
from mathutils import Vector

from .cards import _arc_samples
from .evaluation import HairballError


def strand_seed(identifier, seed):
    digest = hashlib.blake2s(f"{seed}:{identifier}".encode(), digest_size=4).digest()
    return int.from_bytes(digest, "little") / 4294967295


def _project(ribbon, strand):
    points = [Vector(p) for p in strand.points]
    distances = [0.0]
    for a, b in zip(points, points[1:]):
        distances.append(distances[-1] + (b - a).length)
    parameters = sorted(set(ribbon.parameters) | {d / distances[-1] for d in distances})
    samples = _arc_samples(strand.points, parameters)
    knots = [d / distances[-1] for d in distances]
    result = []
    for u, point in zip(parameters, samples):
        row = min(bisect_right(ribbon.parameters, u) - 1, len(ribbon.parameters) - 2)
        t = (u - ribbon.parameters[row]) / (ribbon.parameters[row + 1] - ribbon.parameters[row])
        center = Vector(ribbon.centers[row]).lerp(Vector(ribbon.centers[row + 1]), t)
        side = Vector(ribbon.sides[row]).lerp(Vector(ribbon.sides[row + 1]), t).normalized()
        width = ribbon.half_widths[row] * (1 - t) + ribbon.half_widths[row + 1] * t
        along = (Vector(ribbon.centers[row + 1]) - Vector(ribbon.centers[row])).normalized()
        normal = side.cross(along).normalized()
        offset = point - center
        index = min(bisect_right(knots, u) - 1, len(knots) - 2)
        f = (u - knots[index]) / max(knots[index + 1] - knots[index], 1e-12)
        radius = strand.radii[index] * (1 - f) + strand.radii[index + 1] * f
        lateral = offset.dot(side)
        if abs(lateral) + radius > width + max(1e-8, width * 1e-5):
            raise HairballError("A strand leaves its fitted card width; reduce Fit Error or Strands per Card, "
                                "or increase Minimum Width.")
        result.append((0.5 + offset.dot(side) / (2 * width), u, offset.dot(normal), radius, point, row))
    return result


def _image(name, pixels):
    image = bpy.data.images.new(name, width=pixels.shape[1], height=pixels.shape[0], alpha=True)
    try:
        image.colorspace_settings.name = "Non-Color"
        image.alpha_mode = "CHANNEL_PACKED"
        image.file_format = "PNG"
        image.pixels.foreach_set(pixels.ravel())
        image.update()
        # Packing a new image gives undo/reopen an immutable encoded backing buffer.
        image.pack()
        return image
    except Exception:
        bpy.data.images.remove(image)
        raise


def _segments(ribbon, points, width, height):
    """Precompute geometry once, rather than for every coverage subsample."""
    result = []
    for a, b in zip(points, points[1:]):
        row = a[5]
        across = 2 * max(ribbon.half_widths[row:row + 2])
        along = ((Vector(ribbon.centers[row + 1]) - Vector(ribbon.centers[row])).length
                 / (ribbon.parameters[row + 1] - ribbon.parameters[row]))
        radius = max(a[3], b[3])
        if radius <= 0:
            continue
        rx, ry = radius / across * (width - 1), radius / along * (height - 1)
        x0 = max(0, math.floor(min(a[0], b[0]) * (width - 1) - rx - 1))
        x1 = min(width, math.ceil(max(a[0], b[0]) * (width - 1) + rx + 2))
        y0 = max(0, math.floor(a[1] * (height - 1) - ry - 1))
        y1 = min(height, math.ceil(b[1] * (height - 1) + ry + 2))
        dx, dy = (b[0] - a[0]) * across, (b[1] - a[1]) * along
        denominator = dx * dx + dy * dy
        if x0 >= x1 or y0 >= y1 or denominator < 1e-24:
            continue
        result.append((a, b, row, across, along, x0, x1, y0, y1, dx, dy, denominator))
    return result


def _bounded_batches(segments):
    """Keep vectorized scratch bounded; a single segment uses its old ROI budget."""
    x0, x1 = min(s[5] for s in segments), max(s[6] for s in segments)
    y0, y1 = min(s[7] for s in segments), max(s[8] for s in segments)
    if len(segments) > 1 and len(segments) * (x1 - x0) * (y1 - y0) > 65536:
        middle = len(segments) // 2
        yield from _bounded_batches(segments[:middle])
        yield from _bounded_batches(segments[middle:])
    else:
        yield segments, (x0, x1, y0, y1)


def _batches(segments):
    start = 0
    while start < len(segments):
        end = start + 1
        while end < min(start + 32, len(segments)) and segments[end][2] == segments[start][2]:
            end += 1
        yield from _bounded_batches(segments[start:end])
        start = end


def _raster_batch(segments, bounds, width, height, ox, oy):
    x0, x1, y0, y1 = bounds
    xi, yi = np.arange(x0, x1), np.arange(y0, y1)
    # Broadcast axes instead of allocating a meshgrid for every tiny segment.
    x, y = (xi[None, :] + ox) / (width - 1), (yi[:, None] + oy) / (height - 1)
    data = np.asarray([[s[0][0], s[0][1], s[1][0] - s[0][0], s[1][1] - s[0][1],
                        s[0][2], s[1][2] - s[0][2], s[0][3], s[1][3] - s[0][3],
                        s[3], s[4], s[9], s[10], s[11], s[5], s[6], s[7], s[8]]
                       for s in segments], dtype=np.float64)
    def col(index):
        return data[:, index, None, None]
    t = np.clip(((x - col(0)) * col(8) * col(10)
                 + (y - col(1)) * col(9) * col(11)) / col(12), 0, 1)
    distance2 = ((x - (col(0) + t * col(2))) * col(8)) ** 2
    distance2 += ((y - (col(1) + t * col(3))) * col(9)) ** 2
    hit = distance2 <= (col(6) + t * col(7)) ** 2
    # Respect each original segment's ROI even when sharing a larger batch ROI.
    hit &= (xi[None, :] >= col(13)) & (xi[None, :] < col(14))
    hit &= (yi[:, None] >= col(15)) & (yi[:, None] < col(16))
    return x, y, t, hit, col(4) + t * col(5)


def bake(mesh, ribbons, tiles, name, seed=0):
    size = tiles[0].size
    attributes = np.zeros((size, size, 4), dtype=np.float32)
    attributes[:, :, 3] = 1
    coordinates = np.zeros_like(attributes)
    coordinates[:, :, :3] = (0.5, 1, 0.5)
    mesh.calc_loop_triangles()
    mesh.calc_tangents(uvmap="UVMap")
    # Textured meshes use explicit triangles, in row order (left then right).
    bases = []
    for triangle in mesh.loop_triangles:
        loop = mesh.loops[triangle.loops[0]]
        tangent, normal = Vector(loop.tangent), Vector(loop.normal)
        bases.append((tangent, normal.cross(tangent) * loop.bitangent_sign, normal))
    triangle_start = 0
    warnings = 0
    for ribbon, tile in zip(ribbons, tiles):
        projected = [(strand, _project(ribbon, strand)) for strand in ribbon.strands]
        depths = [p[2] for _, points in projected for p in points]
        low, high = min(depths), max(depths)
        span = high - low
        height, width = tile.height, tile.width
        raster = {strand.identifier: list(_batches(_segments(ribbon, points, width, height)))
                  for strand, points in projected}
        coverage = np.zeros((height, width), np.float32)
        best = np.full((height, width), -np.inf, np.float32)
        attrib = attributes[tile.y:tile.y + height, tile.x:tile.x + width]
        coords = coordinates[tile.y:tile.y + height, tile.x:tile.x + width]
        for ox, oy in ((-0.25, -0.25), (0.25, -0.25), (-0.25, 0.25), (0.25, 0.25)):
            sample_depth = np.full((height, width), -np.inf, np.float32)
            for strand, points in projected:
                random = strand_seed(strand.identifier, seed)
                for segments, bounds in raster[strand.identifier]:
                    x0, x1, y0, y1 = bounds
                    x, y, factors, hits, depths_batch = _raster_batch(segments, bounds, width, height, ox, oy)
                    for i, segment in enumerate(segments):
                        a, b, row = segment[:3]
                        t, hit, depth = factors[i], hits[i], depths_batch[i]
                        # Keep original segment and subsample order, including
                        # strict depth ties and float32 winner-state rounding.
                        sample = sample_depth[y0:y1, x0:x1]
                        sample[hit] = np.maximum(sample[hit], depth[hit])
                        winner = hit & (depth > best[y0:y1, x0:x1])
                        if not winner.any():
                            continue
                        best[y0:y1, x0:x1][winner] = depth[winner]
                        out_a, out_c = attrib[y0:y1, x0:x1], coords[y0:y1, x0:x1]
                        out_a[:, :, 1][winner] = ((depth[winner] - low) / span if span > 1e-10 else 0.5)
                        out_a[:, :, 2][winner] = random
                        out_c[:, :, 3][winner] = a[1] + t[winner] * (b[1] - a[1])
                        direction = (b[4] - a[4]).normalized()
                        row_v = (y - ribbon.parameters[row]) / (ribbon.parameters[row + 1] - ribbon.parameters[row])
                        right = x >= row_v
                        for index, mask in ((0, winner & right), (1, winner & ~right)):
                            tangent, bitangent, normal = bases[triangle_start + 2 * row + index]
                            encoded = [(direction.dot(axis) + 1) / 2 for axis in (tangent, bitangent, normal)]
                            out_c[:, :, :3][mask] = encoded
            coverage += np.isfinite(sample_depth) * 0.25
        attrib[:, :, 0] = coverage
        if not np.any(coverage):
            raise HairballError("A card has no covered texels; increase Atlas Size or strand radius.")
        if np.count_nonzero(coverage) < height:
            warnings += 1
        # Extend data two texels outside coverage; never extend opacity or mix islands.
        valid = coverage > 0
        for _ in range(2):
            old = valid.copy()
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ys, xs = slice(max(0, dy), height + min(0, dy)), slice(max(0, dx), width + min(0, dx))
                sy, sx = slice(max(0, -dy), height - max(0, dy)), slice(max(0, -dx), width - max(0, dx))
                take = ~valid[ys, xs] & old[sy, sx]
                attrib[ys, xs, 1:3][take] = attrib[sy, sx, 1:3][take]
                coords[ys, xs][take] = coords[sy, sx][take]
                valid[ys, xs] |= take
        triangle_start += 2 * (len(ribbon.parameters) - 1)
    images = []
    try:
        images.append(_image(f"{name} Attributes", attributes))
        images.append(_image(f"{name} Coordinates", coordinates))
        return images, warnings
    except Exception:
        for image in images:
            bpy.data.images.remove(image)
        raise
