"""Process-isolated output expansion with cancellation and bounded memory."""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid

from amr_stress_resources import GIB, ProcessGroup, memory_status, process_memory


def export_worker(directory, outputs, gate, parent_pid):
    from amr_run_exports import ensure_exports
    from amr_stress_resources import watch_parent
    threading.Thread(target=watch_parent, args=(parent_pid,), daemon=True).start()
    print('EXPORT ' + json.dumps(dict(type='ready', pid=os.getpid())), flush=True)
    deadline = time.monotonic() + 30
    while not gate.exists():
        if time.monotonic() > deadline:
            return 3
        time.sleep(.05)
    def progress(message):
        print('EXPORT ' + json.dumps(message), flush=True)
    ensure_exports(directory, outputs, progress=progress)
    return 0


def expand_in_process(directory, outputs=('steps_csv',), *, cancel=None, progress=None):
    """Caller can be a GUI load job; only the isolated child expands records."""
    from amr_project_runs import read_json, OUTPUTS
    outputs = tuple(dict.fromkeys(outputs))
    source = Path(directory).resolve()
    standalone = source.is_file()
    from amr_run_review import verified_events, verified_standalone_events
    if standalone:
        _, _, canonical, _ = verified_standalone_events(source)
        directory = canonical.parent
        prefix = canonical.name.removesuffix('.sqlite').removesuffix('.csv')
        filenames = {key: prefix + '_' + name for key, name in OUTPUTS.items()}
        filenames['steps_csv'] = prefix + '.csv'
        registry = directory / (canonical.name + '.exports.json')
        lock = directory / (canonical.name + '.exports.lock')
    else:
        directory = source
        manifest = read_json(directory / 'run_manifest.json')
        if not manifest.get('canonical_events'):
            return
        verified_events(directory, allow_partial=True)
        filenames = OUTPUTS
        registry = directory / 'exports.json'
        lock = directory / '.exports.lock'
    if any(key not in OUTPUTS for key in outputs):
        raise ValueError('Unknown simulation output requested')
    if registry.exists():
        records = read_json(registry)
        if all(key in records and (directory / filenames[key]).exists() for key in outputs):
            from amr_run_exports import ensure_exports
            ensure_exports(source, outputs, cancel=cancel, progress=progress)
            return
    system = memory_status()
    reserve = min(system['total'] * .5, max(2 * GIB, system['total'] * .2))
    if system['available'] < reserve + 256 * 1024 ** 2:
        raise MemoryError('Not enough free RAM to expand outputs while preserving background applications')
    identity = uuid.uuid4().hex
    gate = directory / ('.export-' + identity + '.gate')
    log = directory / ('.export-' + identity + '.log')
    environment = os.environ.copy()
    environment['PYTHONPATH'] = os.pathsep.join(value for value in sys.path if value)
    environment['PYTHONIOENCODING'] = 'utf-8'
    environment['PYTHONUNBUFFERED'] = '1'
    for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
        environment[key] = '1'
    args = ['--export-run', str(source), '--outputs', ','.join(outputs),
            '--export-gate', str(gate), '--export-parent', str(os.getpid())]
    if getattr(sys, 'frozen', False):
        command = [str(Path(sys.executable).with_name('AMRSimulatorWorker.exe')), *args]
    else:
        command = [getattr(sys, '_base_executable', sys.executable), '-u',
                   str(Path(__file__).with_name('amr_app.py')), *args]
    group = ProcessGroup(min(2 * GIB, system['total'] * .5))
    process = None
    offset, buffer, child_pid = 0, '', None
    try:
        with log.open('w', encoding='utf-8') as stream:
            process = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT, env=environment,
                creationflags=(subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS) if os.name == 'nt' else 0)
        group.assign(process.pid)
        while True:
            if cancel and cancel():
                raise InterruptedError('Loading cancelled; completed simulation evidence is retained')
            with log.open(encoding='utf-8', errors='replace') as stream:
                stream.seek(offset)
                buffer += stream.read()
                offset = stream.tell()
            lines = buffer.split('\n')
            buffer = lines.pop()
            for line in lines:
                if line.startswith('EXPORT '):
                    message = json.loads(line[7:])
                    if message.get('type') == 'ready':
                        child_pid = message['pid']
                        if child_pid != process.pid:
                            group.assign(child_pid)
                        gate.touch()
                    elif progress:
                        progress(message)
            code = process.poll()
            if code is not None:
                if code:
                    raise RuntimeError('Output expansion failed; completed evidence is retained. ' +
                                       log.read_text(encoding='utf-8', errors='replace')[-2000:])
                return
            if memory_status()['available'] < reserve:
                raise MemoryError('Output expansion stopped to preserve free system RAM')
            time.sleep(.1)
    finally:
        group.close()
        if process is not None:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)
        if child_pid:
            from amr_stress_resources import wait_for_process_exit
            wait_for_process_exit(child_pid)
        gate.unlink(missing_ok=True)
        # Windows can retain redirected file handles briefly after signalling exit.
        deadline = time.monotonic() + 3
        while True:
            try:
                log.unlink(missing_ok=True)
                break
            except PermissionError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(.05)
        if lock.exists() and lock.read_text().strip() in {str(child_pid), str(getattr(process, 'pid', None))}:
            lock.unlink(missing_ok=True)
        if child_pid:
            for temporary in directory.glob(f'*.{child_pid}.*.tmp'):
                temporary.unlink(missing_ok=True)


def materialise_exports(source, outputs, *, destinations=None, cancel=None, progress=None):
    """Expand in the contained child, then publish explicit CLI paths in chunks."""
    from amr_run_exports import ensure_exports
    outputs = tuple(dict.fromkeys(outputs))
    expand_in_process(source, outputs, cancel=cancel, progress=progress)
    paths = ensure_exports(source, outputs, cancel=cancel)
    if not destinations:
        return paths
    def publish(original, target):
        original, target = Path(original).resolve(), Path(target).resolve()
        if original == target:
            return
        temporary = target.with_name(target.name + '.' + str(os.getpid()) + '.' + uuid.uuid4().hex + '.tmp')
        try:
            with original.open('rb') as reader, temporary.open('wb') as writer:
                while True:
                    if cancel and cancel():
                        raise InterruptedError('Export publication cancelled; completed evidence is retained')
                    chunk = reader.read(1024 * 1024)
                    if not chunk:
                        break
                    writer.write(chunk)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
    for key, target in destinations.items():
        if key not in paths:
            raise ValueError('Destination supplied for an output that was not requested')
        original = paths[key]
        publish(original, target)
        sidecar = Path(str(original) + '.run.json')
        if sidecar.exists():
            publish(sidecar, str(target) + '.run.json')
        paths[key] = Path(target).resolve()
    return paths
