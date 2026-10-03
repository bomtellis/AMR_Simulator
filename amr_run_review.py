"""Verification boundary for completed runs and explicitly opted-in partial review."""
from pathlib import Path
from amr_project_runs import OUTPUTS, read_json, validate_run_inputs, verified_termination
from amr_project import configuration_bytes
from amr_run_evidence import file_hash, config_hash


def verified_inputs(directory, *, drawings=False, allow_partial=False):
    directory = Path(directory).resolve()
    manifest, config = validate_run_inputs(directory, verify_drawings=drawings)
    partial = manifest['status'] == 'partial' and allow_partial
    if manifest['status'] != 'complete' and not partial:
        raise ValueError('This action requires a completed project run. Investigate incomplete runs separately.')
    csv = directory / OUTPUTS['steps_csv']
    evidence = read_json(str(csv) + '.run.json')
    if (type(evidence.get('schema_version')) is not int or evidence.get('schema_version') != 1 or evidence.get('project_binding') != manifest['project_binding'] or
            evidence.get('config_sha256') != manifest['config_object_sha256'] or
            config_hash(evidence.get('frozen_inputs')) != manifest['config_object_sha256'] or
            configuration_bytes(evidence.get('frozen_inputs')) != configuration_bytes(config) or
            evidence.get('software', {}).get('sha256') != manifest['software']['sha256'] or
            evidence.get('log_sha256') != file_hash(csv) or
            evidence.get('log_kind') != 'full' or not evidence.get('logging_enabled') or evidence.get('reduced_logging')):
        raise ValueError('This action requires complete event evidence matching this run and its frozen configuration.')
    if partial:
        termination = verified_termination(evidence, csv)
        if (manifest.get('termination') != termination or manifest.get('termination_sha256') != config_hash(termination)
                or manifest.get('termination_reason') != termination['reason']
                or type(manifest.get('stop_time_sec')) not in (int, float)
                or manifest.get('stop_time_sec') != termination['stop_time_sec']
                or manifest.get('simulation_run_id') != evidence.get('run_id')):
            raise ValueError('Partial termination evidence does not match the saved run manifest.')
    elif evidence.get('run_status') != 'finished' or evidence.get('termination') is not None:
        raise ValueError('This action requires a finished run without partial termination evidence.')
    return manifest, config, csv, evidence['log_sha256']
