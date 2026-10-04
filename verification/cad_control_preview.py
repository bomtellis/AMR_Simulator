"""Capture real drafting controls at normal and compact/large-text sizes."""
import json
import os
from pathlib import Path
import sys


def main():
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / 'visualiser'))
    from unittest.mock import patch
    from dataclasses import replace
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QApplication
    from appearance import Appearance, controller
    from app import AMRGraphEditor
    from models import JsonStore
    from amr_recovery import RecoveryStore
    from verification.cad_preview import reference_project

    output = root / 'verification/latest/cad-control-preview'
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    for filename in ('segoeui.ttf', 'segoeuib.ttf'):
        font = Path('C:/Windows/Fonts') / filename
        if font.is_file():
            QFontDatabase.addApplicationFont(str(font))
    app.setFont(QFont('Segoe UI', 10))
    appearance = controller(app)  # In-memory; never writes user preferences.
    editor = AMRGraphEditor()
    editor._drawings_enabled = False
    editor._recovery_store = RecoveryStore(output / 'recovery')
    editor.store = JsonStore(reference_project())
    editor.refresh_canvas()
    editor._reset_edit_history()
    rows = []
    try:
        for name, width, height, font, command in (
                ('rectangle-normal',1500,900,10,'rectangle'),
                ('rectangle-large-text',1024,768,18,'rectangle'),
                ('corridor-large-text',1024,768,18,'corridor'),
                ('boundary-large-text',1024,768,18,'boundary'),
                ('rotation-large-text',1024,768,18,'rotation'),
                ('rotation-mouse',1500,900,10,'rotation-mouse'),
                ('move-mouse',1500,900,10,'move-mouse'),
                ('copy-large-text',1024,768,18,'copy'),
                ('dxf-layers',1500,900,10,'layers'),
                ('model-layers',1500,900,10,'model-layers'),
                ('layer-styles',1500,900,10,'layer-styles')):
            editor.cancel_cad_command()
            appearance.apply(replace(Appearance(), font_size=font))
            editor.resize(width,height)
            editor.show()
            if command == 'rectangle':
                editor.start_location_rectangle('Stores')
                editor.rectangle_input.dimensions.setText('8,4,30')
            elif command == 'boundary':
                editor.start_location_bounding_box_draw('Stores')
                for text in ('-2,-2', '@4,0', '@3<90'):
                    editor.boundary_input.coordinate.setText(text)
                    editor.boundary_input.submit()
                editor.boundary_input.coordinate.setText('@-4,0')
            elif command == 'move-mouse':
                editor._set_edit_mode('select_move')
                editor.selected_point_names = {'Stores', 'West'}
                editor.show_selection_move()
                bar = editor.cad_move_input
                bar.begin_mouse()
                pos = editor.world_to_scene(0,0)
                bar.mouse_click(pos.x(),pos.y())
                pos = editor.world_to_scene(3,-2)
                bar.pointer_moved(pos.x(),pos.y())
                bar.mouse_timer.stop()
                bar._update_mouse_preview()
            elif command == 'rotation-mouse':
                editor._set_edit_mode('select_move')
                editor.selected_point_names = {'Stores', 'West'}
                editor.show_selection_rotation()
                bar = editor.cad_rotate_input
                bar.begin_mouse()
                for x,y in ((0,0),(5,0)):
                    pos = editor.world_to_scene(x,y)
                    bar.mouse_click(pos.x(),pos.y())
                pos = editor.world_to_scene(4,4)
                bar.pointer_moved(pos.x(),pos.y())
                bar.mouse_timer.stop()
                bar._update_mouse_preview()
            elif command == 'rotation':
                editor._set_edit_mode('select_move')
                editor.selected_point_names = {'Stores', 'West'}
                editor.show_selection_rotation()
                editor.cad_rotate_input.angle.setText('90')
            elif command == 'copy':
                editor._set_edit_mode('select_move')
                editor.selected_point_names = {'Stores', 'D-01'}
                editor.show_selection_copy()
                editor.cad_copy_input.offset.setText('6,-3')
            elif command == 'layer-styles':
                editor.selected_point_names = set()
                editor.selected_point_name = None
                editor.style_model_layer('Default',dict(colour='#633b99',pattern='Dashed',width_px=2.5))
                editor.show_model_layers()
                editor.model_layer_panel.choice.setCurrentText('Default')
                editor.model_layer_panel.style_toggle.setChecked(True)
            elif command == 'model-layers':
                editor.dxf_layers.dock.close()
                editor.update_model_layer('Fixed equipment')
                editor.selected_point_names = {'Stores'}
                editor.selected_edge_keys = set()
                editor.assign_model_layer('Fixed equipment')
                editor.update_model_layer('Fixed equipment',locked=True)
                editor.show_model_layers()
                editor.model_layer_panel.choice.setCurrentText('Fixed equipment')
            elif command == 'layers':
                import ezdxf
                from dxf_scene import DXFScene
                doc = ezdxf.new()
                doc.header['$INSUNITS'] = 6
                for layer in ('Walls', 'Furniture', 'Dimensions'):
                    doc.layers.new(layer)
                doc.modelspace().add_lwpolyline([(0,-9),(25,-9),(25,10),(0,10)],close=True,dxfattribs={'layer':'Walls'})
                doc.modelspace().add_lwpolyline([(2,6),(6,6),(6,8),(2,8)],close=True,dxfattribs={'layer':'Furniture'})
                doc.modelspace().add_text('Reference floor',dxfattribs={'layer':'Dimensions','height':.5,'insert':(8,9)})
                path = output / 'layer-preview.dxf'
                doc.saveas(path)
                editor.store.data['floor_dxf_files'] = [dict(floor=0,filepath=str(path))]
                editor._dxf_cache[0] = DXFScene.load_content(str(path))
                editor._drawings_enabled = True
                editor._set_edit_mode('select_move')
                editor.refresh_canvas()
                editor.show_dxf_layers()
                editor.dxf_layers.set_visible(['Furniture'],False)
            else:
                editor._set_edit_mode('corridor_draw')
                editor.corridor_draw_start = 'Stores'
                editor.cad_drawing_input.coordinate_edit.setText('@10<30')
            app.processEvents()
            editor.fit_view()
            app.processEvents()
            editor.grab().save(str(output / (name+'.png')))
            rows.append(dict(name=name,requested=[width,height],actual=[editor.width(),editor.height()],
                             viewport=[editor.canvas.viewport().width(),editor.canvas.viewport().height()]))
    finally:
        with patch.object(editor, '_confirm_unsaved_changes', return_value=True):
            editor.close()
        editor.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
    (output/'dimensions.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
    print(json.dumps(rows))


if __name__ == '__main__':
    main()
