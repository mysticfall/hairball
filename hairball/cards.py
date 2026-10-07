"""Bundle-fitting feasibility kernel: curved ribbons with parallel-transport frames.

Clustering and atlas placement are deliberately separate from this kernel.
"""
from bisect import bisect_right
from dataclasses import dataclass
import math

from mathutils import Vector

from .evaluation import HairballError


@dataclass(frozen=True)
class Ribbon:
    centers: tuple
    sides: tuple
    half_widths: tuple
    parameters: tuple
    anchor: int
    strands: tuple


def _arc_samples(points, parameters):
    points = [Vector(p) for p in points]
    cumulative = [0.0]
    for a, b in zip(points, points[1:]):
        cumulative.append(cumulative[-1] + (b - a).length)
    if cumulative[-1] < 1e-10:
        raise HairballError("Zero-length strands cannot form cards.")
    cumulative = [value / cumulative[-1] for value in cumulative]
    result = []
    for t in parameters:
        index = min(bisect_right(cumulative, t) - 1, len(points) - 2)
        span = cumulative[index + 1] - cumulative[index]
        factor = (t - cumulative[index]) / span if span > 1e-12 else 0
        result.append(points[index].lerp(points[index + 1], factor))
    return result


def _sampled_radii(radii, knots, parameters):
    """Linear radius at arbitrary arc parameters, matching the baker exactly."""
    values = []
    for u in parameters:
        index = min(bisect_right(knots, u) - 1, len(knots) - 2)
        factor = (u - knots[index]) / max(knots[index + 1] - knots[index], 1e-12)
        values.append(radii[index] * (1 - factor) + radii[index + 1] * factor)
    return values


def _widen(centers, sides, widths, parameters, strands):
    """Grow row half-widths until the interpolated ribbon contains every strand.

    Rows sample the bundle coarsely; strands can bow outward between rows. The
    projection here mirrors the baker's, so baking never needs to clip or fail.
    """
    centers = [Vector(c) for c in centers]
    sides = [Vector(s) for s in sides]
    for _ in range(32):
        deficit = 0.0
        for strand in strands:
            positions = [Vector(p) for p in strand.points]
            distances = [0.0]
            for a, b in zip(positions, positions[1:]):
                distances.append(distances[-1] + (b - a).length)
            knots = [d / distances[-1] for d in distances]
            merged = sorted(set(parameters) | set(knots))
            points = _arc_samples(strand.points, merged)
            radii = _sampled_radii(strand.radii, knots, merged)
            for u, point, radius in zip(merged, points, radii):
                row = min(bisect_right(parameters, u) - 1, len(parameters) - 2)
                span = parameters[row + 1] - parameters[row]
                t = (u - parameters[row]) / span if span > 1e-12 else 0.0
                center = centers[row].lerp(centers[row + 1], t)
                side = sides[row].lerp(sides[row + 1], t).normalized()
                width = widths[row] * (1 - t) + widths[row + 1] * t
                needed = abs((point - center).dot(side)) + radius
                slack = needed - (width + max(1e-8, width * 1e-5))
                if slack > 0:
                    # Uniform growth covers the interpolated deficit exactly;
                    # proportional splits only cover (1-t)^2 + t^2 of it.
                    widths[row] += slack
                    widths[row + 1] += slack
                    deficit = max(deficit, slack)
        if deficit <= 0:
            return
    raise HairballError("Strand widths do not settle; use smaller bundles.")


def fit_bundle(strands, anchor, segments=16, minimum_width=0.002, *, parameters=None):
    """Fit a ribbon to an already attachment-compatible bundle.

    Uniform arc-length rows remain available for fixed-detail callers;
    fit_adaptive supplies curvature-selected parameters instead. Full root-to-tip
    parameters are retained rather than renormalized for individual intervals.
    """
    if not strands or segments < 1 or minimum_width <= 0:
        raise HairballError("Ribbon fitting needs strands, positive width, and at least one segment.")
    parameters = (tuple(i / segments for i in range(segments + 1)) if parameters is None
                  else tuple(parameters))
    if (len(parameters) < 2 or parameters[0] != 0 or parameters[-1] != 1
            or any(not math.isfinite(p) for p in parameters)
            or any(a >= b for a, b in zip(parameters, parameters[1:]))):
        raise HairballError("Ribbon rows must increase strictly from root 0 to tip 1.")
    segments = len(parameters) - 1
    samples = [_arc_samples(s.points, parameters) for s in strands]
    centers = [sum((row[i] for row in samples), Vector()) / len(samples)
               for i in range(segments + 1)]
    tangents = []
    for i in range(segments + 1):
        tangent = centers[min(i + 1, segments)] - centers[max(i - 1, 0)]
        if tangent.length < 1e-10:
            raise HairballError("The bundle centerline folds onto itself; use smaller bundles.")
        tangents.append(tangent.normalized())
    # Widest root displacement is an inexpensive initial width-plane estimate.
    displacement = max((row[0] - centers[0] for row in samples), key=lambda v: v.length_squared)
    side = displacement - tangents[0] * displacement.dot(tangents[0])
    if side.length < 1e-10:
        axis = min((Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))),
                   key=lambda v: abs(v.dot(tangents[0])))
        side = axis - tangents[0] * axis.dot(tangents[0])
    side.normalize()
    sides = []
    widths = []
    radius = max(max(s.radii) for s in strands)
    for i, tangent in enumerate(tangents):
        if i:
            side = tangents[i - 1].rotation_difference(tangent) @ side
            side = (side - tangent * side.dot(tangent)).normalized()
        sides.append(tuple(side))
        width = max(abs((row[i] - centers[i]).dot(side)) for row in samples)
        widths.append(max(minimum_width / 2, width + radius))
    _widen(centers, sides, widths, parameters, strands)
    return Ribbon(tuple(tuple(p) for p in centers), tuple(sides), tuple(widths),
                  parameters, anchor, tuple(strands))


def fit_adaptive(strands, anchor, minimum_width=0.002, fit_error=0.001,
                 bend_limit=math.radians(20), max_segments=64):
    """Simplify the sampled centerline, retaining full root-to-tip coordinates.

    Candidate rows include every strand knot: fixed sparse probes cannot alias
    a tight curl into a straight card. Bend limits constrain turning *within*
    each interval; sharp corners already in the source are not smoothed away.
    """
    if (not strands or max_segments < 1 or not math.isfinite(fit_error) or fit_error <= 0
            or not math.isfinite(bend_limit) or not 0 < bend_limit <= math.pi):
        raise HairballError("Adaptive fitting needs positive error, bend and segment limits.")
    knots = {0.0, 1.0}
    lengths = []
    for strand in strands:
        positions = [Vector(p) for p in strand.points]
        cumulative = [0.0]
        for a, b in zip(positions, positions[1:]):
            cumulative.append(cumulative[-1] + (b - a).length)
        if cumulative[-1] < 1e-10:
            raise HairballError("Zero-length strands cannot form cards.")
        lengths.append(cumulative[-1])
        knots.update(value / cumulative[-1] for value in cumulative)
    parameters = sorted(knots)
    # Merge numerical duplicates, not distinct curve bends.
    parameters = [t for i, t in enumerate(parameters)
                  if i == 0 or t - parameters[i - 1] > 1e-10 or t == 1]
    samples = [_arc_samples(s.points, parameters) for s in strands]
    centers = [sum((row[i] for row in samples), Vector()) / len(samples)
               for i in range(len(parameters))]
    edges = [b - a for a, b in zip(centers, centers[1:])]
    center_length = sum(edge.length for edge in edges)
    if center_length < sum(lengths) / len(lengths) * 0.65:
        raise HairballError("Bundle averaging cancels too much curl; use smaller bundles.")
    turns = [0.0]
    for before, after in zip(edges, edges[1:]):
        turn = before.angle(after, 0) if min(before.length, after.length) > 1e-10 else 0
        turns.append(turns[-1] + turn)
    turns.append(turns[-1])
    rows = {0, len(parameters) - 1}
    pending = [(0, len(parameters) - 1)]
    while pending:
        start, end = pending.pop()
        if end - start <= 1:
            continue
        a, b = centers[start], centers[end]
        interval = parameters[end] - parameters[start]
        errors = [(centers[i] - a.lerp(b, (parameters[i] - parameters[start]) / interval)).length
                  for i in range(start + 1, end)]
        worst = max(range(len(errors)), key=errors.__getitem__) + start + 1
        internal_turn = turns[end - 1] - turns[start]
        if max(errors) <= fit_error and internal_turn <= bend_limit:
            continue
        if max(errors) <= fit_error:
            worst = min(range(start + 1, end),
                        key=lambda i: abs(parameters[i] - (parameters[start] + parameters[end]) / 2))
        if len(rows) - 1 >= max_segments:
            raise HairballError("Card detail limit cannot meet the fit tolerance; increase Max Segments or Fit Error.")
        rows.add(worst)
        pending.extend(((start, worst), (worst, end)))
    chosen = tuple(parameters[i] for i in sorted(rows))
    return fit_bundle(strands, anchor, minimum_width=minimum_width, parameters=chosen)


def fit_bundles(bundles, **settings):
    """Split failed multi-strand fits deterministically; never change root anchors."""
    ribbons = []
    def fit(members, anchor):
        try:
            ribbons.append(fit_adaptive(members, anchor, **settings))
        except HairballError:
            if len(members) == 1:
                raise
            midpoint = len(members) // 2
            fit(members[:midpoint], anchor)
            fit(members[midpoint:], anchor)
    for bundle in bundles:
        fit(bundle.strands, bundle.anchor)
    return tuple(ribbons)


def ribbon_geometry(ribbon):
    vertices = []
    for center, side, width in zip(ribbon.centers, ribbon.sides, ribbon.half_widths):
        center, side = Vector(center), Vector(side)
        vertices.extend((tuple(center - side * width), tuple(center + side * width)))
    faces = [(2 * i, 2 * i + 1, 2 * i + 3, 2 * i + 2)
             for i in range(len(ribbon.centers) - 1)]
    # U is across width; V increases root-to-tip. With this winding T=side,
    # B follows the centerline, so a centered strand encodes near (0.5,1,0.5).
    uvs = [(0, ribbon.parameters[i // 2]) if i % 2 == 0 else (1, ribbon.parameters[i // 2])
           for i in range(len(vertices))]
    return vertices, faces, uvs
