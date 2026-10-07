"""Native/interpolated strand colour, isolated shared data and persistence."""
from pathlib import Path
import sys

import bpy
from mathutils import Vector

assert bpy.app.background and not bpy.data.filepath, 'Use factory startup.'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import hairball
from cards_test import fixture
from hairball.materials import apply_groom_color
from hairball.native import prepare_interpolation
from hairball.evaluation import rest_strands


def check_evaluated(groom, material):
    evaluated = groom.evaluated_get(bpy.context.evaluated_depsgraph_get())
    geometry = evaluated.evaluated_geometry()
    assert any(m.original == material for m in geometry.curves.materials), list(geometry.curves.materials)


hairball.register()
surface, groom, rig = fixture()
original = groom.data
shared = groom.copy()
bpy.context.collection.objects.link(shared)
positions = tuple(tuple(p.vector) for p in original.position_data)
material = apply_groom_color(groom, (0.2, 0.04, 0.01, 1))
assert shared.data == original and groom.data != original
assert not original.materials
assert tuple(tuple(p.vector) for p in groom.data.position_data) == positions
assert groom.data.surface == surface
check_evaluated(groom, material)

settings = bpy.context.scene.hairball
settings.interpolation_density = 30
settings.interpolation_distance = 5
interpolated, count = prepare_interpolation(groom, settings)
before = rest_strands(interpolated)
colour = apply_groom_color(interpolated, (0.01, 0.03, 0.1, 1))
check_evaluated(interpolated, colour)
assert rest_strands(interpolated) == before
assert groom.data.materials[0] == material

bpy.ops.object.select_all(action='DESELECT')
interpolated.select_set(True)
bpy.context.view_layer.objects.active = interpolated
settings.preview_color = (0.1, 0.2, 0.3, 1)
old_data = interpolated.data
bpy.ops.ed.undo_push(message='Before groom colour')
assert bpy.ops.hairball.apply_groom_color() == {'FINISHED'}
name = interpolated.name
data_name = old_data.name
bpy.ops.ed.undo_push(message='After groom colour')
bpy.ops.ed.undo()
assert bpy.data.objects[name].data.name == data_name
bpy.ops.ed.redo()
interpolated = bpy.data.objects[name]
assert interpolated.data.name != data_name
check_evaluated(interpolated, interpolated.data.materials[0])
path = Path('/tmp/opencode/hairball-tests/groom-colour.blend')
path.parent.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=str(path))
bpy.ops.wm.open_mainfile(filepath=str(path))
interpolated = bpy.data.objects[name]
check_evaluated(interpolated, interpolated.data.materials[0])
assert len(rest_strands(interpolated)) == count
# Render the native interpolated strands, not cards, with two distinct colours.
for obj in bpy.context.scene.objects:
    if obj.type in {'MESH', 'CURVES'}:
        obj.hide_render = obj != interpolated
camera = bpy.context.scene.camera
target = Vector((2, -0.9, 0.3))
camera.location = target + Vector((3, -4, 2))
camera.rotation_euler = (target - camera.location).to_track_quat('-Z', 'Y').to_euler()
camera.data.type = 'ORTHO'
camera.data.ortho_scale = 1.6
light = bpy.data.objects['Light']
light.location = camera.location
light.rotation_euler = camera.rotation_euler
light.data.type = 'AREA'
light.data.energy = 500
light.data.size = 3
scene = bpy.context.scene
scene.render.engine = 'BLENDER_EEVEE'
scene.render.resolution_x = scene.render.resolution_y = 256
scene.render.resolution_percentage = 100
scene.render.film_transparent = True
import numpy as np
for label, colour, channel in (('red', (0.8, 0.01, 0.01, 1), 0),
                               ('blue', (0.01, 0.01, 0.8, 1), 2)):
    apply_groom_color(interpolated, colour)
    scene.render.filepath = str(path.parent / f'groom-colour-{label}.png')
    bpy.ops.render.render(write_still=True)
    image = bpy.data.images.load(scene.render.filepath, check_existing=False)
    values = np.empty(len(image.pixels), dtype=np.float32)
    image.pixels.foreach_get(values)
    values = values.reshape(-1, 4)
    visible = values[values[:, 3] > 0.1]
    assert len(visible) > 0
    assert visible[:, channel].mean() > visible[:, 2-channel].mean() * 1.2
    bpy.data.images.remove(image)
print('HAIRBALL_GROOM_COLOR_TESTS=PASS')
