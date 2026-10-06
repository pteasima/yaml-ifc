"""Round trips for the ground floor and the external IFC sample."""

from pathlib import Path

import ifcopenshell

from yaml_ifc.from_ifc import format_skipped, read_ifc
from yaml_ifc.ids import derived_global_id
from yaml_ifc.supported import SUPPORTED
from yaml_ifc.to_ifc import validation_errors, write_ifc
from yaml_ifc.yamlio import load

ROOT = Path(__file__).resolve().parents[1]
GROUND_YAML = ROOT / "samples" / "ground-floor.yaml"
GROUND_IFC = ROOT / "samples" / "ground-floor.ifc"
EXTERNAL_IFC = ROOT / "samples" / "external" / "IfcOpenHouse_IFC4.ifc"
EXTERNAL_YAML = ROOT / "samples" / "external" / "IfcOpenHouse_IFC4.yaml"
EXTERNAL_SKIPPED = ROOT / "samples" / "external" / "IfcOpenHouse_IFC4.skipped.txt"

TOL = 1e-5


def same(left, right, path=""):
    if isinstance(left, dict) and isinstance(right, dict):
        for key in list(dict.fromkeys([*left, *right])):
            if key not in left or key not in right:
                side = "left" if key in left else "right"
                raise AssertionError(f"{path}.{key} only on the {side}")
            same(left[key], right[key], f"{path}.{key}")
        return
    if isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            raise AssertionError(f"{path} length {len(left)} != {len(right)}")
        for index, (item, other) in enumerate(zip(left, right)):
            same(item, other, f"{path}[{index}]")
        return
    if isinstance(left, bool) or isinstance(right, bool):
        if left != right:
            raise AssertionError(f"{path} {left!r} != {right!r}")
        return
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        if abs(float(left) - float(right)) > TOL:
            raise AssertionError(f"{path} {left} != {right}")
        return
    if left != right:
        raise AssertionError(f"{path} {left!r} != {right!r}")


def index_by_global_id(doc):
    found = {}

    def take(entity):
        gid = entity.get("GlobalId") or derived_global_id(entity["id"])
        found[gid] = entity

    for _cls, key, is_list in SUPPORTED:
        value = doc[key]
        if is_list:
            for entity in value:
                take(entity)
        else:
            take(value)
    return found


def test_ground_floor_yaml_round_trip(tmp_path):
    original = load(GROUND_YAML)
    ifc_path = tmp_path / "ground-floor.ifc"
    write_ifc(original, ifc_path)
    restored, skipped = read_ifc(ifc_path)
    assert skipped == {}
    same(original, restored)


def test_ground_floor_ifc_validates_and_counts():
    model = ifcopenshell.open(str(GROUND_IFC))
    assert validation_errors(model) == []
    assert len(model.by_type("IfcWall")) == 67
    assert len(model.by_type("IfcOpeningElement")) == 50
    assert len(model.by_type("IfcDoor")) == 24
    assert len(model.by_type("IfcWindow")) == 24
    assert len(model.by_type("IfcRelVoidsElement")) == 50
    assert len(model.by_type("IfcRelFillsElement")) == 48
    thin = next(wall for wall in model.by_type("IfcWall") if wall.Name == "W-017")
    assert [rep.RepresentationIdentifier for rep in thin.Representation.Representations] == ["Axis"]
    band = next(wall for wall in model.by_type("IfcWall") if wall.Name == "W-002")
    body = next(rep for rep in band.Representation.Representations if rep.RepresentationIdentifier == "Body")
    assert body.Items[0].Depth == 3.0
    assert body.Items[0].SweptArea.YDim == 0.375


def test_ground_floor_reference_matches(tmp_path):
    fresh = tmp_path / "ground-floor.ifc"
    write_ifc(load(GROUND_YAML), fresh)
    assert fresh.read_bytes() == GROUND_IFC.read_bytes()


def test_external_ifc_validates():
    model = ifcopenshell.open(str(EXTERNAL_IFC))
    assert model.schema == "IFC4"
    assert validation_errors(model) == []


def test_external_coverage_follows_the_registry():
    model = ifcopenshell.open(str(EXTERNAL_IFC))
    document, _skipped = read_ifc(EXTERNAL_IFC)
    by_gid = index_by_global_id(document)
    id_of = {gid: entity["id"] for gid, entity in by_gid.items()}
    for cls, _key, _is_list in SUPPORTED:
        for entity in model.by_type(cls):
            assert entity.GlobalId in by_gid, cls
    for rel in model.by_type("IfcRelVoidsElement"):
        opening = by_gid[rel.RelatedOpeningElement.GlobalId]
        assert opening["VoidsElement"] == id_of[rel.RelatingBuildingElement.GlobalId]
    for rel in model.by_type("IfcRelFillsElement"):
        filler = rel.RelatedBuildingElement
        if not (filler.is_a("IfcDoor") or filler.is_a("IfcWindow")):
            continue
        entity = by_gid[filler.GlobalId]
        assert entity["FillsOpening"] == id_of[rel.RelatingOpeningElement.GlobalId]


def test_external_round_trip_is_stable(tmp_path):
    first, _skipped = read_ifc(EXTERNAL_IFC)
    ifc_path = tmp_path / "again.ifc"
    write_ifc(first, ifc_path)
    second, _skipped = read_ifc(ifc_path)
    same(first, second)
    assert validation_errors(ifcopenshell.open(str(ifc_path))) == []


def test_external_reference_matches():
    document, skipped = read_ifc(EXTERNAL_IFC)
    same(document, load(EXTERNAL_YAML))
    assert format_skipped(skipped) == EXTERNAL_SKIPPED.read_text(encoding="utf-8")


def test_extensions_round_trip(tmp_path):
    gid = derived_global_id("explicit-other")
    sample = {
        "schema": "IFC4 ADD2 TC1",
        "units": {"LengthUnit": "METRE"},
        "project": {"id": "PRJ", "Name": "House", "Aggregates": ["SITE"]},
        "site": {"id": "SITE", "Aggregates": ["BLD"]},
        "building": {"id": "BLD", "Aggregates": ["S1"]},
        "storey": {"id": "S1", "Elevation": 0},
        "walls": [
            {
                "id": "W1",
                "Name": "South",
                "GlobalId": gid,
                "Axis": {"Start": [0, 0], "End": [4, 0]},
                "Thickness": 0.3,
                "Height": 2.75,
                "MaterialLayers": {
                    "Layers": [{"Name": "masonry", "LayerThickness": 0.3, "Material": "brick"}]
                },
                "PropertySets": [
                    {
                        "Name": "Pset_WallCommon",
                        "Properties": {"LoadBearing": True, "IsExternal": False},
                    }
                ],
            },
            {
                "id": "W2",
                "Axis": {"Start": [0, 2], "End": [2, 2]},
                "Footprint": [[0, 1.85], [2, 1.85], [2, 2.15], [0, 2.15]],
                "Height": 2.5,
            },
            {
                "id": "W3",
                "Axis": {"Start": [0, 0], "End": [0, 2]},
                "Profile": [[0, -0.1], [1.5, -0.1], [1.5, 0.2], [0, 0.2]],
                "Height": 2.2,
            },
        ],
        "openings": [
            {
                "id": "OP1",
                "VoidsElement": "W1",
                "AlongAxis": 1,
                "Width": 0.9,
                "Height": 2.1,
                "SillHeight": 0,
                "Tag": "D1",
            },
            {"id": "OP2", "VoidsElement": "W1", "AlongAxis": 2.5, "Width": 1.0, "HeadHeight": 2.4},
        ],
        "doors": [
            {
                "id": "D1",
                "FillsOpening": "OP1",
                "OverallWidth": 0.8,
                "OverallHeight": 2.1,
                "OperationType": "SINGLE_SWING_LEFT",
                "PredefinedType": "DOOR",
            }
        ],
        "windows": [
            {"id": "WIN", "OverallWidth": 1.2, "OverallHeight": 1.0, "PredefinedType": "WINDOW"}
        ],
    }
    path = tmp_path / "ext.ifc"
    write_ifc(sample, path)
    assert validation_errors(ifcopenshell.open(str(path))) == []
    restored, skipped = read_ifc(path)
    assert skipped == {}
    same(sample, restored)
