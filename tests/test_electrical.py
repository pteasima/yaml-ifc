"""Electrical elements outside the panel, and the cables that feed them."""

from pathlib import Path

import ifcopenshell
import pytest

from test_roundtrip import same
from yaml_ifc.from_ifc import read_ifc
from yaml_ifc.supported import (
    CABLE_SEGMENT_PSET,
    CUSTOM_PSET,
    DEFAULT_CABLE_RADIUS,
    ELECTRICAL,
    LIGHT_FIXTURE_PSET,
    PREDEFINED_TYPES,
    SUPPORTED,
)
from yaml_ifc.to_ifc import validation_errors, write_ifc
from yaml_ifc.yamlio import load

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "samples" / "electrical.yaml"


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


def _nested(element):
    ports = []
    for rel in element.IsNestedBy or []:
        if rel.is_a("IfcRelNests"):
            ports.extend(rel.RelatedObjects or [])
    return ports


def _pset(element, name):
    for rel in element.IsDefinedBy or []:
        if not rel.is_a("IfcRelDefinesByProperties"):
            continue
        pset = rel.RelatingPropertyDefinition
        if pset and pset.is_a("IfcPropertySet") and pset.Name == name:
            return {
                prop.Name: prop.NominalValue
                for prop in pset.HasProperties or []
                if prop.is_a("IfcPropertySingleValue")
            }
    return None


def test_registry_lists_the_electrical_classes():
    keys = {key for _cls, key, is_list in SUPPORTED if is_list}
    assert "circuits" in keys
    for key, ifc_class, type_class in ELECTRICAL:
        assert key in keys
        assert ifc_class in PREDEFINED_TYPES
        assert type_class
    assert "PUSHBUTTON" not in PREDEFINED_TYPES["IfcSwitchingDevice"]
    assert "MOMENTARYSWITCH" in PREDEFINED_TYPES["IfcSwitchingDevice"]


def test_electrical_sample_round_trip(tmp_path):
    original = load(SAMPLE)
    model = _round_trip(original, tmp_path)

    units = {(unit.UnitType, unit.Name) for unit in model.by_type("IfcSIUnit")}
    assert ("POWERUNIT", "WATT") in units
    assert ("THERMODYNAMICTEMPERATUREUNIT", "KELVIN") in units

    light = model.by_type("IfcLightFixture")[0]
    wattage = _pset(light, LIGHT_FIXTURE_PSET)
    assert wattage["TotalWattage"].is_a("IfcPowerMeasure")
    assert wattage["TotalWattage"].wrappedValue == 12
    cct = _pset(light, CUSTOM_PSET)
    assert set(cct) == {"CctMin", "CctMax"}
    assert cct["CctMin"].is_a("IfcThermodynamicTemperatureMeasure")
    assert cct["CctMin"].wrappedValue == 2700
    assert cct["CctMax"].wrappedValue == 6500
    assert model.by_type("IfcLightSource") == []
    light_type = model.by_type("IfcLightFixtureType")[0]
    assert light_type.Name == "Downlight"
    assert light_type.PredefinedType == "POINTSOURCE"
    assert not light_type.HasPropertySets

    kinds = {element.Name: element.PredefinedType for element in model.by_type("IfcSwitchingDevice")}
    assert kinds == {"Entry switch": "TOGGLESWITCH", "Bed button": "MOMENTARYSWITCH"}
    button = next(element for element in model.by_type("IfcSwitchingDevice") if element.Name == "Bed button")
    assert button.ObjectType == "PushButton"

    sensors = {element.ObjectType: element.PredefinedType for element in model.by_type("IfcSensor")}
    assert sensors == {"MmWavePresence": "MOVEMENTSENSOR", "DoorContact": "CONTACTSENSOR"}

    outlet = model.by_type("IfcOutlet")[0]
    assert outlet.PredefinedType == "POWEROUTLET"
    assert _pset(outlet, "Pset_OutletTypeCommon")["NumberOfSockets"].wrappedValue == 2

    actuator = model.by_type("IfcActuator")[0]
    assert actuator.PredefinedType == "ELECTRICACTUATOR"
    assert actuator.ObjectType == "BlindActuator"
    assert model.by_type("IfcElectricMotor") == []
    power = _pset(actuator, "Pset_ActuatorTypeElectricActuator")
    assert power["ElectricActuatorType"].wrappedValue == "MOTORDRIVE"
    assert power["ActuatorInputPower"].is_a("IfcPowerMeasure")
    assert power["ActuatorInputPower"].wrappedValue == 20
    assert _pset(actuator, "Pset_ActuatorTypeCommon")["Application"].wrappedValue == "SUNBLINDACTUATOR"

    board = model.by_type("IfcElectricDistributionBoard")[0]
    assert board.PredefinedType == "DISTRIBUTIONBOARD"
    assert board.IsDecomposedBy == ()
    assert model.by_type("IfcProtectiveDevice") == []

    # Seven cables, four ports each, nested rather than contained in the storey.
    assert len(model.by_type("IfcCableSegment")) == 7
    assert len(model.by_type("IfcDistributionPort")) == 28
    assert len(model.by_type("IfcRelConnectsPorts")) == 14
    assert model.by_type("IfcRelConnectsPortToElement") == []
    contained_ids = {
        element.id()
        for rel in model.by_type("IfcRelContainedInSpatialStructure")
        for element in rel.RelatedElements or []
    }
    for port in model.by_type("IfcDistributionPort"):
        assert port.id() not in contained_ids
        assert port.PredefinedType == "CABLE"

    light_ports = _nested(light)
    assert len(light_ports) == 1
    assert light_ports[0].FlowDirection == "SINK"
    assert light_ports[0].SystemType == "LIGHTING"
    board_ports = _nested(board)
    assert len(board_ports) == 7
    assert {port.FlowDirection for port in board_ports} == {"SOURCE"}
    systems = {port.SystemType for port in board_ports}
    assert systems == {"LIGHTING", "ELECTRICAL", "CONTROL"}

    cable = next(element for element in model.by_type("IfcCableSegment") if element.Name == "CBL-light")
    cable_ports = {port.FlowDirection: port for port in _nested(cable)}
    assert set(cable_ports) == {"SINK", "SOURCE"}
    # The board's source feeds the cable, and the cable feeds the light.
    up = next(
        rel
        for rel in model.by_type("IfcRelConnectsPorts")
        if rel.RelatedPort == cable_ports["SINK"]
    )
    assert up.RelatingPort in board_ports
    assert up.RealizingElement is None
    down = next(
        rel
        for rel in model.by_type("IfcRelConnectsPorts")
        if rel.RelatingPort == cable_ports["SOURCE"]
    )
    assert down.RelatedPort == light_ports[0]

    assert model.by_type("IfcCableFitting") == []
    cores = {
        "CBL-light": 3,
        "CBL-switch": 3,
        "CBL-button": 3,
        "CBL-outlet": 3,
        "CBL-presence": 2,
        "CBL-door": 2,
        "CBL-blind": 4,
    }
    for cable in model.by_type("IfcCableSegment"):
        reps = {rep.RepresentationIdentifier: rep for rep in cable.Representation.Representations}
        axis = reps["Axis"]
        body = reps["Body"]
        assert axis.RepresentationType == "Curve3D"
        assert axis.ContextOfItems.ContextType == "Model"
        polyline = axis.Items[0]
        assert polyline.is_a("IfcPolyline")
        assert len(polyline.Points) >= 2
        assert all(len(point.Coordinates) == 3 for point in polyline.Points)
        assert body.RepresentationType == "AdvancedSweptSolid"
        disk = body.Items[0]
        assert disk.is_a("IfcSweptDiskSolid")
        assert disk.Directrix == polyline
        assert disk.Radius == DEFAULT_CABLE_RADIUS
        counted = _pset(cable, CABLE_SEGMENT_PSET)["NumberOfCores"]
        assert counted.is_a("IfcInteger")
        assert counted.wrappedValue == cores[cable.Name]
    light_route = next(cable for cable in original["cables"] if cable["id"] == "CBL-light")["Route"]
    drop_from, drop_to = light_route[-2], light_route[-1]
    assert drop_from[0] == drop_to[0] and drop_from[1] == drop_to[1]
    assert drop_from[2] > drop_to[2]
    switch_route = next(cable for cable in original["cables"] if cable["id"] == "CBL-switch")["Route"]
    switch_from, switch_to = switch_route[-3], switch_route[-2]
    assert switch_from[0] == switch_to[0] and switch_from[1] == switch_to[1]
    assert switch_from[2] > switch_to[2]

    lighting = next(element for element in model.by_type("IfcCableSegmentType") if element.Name == "LightingCable")
    assert len(lighting.Types[0].RelatedObjects) == 3

    lights = next(element for element in model.by_type("IfcDistributionCircuit") if element.Name == "Lights")
    assert lights.PredefinedType == "LIGHTING"
    members = {
        element.Name
        for rel in lights.IsGroupedBy
        for element in rel.RelatedObjects
    }
    assert members == {"Main board", "Downlight", "Entry switch", "Bed button", "CBL-light", "CBL-switch", "CBL-button"}

    room = model.by_type("IfcSpace")[0]
    contained = {element.Name for rel in room.ContainsElements for element in rel.RelatedElements}
    assert "Downlight" in contained and "Main board" in contained
    assert "CBL-light" not in contained


def test_switch_loop_and_partial_cct_round_trip(tmp_path):
    doc = _shell()
    doc["lightFixtures"] = [
        {
            "id": "LIGHT",
            "PredefinedType": "DIRECTIONSOURCE",
            "ObjectType": "Spot",
            "Origin": [1, 1],
            "Elevation": 2.4,
            "Wattage": 8.5,
            "CctMax": 4000,
            "PropertySets": [
                {"Name": LIGHT_FIXTURE_PSET, "Properties": {"NumberOfSources": 1}},
                {"Name": CUSTOM_PSET, "Properties": {"Dimming": "trailing-edge"}},
            ],
        }
    ]
    doc["switchingDevices"] = [
        {"id": "SW", "PredefinedType": "TOGGLESWITCH", "ObjectType": "ToggleSwitch", "Origin": [0, 0]}
    ]
    doc["distributionBoards"] = [
        {"id": "DB", "PredefinedType": "DISTRIBUTIONBOARD", "ObjectType": "MainBoard", "Origin": [0, 1]}
    ]
    doc["cables"] = [
        {"id": "CBL-A", "PredefinedType": "CABLESEGMENT", "ObjectType": "LightingCable", "From": "DB", "To": "SW"},
        {"id": "CBL-B", "PredefinedType": "CABLESEGMENT", "ObjectType": "LightingCable", "From": "SW", "To": "LIGHT"},
    ]
    doc["circuits"] = [
        {"id": "CIR", "PredefinedType": "LIGHTING", "Assigns": ["DB", "SW", "LIGHT", "CBL-A", "CBL-B"]}
    ]
    model = _round_trip(doc, tmp_path)
    switch = model.by_type("IfcSwitchingDevice")[0]
    flows = {port.FlowDirection for port in _nested(switch)}
    assert flows == {"SINK", "SOURCE"}
    light = model.by_type("IfcLightFixture")[0]
    assert _pset(light, LIGHT_FIXTURE_PSET)["NumberOfSources"].wrappedValue == 1
    custom = _pset(light, CUSTOM_PSET)
    assert set(custom) == {"Dimming", "CctMax"}
    assert custom["Dimming"].wrappedValue == "trailing-edge"
    assert custom["CctMax"].is_a("IfcThermodynamicTemperatureMeasure")


def test_cable_to_cable_round_trip(tmp_path):
    doc = _shell()
    doc["lightFixtures"] = [
        {"id": "LIGHT", "PredefinedType": "POINTSOURCE", "ObjectType": "Downlight", "Origin": [1, 1]}
    ]
    doc["distributionBoards"] = [
        {"id": "DB", "PredefinedType": "DISTRIBUTIONBOARD", "ObjectType": "MainBoard", "Origin": [0, 0]}
    ]
    doc["cables"] = [
        {
            "id": "CBL-A",
            "PredefinedType": "CABLESEGMENT",
            "ObjectType": "LightingCable",
            "From": "DB",
            "To": "CBL-B",
        },
        {
            "id": "CBL-B",
            "PredefinedType": "CABLESEGMENT",
            "ObjectType": "LightingCable",
            "From": "CBL-A",
            "To": "LIGHT",
        },
    ]
    model = _round_trip(doc, tmp_path)
    splice = next(element for element in model.by_type("IfcCableSegment") if element.Name == "CBL-B")
    flows = [port.FlowDirection for port in _nested(splice)]
    assert sorted(flows) == ["SINK", "SINK", "SOURCE"]


def test_cable_to_furniture_is_rejected(tmp_path):
    doc = _shell()
    doc["furniture"] = [{"id": "CHAIR", "PredefinedType": "CHAIR", "ObjectType": "DiningChair"}]
    doc["distributionBoards"] = [{"id": "DB", "PredefinedType": "DISTRIBUTIONBOARD"}]
    doc["cables"] = [
        {"id": "CBL", "PredefinedType": "CABLESEGMENT", "From": "DB", "To": "CHAIR"}
    ]
    with pytest.raises(ValueError, match="distribution element"):
        write_ifc(doc, tmp_path / "bad.ifc")


def test_unknown_cable_end_is_rejected(tmp_path):
    doc = _shell()
    doc["distributionBoards"] = [{"id": "DB", "PredefinedType": "DISTRIBUTIONBOARD"}]
    doc["cables"] = [{"id": "CBL", "From": "DB", "To": "MISSING"}]
    with pytest.raises(ValueError, match="MISSING"):
        write_ifc(doc, tmp_path / "bad.ifc")


def test_pushbutton_predefined_type_is_rejected(tmp_path):
    doc = _shell()
    doc["switchingDevices"] = [{"id": "SW", "PredefinedType": "PUSHBUTTON", "ObjectType": "PushButton"}]
    with pytest.raises(ValueError, match="PUSHBUTTON"):
        write_ifc(doc, tmp_path / "bad.ifc")


def test_wattage_on_a_switch_is_rejected(tmp_path):
    doc = _shell()
    doc["switchingDevices"] = [
        {"id": "SW", "PredefinedType": "TOGGLESWITCH", "Wattage": 1, "ObjectType": "ToggleSwitch"}
    ]
    with pytest.raises(ValueError, match="light fixture"):
        write_ifc(doc, tmp_path / "bad.ifc")


def test_cct_range_reversed_is_rejected(tmp_path):
    doc = _shell()
    doc["lightFixtures"] = [{"id": "L", "PredefinedType": "POINTSOURCE", "CctMin": 6500, "CctMax": 2700}]
    with pytest.raises(ValueError, match="CctMin"):
        write_ifc(doc, tmp_path / "bad.ifc")


def test_routed_cable_keeps_storey_coordinates(tmp_path):
    doc = _shell()
    doc["storey"]["Elevation"] = 1.5
    doc["spaces"] = [{"id": "ROOM", "PredefinedType": "INTERNAL"}]
    doc["distributionBoards"] = [
        {
            "id": "DB",
            "PredefinedType": "DISTRIBUTIONBOARD",
            "ObjectType": "MainBoard",
            "ContainedInStructure": "ROOM",
            "Origin": [1, 2],
            "Elevation": 0.4,
            "RefDirection": [0, 1],
        }
    ]
    doc["lightFixtures"] = [
        {"id": "LIGHT", "PredefinedType": "POINTSOURCE", "ObjectType": "Downlight", "Origin": [3, 4]}
    ]
    route = [[1, 2, 0.4], [1, 2, 2.5], [3.25, 4.5, 2.5]]
    doc["cables"] = [
        {
            "id": "CBL",
            "PredefinedType": "CABLESEGMENT",
            "ObjectType": "LightingCable",
            "ContainedInStructure": "ROOM",
            "Origin": [1, 2],
            "Elevation": 0.4,
            "RefDirection": [0, 2],
            "From": "DB",
            "To": "LIGHT",
            "Route": route,
            "NumberOfCores": 3,
            "PropertySets": [{"Name": CABLE_SEGMENT_PSET, "Properties": {"Standard": "CYKY"}}],
        },
        {"id": "CBL-bare", "From": "DB", "To": "LIGHT"},
    ]
    model = _round_trip(doc, tmp_path)
    cable = next(element for element in model.by_type("IfcCableSegment") if element.Name == "CBL")
    props = _pset(cable, CABLE_SEGMENT_PSET)
    assert set(props) == {"NumberOfCores", "Standard"}
    assert props["NumberOfCores"].is_a("IfcInteger")
    bare = next(element for element in model.by_type("IfcCableSegment") if element.Name == "CBL-bare")
    assert bare.Representation is None
    assert _pset(bare, CABLE_SEGMENT_PSET) is None


def test_short_route_is_rejected(tmp_path):
    doc = _shell()
    doc["distributionBoards"] = [{"id": "DB", "PredefinedType": "DISTRIBUTIONBOARD"}]
    doc["lightFixtures"] = [{"id": "L", "PredefinedType": "POINTSOURCE"}]
    doc["cables"] = [{"id": "CBL", "From": "DB", "To": "L", "Route": [[0, 0, 0]]}]
    with pytest.raises(ValueError, match="at least two"):
        write_ifc(doc, tmp_path / "bad.ifc")


def test_flat_route_point_is_rejected(tmp_path):
    doc = _shell()
    doc["distributionBoards"] = [{"id": "DB", "PredefinedType": "DISTRIBUTIONBOARD"}]
    doc["lightFixtures"] = [{"id": "L", "PredefinedType": "POINTSOURCE"}]
    doc["cables"] = [{"id": "CBL", "From": "DB", "To": "L", "Route": [[0, 0], [1, 0]]}]
    with pytest.raises(ValueError, match="x, y, z"):
        write_ifc(doc, tmp_path / "bad.ifc")


def test_zero_length_route_segment_is_rejected(tmp_path):
    doc = _shell()
    doc["distributionBoards"] = [{"id": "DB", "PredefinedType": "DISTRIBUTIONBOARD"}]
    doc["lightFixtures"] = [{"id": "L", "PredefinedType": "POINTSOURCE"}]
    doc["cables"] = [{"id": "CBL", "From": "DB", "To": "L", "Route": [[0, 0, 1], [0, 0, 1], [1, 0, 1]]}]
    with pytest.raises(ValueError, match="zero-length"):
        write_ifc(doc, tmp_path / "bad.ifc")


def test_route_on_a_light_is_rejected(tmp_path):
    doc = _shell()
    doc["lightFixtures"] = [{"id": "L", "PredefinedType": "POINTSOURCE", "Route": [[0, 0, 0], [1, 0, 0]]}]
    with pytest.raises(ValueError, match="cable"):
        write_ifc(doc, tmp_path / "bad.ifc")


def test_fractional_core_count_is_rejected(tmp_path):
    doc = _shell()
    doc["distributionBoards"] = [{"id": "DB", "PredefinedType": "DISTRIBUTIONBOARD"}]
    doc["lightFixtures"] = [{"id": "L", "PredefinedType": "POINTSOURCE"}]
    doc["cables"] = [{"id": "CBL", "From": "DB", "To": "L", "NumberOfCores": 2.5}]
    with pytest.raises(ValueError, match="integer"):
        write_ifc(doc, tmp_path / "bad.ifc")


def test_duplicate_core_count_is_rejected(tmp_path):
    doc = _shell()
    doc["distributionBoards"] = [{"id": "DB", "PredefinedType": "DISTRIBUTIONBOARD"}]
    doc["lightFixtures"] = [{"id": "L", "PredefinedType": "POINTSOURCE"}]
    doc["cables"] = [
        {
            "id": "CBL",
            "From": "DB",
            "To": "L",
            "NumberOfCores": 3,
            "PropertySets": [{"Name": CABLE_SEGMENT_PSET, "Properties": {"NumberOfCores": 3}}],
        }
    ]
    with pytest.raises(ValueError, match="NumberOfCores"):
        write_ifc(doc, tmp_path / "bad.ifc")


def test_duplicate_wattage_is_rejected(tmp_path):
    doc = _shell()
    doc["lightFixtures"] = [
        {
            "id": "L",
            "PredefinedType": "POINTSOURCE",
            "Wattage": 10,
            "PropertySets": [{"Name": LIGHT_FIXTURE_PSET, "Properties": {"TotalWattage": 10}}],
        }
    ]
    with pytest.raises(ValueError, match="TotalWattage"):
        write_ifc(doc, tmp_path / "bad.ifc")
