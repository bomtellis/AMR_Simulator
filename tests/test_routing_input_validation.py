"""Routing inputs retain physical dimensions and reject ambiguous flags at entry."""
import copy
import unittest

from simulator import Simulation
from tests.test_engineering_reference import reference_config
from visualiser.models import JsonStore
from visualiser.project_checks import check_project


def put(config, path, value):
    target = config
    parts = path.strip('/').split('/')
    for part in parts[:-1]:
        target = target[int(part)] if isinstance(target, list) else target[part]
    target[parts[-1]] = value


FLAGS = ['/corridors/auto_connect', '/corridors/nodes/0/has_door', '/corridors/edges/0/bidirectional']
WIDTHS = ['/building/default_corridor_width_m', '/building/default_door_clear_width_m',
          '/corridors/nodes/0/door_clear_width_m', '/corridors/edges/0/width_m']


class RoutingInputValidationTests(unittest.TestCase):
    def test_ambiguous_flags_rejected_by_checks_editor_and_simulator(self):
        for path in FLAGS:
            for value in ('false', 'true', 0, 1, None, [], {}):
                with self.subTest(path=path, value=value):
                    cfg = reference_config()
                    put(cfg, path, value)
                    before = copy.deepcopy(cfg)
                    report = check_project(cfg)
                    self.assertTrue(any(f.severity == 'error' and f.path == path for f in report.findings))
                    for loader in (JsonStore, Simulation):
                        with self.assertRaisesRegex(ValueError, 'JSON boolean'):
                            loader(cfg)
                    self.assertEqual(before, cfg)

    def test_invalid_widths_rejected_before_defaults_or_clamping(self):
        for path in WIDTHS:
            for value in (0, -.1, True, None, 'bad', float('nan'), float('inf')):
                with self.subTest(path=path, value=value):
                    cfg = reference_config()
                    put(cfg, path, value)
                    report = check_project(cfg)
                    self.assertTrue(any(f.severity == 'error' and f.path == path for f in report.findings))
                    for loader in (JsonStore, Simulation):
                        with self.assertRaisesRegex(ValueError, 'finite positive'):
                            loader(cfg)

    def test_small_positive_door_is_preserved_and_blocks_wider_robot(self):
        for normalise in (False, True):
            cfg = reference_config()
            cfg['corridors']['nodes'][0]['door_clear_width_m'] = .05
            cfg['amrs'][0]['width_m'] = .07
            cfg = JsonStore(cfg).data if normalise else cfg
            self.assertFalse(any(f.severity == 'error' for f in check_project(cfg).findings))
            sim = Simulation(cfg)
            self.assertEqual(.05, sim.graph_nodes['Door'].door_clear_width_m)
            self.assertIsNone(sim._shortest_path_same_floor(0, 'A', 'B', minimum_width_m=.07))
            self.assertIsNotNone(sim._shortest_path_same_floor(0, 'A', 'B', minimum_width_m=.05))

    def test_small_defaults_and_explicit_corridor_width_are_preserved(self):
        for field in ('default_corridor_width_m', 'default_door_clear_width_m'):
            cfg = reference_config()
            cfg['building'][field] = .05
            cfg['corridors']['nodes'][0].pop('door_clear_width_m')
            for edge in cfg['corridors']['edges']:
                edge.pop('width_m')
            for data in (cfg, JsonStore(cfg).data):
                sim = Simulation(data)
                self.assertEqual(.05, sim._shortest_path_same_floor(0, 'A', 'B')['edges'][0]['width_m'])
        cfg = reference_config()
        cfg['corridors']['edges'][0]['width_m'] = .04
        sim = Simulation(JsonStore(cfg).data)
        edge = sim._shortest_path_same_floor(0, 'A', 'B')['edges'][0]
        self.assertEqual(.04, edge['width_m'])
        self.assertEqual(.02, sim._corridor_lane_capacity(edge, sim.amrs[0], None)[1])

    def test_valid_boolean_and_numeric_string_width_remain_compatible(self):
        cfg = reference_config()
        cfg['corridors']['nodes'][0].update(has_door=False, door_clear_width_m='0.05')
        cfg['corridors']['edges'][0]['bidirectional'] = False
        for data in (cfg, JsonStore(cfg).data):
            sim = Simulation(data)
            self.assertEqual(3, sim._shortest_path_same_floor(0, 'A', 'B')['edges'][0]['width_m'])
            self.assertIsNone(sim._shortest_path_same_floor(0, 'B', 'A'))


if __name__ == '__main__':
    unittest.main()
