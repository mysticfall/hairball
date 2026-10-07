# Approved scope and decisions

The original approved plan is archived at
`/home/mysticfall/.plannotator/plans/hairball-native-blender-hair-t-2026-10-05-approved.md`.
This specification records its durable requirements and subsequent decisions.
Implementation is authorized in the current session; no separate session or
subagent is required or authorized.

## Workflow
Native groom colour preview is an explicit authoring action: Apply Groom Colour
uses the selected colour on isolated curve data and a new opaque material.
It works on guides and interpolated strands without card generation. Existing
cards/materials, shared grooms, guide geometry, radii and graphs are preserved;
card diagnostics remain separate and optional. No colour edit runs during draw.

1. Create an attached modern native Hair Curves groom on a complete mesh or
   selected growth faces, or select an existing attached native groom.
2. Author using native sculpting/Geometry Nodes. Convert the final evaluated
   groom including interpolation/clumping/frizz, not guides alone.
3. Create an independent versioned collection containing cards, two map images,
   preview material, settings and source/anchor provenance. Never replace old
   results, edits, or images. Preserve the source and rig state.
   New result collections live under the groom's collection in the current
   scene (scene-root fallback only when needed). Strip terminal authoring
   suffixes Guides/Interpolated for concise names. Only result collections carry
   the generation counter; object names have no explicit version suffix and
   use Blender's ordinary collision handling. Never rename or move old results.
4. Refine using native mesh moves/bends/deletes with intact UVs. There is no
   automatic rebake after manual UV/topology changes.
5. Save images and export with ordinary Blender tools. No custom exporter or
   live Godot integration. Update (user request, 2026-10-07): the one-click
   Export Cards Package action drives Blender's ordinary glTF exporter and
   image save under one base name; Hairball still implements no exporter or
   file format of its own and writes nothing outside the chosen folder.

Target long scalp hair and short curly fur/body hair. Adaptive ribbons/sections
should preserve curl volume, seed, full strand root-to-tip parameter, and a
consistent original root anchor across sections. Do not join incompatible
deformation regions into one card. Geometry/atlas controls and measurements
come before any fixed runtime budget. Wings (29,936 triangles, 2×2048 maps) is
a local comparison, not a universal budget or redistributable sample.

## Deformation
Nearest original attachment vertex at each root in rest space supplies uniform
deform-bone weights to every card vertex. Ignore helper/mask/nondeform groups.
Relative surface morphs supply uniform anchor displacements, translation only.
Separate cards may share a mesh but retain independent anchors, particularly
for independently moving left/right body regions. This is a shared skinning
transform, not exact strand simulation or guaranteed mathematical rigidity.

Supported posed-generation workflows recover native rest space without
double-applying skin/morph deformation and without changing the source pose.
Unsupported pose-dependent graphs must fail cleanly. Never blindly inverse-skin
final strands. Crop/subdivision/UV-seam correspondence requires validation and
original-vertex provenance where needed; reject ambiguity.

### Approved update: Basis-relative generated morphs (2026-10-05)
The user selected **Flatten keys (Recommended)** after a real GLB probe showed
that Blender's exporter ignores non-Basis relative links. Generate each card
key as its source key's effective delta relative to that source key's relative
reference, including any vertex-group mask, but relative to the generated Basis.
Preserve names and source-value drivers. Store original relationship names in
`hairball_source_relative_keys` metadata rather than actual relative links.
This preserves Blender motion and exported glTF motion. Godot must synchronize
body/card morph values separately. This supersedes retaining literal relative
links on generated cards in the original plan.

## Maps and viewport
| Map | Channels |
| --- | --- |
| Attributes | R coverage; G normalized per-bundle projection depth (deep to shallow); B deterministic strand seed |
| Coordinates | RGB tangent-space strand direction encoded [-1,1]→[0,1]; A full root-to-tip parameter |

The depth channel is an approximation, not physically accurate global occlusion.
Coverage antialiasing, consistent visible-strand data, atlas borders, overlap,
TBN handedness, and root/tip order must be tested. Image data is Non-Color;
coordinate alpha is channel-packed data, never opacity. Generate new immutable
Image datablocks for each result, compatible with ordinary Save/Pack workflows.
Document PNG formats and Godot import settings and validate glTF tangent behavior.

Preview approximates coverage, color, highlights, and root-to-tip variation in
actual EEVEE 5.2. It does not match GodotHair R/TT/TRT scattering, multiple
scattering, frizz, or temporal dithering. Provide map/geometry diagnostics.

## References and exclusions
Use a working copy of Ayana's visible mesh. Its lack of shape keys requires
temporary synthetic morphs for independent-side validation. Do not transfer
keys from the hidden body unless separately requested. Scalp/armpit/crotch
patch duplicates/crops are authorized on the working copy only.

Never modify the original character, reference Pawprint extension, or Alleycat
game. Wings samples are not bundled due to their attribution/noncommercial
license. No old particle hair, hair dynamics, automatic LOD, arbitrary
pose-dependent graph conversion, topology/UV migration, or custom baking after
manual output edits. Native shape-key editing precautions still apply.

## Ordered remaining slices
1. Complete feasibility audits: native interpolation/rest graph patterns,
    subdivision/UV seams, cropped-patch provenance, and tangent-space baking.
   Native local Clump/Frizz nested groups are supported/tested in 0.5.0 using
   recursive content auditing. Source development now audits the exact Blender
   5.2.2 native interpolation asset with Resting Surface on and Viewport Amount 1.
2. Native attached-groom creation and growth-region convenience workflow:
   implemented for initial whole/selected-face guide placement and explicit
   copied-groom interpolation setup with persistent FACE density masks. Add/Slide brushes are
   not restricted by the initial face selection.
    Setup deliberately adds a new density attribute to a single-user source
    mesh; generation does not. Image masks and broader asset revisions pending.
    Explicit Load/Apply authoring controls adjust existing interpolation using
    an isolated root-graph copy, preserving guides, seed, mask, rig state and
    previous outputs. Empty/oversized or failed updates restore the old graph.
3. Compatible root/shape/direction clustering and curvature-adaptive ribbons:
   implemented as geometry previews (0.3.0), with exact anchor boundaries,
   deterministic pairwise 17-sample shape checks and curl-cancellation splitting.
   Production quality/performance review remains pending.
4. Atlas packing and deterministic strand rasterization with both data maps:
   implemented in 0.4.0 with padded grid slots, four coverage samples, shallowest
   data selection and per-island data dilation. Optimal packing/sharing and
   production quality remain pending. Atlas size currently capped at 2048 to
    bound CPU working memory; empty coverage rejects. Source development added
    a generation-time Radius Scale (bake-only strand thickness multiplier; the
    groom radius attribute is never edited) and fitted ribbons now widen until
    the interpolated ribbon contains every strand knot exactly as the baker
    measures it, removing the previous width-fit hard failure.
    Source development batches raster calculations with bounded scratch arrays
    and preserves sample/segment winner ordering; scalar-reference comparisons
    cover identical hit masks, interpolation factors and depth values.
5. Versioned generation operator, controls, preview diagnostics and reporting:
   implemented in 0.4.0, retaining geometry-only previews as a separate action.
   Every exposed parameter has an explanatory tooltip in 0.5.0.
6. Undo/redo/failure cleanup and missing-source validation for complete results:
   packed image pixel restoration and allocation-failure cleanup tested in 0.4.0.
   Actual interactive Ctrl-Z and broader missing-source workflows remain pending.
7. Ayana working-copy scalp/body-hair examples and independent morph/pose tests.
8. Disposable Godot shader compatibility, Wings comparison measurements,
   installation archive and user-facing workflow documentation.

Acceptance requires the complete groom→cards/maps/preview workflow, reviewed
long/short-curly appearance, independent deformation without regeneration,
preservation of old edited results, persistence and ordinary export. Passing
isolated foundation tests alone does not satisfy full acceptance.
