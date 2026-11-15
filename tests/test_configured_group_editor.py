"""Configured schedule copies, deletion and cancellation preserve model ownership."""
from copy import deepcopy
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'visualiser'))
from PySide6.QtCore import Qt, QMimeData, QByteArray, QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
from visualiser.configured_group_editor import ConfiguredGroupEditorDialog, MIME, apply_group_edits
from visualiser.dialogs import TaskGenerationSettingsDialog, BulkDepartmentTaskGenerationDialog
from tests.test_generation_reference import grouped_config
from simulator import Simulation


def config():
    cfg = grouped_config()
    cfg['locations'].append(dict(name='C', floor=0, x=10, y=8))
    cfg['corridors']['edges'].append(dict(**{'from': 'B', 'to': 'C'}, width_m=3))
    cfg['departments'][0]['task_generation_locations'] = {'stores': {'pickup_dropoff_locations': ['B']}}
    cfg['departments'].append(dict(id='E', name='Other department', enabled=True,
        task_generation_locations={'stores': {'pickup_dropoff_locations': ['C']}}))
    category = cfg['task_generation']['categories']['stores']
    payload = {key: deepcopy(value) for key, value in category.items() if key != 'department_groups'}
    payload.update(priority=7, department_location_role='dropoff', requires_staff=False,
        staff_working_hours={'mon': {'enabled': True, 'start': '08:00', 'end': '16:00'}},
        extension={'nested': [1, 2]})
    category['department_groups'] = [dict(id='GROUP-1', departments=['D', 'E'], payload=payload)]
    category['departments'] = {'D': deepcopy(payload), 'E': dict(deepcopy(payload), dropoff_location='C', dropoff_locations=['C'])}
    return cfg


def label(group):
    return ', '.join(group['payload'].get('scheduled_times', []))


class ConfiguredGroupDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        QApplication.clipboard().clear()
        self.groups = {g['id']: g for g in config()['task_generation']['categories']['stores']['department_groups']}
        self.opened = []

    def tearDown(self):
        for dialog in self.opened:
            dialog.close()
            dialog.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        QApplication.clipboard().clear()

    def dialog(self, callback=None, category='stores'):
        dialog = ConfiguredGroupEditorDialog(None, self.groups, label,
            callback or (lambda group: group), category)
        self.opened.append(dialog)
        return dialog

    def test_copy_paste_edit_schedule_has_fresh_identity_and_independent_data(self):
        def edit(group):
            group['payload']['scheduled_times'] = ['00:02']
            group['payload']['extension']['nested'].append(3)
            return group

        before = deepcopy(self.groups)
        dialog = self.dialog(edit)
        dialog.copy_selected()
        self.assertTrue(dialog.paste_button.isEnabled())
        dialog.paste_group()
        self.assertEqual({'GROUP-1', 'GROUP-2'}, set(dialog.groups))
        self.assertEqual(['00:02'], dialog.groups['GROUP-2']['payload']['scheduled_times'])
        self.assertEqual([1, 2], dialog.groups['GROUP-1']['payload']['extension']['nested'])
        self.assertEqual(['D', 'E'], dialog.groups['GROUP-2']['departments'])
        self.assertEqual(before, self.groups)
        self.assertEqual([1, 2], json.loads(bytes(QApplication.clipboard().mimeData().data(MIME)))['group']['payload']['extension']['nested'])
        dialog.paste_group()
        self.assertEqual({'GROUP-1', 'GROUP-2', 'GROUP-3'}, set(dialog.groups))
        dialog.accept()
        self.assertEqual(3, len(dialog.result_groups))

    def test_cancel_paste_does_not_add_group_and_cancel_manager_discards_draft(self):
        dialog = self.dialog(lambda group: None)
        dialog.copy_selected()
        dialog.paste_group()
        self.assertEqual(1, len(dialog.groups))
        dialog.edit_group_callback = lambda group: group
        dialog.paste_group()
        dialog.reject()
        self.assertIsNone(dialog.result_groups)
        self.assertEqual(1, len(self.groups))

    def test_delete_confirmation_and_delete_last_group_then_paste(self):
        dialog = self.dialog()
        dialog.copy_selected()
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.No):
            dialog.delete_selected()
        self.assertEqual(1, len(dialog.groups))
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes):
            dialog.delete_selected()
        self.assertEqual({}, dialog.groups)
        self.assertFalse(dialog.copy_button.isEnabled())
        self.assertTrue(dialog.paste_button.isEnabled())
        dialog.paste_group()
        self.assertEqual(['GROUP-2'], list(dialog.groups))

    def test_empty_manager_accepts_all_deleted_and_clipboard_is_category_scoped(self):
        dialog = self.dialog()
        dialog.copy_selected()
        other = self.dialog(category='linen')
        self.assertFalse(other.paste_button.isEnabled())
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes):
            dialog.delete_selected()
        dialog.accept()
        self.assertEqual([], dialog.result_groups)

    def test_invalid_clipboard_and_editor_error_do_not_change_draft(self):
        dialog = self.dialog()
        for raw in (b'not json', b'[]', b'{"version":1,"category":"stores","group":{"payload":[],"departments":["D"]}}'):
            mime = QMimeData()
            mime.setData(MIME, QByteArray(raw))
            QApplication.clipboard().setMimeData(mime)
            self.assertFalse(dialog.paste_button.isEnabled())
            dialog.paste_group()
        dialog.copy_selected()
        dialog.edit_group_callback = Mock(side_effect=ValueError('Invalid settings'))
        with patch.object(QMessageBox, 'warning') as warning:
            dialog.paste_group()
        warning.assert_called_once()
        self.assertEqual(1, len(dialog.groups))

    def test_edit_existing_preserves_identity(self):
        def edit(group):
            group['payload']['scheduled_times'] = ['00:03']
            group['id'] = 'not-the-original-id'
            return group
        dialog = self.dialog(edit)
        dialog.edit_selected()
        self.assertEqual('GROUP-1', dialog.groups['GROUP-1']['id'])
        self.assertEqual(['00:03'], dialog.groups['GROUP-1']['payload']['scheduled_times'])

    def test_keyboard_copy_paste_and_delete_are_available_on_group_list(self):
        from PySide6.QtTest import QTest
        dialog = self.dialog()
        dialog.show()
        dialog.activateWindow()
        dialog.list_widget.setFocus()
        self.app.processEvents()
        QTest.keyClick(dialog.list_widget, Qt.Key_C, Qt.ControlModifier)
        self.assertTrue(QApplication.clipboard().mimeData().hasFormat(MIME))
        QTest.keyClick(dialog.list_widget, Qt.Key_V, Qt.ControlModifier)
        self.assertEqual(2, len(dialog.groups))
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes):
            QTest.keyClick(dialog.list_widget, Qt.Key_Delete)
        self.assertEqual(1, len(dialog.groups))


class GroupCompatibilityTests(unittest.TestCase):
    def test_delete_last_group_removes_department_specific_compatibility_copies(self):
        category = config()['task_generation']['categories']['stores']
        before = deepcopy(category)
        updated = apply_group_edits(category, category['department_groups'], [], lambda *_: None)
        self.assertEqual({}, updated['departments'])
        self.assertEqual([], updated['department_groups'])
        self.assertEqual(before, category)

    def test_delete_retains_unrelated_department_override(self):
        category = config()['task_generation']['categories']['stores']
        category['departments']['D']['priority'] = 99
        updated = apply_group_edits(category, category['department_groups'], [], lambda *_: None)
        self.assertEqual(99, updated['departments']['D']['priority'])
        self.assertNotIn('E', updated['departments'])

    def test_deleting_one_run_keeps_remaining_groups_and_restores_compatibility(self):
        category = config()['task_generation']['categories']['stores']
        second = deepcopy(category['department_groups'][0])
        second['id'] = 'GROUP-2'
        second['payload']['scheduled_times'] = ['00:02']
        category['department_groups'].append(second)
        category['departments']['D'] = deepcopy(second['payload'])
        updated = apply_group_edits(category, category['department_groups'], [category['department_groups'][0]],
            lambda group, department: group['payload'])
        self.assertEqual(['00:01'], updated['departments']['D']['scheduled_times'])
        self.assertEqual(1, len(updated['department_groups']))


class ParentScheduleIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def tearDown(self):
        QApplication.clipboard().clear()

    def dialog(self, cfg, on_save=None):
        dialog = TaskGenerationSettingsDialog(None, cfg['task_generation'],
            [row['name'] for row in cfg['locations']], ['Box'], [], cfg['departments'], on_save or Mock())
        self.addCleanup(dialog.close)
        dialog.current_key = 'stores'
        dialog._loading = True
        dialog._refresh_category_list(select_key='stores')
        dialog._refresh_department_list(select_dept_id='D')
        dialog._load_category('stores')
        dialog._loading = False
        return dialog

    def test_copy_paste_uses_real_schedule_editor_and_generates_two_independent_runs(self):
        cfg = config()
        before = deepcopy(cfg)
        saved_configs = []
        parent = self.dialog(cfg, saved_configs.append)
        seen = []

        def edit_schedule(editor):
            seen.append(deepcopy(editor.base_category))
            editor.scheduled_times = ['00:02']
            editor.accept()
            return QDialog.Accepted

        def manage(dialog):
            dialog.copy_selected()
            dialog.paste_group()
            dialog.accept()
            return QDialog.Accepted

        with patch.object(ConfiguredGroupEditorDialog, 'exec', new=manage), patch.object(
                BulkDepartmentTaskGenerationDialog, 'exec', new=edit_schedule), patch.object(QMessageBox, 'critical') as critical:
            parent.edit_configured_department_group()
        critical.assert_not_called()
        self.assertEqual(1, len(seen))
        self.assertEqual(['00:01'], seen[0]['scheduled_times'])
        category = parent.config['categories']['stores']
        self.assertEqual(2, len(category['department_groups']))
        self.assertIn('Schedule: 00:02', parent._configured_group_label(category['department_groups'][1]))
        # Switching departments and categories must not overwrite independent runs.
        parent.department_list.setCurrentRow(1)
        for index in range(parent.category_list.count()):
            if parent.category_list.item(index).data(Qt.UserRole) == 'catering':
                parent.category_list.setCurrentRow(index)
                break
        for index in range(parent.category_list.count()):
            if parent.category_list.item(index).data(Qt.UserRole) == 'stores':
                parent.category_list.setCurrentRow(index)
                break
        saved = deepcopy(cfg)
        saved['task_generation'] = deepcopy(parent.config)
        records = Simulation(saved).task_generation_manager.update_until(121)
        self.assertEqual([60, 60, 120, 120], sorted(record.task.release_time for record in records))
        self.assertEqual(before, cfg)
        self.assertEqual([1, 2], category['department_groups'][1]['payload']['extension']['nested'])
        with patch.object(QMessageBox, 'critical') as critical:
            parent.accept()
        critical.assert_not_called()
        self.assertEqual(1, len(saved_configs))
        saved['task_generation'] = saved_configs[0]
        records = Simulation(saved).task_generation_manager.update_until(121)
        self.assertEqual([60, 60, 120, 120], sorted(record.task.release_time for record in records))
        self.assertEqual(before, cfg)

    def test_cancel_manager_and_cancel_main_dialog_preserve_original_configuration(self):
        cfg = config()
        parent = self.dialog(cfg)
        before = deepcopy(parent.config)
        on_save = parent.on_save

        def cancel(dialog):
            dialog.copy_selected()
            with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes):
                dialog.delete_selected()
            dialog.reject()
            return QDialog.Rejected

        with patch.object(ConfiguredGroupEditorDialog, 'exec', new=cancel):
            parent.edit_configured_department_group()
        self.assertEqual(before, parent.config)
        parent.reject()
        on_save.assert_not_called()

    def test_delete_last_group_survives_main_save_without_recreated_overrides(self):
        cfg = config()
        cfg['task_generation']['categories']['stores']['enabled'] = False
        saved = []
        parent = self.dialog(cfg, saved.append)

        def delete(dialog):
            with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes):
                dialog.delete_selected()
            dialog.accept()
            return QDialog.Accepted

        with patch.object(ConfiguredGroupEditorDialog, 'exec', new=delete):
            parent.edit_configured_department_group()
        parent.accept()
        category = saved[0]['categories']['stores']
        self.assertEqual([], category['department_groups'])
        self.assertEqual({}, category['departments'])
        updated = deepcopy(cfg)
        updated['task_generation'] = saved[0]
        self.assertEqual([], Simulation(updated).task_generation_manager.update_until(121))

    def test_unchanged_save_keeps_groups_but_real_department_edits_still_apply(self):
        parent = self.dialog(config())
        before = deepcopy(parent.config['categories']['stores']['department_groups'])
        parent._store_current_category()
        self.assertEqual(before, parent.config['categories']['stores']['department_groups'])
        parent.priority_edit.setText('99')
        parent._store_current_category()
        category = parent.config['categories']['stores']
        self.assertEqual(99, category['departments']['D']['priority'])
        self.assertTrue(all('D' not in group['departments'] for group in category['department_groups']))

    def test_manager_can_paste_after_all_groups_have_been_removed(self):
        source_group = config()['task_generation']['categories']['stores']['department_groups'][0]
        source = ConfiguredGroupEditorDialog(None, {source_group['id']: source_group}, label, lambda group: group, 'stores')
        source.copy_selected()
        source.reject()
        source.deleteLater()
        cfg = config()
        cfg['task_generation']['categories']['stores']['department_groups'] = []
        cfg['task_generation']['categories']['stores']['departments'] = {}
        cfg['task_generation']['categories']['stores']['enabled'] = False
        parent = self.dialog(cfg)

        def edit(editor):
            editor.scheduled_times = ['00:03']
            editor.accept()
            return QDialog.Accepted

        def manage(dialog):
            self.assertTrue(dialog.paste_button.isEnabled())
            dialog.paste_group()
            dialog.accept()
            return QDialog.Accepted

        with patch.object(ConfiguredGroupEditorDialog, 'exec', new=manage), patch.object(
                BulkDepartmentTaskGenerationDialog, 'exec', new=edit):
            parent.edit_configured_department_group()
        self.assertEqual(['00:03'], parent.config['categories']['stores']['department_groups'][0]['payload']['scheduled_times'])


class ScheduleUndoRedoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests import test_corridor_editing as editing
        editing.CorridorEditingUiTests.setUpClass.__func__(cls)

    def setUp(self):
        from tests import test_corridor_editing as editing
        editing.CorridorEditingUiTests.setUp(self)

    def tearDown(self):
        QApplication.clipboard().clear()
        from tests import test_corridor_editing as editing
        editing.CorridorEditingUiTests.tearDown(self)

    def test_schedule_copy_is_undoable_and_survives_project_reopen(self):
        from models import JsonStore
        from amr_project import Project
        from PySide6.QtWidgets import QFileDialog
        self.editor.store = JsonStore(config())
        self.editor._reset_edit_history()
        before = deepcopy(self.editor.store.data)

        def edit_schedule(dialog):
            dialog.scheduled_times = ['00:02']
            dialog.accept()
            return QDialog.Accepted

        def manage(dialog):
            dialog.copy_selected()
            dialog.paste_group()
            dialog.accept()
            return QDialog.Accepted

        def save_outer(dialog):
            dialog.current_key = 'stores'
            dialog._loading = True
            dialog._refresh_category_list(select_key='stores')
            dialog._refresh_department_list(select_dept_id='D')
            dialog._load_category('stores')
            dialog._loading = False
            dialog.edit_configured_department_group()
            dialog.accept()
            return QDialog.Accepted

        with patch('app.TaskGenerationSettingsDialog.exec', new=save_outer), patch.object(
                ConfiguredGroupEditorDialog, 'exec', new=manage), patch(
                'dialogs.BulkDepartmentTaskGenerationDialog.exec', new=edit_schedule), patch.object(QMessageBox, 'critical') as critical:
            self.editor.manage_task_generation()
        critical.assert_not_called()
        after = deepcopy(self.editor.store.data)
        self.assertEqual(2, len(after['task_generation']['categories']['stores']['department_groups']))
        self.assertTrue(self.editor.undo_edit())
        self.assertEqual(before, self.editor.store.data)
        self.assertTrue(self.editor.redo_edit())
        self.assertEqual(after, self.editor.store.data)
        target = Path(self.temp.name) / 'copied-schedules.amrproj'
        with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(target), '')):
            self.assertTrue(self.editor.save_project(save_as=True))
        self.assertEqual(after, Project.open(target).configuration())


if __name__ == '__main__':
    unittest.main()
