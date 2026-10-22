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


def _scene_contains(root, target):
    return root == target or any(_scene_contains(child, target) for child in root.children)


def _result_parent(groom, scene):
    """Use a source collection in this scene; never link into another scene."""
    return next((collection for collection in groom.users_collection
                 if _scene_contains(scene.collection, collection)), scene.collection)


def selected_grooms(context):
    """Resolve the grooms to generate from the current selection.

    Every selected Hair Curves object joins one combined mesh; selecting a
    single groom keeps the exact standalone behaviour. Hidden objects (such
    as backup guide grooms) never join, even when their selection state is
    stale. The active groom names the result and provides the primary
    surface.
    """
    active = context.object
    if active is None or active.type != "CURVES":
        raise HairballError("Select a modern Hair Curves object, not legacy Curve/particle hair.")
    if active.hide_get():
        raise HairballError("The active groom is hidden in the viewport.")
    members = {active}
    members.update(obj for obj in context.selected_objects
                   if obj.type == "CURVES" and not obj.hide_get())
    return tuple(sorted(members, key=lambda obj: obj.name)), active


def generate_geometry(grooms, settings, context=None, *, textured=False, active=None):
    """Generate one independent versioned result from one or more grooms.

    Standalone grooms keep their exact provenance; selected grooms (one Curves
    object per hairstyle side or patch) combine into a single mesh and atlas
    pair while each card keeps its own groom's surface anchor provenance.
    Cards never merge strands from different grooms. The active groom names
    the result and provides the primary surface.
    """
    started = time.perf_counter()
    context = context or bpy.context
    if isinstance(grooms, bpy.types.Object):
        grooms = (grooms,)
    grooms = tuple(grooms)
    if not grooms or any(groom is None or groom.type != "CURVES" for groom in grooms):
        raise HairballError("Select a modern Hair Curves object, not legacy Curve/particle hair.")
    active = active if active is not None else grooms[0]
    combined = len(grooms) > 1
    sources, surfaces, surface_ids = [], [], {}
    bundles, bundle_sources = [], []
    strands_total = 0
    for ordinal, groom in enumerate(grooms):
        surface = validate_groom(groom)
        if any(m.show_viewport and m.type not in {"ARMATURE", "SUBSURF"} for m in surface.modifiers):
            raise HairballError("Geometry preview currently supports only Armature/Subdivision surface modifiers.")
        if id(surface) not in surface_ids:
            surface_ids[id(surface)] = len(surfaces)
            surfaces.append(surface)
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
        if combined and any(s.identifier >= (1 << 40) for s in rest):
            raise HairballError("Strand ids are too large to group deterministically.")
        offset = ordinal << 40 if combined else 0
        strands = tuple(Strand(offset + s.identifier, tuple(tuple(matrix @ Vector(p)) for p in s.points),
                               tuple(radius * scale * settings.radius_scale for radius in s.radii)) for s in rest)
        anchors = nearest_anchors(surface, [s.points[0] for s in rest], matrix)
        produced = cluster_strands(strands, anchors, root_distance=settings.cluster_radius,
                                   shape_distance=settings.cluster_shape_error,
                                   direction_angle=settings.cluster_angle, max_strands=settings.bundle_size)
        bundles.extend(produced)
        bundle_sources.extend([len(sources)] * len(produced))
        strands_total += len(strands)
        sources.append({"groom": groom, "surface": surface,
                        "surface_index": surface_ids[id(surface)], "offset": offset})
    ribbons, ribbon_sources = [], []
    for bundle, ordinal in zip(bundles, bundle_sources):
        produced = fit_bundles((bundle,), minimum_width=settings.card_width, fit_error=settings.fit_error,
                               bend_limit=settings.bend_limit, max_segments=settings.max_segments)
        ribbons.extend(produced)
        ribbon_sources.extend([ordinal] * len(produced))
    tiles = pack(ribbons, settings.atlas_size) if textured else None
    vertices, faces, uvs, vertex_anchors, vertex_surfaces, card_ids, root_parameters, metadata = [], [], [], [], [], [], [], []
    for card_index, ribbon in enumerate(ribbons):
        source = sources[ribbon_sources[card_index]]
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
        vertex_surfaces.extend([source["surface_index"]] * len(positions))
        card_ids.extend([card_index] * len(polygons))
        entry = {"anchor": ribbon.anchor, "strands": [s.identifier for s in ribbon.strands],
                 "vertex_start": start, "vertex_count": len(positions),
                 "face_start": face_start, "face_count": len(polygons)}
        if combined:
            entry["groom"] = source["groom"].name
            entry["surface"] = source["surface"].name
        metadata.append(entry)
        if textured:
            tile = tiles[card_index]
            metadata[-1]["atlas_tile"] = [tile.x, tile.y, tile.width, tile.height]
    kind = "HAIR_CARDS" if textured else "GEOMETRY_PREVIEW"
    members = json.dumps([source["groom"].name for source in sources]) if combined else None
    label = _result_label(active)
    if combined:
        version = max((c.get("hairball_version", 0) for c in bpy.data.collections
                       if c.get("hairball_kind") == kind and c.get("hairball_group") == members
                       and c.get("hairball_label") == label), default=0) + 1
    else:
        version = max((c.get("hairball_version", 0) for c in bpy.data.collections
                       if c.get("hairball_source_object") == active
                       and c.get("hairball_kind") == kind
                       and not c.get("hairball_group")), default=0) + 1
    collection_name = f"{label}{'' if textured else ' Preview'} v{version:03d}"
    name = f"{label} {'Cards' if textured else 'Preview'}"
    primary = next((source["surface_index"] for source in sources if source["groom"] == active),
                   sources[0]["surface_index"])
    mesh = obj = collection = material = None
    images = []
    try:
        collection = bpy.data.collections.new(collection_name)
        parent = _result_parent(active, context.scene)
        parent.children.link(collection)
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
        transfer(surfaces, obj, vertex_anchors, vertex_surfaces, primary=primary)
        if obj.parent is None:
            obj.parent = surfaces[primary]
            obj.matrix_parent_inverse = surfaces[primary].matrix_world.inverted()
            obj.matrix_world = Matrix.Identity(4)
        warnings = saturated = 0
        if textured:
            images, warnings, saturated = bake(mesh, ribbons, tiles, name, settings.seed)
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
        obj["hairball_groom"] = active
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
        if combined:
            obj["hairball_grooms"] = members
            obj["hairball_groom_offsets"] = json.dumps(
                {source["groom"].name: source["offset"] for source in sources})
        report = {"strands": strands_total, "clusters": len(bundles), "cards": len(ribbons),
                  "vertices": len(vertices), "triangles": len(faces) if textured else 2 * len(faces), "version": version,
                  "grooms": len(sources),
                  "seconds": round(time.perf_counter() - started, 4)}
        if textured:
            report.update(atlas_size=settings.atlas_size, sparse_cards=warnings,
                          saturated_cards=saturated)
        obj["hairball_report"] = json.dumps(report)
        collection["hairball_kind"] = kind
        collection["hairball_source_object"] = active
        if combined:
            collection["hairball_group"] = members
            collection["hairball_label"] = label
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
