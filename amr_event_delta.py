"""Lossless baseline references and data-only patches for reduced run evidence."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import zlib


def packed(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def difference(value, original):
    """Typed patches: equal, replacement, mapping edits, or list edits."""
    same = type(value) is type(original) and value == original
    if same and (not isinstance(value, (dict, list, float)) or packed(value) == packed(original)):
        return [0]
    replacement = [1, value]
    if isinstance(value, dict) and isinstance(original, dict):
        # Preserve insertion order as well as values (report generation uses it).
        if list(value) != list(original):
            return replacement
        changes = [[key, difference(item, original[key])] for key, item in value.items()]
        patch = [2, [[key, change] for key, change in changes if change != [0]]]
    elif isinstance(value, list) and isinstance(original, list) and len(value) == len(original):
        changes = [[i, difference(item, original[i])] for i, item in enumerate(value)]
        patch = [3, [[i, change] for i, change in changes if change != [0]]]
    else:
        return replacement
    return patch if len(packed(patch)) < len(packed(replacement)) else replacement


def restore(patch, original):
    if patch[0] == 0:
        return original
    if patch[0] == 1:
        return patch[1]
    if patch[0] not in (2, 3):
        raise ValueError('Invalid baseline difference')
    result = dict(original) if patch[0] == 2 else list(original)
    for key, change in patch[1]:
        result[key] = restore(change, original[key])
    return result


def checksum(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


class Baseline:
    def __init__(self, owner, path, expected=None):
        from amr_event_store import EventStore
        self.path = Path(path).resolve()
        if owner is None or self.path == Path(owner).resolve():
            raise ValueError('Reduced data needs a separate saved normal-operation baseline')
        try:
            actual = checksum(self.path)
            if expected is not None and actual != expected:
                raise ValueError('Reduced-data baseline checksum changed; restore the original baseline')
            # Reject chains before opening EventStore, including circular references.
            connection = sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True)
            try:
                version = connection.execute("SELECT value FROM metadata WHERE key='event_format_version'").fetchone()
                if version and int(version[0]) not in (1, 2, 3):
                    raise ValueError('Reduced data requires a full baseline, not another reduced run')
            finally:
                connection.close()
            self.store = EventStore(self.path, readonly=True)
        except (OSError, sqlite3.Error) as exc:
            raise ValueError(f'Reduced-data baseline is unavailable: {self.path}') from exc
        try:
            location = os.path.relpath(self.path, Path(owner).resolve().parent)
        except ValueError:  # Different Windows drives.
            location = str(self.path)
        self.description = dict(path=location, sha256=actual)
        self.positions = {}

    def next_row(self, kind):
        identity = self.store.by_symbol.get(kind)
        if identity is None:
            return None, None
        record = self.store.connection.execute(
            'SELECT layout,data,seq,sim_time FROM events WHERE kind=? AND seq>? ORDER BY seq LIMIT 1',
            (identity, self.positions.get(kind, -1))).fetchone()
        if record is None:
            return None, None
        self.positions[kind] = record[2]
        return record[2], self.store._decode(record[0], record[1], None, record[2], record[3])

    def row(self, sequence):
        record = self.store.connection.execute(
            'SELECT layout,data,seq,sim_time FROM events WHERE seq=?', (sequence,)).fetchone()
        return self.store._decode(record[0], record[1], None, record[2], record[3]) if record else None

    def close(self):
        self.store.close()


def report_blob(store, key, value):
    full = zlib.compress(packed(value).encode('utf-8'), level=6)
    if store.baseline is not None:
        source = store.baseline.store.connection.execute('SELECT value FROM metadata WHERE key=?', (key,)).fetchone()
        if source is not None:
            original = json.loads(zlib.decompress(source[0]))
            delta = b'AMRD1' + zlib.compress(packed(difference(value, original)).encode('utf-8'), level=6)
            if len(delta) < len(full):
                return delta
    return full


def read_report_blob(store, key, blob):
    if blob.startswith(b'AMRD1'):
        if store.baseline is None:
            raise ValueError('Reduced report state is missing its baseline')
        source = store.baseline.store.connection.execute('SELECT value FROM metadata WHERE key=?', (key,)).fetchone()
        if source is None:
            raise ValueError('Reduced report state is missing a baseline record')
        return restore(json.loads(zlib.decompress(blob[5:])), json.loads(zlib.decompress(source[0])))
    return json.loads(zlib.decompress(blob))
