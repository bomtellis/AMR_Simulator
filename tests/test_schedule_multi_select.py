"""Visible group notes, simultaneous schedule moves and selection gestures."""
from copy import deepcopy
import os
from pathlib import Path
import sys
import unittest

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'visualiser'))
from PySide6.QtCore import Qt, QPoint, QCoreApplication, QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from amr_demand_schedule import move_demand_selection, move_fm_selection
from visualiser.dialogs import TaskGenerationSettingsDialog
from tests.test_day_schedule import window_config, test_font
from tests.test_configured_group_editor import config as grouped_config
from tests.test_fm_logistics import fixture, settings


class MultiMoveAdapterTests(unittest.TestCase):
    def test_adjacent_selected_releases_move_without_intermediate_collision(self):
        config=grouped_config()['task_generation']
        payload=config['categories']['stores']['department_groups'][0]['payload']
        payload['scheduled_times']=['08:00','08:05','10:00']
        before=deepcopy(config)
        result=move_demand_selection(config,[(('group','stores','GROUP-1'),'08:00'),
                                            (('group','stores','GROUP-1'),'08:05')],5)
        self.assertEqual(['08:05','08:10','10:00'],result['categories']['stores']['department_groups'][0]['payload']['scheduled_times'])
        self.assertEqual(before,config)

    def test_collision_with_unselected_release_rejects_entire_move(self):
        config=grouped_config()['task_generation']
        payload=config['categories']['stores']['department_groups'][0]['payload']
        payload['scheduled_times']=['08:00','08:05']
        before=deepcopy(config)
        with self.assertRaises(ValueError):
            move_demand_selection(config,[(('group','stores','GROUP-1'),'08:00')],5)
        self.assertEqual(before,config)

    def test_multiple_windows_keep_lengths_notes_members_and_midnight_wrap(self):
        config=window_config()['task_generation']
        category=config['categories']['stores']
        first=category['department_groups'][0]
        first['payload']['notes']='Night collection'
        category['department_groups'].append(dict(id='GROUP-2',departments=['D'],payload=dict(
            deepcopy(first['payload']),timeframe_start='23:00',timeframe_end='01:00',notes='Separate run')))
        result=move_demand_selection(config,[(('group','stores','GROUP-1'),'window'),
                                            (('group','stores','GROUP-2'),'window')],120)
        groups=result['categories']['stores']['department_groups']
        self.assertEqual(('00:00','04:00'),(groups[0]['payload']['timeframe_start'],groups[0]['payload']['timeframe_end']))
        self.assertEqual(('01:00','03:00'),(groups[1]['payload']['timeframe_start'],groups[1]['payload']['timeframe_end']))
        self.assertEqual('Night collection',groups[0]['payload']['notes'])
        self.assertEqual('Separate run',groups[1]['payload']['notes'])
        self.assertEqual(first['departments'],groups[0]['departments'])

    def test_fm_window_and_its_selected_cohort_are_not_moved_twice(self):
        _,plan=settings(fixture())
        policy=plan['categories']['catering']
        slot=next(iter(policy['slots']))
        cohort=next(iter(policy['slots'][slot]['offsets']))
        old=deepcopy(plan)
        result=move_fm_selection(plan,[('catering',slot,None),('catering',slot,cohort)],5)
        self.assertEqual(old['categories']['catering']['slots'][slot]['offsets'],
                         result['categories']['catering']['slots'][slot]['offsets'])
        self.assertEqual(old,plan)

    def test_invalid_fm_batch_move_leaves_original_plan_intact(self):
        _,plan=settings(fixture())
        before=deepcopy(plan)
        selected=[(category,slot,next(iter(window['offsets'])))
                  for category,policy in plan['categories'].items() for slot,window in policy['slots'].items()]
        with self.assertRaises(ValueError):move_fm_selection(plan,selected,60)
        self.assertEqual(before,plan)


class GroupNotesSelectionWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        test_font(cls.app)

    def setUp(self):
        self.config=grouped_config()
        self.config['task_generation']['categories']['stores']['department_groups'][0]['payload'].update(
            scheduled_times=['08:00','09:00','10:00'],notes='Deliveries for the morning clinic. Keep the service corridor clear.')
        self.saved=[]
        self.dialog=TaskGenerationSettingsDialog(None,self.config['task_generation'],
            [row['name'] for row in self.config['locations']],['Box'],[],self.config['departments'],self.saved.append)
        self.dialog.show()
        self.panel=self.dialog.day_schedule
        self.dialog.schedule_tabs.setCurrentWidget(self.panel)
        self.app.processEvents()
        self.canvas=self.panel.canvas
        self.ids=[('native','group','stores','GROUP-1',time) for time in ('08:00','09:00','10:00')]

    def tearDown(self):
        self.dialog.close();self.dialog.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)

    def point(self,identity):
        self.app.processEvents()
        return next(rect.center().toPoint() for rect,item,edge in self.canvas.hits if item['id']==identity and edge=='move')

    def test_group_notes_render_under_name_and_expand_only_annotated_row(self):
        index=next(index for index,row in enumerate(self.canvas.rows) if row.get('notes','').startswith('Deliveries'))
        self.assertEqual('GROUP-1',self.canvas.rows[index]['label'])
        self.assertGreater(self.canvas.row_geometry(index)[1],self.canvas.ROW)
        hit=next(rect for rect,item,edge in self.canvas.hits if item['id']==self.ids[0] and edge=='move')
        top,height=self.canvas.row_geometry(index)
        self.assertGreater(hit.center().y(),top)
        self.assertLess(hit.center().y(),top+height)
        self.assertEqual(self.config['task_generation']['categories']['stores']['department_groups'],
                         self.dialog.config['categories']['stores']['department_groups'])

    def test_ctrl_click_selects_and_toggles_multiple_bars(self):
        QTest.mouseClick(self.canvas,Qt.LeftButton,pos=self.point(self.ids[0]))
        QTest.mouseClick(self.canvas,Qt.LeftButton,Qt.ControlModifier,pos=self.point(self.ids[1]))
        self.assertEqual(set(self.ids[:2]),self.canvas.selections)
        self.assertEqual('2 selected',self.panel.selection_count.text())
        QTest.mouseClick(self.canvas,Qt.LeftButton,Qt.ControlModifier,pos=self.point(self.ids[1]))
        self.assertEqual({self.ids[0]},self.canvas.selections)

    def test_shift_range_then_keyboard_moves_all_selected_and_preserves_selection(self):
        QTest.mouseClick(self.canvas,Qt.LeftButton,pos=self.point(self.ids[0]))
        QTest.mouseClick(self.canvas,Qt.LeftButton,Qt.ShiftModifier,pos=self.point(self.ids[2]))
        self.assertEqual(set(self.ids),self.canvas.selections)
        QTest.keyClick(self.canvas,Qt.Key_Right)
        payload=self.dialog.config['categories']['stores']['department_groups'][0]['payload']
        self.assertEqual(['08:05','09:05','10:05'],payload['scheduled_times'])
        self.assertEqual(3,len(self.canvas.selections))
        self.assertTrue(all(identity[-1].endswith(':05') for identity in self.canvas.selections))

    def test_real_multi_drag_commits_together_and_escape_cancels_it(self):
        QTest.mouseClick(self.canvas,Qt.LeftButton,pos=self.point(self.ids[0]))
        QTest.mouseClick(self.canvas,Qt.LeftButton,Qt.ControlModifier,pos=self.point(self.ids[1]))
        point=self.point(self.ids[0])
        before=deepcopy(self.dialog.config)
        QTest.mousePress(self.canvas,Qt.LeftButton,pos=point)
        QTest.mouseMove(self.canvas,point+QPoint(24,0))
        self.assertEqual(before,self.dialog.config)
        QTest.keyClick(self.canvas,Qt.Key_Escape)
        QTest.mouseRelease(self.canvas,Qt.LeftButton,pos=point+QPoint(24,0))
        self.assertEqual(before,self.dialog.config)
        QTest.mousePress(self.canvas,Qt.LeftButton,pos=point)
        QTest.mouseMove(self.canvas,point+QPoint(24,0))
        QTest.mouseRelease(self.canvas,Qt.LeftButton,pos=point+QPoint(24,0))
        times=self.dialog.config['categories']['stores']['department_groups'][0]['payload']['scheduled_times']
        self.assertNotEqual(['08:00','09:00','10:00'],times)
        from amr_demand_schedule import minutes
        moved_times=sorted(identity[-1] for identity in self.canvas.selections)
        self.assertEqual(60,(minutes(moved_times[1])-minutes(moved_times[0]))%1440)
        self.assertIn('10:00',times)

    def test_ctrl_a_selects_all_editable_items_and_cancel_discards_changes(self):
        original=deepcopy(self.config)
        self.canvas.setFocus()
        QTest.keyClick(self.canvas,Qt.Key_A,Qt.ControlModifier)
        expected={key for key,item in self.panel.items.items() if item.get('editable')}
        self.assertEqual(expected,self.canvas.selections)
        QTest.keyClick(self.canvas,Qt.Key_Right)
        self.dialog.reject()
        self.assertFalse(self.saved)
        self.assertEqual(original,self.config)


if __name__=='__main__':unittest.main()
