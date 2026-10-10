"""Inventory CAD edits remain private, usable, guided and undoable."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import sys
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'visualiser'))
from PySide6.QtCore import Qt,QTimer,QPointF,QCoreApplication,QEvent
from PySide6.QtGui import QMouseEvent,QFont,QFontDatabase
from PySide6.QtWidgets import QApplication,QPushButton,QDialog,QMenu
from PySide6.QtTest import QTest
from app import AMRGraphEditor
from dialogs import InventorySpacesDialog,ArrayInventorySpacesDialog
from inventory_spaces_manager import space_geometry
from amr_tutorial_assets import building_config


class InventoryCadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.editor=AMRGraphEditor();self.editor._drawings_enabled=False
        config=building_config(ROOT/'docs/building-tutorial')
        next(r for r in config['locations'] if r['name']=='Dispatch')['inventory_spaces']=[]
        config['amrs']=[]
        self.editor.store.data=config;self.editor._reset_edit_history()
        self.editor.resize(1280,900);self.editor.show();self.editor.refresh_canvas();self.app.processEvents()
        self.editor.workbench.show_building_course()
        self.course=self.editor.workbench.quick_start_dialog.building_course
        self.bubble=self.course.card
        self.bubble.pause();self.course.chapters.setCurrentIndex(3)
        self.course.session.state['action']=1;self.course.show_card();self.app.processEvents()
        self.editor.workspace.select_object(('point','Dispatch'))
        self.editor.workspace.set_properties_visible(True);self.app.processEvents()
        self.dialog=None

    def tearDown(self):
        if self.dialog:
            self.dialog.reject();self.dialog.deleteLater()
        with patch.object(self.editor,'_confirm_unsaved_changes',return_value=True):self.editor.close()
        self.editor.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)

    def open_draft(self,tutorial=True):
        self.bubble.pause()
        self.dialog=InventorySpacesDialog(self.editor,'Dispatch',tutorial_charging_bays=tutorial)
        self.dialog.show();self.app.processEvents();self.app.processEvents()
        return self.dialog

    def finish_modal(self,callback):
        errors=[]
        def run():
            modal=QApplication.activeModalWidget()
            try:callback(modal)
            except BaseException as exc:
                errors.append(exc)
                if modal:modal.reject()
        QTimer.singleShot(50,run)
        return errors

    def assert_bays(self,spaces):
        self.assertEqual(4,len(spaces))
        for bay,(x,y) in zip(spaces,((-1,-.8),(1,-.8),(-1,.8),(1,.8))):
            cx,cy,length,width,angle=space_geometry(bay)
            self.assertAlmostEqual(x,cx);self.assertAlmostEqual(y,cy)
            self.assertAlmostEqual(1.4,length);self.assertAlmostEqual(1.1,width)
            self.assertEqual(2,bay['height_m']);self.assertTrue(bay['has_charger'])

    def test_properties_route_guides_preset_then_save_and_supports_project_undo(self):
        panel=self.editor.properties_panel
        self.assertTrue(panel.spaces_button.isVisible());self.assertTrue(panel.spaces_button.isEnabled())
        self.assertIs(panel.spaces_button,self.bubble.resolve()[0])
        before=deepcopy(self.editor.store.data)
        def configure(dialog):
            self.assertIsInstance(dialog,InventorySpacesDialog)
            self.assertTrue(dialog.isMaximized());self.assertTrue(dialog.tutorial_charging_bays)
            self.assertIn('1.4 m × width 1.1 m',dialog.placement_guidance.text())
            self.assertIn('(2, 9.2)',dialog.placement_guidance.text())
            self.assertEqual(4,sum(i.data(0)=='tutorial-bay-preview' for i in dialog.scene.items()))
            self.assertIs(dialog.tutorial_bays_button,self.bubble.resolve()[0])
            QTest.mouseClick(dialog.tutorial_bays_button,Qt.LeftButton)
            self.assert_bays(dialog.spaces)
            self.assertEqual(before,self.editor.store.data)
            self.assertEqual({0,1,2,3},dialog.selected_space_indices)
            save=next(w for w in dialog.findChildren(QPushButton) if w.text()=='Save and close')
            self.assertIs(save,self.bubble.resolve()[0])
            QTest.mouseClick(save,Qt.LeftButton)
        errors=self.finish_modal(configure)
        QTest.mouseClick(panel.spaces_button,Qt.LeftButton)
        if errors:raise errors[0]
        self.assert_bays(self.editor.store.get_location_inventory_spaces('Dispatch'))
        self.assertEqual(2,len(self.editor.edit_history.entries))
        self.assertTrue(self.editor.undo_edit());self.assertEqual(before,self.editor.store.data)
        self.assertTrue(self.editor.redo_edit())
        self.bubble._auto_after=0;self.bubble.follow()
        self.assertTrue(self.bubble.next.isEnabled(),self.bubble.feedback.text())

    def test_right_click_route_uses_same_guided_draft_and_cancel_is_atomic(self):
        before=deepcopy(self.editor.store.data)
        self.editor._set_edit_mode('select_move')
        def cancel(dialog):
            self.assertIsInstance(dialog,InventorySpacesDialog)
            self.assertTrue(dialog.tutorial_charging_bays)
            dialog.tutorial_bays_button.click();dialog.reject()
        errors=self.finish_modal(cancel)
        def choose(menu,*args):return next(a for a in menu.actions() if a.text()=='Inventory spaces')
        event=SimpleNamespace(globalPosition=lambda:QPointF(200,200))
        class ChooseMenu(QMenu):
            def exec(menu,*args):return choose(menu,*args)
        with patch('app.QMenu',ChooseMenu):
            self.editor.on_right_click(event,3,-10)
        if errors:raise errors[0]
        self.assertEqual(before,self.editor.store.data)
        self.assertEqual(1,len(self.editor.edit_history.entries))

    def test_properties_draft_and_non_location_selection_guard_entry(self):
        panel=self.editor.properties_panel
        panel.fields['x'].setText('3.2');self.assertFalse(panel.spaces_button.isEnabled())
        self.assertIn('Apply or discard',panel.spaces_summary.text())
        panel.discard();self.assertTrue(panel.spaces_button.isEnabled())
        node=self.editor.store.data['corridors']['nodes'][0]['name']
        self.editor.workspace.select_object(('point',node));self.assertTrue(panel.spaces_button.isHidden())
        self.editor.workspace.select_object(('point','Dispatch'))
        with patch.object(self.editor,'project_editing_locked',return_value=True):
            panel.refresh();self.assertFalse(panel.spaces_button.isEnabled())

    def test_full_screen_canvas_properties_tools_and_fit_remain_accessible(self):
        dialog=self.open_draft()
        self.assertTrue(dialog.isMaximized());self.assertFalse(dialog.property('amrScrollWrapped'))
        self.assertTrue(dialog.space_properties.isHidden())
        self.assertGreater(dialog.view.viewport().width(),dialog.width()*.6)
        for title in ('Add payload','Add AMR space','Array...','Fit','Properties'):
            widget=dialog.commands.widgetForAction(dialog.command_actions[title])
            self.assertTrue(widget.isVisible(),title)
            self.assertTrue(dialog.commands.rect().contains(widget.geometry()),title)
        for title in ('Copy selected','Paste copy','Delete selected','-5°','+5°',
                      'Auto align','Auto arrange payload capacity...','Undo','Redo','Pan','Grid'):
            self.assertIn(dialog.command_actions[title],dialog.more_tools.menu().actions())
        dialog.properties_action.trigger();self.app.processEvents()
        self.assertTrue(dialog.space_properties.isVisible())
        dialog.properties_action.trigger();self.app.processEvents()
        dialog.command_actions['Pan'].trigger();self.assertTrue(dialog.view.pan_mode)
        dialog.command_actions['Select / move'].trigger();self.assertFalse(dialog.view.pan_mode)
        dialog.command_actions['Grid'].trigger();self.assertFalse(dialog.view.show_grid)
        self.assertGreater(dialog.view.transform().m11(),1)

    def test_tutorial_bays_support_group_drag_numeric_position_rotation_and_local_undo(self):
        dialog=self.open_draft();dialog.tutorial_bays_button.click()
        original=[space_geometry(bay) for bay in dialog.spaces]
        start=dialog.view.mapFromScene(QPointF(2,-9.2))
        finish=dialog.view.mapFromScene(QPointF(2.5,-9.2))
        expected_dx=dialog.view.mapToScene(finish).x()-dialog.view.mapToScene(start).x()
        for kind,pos,button,buttons in ((QEvent.MouseButtonPress,start,Qt.LeftButton,Qt.LeftButton),
                (QEvent.MouseMove,finish,Qt.NoButton,Qt.LeftButton),
                (QEvent.MouseButtonRelease,finish,Qt.LeftButton,Qt.NoButton)):
            event=QMouseEvent(kind,QPointF(pos),QPointF(dialog.view.viewport().mapToGlobal(pos)),button,buttons,Qt.NoModifier)
            QApplication.sendEvent(dialog.view.viewport(),event)
        for before,after in zip(original,[space_geometry(bay) for bay in dialog.spaces]):
            self.assertAlmostEqual(expected_dx,after[0]-before[0],delta=.003)
            self.assertAlmostEqual(before[1],after[1])
        dialog.undo_spaces();self.assert_bays(dialog.spaces)
        dialog.redo_spaces();self.assertAlmostEqual(-1+expected_dx,space_geometry(dialog.spaces[0])[0],delta=.003)
        dialog.space_list.setCurrentRow(0)
        dialog.centre_x_edit.setValue(2.25);dialog.centre_y_edit.setValue(9.35)
        dialog.run_draft_command(dialog.apply_space_centre)
        self.assertAlmostEqual(-.75,space_geometry(dialog.spaces[0])[0])
        self.assertAlmostEqual(-.65,space_geometry(dialog.spaces[0])[1])
        dialog.rotation_edit.setText('37');dialog.apply_rotation_from_field()
        cx,cy,length,width,angle=space_geometry(dialog.spaces[0])
        self.assertAlmostEqual(37,angle,delta=.06)
        self.assertAlmostEqual(1.4,length,delta=.002);self.assertAlmostEqual(1.1,width,delta=.002)
        self.assertEqual('1.400',dialog.length_edit.text())
        dialog.undo_spaces();self.assertAlmostEqual(0,space_geometry(dialog.spaces[0])[4])
        dialog.redo_spaces();dialog.finish()
        saved=self.editor.store.get_location_inventory_spaces('Dispatch')[0]
        self.assertAlmostEqual(37,space_geometry(saved)[4],delta=.06)
        self.assertAlmostEqual(1.4,saved['length_m'],delta=.002)

    def test_local_undo_redo_and_cancel_do_not_change_project(self):
        dialog=self.open_draft();before=deepcopy(self.editor.store.data)
        dialog.tutorial_bays_button.click();self.assertTrue(dialog.undo_space_action.isEnabled())
        dialog.undo_space_action.trigger();self.assertEqual([],dialog.spaces)
        self.assertEqual(4,sum(i.data(0)=='tutorial-bay-preview' for i in dialog.scene.items()))
        dialog.redo_space_action.trigger();self.assert_bays(dialog.spaces)
        self.assertFalse(dialog.tutorial_bays_button.isEnabled())
        dialog.tutorial_bays_button.click();self.assertEqual(4,len(dialog.spaces))
        dialog.reject();self.assertEqual(before,self.editor.store.data)

    def test_free_rotation_handle_and_undo_for_generic_bay(self):
        dialog=self.open_draft();dialog.tutorial_bays_button.click()
        handle=dialog.generic_rotation_handle()
        start=dialog.view.mapFromScene(QPointF(handle['x'],-handle['y']))
        finish=dialog.view.mapFromScene(QPointF(2,-10.25))
        for kind,pos,button,buttons in ((QEvent.MouseButtonPress,start,Qt.LeftButton,Qt.LeftButton),
                (QEvent.MouseMove,finish,Qt.NoButton,Qt.LeftButton),
                (QEvent.MouseButtonRelease,finish,Qt.LeftButton,Qt.NoButton)):
            event=QMouseEvent(kind,QPointF(pos),QPointF(dialog.view.viewport().mapToGlobal(pos)),button,buttons,Qt.ShiftModifier)
            QApplication.sendEvent(dialog.view.viewport(),event)
        self.assertAlmostEqual(90,space_geometry(dialog.spaces[0])[4],delta=.06)
        self.assertAlmostEqual(1.4,space_geometry(dialog.spaces[0])[2],delta=.002)
        dialog.undo_spaces();self.assert_bays(dialog.spaces)

    def test_large_text_maximized_dialog_keeps_canvas_and_save_controls_on_screen(self):
        appearance=self.editor.appearance
        original=appearance.value
        original_font=self.app.font()
        font_id=QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
        self.app.setFont(QFont('Segoe UI',10))
        with patch.object(appearance,'settings',None):
            try:
                appearance.apply(replace(original,font_size=18))
                dialog=self.open_draft()
                screen=dialog.screen().availableGeometry()
                self.assertLessEqual(dialog.height(),screen.height())
                self.assertLessEqual(dialog.width(),screen.width())
                save=next(w for w in dialog.findChildren(QPushButton) if w.text()=='Save and close')
                self.assertTrue(save.isVisible())
                self.assertTrue(dialog.rect().contains(save.mapTo(dialog,save.rect().bottomRight())))
                self.assertGreater(dialog.view.viewport().height(),200)
                self.assertTrue(dialog.more_tools.isVisible())
            finally:
                appearance.apply(original)
                self.app.setFont(original_font)
                if font_id>=0:QFontDatabase.removeApplicationFont(font_id)

    def test_payload_array_and_flexible_resize_keep_heading_centre_and_local_undo(self):
        dialog=self.open_draft(False)
        payload=dialog._payload_names()[0]
        dialog.payload_combo.setCurrentText(payload)
        dialog.command_actions['Add payload'].trigger()
        self.assertEqual(1,len(dialog.spaces))
        class AcceptedArray(ArrayInventorySpacesDialog):
            def exec(self):
                self.result=dict(kind='payload',name=payload,count=3,alignment='grid',columns=2,
                                 spacing_x=.3,spacing_y=.4,rotation_deg=30)
                return QDialog.Accepted
        with patch('dialogs.ArrayInventorySpacesDialog',AcceptedArray):dialog.command_actions['Array...'].trigger()
        self.assertEqual(4,len(dialog.spaces))
        for space in dialog.spaces[1:]:self.assertAlmostEqual(30,space_geometry(space)[4],delta=.1)
        dialog.undo_spaces();self.assertEqual(1,len(dialog.spaces))
        dialog.redo_spaces();self.assertEqual(4,len(dialog.spaces))
        dialog.space_list.setCurrentRow(1)
        dialog.flexible_check.setChecked(True)
        centre=space_geometry(dialog.spaces[1])[:2]
        dialog.length_edit.setText('1.8');dialog.width_edit.setText('1.2')
        dialog._apply_size_from_fields()
        x,y,length,width,angle=space_geometry(dialog.spaces[1])
        self.assertAlmostEqual(centre[0],x,delta=.002);self.assertAlmostEqual(centre[1],y,delta=.002)
        self.assertAlmostEqual(1.8,length,delta=.002);self.assertAlmostEqual(1.2,width,delta=.002)
        self.assertAlmostEqual(30,angle,delta=.1)
        dialog.undo_spaces();self.assertNotAlmostEqual(1.8,space_geometry(dialog.spaces[1])[2],delta=.002)

    def test_generic_robot_dimensions_add_copy_height_chargers_and_rotation(self):
        self.editor.store.data['amrs']=[dict(id='Robot',length_m=1,width_m=.7)]
        dialog=self.open_draft(False)
        self.assertTrue(dialog.tutorial_bays_button.isHidden())
        dialog.properties_action.trigger();dialog.amr_space_combo.setCurrentText('Robot')
        self.assertIn('Robot: 1 × 0.7 m',dialog.placement_guidance.text())
        dialog.command_actions['Add AMR space'].trigger()
        self.assertEqual(1,len(dialog.spaces));self.assertAlmostEqual(1,space_geometry(dialog.spaces[0])[2])
        dialog.command_actions['Copy selected'].trigger();dialog.command_actions['Paste copy'].trigger()
        self.assertEqual(2,len(dialog.spaces))
        dialog.space_list.setCurrentRow(0)
        dialog._set_space_selection({0,1},current_index=0)
        dialog.height_edit.setText('2.4');dialog.apply_height_to_selected_spaces()
        dialog.bulk_charger_on_btn.click()
        dialog.rotation_edit.setText('45');dialog.apply_rotation_from_field()
        dialog.finish()
        spaces=self.editor.store.get_location_inventory_spaces('Dispatch')
        self.assertEqual([2.4,2.4],[s['height_m'] for s in spaces])
        self.assertTrue(all(s['has_charger'] for s in spaces))
        self.assertAlmostEqual(45,space_geometry(spaces[0])[4],delta=.1)


if __name__=='__main__':unittest.main()
