"""Daily report section, PDF-only lift selection and unchanged Excel exports."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from pypdf import PdfReader
from PySide6.QtCore import Qt,QEventLoop,QTimer
from tests.test_lift_movement_charts import chart_fixture
from tests import test_lift_movement_charts_ui as charts_ui
from amr_lift_movement_charts import build_chart_data
from report.amr_lift_movement_plot import pdf_chart_selections


class DailySelectionTests(unittest.TestCase):
    def setUp(self):
        rows,cfg=chart_fixture();self.data=build_chart_data(rows,cfg)

    def test_daily_charts_count_each_lift_day_and_reconcile_to_combined(self):
        daily=pdf_chart_selections(self.data,daily=True)
        self.assertEqual(6,len(daily))
        self.assertEqual([('Lift-A','2026-01-01',6),('Lift-A','2026-01-02',1),
            ('Lift-B','2026-01-01',0),('Lift-B','2026-01-02',2),
            ('Unused','2026-01-01',0),('Unused','2026-01-02',0)],
            [(c['lift_id'],c['day'],c['total']) for c in daily])
        self.assertEqual(sum(c['total'] for c in pdf_chart_selections(self.data)),sum(c['total'] for c in daily))
        self.assertEqual([3,3],[c['scale_peak'] for c in daily if c['lift_id']=='Lift-A'])

    def test_pdf_lift_day_and_reposition_filters_compose(self):
        charts=pdf_chart_selections(self.data,'2026-01-01',False,['Lift-A'],True)
        self.assertEqual([('Lift-A','2026-01-01',5)],[(c['lift_id'],c['day'],c['total']) for c in charts])
        self.assertEqual(2,len(pdf_chart_selections(self.data,lift_ids=['Unused'],daily=True)))
        self.assertEqual(7,pdf_chart_selections(self.data,lift_ids=['Lift-A'])[0]['total'])

    def test_unknown_lifts_and_dates_are_rejected(self):
        with self.assertRaisesRegex(ValueError,'lift not found'):pdf_chart_selections(self.data,lift_ids=['Missing'])
        with self.assertRaisesRegex(ValueError,'not in this run'):pdf_chart_selections(self.data,'2099-01-01',daily=True)

    def test_relative_days_remain_explicit_and_empty_observations_are_honest(self):
        import pandas as pd
        data=build_chart_data(pd.DataFrame([dict(lift_id='L',movement_type='lift_transfer',start_time=86400)]))
        self.assertEqual(['Day 1','Day 2'],[c['day'] for c in pdf_chart_selections(data,daily=True)])
        self.assertEqual([],pdf_chart_selections(build_chart_data(None,dict(lifts=[dict(id='L')])),daily=True))


class DailyPdfTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.test_report_structure import ReportStructureTests
        cls.reference=ReportStructureTests;cls.reference.setUpClass()

    @classmethod
    def tearDownClass(cls):cls.reference.tearDownClass()

    def test_separate_sections_remain_opt_in_and_render_independently(self):
        from report.amr_report_pdf_report import build_report,DEFAULT_REPORT_SECTION_ORDER
        self.assertNotIn('lift_movement_daily',DEFAULT_REPORT_SECTION_ORDER)
        rows,cfg=chart_fixture();results=dict(self.reference.results,lift_movement_detail=rows)
        for sections,pages in [(['lift_movement_daily'],4),(['lift_movement_stacks','lift_movement_daily'],5)]:
            target=self.reference.folder/('daily-'+str(pages)+'.pdf')
            build_report(results,self.reference.csv,target,include_drawings=False,report_sections=sections,
                lift_chart_config=cfg,lift_chart_lift_ids=['Lift-A'])
            reader=PdfReader(target);text='\n'.join(p.extract_text() for p in reader.pages)
            self.assertEqual(pages,len(reader.pages));self.assertNotIn('Lift-B',text);self.assertNotIn('Unused',text)
            self.assertIn('Lift-A - 2026-01-01 (6 movements)',text)
            self.assertIn('Lift-A - 2026-01-02 (1 movements)',text)
            self.assertEqual('lift_movement_stacks' in sections,'Lift-A - All days (7 movements)' in text)


class DailyPdfUiTests(unittest.TestCase):
    setUpClass=classmethod(charts_ui.LiftMovementChartUiTests.setUpClass.__func__)
    setUp=charts_ui.LiftMovementChartUiTests.setUp
    tearDown=charts_ui.LiftMovementChartUiTests.tearDown
    panel=charts_ui.LiftMovementChartUiTests.panel

    def test_daily_option_and_pdf_lift_selector_reach_report_worker_only(self):
        panel=self.panel();identity=panel.lift_chart_pdf_lift.itemData(1)
        self.assertIsNotNone(identity)
        panel.lift_chart_pdf_lift.setCurrentIndex(1)
        for i in range(panel.sections.count()):
            item=panel.sections.item(i)
            if item.data(Qt.UserRole)=='lift_movement_daily':self.assertEqual(Qt.Unchecked,item.checkState())
            item.setCheckState(Qt.Checked if item.data(Qt.UserRole)=='lift_movement_daily' else Qt.Unchecked)
        self.assertNotIn('--lift-chart-lift-id',panel.lift_chart_arguments())
        with patch('visualiser.project_report_panel.QProcess') as process:
            panel.generate()
            arguments=process.return_value.start.call_args.args[1]
            self.assertIn('lift_movement_daily',arguments)
            self.assertEqual(identity,arguments[arguments.index('--lift-chart-lift-id')+1])
        panel.process=None

    def test_real_daily_worker_uses_frozen_lift_and_records_options(self):
        panel=self.panel();identity=panel.lift_chart_pdf_lift.itemData(1)
        panel.lift_chart_pdf_lift.setCurrentIndex(1)
        self.editor.store.data['lifts']=[]
        for i in range(panel.sections.count()):
            item=panel.sections.item(i)
            item.setCheckState(Qt.Checked if item.data(Qt.UserRole)=='lift_movement_daily' else Qt.Unchecked)
        panel.generate()
        loop=QEventLoop();timer=QTimer();timer.setInterval(20)
        timer.timeout.connect(lambda:loop.quit() if not panel.running() else None)
        timer.start();QTimer.singleShot(60000,loop.quit);loop.exec();timer.stop()
        if panel.running():panel.cancel();self.fail('Daily PDF did not complete within one minute.')
        self.assertIsNotNone(panel.pdf,panel.log.toPlainText())
        manifest=json.loads((panel.output/'report_manifest.json').read_text())
        self.assertEqual('complete',manifest['status'])
        self.assertEqual([identity],manifest['lift_movement_charts']['lift_ids'])
        self.assertTrue(manifest['lift_movement_charts']['daily_section'])
        self.assertIn('daily charts','\n'.join(p.extract_text() for p in PdfReader(panel.pdf).pages))

    def test_app_cli_forwards_pdf_lift_ids(self):
        import amr_app
        with patch('amr_project_report.main',return_value=0) as generate:
            self.assertEqual(0,amr_app.main(['--generate-report','run','out','--sections','lift_movement_daily',
                '--lift-chart-lift-id','Lift-A','--lift-chart-lift-id','Lift-B']))
            args=generate.call_args.args[0]
            self.assertEqual(2,args.count('--lift-chart-lift-id'))


if __name__=='__main__':unittest.main()
