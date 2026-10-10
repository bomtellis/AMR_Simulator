"""Actual editable inputs, tab guidance and simulator-bound tutorial values."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'visualiser'))
from PySide6.QtCore import QCoreApplication,QEvent,Qt
from PySide6.QtWidgets import QApplication,QDialogButtonBox,QFormLayout,QMessageBox,QTabBar,QTabWidget
from PySide6.QtTest import QTest
from dialogs import (AMREditorDialog,DepartmentEditorDialog,LiftEditorDialog,
    TaskGenerationSettingsDialog,BulkDepartmentTaskGenerationDialog,SimulationSettingsDialog)
from amr_tutorial_assets import building_config
from amr_tutorial_steps import action_issues
from amr_tutorial_values import demand_issues,transport_issues
from tutorial_controls import dialog_target,reveal,workspace_target,first_field
from advanced_dialogs import RouteProfilesEditorV2,MultiSelectPicker
from tests import test_tutorial_placement as placement


class TutorialControls(unittest.TestCase):
    setUpClass=classmethod(placement.PlacementInteraction.setUpClass.__func__)
    def setUp(self):
        placement.PlacementInteraction.setUp(self);self.dialogs=[]
    def tearDown(self):
        for dialog in reversed(self.dialogs):dialog.reject();dialog.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
        placement.PlacementInteraction.tearDown(self)
    def keep(self,dialog):
        self.dialogs.append(dialog);dialog.setModal(True);dialog.show();self.app.processEvents();return dialog
    def step(self,chapter,index):
        self.course.chapters.setCurrentIndex(chapter);self.course.session.state['action']=index;self.bubble.refresh()
    def test_robot_hidden_battery_field_points_to_tab_then_field_and_save(self):
        self.step(4,0);seed=deepcopy(self.config['amrs'][0]);seed['battery_capacity_kwh']=1
        dialog=self.keep(AMREditorDialog(self.editor,[],seed))
        before=deepcopy(self.editor.store.data);focus=dialog.id_edit;focus.setFocus()
        widget,rect=dialog_target(self.bubble,dialog)
        self.assertIsInstance(widget,QTabBar);self.assertEqual('Battery and charging',widget.tabText(widget.tabAt(rect.center())))
        self.assertEqual(0,dialog.findChild(QTabWidget).currentIndex());self.assertIs(focus,QApplication.focusWidget())
        QTest.mouseClick(widget,Qt.LeftButton,pos=rect.center());self.app.processEvents()
        self.assertIs(dialog.battery_capacity_edit,dialog_target(self.bubble,dialog)[0])
        dialog.battery_capacity_edit.setValue(.1)
        self.assertIs(dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Save),dialog_target(self.bubble,dialog)[0])
        self.assertEqual(before,self.editor.store.data)

    def test_inline_dialog_value_moves_with_edits_without_covering_fields_or_taking_focus(self):
        self.bubble.timer.stop();self.step(4,0);seed=deepcopy(self.config['amrs'][0])
        dialog=self.keep(AMREditorDialog(self.editor,[],seed))
        # Use the actual controls so this also covers legacy seed key names.
        dialog.quantity_edit.setValue(3);dialog.amr_length_edit.setValue(2)
        forms=dialog.findChildren(QFormLayout);original_rows=sum(f.rowCount() for f in forms)
        before=deepcopy(self.editor.store.data);dialog.quantity_edit.setFocus()
        self.bubble.follow();self.app.processEvents()
        guide=self.bubble.field_guide
        self.assertIs(guide.target,dialog.quantity_edit);self.assertIn('4',guide.label.text())
        self.assertFalse(self.bubble.where.isVisible());self.assertIs(QApplication.focusWidget(),dialog.quantity_edit)
        self.assertFalse(self.bubble.visible_rect(guide.label).intersects(self.bubble.visible_rect(dialog.quantity_edit)))
        save=dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Save)
        self.assertFalse(self.bubble.visible_rect(guide.label).intersects(self.bubble.visible_rect(save)))
        dialog.quantity_edit.setValue(4);dialog.amr_length_edit.setFocus();self.bubble.follow();self.app.processEvents()
        self.assertIs(guide.target,dialog.amr_length_edit);self.assertIn('1',guide.label.text())
        self.assertEqual(original_rows+1,sum(f.rowCount() for f in forms));self.assertEqual(before,self.editor.store.data)
        dialog.amr_length_edit.setValue(1);self.bubble.follow();self.app.processEvents()
        self.assertIsNone(guide.label);self.assertEqual(original_rows,sum(f.rowCount() for f in forms))

    def test_inline_values_are_dialog_only_and_removed_on_pause_or_dialog_deletion(self):
        self.bubble.timer.stop();self.step(4,0);dialog=self.keep(AMREditorDialog(self.editor,[],self.config['amrs'][0]))
        dialog.quantity_edit.setValue(1);self.bubble.follow();self.app.processEvents()
        self.assertIsNotNone(self.bubble.field_guide.label)
        self.bubble.pause();self.assertIsNone(self.bubble.field_guide.label)
        self.bubble._running=True;self.course.session.state['paused']=False;self.bubble.follow()
        dialog.reject();self.dialogs.remove(dialog);dialog.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete);self.bubble.follow()
        self.assertIsNone(self.bubble.field_guide.label)
        from tutorial_controls import field_target
        self.assertFalse(self.bubble.field_guide.show(self.editor.cad_move_input.offset,'Move by: 0.1,0'))
        self.assertIsNone(self.bubble.field_guide.label)

    def test_long_action_has_grouped_bullets_and_scrolls_with_navigation_visible(self):
        from PySide6.QtCore import QRect
        self.bubble.instruction.setStyleSheet('font-size: 24px')
        self.app.processEvents()
        with patch.object(self.bubble,'available_geometry',return_value=QRect(0,0,1024,600)):
            self.step(4,0);self.bubble.follow();self.app.processEvents()
        from tutorial_bubble import ACTIONS
        text=ACTIONS[4][0][1]
        self.assertIn('\n\nAMR details\n• Name: Teaching AMR',text)
        self.assertIn('\n\nBattery and charging\n• Usable battery capacity: 0.1 kWh',text)
        self.assertGreater(self.bubble.instruction_scroll.verticalScrollBar().maximum(),0)
        self.assertTrue(self.bubble.rect().contains(self.bubble.next.mapTo(self.bubble,self.bubble.next.rect().bottomRight())))

    def test_simulation_dates_have_exact_adjacent_value_prompts(self):
        self.step(7,0);dialog=self.keep(SimulationSettingsDialog(self.editor,{}))
        dialog.mode_combo.setCurrentIndex(dialog.mode_combo.findData('simple'))
        target=dialog_target(self.bubble,dialog)
        while isinstance(target[0],QTabBar):
            target[0].parentWidget().setCurrentIndex(target[0].tabAt(target[1].center()));self.app.processEvents()
            target=dialog_target(self.bubble,dialog)
        self.assertIs(dialog.start_datetime_edit,target[0]);self.assertIn('5 January 2026, 06:00',target[0].property('amrTutorialHint'))
        self.bubble.follow();self.app.processEvents()
        self.assertIs(dialog.start_datetime_edit,self.bubble.field_guide.target)

    def test_saved_robot_without_own_mass_does_not_block_lift_chapter(self):
        dialog=self.keep(AMREditorDialog(self.editor,[],self.config['amrs'][0]))
        dialog.amr_weight_edit.setValue(0);dialog.accept()
        self.assertIsNone(dialog.result['weight_kg'])
        self.editor.store.data['amrs']=[dialog.result]
        issues=self.course.session.check(4,self.editor.store.data,self.course.context())
        self.assertEqual([],issues)
        self.step(4,3);self.assertTrue(self.bubble.check_action())
    def test_department_floor_and_hours_can_be_saved_from_any_active_floor(self):
        seed=deepcopy(self.config['departments'][2]);seed['floor']=0
        dialog=self.keep(DepartmentEditorDialog(self.editor,[r['name'] for r in self.config['locations']],[],seed=seed,
            task_generation_categories=[('stores','Stores','ST'),('linen','Linen','LN')]))
        self.assertFalse(dialog.floor_edit.isReadOnly());dialog.floor_edit.setValue(2)
        dialog.operating_start_edit.setText('06:00');dialog.operating_end_edit.setText('08:00')
        dialog.accept();self.assertEqual(2,dialog.result['floor'])
        self.assertEqual('06:00',dialog.result['operating_start_time']);self.assertEqual('08:00',dialog.result['operating_end_time'])
    def test_lift_stop_table_edits_saved_positions_and_rejects_nonfinite_atomically(self):
        dialog=self.keep(LiftEditorDialog(self.editor,lift=self.config['lifts'][0]))
        dialog.stop_positions_table.item(1,1).setText('31.123456789')
        dialog.accept();self.assertEqual((31.123456789,10),dialog.result['floor_locations'][1])
        other=self.keep(LiftEditorDialog(self.editor,lift=self.config['lifts'][0]))
        other.stop_positions_table.item(2,2).setText('nan')
        before=deepcopy(self.editor.store.data)
        with patch.object(QMessageBox,'warning') as warning:other.accept()
        warning.assert_called_once();self.assertIsNone(other.result);self.assertEqual(before,self.editor.store.data)
    def test_lift_guidance_points_to_exact_stop_cell_and_hidden_car_tab(self):
        self.step(4,3);dialog=self.keep(LiftEditorDialog(self.editor,lift=self.config['lifts'][0]))
        dialog.stop_positions_table.item(1,1).setText('0')
        widget,rect=dialog_target(self.bubble,dialog)
        self.assertIs(dialog.stop_positions_table.viewport(),widget)
        self.assertEqual(dialog.stop_positions_table.visualItemRect(dialog.stop_positions_table.item(1,1)),rect)
        dialog.stop_positions_table.item(1,1).setText('34');dialog.capacity_width_edit.setValue(1)
        widget,rect=dialog_target(self.bubble,dialog);self.assertIsInstance(widget,QTabBar)
        QTest.mouseClick(widget,Qt.LeftButton,pos=rect.center());self.app.processEvents()
        self.assertIs(dialog.capacity_width_edit,dialog_target(self.bubble,dialog)[0])
    def generation(self):
        config=deepcopy(self.config);saved=[]
        for key,category in config['task_generation']['categories'].items():
            category['departments']={f'D{n}':{**category,**category['department_groups'][n]['payload']} for n in range(3)}
            category.pop('department_groups')
            for row in category['departments'].values():row.pop('department_groups',None);row.pop('departments',None)
        dialog=self.keep(TaskGenerationSettingsDialog(self.editor,config['task_generation'],
            [r['name'] for r in config['locations']],['Clean tote','Dirty cart'],['clean','dirty'],config['departments'],saved.append))
        return config,saved,dialog
    def test_department_scoped_service_target_and_return_profile_reach_generated_tasks(self):
        from simulator import Simulation
        config,saved,dialog=self.generation()
        for n in range(dialog.category_list.count()):
            if dialog.category_list.item(n).data(Qt.UserRole)=='stores':dialog.category_list.setCurrentRow(n);break
        for n in range(dialog.department_list.count()):
            if dialog.department_list.item(n).data(Qt.UserRole)=='D0':dialog.department_list.setCurrentRow(n);break
        dialog.target_time_edit.setText('601');dialog.return_profile_combo.setCurrentText('dirty')
        dialog.accept();self.assertEqual(1,len(saved))
        config['task_generation']=saved[0]
        records=Simulation(config).task_generation_manager.update_until(7199)
        tasks=[r.task for r in records if r.department_id=='D0' and r.task.route_profile=='clean']
        self.assertTrue(tasks);self.assertTrue(all(t.target_time==601 and t.return_route_profile=='dirty' for t in tasks))
        self.assertTrue(demand_issues(1,config));self.assertEqual([],demand_issues(0,config))
    def test_invalid_service_target_does_not_call_save(self):
        _,saved,dialog=self.generation();before=deepcopy(self.editor.store.data)
        dialog.enabled_check.setChecked(True)
        for text in ('nan','inf','-1','invalid'):
            dialog.target_time_edit.setText(text)
            with patch.object(QMessageBox,'critical') as warning:dialog.accept()
            warning.assert_called_once();self.assertEqual([],saved);self.assertEqual(before,self.editor.store.data)

    def test_category_names_keep_stores_and_linen_visible_with_custom_flow_names(self):
        _,_,dialog=self.generation()
        labels={dialog.category_list.item(n).data(Qt.UserRole):dialog.category_list.item(n).text() for n in range(dialog.category_list.count())}
        self.assertEqual('Stores · Clean',labels['stores']);self.assertEqual('Linen · Dirty',labels['linen'])

    def test_linen_destination_picker_is_guided_after_pickup_role_and_actually_opens(self):
        from PySide6.QtCore import QTimer
        self.bubble.timer.stop();self.step(6,0);_,_,dialog=self.generation()
        for n in range(dialog.category_list.count()):
            if dialog.category_list.item(n).data(Qt.UserRole)=='linen':dialog.category_list.setCurrentRow(n);break
        for n in range(dialog.department_list.count()):
            if dialog.department_list.item(n).data(Qt.UserRole)=='D0':dialog.department_list.setCurrentRow(n);break
        dialog.role_dropoff_radio.setChecked(True);dialog.selected_dropoffs=[];dialog._refresh_dropoff_summary()
        self.assertFalse(dialog.pick_dropoffs_btn.isEnabled())
        target=dialog_target(self.bubble,dialog)
        while isinstance(target[0],QTabBar):
            QTest.mouseClick(target[0],Qt.LeftButton,pos=target[1].center());self.app.processEvents()
            target=dialog_target(self.bubble,dialog)
        self.assertIs(dialog.role_pickup_radio,target[0])
        QTest.mouseClick(dialog.role_pickup_radio,Qt.LeftButton);self.app.processEvents()
        self.assertTrue(dialog.pick_dropoffs_btn.isEnabled())
        self.assertIs(dialog.pick_dropoffs_btn,dialog_target(self.bubble,dialog)[0])
        def choose_destination():
            picker=QApplication.activeModalWidget()
            self.assertIsInstance(picker,MultiSelectPicker)
            picker.checkboxes['Dirty receiving'].setChecked(True)
            picker.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).click()
        QTimer.singleShot(0,choose_destination)
        QTest.mouseClick(dialog.pick_dropoffs_btn,Qt.LeftButton)
        self.assertEqual(['Dirty receiving'],dialog.selected_dropoffs)
    def test_saved_department_overrides_pass_schedule_gate_with_unset_category_defaults(self):
        config,_,dialog=self.generation()
        for category in config['task_generation']['categories'].values():
            for key in ('scheduled_times','schedule_times','target_time','return_enabled','return_route_profile'):category.pop(key,None)
            category['enabled']=False
        self.assertEqual([],demand_issues(1,config))
        self.assertEqual([],action_issues(self.course.session,6,1,config,{}))
    def test_bulk_group_editor_exposes_and_saves_service_target_and_return_profile(self):
        category=deepcopy(self.config['task_generation']['categories']['stores'])
        dialog=self.keep(BulkDepartmentTaskGenerationDialog(self.editor,'stores','Stores',self.config['departments'],category,
            [r['name'] for r in self.config['locations']],['Clean tote','Dirty cart'],['clean','dirty'],selected_department_ids=['D0','D1','D2']))
        dialog.target_time_edit.setText('600');dialog.return_profile_combo.setCurrentText('clean')
        dialog.accept();self.assertEqual({'D0','D1','D2'},set(dialog.result))
        for row in dialog.result.values():self.assertEqual((600,'clean'),(row['target_time'],row['return_route_profile']))
    def test_simulation_end_checkbox_is_highlighted_before_disabled_end_field(self):
        self.step(7,0);seed=deepcopy(self.config['simulation']);seed['end_datetime']=None
        dialog=self.keep(SimulationSettingsDialog(self.editor,seed,full_config=self.config))
        target=dialog_target(self.bubble,dialog);widget,rect=target
        if isinstance(widget,QTabBar):QTest.mouseClick(widget,Qt.LeftButton,pos=rect.center());self.app.processEvents()
        self.assertIs(dialog.use_end_datetime_check,dialog_target(self.bubble,dialog)[0])
        dialog.use_end_datetime_check.setChecked(True)
        self.assertIs(dialog.end_datetime_edit,dialog_target(self.bubble,dialog)[0])
    def test_planner_hidden_proposals_and_evidence_tabs_are_highlighted(self):
        self.step(10,0);self.editor.show_lift_planner();planner=self.editor.lift_planner;self.app.processEvents()
        widget,rect=workspace_target(self.bubble)
        if isinstance(widget,QTabBar):
            self.assertEqual('Interpretation',widget.tabText(widget.tabAt(rect.center())))
            QTest.mouseClick(widget,Qt.LeftButton,pos=rect.center());self.app.processEvents()
        self.assertIs(planner.infer_button,workspace_target(self.bubble)[0])
        planner.study={'confirmed':True}
        with patch.object(planner,'stale',return_value=False):
            widget,rect=workspace_target(self.bubble)
            self.assertIs(planner.tabs.tabBar(),widget)
            self.assertEqual('Proposals',widget.tabText(widget.tabAt(rect.center())))
            QTest.mouseClick(widget,Qt.LeftButton,pos=rect.center());self.app.processEvents()
            self.assertIs(planner.generate,workspace_target(self.bubble)[0])
        planner.study=None
        self.step(11,2);widget,rect=workspace_target(self.bubble)
        self.assertIs(planner.tabs.tabBar(),widget);self.assertEqual('Evidence',widget.tabText(widget.tabAt(rect.center())))
    def test_uncommitted_robot_draft_and_wrong_dimensions_cannot_complete_action(self):
        config=deepcopy(self.config);config['amrs'][0]['length_m']=2
        self.assertTrue(action_issues(self.course.session,4,0,config,{}))
        dialog=self.keep(AMREditorDialog(self.editor,[],config['amrs'][0]));dialog.amr_length_edit.setValue(1)
        self.assertTrue(action_issues(self.course.session,4,0,config,{}))
        dialog.accept();config['amrs']=[dialog.result]
        self.assertEqual([],transport_issues(0,config))

    def test_route_guidance_prefers_graphical_selection_and_manual_picker_remains_available(self):
        self.step(5,0)
        points=self.editor.store.all_points()
        dialog=self.keep(RouteProfilesEditorV2(self.editor,self.config['route_profiles'],points,['L1','L2'],self.config['corridors']['edges'],lambda _:None))
        dialog.allowed_nodes=[]
        target=dialog_target(self.bubble,dialog);self.assertIs(dialog.graphical_nodes_btn,target[0])
        picker=self.keep(MultiSelectPicker(dialog,'Pick nodes',points,[],group_resolver=lambda _:'Floor'))
        from amr_tutorial_values import route_nodes
        expected=route_nodes(self.config,'clean',['L1'])
        widget,_=dialog_target(self.bubble,picker);self.assertIn(widget.text(),expected)
        for name,check in picker.checkboxes.items():check.setChecked(name in expected)
        self.assertIs(picker.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok),dialog_target(self.bubble,picker)[0])

    def test_low_configuration_button_scrolls_into_view_without_editing(self):
        self.step(4,2);self.editor.resize(1024,768);self.editor.workspace.activate('configuration');self.app.processEvents()
        self.editor.show_lift_planner();self.app.processEvents()
        before=deepcopy(self.editor.store.data)
        widget,_=self.bubble.resolve();self.assertEqual('Departments',widget.text())
        self.app.processEvents();self.assertFalse(self.bubble.visible_rect(widget).isEmpty())
        self.assertEqual(before,self.editor.store.data)

    def test_part_two_highlights_visible_snap_move_and_edit_controls(self):
        self.step(1,2);self.assertIs(self.editor.snap_controls.master,workspace_target(self.bubble)[0])
        self.step(1,3);self.editor.workspace.select_object(('point','Clean-F0'))
        widget,rect=workspace_target(self.bubble);self.assertIs(self.editor.menuBar(),widget)
        self.assertFalse(rect.isEmpty());self.editor.show_selection_move();self.app.processEvents()
        self.assertIs(self.editor.cad_move_input.offset,workspace_target(self.bubble)[0])
        self.editor.cad_move_input.offset.setText('0.1,0')
        self.assertIs(self.editor.cad_move_input.apply_button,workspace_target(self.bubble)[0])

    def test_all_62_action_targets_remain_visible_without_changing_project_inputs(self):
        from tutorial_bubble import ACTIONS
        before=deepcopy(self.editor.store.data);checked=0
        for chapter,actions in enumerate(ACTIONS):
            for index,_ in enumerate(actions):
                self.course.chapters.blockSignals(True);self.course.chapters.setCurrentIndex(chapter);self.course.chapters.blockSignals(False)
                self.course.session.state.update(chapter=chapter,action=index)
                self.bubble.locate();self.app.processEvents()
                widget,rect=self.bubble.resolve()
                self.assertIsNotNone(widget,(chapter,index));self.assertTrue(widget.isVisible(),(chapter,index))
                self.assertFalse(self.bubble.visible_rect(widget).isEmpty(),(chapter,index,widget.objectName()))
                self.assertEqual(before,self.editor.store.data,(chapter,index));checked+=1
        self.assertEqual(62,checked)

    def test_demand_preview_launches_from_check_pane_and_guidance_follows_build(self):
        self.bubble.timer.stop();self.step(6,2)
        self.editor.show_project_checks();self.app.processEvents()
        checks=self.editor.checks_panel;before=deepcopy(self.editor.store.data)
        self.assertIs(checks.demand_preview_button,workspace_target(self.bubble)[0])
        self.assertTrue(checks.demand_preview_button.isVisible())
        QTest.mouseClick(checks.demand_preview_button,Qt.LeftButton);self.app.processEvents()
        demand=self.editor.demand_panel
        self.assertEqual('demand',self.editor.workspace.stage)
        self.assertIs(demand.build_button,workspace_target(self.bubble)[0])
        self.assertTrue(demand.isVisible())
        QTest.mouseClick(demand.build_button,Qt.LeftButton)
        from PySide6.QtCore import QElapsedTimer
        timeout=QElapsedTimer();timeout.start()
        while demand.job is not None and timeout.elapsed()<10000:
            self.app.processEvents();QTest.qWait(10)
        self.assertIsNone(demand.job)
        self.assertIsNotNone(demand.preview,demand.summary.text())
        self.assertEqual({'D0','D1','D2'},{t['department'] for t in demand.preview['tasks']})
        self.assertEqual({'clean','dirty'},{t['route_profile'] for t in demand.preview['tasks']})
        self.assertEqual(before,self.editor.store.data)
        self.editor.show_project_checks();self.app.processEvents()
        self.assertIs(checks,self.editor.checks_panel)
        QTest.mouseClick(checks.demand_preview_button,Qt.LeftButton);self.app.processEvents()
        self.assertIs(demand,self.editor.demand_panel)
        self.assertIsNotNone(demand.preview)


if __name__=='__main__':unittest.main()
