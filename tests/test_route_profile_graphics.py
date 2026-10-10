"""Graphical permissions preserve direction, floor selections and draft isolation."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import sys,json
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'visualiser'))
from PySide6.QtCore import Qt,QRectF,QPointF
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox,QMenu
from advanced_dialogs import RouteProfilesEditorV2
from amr_tutorial_values import route_nodes,route_edges
from tutorial_controls import dialog_target,workspace_target
from tests import test_tutorial_placement as placement


class GraphicalRouteProfiles(unittest.TestCase):
    setUpClass=classmethod(placement.PlacementInteraction.setUpClass.__func__)
    def setUp(self):
        placement.PlacementInteraction.setUp(self);self.bubble.timer.stop();self.saved=[]
        self.course.chapters.setCurrentIndex(5);self.course.session.state['action']=0;self.bubble.refresh()
        self.dialog=RouteProfilesEditorV2(self.editor,{'clean':{'allowed_nodes':[],'allowed_edges':[]}},
            self.editor.store.all_points(),['L1','L2'],self.config['corridors']['edges'],self.saved.append)
        self.dialog.setModal(True);self.dialog.show();self.app.processEvents()
    def tearDown(self):
        if self.editor.route_profile_selection_active:self.editor._cancel_route_profile_graphical_selection()
        self.dialog.reject();self.dialog.deleteLater();placement.PlacementInteraction.tearDown(self)
    def start(self):
        self.before=deepcopy(self.editor.store.data)
        QTest.mouseClick(self.dialog.graphical_nodes_btn,Qt.LeftButton);self.app.processEvents()
        self.editor.fit_view();self.app.processEvents()
        return self.editor.route_permission_selection
    def click(self,name):
        p=self.editor.store.all_points()[name]
        pixel=self.editor.canvas.mapFromScene(self.editor.world_to_scene(p['x'],p['y']))
        QTest.mouseClick(self.editor.canvas.viewport(),Qt.LeftButton,pos=pixel);self.app.processEvents()
    def test_canvas_node_and_edge_clicks_are_drafts_until_saved_and_one_way_is_respected(self):
        guide=self.start();self.assertEqual('layout',self.editor.workspace.stage)
        self.assertTrue(guide.finish.isVisible());self.assertFalse(self.dialog.isVisible())
        self.click('Clean-J18-F0');self.click('Clean-J24-F0')
        self.assertTrue({'Clean-J18-F0','Clean-J24-F0'}<=self.editor.route_profile_selected_nodes)
        guide.mode.setCurrentIndex(1)
        pixel=self.editor.canvas.mapFromScene(self.editor.world_to_scene(21,7))
        QTest.mouseClick(self.editor.canvas.viewport(),Qt.LeftButton,pos=pixel)
        self.assertEqual({('Clean-J18-F0','Clean-J24-F0'),('Clean-J24-F0','Clean-J18-F0')},self.editor.route_profile_selected_edges)
        self.editor.floor_spin.setValue(1);self.app.processEvents();guide.mode.setCurrentIndex(0)
        self.click('Clean-J18-F1');self.assertIn('Clean-J18-F0',self.editor.route_profile_selected_nodes)
        self.assertEqual(self.before,self.editor.store.data)
        QTest.mouseClick(guide.finish,Qt.LeftButton);self.app.processEvents()
        self.assertTrue(self.dialog.isVisible());self.assertEqual(2,len(json.loads(self.dialog.edges_text.toPlainText())))
        self.assertEqual(self.before,self.editor.store.data);self.assertEqual([],self.saved)
        self.dialog.save_all();self.assertEqual(1,len(self.saved))
        self.assertIn('Clean-J18-F1',self.saved[0]['clean']['allowed_nodes'])
    def test_edge_toggle_has_direction_and_removing_node_removes_its_edges(self):
        guide=self.start()
        edge=next(e for e in self.editor.store.data['corridors']['edges'] if e['from']=='Clean-J18-F0' and e['to']=='Clean-J24-F0')
        edge['bidirectional']=False;guide.toggle_edge(('Clean-J18-F0','Clean-J24-F0'))
        self.assertEqual({('Clean-J18-F0','Clean-J24-F0')},self.editor.route_profile_selected_edges)
        guide.click(18,7,0);self.assertFalse(self.editor.route_profile_selected_edges)
    def test_cancel_preserves_original_draft_and_source(self):
        self.dialog.allowed_nodes=['Clean-J18-F0'];self.dialog.edges_text.setPlainText('[]')
        guide=self.start();guide.click(24,7,0);QTest.mouseClick(guide.cancel,Qt.LeftButton)
        self.assertEqual(['Clean-J18-F0'],self.dialog.allowed_nodes)
        self.assertEqual([],json.loads(self.dialog.edges_text.toPlainText()))
        self.assertEqual(self.before,self.editor.store.data);self.assertFalse(guide.toolbar.isVisible())
    def test_right_click_adds_node_to_active_draft_without_changing_saved_profiles(self):
        guide=self.start();seen=[]
        class ChooseMenu(QMenu):
            def exec(menu,*_):
                action=next(a for a in menu.actions() if a.text()=='Add node to route profile selection')
                seen.append((action.isEnabled(),action.isChecked()))
                if action.isEnabled():action.trigger()
                return action
        from unittest.mock import Mock
        event=Mock();event.globalPosition.return_value=QPointF(100,100)
        with patch('app.QMenu',ChooseMenu):
            self.editor.on_right_click(event,18,-7)
            self.editor.on_right_click(event,18,-7)
        self.assertEqual([(True,False),(False,True)],seen)
        self.assertIn('Clean-J18-F0',self.editor.route_profile_selected_nodes)
        self.assertEqual(self.before,self.editor.store.data)
        self.assertIn('1 nodes',guide.counts.text())
        QTest.mouseClick(guide.cancel,Qt.LeftButton);self.app.processEvents()
        self.assertEqual([],self.dialog.allowed_nodes)
        self.assertEqual(self.before,self.editor.store.data)
    def test_drawing_tools_stay_disabled_through_floor_navigation_and_restore_on_cancel(self):
        guide=self.start();toolbar=self.editor.cad_toolbar
        self.editor.floor_spin.setValue(1);self.editor.workspace._sync_panels()
        for mode,action in toolbar.mode_actions.items():
            self.assertEqual(mode=='select_move',action.isEnabled(),mode)
        self.assertFalse(toolbar.more_action.isEnabled())
        QTest.mouseClick(guide.cancel,Qt.LeftButton);self.app.processEvents()
        self.dialog.reject();self.app.processEvents()
        self.assertTrue(toolbar.mode_actions['corridor_node'].isEnabled())
        self.assertTrue(toolbar.more_action.isEnabled())
    def test_guidance_highlights_required_nodes_edges_floor_mode_and_finish(self):
        self.assertIs(self.dialog.graphical_nodes_btn,dialog_target(self.bubble,self.dialog)[0])
        guide=self.start();self.bubble.follow()
        self.assertTrue(guide.overlay.nodes);self.assertTrue(guide.overlay.edges)
        self.assertIs(self.editor.canvas.viewport(),workspace_target(self.bubble)[0])
        self.editor.route_profile_selected_nodes=route_nodes(self.config,'clean',['L1'])
        self.assertIs(guide.mode,workspace_target(self.bubble)[0]);guide.mode.setCurrentIndex(1)
        self.assertIs(self.editor.canvas.viewport(),workspace_target(self.bubble)[0])
        self.editor.route_profile_selected_edges=route_edges(self.config,'clean',['L1'])
        self.assertIs(guide.finish,workspace_target(self.bubble)[0])
        self.editor.route_profile_selected_nodes.remove('Clean-F2')
        self.assertIs(guide.floor,workspace_target(self.bubble)[0])
        self.assertTrue(guide.floor.isVisible())
    def test_overlapping_nodes_and_zero_length_edges_can_be_chosen_individually(self):
        guide=self.start()
        with patch.object(guide,'choose',side_effect=lambda choices,x,y:next(key for text,key in choices if text=='Clean store')):
            guide.click(3,7,0)
        self.assertEqual({'Clean store'},self.editor.route_profile_selected_nodes)
        guide.mode.setCurrentIndex(1)
        with patch.object(guide,'choose',side_effect=lambda choices,x,y:next(key for text,key in choices if set(key)=={'Clean store','Clean-J3-F0'})):
            guide.click(3,7,0)
        self.assertEqual({('Clean store','Clean-J3-F0'),('Clean-J3-F0','Clean store')},self.editor.route_profile_selected_edges)
    def test_invalid_advanced_edges_do_not_commit_or_close_editor(self):
        self.dialog.edges_text.setPlainText('[[]]')
        with patch.object(QMessageBox,'critical') as warning:self.dialog.save_all()
        warning.assert_called_once();self.assertEqual([],self.saved);self.assertTrue(self.dialog.isVisible())
    def test_layout_menu_commands_activate_actual_node_and_edge_tools(self):
        self.dialog.reject();self.editor.workspace.activate('configuration')
        self.editor.workbench.add_node_action.trigger();self.assertEqual('layout',self.editor.workspace.stage)
        self.assertEqual('corridor_node',self.editor._current_edit_mode())
        self.editor.workbench.add_edge_action.trigger();self.assertEqual('edge',self.editor._current_edit_mode())
        self.assertIs(self.editor.menuBar(),workspace_target(self.bubble)[0])


if __name__=='__main__':unittest.main()
