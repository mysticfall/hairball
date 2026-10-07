"""Check native UV attachment in a factory-startup background Blender process."""
import json
import bpy


def main():
    bpy.ops.mesh.primitive_plane_add(size=2)
    surface = bpy.context.object
    surface.name = "Probe surface"
    surface.add_rest_position_attribute = True
    basis = surface.shape_key_add(name="Basis")
    key = surface.shape_key_add(name="Lift")
    for point in key.data:
        point.co.z += 0.5
    data = bpy.data.hair_curves.new("Probe attached curves")
    data.add_curves([3])
    data.position_data.foreach_set("vector", [0, 0, 0, 0, 0, 0.5, 0, 0, 1])
    data.surface = surface
    data.surface_uv_map = surface.data.uv_layers.active.name
    obj = bpy.data.objects.new("Probe groom", data)
    bpy.context.collection.objects.link(obj)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.curves.snap_curves_to_surface(attach_mode="NEAREST")
    graph = bpy.data.node_groups.new("Native deformation", "GeometryNodeTree")
    graph.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    graph.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    source = graph.nodes.new("NodeGroupInput")
    output = graph.nodes.new("NodeGroupOutput")
    deform = graph.nodes.new("GeometryNodeDeformCurvesOnSurface")
    graph.links.new(source.outputs["Geometry"], deform.inputs["Curves"])
    graph.links.new(deform.outputs["Curves"], output.inputs["Geometry"])
    mod = obj.modifiers.new("Native deformation", "NODES")
    mod.node_group = graph
    key.value = 1
    bpy.context.view_layer.update()
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    geometry = evaluated.evaluated_geometry()
    curves = geometry.curves
    report = {
        "original": [list(p.vector) for p in data.position_data],
        "evaluated": [list(p.vector) for p in curves.position_data],
        "attributes": [(a.name, a.domain, a.data_type) for a in data.attributes],
    }
    assert abs(curves.position_data[0].vector.z - 0.5) < 1e-5, report
    print("HAIRBALL_ATTACHMENT=" + json.dumps(report, indent=2))


main()
