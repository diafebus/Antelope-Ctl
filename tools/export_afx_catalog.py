#!/usr/bin/env python3
"""Export the logical AFX catalog as one inline JSON document; no device I/O."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from antelope.catalog import DEFAULT_CATALOG, load_catalog


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, default=DEFAULT_CATALOG,
                        help='catalog manifest or legacy inline JSON (default: repository catalog)')
    parser.add_argument('--output', type=Path, help='output JSON file (default: stdout)')
    args = parser.parse_args(argv)
    try:
        catalog = load_catalog(args.catalog)
        if args.output:
            source = json.loads(args.catalog.read_text(encoding='utf-8'))
            inputs = [args.catalog.resolve()]
            inputs.extend((args.catalog.resolve().parent / ref).resolve()
                          for ref in source.get('effect_files', []))
            if args.output.resolve() in inputs:
                raise ValueError('Export output must not overwrite a catalog source file')
        text = json.dumps(catalog, indent=2, ensure_ascii=False) + '\n'
        if args.output:
            args.output.write_text(text, encoding='utf-8')
        else:
            sys.stdout.write(text)
    except (OSError, ValueError) as error:
        parser.exit(1, f'AFX catalog export failed: {error}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
