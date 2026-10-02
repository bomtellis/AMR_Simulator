"""Scheduled releases use calendar time, independently of demand polling."""
import contextlib
import datetime
import io
import unittest
from unittest.mock import patch

from simulator import Simulation
from amr_demand_preview import build_demand_preview
from amr_sim_task_generation import TaskGenerationManager
from tests.test_generation_reference import grouped_config
from tests.test_payload_conservation import seeded_service_config


class ScheduledDispatchTests(unittest.TestCase):
    def config(self, start='2026-01-05T00:00:00', seconds=600, times=None, interval=900):
        config = grouped_config()
        config['simulation']['start_datetime'] = start
        config['simulation']['end_datetime'] = (
            datetime.datetime.fromisoformat(start) + datetime.timedelta(seconds=seconds)).isoformat()
        config['task_generation']['update_interval_sec'] = interval
        config['task_generation']['categories']['stores']['scheduled_times'] = times or ['00:01']
        return config

    def run_sim(self, config):
        with contextlib.redirect_stdout(io.StringIO()):
            sim = Simulation(config)
            with patch.object(sim, '_handle_event', wraps=sim._handle_event) as events:
                sim.run()
        self.assertFalse(sim.failed_task_ids)
        sim.observed_test_events = [(c.args[0].event_type, c.args[0].time)
                                    for c in events.call_args_list]
        return sim

    def starts(self, sim):
        return sorted((datetime.datetime.fromisoformat(r['start_datetime']) -
                       sim.clock.start_datetime).total_seconds() for r in sim.completed_task_records)

    def test_off_grid_schedule_starts_at_release_and_finishes_nine_seconds_later(self):
        sim = self.run_sim(self.config())
        self.assertEqual([60], self.starts(sim))
        self.assertEqual('2026-01-05 00:01:09.000', sim.completed_task_records[0]['finish_datetime'])

    def test_poll_interval_does_not_change_uncontended_scheduled_start(self):
        for interval in (60, 90.5, 900, 3600):
            with self.subTest(interval=interval):
                self.assertEqual([60], self.starts(self.run_sim(self.config(interval=interval))))

    def test_explicit_wake_does_not_shift_or_add_consumption_polls(self):
        sim = self.run_sim(self.config(seconds=1000, times=['00:01', '00:16']))
        self.assertEqual([0, 900, 1000], [t for event, t in sim.observed_test_events if event == 'generator_tick'])
        self.assertEqual([60, 960], self.starts(sim))

    def test_last_minute_before_midnight_is_not_lost(self):
        config = self.config(start='2026-01-05T23:58:00', times=['23:59'], seconds=180)
        self.assertEqual([60], self.starts(self.run_sim(config)))

    def test_schedule_before_simulation_start_is_not_replayed_at_zero(self):
        config = self.config(start='2026-01-05T12:00:00', times=['09:00'], seconds=600)
        self.assertEqual([], self.starts(self.run_sim(config)))

    def test_daily_recurrence_across_midnight(self):
        config = self.config(start='2026-01-05T23:58:00', times=['23:59'], seconds=86500)
        self.assertEqual([60, 86460], self.starts(self.run_sim(config)))

    def test_closed_department_releases_at_opening_between_polls(self):
        config = self.config(start='2026-01-05T08:58:00', times=['08:59'], seconds=240)
        config['departments'][0].update(operating_start_time='09:01', operating_end_time='17:00')
        self.assertEqual([180], self.starts(self.run_sim(config)))

    def test_closed_department_retains_schedule_shifted_to_next_day(self):
        config = self.config(start='2026-01-05T23:58:00', times=['23:59'], seconds=33000)
        config['departments'][0].update(operating_start_time='09:01', operating_end_time='17:00')
        self.assertEqual([32580], self.starts(self.run_sim(config)))

    def test_horizon_inclusive_without_later_schedule(self):
        config = self.config(seconds=120, times=['00:02', '00:03'])
        self.assertEqual([120], self.starts(self.run_sim(config)))

    def test_disabled_category_groups_still_obey_global_disable(self):
        config = self.config()
        config['task_generation']['enabled'] = False
        self.assertEqual([], self.starts(self.run_sim(config)))

    def test_weekday_and_fortnight_gates_are_preserved(self):
        config = self.config(seconds=15 * 86400 + 120)
        category = config['task_generation']['categories']['stores']
        category.update(days_active=['mon'], run_every_fortnight=True)
        self.assertEqual([60, 14 * 86400 + 60], self.starts(self.run_sim(config)))

    def test_calendar_planning_does_not_create_tasks_or_consume_schedule(self):
        config = self.config()
        sim = Simulation(config)
        generator = sim.task_generation_manager.generators[0]
        self.assertEqual(0, generator.task_counter)
        self.assertFalse(generator.scheduled_emitted)
        self.assertEqual([60], sim.task_generation_manager.scheduled_wake_times(600))
        self.assertEqual([60], sim.task_generation_manager.scheduled_wake_times(600))
        self.assertEqual([60], [r.task.release_time for r in generator.update_until(600)])
        self.assertEqual([], generator.update_until(600))

    def test_overlapping_schedule_and_poll_produce_one_task(self):
        sim = self.run_sim(self.config(seconds=1000, times=['00:15', '00:15']))
        self.assertEqual([900], self.starts(sim))
        self.assertFalse(any(event == 'scheduled_generator_tick' for event, _t in sim.observed_test_events))

    def test_two_group_services_at_same_time_remain_separate(self):
        config = self.config()
        category = config['task_generation']['categories']['stores']
        category['department_groups'].append({'id': 'G2', 'departments': ['D'], 'payload': {'enabled': True}})
        config['amrs'][0]['quantity'] = 2
        config['simulation']['task_release_stagger_sec'] = 0
        sim = self.run_sim(config)
        self.assertEqual(2, len(sim.completed_task_records))
        releases = [t for event, t in sim.observed_test_events if event == 'task_release']
        self.assertEqual([60], releases)  # Same-time releases are queued together.

    def test_incremental_manager_calls_retain_a_deferred_previous_day(self):
        config = self.config(start='2026-01-05T23:58:00', times=['23:59'], seconds=33000)
        config['departments'][0].update(operating_start_time='09:01', operating_end_time='17:00')
        # The preview uses a manager directly, without simulator event execution.
        sim = Simulation(config)
        manager = TaskGenerationManager(config, sim.clock, sim.locations, sim.payloads)
        self.assertEqual([], manager.update_until(119))
        self.assertEqual([32580], [r.task.release_time for r in manager.update_until(33000)])
        preview = build_demand_preview(config)
        self.assertEqual([32580], [r['release_seconds'] for r in preview['tasks']])

    def test_earlier_nominal_time_can_be_deferred_into_the_simulation(self):
        config = self.config(start='2026-01-05T09:00:00', times=['08:59'], seconds=240)
        config['departments'][0].update(operating_start_time='09:01', operating_end_time='17:00')
        self.assertEqual([60], self.starts(self.run_sim(config)))

    def test_timeframe_starts_at_window_start_between_polls(self):
        config = self.config()
        config['task_generation']['categories']['stores'].update(
            generation_mode='timeframe', timeframe_start='00:01', timeframe_end='00:04',
            timeframe_payload_multiple=1)
        self.assertEqual([60], self.starts(self.run_sim(config)))

    def test_staff_spaced_timeframe_releases_each_slot_between_polls(self):
        config = self.config()
        config['task_generation']['categories']['stores'].update(
            generation_mode='timeframe', timeframe_start='00:01', timeframe_end='00:04',
            timeframe_payload_multiple=3, requires_staff=True,
            staff_use_custom_working_hours=True,
            staff_working_hours={'mon': {'enabled': True, 'start_time': '00:00', 'end_time': '24:00'}},
            staff_handling_minutes=0)
        sim = self.run_sim(config)
        self.assertEqual([60, 120, 180], [t for event, t in sim.observed_test_events if event == 'task_release'])
        self.assertEqual([60, 120, 180], self.starts(sim))

    def test_scheduled_threshold_accumulates_at_each_fill_without_precreating_bins(self):
        config = seeded_service_config()
        config['task_generation']['update_interval_sec'] = 900
        config['task_generation']['categories']['service'].update(
            generation_mode='scheduled_threshold', scheduled_times=['00:01', '00:02'],
            volume_per_event_m3=0.5, threshold_volume_m3=1.0)
        sim = self.run_sim(config)
        self.assertEqual([120, 129], self.starts(sim))
        self.assertEqual(1, len({r['payload_instance_id'] for r in sim.completed_task_records}))

    def test_overnight_timeframe_slot_after_start_is_retained(self):
        config = self.config(start='2026-01-05T23:58:00', seconds=300)
        config['task_generation']['categories']['stores'].update(
            generation_mode='timeframe', timeframe_start='23:59', timeframe_end='00:02',
            timeframe_payload_multiple=1)
        self.assertEqual([60], self.starts(self.run_sim(config)))

    def test_fractional_staff_slots_do_not_round_to_poll_or_minute(self):
        config = self.config()
        config['amrs'][0]['quantity'] = 7
        config['task_generation']['categories']['stores'].update(
            generation_mode='timeframe', timeframe_start='00:01', timeframe_end='00:02',
            timeframe_payload_multiple=7, requires_staff=True,
            staff_use_custom_working_hours=True,
            staff_working_hours={'mon': {'enabled': True, 'start_time': '00:00', 'end_time': '24:00'}},
            staff_handling_minutes=0)
        sim = self.run_sim(config)
        self.assertEqual(7, len(sim.completed_task_records))
        for expected, actual in zip([60 + i * 60 / 7 for i in range(7)], self.starts(sim)):
            self.assertAlmostEqual(expected, actual, delta=0.001)

    def test_timeframe_deferred_beyond_deadline_emits_nothing(self):
        config = self.config()
        config['departments'][0].update(operating_start_time='00:05', operating_end_time='17:00')
        config['task_generation']['categories']['stores'].update(
            generation_mode='timeframe', timeframe_start='00:01', timeframe_end='00:04')
        self.assertEqual([], self.starts(self.run_sim(config)))


if __name__ == '__main__':
    unittest.main()
