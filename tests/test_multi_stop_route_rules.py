"""Every loaded leg must satisfy every payload still on board.

The short A-X-B branch is 10 m and the A-Y-B branch is 20 m.
At 2 m/s with one shared pickup and two separate dropoffs, the latter
tour takes 2 + 20/2 + 2 + 2 = 16 seconds.
"""
import contextlib
import io
import copy
import json
import unittest
from pathlib import Path

from amr_sim_models import Task
from simulator import Simulation
from visualiser.models import JsonStore
from tests.test_engineering_reference import reference_config


SHORT = [['A', 'X'], ['X', 'B']]
LONG = [['A', 'Y'], ['Y', 'B']]


def multi_route_config():
    config = reference_config()
    config['simulation']['task_release_stagger_sec'] = 0
    config['building']['edge_slowdown_per_amr'] = 0
    config['corridors']['nodes'] = [dict(name=n, floor=0, x=x, y=y)
                                    for n, x, y in [('X', 3, 4), ('Y', 0, 10)]]
    config['corridors']['edges'] = [dict(zip(('from', 'to', 'distance_m'), edge), width_m=3)
                                   for edge in [('A', 'X', 5), ('X', 'B', 5),
                                                ('A', 'Y', 10), ('Y', 'B', 10)]]
    slot = dict(payload_capacity_kg=100, payload_length_capacity_m=2,
                payload_width_capacity_m=2, payload_height_capacity_m=2)
    config['amrs'][0].update(multi_stop_enabled=True,
                            payload_slots=[dict(slot, name='One'), dict(slot, name='Two')])
    return config


def multi_lift_config():
    config = multi_route_config()
    config['locations'][1]['floor'] = 1
    config['corridors']['nodes'] = []
    config['corridors']['edges'] = []
    for name, distance in [('L1', 1), ('L2', 2)]:
        config['lifts'].append(dict(id=name, served_floors=[0, 1], speed_floors_per_sec=1,
                                   door_time_sec=0, boarding_time_sec=0,
                                   floor_locations={'0': dict(x=distance, y=0), '1': dict(x=distance, y=0)},
                                   capacity_length_m=5, capacity_width_m=5, capacity_height_m=5,
                                   capacity_size_units=10, health_loss_per_journey_percent=0))
        config['corridors']['edges'].extend([
            dict(**{'from':'A', 'to':f'{name}-F0'}, width_m=3, distance_m=distance),
            dict(**{'from':f'{name}-F1', 'to':'B'}, width_m=3, distance_m=distance)])
    return config


class MultiStopRouteRulesTests(unittest.TestCase):
    def plan(self, tasks, config=None, reserve=True):
        sim = Simulation(config or multi_route_config())
        return sim, sim._estimate_multi_stop_for_amr(sim.amrs[0], tasks, reserve=reserve)

    def edges(self, plan):
        self.assertIsNotNone(plan)
        return [(s['from'], s['to']) for s in plan['segments'] if s['type'] == 'corridor']

    def test_both_loaded_payloads_use_their_common_allowed_edges(self):
        tasks = [Task('T1', 'A', 'B', 'Box', allowed_edges=SHORT + LONG),
                 Task('T2', 'A', 'B', 'Box', allowed_edges=LONG)]
        _sim, plan = self.plan(tasks)
        self.assertEqual([('A', 'Y'), ('Y', 'B')], self.edges(plan))
        self.assertEqual(16, plan['duration'])

    def test_rule_enforcement_is_independent_of_task_list_order(self):
        for reverse in (False, True):
            tasks = [Task('T1', 'A', 'B', 'Box', allowed_edges=SHORT + LONG),
                     Task('T2', 'A', 'B', 'Box', allowed_edges=LONG)]
            if reverse:
                tasks.reverse()
            with self.subTest(reverse=reverse):
                self.assertEqual([('A', 'Y'), ('Y', 'B')], self.edges(self.plan(tasks)[1]))

    def test_unrestricted_payload_cannot_widen_its_companions_rules(self):
        tasks = [Task('T1', 'A', 'B', 'Box'), Task('T2', 'A', 'B', 'Box', allowed_edges=LONG)]
        self.assertEqual([('A', 'Y'), ('Y', 'B')], self.edges(self.plan(tasks)[1]))

    def test_disjoint_edge_lists_do_not_become_unrestricted(self):
        tasks = [Task('T1', 'A', 'B', 'Box', allowed_edges=SHORT),
                 Task('T2', 'A', 'B', 'Box', allowed_edges=LONG)]
        self.assertIsNone(self.plan(tasks, reserve=False)[1])

    def test_each_payloads_node_restrictions_are_enforced(self):
        tasks = [Task('T1', 'A', 'B', 'Box'),
                 Task('T2', 'A', 'B', 'Box', allowed_nodes=['A', 'Y', 'B'])]
        self.assertEqual([('A', 'Y'), ('Y', 'B')], self.edges(self.plan(tasks)[1]))

    def test_delivered_payload_stops_restricting_the_remaining_leg(self):
        config = multi_route_config()
        config['locations'].append(dict(name='C', floor=0, x=7, y=8))
        config['corridors']['edges'].append(dict(**{'from':'B', 'to':'C'}, width_m=3, distance_m=1))
        tasks = [Task('T1', 'A', 'B', 'Box', allowed_edges=LONG),
                 Task('T2', 'A', 'C', 'Box', allowed_edges=LONG + [['B', 'C']])]
        _sim, plan = self.plan(tasks, config)
        self.assertEqual([('A', 'Y'), ('Y', 'B'), ('B', 'C')], self.edges(plan))
        self.assertEqual(16.5, plan['duration'])

    def test_not_yet_collected_payload_does_not_restrict_approach(self):
        config = multi_route_config()
        config['locations'].append(dict(name='P', floor=0, x=0, y=2))
        config['corridors']['edges'].extend([
            dict(**{'from':'A', 'to':'P'}, width_m=3, distance_m=2),
            dict(**{'from':'P', 'to':'Y'}, width_m=3, distance_m=10)])
        shared = [['P', 'Y'], ['Y', 'B']]
        tasks = [Task('T1', 'A', 'B', 'Box', allowed_edges=[['A', 'P']] + shared),
                 Task('T2', 'P', 'B', 'Box', allowed_edges=shared)]
        _sim, plan = self.plan(tasks, config)
        self.assertEqual([('A', 'P'), ('P', 'Y'), ('Y', 'B')], self.edges(plan))
        self.assertEqual(19, plan['duration'])

    def test_incompatible_batch_can_still_complete_as_separate_journeys(self):
        config = multi_route_config()
        config['tasks'] = [dict(id='T1', pickup='A', dropoff='B', payload='Box', allowed_edges=SHORT),
                           dict(id='T2', pickup='A', dropoff='B', payload='Box', allowed_edges=LONG)]
        with contextlib.redirect_stdout(io.StringIO()):
            sim = Simulation(config, verbose=True)
            sim.run()
        self.assertFalse(sim.failed_task_ids)
        self.assertEqual(2, len(sim.completed_task_records))
        self.assertFalse(any(r['event_type'] == 'multi_stop_task_assigned' for r in sim.verbose_rows))
        self.assertEqual([10, 30], [r['distance_m'] for r in sim.completed_task_records])

    def test_profile_task_union_is_resolved_before_intersecting_payloads(self):
        config = multi_route_config()
        config['route_profiles'] = {'shared': {'allowed_edges': LONG}}
        tasks = [Task('T1', 'A', 'B', 'Box', route_profile='shared', allowed_edges=SHORT),
                 Task('T2', 'A', 'B', 'Box', route_profile='shared')]
        self.assertEqual([('A', 'Y'), ('Y', 'B')], self.edges(self.plan(tasks, config)[1]))

    def test_clean_and_dirty_profiles_remain_separate_batch_groups(self):
        config = multi_route_config()
        config['route_profiles'] = {'clean': {'allowed_edges': LONG}, 'dirty': {'allowed_edges': LONG}}
        sim = Simulation(config)
        tasks = [Task('T1', 'A', 'B', 'Box', route_profile='clean'),
                 Task('T2', 'A', 'B', 'Box', route_profile='dirty')]
        self.assertIsNone(sim._multi_stop_batch_for_amr(sim.amrs[0], tasks))

    def test_lift_permissions_use_only_lifts_allowed_by_every_payload(self):
        tasks = [Task('T1', 'A', 'B', 'Box', allowed_lifts=['L1', 'L2']),
                 Task('T2', 'A', 'B', 'Box', allowed_lifts=['L2'])]
        _sim, plan = self.plan(tasks, multi_lift_config())
        self.assertIsNotNone(plan)
        self.assertEqual(['L2'], [s['lift_id'] for s in plan['segments'] if s['type'] == 'lift_transfer'])
        self.assertEqual(9, plan['duration'])  # 2 pickup + 2 horizontal + 1 vertical + 4 dropoff

    def test_disjoint_lift_permissions_prevent_vertical_batch(self):
        tasks = [Task('T1', 'A', 'B', 'Box', allowed_lifts=['L1']),
                 Task('T2', 'A', 'B', 'Box', allowed_lifts=['L2'])]
        self.assertIsNone(self.plan(tasks, multi_lift_config(), reserve=False)[1])

    def test_no_shared_lift_does_not_block_same_floor_travel(self):
        tasks = [Task('T1', 'A', 'B', 'Box', allowed_lifts=['L1']),
                 Task('T2', 'A', 'B', 'Box', allowed_lifts=['L2'])]
        self.assertEqual([('A', 'X'), ('X', 'B')], self.edges(self.plan(tasks)[1]))

    def test_cached_unrestricted_path_cannot_override_empty_intersection(self):
        sim = Simulation(multi_route_config())
        self.assertIsNotNone(sim._shortest_path_same_floor(0, 'A', 'B'))
        tasks = [Task('T1', 'A', 'B', 'Box', allowed_edges=SHORT),
                 Task('T2', 'A', 'B', 'Box', allowed_edges=LONG)]
        rules = sim._onboard_route_rules(tasks)
        self.assertIsNone(sim._shortest_path_same_floor(0, 'A', 'B', rules=rules))
        self.assertIsNotNone(sim._shortest_path_same_floor(0, 'A', 'B'))

    def test_disjoint_node_permissions_are_forbidden_even_with_empty_edges(self):
        tasks = [Task('T1', 'A', 'B', 'Box', allowed_nodes=['A', 'X']),
                 Task('T2', 'A', 'B', 'Box', allowed_nodes=['Y', 'B'])]
        self.assertIsNone(self.plan(tasks, reserve=False)[1])

    def test_unrestricted_lists_still_allow_a_shared_journey(self):
        tasks = [Task('T1', 'A', 'B', 'Box'), Task('T2', 'A', 'B', 'Box')]
        _sim, plan = self.plan(tasks)
        self.assertEqual([('A', 'X'), ('X', 'B')], self.edges(plan))
        self.assertEqual(11, plan['duration'])

    def test_ordering_estimate_uses_payload_width_to_choose_a_passable_route(self):
        config = multi_route_config()
        for edge in config['corridors']['edges'][:2]:
            edge['width_m'] = 0.65  # Robot 0.6 fits; loaded box 0.7 does not.
        sim = Simulation(config)
        self.assertEqual(10, sim._estimate_route_seconds(
            sim.amrs[0], sim.locations['A'], sim.locations['B'], sim.payloads['Box']))

    def test_delivered_wide_payload_stops_restricting_corridor_clearance(self):
        config = multi_route_config()
        config['payloads'].append(dict(config['payloads'][0], name='Narrow', width_m=0.5))
        config['locations'].append(dict(name='C', floor=0, x=7, y=8))
        config['corridors']['edges'].append(dict(**{'from':'B', 'to':'C'}, width_m=0.65, distance_m=1))
        tasks = [Task('T1', 'A', 'B', 'Box', allowed_edges=LONG),
                 Task('T2', 'A', 'C', 'Narrow', allowed_edges=LONG + [['B', 'C']])]
        _sim, plan = self.plan(tasks, config)
        self.assertEqual([('A', 'Y'), ('Y', 'B'), ('B', 'C')], self.edges(plan))
        self.assertEqual(16.5, plan['duration'])

    def test_future_wide_pickup_does_not_restrict_loaded_approach(self):
        config = multi_route_config()
        config['payloads'].append(dict(config['payloads'][0], name='Narrow', width_m=0.5))
        config['locations'].append(dict(name='P', floor=0, x=0, y=2))
        config['corridors']['edges'].extend([
            dict(**{'from':'A', 'to':'P'}, width_m=0.65, distance_m=2),
            dict(**{'from':'P', 'to':'Y'}, width_m=3, distance_m=10)])
        shared = [['P', 'Y'], ['Y', 'B']]
        tasks = [Task('T1', 'A', 'B', 'Narrow', allowed_edges=[['A', 'P']] + shared),
                 Task('T2', 'P', 'B', 'Box', allowed_edges=shared)]
        _sim, plan = self.plan(tasks, config)
        self.assertEqual([('A', 'P'), ('P', 'Y'), ('Y', 'B')], self.edges(plan))
        self.assertEqual(19, plan['duration'])

    def test_review_projects_preserve_expected_journeys_through_editor(self):
        folder = Path(__file__).resolve().parents[1] / 'verification' / 'scenarios'
        for variant, multi_assignments, finish in [('shared', 2, 16), ('separate', 0, 28)]:
            config = json.loads((folder / f'multi-stop-{variant}.json').read_text(encoding='utf-8'))
            for data in (config, JsonStore(copy.deepcopy(config)).data):
                with self.subTest(variant=variant, editor=data is not config):
                    with contextlib.redirect_stdout(io.StringIO()):
                        sim = Simulation(data, verbose=True)
                        sim.run()
                    self.assertFalse(sim.failed_task_ids)
                    self.assertEqual(2, len(sim.completed_task_records))
                    self.assertEqual(multi_assignments, sum(r['event_type'] == 'multi_stop_task_assigned'
                                                           for r in sim.verbose_rows))
                    completions = [float(r['sim_time_sec']) for r in sim.verbose_rows
                                   if r['event_type'] in {'task_complete', 'multi_stop_task_complete'}]
                    self.assertEqual(finish, max(completions))


if __name__ == '__main__':
    unittest.main()
