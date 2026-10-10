"""Physical yielding frees a blocked delivery without creating synthetic tasks."""
import contextlib
import copy
import io
import json
import math
import unittest

from simulator import Simulation
from amr_sim_models import Task
from amr_trajectories import trajectory_from_dict
from tests.test_motion_dynamics_simulation import dynamics_config


def yielding_config():
    c = dynamics_config()
    c['locations'] = [dict(name=name, floor=0, x=x, y=0)
                      for name, x in [('A', 0), ('C', 8), ('B', 16)]]
    c['corridors'] = {'auto_connect': False,
                     'nodes': [dict(name='P', floor=0, x=24, y=0)],
                     'edges': [{'from': a, 'to': b, 'width_m': 1,
                                'bidirectional': True, 'traffic_mode': 'single_file'}
                               for a, b in [('A', 'C'), ('C', 'B'), ('B', 'P')]]}
    c['geometry']['floors'][0].update(bounds=[-3, -3, 35, 3], obstacles=[],
        passing_places=[{'id': 'Passing P', 'bounds': [23, -1, 25, 1]}])
    first = c['amrs'][0]
    for profile in first['movement'].values():
        profile.update(pivot_allowed=False, lateral_allowed=False,
                       forward_speed_m_per_sec=2, reverse_speed_m_per_sec=1,
                       acceleration_m_per_sec2=1, braking_m_per_sec2=1)
    first['manoeuvring']['pivot_allowed'] = False
    second = copy.deepcopy(first)
    second.update(id='S', payload_capacity_kg=5)
    c['amrs'] = [first, second]
    c['geometry']['initial_placements'] = [
        {'amr_id': 'R-1', 'location': 'A', 'heading_deg': 0},
        {'amr_id': 'S-1', 'location': 'C', 'heading_deg': 180}]
    c['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box', priority=1)]
    return c


class GeometricYieldingTests(unittest.TestCase):
    def test_idle_return_from_recovery_graph_node_reports_real_traffic_blockage(self):
        sim = self.run_case()
        robot = sim.amrs_by_id['S-1']
        task = Task('return','P','A','__empty__',release_time=sim.current_time)
        task.is_idle_return = True
        task.amr_id = robot.id
        # R-1 remains parked at B on the return route: wait for real occupancy,
        # rather than treating graph node P as a missing service location.
        self.assertEqual('',sim._released_task_terminal_failure_reason(task))
        self.assertIsNone(sim._estimate_task_for_amr(robot,task,reserve=True))
        self.assertIn('traffic_blocked',task.pending_reason)

    def run_case(self, config=None):
        sim = Simulation(config or yielding_config(), verbose=True)
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        return sim

    def ready_case(self):
        sim = Simulation(yielding_config(), verbose=True)
        release = next(event for event in sim.events if event.event_type == 'task_release')
        sim._queue_pending_task(release.payload['task'])
        return sim

    def test_reverse_recovery_clears_task_and_accounts_for_only_real_payload_work(self):
        sim = self.run_case()
        self.assertEqual(['T'], [row['task_id'] for row in sim.completed_task_records])
        self.assertFalse(sim.failed_tasks)
        blocker = sim.amrs_by_id['S-1']
        self.assertEqual('P', blocker.location_name)
        self.assertEqual(0, blocker.completed_tasks)
        self.assertAlmostEqual(24, sim._robot_location(blocker).x)
        # 16 m: 0.5 m accelerating, 15 m cruising, 0.5 m braking = 17 s.
        self.assertAlmostEqual(17, blocker.total_busy_time)
        self.assertAlmostEqual(750*.75*17/3600000, blocker.total_energy_used_kwh)
        rows = [row for row in sim.verbose_rows if row['amr_id'] == blocker.id
                and row['event_type'] == 'segment_corridor']
        self.assertTrue(rows)
        recorded = [trajectory_from_dict(json.loads(row['trajectory_json'])) for row in rows]
        self.assertAlmostEqual(16, sum(path.length_m for path in recorded))
        self.assertAlmostEqual(17, sum(path.duration_sec for path in recorded))
        for path in recorded:
            for motion in path.motions:
                self.assertEqual('reverse', motion.movement)
                self.assertNotEqual('pivot', motion.kind)
                self.assertAlmostEqual(0, math.sin(motion.start.heading))
                self.assertAlmostEqual(-1, math.cos(motion.start.heading))
        self.assertTrue(any(row['event_type'] == 'geometric_yield_complete'
                            and row['amr_id'] == blocker.id for row in sim.verbose_rows))
        self.assertTrue(all(not row['task_id'] for row in rows))
        self.assertTrue(all(row['journey_id'] for row in rows))
        self.assertFalse(any(row['amr_id'] == blocker.id and row['event_type'] in
                             ('payload_pickup', 'payload_dropoff', 'task_complete')
                             for row in sim.verbose_rows))

    def test_nearest_reachable_drawn_passing_place_wins(self):
        c = yielding_config()
        c['corridors']['nodes'].append(dict(name='Q', floor=0, x=32, y=0))
        c['corridors']['edges'].append({'from': 'P', 'to': 'Q', 'width_m': 1,
                                      'bidirectional': True, 'traffic_mode': 'single_file'})
        # Put the more distant place first to rule out configuration-order choice.
        c['geometry']['floors'][0]['passing_places'].insert(0,
            {'id': 'Passing Q', 'bounds': [31, -1, 33, 1]})
        sim = self.run_case(c)
        self.assertEqual(1, len(sim.completed_task_records))
        self.assertEqual('P', sim.amrs_by_id['S-1'].location_name)

    def test_busy_or_charging_blocker_is_not_preempted(self):
        for attribute, value in [('available_time', 50), ('is_charging', True)]:
            with self.subTest(attribute=attribute):
                sim = self.ready_case()
                blocker = sim.amrs_by_id['S-1']
                setattr(blocker, attribute, value)
                before = copy.deepcopy(vars(blocker))
                ledger = sim.geometric_occupancy
                self.assertFalse(sim._try_geometric_yield(0))
                self.assertEqual(before, vars(blocker))
                self.assertIs(ledger, sim.geometric_occupancy)

    def test_insufficient_recovery_energy_leaves_no_claims_or_side_effects(self):
        sim = self.ready_case()
        blocker = sim.amrs_by_id['S-1']
        blocker.battery_soc_percent = 0
        before = copy.deepcopy(vars(blocker))
        ledger, events = sim.geometric_occupancy, list(sim.events)
        self.assertFalse(sim._try_geometric_yield(0))
        self.assertIs(ledger, sim.geometric_occupancy)
        self.assertEqual(before, vars(blocker))
        self.assertEqual(events, sim.events)

    def test_unfitting_passing_place_does_not_teleport_blocker_or_complete_task(self):
        c = yielding_config()
        c['geometry']['floors'][0]['passing_places'][0]['bounds'] = [23, -.2, 25, .2]
        sim = self.run_case(c)
        self.assertFalse(sim.completed_task_records)
        self.assertEqual('C', sim.amrs_by_id['S-1'].location_name)
        self.assertEqual(0, sim.amrs_by_id['S-1'].total_energy_used_kwh)
        self.assertFalse(any(row['event_type'] == 'geometric_yield_complete' for row in sim.verbose_rows))

    def test_unmarked_safe_graph_anchor_can_be_used_without_passing_places(self):
        c = yielding_config()
        c['geometry']['floors'][0].pop('passing_places')
        sim = self.run_case(c)
        self.assertEqual(['T'], [row['task_id'] for row in sim.completed_task_records])
        self.assertEqual('P', sim.amrs_by_id['S-1'].location_name)
        self.assertTrue(any(row['event_type'] == 'geometric_yield_complete' for row in sim.verbose_rows))

    def test_reversing_cannot_traverse_a_graph_edge_against_its_direction(self):
        c = yielding_config()
        c['corridors']['edges'][-1].update({'from': 'P', 'to': 'B', 'bidirectional': False})
        sim = self.run_case(c)
        self.assertFalse(sim.completed_task_records)
        self.assertEqual('C', sim.amrs_by_id['S-1'].location_name)
        self.assertEqual(0, sim.amrs_by_id['S-1'].total_energy_used_kwh)
        self.assertFalse(any(row['event_type'] == 'geometric_yield_complete' for row in sim.verbose_rows))

    def test_recovery_does_not_clear_a_route_for_a_forbidden_requester(self):
        c = yielding_config()
        # Only S is allowed this work, but S cannot carry its payload. R's
        # otherwise valid blocked estimate must not trigger a pointless recovery.
        sim = Simulation(c, verbose=True)
        release = next(event for event in sim.events if event.event_type == 'task_release')
        release.payload['task'].locked_amr_id = 'S-1'
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        self.assertFalse(sim.completed_task_records)
        self.assertEqual('C', sim.amrs_by_id['S-1'].location_name)
        self.assertEqual(0, sim.amrs_by_id['S-1'].total_energy_used_kwh)
        self.assertFalse(any(row['event_type'] == 'geometric_yield_started' for row in sim.verbose_rows))


if __name__ == '__main__':
    unittest.main()
