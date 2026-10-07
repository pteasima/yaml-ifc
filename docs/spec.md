# yaml-ifc

A YAML file for one house, edited as text. The names match IFC, so a later converter to a real IFC file can be mechanical. This version covers walls, the openings in them, whole furnishing elements (kitchen modules, appliances, and loose furniture), and the electrical installation outside the panels.

## IFC version

**IFC4 ADD2 TC1** (ISO 16739-1:2018). It is the building release. IFC4.3 is the infrastructure release and does not change the wall, opening, door, or window entities this subset uses. `IfcWallStandardCase` is deprecated in IFC4, so every wall is `IfcWall`.

## Supported subset

Spatial container, the minimum IFC asks for:

- `IfcProject`, `IfcSite`, `IfcBuilding`, `IfcBuildingStorey`
- `IfcRelAggregates` along that chain
- `IfcRelContainedInSpatialStructure` from the storey to each wall, door, and window, and to each furnishing or electrical element that names no room
- `IfcSpace`, aggregated under the storey, and `IfcRelContainedInSpatialStructure` from a space to the furnishings in that room

Elements and the relationships between them:

- `IfcWall`
- `IfcOpeningElement`, joined to its wall by `IfcRelVoidsElement`
- `IfcDoor` and `IfcWindow`, joined to an opening by `IfcRelFillsElement`
- `IfcFurniture`, `IfcSystemFurnitureElement`, `IfcSanitaryTerminal`, `IfcElectricAppliance`, `IfcLightFixture`, `IfcCovering`
- `IfcSwitchingDevice`, `IfcSensor`, `IfcOutlet`, `IfcActuator`, `IfcElectricDistributionBoard`, `IfcCableSegment`
- `IfcDistributionPort`, nested by `IfcRelNests` and joined by `IfcRelConnectsPorts`
- `IfcDistributionCircuit`, with members assigned by `IfcRelAssignsToGroup`
- The matching type object (`IfcFurnitureType`, and the others), one per catalogue entry, joined by `IfcRelDefinesByType`

Units are metres, declared once in the header.

## Deferred

Not in this version, and not started: slabs, roofs, stairs, ramps, columns, beams, pipes, ducts, cable carriers, the devices inside a distribution board, openings in anything other than a wall, more than one storey, sites with a map conversion, DWG import, and viewers. A space has no body. Coverings other than a placed box (a floor build-up, a ceiling, cladding) are not modeled. Furniture parts — hinges, fronts, drawers, the L of a sectional — are not entities. `IfcFurnishingElement` itself, when it is neither `IfcFurniture` nor `IfcSystemFurnitureElement`, is not stored. A light source for rendering (`IfcLightSource` and its subtypes) is not stored: the goniometric source can hold one colour temperature, and only together with a colour, a flux, an emission source, and a distribution that this file does not have.

## File shape

Top-level keys, in this order: `schema`, `units`, `project`, `site`, `building`, `storey`, `spaces`, `walls`, `connections`, `openings`, `doors`, `windows`, `furniture`, `systemFurniture`, `sanitaryTerminals`, `electricAppliances`, `lightFixtures`, `coverings`, `switchingDevices`, `sensors`, `outlets`, `actuators`, `distributionBoards`, `cables`, `circuits`. `walls`, `openings`, `doors`, and `windows` are present even when empty. `connections`, `spaces`, the furnishing lists, and the electrical lists are omitted when the file has none. One entity per list item. No YAML anchors or aliases. Comments are for people; a converter ignores them.

```yaml
schema: IFC4 ADD2 TC1
units:
  LengthUnit: METRE
```

`LengthUnit: METRE` is an `IfcSIUnit` of type `LENGTHUNIT`. A converter also emits the derived square-metre and cubic-metre units an IFC project needs.

Every entity has a stable `id`, unique in the file. `Name` is optional; the exported `IfcRoot.Name` is `Name` when set, otherwise `id`. `GlobalId` is optional. When it is absent, derive a UUID5 in the URL namespace from the name `yaml-ifc:` plus the `id`, then compress it with the 22-character IFC encoding (`ifcopenshell.guid.compress`). The same `id` always yields the same `GlobalId`.

List order in a hand-written file is the author's. A canonical writer sorts each list by `id`, then writes keys in the order below, so a round trip comes back identical.

With one storey, every `IfcWall`, `IfcDoor`, and `IfcWindow` is contained in that storey. Openings are not contained in the storey; they void a wall. A furnishing or electrical element, including a cable and a distribution board, is contained in the space named by `ContainedInStructure`, or in the storey when that field is omitted. A port is nested in its element and is not contained in the storey. A circuit is a group, not a contained element. A second storey would need the same field on walls, doors, and windows. Multi-storey files are still deferred.

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

Plan coordinates are metres in the storey's XY. Z is up. A wall's base is `Elevation` when that field is set, otherwise the storey's `Elevation`. A space is placed at the storey origin, so a furnishing's coordinates are storey coordinates whether or not it names a room.

## IfcSpace

The list key `spaces` selects `IfcSpace`. A space is a room that furnishings can belong to. It has no body in this version: no footprint and no height. Every space is aggregated under the one storey.

Required: `id`.

Present when known, and omitted otherwise: `Name`, `GlobalId`, `Description`, `ObjectType`, `LongName`, `PredefinedType`, `ElevationWithFlooring`, `PropertySets`.

`PredefinedType` is `IfcSpaceTypeEnum`: `SPACE`, `PARKING`, `GFA`, `INTERNAL`, `EXTERNAL`, `USERDEFINED`, `NOTDEFINED`. `USERDEFINED` requires `ObjectType`. `INTERNAL` is a room inside the building.

```yaml
- id: SPACE-kitchen
  Name: Kitchen
  PredefinedType: INTERNAL
```

`CompositionType` is written `ELEMENT` and dropped on import, the same way it is for the site, building, and storey. `ElevationWithFlooring` is the IFC attribute, in metres. It is not a placement.

## IfcWall

The list key `walls` selects `IfcWall`.

Required: `id`, and an `Axis` with `Start` and `End` (two plan points, metres). The axis runs from the end with the smaller X, or, when X is equal, the smaller Y, toward increasing coordinates. A wall parallel to the Y axis has the same X at both ends, so that tie-break is what places its start at the smaller Y. The reference line is the centre of the wall.

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

Required: `id`. `FillsOpening` is required when the door or window fills an opening, and omitted when it does not. `OverallWidth` and `OverallHeight` are the IFC attributes of that name, stored when known.

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

## Connections

The optional list `connections` is wall-to-wall joints. Each entry is an `IfcRelConnectsPathElements`. The names are the IFC attributes. There is no join-style field: every joint is a butt joint, and the relating wall runs through.

```yaml
connections:
  - RelatingElement: W-001
    RelatingConnectionType: ATEND
    RelatedElement: W-002
    RelatedConnectionType: ATSTART
```

| YAML | IFC |
| --- | --- |
| `RelatingElement` | `RelatingElement`, a wall `id` |
| `RelatingConnectionType` | `ATSTART`, `ATEND`, or `ATPATH` |
| `RelatedElement` | `RelatedElement`, a wall `id` |
| `RelatedConnectionType` | `ATSTART` or `ATEND` |

`ATSTART` is the axis end with the smaller X, or, when X is equal, the smaller Y. `ATEND` is the other end. A wall parallel to the Y axis has equal X, so `ATSTART` is its smaller Y and `ATEND` is its larger Y. `ATPATH` is a connection along the wall rather than at an end, and only the relating wall may use it. That is the wall the other one is joined into.

An L corner is two ends, as in the example above. A T puts `ATPATH` on the relating wall, the one that runs through, and `ATSTART` or `ATEND` on the related wall. The related wall is trimmed back to the relating wall's face. The relating wall is not mitred and is not notched: its body continues through the joint.

Optional on a door: `PredefinedType` (`DOOR`, `GATE`, `TRAPDOOR`, …), `OperationType`. Optional on a window: `PredefinedType` (`WINDOW`, `SKYLIGHT`, …), `PartitioningType`. Omitted when the drawing does not say.

## Furnishings

A furnishing entry is one whole element: placement, a box, a name, and a catalogue string. Hinges, fronts, drawers, and the generated shape of a type stay out of the file. The list key selects the IFC class.

| YAML key | IFC |
| --- | --- |
| `furniture` | `IfcFurniture` |
| `systemFurniture` | `IfcSystemFurnitureElement` |
| `sanitaryTerminals` | `IfcSanitaryTerminal` |
| `electricAppliances` | `IfcElectricAppliance` |
| `lightFixtures` | `IfcLightFixture` |
| `coverings` | `IfcCovering` |

Required: `id`.

Present when known, and omitted otherwise:

- `Name`, `GlobalId`, `Description`, `Tag`
- `PredefinedType` — the enum of that class (the table below)
- `ObjectType` — the family name, for example `BaseCabinet`. Required when `PredefinedType` is `USERDEFINED`. Allowed beside any other predefined type, where the enum is the class and the name is the product. A family name carries no size: a 600 mm base cabinet and an 800 mm base cabinet are both `BaseCabinet`. `Width`, `Depth`, and `Height` are the only dimensions
- `ContainedInStructure` — a space `id`. Omitted means the storey
- `Origin` — `[x, y]` in the storey plan, the corner of the box. Omitted means `[0, 0]`
- `Elevation` — base Z above the storey. Omitted means `0`
- `RefDirection` — plan direction of local X, the width axis. Omitted means `[1, 0]`
- `Width`, `Depth`, `Height` — the box, in metres. Local X is the width, local Y the depth, local Z the height. The placement origin is the minimum corner. A solid is written only when all three are present. A partial size is kept and has no solid
- `PropertySets`

A written zero is kept. The omitted defaults above are not written back.

`PredefinedType` values, by class:

| Class | `PredefinedType` |
| --- | --- |
| `IfcFurniture` | `CHAIR`, `TABLE`, `DESK`, `BED`, `FILECABINET`, `SHELF`, `SOFA`, `USERDEFINED`, `NOTDEFINED` |
| `IfcSystemFurnitureElement` | `PANEL`, `WORKSURFACE`, `USERDEFINED`, `NOTDEFINED` |
| `IfcSanitaryTerminal` | `BATH`, `BIDET`, `CISTERN`, `SHOWER`, `SINK`, `SANITARYFOUNTAIN`, `TOILETPAN`, `URINAL`, `WASHHANDBASIN`, `WCSEAT`, `USERDEFINED`, `NOTDEFINED` |
| `IfcElectricAppliance` | `DISHWASHER`, `ELECTRICCOOKER`, `FREESTANDINGELECTRICHEATER`, `FREESTANDINGFAN`, `FREESTANDINGWATERHEATER`, `FREESTANDINGWATERCOOLER`, `FREEZER`, `FRIDGE_FREEZER`, `HANDDRYER`, `KITCHENMACHINE`, `MICROWAVE`, `PHOTOCOPIER`, `REFRIGERATOR`, `TUMBLEDRYER`, `VENDINGMACHINE`, `WASHINGMACHINE`, `USERDEFINED`, `NOTDEFINED` |
| `IfcLightFixture` | `POINTSOURCE`, `DIRECTIONSOURCE`, `SECURITYLIGHTING`, `USERDEFINED`, `NOTDEFINED` |
| `IfcCovering` | `CEILING`, `FLOORING`, `CLADDING`, `ROOFING`, `MOLDING`, `SKIRTINGBOARD`, `INSULATION`, `MEMBRANE`, `SLEEVING`, `WRAPPING`, `USERDEFINED`, `NOTDEFINED` |

Kitchen modules are `IfcSystemFurnitureElement`. The enum has no cabinet value, so a cabinet is `USERDEFINED` and the module name is `ObjectType`. `PANEL` and `WORKSURFACE` are the two values the enum does name. A loose chair, table, shelf, or sofa is `IfcFurniture` with the matching predefined type. A product the enum does not name (`Sideboard`, `TvUnit`, a rug, an oven, a hood) is `USERDEFINED` plus `ObjectType`.

The box is not an IFC attribute. `OverallWidth` belongs to doors and windows, not to these classes. Standard property sets can carry a nominal size (`Pset_FurnitureTypeCommon` has `NominalLength`, `NominalDepth`, `NominalHeight`; the system-furniture set has no depth; appliances have none). Those sets are not filled in by the converter. An author can still add `PropertySets`. The box is the size every class can share.

```yaml
- id: CAB-base
  Name: Base cabinet
  PredefinedType: USERDEFINED
  ObjectType: BaseCabinet
  ContainedInStructure: SPACE-kitchen
  Origin: [0, 0]
  Width: 0.6
  Depth: 0.6
  Height: 0.9
- id: SOFA
  Name: Sectional sofa
  PredefinedType: SOFA
  ObjectType: SectionalSofa
  ContainedInStructure: SPACE-living
  Origin: [5.2, 1.2]
  Width: 2.6
  Depth: 1.6
  Height: 0.85
```

Occurrences that share a class, a `PredefinedType`, and an `ObjectType` share one type object (`IfcFurnitureType`, `IfcSystemFurnitureElementType`, `IfcSanitaryTerminalType`, `IfcElectricApplianceType`, `IfcLightFixtureType`, or `IfcCoveringType`), linked by `IfcRelDefinesByType`. The type's `Name` is `ObjectType` when that is set, otherwise `PredefinedType`. Its `ElementType` is `ObjectType`. Its `PredefinedType` matches the occurrence. The type is not a YAML entry. It is rebuilt from the occurrences. `IfcFurnitureType.AssemblyPlace` is required by the schema and is written `NOTDEFINED`; that filler is not a measured value and is not written back. A sanitary terminal, appliance, light, or covering with no `PredefinedType` has no type object, because those type entities require one.

`samples/furnishings.yaml` is one of each piece below, plus a second dining chair so the shared type is visible. The sizes are nominal module dimensions, not a measured plan. `samples/ground-floor.yaml` is not furnished.

These names are the ones the example uses. They are not a closed list. Each one is a family, with no width, depth, or height written into it. The converter stores the string as written and does not parse it, so a digit in the name would be kept, and it would still be the wrong place for a size.

| Piece | IFC | `PredefinedType` | `ObjectType` |
| --- | --- | --- | --- |
| Base cabinet | `IfcSystemFurnitureElement` | `USERDEFINED` | `BaseCabinet` |
| Wall cabinet | `IfcSystemFurnitureElement` | `USERDEFINED` | `WallCabinet` |
| Tall cabinet | `IfcSystemFurnitureElement` | `USERDEFINED` | `TallCabinet` |
| Island | `IfcSystemFurnitureElement` | `USERDEFINED` | `Island` |
| Cooktop | `IfcElectricAppliance` | `ELECTRICCOOKER` | `Cooktop` |
| Sink | `IfcSanitaryTerminal` | `SINK` | `KitchenSink` |
| Built-in fridge | `IfcElectricAppliance` | `REFRIGERATOR` | `BuiltInFridge` |
| Built-in oven | `IfcElectricAppliance` | `USERDEFINED` | `BuiltInOven` |
| Ceiling hood | `IfcElectricAppliance` | `USERDEFINED` | `CeilingHood` |
| Dining table | `IfcFurniture` | `TABLE` | `DiningTable` |
| Dining chair | `IfcFurniture` | `CHAIR` | `DiningChair` |
| Sectional sofa | `IfcFurniture` | `SOFA` | `SectionalSofa` |
| Side table | `IfcFurniture` | `TABLE` | `SideTable` |
| Rug | `IfcCovering` | `USERDEFINED` | `Rug` |
| Wall shelf | `IfcFurniture` | `SHELF` | `WallShelf` |
| Sideboard | `IfcFurniture` | `USERDEFINED` | `Sideboard` |
| TV unit | `IfcFurniture` | `USERDEFINED` | `TvUnit` |
| Hanging plant shelf | `IfcFurniture` | `SHELF` | `HangingPlantShelf` |
| Track light | `IfcLightFixture` | `DIRECTIONSOURCE` | `TrackLight` |

Wattage and the tunable CCT range are electrical properties of a light. They are specified in the next section. The furnishing example leaves them out.

A run of cabinets is one element per module, not one element for the run. A stack of ovens is one `BuiltInOven` per oven. The island is one system-furniture element; the cooktop and the sink are separate products sitting in its volume, not voids cut out of it. The sectional's L, and every front and handle, is generated later from `ObjectType`. The box is the extent.

## Electrical

The electrical installation outside the panels. A device is one whole element: the same placement and box as a furnishing. The inside of a distribution board — breakers, busbars, terminals — is not modeled. IFC is the only store. A value the schema can already carry uses that entity, predefined type, or property set. Anything it cannot carry goes in one project set, `Pset_YamlIfc`. That set is project data. It is not the converter's `yaml-ifc` bookkeeping set, and it is not a second inventory beside the file.

The list key selects the class. `lightFixtures` is the same list as in furnishings.

| YAML key | IFC |
| --- | --- |
| `lightFixtures` | `IfcLightFixture` |
| `switchingDevices` | `IfcSwitchingDevice` |
| `sensors` | `IfcSensor` |
| `outlets` | `IfcOutlet` |
| `actuators` | `IfcActuator` |
| `distributionBoards` | `IfcElectricDistributionBoard` |
| `cables` | `IfcCableSegment` |
| `circuits` | `IfcDistributionCircuit` |

Placed elements (everything except circuits) use the furnishing fields: `id`, `Name`, `GlobalId`, `Description`, `Tag`, `PredefinedType`, `ObjectType`, `ContainedInStructure`, `Origin`, `Elevation`, `RefDirection`, `Width`, `Depth`, `Height`, `PropertySets`. `ObjectType` is a family name and carries no size. Occurrences that share a class, a `PredefinedType`, and an `ObjectType` share one type object, by the same rule as furnishings. Each of these type entities requires a `PredefinedType`, so an occurrence that names none has no type object.

`PredefinedType` values, by class. These are the IFC4 ADD2 TC1 enums.

| Class | `PredefinedType` |
| --- | --- |
| `IfcSwitchingDevice` | `CONTACTOR`, `DIMMERSWITCH`, `EMERGENCYSTOP`, `KEYPAD`, `MOMENTARYSWITCH`, `SELECTORSWITCH`, `STARTER`, `SWITCHDISCONNECTOR`, `TOGGLESWITCH`, `USERDEFINED`, `NOTDEFINED` |
| `IfcSensor` | `COSENSOR`, `CO2SENSOR`, `CONDUCTANCESENSOR`, `CONTACTSENSOR`, `FIRESENSOR`, `FLOWSENSOR`, `FROSTSENSOR`, `GASSENSOR`, `HEATSENSOR`, `HUMIDITYSENSOR`, `IDENTIFIERSENSOR`, `IONCONCENTRATIONSENSOR`, `LEVELSENSOR`, `LIGHTSENSOR`, `MOISTURESENSOR`, `MOVEMENTSENSOR`, `PHSENSOR`, `PRESSURESENSOR`, `RADIATIONSENSOR`, `RADIOACTIVITYSENSOR`, `SMOKESENSOR`, `SOUNDSENSOR`, `TEMPERATURESENSOR`, `WINDSENSOR`, `USERDEFINED`, `NOTDEFINED` |
| `IfcOutlet` | `AUDIOVISUALOUTLET`, `COMMUNICATIONSOUTLET`, `POWEROUTLET`, `DATAOUTLET`, `TELEPHONEOUTLET`, `USERDEFINED`, `NOTDEFINED` |
| `IfcActuator` | `ELECTRICACTUATOR`, `HANDOPERATEDACTUATOR`, `HYDRAULICACTUATOR`, `PNEUMATICACTUATOR`, `THERMOSTATICACTUATOR`, `USERDEFINED`, `NOTDEFINED` |
| `IfcElectricDistributionBoard` | `CONSUMERUNIT`, `DISTRIBUTIONBOARD`, `MOTORCONTROLCENTRE`, `SWITCHBOARD`, `USERDEFINED`, `NOTDEFINED` |
| `IfcCableSegment` | `BUSBARSEGMENT`, `CABLESEGMENT`, `CONDUCTORSEGMENT`, `CORESEGMENT`, `USERDEFINED`, `NOTDEFINED` |
| `IfcDistributionCircuit` | `IfcDistributionSystemEnum`, including `ELECTRICAL`, `LIGHTING`, `CONTROL`, `EARTHING`, `USERDEFINED`, `NOTDEFINED` |

A wall button is an `IfcSwitchingDevice`. IFC4 has no `PUSHBUTTON` predefined type (and IFC4.3 does not add one either). A momentary push button is `MOMENTARYSWITCH` and the family name is `ObjectType`, for example `PushButton`. A maintained switch is `TOGGLESWITCH`. The standard set `Pset_SwitchingDeviceTypeToggleSwitch` does have a `ToggleSwitchType` value `PUSHBUTTON`, and it applies to a `TOGGLESWITCH`, so a latching push button can be written there by an author. The converter does not infer that from the family name.

A presence sensor is `IfcSensor` / `MOVEMENTSENSOR`. `Pset_SensorTypeMovementSensor.MovementSensingType` lists `PHOTOELECTRICCELL` and `PRESSUREPAD` only, so mmWave is not an enum value. The family name carries it (`MmWavePresence`). A door or window contact is `CONTACTSENSOR`, for example `DoorContact`.

An outlet is `IfcOutlet`. A mains socket is `POWEROUTLET`.

A blind actuator is `IfcActuator` / `ELECTRICACTUATOR`, not `IfcElectricMotor`. The product in the room is the actuator that drives the blind. `IfcElectricMotorTypeEnum` classifies a motor (`DC`, `INDUCTION`, and the rest) and has no blind value. `Pset_ActuatorTypeCommon.Application` already has `SUNBLINDACTUATOR`, and `Pset_ActuatorTypeElectricActuator.ElectricActuatorType` has `MOTORDRIVE`. Those are authored `PropertySets`. The converter does not parse `ObjectType` to fill them.

A panel is one `IfcElectricDistributionBoard`. `DISTRIBUTIONBOARD` is the ordinary household board. Nothing is nested inside it except the ports of the cables that leave it.

### Light output

On a light fixture only:

- `Wattage` — watts, written as `Pset_LightFixtureTypeCommon.TotalWattage`, an `IfcPowerMeasure`. The project gains an `IfcSIUnit` `POWERUNIT` / `WATT` when any such measure is written. The property sits on the occurrence, so two fixtures of one family can differ. Type property sets are dropped on import, so the wattage is not stored on the type.
- `CctMin`, `CctMax` — the tunable correlated colour temperature, in kelvin. Written as `Pset_YamlIfc.CctMin` and `Pset_YamlIfc.CctMax`, each an `IfcThermodynamicTemperatureMeasure`. The project gains `THERMODYNAMICTEMPERATUREUNIT` / `KELVIN` when either bound is written. Either bound may be omitted. When both are present, `CctMin` is not above `CctMax`.

Standard IFC has single colour temperatures and no range. `IfcLightSourceGoniometric.ColourTemperature` is one kelvin value, and that entity also requires a colour, a position, a luminous flux, an emission source, and a distribution data source. `Pset_LampTypeCommon.ColorTemperature` is also one value, and its applicable entity is `IfcLamp`, which IFC4 does not contain. Neither is written. A guessed midpoint of the range would come back as if it had been measured.

`Wattage` and the two bounds are not also repeated inside `PropertySets`. Putting `TotalWattage` on `Pset_LightFixtureTypeCommon`, or `CctMin` / `CctMax` on `Pset_YamlIfc`, in addition to the field is rejected. Other properties in those sets are kept. An authored property whose name is `TotalWattage`, `ActuatorInputPower`, `CctMin`, or `CctMax` is written as the measure type above rather than a bare real.

### Cables and ports

`connections` is already the wall-joint list, so a cable is not a connection. Each cable is an `IfcCableSegment` with `From` and `To`, the ids of the elements it joins. Both are required. An endpoint has to be a distribution element already in the file: a light, a switch, a sensor, an outlet, an actuator, a board, an appliance, a sanitary terminal, or another cable. A wall or a chair is not.

Ports are not written in the YAML. For each cable the converter nests four `IfcDistributionPort` entities with `IfcRelNests` and joins them with `IfcRelConnectsPorts`:

| Port | `FlowDirection` | Nested in |
| --- | --- | --- |
| upstream | `SOURCE` | `From` |
| cable inlet | `SINK` | the cable |
| cable outlet | `SOURCE` | the cable |
| downstream | `SINK` | `To` |

`PredefinedType` on every port is `CABLE`. `SystemType` is the `PredefinedType` of the circuits that list the cable, when those types agree, or `ELECTRICAL` when the cable is on none or the types disagree. That system type is derived. It is not a YAML field. `RealizingElement` is left unset: the cable is already in the chain through its own ports. One `IfcRelNests` per element holds all of that element's ports. `IfcRelConnectsPortToElement` is the older port link and is not used.

The segment's own inlet is named `{id}:sink` and its own outlet `{id}:source`. A cable that is itself an end of some other cable also carries that other cable's port, and the name is what keeps the two apart. Import rebuilds `From` and `To` from those two named ports. A cable with exactly one unlabelled sink and one unlabelled source uses those instead.

### Circuits

A circuit is an `IfcDistributionCircuit`. Required: `id`. Present when known: `Name`, `GlobalId`, `Description`, `ObjectType`, `LongName`, `PredefinedType`, `PropertySets`, and `Assigns`.

`Assigns` is a list of element ids. The converter writes one `IfcRelAssignsToGroup` with `RelatedObjectsType` `PRODUCT`. The list is omitted when the circuit has no members, and an empty list is rejected. A board may appear on more than one circuit. Order in the list is the author's.

```yaml
- id: LIGHT-down
  Name: Downlight
  PredefinedType: POINTSOURCE
  ObjectType: Downlight
  ContainedInStructure: SPACE-room
  Origin: [1.2, 1.6]
  Elevation: 2.4
  Width: 0.12
  Depth: 0.12
  Height: 0.05
  Wattage: 12
  CctMin: 2700
  CctMax: 6500
- id: SW-bed
  Name: Bed button
  PredefinedType: MOMENTARYSWITCH
  ObjectType: PushButton
  ContainedInStructure: SPACE-room
  Origin: [2.4, 0.1]
  Elevation: 0.8
  Width: 0.08
  Depth: 0.01
  Height: 0.08
- id: CBL-light
  PredefinedType: CABLESEGMENT
  ObjectType: LightingCable
  From: DB-main
  To: LIGHT-down
- id: CIR-lights
  Name: Lights
  PredefinedType: LIGHTING
  Assigns: [DB-main, LIGHT-down, CBL-light]
```

`samples/electrical.yaml` is one board, a downlight, a toggle switch, a push button, an mmWave presence sensor, a door contact, a socket, a blind actuator, and the cables and circuits that join them. The sizes are nominal, not a survey.

These names are the ones the example uses. They are not a closed list. Each one is a family, with no width, depth, or height written into it.

| Piece | IFC | `PredefinedType` | `ObjectType` |
| --- | --- | --- | --- |
| Downlight | `IfcLightFixture` | `POINTSOURCE` | `Downlight` |
| Toggle switch | `IfcSwitchingDevice` | `TOGGLESWITCH` | `ToggleSwitch` |
| Push button | `IfcSwitchingDevice` | `MOMENTARYSWITCH` | `PushButton` |
| mmWave presence | `IfcSensor` | `MOVEMENTSENSOR` | `MmWavePresence` |
| Door contact | `IfcSensor` | `CONTACTSENSOR` | `DoorContact` |
| Socket | `IfcOutlet` | `POWEROUTLET` | `Socket` |
| Blind actuator | `IfcActuator` | `ELECTRICACTUATOR` | `BlindActuator` |
| Main board | `IfcElectricDistributionBoard` | `DISTRIBUTIONBOARD` | `MainBoard` |
| Lighting cable | `IfcCableSegment` | `CABLESEGMENT` | `LightingCable` |
| Power cable | `IfcCableSegment` | `CABLESEGMENT` | `PowerCable` |
| Signal cable | `IfcCableSegment` | `CABLESEGMENT` | `SignalCable` |

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
| `spaces[]` | `IfcSpace`, aggregated under the storey |
| `furniture[]` | `IfcFurniture` |
| `systemFurniture[]` | `IfcSystemFurnitureElement` |
| `sanitaryTerminals[]` | `IfcSanitaryTerminal` |
| `electricAppliances[]` | `IfcElectricAppliance` |
| `lightFixtures[]` | `IfcLightFixture` |
| `coverings[]` | `IfcCovering` |
| `switchingDevices[]` | `IfcSwitchingDevice` |
| `sensors[]` | `IfcSensor` |
| `outlets[]` | `IfcOutlet` |
| `actuators[]` | `IfcActuator` |
| `distributionBoards[]` | `IfcElectricDistributionBoard` |
| `cables[]` | `IfcCableSegment`. `From` and `To` are element ids |
| `circuits[]` | `IfcDistributionCircuit` |
| `Assigns` | `IfcRelAssignsToGroup.RelatedObjects` |
| `Wattage` | `Pset_LightFixtureTypeCommon.TotalWattage`, watts |
| `CctMin`, `CctMax` | `Pset_YamlIfc`, kelvin. IFC4 has no CCT range |
| cable ports | Derived `IfcDistributionPort`, `IfcRelNests`, `IfcRelConnectsPorts` |
| `ObjectType` | `IfcObject.ObjectType`, and `ElementType` on the derived type |
| `ContainedInStructure` | `IfcRelContainedInSpatialStructure.RelatingStructure`, a space |
| `Origin`, `RefDirection`, `Elevation` | Placement of the box corner. Local X is `RefDirection`, local Z is up |
| `Width`, `Depth`, `Height` | Box body. `Width` along local X, `Depth` along local Y, `Height` extruded up |
| `doors[]`, `windows[]` | `IfcDoor`, `IfcWindow` |
| `FillsOpening` | `IfcRelFillsElement.RelatingOpeningElement` |
| `OverallWidth`, `OverallHeight` | The same attributes on `IfcDoor` / `IfcWindow` |
| `Tag` | `IfcElement.Tag` |
| `PredefinedType` | `PredefinedType` on that entity |
| `MaterialLayers` | `IfcMaterialLayerSetUsage` + `IfcMaterialLayer` |
| `PropertySets` | `IfcPropertySet` + `IfcPropertySingleValue` |
| `Footprint` / `Profile` | Body profile, `IfcArbitraryClosedProfileDef` |
| `connections[]` | `IfcRelConnectsPathElements` |
| `RelatingElement`, `RelatedElement` | The two walls. The relating wall runs through the butt joint |
| `RelatingConnectionType`, `RelatedConnectionType` | `ATSTART`, `ATEND`, or, on the relating wall only, `ATPATH` |
| storey containment | One `IfcRelContainedInSpatialStructure` on the storey for every wall, door, window, furnishing, and electrical element that names no space |
| space containment | One `IfcRelContainedInSpatialStructure` per space that has furnishings |
| type object | One `IfcFurnitureType` (or the matching type class) per distinct class, `PredefinedType`, and `ObjectType`, via `IfcRelDefinesByType` |

## Samples

## Ground floor sample

`samples/ground-floor.yaml` is this schema applied to one real plan. Provenance is in `samples/source/`. Wall ids `W-001` upward are assigned by sorting horizontal axes by Y then X, then vertical axes by X then Y. Opening ids are the source ids (`OP03`, `OP39a`, …). It has no spaces and no furnishings.

`samples/furnishings.yaml` is the furnishing lists applied to one open kitchen, dining, and living room. The sizes are nominal module dimensions, not a survey of that room.

`samples/electrical.yaml` is one distribution board and the devices, cables, and circuits outside it. The sizes are nominal, not a survey, and the file is not a real house.

## Converter

`yaml_ifc` writes this file to IFC4 and reads IFC4 back. A few IFC rules have no YAML field. The converter fills those in, then drops them again on the way back, so a YAML file comes back with the same data:

- A wall with `Thickness`, `Footprint`, or `Profile` and no `Height` is extruded **3 m**. That height is not written back.
- An opening whose host has no `Thickness` and no `Depth`, but does have a `Height`, is cut **0.2 m** deep. That depth is not written back. `Depth` still defaults to the host `Thickness` when the host has one.
- `HeadHeight` is not an IFC attribute. It is kept in a property set named `yaml-ifc` and restored on import. `Height` and `SillHeight` are not invented for that opening, and it has no solid.
- The YAML `id` is stored on each `IfcObject` in that same `yaml-ifc` set (property `id`). `IfcProject` cannot own a property set, so its `id` is stored in `LongName`. The set is converter bookkeeping. It is not a YAML `PropertySets` entry. `Footprint` and `Profile` are marked there too, so a rectangular footprint is not read back as `Thickness`.
- A wall with `Thickness` and no `MaterialLayers`, `Footprint`, or `Profile` is given a one-layer `IfcMaterialLayerSet` / `IfcMaterialLayerSetUsage` of that thickness, centred (`OffsetFromReferenceLine` minus half the thickness). The layer is marked `MaterialFromThickness` in the `yaml-ifc` set and is not written back as `MaterialLayers`. A layer set that was actually in the file is. When a layer set is present and `Thickness` cannot be read from a centred rectangular profile, `Thickness` is the sum of the layer thicknesses.
- Each `connections` entry is an `IfcRelConnectsPathElements`. The relating wall's layers outrank the related wall's at that joint, which is what makes the butt: the relating wall runs through, and the related wall is trimmed to its face. The trimmed body is generated with IfcOpenShell (`regenerate_wall_representation`). Regeneration also rewrites the axis curve, so a joined wall keeps its authored `Axis` in the `yaml-ifc` set and import restores that, not the trimmed curve.
- `GlobalId`, when omitted, is the UUID5 in the URL namespace of `yaml-ifc:` plus the `id`, compressed to the 22-character IFC form. On import it is omitted again when it matches that derivation. For a connection, which has no `id`, the name is the four fields joined with colons.
- `IfcOpeningElement.PredefinedType`, when omitted, is written `OPENING` and omitted again on import.
- A space is an `IfcSpace` with `CompositionType` `ELEMENT` and a placement at the storey origin. Neither is written back. `ElevationWithFlooring` is an attribute and is written back, including zero. Spaces are aggregated under the storey. A space body is not stored.
- A furnishing with `Width`, `Depth`, and `Height` is a rectangular extrusion. The profile centre is half the width and half the depth, so the placement origin is the minimum corner. Local X follows `RefDirection`. One or two sizes, with the third missing, produce no solid.
- `Origin`, `Elevation`, `RefDirection`, `Width`, `Depth`, and `Height` are copied into the `yaml-ifc` set when the file has them, including zeros, and restored from that set on import. Omitted defaults (`Origin` `[0, 0]`, `Elevation` `0`, `RefDirection` `[1, 0]`) are not added to the set and not invented on the way back.
- Each distinct class, `PredefinedType`, and `ObjectType` becomes one type object. `IfcFurnitureType.AssemblyPlace` is `NOTDEFINED`. The type's property sets and representation maps are not stored. On import, an occurrence with no `ObjectType` takes the type's `ElementType`, and an occurrence with no `PredefinedType` takes the type's. A file this converter did not write is read from placement and from that corner-origin box; other geometry keeps the placement only.
- An imported `IfcWallStandardCase` is stored as a wall and written back as `IfcWall`. `PredefinedType` is kept.
- A light's `Wattage` is `Pset_LightFixtureTypeCommon.TotalWattage` (`IfcPowerMeasure`, watts). `CctMin` and `CctMax` are `Pset_YamlIfc` properties (`IfcThermodynamicTemperatureMeasure`, kelvin). Import lifts those properties back into the fields and does not also leave them in `PropertySets`. The `WATT` and `KELVIN` units are emitted only when a measure of that kind is written.
- Each cable becomes an `IfcCableSegment` plus four nested `IfcDistributionPort` entities and two `IfcRelConnectsPorts`. The ports are not YAML. Their `SystemType` follows the circuit that assigns the cable, or `ELECTRICAL`. The segment's own ports are named `{id}:sink` and `{id}:source`, and import restores `From` and `To` from those. A port nested in a supported element is not reported as a skipped product.
- Each circuit is an `IfcDistributionCircuit`. `Assigns` is one `IfcRelAssignsToGroup`. Members this subset does not store are dropped on import.
- YAML lengths are metres. An IFC file in millimetres is converted on the way in.

An IFC file also contains entities this subset does not store (slabs, roofs, stairs, and the rest). Those are counted and reported, not written into the YAML. For the entities above, every instance is kept, matched by `GlobalId`. A bare `IfcFurnishingElement` is one of the counted leftovers.

## Open questions

1. **Default wall geometry.** The stored form is a centreline plus `Thickness`, centred. The sample measures both from the double-line drawing. A footprint polygon would match the drawn edges more directly and would make the centreline a derived view. Which one should be the required core?
2. **One wall through its openings.** Pieces of the same axis are one `IfcWall`, and the axis runs through the voids. The alternative is one wall object per solid stretch between openings.
3. **How far a "same axis" gap can be and still be one wall.** The sample joins collinear pieces when the gap is at most 0.36 m (a reveal the faces did not span) or when one or more openings cover the gap. That threshold is a judgment.
4. **Void width versus leaf size.** `Width` on the opening is the measured hole. `OverallWidth` on the door can be smaller (the written leaf size). Confirm both should be kept.
5. **`AlongAxis` is the start of the void**, the end nearer `Axis.Start`, rather than the centre.
6. **Missing `Height` and missing `Thickness`.** The sample omits `Height` on every wall, and omits `Thickness` on the one wall whose opposite face is not drawn (`W-017`, host of `OP19`). Is a file in that state valid, or only a draft a validator should reject? The converter accepts it: a wall with a thickness and no height is extruded 3 m in the IFC, and that height is not written back.
7. **`HeadHeight`.** `OP27` and `OP29` know the head and not the sill or the height. Is a head-only field the right extension, or should those two stay as comments until the sill is known?
8. **Glazed run `W-023`.** Thickness 0.10 m is the depth of the two posts; the long faces are not drawn. Worth a separate look.
9. **No host, no opening.** The hall-to-garage passage has no wall across it, so it is not an `IfcOpeningElement`. Confirm that is the right reading of `IfcRelVoidsElement`.
10. **120 mm squares** on the wall layer are short `IfcWall`s. `IfcColumn` is deferred; they may want to move later.
11. **Implicit storey containment** while there is only one storey. Confirm, or put `ContainedInStructure` on every element now.
12. **Corner joints** are butt joints, recorded in `connections`. The relating wall runs through and the related wall is trimmed to its face. There is no mitre and no join-style field. An axis in the drawing usually stops on the other wall's face, about half a thickness short of the centre-line intersection. `python -m yaml_ifc detect-connections` snaps those endpoints in the YAML, as a reviewed edit of the file, and shifts `AlongAxis` so a hosted opening stays where it was. The converter does not snap or extend axes itself.
13. **Cabinet granularity.** The example is one element per module (`BaseCabinet`), not one element per run of cabinets. A stack of ovens is one appliance per oven. Confirm that Blueprints wants the module, not the run.
14. **The island is not voided.** The cooktop and the sink are separate products placed in the island's volume. There is no opening relationship. The cut-out is generated from the type.
15. **Non-rectangular plans.** A sectional is `SOFA` / `SectionalSofa` and one box, the extent. The L is not stored. A footprint polygon on a furnishing element would carry it, and would no longer be "a box plus a type string".
16. **Rug versus flooring.** A rug is `IfcCovering` / `USERDEFINED` / `Rug`. `FLOORING` is the room's floor finish. Both predefined types are accepted. Confirm the rug should stay `USERDEFINED`.
17. **Missing appliance enums.** IFC4 has `ELECTRICCOOKER` and `REFRIGERATOR`, and no oven and no hood. Those two are `USERDEFINED`. A fridge-freezer column may be `FRIDGE_FREEZER` rather than `REFRIGERATOR`.
18. **Track lights.** One `IfcLightFixture` per track run, `DIRECTIONSOURCE` / `TrackLight`, not one entity per head. `USERDEFINED` would drop the enum.
19. **Nominal property sets.** `Pset_FurnitureTypeCommon` can store `NominalLength`, `NominalDepth`, `NominalHeight`, and `IsBuiltIn`. The converter does not fill it. The box is the size. Should a later writer copy the box into that set?
20. **Type objects are derived.** They are not YAML entries. `AssemblyPlace` is the filler `NOTDEFINED`, not a claim about factory or site assembly. Type property sets and mapped geometry are dropped on import.
21. **Space bodies.** A room is an id, a name, and a predefined type, so furniture can be contained. A footprint and a clear height are not stored. Wall `Height` in the ground-floor sample is still omitted for that reason.
22. **The TV is the unit.** `TvUnit` is `IfcFurniture`. The screen is not an `IfcAudioVisualAppliance`. The hanging plant shelf is `IfcFurniture` / `SHELF`, not a suspended member.
23. **CCT is a range in `Pset_YamlIfc`.** Standard IFC stores one colour temperature, and the goniometric light source requires colour, flux, and a distribution this file does not have. `IfcLamp` is not in IFC4, so `Pset_LampTypeCommon.ColorTemperature` has no entity to sit on. Confirm the two bounds are the right record, rather than a single kelvin plus a separate tunable flag.
24. **Push buttons.** `PUSHBUTTON` is not an `IfcSwitchingDeviceTypeEnum` value. The example uses `MOMENTARYSWITCH` / `PushButton`. A latching push button could instead be `TOGGLESWITCH` plus `Pset_SwitchingDeviceTypeToggleSwitch.ToggleSwitchType` `PUSHBUTTON`. Confirm which one the wall buttons in the house are.
25. **mmWave.** `MovementSensingType` has no mmWave value. The family name `MmWavePresence` is the record. A controlled token in `Pset_YamlIfc` would say it again. Confirm the family name is enough.
26. **Blind actuator.** `IfcActuator` / `ELECTRICACTUATOR`, with `SUNBLINDACTUATOR` and `MOTORDRIVE` available as standard properties. `IfcElectricMotor` was the other candidate and was not used. Confirm the actuator is the product to count, not the motor inside it.
27. **Ports are derived.** The YAML names `From` and `To`. Four ports and two `IfcRelConnectsPorts` are rebuilt, and `SystemType` follows the circuit. A cable route, a conduit, and a number of cores are not stored. Confirm a logical segment is enough until a route is measured.
28. **Panel interiors.** The board is one element. Breakers, RCDs, and busbars are deferred. A circuit names the board, the devices, and the cables, and does not name a breaker.
29. **Devices are not hosted in a wall.** A switch has a box in the room, the same way a cabinet does. There is no opening voided for the back box. Confirm that stays until a wall host is needed.
30. **Circuit membership** is an `Assigns` list. A board may sit on several circuits. Load, phase, and protective device are not on the circuit.
