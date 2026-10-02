"""Portable version-1 project archives. Simulation outputs are never collected.

Only configured DXF/PDF underlays are embedded. Revisions and drawings are
content-addressed; restore appends history. This is not a tamper-proof audit.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import uuid
import zipfile

SCHEMA_VERSION = 1
MAX_MEMBER_BYTES = 256 * 1024 * 1024
MAX_TOTAL_BYTES = 512 * 1024 * 1024
MAX_MEMBERS = 10000
ASSET_PREFIX = "amr-asset:"
DRAWINGS = {"floor_dxf_files": ".dxf", "floor_pdf_underlays": ".pdf"}


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":")).encode("utf-8")


def configuration_bytes(value):
    # Generation category iteration currently affects task IDs/order. Preserve
    # insertion order even though JSON object order is normally insignificant.
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":")).encode("utf-8")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def atomic_write(path, data):
    """Replace only after a complete flushed write, on the destination volume."""
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def drawing_entries(config):
    for key, suffix in DRAWINGS.items():
        entries = config.get(key, [])
        if not isinstance(entries, list):
            raise ValueError(f"{key} must be a list")
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError(f"{key} entries must be objects")
            if entry.get("filepath"):
                if not isinstance(entry["filepath"], str):
                    raise ValueError(f"{key} drawing paths must be text")
                yield entry, suffix


def asset_hash(reference, suffix):
    match = re.fullmatch(r"amr-asset:([0-9a-f]{64})" + re.escape(suffix), reference)
    if not match:
        raise ValueError(f"Invalid embedded drawing reference: {reference}")
    return match.group(1)


class Project:
    def __init__(self):
        self.project_id = uuid.uuid4().hex
        self.revisions = []
        self.configs = {}
        self.assets = {}
        self.path = None
        self._disk_hash = None
        self.external_results = {"version": 1, "root": None, "runs": []}

    @classmethod
    def open(cls, path):
        path = Path(path).resolve()
        project = cls()
        # Read one immutable byte snapshot; reject excessive expanded data before reading it.
        if path.stat().st_size > MAX_TOTAL_BYTES:
            raise ValueError("Project exceeds the 512 MiB archive limit")
        import io
        raw = path.read_bytes()
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members = archive.infolist()
            names = [m.filename for m in members]
            if len(names) != len(set(names)) or len(names) > MAX_MEMBERS:
                raise ValueError("Duplicate or excessive archive entries")
            if any(m.file_size > MAX_MEMBER_BYTES for m in members) or sum(m.file_size for m in members) > MAX_TOTAL_BYTES:
                raise ValueError("Project exceeds expanded size limits")
            for name in names:
                if name != "manifest.json" and not re.fullmatch(r"(?:configs/[0-9a-f]{64}\.json|assets/[0-9a-f]{64})", name):
                    raise ValueError(f"Unsupported archive entry: {name}")
            manifest = json.loads(archive.read("manifest.json"))
            if not isinstance(manifest, dict) or manifest.get("schema_version") != SCHEMA_VERSION:
                raise ValueError("Unsupported project version; no automatic migration is available")
            if manifest.get("format") != "amrproj":
                raise ValueError("Not an AMR project")
            project.project_id = manifest["project_id"]
            if not isinstance(project.project_id, str) or not re.fullmatch(r"[0-9a-f]{32}", project.project_id):
                raise ValueError("Invalid project identifier")
            project.revisions = manifest["revisions"]
            project.external_results = manifest.get("external_results", {"version": 1, "root": None, "runs": []})
            if not isinstance(project.revisions, list) or not project.revisions:
                raise ValueError("Project has no revision history")
            for name in names:
                if name == "manifest.json":
                    continue
                data = archive.read(name)
                key = Path(name).stem
                if digest(data) != key:
                    raise ValueError(f"Content checksum mismatch: {name}")
                if name.startswith("configs/"):
                    config = json.loads(data)
                    if not isinstance(config, dict):
                        raise ValueError("Configuration must be an object")
                    if digest(configuration_bytes(config)) != key:
                        raise ValueError("Configuration is not in compact project format")
                    project.configs[key] = config
                else:
                    project.assets[key] = data
        seen = set()
        parent = None
        for rev in project.revisions:
            if not isinstance(rev, dict) or not isinstance(rev.get("id"), str) or rev["id"] in seen:
                raise ValueError("Invalid or duplicate revision identifier")
            if rev.get("parent") != parent or rev.get("config") not in project.configs:
                raise ValueError("Broken revision history")
            if not isinstance(rev.get("label"), str) or not isinstance(rev.get("created_utc"), str):
                raise ValueError("Invalid revision description")
            seen.add(rev["id"])
            parent = rev["id"]
        for config in project.configs.values():
            for entry, suffix in drawing_entries(config):
                if asset_hash(entry["filepath"], suffix) not in project.assets:
                    raise ValueError("A revision refers to a missing embedded drawing")
        project.path, project._disk_hash = path, digest(raw)
        project._validate_external_results()
        return project

    def _validate_external_results(self):
        settings = self.external_results
        if not isinstance(settings, dict) or settings.get("version") != 1 or not isinstance(settings.get("runs"), list):
            raise ValueError("Unsupported external-results settings")

        def locator(value):
            if (not isinstance(value, dict) or not isinstance(value.get("path"), str)
                    or not value["path"] or '\x00' in value["path"] or type(value.get("relative")) is not bool):
                raise ValueError("Invalid external-results location")
            if value["relative"] and (Path(value["path"]).is_absolute() or Path(value["path"]).drive):
                raise ValueError("Relative results location must not contain a drive or absolute path")
            if not value["relative"] and not Path(value["path"]).is_absolute():
                raise ValueError("Absolute results location must be absolute")

        if settings.get("root") is not None:
            locator(settings["root"])
        seen, locations = set(), set()
        revisions = {r['id']: r['config'] for r in self.revisions}
        for ref in settings["runs"]:
            if not isinstance(ref, dict):
                raise ValueError("Invalid saved run reference")
            key = ref.get("run_key")
            if not isinstance(key, str) or not re.fullmatch(r'[0-9a-f]{32}', key) or key in seen:
                raise ValueError("Invalid or duplicate saved run identity")
            seen.add(key)
            if not isinstance(ref.get("revision_id"), str) or revisions.get(ref['revision_id']) != ref.get("revision_config_sha256") or ref['revision_id'] not in revisions:
                raise ValueError("Saved run refers to an unknown project revision")
            if not isinstance(ref.get("software_sha256"), str) or not re.fullmatch(r'[0-9a-f]{64}', ref['software_sha256']):
                raise ValueError("Invalid saved run software fingerprint")
            if not isinstance(ref.get("name"), str):
                raise ValueError("Invalid saved run name")
            locator(ref.get("location"))
            location = self.resolve_results_location(ref['location'])
            if location in locations:
                raise ValueError("One results folder cannot represent two saved run identities")
            locations.add(location)

    def _location(self, directory, *, project_path=None):
        base = Path(project_path or self.path).parent
        directory = Path(directory).resolve()
        try:
            return {"relative": True, "path": Path(os.path.relpath(directory, base)).as_posix()}
        except ValueError:  # Different Windows drives cannot share a relative path.
            return {"relative": False, "path": str(directory)}

    def resolve_results_location(self, location):
        if self.path is None:
            raise ValueError("Save the project before linking results")
        path = Path(location['path'])
        return (self.path.parent / path if location['relative'] else path).resolve()

    def results_root(self):
        if self.path is None:
            raise ValueError("Save the project before selecting results")
        root = self.external_results.get('root')
        return self.resolve_results_location(root) if root else self.path.parent / (self.path.stem + '_results')

    def _save_external_results(self, settings):
        if self.path is None:
            raise ValueError("Save the project before linking results")
        if settings == self.external_results:
            return
        candidate = deepcopy(self)
        candidate.external_results = deepcopy(settings)
        candidate._validate_external_results()
        candidate._write(self.path)
        self.__dict__.update(candidate.__dict__)

    def set_results_root(self, directory):
        if self.path is None:
            raise ValueError("Save the project before selecting results")
        settings = deepcopy(self.external_results)
        settings['root'] = self._location(directory)
        self._save_external_results(settings)

    def remember_run(self, directory, manifest):
        """Persist an already inspected run, preserving its immutable identity."""
        if self.path is None:
            raise ValueError("Save the project before linking results")
        binding = manifest['project_binding']
        if binding['project_id'] != self.project_id or binding['run_key'] != manifest['run_key']:
            raise ValueError("Run belongs to a different project or identity")
        reference = {key: binding[key] for key in ('run_key', 'revision_id', 'revision_config_sha256')}
        reference.update(software_sha256=manifest['software']['sha256'], name=manifest['name'],
                         location=self._location(directory))
        settings = deepcopy(self.external_results)
        previous = next((r for r in settings['runs'] if r['run_key'] == reference['run_key']), None)
        if previous:
            for key in ('revision_id', 'revision_config_sha256', 'software_sha256'):
                if previous[key] != reference[key]:
                    raise ValueError("Relinked run does not match its saved revision/software identity")
            settings['runs'].remove(previous)
        settings['runs'].append(reference)
        self._save_external_results(settings)

    def _pack_config(self, config, base_dir):
        if not isinstance(config, dict):
            raise ValueError("Configuration must be an object")
        config = deepcopy(config)
        for entry, suffix in drawing_entries(config):
            reference = entry["filepath"]
            if reference.startswith(ASSET_PREFIX):
                if asset_hash(reference, suffix) not in self.assets:
                    raise ValueError("Embedded drawing is missing")
                continue
            path = Path(reference)
            if not path.is_absolute():
                path = Path(base_dir) / path
            if path.suffix.lower() != suffix:
                raise ValueError(f"Expected a {suffix} drawing: {path}")
            if path.stat().st_size > MAX_MEMBER_BYTES:
                raise ValueError(f"Drawing exceeds 256 MiB: {path}")
            data = path.read_bytes()
            key = digest(data)
            self.assets[key] = data
            if sum(map(len, self.assets.values())) > MAX_TOTAL_BYTES:
                raise ValueError("Embedded drawings exceed 512 MiB")
            entry["filepath"] = f"{ASSET_PREFIX}{key}{suffix}"
        return config

    def _append(self, config, label):
        key = digest(configuration_bytes(config))
        if self.revisions and self.revisions[-1]["config"] == key:
            return
        self.configs[key] = deepcopy(config)
        self.revisions.append({"id": uuid.uuid4().hex, "parent": self.revisions[-1]["id"] if self.revisions else None,
                               "config": key, "label": str(label),
                               "created_utc": datetime.now(timezone.utc).isoformat()})

    def configuration(self, revision_id=None):
        revision = self.revisions[-1] if revision_id is None else next((r for r in self.revisions if r["id"] == revision_id), None)
        if revision is None:
            raise ValueError("Unknown revision")
        return deepcopy(self.configs[revision["config"]])

    def materialize(self, directory, revision_id=None):
        config = self.configuration(revision_id)
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        for entry, suffix in drawing_entries(config):
            key = asset_hash(entry["filepath"], suffix)
            path = directory / (key + suffix)
            if not path.exists() or digest(path.read_bytes()) != key:
                atomic_write(path, self.assets[key])
            entry["filepath"] = str(path.resolve())
        return config

    def _write(self, path):
        self._validate_external_results()
        path = Path(path).resolve()
        if path.suffix.lower() != ".amrproj":
            raise ValueError("Project filenames must end in .amrproj")
        if path == self.path and (not path.exists() or digest(path.read_bytes()) != self._disk_hash):
            raise ValueError("Project changed on disk. Reopen it or save to a new file.")
        results = deepcopy(self.external_results)
        if self.path is not None and path != self.path:
            # Save As keeps existing external folders attached; moving the whole
            # project/results bundle instead preserves the stored relative paths.
            if results.get('root') is not None:
                results['root'] = self._location(self.resolve_results_location(results['root']), project_path=path)
            for ref in results['runs']:
                ref['location'] = self._location(self.resolve_results_location(ref['location']), project_path=path)
        manifest = {"format": "amrproj", "schema_version": SCHEMA_VERSION,
                    "project_id": self.project_id, "revisions": self.revisions,
                    "external_results": results}
        contents = {"manifest.json": encoded(manifest)}
        contents.update({f"configs/{key}.json": configuration_bytes(value) for key, value in self.configs.items()})
        contents.update({f"assets/{key}": data for key, data in self.assets.items()})
        if len(contents) > MAX_MEMBERS or any(len(v) > MAX_MEMBER_BYTES for v in contents.values()) or sum(map(len, contents.values())) > MAX_TOTAL_BYTES:
            raise ValueError("Project exceeds archive size limits")
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "w+b") as stream:
                with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                    for name, data in contents.items():
                        archive.writestr(name, data)
                stream.flush()
                os.fsync(stream.fileno())
            # Check again after building the archive to catch external changes during save.
            if path == self.path and (not path.exists() or digest(path.read_bytes()) != self._disk_hash):
                raise ValueError("Project changed during save; original was preserved")
            saved_hash = digest(Path(temporary).read_bytes())
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
        self.path, self._disk_hash = path, saved_hash
        self.external_results = results

    def save(self, path, config, *, base_dir=".", label="Saved changes"):
        candidate = deepcopy(self)
        candidate._append(candidate._pack_config(config, base_dir), label)
        candidate._write(path)
        self.__dict__.update(candidate.__dict__)

    def restore(self, revision_id, current_config, *, base_dir="."):
        if self.path is None:
            raise ValueError("Save the project before restoring")
        candidate = deepcopy(self)
        target = candidate.configuration(revision_id)
        candidate._append(candidate._pack_config(current_config, base_dir), "Preserved edits before restore")
        candidate._append(target, f"Restored {revision_id[:8]}")
        candidate._write(self.path)
        self.__dict__.update(candidate.__dict__)

    def compare(self, revision_id, current_config, *, base_dir="."):
        candidate = deepcopy(self)
        before = json.dumps(self.configuration(revision_id), indent=2, sort_keys=True, ensure_ascii=False).splitlines()
        after = json.dumps(candidate._pack_config(current_config, base_dir), indent=2, sort_keys=True, ensure_ascii=False).splitlines()
        return "\n".join(difflib.unified_diff(before, after, fromfile=f"Revision {revision_id[:8]}", tofile="Current edits", lineterm=""))

    def export_json(self, path, current_config, *, base_dir="."):
        """Publish drawings first and the JSON last; leave the open project unchanged."""
        path = Path(path).resolve()
        if path.suffix.lower() != ".json":
            raise ValueError("JSON exports must end in .json")
        candidate = deepcopy(self)
        candidate._append(candidate._pack_config(current_config, base_dir), "Export")
        config = candidate.materialize(path.parent / (path.stem + "_drawings"))
        # Absolute drawing paths retain compatibility with tools using the process cwd.
        atomic_write(path, json.dumps(config, indent=2, ensure_ascii=False, allow_nan=False).encode("utf-8"))
