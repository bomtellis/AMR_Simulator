"""Model layer locks, visibility and undo acceptance tests."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests import test_corridor_editing as editing
from visualiser import model_layers as layers


class ModelLayerTests(unittest.TestCase):
    def test_project_archive_roundtrip_preserves_definitions_and_membership(self):
        from amr_project import Project
        config = layers.set_layer(editing.reference_config(), 'Equipment', visible=False, locked=True)
        config = layers.assign(config, {'A'}, set(), 'Equipment')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'layers.amrproj'
            Project().save(path, config, base_dir=root)
            restored = Project.open(path).materialize(root / 'cache')
            self.assertEqual(config['editor_layers'], restored['editor_layers'])
            self.assertEqual(config['locations'], restored['locations'])
            layers.validate(restored)

    def test_legacy_default_does_not_mutate_inputs(self):
        config = editing.reference_config()
        before = deepcopy(config)
        layers.validate(config)
        self.assertEqual({'Default': dict(visible=True, locked=False)}, layers.definitions(config))
        self.assertEqual(before, config)

    def test_invalid_definitions_and_memberships_are_rejected(self):
        for name, visible, locked in [(' ', True, False), (' X', True, False), ('X', 1, False), ('X', True, 'yes')]:
            with self.subTest(name=name, visible=visible, locked=locked), self.assertRaises(ValueError):
                layers.set_layer({}, name, visible=visible, locked=locked)
        for name in ('Missing', [], None):
            config = editing.reference_config()
            config['locations'][0]['editor_layer'] = name
            with self.assertRaisesRegex(ValueError, 'Unknown editor layer'):
                editing.JsonStore(config)

    def test_locked_corridor_protects_endpoints_and_reciprocal_records(self):
        config = layers.set_layer(editing.reference_config(), 'Routes', locked=True)
        config = layers.assign(config, set(), {('A', 'Door')}, 'Routes')
        self.assertEqual({'A', 'Door'}, layers.locked_points(config))
        for change in ('position', 'remove', 'reverse'):
            after = deepcopy(config)
            if change == 'position':
                after['locations'][0]['x'] += 1
            elif change == 'remove':
                after['corridors']['edges'].pop(0)
            else:
                after['corridors']['edges'].append({'from': 'Door', 'to': 'A'})
            with self.subTest(change=change), self.assertRaises(layers.LayerLockedError):
                layers.assert_unlocked_changes(config, after)
        after = deepcopy(config)
        after['locations'][0]['service_time'] = 123
        layers.assert_unlocked_changes(config, after)

    def test_split_inherits_layer_without_changing_route_permissions(self):
        config = layers.set_layer(editing.reference_config(), 'Routes')
        config = layers.assign(config, set(), {('A', 'Door')}, 'Routes')
        updated, chains = editing.split_config(config, {('A', 'Door'): [.5]})
        new_name = chains[('A', 'Door')][1]
        node = next(n for n in updated['corridors']['nodes'] if n['name'] == new_name)
        self.assertEqual('Routes', node['editor_layer'])
        self.assertEqual(2, sum(e.get('editor_layer') == 'Routes' for e in updated['corridors']['edges']))


class ModelLayerUiTests(unittest.TestCase):
    setUpClass = classmethod(editing.CorridorEditingUiTests.setUpClass.__func__)
    setUp = editing.CorridorEditingUiTests.setUp
    tearDown = editing.CorridorEditingUiTests.tearDown

    def prepare(self, *, edges=False):
        e = self.editor
        e.update_model_layer('Protected')
        e.selected_point_names = set() if edges else {'A'}
        e.selected_edge_keys = {('A', 'Door')} if edges else set()
        self.assertTrue(e.assign_model_layer('Protected'))
        self.assertTrue(e.update_model_layer('Protected', locked=True))
        return e

    def test_lock_rejects_move_rotation_reassignment_and_keeps_history(self):
        e = self.prepare()
        before = deepcopy(e.store.data)
        history = deepcopy(e.edit_history.entries)
        for operation in (lambda: e.move_selected_by(2, 1), lambda: e.rotate_selected((0, 0), 90),
                          lambda: e.assign_model_layer('Default')):
            operation()
            self.assertEqual(before, e.store.data)
            self.assertEqual(history, e.edit_history.entries)
        self.assertTrue(e.undo_edit())
        self.assertFalse(layers.definitions(e.store.data)['Protected']['locked'])
        e.selected_point_names = {'A'}
        self.assertTrue(e.move_selected_by(2, 1))

    def test_locked_edge_blocks_subdivision_and_endpoint_move(self):
        e = self.prepare(edges=True)
        before = deepcopy(e.store.data)
        self.assertFalse(e.subdivide_selected_corridors(2))
        e.selected_point_names = {'A'}
        e.move_selected_by(1, 0)
        self.assertEqual(before, e.store.data)
        self.assertFalse(e._layout_points_editable({'A'}))

    def test_locked_point_cannot_be_deleted(self):
        e = self.prepare()
        before = deepcopy(e.store.data)
        with patch.object(editing.QMessageBox, 'question', return_value=editing.QMessageBox.Yes):
            e.delete_selected()
        self.assertEqual(before, e.store.data)
        self.assertIn('locked layer', e.status_label.text())

    def test_hidden_layer_clears_selection_and_cannot_be_picked(self):
        e = self.editor
        e.update_model_layer('Hidden')
        e.selected_point_names = {'A'}
        e.selected_edge_keys = {('A', 'Door')}
        e.assign_model_layer('Hidden')
        profiles = deepcopy(e.store.data['route_profiles'])
        e.update_model_layer('Hidden', visible=False)
        self.assertFalse(e.selected_point_names)
        self.assertFalse(e.selected_edge_keys)
        self.assertIsNone(e.find_nearest_point_name(0, 0, 0, radius_world=.1))
        self.assertIsNone(e.find_nearest_edge_key(1.5, 2, 0, radius_world=.1))
        hidden = [item for item, (kind, value) in e._item_lookup.items()
                  if kind in ('point', 'point_label') and value == 'A']
        self.assertTrue(hidden)
        self.assertTrue(all(not item.isVisible() for item in hidden))
        self.assertEqual(profiles, e.store.data['route_profiles'])
        e.undo_edit()
        self.assertEqual('A', e.find_nearest_point_name(0, 0, 0, radius_world=.1))

    def test_panel_respects_focus_stage_and_explicit_close(self):
        e = self.editor
        e.show_model_layers()
        panel = e.model_layer_panel
        self.assertFalse(panel.dock.isHidden())
        panel.name.setText('Fixtures')
        panel.add()
        self.assertIn('Fixtures', layers.definitions(e.store.data))
        e.workspace.set_canvas_focus(True)
        self.assertTrue(panel.dock.isHidden())
        e.workspace.set_canvas_focus(False)
        self.assertFalse(panel.dock.isHidden())
        e.workspace.activate('configuration')
        self.assertTrue(panel.dock.isHidden())
        e.workspace.activate('layout')
        self.assertFalse(panel.dock.isHidden())
        panel.dock.close()
        e.workspace.set_canvas_focus(True)
        e.workspace.set_canvas_focus(False)
        self.assertTrue(panel.dock.isHidden())
