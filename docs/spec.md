# yaml-ifc

A YAML file for one house, edited as text. The names match IFC, so a later converter to a real IFC file can be mechanical. This version covers walls and the openings in them.

## IFC version

**IFC4 ADD2 TC1** (ISO 16739-1:2018). It is the building release. IFC4.3 is the infrastructure release and does not change the wall, opening, door, or window entities this subset uses. `IfcWallStandardCase` is deprecated in IFC4, so every wall is `IfcWall`.

## Supported subset

Spatial container, the minimum IFC asks for:

- `IfcProject`, `IfcSite`, `IfcBuilding`, `IfcBuildingStorey`
- `IfcRelAggregates` along that chain
- `IfcRelContainedInSpatialStructure` from the storey to each wall, door, and window

Elements and the two relationships between them:

- `IfcWall`
- `IfcOpeningElement`, joined to its wall by `IfcRelVoidsElement`
- `IfcDoor` and `IfcWindow`, joined to an opening by `IfcRelFillsElement`

Units are metres, declared once in the header.

## Deferred

Not in this version, and not started: `IfcSpace` and other rooms, slabs, ceilings, coverings, roofs, stairs, ramps, furniture, columns, beams, MEP, openings in anything other than a wall, more than one storey, sites with a map conversion, DWG import, and viewers.

## File shape

Top-level keys, in this order: `schema`, `units`, `project`, `site`, `building`, `storey`, `walls`, `openings`, `doors`, `windows`. One entity per list item. No YAML anchors or aliases. Comments are for people; a converter ignores them.

```yaml
schema: IFC4 ADD2 TC1
units:
  LengthUnit: METRE
```

`LengthUnit: METRE` is an `IfcSIUnit` of type `LENGTHUNIT`. A converter also emits the derived square-metre and cubic-metre units an IFC project needs.

Every entity has a stable `id`, unique in the file. `Name` is optional; the exported `IfcRoot.Name` is `Name` when set, otherwise `id`. `GlobalId` is optional. When it is absent, derive a UUID5 in the URL namespace from the name `yaml-ifc:` plus the `id`, then compress it with the 22-character IFC encoding (`ifcopenshell.guid.compress`). The same `id` always yields the same `GlobalId`.

List order in a hand-written file is the author's. A canonical writer sorts each list by `id`, then writes keys in the order below, so a round trip comes back identical.

With one storey, every `IfcWall`, `IfcDoor`, and `IfcWindow` is contained in that storey. Openings are not contained in the storey; they void a wall. A second storey would need an explicit `ContainedInStructure` on each element. That field is deferred with multi-storey files.

A value the source does not contain is left out. It is not filled with a guess. Derived values that the file does store (`SillHeight` when head and height are both known, `GlobalId`, the `Name` fallback) are listed below.

## Spatial container

```yaml
project:
  id: PRJ
  Name: "RD Šíma"
  Aggregates: [SITE]
site:
  id: SITE
  Name: "Bor u Tachova"
  RefElevation: 472.1
  Aggregates: [BLD]
building:
  id: BLD
  Name: "RD Šíma"
  Aggregates: [STOREY-1NP]
storey:
  id: STOREY-1NP
  Name: "1.NP"
  Elevation: 0
```

| YAML | IFC |
| --- | --- |
| `project` / `site` / `building` / `storey` | `IfcProject`, `IfcSite`, `IfcBuilding`, `IfcBuildingStorey` |
| `id`, `Name` | `IfcRoot.GlobalId` (derived if needed), `IfcRoot.Name` |
| `Aggregates` | `IfcRelAggregates`: `RelatingObject` is the parent, `RelatedObjects` are the children |
| `site.RefElevation` | `IfcSite.RefElevation`, metres above the map datum |
| `storey.Elevation` | `IfcBuildingStorey.Elevation`, metres above the project origin |

Plan coordinates are metres in the storey's XY. Z is up. A wall's base is `Elevation` when that field is set, otherwise the storey's `Elevation`.

## IfcWall

The list key `walls` selects `IfcWall`.

Required: `id`, and an `Axis` with `Start` and `End` (two plan points, metres). The axis runs from the end with the smaller X, or, when X is equal, the smaller Y, toward increasing coordinates. The reference line is the centre of the wall.

Present when known, and omitted otherwise:

- `Thickness` — full width, centred on the axis (faces at ±`Thickness`/2 in local Y)
- `Height` — extrusion length upward
- `Elevation` — base Z relative to the storey; omitted means the storey elevation
- `Name`, `GlobalId`, `PredefinedType`, `Tag`, `Description`

A wall with an axis and no `Thickness` or no `Height` has no solid body yet. The plan line is still stored.

```yaml
- id: W-south
  Axis:
    Start: [0.0, 0.0]
    End: [6.0, 0.0]
  Thickness: 0.3
  Height: 2.75
```

`Height` is what a finished wall carries. The ground-floor sample leaves `Height` off every wall, because the drawing's clear height belongs to a room and rooms are deferred.

Local placement: origin at `Axis.Start` and at the base Z; local X along the axis; local Y across the thickness; local Z up. The axis representation is a polyline from `(0, 0)` to `(length, 0)`. The body, when `Thickness` and `Height` are both present, is a rectangle `Thickness` wide and `length` long, centred on local Y, extruded by `Height`.

## IfcOpeningElement

The list key `openings` selects `IfcOpeningElement`. The opening voids exactly one wall.

Required: `id`, `VoidsElement` (the wall `id`), `AlongAxis`, `Width`.

- `AlongAxis` — metres from `Axis.Start` to the near end of the void (the end closer to the start).
- `Width` — void length along the wall. It is the hole in the wall. A door or window leaf may be smaller; that size lives on the filler.
- `Height` — void height, when known.
- `SillHeight` — Z of the bottom of the void above the wall base. When the source gives both a head and a height and no separate sill, store `SillHeight` as head minus height.
- `HeadHeight` — Z of the top, only when `Height` and `SillHeight` are not both known, so the known top is not dropped.
- `Depth` — cut depth across the wall. Omitted means the host `Thickness`, centred. A host with no `Thickness` needs `Depth` before a solid void can be cut.
- `Tag` — `IfcElement.Tag`, used for a drawing mark such as `O3` or `D5`.
- `PredefinedType` — `OPENING` or `RECESS`. Omitted means `OPENING` (a void through the wall).

`Width`, `Height`, `AlongAxis`, and `SillHeight` are placement and body geometry. `IfcOpeningElement` has no `OverallWidth` attribute.

```yaml
- id: OP03
  VoidsElement: W-018
  AlongAxis: 0.9
  Width: 1.9
  Height: 2.1
  SillHeight: 0
```

The void's placement is relative to the wall: local X is `AlongAxis`, local Y is `0`, local Z is `SillHeight`. The body is `Width` by `Depth` by `Height`. `AlongAxis` + `Width` lies inside the host axis, so the void is not wider than the wall.

`IfcRelVoidsElement`: `RelatingBuildingElement` is the wall, `RelatedOpeningElement` is the opening.

## IfcDoor and IfcWindow

The list key selects the entity. A door or window fills exactly one opening. A plain opening has no entry here.

Required: `id`, `FillsOpening`. `OverallWidth` and `OverallHeight` are the IFC attributes of that name, stored when known.

```yaml
- id: D-OP03
  FillsOpening: OP03
  OverallWidth: 1.8
  OverallHeight: 2.1
- id: WIN-OP01
  FillsOpening: OP01
  OverallWidth: 2.4
  OverallHeight: 2.5
  Tag: O3
```

`IfcRelFillsElement`: `RelatingOpeningElement` is the opening, `RelatedBuildingElement` is the door or window. The filler is contained in the storey; the opening is not.

Optional on a door: `PredefinedType` (`DOOR`, `GATE`, `TRAPDOOR`, …), `OperationType`. Optional on a window: `PredefinedType` (`WINDOW`, `SKYLIGHT`, …), `PartitioningType`. Omitted when the drawing does not say.

## Optional extensions

Absent unless a file adds them.

**Predefined type.** `PredefinedType` on a wall is the `IfcWallTypeEnum` value (`SOLIDWALL`, `STANDARD`, `PARTITIONING`, …).

**Material layers.** A centred layer set. `OffsetFromReferenceLine` defaults to minus half the sum of `LayerThickness`, which is the same centreing as `Thickness`.

```yaml
MaterialLayers:
  Layers:
    - Name: masonry
      LayerThickness: 0.3
      Material: brick
    - Name: insulation
      LayerThickness: 0.16
      Material: mineral-wool
```

This is `IfcMaterialLayerSetUsage`: `LayerSetDirection` `AXIS2`, `DirectionSense` `POSITIVE`, `OffsetFromReferenceLine` as above. Each layer is an `IfcMaterialLayer` (`Material`, `LayerThickness`, and optional `Name`, `Category`, `Priority`, `IsVentilated`).

**Property sets.** Standard names when they apply: `Pset_WallCommon`, `Pset_DoorCommon`, `Pset_WindowCommon`. Any other name is a custom set.

```yaml
PropertySets:
  - Name: Pset_WallCommon
    Properties:
      LoadBearing: true
      IsExternal: true
```

Each property is an `IfcPropertySingleValue`: the key is `Name`, the YAML value is `NominalValue`.

**Other geometry.** `Footprint` is a closed plan polygon in storey coordinates and replaces `Axis` plus `Thickness` as the plan shape (`IfcArbitraryClosedProfileDef`, extruded by `Height`). `Profile` is an explicit profile in the wall's local XY, used instead of the rectangle from `Thickness`.

```yaml
- id: W-foot
  Footprint:
    - [0, 0]
    - [4.2, 0]
    - [4.2, 0.3]
    - [0, 0.3]
  Height: 2.75
```

## Mapping

| YAML | IFC |
| --- | --- |
| `walls[]` | `IfcWall` |
| `Axis` | Axis representation, `IfcPolyline`. Placement origin at `Start`, X toward `End` |
| `Thickness` | Body profile width, centred on the axis (local Y) |
| `Height` | Body extrusion depth (local Z) |
| `Elevation` | Placement Z relative to the storey |
| `openings[]` | `IfcOpeningElement` |
| `VoidsElement` | `IfcRelVoidsElement.RelatingBuildingElement` |
| `AlongAxis`, `SillHeight` | Opening placement, relative to the wall |
| `Width`, `Height`, `Depth` | Opening body. `Depth` defaults to the host `Thickness` |
| `doors[]`, `windows[]` | `IfcDoor`, `IfcWindow` |
| `FillsOpening` | `IfcRelFillsElement.RelatingOpeningElement` |
| `OverallWidth`, `OverallHeight` | The same attributes on `IfcDoor` / `IfcWindow` |
| `Tag` | `IfcElement.Tag` |
| `PredefinedType` | `PredefinedType` on that entity |
| `MaterialLayers` | `IfcMaterialLayerSetUsage` + `IfcMaterialLayer` |
| `PropertySets` | `IfcPropertySet` + `IfcPropertySingleValue` |
| `Footprint` / `Profile` | Body profile, `IfcArbitraryClosedProfileDef` |
| storey containment | One `IfcRelContainedInSpatialStructure` on the storey, related elements = every wall, door, and window |

## Ground floor sample

`samples/ground-floor.yaml` is this schema applied to one real plan. Provenance is in `samples/source/`. Wall ids `W-001` upward are assigned by sorting horizontal axes by Y then X, then vertical axes by X then Y. Opening ids are the source ids (`OP03`, `OP39a`, …).

## Open questions

1. **Default wall geometry.** The stored form is a centreline plus `Thickness`, centred. The sample measures both from the double-line drawing. A footprint polygon would match the drawn edges more directly and would make the centreline a derived view. Which one should be the required core?
2. **One wall through its openings.** Pieces of the same axis are one `IfcWall`, and the axis runs through the voids. The alternative is one wall object per solid stretch between openings.
3. **How far a "same axis" gap can be and still be one wall.** The sample joins collinear pieces when the gap is at most 0.36 m (a reveal the faces did not span) or when one or more openings cover the gap. That threshold is a judgment.
4. **Void width versus leaf size.** `Width` on the opening is the measured hole. `OverallWidth` on the door can be smaller (the written leaf size). Confirm both should be kept.
5. **`AlongAxis` is the start of the void**, the end nearer `Axis.Start`, rather than the centre.
6. **Missing `Height` and missing `Thickness`.** The sample omits `Height` on every wall, and omits `Thickness` on the one wall whose opposite face is not drawn (`W-017`, host of `OP19`). Is a file in that state valid, or only a draft a validator should reject?
7. **`HeadHeight`.** `OP27` and `OP29` know the head and not the sill or the height. Is a head-only field the right extension, or should those two stay as comments until the sill is known?
8. **Glazed run `W-023`.** Thickness 0.10 m is the depth of the two posts; the long faces are not drawn. Worth a separate look.
9. **No host, no opening.** The hall-to-garage passage has no wall across it, so it is not an `IfcOpeningElement`. Confirm that is the right reading of `IfcRelVoidsElement`.
10. **120 mm squares** on the wall layer are short `IfcWall`s. `IfcColumn` is deferred; they may want to move later.
11. **Implicit storey containment** while there is only one storey. Confirm, or put `ContainedInStructure` on every element now.
12. **Corner joints** are not mitred. An axis ends where its two faces stop overlapping, then continues through openings. A later pass could extend axes to a joint.
