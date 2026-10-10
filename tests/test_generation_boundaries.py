"""Independent demand counts at the generation horizon, including partial ticks.

These tests prove coverage, not exact-time dispatch between polling updates.
"""
import contextlib
import datetime
import io
import unittest
from unittest.mock import patch

from simulator import Simulation
from tests.test_generation_reference import grouped_config


class GenerationBoundaryTests(unittest.TestCase):
    def run_case(self, seconds, schedules, interval=900, enabled=True):
        config = grouped_config()
        start = datetime.datetime.fromisoformat(config['simulation']['start_datetime'])
        config['simulation']['end_datetime'] = (
            start + datetime.timedelta(seconds=seconds)).isoformat()
        config['task_generation']['enabled'] = enabled
        config['task_generation']['update_interval_sec'] = interval
        config['task_generation']['categories']['stores']['scheduled_times'] = schedules
        with contextlib.redirect_stdout(io.StringIO()):
            sim = Simulation(config)
            with patch.object(sim, 'schedule_task_release', wraps=sim.schedule_task_release) as scheduled:
                sim.run()
                sim.observed_test_releases = [call.args[0].release_time for call in scheduled.call_args_list]
        return sim

    def assert_releases(self, sim, expected):
        self.assertEqual(set(), sim.failed_task_ids)
        self.assertEqual(expected, sorted(sim.observed_test_releases))
        self.assertEqual(len(expected), len({r['task_id'] for r in sim.completed_task_records}))

    def test_run_shorter_than_interval_includes_scheduled_demand(self):
        self.assert_releases(self.run_case(600, ['00:01']), [60])

    def test_final_partial_interval_includes_each_rule_once(self):
        self.assert_releases(self.run_case(1000, ['00:01', '00:16']), [60, 960])

    def test_horizon_is_inclusive_and_later_schedule_is_excluded(self):
        self.assert_releases(self.run_case(600, ['00:10', '00:11']), [600])

    def test_exact_interval_boundary_does_not_duplicate_work(self):
        self.assert_releases(self.run_case(900, ['00:01', '00:15']), [60, 900])

    def test_disabled_generator_does_not_gain_a_final_update(self):
        self.assert_releases(self.run_case(600, ['00:01'], enabled=False), [])

    def test_zero_duration_only_includes_start_time(self):
        self.assert_releases(self.run_case(0, ['00:00', '00:01']), [0])


if __name__ == '__main__':
    unittest.main()
