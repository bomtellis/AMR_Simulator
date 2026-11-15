"""Process isolation, RAM protection, reproducible batches and complete cancellation."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from amr_scenario_study import create_study, evaluate, default_settings, validate_study
from amr_stress_resources import GIB, ProcessGroup, admission, memory_status, process_memory
from tests.test_scenario_study import config


class ResourceTests(unittest.TestCase):
    def test_default_eight_workers_and_ram_reserve_admission(self):
        settings = default_settings(config())
        self.assertEqual(8, settings['workers'])
        self.assertEqual(16, settings['ram_limit_gib'])
        policy = admission(settings, dict(total=64*GIB, available=38*GIB), GIB, GIB)
        self.assertEqual(8, policy['slots'])
        limited = admission(settings, dict(total=64*GIB, available=14*GIB), GIB, GIB)
        self.assertEqual(0, limited['slots'])
        limited = admission(settings, dict(total=64*GIB, available=38*GIB), 4*GIB, GIB)
        self.assertEqual(2, limited['slots'])

    def test_memory_probes_return_real_positive_values(self):
        system = memory_status()
        memory = process_memory(os.getpid())
        self.assertGreater(system['total'], 0)
        self.assertGreater(system['available'], 0)
        self.assertGreater(memory['private'], 0)

    @unittest.skipUnless(os.name == 'nt', 'Windows Job Object contract')
    def test_closing_job_object_terminates_assigned_process(self):
        group = ProcessGroup(GIB)
        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'],
                                 creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            group.assign(child.pid)
            self.assertIsNone(child.poll())
            group.close()
            child.wait(timeout=5)
            self.assertIsNotNone(child.poll())
        finally:
            group.close()
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)

    @unittest.skipUnless(os.name == 'nt', 'Windows aggregate memory ceiling')
    def test_job_object_rejects_allocation_above_memory_ceiling(self):
        with tempfile.TemporaryDirectory() as directory:
            gate, result = Path(directory)/'gate', Path(directory)/'result'
            code = "import sys,time; from pathlib import Path\nwhile not Path(sys.argv[1]).exists(): time.sleep(.01)\ntry:\n data=bytearray(256*1024**2)\nexcept MemoryError:\n Path(sys.argv[2]).write_text('limited')\nelse:\n Path(sys.argv[2]).write_text('allocated')"
            group = ProcessGroup(128*1024**2)
            child = subprocess.Popen([getattr(sys, '_base_executable', sys.executable), '-c', code, str(gate), str(result)],
                                     creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                group.assign(child.pid)
                gate.touch()
                child.wait(timeout=10)
                self.assertEqual('limited', result.read_text())
            finally:
                group.close()
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=5)


class ParallelStudyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def study(self, name, workers=8, budget=8):
        path = self.root / (name+'.stress.json')
        create_study(config(), path, dict(workers=workers, trial_budget=budget))
        return path

    def test_exited_worker_waits_for_launcher_without_false_ram_failure(self):
        import io
        from unittest.mock import Mock
        from amr_project_runs import write_json
        from amr_stress_execution import TrialPool
        request = self.root / 'finished.json'
        write_json(request.with_suffix('.result.json'), dict(id='trial', peak_memory_bytes=1024))
        process = Mock(pid=12345)
        process.poll.side_effect = [None, 0]
        pool = TrialPool.__new__(TrialPool)
        pool.state = dict(settings=default_settings(config()), results={}, inflight={'trial': str(request)},
                          active_runs={}, expected_trials=1)
        pool.active = {'trial': dict(process=process, output=io.StringIO(), request=request,
            spec=dict(id='trial', name='Finished trial'), memory=1024, fraction=1,
            phase='Trial complete', started=time.monotonic())}
        pool.last = 0
        pool.estimate = 256 * 1024 ** 2
        pool.checkpoint = Mock()
        pool.cancelled = lambda: False
        snapshots = []
        pool.feedback = snapshots.append
        system = dict(total=64 * GIB, available=48 * GIB)
        def memory(pid):
            if pid == 12345:
                raise ProcessLookupError('Worker has exited')
            return dict(rss=1024, private=1024, peak=1024)
        with patch.object(pool, '_read'), patch('amr_stress_execution.memory_status', return_value=system), \
             patch('amr_stress_execution.process_memory', side_effect=memory):
            self.assertTrue(pool.run([], 'Finishing trial'))
        self.assertIn('trial', pool.state['results'])
        self.assertFalse(pool.active)
        process.wait.assert_not_called()
        self.assertTrue(any(w['phase'] == 'Worker finishing' for s in snapshots for w in s['workers']))

    def test_one_and_eight_workers_choose_identical_candidates_and_ranking(self):
        snapshots = []
        one = evaluate(self.study('serial', workers=1), feedback=snapshots.append)
        many_snapshots = []
        many = evaluate(self.study('parallel'), feedback=many_snapshots.append)
        self.assertEqual(list(one['results']), list(many['results']))
        self.assertEqual(one['ranking'], many['ranking'])
        self.assertEqual(one['coverage'], many['coverage'])
        self.assertEqual(one['sample_queue'], many['sample_queue'])
        self.assertTrue(any(len(m.get('workers', [])) > 1 for m in many_snapshots))
        self.assertEqual('phase', many_snapshots[0]['type'])
        self.assertTrue(any(w.get('sim_time_sec') is not None for m in many_snapshots for w in m.get('workers', [])))

    def test_worker_and_ram_limits_can_change_without_changing_search(self):
        from amr_project_runs import read_json, write_json
        path = self.study('limits')
        state = read_json(path)
        state['settings'].update(workers=1, ram_limit_gib=4, reserve_ram_gib=4)
        validate_study(state)
        write_json(path, state)
        changed = evaluate(path)
        original = evaluate(self.study('original'))
        self.assertEqual(list(original['results']), list(changed['results']))
        self.assertEqual(original['ranking'], changed['ranking'])

    def test_cancel_stops_all_reported_worker_pids_and_resume_keeps_batch(self):
        snapshots = []
        path = self.study('cancel', budget=12)
        def cancel():
            return any(len(m.get('workers', [])) >= 2 for m in snapshots)
        state = evaluate(path, cancel=cancel, feedback=snapshots.append)
        self.assertEqual('cancelled', state['status'])
        pids = {w['pid'] for m in snapshots for w in m.get('workers', [])}
        self.assertGreaterEqual(len(pids), 2)
        for pid in pids:
            with self.assertRaises((OSError, FileNotFoundError, ProcessLookupError)):
                process_memory(pid)
        resumed = evaluate(path)
        uninterrupted = evaluate(self.study('uninterrupted', budget=12))
        self.assertEqual(list(uninterrupted['results']), list(resumed['results']))
        self.assertEqual(uninterrupted['ranking'], resumed['ranking'])

    def test_memory_pressure_prevents_any_worker_from_starting(self):
        path = self.study('memory')
        status = dict(total=64*GIB, available=GIB)
        messages = []
        with patch('amr_stress_execution.memory_status', return_value=status), \
             patch('amr_stress_execution.subprocess.Popen') as spawn:
            state = evaluate(path, feedback=messages.append,
                             cancel=lambda: any(m.get('phase') == 'Waiting for available RAM' for m in messages))
        self.assertEqual('cancelled', state['status'])
        spawn.assert_not_called()

    @unittest.skipUnless(os.name == 'nt', 'Windows coordinator crash containment')
    def test_killing_coordinator_stops_every_active_child(self):
        path = self.study('crash', budget=12)
        environment = os.environ.copy()
        environment['PYTHONPATH'] = os.pathsep.join(value for value in sys.path if value)
        environment['PYTHONIOENCODING'] = 'utf-8'
        child = subprocess.Popen([getattr(sys, '_base_executable', sys.executable), '-u',
            str(Path(__file__).resolve().parents[1]/'amr_app.py'), '--scenario-study', str(path)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8',
            env=environment, creationflags=subprocess.CREATE_NO_WINDOW)
        pids = set()
        try:
            deadline = time.monotonic()+30
            while time.monotonic() < deadline:
                line = child.stdout.readline()
                if not line:
                    break
                if line.startswith('STRESS '):
                    message = json.loads(line[7:])
                    if len(message.get('workers', [])) >= 2:
                        pids = {worker['pid'] for worker in message['workers']}
                        break
            self.assertGreaterEqual(len(pids), 2)
            child.kill()
            child.wait(timeout=5)
            remaining = set(pids)
            deadline = time.monotonic()+5
            while remaining and time.monotonic() < deadline:
                for pid in list(remaining):
                    try:
                        process_memory(pid)
                    except (OSError, ProcessLookupError):
                        remaining.remove(pid)
                time.sleep(.05)
            self.assertFalse(remaining)
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)
            child.stdout.close()


if __name__ == '__main__':
    unittest.main()
