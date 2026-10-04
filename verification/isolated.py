"""Fresh-process test modules with retained evidence and explicit process failures."""
import argparse
import faulthandler
import json
import os
from pathlib import Path
import subprocess
import signal
import sys
import time
import unittest


class IsolatedResult:
    def __init__(self):
        self.cases = []
        self.success = True

    def wasSuccessful(self):
        return self.success


def run_modules(directory, output, *, timeout=180, modules=None):
    directory, output = Path(directory).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    result = IsolatedResult()
    paths = sorted(directory.glob('test_*.py')) if modules is None else [directory / (name + '.py') for name in modules]
    with (output / 'tests.txt').open('w', encoding='utf-8') as combined:
        for path in paths:
            name = path.stem
            folder = output / 'modules' / name
            folder.mkdir(parents=True, exist_ok=True)
            evidence = folder / 'cases.json'
            # An interrupted repeat must never reuse an older successful result.
            evidence.unlink(missing_ok=True)
            problem = None
            started = time.perf_counter()
            with (folder / 'tests.txt').open('w', encoding='utf-8') as log:
                try:
                    process = subprocess.Popen([sys.executable, '-u', '-m', 'verification.isolated',
                        '--worker', str(path), '--output', str(folder)], stdout=log, stderr=subprocess.STDOUT,
                        start_new_session=os.name != 'nt', env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'})
                    returncode = process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    if os.name == 'nt':
                        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                                       stdout=log, stderr=subprocess.STDOUT, check=False)
                    else:
                        os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                    problem = f'Module exceeded {timeout:g} seconds; its process was terminated. See retained module log and stack snapshots.'
                except OSError as exc:
                    problem = f'Module process could not start: {exc}'
            cases = []
            if problem is None:
                try:
                    payload = json.loads(evidence.read_text(encoding='utf-8'))
                    cases = payload['cases']
                    if not cases or not isinstance(cases, list):
                        raise ValueError('No test cases were reported')
                    if returncode != 0 or not payload['successful']:
                        problem = f'Module failed (process exit {returncode}); see module log.'
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    problem = f'Module did not produce valid completed evidence: {exc}'
            result.cases.extend(cases)
            if problem:
                result.success = False
                if not any(case.get('status') in ('failed', 'error', 'unexpected_success') for case in cases):
                    result.cases.append(dict(id=f'{name}.process', status='error', details=problem,
                                             seconds=round(time.perf_counter()-started, 6)))
            combined.write((folder / 'tests.txt').read_text(encoding='utf-8', errors='replace'))
            combined.write('\n' + (problem or f'{name}: completed') + '\n')
            combined.flush()
            print(f'{name}: {problem or str(len(cases)) + " cases completed"}', flush=True)
    if not paths:
        result.success = False
        result.cases.append(dict(id='discovery.process', status='error', details='No test modules found.', seconds=0))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    path, output = args.worker.resolve(), args.output.resolve()
    from verification.run import EvidenceResult
    with (output / 'test-stacks.txt').open('w', encoding='utf-8') as stacks:
        faulthandler.dump_traceback_later(60, repeat=True, file=stacks)
        try:
            suite = unittest.defaultTestLoader.discover(str(path.parent), pattern=path.name)
            result = unittest.TextTestRunner(verbosity=2, resultclass=EvidenceResult).run(suite)
            (output / 'cases.json').write_text(json.dumps(dict(cases=result.cases,
                successful=result.wasSuccessful()), indent=2), encoding='utf-8')
        finally:
            faulthandler.cancel_dump_traceback_later()
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
