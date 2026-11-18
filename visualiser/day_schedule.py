"""Shared graphical demand and FM release editor; all mutations use draft adapters."""
from copy import deepcopy
from datetime import datetime
import json
import math

from PySide6.QtCore import QEvent, QObject, QPointF, QRectF, QRunnable, Qt, QThreadPool, Signal, Slot
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QScrollArea, QSlider, QTableWidget, QTableWidgetItem,
    QHeaderView, QVBoxLayout, QWidget, QSizePolicy, QPlainTextEdit)

from amr_demand_schedule import (DAYS, arrangement, clock, edit_demand, edit_fm,
    invalid_slots, minutes, rule_times, rules, segments, span, validated_generation, edit_category_notes,
    move_demand_selection, move_fm_selection)


class ScheduleSignals(QObject):
    finished = Signal(object, str)


class ScheduleJob(QRunnable):
    def __init__(self, operation):
        super().__init__()
        self.operation = operation
        self.signals = ScheduleSignals()

    def run(self):
        try:
            self.signals.finished.emit(self.operation(), '')
        except Exception as exc:
            self.signals.finished.emit(None, str(exc))


class ScheduleCanvas(QWidget):
    selected = Signal(object)
    edited = Signal(object, float, float)
    moved = Signal(object, float)
    selection_set_changed = Signal(object)
    cancelled = Signal()
    LABEL = 205
    TOP = 40
    ROW = 43

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []
        self.hits = []
        self.selection = None
        self.selections = set()
        self.anchor = None
        self.row_layout = []
        self.drag = None
        self.zoom = 1
        self.fit_width = 820
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName('Day schedule. Select a schedule in the list below for exact keyboard editing.')

    def set_rows(self, rows):
        self.rows = rows
        self.update_size()

    def update_size(self):
        width = max(620, int((self.fit_width - self.LABEL) * self.zoom + self.LABEL))
        top = self.TOP
        self.row_layout = []
        for row in self.rows:
            notes = str(row.get('notes', '') or '').strip()
            note_width = width-16 if row.get('header') else self.LABEL-16
            note_height = self.fontMetrics().boundingRect(
                QRectF(0,0,note_width,100000).toRect(),Qt.TextWordWrap,notes).height() if notes else 0
            height = max(self.ROW,self.fontMetrics().height()+note_height+14) if notes else self.ROW
            self.row_layout.append((top,height))
            top += height
        self.setFixedSize(width, max(160, top+8))
        self.update()

    def row_geometry(self, index):
        return self.row_layout[index]

    def x(self, minute):
        return self.LABEL + (self.width() - self.LABEL - 12) * minute / 1440

    def minute(self, x):
        return (x - self.LABEL) / (self.width() - self.LABEL - 12) * 1440

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        palette = self.palette()
        painter.fillRect(self.rect(), palette.base())
        text_color = palette.text().color()
        accent = palette.highlight().color()
        self.hits = []
        painter.setPen(text_color)
        for hour in range(25):
            x = self.x(hour * 60)
            painter.setPen(palette.mid().color())
            painter.drawLine(QPointF(x, self.TOP - 8), QPointF(x, self.height()))
            if hour % (1 if self.zoom >= 2 else 2) == 0:
                painter.setPen(text_color)
                label_rect = QRectF(x if hour == 0 else x - 50 if hour == 24 else x - 25, 6, 50, 23)
                alignment = Qt.AlignLeft if hour == 0 else Qt.AlignRight if hour == 24 else Qt.AlignCenter
                painter.drawText(label_rect, alignment | Qt.AlignVCenter, f'{hour:02d}:00')
        for index, row in enumerate(self.rows):
            y, height = self.row_geometry(index)
            if row.get('header'):
                painter.fillRect(QRectF(0, y, self.width(), height), palette.alternateBase())
            painter.setPen(palette.mid().color())
            painter.drawLine(0, y + height, self.width(), y + height)
            painter.setPen(text_color)
            label = row['label']
            notes = str(row.get('notes', '') or '').strip()
            label_top = y+4 if notes else y
            label_height = self.fontMetrics().height()+4 if notes else height
            painter.drawText(QRectF(8, label_top, self.LABEL - 16, label_height), Qt.AlignVCenter,
                             painter.fontMetrics().elidedText(label, Qt.ElideRight, self.LABEL - 16))
            if notes:
                painter.drawText(QRectF(8,y+self.fontMetrics().height()+9,
                    self.width()-16 if row.get('header') else self.LABEL-16,
                    height-self.fontMetrics().height()-10),Qt.TextWordWrap,notes)
            if row.get('message'):
                painter.setPen(palette.placeholderText().color())
                painter.drawText(QRectF(self.LABEL + 7, y, self.width() - self.LABEL - 15, min(height,self.ROW)),
                                 Qt.AlignVCenter, painter.fontMetrics().elidedText(row['message'], Qt.ElideRight,
                                                                               self.width() - self.LABEL - 20))
            y += (height-self.ROW)/2
            for item in row.get('items', []):
                start, duration = item['start'], item['duration']
                if self.drag and item['id'] in self.drag['ids']:
                    if len(self.drag['ids'])>1:
                        start = (start+self.drag['delta'])%1440
                    else:
                        start, duration = self.drag['preview']
                selected = item['id'] in self.selections
                color = accent if item.get('enabled', True) else palette.mid().color()
                fill = QColor(color)
                fill.setAlpha(58 if item.get('outline') else 175)
                painter.setBrush(Qt.NoBrush if item.get('outline') else fill)
                pen = QPen(color, 2.5 if selected else 1.3)
                if item.get('outline'):
                    pen.setStyle(Qt.DashLine)
                painter.setPen(pen)
                if not duration:
                    rect = QRectF(self.x(start) - 6, y + 6, 12, 29)
                    painter.drawRoundedRect(rect, 3, 3)
                    self.hits.append((rect.adjusted(-3, -2, 3, 2), item, 'move'))
                    painter.setPen(text_color)
                    time_label = clock(start)
                    right = min(self.x(start) + 10, self.width() - 49)
                    painter.drawText(QRectF(right, y + 6, 44, 29), Qt.AlignVCenter, time_label)
                else:
                    pieces = segments(start, duration)
                    for left, right in pieces:
                        rect = QRectF(self.x(left), y + 7, max(2, self.x(right) - self.x(left)), 28)
                        painter.setPen(pen)
                        painter.drawRoundedRect(rect, 4, 4)
                        self.hits.append((rect, item, 'move'))
                        if item.get('editable'):
                            if left == start % 1440:
                                edge = QRectF(rect.left() - 4, rect.top(), 10, rect.height())
                                self.hits.append((edge, item, 'start'))
                                painter.drawLine(QPointF(rect.left() + 3, rect.top() + 7),
                                                 QPointF(rect.left() + 3, rect.bottom() - 7))
                            if right == (start % 1440 + duration - (1440 if start % 1440 + duration > 1440 else 0)):
                                edge = QRectF(rect.right() - 6, rect.top(), 10, rect.height())
                                self.hits.append((edge, item, 'end'))
                                painter.drawLine(QPointF(rect.right() - 3, rect.top() + 7),
                                                 QPointF(rect.right() - 3, rect.bottom() - 7))
                        label = f"{clock(start)}–{clock(start % 1440 + duration, end=True)}"
                        if len(pieces) > 1:
                            label += ' ↔'
                        if rect.width() > 75:
                            painter.setPen(text_color)
                            painter.drawText(rect.adjusted(10, 0, -7, 0), Qt.AlignVCenter,
                                             painter.fontMetrics().elidedText(label, Qt.ElideRight, int(rect.width() - 17)))
        if self.hasFocus():
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(accent, 2))
            painter.drawRect(self.rect().adjusted(1, 1, -2, -2))

    def hit(self, position):
        return next(((item, edge) for rect, item, edge in reversed(self.hits) if rect.contains(position)), (None, None))

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        item, edge = self.hit(event.position())
        if item is None:
            if not event.modifiers():
                self.selections.clear()
                self.selection = None
                self.selected.emit(None)
                self.selection_set_changed.emit(set())
                self.update()
            return
        self.setFocus()
        identity = item['id']
        candidates = [value for row in self.rows for value in row.get('items',[]) if value.get('editable')]
        scope_order = {}
        for value in candidates:
            scope = value.get('rule') or value['id'][:3]
            scope_order.setdefault(scope,len(scope_order))
        # A schedule split into overlapping lanes still has a chronological range.
        candidates.sort(key=lambda value:(scope_order[value.get('rule') or value['id'][:3]],value['start']))
        editable = [value['id'] for value in candidates]
        modifiers = event.modifiers()
        if modifiers & Qt.ShiftModifier and identity in editable:
            anchor = self.anchor if self.anchor in editable else identity
            first,last = sorted((editable.index(anchor),editable.index(identity)))
            self.selections.update(editable[first:last+1])
        elif modifiers & Qt.ControlModifier and identity in editable:
            self.selections.intersection_update(editable)
            if identity in self.selections:self.selections.remove(identity)
            else:self.selections.add(identity)
            self.anchor = identity
        elif identity not in self.selections:
            self.selections = {identity}
        if not modifiers & Qt.ShiftModifier:
            self.anchor = identity
        self.selection = identity if identity in self.selections else next(iter(self.selections),None)
        self.selected.emit(self.selection)
        self.selection_set_changed.emit(set(self.selections))
        if item.get('editable') and identity in self.selections:
            ids = self.selections.intersection(editable)
            if len(ids)>1:edge='move'
            self.drag = {'item': item, 'edge': edge, 'x': event.position().x(),
                         'preview': (item['start'], item['duration']), 'ids': ids, 'delta': 0}
            self.grabMouse()
        self.update()

    @staticmethod
    def drag_times(start, duration, edge, delta):
        delta = math.floor(delta / 5 + 0.5) * 5
        if edge == 'move':
            return (start + delta) % 1440, duration
        if edge == 'start':
            length = max(1, min(1440, duration - delta))
            return (start + duration - length) % 1440, length
        return start, max(1, min(1440, duration + delta))

    def mouseMoveEvent(self, event):
        if self.drag:
            item = self.drag['item']
            delta = self.minute(event.position().x()) - self.minute(self.drag['x'])
            self.drag['delta'] = math.floor(delta/5+.5)*5
            self.drag['preview'] = self.drag_times(item['start'], item['duration'], self.drag['edge'], delta)
            self.update()
            return
        item, edge = self.hit(event.position())
        self.setCursor(Qt.SizeHorCursor if item and item.get('editable') and edge != 'move'
                       else Qt.OpenHandCursor if item and item.get('editable') else Qt.ArrowCursor)
        self.setToolTip(item['description'] if item else '')

    def mouseReleaseEvent(self, event):
        if self.drag and event.button() == Qt.LeftButton:
            drag, self.drag = self.drag, None
            self.releaseMouse()
            if len(drag['ids'])>1 and drag['delta']:
                self.moved.emit(set(drag['ids']),drag['delta'])
            elif drag['preview'] != (drag['item']['start'], drag['item']['duration']):
                self.edited.emit(drag['item']['id'], *drag['preview'])
            self.update()

    def keyPressEvent(self, event):
        if event.key()==Qt.Key_A and event.modifiers() & Qt.ControlModifier:
            self.selections={item['id'] for row in self.rows for item in row.get('items',[]) if item.get('editable')}
            self.selection_set_changed.emit(set(self.selections))
            self.update()
            event.accept()
        elif event.key() == Qt.Key_Escape and self.drag:
            self.drag = None
            self.releaseMouse()
            self.cancelled.emit()
            self.update()
            event.accept()
        elif event.key() in (Qt.Key_Left, Qt.Key_Right) and self.selection:
            if len(self.selections)>1:
                self.moved.emit(set(self.selections),5 if event.key()==Qt.Key_Right else -5)
                event.accept()
                return
            item = next((item for row in self.rows for item in row.get('items', [])
                         if item['id'] == self.selection), None)
            if item and item.get('editable'):
                self.edited.emit(item['id'], (item['start'] + (5 if event.key() == Qt.Key_Right else -5)) % 1440,
                                 item['duration'])
                event.accept()
        else:
            super().keyPressEvent(event)


class ScheduleRuler(QWidget):
    """A viewport child stays above the canvas during vertical scrolling."""
    def __init__(self, scroll, canvas):
        super().__init__(scroll.viewport())
        self.scroll, self.canvas = scroll, canvas
        self.setAccessibleName('Fixed 24-hour time ruler')
        scroll.horizontalScrollBar().valueChanged.connect(self.update)
        self.setGeometry(0, 0, scroll.viewport().width(), canvas.TOP)
        self.raise_()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.palette().base())
        painter.setPen(self.palette().text().color())
        offset = self.scroll.horizontalScrollBar().value()
        for hour in range(25):
            if hour % (1 if self.canvas.zoom >= 2 else 2):
                continue
            x = self.canvas.x(hour*60) - offset
            rect = QRectF(x if hour==0 else x-50 if hour==24 else x-25, 6, 50, 23)
            alignment = Qt.AlignLeft if hour==0 else Qt.AlignRight if hour==24 else Qt.AlignCenter
            painter.drawText(rect, alignment | Qt.AlignVCenter, f'{hour:02d}:00')
        painter.setPen(self.palette().mid().color())
        painter.drawLine(0,self.height()-1,self.width(),self.height()-1)


class DaySchedulePanel(QWidget):
    """Reusable view of native demand plus an independently reviewed FM draft."""
    preview_changed = Signal()
    def __init__(self, generation, apply_generation, departments=(), project=None,
                 open_rule=None, parent=None, *, native_editable=True, applied_text=None):
        super().__init__(parent)
        self.generation_provider = generation
        self.apply_generation = apply_generation
        self.departments = departments
        self.project_provider = project
        self.open_rule = open_rule
        self.native_editable = native_editable
        self.applied_text = applied_text or 'Arrangement added to this draft. Save the demand generator and project to keep it.'
        self.generation = {}
        self.plan = {'enabled': False, 'categories': {}}
        self.comparison = None
        self.baseline = None
        self.compared_signature = None
        self.job = None
        self.items = {}
        self.rule_by_id = {}
        self._loaded = False
        self.dirty = False
        self._refreshing = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        view = QHBoxLayout()
        self.day = QComboBox()
        for value in DAYS:
            self.day.addItem(value.title(), value)
        self.day.setAccessibleName('Day shown; edits apply to every active day')
        view.addWidget(QLabel('Service day'))
        view.addWidget(self.day)
        self.mode = QComboBox()
        if native_editable:
            self.mode.addItem('Demand', 'demand')
        self.mode.addItem('FM plan', 'fm')
        self.mode.setAccessibleName('Editing mode')
        view.addWidget(QLabel('Editing'))
        view.addWidget(self.mode)
        self.show_disabled = QCheckBox('Show disabled')
        view.addWidget(self.show_disabled)
        self.zoom = QSlider(Qt.Horizontal)
        self.zoom.setRange(100, 400)
        self.zoom.setValue(100)
        self.zoom.setMaximumWidth(140)
        self.zoom.setAccessibleName('Timeline zoom')
        view.addWidget(QLabel('Zoom'))
        view.addWidget(self.zoom)
        self.fit = QPushButton('Fit day')
        view.addWidget(self.fit)
        self.preview_button = QPushButton('Demand preview…')
        view.addWidget(self.preview_button)
        view.addStretch(1)
        layout.addLayout(view)
        self.hint = QLabel('Drag to move; pull either end to resize. Five-minute steps; exact times below. Edits affect every active day.')
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(False)
        self.scroll.setMinimumHeight(180)
        self.canvas = ScheduleCanvas()
        self.scroll.setWidget(self.canvas)
        self.ruler = ScheduleRuler(self.scroll, self.canvas)
        self.scroll.viewport().installEventFilter(self)
        layout.addWidget(self.scroll, 1)
        selection = QHBoxLayout()
        self.selector = QComboBox()
        self.selector.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.selector.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.selector.setMinimumContentsLength(16)
        self.selector.setAccessibleName('Schedule selection; includes all visible bars and markers')
        selection.addWidget(QLabel('Selected'))
        selection.addWidget(self.selector, 1)
        self.selection_count = QLabel('')
        selection.addWidget(self.selection_count)
        self.edit_settings = QPushButton('Open settings…')
        selection.addWidget(self.edit_settings)
        layout.addLayout(selection)
        exact = QHBoxLayout()
        self.start = QLineEdit()
        self.end = QLineEdit()
        for control, name in ((self.start, 'Selected start or release time'), (self.end, 'Selected end time')):
            control.setMaximumWidth(88)
            control.setPlaceholderText('HH:MM')
            control.setAccessibleName(name)
        self.exact_button = QPushButton('Set times')
        exact.addWidget(QLabel('Start / release'))
        exact.addWidget(self.start)
        exact.addWidget(QLabel('End'))
        exact.addWidget(self.end)
        exact.addWidget(self.exact_button)
        self.details = QLabel()
        self.details.setWordWrap(True)
        exact.addWidget(self.details, 1)
        layout.addLayout(exact)
        notes_row = QHBoxLayout()
        notes_row.addWidget(QLabel('Category notes'))
        self.category_notes = QPlainTextEdit()
        self.category_notes.setMaximumHeight(60)
        self.category_notes.setPlaceholderText('Notes for this category, included in the demand preview')
        self.category_notes.setAccessibleName('Selected category notes')
        self.save_notes = QPushButton('Save notes')
        notes_row.addWidget(self.category_notes, 1)
        notes_row.addWidget(self.save_notes)
        layout.addLayout(notes_row)
        actions = QHBoxLayout()
        self.suggest = QPushButton('Suggest arrangement')
        self.compare = QPushButton('Compare arrangements')
        self.use = QPushButton('Use arrangement')
        self.disable = QPushButton('Disable FM plan')
        self.discard = QPushButton('Discard FM draft')
        for button in (self.suggest, self.compare, self.use, self.disable, self.discard):
            actions.addWidget(button)
        layout.addLayout(actions)
        self.options = QComboBox()
        self.options.setAccessibleName('Compared FM arrangement')
        layout.addWidget(self.options)
        self.summary = QTableWidget(0, 5)
        self.summary.setHorizontalHeaderLabels(['Arrangement', 'Unresolved', 'Late', 'Peak lift s / 5 min', 'Lift wait (s)'])
        self.summary.setEditTriggers(QTableWidget.NoEditTriggers)
        self.summary.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for column in range(1, 5):
            self.summary.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeToContents)
        self.summary.setMaximumHeight(160)
        self.summary.setMinimumHeight(95)
        self.summary.hide()
        self.options.hide()
        layout.addWidget(self.summary)
        self.status = QLabel('Open the day schedule to load demand.')
        self.status.setWordWrap(True)
        self.status.setAccessibleName('Schedule status')
        layout.addWidget(self.status)
        self.day.currentIndexChanged.connect(self.render)
        self.mode.currentIndexChanged.connect(self.render)
        self.show_disabled.toggled.connect(self.render)
        self.zoom.valueChanged.connect(self.zoom_changed)
        self.fit.clicked.connect(lambda: self.zoom.setValue(100))
        self.preview_button.clicked.connect(self.open_trip_preview)
        self.save_notes.clicked.connect(self.store_category_notes)
        self.canvas.selected.connect(self.select)
        self.canvas.edited.connect(self.edit_item)
        self.canvas.moved.connect(self.move_items)
        self.canvas.selection_set_changed.connect(self.show_selection_count)
        self.canvas.cancelled.connect(lambda: self.status.setText('Drag cancelled. The schedule is unchanged.'))
        self.selector.currentIndexChanged.connect(self.selection_changed)
        self.exact_button.clicked.connect(self.set_exact)
        self.start.returnPressed.connect(self.set_exact)
        self.end.returnPressed.connect(self.set_exact)
        self.edit_settings.clicked.connect(self.open_settings)
        self.suggest.clicked.connect(lambda: self.calculate(True))
        self.compare.clicked.connect(lambda: self.calculate(False))
        self.use.clicked.connect(self.use_arrangement)
        self.disable.clicked.connect(self.disable_plan)
        self.discard.clicked.connect(self.discard_plan)
        self.options.currentIndexChanged.connect(self.option_changed)
        self.buttons()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.canvas.fit_width = max(620, self.scroll.viewport().width())
        self.canvas.update_size()
        self.ruler.setGeometry(0, 0, self.scroll.viewport().width(), self.canvas.TOP)
        self.ruler.raise_()

    def eventFilter(self, watched, event):
        if watched is self.scroll.viewport() and event.type() == QEvent.Resize:
            self.canvas.fit_width = max(620, self.scroll.viewport().width())
            self.canvas.update_size()
            self.ruler.setGeometry(0, 0, self.scroll.viewport().width(), self.canvas.TOP)
            self.ruler.raise_()
        return super().eventFilter(watched, event)

    def zoom_changed(self, value):
        self.canvas.zoom = value / 100
        self.canvas.update_size()

    def refresh(self):
        try:
            generation = deepcopy(self.generation_provider())
        except Exception as exc:
            self.status.setText(str(exc))
            return False
        if generation != self.generation or not self._loaded:
            self.generation = generation
            self.plan = deepcopy(generation.get('fm_logistics', {'enabled': False, 'categories': {}}))
            self._loaded = True
            self.dirty = False
            self.invalidate()
            self.status.setText('Schedules loaded. Select a bar or marker to move it or edit its exact times.')
        self.render()
        problems = invalid_slots(self.generation) if self.plan.get('enabled') else []
        if problems:
            self.status.setText('Demand timings changed: regenerate or disable the FM plan before saving.')
        elif not self.project_provider:
            self.status.setText('Demand editing is available. Open from the project to calculate FM arrangements.')
        self.buttons()
        return True

    def current_project(self):
        if not self.project_provider:
            raise ValueError('FM suggestions need a full project configuration.')
        result = deepcopy(self.project_provider())
        result['departments'] = deepcopy(self.departments)
        result['task_generation'] = deepcopy(self.generation)
        result['task_generation']['fm_logistics'] = deepcopy(self.plan)
        return result

    def signature(self):
        project = deepcopy(self.project_provider()) if self.project_provider else {}
        project['task_generation'] = deepcopy(self.generation_provider())
        return json.dumps([project, self.plan, self.departments], sort_keys=True, default=str)

    def invalidate(self):
        self.comparison = None
        self.compared_signature = None
        self.summary.hide()
        self.options.hide()
        self.buttons()
        self.preview_changed.emit()

    def render(self, *_):
        if self._refreshing:
            return
        previous = self.canvas.selection
        self.items = {}
        self.rule_by_id = {}
        rows_by_category = {}
        fm = self.mode.currentData() == 'fm'
        self.hint.setText(('FM plan: original demand is outlined; filled windows and markers edit dispatch timing. '
                           if fm else 'Demand: drag to move; pull either end to resize. ')
                          + 'Five-minute steps; exact times below. Edits affect every active day. '
                          + ('Automatic generation is disabled. ' if not self.generation.get('enabled', True) else '')
                          + 'Ctrl-click selects several bars; Shift-click selects a range. '
                          + 'Linked midnight pieces belong to the same service window.')
        day = self.day.currentData()
        for rule in rules(self.generation, self.departments):
            self.rule_by_id[rule.identity] = rule
            cfg = rule.settings
            if not cfg.get('enabled', False) and not self.show_disabled.isChecked():
                rows_by_category.setdefault(rule.category, [])
                continue
            days = cfg.get('days_active', []) or list(DAYS)
            if day not in days:
                continue
            label = rule.label
            if not cfg.get('enabled', False):
                label += ' (disabled)'
            recurrence = 'Every other week' if cfg.get('run_every_fortnight') else 'Every active week'
            members = ', '.join(rule.members)
            description = f"{rule.category.title()} · {rule.label} · {members or 'Site-wide'} · {', '.join(days)} · {recurrence}"
            if cfg.get('notes'):
                description += ' · Notes: ' + str(cfg['notes'])
            category_cfg = self.generation.get('categories',{}).get(rule.category,{})
            if rule.identity[0]=='group':
                scope = next((group.get('payload',{}) for group in category_cfg.get('department_groups',[])
                              if group.get('id')==rule.identity[2]),{})
            elif rule.identity[0]=='department':
                scope = category_cfg.get('departments',{}).get(rule.identity[2],{})
            else:scope={}
            row = {'label': label, 'items': [], 'rule': rule.identity,
                   'notes': str(scope.get('notes','') or '')}
            try:
                times = rule_times(rule)
                for token, start, duration in times:
                    identity = ('native', *rule.identity, token)
                    item = dict(id=identity, rule=rule.identity, token=token, start=start,
                                duration=duration, editable=self.native_editable and not fm and not self.job,
                                enabled=cfg.get('enabled', False), outline=fm, description=description,
                                label=f'{rule.category.title()} · {label} · {clock(start)}')
                    self.items[identity] = item
                    row['items'].append(item)
                if not times:
                    row['message'] = rule.message or 'No scheduled times. Open settings to add a schedule.'
            except ValueError as exc:
                row['message'] = f'{exc} Open settings to correct this schedule.'
            # Readable alternative for empty/runtime-dependent rows, too.
            if not row['items']:
                identity = ('rule', *rule.identity)
                self.items[identity] = dict(id=identity, rule=rule.identity, start=0, duration=0,
                    editable=False, description=description + ' · ' + row['message'], label=f'{rule.category.title()} · {label}')
            rows_by_category.setdefault(rule.category, []).extend(self.pack(row))
        if fm:
            for category, policy in self.plan.get('categories', {}).items():
                cohorts = {group['id']: group.get('departments', []) for group in policy.get('cohorts', [])}
                for slot, window in policy.get('slots', {}).items():
                    matching = [rule for rule in self.rule_by_id.values() if rule.category == category
                                and day in (rule.settings.get('days_active', []) or DAYS)
                                and self.matches_slot(rule, slot)]
                    if not matching:
                        continue
                    try:
                        first = minutes(window['earliest'])
                        duration = span(first, minutes(window['deadline']))
                        identity = ('fm', category, slot, None)
                        description = f'{category.title()} · FM dispatch window · native slot {slot}'
                        item = dict(id=identity, start=first, duration=duration,
                                    editable=not self.job, enabled=self.plan.get('enabled', False),
                                    description=description, label=description)
                        self.items[identity] = item
                        rows_by_category.setdefault(category, []).append({'label': f'FM window · {slot}', 'items': [item]})
                        for cohort, offset in window.get('offsets', {}).items():
                            members = cohorts.get(cohort, [])
                            if not members or not any(set(members).intersection(rule.members) for rule in matching):
                                continue
                            identity = ('fm', category, slot, cohort)
                            description = f"{category.title()} · {cohort} · {', '.join(members)} · slot {slot}"
                            item = dict(id=identity, start=(first + offset / 60) % 1440, duration=0,
                                        editable=not self.job, enabled=self.plan.get('enabled', False),
                                        description=description, label=description)
                            self.items[identity] = item
                            rows_by_category[category].append({'label': f'  {cohort}', 'items': [item]})
                    except (ValueError, KeyError, TypeError):
                        rows_by_category.setdefault(category, []).append({'label': f'FM · {slot}',
                                                                         'message': 'Invalid FM window. Regenerate the arrangement.'})
        rows = []
        for category, category_rows in rows_by_category.items():
            category_label = self.generation.get('categories', {}).get(category, {}).get('display_name') or category.replace('_', ' ').title()
            rows.append({'label': category_label, 'header': True,
                         'notes': str(self.generation.get('categories',{}).get(category,{}).get('notes','') or ''),
                         'message': '' if category_rows else 'No enabled schedules. Select Show disabled to inspect existing settings.'})
            rows.extend(category_rows)
        if not rows:
            rows = [{'label': 'No demand', 'message': 'No schedules on this weekday. Choose another day or add a schedule in Parameters.'}]
        self.canvas.set_rows(rows)
        self.canvas.selections.intersection_update(self.items)
        self.selector.blockSignals(True)
        self.selector.clear()
        for identity, item in self.items.items():
            self.selector.addItem(item['label'], identity)
        selected = self.selection_index(previous)
        self.selector.setCurrentIndex(selected if selected >= 0 else 0)
        self.selector.blockSignals(False)
        self.selection_changed()
        self.buttons()

    def pack(self, row):
        """Put nearby release markers on separate lanes so labels remain readable."""
        if not row.get('items'):
            return [row]
        lanes = []
        for item in sorted(row['items'], key=lambda value: value['start']):
            ranges = [(left, max(right, left + 115 / self.canvas.zoom))
                      for left, right in segments(item['start'], item['duration'] or 1)]
            lane = next((lane for lane in lanes if all(b <= c or d <= a for a, b in ranges
                                                       for c, d in lane['ranges'])), None)
            if lane is None:
                lane = {'label': row['label'] if not lanes else '  ' + row['label'], 'items': [], 'ranges': [],
                        'notes': row.get('notes','') if not lanes else ''}
                lanes.append(lane)
            lane['items'].append(item)
            lane['ranges'].extend(ranges)
        return lanes

    @staticmethod
    def matches_slot(rule, slot):
        if rule.category == 'waste' and rule.message:
            return True  # Stream timing is resolved by the existing FM preview.
        try:
            return any((slot == 'timeframe' or slot == f"timeframe/{rule.settings.get('timeframe_start')}/{rule.settings.get('timeframe_end')}")
                       if token == 'window' else slot == clock(start)
                       for token, start, duration in rule_times(rule))
        except ValueError:
            return False

    def select(self, identity):
        if identity is None:
            self.selector.setCurrentIndex(-1)
            return
        index = self.selection_index(identity)
        if index >= 0:
            self.selector.setCurrentIndex(index)

    def selection_index(self, identity):
        # QVariant equality does not compare Python tuple values reliably.
        return next((index for index in range(self.selector.count())
                     if self.selector.itemData(index) == identity), -1)

    def selection_changed(self, *_):
        identity = self.selector.currentData()
        item = self.items.get(identity)
        self.canvas.selection = identity
        if identity is not None and identity not in self.canvas.selections:
            self.canvas.selections = {identity}
        self.show_selection_count(self.canvas.selections)
        self.canvas.update()
        self.start.setText(clock(item['start']) if item else '')
        self.end.setText(clock(item['start'] + item['duration'], end=True) if item and item['duration'] else '')
        self.details.setText(item['description'] if item else 'Select a bar or marker to inspect its schedule.')
        editable = bool(item and item.get('editable') and not self.job)
        self.start.setEnabled(editable)
        self.end.setEnabled(editable and bool(item['duration']))
        self.exact_button.setEnabled(editable)
        self.edit_settings.setEnabled(bool(item and item.get('rule') and self.open_rule and not self.job))
        category = self.selected_category()
        self.category_notes.setPlainText(str(self.generation.get('categories', {}).get(category, {}).get('notes', '') or ''))
        self.category_notes.setEnabled(bool(category) and self.native_editable and not self.job)
        self.save_notes.setEnabled(self.category_notes.isEnabled())

    def selected_category(self):
        item = self.items.get(self.selector.currentData(), {})
        return item['rule'][1] if item.get('rule') else item['id'][1] if item.get('id', ('',))[0]=='fm' else None

    def store_category_notes(self):
        category = self.selected_category()
        if not category or not self.native_editable:
            return
        updated = edit_category_notes(self.generation, category, self.category_notes.toPlainText())
        self.apply_generation(updated)
        self.generation = deepcopy(updated)
        self.invalidate()
        self.render()
        self.status.setText('Category notes added to this draft. Save the demand generator to keep them.')

    def trip_configuration(self):
        if not self.refresh():
            raise ValueError(self.status.text())
        config = self.current_project()
        if self.mode.currentData() == 'demand':
            config['task_generation'].pop('fm_logistics', None)
        return config

    def open_trip_preview(self):
        if not self.project_provider:
            return
        from visualiser.day_trip_preview import DayTripPreviewDialog
        preview = getattr(self, '_trip_preview', None)
        if preview is None:
            try:
                preview = DayTripPreviewDialog(self.trip_configuration,
                    lambda: 'FM plan' if self.mode.currentData()=='fm' else 'Demand',
                    self.day.currentIndex(), self.focus_preview_category, self)
            except Exception as exc:
                self.status.setText('Unable to open the demand preview: '+str(exc))
                return
            self._trip_preview = preview
            self.preview_changed.connect(preview.source_changed)
            self.mode.currentIndexChanged.connect(preview.source_changed)
        preview.show()
        preview.raise_()
        preview.activateWindow()
        preview.refresh_preview()

    def focus_preview_category(self, category):
        item = None
        if self.mode.currentData()=='fm':
            item = next((item for item in self.items.values() if item['id'][0]=='fm'
                         and item['id'][1]==category and item['id'][3] is None),None)
        if item is None:
            item = next((item for item in self.items.values() if item.get('rule') and item['rule'][1]==category), None)
        if item:
            self.select(item['id'])
            index = next((index for index,row in enumerate(self.canvas.rows)
                          if any(value['id']==item['id'] for value in row.get('items',[]))),None)
            if index is not None:
                top,height = self.canvas.row_geometry(index)
                self.scroll.ensureVisible(int(self.canvas.x(item['start'])),
                    top+height//2,50,self.canvas.ROW+self.canvas.TOP)
            self.window().raise_()
            self.window().activateWindow()

    def show_selection_count(self, selected):
        self.selection_count.setText(f'{len(selected)} selected' if len(selected)>1 else '')

    def move_items(self, selected, delta):
        selected = [identity for identity in selected if identity in self.items and self.items[identity].get('editable')]
        if not selected or self.job:
            return
        try:
            if all(identity[0]=='native' for identity in selected):
                updated = move_demand_selection(self.generation,
                    [(self.items[identity]['rule'],self.items[identity]['token']) for identity in selected],delta)
                self.apply_generation(updated)
                self.generation = deepcopy(updated)
                remapped = {('native',*self.items[identity]['rule'],
                    'window' if self.items[identity]['token']=='window' else clock(self.items[identity]['start']+delta))
                    for identity in selected}
                primary = self.canvas.selection
                self.canvas.selection = (('native',*self.items[primary]['rule'],
                    'window' if self.items[primary]['token']=='window' else clock(self.items[primary]['start']+delta))
                    if primary in selected else next(iter(remapped)))
                self.canvas.selections = remapped
            elif all(identity[0]=='fm' for identity in selected):
                self.plan = move_fm_selection(self.plan,[identity[1:] for identity in selected],delta)
                self.dirty = True
            else:
                raise ValueError('Select bars from one editing mode before moving them together.')
            self.invalidate()
            self.status.setText(f'{len(selected)} selected bars moved together. The move applies on every active day.')
        except (ValueError,KeyError) as exc:
            self.status.setText(str(exc))
        self.render()

    def open_settings(self):
        item = self.items.get(self.selector.currentData())
        if item and item.get('rule') and self.open_rule:
            self.open_rule(item['rule'])

    def set_exact(self):
        item = self.items.get(self.selector.currentData())
        if not item or not item.get('editable'):
            return
        try:
            start = minutes(self.start.text())
            duration = span(start, minutes(self.end.text(), end=True)) if item['duration'] else 0
            self.edit_item(item['id'], start, duration)
        except ValueError as exc:
            self.status.setText(str(exc))

    def edit_item(self, identity, start, duration):
        item = self.items.get(identity)
        if not item or not item.get('editable') or self.job:
            return
        try:
            if identity[0] == 'native':
                updated = edit_demand(self.generation, item['rule'], item['token'], start, duration)
                self.apply_generation(updated)
                self.generation = deepcopy(updated)
                self.plan = deepcopy(updated.get('fm_logistics', self.plan))
                if item['token'] != 'window':
                    self.canvas.selection = ('native', *item['rule'], clock(start))
                self.status.setText('Demand timing changed on every active day. FM comparisons need recalculation.')
            else:
                _, category, slot, cohort = identity
                self.plan = edit_fm(self.plan, category, slot, cohort, start, duration)
                self.dirty = True
                self.status.setText('FM draft changed. Compare arrangements again, then use the arrangement to keep it.')
            self.invalidate()
        except (ValueError, KeyError) as exc:
            self.status.setText(str(exc))
        self.render()

    def buttons(self):
        busy = bool(self.job)
        self.suggest.setEnabled(bool(self.project_provider) and not busy)
        self.compare.setEnabled(bool(self.project_provider) and not busy)
        self.use.setEnabled(bool(self.comparison) and not busy)
        self.disable.setEnabled(bool(self.plan.get('enabled') or self.generation.get('fm_logistics', {}).get('enabled')) and not busy)
        self.discard.setEnabled(self.dirty and not busy)
        self.mode.setEnabled(not busy)
        self.options.setEnabled(not busy)
        self.canvas.setEnabled(not busy)
        self.preview_button.setEnabled(bool(self.project_provider))

    def work(self, title, operation, completed):
        if self.job:
            return
        try:
            signature = self.signature()
        except Exception as exc:
            self.status.setText(str(exc))
            return
        self.status.setText(title)
        self.job_context = (signature, completed)
        self.job = ScheduleJob(operation)
        self.job.signals.finished.connect(self.finish_job, Qt.QueuedConnection)
        QThreadPool.globalInstance().start(self.job)
        self.render()

    @Slot(object, str)
    def finish_job(self, result, error):
        signature, completed = self.job_context
        self.job = None
        self.job_context = None
        try:
            if error:
                self.status.setText(error)
            elif signature != self.signature():
                self.invalidate()
                self.status.setText('Inputs changed during calculation. Reload the day schedule and calculate again.')
            else:
                completed(result)
        except Exception as exc:
            self.status.setText(str(exc))
        self.render()

    def calculate(self, suggest):
        if not self.refresh():
            return
        try:
            config = self.current_project()
        except Exception as exc:
            self.status.setText(str(exc))
            return

        def accept(result):
            self.baseline = result['baseline']
            self.comparison = result['comparison']
            self.options.blockSignals(True)
            self.options.clear()
            for option in self.comparison['results']:
                self.options.addItem(option['label'], option['strategy'])
            self.options.setCurrentIndex(self.options.findData(result['selected']))
            self.options.blockSignals(False)
            self.show_summary()
            self.option_changed()
            runtime = sorted({row['category'] for row in self.comparison.get('runtime', [])})
            self.status.setText('Review the arrangement, then choose Use arrangement. '
                                + ('Current timings retained: no improvement was found. ' if result['selected'] == 'current' else '')
                                + ('Runtime-dependent demand: ' + ', '.join(runtime) + '. ' if runtime else '')
                                + 'Lift estimates use the existing FM forecast; fleet and staff queues are measured in normal runs.')

        self.work('Suggesting and comparing arrangements…' if suggest else 'Comparing arrangements…',
                  lambda: arrangement(config, suggest=suggest), accept)

    def show_summary(self):
        results = self.comparison['results']
        self.summary.setRowCount(len(results))
        for i, option in enumerate(results):
            values = [option['label']] + [round(option['totals'].get(key, 0), 1)
                         for key in ('unresolved', 'late', 'peak_lift_seconds', 'lift_wait_seconds')]
            for j, value in enumerate(values):
                self.summary.setItem(i, j, QTableWidgetItem(str(value)))
        self.options.show()
        self.summary.show()

    def option_changed(self, *_):
        if not self.comparison:
            return
        option = next((row for row in self.comparison['results'] if row['strategy'] == self.options.currentData()), None)
        if not option:
            return
        self.plan = deepcopy(option['settings'])
        self.plan['enabled'] = option['strategy'] != 'current'
        self.compared_signature = self.signature()
        self.dirty = True
        self.mode.setCurrentIndex(self.mode.findData('fm'))
        self.render()
        self.preview_changed.emit()

    def use_arrangement(self):
        if not self.comparison:
            return
        try:
            if self.compared_signature != self.signature():
                self.invalidate()
                raise ValueError('Inputs changed. Compare arrangements again before using this plan.')
            config, plan, baseline = self.current_project(), deepcopy(self.plan), deepcopy(self.baseline)
        except Exception as exc:
            self.status.setText(str(exc))
            return

        def accept(generation):
            self.apply_generation(generation)
            self.generation = deepcopy(generation)
            self.dirty = False
            self.compared_signature = self.signature()
            self.status.setText(self.applied_text)

        self.work('Checking the arrangement against actual demand and calendars…',
                  lambda: validated_generation(config, plan, baseline), accept)

    def disable_plan(self):
        updated = deepcopy(self.generation)
        plan = deepcopy(self.plan)
        plan['enabled'] = False
        updated['fm_logistics'] = plan
        self.apply_generation(updated)
        self.generation, self.plan = updated, plan
        self.dirty = False
        self.invalidate()
        self.status.setText('FM plan disabled. Original demand timings will be used.')
        self.render()

    def discard_plan(self):
        self.plan = deepcopy(self.generation.get('fm_logistics', {'enabled': False, 'categories': {}}))
        self.dirty = False
        self.invalidate()
        self.status.setText('Unaccepted FM draft discarded. The saved arrangement is unchanged.')
        self.render()
