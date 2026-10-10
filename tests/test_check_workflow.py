"""Checks stay traceable without granting readiness to a changed project."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests import test_corridor_editing as editing
from tests.test_engineering_reference import reference_config
from tests.test_route_profiles import profile_config
from PySide6.QtWidgets import QApplication
from project_checks import check_project, CheckReport, Finding, config_fingerprint
from project_checks_panel import ProjectChecksPanel
from check_navigation import destination
from models import JsonStore


def find(report, code):
    return next(f for f in report.findings if f.code == code)


class CheckDependencyTests(unittest.TestCase):
    def config(self):
        config = reference_config()
        config['corridors']['edges'] = []
        config['amrs'][0]['payload_capacity_kg'] = 1
        return config

    def test_unrelated_robot_edit_keeps_graph_findings_but_invalidates_compatibility(self):
        config = self.config()
        report = check_project(config, include_legacy=False)
        graph, capacity = find(report, 'LOCATION_ISOLATED'), find(report, 'PAYLOAD_NO_AMR')
        report.acknowledge_warnings()
        self.assertTrue(report.can_run(config))
        config['amrs'][0]['payload_capacity_kg'] = 100
        self.assertEqual([], report.changed_inputs(graph, config))
        self.assertEqual(['amrs'], report.changed_inputs(capacity, config))
        self.assertFalse(report.can_run(config))
        states = report.group_states(config)
        self.assertEqual([], states['graph']['changed_inputs'])
        self.assertEqual(['amrs'], states['compatibility']['changed_inputs'])
        self.assertNotIn('PAYLOAD_NO_AMR', {f.code for f in check_project(config, include_legacy=False).findings})

    def test_graph_edit_does_not_stale_payload_compatibility(self):
        config = self.config()
        report = check_project(config, include_legacy=False)
        config['corridors']['edges'] = [{'from': 'A', 'to': 'B'}]
        self.assertEqual(['corridors'], report.changed_inputs(find(report, 'LOCATION_ISOLATED'), config))
        self.assertEqual([], report.changed_inputs(find(report, 'PAYLOAD_NO_AMR'), config))
        self.assertNotIn('LOCATION_ISOLATED', {f.code for f in check_project(config, include_legacy=False).findings})

    def test_task_and_profile_edits_invalidate_routing(self):
        config = profile_config()
        config['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box', route_profile='clean')]
        config['route_profiles']['clean']['allowed_nodes'] = ['A', 'Shared']
        report = check_project(config, include_legacy=False)
        finding = find(report, 'TASK_UNREACHABLE')
        config['route_profiles']['clean']['allowed_nodes'] = []
        self.assertEqual(['route_profiles'], report.changed_inputs(finding, config))
        self.assertNotIn('TASK_UNREACHABLE', {f.code for f in check_project(config, include_legacy=False).findings})

    def test_passing_check_groups_become_stale_even_without_findings(self):
        config = reference_config()
        report = check_project(config, include_legacy=False)
        self.assertFalse(any(f.code == 'PAYLOAD_NO_AMR' for f in report.findings))
        config['payloads'][0]['width_m'] = 999
        self.assertEqual(['payloads'], report.group_states(config)['compatibility']['changed_inputs'])
        self.assertFalse(report.can_run(config))

    def test_skipped_checks_are_not_reported_as_completed(self):
        config = reference_config()
        config['amrs'][0]['speed_m_per_sec'] = 0
        report = check_project(config)
        states = report.group_states(config)
        self.assertEqual('completed', states['values']['execution'])
        for key in ('graph', 'compatibility', 'drawings', 'scope', 'legacy'):
            self.assertEqual('not_run', states[key]['execution'])

    def test_unknown_and_legacy_checks_conservatively_depend_on_everything(self):
        from check_dependencies import dependencies
        finding = Finding('FUTURE_CHECK', 'info', 'coverage', '/', 'Project', 'Unknown', '', '', 'project')
        self.assertEqual(('*',), dependencies(finding))
        config = reference_config()
        old = CheckReport(config_fingerprint(config), [finding])
        config['new_extension'] = 7
        self.assertEqual(['*'], old.changed_inputs(finding, config))

    def test_dependency_metadata_preserves_finding_ids_and_old_report_fields(self):
        config = self.config()
        report = check_project(config, include_legacy=False)
        before = [f.id for f in report.findings]
        body = json.loads(json.dumps(report.to_dict()))
        self.assertEqual(1, body['schema_version'])
        self.assertEqual(1, body['dependency_schema_version'])
        self.assertEqual(before, [f['id'] for f in body['findings']])
        self.assertEqual(config_fingerprint(config), body['config_sha256'])
        self.assertEqual(before, [f.id for f in check_project(config, include_legacy=False).findings])

    def test_missing_drawing_becoming_available_stales_checks_without_config_change(self):
        with tempfile.TemporaryDirectory() as directory:
            config = reference_config()
            config['floor_dxf_files'] = [dict(floor=0, filepath='drawing.dxf')]
            report = check_project(config, base_path=directory, include_legacy=False)
            finding = find(report, 'DRAWING_MISSING')
            report.acknowledge_warnings()
            before = config_fingerprint(config)
            self.assertTrue(report.can_run(config))
            Path(directory, 'drawing.dxf').write_text('placeholder; checker tests availability only')
            self.assertEqual(before, config_fingerprint(config))
            self.assertEqual(['@drawings'], report.changed_inputs(finding, config))
            self.assertFalse(report.can_run(config))
            self.assertEqual(['@drawings'], report.group_states(config)['drawings']['changed_inputs'])

    def test_removing_available_drawing_invalidates_previously_clear_group(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, 'drawing.dxf')
            path.write_text('availability only')
            config = reference_config()
            config['floor_dxf_files'] = [dict(floor=0, filepath=str(path))]
            report = check_project(config, include_legacy=False)
            self.assertFalse(any(f.code == 'DRAWING_MISSING' for f in report.findings))
            path.unlink()
            self.assertTrue(report.is_stale(config))
            self.assertEqual(['@drawings'], report.group_states(config)['drawings']['changed_inputs'])

    def test_reverting_inputs_restores_finding_currency_but_not_acknowledgements(self):
        config = self.config()
        report = check_project(config, include_legacy=False)
        before = deepcopy(config)
        config['locations'][0]['x'] = 99
        self.assertTrue(report.changed_inputs(find(report, 'LOCATION_ISOLATED'), config))
        self.assertEqual([], report.changed_inputs(find(report, 'LOCATION_ISOLATED'), before))
        self.assertFalse(report.can_run(before))


class CheckNavigationTests(unittest.TestCase):
    def test_parallel_edge_records_resolve_by_record_index_not_endpoint(self):
        config = reference_config()
        config['corridors']['edges'].append(dict(config['corridors']['edges'][0], width_m=0))
        finding = next(f for f in check_project(config).findings if f.path == '/corridors/edges/2/width_m')
        self.assertEqual(('edge', 2, 'width_m'), tuple(vars(destination(config, finding)).values()))

    def test_duplicate_robot_identity_still_resolves_exact_row(self):
        config = reference_config()
        config['amrs'].append(deepcopy(config['amrs'][0]))
        finding = next(f for f in check_project(config).findings if f.path == '/amrs/1/id')
        target = destination(config, finding)
        self.assertEqual(('amrs', 1, 'id'), (target.kind, target.key, target.field))

    def test_profile_names_with_slashes_resolve_by_recorded_identity(self):
        config = reference_config()
        config['route_profiles'] = {'clean/shared~1': {'allowed_nodes': ['Missing']}}
        finding = next(f for f in check_project(config).findings if f.section == 'route_profiles')
        self.assertEqual('clean/shared~1', destination(config, finding).key)

    def test_ambiguous_points_are_not_selected_by_name(self):
        config = reference_config()
        config['corridors']['nodes'][0]['name'] = 'A'
        finding = next(f for f in check_project(config).findings if f.path == '/corridors/nodes/0/name')
        self.assertIsNone(destination(config, finding))


class CheckWorkflowUiTests(unittest.TestCase):
    setUpClass = classmethod(editing.CorridorEditingUiTests.setUpClass.__func__)
    setUp = editing.CorridorEditingUiTests.setUp
    tearDown = editing.CorridorEditingUiTests.tearDown

    def check(self):
        self.editor.validate_json()
        return self.editor.checks_panel

    def test_corridor_finding_selects_edge_properties(self):
        self.editor.store.data['corridors']['edges'][0]['width_m'] = 0
        panel = self.check()
        finding = next(f for f in panel.report.findings if f.path == '/corridors/edges/0/width_m')
        self.assertTrue(self.editor.navigate_check_finding(finding))
        self.assertEqual(('edges', (0,)), self.editor.properties_panel.target)
        self.assertEqual('layout', self.editor.workspace.stage)
        self.assertEqual(set(), self.editor.selected_point_names)

    def test_robot_finding_selects_common_field_without_opening_modal_editor(self):
        self.editor.store.data['amrs'][0]['speed_m_per_sec'] = 0
        panel = self.check()
        finding = next(f for f in panel.report.findings if f.path == '/amrs/0/speed_m_per_sec')
        with patch.object(self.editor, 'manage_amrs', side_effect=AssertionError('Should use properties')):
            self.editor.navigate_check_finding(finding)
        self.assertEqual(('amrs', (0,)), self.editor.properties_panel.target)
        self.assertEqual('configuration', self.editor.workspace.stage)
        self.assertEqual('0', self.editor.properties_panel.fields['speed_m_per_sec'].text())

    def test_profile_reference_finding_selects_permission_picker(self):
        self.editor.store.data['route_profiles']['clean']['allowed_nodes'] = ['Missing']
        panel = self.check()
        finding = next(f for f in panel.report.findings if f.path.endswith('/allowed_nodes'))
        self.editor.navigate_check_finding(finding)
        self.assertEqual(('route_profiles', ('clean',)), self.editor.properties_panel.target)
        self.assertEqual(['Missing'], self.editor.properties_panel.fields['allowed_nodes'].value())

    def test_ambiguous_point_does_not_fall_back_to_wrong_map_object(self):
        self.editor.store.data['corridors']['nodes'].append(dict(name='A', floor=0, x=99, y=99))
        panel = self.check()
        finding = next(f for f in panel.report.findings if f.code == 'DUPLICATE')
        with patch.object(self.editor, 'manage_corridor_settings', side_effect=AssertionError('Ambiguous object')):
            self.assertFalse(self.editor.navigate_check_finding(finding))
        self.assertEqual('checks', self.editor.workspace.stage)

    def test_unchanged_finding_can_be_investigated_but_changed_project_cannot_run(self):
        self.editor.store.data['corridors']['edges'] = []
        panel = self.check()
        finding = find(panel.report, 'LOCATION_ISOLATED')
        panel.acknowledge.setChecked(True)
        self.editor.store.data['amrs'][0]['speed_m_per_sec'] = 1
        panel.check_staleness()
        self.assertTrue(panel.finding_current(finding))
        self.assertFalse(panel.can_run())
        self.assertFalse(panel.acknowledge.isChecked())
        self.assertIn('Unchanged inputs', [panel.table.item(row, 3).text() for row in range(panel.table.rowCount())])
        self.assertTrue(self.editor.navigate_check_finding(finding))
        self.assertEqual(finding.target, self.editor.selected_point_name)

    def test_affected_finding_cannot_navigate_using_old_indices(self):
        self.editor.store.data['amrs'][0]['speed_m_per_sec'] = 0
        panel = self.check()
        finding = next(f for f in panel.report.findings if f.path == '/amrs/0/speed_m_per_sec')
        self.editor.store.data['amrs'].insert(0, dict(self.editor.store.data['amrs'][0], id='Other'))
        panel.check_staleness()
        self.assertFalse(panel.finding_current(finding))
        self.assertFalse(self.editor.navigate_check_finding(finding))
        self.assertEqual('checks', self.editor.workspace.stage)

    def test_existing_property_draft_is_preserved_during_finding_navigation(self):
        self.editor.store.data['payloads'][0]['weight_kg'] = -1
        panel = self.check()
        finding = next(f for f in panel.report.findings if f.path == '/payloads/0/weight_kg')
        self.editor.workspace.select_configuration('amrs', 0)
        properties = self.editor.properties_panel
        properties.fields['speed_m_per_sec'].setText('1')
        self.editor.navigate_check_finding(finding)
        self.assertTrue(properties.pending)
        self.assertEqual(('amrs', (0,)), properties.target)
        self.assertEqual('1', properties.fields['speed_m_per_sec'].text())

    def test_project_folder_change_blocks_finding_navigation(self):
        self.editor.store.data['corridors']['edges'] = []
        panel = self.check()
        finding = find(panel.report, 'LOCATION_ISOLATED')
        self.editor.current_json_path = str(Path(self.temp.name) / 'moved' / 'project.json')
        panel.check_staleness()
        self.assertFalse(panel.finding_current(finding))
        self.assertFalse(panel.can_run())

    def test_inaccessible_provider_clears_old_selection_on_recheck(self):
        panel = self.check()
        def unavailable():
            raise FileNotFoundError('Unavailable')
        panel.config_provider = unavailable
        panel.check_now()
        self.assertEqual([], panel.visible_findings)
        self.assertIsNone(panel.selected())
        self.assertFalse(panel.navigate_button.isEnabled())
        self.assertFalse(panel.can_run())

    def test_coverage_tab_explains_skipped_checks_without_navigating_old_findings(self):
        self.editor.store.data['amrs'][0]['speed_m_per_sec'] = 0
        panel = self.check()
        panel.tabs.setCurrentIndex(1)
        rows = {panel.groups_table.item(row, 0).text(): row for row in range(panel.groups_table.rowCount())}
        row = rows['Graph connectivity']
        self.assertEqual('not run', panel.groups_table.item(row, 1).text())
        panel.groups_table.selectRow(row)
        self.assertIn('Not run means', panel.details.toPlainText())
        self.assertFalse(panel.navigate_button.isEnabled())

    def test_returning_through_tree_retains_old_report_until_explicit_recheck(self):
        panel = self.check()
        report = panel.report
        self.editor.workspace.select_configuration('amrs', 0)
        self.editor.properties_panel.fields['speed_m_per_sec'].setText('1')
        self.assertTrue(self.editor.properties_panel.apply())
        self.editor.workspace.activate('checks')
        self.assertIs(report, panel.report)
        self.assertIn('STALE', panel.summary.text())
        panel.refresh_button.click()
        self.assertIsNot(report, panel.report)
        self.assertTrue(panel.current())


from tests import test_appearance as appearance_tests


class CheckLargeTextTests(unittest.TestCase):
    setUpClass = classmethod(appearance_tests.AppearanceUiTests.setUpClass.__func__)
    setUp = appearance_tests.AppearanceUiTests.setUp
    tearDown = appearance_tests.AppearanceUiTests.tearDown

    def test_findings_and_coverage_fit_large_text_desktop(self):
        from appearance import Appearance
        self.editor.validate_json()
        self.editor.appearance.apply(Appearance(font_size=24))
        self.editor.resize(1280, 800)
        self.editor.show()
        for _ in range(4):
            self.app.processEvents()
        self.assertEqual(24, self.editor.checks_panel.refresh_button.font().pointSize())
        self.assertLessEqual(self.editor.width(), 1280)
        self.assertLessEqual(self.editor.height(), 800)
        self.editor.checks_panel.tabs.setCurrentIndex(1)
        self.app.processEvents()
        self.assertLessEqual(self.editor.height(), 800)
