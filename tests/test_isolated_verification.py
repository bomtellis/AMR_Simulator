"""Real child processes must never turn crashes, empty discovery or timeouts green."""
import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from verification.isolated import run_modules


class IsolatedVerificationTests(unittest.TestCase):
    def run_reference(self, source, timeout=20):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            tests = root / 'tests'
            tests.mkdir()
            (tests / 'test_reference.py').write_text(source, encoding='utf-8')
            stale = root / 'output/modules/test_reference'
            stale.mkdir(parents=True)
            (stale / 'cases.json').write_text(
                '{"successful": true, "cases": [{"id": "stale.pass", "status": "passed"}]}',
                encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                result = run_modules(tests, root / 'output', timeout=timeout)
            self.assertTrue((root / 'output/tests.txt').is_file())
            return result

    def test_pass_and_failure_keep_real_test_id_and_verdict(self):
        for expression, expected in [('True', True), ('False', False)]:
            result = self.run_reference('import unittest\nclass Reference(unittest.TestCase):\n'
                                        f'    def test_result(self): self.assertTrue({expression})\n')
            self.assertEqual(expected, result.wasSuccessful())
            self.assertEqual(1, len(result.cases))
            self.assertEqual('test_reference.Reference.test_result', result.cases[0]['id'])

    def test_crashed_worker_is_an_error(self):
        result = self.run_reference('import os\nos._exit(7)\n')
        self.assertFalse(result.wasSuccessful())
        self.assertEqual('error', result.cases[0]['status'])

    def test_empty_module_and_failed_class_setup_are_errors(self):
        for source in ['', 'import unittest\nclass Reference(unittest.TestCase):\n'
                       '    @classmethod\n    def setUpClass(cls): raise RuntimeError("fixture failed")\n'
                       '    def test_result(self): pass\n']:
            self.assertFalse(self.run_reference(source).wasSuccessful())

    def test_timeout_reports_error_without_using_stale_evidence(self):
        result = self.run_reference('import time\ntime.sleep(30)\n', timeout=1)
        self.assertFalse(result.wasSuccessful())
        self.assertIn('exceeded', result.cases[0]['details'])
