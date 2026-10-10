"""Preserve simulator generation settings through the desktop editor."""
import contextlib
import copy
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'visualiser'))
from PySide6.QtWidgets import QApplication
from dialogs import TaskGenerationSettingsDialog
from visualiser.models import JsonStore
from simulator import Simulation
from tests.test_generation_reference import grouped_config


class GenerationSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_update_interval_survives_open_save_reopen(self):
        for interval in (0, 60, 90.5, 1800):
            with self.subTest(interval=interval), tempfile.TemporaryDirectory() as folder:
                config = grouped_config()
                config['task_generation']['update_interval_sec'] = interval
                store = JsonStore(copy.deepcopy(config))
                path = Path(folder) / 'project.json'
                store.save(str(path))
                restored = JsonStore.from_file(str(path))
                self.assertEqual(interval, restored.data['task_generation'].get('update_interval_sec'))

    def test_task_generation_dialog_save_retains_update_interval(self):
        config = grouped_config()
        config['task_generation']['update_interval_sec'] = 60
        saved = []
        dialog = TaskGenerationSettingsDialog(None, config['task_generation'], ['A', 'B'], ['Box'], [],
                                               config['departments'], saved.append)
        try:
            dialog.accept()
            self.assertEqual(1, len(saved))
            self.assertEqual(60, saved[0].get('update_interval_sec'))
        finally:
            dialog.close()

    def test_editor_and_cli_keep_the_same_short_scheduled_run(self):
        config = grouped_config()
        config['task_generation']['update_interval_sec'] = 60
        for input_config in (config, JsonStore(copy.deepcopy(config)).data):
            with self.subTest(editor_normalised=input_config is not config):
                with contextlib.redirect_stdout(io.StringIO()):
                    sim = Simulation(input_config)
                    sim.run()
                self.assertEqual(set(), sim.failed_task_ids)
                self.assertEqual(1, len(sim.completed_task_records))
                self.assertEqual(9, sim.completed_task_records[0]['duration_sec'])


if __name__ == '__main__':
    unittest.main()
