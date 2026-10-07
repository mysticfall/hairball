"""Native, UV-attached guide creation without applying the source rig or modifiers."""
from bisect import bisect_right
from dataclasses import dataclass
import math
import random

import bpy
from mathutils import Vector

from .evaluation import HairballError


@dataclass(frozen=True)
class Root:
    position: tuple
    direction: tuple
    uv: tuple
    face: int


def _barycentric_2d(point, triangle):
    a, b, c = triangle
    edge1, edge2, offset = b - a, c - a, point - a
    determinant = edge1.x * edge2.y - edge1.y * edge2.x
    if abs(determinant) < 1e-14:
        return None
    v = (offset.x * edge2.y - offset.y * edge2.x) / determinant
    w = (edge1.x * offset.y - edge1.y * offset.x) / determinant
    weights = (1 - v - w, v, w)
    return weights if min(weights) >= -1e-7 else None


class _UVIndex:
    """Uniform UV grid avoids comparing every new root to every surface triangle."""

    def __init__(self, triangles):
        self.triangles = triangles
        self.cells = {}
        points = [point for tri in triangles for point in tri[1]]
        self.minimum = Vector((min(p.x for p in points), min(p.y for p in points)))
        self.extent = Vector((max(p.x for p in points), max(p.y for p in points))) - self.minimum
        if min(self.extent) < 1e-12:
            raise HairballError("The surface UV map has no usable area.")
        self.size = min(128, max(1, int(math.sqrt(len(triangles)))))
        for index, (_, uvs, _, _) in enumerate(triangles):
            lower = self.cell(Vector((min(p.x for p in uvs), min(p.y for p in uvs))))
            upper = self.cell(Vector((max(p.x for p in uvs), max(p.y for p in uvs))))
            for x in range(lower[0], upper[0] + 1):
                for y in range(lower[1], upper[1] + 1):
                    self.cells.setdefault((x, y), []).append(index)

    def cell(self, uv):
        return tuple(min(self.size - 1, max(0, int((uv[i] - self.minimum[i]) / self.extent[i] * self.size)))
                     for i in range(2))

    def validate_root(self, uv, position, tolerance, source_face):
        found = False
        for index in self.cells.get(self.cell(uv), ()):
            positions, uvs, _, candidate_face = self.triangles[index]
            weights = _barycentric_2d(uv, uvs)
            if weights is None:
                continue
            found = True
            mapped = sum((p * weight for p, weight in zip(positions, weights)), Vector())
            # Coincident duplicate faces can deform independently later, so
            # matching rest positions alone do not establish unique attachment.
            # Shared UV edges between adjacent faces are not interior overlaps.
            overlaps_interior = candidate_face != source_face and min(weights) > 1e-7
            if (mapped - position).length > tolerance or overlaps_interior:
                raise HairballError("Overlapping surface UVs make a sampled root ambiguous. Use a unique UV map.")
        if not found:
            raise HairballError("A sampled root could not be resolved on the surface UV map.")


def sample_roots(surface, count=64, seed=0, selected_faces=False):
    """Sample original Basis geometry in physical area, including while posed.

    Selection is read after the caller flushes Edit Mode. UV uniqueness is
    checked at every sampled root against the entire mesh, not just growth faces.
    """
    if surface is None or surface.type != "MESH":
        raise HairballError("Select a mesh to create an attached groom.")
    if surface.mode != "OBJECT":
        raise HairballError("Flush mesh edits before sampling guide roots.")
    if surface.library or surface.data.library or not surface.is_editable:
        raise HairballError("Make the attachment mesh local and editable first.")
    unsupported = [m.name for m in surface.modifiers
                   if m.show_viewport and m.type not in {"ARMATURE", "SUBSURF"}]
    if unsupported:
        raise HairballError("Surface modifiers not yet audited for UV attachment: " + ", ".join(unsupported)
                            + ". Current setup supports Armature and Subdivision only.")
    if count < 1:
        raise HairballError("Guide count must be positive.")
    mesh = surface.data
    uv_layer = mesh.uv_layers.active
    if uv_layer is None:
        raise HairballError("The surface needs an active UV map for native hair attachment.")
    if not mesh.polygons:
        raise HairballError("The attachment surface has no faces.")
    if selected_faces and not any(face.select and not face.hide for face in mesh.polygons):
        raise HairballError("Select at least one visible face before creating the groom.")
    keys = mesh.shape_keys
    if keys and not keys.use_relative:
        raise HairballError("Use a surface with relative shape keys, not absolute keys.")
    if abs(surface.matrix_world.determinant()) < 1e-12:
        raise HairballError("The surface has a singular transform.")
    basis = keys.reference_key.data if keys else mesh.vertices
    mesh.calc_loop_triangles()
    matrix = surface.matrix_world
    inverse = matrix.inverted().to_3x3()
    normal_matrix = inverse.transposed()
    triangles = []
    distribution = []
    cumulative = []
    total_area = 0.0
    for tri in mesh.loop_triangles:
        positions = tuple(basis[i].co.copy() for i in tri.vertices)
        uvs = tuple(uv_layer.data[i].uv.copy() for i in tri.loops)
        if not all(math.isfinite(v) for p in positions + uvs for v in p):
            raise HairballError("The mesh or UV map contains non-finite coordinates.")
        world = tuple(matrix @ p for p in positions)
        normal = (world[1] - world[0]).cross(world[2] - world[0])
        area = normal.length / 2
        uv_area = abs((uvs[1].x - uvs[0].x) * (uvs[2].y - uvs[0].y)
                      - (uvs[1].y - uvs[0].y) * (uvs[2].x - uvs[0].x))
        if area < 1e-14:
            continue
        face = mesh.polygons[tri.polygon_index]
        grows = (face.select and not face.hide) if selected_faces else not face.hide
        if uv_area < 1e-14:
            if grows:
                raise HairballError("A growth face has degenerate UVs. Unwrap it before creating hair.")
            continue
        local_normal = (positions[1] - positions[0]).cross(positions[2] - positions[0])
        direction = inverse @ (normal_matrix @ local_normal).normalized()
        triangles.append((positions, uvs, tuple(direction), tri.polygon_index))
        if grows:
            total_area += area
            distribution.append(len(triangles) - 1)
            cumulative.append(total_area)
    if not distribution:
        raise HairballError("The growth region has no usable surface area.")
    index = _UVIndex(triangles)
    # Tolerance in surface-local coordinates, scaled to mesh size.
    tolerance = max(1e-6, max((v.co.length for v in basis), default=1) * 1e-6)
    rng = random.Random(seed)
    roots = []
    for _ in range(count):
        choice = min(bisect_right(cumulative, rng.random() * total_area), len(distribution) - 1)
        positions, uvs, direction, face = triangles[distribution[choice]]
        # Uniform triangle-area sampling, kept away from exact UV boundaries.
        u = math.sqrt(max(1e-12, rng.random()))
        v = rng.random()
        weights = (1 - u, u * (1 - v), u * v)
        position = sum((p * w for p, w in zip(positions, weights)), Vector())
        uv = sum((p * w for p, w in zip(uvs, weights)), Vector((0, 0)))
        index.validate_root(uv, position, tolerance, face)
        roots.append(Root(tuple(position), direction, tuple(uv), face))
    return tuple(roots), uv_layer.name


def _deformation_graph(name):
    graph = bpy.data.node_groups.new(name, "GeometryNodeTree")
    try:
        graph.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
        graph.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
        source = graph.nodes.new("NodeGroupInput")
        source.location = (-250, 0)
        deform = graph.nodes.new("GeometryNodeDeformCurvesOnSurface")
        deform.location = (0, 0)
        output = graph.nodes.new("NodeGroupOutput")
        output.location = (250, 0)
        graph.links.new(source.outputs["Geometry"], deform.inputs["Curves"])
        graph.links.new(deform.outputs["Curves"], output.inputs["Geometry"])
        return graph
    except Exception:
        bpy.data.node_groups.remove(graph)
        raise


def create_groom(surface, count=64, length=0.1, points=8, seed=0, selected_faces=False,
                 context=None):
    """Create a new native groom. On failure remove only new data and restore setup.

    No source transforms, weights, morph values, modifiers, or geometry are
    applied/rewritten. Native surface rest-position output is enabled explicitly.
    """
    context = context or bpy.context
    if not math.isfinite(length) or length <= 0 or points < 2:
        raise HairballError("Guide length must be positive and guides need at least two points.")
    roots, uv_name = sample_roots(surface, count, seed, selected_faces)
    curves = obj = graph = None
    previous_rest = surface.add_rest_position_attribute
    try:
        curves = bpy.data.hair_curves.new(f"{surface.name} Hairball Guides")
        curves.add_curves([points] * count)
        positions, radii = [], []
        for root in roots:
            position, direction = Vector(root.position), Vector(root.direction)
            for i in range(points):
                parameter = i / (points - 1)
                positions.extend(position + direction * length * parameter)
                radii.append(max(length * 0.002 * (1 - parameter), length * 0.0001))
        curves.position_data.foreach_set("vector", positions)
        curves.attributes.new("radius", "FLOAT", "POINT").data.foreach_set("value", radii)
        # Let native sculpt tools own curve topology. Without an explicit id
        # attribute Blender's curve order provides deterministic identities;
        # native Add need not maintain a Hairball-specific id allocation scheme.
        curves.attributes.new("surface_uv_coordinate", "FLOAT2", "CURVE").data.foreach_set(
            "vector", [value for root in roots for value in root.uv])
        curves.attributes.new("hairball_source_face", "INT", "CURVE").data.foreach_set(
            "value", [root.face for root in roots])
        curves.surface = surface
        curves.surface_uv_map = uv_name
        obj = bpy.data.objects.new(curves.name, curves)
        collection = surface.users_collection[0] if surface.users_collection else context.scene.collection
        collection.objects.link(obj)
        # Following the surface object also follows its animated object transform;
        # actual vertex skin/morph deformation remains native UV attachment.
        obj.parent = surface
        obj.matrix_parent_inverse.identity()
        obj.matrix_basis.identity()
        graph = _deformation_graph(f"{obj.name} Surface Deformation")
        modifier = obj.modifiers.new("Hairball Native Surface Deformation", "NODES")
        modifier.node_group = graph
        obj["hairball_groom_version"] = 1
        obj["hairball_seed"] = seed
        obj["hairball_growth_region"] = "SELECTED_FACES" if selected_faces else "WHOLE_SURFACE"
        if selected_faces:
            obj["hairball_growth_faces"] = [p.index for p in surface.data.polygons if p.select and not p.hide]
        obj["hairball_guide_length"] = length
        surface.add_rest_position_attribute = True
        context.view_layer.update()
        return obj
    except Exception:
        if obj is not None:
            bpy.data.objects.remove(obj, do_unlink=True)
        if graph is not None:
            bpy.data.node_groups.remove(graph)
        if curves is not None:
            bpy.data.hair_curves.remove(curves)
        surface.add_rest_position_attribute = previous_rest
        context.view_layer.update()
        raise
