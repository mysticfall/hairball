"""Batched raster arithmetic matches scalar reference, including depth ties."""
from pathlib import Path
import sys
import math
import bpy
import numpy as np

assert bpy.app.background and not bpy.data.filepath
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hairball.baking import _project, _segments, _batches, _raster_batch
from hairball.cards import fit_bundle
from hairball.evaluation import Strand


def scalar(segment, width, height, ox, oy):
    a, b, row, across, along, x0, x1, y0, y1, dx, dy, denominator = segment
    x, y = np.meshgrid((np.arange(x0, x1) + ox) / (width - 1),
                       (np.arange(y0, y1) + oy) / (height - 1))
    t = np.clip(((x - a[0]) * across * dx + (y - a[1]) * along * dy) / denominator, 0, 1)
    distance2 = ((x - (a[0] + t * (b[0] - a[0]))) * across) ** 2
    distance2 += ((y - (a[1] + t * (b[1] - a[1]))) * along) ** 2
    return t, distance2 <= (a[3] + t * (b[3] - a[3])) ** 2, a[2] + t * (b[2] - a[2])


def main():
    strands = tuple(Strand(i, tuple((.025 * math.sin(t * 4 * math.pi) + i * .0001,
                                    .01 * math.cos(t * 2 * math.pi), t * .2)
                                   for t in np.linspace(0, 1, 769)),
                           tuple(.0004 + .0001 * t for t in np.linspace(0, 1, 769)))
                    for i in range(3))
    ribbon = fit_bundle(strands, 0, segments=32, minimum_width=.004)
    checked = 0
    for width, height in ((9, 17), (87, 83), (17, 2042)):
        for strand in strands:
            projected = _project(ribbon, strand)
            for batch, bounds in _batches(_segments(ribbon, projected, width, height)):
                bx, ex, by, ey = bounds
                assert len(batch) == 1 or len(batch) * (ex - bx) * (ey - by) <= 65536
                for ox, oy in ((-.25, -.25), (.25, -.25), (-.25, .25), (.25, .25)):
                    _, _, factors, hits, depths = _raster_batch(batch, bounds, width, height, ox, oy)
                    for i, segment in enumerate(batch):
                        sx, ex, sy, ey = segment[5:9]
                        region = (slice(sy - by, ey - by), slice(sx - bx, ex - bx))
                        t, hit, depth = scalar(segment, width, height, ox, oy)
                        assert np.array_equal(t, factors[i][region])
                        assert np.array_equal(hit, hits[i][region])
                        assert np.array_equal(depth, depths[i][region])
                        outside = hits[i].copy()
                        outside[region] = False
                        assert not outside.any()
                        checked += 1
    print('HAIRBALL_BAKING_BATCH_TESTS=PASS', checked, 'scalar segment comparisons')


if __name__ == '__main__':
    main()
