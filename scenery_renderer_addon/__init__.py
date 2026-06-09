"""
OpenRCT2 Scenery Generator: Blender add-on entry point.
"""

from . import operators, panels, props


def register():
    props.register()
    operators.register()
    panels.register()


def unregister():
    panels.unregister()
    operators.unregister()
    props.unregister()
