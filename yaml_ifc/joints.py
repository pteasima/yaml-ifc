"""Butt-joint bodies, and the plan footprints IfcOpenShell computes for them.

The converter writes ``IfcRelConnectsPathElements`` and asks IfcOpenShell to
rebuild each joined wall. ``footprints`` reads those rebuilt profiles back, so
a 3D model can extrude the same polygons the IFC uses.
"""

import ifcopenshell.util.placement
import numpy as np

from yaml_ifc.supported import PSET_NAME
from yaml_ifc.yamlio import num

# IfcOpenShell 0.8.5 stores layers as namedtuples, then assigns into them
# when a connection overrides priorities. The assignment raises, so butt
# joints (which need that override) cannot regenerate until this is patched.
_PATCHED = False


def install_priority_fix():
    global _PATCHED
    if _PATCHED:
        return
    from ifcopenshell.api.geometry.regenerate_wall_representation import (
        PrioritisedLayer,
        Regenerator,
    )

    def combine_layers(self, layers, override_priorities):
        layers = list(layers)
        if override_priorities:
            for index, priority in enumerate(override_priorities[: len(layers)]):
                layers[index] = PrioritisedLayer(priority, layers[index].thickness)
        if not layers:
            return []
        results = [layers.pop(0)]
        for layer in layers:
            if not layer.thickness:
                continue
            if layer.priority == results[-1].priority:
                results[-1] = PrioritisedLayer(layer.priority, results[-1].thickness + layer.thickness)
            else:
                results.append(layer)
        return results

    Regenerator.combine_layers = combine_layers
    _PATCHED = True


def _plain(value):
    if value is None:
        return None
    wrapped = getattr(value, "wrappedValue", value)
    if isinstance(wrapped, bool):
        return bool(wrapped)
    if isinstance(wrapped, (int, float)):
        return wrapped
    return str(wrapped)


def _yaml_id(product):
    for definition in getattr(product, "IsDefinedBy", []) or []:
        if not definition.is_a("IfcRelDefinesByProperties"):
            continue
        pset = definition.RelatingPropertyDefinition
        if not pset or not pset.is_a("IfcPropertySet") or pset.Name != PSET_NAME:
            continue
        for prop in pset.HasProperties or []:
            if prop.is_a("IfcPropertySingleValue") and prop.Name == "id":
                found = _plain(prop.NominalValue)
                if found:
                    return str(found)
    return product.Name


def _apply(matrix, xyz):
    x, y = float(xyz[0]), float(xyz[1])
    z = float(xyz[2]) if len(xyz) > 2 else 0.0
    return matrix @ np.array([x, y, z, 1.0])


def _curve_points(curve):
    if curve is None:
        return []
    if curve.is_a("IfcPolyline"):
        return [tuple(float(c) for c in point.Coordinates) for point in curve.Points]
    if curve.is_a("IfcIndexedPolyCurve") and curve.Points:
        return [tuple(float(c) for c in point) for point in curve.Points.CoordList]
    return []


def _profile_loops(profile):
    if profile is None:
        return []
    if profile.is_a("IfcCompositeProfileDef"):
        loops = []
        for child in profile.Profiles or []:
            loops.extend(_profile_loops(child))
        return loops
    if profile.is_a("IfcRectangleProfileDef"):
        xdim, ydim = float(profile.XDim), float(profile.YDim)
        cx = cy = 0.0
        if profile.Position and profile.Position.Location:
            coords = profile.Position.Location.Coordinates
            cx, cy = float(coords[0]), float(coords[1])
        return [[
            (cx - xdim / 2.0, cy - ydim / 2.0),
            (cx + xdim / 2.0, cy - ydim / 2.0),
            (cx + xdim / 2.0, cy + ydim / 2.0),
            (cx - xdim / 2.0, cy + ydim / 2.0),
        ]]
    if profile.is_a("IfcArbitraryClosedProfileDef"):
        points = _curve_points(profile.OuterCurve)
        return [points] if len(points) >= 3 else []
    return []


def _clean(points):
    cleaned = []
    for point in points:
        pair = (float(point[0]), float(point[1]))
        if cleaned and abs(cleaned[-1][0] - pair[0]) < 1e-9 and abs(cleaned[-1][1] - pair[1]) < 1e-9:
            continue
        cleaned.append(pair)
    if len(cleaned) > 1 and abs(cleaned[0][0] - cleaned[-1][0]) < 1e-9 and abs(cleaned[0][1] - cleaned[-1][1]) < 1e-9:
        cleaned.pop()
    return cleaned


def _body_item(product):
    shape = product.Representation
    if not shape:
        return None
    for rep in shape.Representations or []:
        if rep.RepresentationIdentifier != "Body":
            continue
        for item in rep.Items or []:
            node = item
            while node is not None and node.is_a("IfcBooleanResult"):
                node = node.FirstOperand
            if node is not None and node.is_a("IfcExtrudedAreaSolid"):
                return node
    return None


def _storey_matrix(model):
    storeys = model.by_type("IfcBuildingStorey")
    if storeys and storeys[0].ObjectPlacement:
        return np.linalg.inv(ifcopenshell.util.placement.get_local_placement(storeys[0].ObjectPlacement))
    return np.eye(4)


def footprints(doc):
    """Trimmed wall footprints in plan metres.

    ``doc`` is a yaml-ifc mapping. The result maps each wall id that has a
    body to a polygon ``[[x, y], ...]`` in the storey's plan coordinates, the
    same frame as ``Axis``. The ring is not closed. Joined walls are the
    butt-joint profiles IfcOpenShell builds; other walls are their untrimmed
    rectangles. A wall with no body is left out.
    """
    from yaml_ifc.to_ifc import build_ifc

    model = build_ifc(doc)
    storey = _storey_matrix(model)
    found = {}
    for wall in model.by_type("IfcWall"):
        solid = _body_item(wall)
        if solid is None:
            continue
        loops = _profile_loops(solid.SweptArea)
        if not loops:
            continue
        placement = (
            ifcopenshell.util.placement.get_axis2placement(solid.Position)
            if solid.Position
            else np.eye(4)
        )
        wall_matrix = ifcopenshell.util.placement.get_local_placement(wall.ObjectPlacement)
        rings = []
        for loop in loops:
            ring = []
            for point in _clean(loop):
                local = _apply(placement, (point[0], point[1], 0.0))
                world = _apply(wall_matrix, local[:3])
                plan = _apply(storey, world[:3])
                ring.append([num(float(plan[0])), num(float(plan[1]))])
            ring = _clean(ring)
            if len(ring) >= 3:
                rings.append([[point[0], point[1]] for point in ring])
        if not rings:
            continue
        polygon = rings[0]
        if len(rings) > 1:
            polygon = _union(rings)
        yaml_id = _yaml_id(wall)
        if yaml_id and polygon:
            found[yaml_id] = polygon
    return found


def _union(rings):
    import shapely.geometry
    import shapely.ops

    polygons = [shapely.geometry.Polygon(ring) for ring in rings if len(ring) >= 3]
    merged = shapely.ops.unary_union(polygons)
    if merged.geom_type == "Polygon":
        coords = list(merged.exterior.coords)
    elif merged.geom_type == "MultiPolygon":
        largest = max(merged.geoms, key=lambda item: item.area)
        coords = list(largest.exterior.coords)
    else:
        return rings[0]
    return [[num(point[0]), num(point[1])] for point in _clean(coords)]
