"""Copied graph identities, access rules, inventory policy and CAD transactions."""
from copy import deepcopy
import unittest
from unittest.mock import patch
from tests import test_corridor_editing as editing
from tests.test_route_profiles import profile_config
from visualiser.selection_copy import copy_selection


class CopyGeometryTests(unittest.TestCase):
    def test_induced_edges_and_owned_geometry_keep_attributes_without_aliasing(self):
        store = editing.JsonStore(editing.reference_config())
        a = store.get_location('A')
        a['bounding_box'] = [dict(dx=0,dy=0,tag='origin'),dict(x=2,y=0),dict(dx=0,dy=3)]
        a['inventory_spaces'] = [dict(name='Bay', occupied=True, points=[dict(x=1,y=2)],
                                     payload_slots=[dict(payload='Box',dx=1,dy=2,rotation_deg=30)])]
        a['wash_location'] = 'B'
        store.data['corridors']['edges'][0]['custom'] = {'value':[1]}
        before = deepcopy(store.data)
        copied, names, count = copy_selection(store, ['A','B','Door'], 20,30)
        self.assertEqual(before, store.data)
        self.assertEqual(2,count)
        clone = copied.get_location(names['A'])
        self.assertEqual((20,30), (clone['x'],clone['y']))
        self.assertEqual(names['B'], clone['wash_location'])
        self.assertEqual([dict(dx=0,dy=0,tag='origin'),dict(x=22,y=30),dict(dx=0,dy=3)], clone['bounding_box'])
        self.assertFalse(clone['inventory_spaces'][0]['occupied'])
        self.assertEqual([dict(x=21,y=32)], clone['inventory_spaces'][0]['points'])
        self.assertEqual(a['inventory_spaces'][0]['payload_slots'], clone['inventory_spaces'][0]['payload_slots'])
        copied.data['corridors']['edges'][2]['custom']['value'].append(2)
        self.assertEqual([1],copied.data['corridors']['edges'][0]['custom']['value'])
        self.assertEqual(before['tasks'],copied.data['tasks'])
        occupied, *_ = copy_selection(store, ['A'], 20,30,occupied=True)
        self.assertTrue(occupied.get_location('A-copy-1')['inventory_spaces'][0]['occupied'])

    def test_copied_clean_dirty_routes_have_same_independent_lengths(self):
        store = editing.JsonStore(profile_config())
        copied, names, _ = copy_selection(store, store.all_points(), 100,100)
        sim = editing.Simulation(copied.data)
        for profile, branch, distance in [('clean','Clean',10),('dirty','Dirty',14)]:
            task = editing.Task('Copied', names['A'],names['B'],'Box',route_profile=profile)
            route = sim._shortest_path_same_floor(0,names['A'],names['B'],sim._resolve_task_route_rules(task))
            self.assertEqual(distance,route['distance_m'])
            self.assertEqual([names['Shared'],names[branch],names['B']],[e['to'] for e in route['edges']])
        self.assertEqual(store.data['tasks'],copied.data['tasks'])

    def test_names_are_unique_node_allowances_follow_and_external_links_are_not_copied(self):
        store = editing.JsonStore(editing.reference_config())
        store.add_location('A-copy-1',0,50,50)
        store.data['route_profiles'] = {'one':dict(allowed_nodes=['A','Door'])}
        copied,names,count = copy_selection(store, ['A','Door'], 20,20)
        self.assertEqual('A-copy-2',names['A'])
        self.assertEqual(1,count)
        self.assertEqual(['A','Door',names['A'],names['Door']],copied.data['route_profiles']['one']['allowed_nodes'])
        self.assertFalse(any(e['from'] == names['Door'] and e['to'] == 'B' for e in copied.data['corridors']['edges']))

    def test_collisions_invalid_offsets_and_unsupported_point_kinds_are_atomic(self):
        store = editing.JsonStore(editing.reference_config())
        store.data['departments'] = [dict(name='Ward',floor=0,x=30,y=30)]
        before = deepcopy(store.data)
        for names,dx,dy in [(['A'],0,0),(['A'],6,8),(['A'],float('nan'),2),(['Ward'],5,5),([],1,2)]:
            with self.subTest(names=names,dx=dx), self.assertRaises(ValueError):
                copy_selection(store,names,dx,dy)
            self.assertEqual(before,store.data)
        store.data['corridors']['auto_connect'] = True
        with self.assertRaisesRegex(ValueError,'explicit'):
            copy_selection(store,['A'],20,20)

    def test_copied_project_round_trip_keeps_source_and_new_identities(self):
        from pathlib import Path
        import tempfile
        from amr_project import Project
        store = editing.JsonStore(editing.reference_config())
        copied, mapping, _ = copy_selection(store, ['A','Door'],20,20)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'copy.amrproj'
            Project().save(path,copied.data,base_dir=directory)
            loaded = Project.open(path).materialize(Path(directory) / 'cache')
        self.assertEqual(copied.data['locations'],loaded['locations'])
        self.assertEqual(copied.data['corridors'],loaded['corridors'])
        self.assertTrue(set(mapping.values()) <= editing.JsonStore(loaded).all_points().keys())


class CopyUiTests(unittest.TestCase):
    setUpClass = classmethod(editing.CorridorEditingUiTests.setUpClass.__func__)
    setUp = editing.CorridorEditingUiTests.setUp
    tearDown = editing.CorridorEditingUiTests.tearDown

    def test_preview_commit_new_selection_and_undo_redo(self):
        e = self.editor
        e.selected_edge_keys = {('A','Door')}
        before = deepcopy(e.store.data)
        e.workbench.copy_action.trigger()
        bar = e.cad_copy_input
        self.assertFalse(bar.isHidden())
        self.assertFalse(bar.occupied.isChecked())
        bar.offset.setText('20,20')
        self.assertTrue(bar.apply_button.isEnabled())
        preview = deepcopy(bar.preview_store.data)
        self.assertEqual(before,e.store.data)
        bar.apply_button.click()
        self.assertEqual(preview,e.store.data)
        self.assertEqual({'A-copy-1','Door-copy-1'},e.selected_point_names)
        self.assertTrue(bar.isHidden())
        self.assertEqual(2,len(e.edit_history.entries))
        self.assertTrue(e.undo_edit())
        self.assertEqual(before,e.store.data)
        self.assertTrue(e.redo_edit())
        self.assertEqual(preview,e.store.data)

    def test_cancel_floor_change_and_simulation_lock_preserve_input(self):
        e = self.editor
        e.selected_point_names = {'A'}
        before = deepcopy(e.store.data)
        e.show_selection_copy()
        e.cad_copy_input.offset.setText('20,20')
        self.assertTrue(e.cancel_cad_command())
        self.assertIsNone(e.cad_copy_input.preview_store)
        e.show_selection_copy()
        e.floor_spin.setValue(1)
        self.assertTrue(e.cad_copy_input.isHidden())
        with patch.object(e,'project_editing_locked',return_value=True):
            self.assertFalse(e.copy_selected_by(20,20))
        self.assertEqual(before,e.store.data)
