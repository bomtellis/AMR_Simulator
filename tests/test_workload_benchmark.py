"""Workload counts and saved-run reconciliation for the performance harness."""
from contextlib import redirect_stdout
from datetime import datetime
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from verification.workload import workload_config,run_workload


class WorkloadBenchmarkTests(unittest.TestCase):
    def test_default_operating_dimensions_and_release_calendar(self):
        config = workload_config()
        self.assertEqual(set(range(10)),{p['floor'] for p in config['locations']})
        self.assertEqual(60,sum(robot['quantity'] for robot in config['amrs']))
        self.assertEqual(60,sum(len(p.get('inventory_spaces',[])) for p in config['locations']))
        self.assertEqual(7000,len(config['tasks']))
        self.assertEqual(7000,len({t['id'] for t in config['tasks']}))
        for day in range(7):
            self.assertEqual(1000,sum(day*86400 <= t['release_time'] < (day+1)*86400 for t in config['tasks']))
        self.assertEqual(1750,sum(t['pickup'].split('-')[-1] != t['dropoff'].split('-')[-1] for t in config['tasks']))
        self.assertEqual(7,(datetime.fromisoformat(config['simulation']['end_datetime'])-
                            datetime.fromisoformat(config['simulation']['start_datetime'])).days)

    def test_invalid_dimensions_fail_explicitly(self):
        for value in (0,-1,True,1.5):
            with self.subTest(value=value),self.assertRaises(ValueError):
                workload_config(days=value)

    def test_small_saved_runs_reconcile_and_repeat_without_overwriting(self):
        with tempfile.TemporaryDirectory() as directory,redirect_stdout(StringIO()):
            first = run_workload(Path(directory)/'one',floors=2,robots_per_floor=1,tasks_per_day=4,days=1)
            second = run_workload(Path(directory)/'two',floors=2,robots_per_floor=1,tasks_per_day=4,days=1)
            self.assertTrue(first['configuration_roundtrip_matches'])
            self.assertTrue(first['all_expected_completed'])
            self.assertTrue(first['reconciliation_matches'])
            self.assertTrue(first['input_unchanged'])
            self.assertEqual(4,first['completed_tasks'])
            self.assertEqual(0,first['failed_tasks'])
            self.assertEqual(first['input_sha256'],second['input_sha256'])
            self.assertEqual(first['outcome_sha256'],second['outcome_sha256'])
            with self.assertRaisesRegex(ValueError,'new output directory'):
                run_workload(Path(directory)/'one',floors=2,robots_per_floor=1,tasks_per_day=4,days=1)
