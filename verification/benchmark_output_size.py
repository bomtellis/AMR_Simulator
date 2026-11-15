"""Re-encode recorded events without rerunning the model or altering source evidence.

The output is a benchmark copy, not a verified project run. Refuses overwrite.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import time
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from amr_event_store import EventStore
from amr_event_csv import EventCSVReader


def add_hash(digest, sequence, precise, row, playback):
    digest.update(json.dumps([sequence, precise, row, playback], ensure_ascii=False,
                             sort_keys=True, separators=(',', ':')).encode('utf-8'))
    digest.update(b'\n')


def verify_csv_streams(source, output):
    """Hash the full legacy exports without retaining another large disk copy."""
    started = time.perf_counter()
    fingerprints = []
    for path in (source, output):
        digest, size = hashlib.sha256(), 0
        with io.BufferedReader(EventCSVReader(path)) as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                size += len(chunk)
                digest.update(chunk)
        fingerprints.append((size, digest.hexdigest()))
    if fingerprints[0] != fingerprints[1]:
        raise AssertionError('Re-encoded CSV export differs')
    return dict(csv_stream_bytes=fingerprints[0][0], csv_sha256=fingerprints[0][1], csv_exact_match=True,
                csv_verification_sec=round(time.perf_counter() - started, 3))


def benchmark(source, output):
    started = time.perf_counter()
    original = EventStore(source, readonly=True)
    result = EventStore(output)
    expected, actual = hashlib.sha256(), hashlib.sha256()
    count = 0
    try:
        for seq, precise, layout, data, playback in original.connection.execute(
                'SELECT seq,sim_time,layout,data,playback FROM events ORDER BY seq'):
            row = original._decode(layout, data, None, seq, precise)
            result.append(row, precise_time=precise, playback=bool(playback))
            add_hash(expected, seq, precise, row, playback)
            count += 1
            if count % 25000 == 0:
                print(f'Re-encoded {count:,} events', flush=True)
        for key, value in original.connection.execute('SELECT key,value FROM metadata'):
            if key == 'event_format_version':
                continue
            if key == 'report_state' or key.startswith('report_records:'):
                value = zlib.compress(zlib.decompress(value), level=6)
            result.connection.execute('INSERT INTO metadata VALUES (?,?)', (key, value))
        result.flush()
        for seq, precise, layout, data, playback in result.connection.execute(
                'SELECT seq,sim_time,layout,data,playback FROM events ORDER BY seq'):
            add_hash(actual, seq, precise, result._decode(layout, data, None, seq, precise), playback)
        if expected.digest() != actual.digest():
            raise AssertionError('Re-encoded event evidence differs')
    finally:
        result.close()
        original.close()
    old_size, new_size = source.stat().st_size, output.stat().st_size
    return dict(source=str(source.resolve()), benchmark_copy=str(output.resolve()), events=count,
                original_storage_version=original.format_version, storage_version=result.format_version,
                original_bytes=old_size, compressed_bytes=new_size,
                reduction_percent=round(100 * (1 - new_size / old_size), 2),
                decoded_evidence_sha256=expected.hexdigest(), exact_match=True,
                elapsed_sec=round(time.perf_counter() - started, 3))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--results', type=Path, required=True)
    parser.add_argument('--verify-csv', action='store_true')
    args = parser.parse_args()
    evidence = benchmark(args.source, args.output)
    if args.verify_csv:
        evidence.update(verify_csv_streams(args.source, args.output))
    args.results.write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(evidence, indent=2), flush=True)
