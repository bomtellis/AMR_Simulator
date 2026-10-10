"""Per-state movement permissions at the geometry and timing boundaries."""
import contextlib
import copy
import io
import math
import unittest
from unittest.mock import patch

from amr_geometric_routing import geometry_input_findings, route_trajectory
from amr_motion_profiles import MotionProfileError, select_motion_settings
from amr_trajectories import TrajectoryError, plan_reverse_trajectory, trajectory_from_dict
from amr_trajectory_dynamics import retime_trajectory
from simulator import LocalManoeuvreError, Simulation
from tests.test_motion_dynamics_simulation import dynamics_config


def explicit_config():
    config = dynamics_config()
    movement = config['amrs'][0]['movement']
    movement['schema_version'] = 2
    movement['empty'].update(reverse_allowed=True, pivot_allowed=False)
    movement['loaded'].update(reverse_allowed=False, pivot_allowed=False)
    return config


class ReverseMovementIntegrationTests(unittest.TestCase):
    def reverse_leg(self, sim, payload=None):
        return sim._same_floor_segments(sim.amrs[0], sim.locations['A'], sim.locations['B'],
                                       payload=payload, start_heading_deg=180, movement='reverse')

    def test_empty_reverse_allowed_loaded_reverse_rejected_without_plan_or_energy(self):
        sim = Simulation(explicit_config(), verbose=True)
        result = self.reverse_leg(sim)
        self.assertIsNotNone(result)
        path = trajectory_from_dict(result[0][0]['trajectory'])
        self.assertAlmostEqual(20.5, path.duration_sec)  # d20/v1 + v/a2
        self.assertTrue(all(m.movement == 'reverse' for m in path.motions))
        robot_before = copy.deepcopy(vars(sim.amrs[0]))
        events_before = list(sim.events)
        ledger_before = sim.geometric_occupancy
        reservations_before = copy.deepcopy(sim.geometric_route_reservations)
        with patch('amr_reference_trajectories.plan_reference_trajectory') as planner:
            with self.assertRaises(LocalManoeuvreError) as rejected:
                self.reverse_leg(sim, sim.payloads['Box'])
        self.assertEqual('infeasible_motion', rejected.exception.reason)
        planner.assert_not_called()
        self.assertEqual(robot_before, vars(sim.amrs[0]))
        self.assertEqual(events_before, sim.events)
        self.assertIs(ledger_before, sim.geometric_occupancy)
        self.assertEqual(reservations_before, sim.geometric_route_reservations)
        self.assertEqual(0, sim.amrs[0].total_energy_used_kwh)
        self.assertFalse(any(row['event_type'] == 'segment_corridor' for row in sim.verbose_rows))

    def test_direct_route_boundary_rejects_permission_before_geometry(self):
        sim = Simulation(explicit_config())
        # A malformed route is deliberate: permission rejection must precede
        # coordinate lookup and path search, without publishing a substitute.
        with self.assertRaises(TrajectoryError) as raised:
            route_trajectory(sim, sim.amrs[0], {'edges': [{'to': 'Missing'}]},
                             sim.locations['A'], sim.locations['B'], sim.payloads['Box'],
                             'lengthways', 180, 'reverse')
        self.assertEqual('infeasible_motion', raised.exception.reason)
        self.assertIn('loaded', str(raised.exception))

    def test_nonpivot_robot_can_follow_reverse_curve(self):
        config = explicit_config()
        config['locations'][1].update(x=6, y=6)
        config['geometry']['floors'][0].update(bounds=[-3, -3, 9, 9], obstacles=[])
        config['corridors'] = {'auto_connect': False, 'nodes': [dict(name='J', floor=0, x=6, y=0)],
            'edges': [dict(**{'from': a, 'to': b}, width_m=2, traffic_mode='single_file')
                      for a, b in [('A', 'J'), ('J', 'B')]]}
        sim = Simulation(config)
        result = self.reverse_leg(sim)
        self.assertIsNotNone(result)
        path = trajectory_from_dict(result[0][0]['trajectory'])
        self.assertEqual(['line', 'arc', 'line'], [m.kind for m in path.motions])
        self.assertAlmostEqual(8 + math.pi, path.length_m)
        self.assertFalse(path.pivot_allowed)
        self.assertTrue(all(m.movement == 'reverse' for m in path.motions))

    def test_lateral_permission_is_independent_between_load_states_and_reverse(self):
        config = explicit_config()
        config['amrs'][0]['movement']['loaded'].update(lateral_allowed=True, lateral_speed_m_per_sec=.5)
        sim = Simulation(config)
        args = (sim.amrs[0], sim.locations['A'], sim.locations['B'])
        with self.assertRaises(LocalManoeuvreError) as rejected:
            sim._same_floor_segments(*args, movement='lateral', start_heading_deg=90)
        self.assertEqual('infeasible_motion', rejected.exception.reason)
        loaded = sim._same_floor_segments(*args, payload=sim.payloads['Box'],
                                          movement='lateral', start_heading_deg=90)
        self.assertIsNotNone(loaded)
        path = trajectory_from_dict(loaded[0][0]['trajectory'])
        self.assertTrue(all(m.movement == 'lateral' for m in path.motions))
        self.assertAlmostEqual(40.5, path.duration_sec)

    def test_retimer_cannot_bypass_loaded_reverse_permission(self):
        movement = explicit_config()['amrs'][0]['movement']
        source = plan_reverse_trajectory([(0, 0), (-4, 0)], minimum_radius_m=2,
            speed_m_per_sec=1, pivot_allowed=False, pivot_speed_deg_per_sec=90, start_heading_deg=0)
        self.assertAlmostEqual(4.5, retime_trajectory(source, select_motion_settings(movement, loaded=False)).duration_sec)
        with self.assertRaises(MotionProfileError) as raised:
            retime_trajectory(source, select_motion_settings(movement, loaded=True))
        self.assertEqual('infeasible_motion', raised.exception.reason)

    def test_invalid_explicit_schema_is_rejected_by_shared_checks_and_simulator(self):
        for mutation in ('missing', 'wrong_type', 'future_schema'):
            config = explicit_config()
            movement = config['amrs'][0]['movement']
            if mutation == 'missing':
                del movement['loaded']['reverse_allowed']
            elif mutation == 'wrong_type':
                movement['loaded']['reverse_allowed'] = 'false'
            else:
                movement['schema_version'] = 999
            with self.subTest(mutation=mutation):
                self.assertTrue(any('/movement' in path for path, _ in geometry_input_findings(config)))
                with self.assertRaises(ValueError):
                    Simulation(config)

    def test_unversioned_geometry_retains_previous_reverse_permission(self):
        old = Simulation(dynamics_config())
        explicit = explicit_config()
        explicit['amrs'][0]['movement']['loaded']['reverse_allowed'] = True
        explicit['amrs'][0]['movement']['loaded']['pivot_allowed'] = True
        new = Simulation(explicit)
        first = self.reverse_leg(old, old.payloads['Box'])
        second = self.reverse_leg(new, new.payloads['Box'])
        self.assertEqual(first[1:], second[1:])
        self.assertEqual(first[0][0]['trajectory'], second[0][0]['trajectory'])

    def test_simple_mode_results_unchanged_by_dormant_explicit_reverse_permissions(self):
        config = explicit_config()
        config['simulation']['motion_model'] = 'legacy'
        baseline = copy.deepcopy(config)
        del baseline['amrs'][0]['movement']
        simulations = []
        for candidate in (baseline, config):
            sim = Simulation(candidate, verbose=True)
            with contextlib.redirect_stdout(io.StringIO()):
                sim.run()
            simulations.append(sim)
        first, second = simulations
        self.assertEqual(first.current_time, second.current_time)
        self.assertEqual(first.completed_task_records, second.completed_task_records)
        self.assertEqual(first.amrs[0].total_energy_used_kwh, second.amrs[0].total_energy_used_kwh)
        self.assertFalse(any(row.get('trajectory_json') for row in second.verbose_rows))


if __name__ == '__main__':
    unittest.main()
