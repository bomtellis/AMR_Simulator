"""Audited defaults and routing interactions with independently specified results."""
import copy
import unittest

from amr_sim_models import Task
from simulator import Simulation
from tests.test_engineering_reference import reference_config
from tests.test_route_profiles import profile_config
from visualiser.models import JsonStore
from visualiser.project_checks import check_project


class RoutingContractTests(unittest.TestCase):
    def route(self, config, minimum=0):
        sim = Simulation(config)
        return sim._shortest_path_same_floor(0, 'A', 'B', minimum_width_m=minimum)

    def test_door_runtime_and_building_defaults_then_explicit_override(self):
        for building_width, node_width, expected in [(None, None, .9), (1.1, None, 1.1), (1.1, .8, .8)]:
            for normalise in (False, True):
                with self.subTest(building=building_width, node=node_width, normalise=normalise):
                    cfg = reference_config()
                    cfg['corridors']['nodes'][0].pop('door_clear_width_m')
                    if building_width is not None:
                        cfg['building']['default_door_clear_width_m'] = building_width
                    if node_width is not None:
                        cfg['corridors']['nodes'][0]['door_clear_width_m'] = node_width
                    if normalise:
                        cfg = JsonStore(cfg).data
                    self.assertEqual([expected, expected], [e['width_m'] for e in self.route(cfg)['edges']])

    def test_corridor_default_and_edge_override_when_door_disabled(self):
        for default, explicit, expected in [(None, None, 2.4), (1.8, None, 1.8), (1.8, 1.2, 1.2)]:
            cfg = reference_config()
            cfg['corridors']['nodes'][0]['has_door'] = False
            if default is not None:
                cfg['building']['default_corridor_width_m'] = default
            for edge in cfg['corridors']['edges']:
                edge.pop('width_m')
                if explicit is not None:
                    edge['width_m'] = explicit
            self.assertEqual([expected, expected], [e['width_m'] for e in self.route(cfg)['edges']])

    def test_missing_door_flag_does_not_apply_opening(self):
        cfg = reference_config()
        cfg['corridors']['nodes'][0].pop('has_door')
        self.assertEqual([3, 3], [e['width_m'] for e in self.route(cfg)['edges']])

    def test_door_cannot_widen_narrower_corridor(self):
        cfg = reference_config()
        cfg['corridors']['edges'][0]['width_m'] = .7
        self.assertEqual([.7, .8], [e['width_m'] for e in self.route(cfg)['edges']])
        self.assertIsNone(self.route(cfg, minimum=.71))

    def test_two_endpoint_doors_choose_narrowest_in_each_direction(self):
        cfg = reference_config()
        cfg['corridors']['nodes'] = [dict(name='D1', floor=0, x=2, y=0, has_door=True, door_clear_width_m=1.2),
                                     dict(name='D2', floor=0, x=4, y=0, has_door=True, door_clear_width_m=.8)]
        cfg['corridors']['edges'] = [dict(**{'from': a, 'to': b}, width_m=2)
                                      for a,b in [('A','D1'), ('D1','D2'), ('D2','B')]]
        sim = Simulation(cfg)
        for a,b in [('D1','D2'), ('D2','D1')]:
            route = sim._shortest_path_same_floor(0, a, b)
            self.assertEqual(.8, route['edges'][0]['width_m'])
            self.assertEqual({'D1', 'D2'}, set(route['edges'][0]['door_nodes']))

    def test_missing_bidirectional_flag_defaults_to_two_way(self):
        cfg = reference_config()
        sim = Simulation(cfg)
        self.assertEqual(10, sim._shortest_path_same_floor(0, 'B', 'A')['distance_m'])

    def test_missing_auto_connect_is_preserved_on_import_but_new_editor_default_is_off(self):
        cfg = reference_config()
        cfg['corridors'].pop('auto_connect')
        cfg['corridors']['edges'] = []
        self.assertEqual(10, self.route(cfg)['distance_m'])
        self.assertEqual(10, self.route(JsonStore(copy.deepcopy(cfg)).data)['distance_m'])
        self.assertFalse(JsonStore().data['corridors']['auto_connect'])
        cfg['corridors']['auto_connect'] = False
        self.assertIsNone(self.route(cfg))

    def test_profile_node_and_edge_permissions_both_apply(self):
        cfg = profile_config()
        cfg['route_profiles']['clean']['allowed_nodes'] = ['A', 'Shared', 'B']
        sim = Simulation(cfg)
        task = Task('T', 'A', 'B', 'Box', route_profile='clean')
        self.assertIsNone(sim._shortest_path_same_floor(0, 'A', 'B', sim._resolve_task_route_rules(task)))
        task.allowed_nodes = ['Clean']
        self.assertEqual(10, sim._shortest_path_same_floor(0, 'A', 'B', sim._resolve_task_route_rules(task))['distance_m'])

    def test_profile_permission_cannot_override_narrow_door(self):
        cfg = profile_config()
        cfg['corridors']['nodes'][1].update(has_door=True, door_clear_width_m=.6)
        sim = Simulation(cfg)
        rules = sim._resolve_task_route_rules(Task('T', 'A', 'B', 'Box', route_profile='clean'))
        # Dirty's wider 14 m branch and the 1 m shortcut remain forbidden.
        self.assertIsNone(sim._shortest_path_same_floor(0, 'A', 'B', rules, minimum_width_m=.7))
        self.assertEqual(1, sim._shortest_path_same_floor(0, 'A', 'B', minimum_width_m=.7)['distance_m'])

    def test_invalid_numeric_widths_are_blocking_before_normalisation(self):
        for width in (0, -1, float('nan'), float('inf'), True, 'invalid'):
            cfg = reference_config()
            cfg['corridors']['nodes'][0]['door_clear_width_m'] = width
            report = check_project(cfg)
            self.assertTrue(any(f.severity == 'error' and f.path == '/corridors/nodes/0/door_clear_width_m'
                                for f in report.findings), repr(width))


if __name__ == '__main__':
    unittest.main()
