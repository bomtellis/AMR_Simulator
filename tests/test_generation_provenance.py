"""Independent precedence examples and inspectable source histories."""
import copy
import json
import os
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from amr_demand_preview import build_demand_preview
from simulator import Simulation
from tests.test_generation_reference import grouped_config
from visualiser.demand_preview_panel import DemandPreviewPanel, rule_explanation


def waste_config():
    config = grouped_config()
    config['task_generation']['categories']['waste'] = config['task_generation']['categories'].pop('stores')
    config['waste_streams'] = [{'name': 'General', 'payload': 'Box',
                              'container_capacity_m3': 0.5, 'full_threshold_fraction': 0.8}]
    config['departments'][0]['waste_streams'] = [{'name': 'General'}]
    return config


def active_rule(config):
    preview = build_demand_preview(config)
    return next(r for r in preview['rules'] if not r['id'].startswith('inactive:'))


class GenerationProvenanceTests(unittest.TestCase):
    def test_category_group_history_and_source_pointer(self):
        rule = active_rule(grouped_config())
        field = rule['field_provenance']['priority']
        self.assertEqual(7, field['value'])
        self.assertEqual([40, 7], [s['value'] for s in field['history']])
        self.assertEqual(['Category default', 'Group override'], [s['layer'] for s in field['history']])
        self.assertEqual('/task_generation/categories/stores/department_groups/0/payload/priority', field['path'])
        self.assertEqual((1, 1, 0), tuple(rule[k] for k in ('planned_records', 'expected_fixed_records', 'count_difference')))

    def test_equal_values_still_record_override(self):
        config = grouped_config()
        config['task_generation']['categories']['stores']['priority'] = 7
        field = active_rule(config)['field_provenance']['priority']
        self.assertEqual([7, 7], [s['value'] for s in field['history']])
        self.assertEqual('Group override', field['source'])

    def test_policy_restores_category_after_override(self):
        config = grouped_config()
        config['task_generation']['categories']['stores']['department_groups'][0]['payload']['dropoff_zone_capacity_policy'] = 'allow_temporary_overflow'
        field = active_rule(config)['field_provenance']['dropoff_zone_capacity_policy']
        self.assertEqual(['wait_for_space', 'allow_temporary_overflow', 'wait_for_space'], [s['value'] for s in field['history']])
        self.assertEqual('Category-wide policy', field['source'])

    def test_missing_category_policy_uses_default_after_override(self):
        config = grouped_config()
        category = config['task_generation']['categories']['stores']
        del category['dropoff_zone_capacity_policy']
        category['department_groups'][0]['payload']['dropoff_zone_capacity_policy'] = 'wait_for_space'
        field = active_rule(config)['field_provenance']['dropoff_zone_capacity_policy']
        self.assertEqual('allow_temporary_overflow', field['value'])
        self.assertEqual('Generator default', field['source'])
        self.assertEqual('', field['path'])

    def test_department_override_path_escapes_identifiers(self):
        config = grouped_config()
        category = config['task_generation']['categories'].pop('stores')
        config['task_generation']['categories']['s/~'] = category
        config['departments'][0]['id'] = 'D/~'
        category.pop('department_groups')
        category['departments'] = {'D/~': {'enabled': True, 'priority': 9}}
        field = active_rule(config)['field_provenance']['priority']
        self.assertEqual(9, field['value'])
        self.assertEqual('Department override', field['source'])
        self.assertEqual('/task_generation/categories/s~1~0/departments/D~1~0/priority', field['path'])

    def test_category_only_has_no_phantom_override(self):
        config = grouped_config()
        config['task_generation']['categories']['stores'].pop('department_groups')
        field = active_rule(config)['field_provenance']['priority']
        self.assertEqual([40], [s['value'] for s in field['history']])
        self.assertEqual('Category default', field['source'])

    def test_zone_handoff_records_forced_booleans(self):
        config = grouped_config()
        config['locations'].append({'name': 'C', 'floor': 0, 'x': 20, 'y': 20})
        config['task_generation']['categories']['stores'].update(return_enabled=False, requires_staff=False)
        config['departments'][0]['task_generation_locations'] = {'stores': {
            'pickup_dropoff_locations': ['C'], 'dropoff_zone_locations': ['B']}}
        rule = active_rule(config)
        for key in ('return_enabled', 'requires_staff'):
            field = rule['field_provenance'][key]
            self.assertEqual([False, True], [s['value'] for s in field['history']])
            self.assertEqual('Department drop-off zone handoff', field['source'])
        self.assertEqual(['B'], rule['effective_dropoffs'])
        self.assertEqual(['C'], rule['final_destinations'])

    def test_waste_payload_layers_and_exact_stream_paths(self):
        config = waste_config()
        other = copy.deepcopy(config['payloads'][0])
        other['name'] = 'Other'
        config['payloads'].append(other)
        config['waste_streams'][0]['payload'] = 'Other'
        config['departments'][0]['waste_streams'][0]['payload'] = 'Box'
        field = active_rule(config)['field_provenance']['payload']
        self.assertEqual(['Box', 'Other', 'Box'], [s['value'] for s in field['history']])
        self.assertEqual('/waste_streams/0/payload', field['history'][1]['path'])
        self.assertEqual('/departments/0/waste_streams/0/payload', field['path'])
        self.assertEqual('Department waste stream', field['source'])

    def test_waste_threshold_uses_effective_department_capacity(self):
        config = waste_config()
        config['departments'][0]['waste_streams'][0].update(container_capacity_m3=2, full_threshold_fraction=0.5)
        rule = active_rule(config)
        self.assertEqual(2, rule['effective_config']['container_capacity_m3'])
        # Department overrides: 2 m3 * .5 = 1 m3, replacing global .5 * .8.
        self.assertAlmostEqual(1, rule['effective_config']['threshold_volume_m3'])
        field = rule['field_provenance']['threshold_volume_m3']
        self.assertIn('2.0 m³ × effective fraction 0.5', field['history'][-1]['explanation'])
        self.assertIn('after department stream overrides', field['history'][-1]['explanation'])
        self.assertAlmostEqual(1, rule['effective_config']['volume_per_event_m3'])

    def test_waste_explicit_threshold_wins_and_event_volume_is_retained(self):
        config = waste_config()
        config['departments'][0]['waste_streams'][0].update(threshold_volume_m3=0.7, volume_per_event_m3=0.2)
        fields = active_rule(config)['field_provenance']
        self.assertEqual(0.7, fields['threshold_volume_m3']['value'])
        self.assertIn('Positive effective threshold', fields['threshold_volume_m3']['history'][-1]['explanation'])
        self.assertEqual('Department waste stream', fields['volume_per_event_m3']['source'])
        self.assertEqual(0.2, fields['volume_per_event_m3']['value'])

    def test_stream_overlays_are_visible_after_category_policy(self):
        config = waste_config()
        config['departments'][0]['waste_streams'][0]['dropoff_zone_capacity_policy'] = 'allow_temporary_overflow'
        field = active_rule(config)['field_provenance']['dropoff_zone_capacity_policy']
        self.assertEqual('Department waste stream', field['source'])
        self.assertEqual('allow_temporary_overflow', field['value'])

    def test_runtime_modes_keep_unknown_totals_with_provenance(self):
        for mode in ('threshold', 'continuous', 'hybrid', 'scheduled_threshold'):
            with self.subTest(mode=mode):
                config = waste_config()
                config['task_generation']['categories']['waste']['generation_mode'] = mode
                rule = active_rule(config)
                self.assertIsNone(rule['total_demand'])
                self.assertEqual('Category default', rule['field_provenance']['generation_mode']['source'])

    def test_zero_sporadic_rate_has_known_zero_with_provenance(self):
        config = waste_config()
        config['task_generation']['categories']['waste'].update(generation_mode='sporadic', frequency_per_day=0)
        rule = active_rule(config)
        self.assertEqual(0, rule['total_demand'])
        self.assertEqual('Category default', rule['field_provenance']['generation_mode']['source'])

    def test_trace_is_complete_serialisable_and_does_not_mutate_input(self):
        config = waste_config()
        before = copy.deepcopy(config)
        preview = build_demand_preview(config)
        rule = next(r for r in preview['rules'] if r.get('field_provenance'))
        self.assertEqual(rule['effective_config'], {k: v['value'] for k, v in rule['field_provenance'].items()})
        self.assertNotIn('Unattributed adjustment', json.dumps(rule['field_provenance']))
        self.assertEqual(before, config)
        self.assertEqual(preview, json.loads(json.dumps(preview)))
        runtime = Simulation(copy.deepcopy(config)).task_generation_manager.update_until(61)
        self.assertEqual([60], [r.task.release_time for r in runtime])
        self.assertEqual([7], [r.task.priority for r in runtime])


class ProvenanceUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.config = grouped_config()
        self.panel = DemandPreviewPanel(lambda: self.config)
        self.panel.accept_preview(build_demand_preview(self.config))

    def tearDown(self):
        self.panel.timer.stop()
        self.panel.close()

    def test_task_selects_rule_and_field_history(self):
        panel = self.panel
        panel.tasks.selectRow(0)
        panel.tabs.setCurrentIndex(3)
        panel.field_search.setText('priority')
        self.assertEqual(1, panel.fields.rowCount())
        panel.fields.selectRow(0)
        text = panel.details.toPlainText()
        self.assertIn('Category default: 40', text)
        self.assertIn('Group override: 7', text)
        self.assertIn('/department_groups/0/payload/priority', text)

    def test_rule_selection_and_older_history_fallback(self):
        panel = self.panel
        preview = copy.deepcopy(panel.preview)
        for rule in preview['rules']:
            rule.pop('field_provenance', None)
        panel.accept_preview(preview)
        panel.rules.selectRow(0)
        panel.tabs.setCurrentIndex(3)
        panel.field_search.setText('priority')
        panel.fields.selectRow(0)
        self.assertIn('History unavailable', panel.details.toPlainText())
        self.assertNotIn('Group override: 7', panel.details.toPlainText())

    def test_filter_clears_old_rule_and_stale_export_remains_blocked(self):
        panel = self.panel
        panel.tasks.selectRow(0)
        self.assertGreater(panel.fields.rowCount(), 0)
        panel.search.setText('absent-task')
        self.assertEqual(0, panel.fields.rowCount())
        self.assertIsNone(panel.selected_rule)
        self.config['task_generation']['categories']['stores']['priority'] = 3
        panel.check_staleness()
        self.assertFalse(panel.export_button.isEnabled())
        self.assertIn('STALE', panel.summary.text())

    def test_failed_rebuild_clears_previous_provenance(self):
        panel = self.panel
        panel.tasks.selectRow(0)
        panel.accept_preview(None, 'Invalid input')
        self.assertEqual(0, panel.fields.rowCount())
        self.assertIsNone(panel.selected_rule)
        self.assertFalse(panel.export_button.isEnabled())

    def test_waste_description_uses_precise_source_label(self):
        text = rule_explanation(active_rule(waste_config()))
        self.assertIn('Payload: Box [Waste stream default]', text)


from tests import test_appearance as appearance_tests


class ProvenanceLargeTextTests(unittest.TestCase):
    setUpClass = classmethod(appearance_tests.AppearanceUiTests.setUpClass.__func__)
    setUp = appearance_tests.AppearanceUiTests.setUp
    tearDown = appearance_tests.AppearanceUiTests.tearDown

    def test_demand_and_effective_settings_fit_large_text_desktop(self):
        from appearance import Appearance
        self.editor.store.data = grouped_config()
        self.editor.show_demand_preview()
        panel = self.editor.demand_panel
        panel.accept_preview(build_demand_preview(grouped_config()))
        panel.tasks.selectRow(0)
        self.editor.appearance.apply(Appearance(font_size=24))
        self.editor.resize(1280, 800)
        self.editor.show()
        for _ in range(4):
            self.app.processEvents()
        self.assertEqual(24, panel.build_button.font().pointSize())
        self.assertLessEqual(self.editor.width(), 1280)
        self.assertLessEqual(self.editor.height(), 800)
        panel.tabs.setCurrentIndex(3)
        self.app.processEvents()
        self.assertLessEqual(self.editor.height(), 800)


if __name__ == '__main__':
    unittest.main()
