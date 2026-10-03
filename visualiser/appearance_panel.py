"""Persistent, keyboard-accessible appearance form with an explicit apply step."""
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QComboBox, QSpinBox, QLineEdit, QPushButton, QColorDialog, QScrollArea, QCheckBox, QGridLayout)
from appearance import Appearance, PRESETS, colours, validate


class AppearancePanel(QWidget):
    def __init__(self, appearance, parent=None):
        super().__init__(parent)
        self.appearance = appearance
        root = QVBoxLayout(self)
        title = QLabel('Appearance')
        title.setProperty('sectionHeading', True)
        root.addWidget(title)
        intro = QLabel('Display preferences are saved for this Windows user, separately from projects and simulation results. '
                       'Choose a preset, adjust text, then Apply. Blank interface/background colours and auto map text use the preset.')
        intro.setWordWrap(True)
        root.addWidget(intro)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        root.addWidget(scroll, 1)
        content = QWidget()
        scroll.setWidget(content)
        layout = QVBoxLayout(content)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        layout.addLayout(form)
        self.theme = QComboBox()
        self.theme.addItems(PRESETS)
        form.addRow('&Theme', self.theme)
        self.font_size = QSpinBox()
        self.font_size.setRange(8, 24)
        self.font_size.setSuffix(' pt')
        form.addRow('&Interface text', self.font_size)
        self.map_font_size = QSpinBox()
        self.map_font_size.setRange(10, 28)
        self.map_font_size.setSuffix(' px')
        form.addRow('&Layout map text', self.map_font_size)
        self.colour_fields = {}
        for key, label in [('text_colour', 'Interface text colour'), ('accent_colour', 'Focus / selection colour'),
                           ('map_text_colour', 'Layout map text colour'), ('map_background_colour', 'Layout map background')]:
            row = QWidget()
            horizontal = QHBoxLayout(row)
            horizontal.setContentsMargins(0, 0, 0, 0)
            field = QLineEdit()
            field.setAccessibleName(label)
            field.setPlaceholderText('auto or #RRGGBB' if key == 'map_text_colour' else 'Preset colour')
            self.colour_fields[key] = field
            horizontal.addWidget(field, 1)
            button = QPushButton('Choose…')
            button.setAccessibleName('Choose ' + label.lower())
            button.clicked.connect(lambda _checked=False, k=key: self.choose_colour(k))
            horizontal.addWidget(button)
            form.addRow(label, row)
            field.textChanged.connect(self.preview)
        self.legend = QCheckBox('Show layout map legend')
        form.addRow(self.legend)
        self.grid = QCheckBox('Show adaptive metre grid')
        form.addRow(self.grid)
        self.sample = QLabel('Preview: project objects, labels and instructions')
        self.sample.setWordWrap(True)
        self.sample.setAutoFillBackground(True)
        self.sample.setMargin(12)
        layout.addWidget(self.sample)
        self.preview_status = QLabel()
        self.preview_status.setWordWrap(True)
        layout.addWidget(self.preview_status)
        scope = QLabel('Presets apply to standard application controls and dialogs. Layout labels and the legend have their own text size and colour. '
                       'Robot playback, timelines, drawing underlays and some legacy custom controls retain their existing rendering. '
                       'Contrast checks cover the theme backgrounds, not imported drawings. This is not a claim of complete accessibility compliance.')
        scope.setWordWrap(True)
        layout.addWidget(scope)
        layout.addStretch()
        self.status = QLabel(appearance.load_warning)
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        buttons = QGridLayout()
        self.defaults = QPushButton('Use &defaults')
        self.revert = QPushButton('&Revert draft')
        self.apply_button = QPushButton('&Apply appearance')
        self.apply_button.setProperty('primary', True)
        self.defaults.clicked.connect(lambda: self.populate(Appearance()))
        self.revert.clicked.connect(lambda: self.populate(self.appearance.value))
        self.apply_button.clicked.connect(self.apply)
        buttons.addWidget(self.apply_button, 0, 0, 1, 2)
        buttons.addWidget(self.defaults, 1, 0)
        buttons.addWidget(self.revert, 1, 1)
        root.addLayout(buttons)
        self.theme.currentTextChanged.connect(self.theme_changed)
        self.font_size.valueChanged.connect(self.preview)
        self.map_font_size.valueChanged.connect(self.preview)
        self.legend.toggled.connect(self.preview)
        self.grid.toggled.connect(self.preview)
        self.populate(appearance.value)

    def value(self):
        return Appearance(self.theme.currentText(), self.font_size.value(), self.map_font_size.value(),
                          **{key: field.text().strip() for key, field in self.colour_fields.items()},
                          show_legend=self.legend.isChecked(), show_grid=self.grid.isChecked())

    def populate(self, value):
        self.theme.blockSignals(True)
        self.theme.setCurrentText(value.theme)
        self.theme.blockSignals(False)
        self.font_size.setValue(value.font_size)
        self.map_font_size.setValue(value.map_font_size)
        for key, field in self.colour_fields.items():
            field.setText(getattr(value, key))
        self.legend.setChecked(value.show_legend)
        self.grid.setChecked(value.show_grid)
        self.preview()

    def theme_changed(self):
        # Choosing a preset intentionally restores its compatible text/accent pair.
        self.colour_fields['text_colour'].clear()
        self.colour_fields['accent_colour'].clear()
        self.colour_fields['map_text_colour'].setText('auto')
        self.colour_fields['map_background_colour'].clear()
        self.preview()

    def choose_colour(self, key):
        field = self.colour_fields[key]
        c = colours(Appearance(theme=self.theme.currentText()))
        from cad_map_style import map_colours
        map_palette = map_colours(Appearance(theme=self.theme.currentText()))
        fallback = (map_palette['text' if key == 'map_text_colour' else 'background']
                    if key.startswith('map_') else c['text' if key == 'text_colour' else 'accent'])
        initial = QColor(fallback if field.text() in ('', 'auto') else field.text())
        chosen = QColorDialog.getColor(initial, self, field.accessibleName())
        if chosen.isValid():
            field.setText(chosen.name())

    def preview(self):
        try:
            value = validate(self.value())
        except ValueError as exc:
            self.preview_status.setText(str(exc))
            self.apply_button.setEnabled(False)
            return
        c = colours(value)
        palette = QPalette(self.sample.palette())
        palette.setColor(QPalette.Window, QColor(c['window']))
        palette.setColor(QPalette.WindowText, QColor(c['text']))
        self.sample.setPalette(palette)
        font = self.sample.font()
        font.setPointSize(value.font_size)
        self.sample.setFont(font)
        self.sample.setStyleSheet(f'font-size: {value.font_size}pt; color: {c["text"]}; background: {c["window"]};')
        self.preview_status.setText('Text contrast ≥ 4.5:1; focus / selection contrast ≥ 3:1. Apply to save these preferences.')
        self.apply_button.setEnabled(True)

    def apply(self):
        try:
            self.appearance.apply(self.value())
        except (ValueError, OSError) as exc:
            self.status.setText(str(exc))
            return False
        self.preview()
        self.status.setText('Appearance saved. Project data and recorded results are unchanged.')
        return True
