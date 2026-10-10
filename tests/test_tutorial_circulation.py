"""Independently checked tutorial topology and real click-by-click progression."""
from copy import deepcopy
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'visualiser'))
from PySide6.QtCore import QPointF,QRectF,Qt,QCoreApplication,QEvent
from PySide6.QtWidgets import QApplication,QInputDialog
from PySide6.QtTest import QTest
from amr_tutorial_assets import building_config
from amr_tutorial import TutorialSession
from amr_tutorial_circulation import CIRCULATION_STEPS,inspect_step,inspect_all
from amr_tutorial_steps import action_issues


class CirculationChecks(unittest.TestCase):
    def setUp(self):self.config=building_config(ROOT/'docs/building-tutorial')
    def test_reference_has_every_requested_lane_door_service_and_transition(self):
        self.assertEqual(21,len(CIRCULATION_STEPS));self.assertEqual([],inspect_all(self.config))
    def test_missing_middle_link_does_not_pass_on_node_count_or_alternate_route(self):
        edges=self.config['corridors']['edges'];edges[:]=[e for e in edges if {e['from'],e['to']}!={'Clean-J12-F0','Clean-J18-F0'}]
        issue=inspect_step(self.config,0)[0]
        self.assertEqual((12,7),issue['start']);self.assertEqual((18,7),issue['point']);self.assertEqual(0,issue['floor'])
    def test_wrong_width_direction_and_distance_report_exact_missing_connection(self):
        for values in ({'width_m':1.1},{'bidirectional':False},{'distance_m':1}):
            config=deepcopy(self.config);config['corridors']['edges'][0].update(values)
            issue=inspect_step(config,0)[0];self.assertIn('Properties',issue['message']);self.assertEqual((5.5,7),issue['point'])
            self.assertIn(issue['property'],values)
    def test_door_wrong_opening_and_missing_dirty_service_are_not_completion(self):
        door=next(r for r in self.config['corridors']['nodes'] if r['name']=='Dirty-door-F0');door['door_clear_width_m']=.9
        issue=inspect_step(self.config,3)[0];self.assertEqual('door_clear_width_m',issue['property']);self.assertEqual((8,14),issue['point'])
        self.config['locations']=[r for r in self.config['locations'] if r['name']!='Dirty-F0']
        self.assertEqual((8,16),inspect_step(self.config,4)[0]['point'])
    def test_renamed_service_keeps_binding_and_deleted_service_requires_repair(self):
        session=TutorialSession();session.seed_bindings(self.config)
        row=next(r for r in self.config['locations'] if r['name']=='Clean-F0');row['name']='Renamed clean room'
        self.assertEqual([],inspect_step(self.config,4,session.roles(self.config)))
        self.config['locations'].remove(row);self.assertTrue(inspect_step(self.config,4,session.roles(self.config)))
    def test_raw_cross_floor_edges_report_source_floor_and_point(self):
        self.config['corridors']['edges'].append({'from':'Clean-J3-F0','to':'Clean-J3-F1'})
        issue=inspect_all(self.config)[-1];self.assertIn('cross-floor',issue['message']);self.assertEqual(0,issue['floor'])
    def test_missing_shared_transition_explains_how_to_create_it_on_each_floor(self):
        for floor,index in ((0,2),(1,9),(2,16)):
            with self.subTest(floor=floor):
                config=deepcopy(self.config)
                config['corridors']['nodes']=[r for r in config['corridors']['nodes']
                    if not (r['floor']==floor and (r['x'],r['y'])==(3,10))]
                config['locations']=[r for r in config['locations']
                    if not (r['floor']==floor and (r['x'],r['y'])==(3,10))]
                issues=inspect_step(config,index)
                issue=next(r for r in issues if r['point']==(3,10))
                self.assertIn('create the shared transition',issue['message'])
                self.assertIn('empty space at (3,10)',issue['message'])
                self.assertIn('Corridor',issue['message'])
    def test_each_non_circulation_action_checks_authored_state_not_dialog_visits(self):
        session=TutorialSession();context={'project_created':True}
        self.assertEqual([],action_issues(session,0,0,{},context))
        self.assertTrue(action_issues(session,0,1,{},context))
        self.assertEqual([],action_issues(session,0,1,self.config,context))
        session.observe('properties');self.assertTrue(action_issues(session,4,0,{},context))
        self.assertTrue(action_issues(session,7,1,self.config,{'checks_current':False,'checks_ready':False}))
    def test_restart_clears_action_gates(self):
        session=TutorialSession();session.state.update(action=5,action_checks={'2:0':{'passed':True},'1:0':{'passed':True}})
        session.restart(2);self.assertEqual(0,session.state['action']);self.assertNotIn('2:0',session.state['action_checks'])
        self.assertIn('1:0',session.state['action_checks'])


class CirculationInteraction(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def test_beginner_draws_all_three_floors_with_real_tools_and_cannot_skip_missing_work(self):
        from app import AMRGraphEditor
        editor=AMRGraphEditor();editor._drawings_enabled=False
        config=building_config(ROOT/'docs/building-tutorial')
        for section in ('locations','lifts','amrs','payloads','departments'):config[section]=[]
        config['corridors']={'auto_connect':False,'nodes':[],'edges':[]};config['route_profiles']={}
        config['task_generation']={'enabled':False,'categories':{}}
        editor.store.data=config;editor._reset_edit_history();editor.resize(1600,900);editor.show()
        try:
            self.app.processEvents();editor.workbench.show_building_course();course=editor.workbench.quick_start_dialog.building_course
            course.chapters.setCurrentIndex(2);course.session.state['action']=0;bubble=course.card;bubble.locate();bubble.follow()
            bubble.advance(1);self.assertEqual(0,bubble.current()[1]);self.assertFalse(bubble.next.isEnabled())
            self.assertIsNotNone(bubble._correction)
            bubble.chapter.setCurrentIndex(3);self.assertEqual(2,bubble.current()[0])
            course.chapters.setCurrentIndex(3);course.chapters.activated.emit(3);self.assertEqual(2,course.chapters.currentIndex())
            before=deepcopy(editor.store.data);self.assertFalse(editor.workspace.properties.isVisible())
            bubble.locate();self.assertEqual(before,editor.store.data)
            def click(point):
                editor.canvas.fitInView(QRectF(-2,-22,44,24),Qt.KeepAspectRatio)
                self.app.processEvents()
                pixel=editor.canvas.mapFromScene(QPointF(point[0],-point[1]))
                QTest.mouseClick(editor.canvas.viewport(),Qt.LeftButton,pos=pixel)
                self.app.processEvents();bubble.follow()
            for n,step in enumerate(CIRCULATION_STEPS):
                self.assertEqual((2,n),bubble.current()[:2]);bubble.locate()
                if n in (2,9,16):
                    self.assertIn('choose Transition and click empty space at (3,10)',bubble.instruction.text())
                    self.assertFalse(any(r['floor']==step['floor'] and (r['x'],r['y'])==(3,10)
                        for r in editor.store.data['corridors']['nodes']))
                    self.assertIs(editor.cad_toolbar.widgetForAction(editor.cad_toolbar.mode_actions['corridor_node']),bubble.target)
                    editor.cad_toolbar.mode_actions['corridor_node'].trigger();click((3,10))
                    self.assertTrue(any(r['floor']==step['floor'] and (r['x'],r['y'])==(3,10)
                        for r in editor.store.data['corridors']['nodes']))
                    self.assertIs(editor.cad_toolbar.widgetForAction(editor.cad_toolbar.mode_actions['corridor_draw']),bubble.target)
                mode={'Corridor':'corridor_draw','Door':'door','Location':'location'}[step['tool']]
                editor.cad_toolbar.mode_actions[mode].trigger();bubble.follow()
                self.assertTrue(bubble.route_overlay.isVisible())
                self.assertTrue(bubble.route_overlay.testAttribute(Qt.WA_TransparentForMouseEvents))
                for index,point in enumerate(step['points']):
                    if step['kind']=='location':
                        with patch.object(QInputDialog,'getText',return_value=(step['names'][index],True)):click(point)
                    else:click(point)
                if step['kind']=='door':
                    self.assertFalse(bubble.next.isEnabled());self.assertIn('Clear door opening',bubble.feedback.text())
                    editor._set_edit_mode('select_move')
                    for point in step['points']:
                        click(point);editor.workspace.set_properties_visible(True);self.app.processEvents()
                        editor.properties_panel.fields['door_clear_width_m'].setText('1.2');editor.properties_panel.apply()
                    editor.workspace.set_properties_visible(False)
                if step['kind']=='route':
                    self.assertFalse(bubble.next.isEnabled())
                    editor.finish_corridor_drawing();bubble.follow()
                self.assertEqual([],inspect_step(editor.store.data,n,course.session.roles(editor.store.data)))
                if n in (2,9,16):
                    self.assertTrue(any(r['floor']==step['floor'] and (r['x'],r['y'])==(3,10)
                        for r in editor.store.data['corridors']['nodes']))
                bubble._auto_after=0;bubble.follow()
                self.assertTrue(bubble.next.isEnabled())
                if n==0:
                    editor.store.data['corridors']['edges'][0]['width_m']=1.1
                    self.assertFalse(bubble.check_action());self.assertEqual('width_m',bubble._correction['property'])
                    editor._set_edit_mode('select_move');click(bubble._correction['point'])
                    editor.workspace.set_properties_visible(True);self.app.processEvents();bubble.follow()
                    field=editor.properties_panel.fields['width_m'];self.assertIs(field,bubble.target)
                    field.setText('2.4');editor.properties_panel.apply();editor.workspace.set_properties_visible(False)
                    editor.store.data['corridors']['edges'].pop();bubble.follow()
                    self.assertFalse(bubble.next.isEnabled());self.assertFalse(bubble.check_action())
                    missing=bubble._correction;self.assertEqual(0,missing['floor']);self.assertIn('connect',missing['message'])
                    editor.cad_toolbar.mode_actions['corridor_draw'].trigger();click(missing['start']);click(missing['point']);editor.finish_corridor_drawing()
                bubble.advance(1)
            self.assertEqual(3,bubble.current()[0]);self.assertEqual([],inspect_all(editor.store.data))
            self.assertTrue(course.session.state['completed']['circulation']['passed'])
            self.assertFalse(editor.workspace.properties.isVisible())
        finally:
            with patch.object(editor,'_confirm_unsaved_changes',return_value=True):editor.close()
            editor.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)

    def test_first_project_save_preserves_current_action_and_observations(self):
        from app import AMRGraphEditor
        from amr_project import Project
        import tempfile,json
        editor=AMRGraphEditor();editor._drawings_enabled=False;editor.project=Project()
        try:
            editor.workbench.show_building_course();course=editor.workbench.quick_start_dialog.building_course
            course.sync();course.session.state['action']=2;course.session.observe('fit:0')
            with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as directory:
                path=Path(directory)/'working.amrproj';editor.project.save(path,editor.store.data)
                course.sync();self.assertEqual(2,course.session.state['action']);self.assertIn('fit:0',course.session.state['seen'])
                saved=json.loads(Path(str(path)+'.tutorial.json').read_text())
                self.assertEqual(2,saved['action'])
        finally:
            with patch.object(editor,'_confirm_unsaved_changes',return_value=True):editor.close()
            editor.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)


if __name__=='__main__':unittest.main()
