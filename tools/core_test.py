"""Isolated Blender integration tests; no reference .blend files are modified."""
from pathlib import Path
import importlib
import json
import struct
import sys
import faulthandler

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hairball
from hairball.deformation import nearest_anchors, transfer
from hairball.evaluation import HairballError, evaluated_strands, rest_strands

ARTIFACTS = Path("/tmp/opencode/hairball-tests")
assert bpy.app.background and not bpy.data.filepath, "Use an isolated factory-startup process."
ARTIFACTS.mkdir(parents=True, exist_ok=True)


def close(actual, expected, tolerance=1e-5):
    assert (Vector(actual) - Vector(expected)).length < tolerance, (actual, expected)


def fail(callback, fragment):
    try:
        callback()
    except HairballError as exc:
        assert fragment in str(exc), str(exc)
    else:
        raise AssertionError("Expected validation failure: " + fragment)


def fixture():
    mesh = bpy.data.meshes.new("Attachment surface")
    mesh.from_pydata([(-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0)], [], [(0, 1, 2, 3)])
    uv = mesh.uv_layers.new(name="UVMap")
    for item, coord in zip(uv.data, [(0, 0), (1, 0), (1, 1), (0, 1)]):
        item.uv = coord
    surface = bpy.data.objects.new("Surface", mesh)
    bpy.context.collection.objects.link(surface)
    surface.add_rest_position_attribute = True
    rig_data = bpy.data.armatures.new("Rig")
    rig = bpy.data.objects.new("Rig", rig_data)
    bpy.context.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    for name, x in (("Left", -1), ("Right", 1)):
        bone = rig_data.edit_bones.new(name)
        bone.head = (x, -1, 0)
        bone.tail = (x, -1, 1)
    helper = rig_data.edit_bones.new("NonDeform")
    helper.head = (0, 0, 0)
    helper.tail = (0, 0, 1)
    helper.use_deform = False
    bpy.ops.object.mode_set(mode="OBJECT")
    surface.vertex_groups.new(name="Left").add([0, 3], 1, "REPLACE")
    surface.vertex_groups.new(name="Right").add([1, 2], 1, "REPLACE")
    surface.vertex_groups.new(name="Mask helper").add([0, 1, 2, 3], 0.25, "REPLACE")
    surface.vertex_groups.new(name="NonDeform").add([0, 1, 2, 3], 1, "REPLACE")
    armature = surface.modifiers.new("Armature", "ARMATURE")
    armature.object = rig
    basis = surface.shape_key_add(name="Basis", from_mix=False)
    left = surface.shape_key_add(name='Left "lift"', from_mix=False)
    for index in range(4):
        left.data[index].co = basis.data[index].co
    for index in (0, 3):
        left.data[index].co.z += 0.3
    right = surface.shape_key_add(name="Right lift", from_mix=False)
    for index in range(4):
        right.data[index].co = basis.data[index].co
    for index in (1, 2):
        right.data[index].co.z += 0.6
    chained = surface.shape_key_add(name="Chained")
    chained.relative_key = left
    chained.vertex_group = "Mask helper"
    for i in range(4):
        chained.data[i].co = left.data[i].co + Vector((0, 0, 0.4))
    curves = bpy.data.hair_curves.new("Attached groom")
    curves.add_curves([3, 3])
    positions = [(-1, -1, 0), (-1, -1, 0.5), (-1, -1, 1),
                 (1, -1, 0), (1, -1, 0.5), (1, -1, 1)]
    curves.position_data.foreach_set("vector", [v for point in positions for v in point])
    curves.attributes.new("radius", "FLOAT", "POINT").data.foreach_set("value", [0.01] * 6)
    curves.attributes.new("id", "INT", "CURVE").data.foreach_set("value", [101, 202])
    curves.surface = surface
    curves.surface_uv_map = "UVMap"
    groom = bpy.data.objects.new("Groom", curves)
    bpy.context.collection.objects.link(groom)
    bpy.ops.object.select_all(action="DESELECT")
    groom.select_set(True)
    bpy.context.view_layer.objects.active = groom
    bpy.ops.curves.snap_curves_to_surface(attach_mode="NEAREST")
    graph = bpy.data.node_groups.new("Groom deformation", "GeometryNodeTree")
    graph.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    graph.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    source = graph.nodes.new("NodeGroupInput")
    output = graph.nodes.new("NodeGroupOutput")
    transform = graph.nodes.new("GeometryNodeTransform")
    transform.inputs["Translation"].default_value = (0, 0, 0.05)
    deform = graph.nodes.new("GeometryNodeDeformCurvesOnSurface")
    graph.links.new(source.outputs["Geometry"], transform.inputs["Geometry"])
    graph.links.new(transform.outputs["Geometry"], deform.inputs["Curves"])
    graph.links.new(deform.outputs["Curves"], output.inputs["Geometry"])
    groom.modifiers.new("Native deformation", "NODES").node_group = graph
    left.value = 0.5
    right.value = 0.25
    chained.value = 0.5
    rig.pose.bones["Left"].location.x = 0.2
    rig.pose.bones["Right"].location.x = -0.3
    bpy.context.view_layer.update()
    return surface, groom, rig, positions


def main():
    global HairballError, evaluated_strands, rest_strands, nearest_anchors, transfer
    faulthandler.dump_traceback_later(30, repeat=False)
    print("TEST registration", flush=True)
    hairball.register()
    hairball.unregister()
    importlib.reload(hairball)
    hairball.register()
    from hairball.deformation import nearest_anchors, transfer
    from hairball.evaluation import HairballError, evaluated_strands, rest_strands
    print("TEST attachment fixture", flush=True)
    surface, groom, rig, positions = fixture()
    print("TEST rest recovery", flush=True)
    before = (len(bpy.data.objects), len(bpy.data.node_groups), groom.modifiers[0].node_group,
              bpy.context.object, tuple(bpy.context.selected_objects))
    rest = rest_strands(groom)
    print("TEST evaluated extraction", flush=True)
    final = evaluated_strands(groom)
    assert [s.identifier for s in rest] == [101, 202]
    close(rest[0].points[0], (-1, -1, 0.05))
    close(rest[1].points[0], (1, -1, 0.05))
    # Native surface deformation also rotates the strand with surface normals;
    # generated cards deliberately use translation-only morph deltas instead.
    assert abs(final[0].points[0][0] - rest[0].points[0][0]) > 0.1
    assert abs(final[1].points[0][0] - rest[1].points[0][0]) > 0.1
    assert rest[0].radii[0] > 0
    for point, original in zip(groom.data.position_data, positions):
        close(point.vector, original)
    after = (len(bpy.data.objects), len(bpy.data.node_groups), groom.modifiers[0].node_group,
             bpy.context.object, tuple(bpy.context.selected_objects))
    assert before == after, (before, after)
    cyclic = groom.data.attributes.new("cyclic", "BOOLEAN", "CURVE")
    cyclic.data.foreach_set("value", [True, False])
    bpy.context.view_layer.update()
    fail(lambda: rest_strands(groom), "open root-to-tip")
    assert len(bpy.data.objects) == before[0]
    assert len(bpy.data.node_groups) == before[1]
    groom.data.attributes.remove(cyclic)
    bpy.context.view_layer.update()
    anchors = nearest_anchors(surface, [s.points[0] for s in rest], groom.matrix_world)
    assert anchors == (0, 1), anchors
    # Two cards, each with four vertices and a single independent root anchor.
    vertices = [(-1.1, -1, 0.05), (-0.9, -1, 0.05), (-0.9, -1, 1.05), (-1.1, -1, 1.05),
                (0.9, -1, 0.05), (1.1, -1, 0.05), (1.1, -1, 1.05), (0.9, -1, 1.05)]
    mesh = bpy.data.meshes.new("Cards")
    mesh.from_pydata(vertices, [], [(0, 1, 2, 3), (4, 5, 6, 7)])
    uv = mesh.uv_layers.new(name="UVMap")
    for i, item in enumerate(uv.data):
        item.uv = [(0, 0), (1, 0), (1, 1), (0, 1)][i % 4]
    cards = bpy.data.objects.new("Cards", mesh)
    bpy.context.collection.objects.link(cards)
    print("TEST deformation transfer", flush=True)
    transfer(surface, cards, [0] * 4 + [1] * 4)
    assert set(g.name for g in cards.vertex_groups) == {"Left", "Right"}
    keys = cards.data.shape_keys.key_blocks
    assert keys["Chained"].relative_key.name == "Basis"
    close(keys["Chained"].data[0].co - keys["Basis"].data[0].co, (0, 0, 0.1))
    assert json.loads(cards["hairball_source_relative_keys"])["Chained"] == 'Left "lift"'
    bpy.context.view_layer.update()
    close((keys['Left "lift"'].value, keys["Right lift"].value, keys["Chained"].value), (0.5, 0.25, 0.5))
    evaluated = cards.evaluated_get(bpy.context.evaluated_depsgraph_get())
    for index, point in enumerate(evaluated.data.vertices):
        delta = (0.2, 0, 0.2) if index < 4 else (-0.3, 0, 0.2)
        close(point.co, Vector(vertices[index]) + Vector(delta))
    # Change the source; the existing cards should update without regeneration.
    surface.data.shape_keys.key_blocks['Left "lift"'].value = 1
    surface.data.shape_keys.key_blocks["Right lift"].value = 0
    bpy.context.view_layer.update()
    evaluated = cards.evaluated_get(bpy.context.evaluated_depsgraph_get())
    close(evaluated.data.vertices[0].co, Vector(vertices[0]) + Vector((0.2, 0, 0.35)))
    close(evaluated.data.vertices[4].co, Vector(vertices[4]) + Vector((-0.3, 0, 0.05)))
    # Reject custom scene-dependent geometry before temporary datablocks exist.
    bad_node = groom.modifiers[0].node_group.nodes.new("GeometryNodeObjectInfo")
    fail(lambda: rest_strands(groom), "not yet audited")
    groom.modifiers[0].node_group.nodes.remove(bad_node)
    assert len(bpy.data.objects) == before[0] + 1
    # Standard export, not a Hairball exporter. glTF gets rest mesh and skin/morph data.
    bpy.ops.object.select_all(action="DESELECT")
    cards.select_set(True)
    rig.select_set(True)
    bpy.context.view_layer.objects.active = cards
    path = ARTIFACTS / "cards.glb"
    print("TEST GLB export", flush=True)
    bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_selection=True,
                              export_tangents=True, export_morph=True, export_skins=True,
                              export_materials="NONE", export_animations=False)
    blob = path.read_bytes()
    magic, version, length = struct.unpack_from("<III", blob)
    assert magic == 0x46546C67 and version == 2 and length == len(blob)
    chunk_length, chunk_type = struct.unpack_from("<II", blob, 12)
    assert chunk_type == 0x4E4F534A
    gltf = json.loads(blob[20:20 + chunk_length])
    primitive = gltf["meshes"][0]["primitives"][0]
    assert {"POSITION", "NORMAL", "TEXCOORD_0", "TANGENT", "JOINTS_0", "WEIGHTS_0"} <= set(primitive["attributes"])
    assert len(primitive["targets"]) == 3, primitive
    assert len(gltf["skins"]) == 1
    binary_start = 20 + chunk_length + 8

    def accessor_first(index):
        accessor = gltf["accessors"][index]
        view = gltf["bufferViews"][accessor["bufferView"]]
        offset = binary_start + view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
        count = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[accessor["type"]]
        fmt = {5126: "f", 5123: "H", 5121: "B"}[accessor["componentType"]]
        return struct.unpack_from("<" + fmt * count, blob, offset)

    names = gltf["meshes"][0]["extras"]["targetNames"]
    chained_target = primitive["targets"][names.index("Chained")]
    # glTF +Y up: Blender's Z displacement becomes glTF Y.
    close(accessor_first(chained_target["POSITION"]), (0, 0.1, 0))
    assert abs(accessor_first(primitive["attributes"]["TANGENT"])[3]) == 1
    # Save/reopen the isolated fixture to test drivers and metadata persistence.
    blend = ARTIFACTS / "core.blend"
    print("TEST save/reopen", flush=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    bpy.ops.wm.open_mainfile(filepath=str(blend))
    restored = bpy.data.objects["Cards"]
    bpy.context.view_layer.update()
    assert restored["hairball_surface"] == "Surface"
    assert [p.value for p in restored.data.attributes["hairball_anchor"].data] == [0] * 4 + [1] * 4
    assert len(restored.data.shape_keys.animation_data.drivers) == 3
    assert abs(restored.data.shape_keys.key_blocks['Left "lift"'].value - 1) < 1e-6
    # Ordinary glTF import provides a small independent round-trip check.
    bpy.ops.import_scene.gltf(filepath=str(path))
    imported = next(o for o in bpy.context.selected_objects if o.type == "MESH")
    assert len(imported.data.uv_layers) == 1
    assert len(imported.data.shape_keys.key_blocks) == 4
    assert any(m.type == "ARMATURE" for m in imported.modifiers)
    assert {g.name for g in imported.vertex_groups} >= {"Left", "Right"}
    hairball.unregister()
    faulthandler.cancel_dump_traceback_later()
    print("HAIRBALL_CORE_TESTS=PASS")
    print(json.dumps({"blender": bpy.app.version_string, "strands": len(rest),
                      "glb_attributes": sorted(primitive["attributes"]),
                      "morph_targets": len(primitive["targets"]), "artifacts": str(ARTIFACTS)}))


main()
