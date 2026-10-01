import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "visualiser"))

from PySide6.QtWidgets import QApplication, QPushButton
from PySide6.QtGui import QPixmap
from app import AMRGraphEditor
from models import JsonStore


class OpenWithoutDrawingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "config.json"
        self.data = JsonStore().data
        self.data["floor_dxf_files"] = [
            {"floor": 0, "filepath": "missing-ground.dxf"},
            {"floor": 1, "filepath": "missing-first.dxf"},
        ]
        self.data["floor_pdf_underlays"] = [
            {"floor": 0, "filepath": "missing.pdf", "x_m": 9999},
            {"floor": 1, "filepath": "missing-first.pdf"},
        ]
        self.path.write_text(json.dumps(self.data), encoding="utf-8")
        self.editor = AMRGraphEditor()
        self.jobs = []
        self.editor._request_dxf_batch_load.disconnect()
        self.editor._request_dxf_batch_load.connect(self.jobs.extend)
        self.validation = patch.object(JsonStore, "validate", return_value=[])
        self.validation.start()
        self.progress = patch.object(self.editor, "_update_loading_dialog")
        self.progress.start()

    def tearDown(self):
        self.editor.close()
        self.validation.stop()
        self.progress.stop()
        self.temp.cleanup()

    def test_skips_drawings_across_floors_refresh_and_late_callbacks(self):
        with patch.object(self.editor, "_pdf_pixmap") as pdf:
            self.assertTrue(self.editor.load_json_file(str(self.path), load_drawings=False))
            self.editor.floor_spin.setValue(1)
            self.editor.refresh_canvas()
            self.editor.fit_view()
            self.editor.request_floor_dxf_load(0, force_reload=True)
            self.editor._on_dxf_loaded(1, "missing-first.dxf", [], (0, 0, 100, 100))
            self.editor._on_dxf_failed(1, "missing-first.dxf", "Old request failed")
            self.assertEqual(self.jobs, [])
            pdf.assert_not_called()
            self.assertEqual(self.editor._dxf_cache, {})
            self.assertFalse(self.editor._pending_fit_after_load)
            self.assertIsNone(self.editor._content_bounds(0))
        self.editor.save_json()
        saved = json.loads(self.path.read_text(encoding="utf-8"))
        for key in ("floor_dxf_files", "floor_pdf_underlays"):
            self.assertEqual(saved[key], self.data[key])

    def test_restore_and_normal_open_load_drawings(self):
        self.editor.load_json_file(str(self.path), load_drawings=False)
        with patch.object(self.editor, "_pdf_pixmap", return_value=(QPixmap(2, 2), 1)) as pdf:
            self.editor.load_configured_drawings()
            self.assertTrue(self.editor._drawings_enabled)
            self.assertEqual(set(self.jobs), {(0, "missing-ground.dxf"), (1, "missing-first.dxf")})
            self.assertTrue(pdf.called)
            self.editor.load_json_file(str(self.path), load_drawings=False)
            self.jobs.clear()
            self.editor.load_json_file(str(self.path))
            self.assertTrue(self.editor._drawings_enabled)
            self.assertEqual(len(self.jobs), 2)

    def test_open_button_and_cancel(self):
        button = next(b for b in self.editor.findChildren(QPushButton) if b.text() == "Open without drawings")
        with patch("app.QFileDialog.getOpenFileName", return_value=(str(self.path), "")), patch.object(self.editor, "load_json_file") as load:
            button.click()
            load.assert_called_once_with(str(self.path), load_drawings=False)
        with patch("app.QFileDialog.getOpenFileName", return_value=("", "")), patch.object(self.editor, "load_json_file") as load:
            button.click()
            load.assert_not_called()
        self.assertTrue(self.editor._drawings_enabled)


if __name__ == "__main__":
    unittest.main()
