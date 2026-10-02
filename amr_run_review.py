"""Shared verification boundary for review of completed project runs."""
from pathlib import Path
from amr_project_runs import OUTPUTS, read_json, validate_run_inputs
from amr_run_evidence import file_hash, config_hash


def verified_inputs(directory, *, drawings=False):
    directory = Path(directory).resolve()
    manifest, config = validate_run_inputs(directory, verify_drawings=drawings)
    if manifest['status'] != 'complete':
        raise ValueError('This action requires a completed project run. Investigate incomplete runs separately.')
    csv = directory / OUTPUTS['steps_csv']
    evidence = read_json(str(csv) + '.run.json')
    if (evidence.get('project_binding') != manifest['project_binding'] or
            evidence.get('config_sha256') != manifest['config_object_sha256'] or
            config_hash(evidence.get('frozen_inputs')) != manifest['config_object_sha256'] or
            evidence.get('software', {}).get('sha256') != manifest['software']['sha256'] or
            evidence.get('log_sha256') != file_hash(csv) or evidence.get('run_status') != 'finished' or
            evidence.get('log_kind') != 'full' or not evidence.get('logging_enabled') or evidence.get('reduced_logging')):
        raise ValueError('This action requires complete event evidence matching this run and its frozen configuration.')
    return manifest, config, csv, evidence['log_sha256']
