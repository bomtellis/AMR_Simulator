"""Searchable permission inspection and per-user profile styles."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QLineEdit, QPushButton, QColorDialog, QTableWidget, QTableWidgetItem, QHeaderView, QFormLayout)
from route_display import PATTERNS, SCOPE, ALL, populate_choices, validate_style


class RouteDisplayPanel(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        root = QVBoxLayout(self)
        title = QLabel('Route identification')
        title.setProperty('sectionHeading', True)
        root.addWidget(title)
        note = QLabel(SCOPE + ' Clean/dirty/shared access is defined entirely by route profiles. '
                      'Auto-connections are included and labelled; direct-travel fallbacks are not graph sections. '
                      'Lift allowances are listed below; the map shows same-floor sections.')
        note.setWordWrap(True)
        root.addWidget(note)
        self.profile = QComboBox()
        self.profile.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.profile.setMinimumContentsLength(20)
        self.profile.setAccessibleName('Profile to inspect and display')
        self.profile.currentIndexChanged.connect(self.inspect)
        root.addWidget(self.profile)
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        root.addLayout(form)
        self.colour = QLineEdit()
        self.colour.setPlaceholderText('#RRGGBB')
        self.colour.setAccessibleName('Route label and line colour')
        self.pattern = QComboBox()
        self.pattern.addItems(PATTERNS)
        self.pattern.setAccessibleName('Route line pattern')
        choose = QPushButton('Choose colour…')
        self.choose_button = choose
        choose.clicked.connect(self.choose)
        self.save = QPushButton('Save style')
        self.save.clicked.connect(self.save_style)
        self.reset = QPushButton('Default style')
        self.reset.clicked.connect(lambda: self.save_style(reset=True))
        colour_row = QHBoxLayout()
        colour_row.addWidget(self.colour)
        colour_row.addWidget(choose)
        form.addRow('Colour', colour_row)
        form.addRow('Line pattern', self.pattern)
        actions = QHBoxLayout()
        actions.addWidget(self.save)
        actions.addWidget(self.reset)
        root.addLayout(actions)
        self.status = QLabel(editor.route_styles.warning or 'Styles are saved per user; project permissions stay unchanged.')
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        self.lifts = QLabel()
        self.lifts.setWordWrap(True)
        root.addWidget(self.lifts)
        self.search = QLineEdit()
        self.search.setPlaceholderText('Filter by node, profile, direction or source…')
        self.search.setAccessibleName('Filter profile access records')
        self.search.textChanged.connect(self.filter)
        root.addWidget(self.search)
        self.table = QTableWidget(0, 4)
        self.table.setMinimumHeight(220)
        self.table.setHorizontalHeaderLabels(['Floor', 'Section', 'Permitted profile directions', 'Source'])
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setWordWrap(True)
        root.addWidget(self.table, 1)
        self.count = QLabel()
        self.count.setWordWrap(True)
        root.addWidget(self.count)
        show = QPushButton('Show selected profile in Layout')
        show.clicked.connect(self.show_map)
        root.addWidget(show)
        self.refresh()

    def refresh(self):
        populate_choices(self.profile, self.editor.store.data)
        self.inspect()

    def inspect(self):
        selected = self.profile.currentData()
        enabled = isinstance(selected, str)
        for widget in (self.colour, self.pattern, self.save, self.reset, self.choose_button):
            widget.setEnabled(enabled)
        style = self.editor.route_styles.get(selected) if enabled else {'colour': '', 'pattern': 'Solid'}
        self.colour.setText(style['colour'])
        self.pattern.setCurrentText(style['pattern'])
        self.table.setRowCount(0)
        try:
            _points, sections, rules = self.editor.route_access_model()
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            self.lifts.setText('Preview unavailable: ' + str(exc))
            self.count.setText('Run Project checks to resolve invalid inputs.')
            return
        names = sorted(rules) if selected in (None, ALL) else [selected]
        lift_names = {lift['id'] for lift in self.editor.store.data.get('lifts', [])}
        text = []
        for name in names:
            allowed = rules[name]['allowed_lifts']
            existing = lift_names if not allowed else allowed & lift_names
            missing = allowed - lift_names
            text.append(f'{name}: ' + (', '.join(sorted(existing)) or 'no configured lifts') +
                        (' (unrestricted)' if not allowed else '') +
                        (f"; unknown: {', '.join(sorted(missing))}" if missing else ''))
        self.lifts.setText('Lift allowances — ' + (' | '.join(text) or 'no profiles configured'))
        for section in sections:
            members = [(name, pairs) for name, pairs in sorted(section['profiles'].items()) if name in names]
            if selected not in (None, ALL) and not members:
                continue
            description = '; '.join(f"{name}: " + ', '.join(f'{a} → {b}' for a, b in sorted(pairs)) for name, pairs in members)
            row = self.table.rowCount()
            self.table.insertRow(row)
            source = ('Explicit + auto-connected' if section['auto_directions'] - section['explicit_directions'] and section['explicit_directions']
                      else 'Auto-connected' if section['implicit'] else 'Explicit')
            auto = section['auto_directions'] - section['explicit_directions']
            if auto:
                description += ' | Auto: ' + ', '.join(f'{a} → {b}' for a, b in sorted(auto))
            values = [str(section['floor']), f"{section['a']} — {section['b']}", description or 'No permitted profile', source]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                self.table.setItem(row, column, item)
        self.table.resizeRowsToContents()
        self.filter()

    def filter(self):
        query = self.search.text().casefold()
        shown = 0
        for row in range(self.table.rowCount()):
            match = query in ' '.join(self.table.item(row, col).text() for col in range(4)).casefold()
            self.table.setRowHidden(row, not match)
            shown += bool(match)
        self.count.setText(f'{shown} / {self.table.rowCount()} sections shown. No rows means no matching graph access, not proof of no possible journey.')

    def choose(self):
        if not isinstance(self.profile.currentData(), str):
            return
        colour = QColorDialog.getColor(QColor(self.colour.text()), self, 'Route label and line colour')
        if colour.isValid():
            self.colour.setText(colour.name())

    def save_style(self, _checked=False, *, reset=False):
        try:
            style = None if reset else validate_style(dict(colour=self.colour.text().strip(), pattern=self.pattern.currentText()))
            self.editor.route_styles.save(self.profile.currentData(), style)
        except (ValueError, TypeError, OSError) as exc:
            self.status.setText(str(exc))
            return False
        self.status.setText('Route style saved for this user. Profile permissions are unchanged.')
        self.inspect()
        return True

    def show_map(self):
        combo = self.editor.route_display_combo
        populate_choices(combo, self.editor.store.data)
        combo.setCurrentIndex(max(0, combo.findData(self.profile.currentData())))
        self.editor.workspace.activate('layout')
        self.editor.fit_view()
