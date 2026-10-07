"""Ribbon fitting and actual EEVEE render in an isolated factory-startup process."""
from pathlib import Path
import math
import sys

import bpy
from mathutils import Vector

assert bpy.app.background and not bpy.data.filepath, "Use an isolated factory-startup process."
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hairball.cards import fit_bundle, ribbon_geometry
from hairball.evaluation import Strand
from hairball.materials import preview_material

ARTIFACTS = Path("/tmp/opencode/hairball-tests")
ARTIFACTS.mkdir(parents=True, exist_ok=True)


def data_image(name, coords=False):
    image = bpy.data.images.new(name, width=32, height=64, alpha=True, float_buffer=False)
    image.colorspace_settings.name = "Non-Color"
    image.alpha_mode = "CHANNEL_PACKED"
    pixels = []
    for y in range(64):
        for x in range(32):
            coverage = 1.0 if x % 8 in (2, 3, 4, 5) else 0.0
            pixels.extend((0.5, 1, 0.5, y / 63) if coords else (coverage, 0.5, x / 31, 1))
    image.pixels.foreach_set(pixels)
    image.update()
    image.pack()
    return image


def main():
    attrib = data_image("Preview attributes")
    coords = data_image("Preview coordinates", True)
    material = preview_material("Preview", attrib, coords, color=(0.3, 0.13, 0.045, 1))
    cube = bpy.data.objects.get("Cube")
    if cube:
        bpy.data.objects.remove(cube, do_unlink=True)
    for name, points, segments in (
        ("Long wavy", [(-0.6 + 0.08 * math.sin(i * math.pi / 10), 0, i / 20)
                       for i in range(41)], 40),
        ("Short curl", [(0.65 + 0.13 * math.sin(i * math.pi / 10),
                         0.13 * (1 - math.cos(i * math.pi / 10)), i / 100)
                        for i in range(41)], 40),
    ):
        strand = Strand(0, tuple(points), tuple(0.003 for _ in points))
        ribbon = fit_bundle((strand,), 0, segments=segments, minimum_width=0.15)
        vertices, faces, uvs = ribbon_geometry(ribbon)
        assert len(faces) == segments
        assert ribbon.parameters[0] == 0 and ribbon.parameters[-1] == 1
        for side in ribbon.sides:
            assert abs(Vector(side).length - 1) < 1e-5
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(vertices, [], faces)
        uv = mesh.uv_layers.new(name="UVMap")
        for loop, item in zip(mesh.loops, uv.data):
            item.uv = uvs[loop.vertex_index]
        mesh.calc_tangents(uvmap="UVMap")
        assert all(abs(abs(loop.bitangent_sign) - 1) < 1e-6 for loop in mesh.loops)
        mesh.materials.append(material)
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.collection.objects.link(obj)
    camera = bpy.data.objects["Camera"]
    camera.location = (0, -5, 2)
    camera.rotation_euler = (Vector((0, 0, 1)) - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 2.7
    light = bpy.data.objects["Light"]
    light.data.type = "AREA"
    light.data.energy = 500
    light.data.shape = "DISK"
    light.data.size = 4
    light.location = (0, -2, 3)
    light.rotation_euler = (Vector((0, 0, 1)) - light.location).to_track_quat("-Z", "Y").to_euler()
    scene = bpy.context.scene
    scene.camera = camera
    # The rendering engine's RNA identifier is BLENDER_EEVEE in Blender 5.2.
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 192
    scene.render.resolution_y = 192
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(ARTIFACTS / "preview.png")
    bpy.ops.render.render(write_still=True)
    rendered = bpy.data.images.load(scene.render.filepath, check_existing=False)
    alpha = list(rendered.pixels)[3::4]
    assert max(alpha) > 0.9 and min(alpha) < 0.1, "Coverage transparency must survive rendering."
    bpy.ops.wm.save_as_mainfile(filepath=str(ARTIFACTS / "preview.blend"))
    print("HAIRBALL_PREVIEW_TESTS=PASS")


main()
