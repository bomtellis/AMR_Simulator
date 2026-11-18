"""Lossless sparse event storage; detailed rows are materialised only by readers."""
from collections.abc import Sequence
import csv
import json
import os
from pathlib import Path
import sqlite3
import time
import zlib

FORMAT_VERSION = 3
BLOCK_MAX_EVENTS = 1000
BLOCK_MAX_BYTES = 1024 * 1024
INTERN_FIELDS = frozenset(('event_type', 'amr_id', 'task_id', 'payload', 'payload_instance_id',
    'from_location', 'to_location', 'start_node', 'end_node', 'lift_id', 'task_source', 'department_id',
    'journey_id', 'amr_location_before', 'amr_location_after', 'inventory_space_name',
    'source_rule_path', 'source_rule_id'))


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
    def __init__(self, path=None, *, readonly=False, baseline=None, memory_limit=None):
        self.path = Path(path) if path else None
        self.baseline = None
        self.readonly = readonly
        self.closed = True
        if self.path is not None and not readonly and self.path.exists():
            raise FileExistsError('Existing compact run evidence cannot be overwritten; choose a new run path')
        if readonly:
            self.connection = sqlite3.connect(self.path.resolve().as_uri() + '?mode=ro', uri=True)
            self.connection.execute('PRAGMA temp_store=MEMORY')
        else:
            self.connection = sqlite3.connect(str(path) if path else ':memory:', check_same_thread=False)
            self.closed = False
            if self.path is None:
                self.connection.execute('PRAGMA temp_store=MEMORY')
                if memory_limit is not None:
                    page_size = self.connection.execute('PRAGMA page_size').fetchone()[0]
                    pages = max(1, memory_limit // page_size)
                    self.connection.execute(f'PRAGMA max_page_count={pages}')
            self.connection.executescript('''
                PRAGMA journal_mode=DELETE;
                PRAGMA synchronous=NORMAL;
                CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS layouts(id INTEGER PRIMARY KEY, keys TEXT NOT NULL, defaults TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS symbols(id INTEGER PRIMARY KEY, value TEXT UNIQUE NOT NULL);
                CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY, sim_time REAL, layout INTEGER NOT NULL,
                    data INTEGER NOT NULL, kind INTEGER NOT NULL, playback INTEGER NOT NULL);
                CREATE INDEX IF NOT EXISTS events_kind ON events(kind,seq);
                CREATE TABLE IF NOT EXISTS event_blocks(id INTEGER PRIMARY KEY, data BLOB NOT NULL);
            ''')
            self.connection.execute('INSERT INTO metadata VALUES (?,?)', ('event_format_version', str(FORMAT_VERSION)))
        version = self.connection.execute("SELECT value FROM metadata WHERE key='event_format_version'").fetchone()
        self.format_version = int(version[0]) if version else 1
        if self.format_version not in (1, 2, 3, 4):
            self.connection.close()
            raise ValueError('Unsupported compact event format version')
        self.layouts = {}
        self.by_keys = {}
        for identity, keys, defaults in self.connection.execute('SELECT id,keys,defaults FROM layouts'):
            names, values = tuple(json.loads(keys)), json.loads(defaults)
            self.layouts[identity] = (names, values)
            self.by_keys[(names, values[names.index('event_type')] if 'event_type' in names else '')] = identity
        self.symbols = dict(self.connection.execute('SELECT id,value FROM symbols'))
        self.by_symbol = {value: key for key, value in self.symbols.items()}
        self.buffer = []
        self.last_flush = time.monotonic()
        self.stages = []
        self._decoded_block_id = None
        self._decoded_block = {}
        self.closed = False
        try:
            from amr_event_delta import Baseline
            if readonly and self.format_version == 4:
                description = self.connection.execute("SELECT value FROM metadata WHERE key='baseline'").fetchone()
                if description is None:
                    raise ValueError('Reduced event evidence is missing its baseline reference')
                description = json.loads(description[0])
                self.baseline = Baseline(self.path, self.path.parent / description['path'], description['sha256'])
            elif baseline is not None:
                if readonly:
                    raise ValueError('Cannot change the baseline of saved evidence')
                self.baseline = Baseline(self.path, baseline)
                self.format_version = 4
                self.connection.execute("UPDATE metadata SET value='4' WHERE key='event_format_version'")
                self.connection.execute('INSERT INTO metadata VALUES (?,?)', ('baseline', json.dumps(self.baseline.description)))
        except Exception:
            self.connection.close()
            self.closed = True
            raise

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
        layout_key = (keys, row.get('event_type', ''))
        identity = self.by_keys.get(layout_key)
        if identity is None:
            identity = len(self.layouts) + 1
            # JSON snapshot isolates mutable input values and preserves field types.
            defaults = json.loads(json.dumps(values, ensure_ascii=False, allow_nan=False))
            self.layouts[identity] = (keys, defaults)
            self.by_keys[layout_key] = identity
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
        if self.baseline is not None:
            from amr_event_delta import difference, packed
            baseline_sequence, original = self.baseline.next_row(row.get('event_type', ''))
            if original is not None and original.get('event_type') == row.get('event_type'):
                delta = []
                for index, (key, value) in enumerate(zip(keys, values)):
                    # Event IDs retain this run's prefix, including after gaps.
                    if key == 'event_id':
                        prefix, number = defaults[index].rsplit(':', 1)
                        base = prefix + ':' + str(sequence).zfill(len(number))
                    else:
                        base = original.get(key, defaults[index])
                    patch = difference(value, base)
                    if patch != [0]:
                        delta.append((index, patch))
                encoded = packed(dict(b=baseline_sequence, d=delta))
                # New or extensively changed events retain the ordinary sparse
                # representation when that is smaller than a baseline patch.
                if len(encoded) < len(data):
                    data = encoded
        # Keep staged rows uncompressed. Committed batches share compression
        # while SQL retains each event's identity, time and filter columns.
        self.buffer.append((sequence, float(precise_time if precise_time is not None else row.get('sim_time_sec', 0) or 0),
                            identity, data, self.symbol(row.get('event_type', '')), int(playback)))
        if len(self.buffer) >= 1000 or time.monotonic() - self.last_flush >= 1:
            self.flush()

    def begin_stage(self):
        self.stages.append((len(self.buffer), len(self.layouts), len(self.symbols),
                            dict(self.baseline.positions) if self.baseline is not None else None))

    def end_stage(self, committed):
        boundary, layout_count, symbol_count, positions = self.stages.pop()
        if not committed:
            if self.baseline is not None:
                self.baseline.positions = positions
            del self.buffer[boundary:]
            self.connection.execute('DELETE FROM layouts WHERE id>?', (layout_count,))
            self.connection.execute('DELETE FROM symbols WHERE id>?', (symbol_count,))
            self.layouts = {key: value for key, value in self.layouts.items() if key <= layout_count}
            self.by_keys = {(names, defaults[names.index('event_type')] if 'event_type' in names else ''): key
                            for key, (names, defaults) in self.layouts.items()}
            self.symbols = {key: value for key, value in self.symbols.items() if key <= symbol_count}
            self.by_symbol = {value: key for key, value in self.symbols.items()}
        if len(self.buffer) >= 1000 or time.monotonic() - self.last_flush >= 1:
            self.flush()

    def flush(self):
        if self.closed or self.readonly or self.stages:
            return
        if self.buffer:
            self.connection.execute('SAVEPOINT event_flush')
            try:
                rows, payloads, size = [], [], 2
                for record in self.buffer:
                    sequence, _, _, data, _, _ = record
                    payload = b'[' + str(sequence).encode('ascii') + b',' + data.encode('utf-8') + b']'
                    if rows and (len(rows) >= BLOCK_MAX_EVENTS or size + len(payload) + 1 > BLOCK_MAX_BYTES):
                        self._write_block(rows, payloads)
                        rows, payloads, size = [], [], 2
                    rows.append(record)
                    payloads.append(payload)
                    size += len(payload) + 1
                if rows:
                    self._write_block(rows, payloads)
                self.connection.execute('RELEASE event_flush')
            except Exception:
                # SQLITE_FULL may already have rolled back the entire transaction.
                if self.connection.in_transaction:
                    self.connection.execute('ROLLBACK TO event_flush')
                    self.connection.execute('RELEASE event_flush')
                raise
        self.connection.commit()
        self.buffer.clear()
        self.last_flush = time.monotonic()

    def _write_block(self, rows, payloads):
        identity = rows[0][0]
        payload = zlib.compress(b'[' + b','.join(payloads) + b']', level=3)
        self.connection.execute('INSERT INTO event_blocks VALUES (?,?)', (identity, payload))
        self.connection.executemany('INSERT INTO events VALUES (?,?,?,?,?,?)',
            ((seq, exact, layout, identity, kind, playback)
             for seq, exact, layout, _data, kind, playback in rows))

    def iter_rows(self, fields=None, *, event_types=None, playback_only=False, time_range=None):
        if self.closed:
            yield from iter_events(self.path, fields, event_types=event_types, playback_only=playback_only,
                                   time_range=time_range)
            return
        wanted = set(fields) if fields is not None else None
        kinds = {self.by_symbol[value] for value in event_types if value in self.by_symbol} if event_types is not None else None
        clauses, parameters = [], []
        if kinds is not None:
            clauses.append('kind IN (' + ','.join('?' for _ in kinds) + ')')
            parameters.extend(kinds)
        if playback_only:
            clauses.append('playback=1')
        if time_range is not None:
            clauses.append('sim_time BETWEEN ? AND ?')
            parameters.extend(time_range)
        query = 'SELECT seq,sim_time,layout,data,kind,playback FROM events'
        if clauses:
            query += ' WHERE ' + ' AND '.join(clauses)
        for sequence, exact, identity, data, _, _ in self.connection.execute(query + ' ORDER BY seq', parameters):
            yield self._decode(identity, data, wanted, sequence, exact)
        for sequence, exact, identity, data, kind, playback in self.buffer:
            if ((kinds is None or kind in kinds) and (not playback_only or playback)
                    and (time_range is None or exact is not None and time_range[0] <= exact <= time_range[1])):
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
        if isinstance(data, int) and self.format_version >= 3:
            if self._decoded_block_id != data:
                block = self.connection.execute('SELECT data FROM event_blocks WHERE id=?', (data,)).fetchone()
                if block is None:
                    raise ValueError('Missing compressed event block')
                # Only one block is cached, independent of the total run size.
                self._decoded_block = dict(json.loads(zlib.decompress(block[0])))
                self._decoded_block_id = data
            try:
                changes = self._decoded_block[sequence]
            except KeyError:
                raise ValueError('Event is missing from its compressed block') from None
        else:
            changes = self._decode_row_data(data)
        if isinstance(changes, dict):
            from amr_event_delta import restore
            if self.baseline is None:
                raise ValueError('Event differences require a normal-operation baseline')
            original = self.baseline.row(changes['b'])
            if original is None:
                raise ValueError('Missing baseline event')
            for name in names:
                if name != 'event_id' and (wanted is None or name in wanted):
                    row[name] = original.get(name, row[name])
            for index, patch in changes['d']:
                name = names[index]
                if wanted is None or name in wanted:
                    row[name] = restore(patch, row[name])
            changes = []
        for index, value in changes:
            name = names[index]
            if wanted is None or name in wanted:
                row[name] = self.symbols[value['s']] if name in INTERN_FIELDS and isinstance(value, dict) and set(value) == {'s'} else value
        # Readers must not be able to mutate layout defaults or cached blocks.
        for key, value in tuple(row.items()):
            if isinstance(value, (dict, list)):
                row[key] = json.loads(json.dumps(value))
        return row

    def _decode_row_data(self, data):
        """Legacy format-1/2 rows and unflushed format-3 rows share this path."""
        if isinstance(data, bytes):
            if self.format_version < 2:
                raise ValueError('Compressed event in a legacy compact store')
            data = zlib.decompress(data)
        return json.loads(data)

    def __len__(self):
        if self.closed:
            reader = sqlite3.connect(self.path.resolve().as_uri() + '?mode=ro', uri=True)
            try:
                return reader.execute('SELECT COUNT(*) FROM events').fetchone()[0]
            finally:
                reader.close()
        return self.connection.execute('SELECT COUNT(*) FROM events').fetchone()[0] + len(self.buffer)

    def close(self, *, flush=True):
        if not self.closed:
            try:
                if flush:
                    self.flush()
            finally:
                self.connection.close()
                if self.baseline is not None:
                    self.baseline.close()
                self.closed = True

    def seal_memory(self):
        if self.path is not None or self.closed or self.stages:
            raise ValueError('Only an open memory event store can be sealed.')
        self.flush()
        self.connection.execute('PRAGMA query_only=ON')
        self.readonly = True
        return (self.connection.execute('PRAGMA page_count').fetchone()[0]
                * self.connection.execute('PRAGMA page_size').fetchone()[0])

    def __del__(self):
        if not getattr(self, 'closed', True):
            self.connection.close()
            if self.baseline is not None:
                self.baseline.close()


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


def iter_events(path, fields=None, *, event_types=None, playback_only=False, time_range=None):
    path = Path(path)
    if path.suffix == '.sqlite':
        store = EventStore(path, readonly=True)
        try:
            yield from store.iter_rows(fields, event_types=event_types, playback_only=playback_only,
                                       time_range=time_range)
        finally:
            store.close()
    else:
        with path.open(encoding='utf-8-sig', newline='') as stream:
            for row in csv.DictReader(stream):
                if event_types is None or row.get('event_type') in event_types:
                    if time_range is not None:
                        try:
                            elapsed = float(row.get('sim_time_sec', ''))
                        except (TypeError, ValueError):
                            continue
                        if not time_range[0] <= elapsed <= time_range[1]:
                            continue
                    yield row


def iter_event_text(path, *, playback_only=False):
    """Expose the same strings as a CSV reader, without materialising a CSV."""
    if Path(path).suffix == '.sqlite':
        store = EventStore(path, readonly=True)
        try:
            yield from iter_store_event_text(store, playback_only=playback_only)
        finally:
            store.close()
        return
    for row in iter_events(path, playback_only=playback_only):
        yield {key: '' if value is None else str(value) for key, value in row.items()}


def iter_store_event_text(store, *, playback_only=False):
    headers = store.connection.execute("SELECT value FROM metadata WHERE key='report_headers'").fetchone()
    fields = json.loads(headers[0])['steps_csv'] if headers else None
    for row in store.iter_rows(fields, playback_only=playback_only):
        yield {key: '' if value is None else str(value) for key, value in row.items()}


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
