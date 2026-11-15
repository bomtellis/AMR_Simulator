"""Lossless sparse event storage; detailed rows are materialised only by readers."""
from collections.abc import Sequence
import csv
import json
import os
from pathlib import Path
import sqlite3
import time

FORMAT_VERSION = 1
INTERN_FIELDS = frozenset(('event_type', 'amr_id', 'task_id', 'payload', 'payload_instance_id',
    'from_location', 'to_location', 'start_node', 'end_node', 'lift_id', 'task_source', 'department_id'))


class EventValues:
    """A shared schema and a flat value vector, without a wide per-event dict."""
    _indices = {}
    def __init__(self, names, values):
        if len(names) != len(values):
            raise ValueError('Event schema and values differ in length')
        self.names = names
        self.values = list(values)
        self.indices = self.index_map(names)
    @classmethod
    def index_map(cls, names):
        result = cls._indices.get(names)
        if result is None:
            result = {key: index for index, key in enumerate(names)}
            cls._indices[names] = result
        return result
    def get(self, key, default=None):
        index = self.indices.get(key)
        return default if index is None else self.values[index]
    def update(self, additions):
        for key, value in additions.items():
            index = self.indices.get(key)
            if index is None:
                self.names += (key,)
                self.values.append(value)
                self.indices = self.index_map(self.names)
            else:
                self.values[index] = value
    def __getitem__(self, key):
        return self.values[self.indices[key]]


class EventStore:
    def __init__(self, path=None, *, readonly=False):
        self.path = Path(path) if path else None
        self.readonly = readonly
        self.closed = True
        if self.path is not None and not readonly and self.path.exists():
            raise FileExistsError('Existing compact run evidence cannot be overwritten; choose a new run path')
        if readonly:
            self.connection = sqlite3.connect(self.path.resolve().as_uri() + '?mode=ro', uri=True)
        else:
            self.connection = sqlite3.connect(str(path) if path else ':memory:', check_same_thread=False)
            self.closed = False
            self.connection.executescript('''
                PRAGMA journal_mode=DELETE;
                PRAGMA synchronous=NORMAL;
                CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS layouts(id INTEGER PRIMARY KEY, keys TEXT NOT NULL, defaults TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS symbols(id INTEGER PRIMARY KEY, value TEXT UNIQUE NOT NULL);
                CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY, sim_time REAL, layout INTEGER NOT NULL,
                    data TEXT NOT NULL, kind INTEGER NOT NULL, playback INTEGER NOT NULL);
                CREATE INDEX IF NOT EXISTS events_kind ON events(kind,seq);
            ''')
        self.layouts = {}
        self.by_keys = {}
        for identity, keys, defaults in self.connection.execute('SELECT id,keys,defaults FROM layouts'):
            names, values = tuple(json.loads(keys)), json.loads(defaults)
            self.layouts[identity] = (names, values)
            self.by_keys[names] = identity
        self.symbols = dict(self.connection.execute('SELECT id,value FROM symbols'))
        self.by_symbol = {value: key for key, value in self.symbols.items()}
        self.buffer = []
        self.last_flush = time.monotonic()
        self.stages = []
        self.closed = False

    def symbol(self, value):
        identity = self.by_symbol.get(value)
        if identity is None:
            identity = len(self.symbols) + 1
            self.symbols[identity] = value
            self.by_symbol[value] = identity
            self.connection.execute('INSERT INTO symbols VALUES (?,?)', (identity, value))
        return identity

    def append(self, row, *, precise_time=None, playback=True):
        if self.closed or self.readonly:
            raise ValueError('Finalised event evidence cannot be changed')
        keys = row.names if isinstance(row, EventValues) else tuple(row)
        values = row.values if isinstance(row, EventValues) else list(row.values())
        identity = self.by_keys.get(keys)
        if identity is None:
            identity = len(self.layouts) + 1
            # JSON snapshot isolates mutable input values and preserves field types.
            defaults = json.loads(json.dumps(values, ensure_ascii=False, allow_nan=False))
            self.layouts[identity] = (keys, defaults)
            self.by_keys[keys] = identity
            self.connection.execute('INSERT INTO layouts VALUES (?,?,?)',
                (identity, json.dumps(keys), json.dumps(defaults, ensure_ascii=False, separators=(',', ':'))))
        _, defaults = self.layouts[identity]
        changed = []
        for index, (key, value) in enumerate(zip(keys, values)):
            if key == 'event_id':
                original = defaults[index]
                if (value.rsplit(':', 1)[0] == original.rsplit(':', 1)[0]
                        and len(value.rsplit(':', 1)[1]) == len(original.rsplit(':', 1)[1])):
                    continue
            if type(value) is type(defaults[index]) and value == defaults[index]:
                continue
            if key in INTERN_FIELDS and isinstance(value, str):
                value = {'s': self.symbol(value)}
            changed.append((index, value))
        data = json.dumps(changed, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
        sequence = int(row['event_id'].rsplit(':', 1)[1])
        self.buffer.append((sequence, float(precise_time if precise_time is not None else row.get('sim_time_sec', 0) or 0),
                            identity, data, self.symbol(row.get('event_type', '')), int(playback)))
        if len(self.buffer) >= 1000 or time.monotonic() - self.last_flush >= 1:
            self.flush()

    def begin_stage(self):
        self.stages.append((len(self.buffer), len(self.layouts), len(self.symbols)))

    def end_stage(self, committed):
        boundary, layout_count, symbol_count = self.stages.pop()
        if not committed:
            del self.buffer[boundary:]
            self.connection.execute('DELETE FROM layouts WHERE id>?', (layout_count,))
            self.connection.execute('DELETE FROM symbols WHERE id>?', (symbol_count,))
            self.layouts = {key: value for key, value in self.layouts.items() if key <= layout_count}
            self.by_keys = {value[0]: key for key, value in self.layouts.items()}
            self.symbols = {key: value for key, value in self.symbols.items() if key <= symbol_count}
            self.by_symbol = {value: key for key, value in self.symbols.items()}
        if len(self.buffer) >= 1000 or time.monotonic() - self.last_flush >= 1:
            self.flush()

    def flush(self):
        if self.closed or self.readonly or self.stages:
            return
        if self.buffer:
            self.connection.executemany('INSERT INTO events VALUES (?,?,?,?,?,?)', self.buffer)
            self.buffer.clear()
        self.connection.commit()
        self.last_flush = time.monotonic()

    def iter_rows(self, fields=None, *, event_types=None, playback_only=False):
        if self.closed:
            yield from iter_events(self.path, fields, event_types=event_types, playback_only=playback_only)
            return
        wanted = set(fields) if fields is not None else None
        kinds = {self.by_symbol[value] for value in event_types if value in self.by_symbol} if event_types is not None else None
        clauses, parameters = [], []
        if kinds is not None:
            clauses.append('kind IN (' + ','.join('?' for _ in kinds) + ')')
            parameters.extend(kinds)
        if playback_only:
            clauses.append('playback=1')
        query = 'SELECT seq,sim_time,layout,data,kind,playback FROM events'
        if clauses:
            query += ' WHERE ' + ' AND '.join(clauses)
        for sequence, exact, identity, data, _, _ in self.connection.execute(query + ' ORDER BY seq', parameters):
            yield self._decode(identity, data, wanted, sequence, exact)
        for sequence, exact, identity, data, kind, playback in self.buffer:
            if (kinds is None or kind in kinds) and (not playback_only or playback):
                yield self._decode(identity, data, wanted, sequence, exact)

    def _decode(self, identity, data, wanted, sequence, exact):
        names, defaults = self.layouts[identity]
        row = {name: value for name, value in zip(names, defaults) if wanted is None or name in wanted}
        if wanted is not None:
            row = {**{name: '' for name in wanted}, **row}
        if wanted is None or 'event_id' in wanted:
            prefix, number = row['event_id'].rsplit(':', 1)
            row['event_id'] = prefix + ':' + str(sequence).zfill(len(number))
        if wanted is not None and 'precise_time_sec' in wanted:
            row['precise_time_sec'] = exact
        for index, value in json.loads(data):
            name = names[index]
            if wanted is None or name in wanted:
                row[name] = self.symbols[value['s']] if name in INTERN_FIELDS and isinstance(value, dict) and set(value) == {'s'} else value
        # Readers must not be able to mutate layout defaults through a returned row.
        for key, value in tuple(row.items()):
            if isinstance(value, (dict, list)):
                row[key] = json.loads(json.dumps(value))
        return row

    def __len__(self):
        if self.closed:
            reader = sqlite3.connect(self.path.resolve().as_uri() + '?mode=ro', uri=True)
            try:
                return reader.execute('SELECT COUNT(*) FROM events').fetchone()[0]
            finally:
                reader.close()
        return self.connection.execute('SELECT COUNT(*) FROM events').fetchone()[0] + len(self.buffer)

    def close(self):
        if not self.closed:
            self.flush()
            self.connection.close()
            self.closed = True

    def __del__(self):
        if not getattr(self, 'closed', True):
            self.connection.close()


class EventRows(Sequence):
    def __init__(self, store):
        self.store = store
    def __len__(self):
        return len(self.store)
    def __iter__(self):
        return self.store.iter_rows()
    def __getitem__(self, index):
        if isinstance(index, slice):
            return list(self)[index]
        if index < 0:
            index += len(self)
        for position, row in enumerate(self):
            if position == index:
                return row
        raise IndexError(index)
    def __eq__(self, other):
        return list(self) == other
    def __deepcopy__(self, memo):
        return list(self)


def iter_events(path, fields=None, *, event_types=None, playback_only=False):
    path = Path(path)
    if path.suffix == '.sqlite':
        store = EventStore(path, readonly=True)
        try:
            yield from store.iter_rows(fields, event_types=event_types, playback_only=playback_only)
        finally:
            store.close()
    else:
        with path.open(encoding='utf-8-sig', newline='') as stream:
            for row in csv.DictReader(stream):
                if event_types is None or row.get('event_type') in event_types:
                    yield row


def export_rows(store_path, output_path, fieldnames, predicate=None, cancel=None, progress=None, *, playback_only=False):
    """Write an atomic, bounded-memory legacy export without changing canonical evidence."""
    import uuid
    output_path = Path(output_path)
    temporary = output_path.with_name(output_path.name + '.' + str(os.getpid()) + '.' + uuid.uuid4().hex + '.tmp')
    count = 0
    try:
        with temporary.open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            for row in iter_events(store_path, playback_only=playback_only):
                if cancel and cancel():
                    raise InterruptedError('Export cancelled; completed simulation evidence is retained.')
                if predicate is None or predicate(row):
                    writer.writerow(row)
                count += 1
                if progress and count % 1000 == 0:
                    progress(dict(phase='Expanding detailed output', events=count))
        os.replace(temporary, output_path)
    finally:
        temporary.unlink(missing_ok=True)
    return output_path
