"""Versioned evidence metadata stored beside simulation logs."""
import csv
import hashlib
import json
import os
from pathlib import Path
from amr_lift_evidence import CAPABILITY as LIFT_CAPABILITY, booked_movement_counts


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def config_hash(config):
    return hashlib.sha256(json.dumps(config, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':')).encode('utf-8')).hexdigest()


def software_snapshot():
    """Conservative application-source binding, including editor/check/report code.

    Include whole application directories so newly imported local modules cannot
    silently escape a manually maintained dependency list. Tests, examples,
    outputs and documentation are not executable application inputs. Third-party
    packages and the Python runtime are outside this source-only fingerprint.
    """
    root = Path(__file__).resolve().parent
    paths = set(root.glob('*.py'))
    for directory in ('visualiser', 'report'):
        paths.update((root / directory).rglob('*.py'))
    files = {p.relative_to(root).as_posix(): file_hash(p) for p in sorted(paths)}
    return {'version_scheme': 'source file SHA-256', 'scope_version': 2,
            'scope': 'Root Python modules and all visualiser/report Python modules; excludes third-party runtime.',
            'sha256': config_hash(files), 'files': files}


def write_run_evidence(simulation, csv_path, *, kind='full'):
    path = Path(csv_path)
    data = {
        'schema_version': 1, 'run_id': simulation.run_id,
        'config_sha256': simulation._evidence_config_hash,
        'frozen_inputs': simulation._evidence_inputs,
        'software': simulation._evidence_software,
        'project_binding': getattr(simulation, '_evidence_project_binding', None),
        'log_sha256': file_hash(path), 'log_kind': kind,
        'logging_enabled': simulation.verbose,
        'event_capabilities': list(getattr(simulation, '_evidence_event_capabilities', [])) + [LIFT_CAPABILITY],
        'reduced_logging': bool(simulation.scenario_mode and not simulation.scenario_enhanced_logging),
        'run_status': simulation._evidence_run_status,
        'summary': {'completed_task_ids': sorted({r['task_id'] for r in simulation.completed_task_records}),
                    'failed_task_ids': sorted(simulation.failed_task_ids),
                    'battery_amr_ids': sorted(amr.id for amr in simulation.amrs),
                    'lift_movement_counts': booked_movement_counts(simulation)},
        'scope': 'Recorded inputs and source fingerprint; no claim of tamper-proof audit or certification.',
    }
    termination = getattr(simulation, 'geometric_termination', None)
    if termination is not None:
        data['termination'] = dict(termination)
        if kind == 'full':
            from amr_partial_run import derive_partial_run
            with path.open(newline='', encoding='utf-8-sig') as stream:
                data['partial_run'] = derive_partial_run(
                    list(csv.DictReader(stream)), simulation._evidence_inputs,
                    stop_time=termination['stop_time_sec'])
    target = Path(str(path) + '.run.json')
    temporary = target.with_suffix(target.suffix + '.tmp')
    temporary.write_text(json.dumps(data, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    os.replace(temporary, target)
    return target
