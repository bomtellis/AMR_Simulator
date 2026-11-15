"""Volatile project runs, using the normal compact evidence format on publication."""
from contextlib import closing, contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
from threading import Event, Lock
import uuid

from amr_project import (
    ASSET_PREFIX, MAX_MEMBER_BYTES, MAX_TOTAL_BYTES, Project, asset_hash,
    atomic_write, configuration_bytes, digest, drawing_entries,
)
from amr_project_runs import (
    MANIFEST, OUTPUTS, finish_run, inspect_run, timestamp, verified_termination, write_json,
)
from amr_run_evidence import config_hash, file_hash, run_evidence_data, software_snapshot, write_evidence_data

MEMORY_BUDGET = 1024 ** 3
CANONICAL = OUTPUTS['steps_csv'] + '.sqlite'


class RunMemoryLimit(ValueError):
    def __init__(self):
        super().__init__('Memory run limit reached. Save or discard earlier runs to free space, '
                         'shorten the simulation, or choose Save to disk.')


def check_cancelled(cancel):
    if cancel and cancel():
        raise InterruptedError('Operation cancelled')


class MemoryRuns:
    """One document owns the retained runs and shares immutable drawing bytes."""
    def __init__(self, budget=MEMORY_BUDGET):
        self.budget = budget
        self.runs = []
        self._retired = []

    def _owned(self):
        self._retired[:] = [run for run in self._retired if not run.released]
        return self.runs + self._retired

    def usage(self, extra=None):
        runs = self._owned() + ([extra] if extra is not None else [])
        unique_assets = {key: data for run in runs for key, data in run.assets.items()}
        return sum(run.byte_size for run in runs) + sum(map(len, unique_assets.values()))

    def prepare(self, config, base_dir, project=None, *, cancel=None):
        config = json.loads(configuration_bytes(config))
        assets = {}
        known = {key: data for run in self._owned() for key, data in run.assets.items()}
        remaining = self.budget - self.usage() - len(configuration_bytes(config))
        for entry, suffix in drawing_entries(config):
            check_cancelled(cancel)
            source = entry['filepath']
            if source.startswith(ASSET_PREFIX):
                key = asset_hash(source, suffix)
                if project is None or key not in project.assets:
                    raise ValueError('Embedded drawing is missing')
                data = project.assets[key]
            else:
                path = Path(base_dir) / source
                size = path.stat().st_size
                if path.suffix.lower() != suffix or size > MAX_MEMBER_BYTES:
                    raise ValueError(f'Invalid or oversized {suffix} drawing: {path}')
                checksum = hashlib.sha256()
                with path.open('rb') as stream:
                    for block in iter(lambda: stream.read(1024 ** 2), b''):
                        check_cancelled(cancel)
                        checksum.update(block)
                key = checksum.hexdigest()
                data = assets.get(key, known.get(key))
                if data is None:
                    if size > remaining:
                        raise RunMemoryLimit()
                    with path.open('rb') as stream:
                        data = stream.read(size + 1)
                    if len(data) != size or digest(data) != key:
                        raise ValueError(f'Drawing changed while preparing the run: {path}')
            if key not in assets and key not in known:
                remaining -= len(data)
                if remaining < 0:
                    raise RunMemoryLimit()
            assets[key] = known.get(key, data)
            entry['filepath'] = f'{ASSET_PREFIX}{key}{suffix}'
        frozen = configuration_bytes(config)
        if len(frozen) > MAX_MEMBER_BYTES or sum(map(len, assets.values())) + len(frozen) > MAX_TOTAL_BYTES:
            raise ValueError('Run inputs exceed the portable project archive limits.')
        run = MemoryRun(frozen, assets)
        check_cancelled(cancel)
        if self.usage(run) >= self.budget:
            raise RunMemoryLimit()
        return run

    def reserve(self, run):
        remaining = self.budget - self.usage(run)
        if remaining < 64 * 1024:  # SQLite schema plus room to record initial evidence.
            raise RunMemoryLimit()
        return remaining

    def add(self, run):
        self.runs.insert(0, run)

    def discard(self, run):
        self.runs.remove(run)
        run.dispose()
        if not run.released:
            self._retired.append(run)

    def clear(self):
        for run in self.runs[:]:
            self.discard(run)


class MemoryRun:
    def __init__(self, frozen, assets):
        now = datetime.now(timezone.utc)
        self.key = uuid.uuid4().hex
        self.name = f"run_{now:%Y%m%d_%H%M%S}_{self.key[:12]}"
        self.created = now.isoformat(timespec='seconds')
        self.started = self.completed = None
        self.status = 'prepared'
        self._frozen = frozen
        self.assets = assets
        self._checks = b''
        self._evidence = b''
        self._store = None
        self._store_bytes = 0
        self._lock = Lock()
        self._discarded = Event()
        self.released = False

    @property
    def config(self):
        frozen = self._frozen
        check_cancelled(self._discarded.is_set)
        return json.loads(frozen)

    @property
    def asset_refs(self):
        return frozenset(entry['filepath'] for entry, _ in drawing_entries(self.config))

    @property
    def byte_size(self):
        return len(self._frozen) + len(self._checks) + len(self._evidence) + self._store_bytes

    @property
    def evidence(self):
        evidence, frozen = self._evidence, self._frozen
        check_cancelled(self._discarded.is_set)
        return dict(json.loads(evidence), frozen_inputs=json.loads(frozen))

    @property
    def checks(self):
        checks = self._checks
        check_cancelled(self._discarded.is_set)
        return json.loads(checks)

    def accept_checks(self, report):
        if report.asset_refs != self.asset_refs or not report.can_run(self.config):
            raise ValueError('Inputs or checks changed; review the run again.')
        self._checks = configuration_bytes(report.to_dict())

    def execute(self, remaining, *, cancel=None, progress=None):
        def cancelled():
            return self._discarded.is_set() or (cancel is not None and cancel())

        try:
            with self._lock:
                return self._execute(remaining, cancel=cancelled, progress=progress)
        finally:
            if self._discarded.is_set():
                self._try_release()

    def _execute(self, remaining, *, cancel, progress):
        from simulator import Simulation
        if not self._checks or self.status != 'prepared':
            raise ValueError('Review the inputs before starting a new run.')
        simulation = None
        try:
            self.started = timestamp()
            self.status = 'running'
            check_cancelled(cancel)
            if progress:
                progress(dict(phase='Initializing simulation and preparing routes'))
            software = software_snapshot()
            simulation = Simulation(self.config, verbose=True, defer_exports=True,
                progress_callback=progress, memory_event_limit=remaining, cancel_requested=cancel)
            simulation.progress_update_interval = 1.0
            simulation.run()
            check_cancelled(cancel)
            if progress:
                progress(dict(phase='Finalizing evidence in memory'))
            size = simulation.finalize_memory_evidence()
            data = run_evidence_data(simulation, compact=True)
            if data['software']['sha256'] != software['sha256'] or software_snapshot()['sha256'] != software['sha256']:
                raise ValueError('Simulator software changed during execution.')
            check_cancelled(cancel)
            if data.get('termination'):
                rows = simulation.event_store.iter_rows()
                def checked_rows():
                    for row in rows:
                        check_cancelled(cancel)
                        yield row
                verified_termination(data, rows=checked_rows())
                status = 'partial'
            elif data['run_status'] == 'finished':
                status = 'complete'
            else:
                raise ValueError('Run did not complete.')
            if configuration_bytes(data.pop('frozen_inputs')) != self._frozen:
                raise ValueError('Recorded inputs do not match the checked run.')
            evidence = configuration_bytes(data)
            if len(evidence) + size > remaining:
                raise RunMemoryLimit()
            check_cancelled(cancel)
            self._evidence, self._store, self._store_bytes = evidence, simulation.event_store, size
            self.completed, self.status = timestamp(), status
            return self
        except sqlite3.OperationalError as exc:
            if getattr(exc, 'sqlite_errorcode', None) == sqlite3.SQLITE_FULL:
                raise RunMemoryLimit() from exc
            raise
        except MemoryError as exc:
            raise RunMemoryLimit() from exc
        finally:
            if simulation is not None and self._store is None:
                simulation.event_store.close(flush=False)

    def require_reviewable(self):
        if self.status not in ('complete', 'partial') or self._discarded.is_set():
            raise ValueError('This memory run is no longer available.')
        data = self.evidence
        if data.get('log_kind') != 'full' or not data.get('logging_enabled') or data.get('reduced_logging'):
            raise ValueError('This action requires full event evidence. This run used reduced logging.')
        return data

    @contextmanager
    def using_store(self, cancel=None):
        def check():
            check_cancelled(cancel)
            if self._discarded.is_set():
                raise InterruptedError('The memory run was discarded or saved.')
        check()
        while not self._lock.acquire(timeout=0.05):
            check()
        try:
            check()
            if self._store is None:
                raise ValueError('No completed memory evidence is available.')
            yield self._store
        finally:
            self._lock.release()
            if self._discarded.is_set():
                self._try_release()

    def _release(self):
        if self._store is not None:
            self._store.close(flush=False)
            self._store = None
        self.assets = {}
        self._frozen = self._checks = self._evidence = b''
        self._store_bytes = 0
        self.released = True

    def dispose(self):
        self._discarded.set()
        self._try_release()

    def _try_release(self):
        if self._lock.acquire(blocking=False):
            try:
                self._release()
            finally:
                self._lock.release()

    def _published_checks(self, config):
        # Only drawing addresses change. Keep the original findings and acknowledgements.
        from visualiser.check_dependencies import input_hash
        record = json.loads(self._checks)
        external = {entry['filepath']: True for entry, _ in drawing_entries(config)}
        record.update(config_sha256=config_hash(config), external_drawing_availability=external)
        for inputs in [*record['finding_inputs'].values(),
                       *(group['inputs'] for group in record['check_groups'].values())]:
            for key in inputs:
                inputs[key] = input_hash(config, key, external)
        return record

    def matches_source(self, config, base_dir):
        """Compare live inputs for the first Save run without repacking drawings."""
        try:
            config = json.loads(configuration_bytes(config))
            for entry, suffix in drawing_entries(config):
                path = entry['filepath']
                if not path.startswith(ASSET_PREFIX):
                    entry['filepath'] = f'{ASSET_PREFIX}{file_hash(Path(base_dir) / path)}{suffix}'
            return configuration_bytes(config) == self._frozen
        except (ValueError, OSError, TypeError):
            return False

    def publish(self, project, project_path=None, *, progress=None):
        """Return the committed project and run folder. Leave the input project untouched."""
        if self.status not in ('complete', 'partial'):
            raise ValueError('Only completed or verified partial memory runs can be saved.')
        candidate = deepcopy(project) if project is not None else Project()
        new_project = candidate.path is None
        path = Path(project_path if new_project else candidate.path).resolve()
        if path.suffix.lower() != '.amrproj':
            raise ValueError('Choose a filename ending in .amrproj.')
        if new_project and path.exists():
            raise FileExistsError('Choose a new project file. Existing projects are not replaced.')
        if not new_project and (not path.is_file() or file_hash(path) != candidate._disk_hash):
            raise ValueError('Project changed on disk. Keep the run in memory and resolve the external change before saving.')

        portable = self.config
        candidate.assets.update(self.assets)
        current = candidate.configuration() if candidate.revisions else None
        key = digest(self._frozen)
        revision = next((rev for rev in reversed(candidate.revisions) if rev['config'] == key), None)
        if revision is None:
            candidate._append(portable, f'Inputs for memory run {self.key[:8]}')
            revision = candidate.revisions[-1]
            if current is not None:
                candidate._append(current, 'Preserved current project after saving memory run')
        binding = dict(run_key=self.key, project_id=candidate.project_id, revision_id=revision['id'],
                       revision_config_sha256=key)
        root = candidate.results_root() if not new_project else path.parent / (path.stem + '_results')
        root = root.resolve()
        final = root / self.name
        if final.exists():
            raise FileExistsError('The run folder already exists.')
        root_existed = root.exists()
        root.mkdir(parents=True, exist_ok=True)
        staging = None
        published = False

        def remove_attempt(directory):
            if directory.parent != root or directory.is_symlink() or directory.resolve().parent != root:
                raise ValueError('Refusing to remove a folder outside the results location.')
            shutil.rmtree(directory)

        try:
            staging = Path(tempfile.mkdtemp(prefix='.memory-run-', dir=root))
            config = self.config
            for entry, suffix in drawing_entries(config):
                asset = asset_hash(entry['filepath'], suffix)
                filename = asset + suffix
                target = staging / 'drawings' / filename
                if not target.exists():
                    target.parent.mkdir(exist_ok=True)
                    atomic_write(target, self.assets[asset])
                entry['filepath'] = str(final / 'drawings' / filename)
            write_json(staging / 'project_configuration.json', portable)
            write_json(staging / 'config.json', config)
            checks = self._published_checks(config)
            write_json(staging / 'project_checks.json', checks)
            if progress:
                progress(dict(phase='Saving compact events'))
            with self.using_store() as store, closing(sqlite3.connect(staging / CANONICAL)) as target_db:
                store.connection.backup(target_db, pages=256)
            evidence = dict(self.evidence, project_binding=binding, frozen_inputs=config, config_sha256=config_hash(config))
            write_evidence_data(staging / CANONICAL, evidence)
            manifest = dict(schema_version=1, kind='amr_project_run', run_key=self.key, name=self.name,
                status='running', created_at=self.created, started_at=self.started, config_source=str(path),
                project_binding=binding, config_copy='config.json', config_sha256=file_hash(staging / 'config.json'),
                config_object_sha256=evidence['config_sha256'], software=evidence['software'],
                simulation_mode=evidence['simulation_mode'], outputs=OUTPUTS.copy(), canonical_events=CANONICAL,
                project_checks='project_checks.json', checks_sha256=file_hash(staging / 'project_checks.json'),
                checked_config_sha256=checks['config_sha256'])
            write_json(staging / MANIFEST, manifest)
            if progress:
                progress(dict(phase='Verifying and linking the saved run'))
            manifest = finish_run(staging, 0)
            if manifest['status'] != self.status:
                raise ValueError(manifest.get('error', 'Saved run status does not match memory evidence.'))
            manifest['completed_at'] = self.completed
            write_json(staging / MANIFEST, manifest)
            inspect_run(staging, candidate)
            candidate.external_results = candidate._run_settings(final, manifest, project_path=path)
            staging.rename(final)
            published = True
            candidate._write(path, exclusive=new_project)
            return candidate, final
        except BaseException:
            if published:
                remove_attempt(final)
            raise
        finally:
            if staging is not None and staging.exists():
                remove_attempt(staging)
            if not root_existed:
                try:
                    root.rmdir()
                except OSError:
                    pass
