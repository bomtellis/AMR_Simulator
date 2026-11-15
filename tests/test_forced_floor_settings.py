"""Building toggle lifecycle and explicit-rule conflict handling."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from tests import test_building_settings as building
from tests.test_forced_floor import configured
from tests.test_floor_waypoints import floor_config
from PySide6.QtWidgets import QDialog, QFileDialog, QMessageBox
from amr_project import Project
from models import JsonStore
from building_settings import BuildingSettingsDialog, minimum_floor_count


class ForcedFloorSettingsTests(unittest.TestCase):
    setUpClass=classmethod(building.BuildingSettingsUiTests.setUpClass.__func__)
    setUp=building.BuildingSettingsUiTests.setUp
    tearDown=building.BuildingSettingsUiTests.tearDown

    def test_default_off_unchanged_save_and_cancel_do_not_add_settings(self):
        cfg=floor_config();before=deepcopy(cfg)
        dialog=BuildingSettingsDialog(None,cfg)
        self.assertFalse(dialog.force_via_enabled.isChecked())
        self.assertFalse(dialog.force_via_floor.isEnabled())
        self.assertTrue(dialog.transfer_floor.isEnabled())
        self.assertEqual(2,dialog.force_via_floor.currentData())
        dialog.accept();self.assertEqual(before,dialog.result)
        cancel=BuildingSettingsDialog(None,cfg)
        cancel.force_via_enabled.setChecked(True)
        cancel.reject();self.assertIsNone(cancel.result)
        self.assertEqual(before,cfg)

    def test_toggle_save_disable_and_reopen_remember_floor(self):
        dialog=BuildingSettingsDialog(None,floor_config())
        dialog.force_via_enabled.setChecked(True)
        self.assertTrue(dialog.force_via_floor.isEnabled())
        self.assertFalse(dialog.transfer_floor.isEnabled())
        self.assertFalse(dialog.destination_floors.isEnabled())
        dialog.accept();self.assertTrue(dialog.result['building']['force_via_floor_enabled'])
        self.assertEqual(2,dialog.result['building']['force_via_floor'])
        reopened=BuildingSettingsDialog(None,dialog.result)
        self.assertTrue(reopened.force_via_enabled.isChecked())
        reopened.force_via_enabled.setChecked(False)
        reopened.accept()
        self.assertFalse(reopened.result['building']['force_via_floor_enabled'])
        self.assertEqual(2,reopened.result['building']['force_via_floor'])

    def test_invalid_imported_boolean_is_not_silently_repaired(self):
        cfg=floor_config();cfg['building']['force_via_floor_enabled']='true'
        dialog=BuildingSettingsDialog(None,cfg)
        with patch.object(QMessageBox,'warning') as warning:dialog.accept()
        warning.assert_called_once();self.assertIsNone(dialog.result)

    def test_conflicting_rule_prevents_enabled_save(self):
        cfg=floor_config();cfg['building']['mandatory_floor_waypoints'][0]['via_floor']=3
        dialog=BuildingSettingsDialog(None,cfg)
        dialog.force_via_enabled.setChecked(True)
        with patch.object(QMessageBox,'warning') as warning:dialog.accept()
        warning.assert_called_once();self.assertIn('conflicts',warning.call_args.args[2])
        self.assertIsNone(dialog.result)

    def test_floor_choice_changes_and_floor_count_protects_selected_floor(self):
        cfg=floor_config(waypoint=False)
        dialog=BuildingSettingsDialog(None,cfg);dialog.force_via_enabled.setChecked(True)
        dialog.force_via_floor.setCurrentIndex(dialog.force_via_floor.findData(4))
        dialog.accept();self.assertEqual(4,dialog.result['building']['force_via_floor'])
        self.assertEqual(5,minimum_floor_count(dict(building=dict(force_via_floor=4))))

    def test_toggle_is_one_undo_step_and_project_reopens(self):
        self.editor.store=JsonStore(floor_config());self.editor._reset_edit_history()
        before=deepcopy(self.editor.store.data)
        def save(dialog):
            dialog.force_via_enabled.setChecked(True);dialog.accept();return QDialog.Accepted
        with patch.object(BuildingSettingsDialog,'exec',new=save):self.editor.manage_building_settings()
        after=deepcopy(self.editor.store.data)
        self.assertTrue(after['building']['force_via_floor_enabled'])
        self.assertTrue(self.editor.undo_edit());self.assertEqual(before,self.editor.store.data)
        self.assertTrue(self.editor.redo_edit());self.assertEqual(after,self.editor.store.data)
        target=Path(self.temp.name)/'forced-floor.amrproj'
        with patch.object(QFileDialog,'getSaveFileName',return_value=(str(target),'')):
            self.assertTrue(self.editor.save_project(save_as=True))
        self.assertEqual(after,Project.open(target).configuration())


if __name__=='__main__':unittest.main()
