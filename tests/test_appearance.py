"""Appearance acceptance: independent contrast, persistence and project isolation."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from tests import test_corridor_editing as editing
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QVBoxLayout
from appearance import (Appearance, AppearanceController, PRESETS, SETTINGS_KEY,
                        colours, contrast, validate)
from appearance_panel import AppearancePanel
from ui_theme import install_application_theme


class AppearanceValueTests(unittest.TestCase):
    def test_independent_contrast_reference_values(self):
        self.assertEqual(21, contrast('#000000', '#ffffff'))
        self.assertEqual(1, contrast('#55aaee', '#55aaee'))
        self.assertAlmostEqual(4.4781, contrast('#777777', '#ffffff'), places=4)
        self.assertGreater(contrast('#767676', '#ffffff'), 4.5)

    def test_all_presets_meet_active_text_and_selection_targets(self):
        for name in PRESETS:
            value = validate(Appearance(theme=name))
            c = colours(value)
            for key in ('window', 'base', 'alternate', 'button'):
                self.assertGreaterEqual(contrast(c['text'], c[key]), 4.5)
                self.assertGreaterEqual(contrast(c['accent'], c[key]), 3)
            self.assertGreaterEqual(contrast(c['selected_text'], c['accent']), 4.5)

    def test_invalid_custom_colours_and_ranges_are_rejected(self):
        invalid = [dict(text_colour='#eeeeee'), dict(accent_colour='#fafafa'),
                   dict(map_text_colour='#181818'), dict(text_colour='red'),
                   dict(map_text_colour=''), dict(font_size=25), dict(font_size=True),
                   dict(map_font_size=9), dict(map_font_size=12.5), dict(theme='unknown'),
                   dict(show_legend='false')]
        for change in invalid:
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate(replace(Appearance(), **change))


class AppearancePersistenceTests(unittest.TestCase):
    setUpClass = classmethod(editing.CorridorEditingUiTests.setUpClass.__func__)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / 'preferences.ini')
        self.palette = self.app.palette()
        self.font = self.app.font()
        self.stylesheet = self.app.styleSheet()
        self.settings = QSettings(self.path, QSettings.IniFormat)

    def tearDown(self):
        self.app.setStyleSheet('')
        self.app.setPalette(self.palette)
        self.app.setFont(self.font)
        self.app.setStyleSheet(self.stylesheet)
        self.temp.cleanup()

    def test_preferences_round_trip_outside_project(self):
        first = AppearanceController(self.app, self.settings)
        expected = Appearance(theme='Dark', font_size=16, map_font_size=21,
                              text_colour='#ffffff', accent_colour='#ffff00', show_legend=False)
        first.apply(expected)
        second = AppearanceController(self.app, QSettings(self.path, QSettings.IniFormat))
        self.assertEqual(expected, second.value)
        self.assertEqual([SETTINGS_KEY], self.settings.allKeys())
        self.assertEqual(16, self.app.font().pointSize())

    def test_corrupt_or_future_settings_fall_back_without_overwriting(self):
        for raw in ('not json', '{"font_size": 99}', '{"future": true}', '[]'):
            self.settings.setValue(SETTINGS_KEY, raw)
            instance = AppearanceController(self.app, self.settings)
            self.assertEqual(Appearance(), instance.value)
            self.assertIn('could not be read', instance.load_warning)
            self.assertEqual(raw, self.settings.value(SETTINGS_KEY))

    def test_invalid_apply_retains_display_and_saved_preferences(self):
        instance = AppearanceController(self.app, self.settings)
        instance.apply(Appearance(theme='Dark'))
        raw = self.settings.value(SETTINGS_KEY)
        with self.assertRaises(ValueError):
            instance.apply(Appearance(text_colour='#ffffff'))
        self.assertEqual('Dark', instance.value.theme)
        self.assertEqual(raw, self.settings.value(SETTINGS_KEY))
        self.assertEqual('#f2f5f8', self.app.palette().color(QPalette.Text).name())

    def test_failed_save_keeps_active_theme_and_reports_failure(self):
        settings = Mock()
        settings.value.return_value = ''
        settings.status.return_value = QSettings.AccessError
        instance = AppearanceController(self.app, settings)
        with self.assertRaisesRegex(OSError, 'could not be saved'):
            instance.apply(Appearance(theme='Dark'))
        self.assertEqual(Appearance(), instance.value)
        self.assertEqual('#17212b', self.app.palette().color(QPalette.Text).name())

    def test_open_and_new_standard_dialogs_inherit_display(self):
        install_application_theme(self.app)
        instance = AppearanceController(self.app)
        dialog = QDialog()
        layout = QVBoxLayout(dialog)
        label = QLabel('Existing dialog')
        layout.addWidget(label)
        dialog.show()
        instance.apply(Appearance(theme='High contrast', font_size=18))
        self.app.processEvents()
        new_label = QLabel('New dialog')
        self.assertEqual(18, label.font().pointSize())
        self.assertEqual('#ffffff', label.palette().color(QPalette.WindowText).name())
        self.assertEqual(18, new_label.font().pointSize())
        self.assertEqual('#000000', new_label.palette().color(QPalette.Window).name())
        dialog.close()


class AppearanceUiTests(unittest.TestCase):
    setUpClass = classmethod(editing.CorridorEditingUiTests.setUpClass.__func__)

    def setUp(self):
        self.previous = getattr(self.app, '_amr_appearance', None)
        self.palette = self.app.palette()
        self.font = self.app.font()
        self.stylesheet = self.app.styleSheet()
        self.app._amr_appearance = AppearanceController(self.app)
        editing.CorridorEditingUiTests.setUp(self)
        self.editor.appearance.settings = QSettings(str(Path(self.temp.name) / 'display.ini'), QSettings.IniFormat)
        self.editor.show_appearance()
        self.panel = self.editor.appearance_panel

    def tearDown(self):
        self.editor.appearance.changed.disconnect(self.editor._appearance_changed)
        editing.CorridorEditingUiTests.tearDown(self)
        if self.previous is None:
            del self.app._amr_appearance
        else:
            self.app._amr_appearance = self.previous
        self.app.setStyleSheet('')
        self.app.setPalette(self.palette)
        self.app.setFont(self.font)
        self.app.setStyleSheet(self.stylesheet)

    def test_tree_navigation_and_next_return_to_layout(self):
        self.editor.workspace.tree.setCurrentItem(self.editor.workspace.items['layout'])
        self.editor.workspace.tree.setCurrentItem(self.editor.workspace.items['appearance'])
        self.assertEqual('appearance', self.editor.workspace.stage)
        self.assertTrue(self.editor.properties_panel.isHidden())
        self.editor.workspace.step(1)
        self.assertEqual('layout', self.editor.workspace.stage)

    def test_apply_leaves_config_history_saved_state_and_checks_unchanged(self):
        self.editor.validate_json()
        before = deepcopy(self.editor.store.data)
        history = deepcopy(self.editor.edit_history.entries)
        self.editor.show_appearance()
        self.panel.theme.setCurrentText('Dark')
        self.panel.font_size.setValue(14)
        self.assertTrue(self.panel.apply())
        self.assertEqual(14, self.panel.apply_button.font().pointSize())
        self.assertEqual('#151a20', self.editor.workspace.tree.palette().color(QPalette.Base).name())
        self.assertEqual('#20252b', self.panel.sample.palette().color(QPalette.Window).name())
        self.assertEqual(14, self.panel.sample.font().pointSize())
        self.assertGreaterEqual(contrast(self.editor.workspace.search.palette().color(QPalette.PlaceholderText).name(), '#151a20'), 4.5)
        self.assertEqual(before, self.editor.store.data)
        self.assertEqual(history, self.editor.edit_history.entries)
        self.assertFalse(self.editor.has_unsaved_changes())
        self.assertTrue(self.editor.checks_panel.current())

    def test_pending_project_properties_survive_appearance_apply(self):
        self.editor.workspace.select_configuration('amrs', 0)
        properties = self.editor.properties_panel
        properties.fields['speed_m_per_sec'].setText('1')
        self.editor.show_appearance()
        self.panel.theme.setCurrentText('High contrast')
        self.assertTrue(self.panel.apply())
        self.assertTrue(properties.pending)
        self.assertEqual('1', properties.fields['speed_m_per_sec'].text())
        self.assertEqual(2, self.editor.store.data['amrs'][0]['speed_m_per_sec'])

    def test_map_labels_use_requested_pixel_size_and_colour(self):
        self.panel.map_font_size.setValue(22)
        self.panel.colour_fields['map_text_colour'].setText('#ffff00')
        self.assertTrue(self.panel.apply())
        labels = [item for item, target in self.editor._item_lookup.items()
                  if target[0] == 'point_label' and item.text() != 'D']
        self.assertTrue(labels)
        self.assertTrue(all(item.font().pixelSize() == 22 and item.brush().color().name() == '#ffff00' for item in labels))

    def test_invalid_draft_disables_apply_and_can_be_reverted(self):
        self.panel.colour_fields['text_colour'].setText('#ffffff')
        self.assertFalse(self.panel.apply_button.isEnabled())
        self.assertIn('4.5:1', self.panel.preview_status.text())
        self.assertFalse(self.panel.apply())
        self.panel.revert.click()
        self.assertTrue(self.panel.apply_button.isEnabled())
        self.assertEqual(Appearance(), self.panel.value())

    def test_preset_restores_compatible_colours_and_defaults_require_apply(self):
        self.panel.colour_fields['text_colour'].setText('#001122')
        self.panel.theme.setCurrentText('Dark')
        self.assertEqual('', self.panel.colour_fields['text_colour'].text())
        self.assertTrue(self.panel.apply())
        self.panel.defaults.click()
        self.assertEqual('Dark', self.editor.appearance.value.theme)
        self.assertEqual('Light', self.panel.value().theme)
        self.assertTrue(self.panel.apply())
        self.assertEqual('Light', self.editor.appearance.value.theme)

    def test_colour_chooser_can_repair_invalid_input_and_cancel_preserves_it(self):
        field = self.panel.colour_fields['accent_colour']
        field.setText('bad')
        with patch('appearance_panel.QColorDialog.getColor', return_value=QColor()):
            self.panel.choose_colour('accent_colour')
        self.assertEqual('bad', field.text())
        with patch('appearance_panel.QColorDialog.getColor', return_value=QColor('#005ea8')):
            self.panel.choose_colour('accent_colour')
        self.assertTrue(self.panel.apply_button.isEnabled())

    def test_keyboard_controls_and_large_text_fit_desktop(self):
        install_application_theme(self.app)
        self.editor.resize(1280, 800)
        self.editor.show()
        self.panel.font_size.setFocus()
        QTest.keyClick(self.panel.font_size, Qt.Key_Up)
        self.assertEqual(11, self.panel.font_size.value())
        self.panel.font_size.setValue(24)
        self.panel.map_font_size.setValue(28)
        self.panel.apply_button.setFocus()
        QTest.keyClick(self.panel.apply_button, Qt.Key_Space)
        for _ in range(5):
            self.app.processEvents()
        self.assertEqual(24, self.editor.appearance.value.font_size)
        self.assertEqual(24, self.editor.workspace.tree.font().pointSize())
        self.assertEqual(24, self.panel.apply_button.font().pointSize())
        self.assertEqual('#17212b', self.panel.apply_button.palette().color(QPalette.ButtonText).name())
        self.assertLessEqual(self.editor.width(), 1280)
        self.assertLessEqual(self.editor.height(), 800)
        self.assertTrue(self.panel.rect().contains(self.panel.apply_button.geometry()))
        self.editor.workspace.step(1)
        self.app.processEvents()
        self.assertLessEqual(self.editor.width(), 1280)
        self.assertLessEqual(self.editor.height(), 800)

    def test_reducing_text_updates_hidden_tabs_and_replaces_saved_style_size(self):
        self.panel.font_size.setValue(24)
        self.panel.apply()
        self.panel.font_size.setValue(12)
        self.panel.apply()
        self.editor.workspace.step(1)
        self.editor.show()
        self.app.processEvents()
        self.assertEqual(12, self.editor.ribbon_tabs.tabBar().font().pointSize())
        self.assertEqual(1, self.app.styleSheet().count('/* AMR_APPEARANCE_FONT */'))
        self.assertNotIn('font-size: 24pt', self.app.styleSheet())
        self.assertLess(self.editor.ribbon_tabs.tabBar().tabRect(0).height(), 50)

    def test_legend_can_be_hidden_without_hiding_model(self):
        self.panel.legend.setChecked(False)
        self.panel.apply()
        self.editor.workspace.step(1)
        self.editor.show()
        with patch.object(self.editor, '_draw_overlay_box') as draw:
            self.app.processEvents()
            self.editor.canvas.grab()
        draw.assert_not_called()
        self.assertTrue(self.editor._point_item_lookup)
