"""Approved A2 shell: real workflow controls around a dominant drawing canvas."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtGui import QKeySequence
from tests import test_corridor_editing as editing


class CadConceptShellTests(unittest.TestCase):
    setUpClass = classmethod(editing.CorridorEditingUiTests.setUpClass.__func__)

    def setUp(self):
        editing.CorridorEditingUiTests.setUp(self)
        self.appearance_before = self.editor.appearance.value
        self.editor.resize(1500, 920)
        self.editor.show()
        self.app.processEvents()

    def tearDown(self):
        if self.editor.appearance.value != self.appearance_before:
            self.editor.appearance.apply(self.appearance_before)
        editing.CorridorEditingUiTests.tearDown(self)
        self.app.processEvents()

    def test_real_stage_controls_have_icons_and_share_workspace_navigation(self):
        workbench = self.editor.workbench
        self.assertEqual(['project', 'layout', 'configuration', 'checks', 'simulate', 'review', 'report'],
                         list(workbench.stages))
        self.assertTrue(workbench.stages['layout'].isChecked())
        self.assertTrue(all(not action.icon().isNull() for action in workbench.stages.values()))
        workbench.stages['configuration'].trigger()
        self.assertEqual('configuration', self.editor.workspace.stage)
        self.assertTrue(workbench.stages['configuration'].isChecked())
        self.assertFalse(workbench.stages['layout'].isChecked())
        workbench.stages['layout'].trigger()
        self.assertEqual('layout', self.editor.workspace.stage)
        self.assertTrue(self.editor.properties_panel.isHidden())
        for stage, method in [('simulate', 'show_project_runs'), ('review', 'show_results_investigation'),
                              ('report', 'show_project_report')]:
            with patch.object(self.editor, method) as handler:
                workbench.stages[stage].trigger()
                handler.assert_called_once_with()

    def test_menus_use_actual_shared_actions_and_standard_file_shortcuts(self):
        workbench = self.editor.workbench
        self.assertEqual(['&File', '&Edit', '&View', '&Help'],
                         [action.text() for action in self.editor.menuBar().actions()])
        self.assertIn(workbench.save_action, workbench.file_menu.actions())
        self.assertIn(self.editor.undo_action, workbench.edit_menu.actions())
        self.assertIn(self.editor.redo_action, workbench.edit_menu.actions())
        self.assertIn(self.editor.cad_toolbar.focus_action, workbench.view_menu.actions())
        self.assertEqual(QKeySequence.Save, workbench.save_action.shortcut())
        self.assertEqual(QKeySequence.Open, workbench.open_action.shortcut())
        self.assertNotIn(self.editor.undo_action, self.editor.cad_toolbar.actions())
        self.assertTrue(all(not a.icon().isNull() for a in self.editor.cad_toolbar.mode_actions.values()))
        self.editor.undo_action.setText('Undo: a deliberately long corridor editing operation')
        self.assertEqual('Undo', workbench.workflow.widgetForAction(self.editor.undo_action).text())
        self.assertIn('long corridor', workbench.workflow.widgetForAction(self.editor.undo_action).toolTip())

    def test_right_properties_tab_is_explicit_and_preserves_drafts(self):
        workspace = self.editor.workspace
        self.assertTrue(workspace.properties_tab.isVisible())
        self.assertTrue(workspace.properties.isHidden())
        workspace.select_object(('point', 'A'))
        self.assertTrue(workspace.properties.isHidden())
        workspace.properties_tab.click()
        workspace.properties.fields['x'].setText('1.75')
        recovery = deepcopy(workspace.properties.recovery_config())
        workspace.properties_tab.click()
        self.assertTrue(workspace.properties.isHidden())
        self.assertTrue(workspace.properties.pending)
        self.assertEqual(recovery, workspace.properties.recovery_config())
        workspace.properties_tab.click()
        self.assertEqual('1.75', workspace.properties.fields['x'].text())

    def test_checks_strip_is_unchecked_then_current_then_stale_without_autorunning(self):
        workbench = self.editor.workbench
        self.assertIn('Not checked', workbench.checks_label.text())
        with patch.object(self.editor, 'show_project_checks') as checks:
            self.editor.workspace.select_object(('point', 'A'))
            workbench.refresh()
            checks.assert_not_called()
        workbench.stages['checks'].trigger()
        self.assertIn('Current', workbench.checks_label.text())
        report = self.editor.checks_panel.report
        self.editor.workspace.show_page('layout', self.editor.canvas)
        self.assertTrue(workbench.checks_strip.isVisible())
        self.editor.store.data['locations'][0]['x'] += 1
        workbench.refresh_checks()
        self.assertIn('Stale', workbench.checks_label.text())
        self.assertIs(report, self.editor.checks_panel.report)
        self.editor.workspace.set_canvas_focus(True)
        self.assertTrue(workbench.checks_strip.isHidden())
        self.assertTrue(self.editor.workspace.properties_rail.isHidden())
        self.editor.workspace.set_canvas_focus(False)
        self.assertTrue(workbench.checks_strip.isVisible())

    def test_quick_theme_and_font_controls_are_validated_personal_preferences(self):
        before = deepcopy(self.editor.store.data)
        workbench = self.editor.workbench
        for theme in ('Dark', 'High contrast', 'Light'):
            workbench.theme.setCurrentText(theme)
            self.assertEqual(theme, self.editor.appearance.value.theme)
            self.assertFalse(workbench.stages['layout'].icon().isNull())
        workbench.text_size.setCurrentIndex(workbench.text_size.findData(14))
        self.assertEqual(14, self.editor.appearance.value.font_size)
        self.assertEqual(before, self.editor.store.data)
        self.assertFalse(self.editor.has_unsaved_changes())

    def test_default_concept_keeps_graph_majority_on_small_screen(self):
        self.editor.resize(1024, 768)
        self.app.processEvents()
        viewport = self.editor.canvas.viewport()
        self.assertGreater(viewport.width()*viewport.height(), self.editor.width()*self.editor.height()*.5)
        self.assertTrue(self.editor.workbench.workflow.isVisible())
        self.assertTrue(self.editor.cad_toolbar.isVisible())
        self.assertTrue(self.editor.workbench.checks_strip.isVisible())
        self.assertTrue(self.editor.show_location_bounds_check.isChecked())
        self.assertTrue(self.editor.ribbon_tabs.isHidden())


if __name__ == '__main__':
    unittest.main()
