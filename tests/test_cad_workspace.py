"""Graph-first shell, explicit properties and retained panel/draft state."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtGui import QFont
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidget
from tests import test_corridor_editing as editing


class CadWorkspaceTests(unittest.TestCase):
    setUpClass = classmethod(editing.CorridorEditingUiTests.setUpClass.__func__)
    setUp = editing.CorridorEditingUiTests.setUp

    def tearDown(self):
        editing.CorridorEditingUiTests.tearDown(self)
        self.app.processEvents()

    def show(self, width=1400, height=900):
        self.editor.resize(width, height)
        self.editor.show()
        self.app.processEvents()

    def test_graph_is_majority_default_at_small_and_large_text_sizes(self):
        for size in (9, 18):
            for width, height in ((1024, 768), (1600, 1000)):
                with self.subTest(font=size, width=width):
                    font = QFont(self.editor.font())
                    font.setPointSize(size)
                    self.editor.setFont(font)
                    self.show(width, height)
                    workspace = self.editor.workspace
                    self.assertTrue(workspace.properties.isHidden())
                    self.assertTrue(self.editor.ribbon_tabs.isHidden())
                    viewport = self.editor.canvas.viewport()
                    self.assertGreater(viewport.width()*viewport.height(),
                                       self.editor.width()*self.editor.height()*.5)
                    self.assertTrue(self.editor.cad_toolbar.isVisible())

    def test_select_only_highlights_until_properties_requested(self):
        self.show()
        self.editor.workspace.select_object(('point', 'A'))
        self.assertEqual({'A'}, self.editor.selected_point_names)
        self.assertTrue(self.editor.properties_panel.isHidden())
        self.editor.cad_toolbar.properties_action.trigger()
        self.assertFalse(self.editor.properties_panel.isHidden())
        self.assertEqual(('points', ('A',)), self.editor.properties_panel.target)
        self.editor.cad_toolbar.properties_action.trigger()
        self.editor.workspace.select_object(('point', 'Door'))
        self.assertTrue(self.editor.properties_panel.isHidden())

    def test_collapsing_properties_retains_unapplied_draft_and_recovery(self):
        self.show()
        self.editor.workspace.select_object(('point', 'A'))
        self.editor.workspace.set_properties_visible(True)
        panel = self.editor.properties_panel
        panel.fields['x'].setText('1.25')
        expected_recovery = deepcopy(panel.recovery_config())
        original = deepcopy(self.editor.store.data)
        self.editor.workspace.set_properties_visible(False)
        self.editor.workspace.select_object(('point', 'Door'))
        self.editor.workspace.set_canvas_focus(True)
        self.editor.workspace.set_canvas_focus(False)
        self.assertTrue(panel.pending)
        self.assertEqual('1.25', panel.fields['x'].text())
        self.assertEqual(original, self.editor.store.data)
        self.assertEqual(expected_recovery, panel.recovery_config())
        self.editor.workspace.set_properties_visible(True)
        self.assertEqual(('points', ('A',)), panel.target)
        self.assertIn('Draft retained', panel.note.text())

    def test_stale_draft_is_not_applied_when_panels_or_stages_change(self):
        self.show()
        workspace = self.editor.workspace
        workspace.select_object(('point', 'A'))
        workspace.set_properties_visible(True)
        panel = workspace.properties
        panel.fields['x'].setText('2.5')
        self.editor.store.data['locations'][0]['y'] = 3
        original = deepcopy(self.editor.store.data)
        workspace.set_properties_visible(False)
        workspace.configuration()
        workspace.show_page('layout', self.editor.canvas)
        workspace.set_properties_visible(True)
        self.assertTrue(panel.pending)
        self.assertIn('project changed', panel.note.text())
        self.assertEqual(original, self.editor.store.data)
        self.assertEqual('2.5', panel.fields['x'].text())

    def test_stage_navigation_restores_manual_layout_sizes_and_collapsed_state(self):
        self.show()
        workspace = self.editor.workspace
        workspace.set_properties_visible(True)
        workspace.splitter.setSizes([220, 760, 330])
        expected = workspace.splitter.sizes()
        workspace.show_page('layout', self.editor.canvas)
        self.assertEqual(expected, workspace.splitter.sizes())
        workspace.configuration()
        workspace.show_page('layout', self.editor.canvas)
        self.assertEqual(expected, workspace.splitter.sizes())
        workspace.set_properties_visible(False)
        workspace.configuration()
        workspace.select_object(('point', 'A'))
        self.assertTrue(workspace.properties.isHidden())

    def test_focus_restores_panel_visibility_and_widths(self):
        self.show()
        workspace = self.editor.workspace
        workspace.set_ribbon_visible(True)
        workspace.set_properties_visible(True)
        workspace.splitter.setSizes([210, 800, 300])
        self.app.processEvents()
        previous = workspace.splitter.sizes()
        self.editor.cad_toolbar.focus_action.trigger()
        self.assertTrue(workspace.sidebar.isHidden())
        self.assertTrue(workspace.properties.isHidden())
        self.assertTrue(self.editor.ribbon_tabs.isHidden())
        self.editor.cad_toolbar.focus_action.trigger()
        self.assertFalse(workspace.sidebar.isHidden())
        self.assertFalse(workspace.properties.isHidden())
        self.assertFalse(self.editor.ribbon_tabs.isHidden())
        self.assertEqual(previous, workspace.splitter.sizes())

    def test_compact_commands_share_mode_floor_and_history_state(self):
        toolbar = self.editor.cad_toolbar
        for mode, action in toolbar.mode_actions.items():
            action.trigger()
            self.assertEqual(mode, self.editor.mode_combo.currentData())
            self.assertTrue(action.isChecked())
        self.editor.mode_combo.setCurrentIndex(self.editor.mode_combo.findData('pan'))
        self.assertFalse(any(action.isChecked() for action in toolbar.mode_actions.values()))
        self.editor.mode_combo.setCurrentIndex(self.editor.mode_combo.findData('corridor_draw'))
        self.assertTrue(toolbar.mode_actions['corridor_draw'].isChecked())
        self.assertIn(self.editor.undo_action, self.editor.workbench.workflow.actions())
        self.assertIn(self.editor.redo_action, self.editor.workbench.workflow.actions())
        self.assertIs(toolbar.widgetForAction(next(action for action in toolbar.actions()
            if toolbar.widgetForAction(action) is self.editor.floor_spin)), self.editor.floor_spin)
        toolbar.more_action.trigger()
        self.assertFalse(self.editor.ribbon_tabs.isHidden())
        self.assertTrue(toolbar.more_action.isChecked())
        toolbar.project_action.trigger()
        self.assertTrue(self.editor.workspace.sidebar.isHidden())
        self.assertFalse(toolbar.project_action.isChecked())

    def test_focus_can_be_exited_after_navigating_to_another_stage(self):
        self.show()
        workspace = self.editor.workspace
        workspace.set_canvas_focus(True)
        workspace.configuration()
        self.assertTrue(self.editor.cad_toolbar.focus_action.isEnabled())
        self.editor.cad_toolbar.focus_action.trigger()
        self.assertFalse(workspace._canvas_focus)
        self.assertFalse(workspace.sidebar.isHidden())

    def test_snap_overflow_action_and_full_tools_checkbox_share_state(self):
        self.show(800, 600)
        font = QFont(self.editor.font())
        font.setPointSize(18)
        self.editor.setFont(font)
        toolbar = self.editor.cad_toolbar
        self.assertIn(toolbar.snap_action, toolbar.actions())
        self.assertTrue(toolbar.snap_action.isCheckable())
        toolbar.snap_action.trigger()
        self.assertFalse(self.editor.snap_check.isChecked())
        self.editor.snap_check.setChecked(True)
        self.assertTrue(toolbar.snap_action.isChecked())
        self.assertIsNot(toolbar.widgetForAction(toolbar.snap_action), self.editor.snap_check)

    def test_drawing_input_cannot_commit_outside_layout(self):
        self.show()
        editor = self.editor
        editor._set_edit_mode('corridor_draw')
        entry = editor.cad_drawing_input
        self.assertFalse(entry.isHidden())
        for stage in ('configuration', 'checks'):
            with self.subTest(stage=stage):
                if stage == 'configuration':
                    editor.workspace.configuration()
                else:
                    editor.workspace.show_page('checks', QWidget(editor.workspace))
                self.app.processEvents()
                self.assertTrue(entry.isHidden())
                self.assertFalse(entry.isEnabled())
                self.assertFalse(editor.finish_route_enter_action.isEnabled())
                before = deepcopy(editor.store.data)
                entry.coordinate_edit.setText('40,40')
                QTest.keyClick(entry.coordinate_edit, Qt.Key_Return)
                self.assertFalse(editor.submit_corridor_coordinate())
                self.assertEqual(before, editor.store.data)
        editor.workspace.show_page('layout', editor.canvas)
        self.assertFalse(entry.isHidden())
        self.assertTrue(entry.isEnabled())
        self.assertTrue(editor.finish_route_enter_action.isEnabled())

    def test_check_command_does_not_run_checks_on_selection(self):
        with patch.object(self.editor, 'show_project_checks') as checks:
            self.editor.workspace.select_object(('point', 'A'))
            self.editor.workspace.refresh()
            checks.assert_not_called()
        self.assertTrue(self.editor.cad_toolbar.check_action.toolTip())


if __name__ == '__main__':
    unittest.main()
