"""Read-only route-profile access projection and shared schematic rendering.

This projects graph permissions, not trajectories, vehicle clearance or timing.
Keep its auto-connection contract checked against independent simulator cases.
"""
from copy import deepcopy
import hashlib
import json
import math
import re
from enum import Enum

from PySide6.QtCore import QObject, Signal, Qt, QPointF
from PySide6.QtGui import QColor, QPen, QBrush, QFont, QPolygonF, QTransform
from PySide6.QtWidgets import QApplication, QGraphicsItem, QGraphicsSimpleTextItem, QGraphicsPolygonItem
from PySide6.QtCore import QSettings

PATTERNS = {'Solid': Qt.SolidLine, 'Dashed': Qt.DashLine, 'Dotted': Qt.DotLine, 'Dash-dot': Qt.DashDotLine}
PALETTE = ('#56b4e9', '#e69f00', '#00cc99', '#ff99cc', '#f0e442', '#c4adff')
STYLE_KEY = 'route-display/v1'
class DisplayMode(Enum):
    ALL = 'all'

ALL = DisplayMode.ALL
SCOPE = ('Profile access only: names, patterns and arrows identify permitted graph directions. '
         'Parallel strokes are schematic, not traffic lanes. Empty lists mean unrestricted. '
         'Task-local extensions, combined loads, clearance, outages and timing are not evaluated.')


def default_style(name):
    # Presentation defaults only; names never grant graph access.
    if name.casefold() == 'clean':
        return {'colour': '#56b4e9', 'pattern': 'Solid'}
    if name.casefold() == 'dirty':
        return {'colour': '#e69f00', 'pattern': 'Dashed'}
    digest = hashlib.sha256(name.encode('utf-8')).digest()
    return {'colour': PALETTE[digest[0] % len(PALETTE)], 'pattern': list(PATTERNS)[digest[1] % len(PATTERNS)]}


def validate_style(style):
    from appearance import contrast
    if not isinstance(style, dict) or set(style) != {'colour', 'pattern'}:
        raise ValueError('A route style needs a colour and line pattern.')
    if not isinstance(style['colour'], str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', style['colour']):
        raise ValueError('Route colour must use #RRGGBB notation.')
    if style['pattern'] not in PATTERNS:
        raise ValueError('Choose a supported line pattern.')
    if contrast(style['colour'], '#111111') < 4.5:
        raise ValueError('Route colour needs at least 4.5:1 contrast for labels against the dark map.')
    return style


class RouteStyles(QObject):
    changed = Signal()

    def __init__(self, appearance):
        super().__init__(appearance)
        self.appearance = appearance
        self.styles = {}
        self.warning = ''
        settings = appearance.settings
        raw = settings.value(STYLE_KEY, '') if settings is not None else ''
        if raw:
            try:
                styles = json.loads(raw)
                if not isinstance(styles, dict) or any(not isinstance(n, str) for n in styles):
                    raise ValueError()
                for style in styles.values():
                    validate_style(style)
                self.styles = styles
            except (TypeError, ValueError):
                self.warning = 'Saved route styles could not be read. Defaults are shown until you save a style.'

    def get(self, name):
        return dict(self.styles.get(name, default_style(name)))

    def save(self, name, style=None):
        if not isinstance(name, str) or not name:
            raise ValueError('Select a route profile first.')
        changed = deepcopy(self.styles)
        if style is None:
            changed.pop(name, None)
        else:
            changed[name] = dict(validate_style(style))
        settings = self.appearance.settings
        if settings is not None:
            old = settings.value(STYLE_KEY, None)
            settings.setValue(STYLE_KEY, json.dumps(changed))
            settings.sync()
            if settings.status() != QSettings.NoError:
                if old is None:
                    settings.remove(STYLE_KEY)
                else:
                    settings.setValue(STYLE_KEY, old)
                settings.sync()
                raise OSError('Route styles could not be saved; the active styles are unchanged.')
        self.styles = changed
        self.warning = ''
        self.changed.emit()


def styles_for(appearance):
    if not hasattr(appearance, '_route_styles'):
        appearance._route_styles = RouteStyles(appearance)
    return appearance._route_styles


def profile_rules(config):
    profiles = config.get('route_profiles', {})
    if not isinstance(profiles, dict):
        raise ValueError('Route profiles must be an object. Run Project checks.')
    result = {}
    for name, profile in profiles.items():
        if not isinstance(name, str) or not name or not isinstance(profile, dict):
            raise ValueError('Every route profile needs a name and an object of allowances.')
        rules = {}
        for key in ('allowed_nodes', 'allowed_edges', 'allowed_lifts'):
            value = profile.get(key, [])
            if not isinstance(value, list):
                raise ValueError(f'{name}: {key} must be a list; preview is unavailable.')
            if key == 'allowed_edges':
                if any(not isinstance(pair, (list, tuple)) or len(pair) != 2 or
                       any(not isinstance(n, str) or not n for n in pair) for pair in value):
                    raise ValueError(f'{name}: edge allowances need two node names.')
                rules[key] = {tuple(pair) for pair in value}
            else:
                if any(not isinstance(n, str) or not n for n in value):
                    raise ValueError(f'{name}: {key} needs non-empty names.')
                rules[key] = set(value)
        result[name] = rules
    return result


def permits(rules, a, b):
    nodes, edges = rules['allowed_nodes'], rules['allowed_edges']
    return (not nodes or {a, b} <= nodes) and (not edges or (a, b) in edges)


def access_preview(config):
    """Explicit and auto-connected same-floor edges, grouped by physical pair."""
    profiles = profile_rules(config)
    points, outgoing, sections = {}, {}, {}
    locations = config.get('locations', [])
    lifts = config.get('lifts', [])
    corridors = config.get('corridors', {})

    def point(name, floor, x, y):
        if name in points:
            raise ValueError(f'Duplicate graph point {name}; run Project checks.')
        if not isinstance(name, str) or not name or int(floor) != float(floor) or not all(math.isfinite(float(v)) for v in (floor, x, y)):
            raise ValueError('Graph positions must have names, integer floors and finite coordinates.')
        points[name] = dict(name=name, floor=int(floor), x=float(x), y=float(y))
        outgoing[name] = set()

    for row in locations:
        point(row['name'], row['floor'], row['x'], row['y'])
    for lift in lifts:
        for floor, pos in lift.get('floor_locations', {}).items():
            point(f"{lift['id']}-F{int(floor)}", floor, pos['x'], pos['y'])
    for row in corridors.get('nodes', []):
        point(row['name'], row['floor'], row['x'], row['y'])

    def edge(a, b, bidirectional=True, source=None):
        if a not in points or b not in points:
            raise ValueError(f'Unknown corridor endpoint: {a} → {b}.')
        if points[a]['floor'] != points[b]['floor']:
            raise ValueError(f'Corridor {a} → {b} crosses floors; preview is unavailable.')
        key = tuple(sorted((a, b)))
        section = sections.setdefault(key, dict(a=key[0], b=key[1], floor=points[a]['floor'],
            directions=set(), source=source, implicit=source is None, auto_directions=set(), explicit_directions=set()))
        origins = section['auto_directions'] if source is None else section['explicit_directions']
        origins.add((a, b))
        section['directions'].add((a, b))
        outgoing[a].add(b)
        if bidirectional:
            section['directions'].add((b, a))
            origins.add((b, a))
            outgoing[b].add(a)

    for source in corridors.get('edges', []):
        edge(source['from'], source['to'], source.get('bidirectional', True), source)
    if corridors.get('auto_connect', True):
        location_names = {row['name'] for row in locations}
        prefixes = tuple(lift['id'] + '-F' for lift in lifts)
        for floor in dict.fromkeys(p['floor'] for p in points.values()):
            candidates = [name for name, p in points.items() if p['floor'] == floor and name not in location_names and not name.startswith(prefixes)]
            if not candidates:
                continue
            endpoints = [row['name'] for row in locations if int(row['floor']) == floor]
            endpoints += [f"{lift['id']}-F{floor}" for lift in lifts if f"{lift['id']}-F{floor}" in points]
            for name in endpoints:
                if outgoing[name]:
                    continue
                p = points[name]
                nearest = min(candidates, key=lambda n: math.hypot(p['x'] - points[n]['x'], p['y'] - points[n]['y']))
                edge(name, nearest)
    for section in sections.values():
        section['profiles'] = {name: {(a, b) for a, b in section['directions'] if permits(rules, a, b)}
                               for name, rules in profiles.items()}
        section['profiles'] = {name: pairs for name, pairs in section['profiles'].items() if pairs}
    return points, list(sections.values()), profiles


def populate_choices(combo, config):
    old = combo.currentData()
    profiles = config.get('route_profiles', {})
    names = sorted(profiles) if isinstance(profiles, dict) else []
    wanted = [('Profile display off', None), ('All route profiles', ALL)] + [(name, name) for name in names]
    if [(combo.itemText(i), combo.itemData(i)) for i in range(combo.count())] == wanted:
        return
    combo.blockSignals(True)
    combo.clear()
    for label, value in wanted:
        combo.addItem(label, value)
    combo.setCurrentIndex(max(0, combo.findData(old)))
    combo.blockSignals(False)


class ProfileLabel(QGraphicsSimpleTextItem):
    def __init__(self, text, background='#111111'):
        super().__init__(text)
        self.background = background

    def paint(self, painter, option, widget=None):
        # Keep the name legible over nodes, intersecting lines and underlays.
        painter.fillRect(self.boundingRect(), QColor(self.background))
        super().paint(painter, option, widget)


def draw_access(scene, points, sections, floor, selected, styles, mapper, font_size=12, labels=True,
                label_background='#111111'):
    """Return (item, section) pairs so each host can preserve picking/lifetimes."""
    items = []
    for section in sections:
        if section['floor'] != floor:
            continue
        names = sorted(name for name in section['profiles'] if selected == ALL or selected == name)
        pa, pb = (mapper(points[n]['x'], points[n]['y']) for n in (section['a'], section['b']))
        dx, dy = pb.x() - pa.x(), pb.y() - pa.y()
        length = math.hypot(dx, dy)
        if not length:
            continue
        for index, name in enumerate(names):
            style = styles.get(name)
            offset = (index - (len(names) - 1) / 2) * .24
            shift = QPointF(-dy / length * offset, dx / length * offset)
            a, b = pa + shift, pb + shift
            pen = QPen(QColor(style['colour']), 2.5, PATTERNS[style['pattern']])
            pen.setCosmetic(True)
            line = scene.addLine(a.x(), a.y(), b.x(), b.y(), pen)
            pairs = section['profiles'][name]
            auto = section['auto_directions'] - section['explicit_directions']
            tooltip = name + ' | ' + style['pattern'] + '\n' + '\n'.join(
                f'{x} → {y}' + (' [auto]' if (x, y) in auto else '') for x, y in sorted(pairs))
            tooltip += '\nProfile permissions only; schematic, not a verified trajectory.'
            created = [line]
            angle = math.degrees(math.atan2(dy, dx))
            for pair in sorted(pairs):
                forward = pair == (section['a'], section['b'])
                arrow = QGraphicsPolygonItem(QPolygonF([QPointF(5, 0), QPointF(-4, -4), QPointF(-4, 4)]))
                arrow.setFlag(QGraphicsItem.ItemIgnoresTransformations)
                arrow.setPos(a + (b - a) * (.62 if forward else .38))
                arrow.setRotation(angle + (0 if forward else 180))
                arrow.setPen(QPen(QColor(style['colour']), 1))
                arrow.setBrush(QBrush(QColor(style['colour'])))
                scene.addItem(arrow)
                created.append(arrow)
            if labels:
                text = ProfileLabel(name + (' [auto]' if pairs & auto else ''), label_background)
                font = QFont(QApplication.font())
                font.setPixelSize(font_size)
                text.setFont(font)
                text.setBrush(QBrush(QColor(style['colour'])))
                text.setFlag(QGraphicsItem.ItemIgnoresTransformations)
                # Stack labels in device pixels; line offsets remain schematic.
                text.setPos((a + b) / 2)
                text.setTransform(QTransform.fromTranslate(4, index * (font_size + 3)))
                scene.addItem(text)
                created.append(text)
            for item in created:
                item.setZValue(25 if isinstance(item, ProfileLabel) else 2)
                item.setToolTip(tooltip)
                item.setData(0, 'route_profile_access')
                item.setData(1, name)
                item.setAcceptedMouseButtons(Qt.NoButton)
                items.append((item, section))
    return items
