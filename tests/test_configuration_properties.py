"""Configuration edits preserve unrelated options and change known outcomes."""
from copy import deepcopy
import contextlib
import io
import unittest
from unittest.mock import patch

from tests import test_corridor_editing as editing
from tests.test_engineering_reference import reference_config
from tests.test_route_profiles import profile_config
from tests.test_lift_repair_reference import config as lift_config
from layout_properties import apply_properties, fingerprint
from configuration_properties import choices
from simulator import Simulation
from models import JsonStore
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication


def edit(config, section, key, changes):
    return apply_properties(config, (section, (key,)), changes, fingerprint(config))


def run(config):
    with contextlib.redirect_stdout(io.StringIO()):
        sim = Simulation(config)
        sim.run()
    return sim


class ConfigurationPropertyTests(unittest.TestCase):
    def test_robot_speed_changes_independent_reference_duration(self):
        config = reference_config()
        config['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box')]
        changed = edit(config, 'amrs', 0, {'speed_m_per_sec': 1})
        sim = run(changed)
        self.assertEqual(14, sim.completed_task_records[0]['duration_sec'])  # 10/1 + 2 + 2
        self.assertEqual(2, config['amrs'][0]['speed_m_per_sec'])

    def test_nested_slots_and_unknown_extensions_survive_scalar_edit(self):
        config = reference_config()
        config['amrs'][0]['payload_slots'] = [{'name': 'Custom', 'payload_capacity_kg': 57, 'extension': {'keep': 1}}]
        config['amrs'][0]['extension'] = {'options': [1, 2]}
        before = deepcopy(config)
        changed = edit(config, 'amrs', 0, {'quantity': 3, 'battery_soc_percent': 40})
        self.assertEqual(before['amrs'][0]['payload_slots'], changed['amrs'][0]['payload_slots'])
        self.assertEqual(before['amrs'][0]['extension'], changed['amrs'][0]['extension'])
        self.assertEqual(before, config)

    def test_payload_width_edit_blocks_loaded_door_passage(self):
        config = reference_config()
        changed = edit(config, 'payloads', 0, {'width_m': .81})
        sim = Simulation(changed)
        self.assertIsNone(sim._same_floor_segments(sim.amrs[0], sim.locations['A'], sim.locations['B'], payload=sim.payloads['Box'], orientation='lengthways'))

    def test_payload_items_and_orientation_order_are_preserved(self):
        config = reference_config()
        config['payloads'][0]['items'] = {'linen': {'max': 42, 'custom': 'retained'}}
        changed = edit(config, 'payloads', 0, {'weight_kg': 20, 'allowed_carry_orientations': ['sideways', 'lengthways']})
        self.assertEqual(config['payloads'][0]['items'], changed['payloads'][0]['items'])
        self.assertEqual(['sideways', 'lengthways'], changed['payloads'][0]['allowed_carry_orientations'])

    def test_lift_speed_matches_floor_distance_and_legacy_metres_per_second(self):
        config = lift_config()
        config['building']['floor_height_m'] = 4
        config['lifts'][0]['health_percent'] = 100
        changed = edit(config, 'lifts', 0, {'speed_floors_per_sec': .5})
        self.assertEqual(2, changed['lifts'][0]['speed_m_per_sec'])
        sim = Simulation(changed)
        # Two floors / 0.5 floors per second = four seconds, with full health.
        self.assertEqual(4, sim.lifts[0].vertical_travel_duration_sec(2, 4))
        self.assertEqual(config['lifts'][0]['floor_locations'], changed['lifts'][0]['floor_locations'])

    def test_task_profile_change_uses_dirty_path_without_rewriting_schedule(self):
        config = profile_config()
        config['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box', route_profile='clean', release_time=0, labels=['urgent'])]
        changed = edit(config, 'tasks', 0, {'route_profile': 'dirty'})
        self.assertEqual(config['tasks'][0]['labels'], changed['tasks'][0]['labels'])
        self.assertEqual(0, changed['tasks'][0]['release_time'])
        self.assertEqual(11, run(changed).completed_task_records[0]['duration_sec'])

    def test_profile_permissions_keep_shared_access_and_directional_failure(self):
        config = profile_config()
        config['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box', route_profile='clean')]
        allowed = [pair for pair in config['route_profiles']['clean']['allowed_edges'] if pair != ['Clean', 'B']]
        changed = edit(config, 'route_profiles', 'clean', {'allowed_edges': allowed})
        self.assertEqual(config['route_profiles']['dirty'], changed['route_profiles']['dirty'])
        self.assertIn(['A', 'Shared'], changed['route_profiles']['clean']['allowed_edges'])
        self.assertEqual({'T'}, run(changed).failed_task_ids)

    def test_empty_permission_list_remains_unrestricted(self):
        config = profile_config()
        config['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box', route_profile='clean')]
        changed = edit(config, 'route_profiles', 'clean', {'allowed_edges': []})
        self.assertEqual(4.5, run(changed).completed_task_records[0]['duration_sec'])  # 1/2 + 4

    def test_invalid_references_ranges_and_required_defaults_fail_atomically(self):
        config = profile_config()
        config['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box')]
        original = deepcopy(config)
        for section, key, changes in [
            ('amrs', 0, {'quantity': 1.5}), ('amrs', 0, {'battery_soc_percent': 101}),
            ('amrs', 0, {'speed_m_per_sec': None}), ('amrs', 0, {'speed_m_per_sec': float('nan')}),
            ('payloads', 0, {'weight_kg': None}), ('payloads', 0, {'allowed_carry_orientations': []}),
            ('tasks', 0, {'payload': 'missing'}), ('tasks', 0, {'pickup': None}),
            ('tasks', 0, {'route_profile': 'missing'}),
            ('route_profiles', 'clean', {'allowed_nodes': ['missing']}),
            ('route_profiles', 'clean', {'allowed_edges': [['A', 'missing']]}),
            ('route_profiles', 'clean', {'allowed_lifts': ['missing']}),
            ('amrs', 0, {'id': 'new'})]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                edit(config, section, key, changes)
            self.assertEqual(original, config)

    def test_unknown_graph_nodes_and_required_lift_speed_cannot_be_cleared(self):
        config = lift_config()
        with self.assertRaises(ValueError):
            edit(config, 'lifts', 0, {'speed_floors_per_sec': None})
        config['building']['floor_height_m'] = 0
        with self.assertRaises(ValueError):
            edit(config, 'lifts', 0, {'speed_floors_per_sec': .5})


class ConfigurationPropertyUiTests(unittest.TestCase):
    setUpClass = classmethod(editing.CorridorEditingUiTests.setUpClass.__func__)
    setUp = editing.CorridorEditingUiTests.setUp
    tearDown = editing.CorridorEditingUiTests.tearDown

    def select(self, section, key):
        self.editor.workspace.select_configuration(section, key)
        return self.editor.properties_panel

    def profiles(self):
        self.editor.store = JsonStore(profile_config())
        self.editor._reset_edit_history()
        self.editor._saved_state = self.editor._configuration_state()
        self.editor.workspace.refresh()
        return self.select('route_profiles', 'clean')

    def test_tree_selects_configuration_object_and_inspection_is_read_only(self):
        before = deepcopy(self.editor.store.data)
        key = ('config', 'amrs', 0)
        self.assertIn(key, self.editor.workspace.configuration_items)
        self.editor.workspace.tree.setCurrentItem(self.editor.workspace.configuration_items[key])
        self.assertEqual('configuration', self.editor.workspace.stage)
        self.assertEqual(('amrs', (0,)), self.editor.properties_panel.target)
        self.assertFalse(self.editor.properties_panel.isHidden())
        self.assertEqual(before, self.editor.store.data)

    def test_robot_edit_is_one_undo_step_and_checks_become_stale(self):
        self.editor.validate_json()
        panel = self.select('amrs', 0)
        before = deepcopy(self.editor.store.data)
        panel.fields['speed_m_per_sec'].setText('1')
        self.assertTrue(panel.apply())
        self.assertFalse(self.editor.checks_panel.current())
        self.assertEqual(2, len(self.editor.edit_history.entries))
        self.assertTrue(self.editor.undo_edit())
        self.assertEqual(before, self.editor.store.data)
        self.assertTrue(self.editor.redo_edit())
        self.assertEqual(1, self.editor.store.data['amrs'][0]['speed_m_per_sec'])

    def test_profile_picker_filters_and_preserves_hidden_permissions(self):
        panel = self.profiles()
        widget = panel.fields['allowed_edges']
        original = deepcopy(widget.value())
        widget.search.setText('Clean → B')
        widget.set_shown(False)
        self.assertEqual([p for p in original if p != ['Clean', 'B']], widget.value())
        self.assertIn(['A', 'Shared'], widget.value())
        self.assertTrue(panel.apply())
        self.assertNotIn(['Clean', 'B'], self.editor.store.data['route_profiles']['clean']['allowed_edges'])

    def test_clear_permissions_explicitly_warns_that_empty_is_unrestricted(self):
        panel = self.profiles()
        widget = panel.fields['allowed_edges']
        widget.clear()
        self.assertIn('Unrestricted', widget.count.text())
        self.assertIn('Empty lists mean unrestricted', panel.note.text())
        self.assertTrue(panel.apply())
        self.assertEqual([], self.editor.store.data['route_profiles']['clean']['allowed_edges'])

    def test_named_edge_permission_does_not_create_geometry(self):
        panel = self.profiles()
        geometry = deepcopy(self.editor.store.data['corridors'])
        widget = panel.fields['allowed_edges']
        widget.start.setCurrentIndex(widget.start.findData('Clean'))
        widget.finish.setCurrentIndex(widget.finish.findData('Dirty'))
        widget.add_edge()
        self.assertTrue(panel.apply())
        self.assertIn(['Clean', 'Dirty'], self.editor.store.data['route_profiles']['clean']['allowed_edges'])
        self.assertEqual(geometry, self.editor.store.data['corridors'])

    def test_existing_unknown_choice_stays_visible_and_other_fields_do_not_rewrite_it(self):
        self.editor.store.data['route_profiles']['clean']['allowed_lifts'] = ['missing-lift']
        panel = self.select('route_profiles', 'clean')
        widget = panel.fields['allowed_lifts']
        self.assertIn('missing-lift', widget.list.item(0).text())
        self.assertEqual(['missing-lift'], widget.value())
        panel.fields['allowed_nodes'].search.setText('A')
        panel.fields['allowed_nodes'].set_shown(True)
        self.assertTrue(panel.apply())
        self.assertEqual(['missing-lift'], self.editor.store.data['route_profiles']['clean']['allowed_lifts'])

    def test_configuration_draft_remains_pinned_when_layout_is_selected(self):
        panel = self.select('amrs', 0)
        panel.fields['speed_m_per_sec'].setText('1')
        self.editor.workspace.select_object(('point', 'Door'))
        self.assertEqual(('amrs', (0,)), panel.target)
        self.assertTrue(panel.apply())
        self.assertEqual(1, self.editor.store.data['amrs'][0]['speed_m_per_sec'])
        self.assertEqual(('points', ('Door',)), panel.target)

    def test_stale_configuration_draft_cannot_replace_new_values(self):
        panel = self.select('amrs', 0)
        panel.fields['speed_m_per_sec'].setText('1')
        self.editor.store.data['amrs'][0]['quantity'] = 2
        self.assertFalse(panel.apply())
        self.assertEqual(2, self.editor.store.data['amrs'][0]['speed_m_per_sec'])
        self.assertEqual(2, self.editor.store.data['amrs'][0]['quantity'])

    def test_profile_picker_changes_are_included_in_recovery(self):
        panel = self.profiles()
        panel.fields['allowed_edges'].clear()
        self.assertTrue(self.editor.capture_recovery())
        saved = self.editor._recovery_store.read(self.editor._recovery_store.snapshot_path)
        self.assertEqual([], saved['config']['route_profiles']['clean']['allowed_edges'])
        self.assertTrue(self.editor.store.data['route_profiles']['clean']['allowed_edges'])

    def test_configuration_controls_fit_desktop_and_hide_for_review(self):
        panel = self.profiles()
        self.editor.resize(1280, 800)
        self.editor.show()
        for _ in range(4):
            QApplication.processEvents()
        self.assertLessEqual(self.editor.width(), 1280)
        self.assertLessEqual(self.editor.height(), 800)
        self.assertGreater(panel.width(), 500)
        self.editor.show_results_investigation()
        self.assertTrue(panel.isHidden())
