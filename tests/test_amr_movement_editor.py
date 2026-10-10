"""Robot editing must retain engineering inputs and apply capability changes explicitly."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication
from tests.test_reference_offset_integration import reference_config
from visualiser.dialogs import AMREditorDialog


class AMRMovementEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def dialog(self, robot):
        dialog = AMREditorDialog(None, ['A', 'B'], robot)
        self.addCleanup(dialog.close)
        return dialog

    def save(self, dialog):
        with patch('visualiser.dialogs.QMessageBox.warning') as warning:
            dialog.accept()
        warning.assert_not_called()
        self.assertIsNotNone(dialog.result)
        return dialog.result

    def test_quantity_edit_save_and_reopen_preserve_detailed_inputs(self):
        robot = reference_config()['amrs'][0]
        robot['engineering_extension'] = {'model': ['vendor', 1.234567890123]}
        before = deepcopy(robot)
        dialog = self.dialog(robot)
        dialog.quantity_edit.setValue(3)
        saved = self.save(dialog)
        self.assertEqual(3, saved['quantity'])
        for key in ('movement', 'manoeuvring', 'engineering_extension'):
            self.assertEqual(before[key], saved[key])
        self.assertEqual(before, robot)
        reopened = self.save(self.dialog(saved))
        for key in ('movement', 'manoeuvring', 'engineering_extension'):
            self.assertEqual(before[key], reopened[key])
        saved['engineering_extension']['model'].append('changed')
        self.assertEqual(before, robot)

    def test_preset_changes_one_state_and_persists_explicit_reverse_migration(self):
        robot = reference_config()['amrs'][0]
        robot['movement']['extension'] = {'keep': [1, 2]}
        robot['movement']['empty']['forward_speed_m_per_sec'] = 1.234567890123
        before = deepcopy(robot)
        dialog = self.dialog(robot)
        panel = dialog.movement_capabilities
        panel.presets['loaded'].setCurrentIndex(panel.presets['loaded'].findData('steering'))
        panel.apply_buttons['loaded'].click()
        panel.controls['loaded']['reverse_allowed'].setChecked(False)
        saved = self.save(dialog)
        expected = deepcopy(before['movement'])
        expected['schema_version'] = 2
        expected['empty']['reverse_allowed'] = True
        expected['loaded'].update(reverse_allowed=False, pivot_allowed=False, lateral_allowed=False)
        self.assertEqual(expected, saved['movement'])
        self.assertEqual(before['manoeuvring'], saved['manoeuvring'])
        self.assertEqual(before, robot)
        reopened = self.save(self.dialog(saved))
        self.assertEqual(expected, reopened['movement'])

    def test_cancel_and_returning_controls_to_original_do_not_migrate(self):
        robot = reference_config()['amrs'][0]
        before = deepcopy(robot)
        dialog = self.dialog(robot)
        control = dialog.movement_capabilities.controls['empty']['reverse_allowed']
        control.setChecked(False)
        dialog.reject()
        self.assertIsNone(dialog.result)
        self.assertEqual(before, robot)
        second = self.dialog(robot)
        control = second.movement_capabilities.controls['empty']['reverse_allowed']
        control.setChecked(False)
        control.setChecked(True)
        self.assertEqual(before['movement'], self.save(second)['movement'])

    def test_absent_or_invalid_detailed_settings_are_preserved_on_other_edit(self):
        for value in (None, {'schema_version': 999, 'custom': ['keep']}):
            with self.subTest(value=value):
                robot = reference_config()['amrs'][0]
                if value is None:
                    del robot['movement']
                else:
                    robot['movement'] = value
                dialog = self.dialog(robot)
                self.assertFalse(dialog.movement_capabilities.controls)
                dialog.quantity_edit.setValue(2)
                result = self.save(dialog)
                if value is None:
                    self.assertNotIn('movement', result)
                else:
                    self.assertEqual(value, result['movement'])

    def test_enabling_lateral_without_speed_rejects_without_partial_save(self):
        robot = reference_config()['amrs'][0]
        robot['movement']['empty']['lateral_allowed'] = False
        robot['movement']['empty'].pop('lateral_speed_m_per_sec', None)
        before = deepcopy(robot)
        dialog = self.dialog(robot)
        panel = dialog.movement_capabilities
        panel.presets['empty'].setCurrentIndex(panel.presets['empty'].findData('omnidirectional'))
        panel.apply_buttons['empty'].click()
        with patch('visualiser.dialogs.QMessageBox.warning') as warning:
            dialog.accept()
        warning.assert_called_once()
        self.assertIsNone(dialog.result)
        self.assertIn('lateral_speed_m_per_sec', warning.call_args.args[2])
        self.assertEqual(before, robot)


if __name__ == '__main__':
    unittest.main()
