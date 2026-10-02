"""Versioned evidence metadata stored beside simulation logs."""
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
    root = Path(__file__).resolve().parent
    files = {p.name: file_hash(p) for p in sorted(root.glob('amr_sim_*.py'))}
    for name in ('simulator.py', 'amr_run_evidence.py', 'amr_project_runs.py', 'amr_lift_evidence.py'):
        files[name] = file_hash(root / name)
    return {'version_scheme': 'source file SHA-256', 'sha256': config_hash(files), 'files': files}


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
    target = Path(str(path) + '.run.json')
    temporary = target.with_suffix(target.suffix + '.tmp')
    temporary.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
    os.replace(temporary, target)
    return target
