"""Shared pattern patches must group similar cards and keep donors deterministic."""
from pathlib import Path
import sys

import bpy
import numpy as np

assert bpy.app.background and not bpy.data.filepath, 'Use isolated factory startup.'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hairball.atlas import pack_patterns, Tile
from hairball.baking import bake
from hairball.cards import Ribbon, ribbon_geometry
from hairball.evaluation import HairballError, Strand


def strand(identifier, x, radius, length, wave=0.0, phase=0.0):
    points = [(x + wave * np.sin(np.pi * i / 8 + phase), 0, length * i / 8) for i in range(9)]
    return Strand(identifier, points, (radius,) * 9)


def ribbon(strands, width, length, wave=0.0, phase=0.0):
    centers = [(wave * np.sin(np.pi * i / 8 + phase), 0, length * i / 8) for i in range(9)]
    return Ribbon(centers, ((1, 0, 0),) * 9, (width / 2,) * 9,
                  tuple(i / 8 for i in range(9)), 0, strands)


def main():
    radius, length = 0.0002, 0.2
    straight = [ribbon([strand(i, x * 0.001, radius, length) for i in range(8)], 0.012, length)
                for x in range(-4, 5)]
    wavy = [ribbon([strand(100 + i, x * 0.001, radius, length, 0.002, x * 0.3) for i in range(12)],
                   0.02, length, 0.004, 0.3) for x in range(-2, 3)]
    ribbons = straight + wavy
    sources = [0] * len(straight) + [1] * len(wavy)
    tiles, groups = pack_patterns(ribbons, 1024, sources=sources)
    assert tiles == pack_patterns(ribbons, 1024, sources=sources)[0]
    assert len(tiles) == len(ribbons) and len(groups) == 2
    identities = {(t.x, t.y, t.width, t.height) for t in tiles}
    assert len(identities) == 2
    for group in groups:
        members = group['members']
        donor = group['donor']
        assert donor in members and donor == max(
            members, key=lambda i: (len(ribbons[i].strands), -i))
        for member in members:
            assert (tiles[member].x, tiles[member].y) == (tiles[donor].x, tiles[donor].y)
    assert all(t.width == 128 and t.height == 256 for t in tiles)
    # Groups never mix sources even with identical shapes.
    mixed = straight + [ribbon([strand(200 + i, x * 0.001, radius, length) for i in range(8)],
                               0.012, length) for x in range(-1, 2)]
    tiles2, groups2 = pack_patterns(mixed, 1024, sources=[0] * 9 + [1] * 3)
    assert len(groups2) == 2
    # Within one source, shape/population differences still split groups.
    tiles2b, groups2b = pack_patterns(straight + wavy, 1024, sources=[0] * 14)
    assert len(groups2b) == 2
    # Heavy diversity coarsens deterministically into the fixed patch grid.
    varied = [ribbon([strand(300 + i, 0, radius, length, 0.001 * j, j * 0.1) for i in range(1 + j % 30)],
                     0.010 + 0.0004 * j, length, 0.001 * j, j * 0.1) for j in range(40)]
    tiles3, groups3 = pack_patterns(varied, 256)
    assert tiles3 == pack_patterns(varied, 256)[0]
    assert len(tiles3) == 40 and 1 <= len(groups3) <= 21
    for tile in tiles3:
        assert tile.width == 32 and tile.height == 64
        assert tile.x >= 3 and tile.y >= 3 and tile.x + tile.width + 3 <= 256 and tile.y + tile.height + 3 <= 256
    # Baking writes the donor pattern once into each shared island.
    shared = (ribbons[0], ribbons[1])
    patch_tiles = (tiles[0], tiles[1])
    # Build the mesh for both cards explicitly to keep loop order like geometry.py.
    vertices, faces, uvs = [], [], []
    for shared_ribbon, tile in zip(shared, patch_tiles):
        positions, polygons, coordinates = ribbon_geometry(shared_ribbon)
        triangles = [triangle for a, b, c, d in polygons for triangle in ((a, b, c), (a, c, d))]
        start = len(vertices)
        vertices.extend(positions)
        faces.extend(tuple(start + index for index in triangle) for triangle in triangles)
        uvs.extend(tile.uv(uv) for uv in coordinates)
    mesh = bpy.data.meshes.new('Pattern reuse fixture')
    try:
        mesh.from_pydata(vertices, [], faces)
        layer = mesh.uv_layers.new(name='UVMap')
        layer.data.foreach_set('uv', [v for loop in mesh.loops for v in uvs[loop.vertex_index]])
        images, sparse, saturated = bake(mesh, shared, patch_tiles, 'Pattern test', seed=11)
        pixels = np.array(images[0].pixels[:]).reshape(1024, 1024, 4)
        coverage = pixels[:, :, 0]
        tile = patch_tiles[0]
        region = coverage[tile.y:tile.y + tile.height, tile.x:tile.x + tile.width]
        occupied = region > 0
        assert occupied.any() and occupied.mean() < 0.5
        assert len(np.unique(np.round(region[occupied] * 255))) > 4
        assert sparse == 0 and saturated == 0
        for image in images:
            bpy.data.images.remove(image)
    finally:
        bpy.data.meshes.remove(mesh)
    for invalid in ((),):
        try:
            pack_patterns(invalid, 256)
        except HairballError:
            pass
        else:
            raise AssertionError('Empty pattern input must reject')
    print('HAIRBALL_PATTERN_REUSE_OK')


main()
