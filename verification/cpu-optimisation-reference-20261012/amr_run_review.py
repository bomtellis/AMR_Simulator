"""Verification boundary for completed runs and explicitly opted-in partial review."""
from pathlib import Path
from amr_project_runs import OUTPUTS, read_json, validate_run_inputs, verified_termination
from amr_project import configuration_bytes
from amr_run_evidence import file_hash, config_hash, verified_simulation_mode


def verified_events(directory, *, drawings=False, allow_partial=False):
    directory = Path(directory).resolve()
    manifest, config = validate_run_inputs(directory, verify_drawings=drawings)
    partial = manifest['status'] == 'partial' and allow_partial
    if manifest['status'] != 'complete' and not partial:
        raise ValueError('This action requires a completed project run. Investigate incomplete runs separately.')
    name = manifest.get('canonical_events', OUTPUTS['steps_csv'])
    if Path(name).name != name:
        raise ValueError('Invalid canonical event path')
    csv = directory / name
    evidence = read_json(str(csv) + '.run.json')
    if (type(evidence.get('schema_version')) is not int or evidence.get('schema_version') != (2 if csv.suffix == '.sqlite' else 1) or evidence.get('project_binding') != manifest['project_binding'] or
            evidence.get('config_sha256') != manifest['config_object_sha256'] or
            config_hash(evidence.get('frozen_inputs')) != manifest['config_object_sha256'] or
            configuration_bytes(evidence.get('frozen_inputs')) != configuration_bytes(config) or
            evidence.get('software', {}).get('sha256') != manifest['software']['sha256'] or
            evidence.get('log_sha256') != file_hash(csv) or
            evidence.get('log_kind') != 'full' or not evidence.get('logging_enabled') or evidence.get('reduced_logging')):
        raise ValueError('This action requires complete event evidence matching this run and its frozen configuration.')
    verified_simulation_mode(evidence, config)
    from amr_run_evidence import verify_legacy_computation
    verify_legacy_computation(evidence, config)
    recorded_computation = dict(evidence.get('computation', {'requested': 'cpu', 'implementation': 'python_compact'}))
    recorded_computation.pop('statistics', None)
    if 'computation' in manifest and recorded_computation != manifest['computation']:
        raise ValueError('Evidence computation identity differs from its prepared run')
    if csv.suffix == '.sqlite':
        from amr_event_store import EventStore
        store = EventStore(csv, readonly=True)
        try:
            if evidence.get('storage') != dict(format='sqlite_sparse_events', version=1, event_count=len(store)):
                raise ValueError('Compact event counts or format do not match the evidence')
        finally:
            store.close()
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


def verified_inputs(directory, *, drawings=False, allow_partial=False):
    manifest, config, path, checksum = verified_events(directory, drawings=drawings, allow_partial=allow_partial)
    if path.suffix == '.sqlite':
        from amr_export_execution import expand_in_process
        expand_in_process(directory, ('steps_csv',))
        path = Path(directory) / OUTPUTS['steps_csv']
        checksum = file_hash(path)
    return manifest, config, path, checksum


def verified_standalone_events(path):
    """Compact CLI evidence has no project binding but still binds its inputs."""
    path = Path(path).resolve()
    evidence = read_json(str(path) + '.run.json')
    if (evidence.get('schema_version') != 2 or evidence.get('log_kind') != 'full'
            or evidence.get('logging_enabled') is not True or evidence.get('reduced_logging') is not False
            or evidence.get('log_sha256') != file_hash(path)
            or config_hash(evidence.get('frozen_inputs')) != evidence.get('config_sha256')):
        raise ValueError('Standalone compact evidence does not match its event store and inputs')
    verified_simulation_mode(evidence, evidence['frozen_inputs'])
    from amr_run_evidence import verify_legacy_computation
    verify_legacy_computation(evidence, evidence['frozen_inputs'])
    if evidence.get('run_status') in ('blocked', 'search_limit', 'deadlock'):
        verified_termination(evidence, path)
    elif evidence.get('run_status') != 'finished' or evidence.get('termination') is not None:
        raise ValueError('Standalone evidence does not establish a finished or verified partial run')
    from amr_event_store import EventStore
    store = EventStore(path, readonly=True)
    try:
        if evidence.get('storage') != dict(format='sqlite_sparse_events', version=1, event_count=len(store)):
            raise ValueError('Standalone event counts do not match their evidence')
    finally:
        store.close()
    return evidence, evidence['frozen_inputs'], path, evidence['log_sha256']
