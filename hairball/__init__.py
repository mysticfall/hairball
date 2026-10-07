"""Hairball extension; imports and registration never mutate scene data."""
import importlib

_MODULES = ("evaluation", "native", "deformation", "groom", "cards", "clustering", "atlas", "baking", "materials", "geometry", "export", "model", "operators", "ui")
for _name in _MODULES:
    if _name in globals():
        globals()[_name] = importlib.reload(globals()[_name])
    else:
        globals()[_name] = importlib.import_module(f".{_name}", __package__)


def register():
    model.register()
    operators.register()
    ui.register()


def unregister():
    ui.unregister()
    operators.unregister()
    model.unregister()
