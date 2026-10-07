"""Independent versioned geometry previews and textured results."""
import json
import re
import time

import bpy
from mathutils import Matrix, Vector

from .cards import fit_bundles, ribbon_geometry
from .atlas import pack
from .baking import bake
from .materials import preview_material
from .clustering import cluster_strands
from .deformation import nearest_anchors, transfer
from .evaluation import HairballError, Strand, evaluated_strands, rest_strands, validate_groom


def _result_label(groom):
    """Drop authoring suffixes, not arbitrary portions of the user's name."""
    name = groom.name
    while True:
        shorter = re.sub(r" (?:Guides|Interpolated)(?:\.\d{3})?$", "", name)
        if shorter == name:
            return name.strip() or "Hair"
        name = shorter


def _result_parent(groom, scene):
    """Use a source collection in this scene; never link into another scene."""
    def contains(root, target):
        return root == target or any(contains(child, target) for child in root.children)
    return next((collection for collection in groom.users_collection
                 if contains(scene.collection, collection)), scene.collection)


def generate_geometry(groom, settings, context=None, *, textured=False):
    started = time.perf_counter()
    context = context or bpy.context
    surface = validate_groom(groom)
    if any(m.show_viewport and m.type not in {"ARMATURE", "SUBSURF"} for m in surface.modifiers):
        raise HairballError("Geometry preview currently supports only Armature/Subdivision surface modifiers.")
    final = evaluated_strands(groom)
    rest = rest_strands(groom, context, resample=True)
    if {s.identifier for s in final} != {s.identifier for s in rest}:
        raise HairballError("Rest evaluation changed strand identities; this graph needs another audit.")
    matrix = groom.matrix_world.copy()
    if abs(matrix.determinant()) < 1e-12:
        raise HairballError("The groom has a singular transform.")
    axes = [matrix.to_3x3().col[i].normalized() for i in range(3)]
    if any(abs(axes[a].dot(axes[b])) > 1e-5 for a, b in ((0, 1), (0, 2), (1, 2))):
        raise HairballError("Sheared groom transforms are not yet supported for strand radius conversion.")
    scale = max(abs(value) for value in matrix.to_scale())
    strands = tuple(Strand(s.identifier, tuple(tuple(matrix @ Vector(p)) for p in s.points),
                           tuple(radius * scale * settings.radius_scale for radius in s.radii)) for s in rest)
    anchors = nearest_anchors(surface, [s.points[0] for s in rest], matrix)
    bundles = cluster_strands(strands, anchors, root_distance=settings.cluster_radius,
                              shape_distance=settings.cluster_shape_error,
                              direction_angle=settings.cluster_angle, max_strands=settings.bundle_size)
    ribbons = fit_bundles(bundles, minimum_width=settings.card_width, fit_error=settings.fit_error,
                          bend_limit=settings.bend_limit, max_segments=settings.max_segments)
    tiles = pack(ribbons, settings.atlas_size) if textured else None
    vertices, faces, uvs, vertex_anchors, card_ids, root_parameters, metadata = [], [], [], [], [], [], []
    for card_index, ribbon in enumerate(ribbons):
        positions, polygons, coordinates = ribbon_geometry(ribbon)
        if textured:
            coordinates = [tiles[card_index].uv(uv) for uv in coordinates]
            polygons = [triangle for a, b, c, d in polygons for triangle in ((a, b, c), (a, c, d))]
        start = len(vertices)
        face_start = len(faces)
        vertices.extend(positions)
        faces.extend(tuple(start + index for index in face) for face in polygons)
        uvs.extend(coordinates)
        root_parameters.extend(parameter for parameter in ribbon.parameters for _ in range(2))
        vertex_anchors.extend([ribbon.anchor] * len(positions))
        card_ids.extend([card_index] * len(polygons))
        metadata.append({"anchor": ribbon.anchor, "strands": [s.identifier for s in ribbon.strands],
                          "vertex_start": start, "vertex_count": len(positions),
                          "face_start": face_start, "face_count": len(polygons)})
        if textured:
            tile = tiles[card_index]
            metadata[-1]["atlas_tile"] = [tile.x, tile.y, tile.width, tile.height]
    kind = "HAIR_CARDS" if textured else "GEOMETRY_PREVIEW"
    version = max((c.get("hairball_version", 0) for c in bpy.data.collections
                    if c.get("hairball_source_object") == groom
                    and c.get("hairball_kind") == kind), default=0) + 1
    label = _result_label(groom)
    collection_name = f"{label}{'' if textured else ' Preview'} v{version:03d}"
    name = f"{label} {'Cards' if textured else 'Preview'}"
    mesh = obj = collection = material = None
    images = []
    try:
        collection = bpy.data.collections.new(collection_name)
        _result_parent(groom, context.scene).children.link(collection)
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(vertices, [], faces)
        mesh.update()
        uv_layer = mesh.uv_layers.new(name="UVMap")
        uv_layer.data.foreach_set("uv", [component for loop in mesh.loops for component in uvs[loop.vertex_index]])
        mesh.attributes.new("hairball_card", "INT", "FACE").data.foreach_set("value", card_ids)
        mesh.attributes.new("hairball_root_u", "FLOAT", "POINT").data.foreach_set("value", root_parameters)
        obj = bpy.data.objects.new(name, mesh)
        collection.objects.link(obj)
        obj.matrix_world = Matrix.Identity(4)
        transfer(surface, obj, vertex_anchors)
        if obj.parent is None:
            obj.parent = surface
            obj.matrix_parent_inverse = surface.matrix_world.inverted()
            obj.matrix_world = Matrix.Identity(4)
        warnings = 0
        if textured:
            images, warnings = bake(mesh, ribbons, tiles, name, settings.seed)
            material = bpy.data.materials.new(f"{name} Preview")
            preview_material(material.name, *images, tuple(settings.preview_color),
                             material=material, diagnostic=settings.preview_mode)
            obj["hairball_attributes"] = images[0]
            obj["hairball_coordinates"] = images[1]
        else:
            material = bpy.data.materials.new(f"{name} Geometry Diagnostic")
            material.use_nodes = True
            material.diffuse_color = (0.12, 0.32, 0.65, 1)
            principled = material.node_tree.nodes.get("Principled BSDF")
            principled.inputs["Base Color"].default_value = material.diffuse_color
            principled.inputs["Roughness"].default_value = 0.5
        mesh.materials.append(material)
        obj.show_wire = not textured
        obj.show_all_edges = not textured
        obj["hairball_kind"] = kind
        obj["hairball_groom"] = groom
        obj["hairball_cards"] = json.dumps(metadata)
        keys = (
             "cluster_radius", "cluster_shape_error", "cluster_angle", "bundle_size",
             "card_width", "radius_scale", "fit_error", "bend_limit", "max_segments")
        if textured:
            keys += ("atlas_size", "seed", "preview_mode")
        obj["hairball_settings"] = json.dumps({key: getattr(settings, key) for key in keys})
        if textured:
            stored_settings = json.loads(obj["hairball_settings"])
            stored_settings["preview_color"] = list(settings.preview_color)
            obj["hairball_settings"] = json.dumps(stored_settings)
        report = {"strands": len(strands), "clusters": len(bundles), "cards": len(ribbons),
                  "vertices": len(vertices), "triangles": len(faces) if textured else 2 * len(faces), "version": version,
                  "seconds": round(time.perf_counter() - started, 4)}
        if textured:
            report.update(atlas_size=settings.atlas_size, sparse_cards=warnings)
        obj["hairball_report"] = json.dumps(report)
        collection["hairball_kind"] = kind
        collection["hairball_source_object"] = groom
        collection["hairball_version"] = version
        context.view_layer.update()
        return obj, report
    except Exception:
        if obj is not None:
            bpy.data.objects.remove(obj, do_unlink=True)
        if mesh is not None:
            bpy.data.meshes.remove(mesh)
        if material is not None:
            bpy.data.materials.remove(material)
        for image in images:
            bpy.data.images.remove(image)
        if collection is not None:
            bpy.data.collections.remove(collection)
        context.view_layer.update()
        raise
