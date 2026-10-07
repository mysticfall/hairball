import bpy


class HAIRBALL_PT_main(bpy.types.Panel):
    bl_label = "Hairball"
    bl_idname = "HAIRBALL_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Hairball"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.hairball
        box = layout.box()
        box.label(text="Native Groom Setup")
        box.prop(settings, "growth_region")
        box.prop(settings, "guide_count")
        box.prop(settings, "guide_length")
        box.prop(settings, "guide_points")
        box.prop(settings, "seed")
        box.operator("hairball.create_groom")
        if settings.growth_region == "SELECTED_FACES":
            box.label(text="Limits initial guide placement", icon="INFO")
        box = layout.box()
        box.label(text="Native Interpolation")
        box.prop(settings, "interpolation_density")
        box.prop(settings, "interpolation_distance")
        box.prop(settings, "interpolation_guides")
        box.operator("hairball.prepare_interpolation")
        box.label(text="New groom + surface density attribute", icon="INFO")
        box.operator('hairball.load_interpolation')
        box.operator('hairball.update_interpolation')
        box.label(text="Apply preserves cards; regenerate separately")
        layout.separator()
        layout.operator("hairball.inspect_groom")
        box = layout.box()
        box.label(text="Groom Preview")
        box.prop(settings, "preview_color")
        box.operator("hairball.apply_groom_color")
        box.label(text="Material Preview / Rendered shading", icon="INFO")
        box = layout.box()
        box.label(text="Card Generation")
        box.prop(settings, "cluster_radius")
        box.prop(settings, "cluster_shape_error")
        box.prop(settings, "cluster_angle")
        box.prop(settings, "bundle_size")
        box.prop(settings, "card_width")
        box.prop(settings, "radius_scale")
        box.prop(settings, "fit_error")
        box.prop(settings, "bend_limit")
        box.prop(settings, "max_segments")
        box.prop(settings, "atlas_size")
        box.prop(settings, "preview_mode")
        box.operator("hairball.generate_cards")
        box.operator("hairball.generate_geometry")
        box.separator()
        box.operator("hairball.export_cards")
        box.label(text="Select a cards object; native GLB + map save", icon="INFO")


def register():
    bpy.utils.register_class(HAIRBALL_PT_main)


def unregister():
    bpy.utils.unregister_class(HAIRBALL_PT_main)
