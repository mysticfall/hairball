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
All twelve test scripts pass on the source checkout. Version remains 0.5.0 and no
new distribution was built, as requested.

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
