# Verification status

Source naming/layout regression: `atlas_test.py` checks that
`Pubic Hair Guides Interpolated` generates a child collection `Pubic Hair v001`
with mesh object `Pubic Hair Cards`, not a new scene-root collection. The
generation counter belongs to the collection, not the object name.

## Passed on Blender 5.2.2 LTS
`groom_color_test.py` verifies isolated material assignment on native and
interpolated grooms, unchanged guide positions/rest strands, native snapshot
undo/redo and save/reopen. Actual EEVEE native-strand renders change from red
to blue as requested; this does not establish GodotHair shading equivalence.

All tests run in separate factory-startup background processes. No interactive
Blender MCP, reference character save, or game-project changes were used.
The previous source suite passed before the atlas/filter update below. Version
remains 0.5.0 and no new distribution was built, as requested.

### Atlas/filter correction (2026-10-22)
`subpixel_baking_test.py` checks a 0.015-texel strand at 21 translations,
area proportionality to radius, coincident/partial/disjoint interval unions,
inclined-strip area, resolution scaling, shallowest data, and finite collapsed
row handling. `atlas_packing_test.py` checks deterministic variable tile sizes,
preserved card order, bounds, complete gutters, the minimum packing ceiling,
invalid geometry rejection and resolution diagnostics. Both isolated tests pass.
The interval filter approximates vertical curvature with four samples and clips
root/tip caps; these are not claims of exact two-dimensional disk integration.
The original batching/equivalence rows below describe the prior point-sampled
baker, not pixel equivalence of this intentionally different coverage filter.
All fifteen `tools/*_test.py` scripts pass in separate factory-startup Blender
5.2.2 processes after this update. Corrected Ayana/Godot appearance review is
pending; passing fixtures do not establish production quality.

The separate local bob test export reduces 5,749 cards / 399,404 triangles to
1,683 cards / 213,124 triangles, retaining all 41,944 source strands and rigid
head weights. Islands now span 8–119 texels across rather than uniformly 8;
8-bit coverage has 254 nonzero levels instead of four. GLB skin/UV/data-map
structure checks pass, with both maps 2048 RGBA8. The independent `.blend`
reopens with the corrected result active and packed maps matching the PNGs
within one quantization step. This remains heavy geometry, and
1,658 cards have representative diameters below ¼ texel (median
0.0411 texel). It is an improved test artifact, **not** a Godot visual pass or
reference-quality result. The shader and game project were not changed.
User Godot review subsequently found little visual improvement: the bob still
reads as ragged overlapping sheets. The installed GLB and both PNGs were checked
byte-for-byte against v007 and match; material texture bindings are correct.
Therefore this revision **fails the hairstyle appearance gate** despite passing
structural and synthetic tests. Card overlap, bundle coherence and texture
sampling must be isolated before claiming a visual fix; another atlas-only
adjustment is not established as sufficient.

### Pattern reuse (2026-10-23)
`pattern_reuse_test.py` checks deterministic grouping (source separation,
shape/population splits, coarsening into the fixed patch grid), donor
selection, shared-island bake coverage with subpixel levels, and rejection of
empty input. All sixteen `tools/*_test.py` scripts pass in isolated
factory-startup processes; `atlas_test`/`multi_groom_test` now run through the
pattern path with per-groom seed disjointness intact. The bob pattern export
(`Ayana-bob-godot-v008`) maps 1,683 cards onto 21 shared 256×512 patches
(median 23 members, median 16-strand donors): occupied fraction median 12.8%
with black gaps, near-opaque coverage ~0, 255 nonzero coverage levels, median
strand diameter 0.2405 texel (was 0.0411), underresolved cards 894 (was 1,658).
GLB/skin/map structure and blend-reopen checks pass. Subsequent user Godot
review shows dotted, noisy strands; v008 does **not** pass the appearance gate.

### Thickness-only diagnostic (2026-10-23)
The independent local v009 experiment multiplies v008 baked radii by eight
(effective Radius Scale 2.0 instead of 0.25), without changing paths, patch
donors, seed, UVs, shader or geometry. The GLB is byte-identical to v008.
This is an experiment-local post-projection radius adjustment, not a source
baker/default change or a minimum-radius floor; enlarged strokes clip at the
existing patch bounds (3,314 of 87,520 projected donor samples cross a bound).
Across nonzero atlas texels, median coverage rises from 24.3% to 100%; median
horizontal runs at coverage >=90% rise from one to two pixels. The explicitly
provided read-only Wings reference has corresponding values of 98.8% and two
pixels; horizontal runs are not exact strand diameters or screen-space widths.
GLB skin/UV checks and packed-image save/reopen checks pass. **Godot appearance
is pending**, including whether thicker strands connect or merge into ribbons.
No reference assets were bundled, source grooms changed, or game files written.
User Godot review reports v009 looks much better, but still below the reference
quality, with possible merged strands or model-related bands. This is an
improvement, **not** completion of the appearance gate.

Read-only analysis of the explicitly provided Wings GLB finds 2,008 disconnected
position+UV components versus 1,683 for the bob; these are topology components,
not a guaranteed semantic card count. Wings has 29,936 triangles versus 213,124;
the median component has 14 versus 132 triangles. Exported bob normals nearly
equal triangle face normals, whereas Wings normals depart slightly from the
faces, consistent with smooth shading. The bob has about twice the summed mesh
surface area at comparable extents, but the different silhouettes/styles mean
this is only a layering diagnostic, not an optimization budget or target.
The next local texture-only diagnostic uses four times v008's radius (half of
v009), retaining byte-identical geometry and unchanged UVs, donors and shader.
Smoother normal/tangent handling and card fitting remain separate investigations;
no normal or geometry improvement is claimed by the midpoint texture test.
This diagnostic is exported as local v010. Structure and packed-map reopen
checks pass; median nonzero coverage is 83.9% (v009: 100%), and strong horizontal
runs still have a two-pixel median. GLB bytes match v008/v009. Visual comparison
against v009 in the same view/material remains pending.
User reports v010 improves the result, but no-AA screenshots show both pixel
stair-stepping and larger angular silhouette flyaways, especially at the back.
It remains below the visual gate. A read-only local audit samples each fitted
centerline at 257 uniform root-to-tip parameters, and donor patterns on up to
eight recipient cards per patch. Some fitted paths contain abrupt near-reversals.
For the sampled recipient set, the 95th-percentile turn is 6.39 degrees for
centerlines, 9.64 for their first own projected strand, and 15.03 for transplanted
donor strands. The own-strand comparison is a control, not a one-to-one strand
correspondence or a complete rendered-card/texture-footprint test. Pattern reuse
can amplify angularity; both card-path continuity and recipient-aware texture
warping need investigation. These statistics do not locate the screenshot's
circled strands, prove a single cause, or establish that smoothing normals or
enabling AA repairs silhouette kinks. No visual correction is established.

### Matched physical-path audit and straight-pattern control (2026-10-23)
A further local, scene-independent audit maps atlas paths onto the exact two
triangles of each ribbon row using barycentric coordinates. Depth is not treated
as displacement. Incoming/outgoing 5 mm chords are compared every 2 mm along
each reconstructed path, rather than measuring turns at arbitrarily tiny knots.
With one deterministic source strand per card, 95th-percentile turns are 25.40
degrees in the extracted source, 33.22 for that same strand on its own card,
37.05 for a donor on recipient cards, and 31.55 with the donor held at constant
atlas U. Recipient centerlines measure 20.12 degrees. The own-source/surface
position difference has median 5.14 mm and 95th percentile 17.49 mm; planar
flattening is lossy, so this is not by itself proof of a faulty implementation.
These are differently weighted path samples, not pixel statistics or a mapping
of the circled screenshot strands. Native evaluated groom versus extracted
polyline fidelity and runtime shading remain unverified. Both existing source
bends and mapping distortion need investigation; no single cause is established.

Local v012 is a diagnostic straight-pattern bake against v010, not a proposed
final hairstyle. Each donor strand is held at its V-integrated mean atlas U;
radius/taper (four times v008), depth, seed, donors, UVs and card geometry remain
unchanged. Directions are rebaked for the altered path on the actual triangles.
Coverage/overlap necessarily change when paths straighten. The GLB is copied
byte-for-byte from v010; both PNGs must be replaced together for comparison.
An earlier local v011 used an approximate direction reconstruction and is not
the comparison artifact. Reference/game files and the interactive scene were
not changed. Structural export and packed-map reopen checks are recorded in
the package; Godot comparison of the same rear-side flyaways remains pending.
User subsequently reports v012 looks pretty good, with the particular problem
region still noticeable, and intends to revise its grooming first. This is
positive visual feedback, not a complete production-quality or deformation gate.
The committed add-on contains the filtered coverage and atlas/pattern-reuse
features, including the Pattern Reuse UI toggle. The local v010/v012 thickness
and constant-U path controls remain export-only experiments, not changed
generation defaults or a reproducible v012 preset in the add-on.

| Gate | Evidence |
| --- | --- |
| Final evaluated curve access | A Geometry Nodes translation appears in copied strands while original positions stay unchanged |
| Native UV morph attachment | A surface Lift morph displaces native attached curves |
| Limited rest-space recovery under active pose/morph | Temporary terminal-deformer bypass retains upstream GN geometry and leaves source pose/keys/graph/selection intact |
| Failure cleanup | Cyclic strands rejected during temporary evaluation without leaked objects/node groups |
| Independent anchors and skinning | Left/right cards follow separate bones; helper and nondeform groups excluded |
| Relative morph semantics | Masked/chained deltas flattened to Basis, source-value drivers and original-name metadata retained |
| Standard GLB export | POSITION/NORMAL/TANGENT/TEXCOORD_0/JOINTS_0/WEIGHTS_0 plus three morph targets; chained target delta decoded from binary and checked |
| Standard GLB import | UV layer, skin modifier/groups and morph keys survive |
| Persistence and reload | Registration/unregistration/reload and .blend reopen preserve drivers/anchor metadata |
| Fitting feasibility | Wavy and short-curl ribbons retain normalized width frames, root-to-tip parameters, valid mesh tangent handedness |
| Width satisfaction | Row half-widths grow until the interpolated ribbon contains every strand knot/radius at the baker's exact projection; the real Ayana pubic groom fits at radius scales 1–3 with zero projection failures, and ×2 coverage grows with unchanged vertex counts while the groom radius attribute is untouched |
| Export package | One-click native GLB + both PNG saves under one base name: exported GLB carries POSITION/NORMAL/TANGENT/TEXCOORD_0/JOINTS_0/WEIGHTS_0, two morph targets and a skin; armature included, body surface excluded; PNG bytes round-trip within 8-bit quantization; selection/active restored; invalid name/directory cancel without writing |
| Actual EEVEE preview | Synthetic stripe-map fixture renders with visible coverage and transparent background |
| Prior extension packaging | The 0.5.0 manifest/archive validated; subsequent source changes intentionally are not packaged |
| Native groom creation (0.2.0) | Deterministic area sampling, whole/selected faces, scale-correct length, UV attachment, parenting and terminal native deformer |
| Creation during active pose/morph | Source values/geometry/modifiers remain unchanged; guides follow both deformations and recover original rest space |
| UV ambiguity rejection | Degenerate and overlapping UVs rejected, including overlap against unselected faces |
| Setup failure cleanup | Injected failure after curve/object allocation removes owned data and restores the surface rest-position flag |
| Edit Mode action | Flushed face selection, selected-only roots, native Curves Sculpt mode entry; failed creation restores mode/selection without leaks |
| Subdivided attachment | Native deformation evaluates and rest guides remain recoverable with a subdivision modifier; no cropped-patch provenance claim |
| Creation persistence | Save/reopen preserves native attached guide geometry and rest recovery |
| Creation undo-memory restoration | Undo removes new groom/graph and restores rest-position flag and selection; redo restores attached evaluable guides |
| Deterministic clustering (0.3.0) | Input-order independence, exact anchor separation, pairwise root boundaries, direction/shape rejection and bundle-size cap |
| Adaptive detail | Straight strands need one segment; curls receive more rows; sampled centerline error checked densely; insufficient detail fails clearly |
| Curl cancellation | Opposing curls that average into a straight line split into independent fits retaining the same root anchor |
| Native spline evaluation | Temporary Evaluated-mode resampling produces more path points than Catmull-Rom control points without rewriting the source graph |
| Geometry generation | Four synthetic wavy/curly strands produce two cards, 114 vertices and 110 triangles; separate anchors/groups and source state retained |
| Independent versioning | Fresh collections/meshes/materials, ID-linked source rename support, and prior manual mesh edits preserved |
| Geometry failure cleanup | Injected transfer failure after allocating output and a shape key leaves no owned object/mesh/key/collection leaks |
| Geometry persistence/undo | Geometry action selection, explicit undo/redo snapshots, save/reopen of source ID references, UVs, keys and drivers |
| Geometry render | Opaque wavy and short-curl ribbons rendered in EEVEE; geometry diagnostic only, not atlas or production quality evidence |
| Atlas/channel baking (0.4.0) | Deterministic padded islands, nonempty wavy/curly coverage, four-sample fractional coverage, frontmost seed/depth selection, encoded direction and full root/tip alpha |
| PNG data preservation | Native image save/load preserves Non-Color channel-packed RGB/alpha within one 8-bit quantization step |
| Atlas tangent basis | Ordinary GLB preserves explicit flat triangle normals, tangents and handedness, UV-origin conversion, skin and two morphs; no extra green flip |
| Complete result independence | New collections/mesh/material/packed images; deterministic repeat pixels and prior buffers unchanged |
| Image/result failure cleanup | Failures after two images/material allocation and during second image creation leave no owned data leaks |
| Packed image undo/persistence | Explicit native undo removes result/images; redo and .blend reopen restore exact pixels, source links and morph drivers |
| Textured EEVEE render | Baked wavy/curly synthetic strands render via coverage-driven preview material; not production hairstyle evidence |
| Preview diagnostics | Coverage/depth/seed/direction/root-tip material modes construct without scene mutation |
| Parameter tooltips (0.5.0) | RNA descriptions are nonempty/explanatory for every Hairball setting |
| Native local effects | Installed Blender 5.2 Clump/Frizz assets evaluate and bake; rest points agree under active versus neutral pose/morphs; original graph/guide positions/rig values preserved |
| Nested graph safety | Recursive auditing checks actual contents, rejects Object Info injected into a native-named dependency before temporary allocation |
| Native interpolation (source) | Exact installed Blender 5.2.2 asset content audit, rest/ID invariance under pose/morphs and subdivision, 120 generated strands from four editable guides bake into skinned/morphed cards |
| Persistent growth mask | Independent FACE float mask adds to the source in explicit authoring setup; selected left faces generate 60 roots restricted to that region; original groom unchanged |
| Interpolation lifecycle | No-strands/oversized setup and injected allocation failure cleanup; explicit native undo/redo restores copied groom, appended dependencies and source mask; save/reopen content audit passes |
| Interpolation UV safety | Audits the groom's actual attachment UV map even when another degenerate map is active; positive-area overlap against excluded faces rejects before allocation |
| Existing interpolation controls | Load/Apply edits density/distance/guide count on an isolated root-graph copy; preserves guides, mask, seed and previous cards/maps, including another groom sharing the old graph |
| Update rollback/lifecycle | Empty/oversized results and injected evaluation failure restore the old graph without leaked groups; explicit undo/redo and reopen preserve applied settings |
| Raster batching | 28,764 scalar-reference comparisons have identical interpolation factors, hit masks and depth arrays; bounded batch scratch and original depth-winner ordering |
| Original-baker equivalence | Same saved 120-strand fixture baked through the pre-change and batched functions produces exactly equal packed-image pixels for both maps |
| Grouped multi-groom generation | Two one-sided grooms selected together combine into one versioned mesh named after the active groom; per-groom cards keep disjoint namespaced strand ids, per-vertex surface indices, per-side anchor weights and disjoint baked seed ranges under one shared rig with primary-surface morph drivers |
| Grouping boundaries | Hidden backup grooms never join a run even when still selected; single-groom selection stays standalone with unchanged provenance/versioning; mismatched armatures or shape-key layouts reject without leaks or counts changes |
| Coverage saturation warning | Baking counts cards whose occupied texels are ≥90% above 0.95 coverage; Radius Scale 0.1 yields none, thicker scales only add them, and the cards operator warns that Godot may render flat cards |

The native groom fixture is `/tmp/opencode/hairball-tests/groom.blend`;
the new geometry fixture/render are `cards.blend` and `cards.png` in that directory.
The textured fixture/render are `atlas.blend` and `atlas.png`; `atlas.glb` is a
disposable ordinary-export basis test, not an extension exporter feature.
`native-effects.blend` demonstrates the installed Clump/Frizz asset stack.
`interpolation.blend` contains the full-density and selected-face-mask examples.
The synthetic 120-strand interpolation bake generates 120 cards / 5,830
triangles with 1024px maps. Same-process comparison on the saved fixture:
original baker **31.1663s**, batched baker **12.3801s** (about **2.5× faster**),
with exactly equal map pixels. The original profiled run took 45.8s including
profiler overhead; 43.8s was in baking. Treat this as a synthetic improvement,
not evidence of an acceptable production budget or universal speedup.
`interpolation-controls.blend` demonstrates edited settings and retained output.
`groom_undo_test.py` uses explicit undo snapshots because a background Python
invocation has no normal UI event loop. Actual UI Ctrl-Z interaction remains a
manual check, separate from undo-memory data restoration.

Artifacts: `/tmp/opencode/hairball-tests/{core.blend,cards.glb,preview.blend,preview.png}`.
The preview uses manually supplied diagnostic map fixtures; it is not evidence
of completed texture baking or final hair quality.

## Important discoveries
- Keep the evaluated GeometrySet alive while accessing its Curves RNA. Returning
  detached RNA handles can raise `StructRNA of type Curves has been removed`.
- Curves positions can be spline control points rather than rendered path points.
  Geometry generation resamples at native evaluated resolution on temporary
  rest graphs. Blender 5.2's Resample Curve mode is a menu socket, not `node.mode`.
- The native surface-deformation node follows the surface's changing normals;
  translation-only card morphs intentionally need not match it exactly.
- Blender's standard exporter writes non-Basis-relative keys against Basis.
  The user approved flattening generated morph deltas to avoid this mismatch.
- Packed new byte images provide encoded backing buffers that preserve pixels
  through the tested undo/redo and reopen. Existing image buffers are never edited.
- Blender's tested glTF exporter flips UV V for origin conversion but preserves
  tangent handedness. Do not apply an additional green-channel flip to these maps.
- Blender reports a missing optional MeshOptimizer library during export in this
  environment. Uncompressed ordinary GLB export/import succeeds without it.

## Not yet validated
Broader native asset revisions/effect stacks, image density masks and sculpt brush-region restrictions;
posed custom graphs; comprehensive subdivision/seam/cropped-patch provenance;
production clustering/adaptive quality and large-groom performance;
large-groom atlas quality/optimal packing; comprehensive twist/seam direction checks;
interactive UI undo; topology/UV source edits after generation;
real Ayana appearance/deformation; Godot shader behavior and imports;
Wings comparisons/performance; full acceptance criteria.
