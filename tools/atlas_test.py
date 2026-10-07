"""Atlas/channel/TBN and complete-result lifecycle tests, isolated factory only."""
from pathlib import Path
import json
import struct
import sys

import bpy
import numpy as np
from mathutils import Vector

assert bpy.app.background and not bpy.data.filepath, "Use isolated factory startup."
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import hairball
from hairball.atlas import pack
from hairball.baking import bake, strand_seed
from hairball.cards import fit_adaptive, ribbon_geometry
from hairball.evaluation import HairballError, Strand
from hairball.geometry import generate_geometry
from cards_test import fixture

ARTIFACTS = Path('/tmp/opencode/hairball-tests')
ARTIFACTS.mkdir(parents=True, exist_ok=True)


def pixels(image):
    values = np.empty(image.size[0] * image.size[1] * 4, np.float32)
    image.pixels.foreach_get(values)
    return values.reshape(image.size[1], image.size[0], 4)


def channels_test():
    # Two coincident projections: +normal (-Y) must win, carrying its own seed.
    deep = Strand(10, ((0, 0.001, 0), (0, 0.001, 0.1)), (0.0008, 0.0008))
    shallow = Strand(20, ((0, -0.001, 0), (0, -0.001, 0.1)), (0.0008, 0.0008))
    # Explicit X width frame; the bundle fitter would otherwise use Y spread.
    from dataclasses import replace
    ribbon = replace(fit_adaptive((deep, shallow), 0, minimum_width=0.01), sides=((1, 0, 0), (1, 0, 0)))
    tiles = pack((ribbon,), 128)
    assert tiles == pack((ribbon,), 128)
    verts, quads, uvs = ribbon_geometry(ribbon)
    mesh = bpy.data.meshes.new('Channel test')
    mesh.from_pydata(verts, [], [(0, 1, 3), (0, 3, 2)])
    mesh.update()
    layer = mesh.uv_layers.new(name='UVMap')
    for loop, item in zip(mesh.loops, layer.data):
        item.uv = tiles[0].uv(uvs[loop.vertex_index])
    images, _ = bake(mesh, (ribbon,), tiles, 'Channel test', seed=7)
    a, c = map(pixels, images)
    mask = a[:, :, 0] > 0
    assert mask.any() and np.any((a[:, :, 0] > 0) & (a[:, :, 0] < 1))
    assert np.all(a[:, :, 1][mask] > 0.99)
    assert np.max(np.abs(a[:, :, 2][mask] - strand_seed(20, 7))) < 1 / 255 + 1e-6
    assert np.max(np.abs(c[:, :, :3][mask] - (0.5, 1, 0.5))) < 1 / 255 + 1e-6
    assert c[:, :, 3][mask].min() < 0.01 and c[:, :, 3][mask].max() > 0.99
    assert np.all(a[:3, :, 0] == 0) and np.all(a[:, :3, 0] == 0)
    assert all(image.packed_file and image.alpha_mode == 'CHANNEL_PACKED' for image in images)
    assert strand_seed(20, 7) != strand_seed(10, 7) != strand_seed(10, 8)
    # Normal native image save/load preserves alpha as root data, not opacity.
    for image in images:
        image.filepath_raw = str(ARTIFACTS / (image.name.replace(' ', '_') + '.png'))
        image.save()
        loaded = bpy.data.images.load(image.filepath_raw, check_existing=False)
        loaded.colorspace_settings.name = 'Non-Color'
        loaded.alpha_mode = 'CHANNEL_PACKED'
        assert np.max(np.abs(pixels(image) - pixels(loaded))) <= 1 / 255 + 1e-6
        bpy.data.images.remove(loaded)
    for image in images:
        bpy.data.images.remove(image)
    bpy.data.meshes.remove(mesh)
    try:
        pack((ribbon,) * 100, 64)
    except HairballError as exc:
        assert '100 cards' in str(exc) and '16-card packing ceiling' in str(exc)
    else:
        raise AssertionError('Expected atlas capacity error')
    assert len(pack((ribbon,) * 16, 64)) == 16


def export_basis_test(output):
    # The normal/UV/tangent basis used to bake must be the basis ordinary glTF writes.
    bpy.ops.object.select_all(action='DESELECT')
    output.select_set(True)
    output.parent.select_set(True)
    bpy.context.view_layer.objects.active = output
    path = ARTIFACTS / 'atlas.glb'
    bpy.ops.export_scene.gltf(filepath=str(path), export_format='GLB', use_selection=True,
                             export_tangents=True, export_normals=True, export_materials='NONE')
    raw = path.read_bytes()
    length = struct.unpack_from('<I', raw, 12)[0]
    document = json.loads(raw[20:20+length])
    binary_start = 20 + length + 8
    primitive = document['meshes'][0]['primitives'][0]
    def accessor(index):
        item = document['accessors'][index]
        view = document['bufferViews'][item['bufferView']]
        components = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}[item['type']]
        dtype = {5126: '<f4', 5125: '<u4', 5123: '<u2', 5121: 'u1'}[item['componentType']]
        start = binary_start + view.get('byteOffset', 0) + item.get('byteOffset', 0)
        assert 'byteStride' not in view
        return np.frombuffer(raw, dtype=dtype, count=item['count']*components, offset=start).reshape(-1, components)
    attrs = primitive['attributes']
    assert {'NORMAL', 'TANGENT', 'TEXCOORD_0', 'JOINTS_0', 'WEIGHTS_0'} <= set(attrs)
    assert len(primitive['targets']) == 2
    tangent, normal, uv = [accessor(attrs[key]) for key in ('TANGENT', 'NORMAL', 'TEXCOORD_0')]
    indices = accessor(primitive['indices']).ravel()
    mesh = output.data
    mesh.calc_tangents(uvmap='UVMap')
    for polygon in mesh.polygons:
        # Find by UV triangle, not by exporter vertex order (it duplicates corners).
        source_uv = np.array([mesh.uv_layers.active.data[i].uv for i in polygon.loop_indices])
        candidates = []
        for triangle in indices.reshape(-1, 3):
            target_uv = uv[triangle].copy()
            target_uv[:, 1] = 1-target_uv[:, 1]  # Blender exporter flips UV V.
            if all(np.min(np.linalg.norm(target_uv-point, axis=1)) < 1e-6 for point in source_uv):
                candidates.append(triangle)
        assert len(candidates) == 1
        loop = mesh.loops[polygon.loop_start]
        t, n = Vector(loop.tangent), Vector(loop.normal)
        # Blender +Z→glTF +Y, +Y→-Z is a handedness-preserving rotation.
        expected_t, expected_n = np.array((t.x, t.z, -t.y)), np.array((n.x, n.z, -n.y))
        index = candidates[0][0]
        assert np.dot(tangent[index, :3], expected_t) > 0.9999
        assert np.dot(normal[index], expected_n) > 0.9999
        # Blender's glTF exporter preserves the basis sign despite its UV-origin
        # conversion; data directions must NOT receive an extra green-channel flip.
        assert tangent[index, 3] == loop.bitangent_sign


def counts():
    return tuple(len(getattr(bpy.data, key)) for key in (
        'objects', 'meshes', 'collections', 'materials', 'images', 'node_groups', 'shape_keys'))


def main():
    channels_test()
    hairball.register()
    surface, groom, rig = fixture()
    settings = bpy.context.scene.hairball
    settings.atlas_size = 256
    settings.card_width = 0.004
    original = tuple(tuple(p.vector) for p in groom.data.position_data)
    groom.name = 'Pubic Hair Guides Interpolated'
    result, report = generate_geometry(groom, settings, textured=True)
    assert result.name == 'Pubic Hair Cards'
    collection = result.users_collection[0]
    assert collection.name == 'Pubic Hair v001'
    assert collection in groom.users_collection[0].children[:]
    assert collection not in bpy.context.scene.collection.children[:]
    assert report['cards'] == 2 and report['version'] == 1
    assert result['hairball_kind'] == 'HAIR_CARDS'
    assert all(len(face.vertices) == 3 for face in result.data.polygons)
    assert tuple(tuple(p.vector) for p in groom.data.position_data) == original
    assert result.parent == rig and len(result.data.shape_keys.key_blocks) == 3
    images = [result['hairball_attributes'], result['hairball_coordinates']]
    original_pixels = [pixels(image) for image in images]
    metadata = json.loads(result['hairball_cards'])
    for card in metadata:
        x, y, w, h = card['atlas_tile']
        assert np.any(original_pixels[0][y:y+h, x:x+w, 0] > 0)
    newer, newer_report = generate_geometry(groom, settings, textured=True)
    assert newer_report['version'] == 2 and newer.data != result.data
    assert newer['hairball_attributes'] != images[0]
    assert np.array_equal(pixels(newer['hairball_attributes']), original_pixels[0])
    assert np.array_equal(pixels(images[0]), original_pixels[0])
    export_basis_test(result)
    settings.atlas_size = 2048
    full_size, full_report = generate_geometry(groom, settings, textured=True)
    assert tuple(full_size['hairball_attributes'].size) == (2048, 2048)
    assert full_size['hairball_coordinates'].packed_file
    print('HAIRBALL_DEFAULT_ATLAS', json.dumps(full_report))
    settings.atlas_size = 256
    # Radius scale multiplies baked coverage thickness only: geometry and the
    # groom's own radius attribute must stay untouched.
    radius_attribute = groom.data.attributes['radius']
    groom_radii = np.empty(len(radius_attribute.data), dtype=np.float32)
    radius_attribute.data.foreach_get('value', groom_radii)
    base = generate_geometry(groom, settings, textured=True)[0]
    base_mean = float(pixels(base['hairball_attributes'])[:, :, 0].mean())
    settings.radius_scale = 2.0
    thick = generate_geometry(groom, settings, textured=True)[0]
    thick_mean = float(pixels(thick['hairball_attributes'])[:, :, 0].mean())
    settings.radius_scale = 1.0
    assert len(thick.data.vertices) == len(base.data.vertices)
    # Widened cards grow with scaled radius, so coverage grows sublinearly.
    assert 1.1 < thick_mean / max(base_mean, 1e-6) < 3.0, (base_mean, thick_mean)
    assert '"radius_scale": 2.0' in thick['hairball_settings']
    after = np.empty(len(radius_attribute.data), dtype=np.float32)
    radius_attribute.data.foreach_get('value', after)
    assert np.array_equal(groom_radii, after)
    from hairball.materials import preview_material
    for diagnostic in ('COVERAGE', 'DEPTH', 'SEED', 'DIRECTION', 'ROOT_TIP'):
        material = preview_material('Diagnostic test', *images, diagnostic=diagnostic)
        assert material.node_tree.nodes.get('Emission')
        bpy.data.materials.remove(material)
    # Failure after both images exist must remove all owned output and no old data.
    from hairball import geometry
    original_material = geometry.preview_material
    def fail(*args, **kwargs):
        raise HairballError('injected material failure')
    geometry.preview_material = fail
    before = counts()
    try:
        generate_geometry(groom, settings, textured=True)
    except HairballError:
        pass
    else:
        raise AssertionError('Expected injected failure')
    finally:
        geometry.preview_material = original_material
    assert counts() == before, (counts(), before)
    from hairball import baking
    original_image = baking._image
    calls = 0
    def fail_second_image(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise HairballError('injected second image failure')
        return original_image(*args)
    baking._image = fail_second_image
    before = counts()
    try:
        generate_geometry(groom, settings, textured=True)
    except HairballError:
        pass
    else:
        raise AssertionError('Expected injected image failure')
    finally:
        baking._image = original_image
    assert counts() == before
    bpy.ops.object.select_all(action='DESELECT')
    groom.select_set(True)
    bpy.context.view_layer.objects.active = groom
    bpy.ops.ed.undo_push(message='Before textured generation')
    assert bpy.ops.hairball.generate_cards() == {'FINISHED'}
    output = bpy.context.object
    name = output.name
    image_names = [output[key].name for key in ('hairball_attributes', 'hairball_coordinates')]
    saved_pixels = [pixels(bpy.data.images[n]) for n in image_names]
    bpy.ops.ed.undo_push(message='After textured generation')
    assert bpy.ops.ed.undo() == {'FINISHED'}
    assert bpy.data.objects.get(name) is None
    assert all(bpy.data.images.get(n) is None for n in image_names)
    assert bpy.ops.ed.redo() == {'FINISHED'}
    output = bpy.data.objects[name]
    for n, values in zip(image_names, saved_pixels):
        assert np.array_equal(pixels(bpy.data.images[n]), values), 'Redo lost packed image pixels'
    # Presentation is fixture-only, never part of generation.
    for collection in bpy.data.collections:
        if collection.get('hairball_kind') in {'HAIR_CARDS', 'GEOMETRY_PREVIEW'}:
            collection.hide_render = collection not in tuple(output.users_collection)
            collection.hide_viewport = collection.hide_render
    output['hairball_groom'].hide_render = True
    output['hairball_groom'].data.surface.hide_render = True
    bpy.data.objects['Cube'].hide_render = True
    target = Vector((2, -0.9, 0.3))
    camera = bpy.context.scene.camera
    camera.location = target + Vector((3, -4, 2))
    camera.rotation_euler = (target-camera.location).to_track_quat('-Z', 'Y').to_euler()
    camera.data.type = 'ORTHO'
    camera.data.ortho_scale = 3
    light = bpy.data.objects['Light']
    light.location, light.rotation_euler = camera.location, camera.rotation_euler
    light.data.type, light.data.energy, light.data.size = 'AREA', 700, 3
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x, scene.render.resolution_y = 512, 256
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.render.filepath = str(ARTIFACTS / 'atlas.png')
    bpy.ops.render.render(write_still=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(ARTIFACTS / 'atlas.blend'))
    bpy.ops.wm.open_mainfile(filepath=str(ARTIFACTS / 'atlas.blend'))
    output = bpy.data.objects[name]
    for n, values in zip(image_names, saved_pixels):
        assert np.array_equal(pixels(bpy.data.images[n]), values), 'Reopen lost image pixels'
    assert output['hairball_attributes'].packed_file
    assert output.data.shape_keys.key_blocks['Left lift'].driver_add('value').driver.variables[0].targets[0].id
    print('HAIRBALL_ATLAS_TESTS=PASS', json.dumps(report))


if __name__ == '__main__':
    main()
