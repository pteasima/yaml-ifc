"""Find wall joints and snap axes onto the centre-line intersection.

This is a one-off edit of a YAML file. ``to_ifc`` and ``from_ifc`` never call it.
"""

import math
from copy import deepcopy

from yaml_ifc.yamlio import num

# The gap from an endpoint to the intersection is half the other wall's
# thickness when the axis stops on that wall's face. A tenth of a millimetre
# covers float noise on top of that.
ENDPOINT_SLACK = 1e-4
# An intersection this far inside an end is still that end, not a T.
OVERSHOOT = 0.01
# Report pairs that miss the tolerance by up to this much.
NEAR_MISS = 0.08
# Two walls at one end: keep the nearer when it leads by at least this much.
CLEAR_GAP = 0.02
# Parallel centre-lines closer than this, with ends no further apart, are
# continuations rather than corners. They are listed and left unchanged.
COLLINEAR_OFFSET = 0.05
COLLINEAR_GAP = 0.6


def detect_connections(doc):
    """Return ``(document, report)``.

    The document is a copy. Endpoints within half the other wall's thickness
    of a centre-line intersection are moved onto that intersection. Moving a
    wall's ``Start`` shifts each hosted opening's ``AlongAxis`` by the same
    amount, so the opening stays at the same plan point.

    At an L, the thicker wall is the relating wall (it runs through); equal
    thickness then prefers the longer wall, then the lower id. At a T, the
    wall that is joined into is the relating wall and its type is ``ATPATH``.
    """
    doc = deepcopy(doc)
    walls = _walls(doc)
    openings = doc.get("openings") or []
    joins, skipped = _candidates(walls)
    joins, ambiguous = _drop_ambiguous(joins)
    skipped.extend(ambiguous)

    original = {wall["id"]: (wall["s"], wall["e"]) for wall in walls}
    snaps = {}
    for join in joins:
        for wall, kind in ((join["a"], join["type_a"]), (join["b"], join["type_b"])):
            if kind == "ATPATH":
                continue
            snaps[(wall["id"], kind)] = join["point"]

    by_id = {wall["id"]: wall for wall in walls}
    for (wall_id, kind), point in snaps.items():
        wall = by_id[wall_id]
        snapped = (num(point[0]), num(point[1]))
        if kind == "ATSTART":
            wall["s"] = snapped
        else:
            wall["e"] = snapped

    swapped = set()
    for wall in walls:
        start, end, did_swap = _order(wall["s"], wall["e"])
        wall["s"], wall["e"] = start, end
        _refresh(wall)
        if did_swap:
            swapped.add(wall["id"])

    # Snapping can bring a second wall inside the tolerance. Say so, and keep
    # the join already chosen: a second pass prefers that nearer gap of zero.
    _post, post_notes = _drop_ambiguous(_candidates(walls)[0])
    seen = {item["detail"] for item in skipped}
    for note in post_notes:
        if note["detail"] not in seen:
            skipped.append(note)
            seen.add(note["detail"])

    connections = []
    for join in joins:
        relating, related = _orient(join)
        connections.append(
            {
                "RelatingElement": relating["id"],
                "RelatingConnectionType": _type_of(join, relating["id"], swapped),
                "RelatedElement": related["id"],
                "RelatedConnectionType": _type_of(join, related["id"], swapped),
            }
        )
    connections.sort(
        key=lambda row: (
            row["RelatingElement"],
            row["RelatingConnectionType"],
            row["RelatedElement"],
            row["RelatedConnectionType"],
        )
    )

    _shift_openings(openings, original, by_id)
    rebuilt = _with_connections(_apply(doc, by_id), connections)
    report = {
        "connections": connections,
        "skipped": skipped,
        "counts": _counts(connections),
    }
    return rebuilt, report


def format_report(report):
    counts = report["counts"]
    lines = [
        f"connections: {len(report['connections'])}"
        f" (L {counts['L']}, T {counts['T']})",
    ]
    notes = report["skipped"]
    skipped = [item for item in notes if item["kind"] != "also-near"]
    near = [item for item in notes if item["kind"] == "also-near"]
    if not skipped:
        lines.append("skipped: none")
    else:
        lines.append(f"skipped: {len(skipped)}")
        for item in skipped:
            lines.append(f"- {item['kind']}: {item['detail']}")
    if near:
        lines.append(f"also near after snapping: {len(near)}")
        for item in near:
            lines.append(f"- {item['detail']}")
    return "\n".join(lines) + "\n"


def _counts(connections):
    tee = sum(1 for row in connections if row["RelatingConnectionType"] == "ATPATH")
    return {"T": tee, "L": len(connections) - tee}


def _walls(doc):
    found = []
    for wall in doc.get("walls") or []:
        axis = wall.get("Axis") or {}
        start, end = axis.get("Start"), axis.get("End")
        if not start or not end:
            continue
        sx, sy = float(start[0]), float(start[1])
        ex, ey = float(end[0]), float(end[1])
        dx, dy = ex - sx, ey - sy
        length = math.hypot(dx, dy)
        if length < 1e-9:
            continue
        found.append(
            {
                "id": wall["id"],
                "s": (sx, sy),
                "e": (ex, ey),
                "dx": dx,
                "dy": dy,
                "L": length,
                "t": None if wall.get("Thickness") is None else float(wall["Thickness"]),
            }
        )
    return found


def _candidates(walls):
    joins = []
    skipped = []
    for index, left in enumerate(walls):
        for right in walls[index + 1 :]:
            if _parallel(left, right):
                note = _collinear_note(left, right)
                if note:
                    skipped.append(note)
                continue
            hit = _intersect(left, right)
            if hit is None:
                continue
            point, ta, tb = hit
            if left["t"] is None or right["t"] is None:
                note = _missing_thickness(left, right, ta, tb)
                if note:
                    skipped.append(note)
                continue
            kind_l, gap_l = _classify(left, ta, right["t"])
            kind_r, gap_r = _classify(right, tb, left["t"])
            if kind_l is None or kind_r is None:
                note = _near_miss(left, right, ta, tb)
                if note:
                    skipped.append(note)
                continue
            if kind_l == "ATPATH" and kind_r == "ATPATH":
                skipped.append(
                    {
                        "kind": "crossing",
                        "detail": (
                            f"{left['id']} and {right['id']} cross away from both ends"
                            f" at ({_fmt(point[0])}, {_fmt(point[1])})"
                        ),
                    }
                )
                continue
            if kind_l == "AMBIGUOUS" or kind_r == "AMBIGUOUS":
                skipped.append(
                    {
                        "kind": "ambiguous-end",
                        "detail": (
                            f"{left['id']} and {right['id']} meet where a short wall"
                            " could use either end"
                        ),
                    }
                )
                continue
            joins.append(
                {
                    "a": left,
                    "b": right,
                    "type_a": kind_l,
                    "type_b": kind_r,
                    "gap_a": gap_l,
                    "gap_b": gap_r,
                    "point": point,
                }
            )
    return joins, skipped


def _gap_for(join, wall_id):
    return join["gap_a"] if join["a"]["id"] == wall_id else join["gap_b"]


def _other_id(join, wall_id):
    return join["b"]["id"] if join["a"]["id"] == wall_id else join["a"]["id"]


def _drop_ambiguous(joins):
    groups = {}
    for join in joins:
        for wall, kind in ((join["a"], join["type_a"]), (join["b"], join["type_b"])):
            if kind == "ATPATH":
                continue
            groups.setdefault((wall["id"], kind), []).append(join)
    rejected = set()
    notes = []
    for (wall_id, kind), group in groups.items():
        if len(group) < 2:
            continue
        ranked = sorted(group, key=lambda join: (_gap_for(join, wall_id), _other_id(join, wall_id)))
        best = _gap_for(ranked[0], wall_id)
        second = _gap_for(ranked[1], wall_id)
        nearer = _other_id(ranked[0], wall_id)
        others = [_other_id(join, wall_id) for join in ranked[1:]]
        if second - best >= CLEAR_GAP:
            for join in ranked[1:]:
                rejected.add(id(join))
            notes.append(
                {
                    "kind": "also-near",
                    "detail": (
                        f"{wall_id} {kind} kept the nearer wall {nearer}"
                        f" (gap {_fmt(best)} m); also within tolerance of {', '.join(others)}"
                    ),
                }
            )
            continue
        for join in ranked:
            rejected.add(id(join))
        names = [_other_id(join, wall_id) for join in ranked]
        notes.append(
            {
                "kind": "ambiguous-end",
                "detail": (
                    f"{wall_id} {kind} is within tolerance of {', '.join(names)}"
                    " with no clear nearest; left unjoined"
                ),
            }
        )
    return [join for join in joins if id(join) not in rejected], notes


def _orient(join):
    """The relating wall runs through. At a T that is the ATPATH wall."""
    if join["type_a"] == "ATPATH":
        return join["a"], join["b"]
    if join["type_b"] == "ATPATH":
        return join["b"], join["a"]
    left, right = join["a"], join["b"]
    if (left["t"], left["L"]) != (right["t"], right["L"]):
        winner = left if (left["t"], left["L"]) > (right["t"], right["L"]) else right
    else:
        winner = left if left["id"] < right["id"] else right
    loser = right if winner is left else left
    return winner, loser


def _type_of(join, wall_id, swapped):
    kind = join["type_a"] if join["a"]["id"] == wall_id else join["type_b"]
    if wall_id in swapped and kind in ("ATSTART", "ATEND"):
        return "ATEND" if kind == "ATSTART" else "ATSTART"
    return kind


def _classify(wall, parameter, other_thickness):
    along = parameter * wall["L"]
    tolerance = 0.5 * other_thickness + ENDPOINT_SLACK
    dist_start = abs(along)
    dist_end = abs(along - wall["L"])
    if dist_start <= tolerance and dist_end <= tolerance:
        return "AMBIGUOUS", min(dist_start, dist_end)
    if dist_start <= tolerance and along <= OVERSHOOT:
        return "ATSTART", dist_start
    if dist_end <= tolerance and along >= wall["L"] - OVERSHOOT:
        return "ATEND", dist_end
    if 0.0 <= along <= wall["L"]:
        return "ATPATH", 0.0
    return None, None


def _near_miss(left, right, ta, tb):
    loose_l, gap_l = _classify(left, ta, right["t"] + 2 * NEAR_MISS)
    loose_r, gap_r = _classify(right, tb, left["t"] + 2 * NEAR_MISS)
    if loose_l is None or loose_r is None or "AMBIGUOUS" in (loose_l, loose_r):
        return None
    if loose_l == "ATPATH" and loose_r == "ATPATH":
        return None
    real_l = 0.5 * right["t"] + ENDPOINT_SLACK
    real_r = 0.5 * left["t"] + ENDPOINT_SLACK
    gaps = []
    if loose_l in ("ATSTART", "ATEND"):
        gaps.append(gap_l)
    if loose_r in ("ATSTART", "ATEND"):
        gaps.append(gap_r)
    if not gaps or max(gaps) > max(real_l, real_r) + NEAR_MISS:
        return None
    # Inside the real tolerance this would already have been a join.
    if (loose_l == "ATPATH" or gap_l <= real_l) and (loose_r == "ATPATH" or gap_r <= real_r):
        return None
    return {
        "kind": "near-miss",
        "detail": (
            f"{left['id']} {loose_l} gap {_fmt(gap_l)} m (half of {right['id']} is"
            f" {_fmt(0.5 * right['t'])} m), {right['id']} {loose_r} gap {_fmt(gap_r)} m"
            f" (half of {left['id']} is {_fmt(0.5 * left['t'])} m)"
        ),
    }


def _missing_thickness(left, right, ta, tb):
    # No thickness means no face to stop on and no butt body. Report the
    # ones that would otherwise sit on a corner.
    for wall, other, parameter in ((left, right, ta), (right, left, tb)):
        if wall["t"] is not None:
            continue
        along = parameter * wall["L"]
        if min(abs(along), abs(along - wall["L"])) > 0.3 and not (0.0 <= along <= wall["L"]):
            continue
        if other["t"] is None:
            continue
        other_along = (tb if other is right else ta) * other["L"]
        if min(abs(other_along), abs(other_along - other["L"])) > 0.5 * other["t"] + 0.05:
            if not (0.0 <= other_along <= other["L"]):
                continue
        return {
            "kind": "no-thickness",
            "detail": f"{wall['id']} has no Thickness; it meets {other['id']} and was left unjoined",
        }
    return None


def _collinear_note(left, right):
    if left["t"] is None and right["t"] is None:
        return None
    lateral = _lateral(left, right)
    if lateral > COLLINEAR_OFFSET:
        return None
    gap, end_l, end_r = _end_gap(left, right)
    if gap > COLLINEAR_GAP:
        return None
    return {
        "kind": "collinear",
        "detail": (
            f"{left['id']} {end_l} and {right['id']} {end_r} are collinear,"
            f" gap {_fmt(gap)} m, offset {_fmt(lateral)} m; left as separate walls"
        ),
    }


def _parallel(left, right):
    cross = abs(left["dx"] * right["dy"] - left["dy"] * right["dx"])
    return cross / (left["L"] * right["L"]) < 1e-6


def _lateral(left, right):
    # Distance from right's start to left's infinite centre-line.
    cross = abs(
        (right["s"][0] - left["s"][0]) * left["dy"] - (right["s"][1] - left["s"][1]) * left["dx"]
    )
    return cross / left["L"]


def _end_gap(left, right):
    best = None
    for name_l, point_l in (("ATSTART", left["s"]), ("ATEND", left["e"])):
        for name_r, point_r in (("ATSTART", right["s"]), ("ATEND", right["e"])):
            gap = math.hypot(point_l[0] - point_r[0], point_l[1] - point_r[1])
            if best is None or gap < best[0]:
                best = (gap, name_l, name_r)
    return best


def _intersect(left, right):
    denom = left["dx"] * right["dy"] - left["dy"] * right["dx"]
    if abs(denom) < 1e-12:
        return None
    qx = right["s"][0] - left["s"][0]
    qy = right["s"][1] - left["s"][1]
    ta = (qx * right["dy"] - qy * right["dx"]) / denom
    tb = (qx * left["dy"] - qy * left["dx"]) / denom
    point = (left["s"][0] + ta * left["dx"], left["s"][1] + ta * left["dy"])
    return point, ta, tb


def _order(start, end):
    """Smaller X, or when X is equal the smaller Y, is the start."""
    if (end[0], end[1]) < (start[0], start[1]):
        return end, start, True
    return start, end, False


def _refresh(wall):
    wall["dx"] = wall["e"][0] - wall["s"][0]
    wall["dy"] = wall["e"][1] - wall["s"][1]
    wall["L"] = math.hypot(wall["dx"], wall["dy"])


def _shift_openings(openings, original, walls):
    for opening in openings:
        host_id = opening.get("VoidsElement")
        wall = walls.get(host_id)
        if wall is None or "AlongAxis" not in opening or host_id not in original:
            continue
        old_start, old_end = original[host_id]
        new_start, new_end = wall["s"], wall["e"]
        # AlongAxis is measured from Start, so an end-only snap leaves it.
        if _same_point(old_start, new_start):
            continue
        old_length = math.hypot(old_end[0] - old_start[0], old_end[1] - old_start[1])
        new_length = math.hypot(new_end[0] - new_start[0], new_end[1] - new_start[1])
        if old_length < 1e-9 or new_length < 1e-9:
            continue
        old_u = ((old_end[0] - old_start[0]) / old_length, (old_end[1] - old_start[1]) / old_length)
        new_u = ((new_end[0] - new_start[0]) / new_length, (new_end[1] - new_start[1]) / new_length)
        along = float(opening["AlongAxis"])
        world_x = old_start[0] + old_u[0] * along
        world_y = old_start[1] + old_u[1] * along
        opening["AlongAxis"] = num((world_x - new_start[0]) * new_u[0] + (world_y - new_start[1]) * new_u[1])


def _same_point(left, right):
    return abs(left[0] - right[0]) < 1e-9 and abs(left[1] - right[1]) < 1e-9


def _apply(doc, walls):
    updated = deepcopy(doc)
    by_id = {wall["id"]: wall for wall in walls.values()}
    for wall in updated.get("walls") or []:
        fresh = by_id.get(wall["id"])
        if fresh is None:
            continue
        axis = wall.setdefault("Axis", {})
        axis["Start"] = [num(fresh["s"][0]), num(fresh["s"][1])]
        axis["End"] = [num(fresh["e"][0]), num(fresh["e"][1])]
    return updated


def _with_connections(doc, connections):
    if not connections:
        doc.pop("connections", None)
        return doc
    ordered = {}
    placed = False
    for key, value in doc.items():
        if key == "connections":
            continue
        ordered[key] = value
        if key == "walls":
            ordered["connections"] = connections
            placed = True
    if not placed:
        ordered["connections"] = connections
    doc.clear()
    doc.update(ordered)
    return doc


def _fmt(value):
    return format(round(float(value), 4), ".4f").rstrip("0").rstrip(".") or "0"
