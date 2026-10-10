"""The shipped two-exercise walkthrough must match its runnable practice input."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'visualiser'))

from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication

from simulator import Simulation
from visualiser.project_checks import check_project
from quick_start import EXERCISES, QuickStartDialog


class QuickStartTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_small_map_has_two_types_and_completed_connected_reference(self):
        path = ROOT / 'docs' / 'quick-start' / 'small-map.json'
        before = path.read_bytes()
        config = json.loads(before)
        self.assertEqual({'R1', 'R2'}, {robot['id'] for robot in config['amrs']})
        self.assertIn('TASK_UNREACHABLE', {f.code for f in check_project(config).findings})
        config['corridors']['edges'].append({'from': 'B', 'to': 'C', 'width_m': 2})
        self.assertFalse([f for f in check_project(config).findings if f.severity in {'error', 'warning'}])
        sim = Simulation(config, verbose=True)
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()
        self.assertEqual(1, len(sim.completed_task_records))
        self.assertEqual(set(), sim.failed_task_ids)
        self.assertFalse(sim.pending_tasks)
        self.assertEqual(before, path.read_bytes())

    def test_walkthrough_has_two_exercises_and_navigates_without_editing(self):
        from app import AMRGraphEditor
        editor = AMRGraphEditor()
        try:
            original = json.dumps(editor.store.data, sort_keys=True)
            self.assertEqual(2, len(EXERCISES))
            editor.workbench.show_quick_start()
            dialog = editor.workbench.quick_start_dialog
            self.assertIsInstance(dialog, QuickStartDialog)
            self.assertEqual(2, dialog.exercise.count())
            self.assertEqual(len(EXERCISES[0]['steps']), dialog.steps.count())
            dialog.next.click()
            self.assertEqual(1, dialog.steps.currentRow())
            self.assertIn(editor.workbench.walkthrough_action, editor.workbench.help_menu.actions())
            for exercise_index, exercise in enumerate(EXERCISES):
                dialog.exercise.setCurrentIndex(exercise_index)
                self.assertEqual(len(exercise['steps']), dialog.steps.count())
                for step_index, (title, _action, _expected, stage) in enumerate(exercise['steps']):
                    dialog.steps.setCurrentRow(step_index)
                    self.assertEqual(title, dialog.steps.currentItem().text())
                    with patch.object(editor.workspace, 'activate') as activate:
                        dialog.open_stage.click()
                    activate.assert_called_once_with(stage)
            with patch.object(QDesktopServices, 'openUrl', return_value=True) as open_url:
                dialog.open_guide.click()
            self.assertTrue(open_url.call_args.args[0].toLocalFile().endswith('AMR-Simulator-Quick-Start.pdf'))
            with tempfile.TemporaryDirectory() as temporary:
                example_root = Path(temporary)
                for relative in ('docs/quick-start/small-map.json', 'examples/ltn.amrproj'):
                    candidate = example_root / relative
                    candidate.parent.mkdir(parents=True, exist_ok=True)
                    candidate.touch()
                with patch('quick_start.application_root', return_value=example_root):
                    for index, suffix in ((0, 'small-map.json'), (1, 'ltn.amrproj')):
                        dialog.exercise.setCurrentIndex(index)
                        with patch.object(editor, 'load_json_file') as load_example:
                            dialog.open_example.click()
                        self.assertTrue(load_example.call_args.args[0].endswith(suffix))
            self.assertEqual(original, json.dumps(editor.store.data, sort_keys=True))
            dialog.close()
        finally:
            with patch.object(editor, '_confirm_unsaved_changes', return_value=True):
                editor.close()


if __name__ == '__main__':
    unittest.main()
