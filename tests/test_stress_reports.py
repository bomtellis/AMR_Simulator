"""Selected stress trials become verified, navigable sections of the final PDF."""
import contextlib
from copy import deepcopy
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'visualiser'))
sys.path.insert(0, str(ROOT / 'report'))

from amr_project_runs import read_json, write_json
from amr_project_report import generate
from amr_scenario_study import create_study, evaluate, default_settings
from amr_stress_report import collect_stress_report, normalise_selection, verify_stress_sources
from tests.test_scenario_study import config


class StressReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(dir=ROOT / 'tmp')
        cls.root = Path(cls.temp.name)
        cls.paths, cls.states = [], []
        for index in range(2):
            cfg = config()
            cfg['simulation']['max_task_deferral_minutes'] = 1
            if index:
                cfg['amrs'][0]['speed_m_per_sec'] *= .75
            path = cls.root / f'Study {index + 1} & resilience.stress.json'
            create_study(cfg, path, {**default_settings(cfg), 'trial_budget': 2,
                                    'data_mode': 'reduced' if index else 'full', 'workers': 2})
            with contextlib.redirect_stdout(io.StringIO()):
                state = evaluate(path)
            if state['status'] != 'complete':
                raise AssertionError(state.get('error', state['status']))
            cls.paths.append(path)
            cls.states.append(state)
        cls.run_directory = Path(cls.states[0]['results']['baseline']['directory'])
        cls.report_config = read_json(cls.run_directory / 'config.json')
        cls.selection = [dict(study_path=str(path), study_root=state['root'],
                             trial_ids=[r['id'] for r in state['results'].values() if r['kind'] != 'baseline'][:2 if i == 0 else 1])
                         for i, (path, state) in enumerate(zip(cls.paths, cls.states))]

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def collect(self, selection=None):
        with contextlib.redirect_stdout(io.StringIO()):
            return collect_stress_report(self.selection if selection is None else selection, self.report_config)

    def test_multiple_studies_include_only_selected_trials_and_own_baselines(self):
        snapshot, evidence = self.collect()
        self.assertEqual(2, len(snapshot['studies']))
        self.assertEqual([2, 1], [len(s['trials']) for s in snapshot['studies']])
        self.assertEqual([True, False], [s['matches_report_inputs'] for s in snapshot['studies']])
        for study, selection, state in zip(snapshot['studies'], self.selection, self.states):
            self.assertEqual(selection['trial_ids'], [r['id'] for r in study['trials']])
            self.assertEqual(state['results']['baseline']['metrics']['run_key'], study['baseline']['metrics']['run_key'])
        verify_stress_sources(evidence)
        self.assertFalse(any(Path(record['directory']).joinpath('simulation_steps.csv').exists()
                             for state in self.states for record in state['results'].values()))

    def test_duplicate_selections_merge_without_duplicate_pdf_rows(self):
        selection = normalise_selection(self.selection + [self.selection[0]])
        self.assertEqual(self.selection, selection)
        with self.assertRaisesRegex(ValueError, 'at least one'):
            self.collect([])
        bad = deepcopy(self.selection)
        bad[0]['trial_ids'].append('missing')
        with self.assertRaisesRegex(ValueError, 'missing'):
            self.collect(bad)

    def test_replaced_running_and_tampered_studies_are_rejected(self):
        path = self.paths[0]
        original = path.read_bytes()
        for edit, message in [('root', 'replaced'), ('running', 'Stop or finish'), ('metrics', 'metrics do not match')]:
            with self.subTest(edit=edit):
                state = deepcopy(self.states[0])
                if edit == 'root':
                    state['root'] += '-replaced'
                elif edit == 'running':
                    state['status'] = 'running'
                else:
                    state['results'][self.selection[0]['trial_ids'][0]]['metrics']['added_delay_sec'] += 1
                try:
                    write_json(path, state)
                    with self.assertRaisesRegex(ValueError, message):
                        self.collect()
                finally:
                    path.write_bytes(original)

    def test_old_software_can_be_reported_without_resuming_study(self):
        with patch('amr_scenario_study.software_snapshot', return_value={'sha256': 'new software'}):
            snapshot, _ = self.collect()
        self.assertEqual(2, len(snapshot['studies']))

    def test_historical_reused_baseline_matches_recorded_trial_software(self):
        from amr_run_evidence import config_hash
        state = deepcopy(self.states[0])
        state['results']['baseline']['reused'] = True
        manifest_path = self.run_directory / 'run_manifest.json'
        manifest = read_json(manifest_path)
        sidecar_path = self.run_directory / (manifest['canonical_events'] + '.run.json')
        paths = [self.paths[0], manifest_path, sidecar_path]
        originals = {path: path.read_bytes() for path in paths}
        try:
            manifest['software']['files']['amr_stress_execution.py'] = 'earlier stress runner'
            manifest['software']['sha256'] = config_hash(manifest['software']['files'])
            sidecar = read_json(sidecar_path)
            sidecar['software'] = deepcopy(manifest['software'])
            write_json(manifest_path, manifest)
            write_json(sidecar_path, sidecar)
            write_json(self.paths[0], state)
            with patch('amr_scenario_study.software_snapshot', return_value={'sha256': 'new build'}):
                snapshot, _ = self.collect()
            self.assertEqual(2, len(snapshot['studies']))
        finally:
            for path, content in originals.items():
                path.write_bytes(content)

    def test_missing_reduced_baseline_is_rejected(self):
        path = Path(self.states[1]['results']['baseline']['directory'])
        manifest = read_json(path / 'run_manifest.json')
        events = path / manifest['canonical_events']
        saved = events.with_suffix('.saved')
        events.rename(saved)
        try:
            with self.assertRaises((ValueError, OSError)):
                self.collect()
        finally:
            saved.rename(events)

    def test_pdf_and_manifest_contain_exact_selections_and_linked_section(self):
        from pypdf import PdfReader
        from tests.test_report_structure import destinations
        output = self.root / 'comparison-report'
        with contextlib.redirect_stdout(io.StringIO()):
            pdf = generate(self.run_directory, output, ['method', 'stress_tests'], stress_selection=self.selection,
                           report_title='Selected resilience tests')
        metadata = read_json(output / 'report_manifest.json')
        self.assertEqual('complete', metadata['status'])
        self.assertEqual(self.selection, metadata['stress_tests']['selection'])
        snapshot = read_json(output / 'stress_test_comparison.json')
        self.assertEqual([2, 1], [len(s['trials']) for s in snapshot['studies']])
        reader = PdfReader(pdf)
        text = '\n'.join(page.extract_text() for page in reader.pages)
        for value in ('Selected resilience tests', 'Stress-test comparison', 'Normal operation',
                      'Added delay', 'Availability', 'Design inputs differ', 'Does not pass',
                      'Worst-case impact summary', 'Largest service failures',
                      'Unmet obligations and failed tasks can describe the same incident'):
            self.assertIn(value, ' '.join(text.split()))
        entry = next(item for item in destinations(reader.outline) if item.title == '2 Stress-test comparison')
        page = reader.pages[reader.get_destination_page_number(entry)]
        self.assertGreater(float(page.mediabox.width), float(page.mediabox.height))
        self.assertIn(entry.title, page.extract_text())

    def test_stress_section_inserts_into_existing_pdf_without_changing_source(self):
        from pypdf import PdfReader
        with contextlib.redirect_stdout(io.StringIO()):
            original = generate(self.run_directory, self.root / 'original-report', ['method'])
            before = original.read_bytes()
            combined = generate(self.run_directory, self.root / 'inserted-report', ['stress_tests'],
                                stress_selection=self.selection, existing_pdf=original, insert_after_page=1)
        self.assertEqual(before, original.read_bytes())
        self.assertGreater(len(PdfReader(combined).pages), len(PdfReader(original).pages))
        self.assertIn('Stress-test comparison', ''.join(p.extract_text() for p in PdfReader(combined).pages))

    def test_selection_changes_during_generation_mark_report_failed(self):
        import amr_report_main
        render = amr_report_main.generate_report_from_paths
        original = self.paths[0].read_bytes()
        def changed(*args, **kwargs):
            render(*args, **kwargs)
            state = deepcopy(self.states[0])
            state['changed_during_report'] = True
            write_json(self.paths[0], state)
        output = self.root / 'changed-report'
        try:
            with patch.object(amr_report_main, 'generate_report_from_paths', changed), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(ValueError, 'changed during report'):
                    generate(self.run_directory, output, ['stress_tests'], stress_selection=self.selection)
            self.assertEqual('failed', read_json(output / 'report_manifest.json')['status'])
        finally:
            self.paths[0].write_bytes(original)


class StressReportUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from tests.test_scenario_stress_ui import ScenarioStressUiTests
        ScenarioStressUiTests.setUp(self)

    def close_windows(self):
        from tests.test_scenario_stress_ui import ScenarioStressUiTests
        ScenarioStressUiTests.close_windows(self)

    def test_checkbox_selection_across_studies_and_panel_count(self):
        from PySide6.QtCore import Qt
        from stress_report_selection import StressReportSelectionDialog
        from project_report_panel import ProjectReportPanel
        self.editor.current_json_path = str(self.root / 'design.json')
        paths = []
        for i in range(2):
            path = self.root / f'study-{i}.stress.json'
            create_study(self.editor.store.data, path, {'trial_budget': 1})
            with contextlib.redirect_stdout(io.StringIO()):
                evaluate(path)
            paths.append(path)
        dialog = StressReportSelectionDialog(self.editor)
        self.addCleanup(dialog.close)
        self.assertEqual(2, dialog.tree.topLevelItemCount())
        for i in range(2):
            dialog.tree.topLevelItem(i).child(0).setCheckState(0, Qt.Checked)
        selection = dialog.selection()
        self.assertEqual(2, len(selection))
        self.assertIn('2 trials selected from 2 studies', dialog.count.text())
        dialog.populate(selection)
        self.assertEqual(selection, dialog.selection())
        panel = ProjectReportPanel(self.editor)
        self.addCleanup(panel.close)
        panel.set_stress_selection(selection)
        self.assertIn('2 trials from 2 studies', panel.stress_summary.text())
        section = next(panel.sections.item(i) for i in range(panel.sections.count())
                       if panel.sections.item(i).data(Qt.UserRole) == 'stress_tests')
        self.assertEqual(Qt.Checked, section.checkState())
        panel.set_stress_selection([])
        self.assertEqual(Qt.Unchecked, section.checkState())
        dialog.check_all(Qt.Checked)
        self.assertGreater(sum(len(s['trial_ids']) for s in dialog.selection()), 2)

    def test_packaged_cli_forwards_selection_file(self):
        from amr_app import main
        path = self.root / 'selection.json'
        with patch('amr_project_report.main', return_value=0) as generate_report:
            main(['--generate-report', str(self.root / 'run'), str(self.root / 'out'),
                  '--sections', 'stress_tests', '--stress-selection', str(path)])
        arguments = generate_report.call_args.args[0]
        self.assertEqual(str(path), arguments[arguments.index('--stress-selection') + 1])

    def test_real_report_worker_uses_selected_trials_and_cleans_request(self):
        from PySide6.QtCore import Qt, QEventLoop, QTimer
        from project_report_panel import ProjectReportPanel
        from amr_project import Project
        path = self.root / 'worker.stress.json'
        create_study(self.editor.store.data, path, {'trial_budget': 1, 'workers': 1})
        with contextlib.redirect_stdout(io.StringIO()):
            state = evaluate(path)
        panel = ProjectReportPanel(self.editor)
        self.editor.report_panel = panel
        baseline = state['results']['baseline']
        panel._study_context = Project.open(baseline['project'])
        panel.set_run(baseline['directory'])
        for i in range(panel.sections.count()):
            panel.sections.item(i).setCheckState(Qt.Unchecked)
        panel.set_stress_selection([dict(study_path=str(path), study_root=state['root'],
                                        trial_ids=[key for key in state['results'] if key != 'baseline'])])
        panel.generate()
        request = panel._stress_request
        self.assertIsNotNone(request)
        loop, timer = QEventLoop(), QTimer()
        timer.setInterval(20)
        timer.timeout.connect(lambda: loop.quit() if not panel.running() else None)
        timer.start()
        QTimer.singleShot(30000, loop.quit)
        loop.exec()
        timer.stop()
        if panel.running():
            panel.cancel()
            panel.process.waitForFinished(5000)
            self.fail('Report worker timed out: ' + panel.log.toPlainText())
        self.assertIsNotNone(panel.pdf, panel.log.toPlainText())
        self.assertTrue(panel.pdf.exists())
        self.assertFalse(request.exists())
        self.assertTrue(panel.choose_stress.isEnabled())
