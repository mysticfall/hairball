"""Copy evaluated strands while retaining GeometrySet ownership.

The first supported rest-space graph is intentionally narrow: one node modifier,
with a terminal Deform Curves on Surface and audited, surface-independent input.
Unsupported graphs are rejected, never guessed or rewritten on the source.
"""
from dataclasses import dataclass
import math

import bpy


class HairballError(ValueError):
    """An actionable source-validation error."""


@dataclass(frozen=True)
class Strand:
    identifier: int
    points: tuple
    radii: tuple


def validate_groom(obj):
    if obj is None or obj.type != "CURVES":
        raise HairballError("Select a modern Hair Curves object, not legacy Curve/particle hair.")
    surface = obj.data.surface
    if surface is None or surface.type != "MESH":
        raise HairballError("The groom needs an attached mesh surface.")
    uv_name = obj.data.surface_uv_map
    if not uv_name or surface.data.uv_layers.get(uv_name) is None:
        raise HairballError("The attached surface UV map is missing.")
    keys = surface.data.shape_keys
    if keys and not keys.use_relative:
        raise HairballError("Absolute shape keys are not supported; use relative keys.")
    return surface


def evaluated_strands(obj, depsgraph=None):
    """Return independent Python data in groom-local coordinates, not RNA handles."""
    if obj.type != "CURVES":
        raise HairballError("Expected a modern Hair Curves object.")
    depsgraph = depsgraph or bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    geometry = evaluated.evaluated_geometry()
    if geometry.instance_references():
        raise HairballError("Realize geometry instances before converting the groom.")
    curves = geometry.curves
    if curves is None or not len(curves.curves):
        raise HairballError("The evaluated groom contains no strands.")
    offsets = [item.value for item in curves.curve_offset_data]
    radius = curves.attributes.get("radius")
    ids = curves.attributes.get("id")
    if radius and (radius.domain != "POINT" or radius.data_type != "FLOAT"):
        raise HairballError("Expected a point-domain float radius attribute.")
    if ids and (ids.domain not in {"CURVE", "POINT"} or ids.data_type != "INT"):
        raise HairballError("Expected an integer id attribute on curves or points.")
    cyclic = curves.attributes.get("cyclic")
    result = []
    for index, (start, end) in enumerate(zip(offsets, offsets[1:])):
        if cyclic and cyclic.data[index].value:
            raise HairballError("Hair strands must be open root-to-tip curves.")
        points = tuple(tuple(curves.position_data[i].vector) for i in range(start, end))
        if len(points) < 2:
            raise HairballError(f"Strand {index} has fewer than two points.")
        radii = tuple(radius.data[i].value if radius else 0.001 for i in range(start, end))
        if not all(math.isfinite(v) for point in points for v in point):
            raise HairballError(f"Strand {index} has non-finite positions.")
        if not all(math.isfinite(v) and v >= 0 for v in radii):
            raise HairballError(f"Strand {index} has invalid radii.")
        # Native interpolation propagates IDs onto points in Blender 5.2.
        # Use the root's ID unchanged (never average/hash point IDs); duplicate
        # roots still reject below rather than inventing unstable identifiers.
        identifier = ids.data[index if ids.domain == "CURVE" else start].value if ids else index
        result.append(Strand(identifier, points, radii))
    if len({s.identifier for s in result}) != len(result):
        raise HairballError("Strand ids must be unique for deterministic baking.")
    return tuple(result)


# These nodes only use the input geometry, fields, or constant socket values.
# Nested groups are checked recursively. Unknown nodes, scene inputs and
# geometry from other objects still require a separate rest-space audit.
_REST_SAFE = {
    "NodeGroupInput", "NodeGroupOutput", "NodeReroute", "NodeFrame",
    "GeometryNodeDeformCurvesOnSurface", "GeometryNodeTransform",
    "GeometryNodeSetPosition", "GeometryNodeResampleCurve",
    "GeometryNodeSetCurveRadius", "GeometryNodeInputPosition",
    "GeometryNodeInputIndex", "GeometryNodeInputID",
    "GeometryNodeInputTangent", "GeometryNodeInputNormal",
    "GeometryNodeSplineLength", "GeometryNodeSplineParameter",
    "GeometryNodeCurveLength", "GeometryNodeInputRadius",
    "GeometryNodeInputNamedAttribute", "GeometryNodeStoreNamedAttribute",
    "ShaderNodeValue", "ShaderNodeMath", "ShaderNodeVectorMath",
    "ShaderNodeCombineXYZ", "ShaderNodeSeparateXYZ", "ShaderNodeTexNoise",
    "ShaderNodeMapRange", "ShaderNodeFloatCurve", "ShaderNodeVectorCurve",
    # Local-geometry/field primitives used by Blender 5.2's Clump/Frizz assets.
    "FunctionNodeBooleanMath", "FunctionNodeCompare", "FunctionNodeHashValue",
    "FunctionNodeRandomValue", "FunctionNodeInputBool",
    "GeometryNodeAccumulateField", "GeometryNodeCaptureAttribute",
    "GeometryNodeCurveSplineType", "GeometryNodeFieldAtIndex", "GeometryNodeFieldOnDomain",
    "GeometryNodeGetGeometryComponent", "GeometryNodeInputSplineResolution",
    "GeometryNodeJoinGeometry", "GeometryNodeSampleCurve", "GeometryNodeSampleIndex",
    "GeometryNodeSetSplineResolution", "GeometryNodeSwitch", "ShaderNodeMix",
    "GeometryNodeAttributeStatistic", "GeometryNodeCurveOfPoint",
    "GeometryNodeCurveEndpointSelection", "GeometryNodePointsOfCurve",
    "GeometryNodeOffsetPointInCurve", "GeometryNodeAttributeDomainSize",
    "GeometryNodeCurveToPoints", "GeometryNodeDeleteGeometry", "GeometryNodeMergeByDistance",
    "GeometryNodeMeshToPoints", "GeometryNodeSampleNearest", "GeometryNodeSeparateComponents",
    "GeometryNodeSeparateGeometry",
}


def _audit_local_graph(graph, ancestors=(), *, root=True, surface=None):
    """Audit nested contents, never trust an asset/group's display name.

    With one modifier, these attributes originate in the undeformed input data
    or preceding audited local nodes. Object/collection/image/scene inputs and
    animated group values remain unsupported, including inside nested groups.
    """
    if graph in ancestors:
        raise HairballError("Recursive node groups cannot be audited for rest recovery.")
    if graph.animation_data and (graph.animation_data.drivers or graph.animation_data.action):
        raise HairballError("Animated/driven node graphs require a separate rest-space audit.")
    for node in graph.nodes:
        if node.bl_idname == "GeometryNodeGroup":
            if node.node_tree is None:
                raise HairballError("A nested node group is missing its node tree.")
            from .native import is_interpolation, audit_interpolation
            if is_interpolation(node):
                audit_interpolation(node, surface)
                continue
            _audit_local_graph(node.node_tree, (*ancestors, graph), root=False, surface=surface)
        elif node.bl_idname not in _REST_SAFE:
            raise HairballError("Rest-space graph not yet audited: " + node.bl_idname)
        elif not root and node.bl_idname == "GeometryNodeDeformCurvesOnSurface":
            raise HairballError("Surface deformation must remain terminal, not inside a group.")
        if node.bl_idname in {"GeometryNodeInputNamedAttribute", "GeometryNodeStoreNamedAttribute"}:
            socket = node.inputs["Name"]
            name = socket.default_value
            mask = surface.data.attributes.get(name) if surface and name.startswith('hairball_density_') else None
            safe_mask = (mask is not None and mask.domain == 'FACE' and mask.data_type == 'FLOAT'
                         and all(math.isfinite(v.value) and 0 <= v.value <= 1 for v in mask.data))
            if socket.is_linked or (not safe_mask and name not in {
                    "position", "radius", "id", "rest_position", "guide_curve_index", "surface_uv_coordinate"}):
                raise HairballError("Unverified named attributes cannot drive rest-space geometry.")
        if any(socket.type in {"OBJECT", "COLLECTION", "IMAGE", "MATERIAL"}
               for socket in node.inputs if not socket.is_unavailable):
            raise HairballError("Scene/datablock inputs inside node groups require a separate rest-space audit.")


def _rest_graph(obj):
    modifiers = [m for m in obj.modifiers if m.show_viewport]
    if len(modifiers) != 1 or modifiers[0].type != "NODES":
        raise HairballError("Rest recovery currently requires one visible Geometry Nodes modifier.")
    graph = modifiers[0].node_group
    if graph is None:
        raise HairballError("The groom's Geometry Nodes modifier has no node group.")
    _audit_local_graph(graph, surface=obj.data.surface)
    outputs = [n for n in graph.nodes if n.bl_idname == "NodeGroupOutput" and n.is_active_output]
    deformers = [n for n in graph.nodes if n.bl_idname == "GeometryNodeDeformCurvesOnSurface"]
    if len(outputs) != 1 or len(deformers) != 1:
        raise HairballError("Rest recovery needs one active output and one native surface deformer.")
    output = outputs[0]
    geometry_inputs = [s for s in output.inputs if s.type == "GEOMETRY"]
    if len(geometry_inputs) != 1 or len(geometry_inputs[0].links) != 1:
        raise HairballError("The graph needs one connected geometry output.")
    last_link = geometry_inputs[0].links[0]
    deform = deformers[0]
    if deform.mute:
        raise HairballError("Enable the native surface deformer before conversion.")
    if last_link.from_node != deform or len(deform.inputs["Curves"].links) != 1:
        raise HairballError("Deform Curves on Surface must be the terminal geometry node.")
    return modifiers[0], deform.name, geometry_inputs[0].identifier


def rest_strands(obj, context=None, *, resample=False):
    """Bypass a terminal native deformer on temporary copies, keeping the source intact."""
    context = context or bpy.context
    validate_groom(obj)
    modifier, deform_name, output_identifier = _rest_graph(obj)
    clone = None
    graph = None
    try:
        graph = modifier.node_group.copy()
        deform = graph.nodes[deform_name]
        upstream = deform.inputs["Curves"].links[0].from_socket
        output = next(n for n in graph.nodes if n.bl_idname == "NodeGroupOutput" and n.is_active_output)
        target = next(s for s in output.inputs if s.identifier == output_identifier)
        for link in tuple(target.links):
            graph.links.remove(link)
        if resample:
            # Curve positions are control points for Catmull-Rom/Bezier/NURBS,
            # not necessarily the rendered strand path. Ask Blender to evaluate
            # each spline at its native resolution on the temporary graph only.
            sampler = graph.nodes.new("GeometryNodeResampleCurve")
            sampler.inputs["Mode"].default_value = "Evaluated"
            graph.links.new(upstream, sampler.inputs["Curve"])
            graph.links.new(sampler.outputs["Curve"], target)
        else:
            graph.links.new(upstream, target)
        clone = obj.copy()
        clone.name = "Hairball temporary rest evaluation"
        context.scene.collection.objects.link(clone)
        clone.modifiers[modifier.name].node_group = graph
        clone.hide_viewport = False
        clone.hide_set(False)
        context.view_layer.update()
        return evaluated_strands(clone, context.evaluated_depsgraph_get())
    finally:
        if clone is not None:
            bpy.data.objects.remove(clone, do_unlink=True)
        if graph is not None:
            bpy.data.node_groups.remove(graph)
        context.view_layer.update()
