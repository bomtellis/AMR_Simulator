"""Layer identity, drawing-cache retention and display-only visibility evidence."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PySide6.QtCore import Qt, QSettings
from tests import test_corridor_editing as editing
from tests import test_cad_delete_and_drawing_history as drawing
from visualiser.dxf_scene import DXFScene
from visualiser.dxf_layers import DxfLayers, read_preferences, KEY


class DxfLayerImportTests(unittest.TestCase):
    def test_direct_and_block_layer_zero_inheritance_retain_scaled_geometry(self):
        import ezdxf
        doc = ezdxf.new()
        doc.header['$INSUNITS'] = 4
        for name in ('Walls','Labels','Equipment'):
            doc.layers.new(name)
        doc.modelspace().add_line((0,0),(1000,0),dxfattribs={'layer':'Walls'})
        block = doc.blocks.new('Fixture')
        block.add_line((0,0),(1000,0))
        block.add_line((0,1000),(1000,1000),dxfattribs={'layer':'Equipment'})
        doc.modelspace().add_blockref('Fixture',(2000,0),dxfattribs={'layer':'Walls'})
        doc.modelspace().add_text('Room',dxfattribs={'layer':'Labels','height':100})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'layers.dxf'
            doc.saveas(path)
            payload = DXFScene.load_content(str(path))
        self.assertEqual(['Walls','Walls','Equipment','Labels'],[e['layer'] for e in payload['entities']])
        self.assertEqual((2.,0.),payload['entities'][1]['start'])
        self.assertEqual((3.,1.),payload['entities'][2]['end'])

    def test_invalid_saved_preferences_reject_as_a_whole(self):
        for value in ({},dict(version=True,hidden={}),dict(version=1,hidden={'file':[False]})):
            with self.assertRaises(ValueError):
                read_preferences(json.dumps(value))


class DxfLayerUiTests(unittest.TestCase):
    setUpClass = classmethod(editing.CorridorEditingUiTests.setUpClass.__func__)
    setUp = editing.CorridorEditingUiTests.setUp
    tearDown = editing.CorridorEditingUiTests.tearDown

    def prepare(self):
        drawing.CadDeleteAndDrawingHistoryTests.drawings(self)
        e = self.editor
        e._dxf_cache[0]['entities'] = [dict(type='LINE',layer='Walls',start=(0,0),end=(10,0)),
            dict(type='LINE',layer='Walls',start=(0,1),end=(10,1)),
            dict(type='LINE',layer='Equipment',start=(1,2),end=(3,2)),
            dict(type='TEXT',layer='Labels',insert=(1,1),text='Room',height=.2)]
        e._rendered_dxf_source = None
        e.refresh_canvas()
        return e.dxf_layers

    def test_toggle_reuses_batched_graphics_and_does_not_change_model_history_or_view(self):
        layers = self.prepare()
        e = self.editor
        before = deepcopy(e.store.data)
        history = deepcopy(e.edit_history.entries)
        items = list(e._rendered_dxf_items)
        self.assertEqual(3,len(items))
        transform = e.canvas.transform()
        with patch.object(e.dxf_scene,'populate_graphics_scene',side_effect=AssertionError('Drawing rebuilt')):
            layers.set_visible(['Walls'],False)
            e.refresh_canvas()
            self.assertEqual(items,e._rendered_dxf_items)
            self.assertTrue(all(item.isVisible() == (item.data(10) != 'Walls') for item in items))
            layers.set_visible(['Walls'],True)
        self.assertTrue(all(item.isVisible() for item in items))
        self.assertEqual(before,e.store.data)
        self.assertEqual(history,e.edit_history.entries)
        self.assertEqual(transform,e.canvas.transform())

    def test_search_isolate_checkbox_and_show_all_are_consistent(self):
        layers = self.prepare()
        self.editor.show_dxf_layers()
        layers.search.setText('walls')
        visible = [layers.layers.item(i) for i in range(layers.layers.count()) if not layers.layers.item(i).isHidden()]
        self.assertEqual(1,len(visible))
        layers.layers.setCurrentItem(visible[0])
        layers.isolate()
        self.assertTrue(all(item.isVisible() == (item.data(10)=='Walls') for item in self.editor._rendered_dxf_items))
        visible[0].setCheckState(Qt.Unchecked)
        self.assertTrue(all(not item.isVisible() for item in self.editor._rendered_dxf_items))
        layers.set_visible(layers.counts,True)
        self.assertTrue(all(item.isVisible() for item in self.editor._rendered_dxf_items))

    def test_saved_visibility_follows_drawing_path_and_survives_floor_switch(self):
        self.prepare()
        settings = QSettings(str(Path(self.temp.name)/'layers.ini'),QSettings.IniFormat)
        e = self.editor
        e.dxf_layers = DxfLayers(e,settings)
        e.dxf_layers.refresh()
        e.dxf_layers.set_visible(['Walls'],False)
        self.assertIn('Walls',settings.value(KEY))
        e.floor_spin.setValue(1)
        self.assertEqual({},e.dxf_layers.counts)
        e.floor_spin.setValue(0)
        e.dxf_layers = DxfLayers(e,settings)
        e.refresh_canvas()
        self.assertTrue(all(item.isVisible() == (item.data(10)!='Walls') for item in e._rendered_dxf_items))

    def test_legacy_entities_without_layer_use_zero_and_work_during_run_lock(self):
        layers = self.prepare()
        self.editor._dxf_cache[0]['entities'] = [dict(type='LINE',start=(0,0),end=(1,1))]
        self.editor._rendered_dxf_source = None
        self.editor.refresh_canvas()
        self.assertEqual({'0':1},layers.counts)
        with patch.object(self.editor,'project_editing_locked',return_value=True):
            layers.set_visible(['0'],False)
        self.assertFalse(self.editor._rendered_dxf_items[0].isVisible())

    def test_settings_failure_keeps_session_choice_and_preserves_previous_saved_value(self):
        self.prepare()
        class FailedSettings:
            stored = '{}'
            def value(self,key,default=None):
                return self.stored
            def setValue(self,key,value):
                self.stored = value
            def sync(self):
                pass
            def status(self):
                return QSettings.AccessError
        settings = FailedSettings()
        layers = DxfLayers(self.editor,settings)
        self.assertIn('all layers start visible',layers.warning)
        layers.refresh()
        layers.set_visible(['Walls'],False)
        self.assertEqual('{}',settings.stored)
        self.assertIn('could not be saved',layers.warning)
        self.assertTrue(all(item.isVisible() == (item.data(10)!='Walls') for item in self.editor._rendered_dxf_items))

    def test_dock_restores_after_focus_or_stage_change_but_respects_explicit_close(self):
        layers = self.prepare()
        e = self.editor
        e.show_dxf_layers()
        self.assertFalse(layers.dock.isHidden())
        e.workspace.set_canvas_focus(True)
        self.assertTrue(layers.dock.isHidden())
        e.workspace.set_canvas_focus(False)
        self.assertFalse(layers.dock.isHidden())
        e.workspace.activate('configuration')
        self.assertTrue(layers.dock.isHidden())
        e.workspace.activate('layout')
        self.assertFalse(layers.dock.isHidden())
        layers.dock.close()
        e.workspace.set_canvas_focus(True)
        e.workspace.set_canvas_focus(False)
        self.assertTrue(layers.dock.isHidden())
