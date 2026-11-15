"""Level-height edits preserve physical lift speed and project lifecycle behaviour."""
from copy import deepcopy
import contextlib
import io
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tests import test_corridor_editing as editing
from tests.test_delivery_energy_reference import lift_config
from PySide6.QtWidgets import QDialog, QFileDialog
from amr_project import Project
from simulator import Simulation
from models import JsonStore
from building_settings import BuildingSettingsDialog, set_level_height


class BuildingHeightTests(unittest.TestCase):
    def test_taller_levels_increase_travel_time_at_same_physical_speed(self):
        config = lift_config()
        config['building']['floor_height_m'] = 3
        config['lifts'][0].update(speed_floors_per_sec=.5, speed_m_per_sec=99,
                                 health_percent=100)
        config['tasks'] = [dict(id='Delivery', pickup='A', dropoff='B', payload='Box')]
        original = deepcopy(config)
        changed = set_level_height(config, 6)
        # 1.5 m/s over 3 m takes 2 s; over 6 m takes 4 s.
        self.assertEqual(.25, changed['lifts'][0]['speed_floors_per_sec'])
        self.assertEqual(1.5, changed['lifts'][0]['speed_m_per_sec'])
        times = []
        for candidate in (config, changed):
            with contextlib.redirect_stdout(io.StringIO()):
                sim = Simulation(candidate)
                sim.run()
            self.assertFalse(sim.failed_tasks)
            times.append(sim.completed_task_records[0]['duration_sec'])
        self.assertAlmostEqual(2, times[1] - times[0])
        self.assertEqual(original, config)
        self.assertEqual(config['locations'], changed['locations'])
        self.assertEqual(config['lifts'][0]['floor_locations'], changed['lifts'][0]['floor_locations'])

    def test_invalid_values_fail_atomically_and_incomplete_lifts_are_retained(self):
        config = lift_config()
        before = deepcopy(config)
        for value in (0, -1, float('nan'), float('inf'), True, None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                set_level_height(config, value)
            self.assertEqual(before, config)
        config['lifts'][0]['speed_floors_per_sec'] = 0
        with self.assertRaises(ValueError):
            set_level_height(config, 8)
        draft = {'building': {}, 'lifts': [{'id': 'Draft', 'speed_m_per_sec': 2}]}
        self.assertEqual(draft['lifts'], set_level_height(draft, 5)['lifts'])


class BuildingSettingsUiTests(unittest.TestCase):
    setUpClass = classmethod(editing.CorridorEditingUiTests.setUpClass.__func__)
    setUp = editing.CorridorEditingUiTests.setUp
    tearDown = editing.CorridorEditingUiTests.tearDown

    def test_floor_count_adds_empty_floors_and_is_undoable(self):
        self.editor.store=JsonStore()
        self.editor.store.data['building']['floor_count']=1
        self.editor._reset_edit_history()
        before=deepcopy(self.editor.store.data)
        def save(dialog):
            dialog.floor_count.setValue(3)
            dialog.level_height.setValue(3.5)
            dialog.accept();return QDialog.Accepted
        with patch.object(BuildingSettingsDialog,'exec',new=save):self.editor.manage_building_settings()
        self.assertEqual(3,self.editor.store.data['building']['floor_count'])
        self.assertEqual(3.5,self.editor.store.data['building']['floor_height_m'])
        self.assertEqual((0,1,2),self.editor.workspace._floors)
        self.assertEqual(before['locations'],self.editor.store.data['locations'])
        self.assertTrue(self.editor.undo_edit());self.assertEqual(before,self.editor.store.data)

    def test_floor_count_cannot_remove_referenced_floors_or_change_on_cancel(self):
        config=JsonStore(lift_config()).data
        config['building']['floor_count']=3
        config['floor_dxf_files']=[{'floor':2,'filepath':'retained.dxf'}]
        dialog=BuildingSettingsDialog(self.editor,config)
        self.assertEqual(3,dialog.floor_count.minimum())
        dialog.floor_count.setValue(1);self.assertEqual(3,dialog.floor_count.value())
        dialog.floor_count.setValue(4);dialog.reject()
        self.assertIsNone(dialog.result);self.assertEqual(3,config['building']['floor_count'])
        dialog.deleteLater()

    def test_save_is_one_undo_step_invalidates_checks_and_survives_reopen(self):
        self.editor.store = JsonStore(lift_config())
        self.editor._reset_edit_history()
        self.editor._saved_state = self.editor._configuration_state()
        before = deepcopy(self.editor.store.data)
        self.editor.validate_json()
        self.assertTrue(self.editor.checks_panel.current())

        def save(dialog):
            dialog.level_height.setValue(6)
            dialog.accept()
            return QDialog.Accepted

        with patch.object(BuildingSettingsDialog, 'exec', new=save):
            self.editor.manage_building_settings()
        after = deepcopy(self.editor.store.data)
        self.assertEqual(6, after['building']['floor_height_m'])
        self.assertTrue(self.editor.has_unsaved_changes())
        self.assertFalse(self.editor.checks_panel.current())
        self.assertEqual(2, len(self.editor.edit_history.entries))
        self.assertTrue(self.editor.undo_edit())
        self.assertEqual(before, self.editor.store.data)
        self.assertTrue(self.editor.redo_edit())
        self.assertEqual(after, self.editor.store.data)
        target = Path(self.temp.name) / 'changed.amrproj'
        with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(target), '')):
            self.assertTrue(self.editor.save_project(save_as=True))
        self.assertEqual(after, Project.open(target).configuration())

    def test_cancel_and_unchanged_save_preserve_precision_and_history(self):
        self.editor.store.data['building']['floor_height_m'] = 3.123456789
        self.editor._reset_edit_history()
        before = deepcopy(self.editor.store.data)
        for save in (False, True):
            def close(dialog):
                if save:
                    dialog.accept()
                    return QDialog.Accepted
                dialog.level_height.setValue(8)
                return QDialog.Rejected
            with patch.object(BuildingSettingsDialog, 'exec', new=close):
                self.editor.manage_building_settings()
            self.assertEqual(before, self.editor.store.data)
            self.assertEqual(1, len(self.editor.edit_history.entries))

    def test_configuration_button_opens_settings_and_run_lock_blocks_it(self):
        from PySide6.QtWidgets import QPushButton
        self.editor.workspace.configuration()
        buttons = self.editor.workspace.pages['configuration'].findChildren(QPushButton)
        button = next(b for b in buttons if b.text() == 'Building settings')
        with patch.object(BuildingSettingsDialog, 'exec', return_value=QDialog.Rejected) as opened:
            button.click()
            opened.assert_called_once()
        self.editor.project_runs_panel = SimpleNamespace(running=lambda: True)
        try:
            with patch.object(BuildingSettingsDialog, 'exec') as opened:
                self.assertFalse(self.editor.manage_building_settings())
                opened.assert_not_called()
        finally:
            del self.editor.project_runs_panel
