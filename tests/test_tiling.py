"""Sloped floor, grout joints, tile layout, and the point drain."""

import math
from pathlib import Path

import ifcopenshell
import ifcopenshell.util.placement
import numpy as np
import pytest
from shapely.geometry import Polygon

from test_roundtrip import same
from yaml_ifc import floor_joint_widths, plane_elevation
from yaml_ifc.from_ifc import read_ifc
from yaml_ifc.tiling import floor_layout, plane_minmax, wall_layout
from yaml_ifc.to_ifc import validation_errors, write_ifc
from yaml_ifc.yamlio import load

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "samples" / "bathroom.yaml"

# Room 1.20 inner faces, local origin at the inner southwest corner.
WIDTH = 2.175
DEPTH = 1.925
DOOR_CORNER = (WIDTH, DEPTH)
DRAIN_CORNER = (0.0, 0.0)
WALL_JOINT = 0.002
PITCH = 0.602


def _sample():
    return load(SAMPLE)


def _by_id(rows):
    return {row["id"]: row for row in rows}


def _plane(doc):
    return _by_id(doc["slabs"])["SLAB-1.20"]["Plane"]


def _floor(doc):
    return _by_id(doc["coverings"])["FLR-1.20"]


def _ring_area(rings):
    return sum(Polygon(ring).area for ring in rings)


def _world_points(product):
    matrix = ifcopenshell.util.placement.get_local_placement(product.ObjectPlacement)
    found = []
    seen = set()

    def walk(inst):
        if not isinstance(inst, ifcopenshell.entity_instance):
            return
        if inst.id() in seen:
            return
        seen.add(inst.id())
        if inst.is_a("IfcCartesianPoint"):
            coords = [float(value) for value in inst.Coordinates]
            while len(coords) < 3:
                coords.append(0.0)
            found.append(matrix @ np.array([*coords, 1.0]))
            return
        for value in inst:
            if isinstance(value, ifcopenshell.entity_instance):
                walk(value)
            elif isinstance(value, tuple):
                for item in value:
                    walk(item)

    walk(product.Representation)
    return found


def test_zero_slope_floor_joint_matches_the_wall():
    joints = floor_joint_widths((0.6, 0.6), (0.6, 0.6), WALL_JOINT, (0.0, 0.0))
    assert joints.x == pytest.approx(WALL_JOINT)
    assert joints.y == pytest.approx(WALL_JOINT)
    assert joints.extra_x == pytest.approx(0.0, abs=1e-12)
    assert joints.extra_y == pytest.approx(0.0, abs=1e-12)
    assert joints.plan_pitch_x == pytest.approx(0.602)


def test_one_percent_slope_widens_the_joint_by_hundredths_of_a_millimetre():
    # extra = (tile + joint) * (sqrt(1+g^2) - 1), measured on the slope.
    gradient = 0.01
    joints = floor_joint_widths((0.6, 0.6), (0.6, 0.6), WALL_JOINT, (gradient, 0.0))
    stretch = math.hypot(1.0, gradient)
    expected = (0.6 + WALL_JOINT) * stretch - 0.6
    assert joints.x == pytest.approx(expected)
    assert joints.y == pytest.approx(WALL_JOINT)
    # 0.030 mm. Three joints along a room are still under a tenth of a millimetre.
    assert joints.extra_x == pytest.approx(3.00997e-5, rel=1e-4)
    assert joints.extra_x * 1000 < 0.05


def test_sample_plane_is_zero_at_the_door_and_low_at_the_drain():
    plane = _plane(_sample())
    corners = [
        (0.0, 0.0),
        (WIDTH, 0.0),
        DOOR_CORNER,
        (0.0, DEPTH),
    ]
    elevations = [plane_elevation(plane, x, y) for x, y in corners]
    assert plane_elevation(plane, *DOOR_CORNER) == pytest.approx(0.0, abs=1e-9)
    low, high = plane_minmax(plane, corners)
    assert high == pytest.approx(0.0, abs=1e-9)
    assert low == pytest.approx(elevations[0])
    assert all(value <= 1e-9 for value in elevations)
    # 1.5% along the diagonal, about 43.6 mm, and about 9 mm across the 800 mm leaf.
    fall = -plane_elevation(plane, *DRAIN_CORNER)
    diagonal = math.hypot(WIDTH, DEPTH)
    assert fall / diagonal == pytest.approx(0.015, abs=2e-6)
    assert fall == pytest.approx(0.043566, abs=1e-6)
    leaf = plane_elevation(plane, 2.075, DEPTH) - plane_elevation(plane, 1.275, DEPTH)
    assert leaf == pytest.approx(0.008986, abs=1e-5)


def test_floor_joints_of_the_sample_and_the_alignment():
    doc = _sample()
    plane = _plane(doc)
    floor = _floor(doc)["TileLayout"]
    joints = floor_joint_widths(floor["Tile"], floor["Tile"], floor["WallJoint"], plane["Gradient"])
    # 2.038 mm and 2.030 mm against a 2.000 mm wall joint.
    assert joints.x * 1000 == pytest.approx(2.03797, abs=1e-4)
    assert joints.y * 1000 == pytest.approx(2.02975, abs=1e-4)
    assert joints.extra_x * 1000 == pytest.approx(0.03797, abs=1e-4)
    assert joints.extra_y * 1000 == pytest.approx(0.02975, abs=1e-4)
    assert joints.plan_pitch_x == pytest.approx(PITCH)
    assert joints.plan_pitch_y == pytest.approx(PITCH)

    laid = floor_layout(
        plane,
        floor["Tile"],
        floor["Tile"],
        floor["WallJoint"],
        floor["GridOrigin"],
        floor["Footprint"],
        floor["Cutouts"],
        floor["JointInset"],
    )
    room = WIDTH * DEPTH
    # The grate sits in the corner, so the silicone inset only remains on the two inner edges.
    hole = (0.3 + floor["JointInset"]) ** 2
    assert _ring_area(laid["tiles"]) + _ring_area(laid["grout"]) == pytest.approx(room - hole)
    assert laid["tiles"]
    # Module lines from the door corner. The drain cuts some tiles, so not every
    # edge sits on a line; every line does sit on a tile edge.
    def grid_values(rings, index, origin):
        found = set()
        for ring in rings:
            for point in ring:
                value = point[index]
                if _on_grid(value, origin):
                    found.add(round(value, 6))
        return found

    assert {round(WIDTH - n * PITCH, 6) for n in range(4)} <= grid_values(laid["tiles"], 0, WIDTH)
    assert {round(DEPTH - n * PITCH, 6) for n in range(4)} <= grid_values(laid["tiles"], 1, DEPTH)
    # West cut about 369 mm, south sliver about 119 mm, drain excluded.
    xs = [point[0] for ring in laid["tiles"] for point in ring]
    ys = [point[1] for ring in laid["tiles"] for point in ring]
    assert min(xs) == pytest.approx(0.0, abs=1e-6)
    assert min(ys) == pytest.approx(0.0, abs=1e-6)
    # Three pitches from the door corner: a 369 mm cut on the west, a 119 mm sliver on the south.
    assert round(WIDTH - 3 * PITCH, 6) == pytest.approx(0.369, abs=1e-3)
    assert round(DEPTH - 3 * PITCH, 6) == pytest.approx(0.119, abs=1e-3)
    drain = Polygon([(0, 0), (0.302, 0), (0.302, 0.302), (0, 0.302)])
    for ring in (*laid["tiles"], *laid["grout"]):
        assert Polygon(ring).intersection(drain).area == pytest.approx(0.0, abs=1e-8)

    # South wall has no opening, so the module at the east end is a full tile.
    # It ends on the same line as the floor tile. The floor tile is shorter in
    # plan by the extra joint, about 0.038 mm.
    south = _by_id(doc["coverings"])["CLAD-S"]["TileLayout"]
    wall = wall_layout(
        plane,
        south["Tile"],
        south["Joint"],
        south["Courses"],
        south["BottomJoint"],
        south["GridOrigin"],
        south["Axis"],
        south["Inside"],
        south.get("Openings") or (),
        footprint=_by_id(doc["slabs"])["SLAB-1.20"]["Footprint"],
    )
    assert wall["pitch"] == pytest.approx(PITCH)
    floor_full = next(
        ring
        for ring in laid["tiles"]
        if max(point[0] for point in ring) == pytest.approx(WIDTH)
        and max(point[1] for point in ring) == pytest.approx(DEPTH)
    )
    wall_full = next(
        tile
        for tile in wall["tiles"]
        if max(point[0] for point in tile["polygon"]) == pytest.approx(WIDTH)
        and min(point[0] for point in tile["polygon"]) > 1.5
    )
    floor_low = min(point[0] for point in floor_full)
    wall_low = min(point[0] for point in wall_full["polygon"])
    assert floor_low - wall_low == pytest.approx(joints.plan_joint_x - WALL_JOINT, abs=1e-6)
    assert abs(floor_low - wall_low) * 1000 == pytest.approx(0.0378, abs=1e-3)


def _on_grid(value, origin):
    if value > origin + 1e-6:
        return False
    steps = (origin - value) / PITCH
    return abs(steps - round(steps)) < 1e-4


def test_bottom_course_follows_the_slope_and_openings_cut_tiles():
    doc = _sample()
    plane = _plane(doc)
    footprint = _by_id(doc["slabs"])["SLAB-1.20"]["Footprint"]
    north = _by_id(doc["coverings"])["CLAD-N"]["TileLayout"]
    wall = wall_layout(
        plane,
        north["Tile"],
        north["Joint"],
        north["Courses"],
        north["BottomJoint"],
        north["GridOrigin"],
        north["Axis"],
        north["Inside"],
        north["Openings"],
        footprint=footprint,
    )
    bottoms = [tile for tile in wall["tiles"] if tile["course"] == 0]
    uppers = [tile for tile in wall["tiles"] if tile["course"] == 1]
    assert bottoms and uppers
    for tile in bottoms:
        polygon = tile["polygon"]
        z0 = polygon[0][1]
        z1 = polygon[1][1]
        top = polygon[2][1]
        assert polygon[3][1] == pytest.approx(top)
        assert top == pytest.approx(wall["levels"]["bottom_top"])
        for (along, z) in polygon[:2]:
            x, y = _plan(north["Axis"], along)
            assert z == pytest.approx(plane_elevation(plane, x, y) + north["BottomJoint"])
        # The two bottom corners differ: the cut follows the slope.
        if tile.get("sloped"):
            assert z0 != pytest.approx(z1)
    # A level upper course, and nothing in the door below the head.
    for tile in uppers:
        polygon = tile["polygon"]
        assert polygon[0][1] == pytest.approx(polygon[1][1])
        assert polygon[2][1] == pytest.approx(polygon[3][1])
    for tile in wall["tiles"]:
        s0 = min(point[0] for point in tile["polygon"])
        s1 = max(point[0] for point in tile["polygon"])
        z0 = min(point[1] for point in tile["polygon"])
        if s0 >= 1.175 - 1e-6 and s1 <= 2.075 + 1e-6:
            assert z0 == pytest.approx(2.1)
    # Full blank at the drain, shorter at the door corner.
    west = _by_id(doc["coverings"])["CLAD-W"]["TileLayout"]
    west_wall = wall_layout(
        plane,
        west["Tile"],
        west["Joint"],
        west["Courses"],
        west["BottomJoint"],
        west["GridOrigin"],
        west["Axis"],
        west["Inside"],
        west["Openings"],
        footprint=footprint,
    )
    at_drain = [
        tile
        for tile in west_wall["tiles"]
        if tile["course"] == 0 and min(point[0] for point in tile["polygon"]) < 1e-6
    ]
    assert at_drain
    polygon = at_drain[0]["polygon"]
    height = max(point[1] for point in polygon) - min(point[1] for point in polygon)
    assert height == pytest.approx(1.2, abs=1e-6)
    # Window keeps tiles below the sill and stops the upper course at 1.75 m.
    in_window = [
        tile
        for tile in west_wall["tiles"]
        if min(point[0] for point in tile["polygon"]) >= 0.775 - 1e-6
        and max(point[0] for point in tile["polygon"]) <= 1.675 + 1e-6
    ]
    assert any(tile["course"] == 0 for tile in in_window)
    assert max(point[1] for tile in in_window for point in tile["polygon"]) == pytest.approx(1.75)
    assert wall["levels"]["head"] == pytest.approx(2.360434, abs=1e-5)


def _plan(axis, along):
    start, end = axis["Start"], axis["End"]
    length = math.hypot(end[0] - start[0], end[1] - start[1])
    return (
        start[0] + (end[0] - start[0]) * along / length,
        start[1] + (end[1] - start[1]) * along / length,
    )


def test_bathroom_round_trip_and_ifc(tmp_path):
    original = _sample()
    path = tmp_path / "bathroom.ifc"
    write_ifc(original, path)
    model = ifcopenshell.open(str(path))
    assert validation_errors(model) == []
    restored, skipped = read_ifc(path)
    assert skipped == {}
    same(original, restored)

    slab = next(item for item in model.by_type("IfcSlab") if item.Name == "Screed")
    assert slab.PredefinedType == "FLOOR"
    assert slab.Representation is None
    drain = model.by_type("IfcWasteTerminal")[0]
    assert drain.PredefinedType == "FLOORTRAP"
    assert drain.ObjectType == "PointDrain"
    assert drain.Name == "ACO 450420"
    props = {}
    for rel in drain.IsDefinedBy:
        pset = rel.RelatingPropertyDefinition
        if pset.Name != "Pset_ManufacturerTypeInformation":
            continue
        for prop in pset.HasProperties:
            props[prop.Name] = prop.NominalValue.wrappedValue
    assert props["Manufacturer"] == "ACO"
    assert props["ArticleNumber"] == "450420"

    floor = next(item for item in model.by_type("IfcCovering") if item.Name == "Floor tiles")
    body = floor.Representation.Representations[0]
    assert body.RepresentationType == "Brep"
    assert all(item.is_a("IfcFacetedBrep") for item in body.Items)
    points = _world_points(floor)
    assert points
    assert max(point[2] for point in points) <= 1e-6
    door = [
        point
        for point in points
        if abs(point[0] - WIDTH) < 1e-4 and abs(point[1] - DEPTH) < 1e-4
    ]
    assert door
    assert door[0][2] == pytest.approx(0.0, abs=1e-6)

    grate = _world_points(drain)
    plane = _plane(original)
    for point in grate:
        assert point[2] <= plane_elevation(plane, point[0], point[1]) + 1e-6
    corner = [
        point for point in grate if abs(point[0]) < 1e-4 and abs(point[1]) < 1e-4
    ]
    assert corner
    assert max(point[2] for point in corner) == pytest.approx(plane_elevation(plane, 0, 0), abs=1e-5)
    assert max(point[2] for point in corner) < -0.04

    membrane = next(item for item in model.by_type("IfcCovering") if item.Name == "Waterproofing")
    assert membrane.Representation is None
    ceiling = next(item for item in model.by_type("IfcCovering") if item.Name == "Suspended ceiling")
    assert ceiling.Representation is None


def test_authored_floor_joint_is_not_stored_and_bad_cuts_fail(tmp_path):
    doc = _sample()
    restored, _skipped = read_ifc(_write(doc, tmp_path))
    floor = _by_id(restored["coverings"])["FLR-1.20"]["TileLayout"]
    assert "Joint" not in floor
    assert floor["WallJoint"] == pytest.approx(WALL_JOINT)

    doc["coverings"][1]["TileLayout"]["BottomCut"] = "level"
    with pytest.raises(ValueError, match="follow-slope"):
        write_ifc(doc, tmp_path / "bad.ifc")


def test_slab_thickness_round_trips(tmp_path):
    doc = {
        "schema": "IFC4 ADD2 TC1",
        "units": {"LengthUnit": "METRE"},
        "project": {"id": "PRJ", "Aggregates": ["SITE"]},
        "site": {"id": "SITE", "Aggregates": ["BLD"]},
        "building": {"id": "BLD", "Aggregates": ["S1"]},
        "storey": {"id": "S1", "Elevation": 0},
        "walls": [],
        "openings": [],
        "doors": [],
        "windows": [],
        "slabs": [
            {
                "id": "SLAB",
                "PredefinedType": "FLOOR",
                "ObjectType": "Screed",
                "Thickness": 0.07,
                "Plane": {"Origin": [1, 1], "Elevation": 0, "Gradient": [0.01, 0]},
                "Footprint": [[0, 0], [2, 0], [2, 1], [0, 1]],
            }
        ],
    }
    path = tmp_path / "slab.ifc"
    write_ifc(doc, path)
    model = ifcopenshell.open(str(path))
    assert validation_errors(model) == []
    slab = model.by_type("IfcSlab")[0]
    assert slab.Representation.Representations[0].RepresentationType == "Brep"
    restored, skipped = read_ifc(path)
    assert skipped == {}
    same(doc, restored)


def _write(doc, tmp_path):
    path = tmp_path / "out.ifc"
    write_ifc(doc, path)
    return path
