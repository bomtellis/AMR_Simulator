"""Daily count reconciliation, fixed rulers, category notes and complete exports."""
from copy import deepcopy
from datetime import datetime
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'visualiser'))
from PySide6.QtCore import Qt, QThreadPool, QCoreApplication, QEvent
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QMessageBox
from pypdf import PdfReader
from amr_day_trip_preview import day_trip_preview, run_dates, summarise_day, write_preview_pdf, stacked_bins
from amr_demand_preview import build_demand_preview
from amr_demand_schedule import edit_category_notes
from visualiser.dialogs import TaskGenerationSettingsDialog
from visualiser.day_trip_preview import DayTripPreviewDialog, TripPreviewCanvas
from tests.test_day_schedule import window_config, test_font
from tests.test_fm_logistics import fixture, settings


def day_config():
    config=fixture()
    config['simulation']['end_datetime']='2026-01-07T00:00:00'
    config['task_generation']['categories']={'catering':config['task_generation']['categories']['catering']}
    cfg=config['task_generation']['categories']['catering']['departments']['D1']
    cfg.update(scheduled_times=['00:00','23:59'],return_enabled=False)
    return config


class DayTripCountTests(unittest.TestCase):
    def test_counts_reconcile_with_generator_and_do_not_mutate_inputs(self):
        config=fixture()
        original=deepcopy(config)
        result=day_trip_preview(config,'2026-01-05')
        expected=build_demand_preview(config)
        self.assertEqual(len(expected['tasks']),result['trips'])
        self.assertEqual(sum(float(row['quantity']) for row in expected['tasks']),result['quantity'])
        self.assertEqual(result['trips'],sum(row['trips'] for row in result['categories']))
        self.assertEqual(result['trips'],sum(result['bins']))
        self.assertEqual(original,config)

    def test_midnight_is_counted_once_per_day(self):
        config=day_config()
        first=day_trip_preview(config,'2026-01-05')
        second=day_trip_preview(config,'2026-01-06')
        self.assertEqual((2,2),(first['trips'],second['trips']))
        self.assertEqual((1,1),(first['bins'][0],first['bins'][-1]))
        self.assertEqual('2026-01-06',run_dates(config)[2].isoformat())
        with self.assertRaisesRegex(ValueError,'within the simulation period'):
            day_trip_preview(config,'2026-01-07')

    def test_fortnightly_calendar_keeps_original_run_start(self):
        config=day_config()
        config['simulation']['end_datetime']='2026-01-21T00:00:00'
        cfg=config['task_generation']['categories']['catering']['departments']['D1']
        cfg['run_every_fortnight']=True
        self.assertEqual(2,day_trip_preview(config,'2026-01-05')['trips'])
        self.assertEqual(0,day_trip_preview(config,'2026-01-12')['trips'])
        self.assertEqual(2,day_trip_preview(config,'2026-01-19')['trips'])

    def test_fm_plan_moves_profile_without_changing_counts(self):
        config=fixture()
        _,plan=settings(config)
        native=day_trip_preview(config,'2026-01-05')
        config['task_generation']['fm_logistics']=plan
        planned=day_trip_preview(config,'2026-01-05',source='FM plan')
        self.assertEqual(native['trips'],planned['trips'])
        self.assertNotEqual(native['bins'],planned['bins'])
        self.assertEqual('FM plan',planned['source'])

    def test_unknown_work_is_identified_not_asserted_to_be_zero(self):
        preview=day_trip_preview(fixture(),'2026-01-05')
        linen=next(row for row in preview['categories'] if row['key']=='linen')
        self.assertTrue(linen['additional'])
        self.assertTrue(preview['additional'])
        self.assertIn('Return journeys',preview['explanation'])

    def test_category_and_scope_notes_are_kept_separately(self):
        config=fixture()
        config['task_generation']['categories']['catering']['notes']='Meals must arrive before the ward round.'
        config['task_generation']['categories']['catering']['departments']['D1']['notes']='Use the service entrance.'
        result=day_trip_preview(config,'2026-01-05')
        row=next(row for row in result['categories'] if row['key']=='catering')
        self.assertEqual('Meals must arrive before the ward round.',row['notes'])
        self.assertIn('Use the service entrance.',row['scope_notes'])

    def test_notes_adapter_preserves_groups_and_quantities(self):
        config=window_config()['task_generation']
        before=deepcopy(config)
        updated=edit_category_notes(config,'stores','  Separate clean and dirty loads.  ')
        self.assertEqual('Separate clean and dirty loads.',updated['categories']['stores']['notes'])
        self.assertEqual(before['categories']['stores']['department_groups'],updated['categories']['stores']['department_groups'])
        self.assertEqual(before,config)

    def test_stacked_intervals_preserve_category_and_daily_totals(self):
        preview=day_trip_preview(fixture(),'2026-01-05')
        for interval in (15,30,60):
            series,totals=stacked_bins(preview,interval)
            self.assertEqual(1440//interval,len(totals))
            self.assertEqual(preview['trips'],sum(totals))
            self.assertEqual(totals,[sum(row['bins'][i] for row in series) for i in range(len(totals))])
            self.assertEqual([row['trips'] for row in preview['categories']],[sum(row['bins']) for row in series])
            self.assertEqual(len(series),len({row['color'] for row in series}))


class DayTripPreviewWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        test_font(cls.app)

    def setUp(self):
        self.widgets=[]

    def tearDown(self):
        QThreadPool.globalInstance().waitForDone(10000)
        self.app.processEvents()
        for widget in self.widgets:
            widget.close();widget.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)

    def finish(self,popup):
        QThreadPool.globalInstance().waitForDone(10000)
        self.app.processEvents()
        self.assertIsNone(popup.job,popup.status.text())

    def popup(self,config=None):
        config=config or fixture()
        popup=DayTripPreviewDialog(lambda:config,lambda:'Demand')
        self.widgets.append(popup)
        popup.show()
        popup.refresh_preview()
        self.finish(popup)
        self.assertIsNotNone(popup.preview,popup.status.text())
        return popup,config

    def editor(self,config=None):
        config=config or window_config()
        saved=[]
        dialog=TaskGenerationSettingsDialog(None,config['task_generation'],
            [row['name'] for row in config['locations']],['Box'],[],config['departments'],saved.append,
            project_configuration=lambda:config)
        self.widgets.append(dialog)
        dialog.show()
        dialog.schedule_tabs.setCurrentWidget(dialog.day_schedule)
        self.app.processEvents()
        return dialog,saved

    def test_popout_is_modeless_and_exports_are_available_after_generation(self):
        popup,_=self.popup()
        self.assertFalse(popup.isModal())
        self.assertTrue(popup.pdf.isEnabled())
        self.assertTrue(popup.png.isEnabled())
        self.assertIn('planned trips',popup.totals.text())

    def test_category_notes_save_without_detaching_shared_groups(self):
        dialog,saved=self.editor()
        dialog._loading=True
        dialog._refresh_category_list(select_key='stores')
        dialog.current_key='stores'
        dialog._refresh_department_list(select_dept_id='D')
        dialog._load_category('stores')
        dialog._loading=False
        before=deepcopy(dialog.config['categories']['stores']['department_groups'])
        dialog.category_notes_edit.setPlainText('Keep this window clear of the staff shift change.')
        dialog._store_current_category()
        self.assertEqual(before,dialog.config['categories']['stores']['department_groups'])
        dialog.accept()
        self.assertEqual('Keep this window clear of the staff shift change.',saved[0]['categories']['stores']['notes'])

    def test_day_schedule_notes_and_popup_refresh_follow_edits(self):
        config=window_config()
        config['simulation'].update(start_datetime='2026-01-05T00:00:00',end_datetime='2026-01-06T00:00:00')
        dialog,_=self.editor(config)
        panel=dialog.day_schedule
        identity=('native','group','stores','GROUP-1','window')
        panel.select(identity)
        panel.category_notes.setPlainText('Separate linen from food.')
        panel.save_notes.click()
        self.assertEqual('Separate linen from food.',dialog.config['categories']['stores']['notes'])
        panel.preview_button.click()
        popup=panel._trip_preview
        self.finish(popup)
        self.assertIsNotNone(popup.preview,popup.status.text())
        before=deepcopy(popup.preview['bins'])
        panel.edit_item(identity,21*60,180)
        self.assertFalse(popup.pdf.isEnabled())
        popup.refresh_preview()
        self.finish(popup)
        self.assertNotEqual(before,popup.preview['bins'])

    def test_ruler_remains_at_top_when_category_rows_scroll(self):
        dialog,_=self.editor()
        panel=dialog.day_schedule
        self.app.processEvents()
        before=panel.ruler.grab().toImage()
        panel.scroll.verticalScrollBar().setValue(150)
        self.app.processEvents()
        self.assertEqual(0,panel.ruler.y())
        self.assertIs(panel.ruler.parent(),panel.scroll.viewport())
        self.assertEqual(before,panel.ruler.grab().toImage())
        popup,_=self.popup()
        popup.resize(900,400)
        self.app.processEvents()
        before=popup.ruler.grab().toImage()
        popup.scroll.verticalScrollBar().setValue(180)
        self.app.processEvents()
        self.assertEqual(0,popup.ruler.y())
        self.assertEqual(before,popup.ruler.grab().toImage())

    def test_interval_changes_update_chart_without_recalculating_demand(self):
        popup,_=self.popup()
        self.assertEqual(24,len(popup.canvas.totals))
        signature=popup.valid_signature
        popup.interval.setCurrentIndex(popup.interval.findData(15))
        self.assertEqual(96,len(popup.canvas.totals))
        self.assertEqual(signature,popup.valid_signature)
        self.assertIsNone(popup.job)
        self.assertTrue(popup.pdf.isEnabled())

    def test_exports_include_categories_beyond_visible_view_and_notes(self):
        config=fixture()
        config['task_generation']['categories']['linen']['notes']='FINAL CATEGORY NOTE - check late collections.'
        popup,_=self.popup(config)
        popup.resize(850,360)
        self.app.processEvents()
        with TemporaryDirectory() as folder:
            png=Path(folder)/'preview.png';pdf=Path(folder)/'preview.pdf'
            popup.export_to(png,'png')
            popup.export_to(pdf,'pdf')
            image=QImage(str(png))
            self.assertFalse(image.isNull())
            self.assertGreater(image.height(),popup.scroll.viewport().height()*2)
            self.assertEqual(2800,image.width())
            text=''.join(page.extract_text() for page in PdfReader(pdf).pages)
            self.assertIn('FINAL CATEGORY NOTE',text)
            for row in popup.preview['categories']:
                self.assertIn(row['label'],text)

    def test_pdf_paginates_with_repeated_ruler_and_long_notes(self):
        result=day_trip_preview(fixture(),'2026-01-05')
        template=deepcopy(result['categories'][0])
        result['categories']=[dict(deepcopy(template),key=f'category-{i}',label=f'Category {i}',
            notes='Schedule note '+str(i)+' - '+('All loads must follow local operating hours. '*8)) for i in range(22)]
        with TemporaryDirectory() as folder:
            path=Path(folder)/'many.pdf'
            write_preview_pdf(path,result)
            pages=PdfReader(path).pages
            self.assertGreater(len(pages),1)
            self.assertIn('Category 21',''.join(page.extract_text() for page in pages))
            for page in pages:
                text=page.extract_text()
                self.assertIn('00:00',text)
                self.assertIn('24:00',text)

    def test_stale_preview_cannot_overwrite_export_target(self):
        popup,config=self.popup()
        config['task_generation']['categories']['catering']['notes']='Changed after preview.'
        with TemporaryDirectory() as folder:
            target=Path(folder)/'preview.png'
            target.write_bytes(b'old file')
            with self.assertRaisesRegex(ValueError,'Refresh'):
                popup.export_to(target,'png')
            self.assertEqual(b'old file',target.read_bytes())
        popup.timer.stop()

    def test_worker_result_from_old_inputs_is_discarded(self):
        popup,config=self.popup()
        old=deepcopy(popup.preview)
        popup.job_signature=popup.signature()
        popup.job=object()
        config['task_generation']['categories']['catering']['notes']='Changed.'
        popup.finish_preview_job(dict(old,trips=999),'')
        popup.timer.stop()
        self.assertNotEqual(999,popup.preview['trips'])
        self.assertFalse(popup.pdf.isEnabled())


if __name__=='__main__':
    unittest.main()
