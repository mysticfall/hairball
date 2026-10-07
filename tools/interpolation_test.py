"""Isolated native interpolation, density-mask, cleanup and persistence gates."""
from pathlib import Path
import sys
import bpy
from mathutils import Vector

assert bpy.app.background and not bpy.data.filepath
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import hairball
from cards_test import fixture
from hairball.evaluation import HairballError, rest_strands, evaluated_strands
from hairball.native import prepare_interpolation, is_interpolation
from hairball.geometry import generate_geometry


def counts(surface):
    return (len(bpy.data.objects), len(bpy.data.hair_curves), len(bpy.data.node_groups), len(surface.data.attributes))


def rejected(call, message):
    try:
        call()
    except HairballError as exc:
        assert message in str(exc), str(exc)
    else:
        raise AssertionError('Expected rejection: ' + message)


def main():
    hairball.register()
    surface, source, rig = fixture()
    # Four original faces let us test a real persistent left-half density mask.
    bpy.ops.object.select_all(action='DESELECT')
    surface.select_set(True)
    bpy.context.view_layer.objects.active = surface
    surface.active_shape_key_index = 0
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.subdivide(number_cuts=1)
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.context.view_layer.update()
    settings = bpy.context.scene.hairball
    settings.interpolation_density = 30
    settings.interpolation_distance = 5
    settings.max_segments = 256
    settings.atlas_size = 1024
    settings.card_width = .004
    # The attachment UV map, not whichever map happens to be active, governs setup.
    unrelated = surface.data.uv_layers.new(name='Unrelated degenerate UV')
    for item in unrelated.data: item.uv = (0,0)
    surface.data.uv_layers.active = unrelated
    source_graph = source.modifiers[0].node_group
    before = (tuple(tuple(p.vector) for p in source.data.position_data),
              tuple(k.value for k in surface.data.shape_keys.key_blocks),
              tuple(tuple(b.location) for b in rig.pose.bones), len(source_graph.nodes))
    groom, count = prepare_interpolation(source, settings)
    assert count > 4 and groom.data != source.data and groom.modifiers[0].node_group != source_graph
    mask_name = groom['hairball_density_attribute']
    assert all(v.value == 1 for v in surface.data.attributes[mask_name].data)
    active_rest = rest_strands(groom, resample=True)
    final = evaluated_strands(groom)
    assert {s.identifier for s in final} == {s.identifier for s in active_rest}
    assert any((Vector(s.points[0])-Vector(t.points[0])).length > 1e-4 for s,t in zip(active_rest,final))
    for key in surface.data.shape_keys.key_blocks: key.value = 0
    for bone in rig.pose.bones: bone.location = (0,0,0)
    bpy.context.view_layer.update()
    neutral = rest_strands(groom, resample=True)
    assert [s.identifier for s in active_rest] == [s.identifier for s in neutral]
    assert all((Vector(p)-Vector(q)).length < 1e-6 for a,b in zip(active_rest,neutral) for p,q in zip(a.points,b.points))
    for k,v in zip(surface.data.shape_keys.key_blocks, before[1]): k.value = v
    for b,v in zip(rig.pose.bones, before[2]): b.location = v
    bpy.context.view_layer.update()
    cards, report = generate_geometry(groom, settings, textured=True)
    assert report['strands'] == count and cards['hairball_attributes'].packed_file
    assert before == (tuple(tuple(p.vector) for p in source.data.position_data),
                      tuple(k.value for k in surface.data.shape_keys.key_blocks),
                      tuple(tuple(b.location) for b in rig.pose.bones), len(source_graph.nodes))
    # A persistent face mask restricts generated roots, not the native sculpt brush.
    source['hairball_growth_region'] = 'SELECTED_FACES'
    left_faces = [p.index for p in surface.data.polygons if p.center.x < 0]
    source['hairball_growth_faces'] = left_faces
    selected, selected_count = prepare_interpolation(source, settings)
    mask = surface.data.attributes[selected['hairball_density_attribute']]
    assert [v.value for v in mask.data] == [int(p.index in left_faces) for p in surface.data.polygons]
    selected_rest = rest_strands(selected)
    assert selected_count > 0 and selected_count < count
    assert all(s.points[0][0] <= 1e-5 for s in selected_rest)
    subdiv = surface.modifiers.new('Interpolation audit subdivision', 'SUBSURF')
    subdiv.levels = 1
    bpy.context.view_layer.update()
    subdiv_rest = rest_strands(selected, resample=True)
    for key in surface.data.shape_keys.key_blocks: key.value = 0
    for bone in rig.pose.bones: bone.location = (0,0,0)
    bpy.context.view_layer.update()
    subdiv_neutral = rest_strands(selected, resample=True)
    assert [s.identifier for s in subdiv_rest] == [s.identifier for s in subdiv_neutral]
    assert all((Vector(p)-Vector(q)).length < 1e-6 for a,b in zip(subdiv_rest,subdiv_neutral)
               for p,q in zip(a.points,b.points))
    for k,v in zip(surface.data.shape_keys.key_blocks, before[1]): k.value = v
    for b,v in zip(rig.pose.bones, before[2]): b.location = v
    surface.modifiers.remove(subdiv)
    bpy.context.view_layer.update()
    # Native controls and actual contents are checked before allocating clones.
    node = next(n for n in groom.modifiers[0].node_group.nodes if is_interpolation(n))
    state = counts(surface)
    node.inputs['Resting Surface'].default_value = False
    rejected(lambda: rest_strands(groom), 'Resting Surface')
    assert counts(surface) == state
    node.inputs['Resting Surface'].default_value = True
    node.inputs['Viewport Amount'].default_value = .5
    rejected(lambda: rest_strands(groom), 'Viewport Amount')
    node.inputs['Viewport Amount'].default_value = 1
    dependency = node.node_tree.nodes.get('Get Hair Surface Geometry').node_tree
    bad = dependency.nodes.new('GeometryNodeObjectInfo')
    rejected(lambda: rest_strands(groom), 'contents differ')
    dependency.nodes.remove(bad)
    # Failure after append/mask/data allocation cleans every owned dependency.
    from hairball import evaluation
    original = evaluation.rest_strands
    evaluation.rest_strands = lambda *a,**k: (_ for _ in ()).throw(HairballError('injected'))
    state = counts(surface)
    rejected(lambda: prepare_interpolation(source,settings), 'injected')
    assert state == counts(surface), (state,counts(surface))
    evaluation.rest_strands = original
    # UV ambiguity against excluded faces rejects before allocating anything.
    uv = surface.data.uv_layers['UVMap'].data
    values = [tuple(v.uv) for v in uv]
    for p in surface.data.polygons:
        if p.index not in left_faces:
            for index in p.loop_indices:
                uv[index].uv.x -= .5
    state = counts(surface)
    rejected(lambda: prepare_interpolation(source,settings), 'overlap')
    assert counts(surface) == state
    for item,value in zip(uv,values): item.uv = value
    # Also clean a no-strands setup; reject an oversized setup before append.
    state = counts(surface)
    settings.interpolation_density = .01
    rejected(lambda: prepare_interpolation(source,settings), 'no strands')
    assert counts(surface) == state
    settings.interpolation_density = 1000000
    rejected(lambda: prepare_interpolation(source,settings), '100,000')
    assert counts(surface) == state
    settings.interpolation_density = 30
    # UI undo/redo restores the native graph AND newly allocated surface mask.
    bpy.ops.ed.undo_push(message='Before interpolation')
    for obj in bpy.context.selected_objects: obj.select_set(False)
    source.select_set(True)
    bpy.context.view_layer.objects.active = source
    state = counts(surface)
    assert bpy.ops.hairball.prepare_interpolation() == {'FINISHED'}
    created = bpy.context.object
    name, created_mask = created.name, created['hairball_density_attribute']
    bpy.ops.ed.undo_push(message='After interpolation')
    bpy.ops.ed.undo()
    surface = bpy.data.objects['Card test surface']
    assert name not in bpy.data.objects and created_mask not in surface.data.attributes
    assert state == counts(surface)
    bpy.ops.ed.redo()
    created = bpy.data.objects[name]
    assert len(rest_strands(created)) == selected_count
    bpy.ops.wm.save_as_mainfile(filepath='/tmp/opencode/hairball-tests/interpolation.blend')
    bpy.ops.wm.open_mainfile(filepath='/tmp/opencode/hairball-tests/interpolation.blend')
    created = bpy.data.objects[name]
    assert len(rest_strands(created)) == selected_count
    print('HAIRBALL_INTERPOLATION_TESTS=PASS', report, 'selected', selected_count)


if __name__ == '__main__':
    main()
