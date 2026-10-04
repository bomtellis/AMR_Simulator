"""Independent cardinal geometry, attached-coordinate and atomic CAD cases."""
from copy import deepcopy
import unittest
from unittest.mock import patch
from tests import test_corridor_editing as editing
from visualiser.selection_rotation import rotate_selection
from amr_payload_inputs import inventory_space_dimensions


class RotationGeometryTests(unittest.TestCase):
    def store(self):
        store = editing.JsonStore(editing.reference_config())
        location = store.get_location('A')
        location.update(x=10, y=20, bounding_box=[dict(dx=0, dy=0, label='corner'),
            dict(x=14, y=20), dict(dx=0, dy=3)])
        location['inventory_spaces'] = [dict(name='Bay', points=[dict(dx=1, dy=0),
            dict(dx=5, dy=0), dict(x=15, y=22), dict(dx=1, dy=2)], length_m='0',
            payload_slots=[dict(payload='Box', dx=2, dy=1, rotation_deg=30, custom='retained')])]
        return store

    def test_ninety_degrees_about_explicit_pivot_preserves_owned_geometry_and_capacity(self):
        store = self.store()
        before = deepcopy(store.data)
        after = rotate_selection(store, ['A', 'Door'], (10, 20), 90)
        self.assertEqual(before, store.data)
        self.assertEqual((10, 20), (after.get_location('A')['x'], after.get_location('A')['y']))
        self.assertEqual([dict(x=10., y=20.), dict(x=10., y=24.), dict(x=7., y=20.)],
                         after.get_location_bounding_box_points('A'))
        self.assertEqual('corner', after.get_location('A')['bounding_box'][0]['label'])
        self.assertEqual((26, 13), (after.all_points()['Door']['x'], after.all_points()['Door']['y']))
        bay = after.get_location('A')['inventory_spaces'][0]
        self.assertEqual([dict(dx=0, dy=1), dict(dx=0, dy=5), dict(x=8, y=25), dict(dx=-2, dy=1)], bay['points'])
        self.assertEqual(dict(payload='Box', dx=-1, dy=2, rotation_deg=120, custom='retained'), bay['payload_slots'][0])
        self.assertEqual(90, bay['rotation_deg'])
        self.assertEqual((4, 2), (bay['length_m'], bay['width_m']))
        self.assertEqual(store.data['corridors']['edges'], after.data['corridors']['edges'])
        self.assertEqual(store.get_location('B'), after.get_location('B'))

    def test_negative_and_noncardinal_rotation_preserve_distances(self):
        store = self.store()
        for angle in (-90, 33):
            after = rotate_selection(store, ['A', 'Door'], (0, 0), angle)
            import math
            a, b = after.all_points()['A'], after.all_points()['Door']
            self.assertAlmostEqual(math.hypot(7,16), math.hypot(a['x']-b['x'], a['y']-b['y']))
            old = store.get_location('A')['inventory_spaces'][0]
            new = after.get_location('A')['inventory_spaces'][0]
            payloads = {row['name']: row for row in store.data['payloads']}
            self.assertEqual(inventory_space_dimensions(old, payloads, store.get_location('A')),
                             inventory_space_dimensions(new, payloads, after.get_location('A')))

    def test_lift_and_department_coordinates_rotate_without_identity_changes(self):
        store = self.store()
        store.data['lifts'] = [dict(id='Lift', floor_locations={'0': dict(x=2, y=3), '1': dict(x=7, y=8)})]
        store.data['departments'] = [dict(name='Ward', x=4, y=5, floor=0)]
        after = rotate_selection(store, ['Lift-F0', 'Ward'], (0, 0), 90)
        self.assertEqual(dict(x=-3, y=2), after.data['lifts'][0]['floor_locations']['0'])
        self.assertEqual(dict(x=7, y=8), after.data['lifts'][0]['floor_locations']['1'])
        self.assertEqual((-5,4), (after.all_points()['Ward']['x'], after.all_points()['Ward']['y']))

    def test_invalid_or_overflowing_rotation_is_atomic(self):
        store = self.store()
        before = deepcopy(store.data)
        for centre, angle in (((0,0), 0), ((0,0), 360), ((0,0), True), ((0,0), float('nan')),
                              ((float('inf'),0),90), ((1e308,1e308),180)):
            with self.subTest(centre=centre, angle=angle), self.assertRaises(ValueError):
                rotate_selection(store, ['A'], centre, angle)
            self.assertEqual(before, store.data)
        store.get_location('A')['inventory_spaces'][0]['points'][0] = dict(dx=1)
        before = deepcopy(store.data)
        with self.assertRaises(ValueError):
            rotate_selection(store, ['A'], (0,0), 90)
        self.assertEqual(before, store.data)

    def test_project_round_trip_preserves_rotation_and_independent_floor_geometry(self):
        from pathlib import Path
        import tempfile
        from amr_project import Project
        store = self.store()
        store.data['geometry'] = dict(initial_placements=[dict(amr_id='R-1', location='A', heading_deg=17)])
        after = rotate_selection(store, ['A'], (0,0), 90)
        self.assertEqual(store.data['geometry'], after.data['geometry'])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'rotation.amrproj'
            Project().save(path, after.data, base_dir=directory)
            loaded = Project.open(path).materialize(Path(directory) / 'cache')
        self.assertEqual(after.data['locations'], loaded['locations'])
        self.assertEqual(after.data['geometry'], loaded['geometry'])


class RotationUiTests(unittest.TestCase):
    setUpClass = classmethod(editing.CorridorEditingUiTests.setUpClass.__func__)
    setUp = editing.CorridorEditingUiTests.setUp
    tearDown = editing.CorridorEditingUiTests.tearDown

    def test_inline_edge_selection_rotates_endpoints_in_one_undo_redo(self):
        e = self.editor
        e.selected_edge_keys = {('A','Door')}
        before = deepcopy(e.store.data)
        e.workbench.rotate_action.trigger()
        bar = e.cad_rotate_input
        self.assertFalse(bar.isHidden())
        self.assertEqual('1.5,2', bar.centre.text())
        bar.centre.setText('0,0')
        bar.angle.setText('90')
        self.assertTrue(bar.apply_button.isEnabled())
        self.assertEqual(before, e.store.data)
        previewed = deepcopy(bar.preview_store.data)
        bar.apply_button.click()
        self.assertTrue(bar.isHidden())
        self.assertEqual((-4,3), (e.store.all_points()['Door']['x'], e.store.all_points()['Door']['y']))
        self.assertEqual(before['route_profiles'], e.store.data['route_profiles'])
        after = deepcopy(e.store.data)
        self.assertEqual(previewed, after)
        self.assertIsNone(bar.preview_store)
        self.assertEqual(2, len(e.edit_history.entries))
        self.assertTrue(e.undo_edit())
        self.assertEqual(before, e.store.data)
        self.assertTrue(e.redo_edit())
        self.assertEqual(after, e.store.data)

    def test_cancel_invalid_input_and_running_lock_preserve_model(self):
        e = self.editor
        e.selected_point_names = {'B'}
        before = deepcopy(e.store.data)
        e.show_selection_rotation()
        bar = e.cad_rotate_input
        for text in ('nan', '', '360'):
            bar.angle.setText(text)
            self.assertFalse(bar.apply_button.isEnabled())
        bar.angle.setText('45')
        self.assertTrue(e.cancel_cad_command())
        self.assertTrue(bar.isHidden())
        with patch.object(e, 'project_editing_locked', return_value=True):
            self.assertFalse(e.rotate_selected((0,0),45))
        self.assertEqual(before, e.store.data)
        self.assertEqual(1, len(e.edit_history.entries))

    def test_floor_and_workspace_changes_close_rotation(self):
        e = self.editor
        e.selected_point_names = {'B'}
        e.show_selection_rotation()
        e.floor_spin.setValue(1)
        self.assertTrue(e.cad_rotate_input.isHidden())
        e.floor_spin.setValue(0)
        e.show_selection_rotation()
        e.workspace.activate('configuration')
        self.assertTrue(e.cad_rotate_input.isHidden())
