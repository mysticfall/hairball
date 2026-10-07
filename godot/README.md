# Reusable skinned-mesh import script (Godot 4)

`skinned_mesh_root.gd` turns an imported **single-mesh** rigged asset into a
`MeshInstance3D` scene root, retaining its Mesh, Skin, materials and blend-shape
values. It is not hair-specific: use it for clothing or other rigged attachments.

## Setup once

1. Copy `skinned_mesh_root.gd` into your Godot project, for example
   `res://tools/import/skinned_mesh_root.gd`. Godot cannot assign a script outside
   its project. This checkout does not modify Alleycat automatically.
2. Select the GLB in Godot's FileSystem dock. In the Import dock, enable
   **Skins > Use Named Skins**, and set **Import Script / Custom Script** to that
   file. Keep your existing skeleton bone-profile configuration, then Reimport.
3. Instantiate the GLB **directly under the target Skeleton3D**. Its root is now
   the mesh, with `skeleton = ".."`; there is no nested exported skeleton.
4. Assign your persistent material override on that instance once. For hair,
   use the existing GodotHair material and exported data maps.

Export over the same GLB and texture paths thereafter. Godot reruns this script
on import and updates the instance's Mesh/Skin without copying nodes. Keep the
exported mesh name stable so scene overrides continue to target the same root.
Existing copy-pasted meshes must be replaced with a GLB instance once.

## Safety and limits

- Exactly one MeshInstance3D is required, with a Skin and named bindings to the
  imported skeleton. Multiple meshes or invalid bindings log an error and
  leave the import hierarchy unchanged, rather than silently dropping geometry.
- The target must have matching bone names, hierarchy/rest transforms and bind
  space. Named skins do not retarget incompatible rigs. Missing target bones
  cannot be checked at import, since the character is a separate scene.
- The mesh transform is converted into the imported skeleton's local space.
  Instancing under an equivalent target skeleton preserves that relationship.
- Exported skeletons, animations, collision nodes and helper children are removed.
  This is an attachment asset, not a whole-character importer. Blend-shape
  resources survive, but driving their values from the character is separate.
- Previewing the GLB alone has no parent skeleton; test deformation in the
  character scene. Keep instance transform overrides clear initially.

## Validation

No Godot executable is installed in the development environment, so this script
has not yet been engine-tested. First test in a disposable scene: attach to the
compatible skeleton, pose it, set a material override, then overwrite/reimport
the GLB and confirm geometry updates while the override and animation survive.
