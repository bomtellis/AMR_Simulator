"""Measure baseline differences on existing evidence without modifying either run."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from amr_event_store import EventStore
from amr_event_delta import report_blob, read_report_blob
from verification.benchmark_output_size import add_hash, verify_csv_streams


def benchmark(source, baseline, output):
    started = time.perf_counter()
    original = EventStore(source, readonly=True)
    reduced = EventStore(output, baseline=baseline)
    expected, actual = hashlib.sha256(), hashlib.sha256()
    count = 0
    report_bytes = dict(full=0, reduced=0)
    try:
        for seq, precise, layout, data, playback in original.connection.execute(
                'SELECT seq,sim_time,layout,data,playback FROM events ORDER BY seq'):
            row = original._decode(layout, data, None, seq, precise)
            reduced.append(row, precise_time=precise, playback=bool(playback))
            add_hash(expected, seq, precise, row, playback)
            count += 1
            if count % 25000 == 0:
                print(f'Encoded {count:,} events', flush=True)
        for key, value in original.connection.execute('SELECT key,value FROM metadata'):
            if key in ('event_format_version', 'baseline'):
                continue
            if key == 'report_state' or key.startswith('report_records:'):
                contents = read_report_blob(original, key, value)
                report_bytes['full'] += len(value)
                value = report_blob(reduced, key, contents)
                report_bytes['reduced'] += len(value)
                if contents != read_report_blob(reduced, key, value):
                    raise AssertionError('Report state differs')
            reduced.connection.execute('INSERT INTO metadata VALUES (?,?)', (key, value))
        reduced.flush()
        for seq, precise, layout, data, playback in reduced.connection.execute(
                'SELECT seq,sim_time,layout,data,playback FROM events ORDER BY seq'):
            add_hash(actual, seq, precise, reduced._decode(layout, data, None, seq, precise), playback)
        if expected.digest() != actual.digest():
            raise AssertionError('Event evidence differs')
        references = sum(isinstance(item, dict) for blob, in reduced.connection.execute('SELECT data FROM event_blocks')
                         for _, item in json.loads(zlib.decompress(blob)))
    finally:
        reduced.close()
        original.close()
    full_bytes, delta_bytes = source.stat().st_size, output.stat().st_size
    result = dict(source=str(source.resolve()), baseline=str(baseline.resolve()), events=count,
        baseline_referenced_events=references, full_bytes=full_bytes, reduced_bytes=delta_bytes,
        reduction_percent=round(100 * (1 - delta_bytes / full_bytes), 2), report_payload_bytes=report_bytes,
        exact_events_sha256=expected.hexdigest(), exact_match=True, elapsed_sec=round(time.perf_counter() - started, 3))
    result.update(verify_csv_streams(source, output))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('baseline', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--results', type=Path, required=True)
    args = parser.parse_args()
    result = benchmark(args.source, args.baseline, args.output)
    args.results.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2), flush=True)
