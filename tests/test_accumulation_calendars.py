"""Independent accumulated-volume and event-count conservation references."""
import copy
import contextlib
import io
import unittest
from unittest.mock import patch

from simulator import Simulation
from tests.test_generation_reference import grouped_config
from visualiser.models import JsonStore


def accumulation_config(mode='threshold'):
    config = grouped_config()
    config['simulation'].update(start_datetime='2026-01-05T08:00:00', end_datetime='2026-01-06T12:00:00')
    config['departments'][0].update(operating_start_time='09:00', operating_end_time='10:00')
    config['task_generation']['categories']['stores'].update(
        generation_mode=mode, scheduled_times=[], requires_staff=False,
        base_daily_volume_m3=24, threshold_volume_m3=1,
        frequency_per_day=0, volume_per_event_m3=0)
    return config


class AccumulationCalendarTests(unittest.TestCase):
    def run_updates(self, config, times, editor=False):
        sim = Simulation(JsonStore(config).data if editor else copy.deepcopy(config))
        manager = sim.task_generation_manager
        records = []
        for time in times:
            records.extend(manager.update_until(time))
        generator = manager.generators[0]
        instance = next(i for i in generator.instances if i['department_id'] == 'D')
        runtime = generator._runtime_for_volume_key(instance)
        return records, runtime, manager

    def test_closing_poll_retains_volume_until_next_open_poll(self):
        for editor in (False, True):
            with self.subTest(editor=editor):
                config = accumulation_config()
                records, state, manager = self.run_updates(config, [0, 7200], editor)
                self.assertEqual([], records)
                self.assertAlmostEqual(1, state['volume'])  # one eligible hour * 24 m3 / 24 h
                next_records = manager.update_until(90000)  # Tuesday 09:00
                self.assertEqual([90000], [r.task.release_time for r in next_records])
                self.assertAlmostEqual(1, next_records[0].task.generated_volume_m3)
                self.assertAlmostEqual(0, state['volume'])
                self.assertEqual([], manager.update_until(90000))

    def test_continuous_mode_accumulates_without_inventing_collection_tasks(self):
        records, state, _ = self.run_updates(accumulation_config('continuous'), [0, 7200, 90000])
        self.assertEqual([], records)
        self.assertAlmostEqual(1, state['volume'])

    def test_sporadic_closed_poll_preserves_whole_and_fractional_events(self):
        config = accumulation_config('sporadic')
        config['task_generation']['categories']['stores'].update(frequency_per_day=36, volume_per_event_m3=0.2)
        records, state, manager = self.run_updates(config, [0, 7200])
        self.assertEqual([], records)
        self.assertAlmostEqual(1.5, sum(state['sporadic_accumulator'].values()))
        self.assertEqual(1, len(manager.update_until(90000)))
        self.assertAlmostEqual(0.5, sum(state['sporadic_accumulator'].values()))

    def test_threshold_event_volume_and_residual_are_conserved(self):
        config = accumulation_config()
        config['departments'][0]['operating_end_time'] = '12:00'
        config['task_generation']['categories']['stores'].update(
            base_daily_volume_m3=0, frequency_per_day=24, volume_per_event_m3=0.3, threshold_volume_m3=0.5)
        records, state, _ = self.run_updates(config, [0, 5400, 7200, 9000, 10800])
        self.assertEqual(1, len(records))
        self.assertAlmostEqual(0.5, records[0].task.generated_volume_m3)
        self.assertAlmostEqual(0.1, state['volume'])  # 2 fill events * .3 = .5 collected + .1 stored

    def test_category_closed_days_are_not_counted_in_a_long_poll(self):
        config = accumulation_config()
        config['simulation']['start_datetime'] = '2026-01-05T00:00:00'
        config['departments'][0].update(operating_start_time='00:00', operating_end_time='24:00')
        config['task_generation']['categories']['stores'].update(days_active=['mon'], base_daily_volume_m3=1, threshold_volume_m3=1)
        records, state, manager = self.run_updates(config, [0, 7 * 86400])
        self.assertEqual(1, len(records))  # only the preceding Monday is eligible
        self.assertAlmostEqual(0, state['volume'])
        self.assertEqual([], manager.update_until(7 * 86400))

    def test_poll_landing_on_inactive_date_retains_prior_active_volume(self):
        config = accumulation_config()
        config['simulation']['start_datetime'] = '2026-01-05T00:00:00'
        config['departments'][0].update(operating_start_time='00:00', operating_end_time='24:00')
        config['task_generation']['categories']['stores'].update(days_active=['mon'], base_daily_volume_m3=1, threshold_volume_m3=1)
        records, state, manager = self.run_updates(config, [86400])
        self.assertEqual([], records)
        self.assertAlmostEqual(1, state['volume'])
        self.assertEqual(1, len(manager.update_until(7 * 86400)))

    def test_fortnight_skipped_week_contributes_no_volume(self):
        config = accumulation_config()
        config['simulation']['start_datetime'] = '2026-01-05T00:00:00'
        config['departments'][0].update(operating_start_time='00:00', operating_end_time='24:00')
        config['task_generation']['categories']['stores'].update(run_every_fortnight=True, base_daily_volume_m3=1, threshold_volume_m3=1)
        records, state, _ = self.run_updates(config, [0, 14 * 86400])
        self.assertEqual(7, len(records))
        self.assertAlmostEqual(0, state['volume'])

    def test_poll_partition_changes_release_times_but_not_accumulated_total(self):
        for polls in ([0, 90000], [0, 3600, 5400, 7200, 43200, 90000]):
            config = accumulation_config()
            records, state, _ = self.run_updates(config, polls)
            self.assertAlmostEqual(1, sum(r.task.generated_volume_m3 for r in records) + state['volume'])

    def test_decimal_threshold_collects_exact_total_without_losing_last_container(self):
        config = accumulation_config()
        config['departments'][0]['operating_end_time'] = '12:00'
        config['task_generation']['categories']['stores'].update(base_daily_volume_m3=14.4, threshold_volume_m3=0.2)
        records, state, _ = self.run_updates(config, [7200])
        self.assertEqual(3, len(records))  # one eligible hour: .6 m3 / .2 = 3
        self.assertAlmostEqual(0, state['volume'])
        config['task_generation']['categories']['stores']['base_daily_volume_m3'] = 24 * (0.2 - 1e-8)
        records, state, _ = self.run_updates(config, [7200])
        self.assertEqual([], records)
        self.assertAlmostEqual(0.2 - 1e-8, state['volume'])

    def test_fractional_event_polls_do_not_lose_a_whole_event_to_roundoff(self):
        for mode in ('sporadic', 'threshold'):
            config = accumulation_config(mode)
            config['simulation']['start_datetime'] = '2026-01-05T09:00:00'
            config['task_generation']['categories']['stores'].update(
                frequency_per_day=144, base_daily_volume_m3=0, volume_per_event_m3=1)
            records, state, _ = self.run_updates(config, list(range(60, 601, 60)))
            self.assertEqual(1, len(records))  # ten increments of 0.1 event
            self.assertAlmostEqual(0, state['volume'])

    def test_malformed_accumulation_rates_are_rejected_before_normalisation(self):
        for field in ('base_daily_volume_m3', 'threshold_volume_m3', 'frequency_per_day', 'volume_per_event_m3'):
            for value in (-1, True, 'nan', 'inf'):
                config = accumulation_config()
                config['task_generation']['categories']['stores'][field] = value
                for consumer in (Simulation, JsonStore):
                    with self.assertRaisesRegex(ValueError, field):
                        consumer(config)

    def test_final_partial_poll_dispatches_the_calculated_demand_in_full_simulation(self):
        for mode in ('sporadic', 'threshold'):
            config = accumulation_config(mode)
            config['simulation'].update(start_datetime='2026-01-05T09:00:00', end_datetime='2026-01-05T09:10:00')
            config['task_generation']['update_interval_sec'] = 900
            config['task_generation']['categories']['stores'].update(
                base_daily_volume_m3=144 if mode == 'threshold' else 0,
                frequency_per_day=144 if mode == 'sporadic' else 0)
            sim = Simulation(config)
            with contextlib.redirect_stdout(io.StringIO()), patch.object(sim, 'schedule_task_release', wraps=sim.schedule_task_release) as released:
                sim.run()
            self.assertEqual([600], [call.args[0].release_time for call in released.call_args_list])
            self.assertEqual(1, len(sim.completed_task_records))
            self.assertEqual(set(), sim.failed_task_ids)


if __name__ == '__main__':
    unittest.main()
