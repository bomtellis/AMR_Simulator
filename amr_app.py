"""Launch the unified AMR engineering workbench, optionally opening a project."""
import argparse
from pathlib import Path
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', nargs='?', type=Path, help='AMR project (.amrproj) or JSON configuration to open')
    parser.add_argument('--without-drawings', action='store_true',
                        help='Open configuration without loading drawing underlays')
    args = parser.parse_args(argv)
    # Legacy editor modules use sibling imports. Resolve from this file so
    # shortcuts and callers do not need a particular working directory.
    root = Path(__file__).resolve().parent
    sys.path.insert(0, str(root / 'visualiser'))
    from app import main as run_workbench
    return run_workbench(args.project.resolve() if args.project else None,
                         load_drawings=not args.without_drawings)


if __name__ == '__main__':
    raise SystemExit(main())
