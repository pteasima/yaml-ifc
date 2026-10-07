"""Read the supported yaml-ifc subset out of an IFC file.

Everything else is counted and returned, not written into the YAML.
Lengths are converted to metres.
"""

import math
from collections import Counter

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.placement
import ifcopenshell.util.unit
import numpy as np

from yaml_ifc.ids import connection_yaml_id, is_derived
from yaml_ifc.supported import (
    FURNISHINGS,
    FURNISHING_SIZE,
    ORIGINATING_SYSTEM,
    PSET_AXIS,
    PSET_MATERIAL_FROM_THICKNESS,
    PSET_NAME,
    SCHEMA_NAME,
    SUPPORTED,
)
from yaml_ifc.yamlio import num

TOL = 1e-5
SUPPORTED_CLASSES = tuple(row[0] for row in SUPPORTED)


def _enum(value):
    if value is None:
        return None
    text = str(value).strip(".")
    return text or None


def _plain(value):
    if value is None:
        return None
    wrapped = getattr(value, "wrappedValue", value)
    if isinstance(wrapped, bool):
        return bool(wrapped)
    if isinstance(wrapped, int) and not isinstance(wrapped, bool):
        return int(wrapped)
    if isinstance(wrapped, float):
        return num(wrapped)
    return str(wrapped)


def _apply(matrix, xyz):
    x, y = float(xyz[0]), float(xyz[1])
    z = float(xyz[2]) if len(xyz) > 2 else 0.0
    point = matrix @ np.array([x, y, z, 1.0])
    return point[:3]


def _pset_map(element):
    found = {}
    for definition in getattr(element, "IsDefinedBy", []) or []:
        if not definition.is_a("IfcRelDefinesByProperties"):
            continue
        pset = definition.RelatingPropertyDefinition
        if not pset or not pset.is_a("IfcPropertySet") or pset.Name != PSET_NAME:
            continue
        for prop in pset.HasProperties or []:
            if prop.is_a("IfcPropertySingleValue"):
                found[prop.Name] = _plain(prop.NominalValue)
    return found


def _defining_type(element):
    for rel in getattr(element, "IsTypedBy", []) or []:
        if rel.is_a("IfcRelDefinesByType") and rel.RelatingType:
            return rel.RelatingType
    return None


def _object_type_text(element):
    if getattr(element, "ObjectType", None):
        return str(element.ObjectType)
    typed = _defining_type(element)
    element_type = getattr(typed, "ElementType", None) if typed is not None else None
    if element_type:
        return str(element_type)
    return None


def _user_psets(element):
    groups = []
    for definition in getattr(element, "IsDefinedBy", []) or []:
        if not definition.is_a("IfcRelDefinesByProperties"):
            continue
        pset = definition.RelatingPropertyDefinition
        if not pset or not pset.is_a("IfcPropertySet") or pset.Name == PSET_NAME:
            continue
        properties = {}
        for prop in pset.HasProperties or []:
            if prop.is_a("IfcPropertySingleValue") and prop.Name:
                properties[prop.Name] = _plain(prop.NominalValue)
        groups.append({"Name": pset.Name, "Properties": properties})
    return groups


def _identity():
    return np.eye(4)


def _matrix(placement):
    if placement is None:
        return _identity()
    return ifcopenshell.util.placement.get_local_placement(placement)


def _supported(element):
    return any(element.is_a(name) for name in SUPPORTED_CLASSES)


def _skip_counts(model):
    counts = Counter()
    for product in model.by_type("IfcProduct"):
        if not _supported(product):
            counts[product.is_a()] += 1
    return counts


def _body_tree(item):
    if item is None:
        return
    if item.is_a("IfcMappedItem"):
        source = item.MappingSource.MappedRepresentation if item.MappingSource else None
        if source:
            for child in source.Items or []:
                yield from _body_tree(child)
        return
    if item.is_a("IfcBooleanResult"):
        yield from _body_tree(item.FirstOperand)
        yield from _body_tree(item.SecondOperand)
        yield item
        return
    yield item


def _curve_points(item):
    if item is None:
        return []
    if item.is_a("IfcPolyline"):
        return [tuple(point.Coordinates) for point in item.Points]
    if item.is_a("IfcIndexedPolyCurve") and item.Points is not None:
        return [tuple(point) for point in item.Points.CoordList]
    return []


def _items(product, identifier):
    shape = product.Representation
    if not shape:
        return []
    found = []
    for rep in shape.Representations or []:
        if rep.RepresentationIdentifier == identifier:
            found.extend(rep.Items or [])
    return found


def _clipped(product):
    for item in _items(product, "Body"):
        for node in _body_tree(item):
            if node.is_a("IfcBooleanResult"):
                return True
    return False


def _extrusion(product):
    for item in _items(product, "Body"):
        for node in _body_tree(item):
            if node.is_a("IfcExtrudedAreaSolid"):
                return node
    return None


def _profile_points(profile):
    if profile is None:
        return []
    if profile.is_a("IfcRectangleProfileDef"):
        xdim, ydim = float(profile.XDim), float(profile.YDim)
        position = profile.Position
        cx = cy = 0.0
        if position and position.Location:
            coords = position.Location.Coordinates
            cx, cy = float(coords[0]), float(coords[1])
        return [
            (cx - xdim / 2.0, cy - ydim / 2.0),
            (cx + xdim / 2.0, cy - ydim / 2.0),
            (cx + xdim / 2.0, cy + ydim / 2.0),
            (cx - xdim / 2.0, cy + ydim / 2.0),
        ]
    if profile.is_a("IfcArbitraryClosedProfileDef"):
        curve = profile.OuterCurve
        if curve and curve.is_a("IfcPolyline"):
            return [tuple(float(v) for v in point.Coordinates) for point in curve.Points]
    return []


def _bbox_height(product):
    try:
        settings = ifcopenshell.geom.settings()
        shape = ifcopenshell.geom.create_shape(settings, product)
    except Exception:
        return None
    verts = shape.geometry.verts
    if not verts:
        return None
    zs = verts[2::3]
    return num(max(zs) - min(zs))


def _material_layers(element, scale):
    layers = []
    for rel in getattr(element, "HasAssociations", []) or []:
        if not rel.is_a("IfcRelAssociatesMaterial"):
            continue
        material = rel.RelatingMaterial
        layer_set = None
        if material and material.is_a("IfcMaterialLayerSetUsage"):
            layer_set = material.ForLayerSet
        elif material and material.is_a("IfcMaterialLayerSet"):
            layer_set = material
        if not layer_set:
            continue
        for layer in layer_set.MaterialLayers or []:
            item = {"LayerThickness": num(float(layer.LayerThickness) * scale)}
            if layer.Name:
                item["Name"] = layer.Name
            if layer.Material and layer.Material.Name:
                item["Material"] = layer.Material.Name
            if layer.Category:
                item["Category"] = layer.Category
            if layer.Priority is not None:
                item["Priority"] = int(layer.Priority)
            if layer.IsVentilated is not None:
                item["IsVentilated"] = bool(layer.IsVentilated)
            # Name is optional and comes before the thickness in the spec example.
            ordered = {}
            for key in ("Name", "LayerThickness", "Material", "Category", "Priority", "IsVentilated"):
                if key in item:
                    ordered[key] = item[key]
            layers.append(ordered)
    if not layers:
        return None
    return {"Layers": layers}


def _put(target, key, value):
    if value is None:
        return
    if isinstance(value, str) and value == "":
        return
    target[key] = value


class Reader:
    def __init__(self, model):
        self.model = model
        self.scale = ifcopenshell.util.unit.calculate_unit_scale(model) or 1.0
        self.ours = model.header.file_name.originating_system == ORIGINATING_SYSTEM
        self.used_ids = set()
        self.by_product = {}
        self.storey = None

    def _metres(self, value):
        return num(float(value) * self.scale)

    def _id_for(self, element):
        if element in self.by_product:
            return self.by_product[element]
        book = _pset_map(element)
        if book.get("id"):
            chosen = str(book["id"])
        elif element.Name and element.Name not in self.used_ids:
            chosen = element.Name
        else:
            chosen = element.GlobalId
        if chosen in self.used_ids:
            chosen = element.GlobalId
        self.used_ids.add(chosen)
        self.by_product[element] = chosen
        return chosen

    def _common(self, element, book):
        yaml_id = self._id_for(element)
        entity = {"id": yaml_id}
        name = element.Name
        if name and name != yaml_id:
            entity["Name"] = name
        if element.GlobalId and not is_derived(element.GlobalId, yaml_id):
            entity["GlobalId"] = element.GlobalId
        description = getattr(element, "Description", None)
        _put(entity, "Description", description)
        tag = getattr(element, "Tag", None)
        _put(entity, "Tag", tag)
        predefined = _enum(getattr(element, "PredefinedType", None))
        if predefined and not (element.is_a("IfcOpeningElement") and predefined == "OPENING"):
            entity["PredefinedType"] = predefined
        psets = _user_psets(element)
        if psets:
            entity["PropertySets"] = psets
        entity["_book"] = book
        return entity

    def _storey_matrix(self):
        if self.storey and self.storey.ObjectPlacement:
            return np.linalg.inv(_matrix(self.storey.ObjectPlacement))
        return _identity()

    def _to_storey(self, placement, local):
        world = _apply(_matrix(placement), local)
        return _apply(self._storey_matrix(), world)

    def _axis_ends(self, wall):
        for item in _items(wall, "Axis"):
            points = _curve_points(item)
            if len(points) < 2:
                continue
            start = self._to_storey(wall.ObjectPlacement, points[0])
            end = self._to_storey(wall.ObjectPlacement, points[-1])
            return start, end
        return None

    def _order_axis(self, start, end):
        a = (self._metres(start[0]), self._metres(start[1]))
        b = (self._metres(end[0]), self._metres(end[1]))
        if (b[0], b[1]) < (a[0], a[1]):
            return b, a
        return a, b

    def _wall_height(self, wall):
        if not _items(wall, "Body"):
            return None
        if _clipped(wall):
            height = _bbox_height(wall)
            if height is not None:
                return height
        solid = _extrusion(wall)
        if solid is not None:
            return self._metres(solid.Depth)
        return _bbox_height(wall)

    def _centered_thickness(self, points, scale):
        if len(points) < 4:
            return None
        ys = [float(point[1]) for point in points]
        xs = [float(point[0]) for point in points]
        if abs(min(ys) + max(ys)) > 1e-3:
            return None
        unique = {(round(x, 4), round(y, 4)) for x, y in zip(xs, ys)}
        if len(unique) > 4:
            return None
        return num((max(ys) - min(ys)) * scale)

    def _authored_axis(self, book):
        if not all(key in book for key in PSET_AXIS):
            return None
        start = [book["AxisStartX"], book["AxisStartY"]]
        end = [book["AxisEndX"], book["AxisEndY"]]
        return {"Start": start, "End": end}

    def _wall(self, wall):
        book = _pset_map(wall)
        entity = self._common(wall, book)
        # Regeneration trims the axis curve. The authored ends are in the pset.
        authored = self._authored_axis(book)
        ends = self._axis_ends(wall)
        if authored:
            entity["Axis"] = authored
        elif ends:
            start, end = self._order_axis(*ends)
            entity["Axis"] = {"Start": [start[0], start[1]], "End": [end[0], end[1]]}
        solid = _extrusion(wall)
        points = _profile_points(solid.SweptArea) if solid is not None else []
        plan = book.get("PlanShape")
        thickness = self._centered_thickness(points, self.scale) if points else None
        layers = _material_layers(wall, self.scale)
        derived_layers = bool(book.get(PSET_MATERIAL_FROM_THICKNESS))
        if plan == "footprint" and points and (ends or authored):
            entity["Footprint"] = self._footprint(wall, solid, points)
        elif plan == "profile" and points:
            entity["Profile"] = [[num(p[0] * self.scale), num(p[1] * self.scale)] for p in _unique(points)]
        elif plan == "footprint" and points and not ends and not authored:
            entity["Footprint"] = [
                [self._metres(p[0]), self._metres(p[1])] for p in _unique(points)
            ]
        elif thickness is not None:
            entity["Thickness"] = thickness
        elif layers and plan not in ("footprint", "profile"):
            # A butt joint replaces the rectangle with a trimmed profile.
            entity["Thickness"] = num(sum(layer["LayerThickness"] for layer in layers["Layers"]))
        elif points:
            entity["Footprint"] = self._footprint(wall, solid, points) if (ends or authored) else [
                [self._metres(p[0]), self._metres(p[1])] for p in _unique(points)
            ]
        height = self._wall_height(wall)
        if height is not None and not book.get("HeightDefaulted"):
            entity["Height"] = height
        # Z in the storey frame. Omitted when it is the storey elevation.
        base = self._base_z(wall)
        if abs(base) > TOL:
            entity["Elevation"] = num(base)
        if layers and not derived_layers:
            entity["MaterialLayers"] = layers
        return _ordered_wall(entity)

    def _base_z(self, wall):
        if not wall.ObjectPlacement:
            return 0.0
        origin = self._to_storey(wall.ObjectPlacement, (0.0, 0.0, 0.0))
        return float(origin[2]) * self.scale

    def _footprint(self, wall, solid, points):
        local_solid = (
            ifcopenshell.util.placement.get_axis2placement(solid.Position) if solid.Position else _identity()
        )
        transformed = []
        for point in _unique(points):
            local = _apply(local_solid, (point[0], point[1], 0.0))
            storey = self._to_storey(wall.ObjectPlacement, local)
            transformed.append([self._metres(storey[0]), self._metres(storey[1])])
        return transformed

    def _opening_from_geometry(self, opening, wall, entity):
        solid = _extrusion(opening)
        if solid is None or wall is None:
            return
        ends = self._axis_ends(wall)
        if not ends:
            return
        start, end = self._order_axis(*ends)
        sx, sy = float(start[0]), float(start[1])
        ex, ey = float(end[0]), float(end[1])
        dx, dy = ex - sx, ey - sy
        length = math.hypot(dx, dy) or 1.0
        ux, uy = dx / length, dy / length
        px, py = -uy, ux
        points = _profile_points(solid.SweptArea)
        if not points:
            return
        local_solid = (
            ifcopenshell.util.placement.get_axis2placement(solid.Position)
            if solid.Position
            else _identity()
        )
        depth = float(solid.Depth)
        corners = []
        for point in points:
            for z in (0.0, depth):
                local = _apply(local_solid, (point[0], point[1], z))
                world = _apply(_matrix(opening.ObjectPlacement), local)
                storey = _apply(self._storey_matrix(), world)
                mx, my, mz = (float(v) * self.scale for v in storey)
                along = (mx - sx) * ux + (my - sy) * uy
                across = (mx - sx) * px + (my - sy) * py
                corners.append((along, across, mz))
        alongs = [c[0] for c in corners]
        acrosses = [c[1] for c in corners]
        zs = [c[2] for c in corners]
        entity["AlongAxis"] = num(min(alongs))
        entity["Width"] = num(max(alongs) - min(alongs))
        entity["SillHeight"] = num(min(zs))
        entity["Height"] = num(max(zs) - min(zs))
        measured_depth = num(max(acrosses) - min(acrosses))
        entity["_depth"] = measured_depth
        entity["_host"] = self.by_product.get(wall)

    def _opening(self, opening, void_of):
        book = _pset_map(opening)
        entity = self._common(opening, book)
        host = void_of.get(opening)
        if host is not None and host in self.by_product:
            entity["VoidsElement"] = self.by_product[host]
        if book:
            for key in ("AlongAxis", "Width", "Height", "SillHeight", "Depth", "HeadHeight"):
                if key in book:
                    entity[key] = book[key]
            if book.get("DepthDefaulted"):
                entity.pop("Depth", None)
            if "HeadHeight" in book and "Height" not in book:
                entity.pop("Height", None)
                entity.pop("SillHeight", None)
        else:
            self._opening_from_geometry(opening, host, entity)
        return _ordered_opening(entity)

    def _direction_ratios(self, direction):
        if direction is None:
            return None
        return [float(value) for value in direction.DirectionRatios]

    def _placement_is_identity(self, placement):
        if placement is None:
            return True
        location = placement.Location.Coordinates if placement.Location else (0.0, 0.0, 0.0)
        if any(abs(float(value)) > 1e-6 for value in location):
            return False
        axis = self._direction_ratios(getattr(placement, "Axis", None))
        if axis is not None and (
            len(axis) < 3 or abs(axis[0]) > 1e-4 or abs(axis[1]) > 1e-4 or abs(axis[2] - 1.0) > 1e-4
        ):
            return False
        ref = self._direction_ratios(getattr(placement, "RefDirection", None))
        if ref is not None and (len(ref) < 2 or abs(ref[0] - 1.0) > 1e-4 or abs(ref[1]) > 1e-4):
            return False
        return True

    def _corner_box(self, profile):
        """Width and depth of a rectangle whose corner, not its centre, is the origin."""
        if profile is None or not profile.is_a("IfcRectangleProfileDef"):
            return None
        position = profile.Position
        if position is None or position.Location is None:
            return None
        ref = self._direction_ratios(getattr(position, "RefDirection", None))
        if ref is not None and (len(ref) < 2 or abs(ref[0] - 1.0) > 1e-4 or abs(ref[1]) > 1e-4):
            return None
        centre = position.Location.Coordinates
        xdim, ydim = float(profile.XDim), float(profile.YDim)
        if abs(float(centre[0]) - xdim / 2.0) > 1e-4 or abs(float(centre[1]) - ydim / 2.0) > 1e-4:
            return None
        return xdim, ydim

    def _furnishing_from_geometry(self, product, entity):
        """Placement and the corner-origin box, for a file this writer did not make."""
        if not product.ObjectPlacement:
            return
        origin = self._to_storey(product.ObjectPlacement, (0.0, 0.0, 0.0))
        along = self._to_storey(product.ObjectPlacement, (1.0, 0.0, 0.0))
        entity["Origin"] = [self._metres(origin[0]), self._metres(origin[1])]
        elevation = self._metres(origin[2])
        if abs(float(elevation)) > TOL:
            entity["Elevation"] = elevation
        dx = float(along[0]) - float(origin[0])
        dy = float(along[1]) - float(origin[1])
        length = math.hypot(dx, dy)
        if length > TOL and (abs(dx / length - 1.0) > 1e-4 or abs(dy / length) > 1e-4):
            entity["RefDirection"] = [num(dx / length), num(dy / length)]
        solid = _extrusion(product)
        if solid is None or not self._placement_is_identity(solid.Position):
            return
        extruded = self._direction_ratios(solid.ExtrudedDirection)
        if extruded is not None and (
            len(extruded) < 3
            or abs(extruded[0]) > 1e-4
            or abs(extruded[1]) > 1e-4
            or float(extruded[2]) <= 0
        ):
            return
        box = self._corner_box(solid.SweptArea)
        if box is None:
            return
        entity["Width"] = self._metres(box[0])
        entity["Depth"] = self._metres(box[1])
        entity["Height"] = self._metres(solid.Depth)

    def _space(self, space):
        book = _pset_map(space)
        entity = self._common(space, book)
        _put(entity, "ObjectType", _object_type_text(space))
        _put(entity, "LongName", getattr(space, "LongName", None))
        if space.ElevationWithFlooring is not None:
            entity["ElevationWithFlooring"] = self._metres(space.ElevationWithFlooring)
        return _ordered_space(entity)

    def _furnishing(self, element, contained_in):
        book = _pset_map(element)
        entity = self._common(element, book)
        _put(entity, "ObjectType", _object_type_text(element))
        if "PredefinedType" not in entity:
            typed = _defining_type(element)
            fallback = _enum(getattr(typed, "PredefinedType", None)) if typed is not None else None
            if fallback:
                entity["PredefinedType"] = fallback
        if book.get("id"):
            if "OriginX" in book or "OriginY" in book:
                entity["Origin"] = [book.get("OriginX"), book.get("OriginY")]
            if "Elevation" in book:
                entity["Elevation"] = book["Elevation"]
            if "RefDirectionX" in book or "RefDirectionY" in book:
                entity["RefDirection"] = [book.get("RefDirectionX"), book.get("RefDirectionY")]
            for key in FURNISHING_SIZE:
                if key in book:
                    entity[key] = book[key]
        else:
            self._furnishing_from_geometry(element, entity)
        container = contained_in.get(element)
        if container is not None and container.is_a("IfcSpace"):
            entity["ContainedInStructure"] = self.by_product.get(container) or self._id_for(container)
        return _ordered_furnishing(entity)

    def _filler(self, element, fill_of):
        book = _pset_map(element)
        entity = self._common(element, book)
        opening = fill_of.get(element)
        if opening is not None and opening in self.by_product:
            entity["FillsOpening"] = self.by_product[opening]
        _put(entity, "OverallWidth", None if element.OverallWidth is None else self._metres(element.OverallWidth))
        _put(entity, "OverallHeight", None if element.OverallHeight is None else self._metres(element.OverallHeight))
        if element.is_a("IfcDoor"):
            _put(entity, "OperationType", _enum(element.OperationType))
        if element.is_a("IfcWindow"):
            _put(entity, "PartitioningType", _enum(element.PartitioningType))
        return _ordered_filler(entity)

    def _bind_spatial(self, element):
        if element.is_a("IfcProject") and self.ours and element.LongName:
            self.used_ids.add(element.LongName)
            self.by_product[element] = element.LongName
            return
        self._id_for(element)

    def _spatial_node(self, element, extra):
        book = _pset_map(element)
        if element.is_a("IfcProject") and self.ours and element.LongName:
            # Project cannot own the bookkeeping property set. LongName holds the id.
            self.used_ids.add(element.LongName)
            self.by_product[element] = element.LongName
            entity = {"id": element.LongName}
            if element.Name and element.Name != element.LongName:
                entity["Name"] = element.Name
            if element.GlobalId and not is_derived(element.GlobalId, element.LongName):
                entity["GlobalId"] = element.GlobalId
        else:
            entity = self._common(element, book)
        entity.update(extra)
        entity.pop("_book", None)
        entity.pop("_depth", None)
        entity.pop("_host", None)
        return entity

    def document(self):
        model = self.model
        projects = model.by_type("IfcProject")
        if not projects:
            raise ValueError("IFC file has no IfcProject")
        project = projects[0]
        sites = _children(project) or model.by_type("IfcSite")
        site = sites[0]
        buildings = _children(site) or model.by_type("IfcBuilding")
        building = buildings[0]
        storeys = _children(building) or model.by_type("IfcBuildingStorey")
        if len(storeys) != 1:
            raise ValueError(f"expected one storey, found {len(storeys)}")
        self.storey = storeys[0]
        for element in (project, site, building, self.storey):
            self._bind_spatial(element)

        walls = [_strip(self._wall(wall)) for wall in model.by_type("IfcWall")]
        connections = self._connections()
        void_of = {}
        for rel in model.by_type("IfcRelVoidsElement"):
            void_of[rel.RelatedOpeningElement] = rel.RelatingBuildingElement
        openings = []
        for opening in model.by_type("IfcOpeningElement"):
            openings.append(_strip(self._opening(opening, void_of)))
        self._apply_depth_default(openings, walls)
        fill_of = {}
        for rel in model.by_type("IfcRelFillsElement"):
            fill_of[rel.RelatedBuildingElement] = rel.RelatingOpeningElement
        doors = [_strip(self._filler(door, fill_of)) for door in model.by_type("IfcDoor")]
        windows = [_strip(self._filler(window, fill_of)) for window in model.by_type("IfcWindow")]
        # Spaces first, so a furnishing can name the room that contains it.
        spaces = [_strip(self._space(space)) for space in model.by_type("IfcSpace")]
        contained_in = {}
        for rel in model.by_type("IfcRelContainedInSpatialStructure"):
            for related in rel.RelatedElements or []:
                contained_in[related] = rel.RelatingStructure
        furnishing_lists = {}
        for key, ifc_class, _type_class in FURNISHINGS:
            furnishing_lists[key] = [
                _strip(self._furnishing(element, contained_in))
                for element in model.by_type(ifc_class)
            ]

        site_extra = {}
        if site.RefElevation is not None:
            site_extra["RefElevation"] = self._metres(site.RefElevation)
        site_extra["Aggregates"] = [self.by_product[building]]
        building_extra = {"Aggregates": [self.by_product[self.storey]]}
        storey_extra = {}
        if self.storey.Elevation is not None:
            storey_extra["Elevation"] = self._metres(self.storey.Elevation)
        project_extra = {"Aggregates": [self.by_product[site]]}

        document = {
            "schema": SCHEMA_NAME,
            "units": {"LengthUnit": "METRE"},
            "project": self._spatial_node(project, project_extra),
            "site": self._spatial_node(site, site_extra),
            "building": self._spatial_node(building, building_extra),
            "storey": self._spatial_node(self.storey, storey_extra),
        }
        if spaces:
            document["spaces"] = spaces
        # The original lists stay present when empty, so a walls-only file
        # comes back with openings, doors, and windows still written.
        document["walls"] = walls
        if connections:
            document["connections"] = connections
        document["openings"] = openings
        document["doors"] = doors
        document["windows"] = windows
        for key, _ifc_class, _type_class in FURNISHINGS:
            if furnishing_lists[key]:
                document[key] = furnishing_lists[key]
        return document

    def _connections(self):
        rows = []
        for rel in self.model.by_type("IfcRelConnectsPathElements"):
            relating = self.by_product.get(rel.RelatingElement)
            related = self.by_product.get(rel.RelatedElement)
            if not relating or not related:
                continue
            row = {
                "RelatingElement": relating,
                "RelatingConnectionType": _enum(rel.RelatingConnectionType),
                "RelatedElement": related,
                "RelatedConnectionType": _enum(rel.RelatedConnectionType),
            }
            if rel.GlobalId and not is_derived(rel.GlobalId, connection_yaml_id(row)):
                row["GlobalId"] = rel.GlobalId
            rows.append(row)
        return rows

    def _apply_depth_default(self, openings, walls):
        thickness = {}
        for wall in walls:
            if wall.get("Thickness") is not None:
                thickness[wall["id"]] = wall["Thickness"]
        for opening in openings:
            measured = opening.pop("_depth", None)
            host = opening.pop("_host", None)
            if measured is None or "Depth" in opening:
                continue
            host_thickness = thickness.get(host)
            if host_thickness is not None and abs(float(measured) - float(host_thickness)) <= 1e-4:
                continue
            opening["Depth"] = measured
            ordered = _ordered_opening(opening)
            opening.clear()
            opening.update(ordered)


def _children(element):
    found = []
    for rel in getattr(element, "IsDecomposedBy", []) or []:
        if rel.is_a("IfcRelAggregates"):
            found.extend(rel.RelatedObjects or [])
    return found


def _unique(points):
    cleaned = []
    for point in points:
        pair = (float(point[0]), float(point[1]))
        if cleaned and _close(cleaned[-1], pair):
            continue
        cleaned.append(pair)
    if len(cleaned) > 1 and _close(cleaned[0], cleaned[-1]):
        cleaned.pop()
    return cleaned


def _close(a, b):
    return abs(a[0] - b[0]) < 1e-6 and abs(a[1] - b[1]) < 1e-6


def _strip(entity):
    entity.pop("_book", None)
    return entity


def _pick(entity, keys):
    ordered = {}
    for key in keys:
        if key in entity:
            ordered[key] = entity[key]
    for key, value in entity.items():
        if key not in ordered:
            ordered[key] = value
    return ordered


def _ordered_wall(entity):
    return _pick(
        entity,
        (
            "id",
            "Name",
            "GlobalId",
            "Description",
            "Tag",
            "PredefinedType",
            "Axis",
            "Thickness",
            "Height",
            "Elevation",
            "Footprint",
            "Profile",
            "MaterialLayers",
            "PropertySets",
        ),
    )


def _ordered_space(entity):
    return _pick(
        entity,
        (
            "id",
            "Name",
            "GlobalId",
            "Description",
            "ObjectType",
            "LongName",
            "PredefinedType",
            "ElevationWithFlooring",
            "PropertySets",
        ),
    )


def _ordered_furnishing(entity):
    return _pick(
        entity,
        (
            "id",
            "Name",
            "GlobalId",
            "Description",
            "Tag",
            "PredefinedType",
            "ObjectType",
            "ContainedInStructure",
            "Origin",
            "Elevation",
            "RefDirection",
            "Width",
            "Depth",
            "Height",
            "PropertySets",
        ),
    )


def _ordered_opening(entity):
    return _pick(
        entity,
        (
            "id",
            "Name",
            "GlobalId",
            "Description",
            "VoidsElement",
            "AlongAxis",
            "Width",
            "Height",
            "SillHeight",
            "HeadHeight",
            "Depth",
            "Tag",
            "PredefinedType",
            "PropertySets",
        ),
    )


def _ordered_filler(entity):
    return _pick(
        entity,
        (
            "id",
            "Name",
            "GlobalId",
            "Description",
            "FillsOpening",
            "OverallWidth",
            "OverallHeight",
            "Tag",
            "PredefinedType",
            "OperationType",
            "PartitioningType",
            "PropertySets",
        ),
    )


def read_ifc(path):
    model = ifcopenshell.open(str(path))
    reader = Reader(model)
    return reader.document(), _skip_counts(model)


def format_skipped(counts):
    lines = [f"{name} {counts[name]}" for name in sorted(counts)]
    return "\n".join(lines) + ("\n" if lines else "")
