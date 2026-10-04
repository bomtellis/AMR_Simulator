"""Model layer locks, visibility and undo acceptance tests."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests import test_corridor_editing as editing
from visualiser import model_layers as layers


class ModelLayerTests(unittest.TestCase):
    def test_current_layer_applies_to_new_nodes_locations_and_continuous_routes(self):
        config = layers.set_current(layers.set_layer(editing.reference_config(), 'Drawing'), 'Drawing')
        store = editing.JsonStore(config)
        store.add_location('New room', 0, 30, 30)
        store.add_corridor_node('New node', 0, 20, 20)
        self.assertEqual('Drawing', store.all_points()['New room']['editor_layer'])
        self.assertEqual('Drawing', store.all_points()['New node']['editor_layer'])
        store.connect_corridor('New room', 'New node')
        target = store.draw_corridor_step('New node', 0, 25, 20, exact=True)
        self.assertEqual('Drawing', store.all_points()[target['name']]['editor_layer'])
        self.assertEqual(['Drawing', 'Drawing'], [e['editor_layer'] for e in store.data['corridors']['edges'][-2:]])
        self.assertNotIn('editor_layer', store.all_points()['A'])
        updated, chains = editing.split_config(store.data, {('A', 'Door'): [.5]})
        node = next(n for n in updated['corridors']['nodes'] if n['name'] == chains[('A', 'Door')][1])
        self.assertEqual('Default', layers.layer_name(node))

    def test_current_layer_survives_options_rename_remove_and_archive(self):
        from amr_project import Project
        config = layers.set_current(layers.set_layer(editing.reference_config(), 'Drawing'), 'Drawing')
        config = layers.set_layer(config, 'Other')
        self.assertEqual('Drawing', layers.current_layer(config))
        renamed = layers.reorganize(config, 'Drawing', 'Routes')
        self.assertEqual('Routes', layers.current_layer(renamed))
        merged = layers.reorganize(renamed, 'Routes', 'Other', remove=True)
        self.assertEqual('Other', layers.current_layer(merged))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'current.amrproj'
            Project().save(path, merged, base_dir=directory)
            self.assertEqual('Other', layers.current_layer(Project.open(path).materialize(Path(directory)/'cache')))

    def test_hidden_or_locked_current_layer_blocks_new_drawing_without_mutation(self):
        config = layers.set_current(layers.set_layer(editing.reference_config(), 'Drawing'), 'Drawing')
        for options in (dict(visible=False), dict(locked=True)):
            blocked = layers.set_layer(config, 'Drawing', **options)
            store = editing.JsonStore(blocked)
            before = deepcopy(store.data)
            with self.assertRaises(layers.LayerLockedError):
                store.add_location('New', 0, 30, 30)
            with self.assertRaises(layers.LayerLockedError):
                store.draw_corridor_step('A', 0, 30, 30, exact=True)
            self.assertEqual(before, store.data)
            with self.assertRaises(ValueError):
                layers.set_current(blocked, 'Drawing')
        config['editor_layers']['current'] = 'Missing'
        with self.assertRaises(ValueError):
            editing.JsonStore(config)

    def test_rename_and_remove_preserve_objects_and_route_profiles(self):
        config = layers.set_layer(editing.reference_config(), 'Fixtures', visible=False)
        config = layers.assign(config, {'A', 'Door'}, {('A', 'Door')}, 'Fixtures')
        before = deepcopy(config)
        renamed = layers.reorganize(config, 'Fixtures', 'Equipment')
        self.assertEqual(3, len(layers.members(renamed, 'Equipment')))
        self.assertEqual(dict(visible=False, locked=False), layers.definitions(renamed)['Equipment'])
        merged = layers.reorganize(renamed, 'Equipment', 'Default', remove=True)
        self.assertNotIn('Equipment', layers.definitions(merged))
        self.assertEqual(config['corridors']['edges'][0]['from'], merged['corridors']['edges'][0]['from'])
        for section in ('locations', 'corridors'):
            clean = deepcopy(merged[section])
            original = deepcopy(config[section])
            rows = clean if isinstance(clean, list) else clean['nodes'] + clean['edges']
            old_rows = original if isinstance(original, list) else original['nodes'] + original['edges']
            for row in rows + old_rows:
                row.pop('editor_layer', None)
            self.assertEqual(original, clean)
        self.assertEqual(before, config)

    def test_reorganizing_default_duplicate_missing_and_locked_layers_is_rejected(self):
        config = layers.set_layer({}, 'Fixtures')
        config = layers.set_layer(config, 'Locked', locked=True)
        for source, target, remove in [('Default','New',False), ('Fixtures','Default',False),
                ('Missing','New',False), ('Fixtures','Fixtures',True), ('Fixtures','Missing',True),
                ('Fixtures','Locked',True), ('Locked','New',False), ('Fixtures',' ',False)]:
            with self.subTest(source=source,target=target,remove=remove), self.assertRaises(ValueError):
                layers.reorganize(config, source, target, remove=remove)

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

    def test_current_layer_control_and_undo(self):
        e = self.editor
        e.show_model_layers()
        e.update_model_layer('New work')
        panel = e.model_layer_panel
        panel.choice.setCurrentText('New work')
        before = deepcopy(e.store.data)
        panel.use_current.click()
        self.assertEqual('New work', layers.current_layer(e.store.data))
        self.assertIn('New work', panel.current.text())
        self.assertTrue(e.undo_edit())
        self.assertEqual(before, e.store.data)
        self.assertIn('Default', panel.current.text())
        self.assertTrue(e.redo_edit())
        e.update_model_layer('New work', locked=True)
        panel.choice.setCurrentText('New work')
        self.assertFalse(panel.use_current.isEnabled())

    def test_panel_rename_and_remove_are_single_undo_operations(self):
        e = self.editor
        e.show_model_layers()
        panel = e.model_layer_panel
        e.update_model_layer('Fixtures')
        e.selected_point_names = {'A'}
        e.assign_model_layer('Fixtures')
        before = deepcopy(e.store.data)
        panel.choice.setCurrentText('Fixtures')
        panel.name.setText('Equipment')
        count = len(e.edit_history.entries)
        panel.rename()
        renamed = deepcopy(e.store.data)
        self.assertEqual(count + 1, len(e.edit_history.entries))
        self.assertEqual('Equipment', panel.choice.currentText())
        self.assertIn('1 object record', panel.removal_preview.text())
        panel.destination.setCurrentText('Default')
        panel.remove()
        self.assertEqual(count + 2, len(e.edit_history.entries))
        self.assertEqual('Default', panel.choice.currentText())
        self.assertFalse(panel.remove_button.isEnabled())
        self.assertTrue(e.undo_edit())
        self.assertEqual(renamed, e.store.data)
        self.assertTrue(e.undo_edit())
        self.assertEqual(before, e.store.data)
        self.assertTrue(e.redo_edit())
        self.assertEqual(renamed, e.store.data)

    def test_reorganize_rejection_preserves_history_and_inputs(self):
        e = self.prepare()
        before = deepcopy(e.store.data)
        history = deepcopy(e.edit_history.entries)
        self.assertFalse(e.reorganize_model_layer('Protected', 'Default', remove=True))
        self.assertEqual(before, e.store.data)
        self.assertEqual(history, e.edit_history.entries)
        self.assertIn('Unlock', e.status_label.text())

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
