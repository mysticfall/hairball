"""Selection-grouped multi-groom generation into one hair card mesh, isolated only."""
from pathlib import Path
import json
import math
import sys

import bpy
import numpy as np
from mathutils import Vector

assert bpy.app.background and not bpy.data.filepath, "Use an isolated factory-startup process."
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hairball
from hairball.evaluation import HairballError
from hairball.geometry import generate_geometry, selected_grooms
from hairball.groom import create_groom

ARTIFACTS = Path("/tmp/opencode/hairball-tests")
ARTIFACTS.mkdir(parents=True, exist_ok=True)


def counts():
    return tuple(len(getattr(bpy.data, name)) for name in (
        "objects", "meshes", "materials", "collections", "node_groups", "shape_keys"))


def build():
    """One shared rig, two surface copies, one groom per side, all in the default collection."""
    rig_data = bpy.data.armatures.new("Parted rig")
    rig = bpy.data.objects.new("Parted rig", rig_data)
    bpy.context.collection.objects.link(rig)
    bpy.ops.object.select_all(action="DESELECT")
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    for name, x in (("Left", -1), ("Right", 1)):
        bone = rig_data.edit_bones.new(name)
        bone.head, bone.tail = (x, 0, 0), (x, 0, 1)
    bpy.ops.object.mode_set(mode="OBJECT")
    surfaces = []
    for side, x in (("Left", 2.0), ("Right", 6.0)):
        mesh = bpy.data.meshes.new(f"Scalp {side}")
        mesh.from_pydata([(-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0)], [], [(0, 1, 2, 3)])
        uv = mesh.uv_layers.new(name="UVMap")
        for loop, item in zip(mesh.loops, uv.data):
            co = mesh.vertices[loop.vertex_index].co
            item.uv = ((co.x + 1) / 2, (co.y + 1) / 2)
        surface = bpy.data.objects.new(f"Scalp {side}", mesh)
        bpy.context.collection.objects.link(surface)
        surface.location = (x, 0, 0)
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
        surfaces.append(surface)
    rig.pose.bones["Left"].location.x = 0.1
    rig.pose.bones["Right"].location.x = -0.1
    bpy.context.view_layer.update()

    grooms = []
    curls = {"Left": (0.07, 0.03, 0.6), "Right": (0.025, 0.025, 0.08)}
    for side, surface in zip(("Left", "Right"), surfaces):
        groom = create_groom(surface, count=4, points=65)
        groom.name = f"Scalp {side} Guides"
        groom.data.set_types(type="POLY")
        positions, root_uvs = [], []
        for curve in range(4):
            root = Vector((-0.9 if curve < 2 else 0.9, -0.9 + 0.002 * (curve % 2), 0))
            root_uvs.extend(((root.x + 1) / 2, (root.y + 1) / 2))
            for i in range(65):
                t = i / 64
                a, b, c = curls[side]
                offset = Vector((a * math.sin(2 * math.pi * t), b * math.sin(math.pi * t), c * t))
                positions.extend(root + offset)
        groom.data.position_data.foreach_set("vector", positions)
        groom.data.attributes["surface_uv_coordinate"].data.foreach_set("vector", root_uvs)
        groom.data.attributes["radius"].data.foreach_set("value", [0.0005] * (65 * 4))
        groom.data.update_tag()
        grooms.append(groom)
    bpy.context.view_layer.update()
    return rig, surfaces, grooms


def remove_groom(groom):
    graph = groom.modifiers[0].node_group
    curves = groom.data
    bpy.data.objects.remove(groom, do_unlink=True)
    bpy.data.hair_curves.remove(curves)
    bpy.data.node_groups.remove(graph)


def select(active, *others):
    bpy.ops.object.select_all(action="DESELECT")
    for groom in others:
        groom.select_set(True)
    active.select_set(True)
    bpy.context.view_layer.objects.active = active


def main():
    hairball.register()
    rig, surfaces, grooms = build()
    settings = bpy.context.scene.hairball
    settings.card_width = 0.01
    settings.atlas_size = 512
    members = tuple(sorted(grooms, key=lambda groom: groom.name))

    # Selection resolves the group; the active groom is always a member.
    select(grooms[0], grooms[1])
    resolved, active = selected_grooms(bpy.context)
    assert resolved == members and active == grooms[0]

    # Hidden (eye) backups never join even with a stale selection state.
    backup = create_groom(surfaces[0], count=2, points=8)
    backup.name = "Scalp Left Backup"
    backup.hide_set(True)
    select(grooms[0], grooms[1], backup)
    # selected_objects itself drops hidden objects; selected_grooms filters again.
    assert backup not in bpy.context.selected_objects
    resolved, _ = selected_grooms(bpy.context)
    assert resolved == members
    # A hidden active groom is rejected instead of silently skipped.
    try:
        select(backup)
        selected_grooms(bpy.context)
    except HairballError as exc:
        assert "hidden" in str(exc)
    else:
        raise AssertionError("Expected a hidden active groom rejection")
    remove_groom(backup)

    select(grooms[0], grooms[1])
    assert bpy.ops.hairball.generate_cards() == {"FINISHED"}
    result = bpy.context.object
    report = json.loads(result["hairball_report"])
    assert report["grooms"] == 2 and report["cards"] == 4 and report["version"] == 1, report
    # Combined results are named after the active groom, never the collection.
    assert result.name == "Scalp Left Cards"
    assert result.users_collection[0].name == "Scalp Left v001"
    default_collection = bpy.context.scene.collection.children[0]
    assert default_collection.name == "Collection"
    assert result.users_collection[0].name in (child.name for child in default_collection.children)
    assert json.loads(result["hairball_grooms"]) == ["Scalp Left Guides", "Scalp Right Guides"]
    assert json.loads(result["hairball_groom_offsets"]) == {"Scalp Left Guides": 0, "Scalp Right Guides": 1 << 40}
    assert result["hairball_groom"] == grooms[0]
    assert result["hairball_surface"] == surfaces[0].name
    assert json.loads(result["hairball_surfaces"]) == [surfaces[0].name, surfaces[1].name]
    cards = json.loads(result["hairball_cards"])
    assert {entry["groom"] for entry in cards} == {"Scalp Left Guides", "Scalp Right Guides"}
    assert {entry["surface"] for entry in cards} == {"Scalp Left", "Scalp Right"}
    left_ids = {s for entry in cards if entry["groom"] == "Scalp Left Guides" for s in entry["strands"]}
    right_ids = {s for entry in cards if entry["groom"] == "Scalp Right Guides" for s in entry["strands"]}
    assert left_ids and right_ids and not (left_ids & right_ids)
    assert all(s < (1 << 40) for s in left_ids) and all(s >= (1 << 40) for s in right_ids)
    assert {v.value for v in result.data.attributes["hairball_surface_index"].data} == {0, 1}
    assert {v.value for v in result.data.attributes["hairball_anchor"].data} <= {0, 1, 2, 3}
    assert result.parent == rig
    assert set(g.name for g in result.vertex_groups) == {"Left", "Right"}
    assert len(result.data.shape_keys.key_blocks) == 3
    assert len(result.data.shape_keys.animation_data.drivers) == 2
    for driver in result.data.shape_keys.animation_data.drivers:
        variable = driver.driver.variables[0]
        assert variable.targets[0].id == surfaces[0].data.shape_keys
    # Grouped bakes keep per-side strand seeds independent despite shared ids.
    attributes = result["hairball_attributes"]
    pixels = np.array(attributes.pixels[:]).reshape(attributes.size[0], attributes.size[1], 4)
    values = {}
    for entry in cards:
        x, y, width, height = entry["atlas_tile"]
        values.setdefault(entry["groom"], set()).update(
            np.unique(pixels[y:y + height, x:x + width, 2]))
    left_values = values["Scalp Left Guides"] - {0.0}
    right_values = values["Scalp Right Guides"] - {0.0}
    assert left_values and right_values and left_values.isdisjoint(right_values)

    # Reruns with the same selection create the next combined version.
    select(grooms[0], grooms[1])
    assert bpy.ops.hairball.generate_cards() == {"FINISHED"}
    assert bpy.context.object.users_collection[0].name == "Scalp Left v002"

    # Any member may be active; the active groom names the result and drives it.
    select(grooms[1], grooms[0])
    assert bpy.ops.hairball.generate_geometry() == {"FINISHED"}
    preview = bpy.context.object
    assert json.loads(preview["hairball_grooms"]) == ["Scalp Left Guides", "Scalp Right Guides"]
    assert preview["hairball_surface"] == surfaces[1].name
    assert preview.name == "Scalp Right Preview"
    assert preview.users_collection[0].name == "Scalp Right Preview v001"
    assert "hairball_attributes" not in preview
    assert {v.value for v in preview.data.attributes["hairball_surface_index"].data} == {0, 1}
    for driver in preview.data.shape_keys.animation_data.drivers:
        variable = driver.driver.variables[0]
        assert variable.targets[0].id == surfaces[1].data.shape_keys

    # Regression: a hidden guide groom with a stale selection must stay excluded
    # and the lone selected groom keeps exact standalone naming.
    grooms[0].hide_set(True)
    select(grooms[1], grooms[0])
    assert grooms[0] not in bpy.context.selected_objects
    assert bpy.ops.hairball.generate_cards() == {"FINISHED"}
    solo_cards = bpy.context.object
    solo_report = json.loads(solo_cards["hairball_report"])
    assert solo_report["grooms"] == 1 and solo_report["version"] == 1, solo_report
    assert solo_cards.name == "Scalp Right Cards"
    assert solo_cards.users_collection[0].name == "Scalp Right v001"
    assert "hairball_grooms" not in solo_cards
    assert "hairball_surface_index" not in solo_cards.data.attributes
    grooms[0].hide_set(False)

    # A single selected groom stays standalone with unchanged provenance contracts.
    single = create_groom(surfaces[1], count=2, points=8)
    select(single)
    assert selected_grooms(bpy.context) == ((single,), single)
    assert bpy.ops.hairball.generate_geometry() == {"FINISHED"}
    solo = bpy.context.object
    solo_report = json.loads(solo["hairball_report"])
    assert solo_report["grooms"] == 1 and solo_report["version"] == 1 and solo_report["cards"] >= 1
    assert "hairball_grooms" not in solo
    assert "hairball_surface_index" not in solo.data.attributes
    assert solo["hairball_groom"] == single and solo["hairball_surface"] == surfaces[1].name
    assert solo.users_collection[0].name == "Scalp Right Hairball Preview v001"

    # Standalone and combined version lineages stay separate.
    select(grooms[0], grooms[1])
    assert bpy.ops.hairball.generate_geometry() == {"FINISHED"}
    assert bpy.context.object.users_collection[0].name == "Scalp Left Preview v001"

    # Combined surfaces must share one armature.
    other_data = bpy.data.armatures.new("Other rig")
    other = bpy.data.objects.new("Other rig", other_data)
    bpy.context.collection.objects.link(other)
    surfaces[1].modifiers["Armature"].object = other
    before = counts()
    try:
        generate_geometry(members, settings, bpy.context, textured=True, active=grooms[0])
    except HairballError as exc:
        assert "armature" in str(exc)
    else:
        raise AssertionError("Expected an armature mismatch rejection")
    assert counts() == before, (counts(), before)
    surfaces[1].modifiers["Armature"].object = rig
    bpy.data.objects.remove(other, do_unlink=True)
    bpy.data.armatures.remove(other_data)

    # Combined surfaces must share one shape-key layout.
    key = surfaces[1].data.shape_keys.key_blocks["Right lift"]
    key.name = "Right lift renamed"
    before = counts()
    try:
        generate_geometry(members, settings, bpy.context, active=grooms[0])
    except HairballError as exc:
        assert "shape-key" in str(exc)
    else:
        raise AssertionError("Expected a shape-key layout rejection")
    assert counts() == before, (counts(), before)
    key.name = "Right lift"

    hairball.unregister()
    print("HAIRBALL_MULTI_GROOM_TESTS=PASS")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
