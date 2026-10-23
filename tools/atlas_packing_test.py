"""Variable card extents must receive independent, padded, deterministic tiles."""
from pathlib import Path
import random
import sys

import bpy

assert bpy.app.background and not bpy.data.filepath, 'Use isolated factory startup.'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hairball.atlas import pack, resolution_report
from hairball.cards import Ribbon
from hairball.evaluation import HairballError, Strand


def ribbon(width, length):
    return Ribbon(((0, 0, 0), (0, 0, length)), ((1, 0, 0),) * 2,
                  (width / 2,) * 2, (0, 1), 0, ())


def main():
    rng = random.Random(20261022)
    ribbons = [ribbon(rng.uniform(.001, .04), rng.uniform(.02, .3)) for _ in range(150)]
    ribbons += [ribbon(.005, .1), ribbon(.03, .1), ribbon(.005, .25)]
    tiles = pack(ribbons, 512)
    assert tiles == pack(ribbons, 512)
    assert len(tiles) == len(ribbons)
    assert tiles[-2].width > tiles[-3].width
    assert tiles[-1].height > tiles[-3].height
    assert len({(t.width, t.height) for t in tiles}) > 50
    for i, a in enumerate(tiles):
        assert min(a.width, a.height) >= 8
        assert a.x >= 3 and a.y >= 3
        assert a.x + a.width + 3 <= a.size and a.y + a.height + 3 <= a.size
        assert all(0 <= v <= 1 for uv in ((0, 0), (1, 1)) for v in a.uv(uv))
        for b in tiles[i + 1:]:
            assert (a.x + a.width + 6 <= b.x or b.x + b.width + 6 <= a.x
                    or a.y + a.height + 6 <= b.y or b.y + b.height + 6 <= a.y)
    assert len(pack((ribbons[0],) * 16, 64)) == 16
    from dataclasses import replace
    detailed = replace(ribbons[-3], strands=(Strand(1, ((0, 0, 0), (0, 0, .1)), (.00001,) * 2),))
    report = resolution_report((detailed,), pack((detailed,), 64))
    assert report['underresolved_cards'] == 1
    assert report['atlas_tile_width_min'] == report['atlas_tile_width_max']
    populated = replace(detailed, strands=detailed.strands * 64)
    single_tile, bundle_tile = pack((detailed, populated), 256)
    assert bundle_tile.width > single_tile.width
    assert bundle_tile.height < single_tile.height
    for invalid in (ribbon(0, .1), ribbon(.01, 0), ribbon(float('nan'), .1)):
        try:
            pack((invalid,), 64)
        except HairballError:
            pass
        else:
            raise AssertionError('Invalid dimensions must reject before allocation')
    print('HAIRBALL_ATLAS_PACKING_OK')


main()
