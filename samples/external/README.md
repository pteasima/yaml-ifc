# External IFC sample

`IfcOpenHouse_IFC4.ifc` is an unmodified copy of the IfcOpenHouse model.

- Source: https://github.com/ThatOpen/engine_web-ifc/blob/main/tests/ifcfiles/public/IfcOpenHouse_IFC4.ifc
- Original file: `IfcOpenHouse.ifc`, generated with IfcOpenShell 0.5.0-dev on 2014-05-05 by Thomas Krijnen. The same bytes are mirrored in several IFC test suites, including `ifcquery/IfcFileLoader`.
- License: Mozilla Public License 2.0, the license of [ThatOpen/engine_web-ifc](https://github.com/ThatOpen/engine_web-ifc/blob/main/LICENSE), which is the repository this copy was taken from. MPL-2.0 allows the file to be committed and redistributed with attribution. This copy is unmodified.
- SHA-256: `71c9466bf02306be58d45b77d738541a0e7410767960b5eed1cf85737dfa34c9`

It is one storey, schema IFC4, and `ifcopenshell.validate` reports no errors. It has walls, openings, a door, and windows, and also slabs, a roof, a footing, a stair flight, members, and plates, which this subset does not store.

`IfcOpenHouse_IFC4.yaml` is the converter's reading of that file. The void solids in the IFC are larger than the wall, so an opening's `Width` and `Depth` are the extent of that solid, not a tight reveal. The east and west walls are clipped by the roof; the YAML keeps one height, the vertical extent of the solid. The five windows do not fill an opening in the source file. Lengths are converted from millimetres to metres.

`IfcOpenHouse_IFC4.skipped.txt` is the count of product types the converter did not write into the YAML.
