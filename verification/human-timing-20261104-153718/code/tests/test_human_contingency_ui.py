import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'visualiser'))
import tempfile
import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QEventLoop,QTimer
from app import AMRGraphEditor
from models import JsonStore
from contingency_panel import HumanContingencyDialog
from amr_contingency_study import create_study,load_study
from amr_contingency_inputs import default_settings
from tests.test_human_contingency import fixture


class HumanContingencyUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.editor=AMRGraphEditor();self.config,self.settings,_=fixture()
        self.editor.store=JsonStore(self.config);self.editor.refresh_canvas()
        self.dialog=HumanContingencyDialog(self.editor)
        self.editor.human_contingency_dialog=self.dialog
        self.dialog.set_settings(self.settings)
        self.addCleanup(self.close_windows)

    def close_windows(self):
        if self.dialog.running():
            self.dialog.cancel();self.dialog.process.waitForFinished(5000)
        self.dialog.close()
        with patch.object(self.editor,'_confirm_unsaved_changes',return_value=True):self.editor.close()
        self.editor.deleteLater();self.app.processEvents()

    def test_settings_round_trip_and_undo(self):
        self.assertEqual(self.settings,self.dialog.settings())
        self.dialog.save_settings()
        self.assertEqual(self.settings,self.editor.store.data['human_contingency']['settings'])
        self.assertEqual(self.settings,JsonStore(self.editor.store.data).data['human_contingency']['settings'])
        self.editor.undo_action.trigger()
        self.assertNotIn('human_contingency',self.editor.store.data)

    def test_menu_entry_and_non_modal_window(self):
        self.editor.workbench.human_contingency_action.trigger()
        self.assertTrue(self.dialog.isVisible());self.assertFalse(self.dialog.isModal())

    def test_long_validation_keeps_actions_visible_at_enlarged_text(self):
        from PySide6.QtCore import QPoint
        from PySide6.QtWidgets import QScrollArea,QFormLayout,QLabel
        from ui_theme import polish_dialog
        self.dialog.setStyleSheet('* { font-size: 14pt; }')
        self.dialog.resize(1000,700);self.dialog.show();polish_dialog(self.dialog)
        self.dialog.status.setText('\n'.join(f'Service {i}: review carrying assumptions.' for i in range(100)))
        self.app.processEvents()
        self.assertLess(self.dialog.status.height(),150)
        self.assertGreater(self.dialog.status.verticalScrollBar().maximum(),0)
        self.assertFalse(self.dialog.findChild(QScrollArea,'dialogContentScroll'))
        for button in [*self.dialog.controls,self.dialog.stop]:
            point=button.mapTo(self.dialog,QPoint(0,0))
            self.assertTrue(self.dialog.rect().contains(point),button.text())
            self.assertTrue(self.dialog.rect().contains(point+QPoint(button.width()-1,button.height()-1)),button.text())
        for index in (1,2):
            self.assertIsInstance(self.dialog.tabs.widget(index),QScrollArea)
        self.dialog.tabs.setCurrentIndex(1);self.app.processEvents()
        for form in self.dialog.findChildren(QFormLayout):
            for row in range(form.rowCount()):
                item=form.itemAt(row,QFormLayout.LabelRole)
                if item and isinstance(item.widget(),QLabel):
                    self.assertFalse(item.widget().wordWrap())

    def test_count_edit_updates_estimate_and_retains_manual_dimension(self):
        self.dialog.set_settings(default_settings(self.config))
        self.dialog.fields['width_m'].setValue(1.1)
        self.dialog.fields['capacity_count'].setValue(3)
        result=self.dialog.settings()['profiles']['stores']
        self.assertEqual(30,result['capacity_kg'])
        self.assertAlmostEqual(3.6,result['length_m'])
        self.assertEqual(1.1,result['width_m'])

    def test_trial_progress_reports_simulated_time_and_elapsed_time(self):
        self.dialog.show_progress(dict(phase='simulating',variant='dedicated_current',trial=3,budget=20,
            simulated_hours=12,horizon_hours=168,completed=24,elapsed_seconds=4,best_hours=None))
        self.assertIn('trial 3 / 20',self.dialog.status.text())
        self.assertIn('12 / 168 hours',self.dialog.status.text())
        self.assertIn('4 s',self.dialog.status.text())

    def test_background_execution_and_edit_lock(self):
        path=Path(self.temp.name)/'study.json'
        create_study(self.editor.store.data,self.settings,path)
        self.dialog.path=path;self.dialog.run_study()
        self.assertTrue(self.editor.project_editing_locked())
        loop=QEventLoop();self.dialog.process.finished.connect(loop.quit);QTimer.singleShot(20000,loop.quit);loop.exec()
        self.assertFalse(self.dialog.running());self.assertFalse(self.editor.project_editing_locked())
        state=load_study(path)
        self.assertTrue(all(v['best']['passed'] for v in state['variants'].values()))
        self.assertEqual(4,self.dialog.summary.rowCount(),self.dialog.status.text())
        self.assertGreater(self.dialog.roster.rowCount(),0)


if __name__=='__main__':unittest.main()
