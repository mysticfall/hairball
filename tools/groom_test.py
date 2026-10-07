"""Whole/selected-face native groom integration tests in an isolated process."""
from pathlib import Path
import json
import sys

import bpy
from mathutils import Vector

assert bpy.app.background and not bpy.data.filepath, "Use an isolated factory-startup process."
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hairball
from hairball.evaluation import HairballError, evaluated_strands, rest_strands
from hairball.groom import create_groom, sample_roots

ARTIFACTS = Path("/tmp/opencode/hairball-tests")
ARTIFACTS.mkdir(parents=True, exist_ok=True)


def close(actual, expected, tolerance=1e-5):
    assert (Vector(actual) - Vector(expected)).length < tolerance, (actual, expected)


def counts():
    return len(bpy.data.objects), len(bpy.data.hair_curves), len(bpy.data.node_groups)


def expect_error(callback, fragment):
    before = counts()
    try:
        callback()
    except HairballError as exc:
        assert fragment in str(exc), str(exc)
    else:
        raise AssertionError("Expected: " + fragment)
    assert counts() == before, (counts(), before)


def surface_fixture():
    mesh = bpy.data.meshes.new("Growth surface")
    mesh.from_pydata([(-1, -1, 0), (0, -1, 0), (1, -1, 0),
                     (-1, 1, 0), (0, 1, 0), (1, 1, 0)], [], [(0, 1, 4, 3), (1, 2, 5, 4)])
    uv = mesh.uv_layers.new(name="UVMap")
    for loop, item in zip(mesh.loops, uv.data):
        co = mesh.vertices[loop.vertex_index].co
        item.uv = ((co.x + 1) / 2, (co.y + 1) / 2)
    obj = bpy.data.objects.new("Growth surface", mesh)
    bpy.context.collection.objects.link(obj)
    obj.location = (1, 2, 3)
    obj.scale = (2, 1, 0.5)
    bpy.context.view_layer.update()
    basis = obj.shape_key_add(name="Basis", from_mix=False)
    lift = obj.shape_key_add(name="Lift", from_mix=False)
    for index, point in enumerate(lift.data):
        point.co = basis.data[index].co + Vector((0, 0, 0.4))
    lift.value = 0.5
    return obj


def add_rig(surface):
    data = bpy.data.armatures.new("Groom test rig")
    rig = bpy.data.objects.new("Groom test rig", data)
    bpy.context.collection.objects.link(rig)
    rig.matrix_world = surface.matrix_world.copy()
    bpy.ops.object.select_all(action="DESELECT")
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    bone = data.edit_bones.new("Body")
    bone.head = (0, 0, 0)
    bone.tail = (0, 0, 1)
    bpy.ops.object.mode_set(mode="OBJECT")
    surface.vertex_groups.new(name="Body").add(list(range(6)), 1, "REPLACE")
    modifier = surface.modifiers.new("Armature", "ARMATURE")
    modifier.object = rig
    rig.pose.bones["Body"].location.x = 0.3
    bpy.context.view_layer.update()
    return rig


def main():
    hairball.register()
    surface = surface_fixture()
    rig = add_rig(surface)
    surface.data.polygons[0].select = True
    surface.data.polygons[1].select = False
    before_shape = surface.data.shape_keys.key_blocks["Lift"].value
    before_pose = tuple(rig.pose.bones["Body"].location)
    before_source = tuple(tuple(v.co) for v in surface.data.vertices)
    source_modifiers = tuple(surface.modifiers)
    roots, uv_name = sample_roots(surface, count=32, seed=17, selected_faces=True)
    repeated, _ = sample_roots(surface, count=32, seed=17, selected_faces=True)
    assert roots == repeated
    assert uv_name == "UVMap"
    assert all(root.face == 0 and root.position[0] <= 0 and root.uv[0] <= 0.5 for root in roots)
    all_roots, _ = sample_roots(surface, count=128, seed=17)
    assert {root.face for root in all_roots} == {0, 1}
    groom = create_groom(surface, count=32, length=0.2, points=6, seed=17, selected_faces=True)
    assert groom.data.surface == surface and groom.data.surface_uv_map == "UVMap"
    assert groom.parent == surface
    assert groom["hairball_growth_region"] == "SELECTED_FACES"
    assert list(groom["hairball_growth_faces"]) == [0]
    assert surface.add_rest_position_attribute
    assert len(groom.data.curves) == 32 and len(groom.data.points) == 32 * 6
    assert surface.data.shape_keys.key_blocks["Lift"].value == before_shape
    assert tuple(rig.pose.bones["Body"].location) == before_pose
    assert tuple(tuple(v.co) for v in surface.data.vertices) == before_source
    assert tuple(surface.modifiers) == source_modifiers
    assert groom.data.attributes.get("id") is None  # Native Add owns new topology.
    rest = rest_strands(groom)
    final = evaluated_strands(groom)
    for strand, posed, root in zip(rest, final, roots):
        close(strand.points[0], root.position)
        close(posed.points[0], Vector(root.position) + Vector((0.3, 0, 0.2)))
        world_length = (groom.matrix_world.to_3x3() @
                        (Vector(strand.points[-1]) - Vector(strand.points[0]))).length
        assert abs(world_length - 0.2) < 1e-5, world_length
    # Changing object transforms keeps guides attached through ordinary parenting.
    surface.location.x += 1
    bpy.context.view_layer.update()
    close(groom.matrix_world.translation, surface.matrix_world.translation)
    # Subdivision retains the surface UV/rest attributes and recoverable guide data.
    subdivision = surface.modifiers.new("Subdivision", "SUBSURF")
    subdivision.levels = 1
    bpy.context.view_layer.update()
    assert len(evaluated_strands(groom)) == 32
    assert rest_strands(groom) == rest
    mirror = surface.modifiers.new("Unsupported Mirror", "MIRROR")
    expect_error(lambda: create_groom(surface), "not yet audited")
    surface.modifiers.remove(mirror)
    # Prove cleanup after allocation, not just validation before allocation.
    from hairball import groom as groom_module
    original_graph_builder = groom_module._deformation_graph
    def broken_builder(name):
        raise HairballError("injected setup failure")
    groom_module._deformation_graph = broken_builder
    previous_rest = surface.add_rest_position_attribute
    surface.add_rest_position_attribute = False
    try:
        expect_error(lambda: create_groom(surface), "injected setup failure")
        assert not surface.add_rest_position_attribute
    finally:
        groom_module._deformation_graph = original_graph_builder
        surface.add_rest_position_attribute = previous_rest
    # Invalid attachment inputs fail before creating data or altering rest setup.
    for face in surface.data.polygons:
        face.select = False
    expect_error(lambda: create_groom(surface, selected_faces=True), "Select at least")
    surface.data.uv_layers.remove(surface.data.uv_layers.active)
    expect_error(lambda: create_groom(surface), "active UV map")
    uv = surface.data.uv_layers.new(name="UVMap")
    for item in uv.data:
        item.uv = (0, 0)
    expect_error(lambda: create_groom(surface), "degenerate UVs")
    # Two distinct faces with identical UV squares are ambiguous even if only
    # one face was selected as a growth region.
    for i, item in enumerate(uv.data):
        item.uv = [(0, 0), (1, 0), (1, 1), (0, 1)][i % 4]
    surface.data.polygons[0].select = True
    expect_error(lambda: create_groom(surface, selected_faces=True), "Overlapping surface UVs")
    # Restore the valid original UVs and exercise the Edit Mode UI operator.
    for loop, item in zip(surface.data.loops, uv.data):
        co = surface.data.vertices[loop.vertex_index].co
        item.uv = ((co.x + 1) / 2, (co.y + 1) / 2)
    bpy.ops.object.select_all(action="DESELECT")
    surface.select_set(True)
    bpy.context.view_layer.objects.active = surface
    bpy.context.scene.hairball.growth_region = "SELECTED_FACES"
    bpy.context.scene.hairball.guide_count = 12
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.context.tool_settings.mesh_select_mode = (False, False, True)
    # Set actual BMesh selection rather than relying on stale Mesh flags.
    import bmesh
    bm = bmesh.from_edit_mesh(surface.data)
    bm.faces.ensure_lookup_table()
    for face in bm.faces:
        face.select_set(face.index == 0)
    bmesh.update_edit_mesh(surface.data)
    status = bpy.ops.hairball.create_groom()
    assert status == {"FINISHED"}, status
    ui_groom = bpy.context.object
    assert ui_groom.type == "CURVES" and bpy.context.mode == "OBJECT"
    assert len(ui_groom.data.curves) == 12
    assert all(item.value == 0 for item in ui_groom.data.attributes["hairball_source_face"].data)
    assert bpy.ops.hairball.inspect_groom() == {"FINISHED"}
    bpy.ops.object.mode_set(mode="SCULPT_CURVES")
    assert bpy.context.mode == "SCULPT_CURVES"
    bpy.ops.object.mode_set(mode="OBJECT")
    # A failed UI action must restore Edit Mode and selection, with no leaks.
    bpy.ops.object.select_all(action="DESELECT")
    surface.select_set(True)
    bpy.context.view_layer.objects.active = surface
    bpy.ops.object.mode_set(mode="EDIT")
    bm = bmesh.from_edit_mesh(surface.data)
    for face in bm.faces:
        face.select_set(False)
    bmesh.update_edit_mesh(surface.data)
    before = counts()
    try:
        status = bpy.ops.hairball.create_groom()
    except RuntimeError as exc:
        # bpy.ops turns an operator ERROR report into a Python exception.
        assert "Select at least" in str(exc), str(exc)
    else:
        assert status == {"CANCELLED"}
    assert counts() == before and bpy.context.mode == "EDIT_MESH" and bpy.context.object == surface
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    ui_groom.select_set(True)
    bpy.context.view_layer.objects.active = ui_groom
    bpy.ops.wm.save_as_mainfile(filepath=str(ARTIFACTS / "groom.blend"))
    saved_name = ui_groom.name
    surface_name = surface.name
    bpy.ops.wm.open_mainfile(filepath=str(ARTIFACTS / "groom.blend"))
    restored = bpy.data.objects[saved_name]
    assert restored.data.surface.name == surface_name
    assert len(rest_strands(restored)) == 12
    hairball.unregister()
    print("HAIRBALL_GROOM_TESTS=PASS")
    print(json.dumps({"version": bpy.app.version_string, "selected_guides": 32,
                      "ui_guides": 12, "artifact": str(ARTIFACTS / "groom.blend")}))


main()
