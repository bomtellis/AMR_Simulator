"""Source coverage and invalidation, independent of the previous filename list."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from amr_run_evidence import software_snapshot


class SoftwareFingerprintTests(unittest.TestCase):
    def test_application_dependencies_are_covered(self):
        snapshot = software_snapshot()
        self.assertEqual(2, snapshot['scope_version'])
        for name in ('simulator.py', 'amr_route_reservations.py', 'amr_generation_provenance.py',
                     'amr_project.py', 'visualiser/project_checks.py', 'visualiser/models.py',
                     'report/amr_report_analysis.py'):
            self.assertIn(name, snapshot['files'])

    def test_content_addition_removal_and_nested_modules_invalidate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'visualiser/nested').mkdir(parents=True)
            (root / 'report').mkdir()
            (root / 'tests').mkdir()
            source = root / 'visualiser/nested/new_dependency.py'
            source.write_text('value = 1')
            with patch('amr_run_evidence.__file__', str(root / 'amr_run_evidence.py')):
                before = software_snapshot()
                self.assertIn('visualiser/nested/new_dependency.py', before['files'])
                source.write_text('value = 2')
                self.assertNotEqual(before['sha256'], software_snapshot()['sha256'])
                source.write_text('value = 1')
                extra = root / 'report/new_analysis.py'
                extra.write_text('value = 3')
                self.assertNotEqual(before['sha256'], software_snapshot()['sha256'])
                extra.unlink()
                (root / 'tests/test_example.py').write_text('pass')
                (root / 'example.json').write_text('{}')
                self.assertEqual(before, software_snapshot())
                source.unlink()
                self.assertNotEqual(before['sha256'], software_snapshot()['sha256'])
