"""Isolated CPU trials, bounded memory, deterministic batches and streamed feedback."""
from collections import deque
import contextlib
from copy import deepcopy
import ctypes
import json
import math
import os
from pathlib import Path
import random
import subprocess
import sys
import threading
import time
import uuid

from amr_project import Project
from amr_project_runs import PreparedRun, execute, finish_run, read_json, write_json
from amr_scenario_study import (validate_study, refresh_summary, scenario_config, run_metrics, resources,
    domain, config_hash, candidate_count, candidate_at, candidate_id, candidate_events, neighbours, ranking_key,
    reusable_baseline)
from amr_stress_resources import GIB, memory_status, process_memory, admission, ProcessGroup, wait_for_process_exit


def emit(message):
    print('STRESS ' + json.dumps(message, ensure_ascii=False), flush=True)


class QuietOutput:
    def write(self, text):
        return len(text)
    def flush(self):
        pass


def worker_main(request_path, *, supervise=True):
    request_path = Path(request_path)
    request = read_json(request_path)
    parent = request['parent_pid']
    gate = request_path.with_suffix('.gate')
    # Covers the small spawn/Job Object assignment gap and non-Windows hosts.
    def parent_watch():
        if os.name == 'nt':
            from ctypes import wintypes
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel.OpenProcess.restype = wintypes.HANDLE
            kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            handle = kernel.OpenProcess(0x100000, False, parent)
            if not handle:
                os._exit(3)
            try:
                while kernel.WaitForSingleObject(handle, 500) == 258:
                    pass
            finally:
                kernel.CloseHandle(handle)
        else:
            while os.getppid() == parent:
                time.sleep(.5)
        os._exit(3)
    if supervise:
        threading.Thread(target=parent_watch, daemon=True).start()
    emit(dict(type='ready', id=request['spec']['id'], pid=os.getpid()))
    deadline = time.monotonic() + 30
    while not gate.exists():
        if time.monotonic() >= deadline:
            return 3
        time.sleep(.05)
    state = read_json(request['study'])
    spec = request['spec']
    directory = None
    def update(message):
        emit(dict(type='trial', id=spec['id'], name=spec['name'], pid=os.getpid(), **message))
    try:
        update(dict(phase='Checking frozen trial inputs'))
        validate_study(state, verify_results=False)
        cfg = scenario_config(state['config'], spec['events'], spec['name'])
        project = Project()
        project_path = Path(state['root']) / (spec['id'] + '.amrproj')
        update(dict(phase='Preparing trial project'))
        project.save(project_path, cfg, label=spec['name'])
        draft = PreparedRun(project, Path(state['root']) / 'runs')
        update(dict(phase='Running project checks'))
        from visualiser.project_checks import check_project
        report = check_project(draft.config)
        if any(f.severity == 'error' for f in report.findings):
            draft.discard()
            raise ValueError('; '.join(f.message for f in report.findings if f.severity == 'error'))
        report.acknowledge_warnings()
        directory = draft.commit(report)
        update(dict(phase='Starting simulation', directory=str(directory)))
        with contextlib.redirect_stdout(QuietOutput()):
            # Preserve structured feedback while discarding terminal progress bars.
            def simulation_progress(message):
                original.write('STRESS ' + json.dumps(dict(type='trial', id=spec['id'], name=spec['name'],
                    pid=os.getpid(), **message)) + '\n')
                original.flush()
            execute(directory, progress=simulation_progress, runtime_backend=request.get('runtime_backend', 'compact'))
        validate_study(state, verify_results=False)
        update(dict(phase='Reconciling service outcomes'))
        baseline = None if spec['kind'] == 'baseline' else state['results']['baseline']['metrics']
        metrics = run_metrics(directory, baseline)
        record = dict(**spec, directory=str(directory), project=str(project_path), metrics=metrics,
                      peak_memory_bytes=process_memory(os.getpid())['peak'])
        write_json(request_path.with_suffix('.result.json'), record)
        update(dict(phase='Trial complete', fraction=1))
        return 0
    except Exception as exc:
        if directory and read_json(directory / 'run_manifest.json')['status'] in ('prepared', 'running'):
            finish_run(directory, 1, error=str(exc))
        emit(dict(type='error', id=spec['id'], message=str(exc)))
        return 1


original = sys.stdout


def persistent_worker_main(request_path):
    import gc
    mailbox = Path(request_path).with_suffix('.next')
    first = True
    while True:
        code = worker_main(request_path, supervise=first)
        first = False
        identity = read_json(request_path)['spec']['id']
        gc.collect()
        emit(dict(type='done', id=identity, code=code))
        if code:
            return code
        while not mailbox.exists():
            time.sleep(.05)
        request_path = Path(read_json(mailbox)['request'])
        mailbox.unlink()


class TrialPool:
    def __init__(self, path, state, checkpoint, cancelled, feedback, runtime_backend='compact'):
        self.runtime_backend = runtime_backend
        self.path, self.state, self.checkpoint = path, state, checkpoint
        self.cancelled, self.feedback = cancelled, feedback
        self.active = {}
        self.idle = []
        self.last = 0
        self.estimate = max((r.get('peak_memory_bytes', 0) for r in state['results'].values()), default=256 * 1024 ** 2)
        own = process_memory(os.getpid())['private']
        policy = admission(state['settings'], memory_status(), self.estimate, own)
        if policy['limit'] <= own + 64 * 1024 ** 2:
            raise ValueError('Study RAM limit is too small for the coordinator. Increase the RAM limit.')
        self.group = ProcessGroup(policy['limit'] - own)
        self.policy = policy

    def stop(self):
        self.group.close()
        for identity, job in list(self.active.items()):
            if job['process'].poll() is None:
                job['process'].kill()
            job['process'].wait(timeout=10)
            if job.get('worker_pid'): wait_for_process_exit(job['worker_pid'])
            job['output'].close()
            self._abandon(identity, job)
        self.active.clear()
        for job in self.idle:
            if job['process'].poll() is None:
                job['process'].kill()
            job['process'].wait(timeout=10)
            if job.get('worker_pid'): wait_for_process_exit(job['worker_pid'])
            job['output'].close()
        self.idle.clear()
        self.checkpoint()

    def _abandon(self, identity, job):
        directory = job.get('directory')
        # The worker may have reached preparation before its progress was read.
        if not directory:
            for line in Path(job['log']).read_text(encoding='utf-8', errors='replace').splitlines():
                if line.startswith('STRESS '):
                    message = json.loads(line[7:])
                    directory = message.get('directory', directory)
        if directory and read_json(Path(directory) / 'run_manifest.json')['status'] in ('prepared', 'running'):
            finish_run(directory, -1, cancelled=True)
        self.state.get('active_runs', {}).pop(identity, None)

    def _start(self, spec):
        validate_study(self.state, verify_results=False)
        requests = Path(self.state['root']) / 'requests'
        requests.mkdir(exist_ok=True)
        path = requests / (spec['id'] + '-' + uuid.uuid4().hex[:12] + '.json')
        write_json(path, dict(study=str(self.path), spec=spec, parent_pid=os.getpid(), runtime_backend=self.runtime_backend))
        log = path.with_suffix('.log')
        if self.idle:
            job = self.idle.pop()
            job.update(request=path, spec=spec, phase='Starting trial in reused worker',
                       fraction=0, started=time.monotonic(), buffer='')
            for key in ('done_code', 'exit_observed_at', 'error', 'directory', 'sim_time_sec',
                        'horizon_sec', 'completed', 'failed', 'pending'):
                job.pop(key, None)
            self.active[spec['id']] = job
            self.state.setdefault('inflight', {})[spec['id']] = str(path)
            self.checkpoint()
            write_json(job['mailbox'], dict(request=str(path)))
            return
        output = log.open('w', encoding='utf-8')
        environment = os.environ.copy()
        for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
            environment[key] = '1'
        environment['PYTHONUNBUFFERED'] = '1'
        environment['PYTHONIOENCODING'] = 'utf-8'
        worker_flag = '--scenario-worker' if self.runtime_backend == 'compact' else '--scenario-trial'
        if getattr(sys, 'frozen', False):
            command = [str(Path(sys.executable).with_name('AMRSimulatorWorker.exe')), worker_flag, str(path)]
        else:
            # Avoid the Windows virtualenv redirector spawning an uncontained second PID.
            # Retain the parent's package paths so workers use the same installed dependencies.
            environment['PYTHONPATH'] = os.pathsep.join(value for value in sys.path if value)
            executable = getattr(sys, '_base_executable', sys.executable)
            command = [executable, '-u', str(Path(__file__).resolve().with_name('amr_app.py')), worker_flag, str(path)]
        process = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT, env=environment,
            creationflags=(subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS) if os.name == 'nt' else 0)
        try:
            self.group.assign(process.pid)
            self.active[spec['id']] = dict(process=process, output=output, request=path, log=log,
                offset=0, buffer='', phase='Starting worker', spec=spec, memory=0, fraction=0,
                started=time.monotonic(), mailbox=path.with_suffix('.next'))
            if self.runtime_backend == 'reference':
                self.active[spec['id']].pop('mailbox')
            self.state.setdefault('inflight', {})[spec['id']] = str(path)
            self.checkpoint()
        except Exception:
            process.kill()
            process.wait(timeout=10)
            output.close()
            raise

    def _read(self, identity, job):
        with Path(job['log']).open(encoding='utf-8', errors='replace') as stream:
            stream.seek(job['offset'])
            text = stream.read()
            job['offset'] = stream.tell()
        job['buffer'] += text
        lines = job['buffer'].split('\n')
        job['buffer'] = lines.pop()
        for line in lines:
            if not line.startswith('STRESS '):
                continue
            message = json.loads(line[7:])
            if message.get('type') == 'ready':
                # A Windows venv redirector can create a different interpreter PID.
                if message['pid'] != job['process'].pid:
                    self.group.assign(message['pid'])
                job['worker_pid'] = message['pid']
                job['request'].with_suffix('.gate').touch()
            elif message.get('type') == 'error':
                job['error'] = message['message']
            elif message.get('type') == 'done':
                if message['id'] == identity:
                    job['done_code'] = message['code']
            else:
                job.update({key: value for key, value in message.items() if key in
                    ('phase', 'sim_time_sec', 'horizon_sec', 'completed', 'failed', 'pending', 'directory', 'fraction')})
                if 'sim_time_sec' in message:
                    job['fraction'] = min(.95, message['sim_time_sec'] / max(1, message['horizon_sec']) * .95)
                if 'directory' in message:
                    self.state.setdefault('active_runs', {})[identity] = message['directory']
                    self.checkpoint()

    def _report(self, phase, *, force=False, system=None, own=None):
        now = time.monotonic()
        if self.feedback and (force or now - self.last >= .5):
            system = system or memory_status()
            own = own or process_memory(os.getpid())
            used = sum(j['memory'] for j in list(self.active.values()) + getattr(self, 'idle', []))
            self.last = now
            workers = [dict(id=identity, name=j['spec']['name'], pid=j.get('worker_pid', j['process'].pid), phase=j['phase'],
                elapsed_sec=now-j['started'], memory_bytes=j['memory'], fraction=j['fraction'],
                **{key: j[key] for key in ('sim_time_sec', 'horizon_sec', 'completed', 'failed', 'pending') if key in j})
                for identity, j in self.active.items()]
            completed = len(self.state['results'])
            durations = [r['elapsed_sec'] for r in self.state['results'].values() if 'elapsed_sec' in r]
            capacity = max(1, len(self.active) + self.policy['slots'])
            eta = (sum(durations)/len(durations) * max(0, self.state['expected_trials']-completed)/capacity) if len(durations) > 1 else None
            self.feedback(dict(type='progress', phase=phase if workers else 'Waiting for available RAM',
                completed_trials=completed, total_trials=self.state['expected_trials'], workers=workers,
                requested_workers=self.state['settings']['workers'], ram_bytes=used + own['private'],
                idle_worker_pids=[j.get('worker_pid', j['process'].pid) for j in getattr(self, 'idle', [])],
                ram_limit_bytes=self.policy['limit'], available_ram_bytes=system['available'], reserve_ram_bytes=self.policy['reserve'],
                eta_sec=eta, fraction=(completed + sum(j['fraction'] for j in self.active.values())) / max(1, self.state['expected_trials'])))

    def run(self, specs, phase, max_workers=None):
        if not hasattr(self, 'idle'):
            self.idle = []
        waiting = deque(spec for spec in specs if spec['id'] not in self.state['results'])
        while waiting or self.active:
            if self.cancelled():
                self.stop()
                return False
            for identity, job in list(self.active.items()):
                self._read(identity, job)
                code = job.get('done_code', job['process'].poll())
                if code is None:
                    try:
                        memory = process_memory(job.get('worker_pid', job['process'].pid))
                        job['memory'] = max(memory['rss'], memory['private'])
                        self.estimate = max(self.estimate, memory['peak'])
                    except ProcessLookupError:
                        # Windows can observe the interpreter exit before its launcher
                        # signals Popen's process handle. There is no live worker RAM
                        # to monitor in this gap; keep polling without blocking progress
                        # or cancellation. The Job Object still caps the process tree.
                        job['memory'] = 0
                        job['phase'] = 'Worker finishing'
                        observed = job.setdefault('exit_observed_at', time.monotonic())
                        if time.monotonic() - observed > 5:
                            raise OSError('Trial worker exited but its launcher did not finish; '
                                          'study stopped and completed evidence is retained.')
                    except OSError:
                        if job['process'].poll() is None:
                            # The interpreter may exit just before Popen observes termination.
                            try:
                                job['process'].wait(timeout=.5)
                            except subprocess.TimeoutExpired:
                                raise OSError('Cannot monitor live worker RAM; study stopped for memory protection.')
                    continue
                self._read(identity, job)
                if code != 0:
                    self._abandon(identity, job)
                    raise ValueError(job.get('error') or f"Trial worker exited with code {code}; RAM limit or worker failure. Completed evidence is retained.")
                # Flush final trial progress even when it finishes between heartbeats.
                self._report(phase, force=True)
                record = read_json(job['request'].with_suffix('.result.json'))
                record['elapsed_sec'] = time.monotonic() - job['started']
                self.state['results'][identity] = record
                self.estimate = max(self.estimate, record['peak_memory_bytes'])
                self.state['inflight'].pop(identity, None)
                self.state.get('active_runs', {}).pop(identity, None)
                del self.active[identity]
                if 'mailbox' in job and job['process'].poll() is None:
                    self.idle.append(job)
                else:
                    job['output'].close()
                self.checkpoint()
            system = memory_status()
            own = process_memory(os.getpid())
            for job in self.idle:
                memory = process_memory(job.get('worker_pid', job['process'].pid))
                job['memory'] = max(memory['rss'], memory['private'])
            used = sum(j['memory'] for j in list(self.active.values()) + self.idle)
            self.policy = admission(self.state['settings'], system, self.estimate, max(own['rss'], own['private']), used, len(self.active))
            if (self.active or self.idle) and (system['available'] < self.policy['reserve'] or used + own['private'] > self.policy['limit']):
                # Release RAM promptly; the discarded trial stays in its deterministic batch for resume.
                self.stop()
                raise ValueError('Study stopped to protect background applications: system RAM reserve or study RAM limit was reached. Completed trials are retained; resume after freeing RAM or reducing workers.')
            # Reusing an admitted idle process needs no new interpreter allocation.
            # Include idle memory above and bound total process count independently.
            maximum = min(self.state['settings']['workers'], max(1, (os.cpu_count() or 1) - 2))
            slots = min(self.policy['slots'] + len(self.idle), maximum - len(self.active))
            if system['available'] < self.policy['reserve'] or used + own['private'] + max(0, self.policy['cost'] - min((j['memory'] for j in self.idle), default=0)) > self.policy['limit']:
                slots = self.policy['slots']
            if max_workers is not None:
                slots = min(slots, max_workers - len(self.active))
            for _ in range(min(slots, len(waiting))):
                self._start(waiting.popleft())
            self._report(phase, system=system, own=own)
            if waiting and not self.active and slots == 0 and self.policy['limit'] - own['private'] < self.policy['cost']:
                raise ValueError('Measured trial memory exceeds the study RAM limit. Increase the RAM limit or use a smaller model; completed evidence is retained.')
            time.sleep(.1)
        return True


def evaluate_parallel(path, cancel=None, progress=None, feedback=None, *, runtime_backend='compact'):
    from datetime import datetime, timedelta
    path = Path(path).resolve()
    started = time.monotonic()
    if feedback:
        feedback(dict(type='phase', phase='Loading and validating saved study'))
    state = read_json(path)
    validate_study(state, feedback=feedback)
    settings = state['settings']
    state.setdefault('trial_order', [])
    state.setdefault('pending_batch', [])
    state.setdefault('inflight', {})
    windows, effects = domain(settings)
    corridors = [r for r in resources(state['config']) if r[0] == 'corridor']
    overlap = sum(r in settings['assets'] for r in corridors) if (0, state['horizon_sec']/60) in windows and (0, 100) in effects else 0
    state['expected_trials'] = 1 + len(corridors) + min(settings['trial_budget'], candidate_count(settings)-overlap)
    def checkpoint():
        order = {identity: i for i, identity in enumerate(state['trial_order'])}
        state['results'] = dict(sorted(state['results'].items(), key=lambda pair: order.get(pair[0], -1)))
        refresh_summary(state)
        write_json(path, state)
    def cancelled():
        return bool((cancel and cancel()) or path.with_suffix(path.suffix + '.cancel').exists())
    def batch(specs, phase, limit=None):
        if not state['pending_batch']:
            state['pending_batch'] = specs
            for spec in specs:
                if spec['id'] not in state['trial_order']:
                    state['trial_order'].append(spec['id'])
            checkpoint()
        chosen = state['pending_batch']
        if progress:
            progress(len(state['results']) + 1, state['expected_trials'], phase)
        if not pool.run(chosen, phase, limit):
            return False
        state['pending_batch'] = []
        checkpoint()
        return True
    pool = None
    state.update(status='running')
    state.pop('error', None)
    checkpoint()
    try:
        # Recover fully finished children after a coordinator interruption.
        recovered = False
        for identity, request in sorted(state['inflight'].items(), key=lambda pair: pair[0] != 'baseline'):
            result = Path(request).with_suffix('.result.json')
            if result.exists():
                record = read_json(result)
                baseline = None if identity == 'baseline' else state['results']['baseline']['metrics']
                if run_metrics(record['directory'], baseline) != record['metrics']:
                    raise ValueError('Recovered trial differs from its verified evidence.')
                state['results'][identity] = record
                recovered = True
        state['inflight'] = {}
        checkpoint()
        if recovered:
            validate_study(state, feedback=feedback)
        if 'baseline' not in state['results']:
            reused = reusable_baseline(state, feedback=feedback, cancelled=cancelled)
            if reused:
                state['results']['baseline'] = reused
                if 'baseline' not in state['trial_order']:
                    state['trial_order'].insert(0, 'baseline')
                checkpoint()
                if feedback:
                    feedback(dict(type='phase', phase='Reusing existing normal-operation simulation: ' + reused['directory']))
        pool = TrialPool(path, state, checkpoint, cancelled, feedback, runtime_backend)
        if state['pending_batch']:
            saved_batch = state['pending_batch']
            if not batch(saved_batch, 'Resuming the saved trial batch',
                         1 if saved_batch[0]['kind'] == 'baseline' else None):
                state['status'] = 'cancelled'
                checkpoint()
                return state
        baseline = dict(id='baseline', kind='baseline', name='Normal operation', events=[])
        if 'baseline' not in state['results']:
            if not batch([baseline], 'Evaluating baseline and measuring memory', 1):
                state['status'] = 'cancelled'
                checkpoint()
                return state
        if not state['results']['baseline']['metrics']['passed']:
            metrics = state['results']['baseline']['metrics']
            raise ValueError('Stress test stopped: Baseline has incomplete service or tasks exceeding the configured assignment deferral limit. '
                f"{metrics['unmet_count']} unmet obligations, "
                f"{metrics['failed']} failed tasks and {metrics['pending']} pending tasks. "
                'Select Normal operation in Results and Investigate trial to review the evidence. '
                'Resolve baseline service before testing disruptions.')
        origin = datetime.fromisoformat(state['config']['simulation']['start_datetime'])
        windows, effects = domain(settings)
        corridors = []
        for kind, identity in resources(state['config']):
            if kind != 'corridor':
                continue
            spec = dict(id='corridor-' + config_hash(identity), kind='corridor', name='Block ' + identity,
                corridor=identity, events=[dict(resource_type=kind, resource_ids=[identity], availability_percent=0,
                    speed_factor=1, start_datetime=origin.isoformat(),
                    end_datetime=(origin + timedelta(seconds=state['horizon_sec'])).isoformat())])
            if [kind, identity] in settings['assets'] and (0, state['horizon_sec']/60) in windows and (0, 100) in effects:
                spec['candidate'] = [[settings['assets'].index([kind, identity]), windows.index((0, state['horizon_sec']/60)), effects.index((0, 100))]]
            corridors.append(spec)
        if not batch(corridors, 'Testing individual corridor blockages'):
            state['status'] = 'cancelled'
            checkpoint()
            return state
        count = candidate_count(settings)
        if not state['sample_generated']:
            rng = random.Random(settings['seed'])
            ranks = set()
            while len(ranks) < min(count, math.ceil(settings['trial_budget']/2)):
                ranks.add(rng.randrange(count))
            state['sample_queue'] = [candidate_at(settings, rank) for rank in sorted(ranks)]
            state['sample_sha256'] = config_hash(state['sample_queue'])
            state['sample_generated'] = True
            checkpoint()
        def tested():
            return {candidate_id(r['candidate']) for r in state['results'].values() if r.get('candidate')}
        def spec(candidate):
            identity = candidate_id(candidate)
            return dict(id=identity, kind='combined', name='Combination ' + identity[:8], candidate=candidate,
                        events=candidate_events(state['config'], settings, candidate))
        samples = [spec(c) for c in state['sample_queue'] if candidate_id(c) not in tested()]
        if not batch(samples, 'Evaluating sampled combinations'):
            state['status'] = 'cancelled'
            checkpoint()
            return state
        while state['coverage']['combined_trials'] < settings['trial_budget']:
            seen = tested()
            selected = []
            remaining = settings['trial_budget'] - state['coverage']['combined_trials']
            # Fixed width independent of available workers; choices use the previous full batch.
            for record in sorted((r for r in state['results'].values() if r.get('candidate') and r['metrics']['passed']), key=ranking_key):
                for candidate in neighbours(settings, record['candidate']):
                    identity = candidate_id(candidate)
                    if identity not in seen and len(selected) < min(8, remaining):
                        seen.add(identity)
                        selected.append(spec(candidate))
            offset = (settings['seed'] + state['coverage']['combined_trials']) % count
            for n in range(count):
                if len(selected) >= min(8, remaining):
                    break
                candidate = candidate_at(settings, (offset+n) % count)
                if candidate_id(candidate) not in seen:
                    seen.add(candidate_id(candidate))
                    selected.append(spec(candidate))
            if not selected and not state['pending_batch']:
                break
            if not batch(selected, 'Refining highest-impact passing combinations'):
                state['status'] = 'cancelled'
                checkpoint()
                return state
        state['status'] = 'complete'
        checkpoint()
        if feedback:
            feedback(dict(type='complete', phase='Study complete', completed_trials=len(state['results']),
                          total_trials=len(state['results']), elapsed_sec=time.monotonic()-started, fraction=1))
        return state
    except Exception as exc:
        state.update(status='failed', error=str(exc))
        checkpoint()
        raise
    finally:
        if pool:
            pool.stop()
