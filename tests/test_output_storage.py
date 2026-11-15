"""Bounded block storage and disk-free reports preserve exported evidence."""
import contextlib
import csv
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import zlib

from amr_event_store import EventStore
from amr_event_csv import EventCSVReader, read_event_csv
from amr_run_exports import ensure_exports
from tests import test_compact_execution as compact_tests


class BlockStorageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'events.sqlite'

    def row(self, seq, **values):
        return dict(event_id=f'run:{seq:012d}', event_type='move' if seq % 2 else 'wait',
                    sim_time_sec=seq, details='ward → corridor movement ' * 50, **values)

    def test_blocks_bound_count_and_bytes_and_preserve_gapped_sequences(self):
        store = EventStore(self.path)
        rows = [self.row(seq, value={'items': [seq]}) for seq in (1, 4, 7, 10, 13, 16)]
        with patch('amr_event_store.BLOCK_MAX_EVENTS', 2), patch('amr_event_store.BLOCK_MAX_BYTES', 256):
            for row in rows:
                store.append(row, precise_time=row['sim_time_sec'] + .0000001)
            store.flush()
        for blob, in store.connection.execute('SELECT data FROM event_blocks'):
            raw = zlib.decompress(blob)
            block = json.loads(raw)
            self.assertLessEqual(len(block), 2)
            self.assertTrue(len(raw) <= 256 or len(block) == 1)
        self.assertEqual(rows, list(store.iter_rows()))
        self.assertEqual(rows[1::2], list(store.iter_rows(event_types=('wait',))))
        returned = next(iter(store.iter_rows()))
        returned['value']['items'].append('mutated')
        returned = list(store.iter_rows())[-1]
        returned['value']['items'].append('mutated cached change')
        self.assertEqual(rows, list(store.iter_rows()))
        store.close()

    def test_large_speculative_stage_does_not_publish_blocks(self):
        store = EventStore(self.path)
        first = self.row(1)
        store.append(first)
        store.flush()
        store.begin_stage()
        for seq in range(2, 1005):
            store.append(self.row(seq, speculative=True))
        store.flush()
        self.assertEqual(1, store.connection.execute('SELECT COUNT(*) FROM events').fetchone()[0])
        store.end_stage(False)
        store.close()
        self.assertEqual([first], list(store.iter_rows()))

    def test_failed_flush_rolls_back_block_and_can_retry(self):
        store = EventStore(self.path)
        store.append(self.row(1))
        store.flush()
        store.connection.execute("CREATE TEMP TRIGGER fail_event BEFORE INSERT ON events BEGIN SELECT RAISE(ABORT, 'test failure'); END")
        store.append(self.row(2))
        with self.assertRaises(sqlite3.IntegrityError):
            store.flush()
        self.assertEqual(1, store.connection.execute('SELECT COUNT(*) FROM event_blocks').fetchone()[0])
        self.assertEqual(1, len(store.buffer))
        store.connection.execute('DROP TRIGGER fail_event')
        store.flush()
        store.close()
        self.assertEqual([self.row(1), self.row(2)], list(store.iter_rows()))

    def test_stream_preserves_csv_bytes_at_arbitrary_read_boundaries(self):
        store = EventStore(self.path)
        rows = [self.row(seq, text='comma, quote" and\nnewline →', number=seq / 3, flag=seq % 2 == 0)
                for seq in range(1, 160)]
        fields = list(rows[0]) + ['absent']
        for row in rows:
            store.append(row)
        store.connection.execute('INSERT INTO metadata VALUES (?,?)',
                                 ('report_headers', json.dumps({'steps_csv': fields})))
        store.close()
        expected = io.StringIO(newline='')
        writer = csv.DictWriter(expected, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
        with io.BufferedReader(EventCSVReader(self.path)) as stream:
            actual = b''.join(iter(lambda: stream.read(17), b''))
        self.assertEqual(expected.getvalue().encode(), actual)
        import pandas as pd
        pd.testing.assert_frame_equal(pd.read_csv(io.StringIO(expected.getvalue())), read_event_csv(self.path))
        expected_chunks = list(pd.read_csv(io.StringIO(expected.getvalue()), chunksize=19, usecols=['event_id', 'number', 'flag']))
        actual_chunks = list(read_event_csv(self.path, chunksize=19, usecols=['event_id', 'number', 'flag']))
        for left, right in zip(expected_chunks, actual_chunks, strict=True):
            pd.testing.assert_frame_equal(left, right)


class CompactReportTests(unittest.TestCase):
    setUp = compact_tests.CompactExecutionTests.setUp
    run_project = compact_tests.CompactExecutionTests.run_project

    def test_report_tables_and_energy_match_csv_without_expanding_for_report(self):
        import pandas as pd
        from report.amr_report_analysis import analyse, extract_lift_cohorts, extract_lift_movements
        from report.amr_energy_evidence import read_energy_evidence
        directory, simulation = self.run_project()
        canonical = simulation.event_store.path
        direct = analyse(canonical, .8, .8)
        exported = ensure_exports(directory)['steps_csv']
        expanded = analyse(exported, .8, .8)
        self.assertEqual(set(expanded), set(direct))
        for key in direct:
            if isinstance(direct[key], pd.DataFrame):
                pd.testing.assert_frame_equal(expanded[key], direct[key], obj=key)
            else:
                self.assertEqual(expanded[key], direct[key])
        self.assertEqual(read_energy_evidence(exported), read_energy_evidence(canonical))
        legacy_cohorts, direct_cohorts = extract_lift_cohorts(exported), extract_lift_cohorts(canonical)
        self.assertEqual(set(legacy_cohorts), set(direct_cohorts))
        for key in legacy_cohorts:
            pd.testing.assert_frame_equal(legacy_cohorts[key], direct_cohorts[key])
        pd.testing.assert_frame_equal(extract_lift_movements(exported), extract_lift_movements(canonical))

    def test_project_report_does_not_create_full_csv(self):
        from amr_project_report import generate
        from amr_project_runs import OUTPUTS
        directory, _ = self.run_project()
        before = {p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()}
        for name, sections, cohorts in (('cohorts', [], True), ('pdf', ['front_summary', 'method', 'task_detail'], False)):
            with self.subTest(output=name), contextlib.redirect_stdout(io.StringIO()):
                result = generate(directory, self.root / name, sections, lift_cohorts_only=cohorts)
                self.assertTrue(result.exists())
                self.assertEqual(before, {p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()})
                if not cohorts:
                    from pypdf import PdfReader
                    self.assertGreater(len(PdfReader(result).pages), 0)
        self.assertFalse((directory / OUTPUTS['steps_csv']).exists())

    def test_lift_energy_and_movement_tables_match_explicit_export(self):
        import pandas as pd
        from simulator import Simulation
        from tests.test_delivery_energy_reference import lift_config
        from report.amr_energy_evidence import read_energy_evidence
        from report.amr_report_analysis import extract_lift_movements
        config = lift_config()
        config['tasks'] = [dict(id=f'T{i}', pickup='A', dropoff='B', payload='Box') for i in (1, 2)]
        with contextlib.redirect_stdout(io.StringIO()):
            sim = Simulation(config, verbose=True, verbose_csv_path=str(self.root / 'lift.csv'), defer_exports=True)
            sim.run()
            sim.write_verbose_csv()
        canonical = sim.event_store.path
        movements = extract_lift_movements(canonical)
        self.assertGreater(len(movements), 0)
        energy = read_energy_evidence(canonical)
        self.assertGreater(energy['total_kwh'], 0)
        csv_path = ensure_exports(canonical)['steps_csv']
        pd.testing.assert_frame_equal(extract_lift_movements(csv_path), movements)
        self.assertEqual(read_energy_evidence(csv_path), energy)

    def test_department_review_stream_matches_explicit_export(self):
        from tests.test_department_review import configuration, log_rows
        from report.amr_department_review import load_department_reviews
        from amr_event_store import export_rows
        rows = [dict(row, event_id=f'run:{i:012d}') for i, row in enumerate(log_rows(), 1)]
        fields = list(dict.fromkeys(key for row in rows for key in row))
        path = self.root / 'department.sqlite'
        store = EventStore(path)
        for row in rows:
            store.append(row)
        store.connection.execute('INSERT INTO metadata VALUES (?,?)',
                                 ('report_headers', json.dumps({'steps_csv': fields})))
        store.close()
        inputs = self.root / 'config.json'
        inputs.write_text(json.dumps(configuration()), encoding='utf-8')
        direct = load_department_reviews(path, inputs)
        csv_path = export_rows(path, self.root / 'department.csv', fields)
        legacy = load_department_reviews(csv_path, inputs)
        self.assertEqual(legacy['categories'], direct['categories'])
