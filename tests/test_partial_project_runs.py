"""Verified partial stops retain frozen-run proof without claiming completion."""
import contextlib
import copy
import csv
import io
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from amr_project import Project
from amr_project_runs import (MANIFEST, OUTPUTS, PARTIAL_EXIT_CODE, PreparedRun, execute,
                              finish_run, main, read_json, verified_termination, write_json)
from amr_run_evidence import config_hash, file_hash
from amr_run_review import verified_inputs
from tests.test_engineering_reference import reference_config
from visualiser.project_checks import check_project


class PartialProjectRunTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = Project()
        self.project.save(self.root/'model.amrproj', reference_config())

    def prepare(self):
        draft = PreparedRun(self.project, self.root/'results')
        report = check_project(draft.config, base_path=draft.directory)
        report.acknowledge_warnings()
        return draft.commit(report)

    def evidence(self, directory, reason='blocked'):
        manifest = read_json(directory/MANIFEST)
        termination = dict(schema_version=1, reason=reason, stop_time_sec=2.123456,
                           event_id='run-partial:000000000001', message='No verified retreat is available.',
                           amr_ids=['R-1'], task_ids=['T'])
        row = dict(event_id=termination['event_id'], run_id='run-partial',
                   event_type='geometric_simulation_stopped', status=reason,
                   sim_time_sec=round(termination['stop_time_sec'], 3),
                   details=json.dumps({k: v for k, v in termination.items() if k != 'event_id'}))
        path = directory/OUTPUTS['steps_csv']
        self.write_rows(path, [row])
        data = dict(schema_version=1, run_id='run-partial',
                    project_binding=manifest['project_binding'], software=manifest['software'],
                    config_sha256=manifest['config_object_sha256'], frozen_inputs=read_json(directory/'config.json'),
                    log_sha256=file_hash(path), log_kind='full', logging_enabled=True, reduced_logging=False,
                    run_status=reason, termination=termination,
                    summary=dict(completed_task_ids=[], failed_task_ids=[]))
        write_json(str(path)+'.run.json', data)
        return data

    @staticmethod
    def write_rows(path, rows):
        with Path(path).open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=['event_id','run_id','event_type','status','sim_time_sec','details'])
            writer.writeheader()
            writer.writerows(rows)

    def stopped(self, reason='blocked'):
        directory = self.prepare()
        self.evidence(directory, reason)
        result = finish_run(directory, 0)
        self.assertEqual('partial', result['status'], result.get('error'))
        return directory

    def test_supported_partial_reasons_preserve_binding_counts_and_exact_stop(self):
        for reason in ('blocked', 'search_limit', 'deadlock'):
            with self.subTest(reason=reason):
                directory = self.prepare()
                frozen = (directory/'config.json').read_bytes()
                evidence = self.evidence(directory, reason)
                result = finish_run(directory, PARTIAL_EXIT_CODE)
                self.assertEqual('partial', result['status'])
                self.assertEqual(reason, result['termination_reason'])
                self.assertEqual(2.123456, result['stop_time_sec'])
                self.assertEqual(evidence['termination'], result['termination'])
                self.assertEqual(config_hash(evidence['termination']), result['termination_sha256'])
                self.assertEqual((0, 0), (result['completed_tasks'], result['failed_tasks']))
                self.assertEqual(frozen, (directory/'config.json').read_bytes())
                with self.assertRaisesRegex(ValueError, 'completed project run'):
                    verified_inputs(directory)
                manifest, config, csv_path, log_hash = verified_inputs(directory, allow_partial=True)
                self.assertEqual('partial', manifest['status'])
                self.assertEqual(evidence['frozen_inputs'], config)
                self.assertEqual(file_hash(csv_path), log_hash)

    def test_gui_second_finalisation_with_partial_exit_preserves_partial(self):
        directory = self.stopped()
        result = finish_run(directory, PARTIAL_EXIT_CODE, error='Process exited with code 2')
        self.assertEqual('partial', result['status'])
        self.assertNotIn('error', result)
        self.assertEqual('partial', verified_inputs(directory, allow_partial=True)[0]['status'])

    def test_changed_log_frozen_inputs_software_and_termination_are_rejected(self):
        for target in ('log', 'config', 'software', 'termination', 'manifest'):
            with self.subTest(target=target):
                directory = self.stopped()
                path = directory/OUTPUTS['steps_csv']
                evidence_path = str(path)+'.run.json'
                if target == 'log':
                    with path.open('a') as stream:
                        stream.write('changed\n')
                elif target == 'config':
                    write_json(directory/'config.json', {})
                elif target == 'manifest':
                    manifest = read_json(directory/MANIFEST)
                    manifest['stop_time_sec'] = 10
                    write_json(directory/MANIFEST, manifest)
                else:
                    evidence = read_json(evidence_path)
                    if target == 'software':
                        evidence['software']['sha256'] = 'different'
                    else:
                        evidence['termination']['message'] = 'A different explanation'
                    write_json(evidence_path, evidence)
                with self.assertRaises(ValueError):
                    verified_inputs(directory, allow_partial=True)

    def test_missing_stale_or_ambiguous_stop_event_cannot_verify_partial(self):
        for change in ('missing', 'wrong_time', 'wrong_id', 'duplicate', 'wrong_details', 'wrong_status'):
            with self.subTest(change=change):
                directory = self.prepare()
                evidence = self.evidence(directory)
                path = directory/OUTPUTS['steps_csv']
                with path.open(newline='', encoding='utf-8') as stream:
                    rows = list(csv.DictReader(stream))
                if change == 'missing':
                    rows = []
                elif change == 'duplicate':
                    rows.append(dict(rows[0]))
                else:
                    field, value = {'wrong_time': ('sim_time_sec', '50'),
                        'wrong_id': ('event_id', 'stale:1'), 'wrong_details': ('details', '{}'),
                        'wrong_status': ('status', 'finished')}[change]
                    rows[0][field] = value
                self.write_rows(path, rows)
                # A fresh log hash alone does not establish a valid stop record.
                evidence['log_sha256'] = file_hash(path)
                write_json(str(path)+'.run.json', evidence)
                result = finish_run(directory, 0)
                self.assertEqual('failed', result['status'])
                with self.assertRaises(ValueError):
                    verified_inputs(directory, allow_partial=True)

    def test_malformed_termination_and_reduced_logging_are_rejected(self):
        directory = self.prepare()
        good = self.evidence(directory)
        path = directory/OUTPUTS['steps_csv']
        changes = [{'schema_version': True}, {'stop_time_sec': True}, {'stop_time_sec': math.inf},
                   {'stop_time_sec': math.nan}, {'stop_time_sec': -1}, {'event_id': ''}, {'message': ''},
                   {'reason': []}, {'reason': 'cancelled'}, {'amr_ids': ['R-1', 'R-1']},
                   {'task_ids': 'T'}, {'geometry': {'x': math.inf}}]
        for fields in changes:
            evidence = copy.deepcopy(good)
            evidence['termination'].update(fields)
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                verified_termination(evidence, path)
        for fields in ({'termination': None}, {'run_status': 'finished'}, {'log_kind': 'visualiser'},
                       {'logging_enabled': False}, {'logging_enabled': 1}, {'reduced_logging': True}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                verified_termination({**good, **fields}, path)

    def test_partial_opt_in_cannot_review_generic_failed_or_cancelled_runs(self):
        for cancelled in (False, True):
            directory = self.prepare()
            self.evidence(directory)
            status = finish_run(directory, 1, cancelled=cancelled)['status']
            self.assertEqual('cancelled' if cancelled else 'failed', status)
            with self.assertRaises(ValueError):
                verified_inputs(directory, allow_partial=True)

    def test_evidence_from_another_prepared_run_is_rejected(self):
        first, second = self.prepare(), self.prepare()
        first_evidence = self.evidence(first)
        self.evidence(second)
        write_json(str(second/OUTPUTS['steps_csv'])+'.run.json', first_evidence)
        result = finish_run(second, PARTIAL_EXIT_CODE)
        self.assertEqual('failed', result['status'])
        self.assertIn('prepared run', result['error'])

    def test_stop_evidence_cannot_be_relabelled_finished(self):
        directory = self.prepare()
        evidence = self.evidence(directory)
        evidence['run_status'] = 'finished'
        write_json(str(directory/OUTPUTS['steps_csv'])+'.run.json', evidence)
        self.assertEqual('failed', finish_run(directory, 0)['status'])

    def test_invalid_summary_cannot_leave_a_half_verified_partial_manifest(self):
        directory = self.prepare()
        evidence = self.evidence(directory)
        del evidence['summary']
        write_json(str(directory/OUTPUTS['steps_csv'])+'.run.json', evidence)
        self.assertEqual('failed', finish_run(directory, 0)['status'])
        with self.assertRaises(ValueError):
            verified_inputs(directory, allow_partial=True)

    def test_execute_returns_valid_partial_and_cli_reports_distinct_exit(self):
        directory = self.prepare()
        outer = self
        class StoppedSimulation:
            def __init__(self, *_args, **_kwargs):
                self._evidence_project_binding = None
            def run(self):
                pass
            def write_verbose_csv(self):
                outer.evidence(directory)
            def __getattr__(self, name):
                if name.startswith('write_'):
                    return lambda path: Path(path).write_text('')
                raise AttributeError(name)
        output = io.StringIO()
        with patch('simulator.Simulation', StoppedSimulation), contextlib.redirect_stdout(output):
            result = execute(directory)
        self.assertIsInstance(result, StoppedSimulation)
        self.assertIn('Run stopped (partial): blocked', output.getvalue())
        self.assertNotIn('Run complete:', output.getvalue())
        self.assertEqual('partial', read_json(directory/MANIFEST)['status'])
        with patch('sys.argv', ['amr_project_runs', str(directory)]), patch('amr_project_runs.execute'):
            self.assertEqual(PARTIAL_EXIT_CODE, main())
        before = (directory/OUTPUTS['steps_csv']).read_bytes()
        with self.assertRaisesRegex(ValueError, 'already started'):
            execute(directory)
        self.assertEqual(before, (directory/OUTPUTS['steps_csv']).read_bytes())


if __name__ == '__main__':
    unittest.main()
