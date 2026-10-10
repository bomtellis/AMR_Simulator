"""Independent elapsed-prefix references, never trusting future planned status."""
import contextlib
import copy
import io
import json
import math
import unittest

from amr_partial_run import derive_partial_run, PartialRunError
from amr_trajectories import (Pose, Motion, Trajectory, plan_trajectory,
                              plan_reverse_trajectory, plan_lateral_trajectory)
from amr_trajectory_dynamics import retime_trajectory
from tests.test_directional_trajectories import settings


FROZEN = {'simulation': {'start_datetime': '2026-01-05T00:00:00'},
          'amrs': [{'id': 'R', 'quantity': 1}]}


def movement_row(path, *, start=0, power=1000, event_id='move'):
    energy = power * path.duration_sec / 3600000
    return {'event_id': event_id, 'event_type': 'segment_corridor', 'segment_type': 'corridor',
            'amr_id': 'R-1', 'task_id': 'T', 'journey_id': 'journey-1',
            'sim_time_sec': start, 'start_time': start, 'end_time': start + path.duration_sec,
            'duration_sec': round(path.duration_sec, 3), 'status': 'completed',
            'motion_model': 'geometric_v1', 'trajectory_json': json.dumps(path.to_dict()),
            'energy_kwh': energy,
            'details': json.dumps({'duration': path.duration_sec, 'energy_kwh': energy,
                                   'energy_source': 'amr_battery'})}


def straight():
    path = plan_trajectory([(0, 0), (10, 0)], minimum_radius_m=2, speed_m_per_sec=2,
                           pivot_allowed=True, pivot_speed_deg_per_sec=90)
    return retime_trajectory(path, settings(forward_speed_m_per_sec=2))


class PartialRunTests(unittest.TestCase):
    def test_mid_acceleration_clips_distance_and_energy_using_different_progress_bases(self):
        row = movement_row(straight(), start=2)
        result = derive_partial_run([row], FROZEN, stop_time=3)
        activity = result['activities'][0]
        self.assertEqual('partial', activity['state'])
        self.assertEqual((2, 3), (activity['executed_start_time_sec'], activity['executed_end_time_sec']))
        self.assertAlmostEqual(.5, activity['elapsed_distance_m'])  # .5*a*t²
        self.assertAlmostEqual(.5, activity['pose_at_cutoff']['x'])
        self.assertAlmostEqual(1000 / 3600000, activity['elapsed_model_energy_kwh'])  # power*time
        self.assertEqual('journey-1', activity['journey_id'])
        self.assertEqual(['T'], activity['task_ids'])
        json.dumps(result, allow_nan=False)

    def test_reverse_and_lateral_partial_progress_preserves_body_heading(self):
        reverse = plan_reverse_trajectory([(0, 0), (-10, 0)], minimum_radius_m=2,
            speed_m_per_sec=1, pivot_allowed=False, pivot_speed_deg_per_sec=90, start_heading_deg=0)
        lateral = plan_lateral_trajectory(Pose(0, 0, math.pi / 2), (10, 0),
                                          speed_m_per_sec=1, lateral_allowed=True)
        for path, x, heading in ((reverse, -.125, 0), (lateral, .125, math.pi / 2)):
            path = retime_trajectory(path, settings(lateral_speed_m_per_sec=1))
            record = derive_partial_run([movement_row(path)], FROZEN, stop_time=.5)['activities'][0]
            self.assertAlmostEqual(.125, record['elapsed_distance_m'])
            self.assertAlmostEqual(x, record['pose_at_cutoff']['x'])
            self.assertAlmostEqual(0, math.remainder(record['pose_at_cutoff']['heading_rad'] - heading, 2 * math.pi))

    def test_partial_pivot_has_rotation_but_no_translation(self):
        raw = Trajectory((Motion('pivot', Pose(0, 0, 0), Pose(0, 0, math.pi / 2), 0, 1,
                                  sweep_rad=math.pi / 2),), 2, True)
        path = retime_trajectory(raw, settings())
        record = derive_partial_run([movement_row(path)], FROZEN, stop_time=.5)['activities'][0]
        self.assertEqual(0, record['elapsed_distance_m'])
        self.assertAlmostEqual(math.pi / 16, record['elapsed_rotation_rad'])
        self.assertAlmostEqual(math.pi / 16, record['pose_at_cutoff']['heading_rad'])
        self.assertAlmostEqual(500 / 3600000, record['elapsed_model_energy_kwh'])

    def test_future_segment_completed_status_is_only_a_plan(self):
        row = movement_row(straight(), start=10)
        record = derive_partial_run([row], FROZEN, stop_time=5)['activities'][0]
        self.assertEqual('planned', record['state'])
        self.assertIsNone(record['executed_start_time_sec'])
        self.assertIsNone(record['executed_end_time_sec'])
        self.assertIsNone(record['pose_at_cutoff'])
        self.assertEqual(0, record['elapsed_distance_m'])
        self.assertEqual(0, record['elapsed_model_energy_kwh'])
        self.assertGreater(record['planned_model_energy_kwh'], 0)

    def test_handling_interrupted_completed_and_zero_duration_boundaries(self):
        row = {'event_id': 'pickup', 'event_type': 'segment_pickup', 'amr_id': 'R-1',
               'task_id': 'T', 'sim_time_sec': 2, 'duration_sec': 4, 'status': 'completed',
               'start_x': 1, 'start_y': 2, 'end_x': 1, 'end_y': 2, 'amr_rotation_start_deg': 90}
        for cutoff, state, handling in ((1, 'planned', 'planned'), (2, 'planned', 'planned'),
                                         (3, 'partial', 'interrupted'), (6, 'executed', 'completed')):
            activity = derive_partial_run([row], FROZEN, stop_time=cutoff)['activities'][0]
            self.assertEqual(state, activity['state'])
            self.assertEqual(handling, activity['handling_state'])
            self.assertEqual(0, activity['elapsed_distance_m'])
            self.assertIsNone(activity['elapsed_model_energy_kwh'])
        row['duration_sec'] = 0
        activity = derive_partial_run([row], FROZEN, stop_time=2)['activities'][0]
        self.assertEqual('executed', activity['state'])
        self.assertEqual(0, activity['elapsed_duration_sec'])

    def test_task_completion_requires_actual_completion_event_before_cutoff(self):
        rows = [dict(event_id='release', event_type='task_release', task_id='T', sim_time_sec=0),
                dict(event_id='assignment', event_type='task_assigned', task_id='T', sim_time_sec=1),
                movement_row(straight(), start=1),
                dict(event_id='complete', event_type='task_complete', task_id='T', sim_time_sec=8)]
        partial = derive_partial_run(rows, FROZEN, stop_time=3)['task_outcomes'][0]
        self.assertEqual('assigned_unfinished', partial['outcome'])
        self.assertIsNone(partial['completion_time_sec'])
        self.assertEqual(['complete'], partial['future_event_ids'])
        final = derive_partial_run(rows, FROZEN, stop_time=8)['task_outcomes'][0]
        self.assertEqual('completed', final['outcome'])
        self.assertEqual(8, final['completion_time_sec'])

    def test_charging_plan_and_commit_credit_are_not_elapsed_physical_energy(self):
        rows = [dict(event_id='charge', event_type='segment_charge', amr_id='R-1',
                     sim_time_sec=0, duration_sec=100, energy_kwh=5,
                     details=json.dumps(dict(energy_kwh=5, energy_source='battery_charge_input'))),
                dict(event_id='credit', event_type='battery_charge_applied', amr_id='R-1',
                     sim_time_sec=0, energy_kwh=5,
                     details=json.dumps(dict(energy_kwh=5, energy_source='battery_charge_input',
                                             basis='credited_at_route_commit')))]
        result = derive_partial_run(rows, FROZEN, stop_time=10)
        activity = result['activities'][0]
        self.assertEqual('partial', activity['state'])
        self.assertIsNone(activity['elapsed_model_energy_kwh'])
        self.assertTrue(any('charging energy' in s for s in activity['missing_evidence']))
        self.assertEqual(5, result['applied_charge_records'][0]['accounting_credit_kwh'])
        self.assertIsNone(result['applied_charge_records'][0]['physical_charge_energy_kwh'])

    def test_missing_energy_is_distinct_from_zero(self):
        row = movement_row(straight())
        row['details'] = '{}'
        result = derive_partial_run([row], FROZEN, stop_time=1)['activities'][0]
        self.assertIsNone(result['elapsed_model_energy_kwh'])
        self.assertTrue(result['missing_evidence'])
        row = movement_row(straight(), power=0)
        self.assertEqual(0, derive_partial_run([row], FROZEN, stop_time=1)['activities'][0]['elapsed_model_energy_kwh'])

    def test_datetime_rounding_and_exact_profile_duration_remain_distinct(self):
        row = movement_row(straight(), start=2)
        row['start_time'] = '2026-01-05 00:00:02.000'
        row['end_time'] = '2026-01-05 00:00:09.000'
        original = copy.deepcopy(row)
        first = derive_partial_run([row], FROZEN, stop_time=3)
        second = derive_partial_run([row], FROZEN, stop_time=3)
        self.assertEqual(first, second)
        self.assertEqual(original, row)
        self.assertEqual(64, len(first['frozen_inputs_sha256']))

    def test_malformed_evidence_fails_explicitly_and_duplicate_ids_are_checked(self):
        row = movement_row(straight())
        for mutation in ({'trajectory_json': '{broken'}, {'duration_sec': 999},
                         {'end_time': 200}, {'amr_id': 'missing'}, {'energy_kwh': 50},
                         {'sim_time_sec': math.nan}):
            with self.subTest(mutation=mutation), self.assertRaises(PartialRunError):
                derive_partial_run([{**row, **mutation}], FROZEN, stop_time=1)
        self.assertEqual(1, len(derive_partial_run([row, copy.deepcopy(row)], FROZEN, stop_time=1)['activities']))
        with self.assertRaises(PartialRunError):
            derive_partial_run([row, {**row, 'status': 'different'}], FROZEN, stop_time=1)
        for cutoff in (-1, math.inf, math.nan, True):
            with self.assertRaises(PartialRunError):
                derive_partial_run([], FROZEN, stop_time=cutoff)

    def test_real_simulator_rows_ignore_future_completion_and_clip_loaded_model_energy(self):
        from simulator import Simulation
        from tests.test_motion_dynamics_simulation import dynamics_config
        config = dynamics_config()
        sim = Simulation(config, verbose=True)
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        result = derive_partial_run(sim.verbose_rows, config, stop_time=3)
        moving = next(r for r in result['activities'] if r['segment_type'] == 'corridor')
        self.assertAlmostEqual(.5, moving['elapsed_distance_m'])
        self.assertAlmostEqual(750 * 1.035 / 3600000, moving['elapsed_model_energy_kwh'])
        self.assertEqual('partial', moving['state'])
        self.assertEqual('assigned_unfinished', result['task_outcomes'][0]['outcome'])
        dropoff = next(r for r in result['activities'] if r['segment_type'] == 'dropoff')
        self.assertEqual('planned', dropoff['handling_state'])


if __name__ == '__main__':
    unittest.main()
