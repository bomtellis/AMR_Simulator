import os
import sys
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'visualiser'))
from PySide6.QtWidgets import QApplication, QTableWidgetItem, QMessageBox
from building_settings import BuildingSettingsDialog
from amr_routing_inputs import validate_routing_inputs
from tests.test_floor_waypoints import floor_config


class WaypointInputTests(unittest.TestCase):
    def test_invalid_rules_fail_before_simulation_or_editor_normalisation(self):
        cfg = floor_config()
        for rules in (None, {}, [None], [dict(from_floor=True,to_floors=[1],via_floor=2)],
                      [dict(from_floor=0,to_floors=[1],via_floor=0)],
                      [dict(from_floor=0,to_floors=[8],via_floor=2)],
                      [dict(from_floor=0,to_floors=[1,1],via_floor=2)],
                      [dict(from_floor=0,to_floors=[0],via_floor=2)],
                      [dict(from_floor=0,to_floors=[1],via_floor=2)]*2):
            with self.subTest(rules=rules), self.assertRaises(ValueError):
                cfg['building']['mandatory_floor_waypoints']=rules
                validate_routing_inputs(cfg)


class WaypointSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def test_loaded_rule_remains_editable_and_save_preserves_configuration(self):
        cfg=floor_config()
        before=deepcopy(cfg)
        dialog=BuildingSettingsDialog(None,cfg)
        self.assertEqual('1, 2, 3, 4, 5',dialog.waypoint_rules.item(0,1).text())
        dialog.accept()
        self.assertEqual(before,dialog.result)
        self.assertEqual(before,cfg)
        dialog.close()

    def test_add_edit_remove_and_cancel(self):
        cfg=floor_config(waypoint=False)
        dialog=BuildingSettingsDialog(None,cfg)
        dialog.add_waypoint_rule()
        self.assertEqual(1,dialog.waypoint_rules.rowCount())
        dialog.waypoint_rules.setItem(0,1,QTableWidgetItem('1, 3, 4, 5'))
        dialog.accept()
        self.assertEqual([1,3,4,5],dialog.result['building']['mandatory_floor_waypoints'][0]['to_floors'])
        dialog=BuildingSettingsDialog(None,dialog.result)
        dialog.waypoint_rules.selectRow(0)
        dialog.remove_waypoint_rule()
        dialog.accept()
        self.assertEqual([],dialog.result['building']['mandatory_floor_waypoints'])
        cancel=BuildingSettingsDialog(None,cfg)
        cancel.add_waypoint_rule()
        cancel.reject()
        self.assertIsNone(cancel.result)
        self.assertNotIn('mandatory_floor_waypoints',cfg['building'])

    def test_invalid_rule_keeps_dialog_open_without_committing(self):
        dialog=BuildingSettingsDialog(None,floor_config())
        dialog.waypoint_rules.setItem(0,2,QTableWidgetItem('0'))
        with patch.object(QMessageBox,'warning') as warning:
            dialog.accept()
        warning.assert_called_once()
        self.assertIsNone(dialog.result)
        dialog.close()
