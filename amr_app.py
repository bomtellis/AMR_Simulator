"""Launch the unified AMR engineering workbench, optionally opening a project."""
import argparse
from pathlib import Path
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', nargs='?', type=Path, help='AMR project (.amrproj) or JSON configuration to open')
    parser.add_argument('--without-drawings', action='store_true',
                        help='Open configuration without loading drawing underlays')
    parser.add_argument('--package-smoke', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--package-smoke-ltn', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--run-project', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--lift-study', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--package-smoke-building', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--generate-report', nargs=2, type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--sections', help=argparse.SUPPRESS)
    parser.add_argument('--drawings', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--lift-cohorts-only', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--existing-pdf', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--insert-after-page', type=int, help=argparse.SUPPRESS)
    parser.add_argument('--report-title', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.package_smoke_building is not None:
        from amr_building_smoke import run
        return run(args.package_smoke_building)
    if args.lift_study is not None:
        from amr_lift_study import main as evaluate_study
        return evaluate_study(args.lift_study)
    if args.package_smoke is not None:
        from amr_package_smoke import run
        return run(args.package_smoke)
    if args.package_smoke_ltn is not None:
        from amr_package_smoke import run_ltn
        return run_ltn(args.package_smoke_ltn)
    if args.run_project is not None:
        from amr_project_runs import main as run_project
        return run_project([str(args.run_project)])
    if args.generate_report is not None:
        from amr_project_report import main as generate_report
        report_args = [str(path) for path in args.generate_report]
        report_args += ['--sections', args.sections or '']
        if args.drawings:
            report_args.append('--drawings')
        if args.lift_cohorts_only:
            report_args.append('--lift-cohorts-only')
        if args.existing_pdf:
            report_args.extend(['--existing-pdf', str(args.existing_pdf)])
        if args.insert_after_page is not None:
            report_args.extend(['--insert-after-page', str(args.insert_after_page)])
        if args.report_title:
            report_args.extend(['--report-title', args.report_title])
        return generate_report(report_args)
    # Legacy editor modules use sibling imports. Resolve from this file so
    # shortcuts and callers do not need a particular working directory.
    root = Path(__file__).resolve().parent
    sys.path.insert(0, str(root / 'visualiser'))
    from app import main as run_workbench
    return run_workbench(args.project.resolve() if args.project else None,
                         load_drawings=not args.without_drawings)


if __name__ == '__main__':
    # PyInstaller's process-pool workers re-enter this executable with a
    # multiprocessing flag. Dispatch them before parsing application options.
    import multiprocessing
    multiprocessing.freeze_support()
    raise SystemExit(main())
