# Hairball

Turn native Blender Hair Curves into editable, rigged hair cards for
[GodotHair](https://github.com/2Retr0/GodotHair).

Groom with Blender's native tools, preview the strands in colour, then generate
cards and export a GLB with the two data textures needed by GodotHair. Hairball
supports surface attachment, armature weights, relative shape keys, native
interpolation, and short curly hair as well as longer strands.

**Development status:** usable for experimentation, with broader production
quality and performance validation still pending. Use a working copy of your
character. Tested with **Blender 5.2.2 LTS**; native interpolation is audited
against that version's bundled asset. Legacy particle hair is not supported.

## Installation

Build the extension from this checkout using Blender's extension tools:

```sh
blender --factory-startup --command extension validate hairball
mkdir -p dist
blender --factory-startup --command extension build --source-dir hairball --output-dir dist
```

In Blender, open **Preferences → Get Extensions → Install from Disk**, select
the generated ZIP, and enable Hairball. Its controls appear in the 3D View's
**N sidebar → Hairball**. Restart Blender after updating if old code remains
loaded.

The manifest currently retains version **0.5.0** during source development.
Earlier archives with that version predate several features documented here;
build from the current checkout. Build output is not included in Git.
No external Python dependencies or network access are required by the extension.

## Quick start

### 1. Create and style guides

1. Select a local body mesh with a valid, non-overlapping UV map.
2. Under **Native Groom Setup**, choose **Whole Surface**, or select faces in
   Edit Mode and choose **Selected Faces**. Hidden faces are excluded.
3. Set **Guide Count**, **Guide Length**, **Points per Guide**, and **Seed**,
   then click **Create Attached Groom**.
4. Switch the new groom to Sculpt Mode and style it with Blender's native Comb,
   Puff, Grow/Shrink, and other grooming brushes.
5. Return to Object Mode and click **Validate Groom**.

Selected Faces limits **initial guide placement**, not later Add/Slide brushes.
Creation enables the body's **Add Rest Position** output for native attachment;
it does not change the body's geometry, weights, pose, or shape-key values.

### 2. Add interpolation (optional)

For a fuller groom without sculpting every strand:

1. Select the guide groom in Object Mode.
2. Under **Native Interpolation**, set **Density**, **Guide Distance**, and
   **Guides per Strand**, then click **Create Interpolated Groom**.
3. Hide the original groom and sculpt the new copy directly. Its interpolated
   strands follow the editable guides; the original remains a backup.

To adjust an existing interpolated groom, click **Load Selected Settings**,
edit the controls, then **Apply to Selected Groom**. This preserves sculpted
guides and existing cards; regenerate cards separately when ready.

Density and guide distance use **groom-local units**. Start with modest density:
more strands increase evaluation and baking cost and can produce more cards.
Interpolation fills out existing shapes—it does not curl straight guides.

Setup requires a single-user attachment mesh and adds a persistent FACE density
attribute. This mask limits generated roots, not native sculpt brushes. Source
UV or topology changes require rebuilding the setup.

### 3. Preview the hairstyle

Select the native or interpolated groom in Object Mode. Under **Groom Preview**,
choose **Hair Color** and click **Apply Groom Colour**. Use **Material Preview**
or **Rendered** shading to inspect the strands before generating cards.

Apply again after changing the colour. This isolates the groom's curve data and
assigns a new material; shared grooms, existing materials, and generated cards
are untouched. It is a rough colour preview, not a reproduction of GodotHair's
lighting. The same colour is used for newly generated card preview materials.

### 4. Generate hair cards

Select the groom in Object Mode and click **Generate Hair Cards**. Each run
creates an independent mesh, two packed data images, and an approximate Blender
material. Hide the groom and older results yourself to inspect the new cards.

Results live under the groom's collection. For example:

```text
Scalp Hair v001
└── Scalp Hair Cards
```

The collection counter distinguishes generations; mesh names have no explicit
version suffix. Blender adds its normal `.001` suffix only on a name collision.
Generation never replaces earlier edits or outputs.

Key controls (hover over any setting for details):

| Setting | What it changes |
| --- | --- |
| Root Distance / Shape Difference / Direction Difference | Which strands may share a card; different root anchors remain separate |
| Strands per Card | Maximum bundle size, not a target strand count |
| Minimum Width | Ribbon width, **not strand thickness** |
| Radius Scale | Generated strand thickness; preserves the groom's original radii and taper |
| Fit Error / Bend per Segment | How closely cards follow bends; tighter limits generally need more detail |
| Max Segments | Card detail cap; increase it if the fit cannot meet your tolerance |
| Atlas Size | Resolution of both data maps, up to 2048 × 2048 |
| Card Display | Shaded cards or opaque map-channel diagnostics |

Start Radius Scale at **1**; increase it if strands look too fine at your target
viewing distance. Cards widen as needed to contain the scaled radii.

**Generate Geometry Preview** is an optional fitting diagnostic: opaque ribbons
with local UVs and no textures. It is not the hairstyle-colour preview above.

Generated cards carry uniform bone weights from each card's nearest root
anchor. Relative morph displacements are transferred as Basis-relative shape
keys for glTF compatibility; values follow the source through Blender drivers.
You can edit cards natively, but UV/topology edits do not trigger a rebake.

### 5. Export to Godot

Select the generated cards object and click **Export Cards Package**. Choose
a folder and a base name, such as `scalp_hair`. It writes:

- `scalp_hair.glb` — mesh and armature, normals, tangents, skinning, and morphs.
- `scalp_hair_attributes.png` — coverage, depth, and strand seed.
- `scalp_hair_coordinates.png` — strand direction and root-to-tip coordinate.

This uses Blender's native exporter and image save. Materials are excluded by
default because GodotHair supplies its own shader; **Include Preview Material**
is available when needed. Selection is restored after export. Export updates
the images' file paths to the chosen destination.

Reusing filenames replaces the exported files so Godot can reimport them;
keep your Blender result versions as backups. Images are also packed into the
Blender file. Manual image saving and standard glTF export remain available.

## Godot setup

Assign a GodotHair shader material and connect the matching exported maps:

| Map | Channels |
| --- | --- |
| Attributes | R: coverage; G: local depth, deep → shallow; B: strand seed |
| Coordinates | RGB: tangent-space strand direction, encoded to [0,1]; A: root → tip |

These are **data textures**, not colour or normal maps. For initial inspection:

- Set compression to **Lossless** and **Normal Map** to **Disabled**, then
  reimport both textures.
- Disable mipmaps initially and use the shader's nearest sampling.
- Do not apply sRGB/source-colour conversion or an extra green-channel flip.
- Keep Coordinates as **RGBA**: its alpha is data, not transparency.

Review compression and filtering visually before changing these settings. Keep
the mesh and both maps from the **same generation**.

For attachment to an existing character skeleton, the reusable
[`godot/skinned_mesh_root.gd`](godot/skinned_mesh_root.gd) import script turns a
single-mesh rigged GLB into a mesh-root scene. Instantiate it directly under the
target Skeleton3D and assign the material once; reimports update the mesh and
skin without copying nodes or introducing a nested skeleton.

See [Godot import setup](godot/README.md) for instructions and binding
requirements. Bone names and rest/bind transforms must be compatible; this is
not automatic retargeting. Morph-value synchronization in Godot is separate.

## Compatibility and limitations

- Native **Clump Hair Curves** and **Frizz Hair Curves** are supported before
  the terminal **Deform Curves on Surface** node, in one visible Geometry Nodes
  modifier. Local nested groups are audited by contents, not display names.
- Native interpolation requires the audited Blender **5.2.2** asset with
  **Resting Surface** enabled, **Viewport Amount = 1**, and no image mask.
- Supported attachment-surface modifiers are Armature and Subdivision. Arbitrary
  scene inputs, animated/driven graphs, ambiguous UVs, and sheared groom
  transforms are rejected rather than guessed.
- Each card gets its own padded atlas slot. Fine strands need substantially
  more texels than the minimum packing allows. If capacity or coverage is
  inadequate, increase Atlas Size, reduce interpolation density, or adjust
  compatible clustering. Start with hundreds of cards, not the packing ceiling.
- Interpolation rejects totals over 100,000 strands as a safety cap, not a
  practical performance target. Large-groom performance remains under review.
- The Blender card material approximates appearance; it does not reproduce
  GodotHair scattering, frizz, or temporal dithering. Local projection depth is
  not whole-groom occlusion.

## Development and verification

Tests use separate factory-startup Blender processes. **Do not run them in an
interactive character scene.** For example, from the repository root:

```sh
blender --background --factory-startup --disable-autoexec --threads 2 --python-exit-code 1 --python tools/atlas_test.py
blender --background --factory-startup --disable-autoexec --threads 2 --python-exit-code 1 --python tools/groom_color_test.py
blender --background --factory-startup --disable-autoexec --threads 2 --python-exit-code 1 --python tools/export_test.py
```

The suite covers rest extraction, rig/morph transfer, native effects and
interpolation, card fitting, texture channels, cleanup, undo/persistence, native
export, and EEVEE rendering. Synthetic fixtures establish specific behaviours,
not universal production quality. The Godot attachment script has also been
successfully tested in the user's character workflow.

See the [specification](docs/specification/index.md) and
[verification status](docs/specification/verification.md) for detailed gates
and remaining work.

## License

Hairball is licensed under the **GNU General Public License v3.0 or later
(GPL-3.0-or-later)**. See [LICENSE](LICENSE); the extension includes the same
notice in [`hairball/LICENSE`](hairball/LICENSE).

[GodotHair](https://github.com/2Retr0/GodotHair) is a separate project with its
own licensing. Its shader and example assets are not bundled with Hairball.
