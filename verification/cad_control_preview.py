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
                ('copy-large-text',1024,768,18,'copy')):
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
