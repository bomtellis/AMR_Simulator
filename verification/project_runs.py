"""Bounded real-project regression through the saved-project execution path."""
import argparse
import contextlib
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import time

from amr_project import Project
from amr_project_runs import PreparedRun, execute, inspect_run
from amr_results_investigation import load_investigation
from visualiser.project_checks import check_project


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--minutes', type=float, default=360)
    args = parser.parse_args()
    if not 0 < args.minutes <= 1440:
        parser.error('minutes must be greater than zero and no more than 1440')
    raw = args.config.read_bytes()
    config = json.loads(raw)
    start = datetime.fromisoformat(config['simulation']['start_datetime'])
    end = start + timedelta(minutes=args.minutes)
    if config['simulation'].get('end_datetime'):
        end = min(end, datetime.fromisoformat(config['simulation']['end_datetime']))
    config['simulation']['end_datetime'] = end.isoformat()
    args.output.mkdir(parents=True, exist_ok=True)
    project = Project()
    project.save(args.output / (args.config.stem + '-bounded.amrproj'), config,
                 base_dir=args.config.resolve().parent, label='Bounded engineering regression')
    draft = PreparedRun(project, args.output / 'results')
    try:
        report = check_project(draft.config, base_path=draft.directory)
        # Explicit automated acceptance for this engineering reference run,
        # not an assertion that a person reviewed or approved the warnings.
        report.acknowledge_warnings()
        directory = draft.commit(report)
    finally:
        draft.discard()
    started = time.perf_counter()
    with (directory / 'process.log').open('w', encoding='utf-8') as log, contextlib.redirect_stdout(log):
        simulation = execute(directory)
    investigation = load_investigation(directory)
    outcome = {'completed': simulation.completed_task_records, 'failed': simulation.failed_tasks,
               'pending_ids': sorted(task.id for _p, _r, _s, task in simulation.pending_tasks if task.id not in simulation._removed_pending_task_ids)}
    summary = {'run_directory': str(directory.resolve()), 'project': str(project.path),
               'binding': inspect_run(directory, project)['project_binding'],
               'completed': len(simulation.completed_task_records), 'failed': len(simulation.failed_tasks),
               'pending': len(outcome['pending_ids']), 'run_seconds': round(time.perf_counter() - started, 3),
               'outcome_sha256': hashlib.sha256(json.dumps(outcome, sort_keys=True, default=str).encode()).hexdigest(),
               'input_unchanged': raw == args.config.read_bytes(), 'reconciliation': investigation['reconciliation'],
               'warning_review': 'Automatically acknowledged by the engineering regression command, not human approval.'}
    (directory / 'investigation.json').write_text(json.dumps(investigation, indent=2), encoding='utf-8')
    (args.output / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2))
    return 0 if summary['input_unchanged'] and all(r['matches'] for r in investigation['reconciliation']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
