"""Clustering, adaptive fitting and versioned geometry integration, isolated only."""
from pathlib import Path
from types import SimpleNamespace
import json
import math
import sys

import bpy
from mathutils import Vector

assert bpy.app.background and not bpy.data.filepath, "Use an isolated factory-startup process."
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hairball
from hairball.cards import _arc_samples, fit_adaptive, fit_bundles, ribbon_geometry
from hairball.clustering import Bundle, cluster_strands
from hairball.evaluation import HairballError, Strand, rest_strands
from hairball.geometry import generate_geometry
from hairball.groom import create_groom

ARTIFACTS = Path("/tmp/opencode/hairball-tests")
ARTIFACTS.mkdir(parents=True, exist_ok=True)


def strand(identifier, points):
    return Strand(identifier, tuple(tuple(p) for p in points), tuple(0.0005 for _ in points))


def math_tests():
    a = strand(10, [(0, 0, 0), (0, 0, 0.1)])
    b = strand(20, [(0.001, 0, 0), (0.001, 0, 0.1)])
    c = strand(30, [(0.002, 0, 0), (0.002, 0, 0.1)])
    groups = cluster_strands((c, a, b), (1, 0, 0))
    assert [(g.anchor, [s.identifier for s in g.strands]) for g in groups] == [(0, [10, 20]), (1, [30])]
    assert cluster_strands((a, b, c), (0, 0, 1)) == groups
    assert len(cluster_strands((a, b), (0, 0), max_strands=1)) == 2
    down = strand(40, [(0, 0, 0), (0, 0, -0.1)])
    assert len(cluster_strands((a, down), (0, 0), shape_distance=1)) == 2
    bent = strand(50, [(0, 0, 0), (0, 0, 0.02), (0.04, 0, 0.1)])
    assert len(cluster_strands((a, bent), (0, 0))) == 2
    chain = tuple(strand(i, [(x, 0, 0), (x, 0, 0.1)]) for i, x in enumerate((0, 0.009, 0.018)))
    assert len(cluster_strands(chain, (0, 0, 0))) == 2  # No transitive root-distance drift.
    straight = fit_adaptive((a,), 0)
    assert len(straight.centers) == 2
    helix = strand(60, [(0.025 * math.sin(4 * math.pi * i / 128),
                         0.025 * (1 - math.cos(4 * math.pi * i / 128)), 0.08 * i / 128)
                        for i in range(129)])
    coarse = fit_adaptive((helix,), 0, fit_error=0.002)
    fine = fit_adaptive((helix,), 0, fit_error=0.0002, max_segments=128)
    assert len(fine.centers) >= len(coarse.centers) > len(straight.centers)
    probes = tuple(i / 1000 for i in range(1001))
    original = _arc_samples(helix.points, probes)
    # Ribbon row coordinates are source arc parameters, not necessarily the
    # fitted centerline's new arc lengths. Interpolate explicitly in that space.
    from bisect import bisect_right
    for t, point in zip(probes, original):
        index = min(bisect_right(fine.parameters, t) - 1, len(fine.parameters) - 2)
        blend = (t - fine.parameters[index]) / (fine.parameters[index + 1] - fine.parameters[index])
        fitted = Vector(fine.centers[index]).lerp(Vector(fine.centers[index + 1]), blend)
        assert (point - fitted).length <= 0.0002001
    for side in fine.sides:
        assert abs(Vector(side).length - 1) < 1e-5 and all(math.isfinite(v) for v in side)
    vertices, faces, uvs = ribbon_geometry(fine)
    assert len(vertices) == 2 * len(fine.centers) and len(faces) == len(fine.centers) - 1
    assert uvs[0] == (0, 0) and uvs[-1] == (1, 1)
    try:
        fit_adaptive((helix,), 0, max_segments=1)
    except HairballError as exc:
        assert "detail limit" in str(exc)
    else:
        raise AssertionError("Detail limits must not silently degrade a curl")
    opposite = strand(61, [(-x, -y, z) for x, y, z in helix.points])
    split = fit_bundles((Bundle(3, (helix, opposite)),), max_segments=128)
    assert len(split) == 2 and all(r.anchor == 3 for r in split)


def fixture():
    mesh = bpy.data.meshes.new("Card test surface")
    mesh.from_pydata([(-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0)], [], [(0, 1, 2, 3)])
    uv = mesh.uv_layers.new(name="UVMap")
    for loop, item in zip(mesh.loops, uv.data):
        co = mesh.vertices[loop.vertex_index].co
        item.uv = ((co.x + 1) / 2, (co.y + 1) / 2)
    surface = bpy.data.objects.new("Card test surface", mesh)
    bpy.context.collection.objects.link(surface)
    surface.location = (2, 0, 0)
    rig_data = bpy.data.armatures.new("Card test rig")
    rig = bpy.data.objects.new("Card test rig", rig_data)
    bpy.context.collection.objects.link(rig)
    rig.location = surface.location
    bpy.ops.object.select_all(action="DESELECT")
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    for name, x in (("Left", -1), ("Right", 1)):
        bone = rig_data.edit_bones.new(name)
        bone.head, bone.tail = (x, 0, 0), (x, 0, 1)
    bpy.ops.object.mode_set(mode="OBJECT")
    surface.vertex_groups.new(name="Left").add([0, 3], 1, "REPLACE")
    surface.vertex_groups.new(name="Right").add([1, 2], 1, "REPLACE")
    armature = surface.modifiers.new("Armature", "ARMATURE")
    armature.object = rig
    basis = surface.shape_key_add(name="Basis", from_mix=False)
    for name, indices, delta in (("Left lift", (0, 3), 0.1), ("Right lift", (1, 2), 0.2)):
        key = surface.shape_key_add(name=name, from_mix=False)
        for i, point in enumerate(key.data):
            point.co = basis.data[i].co + Vector((0, 0, delta if i in indices else 0))
        key.value = 0.5
    rig.pose.bones["Left"].location.x = 0.1
    rig.pose.bones["Right"].location.x = -0.1
    bpy.context.view_layer.update()
    groom = create_groom(surface, count=4, points=65)
    groom.data.set_types(type="POLY")
    positions, root_uvs = [], []
    for curve in range(4):
        root = Vector((-0.9 if curve < 2 else 0.9, -0.9 + 0.002 * (curve % 2), 0))
        root_uvs.extend(((root.x + 1) / 2, (root.y + 1) / 2))
        for i in range(65):
            t = i / 64
            offset = (Vector((0.07 * math.sin(2 * math.pi * t), 0.03 * math.sin(math.pi * t), 0.6 * t))
                      if curve < 2 else Vector((0.025 * math.sin(4 * math.pi * t),
                                                0.025 * (1 - math.cos(4 * math.pi * t)), 0.08 * t)))
            positions.extend(root + offset)
    groom.data.position_data.foreach_set("vector", positions)
    groom.data.attributes["surface_uv_coordinate"].data.foreach_set("vector", root_uvs)
    groom.data.attributes["radius"].data.foreach_set("value", [0.0005] * (65 * 4))
    groom.data.update_tag()
    bpy.context.view_layer.update()
    return surface, groom, rig


def counts():
    return tuple(len(getattr(bpy.data, name)) for name in (
        "objects", "meshes", "materials", "collections", "node_groups", "shape_keys"))


def main():
    math_tests()
    hairball.register()
    surface, groom, rig = fixture()
    source_values = [key.value for key in surface.data.shape_keys.key_blocks]
    source_pose = [tuple(bone.location) for bone in rig.pose.bones]
    original = tuple(tuple(p.vector) for p in groom.data.position_data)
    settings = bpy.context.scene.hairball
    settings.card_width = 0.01  # Wider opaque ribbons for the diagnostic fixture.
    result, report = generate_geometry(groom, settings)
    assert report["cards"] == 2, report
    assert report["triangles"] > 4 and report["version"] == 1
    assert {v.value for v in result.data.attributes["hairball_anchor"].data} == {0, 1}
    assert set(group.name for group in result.vertex_groups) == {"Left", "Right"}
    assert result.parent == rig
    assert [key.value for key in surface.data.shape_keys.key_blocks] == source_values
    assert [tuple(bone.location) for bone in rig.pose.bones] == source_pose
    assert tuple(tuple(p.vector) for p in groom.data.position_data) == original
    # A native non-poly spline must be sampled along its evaluated path, not
    # mistaken for a polygon joining its few control points.
    groom.data.set_types(type="CATMULL_ROM")
    assert len(rest_strands(groom, resample=True)[0].points) > 65
    groom.data.set_types(type="POLY")
    bpy.context.view_layer.update()
    # Regeneration cannot overwrite old manual edits, including after renaming
    # the source; version lookup uses an ID reference, not just its old name.
    result.data.vertices[0].co.x += 0.123
    before_vertex = result.data.vertices[0].co.copy()
    groom.name = "Card preview groom"
    newer, newer_report = generate_geometry(groom, settings)
    assert newer != result and newer.data != result.data and newer_report["version"] == 2
    assert result.data.vertices[0].co == before_vertex
    assert newer.data.materials[0] != result.data.materials[0]
    # A failed transfer after output allocation must remove only owned data.
    from hairball import geometry
    original_transfer = geometry.transfer
    def fail_transfer(surface, target, anchors):
        target.shape_key_add(name="Basis")
        raise HairballError("injected transfer failure")
    geometry.transfer = fail_transfer
    before = counts()
    try:
        generate_geometry(groom, settings)
    except HairballError as exc:
        assert "injected" in str(exc)
    else:
        raise AssertionError("Expected injected failure")
    finally:
        geometry.transfer = original_transfer
    assert counts() == before, (counts(), before)
    bpy.ops.object.select_all(action="DESELECT")
    groom.select_set(True)
    bpy.context.view_layer.objects.active = groom
    assert bpy.ops.hairball.generate_geometry() == {"FINISHED"}
    output = bpy.context.object
    assert json.loads(output["hairball_report"])["version"] == 3
    assert output["hairball_groom"] == groom
    # Native memfile undo/redo can remove and restore independent results.
    bpy.ops.ed.undo_push(message="Before another geometry preview")
    bpy.ops.object.select_all(action="DESELECT")
    groom.select_set(True)
    bpy.context.view_layer.objects.active = groom
    assert bpy.ops.hairball.generate_geometry() == {"FINISHED"}
    last_name = bpy.context.object.name
    bpy.ops.ed.undo_push(message="After another geometry preview")
    assert bpy.ops.ed.undo() == {"FINISHED"}
    assert bpy.data.objects.get(last_name) is None
    assert bpy.ops.ed.redo() == {"FINISHED"}
    output = bpy.data.objects[last_name]
    # Fixture presentation only: the generator itself never hides old results.
    for collection in bpy.data.collections:
        if collection.get("hairball_kind") == "GEOMETRY_PREVIEW":
            collection.hide_viewport = collection not in tuple(output.users_collection)
            collection.hide_render = collection.hide_viewport
    source = output["hairball_groom"]
    source.hide_render = True
    source.data.surface.hide_render = True
    bpy.data.objects["Cube"].hide_render = True
    camera = bpy.context.scene.camera
    target = Vector((2, -0.9, 0.3))
    camera.location = target + Vector((3, -4, 2))
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 3
    light = bpy.data.objects["Light"]
    light.location = camera.location
    light.rotation_euler = camera.rotation_euler
    light.data.type = "AREA"
    light.data.energy = 500
    light.data.size = 3
    bpy.context.scene.render.engine = "BLENDER_EEVEE"
    bpy.context.scene.render.resolution_x = 512
    bpy.context.scene.render.resolution_y = 256
    bpy.context.scene.render.resolution_percentage = 100
    bpy.context.scene.render.film_transparent = True
    bpy.context.scene.render.filepath = str(ARTIFACTS / "cards.png")
    bpy.ops.render.render(write_still=True)
    output_name = output.name
    source_name = output["hairball_groom"].name
    bpy.ops.wm.save_as_mainfile(filepath=str(ARTIFACTS / "cards.blend"))
    bpy.ops.wm.open_mainfile(filepath=str(ARTIFACTS / "cards.blend"))
    restored = bpy.data.objects[output_name]
    assert restored["hairball_groom"] == bpy.data.objects[source_name]
    assert restored.data.uv_layers.active and len(restored.data.shape_keys.key_blocks) == 3
    assert len(restored.data.shape_keys.animation_data.drivers) == 2
    hairball.unregister()
    print("HAIRBALL_CARDS_TESTS=PASS")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
