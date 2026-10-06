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
    ("IfcOpeningElement", "openings", True),
    ("IfcDoor", "doors", True),
    ("IfcWindow", "windows", True),
)

# Extrusion used when a wall has a thickness but no height. Not written back.
DEFAULT_WALL_HEIGHT = 3.0
# Void depth used when the host has no thickness and the opening has no depth.
DEFAULT_OPENING_DEPTH = 0.2

PSET_NAME = "yaml-ifc"
ORIGINATING_SYSTEM = "yaml-ifc"
SCHEMA_NAME = "IFC4 ADD2 TC1"
HEADER_FILE_NAME = "yaml-ifc.ifc"
HEADER_TIMESTAMP = "2026-10-06T00:00:00"
