# yaml-ifc

A YAML format, shaped like IFC, for one house's building elements. Agents edit it as text. This version is walls, openings, furnishings, and the electrical installation outside the panels. A cable can carry a route and a core count.

Process for working in this repo is in [AGENTS.md](AGENTS.md).

The format is [docs/spec.md](docs/spec.md). The ground floor of RD Šíma is [samples/ground-floor.yaml](samples/ground-floor.yaml) (walls and openings only). A small furnishings example, with nominal sizes rather than a survey, is [samples/furnishings.yaml](samples/furnishings.yaml). A small electrical example, also nominal, is [samples/electrical.yaml](samples/electrical.yaml).

Render a plan locally with `pip install -r tools/requirements.txt` (needs libcairo2) and `python tools/render_plan.py samples/ground-floor.yaml --out-dir dist`. The electrical sample, devices and cable routes in top view and isometric, is `python tools/render_electrical.py samples/electrical.yaml -o samples/electrical.png`.

Convert with `pip install -r requirements.txt`, then `python -m yaml_ifc to-ifc samples/ground-floor.yaml -o samples/ground-floor.ifc` and `python -m yaml_ifc from-ifc samples/external/IfcOpenHouse_IFC4.ifc -o samples/external/IfcOpenHouse_IFC4.yaml`. The second command prints the entity types it skipped. Tests: `pytest`.

Wall joints are an optional `connections` list on the file (see the spec). The converter writes them as butt joints: the relating wall runs through, and the related wall is trimmed. It does not search for joints. To snap axes that stop short of a corner and record the joints, run `python -m yaml_ifc detect-connections INPUT -o OUTPUT` once and review the diff. Moving a wall's start shifts each opening's `AlongAxis` so the opening stays put.

`yaml_ifc.footprints(doc)` returns `{wall id: [[x, y], ...]}` in metres, in the same plan coordinates as `Axis`. Joined walls are the trimmed polygons IfcOpenShell built for the IFC, so a later model can extrude those rings and match the file. Walls with no body are omitted. The ring is not closed.

## Known issues (v1)

Petr's review of the first plan render, 2026-10-06:

- Some hinged doors open the wrong way in the render.
- Sliding doors and the garage door are not supported yet.
- Window openings are either not supported by the spec or not filled in the sample.
- The plan renderer still draws each wall as a centreline band, so corners overlap in the picture. The IFC footprints are the trimmed butt joints from `yaml_ifc.footprints`.
