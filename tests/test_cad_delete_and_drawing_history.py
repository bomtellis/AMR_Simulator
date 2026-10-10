"""Selection deletion and undo without repeated drawing I/O."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent, QPixmap
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QGraphicsView, QMenu, QMessageBox
from tests import test_corridor_editing as editing


class CadDeleteAndDrawingHistoryTests(unittest.TestCase):
    setUpClass = classmethod(editing.CorridorEditingUiTests.setUpClass.__func__)
    setUp = editing.CorridorEditingUiTests.setUp
    tearDown = editing.CorridorEditingUiTests.tearDown

    def drawings(self):
        editor = self.editor
        editor.store.data['floor_dxf_files'] = [
            {'floor': floor, 'filepath': str(Path(self.temp.name) / f'{floor}.dxf')} for floor in (0, 1)]
        editor.store.data['floor_pdf_underlays'] = [{'floor': 0, 'filepath': 'floor.pdf', 'page': 1}]
        for entry in editor.store.data['floor_dxf_files']:
            editor._dxf_cache[entry['floor']] = dict(path=entry['filepath'], entities=[], bounds=(0, 0, 10, 10))
        pixmap = QPixmap(20, 20)
        pixmap.fill(Qt.white)
        editor._pdf_pixmap_cache[('floor.pdf', 1)] = (pixmap, 2)
        editor._drawings_enabled = True
        editor._reset_edit_history()
        editor.refresh_canvas()

    def test_undo_redo_graph_edits_reuse_dxf_and_pdf_without_loading(self):
        self.drawings()
        cache = dict(self.editor._dxf_cache)
        raster = self.editor._pdf_pixmap_cache[('floor.pdf', 1)]
        requests = QSignalSpy(self.editor._request_dxf_batch_load)
        self.editor._dxf_loading_floors.add(4)
        self.editor.store.data['locations'][0]['x'] = 3
        self.editor._commit_history('Move location')
        with patch('app.render_pdf_page') as render:
            self.assertTrue(self.editor.undo_edit())
            self.assertTrue(self.editor.redo_edit())
            render.assert_not_called()
        self.assertEqual(0, requests.count())
        self.assertEqual({4}, self.editor._dxf_loading_floors)
        for floor, drawing in cache.items():
            self.assertIs(drawing, self.editor._dxf_cache[floor])
        self.assertIs(raster, self.editor._pdf_pixmap_cache[('floor.pdf', 1)])

    def test_pdf_placement_undo_reuses_raster_but_page_change_renders_new_page(self):
        self.drawings()
        mapping = self.editor.get_floor_pdf_underlay(0)
        self.editor.set_floor_pdf_underlay(0, dict(mapping, x_m=8))
        with patch('app.render_pdf_page') as render:
            self.assertTrue(self.editor.undo_edit())
            self.assertTrue(self.editor.redo_edit())
            render.assert_not_called()
        self.assertEqual(8, self.editor.get_floor_pdf_underlay(0)['x_m'])
        self.editor.set_floor_pdf_underlay(0, dict(mapping, page=2))
        with patch('app.render_pdf_page', return_value=(QPixmap(20, 20), 2)) as render:
            self.assertTrue(self.editor.undo_edit())
            render.assert_not_called()
            self.assertTrue(self.editor.redo_edit())
            render.assert_called_once_with('floor.pdf', 2)

    def test_changed_dxf_mapping_still_loads_restored_drawing(self):
        self.drawings()
        self.editor._request_dxf_batch_load.disconnect(self.editor._dxf_worker.load_floors)
        requests = QSignalSpy(self.editor._request_dxf_batch_load)
        original = self.editor.get_floor_dxf_path(0)
        self.editor.store.data['floor_dxf_files'][0]['filepath'] = 'replacement.dxf'
        self.editor._commit_history('Replace drawing')
        self.assertTrue(self.editor.undo_edit())
        jobs = [job for index in range(requests.count()) for job in requests.at(index)[0]]
        self.assertIn((0, original), jobs)

    def test_mixed_selection_deletes_once_and_undo_restores_connections(self):
        before = deepcopy(self.editor.store.data)
        self.editor.selected_point_names = {'Door'}
        self.editor.selected_edge_keys = {('A', 'Door')}
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes) as confirm:
            self.assertTrue(self.editor.delete_selected())
        confirm.assert_called_once()
        self.assertNotIn('Door', self.editor.store.all_points())
        self.assertFalse(self.editor.store.data['corridors']['edges'])
        self.assertEqual(2, len(self.editor.edit_history.entries))
        self.assertTrue(self.editor.undo_edit())
        self.assertEqual(before, self.editor.store.data)
        self.assertTrue(self.editor.redo_edit())
        self.assertNotIn('Door', self.editor.store.all_points())

    def test_edge_only_delete_keeps_endpoints_and_is_undoable(self):
        before = deepcopy(self.editor.store.data)
        self.editor.selected_edge_keys = {('A', 'Door')}
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes):
            self.assertTrue(self.editor.delete_selected())
        self.assertIn('A', self.editor.store.all_points())
        self.assertIn('Door', self.editor.store.all_points())
        self.assertEqual(1, len(self.editor.store.data['corridors']['edges']))
        self.editor.undo_edit()
        self.assertEqual(before, self.editor.store.data)

    def test_cancel_delete_leaves_selection_and_history(self):
        before = deepcopy(self.editor.store.data)
        self.editor.selected_point_names = {'Door'}
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.No):
            self.assertFalse(self.editor.delete_selected())
        self.assertEqual(before, self.editor.store.data)
        self.assertEqual({'Door'}, self.editor.selected_point_names)
        self.assertEqual(1, len(self.editor.edit_history.entries))

    def test_lift_selection_warns_and_deletes_whole_lift_as_one_undo(self):
        self.editor.store.data['lifts'] = [dict(id='Lift-1', served_floors=[0, 1],
            floor_locations={'0': dict(x=2, y=2), '1': dict(x=2, y=2)})]
        self.editor._reset_edit_history()
        before = deepcopy(self.editor.store.data)
        self.editor.selected_point_names = {'Lift-1-F0'}
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes) as confirm:
            self.assertTrue(self.editor.delete_selected())
        self.assertIn('Entire lifts', confirm.call_args.args[2])
        self.assertFalse(self.editor.store.data['lifts'])
        self.editor.undo_edit()
        self.assertEqual(before, self.editor.store.data)

    def test_rejected_department_removal_does_not_partially_delete_other_selection(self):
        self.editor.store.data['departments'] = [dict(id='D1', name='ZDept', floor=0, x=20, y=20)]
        self.editor._reset_edit_history()
        before = deepcopy(self.editor.store.data)
        self.editor.selected_point_names = {'A', 'ZDept'}
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes), \
                patch.object(type(self.editor.store), 'delete_department', side_effect=ValueError('In use')), \
                patch.object(QMessageBox, 'warning'):
            self.assertFalse(self.editor.delete_selected())
        self.assertEqual(before, self.editor.store.data)
        self.assertEqual(1, len(self.editor.edit_history.entries))

    def test_delete_key_operates_on_canvas_and_not_on_text_fields(self):
        self.editor.show()
        self.app.processEvents()
        self.editor.selected_point_names = {'Door'}
        self.editor.canvas.setFocus()
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes) as confirm:
            QTest.keyClick(self.editor.canvas.viewport(), Qt.Key_Delete)
            confirm.assert_called_once()
        self.assertNotIn('Door', self.editor.store.all_points())
        self.editor.undo_edit()
        self.editor.selected_point_names = {'Door'}
        field = self.editor.workspace.search
        field.setText('abc')
        field.setCursorPosition(0)
        field.setFocus()
        with patch.object(QMessageBox, 'question') as confirm:
            QTest.keyClick(field, Qt.Key_Delete)
            confirm.assert_not_called()
        self.assertEqual('bc', field.text())
        self.assertIn('Door', self.editor.store.all_points())

    def test_right_click_exposes_shared_delete_for_single_and_multiple_selection(self):
        self.event.globalPosition.return_value = QPointF(100, 100)
        for names, position in [({'Door'}, (5, 0)), ({'A', 'Door'}, (100, 100))]:
            self.editor.selected_point_names = names
            menus = []
            class InspectMenu(QMenu):
                def exec(menu, *_):
                    menus.append([a.text() for a in menu.actions()])
            with patch('app.QMenu', InspectMenu):
                self.editor.on_right_click(self.event, *position)
            self.assertTrue(menus)
            self.assertIn('Delete selected', menus[0])

    def test_dxf_graphics_survive_redraw_and_undo_but_hide_and_floor_changes_work(self):
        self.drawings()
        self.editor._dxf_cache[0]['entities'] = [dict(type='LINE', start=(0, 0), end=(10, 10))]
        self.editor._rendered_dxf_source = None
        with patch.object(self.editor.dxf_scene, 'populate_graphics_scene',
                          wraps=self.editor.dxf_scene.populate_graphics_scene) as populate:
            self.editor.refresh_canvas()
            items = list(self.editor._rendered_dxf_items)
            self.assertTrue(items)
            self.editor.refresh_canvas()
            self.editor.store.data['locations'][0]['x'] = 2
            self.editor._commit_history('Move location')
            self.editor.undo_edit()
            self.assertEqual(items, self.editor._rendered_dxf_items)
            self.assertEqual(1, populate.call_count)
            self.editor.show_dxf_check.setChecked(False)
            self.assertFalse(self.editor._rendered_dxf_items)
            self.editor.show_dxf_check.setChecked(True)
            self.assertEqual(2, populate.call_count)
            self.editor.floor_spin.setValue(1)
            self.assertFalse(self.editor._rendered_dxf_items)
            self.editor.floor_spin.setValue(0)
            self.assertEqual(3, populate.call_count)

    def test_drag_coalesces_redraws_and_release_flushes_final_position_once(self):
        self.editor._set_edit_mode('select_move')
        self.editor.on_left_click(self.event, 0, 0)
        with patch.object(self.editor, 'refresh_canvas', wraps=self.editor.refresh_canvas) as refresh:
            for position in range(1, 31):
                self.editor.on_drag(self.event, position, -position)
            self.assertTrue(self.editor._drag_refresh_timer.isActive())
            refresh.assert_not_called()
            self.assertEqual(30, self.editor.store.all_points()['A']['x'])
            self.editor.on_left_release(self.event)
            refresh.assert_called_once_with()
        self.assertFalse(self.editor._drag_refresh_timer.isActive())
        self.assertEqual(2, len(self.editor.edit_history.entries))
        self.editor.undo_edit()
        self.assertEqual(0, self.editor.store.all_points()['A']['x'])

    def test_hover_bypasses_native_dxf_picking_except_pdf_alignment(self):
        event = QMouseEvent(QEvent.MouseMove, QPointF(20, 20), QPointF(20, 20),
                            Qt.NoButton, Qt.NoButton, Qt.NoModifier)
        with patch.object(QGraphicsView, 'mouseMoveEvent') as native:
            self.editor.canvas.mouseMoveEvent(event)
            native.assert_not_called()
            self.editor._set_edit_mode('pdf_underlay_align')
            self.editor.canvas.mouseMoveEvent(event)
            native.assert_called_once_with(event)

    def test_demand_generation_sidebar_opens_editor_and_survives_tree_refresh(self):
        workspace = self.editor.workspace
        before = deepcopy(self.editor.store.data)
        with patch.object(self.editor, 'manage_task_generation') as edit:
            workspace.tree.setCurrentItem(workspace.items['demand_generation'])
            edit.assert_called_once_with()
        self.assertEqual('configuration', workspace.stage)
        self.assertEqual(before, self.editor.store.data)
        self.editor.store.data['payloads'].append(dict(name='New payload'))
        workspace.refresh()
        item = workspace.items['demand_generation']
        self.assertIs(item.parent(), workspace.items['configuration'])
        workspace.search.setText('demand')
        self.assertFalse(item.isHidden())
        with patch.object(self.editor, 'manage_task_generation') as edit:
            workspace.tree.setCurrentItem(item)
            edit.assert_called_once_with()
