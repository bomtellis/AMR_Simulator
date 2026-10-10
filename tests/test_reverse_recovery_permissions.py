"""Recovery permission and bounded-search acceptance, independent of routing."""
import contextlib
import copy
import io
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from amr_geometric_recovery import MAX_RECOVERY_CANDIDATES, retreat_candidates
from amr_sim_models import Location
from amr_trajectories import TrajectoryError
from simulator import Simulation
from tests.test_geometric_yielding import yielding_config


def candidate_search(*, targets, reverse=None, lateral=False):
    config = yielding_config()
    movement = copy.deepcopy(config['amrs'][1]['movement'])
    for profile in movement.values():
        profile['lateral_allowed'] = lateral
        if lateral:
            profile['lateral_speed_m_per_sec'] = 1
        if reverse is not None:
            profile['reverse_allowed'] = reverse
    robot = SimpleNamespace(movement=movement, manoeuvring={'clearance_m': 0})
    start = Location(name='origin', floor=0, x=0, y=0)
    locations = [dict(name=f'candidate-{i}', floor=0, x=i+1, y=0)
                 for i in range(targets)]
    sim = SimpleNamespace(config={'geometry': {'floors': [{'floor': 0}]},
                                 'locations': locations},
                          _robot_location=lambda _: start,
                          _same_floor_segments=Mock(return_value=None))
    return sim, robot


class ReverseRecoveryPermissionsTests(unittest.TestCase):
    def test_forbidden_directions_do_not_consume_budget_or_call_route_search(self):
        # Exactly 256 allowed candidates fit the 256 limit; the old unconditional
        # three-direction multiplier incorrectly rejected all of these upfront.
        sim, robot = candidate_search(targets=MAX_RECOVERY_CANDIDATES, reverse=False)
        plans, failures = retreat_candidates(sim, robot, 12)
        self.assertFalse(plans)
        self.assertEqual(MAX_RECOVERY_CANDIDATES, sim._same_floor_segments.call_count)
        self.assertEqual({'forward'}, {call.kwargs['movement']
                                      for call in sim._same_floor_segments.call_args_list})
        self.assertEqual({'reverse', 'lateral'}, {failure['movement'] for failure in failures})
        self.assertTrue(all(failure['reason'] == 'infeasible_route' for failure in failures))
        self.assertTrue(all('permission forbids' in failure['detail'] for failure in failures))

    def test_allowed_candidate_overflow_is_still_explicit_search_limit(self):
        for targets, reverse, lateral in ((257, False, False), (129, True, False),
                                          (86, True, True)):
            with self.subTest(targets=targets, reverse=reverse, lateral=lateral):
                sim, robot = candidate_search(targets=targets, reverse=reverse, lateral=lateral)
                with self.assertRaises(TrajectoryError) as caught:
                    retreat_candidates(sim, robot, 0)
                self.assertEqual('search_limit', caught.exception.reason)
                sim._same_floor_segments.assert_not_called()

    def test_unversioned_reverse_omission_preserves_existing_permission(self):
        sim, robot = candidate_search(targets=2)
        retreat_candidates(sim, robot, 0)
        self.assertEqual(['forward', 'reverse', 'forward', 'reverse'],
                         [call.kwargs['movement'] for call in sim._same_floor_segments.call_args_list])

    def test_allowed_lateral_counts_without_enabling_reverse(self):
        sim, robot = candidate_search(targets=128, reverse=False, lateral=True)
        retreat_candidates(sim, robot, 0)
        self.assertEqual(256, sim._same_floor_segments.call_count)
        self.assertEqual({'forward', 'lateral'}, {call.kwargs['movement']
                                                for call in sim._same_floor_segments.call_args_list})

    def test_empty_reverse_forbidden_prevents_real_retreat_without_mutation(self):
        config = yielding_config()
        movement = config['amrs'][1]['movement']
        movement['empty']['reverse_allowed'] = False
        movement['loaded']['reverse_allowed'] = True
        sim = Simulation(config, verbose=True)
        robot = sim.amrs_by_id['S-1']
        initial_ledger = sim.geometric_occupancy
        initial_energy = robot.total_energy_used_kwh
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        self.assertFalse(sim.completed_task_records)
        self.assertEqual('C', robot.location_name)
        self.assertEqual(180, robot.rotation_deg)
        self.assertEqual(0, robot.total_busy_time)
        self.assertEqual(initial_energy, robot.total_energy_used_kwh)
        self.assertIs(initial_ledger, sim.geometric_occupancy)
        self.assertFalse(any(row['event_type'] == 'geometric_yield_started'
                             for row in sim.verbose_rows))
        failures = [failure for outcome in sim.geometric_recovery_outcomes
                    for failure in outcome.get('failures', [])]
        self.assertTrue(any(failure['movement'] == 'reverse'
                            and 'permission forbids' in failure.get('detail', '') for failure in failures))
        self.assertFalse(any(outcome.get('reason') == 'search_limit'
                             for outcome in sim.geometric_recovery_outcomes))

    def test_empty_permission_is_independent_of_loaded_reverse_prohibition(self):
        config = yielding_config()
        movement = config['amrs'][1]['movement']
        movement['empty']['reverse_allowed'] = True
        movement['loaded']['reverse_allowed'] = False
        sim = Simulation(config, verbose=True)
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        self.assertEqual(['T'], [row['task_id'] for row in sim.completed_task_records])
        robot = sim.amrs_by_id['S-1']
        self.assertEqual('P', robot.location_name)
        # Existing physical reference: sixteen metres at 1m/s with 1m/s²
        # acceleration and braking takes 17 seconds, empty handling consumes none.
        self.assertAlmostEqual(17, robot.total_busy_time)
        self.assertAlmostEqual(750*.75*17/3600000, robot.total_energy_used_kwh)


if __name__ == '__main__':
    unittest.main()
