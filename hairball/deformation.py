"""Root anchoring and uniform skinning/relative-morph transfer."""
import json
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


def transfer(surface, target, vertex_anchors):
    """Prevalidate before adding groups/keys; caller owns the new output object.

    All vertex indices in vertex_anchors refer to the ORIGINAL attachment mesh.
    The target is a new rest-space mesh and must not have existing keys/groups.
    """
    if surface.type != "MESH" or target.type != "MESH":
        raise HairballError("Deformation transfer requires mesh objects.")
    if target.data.shape_keys or len(target.vertex_groups):
        raise HairballError("Transfer requires a new mesh without keys or vertex groups.")
    if len(vertex_anchors) != len(target.data.vertices):
        raise HairballError("Every card vertex needs a root anchor.")
    if any(i < 0 or i >= len(surface.data.vertices) for i in vertex_anchors):
        raise HairballError("A root anchor references a missing surface vertex.")
    if abs(target.matrix_world.determinant()) < 1e-12:
        raise HairballError("The result object has a singular transform.")
    shape_order, _ = _shape_layout(surface)
    armatures = [m for m in surface.modifiers if m.type == "ARMATURE" and m.show_viewport]
    if len(armatures) > 1:
        raise HairballError("Multiple surface armature modifiers are not yet supported.")
    skin = armatures[0] if armatures else None
    weights = {}
    if skin:
        if skin.object is None or not skin.use_vertex_groups or skin.use_bone_envelopes or skin.vertex_group:
            raise HairballError("Use an unmasked vertex-group armature, without bone envelopes.")
        deform_names = {b.name for b in skin.object.data.bones if b.use_deform}
        groups = {g.index: g.name for g in surface.vertex_groups if g.name in deform_names}
        for anchor in set(vertex_anchors):
            weights[anchor] = {
                groups[g.group]: g.weight for g in surface.data.vertices[anchor].groups
                if g.group in groups and g.weight > 0
            }
            if not weights[anchor]:
                raise HairballError(f"Root anchor {anchor} has no deform-bone weights.")
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
            for name, weight in weights[anchor].items():
                groups[name].add([index], weight, "REPLACE")
        modifier = target.modifiers.new("Hairball attachment", "ARMATURE")
        modifier.object = skin.object
        modifier.use_deform_preserve_volume = skin.use_deform_preserve_volume
        modifier.use_vertex_groups = True
        modifier.use_bone_envelopes = False
    if shape_order:
        conversion = (target.matrix_world.inverted() @ surface.matrix_world).to_3x3()
        created = {}
        basis_source = surface.data.shape_keys.reference_key
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
            mask = surface.vertex_groups.get(key.vertex_group) if key.vertex_group else None
            for index, anchor in enumerate(vertex_anchors):
                factor = 1.0
                if key.vertex_group:
                    factor = 0.0
                    if mask:
                        factor = next((g.weight for g in surface.data.vertices[anchor].groups
                                       if g.group == mask.index), 0.0)
                delta = conversion @ (key.data[anchor].co - key.relative_key.data[anchor].co)
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
            variable.targets[0].id = surface.data.shape_keys
            variable.targets[0].data_path = key.path_from_id("value")
        target["hairball_source_relative_keys"] = json.dumps({
            key.name: key.relative_key.name for key in shape_order if key != basis_source
        }, sort_keys=True)
    attr = target.data.attributes.new("hairball_anchor", "INT", "POINT")
    attr.data.foreach_set("value", vertex_anchors)
    target["hairball_surface"] = surface.name
