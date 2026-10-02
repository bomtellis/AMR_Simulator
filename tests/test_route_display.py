"""Profile identification uses independently enumerated directed permissions."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from tests import test_appearance as appearance_tests
from tests import test_project_playback as playback_tests
from tests.test_route_profiles import profile_config
from tests.test_engineering_reference import reference_config
from PySide6.QtCore import Qt, QSettings
from PySide6.QtWidgets import QApplication, QGraphicsLineItem, QGraphicsSimpleTextItem
from models import JsonStore
from simulator import Simulation
from amr_sim_models import Task
from route_display import (ALL, STYLE_KEY, RouteStyles, access_preview, default_style,
                           validate_style, profile_rules, permits)


def section_pairs(config, profile):
    _points, sections, _rules = access_preview(config)
    return set().union(*(s['profiles'].get(profile, set()) for s in sections))


class RouteAccessTests(unittest.TestCase):
    def test_clean_dirty_shared_match_independent_directed_sections(self):
        config = profile_config()
        before = deepcopy(config)
        clean = {('A', 'Shared'), ('Shared', 'A'), ('Shared', 'Clean'),
                 ('Clean', 'Shared'), ('Clean', 'B'), ('B', 'Clean')}
        dirty = {('A', 'Shared'), ('Shared', 'A'), ('Shared', 'Dirty'),
                 ('Dirty', 'Shared'), ('Dirty', 'B'), ('B', 'Dirty')}
        self.assertEqual(clean, section_pairs(config, 'clean'))
        self.assertEqual(dirty, section_pairs(config, 'dirty'))
        self.assertEqual({('A', 'Shared'), ('Shared', 'A')}, clean & dirty)
        self.assertEqual(before, config)
        sim = Simulation(config)
        for name, distance in [('clean', 10), ('dirty', 14)]:
            rules = sim._resolve_task_route_rules(Task('T', 'A', 'B', 'Box', route_profile=name))
            self.assertEqual(distance, sim._shortest_path_same_floor(0, 'A', 'B', rules)['distance_m'])
            actual = {(a, edge['to']) for graph in sim.floor_graphs.values() for a, edges in graph.items()
                      for edge in edges if sim._node_allowed(a, rules) and sim._node_allowed(edge['to'], rules) and sim._edge_allowed(a, edge['to'], rules)}
            self.assertEqual(actual, section_pairs(config, name))

    def test_physical_one_way_and_profile_direction_both_apply(self):
        config = reference_config()
        config['corridors']['edges'] = [{'from': 'A', 'to': 'B', 'bidirectional': False}]
        config['route_profiles'] = {'reverse': {'allowed_edges': [['B', 'A']]}, 'forward': {'allowed_edges': [['A', 'B']]}}
        self.assertEqual(set(), section_pairs(config, 'reverse'))
        self.assertEqual({('A', 'B')}, section_pairs(config, 'forward'))

    def test_empty_allowances_are_unrestricted_and_node_allowances_intersect_edges(self):
        config = reference_config()
        config['route_profiles'] = {'open': {}, 'stem': {'allowed_nodes': ['A', 'Door']}}
        self.assertEqual({('A', 'Door'), ('Door', 'A'), ('Door', 'B'), ('B', 'Door')}, section_pairs(config, 'open'))
        self.assertEqual({('A', 'Door'), ('Door', 'A')}, section_pairs(config, 'stem'))

    def test_auto_connections_match_simulator_and_have_direction_provenance(self):
        config = reference_config()
        config['corridors']['auto_connect'] = True
        config['corridors']['edges'] = [{'from': 'Door', 'to': 'A', 'bidirectional': False}]
        config['route_profiles'] = {'open': {}}
        _points, sections, _rules = access_preview(config)
        first = next(s for s in sections if s['a'] == 'A')
        self.assertEqual({('Door', 'A')}, first['explicit_directions'])
        self.assertEqual({('A', 'Door')}, first['auto_directions'] - first['explicit_directions'])
        sim = Simulation(config)
        actual = {(a, edge['to']) for graph in sim.floor_graphs.values() for a, edges in graph.items() for edge in edges}
        self.assertEqual({('A', 'Door'), ('Door', 'A'), ('Door', 'B'), ('B', 'Door')}, actual)
        self.assertEqual(actual, section_pairs(config, 'open'))

    def test_auto_connection_tie_uses_configured_node_order(self):
        config = reference_config()
        config['corridors'].update(auto_connect=True, edges=[], nodes=[
            dict(name='First', floor=0, x=-1, y=0), dict(name='Second', floor=0, x=1, y=0)])
        config['route_profiles'] = {'open': {}}
        self.assertIn(('A', 'First'), section_pairs(config, 'open'))
        self.assertNotIn(('A', 'Second'), section_pairs(config, 'open'))

    def test_lift_allowances_do_not_block_same_floor_transit_past_lift_nodes(self):
        config = reference_config()
        config['lifts'] = [dict(id='L', floor_locations={'0': {'x': 1, 'y': 1}})]
        config['corridors']['edges'] = [{'from': 'A', 'to': 'L-F0'}]
        config['route_profiles'] = {'clean': {'allowed_lifts': ['Other']}}
        self.assertEqual({('A', 'L-F0'), ('L-F0', 'A')}, section_pairs(config, 'clean'))

    def test_invalid_profile_never_falls_back_to_unrestricted(self):
        for profile in ({'allowed_edges': None}, {'allowed_nodes': 'A'}, {'allowed_edges': [['A']]}, []):
            config = reference_config()
            config['route_profiles'] = {'bad': profile}
            with self.assertRaises(ValueError):
                access_preview(config)

    def test_invalid_graph_is_explicitly_unavailable(self):
        for change in ('missing', 'cross-floor', 'duplicate'):
            config = reference_config()
            if change == 'missing':
                config['corridors']['edges'][0]['to'] = 'Unknown'
            elif change == 'cross-floor':
                config['locations'][0]['floor'] = 1
            else:
                config['corridors']['nodes'][0]['name'] = 'A'
            with self.subTest(change=change), self.assertRaises(ValueError):
                access_preview(config)

    def test_task_local_extensions_are_not_mislabelled_as_profile_permissions(self):
        config = profile_config()
        task = Task('T', 'A', 'B', 'Box', route_profile='clean', allowed_edges=[('A', 'B')])
        sim = Simulation(config)
        self.assertTrue(sim._edge_allowed('A', 'B', sim._resolve_task_route_rules(task)))
        self.assertNotIn(('A', 'B'), section_pairs(config, 'clean'))

    def test_default_styles_are_stable_and_legible(self):
        for name in ('clean', 'dirty', 'shared', 'a profile with spaces', '*'):
            self.assertEqual(default_style(name), default_style(name))
            validate_style(default_style(name))
        with self.assertRaisesRegex(ValueError, '4.5:1'):
            validate_style({'colour': '#111111', 'pattern': 'Solid'})


class RouteDisplayUiTests(unittest.TestCase):
    setUpClass = classmethod(appearance_tests.AppearanceUiTests.setUpClass.__func__)
    tearDown = appearance_tests.AppearanceUiTests.tearDown

    def setUp(self):
        appearance_tests.AppearanceUiTests.setUp(self)
        self.editor.store = JsonStore(profile_config())
        self.editor._reset_edit_history()
        self.editor._saved_state = self.editor._configuration_state()
        self.editor.refresh_canvas()
        self.editor.show_route_identification()
        self.routes = self.editor.route_display_panel

    def select(self, name):
        self.routes.profile.setCurrentIndex(self.routes.profile.findData(name))

    def overlays(self):
        return [item for item in self.editor.scene.items() if item.data(0) == 'route_profile_access']

    def test_all_profiles_draw_labels_patterns_arrows_and_preserve_edge_picking(self):
        self.select(ALL)
        self.routes.show_map()
        items = self.overlays()
        lines = [item for item in items if isinstance(item, QGraphicsLineItem)]
        labels = [item for item in items if isinstance(item, QGraphicsSimpleTextItem)]
        self.assertEqual(6, len(lines))  # shared stem rendered once per profile
        self.assertEqual({'clean', 'dirty'}, {item.text() for item in labels})
        self.assertEqual(24, len(items))  # line, two direction arrows, label
        self.assertTrue(all(self.editor._item_lookup[item][0] == 'edge' for item in items))
        self.assertTrue(all('→' in item.toolTip() for item in items))
        base = [item for item, target in self.editor._item_lookup.items() if target[0] == 'edge' and
                isinstance(item, QGraphicsLineItem) and item.data(0) != 'route_profile_access']
        self.assertTrue(all(item.pen().color().name() == '#505050' for item in base))

    def test_profile_named_asterisk_does_not_select_all(self):
        self.editor.store.data['route_profiles']['*'] = {'allowed_edges': [['A', 'Shared']]}
        self.editor.show_route_identification()
        self.select('*')
        self.routes.show_map()
        self.assertEqual({'*'}, {item.data(1) for item in self.overlays()} )

    def test_saved_styles_reload_without_mutating_project_or_checks(self):
        self.editor.validate_json()
        before = deepcopy(self.editor.store.data)
        self.select('clean')
        self.routes.colour.setText('#ffff00')
        self.routes.pattern.setCurrentText('Dotted')
        self.assertTrue(self.routes.save_style())
        loaded = RouteStyles(self.editor.appearance)
        self.assertEqual({'colour': '#ffff00', 'pattern': 'Dotted'}, loaded.get('clean'))
        self.assertEqual(before, self.editor.store.data)
        self.assertTrue(self.editor.checks_panel.current())
        self.assertFalse(self.editor.has_unsaved_changes())
        self.routes.show_map()
        lines = [item for item in self.overlays() if isinstance(item, QGraphicsLineItem)]
        self.assertTrue(all(item.pen().style() == Qt.DotLine and item.pen().color().name() == '#ffff00' for item in lines))

    def test_rejected_style_keeps_saved_and_active_colour(self):
        self.select('clean')
        old = self.editor.route_styles.get('clean')
        self.routes.colour.setText('#111111')
        self.assertFalse(self.routes.save_style())
        self.assertEqual(old, self.editor.route_styles.get('clean'))
        self.assertIn('4.5:1', self.routes.status.text())

    def test_reset_restores_deterministic_style_and_keeps_other_profiles(self):
        self.editor.route_styles.save('dirty', {'colour': '#ffffff', 'pattern': 'Dotted'})
        self.select('clean')
        self.routes.colour.setText('#ffffff')
        self.routes.save_style()
        self.routes.save_style(reset=True)
        self.assertEqual(default_style('clean'), self.editor.route_styles.get('clean'))
        self.assertEqual('#ffffff', self.editor.route_styles.get('dirty')['colour'])

    def test_corrupt_saved_styles_are_not_silently_overwritten(self):
        settings = self.editor.appearance.settings
        settings.setValue(STYLE_KEY, '{bad json')
        loaded = RouteStyles(self.editor.appearance)
        self.assertIn('could not be read', loaded.warning)
        self.assertEqual(default_style('clean'), loaded.get('clean'))
        self.assertEqual('{bad json', settings.value(STYLE_KEY))

    def test_failed_style_save_keeps_active_styles(self):
        settings = Mock()
        settings.value.return_value = None
        settings.status.return_value = QSettings.AccessError
        with patch.object(self.editor.appearance, 'settings', settings):
            with self.assertRaises(OSError):
                self.editor.route_styles.save('clean', {'colour': '#ffffff', 'pattern': 'Solid'})
        self.assertEqual(default_style('clean'), self.editor.route_styles.get('clean'))

    def test_table_filter_shows_shared_members_and_direction_names(self):
        self.select(ALL)
        self.routes.search.setText('A → Shared')
        shown = [row for row in range(self.routes.table.rowCount()) if not self.routes.table.isRowHidden(row)]
        self.assertEqual(1, len(shown))
        text = self.routes.table.item(shown[0], 2).text()
        self.assertIn('clean:', text)
        self.assertIn('dirty:', text)

    def test_removing_selected_profile_turns_display_off(self):
        self.select('clean')
        self.routes.show_map()
        del self.editor.store.data['route_profiles']['clean']
        self.editor.refresh_canvas()
        self.assertIsNone(self.editor.route_display_combo.currentData())
        self.assertEqual([], self.overlays())

    def test_permissions_edit_invalidates_cached_preview(self):
        before = self.editor.route_access_model()
        self.editor.store.data['route_profiles']['clean']['allowed_edges'] = [['A', 'Shared']]
        after = self.editor.route_access_model()
        self.assertIsNot(before, after)
        self.assertEqual({('A', 'Shared')}, set().union(*(s['profiles'].get('clean', set()) for s in after[1])))

    def test_labels_can_be_hidden_and_turning_display_off_removes_all_overlays(self):
        self.select('dirty')
        self.routes.show_map()
        self.editor.route_labels_check.setChecked(False)
        self.assertTrue(self.overlays())
        self.assertFalse(any(isinstance(item, QGraphicsSimpleTextItem) for item in self.overlays()))
        self.editor.route_display_combo.setCurrentIndex(0)
        self.assertEqual([], self.overlays())

    def test_panel_fits_desktop_and_does_not_edit_permissions(self):
        self.editor.resize(1280, 800)
        self.editor.show()
        self.app.processEvents()
        self.assertLessEqual(self.editor.width(), 1280)
        self.assertLessEqual(self.editor.height(), 800)
        self.assertFalse(self.editor.has_unsaved_changes())

    def test_invalid_preview_remains_visible_with_legend_disabled(self):
        from appearance import Appearance
        self.editor.appearance.apply(Appearance(show_legend=False))
        self.select('clean')
        self.routes.show_map()
        self.editor.store.data['route_profiles']['clean']['allowed_edges'] = None
        self.editor.refresh_canvas()
        self.assertEqual([], self.overlays())
        self.assertIn('preview unavailable', self.editor.route_preview_error)
        self.editor.show()
        with patch.object(self.editor, '_draw_overlay_box') as draw:
            self.app.processEvents()
            self.editor.canvas.grab()
        self.assertTrue(draw.called)

    def test_profile_controls_support_large_text(self):
        from appearance import Appearance
        self.editor.appearance.apply(Appearance(font_size=24))
        self.editor.resize(1280, 800)
        self.editor.show()
        for _ in range(4):
            self.app.processEvents()
        self.assertEqual(24, self.routes.save.font().pointSize())
        self.assertLessEqual(self.editor.width(), 1280)
        self.assertLessEqual(self.editor.height(), 800)


class RoutePlaybackTests(unittest.TestCase):
    prepare = playback_tests.PlaybackUiTests.prepare
    run_reference = playback_tests.PlaybackUiTests.run_reference
    setUpClass = classmethod(playback_tests.PlaybackUiTests.setUpClass.__func__)
    setUp = playback_tests.PlaybackUiTests.setUp
    close_editor = playback_tests.PlaybackUiTests.close_editor
    adopt = playback_tests.PlaybackUiTests.adopt

    def test_playback_uses_frozen_profiles_and_shared_renderer(self):
        self.data[2].data['route_profiles'] = {'saved-clean': {'allowed_edges': [['A', 'Door']]}}
        self.editor.store.data['route_profiles'] = {'current-dirty': {}}
        frozen = deepcopy(self.data[2].data)
        viewer = self.adopt()
        self.assertEqual(-1, viewer.route_choice.findData('current-dirty'))
        viewer.route_choice.setCurrentIndex(viewer.route_choice.findData('saved-clean'))
        items = [item for item in viewer.static_items if item.data(0) == 'route_profile_access']
        self.assertEqual(3, len(items))  # line, one arrow, label
        self.assertEqual({'saved-clean'}, {item.data(1) for item in items})
        self.assertEqual(frozen, viewer.layout_model.data)
        viewer.route_choice.setCurrentIndex(0)
        self.assertFalse(any(item.data(0) == 'route_profile_access' for item in viewer.static_items))
