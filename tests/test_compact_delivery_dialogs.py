"""Functional safeguards for the three approved compact dialog revisions."""
from copy import deepcopy
import os
from pathlib import Path
import sys
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'visualiser'))
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QDialogButtonBox
from dialogs import DepartmentEditorDialog, SimulationSettingsDialog, TaskGenerationSettingsDialog
from project_setup import NewProjectDialog
from tests.test_generation_reference import grouped_config


class CompactDeliveryDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.widgets = []

    def tearDown(self):
        for widget in reversed(self.widgets):
            widget.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def keep(self, widget):
        self.widgets.append(widget)
        return widget

    def generation(self, saved=None):
        cfg = grouped_config()
        return self.keep(TaskGenerationSettingsDialog(None, cfg['task_generation'],
            ['A', 'B'], ['Box'], [], cfg['departments'], saved.append if saved is not None else lambda _: None))

    def test_conditional_schedule_labels_follow_fields_across_tabs(self):
        dialog = self.generation()
        dialog.mode_combo.setCurrentText('scheduled')
        self.assertTrue(dialog.timeframe_start_edit.isHidden())
        self.assertTrue(dialog.form.labelForField(dialog.timeframe_start_edit).isHidden())
        self.assertFalse(dialog.schedule_widget.isHidden())
        dialog.mode_combo.setCurrentText('timeframe')
        self.assertFalse(dialog.timeframe_start_edit.isHidden())
        self.assertFalse(dialog.form.labelForField(dialog.timeframe_start_edit).isHidden())
        self.assertTrue(dialog.schedule_widget.isHidden())
        self.assertTrue(dialog.form.labelForField(dialog.schedule_widget).isHidden())

    def test_tab_switch_does_not_commit_generation_draft(self):
        saved = []
        dialog = self.generation(saved)
        dialog.display_name_edit.setText('Draft category name')
        for index in range(dialog.delivery_tabs.count()):
            dialog.delivery_tabs.setCurrentIndex(index)
        self.assertEqual('Draft category name', dialog.display_name_edit.text())
        self.assertEqual([], saved)
        dialog.reject()
        self.assertEqual([], saved)
        self.assertEqual(5, len(dialog.department_actions.menu().actions()))

    def test_department_tab_selection_keeps_all_category_drafts_and_parent_save_boundary(self):
        cfg = grouped_config()
        seed = deepcopy(cfg['departments'][0])
        dialog = self.keep(DepartmentEditorDialog(None, ['A', 'B'], [], seed=seed,
            task_generation_categories=[('stores', 'Stores', '-STORES'), ('linen', 'Linen', '-LIN')]))
        original = deepcopy(seed)
        dialog.category_suffix_edits['stores'].setText('-SAVED')
        dialog.category_location_selections['stores'] = ['B']
        dialog.location_category_list.setCurrentRow(1)
        dialog.category_suffix_edits['linen'].setText('-SECOND')
        dialog.delivery_tabs.setCurrentIndex(0)
        dialog.name_edit.setText('Edited ward')
        dialog.accept()
        self.assertEqual('Edited ward', dialog.result['name'])
        self.assertEqual('-SAVED', dialog.result['task_generation_location_suffixes']['stores'])
        self.assertEqual('-SECOND', dialog.result['task_generation_location_suffixes']['linen'])
        self.assertEqual(original, seed)
        self.assertEqual(2, dialog.location_category_pages.count())

    def test_mode_details_toggle_keeps_full_findings_and_precision(self):
        simulation = {'start_datetime': '2026-01-05T00:00:00.123456+02:00',
            'generated_task_release_stagger_sec': .123456789, 'custom': {'source': 'imported'}}
        dialog = self.keep(SimulationSettingsDialog(None, simulation))
        full_text = dialog.mode_preview_text.toPlainText()
        self.assertIn('Original representation is preserved', full_text)
        self.assertTrue(dialog.mode_preview_text.isHidden())
        dialog.mode_details_button.setChecked(True)
        self.assertFalse(dialog.mode_preview_text.isHidden())
        dialog.mode_details_button.setChecked(False)
        self.assertEqual(full_text, dialog.mode_preview_text.toPlainText())
        dialog.accept()
        self.assertEqual(simulation, dialog.result)

    def test_mode_change_diagnostics_remain_complete_when_collapsed(self):
        dialog = self.keep(SimulationSettingsDialog(None, full_config={'amrs': [{'id': 'R'}]}))
        dialog.mode_combo.setCurrentIndex(dialog.mode_combo.findData('detailed'))
        self.assertTrue(dialog.mode_preview_text.isHidden())
        self.assertIn('/simulation/mode', dialog.mode_preview_text.toPlainText())
        self.assertIn('Blocking readiness findings', dialog.mode_preview_text.toPlainText())
        self.assertIn('Needs Project Checks', dialog.mode_readiness_label.text())

    def test_fixed_footers_are_reachable_at_compact_size(self):
        dialogs = [self.generation(), self.keep(DepartmentEditorDialog(None, ['A', 'B'], [])),
            self.keep(SimulationSettingsDialog(None, full_config=grouped_config()))]
        for dialog in dialogs:
            dialog.show()
            self.app.processEvents()
            dialog.setMaximumSize(16777215, 16777215)
            dialog.resize(1024, 768)
            self.app.processEvents()
            for index in range(dialog.delivery_tabs.count()):
                dialog.delivery_tabs.setCurrentIndex(index)
                self.app.processEvents()
                for button in dialog.findChild(QDialogButtonBox).buttons():
                    self.assertTrue(button.isVisible())
                    self.assertTrue(dialog.rect().contains(button.mapTo(dialog, button.rect().bottomRight())))

    def test_new_project_is_explicit_simple(self):
        dialog = self.keep(NewProjectDialog())
        config = dialog.configuration()
        self.assertEqual(('simple', 'legacy'), (config['simulation']['mode'], config['simulation']['motion_model']))
