"""Stress studies must measure service, preserve demand and verify their evidence."""
import contextlib
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from simulator import Simulation
from amr_project_runs import read_json, write_json
from amr_scenario_study import (resources, default_settings, validated_settings, domain,
    candidate_count, candidate_at, candidate_id, create_study, evaluate, validate_study,
    run_metrics, candidate_events, scenario_config)
from amr_scenario_study import corridor_sweep_assets, trial_counts, search_settings, config_hash
from tests.test_engineering_reference import reference_config


def config():
    value = reference_config()
    value['corridors']['nodes'] = []
    value['corridors']['edges'] = [dict(**{'from': 'A', 'to': 'B'}, width_m=3)]
    value['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box')]
    return value


def deferred_config(limit=60):
    from tests.test_task_deferral import TaskDeferralTests
    value = TaskDeferralTests.config(limit=limit, generated=True)
    value['task_generation']['categories']['stores']['departments']['D1'].update(
        scheduled_times=['00:01', '00:02'], release_next_after_return_pickup=True,
        staff_handling_minutes=65)
    return value


def event(resource='A -> B', start=0, end=60, availability=0, speed=1):
    from datetime import datetime, timedelta
    origin = datetime(2026, 1, 5)
    return dict(resource_type='corridor', resource_ids=[resource], availability_percent=availability,
                speed_factor=speed, start_datetime=(origin + timedelta(seconds=start)).isoformat(),
                end_datetime=(origin + timedelta(seconds=end)).isoformat())


def scenario(value, events):
    result = deepcopy(value)
    result['scenario_testing'] = dict(enabled=True, enhanced_logging=True, active_scenario='Stress',
                                     scenarios=[dict(name='Stress', events=events)])
    return result


class ScenarioRouteTests(unittest.TestCase):
    def network(self):
        value = config()
        value['corridors']['nodes'] = [dict(name='C', floor=0, x=0, y=10)]
        value['corridors']['edges'] += [dict(**{'from': 'A', 'to': 'C'}, width_m=3),
                                      dict(**{'from': 'C', 'to': 'B'}, width_m=3)]
        return value

    def route(self, value, start=0, reverse=False, rules=None):
        sim = Simulation(value)
        self.addCleanup(lambda: sim.routing_executor.shutdown() if sim.routing_executor else None)
        a, b = ('B', 'A') if reverse else ('A', 'B')
        result = sim._same_floor_segments(sim.amrs[0], sim.locations[a], sim.locations[b],
            payload=sim.payloads['Box'], start_time_value=start, rules=rules)
        return sim, result

    def test_long_closure_chooses_permitted_detour(self):
        _, (segments, duration, distance) = self.route(scenario(self.network(), [event()]))
        self.assertEqual(['A', 'C'], [s['from'] for s in segments])
        self.assertAlmostEqual(10 + 40 ** .5, distance)
        self.assertAlmostEqual(distance / 2, duration)

    def test_short_closure_waits_on_faster_original_route(self):
        _, (segments, duration, distance) = self.route(scenario(self.network(), [event(end=1)]))
        self.assertEqual('wait_for_scenario', segments[0]['type'])
        self.assertEqual(10, distance)
        self.assertEqual(6, duration)

    def test_direction_width_and_profile_restrictions_still_apply(self):
        for restriction in ('direction', 'width', 'profile'):
            with self.subTest(restriction=restriction):
                value = self.network()
                rules = None
                if restriction == 'direction':
                    value['corridors']['edges'][1].update(bidirectional=False)
                    value['corridors']['edges'][1]['from'] = 'C'
                    value['corridors']['edges'][1]['to'] = 'A'
                elif restriction == 'width':
                    value['corridors']['edges'][1]['width_m'] = .2
                else:
                    rules = dict(allowed_nodes=['A', 'B'], allowed_lifts=[], allowed_edges=[])
                _, (_, duration, distance) = self.route(scenario(value, [event()]), rules=rules)
                self.assertEqual(10, distance)
                self.assertEqual(65, duration)

    def test_reverse_travel_uses_same_physical_blockage(self):
        _, (_, duration, distance) = self.route(scenario(config(), [event()]), reverse=True)
        self.assertEqual(65, duration)
        self.assertEqual(10, distance)

    def test_overlapping_and_adjacent_closures_rechecked_until_available(self):
        _, (_, duration, _) = self.route(scenario(config(), [event(end=60), event(start=30, end=120),
                                                            event(start=120, end=180)]))
        self.assertEqual(185, duration)

    def test_exact_end_and_route_cache_do_not_keep_closed_route(self):
        sim, (_, _, _) = self.route(scenario(self.network(), [event()]))
        segments, duration, distance = sim._same_floor_segments(sim.amrs[0], sim.locations['A'], sim.locations['B'],
            payload=sim.payloads['Box'], start_time_value=60)
        self.assertEqual(10, distance)
        self.assertEqual(5, duration)
        self.assertEqual('A', segments[0]['from'])

    def test_slowdown_changes_route_choice_and_zero_speed_waits(self):
        _, (_, _, distance) = self.route(scenario(self.network(), [event(availability=100, speed=.25)]))
        self.assertGreater(distance, 10)
        _, (_, duration, _) = self.route(scenario(config(), [event(availability=100, speed=0)]))
        self.assertEqual(65, duration)

    def test_waiting_for_short_slowdown_is_faster_than_detour(self):
        _, (segments, duration, distance) = self.route(scenario(self.network(), [event(end=1, availability=100, speed=.25)]))
        self.assertEqual('wait_for_scenario', segments[0]['type'])
        self.assertEqual(10, distance)
        self.assertEqual(6, duration)

    def test_recurring_permanent_closure_is_bounded(self):
        value = scenario(config(), [dict(resource_type='corridor', resource_ids=['A -> B'],
            availability_percent=0, speed_factor=1, start_time='00:00', end_time='00:00', days_active=[])])
        _, result = self.route(value)
        self.assertIsNone(result)


class ScenarioStudyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.value = config()
        self.path = self.root / 'study.stress.json'

    def create(self, **settings):
        return create_study(self.value, self.path, {**default_settings(self.value), 'trial_budget': 6, **settings})

    def run_study(self, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            return evaluate(self.path, **kwargs)

    def test_defaults_physical_corridors_and_finite_domain(self):
        self.value['corridors']['edges'].append(dict(**{'from': 'B', 'to': 'A'}, width_m=3))
        self.assertEqual(1, sum(r[0] == 'corridor' for r in resources(self.value)))
        settings = default_settings(self.value)
        self.assertEqual([10], settings['durations_minutes'])
        self.assertEqual(100, settings['trial_budget'])
        # Two assets, four effects, one window: 8 singles + 16 pairs.
        self.assertEqual(24, candidate_count(settings))
        candidates = [candidate_at(settings, i) for i in range(candidate_count(settings))]
        self.assertEqual(24, len({candidate_id(c) for c in candidates}))

    def test_settings_reject_bad_values_and_unknown_assets(self):
        for invalid in [dict(start_step_minutes=0), dict(assets=[['amr', 'missing']]),
                        dict(durations_minutes=[0]), dict(speed_percent=[float('nan')]), dict(end_minute=20)]:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validated_settings(self.value, invalid)

    def test_unchecked_corridors_are_excluded_from_new_study_trials(self):
        settings = {**default_settings(self.value), 'assets': [['amr', 'R']], 'trial_budget': 2}
        self.assertEqual([], corridor_sweep_assets(self.value, settings))
        self.assertEqual(3, trial_counts(self.value, settings)['total'])
        self.create(assets=settings['assets'], trial_budget=2)
        state = self.run_study()
        self.assertEqual(0, state['coverage']['corridor_trials'])
        self.assertEqual(3, state['expected_trials'])
        self.assertEqual(3, len(state['results']))
        self.assertTrue(all(event['resource_type'] == 'amr' for record in state['results'].values()
                            for event in record['events']))

    def test_explicit_full_sweep_and_legacy_studies_keep_all_corridors(self):
        settings = {**default_settings(self.value), 'assets': [['amr', 'R']], 'trial_budget': 1,
                    'corridor_sweep_scope': 'all'}
        self.assertEqual([['corridor', 'A -> B']], corridor_sweep_assets(self.value, settings))
        self.assertEqual(3, trial_counts(self.value, settings)['total'])
        state = self.create(assets=settings['assets'], trial_budget=1, corridor_sweep_scope='all')
        state['settings'].pop('corridor_sweep_scope')
        state['settings_sha256'] = config_hash(search_settings(state['settings']))
        write_json(self.path, state)
        validate_study(state)
        result = self.run_study()
        self.assertEqual(1, result['coverage']['corridor_trials'])
        self.assertEqual(3, result['expected_trials'])
        self.assertEqual(3, len(result['results']))

    def test_corridor_scope_rejects_unknown_values(self):
        with self.assertRaises(ValueError):
            validated_settings(self.value, {'corridor_sweep_scope': 'sometimes'})

    def test_verified_baseline_corridor_sweep_allows_completion_after_demand_end(self):
        self.create()
        state = self.run_study()
        baseline = state['results']['baseline']['metrics']
        self.assertTrue(baseline['passed'])
        self.assertEqual(9, baseline['latest_completion_sec'])
        corridor = state['results'][state['corridor_ranking'][0]]
        self.assertTrue(corridor['metrics']['passed'])
        self.assertEqual(0, corridor['metrics']['unmet_count'])
        self.assertEqual(1, corridor['metrics']['late'])
        self.assertGreater(corridor['metrics']['latest_completion_sec'], 600)
        self.assertEqual(6, state['coverage']['combined_trials'])
        self.assertEqual('complete', state['status'])
        self.assertFalse(state['coverage']['exhaustive'])
        self.assertTrue(state['worst_passing'])
        validate_study(state, self.value)

    def test_baseline_finish_exactly_at_end_passes(self):
        self.value['simulation']['end_datetime'] = '2026-01-05T00:00:09'
        self.create(trial_budget=1)
        state = self.run_study()
        self.assertTrue(state['results']['baseline']['metrics']['passed'])

    def test_submillisecond_completion_after_end_is_informational(self):
        self.value['simulation']['end_datetime'] = '2026-01-05T00:00:09'
        self.value['amrs'][0]['speed_m_per_sec'] = 10 / 5.0001
        self.create(trial_budget=1)
        state = self.run_study()
        metrics = state['results']['baseline']['metrics']
        self.assertGreater(metrics['latest_completion_sec'], 9)
        self.assertEqual(1, metrics['late'])
        self.assertTrue(metrics['passed'])

    def test_inventory_dependent_generation_cannot_hide_unreleased_work(self):
        path = Path(__file__).resolve().parents[1] / 'verification/scenarios/tracked-stock.json'
        self.value = json.loads(path.read_text(encoding='utf-8'))
        self.value['simulation']['end_datetime'] = '2026-01-05T02:30:00'
        self.create(trial_budget=1)
        state = self.run_study()
        baseline = state['results']['baseline']['metrics']
        self.assertEqual(2, len(baseline['obligations']))
        for identity in state['corridor_ranking']:
            metrics = state['results'][identity]['metrics']
            self.assertEqual(1, len(metrics['obligations']))
            missing = set(baseline['obligations']) - set(metrics['obligations'])
            self.assertTrue(missing <= set(metrics['unmet']))
            self.assertFalse(metrics['passed'])

    def test_multi_stop_completions_reconcile_with_run_summary(self):
        from tests.test_multi_stop_route_rules import multi_route_config
        self.value = multi_route_config()
        self.value['tasks'] = [dict(id='ONE', pickup='A', dropoff='B', payload='Box'),
                               dict(id='TWO', pickup='A', dropoff='B', payload='Box')]
        self.create(trial_budget=1)
        state = self.run_study()
        baseline = state['results']['baseline']['metrics']
        self.assertTrue(baseline['passed'])
        self.assertEqual({'ONE', 'TWO'}, set(baseline['obligations']))

    def test_failed_baseline_stops_before_stress_trials(self):
        self.value = deferred_config()
        self.create()
        with self.assertRaisesRegex(ValueError, 'assignment deferral limit'):
            self.run_study()
        state = read_json(self.path)
        self.assertEqual(['baseline'], list(state['results']))
        self.assertEqual('failed', state['status'])
        self.assertEqual(1, state['results']['baseline']['metrics']['failed'])

    def test_normal_and_stress_use_global_deferral_setting_and_drain_returns(self):
        for limit, expected_failed in ((60, 1), (75, 0), (0, 0)):
            with self.subTest(limit=limit):
                self.value = deferred_config(limit)
                with contextlib.redirect_stdout(io.StringIO()):
                    normal = Simulation(self.value)
                    normal.run()
                study_path = self.root / f'deferral-{limit}.stress.json'
                create_study(self.value, study_path, {**default_settings(self.value), 'trial_budget': 1})
                with contextlib.redirect_stdout(io.StringIO()):
                    if expected_failed:
                        with self.assertRaisesRegex(ValueError, 'assignment deferral limit'):
                            evaluate(study_path)
                        state = read_json(study_path)
                    else:
                        state = evaluate(study_path)
                metrics = state['results']['baseline']['metrics']
                self.assertEqual(expected_failed, metrics['failed'])
                self.assertEqual(len(normal.failed_tasks), metrics['failed'])
                self.assertEqual(len(normal.completed_task_records), metrics['completed'])
                self.assertEqual(normal.max_task_deferral_sec, limit * 60)
                self.assertEqual(not expected_failed, metrics['passed'])
                self.assertGreater(metrics['latest_completion_sec'], state['horizon_sec'])
                for record in state['results'].values():
                    cfg = read_json(Path(record['directory']) / 'config.json')
                    self.assertEqual(limit, cfg['simulation']['max_task_deferral_minutes'])

    def test_empty_baseline_cannot_pass(self):
        self.value['tasks'] = []
        self.create()
        with self.assertRaisesRegex(ValueError, 'No service work'):
            self.run_study()

    def test_missing_generation_and_return_are_unmet_obligations(self):
        self.create(trial_budget=1)
        state = self.run_study()
        record = state['results']['baseline']
        baseline = deepcopy(record['metrics'])
        baseline['obligations']['not-generated'] = dict(signature=[], completion=1)
        metrics = run_metrics(record['directory'], baseline)
        self.assertFalse(metrics['passed'])
        self.assertIn('not-generated', metrics['unmet'])
        # Obligation expectation is recorded before completion, not inferred from a return count.
        self.assertIn('expected_return', record['metrics']['obligations']['T'])

    def test_return_keys_match_parent_despite_changed_synthetic_counter(self):
        self.value['tasks'][0].update(return_enabled=True, return_payload='Box', return_delay_minutes=0)
        self.create(trial_budget=2)
        state = self.run_study()
        self.assertEqual({'T', 'return:T'}, set(state['results']['baseline']['metrics']['obligations']))
        for record in state['results'].values():
            self.assertIn('return:T', record['metrics']['obligations'])

    def test_cancel_resume_is_reproducible_and_retains_completed_trials(self):
        self.create()
        stopped = self.run_study(cancel=lambda: len(read_json(self.path)['results']) >= 3)
        self.assertEqual('cancelled', stopped['status'])
        previous = {k: r['directory'] for k, r in stopped['results'].items()}
        resumed = self.run_study()
        self.assertEqual('complete', resumed['status'])
        self.assertTrue(all(resumed['results'][key]['directory'] == path for key, path in previous.items()))
        other = self.root / 'other.stress.json'
        create_study(self.value, other, resumed['settings'])
        with contextlib.redirect_stdout(io.StringIO()):
            uninterrupted = evaluate(other)
        self.assertEqual(list(resumed['results']), list(uninterrupted['results']))
        self.assertEqual(resumed['worst_passing'], uninterrupted['worst_passing'])

    def test_exhaustive_coverage_and_cross_sweep_deduplication(self):
        self.create(assets=[['corridor', 'A -> B']], trial_budget=10)
        state = self.run_study()
        self.assertEqual(4, state['coverage']['candidate_count'])
        self.assertEqual(4, state['coverage']['tested_candidates'])
        self.assertTrue(state['coverage']['exhaustive'])
        self.assertEqual(3, state['coverage']['combined_trials'])

    def test_changed_design_settings_software_and_evidence_rejected(self):
        state = self.create()
        changed = deepcopy(self.value)
        changed['amrs'][0]['speed_m_per_sec'] = 1
        with self.assertRaisesRegex(ValueError, 'Design inputs'):
            validate_study(state, changed)
        state['settings']['seed'] += 1
        with self.assertRaisesRegex(ValueError, 'settings changed'):
            validate_study(state)
        state = read_json(self.path)
        with patch('amr_scenario_study.software_snapshot', return_value={'sha256': 'different'}):
            with self.assertRaisesRegex(ValueError, 'Software changed'):
                validate_study(state)
        state = self.run_study()
        record = state['results']['baseline']
        record['metrics']['added_delay_sec'] = 100
        with self.assertRaisesRegex(ValueError, 'metrics'):
            validate_study(state)

    def test_source_fingerprint_change_between_trials_stops_study(self):
        state = self.create()
        def fingerprint():
            changed = bool(read_json(self.path)['results'])
            return {'sha256': 'changed-between-trials' if changed else state['software_sha256']}
        with patch('amr_scenario_study.software_snapshot', side_effect=fingerprint):
            with self.assertRaisesRegex(ValueError, 'Software changed'):
                self.run_study()
        stopped = read_json(self.path)
        self.assertEqual('failed', stopped['status'])
        self.assertEqual(['baseline'], list(stopped['results']))

    def test_saved_sample_schedule_change_is_rejected(self):
        state = self.create()
        state['sample_queue'] = [[[0, 0, 0]]]
        with self.assertRaisesRegex(ValueError, 'search schedule changed'):
            validate_study(state)

    def test_frozen_drawings_and_source_are_independent(self):
        drawing = self.root / 'floor.dxf'
        drawing.write_bytes(b'drawing reference')
        self.value['floor_dxf_files'] = [dict(floor=0, filepath=str(drawing))]
        original = deepcopy(self.value)
        state = self.create()
        self.assertEqual(original, self.value)
        drawing.write_bytes(b'changed')
        validate_study(state)
        with self.assertRaisesRegex(ValueError, 'Design inputs'):
            validate_study(state, self.value)
        frozen = Path(state['config']['floor_dxf_files'][0]['filepath'])
        frozen.write_bytes(b'changed frozen bytes')
        with self.assertRaisesRegex(ValueError, 'Frozen study'):
            validate_study(state)

    def test_detailed_mode_is_explicitly_rejected(self):
        self.value['simulation'].update(mode='detailed', motion_model='geometric_v1')
        self.value['geometry'] = dict(traffic_model='keep_right_v1')
        with self.assertRaisesRegex(ValueError, 'Simple mode'):
            self.create()


if __name__ == '__main__':
    unittest.main()
