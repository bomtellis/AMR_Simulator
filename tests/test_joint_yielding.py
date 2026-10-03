"""A real directed retreat that needs the requester to vacate its parked tail."""
import contextlib
import io
import math
import unittest

from amr_occupancy_plan import occupancy_plan
from amr_sim_models import Location, Task
from amr_trajectories import Pose
from simulator import Simulation
from tests.test_geometric_yielding import yielding_config


def joint_yielding_config():
    """Requester uses the lower route; blocker loops above it to a rear bay.

    A(-2,0) -> J(0,0) -> D(6,0) -> C(8,0) -> B(16,0).
    The blocker starts at D and retreats via C,Q(8,6),U(0,6),J,A,P(-8,0).
    J->D is one-way, so there is no invented shortcut through the requester.
    The complete joint claims, not removal of a tail, establish safe passage.
    """
    config = yielding_config()
    points = {'A': (-2, 0), 'D': (6, 0), 'B': (16, 0), 'J': (0, 0),
              'C': (8, 0), 'Q': (8, 6), 'U': (0, 6), 'P': (-8, 0)}
    def point(name):
        return dict(name=name, floor=0, x=points[name][0], y=points[name][1])
    config['locations'] = [point(name) for name in ('A', 'D', 'B')]
    config['corridors'] = {'auto_connect': False,
        'nodes': [point(name) for name in ('J', 'C', 'Q', 'U', 'P')],
        'edges': [{'from': a, 'to': b, 'width_m': 1, 'bidirectional': two,
                   'traffic_mode': 'single_file'} for a, b, two in
                  [('A', 'J', True), ('J', 'D', False), ('D', 'C', False),
                   ('C', 'B', False), ('C', 'Q', False), ('Q', 'U', False),
                   ('U', 'J', False), ('A', 'P', False)]]}
    config['geometry']['floors'][0].update(bounds=[-12, -3, 20, 10],
        passing_places=[dict(id='P', bounds=[-9, -1, -7, 1])])
    config['geometry']['initial_placements'][1].update(location='D', heading_deg=0)
    for robot in config['amrs']:
        robot['manoeuvring'].update(minimum_radius_m=.5, pivot_allowed=True)
        for settings in robot['movement'].values():
            settings.update(minimum_radius_m=.5, pivot_allowed=True)
    return config


class JointYieldingTests(unittest.TestCase):
    def test_removed_locked_work_does_not_hold_blocker_for_a_stale_heap_entry(self):
        sim = Simulation(yielding_config(), verbose=True)
        task = next(event.payload['task'] for event in sim.events if event.event_type == 'task_release')
        sim._queue_pending_task(task)
        stale = Task('removed', 'C', 'B', 'Box', priority=task.priority, release_time=0)
        stale.locked_amr_id = 'S-1'
        sim._queue_pending_task(stale)
        # Pending work uses lazy heap removal; internal non-head tombstones can remain.
        sim._removed_pending_task_ids.add(stale.id)
        admitted = sim._try_geometric_yield(0)
        self.assertTrue(admitted)
        self.assertIs(task, admitted[1])
        self.assertEqual('P', sim.amrs_by_id['S-1'].location_name)

    def test_reference_has_two_jointly_feasible_complete_plans(self):
        sim = Simulation(joint_yielding_config())
        original = sim.geometric_occupancy
        requester, blocker = sim.amrs
        try:
            sim.geometric_occupancy = original.provisional_without_parked_tail(requester.id, 0)
            route, _, _ = sim._same_floor_segments(blocker, sim._robot_location(blocker),
                Location(name='P', floor=0, x=-8, y=0), start_time_value=0)
            sim.geometric_occupancy = original.provisional_without_parked_tail(blocker.id, 0)
            request = sim._estimate_task_for_amr(requester, Task('T', 'A', 'B', 'Box'), reserve=False)
        finally:
            sim.geometric_occupancy = original
        self.assertIsNotNone(request)
        # 18 m at 2 m/s, acceleration/braking 1 m/s²: 2+7+2 s;
        # plus two 2-second handling operations = 15 seconds.
        self.assertAlmostEqual(15, request['finish_time'])
        common = dict(start=0, floor=0, robot_length_m=requester.length_m,
                      robot_width_m=requester.width_m, loaded_length_m=1,
                      loaded_width_m=.7, robot_clearance_m=0)
        request_claims = occupancy_plan(initial_pose=Pose(-2, 0, 0), owner=requester.id,
                                       segments=request['segments'], **common)
        retreat_claims = occupancy_plan(initial_pose=Pose(6, 0, 0), owner=blocker.id,
                                       segments=route, **common)
        self.assertFalse(original.replace_plan(requester.id, 0, request_claims).accepted)
        self.assertFalse(original.replace_plan(blocker.id, 0, retreat_claims).accepted)
        result = original.replace_plans({requester.id: (0, request_claims), blocker.id: (0, retreat_claims)})
        self.assertTrue(result.accepted)
        self.assertFalse(result.conflicts)
        self.assertIs(original, sim.geometric_occupancy)

    def test_joint_yield_admits_requester_and_blocker_then_completes_real_task_once(self):
        sim = Simulation(joint_yielding_config(), verbose=True)
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        self.assertEqual('finished', sim._evidence_run_status)
        self.assertEqual(['T'], [r['task_id'] for r in sim.completed_task_records])
        self.assertFalse(sim.failed_tasks)
        self.assertEqual('P', sim.amrs_by_id['S-1'].location_name)
        self.assertEqual(0, sim.amrs_by_id['S-1'].completed_tasks)
        self.assertGreater(sim.amrs_by_id['S-1'].total_energy_used_kwh, 0)
        self.assertEqual(1, sum(r['event_type'] == 'geometric_yield_started' for r in sim.verbose_rows))
        self.assertEqual(1, sum(r['event_type'] == 'geometric_yield_complete' for r in sim.verbose_rows))
        self.assertEqual(1, sum(r['event_type'] == 'task_assigned' and r['task_id'] == 'T' for r in sim.verbose_rows))
        tails = [row for row in sim.geometric_occupancy.rows() if math.isinf(row['end'])]
        self.assertEqual(2, len(tails))
        self.assertTrue(all(row['occupancy_kind'] == 'stationary' for row in tails))
        # Audit the actual published complete histories, not just the preflight
        # candidate: no temporary omitted-tail view may survive joint dispatch.
        original = Simulation(joint_yielding_config()).geometric_occupancy
        rows = sim.geometric_occupancy.rows()
        plans = {owner: (0, [row for row in rows if row['owner'] == owner])
                 for owner in ('R-1', 'S-1')}
        self.assertTrue(all(any(row['occupancy_kind'] == 'moving' for row in claim_rows)
                            for _, claim_rows in plans.values()))
        audited = original.replace_plans(plans)
        self.assertTrue(audited.accepted, audited.conflicts)


if __name__ == '__main__':
    unittest.main()
