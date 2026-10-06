"""Command line: python -m yaml_ifc to-ifc|from-ifc INPUT -o OUTPUT."""

import argparse
import sys
from pathlib import Path

from yaml_ifc.from_ifc import format_skipped, read_ifc
from yaml_ifc.to_ifc import validation_errors, write_ifc
from yaml_ifc.yamlio import dump, load


def main(argv):
    parser = argparse.ArgumentParser(description="Convert yaml-ifc to IFC4 and back.")
    sub = parser.add_subparsers(dest="command", required=True)

    to_ifc = sub.add_parser("to-ifc", help="write an IFC4 file")
    to_ifc.add_argument("source", type=Path)
    to_ifc.add_argument("-o", "--output", type=Path, required=True)

    from_ifc = sub.add_parser("from-ifc", help="write the supported subset as YAML")
    from_ifc.add_argument("source", type=Path)
    from_ifc.add_argument("-o", "--output", type=Path, required=True)

    args = parser.parse_args(argv)
    if args.command == "to-ifc":
        model = write_ifc(load(args.source), args.output)
        errors = validation_errors(model)
        if errors:
            print(f"{args.output}: {len(errors)} validation errors", file=sys.stderr)
            for message in errors[:20]:
                print(message, file=sys.stderr)
            return 1
        print(args.output)
        return 0

    document, skipped = read_ifc(args.source)
    dump(document, args.output)
    report = format_skipped(skipped)
    sys.stderr.write(report)
    sidecar = args.output.with_name(args.output.stem + ".skipped.txt")
    sidecar.write_text(report, encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
