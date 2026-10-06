# yaml-ifc

A YAML format, shaped like IFC, for one house's building elements. Agents edit it as text. This version is walls and openings only.

The format is [docs/spec.md](docs/spec.md). The ground floor of RD Šíma is [samples/ground-floor.yaml](samples/ground-floor.yaml).

Render a plan locally with `pip install -r tools/requirements.txt` (needs libcairo2) and `python tools/render_plan.py samples/ground-floor.yaml --out-dir dist`.
