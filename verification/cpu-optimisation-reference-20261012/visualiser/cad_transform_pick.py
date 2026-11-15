"""Read-only graph geometry snaps for canvas transformations."""
import math
from visualiser.model_layers import definitions, layer_name
from visualiser.corridor_editing import project_fraction, intersection_target, object_snap_modes


def pick_point(editor, sx, sy, *, anchor=None):
    x, y = editor.scene_to_world(sx, sy)
    if editor.object_snap_check.isChecked():
        modes = object_snap_modes(editor.object_snap_mode.currentData())
        points = editor.store.points_for_floor(editor.floor_spin.value())
        layers = definitions(editor.store.data)
        visible = {name:p for name,p in points.items() if layers[layer_name(p)]['visible']}
        edges = [edge for edge in editor.store.data['corridors']['edges']
                 if edge['from'] in points and edge['to'] in points and layers[layer_name(edge)]['visible']]
        targets = []
        nearest = []
        nearest_point = None
        if modes & {'nearest', 'endpoints'}:
            points_nearby = [(math.hypot(p['x']-x,p['y']-y),name) for name,p in visible.items()]
            if points_nearby:
                distance,name = min(points_nearby)
                if distance <= .45:
                    point = (float(visible[name]['x']), float(visible[name]['y']))
                    if len(modes) == 1:
                        return point
                    (targets if 'endpoints' in modes else nearest).append((distance, 1, *point))
                    if 'nearest' in modes:
                        nearest_point = point
        if 'intersections' in modes:
            target = intersection_target(points,edges,editor.floor_spin.value(),x,y)
            if target:
                targets.append((math.hypot(target['x']-x, target['y']-y), 0, target['x'], target['y']))
        for priority, mode in ((2, 'midpoints'), (3, 'perpendicular'), (4, 'nearest')):
            if mode not in modes or (mode == 'perpendicular' and anchor is None):
                continue
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
                    (nearest if mode == 'nearest' else targets).append((distance, priority, px, py))
        if not targets and nearest_point is not None:
            return nearest_point
        candidates = targets or nearest
        if candidates:
            _, _, px, py = min(candidates)
            return px, py
    return editor.snap(x,y)
