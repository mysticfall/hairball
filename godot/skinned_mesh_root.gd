@tool
extends EditorScenePostImport
## Import a single skinned mesh as an attachable MeshInstance3D scene.
## Instantiate the resulting scene directly under a compatible Skeleton3D.


func _post_import(scene: Node) -> Object:
	var meshes: Array[MeshInstance3D] = []
	_collect_meshes(scene, meshes)
	if meshes.size() != 1:
		return _unchanged(scene, "Expected exactly one mesh, found %d." % meshes.size())
	var source := meshes[0]
	if source.mesh == null or source.skin == null:
		return _unchanged(scene, "The mesh must have both Mesh and Skin resources.")
	var skeleton := source.get_node_or_null(source.skeleton) as Skeleton3D
	if skeleton == null:
		return _unchanged(scene, "The mesh's imported Skeleton3D could not be resolved.")
	if source.skin.get_bind_count() == 0:
		return _unchanged(scene, "The skin has no bone bindings.")
	for index in range(source.skin.get_bind_count()):
		var bone_name := source.skin.get_bind_name(index)
		if bone_name == &"" or skeleton.find_bone(bone_name) < 0:
			return _unchanged(scene, "Enable Skins > Use Named Skins and reimport; every bind must name an imported bone.")
	var skeleton_transform := _scene_transform(skeleton)
	if is_zero_approx(skeleton_transform.basis.determinant()):
		return _unchanged(scene, "The imported skeleton has a singular transform.")
	# Do not use global_transform: import nodes need not be inside a SceneTree.
	var attachment_transform := skeleton_transform.affine_inverse() * _scene_transform(source)
	# Duplicate stored mesh-instance properties, including material overrides and
	# blend-shape values, but not attached scripts, signals or scene instantiation.
	var result := source.duplicate(0) as MeshInstance3D
	if result == null:
		return _unchanged(scene, "Could not duplicate the mesh instance.")
	# This asset is geometry only. Animation/collision/helper nodes stay out of it.
	for child in result.get_children():
		child.free()
	result.owner = null
	result.transform = attachment_transform
	result.skeleton = NodePath("..")
	# Mesh/Skin resources are reference-counted and remain alive on the new root.
	scene.free()
	return result


func _collect_meshes(node: Node, meshes: Array[MeshInstance3D]) -> void:
	if node is MeshInstance3D:
		meshes.append(node as MeshInstance3D)
	for child in node.get_children():
		_collect_meshes(child, meshes)


func _scene_transform(node: Node) -> Transform3D:
	var result := Transform3D.IDENTITY
	var current := node
	while current != null:
		if current is Node3D:
			result = (current as Node3D).transform * result
		current = current.get_parent()
	return result


func _unchanged(scene: Node, reason: String) -> Node:
	push_error("skinned_mesh_root: %s Import hierarchy left unchanged." % reason)
	return scene
