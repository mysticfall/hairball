"""Root anchoring and uniform skinning/relative-morph transfer."""
import json

import bpy
from mathutils import Vector
from mathutils.kdtree import KDTree

from .evaluation import HairballError


def nearest_anchors(surface, roots, groom_matrix):
    """Find original mesh vertices, never evaluated/subdivision vertex indices."""
    mesh = surface.data
    if not mesh.vertices:
        raise HairballError("The attachment surface has no vertices.")
    keys = mesh.shape_keys
    basis = keys.reference_key.data if keys else mesh.vertices
    # World-space distance remains meaningful under nonuniform object scale.
    tree = KDTree(len(mesh.vertices))
    for index, point in enumerate(basis):
        tree.insert(surface.matrix_world @ point.co, index)
    tree.balance()
    return tuple(tree.find(groom_matrix @ Vector(root))[1] for root in roots)


def _shape_layout(surface):
    keys = surface.data.shape_keys
    if keys is None:
        return (), {}
    if not keys.use_relative:
        raise HairballError("Only relative shape keys are supported.")
    ordered = []
    visiting = set()
    visited = set()

    def visit(key):
        if key.name in visited:
            return
        if key.name in visiting:
            raise HairballError("Source relative shape keys form a cycle.")
        visiting.add(key.name)
        if key != keys.reference_key:
            visit(key.relative_key)
        visiting.remove(key.name)
        visited.add(key.name)
        ordered.append(key)

    for key in keys.key_blocks:
        visit(key)
    return tuple(ordered), {key.name: key for key in keys.key_blocks}


def transfer(surfaces, target, vertex_anchors, surface_indices=None, primary=0):
    """Prevalidate before adding groups/keys; caller owns the new output object.

    surfaces is a non-empty sequence of distinct attachment meshes. Each vertex
    index in vertex_anchors refers to the ORIGINAL mesh selected by the parallel
    surface_indices entry (defaulting to the first surface). Grouped surfaces
    must share one armature and one shape-key layout; weights and morph deltas
    always come from each vertex's own surface. Drivers follow the primary
    surface. The target is a new rest-space mesh without existing keys/groups.
    """
    if isinstance(surfaces, bpy.types.Object):
        surfaces = [surfaces]
    if (not surfaces or any(surface is None or surface.type != "MESH" for surface in surfaces)
            or target.type != "MESH"):
        raise HairballError("Deformation transfer requires mesh objects.")
    if len({surface.name for surface in surfaces}) != len(surfaces):
        raise HairballError("Grouped grooms must not reuse one surface twice.")
    if target.data.shape_keys or len(target.vertex_groups):
        raise HairballError("Transfer requires a new mesh without keys or vertex groups.")
    if surface_indices is None:
        surface_indices = [0] * len(vertex_anchors)
    if len(vertex_anchors) != len(target.data.vertices) or len(surface_indices) != len(vertex_anchors):
        raise HairballError("Every card vertex needs a root anchor.")
    if any(index < 0 or index >= len(surfaces) for index in surface_indices):
        raise HairballError("A root anchor references a missing surface.")
    if any(anchor < 0 or anchor >= len(surfaces[surface_indices[index]].data.vertices)
           for index, anchor in enumerate(vertex_anchors)):
        raise HairballError("A root anchor references a missing surface vertex.")
    if abs(target.matrix_world.determinant()) < 1e-12:
        raise HairballError("The result object has a singular transform.")
    layouts = [_shape_layout(surface) for surface in surfaces]
    key_names = [[key.name for key in layout[0]] for layout in layouts]
    if any(names != key_names[0] for names in key_names):
        raise HairballError("Grouped surfaces must share one shape-key layout.")
    skins = []
    for surface in surfaces:
        armatures = [m for m in surface.modifiers if m.type == "ARMATURE" and m.show_viewport]
        if len(armatures) > 1:
            raise HairballError("Multiple surface armature modifiers are not yet supported.")
        skins.append(armatures[0] if armatures else None)
    rigged = [skin for skin in skins if skin is not None]
    skin = skins[primary] if skins[primary] is not None else (rigged[0] if rigged else None)
    if rigged and (len(rigged) != len(skins)
                   or len({skin.object.name for skin in rigged}) != 1 or skin.object is None):
        raise HairballError("Grouped surfaces must all skin to the same armature object.")
    if skin and (not skin.use_vertex_groups or skin.use_bone_envelopes or skin.vertex_group):
        raise HairballError("Use an unmasked vertex-group armature, without bone envelopes.")
    weights = {}
    if skin:
        deform_names = {b.name for b in skin.object.data.bones if b.use_deform}
        group_names = [{group.index: group.name for group in surface.vertex_groups
                        if group.name in deform_names} for surface in surfaces]
        for index, anchor in enumerate(vertex_anchors):
            selection = surface_indices[index]
            if (selection, anchor) in weights:
                continue
            weights[(selection, anchor)] = {
                group_names[selection][group.group]: group.weight
                for group in surfaces[selection].data.vertices[anchor].groups
                if group.group in group_names[selection] and group.weight > 0
            }
            if not weights[(selection, anchor)]:
                raise HairballError(
                    f"Root anchor {anchor} on {surfaces[selection].name} has no deform-bone weights.")
    if skin:
        # Standard glTF export expects the armature to parent its skinned mesh.
        # Keep the generated rest mesh's world transform when establishing this.
        world = target.matrix_world.copy()
        target.parent = skin.object
        target.matrix_parent_inverse = skin.object.matrix_world.inverted()
        target.matrix_world = world
        names = sorted({name for row in weights.values() for name in row})
        groups = {name: target.vertex_groups.new(name=name) for name in names}
        for index, anchor in enumerate(vertex_anchors):
            for name, weight in weights[(surface_indices[index], anchor)].items():
                groups[name].add([index], weight, "REPLACE")
        modifier = target.modifiers.new("Hairball attachment", "ARMATURE")
        modifier.object = skin.object
        modifier.use_deform_preserve_volume = skin.use_deform_preserve_volume
        modifier.use_vertex_groups = True
        modifier.use_bone_envelopes = False
    shape_order = layouts[primary][0]
    if shape_order:
        basis_source = surfaces[primary].data.shape_keys.reference_key
        blocks = [{key.name: key for key in surface.data.shape_keys.key_blocks} for surface in surfaces]
        for name in (key.name for key in shape_order if key != basis_source):
            relatives = {blocks[index][name].relative_key.name for index in range(len(surfaces))}
            if len(relatives) != 1:
                raise HairballError("Grouped surfaces must share one shape-key layout.")
        created = {}
        conversions = [(target.matrix_world.inverted() @ surface.matrix_world).to_3x3()
                       for surface in surfaces]
        for key in shape_order:
            dest = target.shape_key_add(name=key.name, from_mix=False)
            created[key.name] = dest
            if key == basis_source:
                continue
            # Standard Blender glTF export ignores non-Basis relative links.
            # Flatten the effective relative delta, not the source absolute
            # key position, to preserve motion both in Blender and Godot.
            basis = created[basis_source.name]
            dest.relative_key = basis
            masks = [surface.vertex_groups.get(key.vertex_group) if key.vertex_group else None
                     for surface in surfaces]
            for index, anchor in enumerate(vertex_anchors):
                selection = surface_indices[index]
                source = blocks[selection][key.name]
                factor = 1.0
                if key.vertex_group:
                    factor = 0.0
                    if masks[selection]:
                        factor = next((group.weight for group in surfaces[selection].data.vertices[anchor].groups
                                       if group.group == masks[selection].index), 0.0)
                delta = conversions[selection] @ (source.data[anchor].co - source.relative_key.data[anchor].co)
                dest.data[index].co = basis.data[index].co + delta * factor
            dest.slider_min = key.slider_min
            dest.slider_max = key.slider_max
            dest.mute = key.mute
            driver = dest.driver_add("value").driver
            driver.type = "AVERAGE"
            variable = driver.variables.new()
            variable.name = "source_value"
            variable.type = "SINGLE_PROP"
            variable.targets[0].id_type = "KEY"
            variable.targets[0].id = surfaces[primary].data.shape_keys
            variable.targets[0].data_path = key.path_from_id("value")
        target["hairball_source_relative_keys"] = json.dumps({
            key.name: key.relative_key.name for key in shape_order if key != basis_source
        }, sort_keys=True)
    attr = target.data.attributes.new("hairball_anchor", "INT", "POINT")
    attr.data.foreach_set("value", vertex_anchors)
    if len(surfaces) > 1:
        index = target.data.attributes.new("hairball_surface_index", "INT", "POINT")
        index.data.foreach_set("value", surface_indices)
        target["hairball_surfaces"] = json.dumps([surface.name for surface in surfaces])
    target["hairball_surface"] = surfaces[primary].name
