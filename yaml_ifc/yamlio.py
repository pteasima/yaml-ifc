"""Read and write yaml-ifc documents. Comments are not preserved."""

from pathlib import Path

import yaml

FLOW_KEYS = {"Start", "End"}


class _Flow(list):
    """A list dumped in YAML flow style, such as `[0.45, 3.0875]`."""


def _represent_flow(dumper, data):
    return dumper.represent_sequence("tag:yaml.org,2002:seq", list(data), flow_style=True)


def _represent_float(dumper, value):
    text = format(round(float(value), 6), ".6f").rstrip("0").rstrip(".")
    if text in ("", "-0", "-"):
        text = "0"
    return dumper.represent_scalar("tag:yaml.org,2002:float", text)


yaml.add_representer(_Flow, _represent_flow)
yaml.add_representer(float, _represent_float)


def num(value):
    value = round(float(value), 6)
    if abs(value - round(value)) < 1e-9:
        return int(round(value))
    return value


def load(path):
    with Path(path).open(encoding="utf-8") as handle:
        doc = yaml.safe_load(handle)
    if not isinstance(doc, dict):
        raise ValueError(f"{path} is not a yaml-ifc mapping")
    return doc


def _flow_points(value):
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if key in FLOW_KEYS and isinstance(item, list):
                out[key] = _Flow(num(v) if isinstance(v, (int, float)) else v for v in item)
            elif key == "Footprint" and isinstance(item, list):
                out[key] = [_Flow(num(v) for v in point) for point in item]
            elif key == "Profile" and isinstance(item, list):
                out[key] = [_Flow(num(v) for v in point) for point in item]
            elif key == "Aggregates" and isinstance(item, list):
                out[key] = _Flow(item)
            else:
                out[key] = _flow_points(item)
        return out
    if isinstance(value, list):
        return [_flow_points(item) for item in value]
    if isinstance(value, float):
        return num(value)
    return value


def dump(doc, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.dump(
        _flow_points(doc),
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=100,
    )
    path.write_text(text, encoding="utf-8")
