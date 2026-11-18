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
    parser.add_argument('--progress-json', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--lift-study', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--scenario-study', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--human-contingency-study', type=Path, help='Run or resume a saved human contingency study')
    parser.add_argument('--contingency-study', type=Path, help='Human contingency evidence to include in a PDF report')
    parser.add_argument('--scenario-trial', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--scenario-worker', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--export-run', type=Path, help='Expand compact run evidence into requested CSV outputs')
    parser.add_argument('--outputs', default='steps_csv', help='Comma-separated output keys for --export-run')
    parser.add_argument('--third-party-lift-csv', type=Path, help='Export one lift from the completed run supplied as the positional input')
    parser.add_argument('--third-party-lifts-dir', type=Path, help='Export every configured lift to separate CSVs in a new folder')
    parser.add_argument('--third-party-lift-xlsx', type=Path, help='Export all lifts and all trips to an Excel table with a concatenation formula')
    parser.add_argument('--lift-charts-xlsx', type=Path, help='Export stacked purpose charts per lift with Excel day selectors')
    parser.add_argument('--lift-chart-day', help='Chart day YYYY-MM-DD or Day N; default All days')
    parser.add_argument('--lift-chart-lift-id',action='append',help='Include one lift in PDF charts; repeat for multiple lifts. Does not affect Excel.')
    parser.add_argument('--lift-chart-bin-minutes', type=int, choices=[5,15,30,60], default=30)
    parser.add_argument('--lift-chart-exclude-reposition', action='store_true', help='Initially exclude empty repositioning from lift charts')
    parser.add_argument('--lift-id', help='Lift identifier for the third-party CSV')
    parser.add_argument('--include-lift-reposition', action='store_true', help='Include empty lift reposition movements in the third-party CSV')
    parser.add_argument('--export-gate', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--export-parent', type=int, help=argparse.SUPPRESS)
    parser.add_argument('--package-smoke-building', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--generate-report', nargs=2, type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--sections', help=argparse.SUPPRESS)
    parser.add_argument('--comparison-baseline', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--drawings', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--lift-cohorts-only', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--existing-pdf', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--insert-after-page', type=int, help=argparse.SUPPRESS)
    parser.add_argument('--report-title', help=argparse.SUPPRESS)
    parser.add_argument('--stress-selection', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.lift_charts_xlsx is not None:
        if args.project is None or args.third_party_lift_xlsx or args.third_party_lift_csv or args.third_party_lifts_dir or args.lift_id or args.include_lift_reposition:
            parser.error('--lift-charts-xlsx requires a saved run and cannot be combined with other lift export flags')
        from amr_lift_movement_charts import export_lift_charts_xlsx
        result = export_lift_charts_xlsx(args.project,args.lift_charts_xlsx,
            day=args.lift_chart_day,interval_minutes=args.lift_chart_bin_minutes,
            include_reposition=not args.lift_chart_exclude_reposition)
        print(f"Exported stacked charts for {result['lifts']} lifts to {args.lift_charts_xlsx}",flush=True)
        return 0
    if args.third_party_lift_xlsx is not None:
        if args.project is None or args.lift_id or args.third_party_lift_csv or args.third_party_lifts_dir:
            parser.error('--third-party-lift-xlsx requires a saved run input and cannot be combined with CSV output flags or --lift-id')
        from amr_third_party_lift import export_lift_trips_xlsx
        counts = export_lift_trips_xlsx(args.project, args.third_party_lift_xlsx)
        print(f'Exported {len(counts)} lifts ({sum(counts.values())} trips) to {args.third_party_lift_xlsx}', flush=True)
        return 0
    if args.third_party_lifts_dir is not None:
        if args.project is None or args.lift_id or args.third_party_lift_csv:
            parser.error('--third-party-lifts-dir requires a saved run input and cannot be combined with --lift-id or --third-party-lift-csv')
        from amr_third_party_lift import export_all_lifts_csv
        counts = export_all_lifts_csv(args.project, args.third_party_lifts_dir, args.include_lift_reposition)
        print(f'Exported {len(counts)} lifts ({sum(counts.values())} movements) to {args.third_party_lifts_dir}', flush=True)
        return 0
    if args.third_party_lift_csv is not None:
        if args.project is None or not args.lift_id:
            parser.error('--third-party-lift-csv requires a completed run input and --lift-id')
        from amr_third_party_lift import export_lift_csv
        count = export_lift_csv(args.project, args.third_party_lift_csv, args.lift_id, args.include_lift_reposition)
        print(f'Exported {count} lift movements to {args.third_party_lift_csv}', flush=True)
        return 0
    if args.lift_id or args.include_lift_reposition:
        parser.error('--lift-id requires --third-party-lift-csv; --include-lift-reposition requires a third-party export')
    if args.human_contingency_study is not None:
        from amr_contingency_study import main as evaluate_humans
        return evaluate_humans(args.human_contingency_study)
    if args.export_run is not None:
        if args.export_gate is not None:
            from amr_export_execution import export_worker
            return export_worker(args.export_run, args.outputs.split(','), args.export_gate, args.export_parent)
        from amr_export_execution import expand_in_process
        def feedback(message):
            import json
            print('EXPORT ' + json.dumps(message), flush=True)
        expand_in_process(args.export_run, args.outputs.split(','), progress=feedback)
        return 0
    if args.scenario_worker is not None:
        from amr_stress_execution import persistent_worker_main
        return persistent_worker_main(args.scenario_worker)
    if args.scenario_trial is not None:
        from amr_stress_execution import worker_main
        return worker_main(args.scenario_trial)
    if args.scenario_study is not None:
        from amr_scenario_study import main as evaluate_scenarios
        return evaluate_scenarios(args.scenario_study)
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
        return run_project([str(args.run_project)] + (['--progress-json'] if args.progress_json else []))
    if args.generate_report is not None:
        from amr_project_report import main as generate_report
        report_args = [str(path) for path in args.generate_report]
        report_args += ['--sections', args.sections or '']
        if args.comparison_baseline is not None:
            report_args.extend(['--comparison-baseline', str(args.comparison_baseline)])
        if args.drawings:
            report_args.append('--drawings')
        if args.lift_cohorts_only:
            report_args.append('--lift-cohorts-only')
        if args.lift_chart_day:
            report_args.extend(['--lift-chart-day',args.lift_chart_day])
        for identity in args.lift_chart_lift_id or []:
            report_args.extend(['--lift-chart-lift-id',identity])
        report_args.extend(['--lift-chart-bin-minutes',str(args.lift_chart_bin_minutes)])
        if args.lift_chart_exclude_reposition:
            report_args.append('--lift-chart-exclude-reposition')
        if args.existing_pdf:
            report_args.extend(['--existing-pdf', str(args.existing_pdf)])
        if args.insert_after_page is not None:
            report_args.extend(['--insert-after-page', str(args.insert_after_page)])
        if args.report_title:
            report_args.extend(['--report-title', args.report_title])
        if args.stress_selection:
            report_args.extend(['--stress-selection', str(args.stress_selection)])
        if args.contingency_study:
            report_args.extend(['--contingency-study', str(args.contingency_study)])
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
