"""Write a yaml-ifc document to an IFC4 file."""

import math
from pathlib import Path

import ifcopenshell
import ifcopenshell.validate

from yaml_ifc.ids import global_id
from yaml_ifc.supported import (
    DEFAULT_OPENING_DEPTH,
    DEFAULT_WALL_HEIGHT,
    HEADER_FILE_NAME,
    HEADER_TIMESTAMP,
    ORIGINATING_SYSTEM,
    PSET_NAME,
)

TOL = 1e-9


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
        self._stamp_header()
        self._units_and_context()
        self._spatial()
        self._elements()
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
        self.axis = f.create_entity(
            "IfcGeometricRepresentationSubContext",
            ContextIdentifier="Axis",
            ContextType="Model",
            ParentContext=context,
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
            RepresentationContexts=[self.context],
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
        self._pset(product, book, yaml_id)
        self._user_psets(product, wall)
        self._materials(product, wall)
        self.products[yaml_id] = product
        self.placements[yaml_id] = placement
        return product

    def _materials(self, product, wall):
        layers = ((wall.get("MaterialLayers") or {}).get("Layers")) or []
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

    def _containment(self):
        if not self.contained:
            return
        self.file.create_entity(
            "IfcRelContainedInSpatialStructure",
            GlobalId=self._gid("containment", self.doc["storey"]["id"]),
            RelatedElements=self.contained,
            RelatingStructure=self.storey,
        )


def build_ifc(doc):
    return Builder(doc).file


def write_ifc(doc, path):
    model = build_ifc(doc)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    model.write(str(path))
    return model
