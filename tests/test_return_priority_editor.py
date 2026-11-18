"""Return priority is optional, visible and survives both delivery editors."""
from copy import deepcopy
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'visualiser'))
from PySide6.QtWidgets import QApplication
from dialogs import TaskGenerationSettingsDialog, BulkDepartmentTaskGenerationDialog, SimulationSettingsDialog
from tests.test_generation_reference import grouped_config
from amr_generation_inputs import generation_input_findings


class ReturnPriorityEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_department_save_and_reopen_preserve_explicit_zero_and_priority(self):
        for value in (0, 35):
            cfg = grouped_config()
            cfg['departments'][0]['task_generation_locations'] = {'stores': {'pickup_dropoff_locations': ['B']}}
            category = cfg['task_generation']['categories']['stores']
            category.pop('department_groups', None)
            category['departments'] = {'D': dict(enabled=True, payload='Box', pickup_location='A',
                dropoff_location='B', days_active=['mon'], scheduled_times=['00:01'],
                return_enabled=True, return_payload='Box', return_priority=value)}
            saved = []
            dialog = TaskGenerationSettingsDialog(None, cfg['task_generation'], ['A', 'B'], ['Box'], [],
                                                   cfg['departments'], saved.append)
            self.addCleanup(dialog.close)
            dialog.current_key = 'stores'
            dialog.current_department_id = 'D'
            dialog._load_category('stores')
            self.assertEqual(str(value), dialog.return_priority_edit.text())
            with patch('dialogs.QMessageBox.warning', side_effect=AssertionError('Unexpected validation warning')):
                dialog.accept()
            self.assertEqual(value, saved[0]['categories']['stores']['departments']['D']['return_priority'])

    def test_bulk_round_trip_and_blank_inherit_delivery_priority(self):
        cfg = grouped_config()
        cfg['departments'][0]['task_generation_locations'] = {'stores': {'pickup_dropoff_locations': ['B']}}
        category = deepcopy(cfg['task_generation']['categories']['stores'])
        category.update(enabled=True, return_enabled=True, return_payload='Box', return_priority=35)
        for text, expected in [('0', 0), ('35', 35), ('', None)]:
            dialog = BulkDepartmentTaskGenerationDialog(None, 'stores', 'Stores', cfg['departments'],
                category, ['A', 'B'], ['Box'], [], selected_department_ids=['D'])
            self.addCleanup(dialog.close)
            self.assertEqual('35', dialog.return_priority_edit.text())
            dialog.return_priority_edit.setText(text)
            with patch('dialogs.QMessageBox.warning', side_effect=AssertionError('Unexpected validation warning')):
                dialog.accept()
            self.assertEqual(expected, dialog.result['D'].get('return_priority'))

    def test_invalid_return_priority_is_rejected_at_each_rule_layer(self):
        for value in (-1, True, 1.5, 'bad'):
            cfg = grouped_config()
            cfg['task_generation']['categories']['stores']['department_groups'][0]['payload']['return_priority'] = value
            self.assertTrue(any('return_priority' in path for _, path, _ in generation_input_findings(cfg)))

    def test_simulation_dialog_retains_dispatch_and_return_policies(self):
        settings = dict(start_datetime='2026-01-05T00:00:00',
                        service_return_amr_policy='any_compatible', dispatch_available_amrs_only=True)
        dialog = SimulationSettingsDialog(None, settings)
        self.addCleanup(dialog.close)
        dialog.accept()
        self.assertEqual(settings, dialog.result)


if __name__ == '__main__':
    unittest.main()
