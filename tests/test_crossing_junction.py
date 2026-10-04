"""Crossing coordinates, directed restrictions and atomic user edits."""
from copy import deepcopy
import unittest
from tests import test_corridor_editing as editing
from tests.test_engineering_reference import reference_config
from visualiser.corridor_editing import create_crossing_junction
from visualiser.models import JsonStore
from simulator import Simulation
from amr_sim_models import Task


def crossing():
    config = reference_config()
    config['locations'] = [dict(name=name, floor=0, x=x, y=y) for name, x, y in
                           [('A', 0, 0), ('B', 10, 0), ('C', 4, -3), ('D', 4, 7)]]
    config['corridors']['nodes'] = []
    config['corridors']['edges'] = [
        dict({'from':'A','to':'B'}, bidirectional=False, width_m=2, distance_m=20),
        dict({'from':'C','to':'D'}, bidirectional=True, width_m=3, distance_m=30)]
    config['route_profiles'] = {'clean': {'allowed_nodes':['A','B'], 'allowed_edges':[['A','B']]},
                                'dirty': {'allowed_nodes':['C','D'], 'allowed_edges':[['C','D'],['D','C']]}}
    config['tasks'] = []
    return config


class JunctionGeometryTests(unittest.TestCase):
    def test_one_shared_point_preserves_distances_directions_and_profile_references(self):
        config = crossing()
        before = deepcopy(config)
        updated, chains = create_crossing_junction(config, JsonStore(config).all_points(), {('A','B'),('C','D')})
        self.assertEqual(before, config)
        self.assertEqual(1, len(updated['corridors']['nodes']))
        node = updated['corridors']['nodes'][0]
        name = node['name']
        self.assertEqual((4, 0), (node['x'], node['y']))
        self.assertEqual([8, 12, 9, 21], [e['distance_m'] for e in updated['corridors']['edges']])
        self.assertEqual([2, 2, 3, 3], [e['width_m'] for e in updated['corridors']['edges']])
        self.assertEqual([False, False, True, True], [e['bidirectional'] for e in updated['corridors']['edges']])
        self.assertEqual(['A',name,'B'], chains['A','B'])
        self.assertEqual(['C',name,'D'], chains['C','D'])
        self.assertEqual([['A',name],[name,'B']], updated['route_profiles']['clean']['allowed_edges'])
        self.assertEqual({'A','B',name}, set(updated['route_profiles']['clean']['allowed_nodes']))
        self.assertEqual({'C','D',name}, set(updated['route_profiles']['dirty']['allowed_nodes']))
        sim = Simulation(updated)
        self.assertIsNotNone(sim._shortest_path_same_floor(0, 'A', 'D'))
        self.assertIsNone(sim._shortest_path_same_floor(0, 'B', 'A'))
        rules = sim._resolve_task_route_rules(Task('T', 'A', 'B', 'Box', route_profile='clean'))
        self.assertIsNotNone(sim._shortest_path_same_floor(0, 'A', 'B', rules=rules))
        self.assertIsNone(sim._shortest_path_same_floor(0, 'A', 'D', rules=rules))

    def test_reverse_edge_records_keep_independent_attributes(self):
        config = crossing()
        config['corridors']['edges'].append(dict({'from':'B','to':'A'}, bidirectional=False, width_m=1.8, distance_m=40))
        updated, _ = create_crossing_junction(config, JsonStore(config).all_points(), {('A','B'),('C','D')})
        self.assertEqual([24,16], [e['distance_m'] for e in updated['corridors']['edges'][-2:]])
        self.assertEqual([1.8,1.8], [e['width_m'] for e in updated['corridors']['edges'][-2:]])

    def test_invalid_crossings_leave_configuration_unchanged(self):
        for variant in ('parallel','outside','endpoint','floor','existing','missing','nonfinite'):
            config = crossing()
            if variant == 'parallel':
                config['locations'][2].update(x=0,y=2)
                config['locations'][3].update(x=10,y=2)
            elif variant == 'outside':
                config['locations'][2]['x'] = config['locations'][3]['x'] = 11
            elif variant == 'endpoint':
                config['locations'][2]['y'] = 0
            elif variant == 'floor':
                config['locations'][2]['floor'] = config['locations'][3]['floor'] = 1
            elif variant == 'existing':
                config['corridors']['nodes'].append(dict(name='J',floor=0,x=4,y=0))
            elif variant == 'missing':
                config['corridors']['edges'].pop()
            else:
                config['locations'][0]['x'] = float('inf')
            before = deepcopy(config)
            with self.subTest(variant=variant), self.assertRaises(ValueError):
                create_crossing_junction(config, JsonStore(config).all_points(), {('A','B'),('C','D')})
            self.assertEqual(before, config)


class JunctionUiTests(unittest.TestCase):
    setUpClass = classmethod(editing.CorridorEditingUiTests.setUpClass.__func__)
    setUp = editing.CorridorEditingUiTests.setUp
    tearDown = editing.CorridorEditingUiTests.tearDown

    def test_junction_is_one_undoable_edit_and_invalid_selection_adds_no_history(self):
        self.editor.store = JsonStore(crossing())
        self.editor.refresh_canvas()
        self.editor._reset_edit_history()
        self.editor.selected_edge_keys = {('A','B')}
        self.assertFalse(self.editor.create_selected_junction())
        self.assertEqual(1, len(self.editor.edit_history.entries))
        self.editor.selected_edge_keys.add(('C','D'))
        before = deepcopy(self.editor.store.data)
        self.editor.floor_spin.setValue(1)
        self.assertFalse(self.editor.create_selected_junction())
        self.assertEqual(before, self.editor.store.data)
        self.editor.floor_spin.setValue(0)
        self.assertTrue(self.editor.create_selected_junction())
        after = deepcopy(self.editor.store.data)
        self.assertEqual(1, len(self.editor.selected_point_names))
        self.assertEqual(4, len(self.editor.selected_edge_keys))
        self.assertEqual(2, len(self.editor.edit_history.entries))
        self.editor.undo_edit()
        self.assertEqual(before, self.editor.store.data)
        self.editor.redo_edit()
        self.assertEqual(after, self.editor.store.data)
