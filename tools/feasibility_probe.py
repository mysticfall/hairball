"""Run with blender --background --factory-startup --python tools/feasibility_probe.py."""
import json
import bpy


def main():
    # Only this isolated process is modified; no existing blend file is loaded.
    data = bpy.data.hair_curves.new("Probe strands")
    data.add_curves([3, 4])
    data.position_data.foreach_set("vector", [
        0, 0, 0, 0, 0, 0.5, 0.1, 0, 1,
        1, 0, 0, 1, 0, 0.3, 1.1, 0, 0.6, 1, 0, 1,
    ])
    obj = bpy.data.objects.new("Probe groom", data)
    bpy.context.collection.objects.link(obj)
    graph = bpy.data.node_groups.new("Probe evaluation", "GeometryNodeTree")
    graph.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    graph.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    source = graph.nodes.new("NodeGroupInput")
    output = graph.nodes.new("NodeGroupOutput")
    transform = graph.nodes.new("GeometryNodeTransform")
    transform.inputs["Translation"].default_value = (0, 2, 0)
    graph.links.new(source.outputs["Geometry"], transform.inputs["Geometry"])
    graph.links.new(transform.outputs["Geometry"], output.inputs["Geometry"])
    modifier = obj.modifiers.new("Evaluated strands", "NODES")
    modifier.node_group = graph
    bpy.context.view_layer.update()
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    geometry = evaluated.evaluated_geometry()
    curves = geometry.curves
    report = {
        "version": bpy.app.version_string,
        "evaluated_curve_count": len(curves.curves),
        "evaluated_point_count": len(curves.points),
        "evaluated_root": list(curves.position_data[0].vector),
        "original_root": list(data.position_data[0].vector),
        "offsets": [item.value for item in curves.curve_offset_data],
        "attributes": [(a.name, a.domain, a.data_type) for a in curves.attributes],
    }
    assert len(curves.curves) == 2
    assert abs(curves.position_data[0].vector.y - 2) < 1e-6
    assert data.position_data[0].vector.y == 0
    deform = graph.nodes.new("GeometryNodeDeformCurvesOnSurface")
    report["deform_sockets"] = {
        "inputs": [s.name for s in deform.inputs],
        "outputs": [s.name for s in deform.outputs],
    }
    material = bpy.data.materials.new("Probe preview")
    material.use_nodes = True
    principled = material.node_tree.nodes.get("Principled BSDF")
    report["principled_inputs"] = [s.name for s in principled.inputs]
    report["render_methods"] = [
        item.identifier for item in material.bl_rna.properties["surface_render_method"].enum_items
    ]
    report["curves_ops"] = [p.identifier for p in bpy.ops.curves.snap_curves_to_surface.get_rna_type().properties]
    print("HAIRBALL_PROBE=" + json.dumps(report, indent=2))


main()
