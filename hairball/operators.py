import bpy
import os
import traceback

from .evaluation import HairballError, evaluated_strands, rest_strands, validate_groom
from .export import export_cards
from .materials import apply_groom_color
from .groom import create_groom
from .geometry import generate_geometry
from .native import prepare_interpolation, interpolation_settings, update_interpolation


class HAIRBALL_OT_groom_color(bpy.types.Operator):
    bl_idname = 'hairball.apply_groom_color'
    bl_label = 'Apply Groom Colour'
    bl_description = 'Colour the selected native groom for Material Preview/Rendered view; preserve shared data, existing materials and generated cards'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.type == 'CURVES' and context.mode == 'OBJECT'

    def execute(self, context):
        try:
            apply_groom_color(context.object, context.scene.hairball.preview_color)
        except Exception as exc:
            if not isinstance(exc, HairballError):
                traceback.print_exc()
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        self.report({'INFO'}, 'Groom coloured; use Material Preview or Rendered shading')
        return {'FINISHED'}


class HAIRBALL_OT_load_interpolation(bpy.types.Operator):
    bl_idname = 'hairball.load_interpolation'
    bl_label = 'Load Selected Settings'
    bl_description = 'Read density and guide controls from the selected interpolated groom into the sidebar'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.type == 'CURVES' and context.mode == 'OBJECT'

    def execute(self, context):
        try:
            values = interpolation_settings(context.object)
        except HairballError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        for key, value in values.items():
            setattr(context.scene.hairball, key, value)
        self.report({'INFO'}, 'Loaded selected groom settings; edit them and click Apply')
        return {'FINISHED'}


class HAIRBALL_OT_update_interpolation(bpy.types.Operator):
    bl_idname = 'hairball.update_interpolation'
    bl_label = 'Apply to Selected Groom'
    bl_description = 'Apply density and guide controls to the selected groom, preserving sculpted guides and existing cards; regenerate cards separately'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.type == 'CURVES' and context.mode == 'OBJECT'

    def execute(self, context):
        try:
            count = update_interpolation(context.object, context.scene.hairball, context)
        except Exception as exc:
            if not isinstance(exc, HairballError):
                traceback.print_exc()
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        self.report({'INFO'}, f'{count} generated strands; existing cards unchanged—regenerate when ready')
        return {'FINISHED'}


class HAIRBALL_OT_interpolate(bpy.types.Operator):
    bl_idname = "hairball.prepare_interpolation"
    bl_label = "Create Interpolated Groom"
    bl_description = "Copy the groom with native interpolation and add a fresh persistent surface density mask; preserve the original groom"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.type == "CURVES" and context.mode == "OBJECT"

    def execute(self, context):
        try:
            result, count = prepare_interpolation(context.object, context.scene.hairball, context)
        except Exception as exc:
            if not isinstance(exc, HairballError):
                traceback.print_exc()
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        for obj in context.selected_objects:
            obj.select_set(False)
        result.select_set(True)
        context.view_layer.objects.active = result
        self.report({"INFO"}, f"New groom: {count} generated strands; use Load/Apply to adjust density")
        return {"FINISHED"}


class HAIRBALL_OT_generate(bpy.types.Operator):
    bl_idname = "hairball.generate_cards"
    bl_label = "Generate Hair Cards"
    bl_description = "Create independent cards, packed GodotHair maps and an approximate preview material"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.type == "CURVES" and context.mode == "OBJECT"

    def execute(self, context):
        try:
            result, report = generate_geometry(context.object, context.scene.hairball, context, textured=True)
        except Exception as exc:
            if not isinstance(exc, HairballError):
                traceback.print_exc()
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        for obj in context.selected_objects:
            obj.select_set(False)
        result.select_set(True)
        context.view_layer.objects.active = result
        self.report({"INFO"}, f"{report['cards']} cards, {report['triangles']} triangles, "
                    f"{report['atlas_size']}px maps; {report['seconds']}s")
        if report["sparse_cards"]:
            self.report({"WARNING"}, "Some cards have sparse coverage; inspect maps and consider a larger atlas")
        return {"FINISHED"}


class HAIRBALL_OT_geometry(bpy.types.Operator):
    bl_idname = "hairball.generate_geometry"
    bl_label = "Generate Geometry Preview"
    bl_description = "Create independent skinned ribbons with local UVs; no atlases or GodotHair maps yet"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.type == "CURVES" and context.mode == "OBJECT"

    def execute(self, context):
        try:
            result, report = generate_geometry(context.object, context.scene.hairball, context)
        except Exception as exc:
            if not isinstance(exc, HairballError):
                traceback.print_exc()
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        for obj in context.selected_objects:
            obj.select_set(False)
        result.select_set(True)
        context.view_layer.objects.active = result
        self.report({"INFO"}, f"{report['cards']} cards, {report['triangles']} triangles; geometry only, no maps")
        return {"FINISHED"}


class HAIRBALL_OT_create_groom(bpy.types.Operator):
    bl_idname = "hairball.create_groom"
    bl_label = "Create Attached Groom"
    bl_description = "Create native editable guides attached to the active mesh's UV surface"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return (context.object is not None and context.object.type == "MESH"
                and context.mode in {"OBJECT", "EDIT_MESH"})

    def execute(self, context):
        source = context.object
        previous_mode = context.mode
        previous_selection = tuple(context.selected_objects)
        settings = context.scene.hairball
        # Edit-mode face selection must be flushed to the original mesh. Refuse
        # multi-object edit mode rather than implicitly committing other meshes.
        if previous_mode == "EDIT_MESH" and len(context.objects_in_mode) != 1:
            self.report({"ERROR"}, "Exit multi-object Edit Mode before creating a groom")
            return {"CANCELLED"}
        if previous_mode == "EDIT_MESH":
            bpy.ops.object.mode_set(mode="OBJECT")
        try:
            groom = create_groom(source, count=settings.guide_count, length=settings.guide_length,
                                 points=settings.guide_points, seed=settings.seed,
                                 selected_faces=settings.growth_region == "SELECTED_FACES", context=context)
        except Exception as exc:
            for obj in context.selected_objects:
                obj.select_set(False)
            for obj in previous_selection:
                obj.select_set(True)
            context.view_layer.objects.active = source
            if previous_mode == "EDIT_MESH":
                bpy.ops.object.mode_set(mode="EDIT")
            if not isinstance(exc, HairballError):
                traceback.print_exc()
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        for obj in context.selected_objects:
            obj.select_set(False)
        groom.select_set(True)
        context.view_layer.objects.active = groom
        self.report({"INFO"}, f"Created {settings.guide_count} native guides; use Curves Sculpt to groom")
        return {"FINISHED"}


class HAIRBALL_OT_inspect(bpy.types.Operator):
    bl_idname = "hairball.inspect_groom"
    bl_label = "Validate Groom"
    bl_description = "Check final strands and supported rest recovery without modifying the groom"

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.type == "CURVES" and context.mode == "OBJECT"

    def execute(self, context):
        try:
            obj = context.object
            validate_groom(obj)
            final = evaluated_strands(obj)
            rest = rest_strands(obj, context)
            self.report({"INFO"}, f"{len(final)} evaluated strands; {len(rest)} recoverable rest strands")
            return {"FINISHED"}
        except HairballError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class HAIRBALL_OT_export_cards(bpy.types.Operator):
    bl_idname = "hairball.export_cards"
    bl_label = "Export Cards Package"
    bl_description = ("Save the selected cards result as a GLB plus both data maps under one base name, "
                      "using Blender's native exporter and image save")
    bl_options = {"REGISTER"}

    directory: bpy.props.StringProperty(subtype="DIR_PATH")
    filename: bpy.props.StringProperty(name="File Name", subtype="FILE_NAME", default="hair_cards.glb",
        description="Base name: hair_cards.glb also writes hair_cards_attributes.png and hair_cards_coordinates.png")
    include_material: bpy.props.BoolProperty(name="Include Preview Material", default=False,
        description="Embed the approximate Blender material in the GLB. Leave off for GodotHair, which supplies its own shader")

    @classmethod
    def poll(cls, context):
        return (context.object is not None and context.object.type == "MESH"
                and context.object.get("hairball_kind") == "HAIR_CARDS" and context.mode == "OBJECT")

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        try:
            paths = export_cards(context.object, self.directory, self.filename, self.include_material)
        except Exception as exc:
            if not isinstance(exc, HairballError):
                traceback.print_exc()
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, f"Exported {os.path.basename(paths['glb'])} + 2 maps")
        return {"FINISHED"}


def register():
    bpy.utils.register_class(HAIRBALL_OT_groom_color)
    bpy.utils.register_class(HAIRBALL_OT_load_interpolation)
    bpy.utils.register_class(HAIRBALL_OT_update_interpolation)
    bpy.utils.register_class(HAIRBALL_OT_interpolate)
    bpy.utils.register_class(HAIRBALL_OT_create_groom)
    bpy.utils.register_class(HAIRBALL_OT_generate)
    bpy.utils.register_class(HAIRBALL_OT_geometry)
    bpy.utils.register_class(HAIRBALL_OT_export_cards)
    bpy.utils.register_class(HAIRBALL_OT_inspect)


def unregister():
    bpy.utils.unregister_class(HAIRBALL_OT_inspect)
    bpy.utils.unregister_class(HAIRBALL_OT_export_cards)
    bpy.utils.unregister_class(HAIRBALL_OT_geometry)
    bpy.utils.unregister_class(HAIRBALL_OT_generate)
    bpy.utils.unregister_class(HAIRBALL_OT_create_groom)
    bpy.utils.unregister_class(HAIRBALL_OT_interpolate)
    bpy.utils.unregister_class(HAIRBALL_OT_update_interpolation)
    bpy.utils.unregister_class(HAIRBALL_OT_load_interpolation)
    bpy.utils.unregister_class(HAIRBALL_OT_groom_color)
