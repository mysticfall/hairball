"""CPU strand projection/rasterization using Blender's bundled NumPy.

Coverage integrates the union of strand-width intervals horizontally at four
vertical samples. Subpixel strands keep their area, without a radius floor.
Data comes from the shallowest contributing strand, never a channel average.
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


# Legacy point-raster reference kernels retained for scalar/batch regression
# comparisons. Production coverage uses _filtered_tile below, not these hits.
def _segments(ribbon, points, width, height):
    """Precompute geometry once, rather than for every coverage subsample."""
    result = []
    for a, b in zip(points, points[1:]):
        row = a[5]
        across = 2 * max(ribbon.half_widths[row:row + 2])
        along = ((Vector(ribbon.centers[row + 1]) - Vector(ribbon.centers[row])).length
                 / (ribbon.parameters[row + 1] - ribbon.parameters[row]))
        radius = max(a[3], b[3])
        if radius <= 0 or along <= 1e-12:
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


def _filtered_tile(ribbon, tile, bases, seed):
    """Area-preserving strip filter, with exact horizontal interval unions.

    V is monotonic root-to-tip even when the world-space strand curls. Each
    vertical sample intersects every projected strand once. Merge its horizontal
    width intervals *before* filtering; coincident strands must not add opacity.
    Four vertical quadrature samples approximate changing width/curvature. End
    caps are clipped at the strand's root and tip rather than enlarged to pixels.
    Row batches bound scratch to 65,536 strand/texel pairs (one row minimum).
    """
    height, width = tile.height, tile.width
    projected = [_project(ribbon, strand) for strand in ribbon.strands]
    low = min(p[2] for points in projected for p in points)
    high = max(p[2] for points in projected for p in points)
    span = high - low
    attributes = np.zeros((height, width, 4), np.float32)
    attributes[:, :, 3] = 1
    coordinates = np.zeros_like(attributes)
    coordinates[:, :, :3] = (0.5, 1, 0.5)
    best = np.full((height, width), -np.inf, np.float64)
    pixel_left = np.arange(width)[None, :] - 0.5
    pixel_right = pixel_left + 1
    count = len(projected)
    rows_per_batch = max(1, min(32, 65536 // max(1, count * width)))
    parameters = np.asarray(ribbon.parameters)
    centers = np.asarray(ribbon.centers)
    row_speed = np.linalg.norm(np.diff(centers, axis=0), axis=1) / np.diff(parameters)
    half_widths = np.asarray(ribbon.half_widths)
    seeds = np.asarray([strand_seed(s.identifier, seed) for s in ribbon.strands])
    samples = [(np.asarray([p[:4] for p in points]),
                np.asarray([tuple(p[4]) for p in points])) for points in projected]
    bases = np.asarray(bases)
    for offset in (-0.375, -0.125, 0.125, 0.375):
        for start in range(0, height, rows_per_batch):
            stop = min(height, start + rows_per_batch)
            u = (np.arange(start, stop) + offset) / (height - 1)
            row = np.clip(np.searchsorted(parameters, u, side='right') - 1, 0, len(parameters) - 2)
            across = 2 * np.interp(u, parameters, half_widths)
            speed = row_speed[row]
            left, right, depths, directions = [], [], [], []
            for data, positions in samples:
                knots = data[:, 1]
                index = np.clip(np.searchsorted(knots, u, side='right') - 1, 0, len(knots) - 2)
                a, b = data[index], data[index + 1]
                du = b[:, 1] - a[:, 1]
                t = np.clip((u - a[:, 1]) / du, 0, 1)
                x = (a[:, 0] + t * (b[:, 0] - a[:, 0])) * (width - 1)
                radius = a[:, 3] + t * (b[:, 3] - a[:, 3])
                slope = (b[:, 0] - a[:, 0]) * across / (du * np.maximum(speed, 1e-12))
                rx = radius / across * (width - 1) * np.sqrt(1 + slope * slope)
                valid = (u >= 0) & (u <= 1) & (speed > 1e-12) & (radius > 0)
                left.append(np.where(valid, x - rx, np.inf))
                right.append(np.where(valid, x + rx, -np.inf))
                depths.append(a[:, 2] + t * (b[:, 2] - a[:, 2]))
                direction = positions[index + 1] - positions[index]
                direction /= np.maximum(np.linalg.norm(direction, axis=1)[:, None], 1e-12)
                directions.append(direction)
            left, right, depths = map(np.asarray, (left, right, depths))
            # Sorted intervals minus the prefix union: exact, including overlaps
            # between strands and depth layers. No alpha accumulation shortcuts.
            order = np.argsort(left, axis=0, kind='stable')
            lo = np.take_along_axis(left, order, axis=0)
            hi = np.take_along_axis(right, order, axis=0)
            previous = np.vstack((np.full((1, stop - start), -np.inf),
                                  np.maximum.accumulate(hi, axis=0)[:-1]))
            lo = np.maximum(lo, previous)
            area = np.maximum(0, np.minimum(hi[:, :, None], pixel_right)
                              - np.maximum(lo[:, :, None], pixel_left))
            attributes[start:stop, :, 0] += area.sum(axis=0) * 0.25
            hits = ((right[:, :, None] > pixel_left) & (left[:, :, None] < pixel_right))
            candidates = np.where(hits, depths[:, :, None], -np.inf)
            winner = candidates.argmax(axis=0)
            sample_depth = np.take_along_axis(candidates, winner[None, :, :], axis=0)[0]
            update = sample_depth > best[start:stop]
            best[start:stop][update] = sample_depth[update]
            out_a, out_c = attributes[start:stop], coordinates[start:stop]
            out_a[:, :, 1][update] = ((sample_depth[update] - low) / span if span > 1e-10 else 0.5)
            out_a[:, :, 2][update] = seeds[winner][update]
            out_c[:, :, 3][update] = np.broadcast_to(u[:, None], update.shape)[update]
            direction = np.asarray(directions)[winner, np.arange(stop - start)[:, None]]
            row_v = (u - parameters[row]) / (parameters[row + 1] - parameters[row])
            triangle = 2 * row[:, None] + (np.arange(width)[None, :] / (width - 1) < row_v[:, None])
            basis = bases[triangle]
            encoded = (np.einsum('...ij,...j->...i', basis, direction) + 1) / 2
            out_c[:, :, :3][update] = encoded[update]
    attributes[:, :, 0] = np.clip(attributes[:, :, 0], 0, 1)
    return attributes, coordinates


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
    starts, total = [], 0
    for ribbon in ribbons:
        starts.append(total)
        total += 2 * (len(ribbon.parameters) - 1)
    # Shared pattern patches bake only their donor; identical islands dedupe.
    patches = {}
    for index, tile in enumerate(tiles):
        patches.setdefault((tile.x, tile.y, tile.width, tile.height, tile.size), []).append(index)
    warnings = 0
    saturated = 0
    for members in patches.values():
        donor = max(members, key=lambda i: (len(ribbons[i].strands), -i))
        ribbon, tile = ribbons[donor], tiles[donor]
        height, width = tile.height, tile.width
        attrib = attributes[tile.y:tile.y + height, tile.x:tile.x + width]
        coords = coordinates[tile.y:tile.y + height, tile.x:tile.x + width]
        attrib[:], coords[:] = _filtered_tile(
            ribbon, tile, bases[starts[donor]:starts[donor] + 2 * (len(ribbon.parameters) - 1)], seed)
        coverage = attrib[:, :, 0]
        if np.max(coverage) < 0.5 / 255:
            raise HairballError("A card has no coverage surviving 8-bit PNG quantization; increase Atlas Size "
                                "or reduce card fragmentation. Do not force thicker strands to hide this.")
        if np.count_nonzero(coverage) < height:
            warnings += 1
        # Near-solid coverage cannot dither into individual strands downstream.
        if np.count_nonzero(coverage > 0.95) >= 0.9 * np.count_nonzero(coverage):
            saturated += 1
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
    images = []
    try:
        images.append(_image(f"{name} Attributes", attributes))
        images.append(_image(f"{name} Coordinates", coordinates))
        return images, warnings, saturated
    except Exception:
        for image in images:
            bpy.data.images.remove(image)
        raise
