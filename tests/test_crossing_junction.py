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
        for variant in ('parallel','outside','floor','ambiguous','nearby','missing','nonfinite'):
            config = crossing()
            if variant == 'parallel':
                config['locations'][2].update(x=0,y=2)
                config['locations'][3].update(x=10,y=2)
            elif variant == 'outside':
                config['locations'][2]['x'] = config['locations'][3]['x'] = 11
            elif variant == 'floor':
                config['locations'][2]['floor'] = config['locations'][3]['floor'] = 1
            elif variant == 'ambiguous':
                config['corridors']['nodes'].extend(dict(name=name,floor=0,x=4,y=0) for name in ('J','K'))
            elif variant == 'nearby':
                config['corridors']['nodes'].append(dict(name='J',floor=0,x=4,y=1e-7))
            elif variant == 'missing':
                config['corridors']['edges'].pop()
            else:
                config['locations'][0]['x'] = float('inf')
            before = deepcopy(config)
            with self.subTest(variant=variant), self.assertRaises(ValueError):
                create_crossing_junction(config, JsonStore(config).all_points(), {('A','B'),('C','D')})
            self.assertEqual(before, config)

    def test_existing_door_is_reused_without_changing_its_settings(self):
        config = crossing()
        door = dict(name='ExistingDoor',floor=0,x=4,y=0,has_door=True,door_clear_width_m=.7,
                    custom={'preserve':['metadata']})
        config['corridors']['nodes'].append(deepcopy(door))
        before = deepcopy(config)
        updated, chains = create_crossing_junction(config, JsonStore(config).all_points(), {('A','B'),('C','D')})
        self.assertEqual(before, config)
        self.assertEqual([door], updated['corridors']['nodes'])
        self.assertEqual({'ExistingDoor'}, {chain[1] for chain in chains.values()})
        sim = Simulation(updated)
        self.assertIsNone(sim._shortest_path_same_floor(0, 'A', 'B', minimum_width_m=.8))
        self.assertIsNotNone(sim._shortest_path_same_floor(0, 'A', 'B', minimum_width_m=.6))

    def test_t_junction_reuses_endpoint_and_splits_only_the_through_corridor(self):
        config = crossing()
        config['locations'][2]['y'] = 0
        original_branch = deepcopy(config['corridors']['edges'][1])
        updated, chains = create_crossing_junction(config, JsonStore(config).all_points(), {('A','B'),('C','D')})
        self.assertEqual([], updated['corridors']['nodes'])
        self.assertEqual(['A','C','B'], chains['A','B'])
        self.assertEqual(['C','D'], chains['C','D'])
        self.assertEqual(original_branch, updated['corridors']['edges'][-1])
        self.assertEqual(3, len(updated['corridors']['edges']))
        self.assertEqual([['A','C'],['C','B']], updated['route_profiles']['clean']['allowed_edges'])
        sim = Simulation(updated)
        self.assertIsNotNone(sim._shortest_path_same_floor(0, 'A', 'D'))
        self.assertIsNone(sim._shortest_path_same_floor(0, 'D', 'A'))

    def test_already_connected_endpoint_and_department_marker_are_not_recreated(self):
        config = crossing()
        points = JsonStore(config).all_points()
        points['Marker'] = dict(name='Marker',kind='department',floor=0,x=4,y=0)
        with self.assertRaisesRegex(ValueError, 'department'):
            create_crossing_junction(config, points, {('A','B'),('C','D')})
        config['corridors']['edges'][1].update({'from':'B','to':'D'})
        with self.assertRaisesRegex(ValueError, 'already meet'):
            create_crossing_junction(config, JsonStore(config).all_points(), {('A','B'),('B','D')})


class JunctionUiTests(unittest.TestCase):
    setUpClass = classmethod(editing.CorridorEditingUiTests.setUpClass.__func__)
    setUp = editing.CorridorEditingUiTests.setUp
    tearDown = editing.CorridorEditingUiTests.tearDown

    def test_existing_point_and_t_junction_select_reused_identity_and_undo(self):
        for variant in ('door', 'endpoint'):
            config = crossing()
            if variant == 'door':
                config['corridors']['nodes'].append(dict(name='J',floor=0,x=4,y=0,has_door=True,door_clear_width_m=.7))
                expected = 'J'
            else:
                config['locations'][2]['y'] = 0
                expected = 'C'
            self.editor.store = JsonStore(config)
            self.editor.refresh_canvas()
            self.editor._reset_edit_history()
            self.editor.selected_edge_keys = {('A','B'),('C','D')}
            before = deepcopy(self.editor.store.data)
            self.assertTrue(self.editor.create_selected_junction())
            self.assertEqual({expected}, self.editor.selected_point_names)
            self.assertEqual(2, len(self.editor.edit_history.entries))
            after = deepcopy(self.editor.store.data)
            self.editor.undo_edit()
            self.assertEqual(before, self.editor.store.data)
            self.editor.redo_edit()
            self.assertEqual(after, self.editor.store.data)

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
