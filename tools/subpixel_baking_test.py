"""Subpixel coverage must retain area, not disappear or acquire a radius floor."""
from pathlib import Path
import sys

import bpy
import numpy as np

assert bpy.app.background and not bpy.data.filepath, 'Use isolated factory startup.'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hairball.atlas import Tile
from hairball.baking import _filtered_tile, bake, strand_seed
from hairball.cards import Ribbon, ribbon_geometry
from hairball.evaluation import HairballError, Strand


def coverage(strands, width=16, height=32):
    ribbon = Ribbon(((0, 0, 0), (0, 0, 0.1)), ((1, 0, 0),) * 2,
                    (0.01,) * 2, (0, 1), 0, strands)
    basis = ((1, 0, 0), (0, 0, 1), (0, -1, 0))
    return _filtered_tile(ribbon, Tile(0, 0, width, height, 64), [basis] * 2, 7)


def strand(identifier, x, radius, y=0):
    return Strand(identifier, ((x, y, 0), (x, y, 0.1)), (radius, radius))


def main():
    # 0.015-texel diameter: all old four point samples missed these strands.
    radius = 0.00001
    areas = []
    for x in np.linspace(-0.001, 0.001, 21):
        a, c = coverage((strand(1, x, radius),))
        assert np.isfinite(a).all() and np.isfinite(c).all()
        assert a[:, :, 0].max() > 0
        expected = 2 * radius / 0.02 * 15 * 31
        assert abs(a[:, :, 0].sum() / expected - 1) < 1e-5
        assert a[:, :, 0].max() < 0.016  # Not a forced 0.25/0.5 footprint.
        areas.append(a[:, :, 0].sum())
    assert max(areas) / min(areas) < 1.00001
    a, _ = coverage((strand(1, 0, radius),))
    half, _ = coverage((strand(1, 0, radius / 2),))
    assert np.allclose(half[:, :, 0], a[:, :, 0] / 2)
    # Coincident depth layers cover the union once, with shallowest data.
    overlap, data = coverage((strand(1, 0, radius, 0.001), strand(2, 0, radius, -0.001)))
    assert np.array_equal(overlap[:, :, 0], a[:, :, 0])
    mask = overlap[:, :, 0] > 0
    assert np.all(overlap[:, :, 1][mask] == 1)
    assert np.allclose(overlap[:, :, 2][mask], strand_seed(2, 7))
    assert np.allclose(data[:, :, :3][mask], (0.5, 1, 0.5))
    # Disjoint intervals in one pixel add area; partially overlapping ones do not.
    separate, _ = coverage((strand(1, -0.0001, radius), strand(2, 0.0001, radius)))
    assert np.isclose(separate[:, :, 0].sum(), a[:, :, 0].sum() * 2)
    partial, _ = coverage((strand(1, 0, radius), strand(2, radius, radius)))
    assert np.isclose(partial[:, :, 0].sum(), a[:, :, 0].sum() * 1.5)
    # Inclined strands use the perpendicular physical radius, not horizontal
    # radius alone. Their integrated strip area grows with projected length.
    inclined = Strand(3, ((-.003, 0, 0), (.003, 0, .1)), (radius, radius))
    diagonal, _ = coverage((inclined,))
    assert np.isclose(diagonal[:, :, 0].sum() / a[:, :, 0].sum(),
                      np.sqrt(1 + (.006 / .1) ** 2), rtol=1e-5)
    # Tile resolution changes texel area, not the physical covered fraction.
    finer, _ = coverage((strand(1, 0, radius),), width=64, height=128)
    assert np.isclose(finer[:, :, 0].sum() / (63 * 127),
                      a[:, :, 0].sum() / (15 * 31))
    # A collapsed centerline interval must not divide by zero or write NaNs.
    from hairball.baking import _segments
    collapsed = Ribbon(((0, 0, 0),) * 2, ((1, 0, 0),) * 2,
                       (0.01,) * 2, (0, 1), 0, (strand(1, 0, radius),))
    from mathutils import Vector
    assert not _segments(collapsed, [(0.5, 0, 0, radius, Vector((0, 0, 0)), 0),
                                     (0.5, 1, 0, radius, Vector((0, 0, 0)), 0)], 16, 32)
    # Nonzero float coverage that becomes an empty PNG is not a valid export.
    tiny = Ribbon(((0, 0, 0), (0, 0, .1)), ((1, 0, 0),) * 2,
                  (.01,) * 2, (0, 1), 0, (strand(1, 0, 1e-10),))
    positions, quads, uvs = ribbon_geometry(tiny)
    faces = [triangle for a, b, c, d in quads for triangle in ((a, b, c), (a, c, d))]
    mesh = bpy.data.meshes.new('Subpixel quantization fixture')
    try:
        mesh.from_pydata(positions, [], faces)
        layer = mesh.uv_layers.new(name='UVMap')
        layer.data.foreach_set('uv', [v for loop in mesh.loops for v in uvs[loop.vertex_index]])
        images = set(bpy.data.images)
        try:
            bake(mesh, (tiny,), (Tile(3, 3, 16, 32, 64),), 'Must reject')
        except HairballError as exc:
            assert '8-bit PNG' in str(exc)
        else:
            raise AssertionError('Quantized-away cards must reject')
        assert set(bpy.data.images) == images
    finally:
        bpy.data.meshes.remove(mesh)
    print('HAIRBALL_SUBPIXEL_BAKING_OK')


main()
