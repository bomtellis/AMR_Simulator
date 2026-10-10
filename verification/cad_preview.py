"""Capture the actual approved workbench against a small, editable reference.

Run: python -m verification.cad_preview --output verification/latest/a2-ui
Uses Qt offscreen rendering; no mock controls or image compositing.
"""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import sys


def reference_project():
    """Three drawn locations and explicit shared profile sections, in metres."""
    from tests.test_engineering_reference import reference_config
    config = reference_config()
    config['building']['charge_location'] = 'Stores'
    config['building']['default_door_clear_width_m'] = 1.2
    # Keep the illustrative one-robot timings independent of legacy congestion
    # history; this example is for UI review, not traffic capacity acceptance.
    config['building']['edge_slowdown_per_amr'] = 0
    config['locations'] = []
    for name, x, y, width, height in (('Stores', 4, 6, 8, 4), ('Ward A', 20, 6, 8, 4),
                                      ('Waste', 12, -6, 4, 4)):
        config['locations'].append(dict(name=name, floor=0, x=x, y=y,
            bounding_box=[{'dx': dx, 'dy': dy} for dx, dy in
                          ((-width/2, -height/2), (width/2, -height/2),
                           (width/2, height/2), (-width/2, height/2))]))
    config['corridors']['nodes'] = [dict(name=name, floor=0, x=x, y=y,
        **({'has_door': True, 'door_clear_width_m': 1.2} if name.startswith('D-') else {}))
        for name, x, y in (('D-01', 4, 4), ('West', 4, 3), ('D-03', 12, 3),
                           ('East', 20, 3), ('D-02', 20, 4), ('South', 12, -3), ('D-04', 12, -4))]
    links = [('Stores', 'D-01'), ('D-01', 'West'), ('West', 'D-03'), ('D-03', 'East'),
             ('East', 'D-02'), ('D-02', 'Ward A'), ('D-03', 'South'), ('South', 'D-04'), ('D-04', 'Waste')]
    config['corridors']['edges'] = [dict(zip(('from', 'to'), link), width_m=2.4) for link in links]
    both = lambda pairs: [list(pair) for a, b in pairs for pair in ((a, b), (b, a))]
    config['route_profiles'] = {
        'Clean': {'allowed_edges': both(links[:6])},
        'Dirty': {'allowed_edges': both(links[2:])}}
    config['tasks'] = [dict(id='DELIVERY', pickup='Stores', dropoff='Ward A', payload='Box', route_profile='Clean'),
                       dict(id='COLLECTION', pickup='Ward A', dropoff='Waste', payload='Box', route_profile='Dirty')]
    return config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('verification/latest/a2-ui'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'visualiser'))
    from dataclasses import replace
    from unittest.mock import patch
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QApplication
    from appearance import Appearance, controller
    from app import AMRGraphEditor
    from models import JsonStore
    from amr_recovery import RecoveryStore
    from amr_project import Project
    from route_display import ALL
    from ui_theme import install_application_theme

    app = QApplication.instance() or QApplication([])
    for filename in ('segoeui.ttf', 'segoeuib.ttf'):
        path = Path('C:/Windows/Fonts') / filename
        if path.is_file():
            QFontDatabase.addApplicationFont(str(path))
    app.setFont(QFont('Segoe UI', 10))
    appearance = controller(app)
    appearance.apply(Appearance())
    install_application_theme(app)
    editor = AMRGraphEditor()
    editor._drawings_enabled = False
    editor._recovery_store = RecoveryStore(args.output / 'recovery')
    reference = reference_project()
    reference_path = args.output / 'A2-reference.amrproj'
    Project().save(reference_path, deepcopy(reference))
    editor.store = JsonStore(reference)
    editor.current_json_path = str(reference_path.resolve())
    editor._saved_state = editor._configuration_state()
    editor._reset_edit_history()
    editor.resize(1586, 992)
    editor.show()
    editor.refresh_canvas()
    editor.route_display_combo.setCurrentIndex(editor.route_display_combo.findData(ALL))
    editor.show_labels_check.setChecked(True)
    editor.validate_json()
    editor.workspace.show_page('layout', editor.canvas)
    app.processEvents()
    editor.fit_view()
    app.processEvents()
    editor.grab().save(str(args.output / 'light-workbench.png'))
    editor.workspace.select_object(('point', 'D-03'))
    editor.workspace.set_properties_visible(True)
    app.processEvents()
    editor.grab().save(str(args.output / 'properties.png'))
    editor.workspace.set_properties_visible(False)
    for theme in ('Dark', 'High contrast'):
        appearance.apply(replace(Appearance(), theme=theme))
        app.processEvents()
        editor.fit_view()
        app.processEvents()
        editor.grab().save(str(args.output / (theme.lower().replace(' ', '-') + '-workbench.png')))
    appearance.apply(Appearance())
    editor.resize(1024, 768)
    app.processEvents()
    editor.fit_view()
    app.processEvents()
    editor.grab().save(str(args.output / 'compact-workbench.png'))
    (args.output / 'reference.json').write_text(json.dumps(reference, indent=2), encoding='utf-8')
    with patch.object(editor, '_confirm_unsaved_changes', return_value=True):
        editor.close()
    editor.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    print(f'Captured actual A2 workbench and editable reference at {args.output.resolve()}')


if __name__ == '__main__':
    main()
