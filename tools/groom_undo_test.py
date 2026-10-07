"""Native undo-memory restoration of groom creation in an isolated process."""
from pathlib import Path
import sys

import bpy

assert bpy.app.background and not bpy.data.filepath, "Use an isolated factory-startup process."
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hairball
from hairball.evaluation import rest_strands


def main():
    hairball.register()
    source = bpy.data.objects["Cube"]
    assert not source.add_rest_position_attribute
    source_name = source.name
    before = len(bpy.data.objects), len(bpy.data.hair_curves), len(bpy.data.node_groups)
    bpy.ops.ed.undo_push(message="Before Hairball creation")
    assert bpy.ops.hairball.create_groom() == {"FINISHED"}
    groom_name = bpy.context.object.name
    assert len(rest_strands(bpy.context.object)) == 64
    # Python/background invocations have no normal UI event loop to push the
    # completed operator state, so explicitly snapshot it for memfile testing.
    bpy.ops.ed.undo_push(message="After Hairball creation")
    assert bpy.ops.ed.undo() == {"FINISHED"}
    assert (len(bpy.data.objects), len(bpy.data.hair_curves), len(bpy.data.node_groups)) == before
    assert not bpy.data.objects[source_name].add_rest_position_attribute
    assert bpy.context.object.name == source_name
    assert bpy.ops.ed.redo() == {"FINISHED"}
    groom = bpy.data.objects[groom_name]
    assert groom.data.surface == bpy.data.objects[source_name]
    assert bpy.data.objects[source_name].add_rest_position_attribute
    assert len(rest_strands(groom)) == 64
    hairball.unregister()
    print("HAIRBALL_GROOM_UNDO_TESTS=PASS")


main()
