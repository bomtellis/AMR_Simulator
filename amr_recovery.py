"""Atomic, per-editor recovery snapshots, separate from project revision history."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import uuid
import zlib

from amr_project import atomic_write, digest, drawing_entries, encoded, MAX_MEMBER_BYTES, MAX_TOTAL_BYTES

MAX_SNAPSHOT_BYTES = 32 * 1024 * 1024
PREFIX = "amr-recovery-asset:"


def read_asset(path, key):
    if path.stat().st_size > MAX_MEMBER_BYTES + 1024 * 1024:
        raise ValueError("Recovery drawing exceeds size limit")
    try:
        decoder = zlib.decompressobj()
        data = decoder.decompress(path.read_bytes(), MAX_MEMBER_BYTES + 1)
        if len(data) > MAX_MEMBER_BYTES or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
            raise ValueError("Recovery drawing exceeds size limit or is incomplete")
    except zlib.error as exc:
        raise ValueError("Recovery drawing checksum or compression mismatch") from exc
    if digest(data) != key:
        raise ValueError("Recovery drawing checksum mismatch")
    return data


class RecoveryStore:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.session_id = uuid.uuid4().hex

    @property
    def snapshot_path(self):
        return self.root / "drafts" / (self.session_id + ".json")

    def _snapshot_path(self, path):
        path = Path(path).resolve()
        if path.parent != self.root / "drafts" or not re.fullmatch(r"[0-9a-f]{32}\.json", path.name):
            raise ValueError("Not a recovery snapshot in this recovery folder")
        return path

    def capture(self, config, *, source_path=None, source_hash=None, revision_id=None):
        config = deepcopy(config)
        base = Path(source_path).resolve().parent if source_path else Path.cwd()
        warnings = []
        used_assets = {}
        for entry, suffix in drawing_entries(config):
            path = Path(entry["filepath"])
            if not path.is_absolute():
                path = base / path
            try:
                if path.stat().st_size > MAX_MEMBER_BYTES:
                    raise ValueError("Drawing exceeds the 256 MiB recovery limit")
                data = path.read_bytes()
            except (OSError, ValueError) as exc:
                entry["filepath"] = str(path.resolve())
                warnings.append(f"Drawing not copied: {path}: {exc}")
                continue
            key = digest(data)
            used_assets[key] = len(data)
            if len(data) > MAX_MEMBER_BYTES or sum(used_assets.values()) > MAX_TOTAL_BYTES:
                raise ValueError("Recovery drawings exceed size limits; previous snapshot retained")
            name = key + suffix
            target = self.root / "assets" / (name + ".z")
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                already_stored = target.exists() and read_asset(target, key) == data
            except (OSError, ValueError):
                already_stored = False
            if not already_stored:
                atomic_write(target, zlib.compress(data))
            entry["filepath"] = PREFIX + name
        body = {"schema_version": 1, "captured_utc": datetime.now(timezone.utc).isoformat(),
                "source_path": str(Path(source_path).resolve()) if source_path else None,
                "source_hash": source_hash, "revision_id": revision_id,
                "config": config, "warnings": warnings}
        data = encoded({"body": body, "sha256": digest(encoded(body))})
        if len(data) > MAX_SNAPSHOT_BYTES:
            raise ValueError("Recovery configuration exceeds 32 MiB; previous snapshot retained")
        self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(self.snapshot_path, data)
        return body

    def read(self, path):
        path = self._snapshot_path(path)
        if path.stat().st_size > MAX_SNAPSHOT_BYTES:
            raise ValueError("Recovery configuration exceeds size limit")
        envelope = json.loads(path.read_bytes())
        body = envelope["body"]
        if digest(encoded(body)) != envelope["sha256"]:
            raise ValueError("Recovery snapshot checksum mismatch")
        if body.get("schema_version") != 1 or not isinstance(body.get("config"), dict):
            raise ValueError("Unsupported recovery snapshot format")
        if not isinstance(body.get("warnings"), list) or not isinstance(body.get("captured_utc"), str):
            raise ValueError("Invalid recovery description")
        return body

    def list_snapshots(self):
        rows = []
        for path in sorted((self.root / "drafts").glob("*.json")):
            try:
                body = self.read(path)
                rows.append({"path": str(path), "source": body["source_path"] or "Untitled project",
                             "captured_utc": body["captured_utc"], "warnings": body["warnings"], "error": None})
            except Exception as exc:
                rows.append({"path": str(path), "source": path.name, "captured_utc": "",
                             "warnings": [], "error": str(exc)})
        return sorted(rows, key=lambda row: row["captured_utc"], reverse=True)

    def recover(self, path, directory):
        body = self.read(path)
        config = deepcopy(body["config"])
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        copied = set()
        total = 0
        for entry, suffix in drawing_entries(config):
            reference = entry["filepath"]
            if not reference.startswith(PREFIX):
                continue  # A missing external drawing was explicitly recorded at capture.
            match = re.fullmatch(re.escape(PREFIX) + r"([0-9a-f]{64})" + re.escape(suffix), reference)
            if not match:
                raise ValueError("Invalid recovery drawing reference")
            key = match.group(1)
            name = key + suffix
            asset = self.root / "assets" / (name + ".z")
            data = read_asset(asset, key)
            if key not in copied:
                total += len(data)
                copied.add(key)
            if total > MAX_TOTAL_BYTES or digest(data) != key:
                raise ValueError("Recovery drawing checksum or size mismatch")
            target = directory / name
            atomic_write(target, data)
            entry["filepath"] = str(target.resolve())
        return config, body

    def discard(self, path=None):
        # Never delete another editor's snapshot implicitly. Shared asset bytes
        # are retained; recovery asset cleanup is a separate maintenance task.
        self._snapshot_path(path or self.snapshot_path).unlink(missing_ok=True)
