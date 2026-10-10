"""Optional new-project floor setup, drawing settings and lifecycle protection."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from tests import test_corridor_editing as editing
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QDialog, QFileDialog, QMessageBox
from amr_project import Project
from models import JsonStore
from project_setup import NewProjectDialog
from pdf_underlay import PdfUnderlayDialog
from visualiser.dxf_export import configured_floors


class ProjectSetupDialogTests(unittest.TestCase):
    setUpClass = classmethod(editing.CorridorEditingUiTests.setUpClass.__func__)

    def setUp(self):
        self.dialog = NewProjectDialog()

    def tearDown(self):
        self.dialog.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_floor_count_creates_empty_floors_and_retains_choices_while_resizing(self):
        self.dialog.floor_count.setValue(3)
        self.dialog.floor_height.setValue(3.5)
        with patch.object(QFileDialog, 'getOpenFileName', return_value=('upper.DXF', '')):
            self.dialog.choose_drawing(2)
        self.assertEqual(3, self.dialog.table.rowCount())
        self.dialog.floor_count.setValue(1)
        self.assertEqual([], self.dialog.configuration()['floor_dxf_files'])
        self.dialog.floor_count.setValue(3)
        config = self.dialog.configuration()
        self.assertEqual(3, config['building']['floor_count'])
        self.assertEqual(3.5, config['building']['floor_height_m'])
        self.assertEqual([0, 1, 2], configured_floors(config))
        self.assertEqual([{'floor': 2, 'filepath': 'upper.DXF'}], config['floor_dxf_files'])
        self.dialog.clear_drawing(2)
        self.assertEqual([], self.dialog.configuration()['floor_dxf_files'])

    def test_pdf_uses_existing_page_scale_and_alignment_settings(self):
        def settings(dialog):
            dialog.page.setValue(2)
            dialog.scale_denominator.setValue(50)
            dialog.x_m.setValue(2.5)
            return QDialog.Accepted

        self.dialog.floor_count.setValue(2)
        with patch.object(QFileDialog, 'getOpenFileName', return_value=('first.pdf', '')), \
                patch('project_setup.render_pdf_page', return_value=(None, 3)), \
                patch.object(PdfUnderlayDialog, 'exec', new=settings):
            self.dialog.choose_drawing(1)
        mapping = self.dialog.configuration()['floor_pdf_underlays'][0]
        self.assertEqual((1, 'first.pdf', 2, 50, 2.5),
                         (mapping['floor'], mapping['filepath'], mapping['page'],
                          mapping['scale_denominator'], mapping['x_m']))
        self.assertNotIn('kind', mapping)
        self.assertEqual([], self.dialog.configuration()['floor_dxf_files'])

    def test_cancelled_or_invalid_pdf_selection_keeps_previous_drawing(self):
        self.dialog.drawings[0] = {'floor': 0, 'filepath': 'original.dxf', 'kind': 'dxf'}
        original = deepcopy(self.dialog.configuration())
        with patch.object(QFileDialog, 'getOpenFileName', return_value=('', '')):
            self.dialog.choose_drawing(0)
        self.assertEqual(original, self.dialog.configuration())
        with patch.object(QFileDialog, 'getOpenFileName', return_value=('new.pdf', '')), \
                patch('project_setup.render_pdf_page', return_value=(None, 1)), \
                patch.object(PdfUnderlayDialog, 'exec', new=lambda _dialog: QDialog.Rejected):
            self.dialog.choose_drawing(0)
        self.assertEqual(original, self.dialog.configuration())
        with patch.object(QFileDialog, 'getOpenFileName', return_value=('broken.pdf', '')), \
                patch('project_setup.render_pdf_page', side_effect=ValueError('no pages')), \
                patch.object(QMessageBox, 'critical') as error:
            self.dialog.choose_drawing(0)
        error.assert_called_once()
        self.assertEqual(original, self.dialog.configuration())

    def test_skip_is_separate_from_cancel(self):
        self.dialog.skip_button.click()
        self.assertEqual(NewProjectDialog.SKIPPED, self.dialog.result())
        self.dialog.reject()
        self.assertEqual(QDialog.Rejected, self.dialog.result())


class ProjectSetupLifecycleTests(unittest.TestCase):
    setUpClass = classmethod(editing.CorridorEditingUiTests.setUpClass.__func__)
    setUp = editing.CorridorEditingUiTests.setUp
    tearDown = editing.CorridorEditingUiTests.tearDown

    def test_cancel_setup_preserves_document_and_recovery(self):
        self.editor.store.data['building']['floor_height_m'] = 7
        self.editor.capture_recovery()
        original = deepcopy(self.editor.store.data)
        with patch.object(QMessageBox, 'warning', return_value=QMessageBox.Discard), \
                patch.object(NewProjectDialog, 'exec', new=lambda _dialog: QDialog.Rejected):
            self.assertFalse(self.editor.new_project())
        self.assertEqual(original, self.editor.store.data)
        self.assertTrue(self.editor._recovery_store.snapshot_path.exists())

    def test_setup_creates_visible_floors_protects_work_and_survives_save_reopen(self):
        root = Path(self.temp.name)
        drawing = root / 'first.dxf'
        drawing.write_bytes(b'portable drawing')
        config = JsonStore().data
        config['building']['floor_count'] = 3
        config['floor_dxf_files'] = [{'floor': 1, 'filepath': str(drawing)}]
        self.editor.show_results_investigation()
        with patch.object(NewProjectDialog, 'exec', new=lambda _dialog: QDialog.Accepted), \
                patch.object(NewProjectDialog, 'configuration', new=lambda _dialog: config), \
                patch.object(self.editor, '_queue_all_floor_dxf_loads'), \
                patch.object(self.editor, 'ensure_floor_dxf_loaded', return_value=True):
            self.assertTrue(self.editor.new_project())
        self.assertEqual('layout', self.editor.workspace.stage)
        self.assertTrue(self.editor.has_unsaved_changes())
        self.assertEqual(1, len(self.editor.edit_history.entries))
        self.assertEqual([0, 1, 2], [key[1] for key in self.editor.workspace.object_items if key[0] == 'floor'])
        self.assertTrue(self.editor.capture_recovery())
        project = root / 'created.amrproj'
        with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(project), '')):
            self.assertTrue(self.editor.save_project(save_as=True))
        self.assertFalse(self.editor.has_unsaved_changes())
        self.assertEqual(3, Project.open(project).configuration()['building']['floor_count'])
        with patch.object(NewProjectDialog, 'exec', new=lambda _dialog: NewProjectDialog.SKIPPED):
            self.assertTrue(self.editor.new_project())
        self.assertTrue(self.editor.load_json_file(str(project), load_drawings=False))
        self.assertEqual([0, 1, 2], [key[1] for key in self.editor.workspace.object_items if key[0] == 'floor'])
        self.assertEqual(b'portable drawing', Path(self.editor.get_floor_dxf_path(1)).read_bytes())
