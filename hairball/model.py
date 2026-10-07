import bpy
import math
from bpy.props import EnumProperty, FloatProperty, FloatVectorProperty, IntProperty, PointerProperty


class HairballSettings(bpy.types.PropertyGroup):
    interpolation_density: FloatProperty(name="Density", default=1000, min=0.01, max=1000000,
        description="Native generated strands per square groom-local unit of resting surface. More density increases evaluation/card/baking cost; estimated setups over 100,000 strands reject")
    interpolation_distance: FloatProperty(name="Guide Distance", default=0.1, min=0.00001,
        subtype="DISTANCE", unit="LENGTH",
        description="Native maximum distance to interpolation guides, in groom-local units. Increase if sparse guides leave gaps; too large may blend unrelated hair regions")
    interpolation_guides: IntProperty(name="Guides per Strand", default=4, min=1, max=64,
        description="Nearby editable guides used to interpolate each generated strand. More guides blend shape smoothly; fewer retain stronger individual guide influence")
    cluster_radius: FloatProperty(name="Root Distance", default=0.01, min=0.00001,
                                  description="Maximum world-space distance between strand roots in one card. Larger values allow more grouping; different root anchors always stay separate",
                                  subtype="DISTANCE", unit="LENGTH")
    cluster_shape_error: FloatProperty(name="Shape Difference", default=0.005, min=0.00001,
                                       description="Maximum difference between root-relative strand shapes, sampled along their lengths. Smaller values preserve distinct waves/curls but usually create more cards",
                                       subtype="DISTANCE", unit="LENGTH")
    cluster_angle: FloatProperty(name="Direction Difference", default=math.radians(35),
                                 description="Maximum angle between strand directions near their roots in one card. Smaller angles keep differently directed strands separate",
                                 min=0, max=math.pi, subtype="ANGLE")
    bundle_size: IntProperty(name="Strands per Card", default=8, min=1, max=64,
                             description="Maximum strands grouped into one card, not a target count. Higher values may reduce cards; incompatible roots/shapes and failed fits still split")
    card_width: FloatProperty(name="Minimum Width", default=0.002, min=0.00001,
                              description="Minimum full ribbon width in world-space units. Cards widen further to cover their strands; extra empty width does not make baked strands thicker",
                              subtype="DISTANCE", unit="LENGTH")
    radius_scale: FloatProperty(name="Radius Scale", default=1.0, min=0.01, soft_max=10, precision=2,
                                description="Generation-time multiplier for baked strand radii (coverage thickness). "
                                            "The groom's radius attribute is never modified; 1.0 keeps physical radius. "
                                            "Short body hair often reads thicker at 2-4")
    fit_error: FloatProperty(name="Fit Error", default=0.001, min=0.000001,
                             description="Maximum sampled centerline fitting error in world-space units. Smaller values follow bends more closely and use more segments; increase Max Segments if fitting fails",
                             subtype="DISTANCE", unit="LENGTH")
    bend_limit: FloatProperty(name="Bend per Segment", default=math.radians(20),
                              description="Maximum accumulated turning inside a sampled interval. Smaller angles add detail to curls; this does not smooth sharp source corners or limit the angle between neighboring faces",
                              min=0.001, max=math.pi, subtype="ANGLE")
    max_segments: IntProperty(name="Max Segments", default=64, min=1, max=1024,
                              description="Maximum segments per card. Generation fails if a single strand cannot meet Fit Error/Bend limits; raise this cap or loosen those tolerances")
    growth_region: EnumProperty(name="Growth Region", items=(
        ("WHOLE_SURFACE", "Whole Surface", "Place initial guides on all visible faces"),
        ("SELECTED_FACES", "Selected Faces", "Place initial guides only on selected visible faces"),
    ), default="WHOLE_SURFACE",
        description="Surface region for initial guide placement only. Selected Faces does not constrain later native Add/Slide brushes")
    guide_count: IntProperty(name="Guide Count", default=64, min=1, max=100000,
                             description="Number of editable native guides to create. More guides give more direct grooming control; this is not a generated card count")
    guide_length: FloatProperty(name="Guide Length", default=0.1, min=0.0001,
                                description="Initial root-to-tip guide length in world-space units, adjusted for object scale. Native grooming can change individual lengths afterward",
                               soft_max=1, subtype="DISTANCE", unit="LENGTH")
    guide_points: IntProperty(name="Points per Guide", default=8, min=2, max=128,
                              description="Editable control points per new guide. More points support finer curls but increase grooming/evaluation cost; this is not card segment count")
    atlas_size: IntProperty(name="Atlas Size", default=2048, min=64, max=2048,
                            description="Width and height in pixels of each of the two data maps. Larger maps resolve thinner strands/more cards but use more memory and baking time; current limit is 2048")
    preview_color: FloatVectorProperty(name="Hair Color", subtype="COLOR", size=4,
                                       description="Colour for Apply Groom Colour and new card preview materials. Apply explicitly to preview native strands; does not change data maps, existing cards or Godot materials",
                                      default=(0.12, 0.045, 0.02, 1), min=0, max=1)
    preview_mode: EnumProperty(name="Card Display", items=tuple((key, label, description) for key, label, description in (
        ("SHADED", "Shaded", "Approximate hair shading and coverage"),
        ("COVERAGE", "Coverage", "Attributes R"), ("DEPTH", "Depth", "Attributes G"),
        ("SEED", "Strand Seed", "Attributes B"), ("DIRECTION", "Strand Direction", "Coordinates RGB"),
        ("ROOT_TIP", "Root to Tip", "Coordinates A, not opacity"))), default="SHADED",
        description="Material mode for the next generated result. Shaded uses coverage; diagnostic modes display opaque channel values. Existing results are not changed")
    seed: IntProperty(name="Seed", default=0, min=0,
                      description="Deterministic seed for initial root placement and baked per-strand random values. Same inputs/seed reproduce results; changing it does not regroom existing guides")


def register():
    bpy.utils.register_class(HairballSettings)
    bpy.types.Scene.hairball = PointerProperty(type=HairballSettings)


def unregister():
    if hasattr(bpy.types.Scene, "hairball"):
        del bpy.types.Scene.hairball
    bpy.utils.unregister_class(HairballSettings)
