import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from amr_project import Project, digest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "visualiser"))
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
from app import AMRGraphEditor
from models import JsonStore


class ProjectStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.path = self.folder / "test.amrproj"
        self.config = {"building": {"floor_height_m": 3}, "floor_dxf_files": [
            {"floor": 0, "filepath": "a.dxf"}, {"floor": 1, "filepath": "b.dxf"}],
            "floor_pdf_underlays": [{"floor": 0, "filepath": "a.pdf", "x_m": 1.5}]}
        (self.folder / "a.dxf").write_bytes(b"same drawing" * 100)
        (self.folder / "b.dxf").write_bytes(b"same drawing" * 100)
        (self.folder / "a.pdf").write_bytes(b"different pdf")
        (self.folder / "simulation_steps.csv").write_text("Must not be included")
        self.project = Project()

    def save(self):
        self.project.save(self.path, self.config, base_dir=self.folder)

    def rewrite(self, change):
        with zipfile.ZipFile(self.path) as archive:
            entries = {n: archive.read(n) for n in archive.namelist()}
        change(entries)
        with zipfile.ZipFile(self.path, "w") as archive:
            for name, data in entries.items():
                archive.writestr(name, data)

    def test_portable_roundtrip_deduplicates_drawings_and_excludes_outputs(self):
        self.save()
        self.assertEqual("a.dxf", self.config["floor_dxf_files"][0]["filepath"])
        with zipfile.ZipFile(self.path) as archive:
            self.assertEqual(2, sum(n.startswith("assets/") for n in archive.namelist()))
            self.assertFalse(any("simulation" in n for n in archive.namelist()))
            self.assertTrue(all(i.compress_type == zipfile.ZIP_DEFLATED for i in archive.infolist()))
        moved = self.folder / "moved"
        moved.mkdir()
        shutil.copyfile(self.path, moved / "portable.amrproj")
        for name in ("a.dxf", "b.dxf", "a.pdf"):
            (self.folder / name).unlink()
        reopened = Project.open(moved / "portable.amrproj")
        data = reopened.materialize(moved / "cache")
        self.assertEqual(self.config["building"], data["building"])
        self.assertEqual(data["floor_dxf_files"][0]["filepath"], data["floor_dxf_files"][1]["filepath"])
        self.assertEqual(b"same drawing" * 100, Path(data["floor_dxf_files"][0]["filepath"]).read_bytes())
        self.assertEqual(1.5, data["floor_pdf_underlays"][0]["x_m"])

    def test_no_change_save_does_not_duplicate_revision(self):
        self.save()
        self.save()
        self.assertEqual(1, len(Project.open(self.path).revisions))

    def test_restore_preserves_unsaved_changes_and_old_drawing(self):
        self.save()
        first = self.project.revisions[0]["id"]
        self.config["building"]["floor_height_m"] = 4
        (self.folder / "a.dxf").write_bytes(b"changed drawing")
        self.save()
        self.config["building"]["floor_height_m"] = 5
        self.project.restore(first, self.config, base_dir=self.folder)
        loaded = Project.open(self.path)
        self.assertEqual(4, len(loaded.revisions))
        self.assertEqual(5, loaded.configuration(loaded.revisions[-2]["id"])["building"]["floor_height_m"])
        self.assertEqual(3, loaded.configuration()["building"]["floor_height_m"])
        self.assertEqual(b"same drawing" * 100, Path(loaded.materialize(self.folder / "cache")["floor_dxf_files"][0]["filepath"]).read_bytes())

    def test_failed_replace_preserves_file_and_in_memory_history(self):
        self.save()
        before = self.path.read_bytes()
        self.config["building"]["floor_height_m"] = 6
        with patch("amr_project.os.replace", side_effect=OSError("locked file")):
            with self.assertRaisesRegex(OSError, "locked"):
                self.save()
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(1, len(self.project.revisions))
        self.assertFalse(list(self.folder.glob("*.tmp")))

    def test_missing_drawing_blocks_save_without_changing_original(self):
        self.save()
        before = self.path.read_bytes()
        (self.folder / "a.pdf").unlink()
        with self.assertRaises(FileNotFoundError):
            self.save()
        self.assertEqual(before, self.path.read_bytes())

    def test_external_changes_block_overwrite(self):
        self.save()
        other = Project.open(self.path)
        other.save(self.path, {"building": {"floor_height_m": 99}})
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "changed on disk"):
            self.save()
        self.assertEqual(before, self.path.read_bytes())

    def test_compare_and_export_do_not_change_history_or_current_config(self):
        self.save()
        first = self.project.revisions[0]["id"]
        self.config["building"]["floor_height_m"] = 7
        diff = self.project.compare(first, self.config, base_dir=self.folder)
        self.assertIn('-    "floor_height_m": 3', diff)
        self.assertIn('+    "floor_height_m": 7', diff)
        output = self.folder / "export.json"
        self.project.export_json(output, self.config, base_dir=self.folder)
        data = json.loads(output.read_text())
        self.assertEqual(7, data["building"]["floor_height_m"])
        self.assertTrue(Path(data["floor_dxf_files"][0]["filepath"]).is_file())
        self.assertEqual(1, len(self.project.revisions))
        self.assertEqual("a.dxf", self.config["floor_dxf_files"][0]["filepath"])

    def test_unknown_schema_rejected_without_migration_or_file_change(self):
        self.save()
        def change(entries):
            manifest = json.loads(entries["manifest.json"])
            manifest["schema_version"] = 999
            entries["manifest.json"] = json.dumps(manifest).encode()
        self.rewrite(change)
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "version"):
            Project.open(self.path)
        self.assertEqual(before, self.path.read_bytes())

    def test_corrupt_asset_rejected(self):
        self.save()
        self.rewrite(lambda entries: entries.__setitem__(next(n for n in entries if n.startswith("assets/")), b"tampered"))
        with self.assertRaisesRegex(ValueError, "checksum"):
            Project.open(self.path)

    def test_path_traversal_and_unknown_members_rejected(self):
        self.save()
        self.rewrite(lambda entries: entries.__setitem__("../outside.pdf", b"bad"))
        with self.assertRaisesRegex(ValueError, "Unsupported archive entry"):
            Project.open(self.path)
        self.assertFalse((self.folder.parent / "outside.pdf").exists())

    def test_missing_embedded_drawing_rejected(self):
        self.save()
        self.rewrite(lambda entries: entries.pop(next(n for n in entries if n.startswith("assets/"))))
        with self.assertRaisesRegex(ValueError, "missing embedded drawing"):
            Project.open(self.path)

    def test_broken_history_rejected(self):
        self.save()
        def change(entries):
            manifest = json.loads(entries["manifest.json"])
            manifest["revisions"][0]["parent"] = "missing"
            entries["manifest.json"] = json.dumps(manifest).encode()
        self.rewrite(change)
        with self.assertRaisesRegex(ValueError, "Broken revision history"):
            Project.open(self.path)

    def test_expanded_archive_limit_enforced(self):
        self.save()
        with patch("amr_project.MAX_MEMBER_BYTES", 10):
            with self.assertRaisesRegex(ValueError, "size limits"):
                Project.open(self.path)

    def test_json_atomic_save_failure_preserves_original(self):
        path = self.folder / "config.json"
        path.write_text('{"original": true}')
        with patch("models.os.replace", side_effect=OSError("locked")):
            with self.assertRaises(OSError):
                JsonStore().save(path)
        self.assertEqual('{"original": true}', path.read_text())


class ProjectStorageUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_editor_save_reopen_restore_and_export(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "editor.amrproj"
            editor = AMRGraphEditor()
            try:
                with patch.object(QFileDialog, "getSaveFileName", return_value=(str(path), "")):
                    self.assertTrue(editor.save_project())
                editor.store.data["building"]["floor_height_m"] = 12
                editor.save_json()
                self.assertEqual(2, len(editor.project.revisions))
                with patch.object(JsonStore, "validate", return_value=[]):
                    self.assertTrue(editor.load_json_file(str(path), load_drawings=False))
                    editor.show_project_revisions()
                    panel = editor.project_history_panel
                    panel.revisions.setCurrentIndex(1)
                    panel.compare()
                    self.assertIn("floor_height_m", panel.changes.toPlainText())
                    editor.store.data["building"]["floor_height_m"] = 13
                    panel.restore()
                self.assertEqual(4, len(editor.project.revisions))
                self.assertNotEqual(13, editor.store.data["building"]["floor_height_m"])
                output = Path(folder) / "export.json"
                with patch.object(QFileDialog, "getSaveFileName", return_value=(str(output), "")):
                    editor.export_project_json()
                self.assertTrue(output.is_file())
                self.assertEqual(str(path), editor.current_json_path)
                with patch.object(JsonStore, "validate", return_value=[]):
                    self.assertTrue(editor.load_json_file(str(output), load_drawings=False))
                self.assertIsNone(editor.project)
                self.assertFalse(panel.restore_button.isEnabled())
            finally:
                editor.close()

    def test_invalid_project_keeps_current_editor_state(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.amrproj"
            path.write_text("not a zip")
            editor = AMRGraphEditor()
            try:
                original = editor.store
                with patch.object(QMessageBox, "critical"):
                    self.assertFalse(editor.load_json_file(str(path)))
                self.assertIs(original, editor.store)
            finally:
                editor.close()


    def test_relative_drawings_survive_save_as_and_source_removal(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source"
            source.mkdir()
            drawing = source / "floor.dxf"
            drawing.write_bytes(b"portable drawing")
            config = JsonStore().data
            config["floor_dxf_files"] = [{"floor": 0, "filepath": "floor.dxf"}]
            original = source / "original.json"
            original.write_text(json.dumps(config))
            target = root / "saved.amrproj"
            editor = AMRGraphEditor()
            try:
                with patch.object(JsonStore, "validate", return_value=[]):
                    editor.load_json_file(str(original), load_drawings=False)
                with patch.object(QFileDialog, "getSaveFileName", return_value=(str(target), "")):
                    self.assertTrue(editor.save_project(save_as=True))
                drawing.unlink()
                self.assertTrue(editor.save_project())
                self.assertEqual(b"portable drawing", Path(editor.store.data["floor_dxf_files"][0]["filepath"]).read_bytes())
                self.assertEqual("floor.dxf", json.loads(original.read_text())["floor_dxf_files"][0]["filepath"])
            finally:
                editor.close()


if __name__ == "__main__":
    unittest.main()
