"""Run a bounded verbose scenario and reconcile its saved investigation evidence."""
import argparse
import contextlib
import copy
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

from amr_results_investigation import load_investigation
from simulator import Simulation


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
    (args.output / 'config.json').write_text(json.dumps(config, indent=2) + '\n', encoding='utf-8')
    path = args.output / 'simulation_steps.csv'
    with (args.output / 'run.txt').open('w', encoding='utf-8') as log, contextlib.redirect_stdout(log):
        sim = Simulation(copy.deepcopy(config), verbose=True, verbose_csv_path=str(path))
        sim.run()
        sim.write_verbose_csv()
    report = load_investigation(path)
    (args.output / 'investigation.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    outcome = {'completed': sim.completed_task_records, 'failed': sim.failed_tasks,
               'pending_ids': sorted(task.id for _p, _r, _s, task in sim.pending_tasks if task.id not in sim._removed_pending_task_ids)}
    summary = {'metrics': [{k: m[k] for k in ('key', 'value', 'coverage')} for m in report['metrics']],
               'reconciliation': report['reconciliation'], 'findings': report['findings'],
               'outcome_sha256': hashlib.sha256(json.dumps(outcome, sort_keys=True, default=str).encode()).hexdigest(),
               'input_unchanged': raw == args.config.read_bytes()}
    (args.output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, indent=2))
    return 0 if summary['input_unchanged'] and all(r['matches'] for r in report['reconciliation']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
