"""Write a yaml-ifc document to an IFC4 file."""

import math
from pathlib import Path

import ifcopenshell
import ifcopenshell.api.geometry
import ifcopenshell.util.element
import ifcopenshell.validate

from yaml_ifc.ids import connection_yaml_id, global_id
from yaml_ifc.joints import install_priority_fix
from yaml_ifc.supported import (
    DEFAULT_OPENING_DEPTH,
    DEFAULT_WALL_HEIGHT,
    DERIVED_MATERIAL_NAME,
    FURNISHINGS,
    FURNISHING_SIZE,
    FURNITURE_TYPE_CLASS,
    HEADER_FILE_NAME,
    HEADER_TIMESTAMP,
    ORIGINATING_SYSTEM,
    PREDEFINED_TYPES,
    PSET_AXIS,
    PSET_MATERIAL_FROM_THICKNESS,
    PSET_NAME,
    RELATED_CONNECTION_TYPES,
    RELATING_CONNECTION_TYPES,
    TYPE_PREDEFINED_REQUIRED,
)

TOL = 1e-9


def _derived_thickness(wall):
    layers = ((wall.get("MaterialLayers") or {}).get("Layers")) or []
    return (
        wall.get("Thickness") is not None
        and not layers
        and not wall.get("Footprint")
        and not wall.get("Profile")
    )


def _regenerable(wall):
    """A centreline wall with a thickness. Footprints and profiles keep their body."""
    if wall.get("Footprint") or wall.get("Profile"):
        return False
    return wall.get("Thickness") is not None


def _connected_ids(doc):
    found = set()
    for connection in doc.get("connections") or []:
        if connection.get("RelatingElement"):
            found.add(connection["RelatingElement"])
        if connection.get("RelatedElement"):
            found.add(connection["RelatedElement"])
    return found


def _layer_count(product):
    material = ifcopenshell.util.element.get_material(product, should_skip_usage=True)
    if material and material.is_a("IfcMaterialLayerSet"):
        return len(material.MaterialLayers or [])
    return 0


def _number(value, where):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{where} must be a number")
    return value


def _check_predefined(element, ifc_class):
    predefined = element.get("PredefinedType")
    if predefined is None:
        return
    allowed = PREDEFINED_TYPES[ifc_class]
    if predefined not in allowed:
        raise ValueError(
            f"{element['id']} PredefinedType {predefined} is not valid for {ifc_class}"
        )
    if predefined == "USERDEFINED" and not element.get("ObjectType"):
        raise ValueError(f"{element['id']} PredefinedType USERDEFINED needs an ObjectType")


def validation_errors(model):
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(model, logger)
    messages = []
    for statement in logger.statements:
        if isinstance(statement, dict):
            messages.append(statement.get("message") or str(statement))
        else:
            messages.append(str(statement))
    return messages


class Builder:
    def __init__(self, doc):
        self.doc = doc
        self.file = ifcopenshell.file(schema="IFC4")
        self.products = {}
        self.placements = {}
        self.space_ids = set()
        self.typed = {}
        self.connected_ids = _connected_ids(doc)
        self._stamp_header()
        self._units_and_context()
        self._spatial()
        self._spaces()
        self._elements()
        self._types()
        self._connections()
        self._containment()

    def _stamp_header(self):
        header = self.file.header
        header.file_description.description = ("ViewDefinition [ReferenceView]",)
        header.file_name.name = HEADER_FILE_NAME
        header.file_name.time_stamp = HEADER_TIMESTAMP
        header.file_name.author = ("yaml-ifc",)
        header.file_name.organization = ("yaml-ifc",)
        header.file_name.preprocessor_version = "yaml-ifc"
        header.file_name.originating_system = ORIGINATING_SYSTEM
        header.file_name.authorization = "None"

    def _gid(self, kind, yaml_id):
        return global_id(f"rel:{kind}:{yaml_id}")

    def _point(self, *coords):
        return self.file.create_entity("IfcCartesianPoint", Coordinates=tuple(float(c) for c in coords))

    def _direction(self, coords):
        return self.file.create_entity(
            "IfcDirection", DirectionRatios=tuple(float(c) for c in coords)
        )

    def _placement3d(self, origin, ref=(1.0, 0.0, 0.0)):
        return self.file.create_entity(
            "IfcAxis2Placement3D",
            Location=self._point(*origin),
            Axis=self._direction((0.0, 0.0, 1.0)),
            RefDirection=self._direction(ref),
        )

    def _local(self, origin, ref, parent):
        values = {"RelativePlacement": self._placement3d(origin, ref)}
        if parent is not None:
            values["PlacementRelTo"] = parent
        return self.file.create_entity("IfcLocalPlacement", **values)

    def _nominal(self, value):
        if isinstance(value, bool):
            wrapped = self.file.create_entity("IfcBoolean", bool(value))
        elif isinstance(value, int):
            wrapped = self.file.create_entity("IfcInteger", int(value))
        elif isinstance(value, float):
            wrapped = self.file.create_entity("IfcReal", float(value))
        else:
            wrapped = self.file.create_entity("IfcLabel", str(value))
        return wrapped

    def _pset(self, product, properties, yaml_id):
        if not properties:
            return
        props = []
        for name, value in properties.items():
            props.append(
                self.file.create_entity(
                    "IfcPropertySingleValue",
                    Name=name,
                    NominalValue=self._nominal(value),
                )
            )
        pset = self.file.create_entity(
            "IfcPropertySet",
            GlobalId=self._gid("pset", yaml_id),
            Name=PSET_NAME,
            HasProperties=props,
        )
        self.file.create_entity(
            "IfcRelDefinesByProperties",
            GlobalId=self._gid("defines", yaml_id),
            RelatedObjects=[product],
            RelatingPropertyDefinition=pset,
        )

    def _units_and_context(self):
        f = self.file
        length = f.create_entity("IfcSIUnit", UnitType="LENGTHUNIT", Name="METRE")
        area = f.create_entity("IfcSIUnit", UnitType="AREAUNIT", Name="SQUARE_METRE")
        volume = f.create_entity("IfcSIUnit", UnitType="VOLUMEUNIT", Name="CUBIC_METRE")
        angle = f.create_entity("IfcSIUnit", UnitType="PLANEANGLEUNIT", Name="RADIAN")
        units = f.create_entity("IfcUnitAssignment", Units=[length, area, volume, angle])
        origin = self._point(0.0, 0.0, 0.0)
        wcs = f.create_entity(
            "IfcAxis2Placement3D",
            Location=origin,
            Axis=self._direction((0.0, 0.0, 1.0)),
            RefDirection=self._direction((1.0, 0.0, 0.0)),
        )
        context = f.create_entity(
            "IfcGeometricRepresentationContext",
            ContextType="Model",
            CoordinateSpaceDimension=3,
            Precision=1e-5,
            WorldCoordinateSystem=wcs,
            TrueNorth=self._direction((0.0, 1.0)),
        )
        self.body = f.create_entity(
            "IfcGeometricRepresentationSubContext",
            ContextIdentifier="Body",
            ContextType="Model",
            ParentContext=context,
            TargetView="MODEL_VIEW",
        )
        # Wall axes live in Plan/Axis/GRAPH_VIEW. That is the context
        # regenerate_wall_representation reads and rewrites.
        plan_origin = f.create_entity(
            "IfcAxis2Placement2D",
            Location=self._point(0.0, 0.0),
            RefDirection=self._direction((1.0, 0.0)),
        )
        self.plan = f.create_entity(
            "IfcGeometricRepresentationContext",
            ContextType="Plan",
            CoordinateSpaceDimension=2,
            Precision=1e-5,
            WorldCoordinateSystem=plan_origin,
        )
        self.axis = f.create_entity(
            "IfcGeometricRepresentationSubContext",
            ContextIdentifier="Axis",
            ContextType="Plan",
            ParentContext=self.plan,
            TargetView="GRAPH_VIEW",
        )
        self.units = units
        self.context = context

    def _named(self, entity, yaml_id):
        name = entity.get("Name") or yaml_id
        return name

    def _spatial(self):
        f = self.file
        doc = self.doc
        project = doc["project"]
        site = doc["site"]
        building = doc["building"]
        storey = doc["storey"]
        self.project = f.create_entity(
            "IfcProject",
            GlobalId=global_id(project["id"], project.get("GlobalId")),
            Name=self._named(project, project["id"]),
            LongName=project["id"],
            RepresentationContexts=[self.context, self.plan],
            UnitsInContext=self.units,
        )
        site_place = self._local((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), None)
        site_values = {
            "GlobalId": global_id(site["id"], site.get("GlobalId")),
            "Name": self._named(site, site["id"]),
            "ObjectPlacement": site_place,
            "CompositionType": "ELEMENT",
        }
        if site.get("RefElevation") is not None:
            site_values["RefElevation"] = float(site["RefElevation"])
        self.site = f.create_entity("IfcSite", **site_values)
        building_place = self._local((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), site_place)
        self.building = f.create_entity(
            "IfcBuilding",
            GlobalId=global_id(building["id"], building.get("GlobalId")),
            Name=self._named(building, building["id"]),
            ObjectPlacement=building_place,
            CompositionType="ELEMENT",
        )
        elevation = float(storey["Elevation"]) if storey.get("Elevation") is not None else 0.0
        storey_place = self._local((0.0, 0.0, elevation), (1.0, 0.0, 0.0), building_place)
        storey_values = {
            "GlobalId": global_id(storey["id"], storey.get("GlobalId")),
            "Name": self._named(storey, storey["id"]),
            "ObjectPlacement": storey_place,
            "CompositionType": "ELEMENT",
        }
        if storey.get("Elevation") is not None:
            storey_values["Elevation"] = float(storey["Elevation"])
        self.storey = f.create_entity("IfcBuildingStorey", **storey_values)
        self.storey_placement = storey_place
        self.products[project["id"]] = self.project
        self.products[site["id"]] = self.site
        self.products[building["id"]] = self.building
        self.products[storey["id"]] = self.storey
        self._aggregate(project, [self.site])
        self._aggregate(site, [self.building])
        self._aggregate(building, [self.storey])
        for element, node in (
            (site, self.site),
            (building, self.building),
            (storey, self.storey),
        ):
            self._pset(node, {"id": element["id"]}, element["id"])
        self._user_psets(self.site, site)
        self._user_psets(self.building, building)
        self._user_psets(self.storey, storey)

    def _aggregate(self, parent, children):
        self.file.create_entity(
            "IfcRelAggregates",
            GlobalId=self._gid("aggregates", parent["id"]),
            RelatingObject=self.products[parent["id"]],
            RelatedObjects=children,
        )

    def _user_psets(self, product, entity):
        for index, pset in enumerate(entity.get("PropertySets") or []):
            props = []
            for name, value in (pset.get("Properties") or {}).items():
                props.append(
                    self.file.create_entity(
                        "IfcPropertySingleValue",
                        Name=str(name),
                        NominalValue=self._nominal(value),
                    )
                )
            created = self.file.create_entity(
                "IfcPropertySet",
                GlobalId=self._gid(f"userpset:{index}:{pset.get('Name')}", entity["id"]),
                Name=pset.get("Name") or "Pset",
                HasProperties=props,
            )
            self.file.create_entity(
                "IfcRelDefinesByProperties",
                GlobalId=self._gid(f"userdefines:{index}:{pset.get('Name')}", entity["id"]),
                RelatedObjects=[product],
                RelatingPropertyDefinition=created,
            )

    def _elements(self):
        self.walls = {}
        self.openings = {}
        contained = []
        for wall in self.doc.get("walls") or []:
            product = self._wall(wall)
            self.walls[wall["id"]] = product
            contained.append(product)
        for opening in self.doc.get("openings") or []:
            self.openings[opening["id"]] = self._opening(opening)
        for kind, key in (("door", "doors"), ("window", "windows")):
            for element in self.doc.get(key) or []:
                contained.append(self._filler(element, kind))
        self.contained_by_space = {}
        for key, ifc_class, type_class in FURNISHINGS:
            for element in self.doc.get(key) or []:
                product = self._furnishing(element, ifc_class, type_class)
                container = element.get("ContainedInStructure")
                if container:
                    self.contained_by_space.setdefault(container, []).append(product)
                else:
                    contained.append(product)
        self.contained = contained

    def _wall_frame(self, wall):
        axis = wall.get("Axis") or {}
        start, end = axis.get("Start"), axis.get("End")
        if not start or not end:
            return None
        sx, sy = float(start[0]), float(start[1])
        ex, ey = float(end[0]), float(end[1])
        dx, dy = ex - sx, ey - sy
        length = math.hypot(dx, dy)
        if length < TOL:
            raise ValueError(f"{wall['id']} has a zero-length axis")
        return (sx, sy), (dx / length, dy / length, 0.0), length

    def _profile_curve(self, points):
        coords = [self._point(float(p[0]), float(p[1])) for p in points]
        if points[0] != points[-1]:
            coords.append(self._point(float(points[0][0]), float(points[0][1])))
        polyline = self.file.create_entity("IfcPolyline", Points=coords)
        return self.file.create_entity(
            "IfcArbitraryClosedProfileDef", ProfileType="AREA", OuterCurve=polyline
        )

    def _rectangle(self, length, thickness):
        position = self.file.create_entity(
            "IfcAxis2Placement2D",
            Location=self._point(length / 2.0, 0.0),
        )
        return self.file.create_entity(
            "IfcRectangleProfileDef",
            ProfileType="AREA",
            Position=position,
            XDim=float(length),
            YDim=float(thickness),
        )

    def _extrusion(self, profile, depth):
        return self.file.create_entity(
            "IfcExtrudedAreaSolid",
            SweptArea=profile,
            Position=self._placement3d((0.0, 0.0, 0.0)),
            ExtrudedDirection=self._direction((0.0, 0.0, 1.0)),
            Depth=float(depth),
        )

    def _shape(self, items):
        reps = []
        for identifier, rep_type, context, item in items:
            reps.append(
                self.file.create_entity(
                    "IfcShapeRepresentation",
                    ContextOfItems=context,
                    RepresentationIdentifier=identifier,
                    RepresentationType=rep_type,
                    Items=[item],
                )
            )
        return self.file.create_entity("IfcProductDefinitionShape", Representations=reps)

    def _axis_curve(self, length):
        polyline = self.file.create_entity(
            "IfcPolyline",
            Points=[self._point(0.0, 0.0), self._point(float(length), 0.0)],
        )
        return polyline

    def _local_polygon(self, frame, points):
        (sx, sy), (ux, uy, _), _length = frame
        px, py = -uy, ux
        local = []
        for point in points:
            dx, dy = float(point[0]) - sx, float(point[1]) - sy
            local.append((dx * ux + dy * uy, dx * px + dy * py))
        return local

    def _wall(self, wall):
        yaml_id = wall["id"]
        frame = self._wall_frame(wall)
        elevation = float(wall.get("Elevation") or 0.0)
        height = wall.get("Height")
        height_defaulted = height is None and (
            wall.get("Thickness") is not None or wall.get("Footprint") or wall.get("Profile")
        )
        if height is None and height_defaulted:
            height = DEFAULT_WALL_HEIGHT
        placement_parent = self.storey_placement
        reps = []
        if frame:
            origin, ref, length = frame
            placement = self._local((origin[0], origin[1], elevation), ref, placement_parent)
            reps.append(("Axis", "Curve2D", self.axis, self._axis_curve(length)))
            profile = None
            plan = None
            if wall.get("Footprint"):
                profile = self._profile_curve(self._local_polygon(frame, wall["Footprint"]))
                plan = "footprint"
            elif wall.get("Profile"):
                profile = self._profile_curve(wall["Profile"])
                plan = "profile"
            elif wall.get("Thickness") is not None:
                profile = self._rectangle(length, float(wall["Thickness"]))
            if profile is not None and height is not None:
                reps.append(("Body", "SweptSolid", self.body, self._extrusion(profile, height)))
        else:
            placement = self._local((0.0, 0.0, elevation), (1.0, 0.0, 0.0), placement_parent)
            plan = "footprint" if wall.get("Footprint") else None
            if wall.get("Footprint") and height is not None:
                profile = self._profile_curve(wall["Footprint"])
                reps.append(("Body", "SweptSolid", self.body, self._extrusion(profile, height)))
        shape = self._shape(reps) if reps else None
        wall_values = {
            "GlobalId": global_id(yaml_id, wall.get("GlobalId")),
            "Name": self._named(wall, yaml_id),
            "ObjectPlacement": placement,
            "Representation": shape,
        }
        for key, attr in (
            ("Description", "Description"),
            ("Tag", "Tag"),
            ("PredefinedType", "PredefinedType"),
        ):
            if wall.get(key) is not None:
                wall_values[attr] = wall[key]
        product = self.file.create_entity("IfcWall", **wall_values)
        book = {"id": yaml_id}
        if height_defaulted:
            book["HeightDefaulted"] = True
        if plan:
            book["PlanShape"] = plan
        if _derived_thickness(wall):
            book[PSET_MATERIAL_FROM_THICKNESS] = True
        if yaml_id in self.connected_ids and frame:
            start, end = wall["Axis"]["Start"], wall["Axis"]["End"]
            for key, value in zip(PSET_AXIS, (start[0], start[1], end[0], end[1])):
                book[key] = value
        self._pset(product, book, yaml_id)
        self._user_psets(product, wall)
        self._materials(product, wall)
        self.products[yaml_id] = product
        self.placements[yaml_id] = placement
        return product

    def _materials(self, product, wall):
        layers = ((wall.get("MaterialLayers") or {}).get("Layers")) or []
        if not layers and _derived_thickness(wall):
            layers = [
                {"LayerThickness": float(wall["Thickness"]), "Material": DERIVED_MATERIAL_NAME}
            ]
        if not layers:
            return
        ifc_layers = []
        total = 0.0
        for layer in layers:
            thickness = float(layer["LayerThickness"])
            total += thickness
            material = self.file.create_entity("IfcMaterial", Name=str(layer.get("Material") or "material"))
            layer_values = {"Material": material, "LayerThickness": thickness}
            for key in ("Name", "Category", "Priority", "IsVentilated"):
                if layer.get(key) is not None:
                    layer_values[key] = layer[key]
            ifc_layers.append(self.file.create_entity("IfcMaterialLayer", **layer_values))
        layer_set = self.file.create_entity(
            "IfcMaterialLayerSet",
            MaterialLayers=ifc_layers,
            LayerSetName=wall["id"],
        )
        usage = self.file.create_entity(
            "IfcMaterialLayerSetUsage",
            ForLayerSet=layer_set,
            LayerSetDirection="AXIS2",
            DirectionSense="POSITIVE",
            OffsetFromReferenceLine=-total / 2.0,
        )
        self.file.create_entity(
            "IfcRelAssociatesMaterial",
            GlobalId=self._gid("material", wall["id"]),
            RelatedObjects=[product],
            RelatingMaterial=usage,
        )

    def _opening(self, opening):
        yaml_id = opening["id"]
        host_id = opening["VoidsElement"]
        host = self.walls.get(host_id)
        if host is None:
            raise ValueError(f"{yaml_id} voids unknown wall {host_id}")
        host_yaml = next(wall for wall in self.doc["walls"] if wall["id"] == host_id)
        along = float(opening["AlongAxis"])
        width = float(opening["Width"])
        height = opening.get("Height")
        sill = opening.get("SillHeight")
        depth = opening.get("Depth")
        depth_defaulted = False
        if depth is None:
            if host_yaml.get("Thickness") is not None:
                depth = float(host_yaml["Thickness"])
            elif height is not None:
                depth = DEFAULT_OPENING_DEPTH
                depth_defaulted = True
        placement = self._local(
            (along, 0.0, float(sill or 0.0)),
            (1.0, 0.0, 0.0),
            self.placements[host_id],
        )
        shape = None
        if height is not None and depth is not None:
            profile = self._rectangle(width, float(depth))
            shape = self._shape([("Body", "SweptSolid", self.body, self._extrusion(profile, height))])
        predefined = opening.get("PredefinedType") or "OPENING"
        product = self.file.create_entity(
            "IfcOpeningElement",
            GlobalId=global_id(yaml_id, opening.get("GlobalId")),
            Name=self._named(opening, yaml_id),
            Description=opening.get("Description"),
            ObjectPlacement=placement,
            Representation=shape,
            Tag=opening.get("Tag"),
            PredefinedType=predefined,
        )
        self.file.create_entity(
            "IfcRelVoidsElement",
            GlobalId=self._gid("voids", yaml_id),
            RelatingBuildingElement=host,
            RelatedOpeningElement=product,
        )
        book = {"id": yaml_id}
        for key in ("AlongAxis", "Width", "Height", "SillHeight", "Depth", "HeadHeight"):
            if key in opening:
                value = opening[key]
                book[key] = float(value) if isinstance(value, (int, float)) else value
        if depth_defaulted:
            book["DepthDefaulted"] = True
        self._pset(product, book, yaml_id)
        self._user_psets(product, opening)
        self.products[yaml_id] = product
        self.placements[yaml_id] = placement
        return product

    def _filler(self, element, kind):
        yaml_id = element["id"]
        opening_id = element.get("FillsOpening")
        parent = self.placements.get(opening_id) or self.storey_placement
        placement = self._local((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), parent)
        ifc_class = "IfcDoor" if kind == "door" else "IfcWindow"
        values = {
            "GlobalId": global_id(yaml_id, element.get("GlobalId")),
            "Name": self._named(element, yaml_id),
            "ObjectPlacement": placement,
        }
        for key in ("Description", "Tag", "OverallWidth", "OverallHeight", "PredefinedType"):
            if element.get(key) is not None:
                values[key] = element[key]
        extra = "OperationType" if kind == "door" else "PartitioningType"
        if element.get(extra) is not None:
            values[extra] = element[extra]
        product = self.file.create_entity(ifc_class, **values)
        if opening_id:
            opening = self.openings.get(opening_id)
            if opening is None:
                raise ValueError(f"{yaml_id} fills unknown opening {opening_id}")
            self.file.create_entity(
                "IfcRelFillsElement",
                GlobalId=self._gid("fills", yaml_id),
                RelatingOpeningElement=opening,
                RelatedBuildingElement=product,
            )
        self._pset(product, {"id": yaml_id}, yaml_id)
        self._user_psets(product, element)
        self.products[yaml_id] = product
        return product

    def _connections(self):
        connections = self.doc.get("connections") or []
        if not connections:
            return
        seen = set()
        for connection in connections:
            relating_id = connection.get("RelatingElement")
            related_id = connection.get("RelatedElement")
            relating_type = connection.get("RelatingConnectionType")
            related_type = connection.get("RelatedConnectionType")
            relating = self.walls.get(relating_id)
            related = self.walls.get(related_id)
            if relating is None or related is None:
                raise ValueError(
                    f"connection {relating_id}/{related_id} references an unknown wall"
                )
            if relating_id == related_id:
                raise ValueError(f"{relating_id} cannot connect to itself")
            if relating_type not in RELATING_CONNECTION_TYPES:
                raise ValueError(f"unknown RelatingConnectionType {relating_type}")
            if related_type not in RELATED_CONNECTION_TYPES:
                raise ValueError(f"unknown RelatedConnectionType {related_type}")
            pair = tuple(sorted((relating_id, related_id)))
            if pair in seen:
                raise ValueError(f"{relating_id} and {related_id} are connected more than once")
            seen.add(pair)
            # Written directly so the GlobalId stays derived from the four
            # fields. connect_path would also invent an OwnerHistory and a
            # random GlobalId, and would leave the priorities empty (a mitre).
            self.file.create_entity(
                "IfcRelConnectsPathElements",
                GlobalId=global_id(connection_yaml_id(connection), connection.get("GlobalId")),
                RelatingElement=relating,
                RelatedElement=related,
                RelatingConnectionType=relating_type,
                RelatedConnectionType=related_type,
                RelatingPriorities=[1] * _layer_count(relating),
                RelatedPriorities=[0] * _layer_count(related),
            )
        install_priority_fix()
        for wall in self.doc.get("walls") or []:
            if wall["id"] not in self.connected_ids or not _regenerable(wall):
                continue
            product = self.walls[wall["id"]]
            frame = self._wall_frame(wall)
            if frame is None:
                continue
            _length = frame[2]
            height = wall.get("Height")
            if height is None:
                height = DEFAULT_WALL_HEIGHT
            ifcopenshell.api.geometry.regenerate_wall_representation(
                self.file,
                wall=product,
                length=float(_length),
                height=float(height),
            )

    def _spaces(self):
        products = []
        for space in self.doc.get("spaces") or []:
            yaml_id = space["id"]
            if yaml_id in self.products:
                raise ValueError(f"duplicate id {yaml_id}")
            _check_predefined(space, "IfcSpace")
            placement = self._local((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), self.storey_placement)
            values = {
                "GlobalId": global_id(yaml_id, space.get("GlobalId")),
                "Name": self._named(space, yaml_id),
                "ObjectPlacement": placement,
                "CompositionType": "ELEMENT",
            }
            for key in ("Description", "ObjectType", "LongName", "PredefinedType"):
                if space.get(key) is not None:
                    values[key] = space[key]
            if space.get("ElevationWithFlooring") is not None:
                values["ElevationWithFlooring"] = float(
                    _number(space["ElevationWithFlooring"], f"{yaml_id} ElevationWithFlooring")
                )
            product = self.file.create_entity("IfcSpace", **values)
            self._pset(product, {"id": yaml_id}, yaml_id)
            self._user_psets(product, space)
            self.products[yaml_id] = product
            self.placements[yaml_id] = placement
            self.space_ids.add(yaml_id)
            products.append(product)
        if products:
            self._aggregate(self.doc["storey"], products)

    def _box(self, width, depth, height):
        position = self.file.create_entity(
            "IfcAxis2Placement2D",
            Location=self._point(float(width) / 2.0, float(depth) / 2.0),
        )
        profile = self.file.create_entity(
            "IfcRectangleProfileDef",
            ProfileType="AREA",
            Position=position,
            XDim=float(width),
            YDim=float(depth),
        )
        return self._extrusion(profile, height)

    def _furnishing(self, element, ifc_class, type_class):
        yaml_id = element["id"]
        if yaml_id in self.products:
            raise ValueError(f"duplicate id {yaml_id}")
        _check_predefined(element, ifc_class)
        origin = element.get("Origin")
        if origin is None:
            ox = oy = 0.0
        else:
            if not isinstance(origin, (list, tuple)) or len(origin) != 2:
                raise ValueError(f"{yaml_id} Origin must be [x, y]")
            ox = float(_number(origin[0], f"{yaml_id} Origin"))
            oy = float(_number(origin[1], f"{yaml_id} Origin"))
        elevation = element.get("Elevation")
        z = 0.0 if elevation is None else float(_number(elevation, f"{yaml_id} Elevation"))
        ref = element.get("RefDirection")
        if ref is None:
            ux, uy = 1.0, 0.0
        else:
            if not isinstance(ref, (list, tuple)) or len(ref) != 2:
                raise ValueError(f"{yaml_id} RefDirection must be [x, y]")
            ux = float(_number(ref[0], f"{yaml_id} RefDirection"))
            uy = float(_number(ref[1], f"{yaml_id} RefDirection"))
            if math.hypot(ux, uy) < TOL:
                raise ValueError(f"{yaml_id} RefDirection has zero length")
        container = element.get("ContainedInStructure")
        if container is not None and container not in self.space_ids:
            raise ValueError(f"{yaml_id} is contained in unknown space {container}")
        parent = self.placements[container] if container else self.storey_placement
        placement = self._local((ox, oy, z), (ux, uy, 0.0), parent)
        sizes = []
        for key in FURNISHING_SIZE:
            if element.get(key) is None:
                sizes.append(None)
                continue
            value = _number(element[key], f"{yaml_id} {key}")
            if float(value) <= 0:
                raise ValueError(f"{yaml_id} {key} must be positive")
            sizes.append(value)
        shape = None
        if all(size is not None for size in sizes):
            shape = self._shape(
                [("Body", "SweptSolid", self.body, self._box(sizes[0], sizes[1], sizes[2]))]
            )
        values = {
            "GlobalId": global_id(yaml_id, element.get("GlobalId")),
            "Name": self._named(element, yaml_id),
            "ObjectPlacement": placement,
            "Representation": shape,
        }
        for key in ("Description", "Tag", "ObjectType", "PredefinedType"):
            if element.get(key) is not None:
                values[key] = element[key]
        product = self.file.create_entity(ifc_class, **values)
        book = {"id": yaml_id}
        if origin is not None:
            book["OriginX"] = origin[0]
            book["OriginY"] = origin[1]
        if elevation is not None:
            book["Elevation"] = elevation
        if ref is not None:
            book["RefDirectionX"] = ref[0]
            book["RefDirectionY"] = ref[1]
        for key, size in zip(FURNISHING_SIZE, sizes):
            if size is not None:
                book[key] = size
        self._pset(product, book, yaml_id)
        self._user_psets(product, element)
        self._note_type(element, type_class, product)
        self.products[yaml_id] = product
        self.placements[yaml_id] = placement
        return product

    def _note_type(self, element, type_class, product):
        predefined = element.get("PredefinedType")
        object_type = element.get("ObjectType")
        if predefined is None and not object_type:
            return
        if type_class in TYPE_PREDEFINED_REQUIRED and predefined is None:
            return
        key = (type_class, predefined, object_type)
        self.typed.setdefault(key, []).append(product)

    def _types(self):
        for (type_class, predefined, object_type), products in self.typed.items():
            token = f"{type_class}:{predefined or ''}:{object_type or ''}"
            values = {
                "GlobalId": global_id(f"type:{token}"),
                "Name": object_type or predefined,
            }
            if predefined is not None:
                values["PredefinedType"] = predefined
            if object_type:
                values["ElementType"] = object_type
            if type_class == FURNITURE_TYPE_CLASS:
                # Required attribute. Not a measured assembly place.
                values["AssemblyPlace"] = "NOTDEFINED"
            created = self.file.create_entity(type_class, **values)
            self.file.create_entity(
                "IfcRelDefinesByType",
                GlobalId=global_id(f"rel:defines-type:{token}"),
                RelatedObjects=products,
                RelatingType=created,
            )

    def _containment(self):
        if self.contained:
            self.file.create_entity(
                "IfcRelContainedInSpatialStructure",
                GlobalId=self._gid("containment", self.doc["storey"]["id"]),
                RelatedElements=self.contained,
                RelatingStructure=self.storey,
            )
        for space in self.doc.get("spaces") or []:
            products = self.contained_by_space.get(space["id"])
            if not products:
                continue
            self.file.create_entity(
                "IfcRelContainedInSpatialStructure",
                GlobalId=self._gid("containment", space["id"]),
                RelatedElements=products,
                RelatingStructure=self.products[space["id"]],
            )


def build_ifc(doc):
    return Builder(doc).file


def write_ifc(doc, path):
    model = build_ifc(doc)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    model.write(str(path))
    return model
