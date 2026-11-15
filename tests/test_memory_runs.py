import contextlib
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from threading import Event
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'visualiser'))

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication, QFileDialog, QDialog, QMessageBox
from amr_event_store import iter_events
from amr_memory_runs import MemoryRuns, RunMemoryLimit
from amr_project import Project
from amr_project_report import generate
from amr_project_runs import OUTPUTS, PreparedRun, execute, inspect_run
from amr_recovery import RecoveryStore
from amr_run_exports import ensure_exports
from amr_run_review import verified_events
from app import AMRGraphEditor
from models import JsonStore
from project_checks_panel import RunChecksDialog
from project_playback_panel import load_playback
from results_investigation_panel import load_review
from simulator import Simulation
from tests.test_compact_execution import normalise
from tests.test_engineering_reference import reference_config
from visualiser.project_checks import check_project


def config():
    result = reference_config()
    result['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box')]
    return result


class MemoryRunTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.pool = MemoryRuns()
        self.addCleanup(self.pool.clear)

    def prepare(self, inputs):
        run = self.pool.prepare(inputs, self.root)
        report = check_project(run.config, asset_refs=run.asset_refs)
        report.acknowledge_warnings()
        run.accept_checks(report)
        return run

    def retain(self, inputs):
        run = self.prepare(inputs)
        run.execute(self.pool.reserve(run))
        self.pool.add(run)
        return run

    def test_discard_releases_run_data_after_the_last_reader(self):
        run = self.retain(config())
        self.assertGreater(run.byte_size, 0)
        with run.using_store() as store:
            self.pool.discard(run)
            self.assertFalse(run.released)
            self.assertFalse(store.closed)
        self.assertTrue(store.closed)
        self.assertTrue(run.released)
        self.assertEqual(0, run.byte_size)
        self.assertEqual(0, self.pool.usage())
        self.assertEqual({}, run.assets)
        with self.assertRaises(InterruptedError):
            _ = run.evidence

    def test_review_stays_in_memory_and_publication_matches_disk(self):
        inputs = config()
        run = self.retain(inputs)
        with run.using_store() as store:
            self.assertEqual('', store.connection.execute('PRAGMA database_list').fetchone()[2])
            self.assertEqual(2, store.connection.execute('PRAGMA temp_store').fetchone()[0])
            memory_rows = list(store.iter_rows())
        memory_review = load_review(run)
        memory_playback = load_playback(run)[3]
        self.assertEqual([], list(self.root.iterdir()))
        self.assertTrue(memory_review['in_memory'])
        self.assertEqual('completed', memory_review['tasks'][0]['outcome'])

        with patch.object(Simulation, 'run', side_effect=AssertionError('Must not rerun')):
            project, saved = run.publish(None, self.root / 'model.amrproj')
        reopened = Project.open(project.path)
        self.assertEqual(run.key, inspect_run(saved, reopened)['run_key'])
        manifest, _, canonical, _ = verified_events(saved)
        self.assertEqual(memory_rows, list(iter_events(canonical)))
        self.assertEqual(memory_playback.events, load_playback(saved)[3].events)
        disk_review = load_review(saved)
        for name in ('tasks', 'events', 'metrics', 'reconciliation'):
            self.assertEqual(memory_review[name], disk_review[name])

        draft = PreparedRun(reopened, self.root / 'comparison')
        checks = check_project(draft.config, base_path=draft.directory)
        checks.acknowledge_warnings()
        other = draft.commit(checks)
        with contextlib.redirect_stdout(io.StringIO()):
            execute(other)
        for directory in (saved, other):
            ensure_exports(directory, OUTPUTS)
        disk_id = inspect_run(other, reopened)['simulation_run_id']
        for name in OUTPUTS.values():
            with self.subTest(output=name):
                self.assertEqual(normalise((saved / name).read_text(encoding='utf-8'), manifest['simulation_run_id']),
                                 normalise((other / name).read_text(encoding='utf-8'), disk_id))
        self.assertTrue(generate(saved, self.root / 'report', ('front_summary',)).read_bytes().startswith(b'%PDF-'))

    def test_drawing_is_frozen_and_matching_revision_is_reused(self):
        drawing = self.root / 'floor.dxf'
        drawing.write_bytes(b'original drawing bytes')
        inputs = config()
        inputs['floor_dxf_files'] = [{'floor': 0, 'filepath': drawing.name}]
        project = Project()
        project.save(self.root / 'model.amrproj', inputs, base_dir=self.root)
        first, second = self.retain(inputs), self.retain(inputs)
        asset = next(iter(first.assets))
        self.assertIs(first.assets[asset], second.assets[asset])
        drawing.write_bytes(b'changed drawing bytes')
        committed, directory = first.publish(project)
        self.assertEqual(project.revisions, committed.revisions)
        self.assertEqual(b'original drawing bytes', (directory / 'drawings' / (asset + '.dxf')).read_bytes())
        self.assertEqual('complete', verified_events(directory, drawings=True)[0]['status'])
        self.pool.discard(first)
        self.assertEqual({}, first.assets)
        self.assertEqual(b'original drawing bytes', second.assets[asset])

    def test_failed_publication_leaves_project_and_ram_untouched(self):
        project = Project()
        project.save(self.root / 'model.amrproj', config())
        run = self.retain(config())
        original = project.path.read_bytes()
        with patch.object(Project, '_write', side_effect=PermissionError('archive locked')):
            with self.assertRaisesRegex(PermissionError, 'archive locked'):
                run.publish(project)
        self.assertEqual(original, project.path.read_bytes())
        self.assertFalse(project.results_root().exists())
        self.assertEqual(run, self.pool.runs[0])
        self.assertTrue(load_review(run)['complete_evidence'])
        project.path.write_bytes(b'edited externally')
        with self.assertRaisesRegex(ValueError, 'changed on disk'):
            run.publish(project)
        self.assertEqual(b'edited externally', project.path.read_bytes())
        self.assertFalse(project.results_root().exists())

    def test_memory_limit_and_cancel_preserve_earlier_results(self):
        kept = self.retain(config())
        incoming = self.prepare(config())
        with self.assertRaises(InterruptedError):
            incoming.execute(self.pool.reserve(incoming), cancel=lambda: True)
        stopped = Event()
        incoming = self.prepare(config())
        def progress(message):
            if message['phase'] == 'Running simulation':
                stopped.set()
        with self.assertRaises(InterruptedError):
            incoming.execute(self.pool.reserve(incoming), cancel=stopped.is_set, progress=progress)
        self.assertTrue(stopped.is_set())
        incoming = self.prepare(config())
        with self.assertRaises(RunMemoryLimit):
            incoming.execute(16 * 1024)
        self.pool.budget = self.pool.usage(incoming) + 1
        with self.assertRaises(RunMemoryLimit):
            self.pool.reserve(incoming)
        self.assertEqual([kept], self.pool.runs)
        self.assertTrue(load_review(kept)['complete_evidence'])
        self.pool.discard(kept)
        self.assertTrue(kept.released)
        self.assertEqual(0, self.pool.usage())
        self.assertEqual([], list(self.root.iterdir()))

    def test_partial_review_and_publication_preserve_termination(self):
        def stop(sim, **_):
            record = dict(schema_version=1, reason='blocked', stop_time_sec=float(sim.current_time),
                          message='No verified retreat.', amr_ids=['R-1'], task_ids=['T'])
            record['event_id'] = sim.log_step(event_time=sim.current_time, event_type='geometric_simulation_stopped',
                                               status='blocked', details=json.dumps(record))
            sim.geometric_termination = record
            return True

        with patch.object(Simulation, '_stop_unresolved_geometry', stop):
            run = self.retain(config())
        self.assertEqual('partial', run.status)
        review = load_review(run)
        self.assertFalse(review['complete_evidence'])
        self.assertTrue(all(metric['value'] is None for metric in review['metrics']))
        self.assertEqual('blocked', load_playback(run)[1]['termination']['reason'])
        _, saved = run.publish(None, self.root / 'partial.amrproj')
        self.assertEqual(review['termination'], verified_events(saved, allow_partial=True)[0]['termination'])

    def test_reduced_logging_is_saved_with_existing_review_restriction(self):
        from tests.test_scenario_study import scenario
        inputs = scenario(config(), [])
        inputs['scenario_testing']['enhanced_logging'] = False
        run = self.retain(inputs)
        for review in (load_playback, load_review):
            with self.assertRaisesRegex(ValueError, 'full event evidence'):
                review(run)
        _, saved = run.publish(None, self.root / 'reduced.amrproj')
        with self.assertRaisesRegex(ValueError, 'complete event evidence'):
            verified_events(saved)


class MemoryRunEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.editor = AMRGraphEditor()
        self.addCleanup(self.close_editor)
        self.editor._recovery_timer.stop()
        self.editor._recovery_store = RecoveryStore(self.root / 'recovery')
        self.editor._replace_document(JsonStore(config()), None, load_drawings=False)
        self.editor.show_project_runs()
        self.panel = self.editor.project_runs_panel

    def close_editor(self):
        with patch.object(self.editor, '_confirm_unsaved_changes', return_value=True):
            self.editor.close()

    def wait_for(self, predicate):
        if not predicate():
            loop = QEventLoop()
            poll = QTimer()
            poll.timeout.connect(lambda: loop.quit() if predicate() else None)
            poll.start(10)
            QTimer.singleShot(10000, loop.quit)
            loop.exec()
            poll.stop()
        self.assertTrue(predicate(), self.panel.log.toPlainText())

    def start_run(self, *, stop=False):
        class AcceptChecks(RunChecksDialog):
            def exec(self):
                self.panel.acknowledge.setChecked(True)
                return QDialog.Accepted

        with patch('project_runs_panel.RunChecksDialog', AcceptChecks):
            self.panel.start_run()
            self.assertTrue(self.panel.running())
            self.assertTrue(self.editor.project_editing_locked())
            if stop:
                self.panel.stop_run()
            self.wait_for(lambda: not self.panel.running())
        self.assertFalse(self.editor.project_editing_locked())

    def test_two_unsaved_runs_review_save_and_document_switch(self):
        self.assertEqual('Save to disk', self.panel.storage.currentText())
        original = self.root / 'model.amrproj'
        project = Project()
        project.save(original, self.editor.store.data)
        self.editor.project = project
        self.editor.current_json_path = str(original)
        self.editor._mark_saved()
        archive = original.read_bytes()
        self.panel.storage.setCurrentText('Memory only')
        self.editor.store.data['amrs'][0]['speed_m_per_sec'] = 1
        self.start_run()
        older = self.panel.selected_memory_run()
        self.editor.store.data['amrs'][0]['speed_m_per_sec'] = 3
        self.start_run()
        newer = self.panel.selected_memory_run()
        self.assertEqual(archive, original.read_bytes())
        self.assertFalse(project.results_root().exists())
        self.assertEqual([newer, older], self.panel.memory.runs)
        self.assertNotEqual(load_review(older)['tasks'], load_review(newer)['tasks'])
        self.start_run(stop=True)
        self.assertEqual([newer, older], self.panel.memory.runs)
        self.assertIn('cancelled', self.panel.log.toPlainText())

        self.panel.refresh_runs(select=older)
        self.panel.playback()
        self.wait_for(lambda: self.editor.playback_panel.viewer is not None)
        self.editor.playback_panel.investigate()
        self.wait_for(lambda: self.editor.results_panel.result is not None)
        self.assertFalse(self.editor.results_panel.export_button.isEnabled())
        self.panel.save_memory_run()
        self.wait_for(lambda: not self.panel.running())
        reopened = Project.open(original)
        manifest, frozen, _, _ = verified_events(self.panel.selected_path())
        self.assertEqual(older.key, manifest['run_key'])
        self.assertEqual(1, frozen['amrs'][0]['speed_m_per_sec'])
        self.assertEqual(2, reopened.configuration()['amrs'][0]['speed_m_per_sec'])
        self.assertEqual(3, self.editor.store.data['amrs'][0]['speed_m_per_sec'])
        self.assertTrue(self.editor.has_unsaved_changes())
        self.assertEqual([newer], self.panel.memory.runs)
        with patch.object(QMessageBox, 'warning', return_value=QMessageBox.Cancel):
            self.assertFalse(self.editor.load_json_file(str(original), load_drawings=False))
        with patch.object(QMessageBox, 'warning', return_value=QMessageBox.Discard):
            self.assertTrue(self.editor.load_json_file(str(original), load_drawings=False))
        self.assertEqual([], self.panel.memory.runs)
        self.assertTrue(newer.released)

    def test_stop_interrupts_an_active_lift_search(self):
        from tests.test_forced_floor import configured

        inputs = configured()
        inputs['tasks'] = [dict(id='T', pickup='A', dropoff='B5', payload='Box')]
        self.editor._replace_document(JsonStore(inputs), None, load_drawings=False)
        self.panel = self.editor.project_runs_panel
        self.panel.storage.setCurrentText('Memory only')
        searching, resume, interrupted = Event(), Event(), Event()
        self.addCleanup(resume.set)
        original = Simulation._direct_lift_plan

        def pause_in_search(sim, *args, **kwargs):
            searching.set()
            resume.wait(5)
            try:
                return original(sim, *args, **kwargs)
            except InterruptedError:
                interrupted.set()
                raise

        class AcceptChecks(RunChecksDialog):
            def exec(self):
                self.panel.acknowledge.setChecked(True)
                return QDialog.Accepted

        with patch('project_runs_panel.RunChecksDialog', AcceptChecks), patch.object(
                Simulation, '_direct_lift_plan', pause_in_search):
            self.panel.start_run()
            self.wait_for(searching.is_set)
            self.panel.stop_run()
            resume.set()
            self.wait_for(lambda: not self.panel.running())
        self.assertTrue(interrupted.is_set())
        self.assertFalse(self.editor.project_editing_locked())
        self.assertEqual([], self.panel.memory.runs)
        self.assertIn('Memory run cancelled.', self.panel.log.toPlainText())

    def test_first_save_from_untitled_keeps_newer_edits_dirty(self):
        self.panel.storage.setCurrentText('Memory only')
        self.start_run()
        self.assertIsNone(self.editor.project)
        self.editor.store.data['amrs'][0]['speed_m_per_sec'] = 3
        path = self.root / 'kept.amrproj'
        with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(path), '')):
            self.panel.save_memory_run()
        self.wait_for(lambda: not self.panel.running())
        self.assertEqual(2, Project.open(path).configuration()['amrs'][0]['speed_m_per_sec'])
        self.assertEqual(3, self.editor.store.data['amrs'][0]['speed_m_per_sec'])
        self.assertTrue(self.editor.has_unsaved_changes())
        self.assertEqual([], self.panel.memory.runs)


if __name__ == '__main__':
    unittest.main()
