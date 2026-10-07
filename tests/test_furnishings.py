"""Furnishings, spaces, and the type objects derived from them."""

from pathlib import Path

import ifcopenshell
import pytest

from test_roundtrip import same
from yaml_ifc.from_ifc import read_ifc
from yaml_ifc.ids import derived_global_id
from yaml_ifc.supported import FURNISHINGS, PREDEFINED_TYPES, SUPPORTED
from yaml_ifc.to_ifc import validation_errors, write_ifc
from yaml_ifc.yamlio import load

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "samples" / "furnishings.yaml"


def _shell():
    return {
        "schema": "IFC4 ADD2 TC1",
        "units": {"LengthUnit": "METRE"},
        "project": {"id": "PRJ", "Name": "House", "Aggregates": ["SITE"]},
        "site": {"id": "SITE", "Aggregates": ["BLD"]},
        "building": {"id": "BLD", "Aggregates": ["S1"]},
        "storey": {"id": "S1", "Elevation": 0},
        "walls": [],
        "openings": [],
        "doors": [],
        "windows": [],
    }


def _round_trip(doc, tmp_path):
    path = tmp_path / "out.ifc"
    write_ifc(doc, path)
    model = ifcopenshell.open(str(path))
    assert validation_errors(model) == []
    restored, skipped = read_ifc(path)
    assert skipped == {}
    same(doc, restored)
    return model


def test_registry_lists_the_furnishing_classes():
    keys = {key for _cls, key, is_list in SUPPORTED if is_list}
    assert "spaces" in keys
    for key, ifc_class, _type_class in FURNISHINGS:
        assert key in keys
        assert ifc_class in PREDEFINED_TYPES


def test_furnishings_sample_round_trip(tmp_path):
    original = load(SAMPLE)
    model = _round_trip(original, tmp_path)

    spaces = {space.Name: space for space in model.by_type("IfcSpace")}
    assert set(spaces) == {"Kitchen", "Dining", "Living"}
    storey = model.by_type("IfcBuildingStorey")[0]
    aggregated = []
    for rel in storey.IsDecomposedBy:
        aggregated.extend(rel.RelatedObjects or [])
    assert {space.Name for space in aggregated} == set(spaces)

    kitchen = spaces["Kitchen"]
    contained = {
        element.Name
        for rel in kitchen.ContainsElements
        for element in rel.RelatedElements
    }
    assert {"Island", "Sink", "Cooktop", "Fridge", "Oven", "Hood"} <= contained
    assert "Sectional sofa" not in contained

    # The two dining chairs are one catalogue type.
    chair_types = [
        rel.RelatingType
        for rel in model.by_type("IfcRelDefinesByType")
        if rel.RelatingType.is_a("IfcFurnitureType") and rel.RelatingType.Name == "DiningChair"
    ]
    assert len(chair_types) == 1
    assert len(chair_types[0].Types[0].RelatedObjects) == 2
    assert chair_types[0].PredefinedType == "CHAIR"
    assert chair_types[0].ElementType == "DiningChair"
    assert chair_types[0].AssemblyPlace == "NOTDEFINED"

    island_type = next(
        element
        for element in model.by_type("IfcSystemFurnitureElementType")
        if element.Name == "Island"
    )
    assert island_type.PredefinedType == "USERDEFINED"
    assert island_type.ElementType == "Island"
    assert not hasattr(island_type, "AssemblyPlace") or island_type.AssemblyPlace is None

    cooktop = next(element for element in model.by_type("IfcElectricAppliance") if element.Name == "Cooktop")
    assert cooktop.PredefinedType == "ELECTRICCOOKER"
    assert cooktop.ObjectType == "Cooktop"
    fridge = next(element for element in model.by_type("IfcElectricAppliance") if element.Name == "Fridge")
    assert fridge.PredefinedType == "REFRIGERATOR"
    oven = next(element for element in model.by_type("IfcElectricAppliance") if element.Name == "Oven")
    assert oven.PredefinedType == "USERDEFINED"
    assert oven.ObjectType == "BuiltInOven"
    hood = next(element for element in model.by_type("IfcElectricAppliance") if element.Name == "Hood")
    assert hood.PredefinedType == "USERDEFINED"
    assert hood.ObjectType == "CeilingHood"

    sink = model.by_type("IfcSanitaryTerminal")[0]
    assert sink.PredefinedType == "SINK"
    assert sink.ObjectType == "KitchenSink"

    rug = model.by_type("IfcCovering")[0]
    assert rug.PredefinedType == "USERDEFINED"
    assert rug.ObjectType == "Rug"
    track = model.by_type("IfcLightFixture")[0]
    assert track.PredefinedType == "DIRECTIONSOURCE"
    assert track.ObjectType == "TrackLight"

    base = next(element for element in model.by_type("IfcSystemFurnitureElement") if element.Name == "Base cabinet")
    solid = next(
        item
        for rep in base.Representation.Representations
        if rep.RepresentationIdentifier == "Body"
        for item in rep.Items
    )
    assert solid.is_a("IfcExtrudedAreaSolid")
    assert solid.SweptArea.XDim == 0.6
    assert solid.SweptArea.YDim == 0.6
    assert solid.Depth == 0.9
    # No catalogue pset: the type string is ObjectType, and the box is the body.
    pset_names = {
        rel.RelatingPropertyDefinition.Name
        for rel in base.IsDefinedBy
        if rel.is_a("IfcRelDefinesByProperties")
    }
    assert pset_names == {"yaml-ifc"}


def test_partial_box_and_authored_zero_round_trip(tmp_path):
    doc = _shell()
    doc["spaces"] = [
        {
            "id": "ROOM",
            "Name": "Kitchen",
            "LongName": "Kitchen and dining",
            "ObjectType": "OpenPlan",
            "PredefinedType": "INTERNAL",
            "ElevationWithFlooring": 0,
            "PropertySets": [
                {"Name": "Pset_SpaceCommon", "Properties": {"IsExternal": False, "Reference": "1.11"}}
            ],
        }
    ]
    doc["furniture"] = [
        {
            "id": "LOOSE",
            "Description": "not placed in a room",
            "Tag": "F1",
            "PredefinedType": "CHAIR",
            "Origin": [0, 0],
            "Elevation": 0,
            "Width": 0.45,
        },
        {
            "id": "WORK",
            "PredefinedType": "USERDEFINED",
            "ObjectType": "Bench",
            "ContainedInStructure": "ROOM",
            "Origin": [1, 2],
            "RefDirection": [0, 1],
            "Width": 1.2,
            "Depth": 0.4,
            "Height": 0.45,
            "PropertySets": [
                {"Name": "Pset_FurnitureTypeCommon", "Properties": {"IsBuiltIn": False, "NominalLength": 1.2}}
            ],
        },
    ]
    doc["systemFurniture"] = [
        {"id": "PANEL", "PredefinedType": "PANEL", "Origin": [3, 0], "Width": 1, "Depth": 0.05, "Height": 1.4},
        {
            "id": "TOP",
            "PredefinedType": "WORKSURFACE",
            "ObjectType": "Counter",
            "Origin": [3, 1],
            "Width": 2,
            "Depth": 0.6,
            "Height": 0.04,
        },
    ]
    doc["lightFixtures"] = [
        {"id": "BULB", "PredefinedType": "POINTSOURCE", "ObjectType": "Pendant", "Origin": [1, 1], "Elevation": 2}
    ]
    doc["coverings"] = [
        {"id": "FLOOR", "PredefinedType": "FLOORING", "Origin": [0, 0], "Width": 4, "Depth": 3, "Height": 0.01}
    ]
    # An appliance with only a catalogue string has no type object: the type
    # entity requires a predefined type, and none was given.
    doc["electricAppliances"] = [{"id": "BOX", "ObjectType": "Unclassified", "Origin": [4, 0]}]
    model = _round_trip(doc, tmp_path)
    loose = next(element for element in model.by_type("IfcFurniture") if element.Name == "LOOSE")
    assert loose.Representation is None
    typed = {rel.RelatingType.Name for rel in model.by_type("IfcRelDefinesByType")}
    assert "Unclassified" not in typed
    assert "PANEL" in typed
    assert "Bench" in typed
    storey_contents = {
        element.Name
        for rel in model.by_type("IfcRelContainedInSpatialStructure")
        if rel.RelatingStructure.is_a("IfcBuildingStorey")
        for element in rel.RelatedElements
    }
    assert "LOOSE" in storey_contents
    assert "WORK" not in storey_contents


def test_geometry_fallback_reads_the_box(tmp_path):
    doc = _shell()
    doc["spaces"] = [{"id": "ROOM", "Name": "Living", "PredefinedType": "INTERNAL"}]
    doc["furniture"] = [
        {
            "id": "SOFA",
            "Name": "Sectional",
            "PredefinedType": "SOFA",
            "ObjectType": "SectionalSofa",
            "ContainedInStructure": "ROOM",
            "Origin": [1.5, 2.25],
            "RefDirection": [0, 1],
            "Elevation": 0.2,
            "Width": 2.4,
            "Depth": 0.9,
            "Height": 0.8,
        }
    ]
    path = tmp_path / "box.ifc"
    write_ifc(doc, path)
    model = ifcopenshell.open(str(path))
    sofa = model.by_type("IfcFurniture")[0]
    for rel in list(sofa.IsDefinedBy):
        if rel.is_a("IfcRelDefinesByProperties") and rel.RelatingPropertyDefinition.Name == "yaml-ifc":
            model.remove(rel)
    bare = tmp_path / "bare.ifc"
    model.write(str(bare))
    restored, skipped = read_ifc(bare)
    assert skipped == {}
    # Without the bookkeeping id, Name becomes the YAML id, and the GlobalId
    # (derived from the old id) no longer matches, so it is kept.
    item = restored["furniture"][0]
    assert item.pop("GlobalId") == derived_global_id("SOFA")
    same(
        {
            "id": "Sectional",
            "PredefinedType": "SOFA",
            "ObjectType": "SectionalSofa",
            "ContainedInStructure": "ROOM",
            "Origin": [1.5, 2.25],
            "Elevation": 0.2,
            "RefDirection": [0, 1],
            "Width": 2.4,
            "Depth": 0.9,
            "Height": 0.8,
        },
        item,
    )
    same(doc["spaces"][0], restored["spaces"][0])


def test_userdefined_without_object_type_is_rejected(tmp_path):
    doc = _shell()
    doc["furniture"] = [{"id": "X", "PredefinedType": "USERDEFINED", "Origin": [0, 1]}]
    with pytest.raises(ValueError, match="ObjectType"):
        write_ifc(doc, tmp_path / "bad.ifc")


def test_unknown_predefined_type_is_rejected(tmp_path):
    doc = _shell()
    doc["furniture"] = [{"id": "X", "PredefinedType": "CABINET", "Origin": [0, 1]}]
    with pytest.raises(ValueError, match="CABINET"):
        write_ifc(doc, tmp_path / "bad.ifc")


def test_unknown_space_is_rejected(tmp_path):
    doc = _shell()
    doc["furniture"] = [
        {"id": "X", "PredefinedType": "CHAIR", "ContainedInStructure": "MISSING", "Origin": [0, 1]}
    ]
    with pytest.raises(ValueError, match="MISSING"):
        write_ifc(doc, tmp_path / "bad.ifc")


def test_non_positive_size_is_rejected(tmp_path):
    doc = _shell()
    doc["furniture"] = [{"id": "X", "PredefinedType": "CHAIR", "Width": 0, "Depth": 1, "Height": 1}]
    with pytest.raises(ValueError, match="Width"):
        write_ifc(doc, tmp_path / "bad.ifc")
