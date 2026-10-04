"""Independent geometry, routing consequences and contextual editing safeguards."""
from copy import deepcopy
import contextlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from tests import test_corridor_editing as editing
from tests.test_engineering_reference import reference_config
from layout_properties import apply_properties, fingerprint, records
from simulator import Simulation
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox


class LayoutPropertyTests(unittest.TestCase):
    def setUp(self):
        self.config = reference_config()

    def edit(self, target, changes):
        return apply_properties(self.config, target, changes, fingerprint(self.config))

    def test_move_preserves_offsets_identity_and_references(self):
        self.config['locations'][0]['bounding_box'] = [{'dx': 0, 'dy': 0}, {'dx': 2, 'dy': 0}, {'dx': 0, 'dy': 1}]
        self.config['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box')]
        before = deepcopy(self.config)
        result = self.edit(('points', ('A',)), {'x': 12.3456, 'y': -8})
        self.assertEqual(12.3456, result['locations'][0]['x'])
        self.assertEqual(-8, result['locations'][0]['y'])
        self.assertEqual(before['locations'][0]['bounding_box'], result['locations'][0]['bounding_box'])
        self.assertEqual(before['tasks'], result['tasks'])
        self.assertEqual(before['corridors'], result['corridors'])
        self.assertEqual(before, self.config)

    def test_lift_stop_and_department_positions_use_original_records(self):
        self.config['lifts'] = [dict(id='L', floor_locations={'0': {'x': 1, 'y': 2}, '1': {'x': 3, 'y': 4}})]
        self.config['departments'] = [dict(id='D', name='Department', x=10, y=20, floor=0)]
        result = self.edit(('points', ('L-F1',)), {'x': 8})
        self.assertEqual({'x': 8, 'y': 4}, result['lifts'][0]['floor_locations']['1'])
        self.assertEqual({'x': 1, 'y': 2}, result['lifts'][0]['floor_locations']['0'])
        result = self.edit(('points', ('Department',)), {'y': -5})
        self.assertEqual(-5, result['departments'][0]['y'])
        self.assertEqual('D', result['departments'][0]['id'])

    def test_length_override_changes_independently_calculated_task_duration(self):
        self.config['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box')]
        for distance, expected in [(10, 11.5), (0, 6.5)]:
            result = self.edit(('edges', (0,)), {'distance_m': distance})
            with contextlib.redirect_stdout(io.StringIO()):
                sim = Simulation(result)
                sim.run()
            # (first edge + 5 m second edge) / 2 m/s + 2 s load + 2 s unload.
            self.assertAlmostEqual(expected, sim.completed_task_records[0]['duration_sec'])
            self.assertFalse(sim.failed_task_ids)

    def test_clearing_override_restores_geometric_distance(self):
        self.config['corridors']['edges'][0]['distance_m'] = 20
        result = self.edit(('edges', (0,)), {'distance_m': None})
        self.assertNotIn('distance_m', result['corridors']['edges'][0])
        sim = Simulation(result)
        self.assertEqual(10, sim._same_floor_segments(sim.amrs[0], sim.locations['A'], sim.locations['B'])[2])

    def test_door_width_and_one_way_edit_change_routing(self):
        result = self.edit(('points', ('Door',)), {'door_clear_width_m': .69})
        sim = Simulation(result)
        self.assertIsNone(sim._same_floor_segments(sim.amrs[0], sim.locations['A'], sim.locations['B'], payload=sim.payloads['Box'], orientation='lengthways'))
        result = self.edit(('edges', (0,)), {'bidirectional': False})
        sim = Simulation(result)
        self.assertIsNotNone(sim._shortest_path_same_floor(0, 'A', 'B'))
        self.assertIsNone(sim._shortest_path_same_floor(0, 'B', 'A'))

    def test_bulk_edit_preserves_directions_profiles_and_other_attributes(self):
        edges = self.config['corridors']['edges']
        edges[0].update(bidirectional=False, custom={'value': 2})
        self.config['route_profiles'] = {'clean': {'allowed_edges': [['A', 'Door']]}}
        result = self.edit(('edges', (0, 1)), {'width_m': 1.2})
        self.assertEqual([1.2, 1.2], [e['width_m'] for e in result['corridors']['edges']])
        self.assertEqual(self.config['route_profiles'], result['route_profiles'])
        self.assertFalse(result['corridors']['edges'][0]['bidirectional'])
        self.assertNotIn('bidirectional', result['corridors']['edges'][1])
        self.assertEqual({'value': 2}, result['corridors']['edges'][0]['custom'])

    def test_invalid_properties_fail_atomically(self):
        before = deepcopy(self.config)
        for target, changes in [
            (('points', ('A',)), {'x': float('nan')}),
            (('points', ('A',)), {'x': float('inf')}),
            (('points', ('A',)), {'x': None}),
            (('points', ('A',)), {'wash_cycle_duration_sec': -1}),
            (('points', ('A',)), {'wash_location': 'missing'}),
            (('points', ('Door',)), {'door_clear_width_m': 0}),
            (('points', ('Door',)), {'door_clear_width_m': .099}),
            (('edges', (0, 1)), {'width_m': -1}),
            (('edges', (0, 1)), {'bidirectional': False}),
            (('edges', (0,)), {'people_area_type': 'clean'}),
            (('edges', (0,)), {'bidirectional': 'false'}),
            (('edges', (0,)), {'distance_m': -1}),
            (('points', ('A',)), {'name': 'new'})]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.edit(target, changes)
            self.assertEqual(before, self.config)

    def test_stale_or_ambiguous_selection_is_rejected(self):
        old = fingerprint(self.config)
        self.config['locations'][0]['x'] = 1
        with self.assertRaisesRegex(ValueError, 'project changed'):
            apply_properties(self.config, ('points', ('A',)), {'x': 2}, old)
        self.config['corridors']['nodes'].append(dict(name='A', x=0, y=0, floor=0))
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            self.edit(('points', ('A',)), {'x': 2})
        with self.assertRaises(ValueError):
            self.edit(('edges', (99,)), {'width_m': 2})

    def test_door_inherited_default_and_wash_location_validation(self):
        self.config['building']['default_door_clear_width_m'] = .95
        result = self.edit(('points', ('Door',)), {'door_clear_width_m': None})
        self.assertNotIn('door_clear_width_m', result['corridors']['nodes'][0])
        result = self.edit(('points', ('A',)), {'wash_cycle_required': True, 'wash_cycle_duration_sec': 30, 'wash_location': 'B'})
        self.assertEqual('B', result['locations'][0]['wash_location'])
        self.assertEqual(30, result['locations'][0]['wash_cycle_duration_sec'])


class LayoutPropertyUiTests(unittest.TestCase):
    setUpClass = classmethod(editing.CorridorEditingUiTests.setUpClass.__func__)
    setUp = editing.CorridorEditingUiTests.setUp
    tearDown = editing.CorridorEditingUiTests.tearDown

    def select(self, name):
        self.editor.workspace.select_object(('point', name))
        return self.editor.properties_panel

    def test_tree_lists_points_and_distinct_directed_edges(self):
        edges = self.editor.store.data['corridors']['edges']
        edges.append({'from': 'Door', 'to': 'A', 'width_m': 1, 'bidirectional': False})
        self.editor.workspace.refresh()
        items = self.editor.workspace.object_items
        self.assertIn(('point', 'Door'), items)
        self.assertIn(('point', 'A'), items)
        self.assertEqual(3, sum(key[0] == 'edge' for key in items))
        self.editor.workspace.select_object(('edge', 2))
        panel = self.editor.properties_panel
        self.assertEqual(('edges', (2,)), panel.target)
        panel.fields['width_m'].setText('1.5')
        self.assertTrue(panel.apply())
        self.assertEqual(3, self.editor.store.data['corridors']['edges'][0]['width_m'])
        self.assertEqual(1.5, self.editor.store.data['corridors']['edges'][2]['width_m'])

    def test_apply_is_one_undo_step_with_preview_and_check_staleness(self):
        self.editor.validate_json()
        self.assertTrue(self.editor.checks_panel.current())
        panel = self.select('Door')
        before = deepcopy(self.editor.store.data)
        panel.fields['x'].setText('4')
        panel.fields['door_clear_width_m'].setText('1.1')
        self.assertIn('1 object(s)', panel.preview.text())
        self.assertEqual(before, self.editor.store.data)
        self.assertTrue(self.editor.has_unsaved_changes())
        self.assertTrue(panel.apply())
        self.assertEqual(2, len(self.editor.edit_history.entries))
        self.assertFalse(self.editor.checks_panel.current())
        self.assertTrue(self.editor.undo_edit())
        self.assertEqual(before, self.editor.store.data)
        self.assertTrue(self.editor.redo_edit())
        self.assertEqual(1.1, self.editor.store.data['corridors']['nodes'][0]['door_clear_width_m'])

    def test_selection_change_retains_draft_on_original_target(self):
        panel = self.select('A')
        panel.fields['x'].setText('15')
        self.select('B')
        self.assertEqual(('points', ('A',)), panel.target)
        self.assertIn('Draft retained', panel.note.text())
        self.assertTrue(panel.apply())
        self.assertEqual(15, self.editor.store.data['locations'][0]['x'])
        self.assertEqual(6, self.editor.store.data['locations'][1]['x'])
        self.assertEqual(('points', ('B',)), panel.target)

    def test_discard_draft_restores_clean_state_without_undo_entry(self):
        panel = self.select('Door')
        panel.fields['x'].setText('12')
        self.assertTrue(panel.pending)
        panel.discard()
        self.assertFalse(self.editor.has_unsaved_changes())
        self.assertEqual(1, len(self.editor.edit_history.entries))

    def test_invalid_draft_blocks_save_and_close_without_modal_dialog(self):
        panel = self.select('Door')
        panel.fields['door_clear_width_m'].setText('-1')
        with patch.object(QFileDialog, 'getSaveFileName') as dialog:
            self.assertFalse(self.editor.save_json())
            dialog.assert_not_called()
        self.assertFalse(self.editor._confirm_unsaved_changes())
        self.assertTrue(panel.pending)
        self.assertIn('greater than zero', panel.note.text())
        self.assertEqual(.8, self.editor.store.data['corridors']['nodes'][0]['door_clear_width_m'])

    def test_active_editor_blocks_apply_and_preserves_pending_values(self):
        panel = self.select('Door')
        panel.fields['x'].setText('7')
        with patch.object(self.editor, '_history_busy', return_value=True):
            self.assertFalse(panel.apply())
        self.assertEqual(3, self.editor.store.data['corridors']['nodes'][0]['x'])
        self.assertTrue(panel.pending)
        self.assertTrue(panel.apply())
        self.assertEqual(2, len(self.editor.edit_history.entries))

    def test_stale_draft_cannot_overwrite_another_edit(self):
        panel = self.select('A')
        panel.fields['x'].setText('15')
        self.editor.store.data['locations'][0]['y'] = 99
        self.editor.refresh_canvas()
        self.assertFalse(panel.apply())
        self.assertEqual(0, self.editor.store.data['locations'][0]['x'])
        self.assertEqual(99, self.editor.store.data['locations'][0]['y'])
        panel.discard()
        self.assertEqual('99', panel.fields['y'].text())

    def test_save_applies_valid_draft_before_serializing(self):
        panel = self.select('Door')
        panel.fields['door_clear_width_m'].setText('1.1')
        path = Path(self.temp.name) / 'saved.amrproj'
        with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(path), '')), \
                patch.object(QMessageBox, 'critical') as failure:
            self.assertTrue(self.editor.save_json())
        failure.assert_not_called()
        from amr_project import Project
        self.assertEqual(1.1, Project.open(path).configuration()['corridors']['nodes'][0]['door_clear_width_m'])
        self.assertFalse(panel.pending)
        self.assertFalse(self.editor.has_unsaved_changes())

    def test_imported_json_save_applies_valid_draft_before_serializing(self):
        path = Path(self.temp.name) / 'imported.json'
        path.write_text(json.dumps(self.editor.store.data), encoding='utf-8')
        self.editor.current_json_path = str(path)
        panel = self.select('Door')
        panel.fields['door_clear_width_m'].setText('1.1')
        with patch.object(QMessageBox, 'critical') as failure:
            self.assertTrue(self.editor.save_json())
        failure.assert_not_called()
        self.assertEqual(1.1, json.loads(path.read_text())['corridors']['nodes'][0]['door_clear_width_m'])
        self.assertFalse(panel.pending)
        self.assertFalse(self.editor.has_unsaved_changes())

    def test_export_applies_valid_draft_without_losing_other_values(self):
        panel = self.select('Door')
        panel.fields['door_clear_width_m'].setText('1.1')
        path = Path(self.temp.name) / 'export.json'
        with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(path), '')):
            self.editor.export_project_json()
        body = json.loads(path.read_text())
        self.assertEqual(1.1, body['corridors']['nodes'][0]['door_clear_width_m'])
        self.assertEqual(self.editor.store.data['route_profiles'], body['route_profiles'])
        self.assertTrue(self.editor.has_unsaved_changes())

    def test_existing_null_is_distinct_from_absent_override_and_not_rewritten(self):
        self.editor.store.data['locations'][0]['wash_cycle_duration_sec'] = None
        self.editor.store.data['corridors']['edges'][0]['bidirectional'] = None
        before = deepcopy(self.editor.store.data)
        panel = self.select('A')
        self.assertEqual('null', panel.fields['wash_cycle_duration_sec'].text())
        self.editor.workspace.select_object(('edge', 0))
        self.assertIn('Existing null', panel.fields['bidirectional'].currentText())
        self.assertEqual(before, self.editor.store.data)
        self.select('A')
        panel.fields['wash_cycle_duration_sec'].setText('default')
        self.assertTrue(panel.apply())
        self.assertNotIn('wash_cycle_duration_sec', self.editor.store.data['locations'][0])

    def test_mixed_corridor_width_preview_preserves_unedited_values(self):
        self.editor.store.data['corridors']['edges'][1]['width_m'] = 2
        self.editor.selected_point_names.clear()
        self.editor.selected_point_name = None
        self.editor.selected_edge_keys = {('A', 'Door'), ('B', 'Door')}
        self.editor.refresh_canvas()
        panel = self.editor.properties_panel
        self.assertIn('Mixed', panel.fields['width_m'].placeholderText())
        self.assertNotIn('bidirectional', panel.fields)
        panel.fields['width_m'].setText('1.2')
        self.assertIn('2 object(s)', panel.preview.text())
        self.assertTrue(panel.apply())
        self.assertEqual([1.2, 1.2], [e['width_m'] for e in self.editor.store.data['corridors']['edges']])

    def test_properties_hide_outside_layout_and_tree_navigation_follows_floor(self):
        self.editor.store.add_corridor_node('UP', 1, 20, 30)
        panel = self.select('UP')
        self.assertEqual(1, self.editor.floor_spin.value())
        self.assertTrue(panel.isHidden())
        self.editor.workspace.set_properties_visible(True)
        self.assertFalse(panel.isHidden())
        self.editor.workspace.activate('configuration')
        self.assertTrue(panel.isHidden())
        self.editor.workspace.select_object(('point', 'A'))
        self.assertEqual(0, self.editor.floor_spin.value())
        self.assertEqual('layout', self.editor.workspace.stage)

    def test_inspection_and_tree_refresh_leave_configuration_unchanged(self):
        before = deepcopy(self.editor.store.data)
        self.select('A')
        self.select('Door')
        self.editor.workspace.refresh()
        self.assertEqual(before, self.editor.store.data)
        self.assertFalse(self.editor.has_unsaved_changes())

    def test_tree_search_finds_objects_without_hiding_workflow_stages(self):
        workspace = self.editor.workspace
        workspace.search.setText('Door')
        self.assertFalse(workspace.object_items['point', 'Door'].isHidden())
        self.assertTrue(workspace.object_items['point', 'A'].isHidden())
        from visualiser.project_workspace import STAGES
        self.assertTrue(all(not workspace.items[key].isHidden() for key, _ in STAGES))
        self.assertTrue(workspace.items['demand_generation'].isHidden())
        workspace.search.clear()
        self.assertFalse(workspace.object_items['point', 'A'].isHidden())
        self.assertFalse(workspace.items['demand_generation'].isHidden())

    def test_contextual_properties_fit_desktop_window(self):
        self.select('Door')
        self.editor.resize(1280, 800)
        self.editor.show()
        for _ in range(4):
            QApplication.processEvents()
        self.assertLessEqual(self.editor.width(), 1280)
        self.assertLessEqual(self.editor.height(), 800)
        self.assertGreater(self.editor.canvas.viewport().width(), 250)
        for index in range(100):
            self.editor.store.add_corridor_node(f'Bulk-{index}', 0, index, 0)
        self.editor.selected_point_name = None
        self.editor.selected_point_names = {f'Bulk-{index}' for index in range(100)}
        self.editor.refresh_canvas()
        for _ in range(4):
            QApplication.processEvents()
        self.assertIn('97 more objects', self.editor.properties_panel.title.text())
        self.assertLessEqual(self.editor.height(), 800)

    def test_bulk_default_removes_mixed_overrides_explicitly(self):
        self.editor.store.data['corridors']['edges'][1]['width_m'] = 2
        self.editor.selected_edge_keys = {('A', 'Door'), ('B', 'Door')}
        self.editor.refresh_canvas()
        panel = self.editor.properties_panel
        panel.fields['width_m'].setText('default')
        self.assertTrue(panel.apply())
        self.assertTrue(all('width_m' not in e for e in self.editor.store.data['corridors']['edges']))

    def test_recovery_includes_valid_draft_without_committing_it(self):
        panel = self.select('Door')
        panel.fields['door_clear_width_m'].setText('1.2')
        self.assertTrue(self.editor.capture_recovery())
        saved = self.editor._recovery_store.read(self.editor._recovery_store.snapshot_path)
        self.assertEqual(1.2, saved['config']['corridors']['nodes'][0]['door_clear_width_m'])
        self.assertEqual(.8, self.editor.store.data['corridors']['nodes'][0]['door_clear_width_m'])
        self.assertTrue(panel.pending)
        panel.fields['door_clear_width_m'].setText('invalid')
        self.assertFalse(self.editor.capture_recovery())
        self.assertIn('Recovery failed', self.editor._recovery_status)
        self.assertEqual(saved, self.editor._recovery_store.read(self.editor._recovery_store.snapshot_path))
