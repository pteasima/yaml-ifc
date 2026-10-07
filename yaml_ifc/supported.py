"""Entity types this converter promises to carry.

`IfcWall` includes `IfcWallStandardCase`, which is a subtype. Adding a class
here makes the round-trip coverage test require every instance of that class.
"""

# (IFC class, YAML key, True when the YAML value is a list)
SUPPORTED = (
    ("IfcProject", "project", False),
    ("IfcSite", "site", False),
    ("IfcBuilding", "building", False),
    ("IfcBuildingStorey", "storey", False),
    ("IfcSpace", "spaces", True),
    ("IfcWall", "walls", True),
    ("IfcRelConnectsPathElements", "connections", True),
    ("IfcOpeningElement", "openings", True),
    ("IfcDoor", "doors", True),
    ("IfcWindow", "windows", True),
    ("IfcFurniture", "furniture", True),
    ("IfcSystemFurnitureElement", "systemFurniture", True),
    ("IfcSanitaryTerminal", "sanitaryTerminals", True),
    ("IfcElectricAppliance", "electricAppliances", True),
    ("IfcLightFixture", "lightFixtures", True),
    ("IfcCovering", "coverings", True),
    ("IfcSwitchingDevice", "switchingDevices", True),
    ("IfcSensor", "sensors", True),
    ("IfcOutlet", "outlets", True),
    ("IfcActuator", "actuators", True),
    ("IfcElectricDistributionBoard", "distributionBoards", True),
    ("IfcCableSegment", "cables", True),
    ("IfcDistributionCircuit", "circuits", True),
)

# (YAML key, occurrence class, type class). The type object is derived: one
# per distinct predefined type and object type, not a YAML entry.
FURNISHINGS = (
    ("furniture", "IfcFurniture", "IfcFurnitureType"),
    ("systemFurniture", "IfcSystemFurnitureElement", "IfcSystemFurnitureElementType"),
    ("sanitaryTerminals", "IfcSanitaryTerminal", "IfcSanitaryTerminalType"),
    ("electricAppliances", "IfcElectricAppliance", "IfcElectricApplianceType"),
    ("lightFixtures", "IfcLightFixture", "IfcLightFixtureType"),
    ("coverings", "IfcCovering", "IfcCoveringType"),
)

# Placed electrical elements. Same box, type object, and containment as
# furnishings. Circuits are a group, not a placed element. Ports are derived
# from cables and are not a YAML list.
ELECTRICAL = (
    ("switchingDevices", "IfcSwitchingDevice", "IfcSwitchingDeviceType"),
    ("sensors", "IfcSensor", "IfcSensorType"),
    ("outlets", "IfcOutlet", "IfcOutletType"),
    ("actuators", "IfcActuator", "IfcActuatorType"),
    ("distributionBoards", "IfcElectricDistributionBoard", "IfcElectricDistributionBoardType"),
    ("cables", "IfcCableSegment", "IfcCableSegmentType"),
)

# PredefinedType is mandatory on these type entities. An occurrence that
# names no predefined type does not grow a type object of these classes.
TYPE_PREDEFINED_REQUIRED = frozenset(
    {
        "IfcSanitaryTerminalType",
        "IfcElectricApplianceType",
        "IfcLightFixtureType",
        "IfcCoveringType",
        "IfcSwitchingDeviceType",
        "IfcSensorType",
        "IfcOutletType",
        "IfcActuatorType",
        "IfcElectricDistributionBoardType",
        "IfcCableSegmentType",
    }
)

# IfcFurnitureType.AssemblyPlace is required. NOTDEFINED is the filler.
FURNITURE_TYPE_CLASS = "IfcFurnitureType"

PREDEFINED_TYPES = {
    "IfcSpace": (
        "SPACE",
        "PARKING",
        "GFA",
        "INTERNAL",
        "EXTERNAL",
        "USERDEFINED",
        "NOTDEFINED",
    ),
    "IfcFurniture": (
        "CHAIR",
        "TABLE",
        "DESK",
        "BED",
        "FILECABINET",
        "SHELF",
        "SOFA",
        "USERDEFINED",
        "NOTDEFINED",
    ),
    "IfcSystemFurnitureElement": (
        "PANEL",
        "WORKSURFACE",
        "USERDEFINED",
        "NOTDEFINED",
    ),
    "IfcSanitaryTerminal": (
        "BATH",
        "BIDET",
        "CISTERN",
        "SHOWER",
        "SINK",
        "SANITARYFOUNTAIN",
        "TOILETPAN",
        "URINAL",
        "WASHHANDBASIN",
        "WCSEAT",
        "USERDEFINED",
        "NOTDEFINED",
    ),
    "IfcElectricAppliance": (
        "DISHWASHER",
        "ELECTRICCOOKER",
        "FREESTANDINGELECTRICHEATER",
        "FREESTANDINGFAN",
        "FREESTANDINGWATERHEATER",
        "FREESTANDINGWATERCOOLER",
        "FREEZER",
        "FRIDGE_FREEZER",
        "HANDDRYER",
        "KITCHENMACHINE",
        "MICROWAVE",
        "PHOTOCOPIER",
        "REFRIGERATOR",
        "TUMBLEDRYER",
        "VENDINGMACHINE",
        "WASHINGMACHINE",
        "USERDEFINED",
        "NOTDEFINED",
    ),
    "IfcLightFixture": (
        "POINTSOURCE",
        "DIRECTIONSOURCE",
        "SECURITYLIGHTING",
        "USERDEFINED",
        "NOTDEFINED",
    ),
    "IfcCovering": (
        "CEILING",
        "FLOORING",
        "CLADDING",
        "ROOFING",
        "MOLDING",
        "SKIRTINGBOARD",
        "INSULATION",
        "MEMBRANE",
        "SLEEVING",
        "WRAPPING",
        "USERDEFINED",
        "NOTDEFINED",
    ),
    "IfcSwitchingDevice": (
        "CONTACTOR",
        "DIMMERSWITCH",
        "EMERGENCYSTOP",
        "KEYPAD",
        "MOMENTARYSWITCH",
        "SELECTORSWITCH",
        "STARTER",
        "SWITCHDISCONNECTOR",
        "TOGGLESWITCH",
        "USERDEFINED",
        "NOTDEFINED",
    ),
    "IfcSensor": (
        "COSENSOR",
        "CO2SENSOR",
        "CONDUCTANCESENSOR",
        "CONTACTSENSOR",
        "FIRESENSOR",
        "FLOWSENSOR",
        "FROSTSENSOR",
        "GASSENSOR",
        "HEATSENSOR",
        "HUMIDITYSENSOR",
        "IDENTIFIERSENSOR",
        "IONCONCENTRATIONSENSOR",
        "LEVELSENSOR",
        "LIGHTSENSOR",
        "MOISTURESENSOR",
        "MOVEMENTSENSOR",
        "PHSENSOR",
        "PRESSURESENSOR",
        "RADIATIONSENSOR",
        "RADIOACTIVITYSENSOR",
        "SMOKESENSOR",
        "SOUNDSENSOR",
        "TEMPERATURESENSOR",
        "WINDSENSOR",
        "USERDEFINED",
        "NOTDEFINED",
    ),
    "IfcOutlet": (
        "AUDIOVISUALOUTLET",
        "COMMUNICATIONSOUTLET",
        "POWEROUTLET",
        "DATAOUTLET",
        "TELEPHONEOUTLET",
        "USERDEFINED",
        "NOTDEFINED",
    ),
    "IfcActuator": (
        "ELECTRICACTUATOR",
        "HANDOPERATEDACTUATOR",
        "HYDRAULICACTUATOR",
        "PNEUMATICACTUATOR",
        "THERMOSTATICACTUATOR",
        "USERDEFINED",
        "NOTDEFINED",
    ),
    "IfcElectricDistributionBoard": (
        "CONSUMERUNIT",
        "DISTRIBUTIONBOARD",
        "MOTORCONTROLCENTRE",
        "SWITCHBOARD",
        "USERDEFINED",
        "NOTDEFINED",
    ),
    "IfcCableSegment": (
        "BUSBARSEGMENT",
        "CABLESEGMENT",
        "CONDUCTORSEGMENT",
        "CORESEGMENT",
        "USERDEFINED",
        "NOTDEFINED",
    ),
    "IfcDistributionCircuit": (
        "AIRCONDITIONING",
        "AUDIOVISUAL",
        "CHEMICAL",
        "CHILLEDWATER",
        "COMMUNICATION",
        "COMPRESSEDAIR",
        "CONDENSERWATER",
        "CONTROL",
        "CONVEYING",
        "DATA",
        "DISPOSAL",
        "DOMESTICCOLDWATER",
        "DOMESTICHOTWATER",
        "DRAINAGE",
        "EARTHING",
        "ELECTRICAL",
        "ELECTROACOUSTIC",
        "EXHAUST",
        "FIREPROTECTION",
        "FUEL",
        "GAS",
        "HAZARDOUS",
        "HEATING",
        "LIGHTING",
        "LIGHTNINGPROTECTION",
        "MUNICIPALSOLIDWASTE",
        "OIL",
        "OPERATIONAL",
        "POWERGENERATION",
        "RAINWATER",
        "REFRIGERATION",
        "SECURITY",
        "SEWAGE",
        "SIGNAL",
        "STORMWATER",
        "TELEPHONE",
        "TV",
        "VACUUM",
        "VENT",
        "VENTILATION",
        "WASTEWATER",
        "WATERSUPPLY",
        "USERDEFINED",
        "NOTDEFINED",
    ),
}

FURNISHING_SIZE = ("Width", "Depth", "Height")

# Extrusion used when a wall has a thickness but no height. Not written back.
DEFAULT_WALL_HEIGHT = 3.0
# Disk radius for a routed cable. Not a measured diameter, and not written back.
DEFAULT_CABLE_RADIUS = 0.005
# Void depth used when the host has no thickness and the opening has no depth.
DEFAULT_OPENING_DEPTH = 0.2

PSET_NAME = "yaml-ifc"
# Project data IFC4 has no standard property for. One set, not one per topic.
# Distinct from PSET_NAME, which is converter bookkeeping and is not YAML.
CUSTOM_PSET = "Pset_YamlIfc"
LIGHT_FIXTURE_PSET = "Pset_LightFixtureTypeCommon"
# IFC4 ADD2 TC1 property set for IfcCableSegment / CABLESEGMENT.
# NumberOfCores is IfcInteger here. IFC4.3 later changed it to IfcCountMeasure.
CABLE_SEGMENT_PSET = "Pset_CableSegmentTypeCableSegment"
POWER_MEASURE = "IfcPowerMeasure"
TEMPERATURE_MEASURE = "IfcThermodynamicTemperatureMeasure"
INTEGER_MEASURE = "IfcInteger"
# Applied wherever these property names are written, including authored sets.
MEASURED_PROPERTIES = {
    "TotalWattage": POWER_MEASURE,
    "ActuatorInputPower": POWER_MEASURE,
    "CctMin": TEMPERATURE_MEASURE,
    "CctMax": TEMPERATURE_MEASURE,
}
# Ports nested into a supported element are rebuilt from cables. They are not
# a YAML list and not a skipped leftover.
DERIVED_PORT = "IfcDistributionPort"
# A one-layer set invented from Thickness. Import must not emit MaterialLayers.
PSET_MATERIAL_FROM_THICKNESS = "MaterialFromThickness"
# Authored axis of a joined wall, kept because regeneration trims the curve.
PSET_AXIS = ("AxisStartX", "AxisStartY", "AxisEndX", "AxisEndY")
DERIVED_MATERIAL_NAME = "wall"
RELATING_CONNECTION_TYPES = ("ATSTART", "ATEND", "ATPATH")
RELATED_CONNECTION_TYPES = ("ATSTART", "ATEND")
ORIGINATING_SYSTEM = "yaml-ifc"
SCHEMA_NAME = "IFC4 ADD2 TC1"
HEADER_FILE_NAME = "yaml-ifc.ifc"
HEADER_TIMESTAMP = "2026-10-06T00:00:00"
