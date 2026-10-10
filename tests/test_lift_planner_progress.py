"""Real planner clicks report progress, keep UI responsive and retain evidence."""
from copy import deepcopy
from pathlib import Path
import json,tempfile,time
import unittest
from unittest.mock import patch

from tests import test_corridor_editing as editing
from PySide6.QtCore import Qt,QProcess,QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from amr_tutorial_assets import generate_assets
from amr_lift_study import create_study,realize_demand,write_record
from amr_lift_planning_geometry import extract_floor
from lift_planner import LiftPlanner
from models import JsonStore


class LiftPlannerProgressTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        editing.CorridorEditingUiTests.setUpClass.__func__(cls)
        cls.assets=tempfile.TemporaryDirectory()
        cls.config=generate_assets(Path(cls.assets.name))
        cls.requests=realize_demand(cls.config)
        cls.geometry=[extract_floor(r['filepath'],r['floor']) for r in cls.config['floor_dxf_files']]

    @classmethod
    def tearDownClass(cls):cls.assets.cleanup()

    def setUp(self):
        editing.CorridorEditingUiTests.setUp(self)
        self.editor.store=JsonStore(deepcopy(self.config));self.editor.refresh_canvas()
        self.planner=LiftPlanner(self.editor);self.editor.lift_planner=self.planner
        path=Path(self.temp.name)/'study.json'
        with patch('amr_lift_study.realize_demand',return_value=deepcopy(self.requests)):
            state=create_study(self.editor.store.data,path)
        state.update(confirmed=True,geometry=deepcopy(self.geometry),options=self.planner.option_values())
        write_record(path,state);self.planner.study=state;self.planner.path=path;self.planner.geometries=deepcopy(self.geometry)
        self.planner.refresh_state();self.editor.show();self.planner.show();self.app.processEvents()

    def tearDown(self):
        if self.planner.running():self.planner.cancel();self.wait()
        self.planner.close();editing.CorridorEditingUiTests.tearDown(self)

    def wait(self,timeout=20000):
        end=time.monotonic()+timeout/1000
        while self.planner.running() and time.monotonic()<end:QTest.qWait(25)
        self.assertFalse(self.planner.running(),'Planner did not finish within the test timeout.')

    def test_real_generate_click_reports_progress_without_blocking_ui_and_selects_preview(self):
        self.planner.tabs.setCurrentIndex(1);self.app.processEvents()
        before=deepcopy(self.editor.store.data);ticks=[]
        heartbeat=QTimer();heartbeat.setInterval(20);heartbeat.timeout.connect(lambda:ticks.append(1));heartbeat.start()
        QTest.mouseClick(self.planner.generate,Qt.LeftButton)
        self.assertTrue(self.planner.running());self.assertTrue(self.planner.progress.isVisible())
        self.assertIn('Generating',self.planner.progress_label.text())
        self.assertFalse(self.planner.generate.isEnabled());self.assertFalse(self.planner.evaluate.isEnabled())
        self.assertFalse(self.planner.movable['L1'].isEnabled());self.assertTrue(self.planner.stop.isEnabled())
        self.wait();heartbeat.stop()
        self.assertTrue(ticks);self.assertEqual(5,self.planner.proposals.rowCount())
        self.assertEqual(0,self.planner.proposals.currentRow());self.assertTrue(self.planner.proposal_scene.items())
        self.assertEqual(100,self.planner.progress.value());self.assertIn('Generated 5',self.planner.progress_label.text())
        self.assertEqual(before,self.editor.store.data);self.assertTrue(self.planner.generate.isEnabled())
        self.assertEqual(5,len(json.loads(self.planner.path.read_text())['proposals']))

    def test_cancel_generation_retains_previous_study_and_unlocks_controls(self):
        before=deepcopy(self.planner.study)
        self.planner.propose();self.planner.cancel();self.wait()
        self.assertEqual(before,self.planner.study)
        self.assertIn('cancelled',self.planner.progress_label.text())
        self.assertTrue(self.planner.generate.isEnabled());self.assertFalse(self.editor.project_editing_locked())

    def test_generation_failure_is_visible_and_retains_previous_evidence(self):
        before=deepcopy(self.planner.study)
        with patch('lift_proposal_job.generate_sites',side_effect=ValueError('No two aligned sites fit.')):
            self.planner.propose();self.wait()
        self.assertEqual(before,self.planner.study)
        self.assertIn('Proposal generation failed: No two aligned sites fit.',self.planner.progress_label.text())
        self.assertTrue(self.planner.generate.isEnabled())

    def test_real_evaluate_click_shows_start_progress_and_completes_in_worker(self):
        self.planner.study['scenarios']=['normal'];write_record(self.planner.path,self.planner.study)
        QTest.mouseClick(self.planner.evaluate,Qt.LeftButton)
        self.assertTrue(self.planner.running());self.assertTrue(self.planner.progress.isVisible())
        self.assertIn('Starting evaluation',self.planner.progress_label.text())
        self.assertEqual('Evaluating scenarios…',self.planner.evaluate.text())
        self.wait()
        self.assertEqual('complete',self.planner.study['status'])
        self.assertTrue(self.planner.study['baseline_complete']);self.assertEqual(2,self.planner.tabs.currentIndex())
        self.assertIn('Evaluation complete',self.planner.progress_label.text())
        self.assertEqual(100,self.planner.progress.value());self.assertTrue(self.planner.scenarios.rowCount())
        self.assertTrue(self.planner.generate.isEnabled());self.assertFalse(self.editor.project_editing_locked())

    def test_stop_evaluation_unlocks_and_can_resume_the_worker(self):
        self.planner.study['scenarios']=['normal'];write_record(self.planner.path,self.planner.study)
        self.planner.start();QTest.qWait(100);self.planner.cancel();self.wait()
        self.assertEqual('cancelled',self.planner.study['status'])
        self.assertIn('Evaluation stopped',self.planner.progress_label.text())
        self.assertTrue(self.planner.evaluate.isEnabled());self.assertFalse(self.editor.project_editing_locked())
        self.planner.start();self.wait()
        self.assertEqual('complete',self.planner.study['status'])
        self.assertNotIn('error',self.planner.study)

    def test_failed_start_is_reported_even_when_study_never_reaches_running(self):
        self.planner.process=QProcess(self.planner);self.planner._worker_error='Worker executable unavailable.'
        self.planner.evaluation_finished(-1,QProcess.NormalExit)
        self.assertEqual('failed',self.planner.study['status'])
        self.assertIn('Evaluation failed: Worker executable unavailable.',self.planner.progress_label.text())
        self.assertTrue(self.planner.evaluate.isEnabled());self.assertFalse(self.planner.running())

    def test_worker_chunks_update_scenario_progress_and_unterminated_error_is_retained(self):
        self.planner.process=QProcess(self.planner)
        with patch.object(self.planner.process,'readAllStandardOutput',side_effect=[b'2/8: current ',b'- peak\nTraceback: broken']):
            self.planner.read_progress();self.planner.read_progress()
        self.assertIn('Evaluating 2/8: current - peak',self.planner.progress_label.text())
        self.assertEqual(12,self.planner.progress.value())
        self.planner.evaluation_finished(1,QProcess.NormalExit)
        self.assertIn('Evaluation failed: Traceback: broken',self.planner.progress_label.text())


if __name__=='__main__':unittest.main()
