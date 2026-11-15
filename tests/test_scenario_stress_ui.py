"""Offscreen checks of stress settings, worker lifecycle and review actions."""
from copy import deepcopy
import contextlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'visualiser'))
from PySide6.QtCore import QEventLoop, QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QAbstractItemView, QStyle, QStyleOptionViewItem
from app import AMRGraphEditor
from models import JsonStore
from dialogs import ScenarioTestingDialog, ScenarioEventDialog
from scenario_stress_panel import ScenarioStressDialog
from amr_scenario_study import create_study, default_settings, evaluate, run_metrics
from amr_project_runs import read_json
from tests.test_scenario_study import config, event, deferred_config


class ScenarioStressUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.editor = AMRGraphEditor()
        self.editor.store = JsonStore(config())
        self.editor.refresh_canvas()
        self.dialog = ScenarioStressDialog(self.editor)
        self.dialog.set_settings(default_settings(self.editor.store.data))
        self.editor.scenario_stress_dialog = self.dialog
        self.addCleanup(self.close_windows)

    def close_windows(self):
        if self.dialog.running():
            self.dialog.process.kill()
            self.dialog.process.waitForFinished(5000)
        self.dialog.close()
        with patch.object(self.editor, '_confirm_unsaved_changes', return_value=True):
            self.editor.close()
        self.editor.deleteLater()
        self.app.processEvents()

    def load_study(self, budget=1):
        path = self.root / 'study.stress.json'
        settings = {**default_settings(self.editor.store.data), 'trial_budget': budget}
        create_study(self.editor.store.data, path, settings)
        with contextlib.redirect_stdout(io.StringIO()):
            state = evaluate(path)
        self.dialog.path = path
        self.dialog.study = state
        self.dialog.set_settings(settings)
        self.dialog.refresh()
        return state

    def test_manual_dialog_preserves_stress_settings_and_launches_entry(self):
        cfg = dict(enabled=False, active_scenario='Normal operation', enhanced_logging=False,
                   scenarios=[], stress_test={'seed': 42})
        dialog = ScenarioTestingDialog(self.editor, cfg, self.editor.store.data)
        dialog.stress_button.click()
        self.assertEqual(QDialog.Accepted, QDialog.result(dialog))
        self.assertTrue(dialog.launch_stress_test)
        self.assertEqual({'seed': 42}, dialog.result['stress_test'])
        dialog.deleteLater()

    def test_settings_persist_through_manual_editor_and_normalization(self):
        self.dialog.seed.setValue(123)
        self.dialog.budget.setValue(8)
        self.dialog.save_settings()
        stored = self.editor.store.scenario_testing()['stress_test']
        self.assertEqual(123, stored['seed'])
        self.assertEqual(8, stored['trial_budget'])
        self.assertEqual(stored, JsonStore(self.editor.store.data).scenario_testing()['stress_test'])

    def test_fresh_setup_only_runs_ticked_assets_and_preserves_them_on_reopen(self):
        self.grouped_assets()
        # The grouping fixture's lifts are UI placeholders, not runnable lifts.
        self.editor.store.data['lifts'] = []
        self.dialog.set_settings({})
        self.assertTrue(all(item.checkState(0) == Qt.Unchecked for item in self.dialog._asset_items.values()))
        self.dialog._asset_items[('amr', 'R2')].setCheckState(0, Qt.Checked)
        self.dialog._asset_items[('amr', 'R3')].setCheckState(0, Qt.Checked)
        settings = self.dialog.settings()
        self.assertEqual([['amr', 'R2'], ['amr', 'R3']], settings['assets'])
        self.assertIn('2 / 5', self.dialog.assets.headerItem().text(0))
        self.dialog.budget.setValue(2)
        path = self.root / 'selected.stress.json'
        with patch('scenario_stress_panel.QFileDialog.getSaveFileName', return_value=(str(path), '')):
            with patch.object(self.dialog, 'start'):
                self.dialog.new_study()
        self.assertEqual(settings['assets'], read_json(path)['settings']['assets'])
        state = evaluate(path)
        self.assertEqual(0, state['coverage']['corridor_trials'])
        for record in state['results'].values():
            for event in record['events']:
                self.assertIn([event['resource_type'], event['resource_ids'][0]], settings['assets'])
        self.dialog.set_settings(self.editor.store.scenario_testing()['stress_test'])
        self.assertEqual(settings['assets'], self.dialog.settings()['assets'])
        self.dialog.clear_assets_button.click()
        self.assertTrue(all(item.checkState(0) == Qt.Unchecked for item in self.dialog._asset_items.values()))

    def test_loaded_timing_precision_survives_display_and_user_edits(self):
        self.editor.store.data['simulation']['end_datetime'] = '2026-01-05T00:00:08'
        settings = default_settings(self.editor.store.data)
        settings['start_step_minutes'] = .0123456789
        settings['durations_minutes'] = [.0123456789, 8 / 60]
        self.dialog.set_settings(settings)
        self.assertEqual(settings, self.dialog.settings())
        self.dialog.spacing.setValue(.02)
        self.dialog.durations.setText('0.01, 0.02')
        changed = self.dialog.settings()
        self.assertEqual(.02, changed['start_step_minutes'])
        self.assertEqual([.01, .02], changed['durations_minutes'])
        self.assertEqual(8 / 60, changed['end_minute'])

    def grouped_assets(self):
        value = config()
        value['amrs'] += [{**deepcopy(value['amrs'][0]), 'id': 'R2'},
                          {**deepcopy(value['amrs'][0]), 'id': 'R3'}]
        value['lifts'] = [dict(id='L1', served_floors=[0, 1]), dict(id='L2', served_floors=[0, 1])]
        value['corridors']['nodes'] = [dict(name='Door', floor=0, x=3, y=4, has_door=True)]
        self.editor.store = JsonStore(value)
        settings = default_settings(self.editor.store.data)
        self.dialog.set_settings(settings)
        return settings

    def test_grouped_assets_round_trip_in_canonical_study_order(self):
        settings = self.grouped_assets()
        settings['assets'] = [['amr', 'R2'], ['corridor_node', 'Door'], ['lift', 'L1']]
        self.dialog.set_settings(settings)
        self.assertEqual(settings, self.dialog.settings())
        self.assertEqual(['Lifts (2)', 'Corridors (1)', 'AMRs (3)', 'Doors (1)'],
                         [group.text(0) for group in self.dialog._asset_groups])
        groups = self.dialog._asset_groups
        self.assertEqual([Qt.PartiallyChecked, Qt.Unchecked, Qt.PartiallyChecked, Qt.Checked],
                         [group.checkState(0) for group in groups])
        self.dialog.save_settings()
        self.assertEqual(settings, self.editor.store.scenario_testing()['stress_test'])
        self.dialog.set_settings(self.editor.store.scenario_testing()['stress_test'])
        self.assertEqual(settings, self.dialog.settings())

    def test_bulk_buttons_apply_to_collapsed_category_and_individual_row(self):
        settings = self.grouped_assets()
        lifts = self.dialog._asset_groups[0]
        lifts.setExpanded(False)
        lifts.setSelected(True)
        robot = self.dialog._asset_items[('amr', 'R2')]
        robot.setSelected(True)
        self.dialog.exclude_assets_button.click()
        excluded = {('lift', 'L1'), ('lift', 'L2'), ('amr', 'R2')}
        self.assertEqual([asset for asset in settings['assets'] if tuple(asset) not in excluded],
                         self.dialog.settings()['assets'])
        self.assertEqual(Qt.Unchecked, lifts.checkState(0))
        self.assertTrue(lifts.isSelected())
        self.assertTrue(robot.isSelected())
        self.assertFalse(self.dialog.exclude_assets_button.isEnabled())
        self.dialog.include_assets_button.click()
        self.assertEqual(settings, self.dialog.settings())
        self.assertFalse(self.dialog.include_assets_button.isEnabled())

    def test_ctrl_shift_selection_and_space_toggle_rows_together(self):
        self.grouped_assets()
        tree = self.dialog.assets
        self.dialog.show()
        self.app.processEvents()
        self.assertEqual(QAbstractItemView.ExtendedSelection, tree.selectionMode())
        robots = [self.dialog._asset_items[('amr', name)] for name in ('R', 'R2', 'R3')]
        tree.scrollToItem(robots[0])
        self.app.processEvents()
        QTest.mouseClick(tree.viewport(), Qt.LeftButton, Qt.NoModifier, tree.visualItemRect(robots[0]).center())
        tree.scrollToItem(robots[2])
        self.app.processEvents()
        QTest.mouseClick(tree.viewport(), Qt.LeftButton, Qt.ShiftModifier, tree.visualItemRect(robots[2]).center())
        lift = self.dialog._asset_items[('lift', 'L1')]
        tree.scrollToItem(lift)
        self.app.processEvents()
        QTest.mouseClick(tree.viewport(), Qt.LeftButton, Qt.ControlModifier, tree.visualItemRect(lift).center())
        self.assertEqual({id(item) for item in robots + [lift]}, {id(item) for item in tree.selectedItems()})
        QTest.keyClick(tree, Qt.Key_Space)
        self.assertTrue(all(item.checkState(0) == Qt.Unchecked for item in robots + [lift]))
        self.assertEqual(Qt.Checked, self.dialog._asset_items[('lift', 'L2')].checkState(0))
        QTest.keyClick(tree, Qt.Key_Space)
        self.assertTrue(all(item.checkState(0) == Qt.Checked for item in robots + [lift]))

    def test_category_checkbox_changes_only_its_category_when_not_selected(self):
        settings = self.grouped_assets()
        robot = self.dialog._asset_items[('amr', 'R')]
        robot.setSelected(True)
        lifts = self.dialog._asset_groups[0]
        lifts.setCheckState(0, Qt.Unchecked)
        self.assertEqual([asset for asset in settings['assets'] if asset[0] != 'lift'],
                         self.dialog.settings()['assets'])
        self.assertEqual(Qt.Checked, robot.checkState(0))
        lifts.setCheckState(0, Qt.Checked)
        self.assertEqual(settings, self.dialog.settings())

    def test_selected_checkbox_toggles_multiple_rows_and_preserves_selection(self):
        self.grouped_assets()
        self.dialog.show()
        self.app.processEvents()
        tree = self.dialog.assets
        selected = [self.dialog._asset_items[asset] for asset in [('lift', 'L1'), ('amr', 'R2')]]
        for item in selected:
            item.setSelected(True)
        index = tree.indexFromItem(selected[0], 0)
        option = QStyleOptionViewItem()
        tree.itemDelegate().initStyleOption(option, index)
        option.rect = tree.visualRect(index)
        checkbox = tree.style().subElementRect(QStyle.SE_ItemViewItemCheckIndicator, option, tree)
        for state in (Qt.Unchecked, Qt.Checked):
            QTest.mouseClick(tree.viewport(), Qt.LeftButton, Qt.NoModifier, checkbox.center())
            self.assertEqual({id(item) for item in selected}, {id(item) for item in tree.selectedItems()})
            self.assertTrue(all(item.checkState(0) == state for item in selected))
            self.assertEqual(Qt.Checked, self.dialog._asset_items[('lift', 'L2')].checkState(0))

    def test_bulk_asset_actions_remain_locked_while_study_runs(self):
        settings = self.grouped_assets()
        self.dialog._asset_groups[0].setSelected(True)
        self.dialog.process = object()
        try:
            self.dialog.refresh()
            self.assertFalse(self.dialog.assets.isEnabled())
            self.assertFalse(self.dialog.include_assets_button.isEnabled())
            self.assertFalse(self.dialog.exclude_assets_button.isEnabled())
            self.dialog.set_selected_assets_checked(Qt.Unchecked)
            self.assertEqual(settings, self.dialog.settings())
        finally:
            self.dialog.process = None
        self.dialog.refresh()
        self.assertTrue(self.dialog.exclude_assets_button.isEnabled())

    def test_reopening_empty_dialog_populates_current_project_assets(self):
        empty = config()
        empty['amrs'] = []
        empty['corridors'] = dict(nodes=[], edges=[])
        self.editor.store = JsonStore(empty)
        self.dialog.set_settings({})
        self.assertEqual(0, self.dialog.assets.topLevelItemCount())
        self.editor.store = JsonStore(config())
        self.editor.show_scenario_stress_test()
        self.app.processEvents()
        self.assertIs(self.dialog, self.editor.scenario_stress_dialog)
        self.assertGreater(self.dialog.assets.topLevelItemCount(), 0)
        self.assertTrue(all(item.checkState(0) == Qt.Unchecked for item in self.dialog._asset_items.values()))

    def test_refresh_added_assets_preserves_exclusions_and_edited_settings(self):
        self.grouped_assets()
        excluded = self.dialog._asset_items[('amr', 'R2')]
        excluded.setCheckState(0, Qt.Unchecked)
        self.dialog.seed.setValue(123)
        self.dialog.durations.setText('1, 2')
        before = self.dialog.settings()
        self.editor.store.data['amrs'].append({**deepcopy(self.editor.store.data['amrs'][0]), 'id': 'R4'})
        excluded.setSelected(True)
        self.dialog.refresh()
        after = self.dialog.settings()
        self.assertEqual(before['assets'], after['assets'])
        self.assertEqual({k: v for k, v in before.items() if k != 'assets'},
                         {k: v for k, v in after.items() if k != 'assets'})
        self.assertTrue(self.dialog._asset_items[('amr', 'R2')].isSelected())

    def test_refresh_recovers_empty_tree_from_current_assets_and_loaded_choices(self):
        settings = self.grouped_assets()
        settings['assets'] = [asset for asset in settings['assets'] if asset != ['amr', 'R2']]
        self.dialog.set_settings(settings)
        self.dialog.assets.clear()
        self.dialog.refresh()
        self.assertGreater(self.dialog.assets.topLevelItemCount(), 0)
        self.assertEqual(settings, self.dialog.settings())

    def test_categories_remain_visible_after_application_theme_polishing(self):
        from appearance import Appearance, AppearanceController
        from ui_theme import install_application_theme, polish_dialog
        palette, font, stylesheet = self.app.palette(), self.app.font(), self.app.styleSheet()
        appearance = self.editor.appearance.value
        self.addCleanup(lambda: setattr(self.editor.appearance, 'value', appearance))
        def restore():
            self.app.setStyleSheet('')
            self.app.setPalette(palette)
            self.app.setFont(font)
            self.app.setStyleSheet(stylesheet)
        self.addCleanup(restore)
        self.grouped_assets()
        install_application_theme(self.app)
        display = AppearanceController(self.app)
        for theme, size in [('Light', 10), ('Dark', 18), ('High contrast', 24)]:
            with self.subTest(theme=theme, font_size=size):
                display.apply(Appearance(theme=theme, font_size=size))
                self.dialog.show()
                polish_dialog(self.dialog)
                self.dialog.show()
                for _ in range(3):
                    self.app.processEvents()
                self.assertEqual(4, self.dialog.assets.topLevelItemCount())
                first = self.dialog.assets.topLevelItem(0)
                rect = self.dialog.assets.visualItemRect(first)
                self.assertGreater(rect.height(), 0)
                self.assertTrue(self.dialog.assets.viewport().rect().intersects(rect))
                self.assertFalse(self.dialog.assets_empty.isVisible())
                self.assertEqual(Qt.Checked, first.checkState(0))
                self.dialog.hide()

    def test_first_open_displays_categories_and_saved_choices_without_reopening(self):
        from appearance import Appearance
        from ui_theme import install_application_theme
        self.grouped_assets()
        saved = default_settings(self.editor.store.data)
        saved['assets'] = [['amr', 'R2'], ['lift', 'L1']]
        self.editor.store.data['scenario_testing']['stress_test'] = saved
        self.dialog.close()
        self.dialog.deleteLater()
        del self.editor.scenario_stress_dialog
        install_application_theme(self.app)
        palette, font, stylesheet = self.app.palette(), self.app.font(), self.app.styleSheet()
        previous_appearance = self.editor.appearance.value
        self.addCleanup(lambda: setattr(self.editor.appearance, 'value', previous_appearance))
        self.addCleanup(lambda: self.app.setStyleSheet(stylesheet))
        self.addCleanup(lambda: self.app.setFont(font))
        self.addCleanup(lambda: self.app.setPalette(palette))
        self.editor.appearance.apply(Appearance(theme='Dark', font_size=14))
        self.editor.show_scenario_stress_test()
        self.dialog = self.editor.scenario_stress_dialog
        for _ in range(5):
            self.app.processEvents()
        self.assertTrue(self.dialog.isVisible())
        self.assertTrue(self.dialog.assets.viewport().isVisible())
        first = self.dialog.assets.topLevelItem(0)
        self.assertGreater(self.dialog.assets.visualItemRect(first).height(), 0)
        self.assertEqual(saved, self.dialog.settings())

    def test_trial_plan_updates_when_corridors_are_unticked(self):
        self.grouped_assets()
        corridor = self.dialog._asset_items[('corridor', 'A -> B')]
        corridor.setCheckState(0, Qt.Unchecked)
        self.app.processEvents()
        self.assertIn('0 individual corridor tests', self.dialog.trial_plan.text())
        self.assertEqual('selected', self.dialog.settings()['corridor_sweep_scope'])
        self.dialog.corridor_scope.setCurrentIndex(self.dialog.corridor_scope.findData('all'))
        self.app.processEvents()
        self.assertIn('1 individual corridor tests', self.dialog.trial_plan.text())

    def test_dated_events_remain_editable_and_can_switch_to_daily(self):
        seed = event(end=600)
        dialog = ScenarioEventDialog(self.editor, {'corridor': ['A -> B']}, seed)
        dialog.accept()
        self.assertEqual(seed['start_datetime'], dialog.result['start_datetime'])
        self.assertEqual(seed['end_datetime'], dialog.result['end_datetime'])
        dialog.dated_check.setChecked(False)
        dialog.accept()
        self.assertNotIn('start_datetime', dialog.result)
        dialog.deleteLater()

    def test_saved_physical_blockage_can_edit_reverse_authored_edge(self):
        dialog = ScenarioEventDialog(self.editor, {'corridor': ['B -> A']}, event())
        dialog.accept()
        self.assertEqual(['B -> A'], dialog.result['resource_ids'])
        self.assertIn('start_datetime', dialog.result)
        dialog.deleteLater()

    def test_results_corridor_highlight_and_save_unique_editable_scenario(self):
        state = self.load_study()
        self.assertEqual(len(state['results']), self.dialog.results.rowCount())
        self.assertEqual(1, self.dialog.corridors.rowCount())
        self.dialog.corridors.setCurrentCell(0, 0)
        self.assertEqual({('A', 'B')}, self.editor.selected_edge_keys)
        selected = self.dialog.selected_trial()
        self.dialog.save_scenario()
        saved = self.editor.store.scenario_testing()['scenarios'][-1]
        for original, stored in zip(selected['events'], saved['events']):
            self.assertTrue(all(stored[key] == value for key, value in original.items()))
        self.assertIn('start_datetime', saved['events'][0])
        first = self.editor.save_stress_scenario(saved['events'], 'Example')
        second = self.editor.save_stress_scenario(saved['events'], 'Example')
        self.assertNotEqual(first, second)
        self.assertFalse(self.editor.store.scenario_testing()['enabled'])

    def test_investigation_and_playback_use_selected_evidence(self):
        self.load_study()
        record = self.dialog.selected_trial()
        with patch.object(self.editor, 'show_results_investigation'):
            from types import SimpleNamespace
            accepted = []
            self.editor.results_panel = SimpleNamespace(load=accepted.append)
            self.dialog.investigate()
            self.assertEqual([record['directory']], accepted)
            del self.editor.results_panel
        with patch.object(self.editor, 'show_project_playback'):
            from types import SimpleNamespace
            loaded = []
            self.editor.playback_panel = SimpleNamespace(load=loaded.append)
            self.dialog.playback()
            self.assertEqual([record['directory']], loaded)
            self.assertIsNotNone(self.editor.playback_panel._study_context)
            del self.editor.playback_panel

    def test_reused_normal_run_supports_review_and_shows_original_evidence(self):
        from amr_project import Project
        from amr_project_runs import PreparedRun, execute
        from visualiser.project_checks import check_project
        project = Project()
        project.save(self.root / 'design.amrproj', self.editor.store.data)
        self.editor.project = project
        draft = PreparedRun(project, project.results_root())
        report = check_project(draft.config)
        report.acknowledge_warnings()
        directory = draft.commit(report)
        with contextlib.redirect_stdout(io.StringIO()):
            execute(directory)
        self.dialog.path = self.root / 'reused.stress.json'
        create_study(self.editor.store.data, self.dialog.path, {'trial_budget': 1}, project=project)
        self.dialog.study = evaluate(self.dialog.path)
        self.dialog.refresh()
        row = self.dialog._trial_rows.index('baseline')
        self.dialog.results.setCurrentCell(row, 0)
        record = self.dialog.verified_selected()
        self.assertTrue(record['reused'])
        self.assertIn(str(directory), self.dialog.details.toPlainText())
        from types import SimpleNamespace
        loaded = []
        self.editor.playback_panel = SimpleNamespace(load=loaded.append)
        with patch.object(self.editor, 'show_project_playback'):
            self.dialog.playback()
        self.assertEqual([str(directory)], loaded)
        self.assertEqual(project.project_id, self.editor.playback_panel._study_context.project_id)
        del self.editor.playback_panel

    def test_worker_runs_off_ui_thread_and_locks_project(self):
        settings = {**default_settings(self.editor.store.data), 'trial_budget': 2}
        self.dialog.set_settings(settings)
        with patch('scenario_stress_panel.QFileDialog.getSaveFileName',
                   return_value=(str(self.root / 'worker.stress.json'), '')):
            self.dialog.new_button.click()
        self.assertTrue(self.dialog.running())
        self.assertTrue(self.editor.project_editing_locked())
        loop = QEventLoop()
        timer = QTimer()
        timer.setInterval(20)
        timer.timeout.connect(lambda: loop.quit() if not self.dialog.running() else None)
        timer.start()
        QTimer.singleShot(25000, loop.quit)
        loop.exec()
        timer.stop()
        self.assertFalse(self.dialog.running(), self.dialog._output)
        self.assertEqual('complete', self.dialog.study['status'], self.dialog.status.text())
        self.assertFalse(self.editor.project_editing_locked())
        self.assertEqual(100, self.dialog.progress.value())

    def test_baseline_progress_is_visible_when_overall_rounds_to_zero(self):
        self.dialog.study = {'horizon_sec': 1000}
        self.dialog.accept_progress(dict(type='progress', phase='Evaluating baseline and measuring memory',
            fraction=.00004, completed_trials=0, total_trials=905, requested_workers=8,
            ram_bytes=100000000, ram_limit_bytes=16000000000, available_ram_bytes=30000000000,
            reserve_ram_bytes=8000000000, workers=[dict(id='baseline', name='Normal operation',
                phase='Running simulation', elapsed_sec=20, memory_bytes=80000000, sim_time_sec=40,
                horizon_sec=1000, completed=10, failed=0, pending=2)]))
        self.assertEqual(0, self.dialog.progress.value())
        self.assertEqual(40, self.dialog.trial_progress.value())
        self.assertIn('4.0%', self.dialog.trial_progress.format())
        self.assertIn('Normal-operation baseline: Running simulation', self.dialog.status.text())
        self.assertIn('One worker', self.dialog.phase_label.text())
        self.assertIn('Completed: 10', self.dialog.phase_label.text())

    def test_baseline_failure_opens_results_with_actionable_evidence(self):
        self.editor.store = JsonStore(deferred_config())
        settings = default_settings(self.editor.store.data)
        self.dialog.path = self.root / 'failed-baseline.stress.json'
        self.dialog.study = create_study(self.editor.store.data, self.dialog.path, settings)
        self.dialog.set_settings(settings)
        self.dialog.start()
        loop = QEventLoop()
        timer = QTimer()
        timer.setInterval(20)
        timer.timeout.connect(lambda: loop.quit() if not self.dialog.running() else None)
        timer.start()
        QTimer.singleShot(25000, loop.quit)
        loop.exec()
        timer.stop()
        self.assertFalse(self.dialog.running(), self.dialog._output)
        self.assertEqual('failed', self.dialog.study['status'])
        self.assertEqual(['baseline'], list(self.dialog.study['results']))
        self.assertIn('1 failed tasks', self.dialog.status.text())
        self.assertIn('assignment deferral limit', self.dialog.status.text())
        self.assertIn('Investigate trial', self.dialog.status.text())
        self.assertEqual(2, self.dialog.tabs.currentIndex())
        self.assertEqual('baseline', self.dialog.selected_trial()['id'])
        self.assertTrue(self.dialog.investigate_button.isEnabled())
        self.assertFalse(self.editor.project_editing_locked())

    def test_stop_retains_evidence_and_resume_rejects_changed_setup(self):
        settings = {**default_settings(self.editor.store.data), 'trial_budget': 50}
        self.dialog.path = self.root / 'cancel.stress.json'
        self.dialog.study = create_study(self.editor.store.data, self.dialog.path, settings)
        self.dialog.set_settings(settings)
        self.dialog.start()
        loop = QEventLoop()
        timer = QTimer()
        timer.setInterval(50)
        def tick():
            if not self.dialog.running():
                loop.quit()
            elif len(read_json(self.dialog.path)['results']) >= 2:
                self.dialog.cancel()
        timer.timeout.connect(tick)
        timer.start()
        QTimer.singleShot(25000, loop.quit)
        loop.exec()
        timer.stop()
        self.assertFalse(self.dialog.running())
        self.assertEqual('cancelled', self.dialog.study['status'])
        self.assertGreaterEqual(len(self.dialog.study['results']), 2)
        self.dialog.seed.setValue(99)
        self.dialog.start()
        self.assertFalse(self.dialog.running())
        self.assertIn('Setup differs', self.dialog.status.text())


if __name__ == '__main__':
    unittest.main()
