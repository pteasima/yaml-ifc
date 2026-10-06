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
    ("IfcWall", "walls", True),
    ("IfcRelConnectsPathElements", "connections", True),
    ("IfcOpeningElement", "openings", True),
    ("IfcDoor", "doors", True),
    ("IfcWindow", "windows", True),
)

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
