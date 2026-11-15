"""Day-filtered purpose counts, native Excel charts and optional vector PDF."""
from copy import deepcopy
import contextlib
import io
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile

import pandas as pd
from amr_lift_movement_charts import build_chart_data, selected_charts, export_lift_charts_xlsx,extract_chart_data
from tests import test_lift_integration as integration


def chart_fixture():
    cfg=dict(simulation=dict(start_datetime='2026-01-01T00:00:00',end_datetime='2026-01-03T00:00:00'),
             lifts=[dict(id=name,boarding_time_sec=10,door_time_sec=2) for name in ('Lift-A','Lift-B','Unused')])
    rows=[]
    for lift,start,purpose,kind,activity in [
        ('Lift-A','2026-01-01T08:00:00','catering','lift_transfer','loaded_outbound'),
        ('Lift-A','2026-01-01T08:02:00','catering','lift_transfer','loaded_return'),
        ('Lift-A','2026-01-01T08:29:59.999','linen','lift_transfer','loaded_outbound'),
        ('Lift-A','2026-01-01T08:30:00','pharmacy','lift_transfer','loaded_outbound'),
        ('Lift-A','2026-01-01T09:00:00','catering','lift_reposition','empty_lift_reposition'),
        ('Lift-A','2026-01-01T23:59:59.999','mixed','lift_transfer','mixed_load'),
        ('Lift-A','2026-01-02T00:00:00','catering','lift_transfer','loaded_outbound'),
        ('Lift-B','2026-01-02T15:02:00','unknown','lift_transfer','empty_amr_travel'),
        ('Lift-B','2026-01-02T16:00:00','unknown','lift_transfer','unknown')]:
        rows.append(dict(lift_id=lift,start_time=start,service_category=purpose,movement_type=kind,
                         activity_type=activity,origin_level='L00',destination_level='L02',duration_s=30))
    return pd.DataFrame(rows),cfg


def chart_source(folder):
    movements,cfg=chart_fixture();events=[]
    epoch=pd.Timestamp(cfg['simulation']['start_datetime'])
    for i,row in enumerate(movements.to_dict('records')):
        stamp=pd.Timestamp(row['start_time']);purpose=row['service_category']
        categories=['catering','linen'] if purpose=='mixed' else [] if purpose=='unknown' else [purpose]
        details={'from':row['lift_id']+'-F0','to':row['lift_id']+'-F2',
            'fm_lift':dict(loaded=False if row['activity_type']=='empty_amr_travel' else None if purpose=='unknown' else True,
                tasks=[dict(category=c,**{'return':row['activity_type']=='loaded_return'}) for c in categories])}
        if row['movement_type']=='lift_reposition':details['amr_wait_node']='Waiting corridor'
        events.append(dict(event_type='segment_'+row['movement_type'],segment_type=row['movement_type'],
            lift_id=row['lift_id'],sim_datetime=stamp.isoformat(),sim_time_sec=(stamp-epoch).total_seconds(),
            duration_sec=30,task_id=f'T{i}',details=json.dumps(details)))
    fixture=integration.ThirdPartyLiftExportTests()
    with patch.object(fixture,'config',return_value=cfg):return fixture.source(folder,events)


class LiftMovementChartTests(unittest.TestCase):
    def test_day_boundaries_purposes_and_mixed_movements_count_once(self):
        rows,cfg=chart_fixture();data=build_chart_data(rows,cfg)
        self.assertEqual(9,data['movements']);self.assertEqual(['2026-01-01','2026-01-02'],data['days'])
        charts=selected_charts(data,'2026-01-01',False)
        first=charts[0]
        self.assertEqual(5,first['total'])
        series={s['id']:s['values'] for s in first['series']}
        self.assertEqual(2,series['catering'][16]);self.assertEqual(1,series['linen'][16])
        self.assertEqual(1,series['pharmacy'][17]);self.assertEqual(1,series['mixed'][47])
        self.assertNotIn('empty_lift_reposition',series)
        self.assertEqual(0,charts[-1]['total'])
        self.assertEqual(1,selected_charts(data,'2026-01-02')[0]['total'])
        self.assertEqual(7,selected_charts(data)[0]['total'])
        self.assertEqual({'empty_amr_travel','unknown'}, {r['purpose'] for r in data['counts'] if r['lift_id']=='Lift-B'})

    def test_complete_day_grid_preserves_zero_days_and_unused_lifts(self):
        rows,cfg=chart_fixture();cfg['simulation']['end_datetime']='2026-01-05T00:00:00'
        data=build_chart_data(rows,cfg,15)
        self.assertEqual(4,len(data['days']))
        self.assertTrue(all(c['total']==0 for c in selected_charts(data,'2026-01-04')))
        self.assertEqual(96,len(selected_charts(data)[0]['labels']))
        empty=build_chart_data(None,cfg)
        self.assertEqual(0,empty['movements']);self.assertEqual(3,len(selected_charts(empty)))

    def test_elapsed_timestamps_use_frozen_epoch_or_explicit_simulation_days(self):
        frame=pd.DataFrame([dict(lift_id='L',start_time='86,400.125s',movement_type='lift_transfer',service_category='linen')])
        relative=build_chart_data(frame)
        self.assertEqual(['Day 1','Day 2'],relative['days']);self.assertEqual(1,selected_charts(relative,'Day 2')[0]['total'])
        cfg=dict(simulation=dict(start_datetime='2026-05-04T06:00:00'))
        absolute=build_chart_data(frame,cfg)
        self.assertEqual('2026-05-05',absolute['counts'][0]['day']);self.assertEqual(360,absolute['counts'][0]['minute'])

    def test_invalid_day_time_and_intervals_fail_clearly(self):
        rows,cfg=chart_fixture();data=build_chart_data(rows,cfg)
        with self.assertRaisesRegex(ValueError,'not in this run'):selected_charts(data,'2026-02-01')
        for interval in (0,7,True,30.0):
            with self.assertRaises(ValueError):build_chart_data(rows,cfg,interval)
        rows.loc[0,'start_time']='missing'
        with self.assertRaisesRegex(ValueError,'missing or invalid'):build_chart_data(rows,cfg)

    def test_purpose_colour_is_stable_across_days_and_lifts(self):
        rows,cfg=chart_fixture();data=build_chart_data(rows,cfg)
        left=selected_charts(data,'2026-01-01');right=selected_charts(data,'2026-01-02')
        self.assertEqual([(s['id'],s['colour']) for s in left[0]['series']],[(s['id'],s['colour']) for s in right[1]['series']])

    def test_missing_durations_do_not_remove_countable_movements(self):
        import csv
        with tempfile.TemporaryDirectory() as folder:
            source=chart_source(folder)
            with source.open(newline='') as stream:
                rows=list(csv.DictReader(stream))
            for row in rows:row['duration_sec']=''
            with source.open('w',newline='') as stream:
                writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
            _,cfg=chart_fixture()
            data=extract_chart_data(source,cfg)
            self.assertEqual(9,data['movements'])


class LiftMovementWorkbookTests(unittest.TestCase):
    def test_native_stacked_charts_day_validation_and_safe_publication(self):
        with tempfile.TemporaryDirectory() as folder:
            source=chart_source(folder);target=Path(folder)/'charts.xlsx'
            before=source.read_bytes();sidecar=Path(str(source)+'.run.json').read_bytes()
            result=export_lift_charts_xlsx(source,target)
            self.assertEqual(dict(lifts=3,movements=9,days=2),result)
            ns={'c':'http://schemas.openxmlformats.org/drawingml/2006/chart','s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
            with zipfile.ZipFile(target) as archive:
                charts=[n for n in archive.namelist() if '/charts/chart' in n and n.endswith('.xml')]
                self.assertEqual(3,len(charts))
                for name in charts:
                    tree=ET.fromstring(archive.read(name))
                    self.assertEqual('stacked',tree.find('.//c:barChart/c:grouping',ns).get('val'))
                    self.assertEqual('col',tree.find('.//c:barChart/c:barDir',ns).get('val'))
                    self.assertTrue(tree.findall('.//c:ser/c:val/c:numRef/c:f',ns))
                sheet=ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
                selectors=sheet.findall('.//s:dataValidation',ns)
                self.assertTrue(any(s.get('sqref')=='B4' for s in selectors))
                self.assertTrue(any('SUMIFS' in (f.text or '') for f in sheet.findall('.//s:f',ns)))
            self.assertEqual(before,source.read_bytes());self.assertEqual(sidecar,Path(str(source)+'.run.json').read_bytes())
            saved=target.read_bytes()
            with self.assertRaises(ValueError):export_lift_charts_xlsx(source,target,day='2099-01-01')
            self.assertEqual(saved,target.read_bytes())

    def test_failed_or_changed_source_does_not_replace_workbook(self):
        with tempfile.TemporaryDirectory() as folder:
            source=chart_source(folder);target=Path(folder)/'charts.xlsx';target.write_bytes(b'original workbook')
            original=build_chart_data
            def changed(*args,**kwargs):
                result=original(*args,**kwargs);source.write_text(source.read_text()+'\n');return result
            with patch('amr_lift_movement_charts.build_chart_data',side_effect=changed),self.assertRaisesRegex(ValueError,'changed'):
                export_lift_charts_xlsx(source,target)
            self.assertEqual(b'original workbook',target.read_bytes())

    def test_app_and_report_cli_export_charts_without_pdf(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            source=chart_source(folder)
            for index,script in enumerate(('amr_app.py','report/amr_report_main.py')):
                target=Path(folder)/f'charts-{index}.xlsx'
                result=subprocess.run([sys.executable,str(root/script),str(source),'--lift-charts-xlsx',str(target),
                    '--lift-chart-day','2026-01-01','--lift-chart-exclude-reposition'],capture_output=True,text=True)
                self.assertEqual(0,result.returncode,result.stderr);self.assertTrue(target.is_file())
            self.assertEqual([],list(Path(folder).rglob('*.pdf')))

    def test_invalid_mixed_export_flags_are_rejected(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            source=chart_source(folder);target=Path(folder)/'charts.xlsx'
            result=subprocess.run([sys.executable,str(root/'amr_app.py'),str(source),'--lift-charts-xlsx',str(target),
                '--lift-id','Lift-A'],capture_output=True,text=True)
            self.assertNotEqual(0,result.returncode);self.assertFalse(target.exists())


class LiftMovementPdfTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.test_report_structure import ReportStructureTests
        cls.reference=ReportStructureTests;cls.reference.setUpClass()

    @classmethod
    def tearDownClass(cls):cls.reference.tearDownClass()

    def test_optional_section_and_day_filter_produce_per_lift_vector_charts(self):
        from report.amr_report_pdf_report import build_report,DEFAULT_REPORT_SECTION_ORDER,REPORT_SECTION_LABELS
        from pypdf import PdfReader
        self.assertIn('lift_movement_stacks',REPORT_SECTION_LABELS)
        self.assertNotIn('lift_movement_stacks',DEFAULT_REPORT_SECTION_ORDER)
        rows,cfg=chart_fixture();results=dict(self.reference.results,lift_movement_detail=rows)
        target=self.reference.folder/'stacked.pdf'
        build_report(results,self.reference.csv,target,include_drawings=False,report_sections=['lift_movement_stacks'],
                     lift_chart_config=cfg,lift_chart_day='2026-01-01',lift_chart_include_reposition=False)
        pages=PdfReader(target).pages;text='\n'.join(p.extract_text() for p in pages)
        self.assertIn('Lift-A - 2026-01-01 (5 movements)',text)
        self.assertIn('Unused - 2026-01-01 (0 movements)',text)
        self.assertIn('Catering',text);self.assertIn('Empty lift repositioning is excluded.',text)
        self.assertTrue(any(' re' in p.get_contents().get_data().decode('latin1') for p in pages))


if __name__=='__main__':unittest.main()
