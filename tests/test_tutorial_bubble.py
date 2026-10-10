"""Bubble placement keeps real UI usable, including after manual repositioning."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'visualiser'))
from PySide6.QtCore import QPoint,QRect,QSize,QCoreApplication,QEvent,Qt,QPointF
from PySide6.QtGui import QMouseEvent,QCloseEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from tutorial_bubble import place_bubble


class BubblePlacementTests(unittest.TestCase):
    def test_left_control_places_bubble_in_canvas_without_covering_either_pane(self):
        screen=QRect(0,0,1024,768);target=QRect(20,250,130,30)
        panes=[QRect(0,100,190,668),QRect(790,100,234,668)]
        controls=[QRect(190,0,834,100)]
        card=QRect(place_bubble(QSize(370,240),screen,screen,target,panes,controls),QSize(370,240))
        self.assertTrue(screen.contains(card))
        self.assertFalse(any(card.intersects(r) for r in [target,*panes,*controls]))

    def test_gap_between_form_controls_is_used_instead_of_covering_save(self):
        screen=QRect(0,0,1600,900);owner=QRect(200,150,1100,650)
        target=QRect(220,170,400,60)
        controls=[target,QRect(220,250,1060,60),QRect(220,710,1060,70)]
        card=QRect(place_bubble(QSize(370,240),screen,owner,target,(),controls),QSize(370,240))
        self.assertTrue(owner.contains(card));self.assertFalse(any(card.intersects(r) for r in controls))

    def test_crowded_dialog_uses_neighbouring_space_with_target_and_buttons_clear(self):
        screen=QRect(-1600,0,1600,900);owner=QRect(-1100,250,450,350)
        controls=[owner];target=QRect(-900,290,180,40)
        card=QRect(place_bubble(QSize(370,240),screen,owner,target,(),controls),QSize(370,240))
        self.assertTrue(screen.contains(card));self.assertFalse(card.intersects(owner))

    def test_safe_manual_position_survives_follow_and_collision_moves_it(self):
        screen=QRect(0,0,1600,900);target=QRect(20,100,100,30)
        position=QPoint(800,400);size=QSize(370,240)
        self.assertEqual(position,place_bubble(size,screen,screen,target,preferred=position))
        control=QRect(800,400,200,80)
        moved=place_bubble(size,screen,screen,target,controls=[control],preferred=position)
        self.assertNotEqual(position,moved);self.assertFalse(QRect(moved,size).intersects(control))

    def test_resize_clamps_manual_position_and_crowded_fallback_preserves_target(self):
        screen=QRect(0,0,800,600);size=QSize(370,240);target=QRect(0,0,300,100)
        card=QRect(place_bubble(size,screen,screen,target,controls=[screen],preferred=QPoint(1400,800)),size)
        self.assertTrue(screen.contains(card));self.assertFalse(card.intersects(target))

    def test_real_bubble_drag_stays_put_and_navigation_returns_to_auto_position(self):
        from app import AMRGraphEditor
        app=QApplication.instance() or QApplication([])
        editor=AMRGraphEditor();editor._drawings_enabled=False;editor.resize(1024,768);editor.show()
        try:
            from amr_project import Project
            editor.project=Project()
            app.processEvents();editor.workbench.show_building_course();app.processEvents()
            bubble=editor.workbench.quick_start_dialog.building_course.card
            before=editor.store.data.copy();handle=bubble.drag_handle
            start=handle.mapToGlobal(handle.rect().center());finish=start+QPoint(160,180)
            for kind,global_pos,button,buttons in (
                (QEvent.MouseButtonPress,start,Qt.LeftButton,Qt.LeftButton),
                (QEvent.MouseMove,finish,Qt.NoButton,Qt.LeftButton),
                (QEvent.MouseButtonRelease,finish,Qt.LeftButton,Qt.NoButton)):
                event=QMouseEvent(kind,QPointF(handle.mapFromGlobal(global_pos)),QPointF(global_pos),button,buttons,Qt.NoModifier)
                QApplication.sendEvent(handle,event)
            self.assertIsNotNone(bubble._manual_position)
            position=bubble.pos();bubble.follow();self.assertEqual(position,bubble.pos())
            bubble.advance(1);app.processEvents();self.assertIsNone(bubble._manual_position)
            self.assertEqual(before,editor.store.data)
            self.assertFalse(editor.workspace.properties.isVisible())
            bubble.follow();rect=QRect(bubble.pos(),bubble.size())
            self.assertFalse(rect.intersects(bubble.visible_rect(bubble.target)))
            self.assertFalse(rect.intersects(bubble.visible_rect(editor.workspace.sidebar)))
        finally:
            with patch.object(editor,'_confirm_unsaved_changes',return_value=True):editor.close()
            editor.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)


class BubbleLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        from app import AMRGraphEditor
        self.editor=AMRGraphEditor();self.editor.resize(1024,768);self.editor.show()
        self.app.processEvents();self.editor.workbench.show_building_course()
        self.course=self.editor.workbench.quick_start_dialog.building_course
        self.bubble=self.course.card

    def tearDown(self):
        with patch.object(self.editor,'_confirm_unsaved_changes',return_value=True):self.editor.close()
        self.editor.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)

    def wait_until(self,predicate):
        for _ in range(500):
            self.app.processEvents()
            if predicate():return
            QTest.qWait(10)
        self.fail('Timed out waiting for tutorial/demo loading')

    def test_hidden_running_bubble_recovers_without_stealing_focus(self):
        self.editor.activateWindow();self.editor.canvas.setFocus();self.app.processEvents();focus=self.app.focusWidget()
        self.assertIs(self.editor.canvas,focus)
        self.bubble.hide()
        self.wait_until(self.bubble.isVisible)
        QTest.qWait(30)
        self.assertIs(focus,self.app.focusWidget())
        self.assertFalse(self.editor.workspace.properties.isVisible())

    def test_pause_resume_hide_and_minimise_keep_explicit_navigation_state(self):
        self.course.session.state['action']=1;self.bubble.refresh()
        self.course.pause();QTest.qWait(300)
        self.assertFalse(self.bubble.isVisible());self.assertFalse(self.bubble.timer.isActive())
        self.course.pause();self.assertTrue(self.bubble.isVisible())
        self.assertEqual(1,self.course.session.state['action'])
        for hide,show in ((self.editor.hide,self.editor.show),
                          (self.editor.showMinimized,self.editor.showNormal)):
            hide();QTest.qWait(300);self.bubble.follow()
            self.assertFalse(self.bubble.isVisible())
            self.assertFalse(self.course.session.state['paused'])
            show();self.wait_until(self.bubble.isVisible)
        self.bubble.pause();self.editor.hide();self.editor.show();QTest.qWait(300)
        self.assertFalse(self.bubble.isVisible())

    def test_first_project_save_preserves_and_persists_unsaved_tutorial_progress(self):
        from amr_tutorial import TutorialSession
        self.assertIsNone(self.editor.project)
        self.course.chapters.setCurrentIndex(1)
        self.course.session.state['action']=3
        self.course.session.observe('undo')
        self.bubble.pause()
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'first.amrproj'
            with patch('app.QFileDialog.getSaveFileName',return_value=(str(target),'')):
                self.assertTrue(self.editor.save_project())
            saved=TutorialSession(Path(str(target)+'.tutorial.json'))
            self.assertEqual((1,3,True),(saved.state['chapter'],saved.state['action'],saved.state['paused']))
            self.assertIn('undo',saved.state['seen'])
            self.assertEqual((1,3),self.bubble.current()[:2])

    def test_chapter_navigation_and_observations_save_while_bubble_is_paused(self):
        from amr_tutorial import TutorialSession
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'course.amrproj'
            with patch('app.QFileDialog.getSaveFileName',return_value=(str(target),'')):
                self.assertTrue(self.editor.save_project())
            self.course.sync()
            self.bubble.pause()
            self.course.chapters.setCurrentIndex(1)
            self.editor.cad_toolbar.fit_action.trigger()
            saved=TutorialSession(Path(str(target)+'.tutorial.json'))
            self.assertEqual(1,saved.state['chapter'])
            self.assertIn('fit',saved.state['seen'])

    def test_reopen_and_immediately_resume_restores_saved_chapter_and_action(self):
        from amr_project import Project
        from amr_tutorial import TutorialSession
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'resume.amrproj'
            Project().save(target,self.editor.store.data)
            progress=TutorialSession(Path(str(target)+'.tutorial.json'))
            progress.state.update(chapter=2,action=3,paused=True,seen=['undo','redo'])
            progress.save()
            self.bubble.pause()
            self.assertTrue(self.editor.load_json_file(str(target),load_drawings=False,check_unsaved=False))
            self.editor.workbench.show_building_course()
            self.assertEqual((2,3),self.bubble.current()[:2])
            saved=TutorialSession(progress.path)
            self.assertEqual((2,3),(saved.state['chapter'],saved.state['action']))
            self.assertFalse(saved.state['paused'])
            self.assertIn('redo',saved.state['seen'])

    def test_resume_skips_completed_chapters_after_editor_history_is_cleared(self):
        from amr_project import Project
        from amr_tutorial import TutorialSession
        from amr_tutorial_assets import generate_assets
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);config=generate_assets(root);target=root/'resume.amrproj'
            Project().save(target,config)
            saved=TutorialSession(Path(str(target)+'.tutorial.json'))
            saved.state.update(chapter=0,action=4,paused=True)
            for name in ('fit','snaps','selection','properties','undo','redo'):saved.observe(name)
            self.assertFalse(saved.check(0,config,{'saved':True}))
            self.assertFalse(saved.check(1,config,{'history_changes':1}))
            self.bubble.pause()
            self.assertTrue(self.editor.load_json_file(str(target),load_drawings=False,check_unsaved=False))
            self.editor.workbench.show_building_course()
            self.assertEqual((2,0),self.bubble.current()[:2])
            resumed=TutorialSession(saved.path)
            self.assertTrue(resumed.state['completed']['workbench']['passed'])
            self.assertEqual((2,0),(resumed.state['chapter'],resumed.state['action']))

    def test_resume_skips_verified_actions_but_stops_at_unfinished_or_changed_work(self):
        from amr_run_evidence import config_hash
        self.bubble.pause();self.course.chapters.setCurrentIndex(4)
        self.course.session.state['action_checks']={'4:0':dict(passed=True,config_hash=config_hash(self.editor.store.data))}
        self.course.show_card()
        self.assertEqual((4,1),self.bubble.current()[:2])
        self.bubble.pause();self.course.session.state['action']=0
        self.course.session.state['action_checks']['4:0']['config_hash']='old configuration'
        self.course.show_card()
        self.assertEqual((4,0),self.bubble.current()[:2])

    def test_demo_working_copies_survive_file_and_dxf_loading_windows(self):
        from PySide6.QtWidgets import QFileDialog
        from PySide6.QtCore import QTimer
        seen=[];choosers=[];original=self.editor._update_loading_dialog
        def update():
            original()
            if self.editor._loading_dialog and self.editor._loading_dialog.isVisible():
                self.bubble.follow()
                seen.append(self.bubble.parentWidget() is self.editor and self.bubble.windowHandle().transientParent() is self.editor._loading_dialog.windowHandle())
        with tempfile.TemporaryDirectory() as directory,patch.object(self.editor,'_update_loading_dialog',side_effect=update):
            for name in ('starter','reference-dedicated'):
                with self.subTest(name=name):
                    source=ROOT/'docs/building-tutorial'/f'{name}.amrproj';original_bytes=source.read_bytes()
                    target=Path(directory)/f'{name}-working.amrproj'
                    def choose(*_):
                        # Real modal event loop, without depending on a desktop
                        # file chooser. The working-copy code remains unmocked.
                        dialog=QFileDialog(self.editor);dialog.setOption(QFileDialog.DontUseNativeDialog)
                        def finish():
                            self.bubble.follow();choosers.append(self.bubble.parentWidget() is self.editor and self.bubble.windowHandle().transientParent() is dialog.windowHandle());dialog.reject()
                        QTimer.singleShot(0,finish);dialog.exec();dialog.deleteLater()
                        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
                        return str(target),''
                    with patch('building_tutorial_panel.QFileDialog.getSaveFileName',side_effect=choose),patch.object(self.editor,'_confirm_unsaved_changes',return_value=True):
                        self.course.open_checkpoint(name)
                    self.wait_until(lambda:not self.editor._loading_batch_active)
                    # Native tool-window hiding can arrive after the owner's
                    # Hide event. The follower must recover that ordering too.
                    self.bubble.hide();self.wait_until(self.bubble.isVisible)
                    self.course.sync();self.bubble.follow()
                    self.assertEqual(target,self.editor.project.path)
                    self.assertEqual(3,len(self.editor._dxf_cache))
                    self.assertIs(self.editor,self.bubble.parentWidget())
                    self.assertTrue(self.bubble.outline.isVisible())
                    self.assertFalse(self.course.session.state['paused'])
                    self.assertEqual(original_bytes,source.read_bytes())
                    self.assertFalse(self.editor.workspace.properties.isVisible())
            self.assertTrue(seen);self.assertTrue(all(seen))
            self.assertEqual([True,True],choosers)

    def test_small_map_demo_keeps_active_bubble(self):
        from shutil import copyfile
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'docs/quick-start/small-map.json';path.parent.mkdir(parents=True)
            copyfile(ROOT/'docs/quick-start/small-map.json',path)
            self.editor.workbench.quick_start_dialog.exercise.setCurrentIndex(0)
            with patch('quick_start.application_root',return_value=root),patch.object(self.editor,'_confirm_unsaved_changes',return_value=True):
                self.editor.workbench.quick_start_dialog.show_example()
            self.course.sync();self.bubble.hide();self.wait_until(self.bubble.isVisible)
            self.assertEqual(str(path),str(self.editor.current_json_path))
            self.assertFalse(self.course.session.state['paused'])

    def test_destroying_save_dialog_immediately_cannot_destroy_or_pause_bubble(self):
        from PySide6.QtWidgets import QFileDialog
        from shiboken6 import delete,isValid
        dialog=QFileDialog(self.editor);dialog.setOption(QFileDialog.DontUseNativeDialog)
        dialog.setModal(True);dialog.show();self.app.processEvents();self.bubble.follow()
        delete(dialog)  # Static native choosers can be destroyed without deleteLater.
        self.assertTrue(isValid(self.bubble),'Save dialog destroyed the tutorial bubble')
        self.wait_until(self.bubble.isVisible)
        self.assertFalse(self.course.session.state['paused'])

    def test_transient_window_close_is_not_an_explicit_tutorial_pause(self):
        QApplication.sendEvent(self.bubble,QCloseEvent())
        self.assertFalse(self.course.session.state['paused'])
        self.wait_until(self.bubble.isVisible)

    def test_help_restart_recreates_paused_bubble_without_resetting_work(self):
        from copy import deepcopy
        from amr_project import Project
        from shiboken6 import isValid
        self.editor.project=Project();self.bubble.advance(1)
        before=deepcopy(self.editor.store.data);checks=deepcopy(self.course.session.state['action_checks'])
        old=self.bubble;old.pause()
        action=self.editor.workbench.restart_bubble_action
        self.assertIn(action,self.editor.workbench.help_menu.actions())
        self.assertTrue(action.isEnabled());action.trigger()
        self.bubble=self.course.card
        self.assertIsNot(old,self.bubble);self.assertTrue(self.bubble.isVisible())
        self.assertFalse(self.course.session.state['paused']);self.assertEqual(1,self.course.session.state['action'])
        self.assertEqual(checks,{key:self.course.session.state['action_checks'][key] for key in checks})
        self.assertEqual(before,self.editor.store.data);self.assertFalse(self.editor.workspace.properties.isVisible())
        self.assertFalse(old.timer.isActive());self.assertIsNone(self.bubble._manual_position)
        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
        self.assertFalse(isValid(old));self.assertTrue(isValid(self.bubble))

    def test_help_restart_recovers_deleted_bubble_and_disposes_orphan_hints(self):
        from shiboken6 import delete,isValid
        old=self.bubble;hints=(old.outline,old.route_overlay)
        delete(old)
        self.editor.workbench.restart_bubble_action.trigger();self.bubble=self.course.card
        self.assertTrue(isValid(self.bubble));self.assertTrue(self.bubble.isVisible())
        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
        self.assertTrue(all(hint is None or not isValid(hint) for hint in hints))
        actions=self.course.tools.menu().actions()
        self.assertIn('Restart tutorial bubble',[action.text() for action in actions])

    def test_real_save_chooser_save_as_and_cancel_keep_tutorial_running(self):
        from PySide6.QtWidgets import QFileDialog
        from PySide6.QtCore import QTimer
        from amr_project import Project
        import json
        self.editor.project=Project();self.course.sync()
        self.course.session.state['action']=1;self.bubble.refresh()
        choose=QFileDialog.getSaveFileName;seen=[];timeouts=[]
        with tempfile.TemporaryDirectory() as directory:
            for name,cancel,save_as in (('cancel-first',True,False),('first-save',False,False),
                                         ('cancel-as',True,True),('save-as',False,True)):
                with self.subTest(operation=name):
                    target=Path(directory)/f'{name}.amrproj'
                    def finish():
                        dialog=QApplication.activeModalWidget()
                        self.bubble.follow();seen.append(isinstance(dialog,QFileDialog))
                        # Reproduce the transient close reported with Windows'
                        # native Save dialog, while exercising Qt's real chooser.
                        self.bubble.close()
                        if cancel:dialog.reject()
                        else:dialog.selectFile(str(target));dialog.accept()
                    def chooser(parent,title,suggested,filters):
                        watchdog=QTimer(self.editor);watchdog.setSingleShot(True)
                        def abort():
                            timeouts.append(name)
                            dialog=QApplication.activeModalWidget()
                            if dialog:dialog.reject()
                        watchdog.timeout.connect(abort);watchdog.start(3000)
                        QTimer.singleShot(150,finish)
                        try:return choose(parent,title,str(target),filters,options=QFileDialog.DontUseNativeDialog)
                        finally:watchdog.stop();watchdog.deleteLater()
                    previous_path=self.editor.project.path
                    with patch('app.QFileDialog.getSaveFileName',side_effect=chooser):
                        self.assertEqual(not cancel,self.editor.save_project(save_as=save_as))
                    self.course.sync();self.wait_until(self.bubble.isVisible);QTest.qWait(30)
                    self.assertFalse(self.course.session.state['paused']);self.assertTrue(self.bubble.timer.isActive())
                    self.assertEqual(1,self.course.session.state['action'])
                    self.assertIs(self.editor,self.bubble.parentWidget())
                    if cancel:
                        self.assertEqual(previous_path,self.editor.project.path);self.assertFalse(target.exists())
                    else:
                        self.assertEqual(target,self.editor.project.path)
                        self.assertFalse(json.loads(Path(str(target)+'.tutorial.json').read_text())['paused'])
                        self.assertEqual(Project.open(target).project_id,self.editor.project.project_id)
            self.assertEqual([True]*4,seen)
            self.assertEqual([],timeouts)
            with patch('app.QFileDialog.getSaveFileName',side_effect=AssertionError('Saved projects do not need another chooser')):
                self.assertTrue(self.editor.save_project())
            self.course.sync();self.assertFalse(self.course.session.state['paused'])
            self.assertEqual(1,self.course.session.state['action'])


if __name__=='__main__':unittest.main()
