"""SLA rule precedence, linked report navigation and preservation during PDF insertion."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
from pypdf import PdfReader
from reportlab.lib.pagesizes import A4, landscape

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'report'))
from amr_report_analysis import analyse
from amr_report_pdf_report import build_report
from amr_report_pdf_insert import insert_pdf_sections
from amr_report_sla import build_sla_assignments


def destinations(outline):
    for entry in outline:
        if isinstance(entry, list):
            yield from destinations(entry)
        else:
            yield entry


class SlaAssignmentTests(unittest.TestCase):
    def test_department_and_group_precedence_and_disabled_defaults(self):
        config = dict(departments=[dict(id='D', name='Ward'), dict(id='E', name='Theatre')],
            task_generation=dict(categories=dict(linen=dict(enabled=False, target_time=600,
                departments=dict(D=dict(enabled=True, target_time=900), E=dict(enabled=False)),
                department_groups=[dict(id='G', departments=['E'], payload=dict(enabled=True, target_time=1800))]),
                waste=dict(enabled=False, target_time=300))))
        frame = build_sla_assignments(config)['sla_assignments']
        self.assertEqual({'linen'}, set(frame.category))
        self.assertEqual({'Ward': 900, 'Theatre': 1800}, dict(zip(frame.scope, frame.target_s)))
        self.assertEqual({15, 30}, set(frame.target_minutes))
        self.assertTrue(frame.source.str.contains('Effective generation rule').all())

    def test_global_disable_zero_and_invalid_targets_are_not_attributed(self):
        config = dict(task_generation=dict(enabled=False, categories=dict(linen=dict(enabled=True, target_time=600))))
        self.assertTrue(build_sla_assignments(config)['sla_assignments'].empty)
        config['task_generation'] = dict(categories={str(i): dict(enabled=True, target_time=v)
            for i, v in enumerate([0, -1, None, 'bad', float('inf'), float('nan')])})
        self.assertTrue(build_sla_assignments(config)['sla_assignments'].empty)

    def test_overnight_deadline_and_separate_return_target(self):
        config = dict(task_generation=dict(categories=dict(catering=dict(enabled=True,
            generation_mode='timeframe', timeframe_start='23:00', timeframe_end='01:00',
            target_time=600, return_enabled=True, return_target_time=120))))
        frame = build_sla_assignments(config)['sla_assignments'].set_index('task_type')
        self.assertTrue(pd.isna(frame.loc['Outbound', 'target_s']))
        self.assertIn('23:00-01:00', frame.loc['Outbound', 'detail'])
        self.assertEqual(120, frame.loc['Return / collection', 'target_s'])

    def test_explicit_tasks_and_string_labels(self):
        config = dict(tasks=[dict(id='T', labels='pharmacy', target_time=45), dict(id='None', target_time=0)])
        row = build_sla_assignments(config)['sla_assignments'].iloc[0]
        self.assertEqual(('pharmacy', 'T', 45), (row.category, row.scope, row.target_s))

    def test_observed_different_targets_and_pending_deadlines(self):
        requests = pd.DataFrame([
            dict(stream='Linen', target_s=60, outcome='completed', overdue=False),
            dict(stream='Linen', target_s=60, outcome='failed', overdue=False),
            dict(stream='Linen', target_s=60, outcome='incomplete', overdue=False),
            dict(stream='Linen', target_s=120, outcome='incomplete', overdue=True),
            dict(stream='Waste', target_s=0, outcome='completed', overdue=False)])
        table = build_sla_assignments({}, requests)['sla_observed_targets'].set_index('target_s')
        self.assertEqual({60, 120}, set(table.index))
        self.assertEqual(2, table.loc[60, 'assessed'])
        self.assertEqual(50, table.loc[60, 'compliance_pct'])
        self.assertEqual(0, table.loc[120, 'compliance_pct'])


class ReportStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from simulator import Simulation
        from tests.test_charger_contention import contention_config
        folder = Path(__file__).resolve().parents[1] / 'tmp'
        folder.mkdir(exist_ok=True)
        cls.temp = tempfile.TemporaryDirectory(dir=folder)
        cls.folder = Path(cls.temp.name)
        config = contention_config()
        for task in config['tasks']:
            task['target_time'] = 5
        config['task_generation'] = dict(categories=dict(pharmacy=dict(enabled=False, target_time=900)))
        cls.csv = cls.folder / 'events.csv'
        cls.config = cls.folder / 'config.json'
        cls.config.write_text(json.dumps(config), encoding='utf-8')
        with contextlib.redirect_stdout(io.StringIO()):
            sim = Simulation(config, verbose=True, verbose_csv_path=str(cls.csv))
            sim.run()
            sim.write_verbose_csv()
            cls.results = analyse(cls.csv, .85, .70, kpi_config=config)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def build(self, filename, sections=None, title='AMR Simulation Performance Report'):
        path = self.folder / filename
        build_report(self.results, self.csv, path, include_drawings=False, report_sections=sections, report_title=title)
        return path

    def test_cover_contents_numbering_follow_selection_and_link_to_real_pages(self):
        path = self.build('selected.pdf', ['sla_categories', 'operational_kpis', 'method'], 'Hospital A & B')
        reader = PdfReader(path)
        self.assertIn('Hospital A & B', reader.pages[0].extract_text())
        self.assertEqual('Hospital A & B', reader.metadata.title)
        self.assertIn('Contents', reader.pages[1].extract_text())
        entries = list(destinations(reader.outline))
        titles = [item.title for item in entries]
        self.assertIn('1 SLA categories and assigned targets', titles)
        self.assertIn('1.1 Configured assignments', titles)
        self.assertIn('2.1.1 Hourly requests and fleet use', titles)
        self.assertIn('3 Method', titles)
        for entry in entries:
            page = reader.get_destination_page_number(entry)
            self.assertIn(entry.title, reader.pages[page].extract_text())
        self.assertTrue(reader.pages[1].get('/Annots'))
        self.assertAlmostEqual(A4[0], float(reader.pages[0].mediabox.width), places=3)
        self.assertAlmostEqual(A4[1], float(reader.pages[0].mediabox.height), places=3)
        self.assertAlmostEqual(landscape(A4)[0], float(reader.pages[2].mediabox.width), places=3)

    def test_full_report_multi_page_contents_and_heatmap_navigation(self):
        reader = PdfReader(self.build('full.pdf'))
        entries = list(destinations(reader.outline))
        heatmap = next(entry for entry in entries if entry.title.endswith('Congestion heatmaps'))
        page = reader.get_destination_page_number(heatmap)
        self.assertIn('Floor 0', reader.pages[page].extract_text())
        self.assertTrue(any(entry.title.endswith('Floor 0') for entry in entries))
        executive = next(entry for entry in entries if entry.title == '1 Executive summary')
        self.assertGreater(reader.get_destination_page_number(executive), 2)
        # A final contents page must reference the final section after pagination converges.
        toc_text = ''.join(p.extract_text() for p in reader.pages[1:reader.get_destination_page_number(executive)])
        self.assertIn(heatmap.title, toc_text)
        for entry in entries:
            self.assertGreaterEqual(reader.get_destination_page_number(entry), 0)

    def test_insert_preserves_original_page_streams_sizes_links_and_source(self):
        source = self.build('original.pdf', ['method'])
        supplement = self.build('supplement.pdf', ['sla_categories'], 'SLA supplement')
        before = source.read_bytes()
        original = PdfReader(source)
        extra = PdfReader(supplement)
        for position in [0, 2, None]:
            with self.subTest(position=position):
                target = self.folder / f'combined-{position}.pdf'
                insert_pdf_sections(source, supplement, target, position)
                combined = PdfReader(target)
                pos = len(original.pages) if position is None else position
                self.assertEqual(len(original.pages)+len(extra.pages), len(combined.pages))
                for i, page in enumerate(original.pages):
                    copied = combined.pages[i if i < pos else i + len(extra.pages)]
                    self.assertEqual(page.get_contents().get_data(), copied.get_contents().get_data())
                    self.assertEqual(tuple(page.mediabox), tuple(copied.mediabox))
                    self.assertEqual(len(page.get('/Annots', [])), len(copied.get('/Annots', [])))
                for i, page in enumerate(extra.pages):
                    self.assertEqual(len(page.get('/Annots', [])), len(combined.pages[pos+i].get('/Annots', [])))
                for entry in destinations(combined.outline):
                    actual = combined.get_destination_page_number(entry)
                    self.assertIsNotNone(actual)
                    if entry.title != 'Inserted report sections':
                        self.assertIn(entry.title, combined.pages[actual].extract_text())
                for page in combined.pages:
                    for reference in page.get('/Annots', []):
                        annotation = reference.get_object()
                        dest = annotation.get('/Dest')
                        if dest:
                            self.assertIsNotNone(combined.get_page_number(dest[0].get_object()))
        self.assertEqual(before, source.read_bytes())

    def test_invalid_position_and_source_overwrite_leave_files_intact(self):
        source = self.build('safe.pdf', ['method'])
        original = source.read_bytes()
        for target, position in [(source, None), (self.folder/'absent.pdf', -1), (self.folder/'absent.pdf', 9999)]:
            with self.subTest(position=position), self.assertRaises(ValueError):
                insert_pdf_sections(source, source, target, position)
        self.assertEqual(original, source.read_bytes())
        self.assertFalse((self.folder/'absent.pdf').exists())

    def test_prepared_pdf_cli_skips_analysis(self):
        from amr_report_main import main
        source = self.build('cli-source.pdf', ['method'])
        target = self.folder/'cli-result.pdf'
        args = ['report', '--existing-pdf', str(source), '--insert-pdf', str(source), '--output', str(target)]
        with patch.object(sys, 'argv', args), patch('amr_report_main.analyse', side_effect=AssertionError('Analysis must be skipped')):
            with contextlib.redirect_stdout(io.StringIO()):
                main()
        self.assertEqual(2*len(PdfReader(source).pages), len(PdfReader(target).pages))

    def test_generation_inserts_only_selected_sections_and_exports_sla_details(self):
        from amr_report_main import generate_report_from_paths
        source = self.build('generated-source.pdf', ['method'])
        target = self.folder/'generated-insert.pdf'
        with patch('amr_report_pdf_report.prepare_heatmap_floor', side_effect=AssertionError('Unselected heatmaps must not render')):
            with contextlib.redirect_stdout(io.StringIO()):
                generate_report_from_paths(self.csv, target, config_json=self.config,
                    report_sections=['sla_categories'], include_drawings=False, existing_pdf=source,
                    insert_after_page=2, report_title='Updated SLA')
        reader = PdfReader(target)
        self.assertEqual(6, len(reader.pages))
        self.assertIn('Updated SLA', reader.pages[2].extract_text())
        self.assertIn('1 SLA categories and assigned targets', reader.pages[4].extract_text())
        self.assertIn('1 Method', reader.pages[5].extract_text())
        self.assertEqual(4, len(pd.read_csv(target.with_name(target.stem+'_sla_assignments.csv'))))

    def test_prepared_pdf_dialog_skips_missing_simulation_inputs(self):
        import os
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QScrollArea
        from amr_report_main import launch_report_generator_dialog
        self.__class__.qt_app = QApplication.instance() or QApplication([])
        source = self.build('dialog-source.pdf', ['method'])
        output = self.folder/'dialog-output.pdf'
        def execute(dialog):
            dialog.existing_pdf_edit.setText(str(source))
            dialog.prepared_pdf_edit.setText(str(source))
            dialog.output_edit.setText(str(output))
            dialog.csv_edit.setText('missing.csv')
            self.assertTrue(dialog.findChildren(QScrollArea))
            dialog.generate_report()
            self.assertEqual(100, dialog.progress.value())
            return QDialog.Accepted
        with patch.object(QDialog, 'exec', execute), patch.object(QMessageBox, 'information'), patch.object(QMessageBox, 'critical') as error:
            with patch('amr_report_main.analyse', side_effect=AssertionError('Prepared PDF must skip analysis')):
                launch_report_generator_dialog()
            error.assert_not_called()
        self.assertEqual(6, len(PdfReader(output).pages))


if __name__ == '__main__':
    unittest.main()
