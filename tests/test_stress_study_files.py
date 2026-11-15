"""Replacement and concurrent-process regressions for study files."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from amr_scenario_study import create_study, default_settings, evaluate, study_lock
from tests.test_scenario_study import config


class StressStudyFileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'existing.stress.json'
        self.config = config()
        self.settings = default_settings(self.config)
        self.state = create_study(self.config, self.path, self.settings)
        self.original = self.path.read_bytes()

    def test_existing_file_requires_explicit_overwrite(self):
        with self.assertRaisesRegex(ValueError, 'existing studies'):
            create_study(self.config, self.path, self.settings)
        self.assertEqual(self.original, self.path.read_bytes())

    def test_invalid_overwrite_preserves_existing_file(self):
        with self.assertRaises(ValueError):
            create_study(self.config, self.path, {**self.settings, 'assets': []}, overwrite=True)
        self.assertEqual(self.original, self.path.read_bytes())

    def test_backup_write_failure_preserves_existing_file(self):
        with patch('amr_scenario_study.atomic_write', side_effect=PermissionError('Backup is read-only')):
            with self.assertRaises(PermissionError):
                create_study(self.config, self.path, self.settings, overwrite=True)
        self.assertEqual(self.original, self.path.read_bytes())

    def test_replacement_write_failure_preserves_old_file_and_backup(self):
        with patch('amr_scenario_study.write_json', side_effect=PermissionError('File is read-only')):
            with self.assertRaises(PermissionError):
                create_study(self.config, self.path, self.settings, overwrite=True)
        self.assertEqual(self.original, self.path.read_bytes())
        backups = list(self.path.parent.glob('*.previous-*.stress.json'))
        self.assertEqual(1, len(backups))
        self.assertEqual(self.original, backups[0].read_bytes())

    def test_locked_study_rejects_second_coordinator_without_changes(self):
        with study_lock(self.path):
            with self.assertRaisesRegex(ValueError, 'already running'):
                evaluate(self.path)
        self.assertEqual(self.original, self.path.read_bytes())

    def test_cancel_marker_permission_failure_does_not_replace_old_study(self):
        marker = self.path.with_suffix('.json.cancel')
        marker.write_text('{}')
        original_unlink = Path.unlink
        def unlink(path, *args, **kwargs):
            if path == marker:
                raise PermissionError('Cannot remove stop request')
            return original_unlink(path, *args, **kwargs)
        with patch.object(Path, 'unlink', unlink):
            with self.assertRaisesRegex(PermissionError, 'stop request'):
                create_study(self.config, self.path, self.settings, overwrite=True)
        self.assertEqual(self.original, self.path.read_bytes())

    def test_lock_is_cross_process_and_released_when_owner_exits(self):
        script = (
            'from amr_scenario_study import study_lock\n'
            'import sys\n'
            'with study_lock(sys.argv[1]):\n'
            ' print("locked", flush=True)\n'
            ' sys.stdin.readline()\n'
        )
        with subprocess.Popen([sys.executable, '-u', '-c', script, str(self.path)],
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True) as process:
            try:
                self.assertEqual('locked', process.stdout.readline().strip())
                with self.assertRaisesRegex(ValueError, 'already running'):
                    create_study(self.config, self.path, self.settings, overwrite=True)
                self.assertEqual(self.original, self.path.read_bytes())
            finally:
                process.kill()
                process.communicate(timeout=10)
        with study_lock(self.path):
            pass


if __name__ == '__main__':
    unittest.main()
