"""Read-only graph geometry snaps for canvas transformations."""
import math
from visualiser.model_layers import definitions, layer_name
from visualiser.corridor_editing import project_fraction, intersection_target


def pick_point(editor, sx, sy, *, anchor=None):
    x, y = editor.scene_to_world(sx, sy)
    if editor.object_snap_check.isChecked():
        mode = editor.object_snap_mode.currentData()
        points = editor.store.points_for_floor(editor.floor_spin.value())
        layers = definitions(editor.store.data)
        visible = {name:p for name,p in points.items() if layers[layer_name(p)]['visible']}
        edges = [edge for edge in editor.store.data['corridors']['edges']
                 if edge['from'] in points and edge['to'] in points and layers[layer_name(edge)]['visible']]
        if mode in ('nearest','endpoints'):
            candidates = [(math.hypot(p['x']-x,p['y']-y),name) for name,p in visible.items()]
            if candidates:
                distance,name = min(candidates)
                if distance <= .45:
                    return float(visible[name]['x']),float(visible[name]['y'])
        if mode == 'intersections':
            target = intersection_target(points,edges,editor.floor_spin.value(),x,y)
            if target:
                return target['x'],target['y']
        elif mode in ('nearest','midpoints','perpendicular') and (mode != 'perpendicular' or anchor is not None):
            candidates = []
            for edge in edges:
                a,b = points[edge['from']],points[edge['to']]
                try:
                    fraction = (.5 if mode == 'midpoints' else
                                project_fraction(a,b,*(anchor if mode == 'perpendicular' else (x,y))))
                except ValueError:
                    continue
                if mode == 'perpendicular' and not 0 <= fraction <= 1:
                    continue
                fraction = min(1,max(0,fraction))
                px,py = a['x']+fraction*(b['x']-a['x']),a['y']+fraction*(b['y']-a['y'])
                if mode == 'perpendicular' and math.dist((px,py),anchor) < 1e-9:
                    continue
                distance = math.hypot(px-x,py-y)
                if distance <= .45:
                    candidates.append((distance,px,py))
            if candidates:
                _,px,py = min(candidates)
                return px,py
    return editor.snap(x,y)
