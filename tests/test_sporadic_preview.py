"""Independent rate/polling references for deterministic sporadic demand."""
import contextlib
import copy
import io
import json
import unittest
from pathlib import Path

from amr_demand_preview import build_demand_preview
from simulator import Simulation
from tests.test_generation_reference import grouped_config
from visualiser.models import JsonStore
from visualiser.demand_preview_panel import rule_explanation


def sporadic_config(mode='sporadic'):
    config = grouped_config()
    config['simulation']['end_datetime'] = '2026-01-05T02:00:00'
    config['simulation']['generated_task_release_stagger_sec'] = 0
    config['task_generation']['update_interval_sec'] = 3600
    config['task_generation']['categories']['stores'].update(
        generation_mode=mode, scheduled_times=[], frequency_per_day=36,
        volume_per_event_m3=0.2, requires_staff=False)
    return config


class SporadicPreviewTests(unittest.TestCase):
    def preview(self, config):
        result = build_demand_preview(config)
        rule = next(r for r in result['rules'] if r['id'] == 'stores:D:group:G')
        return result, rule

    def test_three_events_in_two_hours_match_independent_arithmetic(self):
        for config in (sporadic_config(), JsonStore(sporadic_config()).data):
            preview, rule = self.preview(config)
            self.assertEqual([3600, 7200, 7200], [t['release_seconds'] for t in preview['tasks']])
            self.assertEqual(3, rule['total_demand'])
            self.assertEqual(3, rule['expected_fixed_records'])
            self.assertEqual(0, rule['count_difference'])
            self.assertEqual(3, rule['sporadic_accounting']['accrued_events'])
            self.assertEqual(0, rule['sporadic_accounting']['retained_events'])

    def test_combined_mode_orders_schedule_and_poll_releases_like_simulation(self):
        scenario = Path(__file__).resolve().parents[1] / 'verification/scenarios/sporadic-preview.json'
        config = json.loads(scenario.read_text(encoding='utf-8'))
        preview, rule = self.preview(config)
        self.assertEqual([1800, 3600, 4500, 7200, 7200], [t['release_seconds'] for t in preview['tasks']])
        self.assertEqual(5, rule['expected_fixed_records'])
        sim = Simulation(config, verbose=True)
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        generated = [r for r in sim.verbose_rows if r['event_type'] == 'task_generated']
        self.assertEqual([t['release_seconds'] for t in preview['tasks']], [float(r['sim_time_sec']) for r in generated])
        self.assertEqual(5, len(sim.completed_task_records))

    def test_fractional_event_is_retained_and_explained(self):
        config = sporadic_config()
        config['simulation']['end_datetime'] = '2026-01-05T01:00:00'
        preview, rule = self.preview(config)
        self.assertEqual(1, len(preview['tasks']))
        self.assertAlmostEqual(0.5, rule['sporadic_accounting']['retained_events'])
        self.assertIn('Retained events: 0.5', rule_explanation(rule))

    def test_closed_poll_retains_whole_events_until_next_opening(self):
        config = sporadic_config()
        config['simulation'].update(start_datetime='2026-01-05T08:00:00', end_datetime='2026-01-06T09:00:00')
        config['departments'][0].update(operating_start_time='09:00', operating_end_time='10:00')
        preview, rule = self.preview(config)
        self.assertEqual([90000], [t['release_seconds'] for t in preview['tasks']])
        self.assertAlmostEqual(1.5, rule['sporadic_accounting']['accrued_events'])
        self.assertAlmostEqual(0.5, rule['sporadic_accounting']['retained_events'])

    def test_zero_frequency_explains_no_work(self):
        config = sporadic_config()
        config['task_generation']['categories']['stores']['frequency_per_day'] = 0
        preview, rule = self.preview(config)
        self.assertEqual([], preview['tasks'])
        self.assertEqual('no-work', rule['status'])
        self.assertEqual(0, rule['total_demand'])
        self.assertIn('0', rule['explanation'])

    def test_final_partial_poll_and_minimum_interval_match_runtime(self):
        config = sporadic_config()
        config['simulation']['end_datetime'] = '2026-01-05T00:10:00'
        config['task_generation']['update_interval_sec'] = 900
        config['task_generation']['categories']['stores']['frequency_per_day'] = 144
        preview, _ = self.preview(config)
        self.assertEqual([600], [t['release_seconds'] for t in preview['tasks']])
        config['task_generation']['update_interval_sec'] = 1
        config['task_generation']['categories']['stores']['frequency_per_day'] = 1440
        preview, _ = self.preview(config)
        self.assertEqual(list(range(60, 601, 60)), [t['release_seconds'] for t in preview['tasks']])

    def test_no_route_pair_does_not_destroy_accumulated_events(self):
        sim = Simulation(sporadic_config())
        generator = sim.task_generation_manager.generators[0]
        instance = generator.instances[0]
        instance['dropoff_locations'] = ['A']
        self.assertEqual([], generator.update_until(3600))
        runtime = generator._runtime_for_volume_key(instance)
        self.assertAlmostEqual(1.5, runtime['sporadic_accumulator'][instance['key']])
        instance['dropoff_locations'] = ['B']
        self.assertEqual(1, len(generator.update_until(3601)))

    def test_preview_is_repeatable_and_does_not_mutate_inputs(self):
        config = sporadic_config()
        before = copy.deepcopy(config)
        self.assertEqual(self.preview(config), self.preview(config))
        self.assertEqual(before, config)

    def test_multiple_category_routes_keep_occurrences_separate_from_records(self):
        config = sporadic_config()
        config['locations'].append(dict(name='C', floor=0, x=0, y=10))
        category = config['task_generation']['categories']['stores']
        category['department_groups'] = []
        category['dropoff_locations'] = ['B', 'C']
        preview = build_demand_preview(config)
        rule = next(r for r in preview['rules'] if r.get('sporadic_accounting'))
        self.assertEqual(6, len(preview['tasks']))  # three occurrences, two route pairs
        self.assertEqual(3, rule['sporadic_accounting']['emitted_events'])
        self.assertIsNone(rule['expected_fixed_records'])

    def test_returns_and_tracked_replenishment_keep_total_demand_unknown(self):
        for extra in ({'return_enabled': True, 'return_payload': 'Box'}, {'tracked_item_exchange': True}):
            with self.subTest(extra=extra):
                config = sporadic_config()
                config['task_generation']['categories']['stores'].update(extra)
                preview, rule = self.preview(config)
                self.assertEqual(3, len(preview['tasks']))
                self.assertIsNone(rule['total_demand'])

    def test_hybrid_remains_runtime_dependent(self):
        _, rule = self.preview(sporadic_config('hybrid'))
        self.assertIsNone(rule['total_demand'])
        self.assertNotIn('sporadic_accounting', rule)

    def test_independent_count_respects_documented_event_roundoff_tolerance(self):
        config = sporadic_config()
        config['simulation']['end_datetime'] = '2026-01-05T00:10:00'
        config['task_generation']['categories']['stores']['frequency_per_day'] = 143.999999995
        preview, rule = self.preview(config)
        self.assertEqual(1, len(preview['tasks']))
        self.assertEqual(1, rule['expected_fixed_records'])
        self.assertEqual(0, rule['count_difference'])

    def test_extreme_rate_is_rejected_before_generating_records(self):
        config = sporadic_config()
        config['task_generation']['categories']['stores']['frequency_per_day'] = 1e12
        with self.assertRaisesRegex(ValueError, 'preview limit'):
            self.preview(config)


if __name__ == '__main__':
    unittest.main()
