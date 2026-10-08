# Hairball

Blender 5.2 extension converting modern native Hair Curves to GodotHair mesh
cards. Read `README.md` and `docs/specification/index.md` first.

## Safety and development
- Only inspect explicitly named reference files/directories. Do not scan the
  user's entire workspace.
- The user's interactive Blender is used for unrelated work. Do not access
  Blender MCP without first asking the user. Run tests in isolated processes:
  `blender --background --factory-startup --disable-autoexec --threads 2`.
- Never save over reference characters or modify external game projects;
  everything listed under References is read-only.
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

## Repository layout
- `hairball/` — extension source package: `blender_manifest.toml`, UI and
  operators, plus the evaluation, deformation, clustering, cards, atlas,
  baking, material, groom and export modules.
- `tools/` — headless test scripts and feasibility/attachment probes, run
  as shown in README "Development and verification".
- `docs/specification/` — approved scope and decisions (`index.md`) and
  verification status (`verification.md`).
- `godot/` — Godot import instructions and the reusable
  `skinned_mesh_root.gd` mesh-root import script.
- `dist/` — extension build output, never committed.

## References (read only)
None of these are part of the repository; consult them only when explicitly
provided in the environment.
- Target runtime: GodotHair (https://github.com/2Retr0/GodotHair). The
  data-map channel contract is recorded in `docs/specification/index.md`
  ("Maps and viewport") and the README ("Godot setup"); the original
  reference shaders belong to the author's private game project.
- Validation character: a local textured human character ("Ayana") on the
  original developer's machine, never committed or redistributed. Use its
  visible mesh `Ayana.Ayana.female_generic_with_simplified_genitals_fixed`
  (no shape keys), NOT the hidden `Ayana.body`, and only through a working
  copy. Otherwise validate with any complete mesh that has valid,
  non-overlapping UVs; synthetic fixtures in `tools/` provide automated
  coverage.
- Wings comparison assets are local and license-restricted
  (attribution/noncommercial): never redistribute or bundle them, and treat
  their measurements as one comparison point, not a universal budget.
