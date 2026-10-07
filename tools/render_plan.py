#!/usr/bin/env python3
"""Render a yaml-ifc file as a 2D plan.

Reads the walls-and-openings subset in docs/spec.md and writes an SVG plus a
PNG (via cairosvg). Walls are the centreline axis with Thickness drawn as a
filled band. A wall with no thickness is a thin line. Openings are cut out of
the host wall; doors, windows, and plain openings are drawn differently.
Furnishings are rectangles from Origin, Width, and Depth.
"""

import argparse
import math
import sys
import xml.sax.saxutils as xml_escape
from pathlib import Path

import yaml

BG = "#f6f4f1"
WALL = "#d9d3c9"
WALL_EDGE = "#6e685f"
DOOR = "#c45c26"
DOOR_FILL = "#f4d4c4"
WINDOW = "#2a6fdb"
WINDOW_FILL = "#d7e5f8"
PLAIN = "#2a8f4a"
PLAIN_FILL = "#d9efe1"
INK = "#2b2824"
MUTED = "#6a645c"
FURN_FILL = "#e4d7c3"
FURN_EDGE = "#8a5a32"

# Plan boxes for the furnishing lists. Coverings (a rug) are drawn under the
# pieces that sit on them. The converter owns the IFC; this is only the picture.
FURNISHING_KEYS = (
    "coverings",
    "systemFurniture",
    "furniture",
    "sanitaryTerminals",
    "electricAppliances",
    "lightFixtures",
)

HEADER = 44
MARGIN = 28
FOOTER = 40
TARGET_W = 1500
MAX_H = 900


def load_document(path):
    with path.open(encoding="utf-8") as handle:
        doc = yaml.safe_load(handle)
    if not isinstance(doc, dict):
        raise ValueError("file is not a yaml-ifc mapping")
    return doc


def _xy(point):
    return float(point[0]), float(point[1])


def axis_of(wall):
    axis = wall.get("Axis") or {}
    start, end = axis.get("Start"), axis.get("End")
    if not start or not end:
        return None
    return _xy(start), _xy(end)


def thickness_of(wall):
    if wall.get("Thickness") is not None:
        return float(wall["Thickness"])
    layers = (wall.get("MaterialLayers") or {}).get("Layers") or []
    total = 0.0
    found = False
    for layer in layers:
        if isinstance(layer, dict) and layer.get("LayerThickness") is not None:
            total += float(layer["LayerThickness"])
            found = True
    return total if found else None


def footprint_of(wall):
    raw = wall.get("Footprint")
    if not raw:
        return None
    return [_xy(point) for point in raw]


class Frame:
    def __init__(self, start, end):
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        self.length = math.hypot(dx, dy)
        self.start = start
        self.end = end
        if self.length < 1e-9:
            self.ux = self.uy = 0.0
            self.px = self.py = 0.0
        else:
            self.ux, self.uy = dx / self.length, dy / self.length
            self.px, self.py = -self.uy, self.ux

    def point(self, along, across):
        return (
            self.start[0] + self.ux * along + self.px * across,
            self.start[1] + self.uy * along + self.py * across,
        )

    def rect(self, along, width, depth):
        half = depth / 2.0
        far = along + width
        return [
            self.point(along, half),
            self.point(far, half),
            self.point(far, -half),
            self.point(along, -half),
        ]


def band(frame, thickness):
    half = thickness / 2.0
    return [
        frame.point(0.0, half),
        frame.point(frame.length, half),
        frame.point(frame.length, -half),
        frame.point(0.0, -half),
    ]


def profile_world(wall, frame):
    raw = wall.get("Profile")
    if not raw or frame is None:
        return None
    return [frame.point(float(point[0]), float(point[1])) for point in raw]


def kind_of(opening_id, doors, windows):
    if opening_id in doors:
        return "door"
    if opening_id in windows:
        return "window"
    return "plain"


def nice_metres(px_per_m, target_px=120):
    raw = target_px / px_per_m if px_per_m else 1.0
    if raw <= 0:
        return 1.0
    power = 10 ** math.floor(math.log10(raw))
    for factor in (1, 2, 5, 10):
        if factor * power >= raw * 0.55:
            return factor * power
    return 10 * power


def escape(text):
    return xml_escape.escape(str(text), {'"': "&quot;"})


class Canvas:
    def __init__(self, scale, min_x, max_y, width, height):
        self.scale = scale
        self.min_x = min_x
        self.max_y = max_y
        self.width = width
        self.height = height
        self.parts = []

    def xy(self, point):
        x = MARGIN + (point[0] - self.min_x) * self.scale
        y = HEADER + (self.max_y - point[1]) * self.scale
        return x, y

    def path(self, rings, **attrs):
        commands = []
        for ring in rings:
            if len(ring) < 2:
                continue
            mapped = [self.xy(point) for point in ring]
            commands.append(
                "M "
                + " L ".join(f"{x:.2f} {y:.2f}" for x, y in mapped)
                + " Z"
            )
        if not commands:
            return
        attr = " ".join(f'{key}="{value}"' for key, value in attrs.items())
        self.parts.append(f'<path d="{" ".join(commands)}" {attr}/>')

    def line(self, a, b, **attrs):
        x1, y1 = self.xy(a)
        x2, y2 = self.xy(b)
        attr = " ".join(f'{key}="{value}"' for key, value in attrs.items())
        self.parts.append(
            f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" {attr}/>'
        )

    def polyline(self, points, **attrs):
        if len(points) < 2:
            return
        mapped = [self.xy(point) for point in points]
        attr = " ".join(f'{key}="{value}"' for key, value in attrs.items())
        data = " ".join(f"{x:.2f},{y:.2f}" for x, y in mapped)
        self.parts.append(f'<polyline points="{data}" {attr}/>')

    def text(self, x, y, text, **attrs):
        attr = " ".join(f'{key}="{value}"' for key, value in attrs.items())
        self.parts.append(f'<text x="{x:.1f}" y="{y:.1f}" {attr}>{escape(text)}</text>')


def swing_arc(frame, hinge, radius, direction, side, steps=16):
    points = []
    for step in range(steps + 1):
        angle = (step / steps) * (math.pi / 2)
        points.append(
            frame.point(
                hinge + math.cos(angle) * radius * direction,
                math.sin(angle) * radius * side,
            )
        )
    return points


def opening_depth(opening, thickness):
    if opening.get("Depth") is not None:
        return float(opening["Depth"])
    if thickness:
        return thickness
    return 0.16


def furnishing_rect(item):
    origin = item.get("Origin")
    if not isinstance(origin, (list, tuple)) or len(origin) < 2:
        return None
    ox, oy = float(origin[0]), float(origin[1])
    width, depth = item.get("Width"), item.get("Depth")
    if width is None or depth is None:
        return [
            (ox, oy),
            (ox + 0.15, oy),
            (ox + 0.15, oy + 0.15),
            (ox, oy + 0.15),
        ]
    ref = item.get("RefDirection") or [1.0, 0.0]
    ux, uy = float(ref[0]), float(ref[1])
    length = math.hypot(ux, uy) or 1.0
    ux, uy = ux / length, uy / length
    px, py = -uy, ux
    width, depth = float(width), float(depth)

    def corner(x, y):
        return (ox + x * ux + y * px, oy + x * uy + y * py)

    return [corner(0, 0), corner(width, 0), corner(width, depth), corner(0, depth)]


def collect_bounds(points, bounds):
    for x, y in points:
        bounds[0] = min(bounds[0], x)
        bounds[1] = min(bounds[1], y)
        bounds[2] = max(bounds[2], x)
        bounds[3] = max(bounds[3], y)


def render_document(doc, filename):
    walls = doc.get("walls") or []
    openings = doc.get("openings") or []
    doors = {
        item.get("FillsOpening"): item
        for item in (doc.get("doors") or [])
        if isinstance(item, dict)
    }
    windows = {
        item.get("FillsOpening"): item
        for item in (doc.get("windows") or [])
        if isinstance(item, dict)
    }
    by_wall = {}
    for opening in openings:
        if isinstance(opening, dict):
            by_wall.setdefault(opening.get("VoidsElement"), []).append(opening)

    prepared = []
    bounds = [math.inf, math.inf, -math.inf, -math.inf]
    for wall in walls:
        if not isinstance(wall, dict):
            continue
        axis = axis_of(wall)
        frame = Frame(*axis) if axis else None
        if frame is not None and frame.length < 1e-9:
            frame = None
        footprint = footprint_of(wall)
        profile = profile_world(wall, frame)
        thickness = thickness_of(wall)
        if footprint:
            shape = footprint
        elif profile:
            shape = profile
        elif frame is not None and thickness:
            shape = band(frame, thickness)
        else:
            shape = None
        if shape:
            collect_bounds(shape, bounds)
        elif frame is not None:
            collect_bounds([frame.start, frame.end], bounds)
        else:
            continue
        marks = []
        for opening in by_wall.get(wall.get("id"), []):
            if frame is None:
                print(
                    f"warning: {opening.get('id')} host {wall.get('id')} has no axis",
                    file=sys.stderr,
                )
                continue
            along = float(opening.get("AlongAxis") or 0)
            gap = float(opening.get("Width") or 0)
            if gap <= 0:
                continue
            depth = opening_depth(opening, thickness)
            hole = frame.rect(along, gap, depth)
            collect_bounds(hole, bounds)
            kind = kind_of(opening.get("id"), doors, windows)
            if kind == "door":
                side = 1
                leaves = (
                    ((along, gap / 2, 1), (along + gap, gap / 2, -1))
                    if gap > 1.35
                    else ((along, gap, 1),)
                )
                for hinge, radius, direction in leaves:
                    collect_bounds(swing_arc(frame, hinge, radius, direction, side), bounds)
            marks.append((opening, along, gap, depth, hole, kind))
        prepared.append(
            {
                "id": wall.get("id"),
                "frame": frame,
                "shape": shape,
                "thickness": thickness,
                "marks": marks,
            }
        )

    pieces = []
    for key in FURNISHING_KEYS:
        for item in doc.get(key) or []:
            if not isinstance(item, dict):
                continue
            rect = furnishing_rect(item)
            if rect is None:
                continue
            collect_bounds(rect, bounds)
            pieces.append((item, rect))

    if (not prepared and not pieces) or bounds[0] is math.inf:
        raise ValueError("nothing to draw")

    pad = 1.2
    bounds[0] -= pad
    bounds[1] -= pad
    bounds[2] += pad
    bounds[3] += pad

    span_x = max(bounds[2] - bounds[0], 1e-6)
    span_y = max(bounds[3] - bounds[1], 1e-6)
    scale = min((TARGET_W - 2 * MARGIN) / span_x, (MAX_H - HEADER - FOOTER) / span_y)
    width = int(math.ceil(span_x * scale + 2 * MARGIN))
    height = int(math.ceil(span_y * scale + HEADER + FOOTER))
    canvas = Canvas(scale, bounds[0], bounds[3], width, height)

    labels = []
    for wall in prepared:
        frame = wall["frame"]
        marks = wall["marks"]
        holes = [mark[4] for mark in marks]

        if wall["shape"] is not None:
            rings = [wall["shape"], *holes] if holes else [wall["shape"]]
            canvas.path(
                rings,
                fill=WALL,
                stroke=WALL_EDGE,
                **{
                    "stroke-width": "1",
                    "fill-rule": "evenodd",
                    "stroke-linejoin": "miter",
                },
            )
        elif frame is not None:
            canvas.line(
                frame.start,
                frame.end,
                stroke=WALL_EDGE,
                **{"stroke-width": "1.4", "stroke-linecap": "square"},
            )

        for opening, along, gap, depth, hole, kind in marks:
            fill = {"door": DOOR_FILL, "window": WINDOW_FILL, "plain": PLAIN_FILL}[kind]
            stroke = {"door": DOOR, "window": WINDOW, "plain": PLAIN}[kind]
            dash = ' stroke-dasharray="4 3"' if kind == "plain" else ""
            canvas.path(
                [hole],
                fill=fill,
                stroke=stroke,
                **{"stroke-width": "1.2", "stroke-linejoin": "miter"},
            )
            if dash:
                canvas.parts[-1] = canvas.parts[-1].replace("/>", dash + "/>")

            if kind == "window":
                inset = max((wall["thickness"] or depth) * 0.22, 0.025)
                canvas.line(
                    frame.point(along, inset),
                    frame.point(along + gap, inset),
                    stroke=WINDOW,
                    **{"stroke-width": "1.4", "stroke-linecap": "square"},
                )
                canvas.line(
                    frame.point(along, -inset),
                    frame.point(along + gap, -inset),
                    stroke=WINDOW,
                    **{"stroke-width": "1.4", "stroke-linecap": "square"},
                )
            elif kind == "door":
                side = 1
                if gap > 1.35:
                    leaves = (
                        (along, gap / 2, 1),
                        (along + gap, gap / 2, -1),
                    )
                else:
                    leaves = ((along, gap, 1),)
                for hinge, radius, direction in leaves:
                    arc = swing_arc(frame, hinge, radius, direction, side)
                    canvas.polyline(
                        arc,
                        fill="none",
                        stroke=DOOR,
                        **{"stroke-width": "1.15", "stroke-linejoin": "round"},
                    )
                    canvas.line(
                        frame.point(hinge, 0),
                        arc[-1],
                        stroke=DOOR,
                        **{"stroke-width": "1.3", "stroke-linecap": "square"},
                    )

            label = opening.get("id") or ""
            tag = opening.get("Tag")
            if tag and gap * scale >= 36:
                label = f"{label} {tag}"
            if label and gap * scale >= 16:
                half = depth / 2.0
                anchor = frame.point(along + gap / 2.0, -(half + 0.28))
                sx, sy = canvas.xy(anchor)
                labels.append((gap, sx, sy, label))

    placed = []
    for _gap, x, y, text in sorted(labels, key=lambda item: -item[0]):
        if any(math.hypot(x - px, y - py) < 22 for _t, px, py in placed):
            continue
        placed.append((text, x, y))
        canvas.text(
            x,
            y,
            text,
            **{
                "text-anchor": "middle",
                "dominant-baseline": "middle",
                "font-family": "DejaVu Sans, sans-serif",
                "font-size": "8",
                "fill": INK,
                "stroke": BG,
                "stroke-width": "3",
                "paint-order": "stroke",
            },
        )

    for item, rect in pieces:
        canvas.path(
            [rect],
            fill=FURN_FILL,
            stroke=FURN_EDGE,
            **{"stroke-width": "1.2", "stroke-linejoin": "miter"},
        )
        label = item.get("id") or ""
        if not label:
            continue
        cx = sum(point[0] for point in rect) / len(rect)
        cy = sum(point[1] for point in rect) / len(rect)
        sx, sy = canvas.xy((cx, cy))
        if any(math.hypot(sx - px, sy - py) < 18 for _text, px, py in placed):
            continue
        placed.append((label, sx, sy))
        canvas.text(
            sx,
            sy,
            label,
            **{
                "text-anchor": "middle",
                "dominant-baseline": "middle",
                "font-family": "DejaVu Sans, sans-serif",
                "font-size": "8",
                "fill": INK,
                "stroke": BG,
                "stroke-width": "3",
                "paint-order": "stroke",
            },
        )

    plain = sum(1 for opening in openings if kind_of(opening.get("id"), doors, windows) == "plain")
    title = (
        f"{filename} · {len(walls)} walls · {len(openings)} openings · "
        f"{len(doors)} doors · {len(windows)} windows · {plain} plain"
    )
    if pieces:
        title += f" · {len(pieces)} furnishings"
    canvas.text(
        MARGIN,
        26,
        title,
        **{
            "font-family": "DejaVu Sans, sans-serif",
            "font-size": "15",
            "fill": INK,
        },
    )

    bar_m = nice_metres(scale)
    bar_px = bar_m * scale
    x0 = MARGIN
    y0 = height - 18
    canvas.parts.append(
        f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x0 + bar_px:.1f}" y2="{y0:.1f}" '
        f'stroke="{INK}" stroke-width="2"/>'
    )
    for tick in (x0, x0 + bar_px):
        canvas.parts.append(
            f'<line x1="{tick:.1f}" y1="{y0 - 5:.1f}" x2="{tick:.1f}" y2="{y0 + 5:.1f}" '
            f'stroke="{INK}" stroke-width="1.4"/>'
        )
    label = f"{bar_m:g} m"
    canvas.text(
        x0 + bar_px + 8,
        y0 + 4,
        label,
        **{
            "font-family": "DejaVu Sans, sans-serif",
            "font-size": "12",
            "fill": INK,
        },
    )
    legend_x = x0 + bar_px + 72
    for index, (color, name) in enumerate(
        ((DOOR, "door"), (WINDOW, "window"), (PLAIN, "plain opening"))
    ):
        lx = legend_x + index * 118
        canvas.parts.append(
            f'<rect x="{lx:.1f}" y="{y0 - 8:.1f}" width="12" height="8" '
            f'fill="{color}" />'
        )
        canvas.text(
            lx + 16,
            y0 + 1,
            name,
            **{
                "font-family": "DejaVu Sans, sans-serif",
                "font-size": "11",
                "fill": MUTED,
            },
        )

    body = "\n".join(canvas.parts)
    svg = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">\n'
        f'<rect width="{width}" height="{height}" fill="{BG}"/>\n'
        f"{body}\n</svg>\n"
    )
    return svg


def write_png(svg_path, png_path):
    import cairosvg

    cairosvg.svg2png(url=str(svg_path), write_to=str(png_path))


def render_file(path, out_dir, png=True):
    doc = load_document(path)
    svg = render_document(doc, path.name)
    out_dir.mkdir(parents=True, exist_ok=True)
    svg_path = out_dir / f"{path.stem}.svg"
    svg_path.write_text(svg, encoding="utf-8")
    print(svg_path)
    if png:
        png_path = out_dir / f"{path.stem}.png"
        write_png(svg_path, png_path)
        print(png_path)


def main(argv):
    parser = argparse.ArgumentParser(description="Render yaml-ifc plans to SVG and PNG.")
    parser.add_argument("files", nargs="+", type=Path, help="yaml-ifc files")
    parser.add_argument("--out-dir", type=Path, default=Path("dist"))
    parser.add_argument(
        "--svg-only",
        action="store_true",
        help="skip the PNG (no Cairo needed)",
    )
    args = parser.parse_args(argv)
    failed = False
    for path in args.files:
        try:
            render_file(path, args.out_dir, png=not args.svg_only)
        except Exception as exc:
            print(f"{path}: {exc}", file=sys.stderr)
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
