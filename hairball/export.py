"""One-click delivery of a generated cards result with Blender's native tools.

This module drives the standard glTF exporter and the standard image save; it
implements no exporter, file format, or game-project integration of its own.
"""
import json
import os
import time

import bpy

from .evaluation import HairballError


def _stem(filename):
    stem = os.path.splitext(os.path.basename(filename or ""))[0].strip()
    if not stem or stem.startswith("."):
        raise HairballError("Choose a base file name for the exported package.")
    return stem


def export_cards(obj, directory, filename, include_material=False):
    """Export one generated cards object as a GLB plus both data maps.

    Selection is borrowed for the native exporter (card mesh and its armature)
    and restored afterwards. The generated images' file paths are updated to the
    export destination, which is how the native save works; pixels, geometry,
    and every other scene object are untouched. The export is recorded on the
    object itself; nothing outside the chosen directory is written.
    """
    if obj is None or obj.type != "MESH" or obj.get("hairball_kind") != "HAIR_CARDS":
        raise HairballError("Select a generated Hairball cards object first.")
    attributes = obj.get("hairball_attributes")
    coordinates = obj.get("hairball_coordinates")
    if attributes is None or coordinates is None:
        raise HairballError("This cards object no longer references its data maps.")
    directory = bpy.path.abspath(directory or "")
    if not os.path.isdir(directory):
        raise HairballError("Choose an existing export directory.")
    stem = _stem(filename)
    paths = {
        "glb": os.path.join(directory, f"{stem}.glb"),
        "attributes": os.path.join(directory, f"{stem}_attributes.png"),
        "coordinates": os.path.join(directory, f"{stem}_coordinates.png"),
    }
    context = bpy.context
    previous = tuple(context.selected_objects)
    previous_active = context.view_layer.objects.active
    try:
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        # Skinning needs the armature selected; a mesh parent (no-rig fallback)
        # is deliberately not exported with the hair.
        if obj.parent is not None and obj.parent.type == "ARMATURE":
            obj.parent.select_set(True)
        context.view_layer.objects.active = obj
        try:
            result = bpy.ops.export_scene.gltf(
                filepath=paths["glb"], export_format="GLB", use_selection=True,
                export_apply=False, export_normals=True, export_tangents=True,
                export_skins=True, export_morph=True, export_animations=False,
                export_materials="EXPORT" if include_material else "NONE")
        except RuntimeError as exc:  # exporter reports failures this way
            raise HairballError(f"glTF export failed: {exc}") from exc
        if result != {"FINISHED"}:
            raise HairballError(f"glTF export failed: {result}")
        for image, path in ((attributes, paths["attributes"]),
                            (coordinates, paths["coordinates"])):
            image.filepath = path
            image.save()
    finally:
        bpy.ops.object.select_all(action="DESELECT")
        for other in previous:
            other.select_set(True)
        context.view_layer.objects.active = previous_active
    obj["hairball_export"] = json.dumps({
        "stem": stem, "directory": directory, "timestamp": time.time(),
        "glb": paths["glb"], "attributes": paths["attributes"],
        "coordinates": paths["coordinates"], "materials": bool(include_material)})
    return paths
