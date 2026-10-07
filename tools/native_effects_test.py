"""Native local asset group audit and explanatory tooltips; isolated only."""
from pathlib import Path
import sys

import bpy
from mathutils import Vector

assert bpy.app.background and not bpy.data.filepath, 'Use factory startup.'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import hairball
from hairball.evaluation import HairballError, rest_strands, evaluated_strands
from hairball.geometry import generate_geometry
from cards_test import fixture


def main():
    hairball.register()
    for key in hairball.model.HairballSettings.__annotations__:
        prop = hairball.model.HairballSettings.bl_rna.properties[key]
        assert len(prop.description) >= 40, (key, prop.description)
    surface, groom, rig = fixture()
    base = rest_strands(groom, resample=True)
    path = Path(bpy.utils.system_resource('DATAFILES', path='assets')) / 'nodes/procedural_hair_node_assets.blend'
    with bpy.data.libraries.load(str(path), link=False) as (source, target):
        target.node_groups = ['Clump Hair Curves', 'Frizz Hair Curves']
    graph = groom.modifiers[0].node_group
    deformer = next(n for n in graph.nodes if n.bl_idname == 'GeometryNodeDeformCurvesOnSurface')
    upstream = deformer.inputs['Curves'].links[0].from_socket
    for group in target.node_groups:
        node = graph.nodes.new('GeometryNodeGroup')
        node.node_tree = group
        if group.name.startswith('Frizz'):
            node.inputs['Distance'].default_value = 0.0005
        if group.name.startswith('Clump'):
            node.inputs['Factor'].default_value = 0.15
        graph.links.new(upstream, node.inputs['Geometry'])
        upstream = node.outputs['Geometry']
    graph.links.new(upstream, deformer.inputs['Curves'])
    bpy.context.view_layer.update()
    nodes_before = tuple((node.name, node.node_tree if node.type == 'GROUP' else None) for node in graph.nodes)
    values_before = tuple(k.value for k in surface.data.shape_keys.key_blocks)
    positions_before = tuple(tuple(p.vector) for p in groom.data.position_data)
    poses_before = tuple(tuple(b.location) for b in rig.pose.bones)
    rest = rest_strands(groom, resample=True)
    final = evaluated_strands(groom)
    assert len(rest) == len(final) == len(base) == 4
    assert any((Vector(a.points[-1])-Vector(b.points[-1])).length > 1e-7 for a,b in zip(base,rest))
    # The audited effect stack is invariant to source key/pose values in rest evaluation.
    for key in surface.data.shape_keys.key_blocks:
        key.value = 0
    for bone in rig.pose.bones:
        bone.location = (0,0,0)
    bpy.context.view_layer.update()
    neutral = rest_strands(groom, resample=True)
    for a,b in zip(rest,neutral):
        assert len(a.points) == len(b.points)
        assert all((Vector(p)-Vector(q)).length < 1e-6 for p,q in zip(a.points,b.points))
    for key,value in zip(surface.data.shape_keys.key_blocks,values_before):
        key.value = value
    for bone,pose in zip(rig.pose.bones,poses_before):
        bone.location = pose
    bpy.context.view_layer.update()
    settings = bpy.context.scene.hairball
    settings.atlas_size = 256
    settings.max_segments = 256
    settings.card_width = 0.01
    result, report = generate_geometry(groom, settings, textured=True)
    assert result['hairball_attributes'].packed_file
    assert tuple((n.name,n.node_tree if n.type == 'GROUP' else None) for n in graph.nodes) == nodes_before
    assert tuple(tuple(p.vector) for p in groom.data.position_data) == positions_before
    assert tuple(k.value for k in surface.data.shape_keys.key_blocks) == values_before
    assert tuple(tuple(b.location) for b in rig.pose.bones) == poses_before
    # Sneak an unsafe node into a native-named dependency: reject actual contents.
    dependency = target.node_groups[1]
    bad = dependency.nodes.new('GeometryNodeObjectInfo')
    count = len(bpy.data.objects), len(bpy.data.node_groups)
    try:
        rest_strands(groom)
    except HairballError as exc:
        assert 'not yet audited' in str(exc)
    else:
        raise AssertionError('Unsafe nested graph was accepted')
    assert count == (len(bpy.data.objects),len(bpy.data.node_groups))
    dependency.nodes.remove(bad)
    bpy.ops.wm.save_as_mainfile(filepath='/tmp/opencode/hairball-tests/native-effects.blend')
    print('HAIRBALL_NATIVE_EFFECTS_TESTS=PASS', report)


if __name__ == '__main__':
    main()
