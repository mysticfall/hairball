"""Explicit sidebar edits preserve guides, other grooms and prior card results."""
from pathlib import Path
import sys
import bpy

assert bpy.app.background and not bpy.data.filepath
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import hairball
from cards_test import fixture
from hairball import evaluation
from hairball.evaluation import HairballError, rest_strands
from hairball.native import prepare_interpolation, interpolation_settings, update_interpolation
from hairball.geometry import generate_geometry


def main():
    hairball.register()
    surface, source, rig = fixture()
    settings = bpy.context.scene.hairball
    settings.atlas_size = 256
    settings.card_width = .01
    cards, _ = generate_geometry(source, settings, textured=True)
    vertices = tuple(tuple(v.co) for v in cards.data.vertices)
    pixels = tuple(cards['hairball_coordinates'].pixels)
    settings.interpolation_density = 30
    settings.interpolation_distance = 5
    groom, count = prepare_interpolation(source, settings)
    positions = tuple(tuple(p.vector) for p in groom.data.position_data)
    mask = tuple(v.value for v in surface.data.attributes[groom['hairball_density_attribute']].data)
    original_graph = groom.modifiers[0].node_group
    # Simulate another groom sharing its graph. Applying must make a local copy.
    other = groom.copy()
    bpy.context.collection.objects.link(other)
    assert other.modifiers[0].node_group == original_graph
    bpy.ops.object.select_all(action='DESELECT')
    groom.select_set(True)
    bpy.context.view_layer.objects.active = groom
    settings.interpolation_density = 999
    assert bpy.ops.hairball.load_interpolation() == {'FINISHED'}
    assert settings.interpolation_density == 30
    settings.interpolation_density = 15
    settings.interpolation_distance = 4
    settings.interpolation_guides = 2
    assert bpy.ops.hairball.update_interpolation() == {'FINISHED'}
    assert len(rest_strands(groom)) < count
    assert interpolation_settings(groom)['interpolation_density'] == 15
    assert interpolation_settings(groom)['interpolation_distance'] == 4
    assert interpolation_settings(groom)['interpolation_guides'] == 2
    assert interpolation_settings(other)['interpolation_density'] == 30
    assert positions == tuple(tuple(p.vector) for p in groom.data.position_data)
    assert mask == tuple(v.value for v in surface.data.attributes[groom['hairball_density_attribute']].data)
    assert vertices == tuple(tuple(v.co) for v in cards.data.vertices)
    assert pixels == tuple(cards['hairball_coordinates'].pixels)
    graph = groom.modifiers[0].node_group
    groups = len(bpy.data.node_groups)
    original = evaluation.rest_strands
    evaluation.rest_strands = lambda *a,**k: (_ for _ in ()).throw(HairballError('injected'))
    try:
        update_interpolation(groom, settings)
    except HairballError as exc:
        assert 'injected' in str(exc)
    else:
        raise AssertionError('Expected rollback')
    finally:
        evaluation.rest_strands = original
    assert groom.modifiers[0].node_group == graph and len(bpy.data.node_groups) == groups
    for density in (.01, 1000000):
        settings.interpolation_density = density
        try:
            update_interpolation(groom, settings)
        except HairballError:
            pass
        else:
            raise AssertionError('Expected empty/oversized update rejection')
        assert groom.modifiers[0].node_group == graph and len(bpy.data.node_groups) == groups
    settings.interpolation_density = 15
    bpy.ops.ed.undo_push(message='Before density apply')
    settings.interpolation_density = 10
    assert bpy.ops.hairball.update_interpolation() == {'FINISHED'}
    name = groom.name
    bpy.ops.ed.undo_push(message='After density apply')
    bpy.ops.ed.undo()
    assert interpolation_settings(bpy.data.objects[name])['interpolation_density'] == 15
    bpy.ops.ed.redo()
    assert interpolation_settings(bpy.data.objects[name])['interpolation_density'] == 10
    bpy.ops.wm.save_as_mainfile(filepath='/tmp/opencode/hairball-tests/interpolation-controls.blend')
    bpy.ops.wm.open_mainfile(filepath='/tmp/opencode/hairball-tests/interpolation-controls.blend')
    assert interpolation_settings(bpy.data.objects[name])['interpolation_density'] == 10
    print('HAIRBALL_INTERPOLATION_CONTROLS_TESTS=PASS')


if __name__ == '__main__':
    main()
