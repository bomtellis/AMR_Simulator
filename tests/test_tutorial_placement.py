"""Real facility placement, automatic gates and independent modal guidance."""
from copy import deepcopy
from pathlib import Path
import os
import sys
import unittest
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'visualiser'))
from PySide6.QtCore import QCoreApplication,QEvent,QPointF,QRectF,Qt,QTimer,QRect
from PySide6.QtWidgets import QApplication,QInputDialog,QDialog,QLineEdit,QLabel
from PySide6.QtTest import QTest
from shiboken6 import delete,isValid
from amr_tutorial_assets import building_config
from amr_tutorial_placement import FACILITIES,facility_issues,placement_issues
from amr_tutorial import TutorialSession


class PlacementChecks(unittest.TestCase):
    def test_facilities_require_correct_floor_position_and_corridor_connection(self):
        config=building_config(ROOT/'docs/building-tutorial');session=TutorialSession();session.seed_bindings(config)
        self.assertEqual([],facility_issues(config,session.roles(config)))
        wash=next(r for r in config['locations'] if r['name']=='Wash');wash['x']=6
        self.assertEqual('x',facility_issues(config,session.roles(config))[0]['property'])
        wash['x']=5;config['corridors']['edges']=[r for r in config['corridors']['edges'] if 'Wash' not in (r['from'],r['to'])]
        self.assertTrue(facility_issues(config,session.roles(config))[0]['connection'])
    def test_facility_renaming_preserves_role_but_deleting_requires_repair(self):
        config=building_config(ROOT/'docs/building-tutorial');session=TutorialSession();session.seed_bindings(config)
        row=next(r for r in config['locations'] if r['name']=='Dispatch');row['name']='New dispatch'
        for edge in config['corridors']['edges']:
            for key in ('from','to'):
                if edge[key]=='Dispatch':edge[key]=row['name']
        self.assertEqual([],facility_issues(config,session.roles(config)))
        config['locations'].remove(row);self.assertEqual('dispatch',facility_issues(config,session.roles(config))[0]['role'])
    def test_lift_guidance_identifies_missing_stop_floor_and_position(self):
        config=building_config(ROOT/'docs/building-tutorial');session=TutorialSession();session.seed_bindings(config)
        del config['lifts'][0]['floor_locations']['1']
        issue=placement_issues(4,3,config,session.roles(config))[0]
        self.assertEqual((1,(34,10),'L1'),(issue['floor'],issue['point'],issue['name']))


class PlacementInteraction(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        from app import AMRGraphEditor
        self.editor=AMRGraphEditor();self.editor._drawings_enabled=False
        self.config=building_config(ROOT/'docs/building-tutorial')
        self.editor.store.data=deepcopy(self.config);self.editor._reset_edit_history();self.editor.resize(1600,900);self.editor.show()
        self.app.processEvents();self.editor.workbench.show_building_course()
        self.course=self.editor.workbench.quick_start_dialog.building_course;self.bubble=self.course.card
    def tearDown(self):
        with patch.object(self.editor,'_confirm_unsaved_changes',return_value=True):self.editor.close()
        self.editor.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
    def poll(self):
        self.bubble._auto_after=0;self.bubble.follow();self.app.processEvents()
    def facilities(self):
        names={r[1] for r in FACILITIES}
        self.editor.store.data['locations']=[r for r in self.editor.store.data['locations'] if r['name'] not in names]
        self.editor.store.data['corridors']['edges']=[r for r in self.editor.store.data['corridors']['edges'] if r['from'] not in names and r['to'] not in names]
        self.editor._reset_edit_history();self.editor.refresh_canvas()
        self.course.chapters.setCurrentIndex(3);self.course.session.state['action']=0;self.bubble.refresh();self.bubble.locate()
        self.editor._set_edit_mode('location');self.poll()
    def place(self,name,point):
        self.editor.canvas.fitInView(QRectF(-2,-22,44,24),Qt.KeepAspectRatio);self.app.processEvents()
        pixel=self.editor.canvas.mapFromScene(QPointF(point[0],-point[1]))
        with patch.object(QInputDialog,'getText',return_value=(name,True)):
            QTest.mouseClick(self.editor.canvas.viewport(),Qt.LeftButton,pos=pixel)
        self.poll()
    def test_facilities_next_marker_and_gate_update_without_clicking_check(self):
        self.facilities()
        for _,name,point in FACILITIES:
            self.assertEqual(point,self.bubble.route_overlay.next_point)
            self.assertIn(name,self.bubble.where.text());self.assertFalse(self.bubble.next.isEnabled())
            self.place(name,point)
        QTest.qWait(850)  # Also exercise the real follower timer, not just forced polls.
        self.assertTrue(self.bubble.next.isEnabled(),self.bubble.feedback.text())
        self.assertEqual([],facility_issues(self.editor.store.data,self.course.session.roles(self.editor.store.data)))
        after=deepcopy(self.editor.store.data);self.assertTrue(self.editor.undo_edit());self.poll()
        self.assertFalse(self.bubble.next.isEnabled());self.assertIn('Wash',self.bubble.where.text())
        self.assertTrue(self.editor.redo_edit());self.poll();self.assertEqual(after,self.editor.store.data)
        self.assertTrue(self.bubble.next.isEnabled());QTest.mouseClick(self.bubble.next,Qt.LeftButton)
        self.assertEqual((3,1),self.bubble.current()[:2])
    def test_incorrect_position_and_removed_access_link_block_progress_and_show_repair(self):
        self.facilities();self.place('Dispatch',(6,10))
        self.assertFalse(self.bubble.next.isEnabled());self.assertIn('Move Dispatch',self.bubble.feedback.text())
        self.assertEqual((3,10),self.bubble.route_overlay.next_point)
        self.editor.undo_edit();self.poll()
        for _,name,point in FACILITIES:self.place(name,point)
        edges=self.editor.store.data['corridors']['edges'];edges[:]=[r for r in edges if 'Wash' not in (r['from'],r['to'])]
        self.poll();self.assertFalse(self.bubble.next.isEnabled());self.assertIn('no circulation connection',self.bubble.feedback.text())
    def test_location_name_remains_visible_during_real_modal_accept_and_cancel(self):
        self.facilities();original=QInputDialog.getText
        for accept in (False,True):
            before=deepcopy(self.editor.store.data);observations=[];errors=[]
            self.editor.cad_drawing_input.coordinate_edit.setText('3,10')
            def inspect_modal():
                modal=QApplication.activeModalWidget();self.assertIsInstance(modal,QInputDialog)
                self.bubble.follow();observations.append(self.bubble.isVisible())
                self.assertIs(self.editor,self.bubble.parentWidget());self.assertIs(modal.windowHandle(),self.bubble.windowHandle().transientParent())
                self.assertIn('Dispatch',self.bubble.where.text());self.assertIn('X 3, Y 10',self.bubble.where.text())
                self.assertIs(modal.findChild(QLineEdit),self.bubble.target)
                self.assertIsNone(modal.findChild(QLabel,'dialogIntro'))
                self.assertFalse(QRect(self.bubble.pos(),self.bubble.size()).intersects(self.bubble.visible_rect(self.bubble.target)))
                self.assertFalse(QRect(self.bubble.pos(),self.bubble.size()).intersects(self.bubble.visible_rect(modal)))
                self.assertFalse(self.bubble.next.isEnabled());self.assertFalse(self.bubble.chapter.isEnabled())
                self.assertFalse(self.bubble.more_button.isEnabled())
                QTest.mouseClick(self.bubble.check,Qt.LeftButton);self.assertTrue(self.bubble.explanation.isVisible())
                QTest.mouseClick(self.bubble.check,Qt.LeftButton);self.assertFalse(self.bubble.explanation.isVisible())
                from PySide6.QtWidgets import QDialogButtonBox
                save=modal.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok)
                self.assertGreaterEqual(save.width(),save.fontMetrics().horizontalAdvance(save.text().replace('&',''))+24)
                modal.setTextValue('Dispatch');modal.accept() if accept else modal.reject()
            def finish():
                try:inspect_modal()
                except BaseException as exc:
                    errors.append(exc)
                    if QApplication.activeModalWidget():QApplication.activeModalWidget().reject()
            def prompt(*args):
                QTimer.singleShot(100,finish)
                QTimer.singleShot(3000,lambda:QApplication.activeModalWidget() and QApplication.activeModalWidget().reject())
                return original(*args)
            with patch.object(QInputDialog,'getText',side_effect=prompt):self.editor.submit_corridor_coordinate()
            self.poll()
            if errors:raise errors[0]
            self.assertEqual([True],observations);self.assertTrue(self.bubble.isVisible())
            if not accept:self.assertEqual(before,self.editor.store.data)
        self.assertIn('Clean store',self.bubble.where.text())
    def test_every_chapter_validates_automatically_including_non_model_context(self):
        context=dict(project_created=True,saved=True,unsaved=False,floor=0,history_changes=1,properties_open=False,
            checks_current=True,checks_ready=True,investigation_ready=True,geometry_ready=True,report_ready=True,run=None,
            study=dict(confirmed=True,status='complete',baseline_complete=True,proposals={str(n):{} for n in range(5)}),study_stale=False)
        with patch.object(self.course,'context',return_value=context):
            for chapter in range(12):
                self.course.chapters.setCurrentIndex(chapter);self.course.session.state['action']=0
                self.course.session.state['seen']+=['floor:0','floor:1','floor:2','fit','fit:0','fit:1','fit:2']
                self.poll();self.assertTrue(self.bubble.next.isEnabled(),(chapter,self.bubble.feedback.text()))
            self.course.chapters.setCurrentIndex(7);self.course.session.state['action']=1
            context['checks_current']=False;self.poll();self.assertFalse(self.bubble.next.isEnabled())
            context['checks_current']=True;self.poll();self.assertTrue(self.bubble.next.isEnabled())
    def test_nested_dialog_deletion_and_escape_cannot_close_independent_bubble(self):
        outer=QDialog(self.editor);outer.setModal(True);outer.show();self.app.processEvents();self.bubble.follow()
        inner=QDialog(outer);inner.setModal(True);inner.show();self.app.processEvents();self.bubble.follow()
        self.assertIs(self.editor,self.bubble.parentWidget())
        QTest.keyClick(self.bubble,Qt.Key_Escape);self.bubble.close();self.assertTrue(self.bubble.isVisible())
        delete(inner);self.poll();self.assertTrue(isValid(self.bubble));self.assertTrue(self.bubble.isVisible())
        delete(outer);self.poll();self.assertTrue(self.bubble.isVisible());self.assertIs(self.editor,self.bubble._owner)

    def test_washing_guidance_follows_visible_fields_and_requires_apply(self):
        dirty=self.editor.store.get_location('Dirty receiving')
        for key in ('wash_cycle_required','wash_location','wash_cycle_duration_sec'):dirty.pop(key,None)
        self.editor._reset_edit_history();self.editor.refresh_canvas()
        self.course.chapters.setCurrentIndex(3);self.course.session.state['action']=2;self.bubble.refresh()
        self.editor.workspace.select_object(('point','Dirty receiving'));self.poll()
        panel=self.editor.properties_panel
        self.assertIs(self.editor.workspace.properties_tab,self.bubble.target)
        QTest.mouseClick(self.editor.workspace.properties_tab,Qt.LeftButton);self.poll()
        for key,value in (('wash_cycle_required',True),('wash_location','Wash'),('wash_cycle_duration_sec','60')):
            widget=panel.fields[key]
            self.assertIs(widget,self.bubble.target)
            self.assertTrue(widget.isVisible());self.assertFalse(self.bubble.next.isEnabled())
            if isinstance(widget,QLineEdit):widget.setText(value)
            else:widget.setCurrentIndex(widget.findData(value))
            self.poll()
        self.assertIs(panel.apply_button,self.bubble.target)
        self.assertNotIn('wash_cycle_required',dirty);self.assertFalse(self.bubble.next.isEnabled())
        QTest.mouseClick(panel.apply_button,Qt.LeftButton);self.poll()
        saved=self.editor.store.get_location('Dirty receiving')
        self.assertEqual((True,'Wash',60),(saved['wash_cycle_required'],saved['wash_location'],saved['wash_cycle_duration_sec']))
        self.assertTrue(self.bubble.next.isEnabled(),self.bubble.feedback.text())
        self.assertTrue(self.editor.undo_edit());self.poll();self.assertFalse(self.bubble.next.isEnabled())
        self.assertTrue(self.editor.redo_edit());self.poll();self.assertTrue(self.bubble.next.isEnabled())

    def test_wash_service_capacity_is_editable_and_legacy_unused_field_cannot_pass(self):
        from simulator import Simulation
        wash=self.editor.store.get_location('Wash');wash.pop('max_concurrency',None);wash['service_capacity']=1
        self.editor._reset_edit_history();self.editor.refresh_canvas()
        self.course.chapters.setCurrentIndex(3);self.course.session.state['action']=3;self.bubble.refresh()
        self.editor.workspace.select_object(('point','Wash'));self.editor.workspace.set_properties_visible(True);self.poll()
        panel=self.editor.properties_panel;field=panel.fields['max_concurrency']
        self.assertEqual('Service capacity (AMRs)',panel.labels['max_concurrency'])
        self.assertIs(field,self.bubble.target);self.assertFalse(self.bubble.next.isEnabled())
        for value in ('0','-1','1.5'):
            field.setText(value);self.assertFalse(panel.apply());self.poll()
            self.assertIn('positive whole number',panel.note.text());self.assertNotIn('max_concurrency',wash)
            self.assertFalse(self.bubble.next.isEnabled())
        field.setText('1');self.poll();self.assertIs(panel.apply_button,self.bubble.target)
        self.assertFalse(self.bubble.next.isEnabled())
        QTest.mouseClick(panel.apply_button,Qt.LeftButton);self.poll()
        capacity=self.editor.store.get_location('Wash')['max_concurrency']
        self.assertIs(type(capacity),int);self.assertEqual(1,capacity)
        self.assertEqual(1,Simulation(self.editor.store.data).location_max_concurrency['Wash'])
        self.assertTrue(self.bubble.next.isEnabled(),self.bubble.feedback.text())
        self.assertTrue(self.editor.undo_edit());self.poll();self.assertFalse(self.bubble.next.isEnabled())
    def test_coordinate_feedback_and_preview_for_every_primary_insertion_tool(self):
        self.editor.object_snap_check.setChecked(False);self.editor.snap_check.setChecked(False)
        before=deepcopy(self.editor.store.data)
        for mode in self.editor.coordinate_insertion_modes():
            if mode=='corridor_draw':continue
            with self.subTest(mode=mode):
                self.editor._set_edit_mode(mode);self.app.processEvents()
                field=self.editor.cad_drawing_input.coordinate_edit
                self.assertTrue(field.isVisible());field.setText('21.25,9.125')
                self.assertIn('X 21.25, Y 9.125',self.editor.cad_drawing_input.feedback_label.text())
                self.assertEqual((21.25,9.125),(self.editor._insertion_preview['x'],self.editor._insertion_preview['y']))
                self.editor.canvas.viewport().grab()  # Actual paint of the coordinate/crosshair preview.
                self.assertEqual(before,self.editor.store.data)
    def test_typed_node_door_and_location_use_normal_atomic_undo_boundaries(self):
        self.editor.object_snap_check.setChecked(False);self.editor.snap_check.setChecked(True)
        for mode in ('corridor_node','door','location'):
            with self.subTest(mode=mode):
                self.editor._set_edit_mode(mode);before=deepcopy(self.editor.store.data)
                self.editor.cad_drawing_input.coordinate_edit.setText('21.25,9.125')
                with patch.object(QInputDialog,'getText',return_value=('Typed location',True)):
                    self.assertTrue(self.editor.submit_corridor_coordinate())
                after=deepcopy(self.editor.store.data);self.assertNotEqual(before,after)
                rows=after['locations'] if mode=='location' else after['corridors']['nodes']
                self.assertEqual((21.25,9.125),(rows[-1]['x'],rows[-1]['y']))
                self.assertTrue(self.editor.undo_edit());self.assertEqual(before,self.editor.store.data)
                self.assertTrue(self.editor.redo_edit());self.assertEqual(after,self.editor.store.data)
                self.editor.undo_edit()
    def test_new_facility_access_links_support_complete_simple_teaching_run(self):
        import contextlib,io
        from simulator import Simulation
        from visualiser.project_checks import check_project
        self.facilities()
        for _,name,point in FACILITIES:self.place(name,point)
        # Continue the course by saving the authored facility settings, and
        # include the new dirty-lane junction in the user's route selection.
        config=deepcopy(self.editor.store.data)
        for row in config['locations']:
            source=next(r for r in self.config['locations'] if r['name']==row['name'])
            for key in ('inventory_spaces','wash_cycle_required','wash_location','wash_cycle_duration_sec','max_concurrency'):
                if key in source:row[key]=deepcopy(source[key])
        dirty=config['route_profiles']['dirty']['allowed_nodes']
        dirty.extend(r['name'] for r in config['corridors']['nodes'] if r['floor']==0 and r['y']==13 and r['name'] not in dirty)
        self.assertFalse([r for r in check_project(config).findings if r.severity=='error'])
        simulation=Simulation(config,verbose=True)
        with contextlib.redirect_stdout(io.StringIO()):simulation.run()
        self.assertEqual(36,len(simulation.completed_task_records));self.assertFalse(simulation.failed_tasks);self.assertFalse(simulation.pending_tasks)
        self.assertEqual(12,simulation.wash_cycles_completed);self.assertGreaterEqual(len(simulation.charge_intervals),4)
        self.assertEqual({'L1','L2'},{r['lift_id'] for r in simulation.verbose_rows if r['event_type']=='segment_lift_transfer'})

if __name__=='__main__':unittest.main()
