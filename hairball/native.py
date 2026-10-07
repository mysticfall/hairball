"""Strict native surface-interpolation audit and explicit authoring setup."""
import hashlib
import json
import math
from pathlib import Path
import uuid

import bpy

from .evaluation import HairballError

# Content signature of the installed/audited Blender 5.2.2 native asset, NOT
# a name check or a user-set trust flag. Changes in native asset code require
# re-running the posed/rest tests and reviewing a new signature.
INTERPOLATION_SIGNATURE = "07f7646f5273d8d549567d85d0edd4a8ead397b7d210effc6a40fda93bf1ddb0"

_UI = {'name', 'label', 'location', 'width', 'height', 'dimensions', 'select',
       'parent', 'color', 'use_custom_color', 'show_options', 'show_preview',
       'show_texture', 'node_tree'}


def _values(value, depth=0):
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, bpy.types.ID):
        raise HairballError('Native interpolation has an unexpected datablock reference.')
    if hasattr(value, 'bl_rna'):
        if depth > 8:
            raise HairballError('Native asset configuration is too deeply nested to audit.')
        result = {}
        for prop in value.bl_rna.properties:
            if prop.identifier in {'rna_type', 'id_data'}:
                continue
            if prop.is_readonly and prop.type != 'COLLECTION':
                continue
            result[prop.identifier] = _values(getattr(value, prop.identifier), depth + 1)
        return result
    return [_values(v, depth + 1) for v in value]


def asset_signature(graph, ancestors=()):
    if graph in ancestors:
        raise HairballError('Recursive native asset dependencies cannot be audited.')
    if graph.animation_data and (graph.animation_data.action or graph.animation_data.drivers):
        raise HairballError('Animated native asset dependencies are unsupported.')
    nodes = []
    for node in sorted(graph.nodes, key=lambda n: n.name):
        properties = {}
        for prop in node.bl_rna.properties:
            if prop.identifier in _UI | {'rna_type', 'id_data', 'inputs', 'outputs', 'internal_links'}:
                continue
            if prop.is_readonly and prop.type != 'COLLECTION':
                continue
            properties[prop.identifier] = _values(getattr(node, prop.identifier))
        sockets = []
        for socket in (*node.inputs, *node.outputs):
            sockets.append((socket.identifier, socket.bl_idname,
                            _values(socket.default_value) if hasattr(socket, 'default_value') else None))
        nodes.append((node.name, node.bl_idname, properties, sockets,
                      asset_signature(node.node_tree, (*ancestors, graph)) if node.type == 'GROUP' else None))
    links = sorted((l.from_node.name, l.from_socket.identifier, l.to_node.name, l.to_socket.identifier)
                   for l in graph.links)
    interface = [(s.name, s.in_out, s.socket_type,
                  _values(s.default_value) if hasattr(s, 'default_value') else None)
                 for s in graph.interface.items_tree if s.item_type == 'SOCKET']
    encoded = json.dumps((nodes, links, interface), sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(encoded).hexdigest()


def is_interpolation(node):
    return (node.bl_idname == 'GeometryNodeGroup' and node.node_tree is not None
            and node.inputs.get('Resting Surface') is not None
            and node.inputs.get('Interpolation Guides') is not None)


def audit_interpolation(node, surface):
    if asset_signature(node.node_tree) != INTERPOLATION_SIGNATURE:
        raise HairballError('Interpolation asset contents differ from the audited Blender 5.2.2 asset.')
    for name, expected in (('Resting Surface', True), ('Viewport Amount', 1.0)):
        socket = node.inputs[name]
        if socket.is_linked or socket.default_value != expected:
            raise HairballError(f'Native interpolation requires unlinked {name} = {expected}.')
    if node.inputs['Mask Texture'].is_linked or node.inputs['Mask Texture'].default_value is not None:
        raise HairballError('Image density masks require a separate interpolation audit; use the surface density attribute.')
    if not surface.add_rest_position_attribute:
        raise HairballError('Enable Add Rest Position on the attachment surface before interpolation.')
    if any(m.show_viewport and m.type not in {'ARMATURE', 'SUBSURF'} for m in surface.modifiers):
        raise HairballError('Interpolated surfaces currently support only Armature and Subdivision modifiers.')


def asset_path():
    return Path(bpy.utils.system_resource('DATAFILES', path='assets')) / 'nodes/procedural_hair_node_assets.blend'


_SETTINGS = {'interpolation_density': 'Density', 'interpolation_distance': 'Distance to Guides',
             'interpolation_guides': 'Interpolation Guides'}


def _editable_interpolation(groom):
    from .evaluation import validate_groom, _rest_graph
    validate_groom(groom)
    if not groom.is_editable:
        raise HairballError('Select a local editable groom to adjust interpolation.')
    modifier, _, _ = _rest_graph(groom)
    nodes = [n for n in modifier.node_group.nodes if is_interpolation(n)]
    if len(nodes) != 1:
        raise HairballError('Sidebar adjustment requires exactly one top-level native interpolation node.')
    node = nodes[0]
    if any(node.inputs[name].is_linked for name in _SETTINGS.values()):
        raise HairballError('Interpolation controls are driven by fields; edit those links in Geometry Nodes.')
    return modifier, node


def interpolation_settings(groom):
    """Read actual node values, without scene/UI mutation or cached trust flags."""
    _, node = _editable_interpolation(groom)
    values = {key: node.inputs[name].default_value for key, name in _SETTINGS.items()}
    if (not .01 <= values['interpolation_density'] <= 1000000
            or not math.isfinite(values['interpolation_distance']) or values['interpolation_distance'] < .00001
            or not 1 <= values['interpolation_guides'] <= 64):
        raise HairballError('Current native values are outside the supported sidebar ranges.')
    return values


def update_interpolation(groom, settings, context=None):
    """Explicit, transactional authoring edit; preserve guides, mask and outputs."""
    from .evaluation import rest_strands
    context = context or bpy.context
    modifier, node = _editable_interpolation(groom)
    values = {key: getattr(settings, key) for key in _SETTINGS}
    if (not .01 <= values['interpolation_density'] <= 1000000
            or not math.isfinite(values['interpolation_distance']) or values['interpolation_distance'] < .00001
            or not 1 <= values['interpolation_guides'] <= 64):
        raise HairballError('Density/distance/guide count are outside the supported sidebar ranges.')
    surface = groom.data.surface
    # Honor the actual linked FACE mask, not a possibly stale custom property.
    # Other native field expressions retain a conservative whole-area bound.
    weights = None
    socket = node.inputs['Density Mask']
    if socket.is_linked:
        field = socket.links[0].from_node
        if (field.bl_idname == 'GeometryNodeInputNamedAttribute'
                and not field.inputs['Name'].is_linked):
            mask = surface.data.attributes.get(field.inputs['Name'].default_value)
            if mask is not None and mask.data_type == 'FLOAT' and mask.domain == 'FACE':
                weights = [v.value for v in mask.data]
    else:
        weights = [max(0, min(1, socket.default_value))] * len(surface.data.polygons)
    area = _growth_area(groom, surface, set(range(len(surface.data.polygons))), weights)
    if area * values['interpolation_density'] > 100000:
        raise HairballError('Estimated interpolation exceeds 100,000 strands; reduce Density.')
    old = modifier.node_group
    graph = old.copy()
    try:
        new_node = graph.nodes[node.name]
        for key, name in _SETTINGS.items():
            new_node.inputs[name].default_value = values[key]
        modifier.node_group = graph
        context.view_layer.update()
        count = len(rest_strands(groom))
        if count > 100000:
            raise HairballError('Evaluated interpolation exceeds 100,000 strands; reduce Density.')
        return count
    except Exception:
        modifier.node_group = old
        bpy.data.node_groups.remove(graph)
        context.view_layer.update()
        raise


def _uv_overlap(mesh, faces, uv_name):
    """Positive-area triangle overlap, including against excluded faces.

    Shared UV edges are fine. A sweep avoids comparing distant UV islands.
    This is deliberately conservative: coincident duplicate faces also reject.
    """
    mesh.calc_loop_triangles()
    uv = mesh.uv_layers[uv_name].data
    triangles = []
    for tri in mesh.loop_triangles:
        points = [tuple(uv[i].uv) for i in tri.loops]
        if not all(math.isfinite(v) for p in points for v in p):
            raise HairballError('The attachment UV map has non-finite coordinates.')
        area = _cross(points[0], points[1], points[2])
        if abs(area) < 1e-12:
            if tri.polygon_index in faces:
                raise HairballError('Growth faces need non-degenerate UV triangles.')
            continue
        triangles.append((min(p[0] for p in points), max(p[0] for p in points),
                          min(p[1] for p in points), max(p[1] for p in points), tri.polygon_index, points))
    active = []
    for tri in sorted(triangles):
        active = [other for other in active if other[1] > tri[0] + 1e-12]
        for other in active:
            if ((tri[4] not in faces and other[4] not in faces)
                    or min(tri[3], other[3]) <= max(tri[2], other[2]) + 1e-12):
                continue
            polygon = tri[5][:]
            sign = 1 if _cross(*other[5]) > 0 else -1
            for a, b in zip(other[5], other[5][1:] + other[5][:1]):
                clipped = []
                for p, q in zip(polygon, polygon[1:] + polygon[:1]):
                    dp, dq = sign * _cross(a, b, p), sign * _cross(a, b, q)
                    if dp >= 0:
                        clipped.append(p)
                    if (dp >= 0) != (dq >= 0):
                        factor = dp / (dp - dq)
                        clipped.append(tuple(p[i] + factor * (q[i] - p[i]) for i in range(2)))
                polygon = clipped
                if not polygon:
                    break
            area = abs(sum(p[0]*q[1] - q[0]*p[1]
                           for p,q in zip(polygon, polygon[1:] + polygon[:1]))) / 2
            if area > 1e-12:
                raise HairballError('Growth UVs overlap another surface face; use unique UVs or an attachment patch.')
        active.append(tri)


def _cross(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])


def _growth_area(groom, surface, faces, weights=None):
    determinant = groom.matrix_world.determinant()
    if determinant == 0 or not math.isfinite(determinant):
        raise HairballError('The groom transform must be invertible.')
    surface.data.calc_loop_triangles()
    basis = surface.data.shape_keys.reference_key.data if surface.data.shape_keys else None
    transform = groom.matrix_world.inverted() @ surface.matrix_world
    area = 0
    for tri in surface.data.loop_triangles:
        if tri.polygon_index in faces:
            points = [transform @ (basis[v].co if basis else surface.data.vertices[v].co) for v in tri.vertices]
            if not all(math.isfinite(v) for point in points for v in point):
                raise HairballError('Growth surface rest positions must be finite.')
            area += ((points[1]-points[0]).cross(points[2]-points[0]).length / 2
                     * (weights[tri.polygon_index] if weights is not None else 1))
    return area


def prepare_interpolation(groom, settings, context=None):
    """Create a new independent groom with native interpolation, never rewrite input.

    Explicit authoring setup adds one fresh FACE density attribute to the source
    surface. This is a persistent native mask, not an Add/Slide sculpt restriction.
    """
    from .evaluation import validate_groom, _rest_graph, rest_strands
    context = context or bpy.context
    surface = validate_groom(groom)
    if (not math.isfinite(settings.interpolation_density) or settings.interpolation_density <= 0
            or not math.isfinite(settings.interpolation_distance) or settings.interpolation_distance <= 0):
        raise HairballError('Density and Guide Distance must be finite positive values.')
    modifier, deform_name, _ = _rest_graph(groom)
    if any(is_interpolation(n) for n in modifier.node_group.nodes):
        raise HairballError('This groom already has native interpolation; edit its node settings instead.')
    if not surface.add_rest_position_attribute:
        raise HairballError('Enable Add Rest Position on the attachment surface first.')
    if surface.data.users != 1 or not surface.data.is_editable:
        raise HairballError('Interpolation masks require a local, single-user attachment mesh.')
    region = groom.get('hairball_growth_region', 'WHOLE_SURFACE')
    faces = set(groom.get('hairball_growth_faces', [])) if region == 'SELECTED_FACES' else {
        p.index for p in surface.data.polygons if not p.hide}
    if not faces or any(not isinstance(i, int) or i < 0 or i >= len(surface.data.polygons) for i in faces):
        raise HairballError('The stored growth-face region is missing/invalid; recreate its guides.')
    _uv_overlap(surface.data, faces, groom.data.surface_uv_map)
    estimated_area = _growth_area(groom, surface, faces)
    if estimated_area * settings.interpolation_density > 100000:
        raise HairballError('Estimated interpolation exceeds 100,000 strands; reduce Density or use a smaller patch.')
    before_groups = set(bpy.data.node_groups)
    clone = data = graph = mask = None
    try:
        with bpy.data.libraries.load(str(asset_path()), link=False) as (source, target):
            target.node_groups = ['Interpolate Hair Curves']
        asset = target.node_groups[0]
        if asset is None or asset_signature(asset) != INTERPOLATION_SIGNATURE:
            raise HairballError('Installed native interpolation asset differs from the audited Blender 5.2.2 contents.')
        graph = modifier.node_group.copy()
        deform = graph.nodes[deform_name]
        node = graph.nodes.new('GeometryNodeGroup')
        node.node_tree = asset
        node.label = 'Native density — edit here'
        node.inputs['Resting Surface'].default_value = True
        node.inputs['Viewport Amount'].default_value = 1
        node.inputs['Density'].default_value = settings.interpolation_density
        node.inputs['Distance to Guides'].default_value = settings.interpolation_distance
        node.inputs['Interpolation Guides'].default_value = settings.interpolation_guides
        node.inputs['Seed'].default_value = settings.seed
        mask = surface.data.attributes.new('hairball_density_' + uuid.uuid4().hex[:12], 'FLOAT', 'FACE')
        mask.data.foreach_set('value', [1.0 if p.index in faces else 0.0 for p in surface.data.polygons])
        field = graph.nodes.new('GeometryNodeInputNamedAttribute')
        field.data_type = 'FLOAT'
        field.inputs['Name'].default_value = mask.name
        graph.links.new(field.outputs['Attribute'], node.inputs['Density Mask'])
        graph.links.new(deform.inputs['Curves'].links[0].from_socket, node.inputs['Geometry'])
        graph.links.new(node.outputs['Geometry'], deform.inputs['Curves'])
        node.location = (deform.location.x - 220, deform.location.y)
        field.location = (node.location.x - 220, node.location.y - 200)
        data = groom.data.copy()
        clone = groom.copy()
        clone.data = data
        clone.name = groom.name + ' Interpolated'
        clone.modifiers[modifier.name].node_group = graph
        (groom.users_collection[0] if groom.users_collection else context.scene.collection).objects.link(clone)
        clone['hairball_density_attribute'] = mask.name
        clone['hairball_guide_source'] = groom
        context.view_layer.update()
        count = len(rest_strands(clone))
        if count > 100000:
            raise HairballError('Evaluated interpolation exceeds 100,000 strands; reduce Density.')
        return clone, count
    except Exception:
        if clone is not None:
            bpy.data.objects.remove(clone, do_unlink=True)
        if data is not None:
            bpy.data.hair_curves.remove(data)
        if mask is not None:
            surface.data.attributes.remove(mask)
        # Includes every freshly appended dependency and the copied root graph.
        owned = set(bpy.data.node_groups) - before_groups
        while owned:
            unused = [g for g in owned if g.users == 0 or g.use_fake_user and g.users == 1]
            if not unused:
                break
            for group in unused:
                owned.remove(group)
                bpy.data.node_groups.remove(group)
        context.view_layer.update()
        raise
