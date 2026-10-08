#!/usr/bin/env python3
"""Draw a tiled floor plan and the wall elevations from a yaml-ifc file.

The floor plan is the tile and grout layout in plan, including the point
drain. The wall sheet is one elevation per tiled wall: the bottom course
follows the floor, and openings are the holes in the tiling.

Needs libcairo2 and tools/requirements.txt (cairosvg). The geometry is
yaml_ifc.tiling, the same layout the IFC writer extrudes.
"""

import argparse
import math
import sys
import xml.sax.saxutils as xml_escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import yaml

from yaml_ifc.tiling import floor_layout, wall_layout

BG = "#f6f4f1"
INK = "#2b2824"
MUTED = "#6a645c"
TILE = "#e4d3b0"
GROUT = "#b7a48a"
DRAIN = "#8d8880"
OPENING = "#f7f5f2"
EDGE = "#6e685f"
WALL = "#d9d3c9"


def load_document(path):
    with path.open(encoding="utf-8") as handle:
        doc = yaml.safe_load(handle)
    if not isinstance(doc, dict):
        raise ValueError("file is not a yaml-ifc mapping")
    return doc


def _find(doc, yaml_id):
    for key in ("slabs", "coverings", "wasteTerminals", "walls"):
        for item in doc.get(key) or []:
            if item.get("id") == yaml_id:
                return item
    raise ValueError(f"unknown element {yaml_id}")


def plane_of(doc, element):
    plane = element.get("Plane")
    if isinstance(plane, str):
        plane = _find(doc, plane).get("Plane")
    if not isinstance(plane, dict):
        raise ValueError(f"{element.get('id')} has no plane")
    return plane


def floor_covering(doc):
    for item in doc.get("coverings") or []:
        layout = item.get("TileLayout") or {}
        if layout.get("Footprint"):
            return item
    raise ValueError("no floor TileLayout")


def wall_coverings(doc):
    rows = []
    for item in doc.get("coverings") or []:
        layout = item.get("TileLayout") or {}
        if layout.get("Axis"):
            rows.append(item)
    return rows


def _layout_floor(doc):
    covering = floor_covering(doc)
    layout = covering["TileLayout"]
    plane = plane_of(doc, covering)
    laid = floor_layout(
        plane,
        layout["Tile"],
        layout.get("WallTile") or layout["Tile"],
        layout["WallJoint"],
        layout["GridOrigin"],
        layout["Footprint"],
        layout.get("Cutouts") or (),
        layout.get("JointInset") or 0.0,
    )
    return covering, plane, laid


def _layout_wall(doc, covering):
    layout = covering["TileLayout"]
    plane = plane_of(doc, covering)
    owner = covering
    if isinstance(covering.get("Plane"), str):
        owner = _find(doc, covering["Plane"])
    return wall_layout(
        plane,
        layout["Tile"],
        layout["Joint"],
        layout["Courses"],
        layout["BottomJoint"],
        layout["GridOrigin"],
        layout["Axis"],
        layout["Inside"],
        layout.get("Openings") or (),
        footprint=layout.get("Footprint") or owner.get("Footprint"),
    )


def escape(text):
    return xml_escape.escape(str(text))


class Canvas:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.parts = []

    def add(self, tag, **attrs):
        body = " ".join(f'{key}="{value}"' for key, value in attrs.items())
        self.parts.append(f"<{tag} {body}/>")

    def polygon(self, points, **attrs):
        drawn = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
        self.add("polygon", points=drawn, **attrs)

    def text(self, x, y, text, **attrs):
        body = " ".join(f'{key}="{value}"' for key, value in attrs.items())
        self.parts.append(f'<text x="{x:.1f}" y="{y:.1f}" {body}>{escape(text)}</text>')

    def svg(self):
        body = "\n".join(self.parts)
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" height="{self.height}" '
            f'viewBox="0 0 {self.width} {self.height}">\n'
            f'<rect width="{self.width}" height="{self.height}" fill="{BG}"/>\n'
            f"{body}\n</svg>\n"
        )


def _bounds(rings):
    xs = [point[0] for ring in rings for point in ring]
    ys = [point[1] for ring in rings for point in ring]
    return min(xs), min(ys), max(xs), max(ys)


def render_plan(doc):
    _covering, plane, laid = _layout_floor(doc)
    footprint = floor_covering(doc)["TileLayout"]["Footprint"]
    rings = [footprint, *laid["tiles"], *laid["grout"]]
    min_x, min_y, max_x, max_y = _bounds(rings)
    span_x = max(max_x - min_x, 1e-6)
    span_y = max(max_y - min_y, 1e-6)
    margin = 56
    header = 64
    footer = 48
    scale = min(980 / span_x, 820 / span_y)
    width = int(math.ceil(span_x * scale + 2 * margin))
    height = int(math.ceil(span_y * scale + header + footer))
    canvas = Canvas(width, height)

    def xy(point):
        return (
            margin + (point[0] - min_x) * scale,
            header + (max_y - point[1]) * scale,
        )

    def paint(ring, fill, stroke, stroke_width):
        canvas.polygon(tuple(xy(point) for point in ring), fill=fill, stroke=stroke, **{"stroke-width": stroke_width, "stroke-linejoin": "miter"})

    paint(footprint, WALL, EDGE, "1.4")
    for ring in laid["grout"]:
        paint(ring, GROUT, GROUT, "0.4")
    for ring in laid["tiles"]:
        paint(ring, TILE, EDGE, "0.6")
    for terminal in doc.get("wasteTerminals") or []:
        origin = terminal.get("Origin") or [0, 0]
        w = float(terminal.get("Width") or 0)
        d = float(terminal.get("Depth") or 0)
        ox, oy = float(origin[0]), float(origin[1])
        paint([(ox, oy), (ox + w, oy), (ox + w, oy + d), (ox, oy + d)], DRAIN, INK, "1.2")

    fall = -_elev(plane, min_x, min_y) * 1000
    high = _elev(plane, max_x, max_y) * 1000
    canvas.text(margin, 28, "Floor tiles", **{"font-family": "DejaVu Sans, sans-serif", "font-size": "18", "fill": INK})
    canvas.text(
        margin,
        48,
        f"door corner {high:.1f} mm    drain corner { _elev(plane, min_x, min_y) * 1000:.1f} mm    fall {fall:.1f} mm",
        **{"font-family": "DejaVu Sans, sans-serif", "font-size": "12", "fill": MUTED},
    )
    canvas.text(
        margin,
        height - 20,
        "Beige is tile, darker is grout, grey is the point drain. North is up.",
        **{"font-family": "DejaVu Sans, sans-serif", "font-size": "12", "fill": MUTED},
    )
    return canvas.svg()


def _elev(plane, x, y):
    origin_x, origin_y = plane["Origin"]
    gradient_x, gradient_y = plane["Gradient"]
    return (
        float(plane["Elevation"])
        + float(gradient_x) * (float(x) - float(origin_x))
        + float(gradient_y) * (float(y) - float(origin_y))
    )


def render_walls(doc):
    walls = [(covering, _layout_wall(doc, covering)) for covering in wall_coverings(doc)]
    if not walls:
        raise ValueError("no wall TileLayout")
    margin = 48
    label_w = 150
    header = 56
    gap = 28
    lengths = [laid["frame"]["length"] for _covering, laid in walls]
    heads = [laid["levels"]["head"] for _covering, laid in walls]
    scale = min(920 / max(lengths), 180 / max(heads))
    row_h = max(heads) * scale
    width = int(math.ceil(margin + label_w + max(lengths) * scale + margin))
    height = int(math.ceil(header + len(walls) * (row_h + gap) + 24))
    canvas = Canvas(width, height)
    canvas.text(margin, 32, "Wall tiles", **{"font-family": "DejaVu Sans, sans-serif", "font-size": "18", "fill": INK})

    for index, (covering, laid) in enumerate(walls):
        top = header + index * (row_h + gap)
        base = top + row_h

        def sz(along, z, _base=base):
            return (margin + label_w + along * scale, _base - z * scale)

        name = covering.get("Name") or covering.get("id")
        canvas.text(
            margin,
            top + 18,
            name,
            **{"font-family": "DejaVu Sans, sans-serif", "font-size": "13", "fill": INK},
        )
        for piece in laid["grout"]:
            canvas.polygon(
                tuple(sz(*point) for point in piece["polygon"]),
                fill=GROUT,
                stroke=GROUT,
                **{"stroke-width": "0.4"},
            )
        for piece in laid["tiles"]:
            canvas.polygon(
                tuple(sz(*point) for point in piece["polygon"]),
                fill=TILE,
                stroke=EDGE,
                **{"stroke-width": "0.7", "stroke-linejoin": "miter"},
            )
        layout = covering["TileLayout"]
        axis = layout["Axis"]
        length = laid["frame"]["length"]
        plane = plane_of(doc, covering)

        def floor_z(along):
            x = axis["Start"][0] + (axis["End"][0] - axis["Start"][0]) * along / length
            y = axis["Start"][1] + (axis["End"][1] - axis["Start"][1]) * along / length
            return _elev(plane, x, y)

        for opening in layout.get("Openings") or []:
            along = float(opening["AlongAxis"])
            gap_s = float(opening["Width"])
            sill = float(opening.get("SillHeight") or 0)
            head = sill + float(opening["Height"])
            # A door is open down through the sloped bottom, including below datum.
            if sill <= 1e-6:
                z0 = min(0.0, floor_z(along), floor_z(along + gap_s))
            else:
                z0 = sill
            z1 = min(head, laid["levels"]["head"] + 0.05)
            canvas.polygon(
                (sz(along, z0), sz(along + gap_s, z0), sz(along + gap_s, z1), sz(along, z1)),
                fill=OPENING,
                stroke=EDGE,
                **{"stroke-width": "1.0"},
            )
        zero_y = base
        canvas.add(
            "line",
            x1=f"{margin + label_w:.1f}",
            y1=f"{zero_y:.1f}",
            x2=f"{margin + label_w + laid['frame']['length'] * scale:.1f}",
            y2=f"{zero_y:.1f}",
            stroke=MUTED,
            **{"stroke-width": "1", "stroke-dasharray": "4 3"},
        )
    canvas.text(
        margin,
        height - 16,
        "Bottom edges follow the floor. The dashed line is elevation 0. Openings are untiled.",
        **{"font-family": "DejaVu Sans, sans-serif", "font-size": "12", "fill": MUTED},
    )
    return canvas.svg()


def write_png(svg, path):
    import cairosvg

    path.parent.mkdir(parents=True, exist_ok=True)
    cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to=str(path))


def main(argv):
    parser = argparse.ArgumentParser(description="Render a tiled floor and its wall elevations.")
    parser.add_argument("file", type=Path, help="yaml-ifc file")
    parser.add_argument("--plan", type=Path, required=True, help="floor-plan PNG")
    parser.add_argument("--walls", type=Path, required=True, help="wall-elevation PNG")
    args = parser.parse_args(argv)
    doc = load_document(args.file)
    write_png(render_plan(doc), args.plan)
    write_png(render_walls(doc), args.walls)
    print(args.plan)
    print(args.walls)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
