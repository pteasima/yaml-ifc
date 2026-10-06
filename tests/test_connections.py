"""Wall connections, butt-joint footprints, and axis snapping."""

import math
from pathlib import Path

import ifcopenshell
import shapely.geometry

from yaml_ifc.detect import detect_connections
from yaml_ifc.from_ifc import read_ifc
from yaml_ifc.ids import connection_yaml_id, derived_global_id
from yaml_ifc.joints import footprints
from yaml_ifc.to_ifc import validation_errors, write_ifc
from yaml_ifc.yamlio import load

from test_roundtrip import same

ROOT = Path(__file__).resolve().parents[1]
GROUND_YAML = ROOT / "samples" / "ground-floor.yaml"


def _house(walls, openings=None, connections=None, doors=None, windows=None):
    document = {
        "schema": "IFC4 ADD2 TC1",
        "units": {"LengthUnit": "METRE"},
        "project": {"id": "PRJ", "Name": "House", "Aggregates": ["SITE"]},
        "site": {"id": "SITE", "Aggregates": ["BLD"]},
        "building": {"id": "BLD", "Aggregates": ["S1"]},
        "storey": {"id": "S1", "Elevation": 0},
        "walls": walls,
        "openings": openings or [],
        "doors": doors or [],
        "windows": windows or [],
    }
    if connections:
        document = {
            **{key: document[key] for key in list(document)[:6]},
            "walls": walls,
            "connections": connections,
            "openings": document["openings"],
            "doors": document["doors"],
            "windows": document["windows"],
        }
    return document


def _world(wall, opening):
    start = wall["Axis"]["Start"]
    end = wall["Axis"]["End"]
    dx, dy = float(end[0]) - float(start[0]), float(end[1]) - float(start[1])
    length = math.hypot(dx, dy)
    along = float(opening["AlongAxis"])
    return (float(start[0]) + dx / length * along, float(start[1]) + dy / length * along)


def test_connections_round_trip_and_validate(tmp_path):
    sample = _house(
        [
            {
                "id": "W-001",
                "Axis": {"Start": [0, 0], "End": [4, 0]},
                "Thickness": 0.3,
                "Height": 2.75,
            },
            {
                "id": "W-002",
                "Axis": {"Start": [4, 0], "End": [4, 3]},
                "Thickness": 0.2,
                "Height": 2.75,
            },
            {
                "id": "W-003",
                "Axis": {"Start": [2, 0], "End": [2, 2]},
                "Thickness": 0.2,
                "Height": 2.75,
                "MaterialLayers": {
                    "Layers": [{"Name": "masonry", "LayerThickness": 0.2, "Material": "brick"}]
                },
            },
        ],
        openings=[
            {
                "id": "OP1",
                "VoidsElement": "W-001",
                "AlongAxis": 1,
                "Width": 0.9,
                "Height": 2.1,
                "SillHeight": 0,
            }
        ],
        connections=[
            {
                "RelatingElement": "W-001",
                "RelatingConnectionType": "ATEND",
                "RelatedElement": "W-002",
                "RelatedConnectionType": "ATSTART",
            },
            {
                "RelatingElement": "W-001",
                "RelatingConnectionType": "ATPATH",
                "RelatedElement": "W-003",
                "RelatedConnectionType": "ATSTART",
            },
        ],
    )
    path = tmp_path / "joints.ifc"
    write_ifc(sample, path)
    model = ifcopenshell.open(str(path))
    assert validation_errors(model) == []
    assert len(model.by_type("IfcRelConnectsPathElements")) == 2
    rel = next(
        item
        for item in model.by_type("IfcRelConnectsPathElements")
        if item.RelatedElement.Name == "W-002"
    )
    assert rel.RelatingConnectionType == "ATEND"
    assert rel.RelatedConnectionType == "ATSTART"
    assert list(rel.RelatingPriorities) == [1]
    assert list(rel.RelatedPriorities) == [0]
    assert rel.GlobalId == derived_global_id(connection_yaml_id(sample["connections"][0]))
    restored, skipped = read_ifc(path)
    assert skipped == {}
    same(sample, restored)
    # The derived thickness layer is not a YAML MaterialLayers entry.
    w1 = next(wall for wall in restored["walls"] if wall["id"] == "W-001")
    assert "MaterialLayers" not in w1
    w3 = next(wall for wall in restored["walls"] if wall["id"] == "W-003")
    assert w3["MaterialLayers"]["Layers"][0]["Material"] == "brick"


def test_butt_joint_footprints_touch_without_overlap():
    sample = _house(
        [
            {"id": "W-001", "Axis": {"Start": [0, 0], "End": [4, 0]}, "Thickness": 0.3, "Height": 2.75},
            {"id": "W-002", "Axis": {"Start": [4, 0], "End": [4, 3]}, "Thickness": 0.2, "Height": 2.75},
        ],
        connections=[
            {
                "RelatingElement": "W-001",
                "RelatingConnectionType": "ATEND",
                "RelatedElement": "W-002",
                "RelatedConnectionType": "ATSTART",
            }
        ],
    )
    rings = footprints(sample)
    assert set(rings) == {"W-001", "W-002"}
    relating = shapely.geometry.Polygon(rings["W-001"])
    related = shapely.geometry.Polygon(rings["W-002"])
    assert relating.is_valid and related.is_valid
    assert relating.area > 0 and related.area > 0
    assert relating.distance(related) < 1e-6
    assert relating.intersection(related).area < 1e-8
    shared = relating.boundary.intersection(related.boundary)
    assert shared.length > 0.15
    # The relating wall runs through, past the related wall's centre-line.
    assert relating.bounds[2] > 4.0
    assert related.bounds[1] > 0.1


def test_opening_stays_put_when_start_is_snapped():
    sample = _house(
        [
            {"id": "W-001", "Axis": {"Start": [0.15, 0], "End": [4, 0]}, "Thickness": 0.3},
            {"id": "W-002", "Axis": {"Start": [0, 0.15], "End": [0, 3]}, "Thickness": 0.3},
        ],
        openings=[
            {"id": "OP1", "VoidsElement": "W-001", "AlongAxis": 1.0, "Width": 0.9},
            {"id": "OP2", "VoidsElement": "W-002", "AlongAxis": 0.5, "Width": 0.8},
        ],
    )
    before = {
        opening["id"]: _world(
            next(wall for wall in sample["walls"] if wall["id"] == opening["VoidsElement"]),
            opening,
        )
        for opening in sample["openings"]
    }
    detected, report = detect_connections(sample)
    assert report["counts"] == {"L": 1, "T": 0}
    wall_a = next(wall for wall in detected["walls"] if wall["id"] == "W-001")
    wall_b = next(wall for wall in detected["walls"] if wall["id"] == "W-002")
    assert wall_a["Axis"]["Start"] == [0, 0]
    assert wall_b["Axis"]["Start"] == [0, 0]
    # W-001 is longer, so it is the relating wall and its start moved.
    assert detected["connections"] == [
        {
            "RelatingElement": "W-001",
            "RelatingConnectionType": "ATSTART",
            "RelatedElement": "W-002",
            "RelatedConnectionType": "ATSTART",
        }
    ]
    opening_a = next(item for item in detected["openings"] if item["id"] == "OP1")
    assert opening_a["AlongAxis"] != 1.0
    after = {
        opening["id"]: _world(
            next(wall for wall in detected["walls"] if wall["id"] == opening["VoidsElement"]),
            opening,
        )
        for opening in detected["openings"]
    }
    for opening_id, point in before.items():
        assert abs(point[0] - after[opening_id][0]) < 1e-6
        assert abs(point[1] - after[opening_id][1]) < 1e-6
    # The source document is not edited in place.
    assert sample["walls"][0]["Axis"]["Start"] == [0.15, 0]
    assert "connections" not in sample


def test_converter_does_not_invent_connections(tmp_path):
    sample = _house(
        [
            {"id": "W-001", "Axis": {"Start": [0.15, 0], "End": [4, 0]}, "Thickness": 0.3},
            {"id": "W-002", "Axis": {"Start": [0, 0.15], "End": [0, 3]}, "Thickness": 0.3},
        ]
    )
    path = tmp_path / "plain.ifc"
    write_ifc(sample, path)
    model = ifcopenshell.open(str(path))
    assert model.by_type("IfcRelConnectsPathElements") == []
    assert validation_errors(model) == []
    restored, _skipped = read_ifc(path)
    assert "connections" not in restored
    same(sample, restored)


def test_detect_is_idempotent():
    once, _report = detect_connections(load(GROUND_YAML))
    twice, _again = detect_connections(once)
    same(once, twice)


def test_ground_floor_sample_matches_detection():
    document = load(GROUND_YAML)
    detected, _report = detect_connections(document)
    same(document, detected)
    assert len(document["connections"]) == 55


def test_written_ifc_matches_twice(tmp_path):
    sample = _house(
        [
            {"id": "W-001", "Axis": {"Start": [0, 0], "End": [4, 0]}, "Thickness": 0.3, "Height": 2.5},
            {"id": "W-002", "Axis": {"Start": [4, 0], "End": [4, 3]}, "Thickness": 0.2, "Height": 2.5},
        ],
        connections=[
            {
                "RelatingElement": "W-001",
                "RelatingConnectionType": "ATEND",
                "RelatedElement": "W-002",
                "RelatedConnectionType": "ATSTART",
            }
        ],
    )
    first = tmp_path / "a.ifc"
    second = tmp_path / "b.ifc"
    write_ifc(sample, first)
    write_ifc(sample, second)
    assert first.read_bytes() == second.read_bytes()
