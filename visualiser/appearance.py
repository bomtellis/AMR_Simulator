"""Per-user presentation preferences; never part of a project's frozen inputs."""
from dataclasses import asdict, dataclass
import json
import re

from PySide6.QtCore import QObject, QSettings, Signal
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication


PRESETS = {
    'Light': dict(window='#f3f4f6', base='#ffffff', alternate='#e9edf2',
                  button='#e9edf2', text='#17212b', accent='#005ea8', mid='#6b7280'),
    'Dark': dict(window='#20252b', base='#151a20', alternate='#2c333c',
                 button='#2c333c', text='#f2f5f8', accent='#80c7ff', mid='#8995a3'),
    'High contrast': dict(window='#000000', base='#000000', alternate='#000000',
                          button='#000000', text='#ffffff', accent='#ffff00', mid='#ffffff'),
}
SETTINGS_KEY = 'appearance/v1'


@dataclass(frozen=True)
class Appearance:
    theme: str = 'Light'
    font_size: int = 10
    map_font_size: int = 12
    text_colour: str = ''
    accent_colour: str = ''
    map_text_colour: str = '#ffffff'
    show_legend: bool = True


def contrast(first, second):
    """sRGB relative-luminance ratio (black/white = 21; identical = 1)."""
    def luminance(colour):
        channels = [int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in channels]
        return sum(c * weight for c, weight in zip(linear, (.2126, .7152, .0722)))
    a, b = sorted((luminance(first), luminance(second)))
    return (b + .05) / (a + .05)


def colours(value):
    result = dict(PRESETS[value.theme])
    result['text'] = value.text_colour or result['text']
    result['accent'] = value.accent_colour or result['accent']
    result['selected_text'] = max(('#000000', '#ffffff'), key=lambda c: contrast(c, result['accent']))
    return result


def validate(value):
    if value.theme not in PRESETS:
        raise ValueError('Choose a known theme.')
    for label, size, lower, upper in [('Interface', value.font_size, 8, 24), ('Map', value.map_font_size, 10, 28)]:
        if type(size) is not int or not lower <= size <= upper:
            raise ValueError(f'{label} text size must be a whole number from {lower} to {upper}.')
    if type(value.show_legend) is not bool:
        raise ValueError('Show map legend must be true or false.')
    for label, colour, optional in [('Interface text', value.text_colour, True),
                                     ('Accent', value.accent_colour, True), ('Map text', value.map_text_colour, False)]:
        if optional and colour == '':
            continue
        if not isinstance(colour, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', colour):
            raise ValueError(f'{label} colour must use #RRGGBB notation.')
    palette = colours(value)
    backgrounds = [palette[k] for k in ('window', 'base', 'alternate', 'button')]
    if min(contrast(palette['text'], b) for b in backgrounds) < 4.5:
        raise ValueError('Interface text needs at least 4.5:1 contrast against every theme background.')
    if min(contrast(palette['accent'], b) for b in backgrounds) < 3:
        raise ValueError('Accent needs at least 3:1 contrast against every theme background.')
    if min(contrast(value.map_text_colour, b) for b in ('#111111', '#151515')) < 4.5:
        raise ValueError('Map text needs at least 4.5:1 contrast against the dark map and legend.')
    return value


class AppearanceController(QObject):
    changed = Signal(object)

    def __init__(self, app, settings=None):
        super().__init__(app)
        self.app = app
        self.settings = settings  # None is deliberately in-memory, useful for tests/embedders.
        self.load_warning = ''
        self.value = Appearance()
        if settings is not None:
            raw = settings.value(SETTINGS_KEY, '')
            if raw:
                try:
                    self.value = validate(Appearance(**json.loads(raw)))
                except (ValueError, TypeError):
                    self.load_warning = 'Saved appearance settings could not be read. Defaults are in use; Apply replaces the saved settings.'
        self._display(self.value)

    def _display(self, value):
        # Qt's application stylesheet caches palette/font values. Reinstall it
        # after changing the defaults so existing controls are repolished too.
        stylesheet = self.app.styleSheet()
        stylesheet = re.sub(r'/\* AMR_APPEARANCE_FONT \*/.*?/\* END_AMR_APPEARANCE_FONT \*/', '', stylesheet, flags=re.S).strip()
        if stylesheet:
            self.app.setStyleSheet('')
        if self.app.style().objectName().lower() != 'fusion':
            self.app.setStyle('Fusion')
        c = colours(value)
        palette = QPalette()
        roles = {'Window': 'window', 'Base': 'base', 'AlternateBase': 'alternate', 'Button': 'button',
                 'WindowText': 'text', 'Text': 'text', 'ButtonText': 'text', 'ToolTipBase': 'base',
                 'PlaceholderText': 'text', 'BrightText': 'text',
                 'ToolTipText': 'text', 'Highlight': 'accent', 'HighlightedText': 'selected_text',
                 'Link': 'accent', 'LinkVisited': 'accent', 'Mid': 'mid', 'Light': 'mid', 'Dark': 'mid'}
        for role, key in roles.items():
            palette.setColor(getattr(QPalette.ColorRole, role), QColor(c[key]))
        self.app.setPalette(palette)
        font = QFont(self.app.font())
        font.setPointSize(value.font_size)
        self.app.setFont(font)
        # Include the size in the stylesheet as well: hidden tab bars can retain
        # old drawing metrics after QApplication.setFont alone.
        self.app.setStyleSheet(stylesheet + f'\n/* AMR_APPEARANCE_FONT */\nQWidget {{ font-size: {value.font_size}pt; }}\n/* END_AMR_APPEARANCE_FONT */')

    def apply(self, value):
        validate(value)
        if self.settings is not None:
            old = self.settings.value(SETTINGS_KEY, None)
            self.settings.setValue(SETTINGS_KEY, json.dumps(asdict(value)))
            self.settings.sync()
            if self.settings.status() != QSettings.NoError:
                if old is None:
                    self.settings.remove(SETTINGS_KEY)
                else:
                    self.settings.setValue(SETTINGS_KEY, old)
                self.settings.sync()
                raise OSError('Appearance settings could not be saved. Check access to your user settings folder.')
        self.value = value
        self.load_warning = ''
        self._display(value)
        self.changed.emit(value)


def controller(app=None, *, settings=None):
    app = app or QApplication.instance()
    if not hasattr(app, '_amr_appearance'):
        app._amr_appearance = AppearanceController(app, settings)
    return app._amr_appearance


def user_settings():
    return QSettings(QSettings.IniFormat, QSettings.UserScope, 'AMR Engineering', 'Desktop')
