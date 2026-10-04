"""Workspace preferences persist independently of project/revision state."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from tests import test_corridor_editing as editing
from PySide6.QtCore import QCoreApplication, QEvent, QSettings
from visualiser.workspace_preferences import KEY, WorkspacePreferences, validate


class WorkspacePreferenceTests(unittest.TestCase):
    setUpClass = classmethod(editing.CorridorEditingUiTests.setUpClass.__func__)
    setUp = editing.CorridorEditingUiTests.setUp
    tearDown = editing.CorridorEditingUiTests.tearDown

    def preferences(self):
        settings = QSettings(str(Path(self.temp.name)/'workspace.ini'), QSettings.IniFormat)
        self.editor.workspace_preferences = WorkspacePreferences(self.editor,settings)
        return settings

    def test_preferences_survive_new_editor_without_affecting_project_or_history(self):
        settings = self.preferences()
        before = deepcopy(self.editor.store.data)
        history = deepcopy(self.editor.edit_history.entries)
        workspace = self.editor.workspace
        workspace.set_project_tree_visible(False)
        workspace.set_ribbon_visible(True)
        workspace.set_properties_visible(True)
        self.editor.object_label_mode.setCurrentIndex(2)
        self.editor.show_labels_check.setChecked(False)
        workspace.set_canvas_focus(True)
        saved = json.loads(settings.value(KEY))
        self.assertFalse(saved['project_tree'])
        self.assertTrue(saved['layout_properties'])
        self.assertNotIn('canvas_focus', saved)
        self.assertEqual(before,self.editor.store.data)
        self.assertEqual(history,self.editor.edit_history.entries)
        other = editing.AMRGraphEditor()
        try:
            other.workspace_preferences = WorkspacePreferences(other,QSettings(settings.fileName(),QSettings.IniFormat))
            self.assertFalse(other.workspace._project_tree_open)
            self.assertTrue(other.workspace._layout_properties_open)
            self.assertTrue(other.workspace._ribbon_open)
            self.assertFalse(other.workspace._canvas_focus)
            self.assertEqual('selected',other.object_label_mode.currentData())
            self.assertFalse(other.show_labels_check.isChecked())
            self.assertFalse(other.has_unsaved_changes())
        finally:
            with patch.object(other,'_confirm_unsaved_changes',return_value=True):
                other.close()
            other.deleteLater()
            QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)

    def test_invalid_settings_remain_untouched_until_view_preference_changes(self):
        settings = self.preferences()
        settings.setValue(KEY,'{broken')
        self.editor.workspace_preferences = WorkspacePreferences(self.editor,settings)
        self.assertIn('could not be read',self.editor.workspace_preferences.warning)
        self.editor.workspace._sync_panels()
        self.assertEqual('{broken',settings.value(KEY))
        self.editor.show_labels_check.setChecked(False)
        saved = validate(json.loads(settings.value(KEY)))
        self.assertFalse(saved['show_names'])

    def test_strict_validation_rejects_unknown_modes_versions_and_boolean_strings(self):
        value = json.loads(self.editor.workspace_preferences.snapshot())
        for key, invalid in [('version',True),('version',2),('name_mode','bad'),('project_tree','false')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate(dict(value,**{key:invalid}))

    def test_in_memory_mode_does_not_require_user_settings(self):
        self.assertIsNone(self.editor.workspace_preferences.settings)
        self.editor.workspace.set_project_tree_visible(False)
        self.assertFalse(self.editor.workspace._project_tree_open)

    def test_failed_preference_write_retains_previous_value_and_session_view(self):
        original = self.editor.workspace_preferences.snapshot()
        class FailingSettings:
            raw = original
            def value(self, _key, default=None):
                return self.raw
            def setValue(self, _key, value):
                self.raw = value
            def sync(self):
                pass
            def status(self):
                return QSettings.AccessError
        settings = FailingSettings()
        self.editor.workspace_preferences = WorkspacePreferences(self.editor,settings)
        self.editor.show_labels_check.setChecked(False)
        self.assertEqual(original,settings.raw)
        self.assertFalse(self.editor.show_labels_check.isChecked())
        self.assertIn('could not be saved',self.editor.workspace_preferences.warning)

    def test_panel_sizes_restore_and_focus_mode_does_not_replace_them(self):
        settings = self.preferences()
        workspace = self.editor.workspace
        self.editor.resize(1500,920)
        self.editor.show()
        workspace.set_properties_visible(True)
        self.app.processEvents()
        workspace.splitter.setSizes([230,850,330])
        workspace.splitter.splitterMoved.emit(230,1)
        saved = json.loads(settings.value(KEY))
        sizes = workspace.splitter.sizes()
        self.assertEqual(sizes,saved['panel_sizes']['layout'])
        self.assertEqual(sizes[2],saved['property_widths']['layout'])
        workspace.set_canvas_focus(True)
        workspace.splitter.splitterMoved.emit(0,1)
        self.assertEqual(saved,json.loads(settings.value(KEY)))
        other = editing.AMRGraphEditor()
        try:
            other.workspace_preferences = WorkspacePreferences(other,QSettings(settings.fileName(),QSettings.IniFormat))
            other.resize(1500,920)
            other.show()
            self.app.processEvents()
            self.assertEqual(sizes,other.workspace._stage_sizes['layout'])
            restored = other.workspace.splitter.sizes()
            for expected,actual in zip(sizes,restored):
                self.assertAlmostEqual(expected/sum(sizes),actual/sum(restored),delta=.04)
        finally:
            with patch.object(other,'_confirm_unsaved_changes',return_value=True):
                other.close()
            other.deleteLater()
            QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)

    def test_optional_panel_fields_migrate_old_preferences_and_reject_invalid_sizes(self):
        old = json.loads(self.editor.workspace_preferences.snapshot())
        old.pop('panel_sizes')
        old.pop('property_widths')
        self.assertEqual({},validate(old)['panel_sizes'])
        for sizes in ([1,0,2],[1,-2,3],[1,2],[True,300,200],[1,20001,2]):
            with self.subTest(sizes=sizes), self.assertRaises(ValueError):
                validate(dict(old,panel_sizes={'layout':sizes}))
        with self.assertRaises(ValueError):
            validate(dict(old,property_widths={'layout':float('nan')}))

    def test_layout_and_configuration_keep_independent_panel_sizes(self):
        settings = self.preferences()
        workspace = self.editor.workspace
        self.editor.resize(1500,920)
        self.editor.show()
        workspace.set_properties_visible(True)
        self.app.processEvents()
        workspace.splitter.setSizes([200,900,300])
        workspace.splitter.splitterMoved.emit(200,1)
        layout = list(workspace.splitter.sizes())
        workspace.configuration()
        workspace.set_properties_visible(True)
        self.app.processEvents()
        workspace.splitter.setSizes([250,600,550])
        workspace.splitter.splitterMoved.emit(250,1)
        config = list(workspace.splitter.sizes())
        saved = json.loads(settings.value(KEY))
        self.assertEqual(layout,saved['panel_sizes']['layout'])
        self.assertEqual(config,saved['panel_sizes']['configuration'])
        self.assertNotEqual(layout,config)
