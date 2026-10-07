"""Approximate EEVEE preview, not GodotHair scattering or temporal dithering."""
import bpy

from .evaluation import HairballError, validate_groom


def apply_groom_color(groom, color):
    """Explicit authoring edit; isolate curve data and never edit shared materials."""
    validate_groom(groom)
    if not groom.is_editable or not groom.data.is_editable:
        raise HairballError("Groom colour requires a local editable groom.")
    original = groom.data
    curves = material = None
    try:
        curves = original.copy()
        material = bpy.data.materials.new(f"{groom.name} Colour")
        material.use_nodes = True
        material.diffuse_color = tuple(color[:3]) + (1,)
        shader = material.node_tree.nodes.get('Principled BSDF')
        shader.inputs['Base Color'].default_value = material.diffuse_color
        shader.inputs['Roughness'].default_value = 0.45
        curves.materials.clear()
        curves.materials.append(material)
        indices = curves.attributes.get('material_index')
        if indices is not None:
            if indices.domain != 'CURVE' or indices.data_type != 'INT':
                raise HairballError("Unsupported groom material-index attribute.")
            indices.data.foreach_set('value', [0] * len(indices.data))
        groom.data = curves
        bpy.context.view_layer.update()
        return material
    except Exception:
        groom.data = original
        if curves is not None:
            bpy.data.hair_curves.remove(curves)
        if material is not None:
            bpy.data.materials.remove(material)
        bpy.context.view_layer.update()
        raise


def preview_material(name, attributes, coordinates, color=(0.12, 0.045, 0.02, 1), *,
                     material=None, diagnostic="SHADED"):
    material = material if material is not None else bpy.data.materials.new(name)
    material.use_nodes = True
    material.surface_render_method = "DITHERED"
    material.use_backface_culling = False
    material.diffuse_color = color
    nodes, links = material.node_tree.nodes, material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (650, 0)
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    shader.location = (350, 0)
    shader.inputs["Base Color"].default_value = color
    shader.inputs["Roughness"].default_value = 0.45
    shader.inputs["Anisotropic"].default_value = 0.6
    attrib = nodes.new("ShaderNodeTexImage")
    attrib.name = "Hairball Attributes"
    attrib.label = "R coverage / G depth / B seed"
    attrib.image = attributes
    attrib.interpolation = "Closest"
    attrib.location = (-650, 100)
    coords = nodes.new("ShaderNodeTexImage")
    coords.name = "Hairball Coordinates"
    coords.label = "RGB strand tangent / A root-to-tip data"
    coords.image = coordinates
    coords.interpolation = "Closest"
    coords.location = (-650, -250)
    separate = nodes.new("ShaderNodeSeparateColor")
    separate.location = (-350, 100)
    links.new(attrib.outputs["Color"], separate.inputs["Color"])
    links.new(separate.outputs["Red"], shader.inputs["Alpha"])
    # A tangent-space direction is decoded through the mesh TBN basis, but
    # used as a shading tangent, NOT as a perturbation of the mesh normal.
    tangent = nodes.new("ShaderNodeNormalMap")
    tangent.name = "Hairball Strand Basis"
    tangent.space = "TANGENT"
    tangent.location = (-300, -250)
    links.new(coords.outputs["Color"], tangent.inputs["Color"])
    links.new(tangent.outputs["Normal"], shader.inputs["Tangent"])
    tint = nodes.new("ShaderNodeMixRGB")
    tint.blend_type = "MIX"
    tint.location = (0, 200)
    tint.inputs[1].default_value = tuple(v * 0.45 for v in color[:3]) + (1,)
    tint.inputs[2].default_value = color
    links.new(coords.outputs["Alpha"], tint.inputs[0])
    links.new(tint.outputs[0], shader.inputs["Base Color"])
    if diagnostic == "SHADED":
        links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    else:
        emission = nodes.new("ShaderNodeEmission")
        channels = {"COVERAGE": separate.outputs["Red"], "DEPTH": separate.outputs["Green"],
                    "SEED": separate.outputs["Blue"], "DIRECTION": coords.outputs["Color"],
                    "ROOT_TIP": coords.outputs["Alpha"]}
        links.new(channels[diagnostic], emission.inputs["Color"])
        links.new(emission.outputs[0], output.inputs["Surface"])
    material["hairball_preview"] = "Approximate Principled shading; not GodotHair BSDF"
    return material
