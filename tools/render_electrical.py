#!/usr/bin/env python3
"""Draw devices and cable routes from a yaml-ifc electrical file.

Two views in one PNG: the storey plan, and an isometric. The plan draws
each wall as a centreline band. The isometric extrudes that footprint
from the floor to Height, with z up. A device is the box from Origin,
Width, Depth, and Elevation. A cable Route is a polyline in that same
frame, metres.
Needs libcairo2 and tools/requirements.txt (cairosvg).
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
INK = "#2b2824"
MUTED = "#6a645c"
DEVICE_FILL = {
    "lightFixtures": "#f0d56a",
    "switchingDevices": "#f4d4c4",
    "sensors": "#d9efe1",
    "outlets": "#d7e5f8",
    "actuators": "#e4d7f0",
    "distributionBoards": "#d5d8de",
}
DEVICE_EDGE = {
    "lightFixtures": "#a07b12",
    "switchingDevices": "#c45c26",
    "sensors": "#2a8f4a",
    "outlets": "#2a6fdb",
    "actuators": "#6b4c8a",
    "distributionBoards": "#3d4450",
}
CABLE_COLOR = {
    "LightingCable": "#c45c26",
    "PowerCable": "#2a6fdb",
    "SignalCable": "#2a8f4a",
}
DEVICE_KEYS = tuple(DEVICE_FILL)


def load_document(path):
    with path.open(encoding="utf-8") as handle:
        doc = yaml.safe_load(handle)
    if not isinstance(doc, dict):
        raise ValueError("file is not a yaml-ifc mapping")
    return doc


def _xy(point):
    return float(point[0]), float(point[1])


def wall_corners(wall):
    axis = wall.get("Axis") or {}
    start, end = axis.get("Start"), axis.get("End")
    if not start or not end:
        return None, 0.0
    sx, sy = _xy(start)
    ex, ey = _xy(end)
    dx, dy = ex - sx, ey - sy
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return None, 0.0
    thickness = float(wall.get("Thickness") or 0.02)
    px, py = -dy / length * thickness / 2.0, dx / length * thickness / 2.0
    corners = (
        (sx + px, sy + py),
        (ex + px, ey + py),
        (ex - px, ey - py),
        (sx - px, sy - py),
    )
    return corners, float(wall.get("Height") or 0.0)


def device_box(item):
    origin = item.get("Origin") or [0, 0]
    x, y = float(origin[0]), float(origin[1])
    z = float(item.get("Elevation") or 0)
    width = float(item.get("Width") or 0.08)
    depth = float(item.get("Depth") or 0.08)
    height = float(item.get("Height") or 0.08)
    return x, y, z, width, depth, height


def iso(x, y, z):
    """Plan x to the right, plan y to the left, z up.

    ``_fit`` treats the second axis as up and flips it into SVG. z is added
    so a higher Elevation lands higher on the page.
    """
    return (x - y) * 0.8660254037844386, z - (x + y) * 0.5


class Canvas:
    def __init__(self):
        self.parts = []

    def el(self, tag, **attrs):
        body = "".join(f' {key}="{value}"' for key, value in attrs.items())
        self.parts.append(f"<{tag}{body}/>")

    def text(self, x, y, content, **attrs):
        body = "".join(f' {key}="{value}"' for key, value in attrs.items())
        safe = xml_escape.escape(str(content))
        self.parts.append(f'<text x="{x:.1f}" y="{y:.1f}"{body}>{safe}</text>')

    def tag(self, x, y, content, fill, size=12, anchor="start"):
        width = max(len(str(content)), 1) * size * 0.62 + 6
        height = size + 3
        if anchor == "middle":
            rx = x - width / 2
        elif anchor == "end":
            rx = x - width
        else:
            rx = x
        self.el(
            "rect",
            x=f"{rx:.1f}",
            y=f"{y - size:.1f}",
            width=f"{width:.1f}",
            height=f"{height:.1f}",
            fill=BG,
            opacity="0.88",
        )
        self.text(
            x,
            y,
            content,
            **{
                "font-family": "DejaVu Sans, sans-serif",
                "font-size": str(size),
                "fill": fill,
                "text-anchor": anchor,
            },
        )


def _fit(points, x0, y0, width, height, pad):
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    spanx = max(maxx - minx, 1e-6)
    spany = max(maxy - miny, 1e-6)
    scale = min((width - 2 * pad) / spanx, (height - 2 * pad) / spany)

    def project(x, y):
        sx = x0 + pad + (x - minx) * scale
        sy = y0 + height - pad - (y - miny) * scale
        return sx, sy

    return project


def _points(seq):
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in seq)


def render_document(doc):
    walls = []
    for wall in doc.get("walls") or []:
        corners, height = wall_corners(wall)
        if corners:
            walls.append((corners, height, wall.get("id") or ""))
    devices = []
    for key in DEVICE_KEYS:
        for item in doc.get(key) or []:
            devices.append((key, item, device_box(item)))
    cables = []
    for cable in doc.get("cables") or []:
        route = cable.get("Route") or []
        if len(route) >= 2:
            cables.append(cable)

    top_points = []
    iso_points = []
    for corners, height, _wall_id in walls:
        top_points.extend(corners)
        for x, y in corners:
            iso_points.append(iso(x, y, 0))
            iso_points.append(iso(x, y, height))
    for _key, _item, (x, y, z, width, depth, height) in devices:
        for cx, cy, cz in (
            (x, y, z),
            (x + width, y + depth, z + height),
        ):
            top_points.append((cx, cy))
            iso_points.append(iso(cx, cy, cz))
    for cable in cables:
        for point in cable["Route"]:
            x, y, z = (float(value) for value in point)
            top_points.append((x, y))
            iso_points.append(iso(x, y, z))
    if not top_points:
        raise ValueError("nothing to draw")

    width, height = 1500, 820
    panel_w = 700
    left = 30
    right = 770
    top = 56
    panel_h = 700
    top_of = _fit(top_points, left, top, panel_w, panel_h, 48)
    iso_of = _fit(iso_points, right, top, panel_w, panel_h, 56)
    canvas = Canvas()
    font = "DejaVu Sans, sans-serif"

    def panel_title(x, y, title):
        canvas.text(x, y, title, **{"font-family": font, "font-size": "18", "fill": INK})

    panel_title(left, 34, "Top view")
    panel_title(right, 34, "Isometric")

    def draw_walls(project, isometric):
        if not isometric:
            for corners, _wall_height, _wall_id in walls:
                canvas.el(
                    "polygon",
                    points=_points(project(*corner) for corner in corners),
                    fill=WALL,
                    stroke=WALL_EDGE,
                    **{"stroke-width": "1"},
                )
            return
        # Wireframe extrusion: base at z=0, head at Height, vertical corners.
        # Filled side faces cover the room and hide the routes.
        ordered = sorted(walls, key=lambda row: sum(x + y for x, y in row[0]) / len(row[0]), reverse=True)
        for corners, wall_height, _wall_id in ordered:
            base = [project(*iso(x, y, 0.0)) for x, y in corners]
            top = [project(*iso(x, y, wall_height)) for x, y in corners]
            canvas.el(
                "polygon",
                points=_points(base),
                fill="none",
                stroke=WALL_EDGE,
                **{"stroke-width": "1.2"},
            )
            for start, end in zip(base, top):
                canvas.el(
                    "line",
                    x1=f"{start[0]:.1f}",
                    y1=f"{start[1]:.1f}",
                    x2=f"{end[0]:.1f}",
                    y2=f"{end[1]:.1f}",
                    stroke=WALL_EDGE,
                    **{"stroke-width": "1.6"},
                )
            canvas.el(
                "polygon",
                points=_points(top),
                fill=WALL,
                stroke=WALL_EDGE,
                **{"stroke-width": "1.6"},
            )

    def draw_routes(project, isometric):
        for cable in cables:
            color = CABLE_COLOR.get(cable.get("ObjectType"), INK)
            mapped = []
            for point in cable["Route"]:
                x, y, z = (float(value) for value in point)
                mapped.append(project(x, y) if not isometric else project(*iso(x, y, z)))
            canvas.el(
                "polyline",
                points=_points(mapped),
                fill="none",
                stroke=color,
                **{"stroke-width": "3.2", "stroke-linejoin": "round", "stroke-linecap": "round"},
            )
            end = mapped[-1]
            canvas.el(
                "circle",
                cx=f"{end[0]:.1f}",
                cy=f"{end[1]:.1f}",
                r="3.2",
                fill=color,
            )
            if isometric:
                continue
            # Name the run at the top of the drop, on the wall, clear of the device tag.
            mark = mapped[-3] if len(mapped) >= 3 else mapped[0]
            canvas.tag(mark[0] + 6, mark[1] - 4, cable.get("id") or "", color, size=11)

    def draw_devices(project, isometric):
        ordered = devices
        if isometric:
            ordered = sorted(devices, key=lambda row: row[2][0] + row[2][1], reverse=True)
        for key, item, (x, y, z, box_w, box_d, box_h) in ordered:
            fill = DEVICE_FILL[key]
            edge = DEVICE_EDGE[key]
            name = item.get("id") or ""
            if not isometric:
                rect = (
                    project(x, y),
                    project(x + box_w, y),
                    project(x + box_w, y + box_d),
                    project(x, y + box_d),
                )
                canvas.el(
                    "polygon",
                    points=_points(rect),
                    fill=fill,
                    stroke=edge,
                    **{"stroke-width": "1.4"},
                )
                centre = project(x + box_w / 2.0, y + box_d / 2.0)
                canvas.tag(centre[0], centre[1] - 8, name, INK, size=11, anchor="middle")
                continue
            xs = (x, x + box_w)
            ys = (y, y + box_d)
            zs = (z, z + box_h)
            corners = {
                (ix, iy, iz): project(*iso(px, py, pz))
                for ix, px in enumerate(xs)
                for iy, py in enumerate(ys)
                for iz, pz in enumerate(zs)
            }
            # Top, the west face, and the south face: the three sides toward the viewer.
            faces = (
                ((0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)),
                ((0, 0, 0), (0, 1, 0), (0, 1, 1), (0, 0, 1)),
                ((0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)),
            )
            for face in faces:
                canvas.el(
                    "polygon",
                    points=_points(corners[index] for index in face),
                    fill=fill,
                    stroke=edge,
                    **{"stroke-width": "1"},
                )
            label = corners[(0, 0, 1)]
            canvas.tag(label[0] + 4, label[1] - 2, name, INK, size=11)

    for isometric, project in ((False, top_of), (True, iso_of)):
        draw_walls(project, isometric)
        draw_routes(project, isometric)
        draw_devices(project, isometric)

    legend_y = height - 28
    legend = (
        (CABLE_COLOR["LightingCable"], "lighting"),
        (CABLE_COLOR["PowerCable"], "power"),
        (CABLE_COLOR["SignalCable"], "signal"),
    )
    canvas.text(
        left,
        legend_y,
        "routes",
        **{"font-family": font, "font-size": "12", "fill": MUTED},
    )
    for index, (color, name) in enumerate(legend):
        lx = left + 70 + index * 120
        canvas.el(
            "line",
            x1=f"{lx:.1f}",
            y1=f"{legend_y - 4:.1f}",
            x2=f"{lx + 22:.1f}",
            y2=f"{legend_y - 4:.1f}",
            stroke=color,
            **{"stroke-width": "3"},
        )
        canvas.text(
            lx + 28,
            legend_y,
            name,
            **{"font-family": font, "font-size": "12", "fill": MUTED},
        )

    body = "\n".join(canvas.parts)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">\n'
        f'<rect width="{width}" height="{height}" fill="{BG}"/>\n'
        f"{body}\n</svg>\n"
    )


def write_png(svg, png_path):
    import cairosvg

    cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to=str(png_path))


def main(argv):
    parser = argparse.ArgumentParser(description="Render devices and cable routes.")
    parser.add_argument("file", type=Path, help="yaml-ifc file")
    parser.add_argument("-o", "--out", type=Path, required=True, help="PNG path")
    args = parser.parse_args(argv)
    svg = render_document(load_document(args.file))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_png(svg, args.out)
    print(args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
