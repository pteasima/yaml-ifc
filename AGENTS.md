# Agents

Humans are agents too. Process for this repo lives in this file. [README.md](README.md) is the docs root, and the format is [docs/spec.md](docs/spec.md). This file is the only process doc. A rule that applies only here sits next to an ordinary engineering reason.

## Pull requests

Open every pull request as a draft. A draft means agents are still working. Ready for review means it is the repo owner's turn. Mark a pull request ready only when CI is green and you have reviewed the diff yourself. If another agent launched you, leave the pull request as a draft and report back to that agent.

Pull requests merge by squash. The head branch is deleted when the pull request merges.

## Checks

Install converter dependencies with `pip install -r requirements.txt`. The test suite is `pytest`. It round-trips the ground-floor sample, compares `samples/ground-floor.ifc` byte for byte, and checks the reading of the external IFC sample.

CI runs that suite on pull requests and on pushes to `main`, on Python 3.12, with a read-only token (`permissions: contents: read`). The workflow pins one Python and the versions in `requirements.txt` because that byte comparison fails when the writer or IfcOpenShell changes, even if the YAML is the same.

The plan renderer is a separate check. It needs `libcairo2`, and Cairo is a system library the converter tests do not use. Render locally with `pip install -r tools/requirements.txt` and `python tools/render_plan.py samples/ground-floor.yaml --out-dir dist`. On a pull request, `.github/workflows/plan-preview.yml` renders the samples, pushes the PNGs to the `previews` branch, and keeps one comment with the raw image URLs. That job's token is recorded under Repo settings.

## Editing files

Leave out a value the source does not contain. A filled-in guess would come back from a round trip as if it had been measured.

`samples/external/IfcOpenHouse_IFC4.ifc` stays an unmodified copy of IfcOpenHouse. The from-IFC tests compare the converter's reading with the committed YAML and `.skipped.txt`, so those input bytes stay fixed. When the converter's reading changes, regenerate those two outputs with `python -m yaml_ifc from-ifc` and review the diff. When the ground-floor YAML or the writer changes, regenerate `samples/ground-floor.ifc` with `python -m yaml_ifc to-ifc` so the byte comparison still matches.

`python -m yaml_ifc detect-connections` snaps axes that stop short of a corner and records `connections`. Run it once and review the diff. `to-ifc` and `from-ifc` write the joints the file already lists, as butt joints. Moving a wall's start shifts each opening's `AlongAxis` so the opening stays put.

The YAML writer drops comments. Hand-written comments are for people reading the file. `dump`, `from-ifc`, and `detect-connections` omit them.

## Repo settings

- **Plan preview token:** `contents: write` and `pull-requests: write` on `.github/workflows/plan-preview.yml`, because that workflow pushes rendered plans to the `previews` branch and updates the pull request comment. The test workflow uses `contents: read`.
