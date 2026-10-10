"""Draft controls remain readable without narrow feedback columns."""
from dataclasses import replace
from pathlib import Path
import unittest
from tests import test_corridor_editing as editing
from PySide6.QtGui import QFont, QFontDatabase


class CadInputLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = editing.QApplication.instance() or editing.QApplication([])
        font = Path('C:/Windows/Fonts/segoeui.ttf')
        if font.is_file():
            QFontDatabase.addApplicationFont(str(font))

    def setUp(self):
        editing.CorridorEditingUiTests.setUp(self)
        self.original_font = QFont(self.app.font())
        self.original_appearance = self.editor.appearance.value

    def tearDown(self):
        self.editor.appearance.apply(self.original_appearance)
        self.app.setFont(self.original_font)
        editing.CorridorEditingUiTests.tearDown(self)

    def check_bars(self, width, height, size):
        if Path('C:/Windows/Fonts/segoeui.ttf').is_file():
            self.app.setFont(QFont('Segoe UI', size))
        self.editor.appearance.apply(replace(self.original_appearance, font_size=size))
        self.editor.resize(width,height)
        self.editor.show()
        self.app.processEvents()
        for mode in ('corridor_node','lift'):
            button=self.editor.cad_toolbar.widgetForAction(self.editor.cad_toolbar.mode_actions[mode])
            self.assertTrue(button.isVisible(),mode)
            self.assertTrue(self.editor.cad_toolbar.rect().contains(button.geometry()),mode)
        for mode in ('rectangle','corridor','corridor_node','door','location','department','lift','edge','move','boundary','rotate','copy'):
            with self.subTest(mode=mode):
                self.editor.cancel_cad_command()
                self.editor.cad_move_input.hide()
                if mode == 'rectangle':
                    self.editor.start_location_rectangle('A')
                    bar = self.editor.rectangle_input
                    entry, feedback = bar.dimensions, bar.explanation
                    entry.setText('8,4,30')
                elif mode in ('corridor','corridor_node','door','location','department','lift','edge'):
                    self.editor._set_edit_mode('corridor_draw' if mode=='corridor' else mode)
                    bar = self.editor.cad_drawing_input
                    entry, feedback = bar.coordinate_edit, bar.feedback_label
                    entry.setText('10,5')
                elif mode == 'boundary':
                    self.editor.start_location_bounding_box_draw('A')
                    bar = self.editor.boundary_input
                    entry, feedback = bar.coordinate, bar.feedback
                    entry.setText('10,5')
                elif mode == 'rotate':
                    self.editor._set_edit_mode('select_move')
                    self.editor.selected_point_names = {'A', 'B'}
                    self.editor.show_selection_rotation()
                    bar = self.editor.cad_rotate_input
                    entry, feedback = bar.centre, bar.preview
                    bar.angle.setText('90')
                elif mode == 'copy':
                    self.editor._set_edit_mode('select_move')
                    self.editor.selected_point_names = {'A', 'B'}
                    self.editor.show_selection_copy()
                    bar = self.editor.cad_copy_input
                    entry, feedback = bar.offset, bar.preview
                    entry.setText('20,20')
                else:
                    self.editor._set_edit_mode('select_move')
                    self.editor.selected_point_name = 'A'
                    self.editor.selected_point_names = {'A'}
                    self.editor.show_selection_move()
                    bar = self.editor.cad_move_input
                    entry, feedback = bar.offset, bar.preview
                    entry.setText('2,3')
                self.app.processEvents()
                self.assertEqual(width,self.editor.width())
                self.assertLessEqual(bar.height(),160)
                # Transform bars share the feedback row with canvas picking.
                self.assertGreater(feedback.width(),bar.width()*(.75 if mode in ('rotate','move','copy') else .9))
                if mode in ('rotate','move','copy'):
                    self.assertFalse(feedback.geometry().intersects(bar.pick_button.geometry()))
                    self.assertTrue(bar.rect().contains(bar.pick_button.geometry()))
                self.assertGreater(feedback.geometry().top(),entry.geometry().bottom())
                self.assertTrue(bar.rect().contains(entry.geometry()))
                self.assertGreater(self.editor.canvas.viewport().height(),height*.4)

    def test_compact_large_text(self):
        self.check_bars(1024,768,18)

    def test_normal_window(self):
        self.check_bars(1500,900,10)
