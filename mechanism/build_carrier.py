"""Compute the curved B-rep with FreeCAD; import and inspect it in SolidCraft.

Run with FreeCAD's bundled Python. Dimensions come from build_carrier.json.
SolidCraft 0.19.0 cannot complete the intersecting cylindrical cuts in this part.
"""

from __future__ import annotations

import json
import math
import re
import sys
from dataclasses import asdict, dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Final, assert_never

import FreeCAD as App
import Import
import Part

ROOT: Final = Path(__file__).resolve().parent
Z_AXIS: Final = App.Vector(0, 0, 1)
X_AXIS: Final = App.Vector(1, 0, 0)


@dataclass(frozen=True, slots=True)
class Dimensions:
    ground_clearance: float
    carrier_t: float
    housing_h: float
    inner_r: float
    outer_r: float
    sensor_angle: float
    panel_r: float
    pcb_t: float
    can_pitch: float
    can_clearance: float
    bolt_d: float
    qi_width: float
    qi_depth: float
    qi_height: float
    qi_extra: float
    support_t: float
    qi_width_tol: float
    qi_height_tol: float


@dataclass(frozen=True, slots=True)
class Mount:
    carrier: Part.Shape
    clamps: tuple[Part.Shape, ...]


class WalkCommand(StrEnum):
    CHANGE = "parameters.change"
    INSPECT = "document.inspect"


class NonLiteralDimensionError(Exception):
    def __init__(self, expression: str) -> None:
        self.expression = expression
        super().__init__(f"Use a numeric mm/deg dimension, not {expression!r}.")


def number(expression: str) -> float:
    match = re.fullmatch(r"\s*([-+]?\d+(?:\.\d+)?)\s*(?:mm|deg)?\s*", expression)
    if match is None:
        raise NonLiteralDimensionError(expression)
    return float(match[1])


def build(d: Dimensions) -> Mount:
    """Build one connected carrier and four removable flat clamps."""
    g, r, p = d.ground_clearance, d.panel_r, d.pcb_t
    assert g == 20 and d.carrier_t == 4 and d.support_t == 6
    assert d.housing_h == 27.3
    assert 28 <= d.sensor_angle <= 30
    carrier = Part.makeCylinder(
        d.outer_r, d.housing_h, App.Vector(-32, 0, g), Z_AXIS, 104
    )
    carrier.rotate(App.Vector(-32, 0, 0), Z_AXIS, -52)
    carrier = carrier.cut(
        Part.makeCylinder(d.inner_r, 30, App.Vector(-32, 0, g - 1))
    )

    support = Part.makeBox(33, 29.6, d.support_t, App.Vector(13, -14.8, g + 2))
    stop = Part.makeBox(4, 29.6, 2.2, App.Vector(32, -14.8, g))
    ribs = []
    for y in (4.5, -7.5):
        wire = Part.makePolygon(
            [App.Vector(14, y, g + 7.8), App.Vector(34, y, g + 14),
             App.Vector(46, y, g + 7.8), App.Vector(14, y, g + 7.8)]
        )
        ribs.append(Part.Face(wire).extrude(App.Vector(0, 3, 0)))
    carrier = carrier.fuse([support, stop, *ribs])

    clearances = []
    for x in (17, 23):
        for y in (-6, 6):
            clearances.append(Part.makeCylinder(2.5, 2.7, App.Vector(x, y, g + 1)))
    for y in (-12, 12):
        clearances.extend([
            Part.makeCylinder(d.bolt_d / 2, 12, App.Vector(32, y, g - 1)),
            Part.makeCylinder(2.6, 3.2, App.Vector(32, y, g - 1)),
        ])
    for y in (-60, 60):
        clearances.append(Part.makeCylinder(6.2, 32, App.Vector(16, y, g - 1)))
    carrier = carrier.cut(clearances)

    clamps = []
    for angle in (d.sensor_angle, -d.sensor_angle):
        tools = [
            Part.makeBox(p + 12, 45.4, 20.4, App.Vector(r - p - 12, -22.7, g + 3.8)),
            Part.makeBox(12, 9.9, 19.2, App.Vector(r - p - 12, -31.2, g + 4.8)),
            Part.makeBox(12, 9.9, 19.2, App.Vector(r - p - 12, 21.3, g + 4.8)),
            Part.makeBox(
                3 + 2 * d.qi_extra,
                d.qi_width + d.qi_width_tol + 2 * d.qi_extra,
                d.qi_height + 3 + 2 * d.qi_extra,
                App.Vector(r - p - 3 - d.qi_extra,
                           -(d.qi_width + d.qi_width_tol) / 2 - d.qi_extra,
                           g + 24 - d.qi_extra),
            ),
        ]
        for t in (-d.can_pitch / 2, d.can_pitch / 2):
            tools.append(Part.makeCylinder(
                d.can_clearance / 2, 17, App.Vector(r - 2, t, g + 14), X_AXIS
            ))
        for t in (-26.5, 26.5):
            tools.extend([
                Part.makeCylinder(d.bolt_d / 2, 13, App.Vector(r - p - 1, t, g + 14), X_AXIS),
                Part.makeCylinder(3.3, 14.5, App.Vector(r + 0.5, t, g + 14), X_AXIS),
            ])
        for tool in tools:
            tool.rotate(App.Vector(0, 0, 0), Z_AXIS, angle)
            tool.translate(App.Vector(-32, 0, 0))
        carrier = carrier.cut(tools)
        for t0, t in ((-31, -26.5), (21.5, 26.5)):
            clamp = Part.makeBox(2.4, 9.5, 18.8, App.Vector(r - p - 2.4, t0, g + 5))
            clamp = clamp.cut(Part.makeCylinder(
                d.bolt_d / 2, 4.4, App.Vector(r - p - 3.4, t, g + 14), X_AXIS
            ))
            clamp.rotate(App.Vector(0, 0, 0), Z_AXIS, angle)
            clamp.translate(App.Vector(-32, 0, 0))
            clamps.append(clamp.removeSplitter())
    return Mount(carrier.removeSplitter(), tuple(clamps))


def check(mount: Mount, d: Dimensions) -> None:
    """Reject disconnected, invalid or obstructed geometry before exporting."""
    for shape in (mount.carrier, *mount.clamps):
        assert shape.isValid() and len(shape.Solids) == 1 and shape.Volume > 0
    assert abs(mount.carrier.BoundBox.ZMin - 20) < 1e-6
    assert abs(mount.carrier.BoundBox.ZMax - 47.3) < 1e-6
    for clamp in mount.clamps:
        assert mount.carrier.common(clamp).Volume < 1e-6
    for angle in (d.sensor_angle, -d.sensor_angle):
        theta = math.radians(angle)
        normal = App.Vector(math.cos(theta), math.sin(theta), 0)
        origin = App.Vector(-32, 0, 0)
        seat_area = sum(
            face.Area for face in mount.carrier.Faces
            if abs(abs(face.normalAt(0, 0).dot(normal)) - 1) < 1e-8
            and abs((face.CenterOfMass - origin).dot(normal) - d.panel_r) < 1e-6
        )
        assert seat_area > 100, "The planar PCB seat must remain after the openings."
        for t in (-d.can_pitch / 2, d.can_pitch / 2):
            transducer = Part.makeCylinder(
                8, 12, App.Vector(d.panel_r, t, d.ground_clearance + 14), X_AXIS
            )
            transducer.rotate(App.Vector(0, 0, 0), Z_AXIS, angle)
            transducer.translate(App.Vector(-32, 0, 0))
            assert mount.carrier.common(transducer).Volume < 1e-6
        keepout = Part.makeBox(
            d.qi_depth + 2 * d.qi_extra,
            d.qi_width + d.qi_width_tol + 2 * d.qi_extra,
            d.qi_height + d.qi_height_tol + 2 * d.qi_extra,
            App.Vector(d.panel_r - d.pcb_t - 1.68 - d.qi_depth / 2 - d.qi_extra,
                       -(d.qi_width + d.qi_width_tol) / 2 - d.qi_extra,
                       d.ground_clearance + 26.5 - d.qi_extra),
        )
        keepout.rotate(App.Vector(0, 0, 0), Z_AXIS, angle)
        keepout.translate(App.Vector(-32, 0, 0))
        assert mount.carrier.common(keepout).Volume < 1e-6
    for y in (-12, 12):
        driver = Part.makeCylinder(4, 14, App.Vector(32, y, 28))
        assert mount.carrier.common(driver).Volume < 1e-6


def main() -> None:
    with (ROOT / "build_carrier.json").open(encoding="utf-8") as stream:
        recipe = json.load(stream)
    values = {
        step["params"]["name"]: number(step["params"]["expression"])
        for step in recipe["commands"] if step["command"] == "parameters.add"
    }
    dimensions = Dimensions(**values)
    mount = build(dimensions)
    check(mount, dimensions)
    doc = App.newDocument("MountGeometry")
    names = ("Carrier", "LeftInnerClamp", "LeftOuterClamp", "RightInnerClamp", "RightOuterClamp")
    objects = []
    for name, shape in zip(names, (mount.carrier, *mount.clamps), strict=True):
        obj = doc.addObject("Part::Feature", name)
        obj.Label = name
        obj.Shape = shape
        objects.append(obj)
    doc.recompute()
    Import.export(objects, str(ROOT / "reference" / "mount_master.step"))
    report = {
        "backend": f"FreeCAD {'.'.join(App.Version()[:3])} / OpenCASCADE",
        "carrier_volume_mm3": mount.carrier.Volume,
        "carrier_solids": len(mount.carrier.Solids),
        "carrier_valid": mount.carrier.isValid(),
        "qi_extra_each_side_mm": dimensions.qi_extra,
        "qi_roof_window_width_mm": dimensions.qi_width + dimensions.qi_width_tol + 2 * dimensions.qi_extra,
        "driver_clearance_diameter_mm": 8,
    }
    if "--verify" in sys.argv:
        with (ROOT / "parameter_walk.json").open(encoding="utf-8") as stream:
            walk = json.load(stream)
        current = dimensions
        cases = []
        for command in walk["commands"]:
            match WalkCommand(command["command"]):
                case WalkCommand.CHANGE:
                    current = replace(current, **{
                        command["params"]["name"]: number(command["params"]["expression"])
                    })
                case WalkCommand.INSPECT:
                    variant = build(current)
                    check(variant, current)
                    cases.append({
                        "parameters": asdict(current),
                        "volume_mm3": variant.carrier.Volume,
                        "valid": True,
                    })
                case unreachable:
                    assert_never(unreachable)
        assert current == dimensions
        report["parameter_states"] = cases
    with (ROOT / "verification" / "source_geometry.json").open("w", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps(report, indent=2))
    App.closeDocument(doc.Name)


if __name__ == "__main__":
    main()
