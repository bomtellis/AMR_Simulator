"""Completion follows live drawing state; location repairs show the required name."""
from copy import deepcopy
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'visualiser'))
from PySide6.QtCore import QCoreApplication, QEvent, QPointF, QRectF, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from amr_tutorial_assets import building_config


class TutorialStatusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from app import AMRGraphEditor
        self.editor = AMRGraphEditor()
        self.editor._drawings_enabled = False
        self.editor.store.data = building_config(ROOT / 'docs/building-tutorial')
        self.editor._reset_edit_history()
        self.editor.resize(1280, 900)
        self.editor.show()
        self.app.processEvents()
        self.editor.workbench.show_building_course()
        self.course = self.editor.workbench.quick_start_dialog.building_course
        self.bubble = self.course.card
        self.course.chapters.setCurrentIndex(2)

    def tearDown(self):
        with patch.object(self.editor, '_confirm_unsaved_changes', return_value=True):
            self.editor.close()
        self.editor.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def poll(self):
        self.bubble._auto_after = 0
        self.bubble.follow()
        self.app.processEvents()

    def test_finishing_completed_corridor_updates_next_without_model_edit(self):
        self.course.session.state['action'] = 0
        self.editor._set_edit_mode('corridor_draw')
        self.editor.corridor_draw_start = 'Clean-J38-F0'
        self.bubble.refresh()
        self.poll()
        self.assertFalse(self.bubble.next.isEnabled())
        before = deepcopy(self.editor.store.data)
        self.editor.finish_corridor_drawing()
        self.assertEqual(before, self.editor.store.data)
        self.poll()
        self.assertTrue(self.bubble.next.isEnabled(), self.bubble.feedback.text())
        self.assertTrue(self.course.session.state['action_checks']['2:0']['passed'])
        self.editor.corridor_draw_start = 'Clean-J38-F0'
        self.poll()
        self.assertFalse(self.bubble.next.isEnabled())

    def click(self, point):
        self.editor.canvas.fitInView(QRectF(-2, -22, 44, 24), Qt.KeepAspectRatio)
        self.app.processEvents()
        pixel = self.editor.canvas.mapFromScene(QPointF(point[0], -point[1]))
        QTest.mouseClick(self.editor.canvas.viewport(), Qt.LeftButton, pos=pixel)
        self.poll()

    def test_action_18_floor_two_doors_recheck_after_apply_undo_and_redo(self):
        self.course.session.state['action'] = 17
        door = next(r for r in self.editor.store.data['corridors']['nodes'] if r['name'] == 'Clean-door-F2')
        door['door_clear_width_m'] = .9
        self.editor._reset_edit_history()
        self.editor.floor_spin.setValue(2)
        self.editor.refresh_canvas()
        self.bubble.refresh()
        self.poll()
        self.assertFalse(self.bubble.next.isEnabled())
        self.assertIn('Clear door opening', self.bubble.feedback.text())
        self.editor._set_edit_mode('select_move')
        self.click((12, 6))
        self.editor.workspace.set_properties_visible(True)
        self.app.processEvents()
        self.editor.properties_panel.fields['door_clear_width_m'].setText('1.2')
        self.editor.properties_panel.apply()
        self.editor.workspace.set_properties_visible(False)
        self.poll()
        self.assertTrue(self.bubble.next.isEnabled(), self.bubble.feedback.text())
        self.assertTrue(self.editor.undo_edit())
        self.poll()
        self.assertFalse(self.bubble.next.isEnabled())
        self.assertTrue(self.editor.redo_edit())
        self.poll()
        self.assertTrue(self.bubble.next.isEnabled())

    def test_floor_two_wrong_name_repair_displays_F2_and_blocks_completion(self):
        config = self.editor.store.data
        row = next(r for r in config['locations'] if r['name'] == 'Clean-F2')
        row['name'] = 'Wrong-F1'
        for edge in config['corridors']['edges']:
            for key in ('from', 'to'):
                if edge[key] == 'Clean-F2':
                    edge[key] = row['name']
        self.course.session.state['bindings'].pop('service_clean_2', None)
        self.course.session.state['action'] = 18
        self.editor.floor_spin.setValue(2)
        self.bubble.refresh()
        self.poll()
        self.assertIn('Clean-F2', self.bubble.where.text())
        self.assertNotIn('Wrong-F1', self.bubble.where.text())
        self.assertIn('Floor 2', self.bubble.where.text())
        self.assertFalse(self.bubble.next.isEnabled())
        self.assertIn('Clean-F2', self.bubble.feedback.text())
        self.bubble.check_action()
        self.assertEqual('name', self.bubble._correction['property'])
        self.assertEqual('Wrong-F1', self.bubble._correction['name'])
        self.editor.refresh_canvas()
        self.editor._reset_edit_history()
        self.editor._set_edit_mode('select_move')
        self.click((12, 4))
        observations = []
        def rename():
            modal = QApplication.activeModalWidget()
            self.bubble.follow()
            observations.append(self.bubble.target is modal.name_edit)
            modal.name_edit.setText('Clean-F2')
            modal.accept()
        QTimer.singleShot(30, rename)
        pixel = self.editor.canvas.mapFromScene(QPointF(12, -4))
        QTest.mouseDClick(self.editor.canvas.viewport(), Qt.LeftButton, pos=pixel)
        self.assertEqual([True], observations)
        self.poll()
        self.assertTrue(self.bubble.next.isEnabled(), self.bubble.feedback.text())

    def test_action_19_missing_floor_two_locations_prompt_each_F2_name(self):
        from PySide6.QtWidgets import QInputDialog
        self.editor.store.data['locations'] = [r for r in self.editor.store.data['locations']
                                               if r['name'] not in ('Clean-F2', 'Dirty-F2')]
        self.course.session.state['bindings'].pop('service_clean_2', None)
        self.course.session.state['bindings'].pop('service_dirty_2', None)
        self.course.session.state['action'] = 18
        self.editor.floor_spin.setValue(2)
        self.editor.refresh_canvas()
        self.editor._reset_edit_history()
        self.bubble.refresh()
        self.editor._set_edit_mode('location')
        for name, point in (('Clean-F2', (12, 4)), ('Dirty-F2', (12, 16))):
            self.poll()
            self.assertIn(name, self.bubble.where.text())
            self.assertNotIn('F1', self.bubble.where.text())
            self.assertFalse(self.bubble.next.isEnabled())
            with patch.object(QInputDialog, 'getText', return_value=(name, True)):
                self.click(point)
        self.assertTrue(self.bubble.next.isEnabled(), self.bubble.feedback.text())
        self.assertTrue(self.editor.undo_edit())
        self.poll()
        self.assertFalse(self.bubble.next.isEnabled())
        self.assertIn('Dirty-F2', self.bubble.where.text())
        self.assertTrue(self.editor.redo_edit())
        self.poll()
        self.assertTrue(self.bubble.next.isEnabled())

    def test_saved_floor_two_role_cannot_request_Dirty_F1_for_Clean_F2(self):
        from amr_tutorial import TutorialSession
        from amr_tutorial_circulation import inspect_step
        config = self.editor.store.data
        # A stale companion file can bind the floor-2 clean role to a floor-1
        # object. The checker must validate the role, not use its name blindly.
        old = TutorialSession()
        old.seed_bindings(config)
        old.state['bindings']['service_clean_2'] = deepcopy(old.state['bindings']['service_dirty_1'])
        with tempfile.TemporaryDirectory() as folder:
            old.path = Path(folder) / 'working.amrproj.tutorial.json'
            old.save()
            restored = TutorialSession(old.path)
        self.course.session.state['bindings'] = deepcopy(restored.state['bindings'])
        self.course.session.state['action'] = 18
        self.editor.floor_spin.setValue(2)
        raw_roles = {k: v['name'] for k, v in old.state['bindings'].items()}
        before = deepcopy(config)
        self.assertEqual([], inspect_step(config, 18, raw_roles))
        self.bubble.refresh()
        self.poll()
        self.assertEqual('Clean-F2', self.course.session.roles(config)['service_clean_2'])
        self.assertTrue(self.bubble.next.isEnabled(), self.bubble.feedback.text())
        self.assertNotIn('Dirty-F1', self.bubble.feedback.text())
        self.assertEqual(before, config, 'Repair progress bindings without editing project inputs.')

    def test_binding_service_role_rejects_another_floor_or_flow(self):
        from amr_tutorial import TutorialSession
        session = TutorialSession()
        for wrong in ('Dirty-F1', 'Dirty-F2', 'Clean-F1'):
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                session.bind('service_clean_2', self.editor.store.data, 'locations', wrong)


if __name__ == '__main__':
    unittest.main()
