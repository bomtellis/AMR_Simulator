import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from amr_recovery import RecoveryStore
from amr_project import digest, encoded, configuration_bytes

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "visualiser"))
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
from PySide6.QtGui import QCloseEvent
from app import AMRGraphEditor
from models import JsonStore


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.recovery = RecoveryStore(self.root / "recovery")

    def test_restart_recovers_configuration_and_drawing_without_original(self):
        source = self.root / "input.json"
        source.write_text('{"original":true}')
        drawing = self.root / "floor.dxf"
        drawing.write_bytes(b"drawing bytes")
        config = {"setting": 17, "floor_dxf_files": [{"floor": 1, "filepath": "floor.dxf"}]}
        self.recovery.capture(config, source_path=source, source_hash=digest(source.read_bytes()))
        drawing.unlink()
        restarted = RecoveryStore(self.recovery.root)
        rows = restarted.list_snapshots()
        self.assertEqual(1, len(rows))
        recovered, body = restarted.recover(rows[0]['path'], self.root / "cache")
        self.assertEqual(17, recovered['setting'])
        self.assertEqual(b"drawing bytes", Path(recovered['floor_dxf_files'][0]['filepath']).read_bytes())
        self.assertEqual(str(source), body['source_path'])
        self.assertEqual('{"original":true}', source.read_text())
        self.assertEqual("floor.dxf", config['floor_dxf_files'][0]['filepath'])

    def test_missing_drawing_keeps_configuration_and_explicit_warning(self):
        self.recovery.capture({"value": 9, "floor_pdf_underlays": [{"filepath": "missing.pdf"}]}, source_path=self.root / "input.json")
        config, body = self.recovery.recover(self.recovery.snapshot_path, self.root / "cache")
        self.assertEqual(9, config['value'])
        self.assertEqual(1, len(body['warnings']))
        self.assertEqual(str(self.root / "missing.pdf"), config['floor_pdf_underlays'][0]['filepath'])

    def test_recovery_preserves_generation_category_order(self):
        self.recovery.capture({'categories': {'waste': {}, 'stores': {}, 'linen': {}}})
        config, _ = self.recovery.recover(self.recovery.snapshot_path, self.root / 'cache')
        self.assertEqual(['waste', 'stores', 'linen'], list(config['categories']))

    def test_failed_atomic_write_keeps_previous_snapshot(self):
        self.recovery.capture({"value": 2})
        before = self.recovery.snapshot_path.read_bytes()
        with patch('amr_project.os.replace', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.recovery.capture({"value": 3})
        self.assertEqual(before, self.recovery.snapshot_path.read_bytes())

    def test_multiple_sessions_do_not_overwrite_or_clear_each_other(self):
        other = RecoveryStore(self.recovery.root)
        self.recovery.capture({"value": 1})
        other.capture({"value": 2})
        self.assertEqual(2, len(other.list_snapshots()))
        other.discard()
        self.assertEqual(1, len(other.list_snapshots()))
        self.assertEqual(1, self.recovery.read(self.recovery.snapshot_path)['config']['value'])

    def test_committed_recovery_survives_abrupt_process_exit(self):
        script = "from amr_recovery import RecoveryStore; import os,sys; RecoveryStore(sys.argv[1]).capture({'independent_expected_value': 42}); os._exit(17)"
        result = subprocess.run([sys.executable, '-c', script, str(self.recovery.root)],
                                cwd=Path(__file__).resolve().parents[1], capture_output=True)
        self.assertEqual(17, result.returncode, result.stderr.decode())
        row = self.recovery.list_snapshots()[0]
        config, _ = self.recovery.recover(row['path'], self.root / 'cache')
        self.assertEqual({'independent_expected_value': 42}, config)

    def test_future_schema_is_rejected_even_with_valid_checksum(self):
        self.recovery.capture({'value': 1})
        envelope = json.loads(self.recovery.snapshot_path.read_bytes())
        envelope['body']['schema_version'] = 99
        envelope['sha256'] = digest(encoded(envelope['body']))
        self.recovery.snapshot_path.write_text(json.dumps(envelope))
        with self.assertRaisesRegex(ValueError, 'format'):
            self.recovery.recover(self.recovery.snapshot_path, self.root / 'cache')

    def test_corrupt_snapshot_remains_listed_and_is_rejected(self):
        self.recovery.capture({"value": 1})
        envelope = json.loads(self.recovery.snapshot_path.read_bytes())
        envelope['body']['config']['value'] = 2
        self.recovery.snapshot_path.write_text(json.dumps(envelope))
        self.assertIn('checksum', self.recovery.list_snapshots()[0]['error'])
        with self.assertRaisesRegex(ValueError, 'checksum'):
            self.recovery.recover(self.recovery.snapshot_path, self.root / "cache")

    def test_corrupt_asset_and_path_traversal_are_rejected(self):
        drawing = self.root / "floor.dxf"
        drawing.write_bytes(b"safe")
        self.recovery.capture({"floor_dxf_files": [{"filepath": str(drawing)}]})
        asset = next((self.recovery.root / 'assets').iterdir())
        asset.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, 'checksum'):
            self.recovery.recover(self.recovery.snapshot_path, self.root / 'cache')
        envelope = json.loads(self.recovery.snapshot_path.read_bytes())
        envelope['body']['config']['floor_dxf_files'][0]['filepath'] = 'amr-recovery-asset:../escape.dxf'
        envelope['body']['config_order_sha256'] = digest(configuration_bytes(envelope['body']['config']))
        envelope['sha256'] = digest(encoded(envelope['body']))
        self.recovery.snapshot_path.write_text(json.dumps(envelope))
        with self.assertRaisesRegex(ValueError, 'reference'):
            self.recovery.recover(self.recovery.snapshot_path, self.root / 'cache')
        with self.assertRaisesRegex(ValueError, 'folder'):
            self.recovery.discard(self.root / 'outside.json')


class RecoveryUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.editor = AMRGraphEditor()
        self.editor._recovery_store = RecoveryStore(self.root / 'recovery')
        self.validator = patch.object(JsonStore, 'validate', return_value=[])
        self.validator.start()

    def tearDown(self):
        with patch.object(self.editor, '_confirm_unsaved_changes', return_value=True):
            self.editor.close()
        self.validator.stop()
        self.temp.cleanup()

    def edit(self, value=8):
        self.editor.store.data['building']['floor_height_m'] = value

    def write_config(self, name='input.json'):
        path = self.root / name
        path.write_text(json.dumps(JsonStore().data))
        return path

    def test_dirty_tracking_includes_direct_edits_and_reverting_to_saved_values(self):
        self.assertFalse(self.editor.has_unsaved_changes())
        original = self.editor.store.data['building']['floor_height_m']
        self.edit()
        self.assertTrue(self.editor.has_unsaved_changes())
        self.assertTrue(self.editor.capture_recovery())
        path = self.editor._recovery_store.snapshot_path
        self.assertTrue(path.exists())
        self.edit(original)
        self.assertFalse(self.editor.has_unsaved_changes())
        self.editor.capture_recovery()
        self.assertFalse(path.exists())

    def test_cancel_open_preserves_current_work_and_recovery(self):
        self.edit()
        self.editor.capture_recovery()
        with patch.object(QMessageBox, 'warning', return_value=QMessageBox.Cancel):
            self.assertFalse(self.editor.load_json_file(str(self.write_config())))
        self.assertEqual(8, self.editor.store.data['building']['floor_height_m'])
        self.assertTrue(self.editor._recovery_store.snapshot_path.exists())

    def test_cancel_close_keeps_timers_and_recovery_running(self):
        self.edit()
        self.editor.capture_recovery()
        event = QCloseEvent()
        with patch.object(QMessageBox, 'warning', return_value=QMessageBox.Cancel):
            self.editor.closeEvent(event)
        self.assertFalse(event.isAccepted())
        self.assertTrue(self.editor._recovery_timer.isActive())
        self.assertTrue(self.editor._recovery_store.snapshot_path.exists())

    def test_discard_close_removes_own_snapshot_and_stops_timers(self):
        self.edit()
        self.editor.capture_recovery()
        event = QCloseEvent()
        with patch.object(QMessageBox, 'warning', return_value=QMessageBox.Discard):
            self.editor.closeEvent(event)
        self.assertTrue(event.isAccepted())
        self.assertFalse(self.editor._recovery_timer.isActive())
        self.assertFalse(self.editor._recovery_store.snapshot_path.exists())

    def test_save_cancellation_or_failure_prevents_close(self):
        self.edit()
        with patch.object(QMessageBox, 'warning', return_value=QMessageBox.Save), patch.object(QFileDialog, 'getSaveFileName', return_value=('', '')):
            self.assertFalse(self.editor._confirm_unsaved_changes())
        with patch.object(QMessageBox, 'warning', return_value=QMessageBox.Save), patch.object(self.editor, 'save_json', return_value=False):
            self.assertFalse(self.editor._confirm_unsaved_changes())

    def test_save_before_open_preserves_edits_and_clears_own_snapshot(self):
        current = self.write_config()
        self.editor.load_json_file(str(current))
        self.edit()
        self.editor.capture_recovery()
        with patch.object(QMessageBox, 'warning', return_value=QMessageBox.Save):
            self.assertTrue(self.editor.load_json_file(str(self.write_config('next.json'))))
        self.assertEqual(8, json.loads(current.read_text())['building']['floor_height_m'])
        self.assertFalse(self.editor.has_unsaved_changes())
        self.assertFalse(self.editor._recovery_store.snapshot_path.exists())

    def test_failed_open_after_discard_keeps_current_work_and_snapshot(self):
        self.edit()
        self.editor.capture_recovery()
        with patch.object(QMessageBox, 'warning', return_value=QMessageBox.Discard), patch.object(QMessageBox, 'critical'):
            self.assertFalse(self.editor.load_json_file(str(self.root / 'missing.json')))
        self.assertEqual(8, self.editor.store.data['building']['floor_height_m'])
        self.assertTrue(self.editor._recovery_store.snapshot_path.exists())

    def test_discard_successful_open_clears_only_own_snapshot(self):
        self.edit()
        self.editor.capture_recovery()
        other = RecoveryStore(self.editor._recovery_store.root)
        other.capture({'other': 10})
        with patch.object(QMessageBox, 'warning', return_value=QMessageBox.Discard):
            self.assertTrue(self.editor.load_json_file(str(self.write_config())))
        self.assertFalse(self.editor._recovery_store.snapshot_path.exists())
        self.assertTrue(other.snapshot_path.exists())

    def test_recovery_opens_unsaved_and_json_save_keeps_durable_drawings(self):
        source = self.write_config()
        original = source.read_bytes()
        drawing = self.root / 'floor.dxf'
        drawing.write_bytes(b'recovered drawing')
        data = JsonStore().data
        data['building']['floor_height_m'] = 19
        data['floor_dxf_files'] = [{'floor': 0, 'filepath': str(drawing)}]
        previous = RecoveryStore(self.editor._recovery_store.root)
        previous.capture(data, source_path=source, source_hash=digest(original))
        drawing.unlink()
        source.write_text('{}')
        with patch.object(QMessageBox, 'information') as info:
            self.assertTrue(self.editor.load_recovery_snapshot(previous.snapshot_path))
            self.assertIn('original file has changed', info.call_args.args[2])
        self.assertIsNone(self.editor.current_json_path)
        self.assertTrue(self.editor.has_unsaved_changes())
        self.assertEqual(19, self.editor.store.data['building']['floor_height_m'])
        destination = self.root / 'recovered.json'
        with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(destination), '')):
            self.assertTrue(self.editor.save_json())
        self.editor.close()
        exported = json.loads(destination.read_text())
        self.assertEqual(b'recovered drawing', Path(exported['floor_dxf_files'][0]['filepath']).read_bytes())
        self.assertEqual('{}', source.read_text())

    def test_changed_json_on_disk_is_not_overwritten(self):
        path = self.write_config()
        self.editor.load_json_file(str(path))
        self.edit()
        path.write_text('{"external":true}')
        with patch.object(QMessageBox, 'critical'):
            self.assertFalse(self.editor.save_json())
        self.assertEqual('{"external":true}', path.read_text())
        self.assertTrue(self.editor.has_unsaved_changes())

    def test_nonfinite_input_can_be_opened_and_repaired_without_dirty_tracker_crash(self):
        path = self.write_config()
        config = json.loads(path.read_text())
        config['building']['floor_height_m'] = float('nan')
        path.write_text(json.dumps(config))
        self.assertTrue(self.editor.load_json_file(str(path)))
        self.assertFalse(self.editor.has_unsaved_changes())
        self.edit(4)
        self.assertTrue(self.editor.save_json())
        self.assertEqual(4, json.loads(path.read_text())['building']['floor_height_m'])

    def test_recovery_failure_is_visible_and_keeps_prior_snapshot(self):
        self.edit()
        self.editor.capture_recovery()
        path = self.editor._recovery_store.snapshot_path
        original = path.read_bytes()
        self.edit(9)
        with patch.object(self.editor._recovery_store, 'capture', side_effect=OSError('disk full')):
            self.assertFalse(self.editor.capture_recovery())
        self.assertIn('disk full', self.editor._recovery_status)
        self.assertEqual(original, path.read_bytes())


if __name__ == '__main__':
    unittest.main()
