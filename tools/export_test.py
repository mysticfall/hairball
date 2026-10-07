"""Isolated factory-startup checks for the one-click cards export package."""
import json
import os
import struct
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
assert "--background" in sys.argv, "Isolated Blender only: run with --background --factory-startup"
assert not bpy.data.filepath, "Refusing to touch a loaded user file"

import numpy as np

from cards_test import fixture

ARTIFACTS = None


def pixels(image):
    array = np.empty(len(image.pixels), dtype=np.float32)
    image.pixels.foreach_get(array)
    return array.reshape(image.size[1], image.size[0], 4)


def accessor(document, raw, length, index):
    item = document['accessors'][index]
    view = document['bufferViews'][item['bufferView']]
    components = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}[item['type']]
    dtype = {5126: '<f4', 5125: '<u4', 5123: '<u2', 5121: 'u1'}[item['componentType']]
    start = 20 + length + 8 + view.get('byteOffset', 0) + item.get('byteOffset', 0)
    return np.frombuffer(raw, dtype=dtype, count=item['count'] * components, offset=start).reshape(-1, components)


def main():
    global ARTIFACTS
    artifacts = os.environ.get('HAIRBALL_ARTIFACTS', '/tmp/opencode/hairball-tests')
    os.makedirs(artifacts, exist_ok=True)
    ARTIFACTS = artifacts
    import hairball
    hairball.register()
    from hairball.geometry import generate_geometry
    surface, groom, rig = fixture()
    settings = bpy.context.scene.hairball
    settings.atlas_size = 256
    settings.card_width = 0.004
    result, report = generate_geometry(groom, settings, textured=True)
    assert report['cards'] == 2
    images = (result['hairball_attributes'], result['hairball_coordinates'])
    original = [pixels(image) for image in images]

    # Selection is borrowed and restored around the export.
    bpy.ops.object.select_all(action='DESELECT')
    result.select_set(True)
    rig.select_set(True)
    bpy.context.view_layer.objects.active = result
    previous = tuple(bpy.context.selected_objects)
    directory = os.path.join(artifacts, 'package')
    os.makedirs(directory, exist_ok=True)
    status = bpy.ops.hairball.export_cards('EXEC_DEFAULT', directory=directory,
                                           filename='pubic_test.glb')
    assert status == {'FINISHED'}, status
    assert tuple(bpy.context.selected_objects) == previous
    assert bpy.context.view_layer.objects.active == result

    stem = os.path.join(directory, 'pubic_test')
    for suffix in ('.glb', '_attributes.png', '_coordinates.png'):
        assert os.path.isfile(stem + suffix), stem + suffix
    raw = open(stem + '.glb', 'rb').read()
    assert raw[:4] == b'glTF'
    length = struct.unpack_from('<I', raw, 12)[0]
    document = json.loads(raw[20:20 + length])
    primitive = document['meshes'][0]['primitives'][0]
    attrs = primitive['attributes']
    assert {'NORMAL', 'TANGENT', 'TEXCOORD_0', 'JOINTS_0', 'WEIGHTS_0'} <= set(attrs)
    assert len(primitive['targets']) == 2  # independent source morphs
    assert document.get('skins'), 'expected exported skin'
    joints = accessor(document, raw, length, attrs['JOINTS_0'])
    weights = accessor(document, raw, length, attrs['WEIGHTS_0'])
    assert joints.min() >= 0 and joints.max() <= len(document['skins'][0]['joints'])
    assert np.allclose(weights.sum(axis=1), 1.0, atol=1e-5)
    # The armature travels with the cards; the body surface does not.
    names = {node['name'] for node in document['nodes']}
    assert rig.name in names and surface.name not in names, names

    for image, path, source in zip(images, ('_attributes.png', '_coordinates.png'), original):
        assert bpy.path.abspath(image.filepath) == stem + path
        loaded = bpy.data.images.load(stem + path, check_existing=False)
        loaded.colorspace_settings.name = 'Non-Color'
        loaded.alpha_mode = 'CHANNEL_PACKED'
        assert tuple(loaded.size) == tuple(image.size)
        assert np.max(np.abs(pixels(loaded) - source)) <= 1 / 255 + 1e-6
        bpy.data.images.remove(loaded)
    record = json.loads(result['hairball_export'])
    assert record['stem'] == 'pubic_test' and record['glb'] == stem + '.glb'
    assert record['materials'] is False

    # Include-material variant still exports the same basis, now with a material.
    status = bpy.ops.hairball.export_cards('EXEC_DEFAULT', directory=directory,
                                           filename='pubic_test.glb', include_material=True)
    assert status == {'FINISHED'}
    raw = open(stem + '.glb', 'rb').read()
    length = struct.unpack_from('<I', raw, 12)[0]
    document = json.loads(raw[20:20 + length])
    assert document.get('materials'), 'embedded material expected'
    assert json.loads(result['hairball_export'])['materials'] is True

    # Invalid inputs cancel without writing anything new.
    before = sorted(os.listdir(directory))
    for kwargs in ({'directory': directory, 'filename': ''},
                   {'directory': '/nonexistent/hairball', 'filename': 'x.glb'}):
        try:
            bpy.ops.hairball.export_cards('EXEC_DEFAULT', **kwargs)
        except RuntimeError:
            pass
        else:
            raise AssertionError(f'expected cancellation: {kwargs}')
    assert sorted(os.listdir(directory)) == before

    # Poll refuses anything that is not a generated cards object.
    bpy.context.view_layer.objects.active = surface
    assert bpy.ops.hairball.export_cards.poll() is False
    bpy.context.view_layer.objects.active = groom
    assert bpy.ops.hairball.export_cards.poll() is False
    print('HAIRBALL_EXPORT_TESTS=PASS')


try:
    main()
except Exception:
    traceback.print_exc()
    sys.exit(1)
