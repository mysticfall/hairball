# Hairball

Blender 5.2 extension converting modern native Hair Curves to GodotHair mesh
cards. Read `README.md` and `docs/specification/index.md` first.

## Safety and development
- Only inspect explicitly named reference files/directories. Do not scan the
  user's entire workspace.
- The user's interactive Blender is used for unrelated work. Do not access
  Blender MCP without first asking the user. Run tests in isolated processes:
  `blender --background --factory-startup --disable-autoexec --threads 2`.
- Never save over the supplied Ayana character or modify the Alleycat game.
- Every generation must create independent versioned output; never modify
  existing cards, images, grooms, or rig state to regenerate.
- No scene mutation at import, registration, or UI draw.
- Use package-relative imports compatible with `bl_ext` extension packages.
- Keep tests and specifications current. Distinguish completed gates from
  pending requirements and fixtures from production quality validation.
- Use native Blender undo/save/image export/glTF tools. Never assume pixel
  writes are undoable merely because an operator has the UNDO option.

## Current slice
Evaluated/rest strand extraction for a narrowly audited terminal-deformer graph,
uniform root-anchor deformation transfer, Basis-relative export-compatible
morphs, bundle-fitting kernel, and approximate EEVEE material are implemented.
User-facing actions are Create Attached Groom, Validate Groom, and Generate
Geometry Preview (0.3.0) and Generate Hair Cards (0.4.0). Deterministic anchor-compatible clustering, adaptive
fitting and independent versioned skinned/morphed geometry are implemented.
Geometry previews have opaque diagnostic materials and local UVs, not atlases.
Selected Faces restricts initial guide placement, not native Add/Slide brushes.
Textured generation includes padded grid atlases, packed Non-Color data images,
coverage rasterization and approximate preview/diagnostic materials. Synthetic
image undo/persistence and export basis tests pass; production/Godot validation
remain pending. Atlas size capped at 2048. Native interpolation status is below.
Version 0.5.0 adds descriptions to every setting and recursively audits local
nested node groups, tested with native Clump/Frizz assets. Do not admit scene
inputs or trust group display names; surface interpolation is gated as below.
Source development now includes strict content-signature auditing of Blender
5.2.2 native Interpolate Hair Curves (Resting Surface on, Viewport Amount 1,
no image mask). Explicit setup copies the groom and adds a new FACE density
attribute to its single-user attachment mesh; conversion itself does not mutate
the source. Persistent masks restrict generated roots, not sculpt Add/Slide.
Do not update the version or build distributions until production-ready (user
request). Test the checkout directly; the 0.5.0 archive predates interpolation.
Explicit Load/Apply interpolation controls edit the selected groom transactionally
on a copied root graph, preserving guides/mask/seed/old outputs. Keep these
authoring edits separate from non-mutating asset generation. Raster batching
retains original subsample/segment order and bounds batch scratch allocations.
Card generation includes a bake-only Radius Scale (groom radii are never edited)
and widens fitted rows to contain all strand knots, so generation no longer
fails on strands bowing between rows. Export Cards Package drives the native
glTF exporter and image save with one base name; it is automation of ordinary
Blender tools, not a custom exporter, and never writes game projects.

## References (read only)
- Layout: `/home/mysticfall/workspace/pawprint/pawprint/` and its tools/specifications.
- Shader contract: `/home/mysticfall/workspace/alleycat/game/content/the_veridian_spc/hair/materials/shaders/hair.gdshader`
  and `hair.gdshaderinc`.
- Character: `/home/mysticfall/workspace/Blender/Ayana/Ayana.texture.blend`.
  Use visible `Ayana.Ayana.female_generic_with_simplified_genitals_fixed`,
  NOT hidden `Ayana.body`. The visible mesh has no shape keys.
- Local Wings comparison assets must not be redistributed.
