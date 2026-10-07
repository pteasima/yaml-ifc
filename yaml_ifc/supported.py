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

# PredefinedType is mandatory on these type entities. An occurrence that
# names no predefined type does not grow a type object of these classes.
TYPE_PREDEFINED_REQUIRED = frozenset(
    {
        "IfcSanitaryTerminalType",
        "IfcElectricApplianceType",
        "IfcLightFixtureType",
        "IfcCoveringType",
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
}

FURNISHING_SIZE = ("Width", "Depth", "Height")

# Extrusion used when a wall has a thickness but no height. Not written back.
DEFAULT_WALL_HEIGHT = 3.0
# Void depth used when the host has no thickness and the opening has no depth.
DEFAULT_OPENING_DEPTH = 0.2

PSET_NAME = "yaml-ifc"
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
