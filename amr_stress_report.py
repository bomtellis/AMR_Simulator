"""Verify selected saved trials and prepare a compact PDF comparison snapshot."""
from copy import deepcopy
from pathlib import Path

from amr_project_runs import read_json
from amr_run_evidence import config_hash, file_hash
from amr_run_review import verified_events
from amr_scenario_study import (validate_study_document, input_identity, search_settings,
    verify_trial_inputs, run_metrics, baseline_identity, scenario_config)
from amr_scenario_study import is_amr_speed_sweep, speed_sweep_summary
from amr_simulation_inputs import simulation_horizon_seconds

METRICS = ('passed', 'unmet_count', 'added_delay_sec', 'latest_completion_sec',
           'completed', 'failed', 'pending', 'late', 'status', 'run_key')


def normalise_selection(selection):
    if not isinstance(selection, list) or not selection:
        raise ValueError('Select at least one saved stress-test trial.')
    groups = {}
    for item in selection:
        if (not isinstance(item, dict) or not isinstance(item.get('study_path'), str)
                or not isinstance(item.get('study_root'), str)
                or not isinstance(item.get('trial_ids'), list) or not item['trial_ids']
                or any(not isinstance(identity, str) or not identity for identity in item['trial_ids'])):
            raise ValueError('Invalid stress-test report selection.')
        path = str(Path(item['study_path']).resolve())
        group = groups.setdefault(path, dict(study_path=path, study_root=item['study_root'], trial_ids=[]))
        if group['study_root'] != item['study_root']:
            raise ValueError('Conflicting versions of the same study were selected.')
        group['trial_ids'] = list(dict.fromkeys(group['trial_ids'] + item['trial_ids']))
    return list(groups.values())


def collect_stress_report(selection, report_config):
    """Recompute metrics from evidence; saved JSON summaries alone are insufficient."""
    selections = normalise_selection(selection)
    files, runs, studies = {}, set(), []

    def remember(path):
        path = Path(path).resolve()
        checksum = file_hash(path)
        if str(path) in files and files[str(path)] != checksum:
            raise ValueError('Stress-test evidence changed during verification.')
        files[str(path)] = checksum

    def verified_run(directory):
        directory = Path(directory).resolve()
        manifest, _, events, _ = verified_events(directory, drawings=True, allow_partial=True)
        runs.add(str(directory))
        for name in ('run_manifest.json', 'config.json', 'project_configuration.json', 'project_checks.json',
                     events.name, events.name + '.run.json'):
            remember(directory / name)
        if events.suffix == '.sqlite':
            from amr_event_store import EventStore
            store = EventStore(events, readonly=True)
            try:
                if store.baseline is not None:
                    remember(store.baseline.path)
            finally:
                store.close()
        return manifest

    for selected in selections:
        path = Path(selected['study_path'])
        print(f'Verifying stress study: {path.name}', flush=True)
        remember(path)
        state = read_json(path)
        validate_study_document(state)
        if state['root'] != selected['study_root']:
            raise ValueError(f'{path.name} was replaced. Select its trials again.')
        if state['status'] == 'running':
            raise ValueError(f'Stop or finish {path.name} before reporting its trials.')
        if (state['source_identity'] != input_identity(state['config'])
                or state['settings_sha256'] != config_hash(search_settings(state['settings']))
                or state['horizon_sec'] != simulation_horizon_seconds(state['config'])):
            raise ValueError(f'{path.name}: frozen study inputs or settings changed.')
        if 'baseline' not in state['results'] or any(identity not in state['results'] for identity in selected['trial_ids']):
            raise ValueError(f'{path.name}: selected trials or their baseline are missing.')
        records = [state['results'][identity] for identity in selected['trial_ids'] if identity != 'baseline']
        manifests = {r['id']: verified_run(r['directory']) for r in records}
        # Historical reports compare against recorded software, not today's build.
        recorded_software = next((m['software'] for m in manifests.values()
                                  if m['software']['sha256'] == state['software_sha256']), None)
        baseline = state['results']['baseline']
        verified_run(baseline['directory'])
        verify_trial_inputs(state, baseline, study_software=recorded_software)
        baseline_metrics = run_metrics(baseline['directory'])
        if baseline_metrics != baseline['metrics']:
            raise ValueError(f'{path.name}: baseline metrics do not match verified evidence.')

        def summary(record, metrics):
            value = dict(id=record['id'], name=record['name'], kind=record['kind'],
                        directory=record['directory'], events=deepcopy(record['events']),
                        metrics={key: metrics[key] for key in METRICS},
                        unmet_examples=metrics['unmet'][:10])
            if is_amr_speed_sweep(state['settings']):
                value['amr_speed_percent'] = round(record['events'][0]['speed_factor'] * 100) if record['events'] else 100
            return value

        trials = []
        for index, record in enumerate(records, 1):
            print(f"Verifying selected trial {index}/{len(records)}: {record['name']}", flush=True)
            verify_trial_inputs(state, record)
            metrics = run_metrics(record['directory'], baseline_metrics)
            if metrics != record['metrics']:
                raise ValueError(f"{path.name}: {record['name']} metrics do not match verified evidence.")
            trials.append(summary(record, metrics))
        same_inputs = (baseline_identity(scenario_config(report_config, [], 'Normal operation'))
                       == baseline_identity(scenario_config(state['config'], [], 'Normal operation')))
        studies.append(dict(name=path.name, path=str(path), root=state['root'], status=state['status'],
            source_identity=state['source_identity'], software_sha256=state['software_sha256'],
            matches_report_inputs=same_inputs, start_datetime=state['config']['simulation']['start_datetime'],
            horizon_sec=state['horizon_sec'], saved_trials=len(state['results']) - 1,
            baseline=summary(baseline, baseline_metrics), trials=trials))
        if is_amr_speed_sweep(state['settings']):
            studies[-1]['speed_sweep'] = speed_sweep_summary(trials, studies[-1]['baseline'])
    evidence = dict(files=files, runs=sorted(runs), selection=selections)
    verify_stress_sources(evidence)
    return dict(studies=studies), evidence


def verify_stress_sources(evidence):
    for path, checksum in evidence['files'].items():
        if file_hash(path) != checksum:
            raise ValueError('Selected stress-study inputs or evidence changed during report generation.')
    for directory in evidence['runs']:
        verified_events(directory, drawings=True, allow_partial=True)
