"""Profile bounded AMR workflows against the repository's regression fixtures."""

import argparse
from collections import Counter
import cProfile
from hashlib import sha256
import json
import os
from pathlib import Path
import pstats
import re
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from zipfile import ZipFile


CASES = {
    'workbench': (
        'test_workbench_lifecycle.WorkbenchLifecycleTests.test_fresh_save_reopens_portable_project_and_json_save_stays_json',
        'test_check_workflow.CheckDependencyTests.test_unrelated_robot_edit_keeps_graph_findings_but_invalidates_compatibility',
    ),
    'scenario': ('test_scenario_study.ScenarioStudyTests.test_exhaustive_coverage_and_cross_sweep_deduplication',),
    'stress': ('test_stress_parallel.ParallelStudyTests.test_one_and_eight_workers_choose_identical_candidates_and_ranking',),
    'lift-study': ('test_building_tutorial.BuildingTutorialTests.test_cancel_resume_relink_and_changed_frozen_drawing',),
    'human-contingency': ('test_human_contingency.HumanContingencyTests.test_cancelled_search_and_uninterrupted_search_match',),
    'compatibility': (
        'test_compact_execution.CompactExecutionTests.test_all_exports_match_reference_and_cached_exports_are_not_rewritten',
        'test_compact_execution.CompactExecutionTests.test_cancelled_export_keeps_complete_canonical_evidence',
        'test_compact_execution.CompactExecutionTests.test_legacy_uncompressed_store_remains_readable',
        'test_partial_playback.PartialPlaybackTests.test_investigation_explains_stop_and_withholds_full_run_metrics',
    ),
}
WORKFLOWS = ('workbench', 'simple', 'detailed', 'scenario', 'stress', 'lift-study',
             'human-contingency', 'review-playback', 'pdf', 'csv', 'xlsx', 'compatibility',
             'direct-verbose-csv')


def emit(path, value):
    path.write_text(json.dumps(value, indent=2, default=str) + '\n', encoding='utf-8')


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def managed_run(folder, detailed):
    from amr_project import Project
    from amr_project_runs import PreparedRun, execute
    from visualiser.project_checks import check_project
    from tests.test_geometric_simulation import geometric_config
    from tests.test_lift_integration import direct_config

    folder.mkdir(parents=True, exist_ok=True)
    config = geometric_config() if detailed else direct_config(True)
    if not detailed:
        config['tasks'] = [dict(id=f'T{i}', pickup='A', dropoff='B3', payload='Box', release_time=30 * i)
                           for i in range(12)]
    path = folder / 'fixture.amrproj'
    Project().save(path, config)
    draft = PreparedRun(Project.open(path), folder / 'runs')
    report = check_project(draft.config)
    report.acknowledge_warnings()
    return execute(draft.commit(report))


def results(simulation):
    from amr_event_store import iter_events
    from amr_run_review import verified_events
    from tests.test_compact_execution import normalise

    directory = simulation.event_store.path.parent
    manifest, _, store, _ = verified_events(directory)
    rows = list(iter_events(store))
    ids = [row['event_id'] for row in rows]
    return {'events': len(rows), 'unique_event_ids': len(set(ids)),
            'completed_tasks': manifest['completed_tasks'], 'failed_tasks': manifest['failed_tasks'],
            'lift_movements': sum(row.get('event_type') in ('segment_lift_transfer', 'segment_lift_reposition')
                                  for row in rows),
            'event_digest': digest(normalise(rows, simulation.run_id))}


def benchmark(workflow, folder):
    if workflow in CASES:
        loader = unittest.TestLoader()
        names = [f'tests.{test}' for test in CASES[workflow]]
        test = unittest.TextTestRunner(verbosity=2).run(loader.loadTestsFromNames(names))
        if not test.wasSuccessful() or test.skipped:
            raise RuntimeError(f'{test.testsRun} cases, {len(test.failures)} failures, '
                               f'{len(test.errors)} errors, {len(test.skipped)} skips')
        return {'tests_run': test.testsRun}
    if workflow == 'xlsx':
        from amr_lift_movement_charts import export_lift_charts_xlsx
        from amr_third_party_lift import export_lift_trips_xlsx
        from tests.test_lift_movement_charts import chart_source
        from tests.test_lift_trip_excel import LiftTripExcelTests, saved_cells

        chart_dir, trip_dir = folder / 'chart-fixture', folder / 'trip-fixture'
        chart_dir.mkdir()
        trip_dir.mkdir()
        chart, trips = folder / 'charts.xlsx', folder / 'trips.xlsx'
        export_lift_charts_xlsx(chart_source(chart_dir), chart)
        counts = export_lift_trips_xlsx(LiftTripExcelTests().source(trip_dir), trips)
        with ZipFile(chart) as archive:
            chart_xml = [(name, archive.read(name).decode()) for name in sorted(archive.namelist())
                         if re.fullmatch(r'xl/(?:drawings/)?charts/chart\d+\.xml', name)]
        if not chart_xml:
            raise ValueError('Workbook contains no native chart parts')
        cells, _, tables = saved_cells(trips)
        return {'counts': counts, 'chart_count': len(chart_xml), 'chart_digest': digest(chart_xml),
                'trip_table_count': len(tables), 'trip_cells_digest': digest(cells)}
    if workflow in ('simple', 'detailed'):
        return results(managed_run(folder, workflow == 'detailed'))
    if workflow == 'direct-verbose-csv':
        from simulator import Simulation
        from tests.test_scenario_study import config

        evidence = {}
        for backing in ('in-memory', 'file-backed'):
            path = folder / f'{backing}.csv'
            store = path.with_suffix('.sqlite') if backing == 'file-backed' else None
            simulation = Simulation(config(), verbose=True, verbose_csv_path=str(path), event_store_path=store)
            simulation.run()
            simulation.write_verbose_csv()
            evidence[backing] = digest(path.read_text(encoding='utf-8').replace(simulation.run_id, '<run>'))
        return evidence

    from amr_run_review import verified_events

    directory = next((folder.parent / 'simple' / 'runs').iterdir())
    _, _, store, _ = verified_events(directory)
    run_id = json.loads(Path(str(store) + '.run.json').read_text(encoding='utf-8'))['run_id']
    if workflow == 'review-playback':
        from amr_results_investigation import load_investigation
        from visualiser.project_playback_panel import load_playback
        from tests.test_compact_execution import normalise

        _, _, layout, log = load_playback(directory)
        states, _ = log.state_at(log.start_time, layout)
        review = load_investigation(directory)
        return {'playback_events': len(log.events), 'review_events': len(review['events']),
                'playback_digest': digest(normalise([event.row for event in log.events], run_id)),
                'initial_state_digest': digest(normalise(states, run_id)),
                'review_digest': digest(normalise([review[key] for key in ('events', 'tasks', 'metrics')], run_id))}
    if workflow == 'pdf':
        from amr_project_report import generate
        from pypdf import PdfReader

        pdf = generate(directory, folder / 'report', ('lift_movements_by_level',))
        pages = [page.extract_text().replace(run_id, '<run>') for page in PdfReader(pdf).pages]
        pages = [re.sub(r'^Generated: [^\r\n]*$', 'Generated: <timestamp>', page, flags=re.MULTILINE)
                 for page in pages]
        return {'pages': len(pages), 'page_text_digest': digest(pages)}
    from amr_project_runs import OUTPUTS
    from amr_run_exports import ensure_exports
    from amr_third_party_lift import export_all_lifts_csv

    expanded = ensure_exports(directory, OUTPUTS)
    export_all_lifts_csv(directory, folder / 'lifts', include_reposition=True)
    csvs = sorted([*map(Path, expanded.values()), *(folder / 'lifts').glob('*.csv')])
    return {'csv_digests': {path.name: digest(path.read_text(encoding='utf-8').replace(run_id, '<run>'))
                            for path in csvs}}


def measure(root, folder, workflow):
    from amr_event_store import EventStore

    opens, reads, publications, event_blocks = Counter(), Counter(), Counter(), Counter()
    parent = str(folder.parent).casefold() + os.sep

    def artifact(value):
        if isinstance(value, (str, bytes, os.PathLike)):
            filename = os.path.abspath(os.fsdecode(value))
            if filename.casefold().startswith(parent):
                name = Path(filename).name
                return re.sub(r'(?<=\.)[\w-]{8,}(?=\.tmp$)', '<temp>', name)
        return None

    def audit(action, values):
        if action == 'open':
            name = artifact(values[0])
            if name:
                if values[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT):
                    opens[name] += 1
                elif name.endswith('.sqlite'):
                    reads[name] += 1
        elif action == 'os.rename':
            name = artifact(values[1])
            if name:
                publications[name] += 1

    original_write = EventStore._write_block

    def block(store, rows, payloads):
        result = original_write(store, rows, payloads)
        if store.path and (name := artifact(store.path)):
            event_blocks[name] += 1
            events_written[name] += len(rows)
        return result

    events_written = Counter()
    sys.addaudithook(audit)
    profile = cProfile.Profile()
    start, cpu = time.perf_counter(), time.process_time()
    try:
        with patch.object(EventStore, '_write_block', block):
            profile.enable()
            try:
                evidence = benchmark(workflow, folder)
            finally:
                profile.disable()
        error = None
    except Exception as failure:
        import traceback
        traceback.print_exc()
        evidence, error = {}, f'{type(failure).__name__}: {failure}'
    seconds, cpu_seconds = time.perf_counter() - start, time.process_time() - cpu
    stats = pstats.Stats(profile)
    rows = []
    for (name, line, symbol), (_, calls, own, cumulative, _) in stats.stats.items():
        path = Path(name)
        if path.is_relative_to(root) and 'tests' not in path.relative_to(root).parts:
            rows.append({'file': path.relative_to(root).as_posix(), 'line': line, 'symbol': symbol,
                         'calls': calls, 'own_seconds': own, 'cumulative_seconds': cumulative})
    emit(folder / 'profile.json', {'workflow': workflow, 'wall_seconds': seconds, 'process_cpu_seconds': cpu_seconds,
         'profile_calls': stats.total_calls, 'app_calls': sum(item['calls'] for item in rows),
         'top_app_calls': sorted(rows, key=lambda item: item['cumulative_seconds'], reverse=True)[:25],
         'write_opens': dict(opens), 'sqlite_read_opens': dict(reads), 'publications': dict(publications),
         'sqlite_event_blocks': dict(event_blocks),
         'sqlite_events_written': dict(events_written), 'evidence': evidence, 'error': error})
    profile.dump_stats(str(folder / 'profile.pstats'))
    return bool(error)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path, help='A new scratch output directory')
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--workflow', choices=WORKFLOWS, help=argparse.SUPPRESS)
    parser.add_argument('--timeout', type=int, default=180, help='Seconds allowed for each workflow')
    args = parser.parse_args()
    root, output = args.root.resolve(), args.output.resolve()
    if args.workflow:
        sys.path[:0] = [str(root), str(root / 'visualiser')]
        temp = output / 'temp'
        temp.mkdir()
        tempfile.tempdir = str(temp)
        return measure(root, output, args.workflow)

    output.mkdir(parents=True)
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1', QT_QPA_PLATFORM='offscreen',
                       OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
    results = {}
    for workflow in WORKFLOWS:
        folder = output / workflow
        folder.mkdir()
        command = [sys.executable, '-B', __file__, str(folder), '--root', str(root), '--workflow', workflow]
        with (folder / 'run.log').open('w', encoding='utf-8') as log:
            try:
                status = subprocess.run(command, cwd=root, env=environment, stdout=log,
                                        stderr=subprocess.STDOUT, timeout=args.timeout).returncode
            except subprocess.TimeoutExpired:
                status = 'timeout'
        report = folder / 'profile.json'
        results[workflow] = {'exit': status, **(json.loads(report.read_text(encoding='utf-8')) if report.exists() else {})}
        print(f'{workflow}: {status}', flush=True)
    emit(output / 'summary.json', results)
    return any(item['exit'] != 0 for item in results.values())


if __name__ == '__main__':
    raise SystemExit(main())
