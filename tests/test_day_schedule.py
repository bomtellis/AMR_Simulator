"""Graphical schedule contracts, draft ownership, and FM forecast integration."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'visualiser'))
from PySide6.QtCore import Qt, QPoint, QThreadPool, QCoreApplication, QEvent
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
from amr_demand_schedule import (arrangement, clock, edit_demand, edit_fm, invalid_slots,
    minutes, rules, rule_times, segments, span, validated_generation)
from visualiser.day_schedule import DaySchedulePanel, ScheduleCanvas
from visualiser.dialogs import TaskGenerationSettingsDialog
from tests.test_configured_group_editor import config as group_config
from tests.test_fm_logistics import fixture, settings
from amr_fm_forecast import compare, native_demand


def test_font(app):
    # The Windows offscreen Qt plugin has no system font database.
    if not QFontDatabase.families():
        font=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts/segoeui.ttf'
        if font.exists():
            QFontDatabase.addApplicationFont(str(font))
            app.setFont(QFont('Segoe UI',9))


def window_config():
    config = group_config()
    category = config['task_generation']['categories']['stores']
    for payload in [category['department_groups'][0]['payload'], *category['departments'].values()]:
        payload.update(generation_mode='timeframe', timeframe_start='22:00', timeframe_end='02:00',
                       days_active=['mon', 'tue'], frequency_per_day=12, timeframe_payload_multiple=3)
    return config


class ScheduleAdapterTests(unittest.TestCase):
    def test_group_shown_once_and_independent_department_kept(self):
        config = window_config()
        category = config['task_generation']['categories']['stores']
        category['departments']['Z'] = dict(category['departments']['D'], generation_mode='scheduled', scheduled_times=['13:00'])
        rows = [row for row in rules(config['task_generation']) if row.category == 'stores']
        self.assertEqual([('group', 'stores', 'GROUP-1'), ('department', 'stores', 'Z')], [row.identity for row in rows])

    def test_group_edit_preserves_identity_other_rules_and_department_endpoints(self):
        config = window_config()
        before = deepcopy(config)
        category = config['task_generation']['categories']['stores']
        category['department_groups'].append(dict(id='GROUP-2', departments=['D'], payload=dict(
            deepcopy(category['department_groups'][0]['payload']), timeframe_start='09:00', timeframe_end='10:00')))
        updated = edit_demand(config['task_generation'], ('group', 'stores', 'GROUP-1'), 'window', 23*60, 180)
        result = updated['categories']['stores']
        self.assertEqual('23:00', result['department_groups'][0]['payload']['timeframe_start'])
        self.assertEqual('02:00', result['department_groups'][0]['payload']['timeframe_end'])
        self.assertEqual(category['department_groups'][1], result['department_groups'][1])
        self.assertEqual(['D', 'E'], result['department_groups'][0]['departments'])
        self.assertEqual('C', result['departments']['E']['dropoff_location'])
        self.assertEqual(12, result['department_groups'][0]['payload']['frequency_per_day'])
        self.assertEqual(3, result['department_groups'][0]['payload']['timeframe_payload_multiple'])
        self.assertEqual(before['task_generation']['categories']['stores']['department_groups'][0], category['department_groups'][0])

    def test_midnight_full_day_and_exact_minute_values(self):
        config = window_config()['task_generation']
        identity = ('group', 'stores', 'GROUP-1')
        for start, duration, expected in [(0, 1440, ('00:00','24:00')), (23*60+57, 9, ('23:57','00:06')),
                                         (60, 1440, ('01:00','01:00'))]:
            updated = edit_demand(config, identity, 'window', start, duration)
            payload = updated['categories']['stores']['department_groups'][0]['payload']
            self.assertEqual(expected, (payload['timeframe_start'], payload['timeframe_end']))
            row = next(row for row in rules(updated) if row.identity == identity)
            self.assertEqual(duration, rule_times(row)[0][2])
        self.assertEqual([(1380,1440),(0,120)], segments(1380,180))
        with self.assertRaises(ValueError): minutes('24:01', end=True)
        with self.assertRaises(ValueError): edit_demand(config, identity, 'window', 0, 0)

    def test_clock_marker_collision_rejected_without_changing_input(self):
        config = group_config()['task_generation']
        identity = ('group','stores','GROUP-1')
        config['categories']['stores']['department_groups'][0]['payload']['scheduled_times'] = ['08:00','09:00']
        before = deepcopy(config)
        with self.assertRaises(ValueError): edit_demand(config, identity, '08:00', 540)
        self.assertEqual(before, config)
        edited = edit_demand(config, identity, '08:00', 481)
        self.assertEqual(['08:01','09:00'], edited['categories']['stores']['department_groups'][0]['payload']['scheduled_times'])

    def test_fm_window_movement_preserves_offsets_and_rejects_invalid_resize(self):
        config = fixture()
        baseline, plan = settings(config)
        policy = plan['categories']['catering']
        slot = next(iter(policy['slots']))
        window = policy['slots'][slot]
        first = minutes(window['earliest'])
        length = span(first, minutes(window['deadline']))
        changed = edit_fm(plan, 'catering', slot, None, first + 5, length)
        self.assertEqual(window['offsets'], changed['categories']['catering']['slots'][slot]['offsets'])
        with self.assertRaises(ValueError): edit_fm(plan, 'catering', slot, None, first, 1)
        cohort = next(iter(window['offsets']))
        with self.assertRaises(ValueError): edit_fm(plan, 'catering', slot, cohort, minutes(window['deadline']))
        self.assertEqual(window, plan['categories']['catering']['slots'][slot])

    def test_native_slot_change_requires_regeneration(self):
        config = fixture()
        _, plan = settings(config)
        generation = dict(config['task_generation'], fm_logistics=plan)
        self.assertEqual([], invalid_slots(generation))
        updated = edit_demand(generation, ('department','catering','D1'), '00:45', 44)
        self.assertIn(('catering','00:45'), invalid_slots(updated))

    def test_suggestion_uses_all_eligible_categories_and_existing_ranking(self):
        config = fixture()
        before = deepcopy(config)
        result = arrangement(config, suggest=True)
        candidate = next(row for row in result['comparison']['results'] if row['strategy'] == 'manual')['settings']
        self.assertEqual({'catering','pharmacy'}, set(candidate['categories']))
        expected = compare(config, candidate, result['baseline'])
        self.assertEqual(expected, result['comparison'])
        score = lambda row: tuple(row['totals'].get(key,0) for key in ('unresolved','late','peak_lift_seconds','lift_wait_seconds'))
        current = next(row for row in expected['results'] if row['strategy']=='current')
        self.assertEqual(expected['results'][0]['strategy'] if score(expected['results'][0]) < score(current)
                         else 'current', result['selected'])
        self.assertEqual(before, config)
        generation = validated_generation(config, candidate, result['baseline'])
        self.assertEqual(before['task_generation']['categories'], generation['categories'])
        planned = native_demand(dict(config, task_generation=generation))
        self.assertEqual(len(result['baseline']['tasks']), len(planned['tasks']))

    def test_missing_department_assignments_require_existing_fm_review(self):
        config=fixture()
        config['task_generation']['categories']['catering']['departments']['MISSING'] = \
            config['task_generation']['categories']['catering']['departments'].pop('D1')
        with self.assertRaisesRegex(ValueError,'missing departments'):
            arrangement(config,suggest=True)

    def test_no_improvement_retains_current_timings(self):
        config=fixture()
        config['task_generation']['categories'].pop('pharmacy')
        config['task_generation']['categories'].pop('linen')
        config['task_generation']['categories']['catering']['departments']['D1']['return_enabled']=False
        config['task_generation']['categories']['catering']['departments']['D1']['dropoff_location']='A'
        result=arrangement(config,suggest=True)
        self.assertEqual('current',result['selected'])

    def test_fm_windows_are_filtered_by_matching_native_slot_and_day(self):
        cfg={'enabled':True,'generation_mode':'scheduled','scheduled_times':['09:00'],'days_active':['mon']}
        rule=rules({'categories':{'stores':cfg}})[0]
        self.assertTrue(DaySchedulePanel.matches_slot(rule,'09:00'))
        self.assertFalse(DaySchedulePanel.matches_slot(rule,'10:00'))


class ScheduleWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        test_font(cls.app)

    def setUp(self):
        self.widgets = []

    def tearDown(self):
        QThreadPool.globalInstance().waitForDone(10000)
        self.app.processEvents()
        for widget in self.widgets:
            widget.close()
            widget.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def editor(self, config=None, project=False):
        config = config or window_config()
        saved = []
        dialog = TaskGenerationSettingsDialog(None, config['task_generation'],
            [row['name'] for row in config['locations']], ['Box'], [], config['departments'], saved.append,
            project_configuration=(lambda: config) if project else None)
        self.widgets.append(dialog)
        dialog.resize(1120,850)
        dialog.show()
        dialog.schedule_tabs.setCurrentWidget(dialog.day_schedule)
        self.app.processEvents()
        return dialog, saved

    def finish(self, panel):
        self.assertTrue(QThreadPool.globalInstance().waitForDone(10000))
        self.app.processEvents()
        self.assertIsNone(panel.job)

    def test_drag_math_move_both_handles_and_five_minute_steps(self):
        self.assertEqual((485,120), ScheduleCanvas.drag_times(480,120,'move',7))
        self.assertEqual((485,115), ScheduleCanvas.drag_times(480,120,'start',7))
        self.assertEqual((480,125), ScheduleCanvas.drag_times(480,120,'end',7))
        self.assertEqual((0,120), ScheduleCanvas.drag_times(1435,120,'move',5))

    def test_exact_edit_cancel_save_and_reopen(self):
        config = window_config()
        before = deepcopy(config)
        dialog, saved = self.editor(config)
        panel = dialog.day_schedule
        identity = ('native','group','stores','GROUP-1','window')
        panel.select(identity)
        panel.start.setText('23:57')
        panel.end.setText('00:06')
        panel.set_exact()
        self.assertEqual('23:57', dialog.config['categories']['stores']['department_groups'][0]['payload']['timeframe_start'])
        self.assertEqual(before, config)
        dialog.reject()
        self.assertFalse(saved)
        second, saved = self.editor(config)
        second.day_schedule.edit_item(identity, 1380, 180)
        second.accept()
        self.assertEqual(1,len(saved))
        reopened, _ = self.editor(dict(config, task_generation=json.loads(json.dumps(saved[0]))))
        self.assertEqual('23:00', reopened.config['categories']['stores']['department_groups'][0]['payload']['timeframe_start'])

    def test_escape_cancels_real_mouse_drag(self):
        dialog, _ = self.editor()
        canvas = dialog.day_schedule.canvas
        before = deepcopy(dialog.config)
        identity = ('native','group','stores','GROUP-1','window')
        rect = next(rect for rect,item,edge in canvas.hits if item['id']==identity and edge=='move')
        point = rect.center().toPoint()
        QTest.mousePress(canvas, Qt.LeftButton, pos=point)
        self.assertIsNotNone(canvas.drag)
        QTest.mouseMove(canvas, point + QPoint(25,0))
        QTest.keyClick(canvas, Qt.Key_Escape)
        QTest.mouseRelease(canvas, Qt.LeftButton, pos=point + QPoint(25,0))
        self.assertIsNone(canvas.drag)
        self.assertEqual(before,dialog.config)

    def test_mouse_move_and_keyboard_nudge_commit_once(self):
        dialog, _ = self.editor()
        panel, canvas = dialog.day_schedule, dialog.day_schedule.canvas
        identity = ('native','group','stores','GROUP-1','window')
        rect = next(rect for rect,item,edge in canvas.hits if item['id']==identity and edge=='move')
        point = rect.center().toPoint()
        QTest.mousePress(canvas,Qt.LeftButton,pos=point)
        QTest.mouseMove(canvas,point+QPoint(30,0))
        self.assertEqual('22:00', dialog.config['categories']['stores']['department_groups'][0]['payload']['timeframe_start'])
        QTest.mouseRelease(canvas,Qt.LeftButton,pos=point+QPoint(30,0))
        payload = dialog.config['categories']['stores']['department_groups'][0]['payload']
        moved = minutes(payload['timeframe_start'])
        self.assertNotEqual(1320,moved)
        self.assertEqual(240,span(moved,minutes(payload['timeframe_end'])))
        QTest.keyClick(canvas,Qt.Key_Right)
        self.assertEqual(clock(moved+5),dialog.config['categories']['stores']['department_groups'][0]['payload']['timeframe_start'])

    def test_overlapping_markers_pack_and_day_filter(self):
        config = group_config()
        config['task_generation']['categories']['stores']['department_groups'][0]['payload'].update(
            scheduled_times=['08:00','08:05'], days_active=['mon'])
        dialog,_ = self.editor(config)
        panel = dialog.day_schedule
        lanes = [row for row in panel.canvas.rows if any(item.get('rule')==('group','stores','GROUP-1')
                                                        for item in row.get('items',[]))]
        self.assertEqual(2,len(lanes))
        panel.day.setCurrentIndex(1)
        self.assertFalse(any(item.get('rule')==('group','stores','GROUP-1') for item in panel.items.values()))

    def test_fm_suggestion_is_draft_only_then_saved_without_changing_demand(self):
        config = fixture()
        dialog,saved = self.editor(config,project=True)
        panel = dialog.day_schedule
        categories = deepcopy(dialog.config['categories'])
        panel.calculate(True)
        self.finish(panel)
        self.assertIsNotNone(panel.comparison, panel.status.text())
        self.assertNotIn('fm_logistics',dialog.config)
        # Choose a planned option even if this small fixture ranks current first.
        panel.options.setCurrentIndex(panel.options.findData('coordinated'))
        self.assertTrue(panel.use.isEnabled())
        panel.use_arrangement()
        self.finish(panel)
        self.assertIn('fm_logistics',dialog.config,panel.status.text())
        self.assertEqual(categories,dialog.config['categories'])
        self.assertFalse(panel.dirty)
        dialog.accept()
        self.assertEqual(1,len(saved))

    def test_manual_plan_change_invalidates_use_and_bad_resize_is_rejected(self):
        config = fixture()
        dialog,_ = self.editor(config,project=True)
        panel = dialog.day_schedule
        panel.calculate(True)
        self.finish(panel)
        panel.options.setCurrentIndex(panel.options.findData('coordinated'))
        identity,item = next((key,item) for key,item in panel.items.items() if key[0]=='fm' and key[3] is None)
        original = deepcopy(panel.plan)
        panel.edit_item(identity,item['start'],1)
        self.assertEqual(original,panel.plan)
        panel.edit_item(identity,item['start']+5,item['duration'])
        self.assertIsNone(panel.comparison)
        self.assertFalse(panel.use.isEnabled())
        self.assertTrue(panel.dirty)

    def test_external_change_during_job_rejects_result(self):
        config=fixture()
        dialog,_=self.editor(config,project=True)
        panel=dialog.day_schedule
        signature=panel.signature()
        called=[]
        panel.job_context=(signature,called.append)
        panel.job=object()
        config['simulation']['end_datetime']='2026-01-05T02:00:00'
        panel.finish_job({},'')
        self.assertFalse(called)
        self.assertIn('Inputs changed',panel.status.text())

    def test_enabled_orphan_plan_blocks_save_but_disable_allows_it(self):
        config=fixture()
        _,plan=settings(config)
        config['task_generation']['fm_logistics']=plan
        dialog,saved=self.editor(config,project=True)
        panel=dialog.day_schedule
        identity=('native','department','catering','D1','00:45')
        panel.edit_item(identity,44,0)
        with patch.object(QMessageBox,'critical') as error:
            dialog.accept()
        error.assert_called_once()
        self.assertFalse(saved)
        panel.disable_plan()
        dialog.accept()
        self.assertEqual(1,len(saved))

    def test_actual_resize_handles_and_zoom_fit(self):
        dialog,_=self.editor()
        canvas=dialog.day_schedule.canvas
        identity=('native','group','stores','GROUP-1','window')
        for edge in ('start','end'):
            self.app.processEvents()
            rect=next(rect for rect,item,part in canvas.hits if item['id']==identity and part==edge)
            point=rect.center().toPoint()
            old=deepcopy(dialog.config)
            QTest.mousePress(canvas,Qt.LeftButton,pos=point)
            self.assertEqual(edge,canvas.drag['edge'])
            QTest.mouseMove(canvas,point+QPoint(12,0))
            QTest.mouseRelease(canvas,Qt.LeftButton,pos=point+QPoint(12,0))
            self.assertNotEqual(old,dialog.config)
        dialog.day_schedule.zoom.setValue(250)
        self.assertEqual(2.5,canvas.zoom)
        dialog.day_schedule.fit.click()
        self.assertEqual(1,canvas.zoom)

    def test_discarding_suggestion_does_not_apply_plan(self):
        dialog,_=self.editor(fixture(),project=True)
        panel=dialog.day_schedule
        panel.calculate(True)
        self.finish(panel)
        self.assertTrue(panel.dirty)
        panel.discard.click()
        self.assertFalse(panel.dirty)
        self.assertFalse(panel.plan['enabled'])
        self.assertNotIn('fm_logistics',dialog.config)

    def test_department_editor_is_transactional_with_outer_dialog(self):
        config=window_config()
        saved=[]
        original=deepcopy(config['departments'])
        changed=deepcopy(original)
        changed[0]['name']='New department name'
        dialog=TaskGenerationSettingsDialog(None,config['task_generation'],['A','B','C'],['Box'],[],
            original,lambda value:None,open_departments=lambda draft:changed,on_departments_save=saved.append)
        self.widgets.append(dialog)
        dialog.day_schedule.refresh()
        dialog._open_schedule_rule(('category','waste',''))
        self.assertEqual(changed,dialog.departments)
        self.assertFalse(saved)
        self.assertEqual(original,config['departments'])
        dialog.reject()
        self.assertFalse(saved)


class ScheduleProjectIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests import test_corridor_editing as editing
        editing.CorridorEditingUiTests.setUpClass.__func__(cls)
        test_font(cls.app)

    def setUp(self):
        from tests import test_corridor_editing as editing
        editing.CorridorEditingUiTests.setUp(self)

    def tearDown(self):
        from tests import test_corridor_editing as editing
        editing.CorridorEditingUiTests.tearDown(self)

    def test_demand_timeline_is_one_undoable_edit_and_reopens(self):
        from models import JsonStore
        from amr_project import Project
        from PySide6.QtWidgets import QFileDialog
        self.editor.store=JsonStore(window_config())
        self.editor._reset_edit_history()
        before=deepcopy(self.editor.store.data)

        def edit(dialog):
            dialog.schedule_tabs.setCurrentWidget(dialog.day_schedule)
            dialog.day_schedule.edit_item(('native','group','stores','GROUP-1','window'),1380,180)
            dialog.accept()
            return QDialog.Accepted

        with patch('app.TaskGenerationSettingsDialog.exec',new=edit),patch.object(QMessageBox,'critical') as error:
            self.editor.manage_task_generation()
        error.assert_not_called()
        after=deepcopy(self.editor.store.data)
        self.assertEqual('23:00',after['task_generation']['categories']['stores']['department_groups'][0]['payload']['timeframe_start'])
        self.assertTrue(self.editor.undo_edit())
        self.assertEqual(before,self.editor.store.data)
        self.assertTrue(self.editor.redo_edit())
        self.assertEqual(after,self.editor.store.data)
        path=Path(self.temp.name)/'day-schedule.amrproj'
        with patch.object(QFileDialog,'getSaveFileName',return_value=(str(path),'')):
            self.assertTrue(self.editor.save_project(save_as=True))
        self.assertEqual(after,Project.open(path).configuration())

    def test_fm_screen_uses_shared_timeline_and_applies_undoably(self):
        from models import JsonStore
        self.editor.store=JsonStore(fixture())
        self.editor._reset_edit_history()
        before=deepcopy(self.editor.store.data)
        self.editor.show_fm_logistics()
        host=self.editor.fm_logistics_panel
        host.tabs.setCurrentWidget(host.day_schedule)
        panel=host.day_schedule
        panel.calculate(True)
        QThreadPool.globalInstance().waitForDone(10000)
        self.app.processEvents()
        self.assertIsNotNone(panel.comparison,panel.status.text())
        panel.options.setCurrentIndex(panel.options.findData('coordinated'))
        panel.use_arrangement()
        QThreadPool.globalInstance().waitForDone(10000)
        self.app.processEvents()
        self.assertIn('fm_logistics',self.editor.store.data['task_generation'],panel.status.text())
        self.assertTrue(self.editor.undo_edit())
        self.assertEqual(before,self.editor.store.data)
        self.assertTrue(self.editor.redo_edit())
        opened=[]
        def reject_dialog(dialog):
            opened.append(dialog)
            return QDialog.Rejected
        with patch('app.TaskGenerationSettingsDialog.exec',new=reject_dialog):
            panel.open_rule(('department','catering','D1'))
        self.assertEqual(1,len(opened))


if __name__=='__main__':
    unittest.main()
