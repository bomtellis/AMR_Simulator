"""Shared run-control contracts; omission keeps the direct simulator defaults.

New-project choices can differ when explicitly stored. These functions never
mutate input and do not treat unknown metadata as simulator settings.
"""
import math
from datetime import datetime, timedelta

from amr_sim_time_utils import parse_release_time


DEFAULTS = {
    'start_datetime': '2026-01-01T08:00:00', 'tick_rate': 120.0,
    'generated_task_release_stagger_sec': 0.25, 'max_task_deferral_minutes': 60.0,
    'precompute_static_routes': True, 'route_precompute_max_pairs': 100000,
    'max_single_candidate_tasks': 8, 'max_multi_stop_candidate_tasks': 8,
    'max_assignments_per_tick': 50, 'assignment_continue_delay_sec': 0.001,
    'idle_return_check_interval_sec': 60.0, 'enable_opportunity_charging': False,
    'opportunity_charging_idle_period_sec': 900.0,
    'seed_waste_stream_containers_at_start': False,
    'reservation_prune_interval_sec': 300.0,
    'ignore_invalid_local_manoeuvres': False,
    'spawn_payloads_when_empty': False,
    'waste_bin_return_policy': 'same_amr',
    'service_return_amr_policy': 'same_amr',
    'dispatch_available_amrs_only': False,
    'waste_swap_advance_staging': False,
    'waste_swap_stage_initial_spares': False,
}
ALIASES = {'generated_task_release_stagger_sec': 'task_release_stagger_sec',
           'seed_waste_stream_containers_at_start': 'waste_stream_containers_present_at_start'}
COUNTS = {'route_precompute_max_pairs': 0, 'max_assignments_per_tick': 0,
          'max_single_candidate_tasks': 1, 'max_multi_stop_candidate_tasks': 2}
NUMBERS = {'tick_rate': 0, 'generated_task_release_stagger_sec': 0, 'task_release_stagger_sec': 0,
           'max_task_deferral_minutes': 0, 'duration_hours': 0, 'duration_days': 0,
           'assignment_continue_delay_sec': 0.001, 'idle_return_check_interval_sec': 1,
           'opportunity_charging_idle_period_sec': 0, 'opportunity_charging_check_interval_sec': 1,
           'reservation_prune_interval_sec': 1, 'reservation_history_retention_sec': 0}
FLAGS = {'precompute_static_routes', 'enable_opportunity_charging',
         'dispatch_available_amrs_only',
         'ignore_invalid_local_manoeuvres', 'spawn_payloads_when_empty',
         'seed_waste_stream_containers_at_start', 'waste_stream_containers_present_at_start',
         'disable_inventory_spaces', 'scenario_mode', 'scenario_enhanced_logging',
         'waste_swap_advance_staging', 'waste_swap_stage_initial_spares'}


def run_control_bool(value):
    """Explicit legacy checkbox encodings; never use Python string truthiness."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {'1', 'true', 'yes', 'y', 'on', 'enabled', 'enable'}:
            return True
        if text in {'0', 'false', 'no', 'n', 'off', 'disabled', 'disable'}:
            return False
    raise ValueError('Use a boolean or an explicit legacy true/false checkbox value.')


def simulation_input_findings(config):
    if config is None:
        return []
    if not isinstance(config, dict):
        return [('/', 'Configuration must be an object.')]
    sim = config.get('simulation', {})
    if not isinstance(sim, dict):
        return [('/simulation', 'Simulation settings must be an object.')]
    findings = []
    if sim.get('service_return_amr_policy', 'same_amr') not in ('same_amr', 'any_compatible'):
        findings.append(('/simulation/service_return_amr_policy',
                         'Service return AMR policy must be same_amr or any_compatible.'))
    if sim.get('waste_bin_return_policy', 'same_amr') not in ('same_amr', 'second_amr_swap'):
        findings.append(('/simulation/waste_bin_return_policy',
                         'Waste bin return policy must be same_amr or second_amr_swap.'))
    locations = config.get('locations', [])
    location_names = {row.get('name') for row in locations
                      if isinstance(row, dict) and isinstance(row.get('name'), str)} if isinstance(locations, list) else set()
    dispatch = sim.get('waste_swap_collection_dispatch', {})
    if not isinstance(dispatch, dict) or any(
            name not in location_names or policy != 'earliest_pickup'
            for name, policy in dispatch.items()):
        findings.append(('/simulation/waste_swap_collection_dispatch',
                         'Use configured locations with earliest_pickup dispatch.'))
    working = sim.get('waste_swap_opening_working_bins', {})
    payloads = config.get('payloads', [])
    payload_names = {row.get('name') for row in payloads
                     if isinstance(row, dict) and isinstance(row.get('name'), str)} if isinstance(payloads, list) else set()
    if not isinstance(working, dict) or any(
            name not in location_names or not isinstance(payload, str) or payload not in payload_names
            for name, payload in working.items()):
        findings.append(('/simulation/waste_swap_opening_working_bins',
                         'Use configured collection locations and a payload for the additional working bin.'))
    targets = sim.get('waste_swap_spare_targets', {})
    if not isinstance(targets, dict):
        findings.append(('/simulation/waste_swap_spare_targets',
                         'Specify a spare count by collection location and payload.'))
    elif targets:
        for name, counts in targets.items():
            if name not in location_names or not isinstance(counts, dict) or any(
                    payload not in payload_names or type(count) is not int or count < 1
                    for payload, count in counts.items()):
                findings.append(('/simulation/waste_swap_spare_targets',
                                 'Use configured locations and payloads with positive whole spare counts.'))
    for key, minimum in {**NUMBERS, **COUNTS}.items():
        if key not in sim:
            continue
        try:
            value = sim[key]
            number = float(value)
            if isinstance(value, bool) or not math.isfinite(number) or number < minimum:
                raise ValueError
            if key == 'tick_rate' and number == 0:
                raise ValueError
            if key in COUNTS and number != int(number):
                raise ValueError
            multiplier = {'duration_hours': 3600, 'duration_days': 86400, 'max_task_deferral_minutes': 60}.get(key, 1)
            if not math.isfinite(number * multiplier):
                raise ValueError
        except (TypeError, ValueError, OverflowError):
            requirement = 'greater than zero' if key == 'tick_rate' else f'at least {minimum}'
            findings.append(('/simulation/' + key, f'{key} must be a finite {"whole " if key in COUNTS else ""}number {requirement}.'))
    for key in FLAGS & sim.keys():
        try:
            run_control_bool(sim[key])
        except ValueError as exc:
            findings.append(('/simulation/' + key, str(exc)))
    mass = config.get('mass_collections', [])
    if isinstance(mass, dict):
        mass = mass.get('items', [])
    if isinstance(mass, list):
        known_payloads = {
            row.get('name') for row in config.get('payloads', [])
            if isinstance(row, dict) and isinstance(row.get('name'), str)
        } if isinstance(config.get('payloads', []), list) else set()
        for index, row in enumerate(mass):
            if not isinstance(row, dict) or 'initial_empty_overflow' not in row:
                continue
            stock = row['initial_empty_overflow']
            path = f'/mass_collections/{index}/initial_empty_overflow'
            if not isinstance(stock, dict) or any(
                    name not in known_payloads or type(count) is not int or count < 0
                    for name, count in stock.items()):
                findings.append((path, 'Specify configured payload names and nonnegative whole bin counts.'))
    dates = {}
    for key in ('start_datetime', 'end_datetime'):
        value = sim.get(key, DEFAULTS.get(key))
        if key == 'end_datetime' and value in (None, ''):
            continue
        try:
            dates[key] = datetime.fromisoformat(value)
        except (TypeError, ValueError):
            findings.append(('/simulation/' + key, f'{key} must be an ISO date and time.'))
    if len(dates) == 2:
        try:
            if dates['end_datetime'] < dates['start_datetime']:
                raise ValueError
        except (TypeError, ValueError):
            findings.append(('/simulation/end_datetime', 'End must not precede start and both dates must use compatible timezone offsets.'))
    if not findings:
        try:
            seconds = simulation_horizon_seconds(config)
            dates['start_datetime'] + timedelta(seconds=seconds)
        except (ValueError, TypeError, OverflowError):
            key = 'end_datetime' if sim.get('end_datetime') else 'duration_hours' if 'duration_hours' in sim else 'duration_days' if 'duration_days' in sim else 'start_datetime'
            findings.append(('/simulation/' + key, 'The resolved run period exceeds the supported datetime range.'))
    return findings


def validate_simulation_inputs(config):
    findings = simulation_input_findings(config)
    if findings:
        raise ValueError('Invalid simulation inputs: ' + '; '.join(f'{path}: {message}' for path, message in findings))


def resolved_simulation_settings(simulation):
    """Resolve validated settings for runtime/display without supplying an end."""
    result = dict(simulation)
    # The retired computation selector has no effect on CPU-only execution.
    result.pop('computation_backend', None)
    for key, default in DEFAULTS.items():
        result.setdefault(key, simulation.get(ALIASES.get(key), default))
    for key in FLAGS & result.keys():
        result[key] = run_control_bool(result[key])
    for key in (NUMBERS.keys() | COUNTS.keys()) & result.keys():
        result[key] = int(float(result[key])) if key in COUNTS else float(result[key])
    return result


def simulation_horizon_seconds(config):
    """Inclusive generated-demand horizon, not a cutoff for released transport.

    Explicit end > hours > days > latest static release plus one day (minimum
    one day). Invalid dates must be rejected by the shared input validator.
    """
    sim = config.get('simulation', {})
    start = datetime.fromisoformat(sim.get('start_datetime', DEFAULTS['start_datetime']))
    if sim.get('end_datetime'):
        return (datetime.fromisoformat(sim['end_datetime']) - start).total_seconds()
    for key, scale in (('duration_hours', 3600), ('duration_days', 86400)):
        if key in sim:
            return float(sim[key]) * scale
    latest = 0.0
    for task in config.get('tasks', []):
        try:
            latest = max(latest, parse_release_time(task, start))
        except (TypeError, ValueError, KeyError):
            # Task validation remains responsible for malformed static tasks.
            continue
    return latest + 86400.0
