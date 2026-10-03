"""Independent scale/grid references, theme readability and preference isolation."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from tests import test_corridor_editing as editing
from PySide6.QtCore import QCoreApplication, QEvent, QSettings
from appearance import Appearance, AppearanceController, SETTINGS_KEY, contrast, validate, with_theme
from cad_map_style import adaptive_grid, scale_bar, map_colours, ContrastRouteStyles
from route_display import ProfileLabel, ALL


class CadMapArithmeticTests(unittest.TestCase):
    def test_grid_is_world_aligned_at_known_scale_and_bounded_at_extremes(self):
        spacing, lines = adaptive_grid((-2, -2, 2, 2), 40)
        self.assertEqual(1, spacing)
        self.assertEqual(10, len(lines))
        self.assertEqual(2, sum(line[-1] for line in lines))
        for scale in (1e-12, 1, 1e12):
            _, lines = adaptive_grid((-1e6, -1e6, 1e6, 1e6), scale)
            self.assertLessEqual(len(lines), 180)
        self.assertEqual((0, []), adaptive_grid((0, 0, 10, 10), 0))
        self.assertEqual((0, []), adaptive_grid((0, 0, float('inf'), 10), 1))

    def test_scale_matches_pixels_and_never_claims_geographic_north(self):
        self.assertEqual((2, 100), scale_bar(50))
        self.assertEqual((5, 100), scale_bar(20))
        self.assertIsNone(scale_bar(0))
        self.assertIsNone(scale_bar(float('inf')))

    def test_theme_map_text_and_marker_contrast(self):
        for theme in ('Light', 'Dark', 'High contrast'):
            colours = map_colours(validate(Appearance(theme=theme)))
            for background in ('background', 'panel'):
                self.assertGreaterEqual(contrast(colours['text'], colours[background]), 4.5)
            for symbol in ('location', 'door', 'node', 'accent'):
                self.assertGreaterEqual(contrast(colours[symbol], colours['background']), 3)
        with self.assertRaises(ValueError):
            validate(Appearance(map_text_colour='#ffffff'))
        validate(Appearance(map_text_colour='#ffffff', map_background_colour='#111111'))


class CadMapUiTests(unittest.TestCase):
    setUpClass = classmethod(editing.CorridorEditingUiTests.setUpClass.__func__)

    def setUp(self):
        editing.CorridorEditingUiTests.setUp(self)
        self.original_appearance = self.editor.appearance.value

    def tearDown(self):
        self.editor.appearance.apply(self.original_appearance)
        editing.CorridorEditingUiTests.tearDown(self)

    def test_theme_grid_and_custom_route_rendering_never_edit_project(self):
        editor = self.editor
        before = deepcopy(editor.store.data)
        editor.validate_json()
        editor.route_display_combo.setCurrentIndex(editor.route_display_combo.findData(ALL))
        saved_styles = deepcopy(editor.route_styles.styles)
        for theme in ('Light', 'Dark', 'High contrast'):
            editor.appearance.apply(with_theme(editor.appearance.value, theme))
            background = editor._map_colours['background']
            self.assertEqual(background, editor.canvas.backgroundBrush().color().name())
            labels = [item for item in editor.scene.items() if isinstance(item, ProfileLabel)]
            self.assertTrue(labels)
            for item in labels:
                self.assertEqual(background, item.background)
                self.assertGreaterEqual(contrast(item.brush().color().name(), background), 4.5)
        snap = editor.snap_check.isChecked()
        editor.cad_toolbar.grid_action.trigger()
        self.assertEqual(snap, editor.snap_check.isChecked())
        self.assertEqual(editor.appearance.value.show_grid, editor.canvas._show_map_grid)
        editor.workbench.legend_action.trigger()
        self.assertEqual(editor.appearance.value.show_legend, editor.workbench.legend_action.isChecked())
        self.assertEqual(before, editor.store.data)
        self.assertEqual(saved_styles, editor.route_styles.styles)
        self.assertTrue(editor.checks_panel.current())
        self.assertFalse(editor.has_unsaved_changes())

    def test_legacy_preferences_migrate_in_memory_without_overwriting_file(self):
        settings = QSettings(str(Path(self.temp.name) / 'old.ini'), QSettings.IniFormat)
        for old_colour, expected_text, expected_background in (
                ('#ffffff', 'auto', ''), ('#ffff00', '#ffff00', '#111111')):
            raw = json.dumps({'theme': 'Light', 'map_text_colour': old_colour})
            settings.setValue(SETTINGS_KEY, raw)
            migrated = AppearanceController(self.app, settings)
            self.assertEqual(expected_text, migrated.value.map_text_colour)
            self.assertEqual(expected_background, migrated.value.map_background_colour)
            self.assertEqual(raw, settings.value(SETTINGS_KEY))
            self.assertTrue(migrated.load_warning)
            migrated.deleteLater()
        self.editor.appearance.apply(self.original_appearance)

    def test_route_colour_adapter_preserves_user_colour_and_pattern(self):
        class Styles:
            def get(self, _name):
                return {'colour': '#ffff00', 'pattern': 'Dotted'}
        styles = Styles()
        adapted = ContrastRouteStyles(styles, '#fbfdff').get('anything')
        self.assertGreaterEqual(contrast(adapted['colour'], '#fbfdff'), 4.5)
        self.assertEqual('Dotted', adapted['pattern'])
        self.assertEqual('#ffff00', styles.get('anything')['colour'])

    def test_changing_theme_after_closing_another_window_has_no_stale_callbacks(self):
        other = type(self.editor)()
        with patch.object(other, '_confirm_unsaved_changes', return_value=True):
            other.close()
        other.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        with patch('sys.excepthook') as errors:
            self.editor.appearance.apply(with_theme(self.editor.appearance.value, 'Dark'))
        errors.assert_not_called()


if __name__ == '__main__':
    unittest.main()
