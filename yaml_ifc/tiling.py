"""Ceramic tile layout on one sloped plane.

The floor is a single plane: ``z = Elevation + Gradient · (point − Origin)``.
``Gradient`` is rise over plan run, ``(dz/dx, dz/dy)``. There is no valley.

Wall joints are authored. Floor joints are wider, measured on the slope, so
that one floor module projects to the same plan pitch as the wall module.
A tile on the slope is shorter in plan by ``1/sqrt(1+g²)``. The extra joint
width is ``(wall_tile + wall_joint) * (sqrt(1+g²) − 1)`` when the ceramic
sizes match, which is a few hundredths of a millimetre at a one-percent slope.

The bottom course is cut to that plane (``BottomCut: follow-slope``). Each
bottom tile is a trapezoid: the top edge stays level, the bottom edge follows
the floor, and the gap to the floor is a constant vertical ``BottomJoint``.
A level bottom would open that gap by the fall across one tile.
"""

import math
from collections import namedtuple

from shapely.geometry import Point, Polygon

from yaml_ifc.yamlio import num

FloorJoints = namedtuple(
    "FloorJoints",
    (
        "x",
        "y",
        "extra_x",
        "extra_y",
        "plan_pitch_x",
        "plan_pitch_y",
        "plan_tile_x",
        "plan_tile_y",
        "plan_joint_x",
        "plan_joint_y",
    ),
)

BOTTOM_CUT = "follow-slope"
_EPS = 1e-9


def plane_elevation(plane, x, y):
    """Finished-surface elevation at a plan point.

    ``plane`` is ``Origin``, ``Elevation``, and ``Gradient``.
    """
    origin_x, origin_y = plane["Origin"]
    gradient_x, gradient_y = plane["Gradient"]
    return (
        float(plane["Elevation"])
        + float(gradient_x) * (float(x) - float(origin_x))
        + float(gradient_y) * (float(y) - float(origin_y))
    )


def surface_per_plan(gradient):
    """Surface length of one metre in plan, along a line of gradient ``g``."""
    return math.hypot(1.0, float(gradient))


def floor_joint_widths(floor_tile, wall_tile, wall_joint, gradient):
    """Floor joint widths, measured on the slope, that line up with the wall.

    ``floor_tile`` and ``wall_tile`` are ``(x, y)`` ceramic sizes in metres.
    The wall size is the horizontal module (a portrait 600×1200 tile is
    0.6 in both plan axes). ``wall_joint`` is the wall grout in metres,
    measured in plan because the wall is vertical. ``gradient`` is
    ``(dz/dx, dz/dy)``.

    Plan pitch of the wall is ``wall_tile + wall_joint``. A floor tile of
    surface length ``t`` on gradient ``g`` covers ``t / sqrt(1+g²)`` in plan.
    The floor joint, also measured on the slope, makes one floor module
    project to that same plan pitch.

    ``extra_x`` and ``extra_y`` are the floor joint minus ``wall_joint``.
    """
    floor_x, floor_y = (float(v) for v in floor_tile)
    wall_x, wall_y = (float(v) for v in wall_tile)
    joint = float(wall_joint)
    gradient_x, gradient_y = (float(v) for v in gradient)
    if min(floor_x, floor_y, wall_x, wall_y) <= 0 or joint < 0:
        raise ValueError("tile sizes must be positive and the wall joint must not be negative")
    stretch_x = surface_per_plan(gradient_x)
    stretch_y = surface_per_plan(gradient_y)
    pitch_x = wall_x + joint
    pitch_y = wall_y + joint
    joint_x = pitch_x * stretch_x - floor_x
    joint_y = pitch_y * stretch_y - floor_y
    plan_tile_x = floor_x / stretch_x
    plan_tile_y = floor_y / stretch_y
    return FloorJoints(
        x=joint_x,
        y=joint_y,
        extra_x=joint_x - joint,
        extra_y=joint_y - joint,
        plan_pitch_x=pitch_x,
        plan_pitch_y=pitch_y,
        plan_tile_x=plan_tile_x,
        plan_tile_y=plan_tile_y,
        plan_joint_x=pitch_x - plan_tile_x,
        plan_joint_y=pitch_y - plan_tile_y,
    )


def plane_minmax(plane, points):
    """Min and max elevation of a plane over a list of plan points.

    On a single plane the extremes sit at vertices.
    """
    elevations = [plane_elevation(plane, x, y) for x, y in points]
    return min(elevations), max(elevations)


def course_levels(z_min, tile_height, joint, bottom_joint, courses):
    """Shared horizontal course lines, measured from the lowest floor point.

    The bottom tile is a full blank at that low point and shorter everywhere
    else, so no course needs a tile taller than the blank. ``head`` is the
    top of the last course. One level is used on every wall, so the joint
    between courses does not step at the corners.
    """
    courses = int(courses)
    if courses < 1:
        raise ValueError("Courses must be at least 1")
    tile_height = float(tile_height)
    joint = float(joint)
    bottom_joint = float(bottom_joint)
    if tile_height <= 0 or joint < 0 or bottom_joint < 0:
        raise ValueError("course sizes must be positive")
    bottom_top = float(z_min) + bottom_joint + tile_height
    tops = [bottom_top]
    top = bottom_top
    for _ in range(1, courses):
        top = top + joint + tile_height
        tops.append(top)
    return {"bottom_top": bottom_top, "head": tops[-1], "course_tops": tops}


def _cells_1d(origin, pitch, tile_length, low, high):
    """Tile and joint intervals along one axis.

    Module boundaries fall on ``origin + n * pitch``. In each module the
    tile sits against the boundary closer to ``origin``; the joint is the
    rest. A short module at the far end is a cut tile and has no joint.
    """
    origin = float(origin)
    pitch = float(pitch)
    tile_length = float(tile_length)
    low = float(low)
    high = float(high)
    if pitch <= _EPS or tile_length <= _EPS:
        raise ValueError("pitch and tile length must be positive")
    if high - low <= _EPS:
        return []
    n0 = math.floor((low - origin) / pitch)
    n1 = math.ceil((high - origin) / pitch)
    bounds = [origin + n * pitch for n in range(n0, n1 + 1)]
    cells = []
    for left, right in zip(bounds, bounds[1:]):
        clip_left = max(left, low)
        clip_right = min(right, high)
        if clip_right - clip_left <= _EPS:
            continue
        if abs(right - origin) <= abs(left - origin):
            tile_left = right - tile_length
            tile_right = right
        else:
            tile_left = left
            tile_right = left + tile_length
        tile_left = max(tile_left, clip_left)
        tile_right = min(tile_right, clip_right)
        if tile_right - tile_left <= _EPS:
            continue
        joints = []
        if tile_left - clip_left > _EPS:
            joints.append((clip_left, tile_left))
        if clip_right - tile_right > _EPS:
            joints.append((tile_right, clip_right))
        cells.append({"tile": (tile_left, tile_right), "joints": joints})
    return cells


def _ring(coords):
    points = [(float(x), float(y)) for x, y in coords]
    if len(points) >= 2 and points[0] == points[-1]:
        points = points[:-1]
    start = min(range(len(points)), key=lambda index: (points[index][0], points[index][1]))
    points = points[start:] + points[:start]
    area = 0.0
    for index, point in enumerate(points):
        nxt = points[(index + 1) % len(points)]
        area += point[0] * nxt[1] - nxt[0] * point[1]
    if area < 0:
        points.reverse()
        start = min(range(len(points)), key=lambda index: (points[index][0], points[index][1]))
        points = points[start:] + points[:start]
    return points


def _axis_aligned(polygon):
    coords = list(polygon.exterior.coords)
    for ring in polygon.interiors:
        coords.extend(ring.coords)
    for (x0, y0), (x1, y1) in zip(coords, coords[1:]):
        if abs(x0 - x1) > 1e-8 and abs(y0 - y1) > 1e-8:
            return False
    return True


def _explode(polygon):
    """Simple polygons covering ``polygon``, holes included as gaps.

    An orthogonal polygon (a rectangle, an L, a rectangle with a rectangular
    drain) becomes rectangles. Anything else is the exterior ring, and a
    hole in a non-orthogonal outline is rejected rather than filled in.
    """
    if polygon.is_empty or polygon.area <= _EPS:
        return []
    parts = []
    geoms = list(polygon.geoms) if polygon.geom_type == "MultiPolygon" else [polygon]
    for geom in geoms:
        if geom.area <= _EPS:
            continue
        if _axis_aligned(geom):
            coords = list(geom.exterior.coords)
            for ring in geom.interiors:
                coords.extend(ring.coords)
            xs = sorted({round(x, 9) for x, _y in coords})
            ys = sorted({round(y, 9) for _x, y in coords})
            for x0, x1 in zip(xs, xs[1:]):
                for y0, y1 in zip(ys, ys[1:]):
                    if x1 - x0 <= _EPS or y1 - y0 <= _EPS:
                        continue
                    if geom.contains(Point((x0 + x1) / 2.0, (y0 + y1) / 2.0)):
                        parts.append([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
            continue
        if geom.interiors:
            raise ValueError("a tile cutout leaves a hole that is not a rectangular notch")
        parts.append(_ring(geom.exterior.coords))
    parts.sort(key=lambda ring: (ring[0][0], ring[0][1], ring[1][0], ring[1][1]))
    return parts


def _region(footprint, cutouts, inset):
    room = Polygon([(float(x), float(y)) for x, y in footprint])
    if not room.is_valid:
        room = room.buffer(0)
    holes = []
    for cutout in cutouts or []:
        hole = Polygon([(float(x), float(y)) for x, y in cutout])
        if inset:
            hole = hole.buffer(float(inset), join_style="mitre")
        holes.append(hole)
    if holes:
        room = room.difference(holes[0] if len(holes) == 1 else holes[0].union(*holes[1:]))
    return room


def _clip_rect(rect, region):
    x0, y0, x1, y1 = rect
    tile = Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
    return _explode(tile.intersection(region))


def floor_layout(plane, floor_tile, wall_tile, wall_joint, grid_origin, footprint, cutouts=(), joint_inset=0.0):
    """Plan tiles and grout for one room.

    ``grid_origin`` is a module boundary in plan (a corner of the grid, not
    necessarily a tile corner). Tiles are clipped to ``footprint`` minus
    ``cutouts``. ``joint_inset`` widens each cutout by that much, which is
    the silicone joint around a grate. The grate itself is not a tile.
    """
    joints = floor_joint_widths(floor_tile, wall_tile, wall_joint, plane["Gradient"])
    if joints.x < -_EPS or joints.y < -_EPS:
        raise ValueError("floor joint would be negative; the floor tile is longer than the wall module")
    region = _region(footprint, cutouts, joint_inset)
    min_x, min_y, max_x, max_y = region.bounds
    origin_x, origin_y = grid_origin
    tiles = []
    grout = []
    cells_x = _cells_1d(origin_x, joints.plan_pitch_x, joints.plan_tile_x, min_x, max_x)
    cells_y = _cells_1d(origin_y, joints.plan_pitch_y, joints.plan_tile_y, min_y, max_y)
    for cell_x in cells_x:
        for cell_y in cells_y:
            x0, x1 = cell_x["tile"]
            y0, y1 = cell_y["tile"]
            tiles.extend(_clip_rect((x0, y0, x1, y1), region))
            for jx0, jx1 in cell_x["joints"]:
                # The crossing belongs to the joint that runs in Y, below.
                grout.extend(_clip_rect((jx0, y0, jx1, y1), region))
            for jy0, jy1 in cell_y["joints"]:
                grout.extend(_clip_rect((x0, jy0, x1, jy1), region))
                for jx0, jx1 in cell_x["joints"]:
                    grout.extend(_clip_rect((jx0, jy0, jx1, jy1), region))
    return {"joints": joints, "tiles": tiles, "grout": grout}


def _unit(start, end):
    dx = float(end[0]) - float(start[0])
    dy = float(end[1]) - float(start[1])
    length = math.hypot(dx, dy)
    if length <= _EPS:
        raise ValueError("wall axis has zero length")
    return dx / length, dy / length, length


def _inward(start, direction, inside):
    _dx, _dy = direction
    dx, dy = direction
    normal = (-dy, dx)
    mid_x = float(start[0])
    mid_y = float(start[1])
    toward = (float(inside[0]) - mid_x) * normal[0] + (float(inside[1]) - mid_y) * normal[1]
    if abs(toward) <= _EPS:
        raise ValueError("Inside is on the wall line")
    if toward < 0:
        normal = (dy, -dx)
    return normal


def _wall_frame(axis, inside):
    start = axis["Start"]
    end = axis["End"]
    dx, dy, length = _unit(start, end)
    if abs(dx) > 1e-8 and abs(dy) > 1e-8:
        raise ValueError("wall tile axes must be parallel to X or Y")
    return {
        "start": (float(start[0]), float(start[1])),
        "dx": dx,
        "dy": dy,
        "length": length,
        "normal": _inward(start, (dx, dy), inside),
    }


def _s_of(frame, x):
    """Parameter along the wall for a plan coordinate on its axis."""
    if abs(frame["dx"]) >= abs(frame["dy"]):
        return (float(x) - frame["start"][0]) / frame["dx"]
    return (float(x) - frame["start"][1]) / frame["dy"]


def _plan_of(frame, along):
    return (
        frame["start"][0] + frame["dx"] * along,
        frame["start"][1] + frame["dy"] * along,
    )


def _subtract_intervals(span, cuts):
    """``span`` minus ``cuts``, both as ``(a, b)`` intervals."""
    pieces = [span]
    for cut_a, cut_b in cuts:
        nxt = []
        for left, right in pieces:
            if cut_b <= left + _EPS or cut_a >= right - _EPS:
                nxt.append((left, right))
                continue
            if cut_a > left + _EPS:
                nxt.append((left, cut_a))
            if cut_b < right - _EPS:
                nxt.append((cut_b, right))
        pieces = nxt
    return [(left, right) for left, right in pieces if right - left > _EPS]


def wall_layout(
    plane,
    tile,
    joint,
    courses,
    bottom_joint,
    grid_origin,
    axis,
    inside,
    openings=(),
    z_min=None,
    footprint=None,
):
    """Wall tiles for one straight run.

    ``tile`` is ``(along, height)`` of the ceramic. ``joint`` is the wall
    grout. ``grid_origin`` is the same plan point the floor uses, so the
    vertical joints share the floor's module boundaries.

    ``z_min``, when omitted, is the lowest plane elevation on ``footprint``.
    Every wall in a room should pass the same value so the course lines match.
    A door (``SillHeight`` 0) is void down to the floor. A window keeps the
    tiles below its sill.
    """
    if bottom_joint is None:
        raise ValueError("BottomJoint is required")
    frame = _wall_frame(axis, inside)
    width, height = (float(v) for v in tile)
    joint = float(joint)
    bottom_joint = float(bottom_joint)
    if width <= 0 or height <= 0 or joint < 0:
        raise ValueError("wall tile sizes must be positive")
    if z_min is None:
        if not footprint:
            raise ValueError("wall layout needs z_min or a footprint")
        z_min, _z_max = plane_minmax(plane, footprint)
    levels = course_levels(z_min, height, joint, bottom_joint, courses)
    along_is_x = abs(frame["dx"]) >= abs(frame["dy"])
    origin = float(grid_origin[0] if along_is_x else grid_origin[1])
    pitch = width + joint
    end_coord = _plan_of(frame, frame["length"])
    start_coord = frame["start"][0] if along_is_x else frame["start"][1]
    end_value = end_coord[0] if along_is_x else end_coord[1]
    low = min(start_coord, end_value)
    high = max(start_coord, end_value)
    cells = _cells_1d(origin, pitch, width, low, high)

    def s_interval(a, b):
        s0 = _s_of(frame, a)
        s1 = _s_of(frame, b)
        return (min(s0, s1), max(s0, s1))

    opening_rows = []
    for opening in openings or []:
        along = float(opening["AlongAxis"])
        gap = float(opening["Width"])
        sill = float(opening.get("SillHeight") or 0)
        if opening.get("Height") is None:
            raise ValueError("a tile opening needs Height")
        head = sill + float(opening["Height"])
        # A sill at the datum is a door: the void continues down the slope.
        z0 = -1e6 if sill <= _EPS else sill
        opening_rows.append((along, along + gap, z0, head))

    tiles = []
    grout = []

    def add_tile(s0, s1, z_bottom, z_top, course):
        if s1 - s0 <= _EPS or z_top - z_bottom <= _EPS:
            return
        # Openings that cover this whole s-span remove a z band.
        blocked = []
        for left, right, z0, z1 in opening_rows:
            if left <= s0 + 1e-8 and right >= s1 - 1e-8:
                blocked.append((z0, z1))
        for z_lo, z_hi in _subtract_intervals((z_bottom, z_top), blocked):
            tiles.append(
                {
                    "course": course,
                    "polygon": [(s0, z_lo), (s1, z_lo), (s1, z_hi), (s0, z_hi)],
                }
            )

    def add_grout(s0, s1, z0, z1, course):
        if s1 - s0 <= _EPS or z1 - z0 <= _EPS:
            return
        blocked = []
        for left, right, bz0, bz1 in opening_rows:
            if left <= s0 + 1e-8 and right >= s1 - 1e-8:
                blocked.append((bz0, bz1))
        for gz0, gz1 in _subtract_intervals((z0, z1), blocked):
            grout.append(
                {
                    "course": course,
                    "polygon": [(s0, gz0), (s1, gz0), (s1, gz1), (s0, gz1)],
                }
            )

    # Bottom course: the lower edge follows the floor. Split on opening edges
    # so a door removes the whole piece and a window does not.
    edges = {0.0, frame["length"]}
    for cell in cells:
        for value in cell["tile"]:
            edges.add(s_interval(value, value)[0])
        for joint_span in cell["joints"]:
            for value in joint_span:
                edges.add(s_interval(value, value)[0])
    for left, right, _z0, _z1 in opening_rows:
        edges.add(max(0.0, min(frame["length"], left)))
        edges.add(max(0.0, min(frame["length"], right)))
    ordered = sorted(edge for edge in edges if -1e-8 <= edge <= frame["length"] + 1e-8)
    spans = []
    for left, right in zip(ordered, ordered[1:]):
        if right - left > _EPS:
            spans.append((left, right))

    def floor_z(along):
        x, y = _plan_of(frame, along)
        return plane_elevation(plane, x, y) + bottom_joint

    def is_joint_span(s0, s1):
        mid = (s0 + s1) / 2.0
        for cell in cells:
            for j0, j1 in cell["joints"]:
                gs0, gs1 = s_interval(j0, j1)
                if gs0 - 1e-8 <= mid <= gs1 + 1e-8:
                    return True
        return False

    bottom_top = levels["bottom_top"]
    for s0, s1 in spans:
        if is_joint_span(s0, s1):
            continue
        z0 = floor_z(s0)
        z1 = floor_z(s1)
        z_lo = min(z0, z1)
        if bottom_top - z_lo <= _EPS:
            continue
        # Openings split these spans, so each span is wholly inside or outside.
        inside = None
        for left, right, oz0, oz1 in opening_rows:
            if left <= s0 + 1e-8 and right >= s1 - 1e-8 and oz0 <= z_lo + 1e-8 and oz1 >= bottom_top - 1e-8:
                inside = True
                break
            if left <= s0 + 1e-8 and right >= s1 - 1e-8 and oz1 > z_lo + _EPS and oz0 < bottom_top - _EPS:
                inside = (oz0, oz1)
        if inside is True:
            continue
        if inside is None:
            tiles.append(
                {
                    "course": 0,
                    "polygon": [(s0, z0), (s1, z1), (s1, bottom_top), (s0, bottom_top)],
                    "sloped": True,
                }
            )
            continue
        oz0, oz1 = inside
        if oz0 > z_lo + _EPS:
            tiles.append(
                {
                    "course": 0,
                    "polygon": [
                        (s0, z0),
                        (s1, z1),
                        (s1, min(oz0, bottom_top)),
                        (s0, min(oz0, bottom_top)),
                    ],
                    "sloped": True,
                }
            )
        if oz1 < bottom_top - _EPS:
            tiles.append(
                {
                    "course": 0,
                    "polygon": [(s0, oz1), (s1, oz1), (s1, bottom_top), (s0, bottom_top)],
                    "sloped": False,
                }
            )

    def add_sloped_grout(s0, s1):
        z0 = floor_z(s0)
        z1 = floor_z(s1)
        z_lo = min(z0, z1)
        for left, right, oz0, oz1 in opening_rows:
            if left <= s0 + 1e-8 and right >= s1 - 1e-8 and oz0 <= z_lo + 1e-8 and oz1 >= bottom_top - 1e-8:
                return
        grout.append(
            {
                "course": 0,
                "polygon": [(s0, z0), (s1, z1), (s1, bottom_top), (s0, bottom_top)],
            }
        )

    for s0, s1 in spans:
        if is_joint_span(s0, s1):
            add_sloped_grout(s0, s1)

    # Courses above the bottom one are rectangles between level lines.
    # The vertical joint continues through the horizontal joint, so the
    # crossing is grout once.
    previous = bottom_top
    for course in range(1, int(courses)):
        joint_top = previous + joint
        course_top = levels["course_tops"][course]
        for s0, s1 in spans:
            if is_joint_span(s0, s1):
                add_grout(s0, s1, previous, course_top, course)
            else:
                add_grout(s0, s1, previous, joint_top, course)
                add_tile(s0, s1, joint_top, course_top, course)
        previous = course_top

    return {"frame": frame, "levels": levels, "tiles": tiles, "grout": grout, "pitch": pitch}


def sloped_shell(ring, z_at, thickness, gradient):
    """A tile prism. The top follows ``z_at``; thickness is along the downward normal."""
    gx, gy = (float(v) for v in gradient)
    normal = (-gx, -gy, 1.0)
    scale = math.hypot(*normal)
    offset = tuple(-float(thickness) * component / scale for component in normal)
    top = [(float(x), float(y), float(z_at(x, y))) for x, y in ring]
    return _prism(top, offset)


def wall_shell(polygon, frame, thickness):
    """Extrude a wall-plane polygon ``(along, z)`` into the room by ``thickness``."""
    nx, ny = frame["normal"]
    top = []
    for along, z in polygon:
        x = frame["start"][0] + frame["dx"] * along
        y = frame["start"][1] + frame["dy"] * along
        top.append((x, y, float(z)))
    offset = (nx * float(thickness), ny * float(thickness), 0.0)
    return _prism(top, offset)


def _prism(top, offset):
    count = len(top)
    bottom = [
        (point[0] + offset[0], point[1] + offset[1], point[2] + offset[2]) for point in top
    ]
    vertices = top + bottom
    faces = [list(range(count))]
    faces.append(list(range(2 * count - 1, count - 1, -1)))
    for index in range(count):
        nxt = (index + 1) % count
        faces.append([index, nxt, nxt + count, index + count])
    if _volume(vertices, faces) < 0:
        faces = [list(reversed(face)) for face in faces]
    return vertices, faces


def _volume(vertices, faces):
    total = 0.0
    for face in faces:
        for index in range(1, len(face) - 1):
            ax, ay, az = vertices[face[0]]
            bx, by, bz = vertices[face[index]]
            cx, cy, cz = vertices[face[index + 1]]
            total += ax * (by * cz - bz * cy) + ay * (bz * cx - bx * cz) + az * (bx * cy - by * cx)
    return total / 6.0


def mesh_volume(vertices, faces):
    return _volume(vertices, faces)


def _fmt(value):
    text = format(round(float(value), 6), ".6f").rstrip("0").rstrip(".")
    if text in ("", "-0", "-"):
        return "0"
    return text


def encode_points(points):
    return " ".join(f"{_fmt(x)},{_fmt(y)}" for x, y in points)


def decode_points(text):
    points = []
    for pair in str(text).split():
        x, y = pair.split(",")
        points.append([num(x), num(y)])
    return points


def encode_cutouts(cutouts):
    return "/".join(encode_points(ring) for ring in cutouts)


def decode_cutouts(text):
    return [decode_points(part) for part in str(text).split("/") if part]


def encode_openings(openings):
    rows = []
    for opening in openings:
        sill = opening.get("SillHeight") or 0
        rows.append(
            ",".join(
                _fmt(value)
                for value in (
                    opening["AlongAxis"],
                    opening["Width"],
                    sill,
                    opening["Height"],
                )
            )
        )
    return "|".join(rows)


def decode_openings(text):
    rows = []
    for part in str(text).split("|"):
        if not part:
            continue
        along, width, sill, height = (num(value) for value in part.split(","))
        rows.append(
            {
                "AlongAxis": along,
                "Width": width,
                "SillHeight": sill,
                "Height": height,
            }
        )
    return rows
