"""Shared grid/visible-point picking for canvas transformation gestures."""
def pick_point(editor, sx, sy):
    x, y = editor.scene_to_world(sx, sy)
    if editor.object_snap_check.isChecked():
        name = editor.find_nearest_point_name(x,y,editor.floor_spin.value(),radius_world=.45)
        if name:
            point = editor.store.all_points()[name]
            return float(point['x']),float(point['y'])
    return editor.snap(x,y)
