"""Deterministic greedy clusters with conservative per-root deformation boundaries."""
from dataclasses import dataclass
import math

from mathutils import Vector

from .cards import _arc_samples
from .evaluation import HairballError


@dataclass(frozen=True)
class Bundle:
    anchor: int
    strands: tuple


def cluster_strands(strands, anchors, root_distance=0.01, shape_distance=0.005,
                    direction_angle=math.radians(35), max_strands=8):
    """Inputs use one metric coordinate space (world space in the generator).

    All members must pass pairwise tests, not just match a moving centroid.
    Exact anchor equality intentionally favors independent motion over savings.
    """
    if (not strands or len(strands) != len(anchors) or max_strands < 1
            or not all(math.isfinite(v) and v > 0 for v in (root_distance, shape_distance))
            or not math.isfinite(direction_angle) or not 0 <= direction_angle <= math.pi):
        raise HairballError("Clustering needs valid strands, anchors, distances and direction limits.")
    if len({s.identifier for s in strands}) != len(strands):
        raise HairballError("Clustering needs unique strand identities.")
    parameters = tuple(i / 16 for i in range(17))
    features = {}
    for strand in strands:
        samples = _arc_samples(strand.points, parameters)
        root = samples[0]
        direction = next((p - root for p in samples[1:] if (p - root).length > 1e-10), None)
        if direction is None:
            raise HairballError("Zero-length strands cannot be clustered.")
        features[strand.identifier] = (root, direction.normalized(), tuple(p - root for p in samples))
    cosine = math.cos(direction_angle)

    def compatible(a, b):
        root_a, direction_a, shape_a = features[a.identifier]
        root_b, direction_b, shape_b = features[b.identifier]
        return ((root_a - root_b).length <= root_distance
                and direction_a.dot(direction_b) >= cosine - 1e-7
                and max((x - y).length for x, y in zip(shape_a, shape_b)) <= shape_distance)

    def cell(root):
        return tuple(math.floor(value / root_distance) for value in root)

    groups, buckets = [], {}
    for strand, anchor in sorted(zip(strands, anchors), key=lambda item: item[0].identifier):
        if not isinstance(anchor, int) or anchor < 0:
            raise HairballError("Root anchors must be original non-negative vertex indices.")
        root = features[strand.identifier][0]
        xyz = cell(root)
        candidates = []
        for x in range(xyz[0] - 1, xyz[0] + 2):
            for y in range(xyz[1] - 1, xyz[1] + 2):
                for z in range(xyz[2] - 1, xyz[2] + 2):
                    candidates.extend(buckets.get((anchor, x, y, z), ()))
        destination = next((index for index in sorted(candidates)
                            if len(groups[index][1]) < max_strands
                            and all(compatible(strand, other) for other in groups[index][1])), None)
        if destination is None:
            destination = len(groups)
            groups.append((anchor, []))
            buckets.setdefault((anchor, *xyz), []).append(destination)
        groups[destination][1].append(strand)
    return tuple(Bundle(anchor, tuple(members)) for anchor, members in groups)
