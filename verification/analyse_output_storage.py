"""Read-only inventory and compression probes for recorded simulation evidence."""
import collections
import json
from pathlib import Path
import sqlite3
import sys
import time
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from amr_event_store import EventStore


def main():
    paths = sorted((p for root in ('ltn_results', 'output', 'outputs', 'verification/latest')
                    for p in Path(root).rglob('*.sqlite')), key=lambda p: p.stat().st_mtime, reverse=True)
    print('Recent stores:', [(str(p), p.stat().st_size) for p in paths[:8]], flush=True)
    source = EventStore('ltn_results/run_20261012_202248_2f6_trf6/simulation_steps.csv.sqlite', readonly=True)
    try:
        print('Event payload bytes:', source.connection.execute(
            'SELECT count(*),sum(length(data)) FROM events').fetchone(), flush=True)
        metadata = list(source.connection.execute('SELECT key,value FROM metadata'))
        print('Metadata:', collections.Counter({k: sum(len(v) for key, v in metadata if key.startswith(k))
              for k in ('report_records:', 'report_state', 'report_headers')}), flush=True)
        sample = EventStore()
        total = len(source)
        for offset in range(0, total, max(1, total // 20)):
            for seq, exact, layout, data, playback in source.connection.execute(
                    'SELECT seq,sim_time,layout,data,playback FROM events WHERE seq>? ORDER BY seq LIMIT 1000', (offset,)):
                sample.append(source._decode(layout, data, None, seq, exact), precise_time=exact, playback=bool(playback))
        sample.flush()
        rows = list(sample.connection.execute('SELECT seq,layout,data FROM events ORDER BY seq'))
        if sample.format_version >= 3:
            blocks = {identity: dict(json.loads(zlib.decompress(blob)))
                      for identity, blob in sample.connection.execute('SELECT id,data FROM event_blocks')}
            raw = [(seq, layout, json.dumps(blocks[data][seq], ensure_ascii=False, separators=(',', ':')).encode())
                   for seq, layout, data in rows]
        else:
            raw = [(seq, layout, zlib.decompress(data) if isinstance(data, bytes) else data.encode())
                   for seq, layout, data in rows]
        print('Sample events:', len(rows), flush=True)
        for level in (1, 3, 6):
            start = time.perf_counter()
            per_row = sum(min(len(data), len(zlib.compress(data, level))) for _, _, data in raw)
            print('Individual rows', level, per_row, 'seconds', time.perf_counter() - start, flush=True)
        dictionaries = {key: json.dumps(defaults, ensure_ascii=False, separators=(',', ':')).encode()[-32768:]
                        for key, (_, defaults) in sample.layouts.items()}
        start = time.perf_counter()
        size = 0
        for _, layout, data in raw:
            compressor = zlib.compressobj(1, zdict=dictionaries[layout])
            size += min(len(data), len(compressor.compress(data) + compressor.flush()))
        print('Layout dictionaries:', size, 'seconds', time.perf_counter() - start, flush=True)
        for count in (100, 500, 1000):
            for level in (1, 3, 6):
                start = time.perf_counter()
                size = 0
                for offset in range(0, len(raw), count):
                    payload = b'[' + b','.join(b'[' + str(seq).encode() + b',' + data + b']'
                                               for seq, _, data in raw[offset:offset + count]) + b']'
                    size += len(zlib.compress(payload, level))
                print('Blocks', count, 'level', level, 'bytes', size, 'seconds', time.perf_counter() - start, flush=True)
        sample.close()
    finally:
        source.close()


if __name__ == '__main__':
    main()
