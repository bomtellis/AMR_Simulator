"""Explicit simulation mode selection, compatibility and lossless previews."""
import copy
import json
import unittest

from amr_geometric_routing import geometry_input_findings, validate_geometry_inputs
from amr_movement_inputs import migrate_movement_inputs
from amr_reference_inputs import DEFAULT_REFERENCE_POINT
from amr_simulation_modes import (resolve_simulation_mode, mode_input_findings,
                                   preview_mode_change, apply_mode_change)
from tests.test_motion_dynamics_simulation import dynamics_config


def detailed_config():
    config = dynamics_config()
    config['simulation']['mode'] = 'detailed'
    config['amrs'][0]['movement'] = migrate_movement_inputs(config['amrs'][0]['movement'])['movement']
    config['amrs'][0]['manoeuvring']['reference_point'] = dict(DEFAULT_REFERENCE_POINT)
    config['geometry']['clearances'] = {'wall_m': 0, 'robot_m': 0}
    config['geometry']['initial_placements'] = [{'amr_id': 'R-1', 'location': 'A', 'heading_deg': 0}]
    return config


class SimulationModeTests(unittest.TestCase):
    def test_empty_editor_sentinel_remains_supported_without_weakening_mode_api(self):
        self.assertEqual([], geometry_input_findings(None))
        validate_geometry_inputs(None)
        self.assertTrue(mode_input_findings(None))
        with self.assertRaises(ValueError): resolve_simulation_mode(None)
        with self.assertRaises(ValueError): preview_mode_change(None, 'simple')
        self.assertTrue(geometry_input_findings([]))

    def test_omitted_mode_resolves_simple_without_modifying_legacy_inputs(self):
        config = {'simulation': {'start_datetime': '2026-01-01'}, 'notes': {'test': 1}}
        before = json.dumps(config)
        self.assertEqual(dict(schema_version=1, mode='simple', motion_model='legacy',
                              traffic_model=None, selection='legacy_adapter'), resolve_simulation_mode(config))
        self.assertEqual([], mode_input_findings(config))
        self.assertEqual(before, json.dumps(config))
        self.assertEqual('simple', resolve_simulation_mode({})['mode'])

    def test_old_geometric_models_never_silently_become_detailed(self):
        for traffic in (None, 'whole_route_v1', 'keep_right_v1'):
            config = {'simulation': {'motion_model': 'geometric_v1'}}
            if traffic is not None:
                config['geometry'] = {'traffic_model': traffic}
            original = copy.deepcopy(config)
            mode = resolve_simulation_mode(config)
            self.assertEqual('geometric_compatibility', mode['mode'])
            self.assertEqual(traffic or 'whole_route_v1', mode['traffic_model'])
            self.assertEqual('legacy_adapter', mode['selection'])
            self.assertEqual(original, config)

    def test_resolver_reads_mode_evidence_without_demanding_new_physical_parameters(self):
        config = {'simulation': {'mode': 'detailed', 'motion_model': 'geometric_v1'},
                  'geometry': {'traffic_model': 'keep_right_v1'}}
        self.assertEqual('detailed', resolve_simulation_mode(config)['mode'])
        self.assertTrue(geometry_input_findings(config))
        self.assertEqual('explicit', resolve_simulation_mode(config)['selection'])

    def test_contradictory_models_and_unknown_modes_are_errors_not_precedence(self):
        cases = [({'mode': 'simple', 'motion_model': 'geometric_v1'}, {}),
                 ({'mode': 'detailed', 'motion_model': 'legacy'}, {'traffic_model': 'keep_right_v1'}),
                 ({'mode': 'detailed', 'motion_model': 'geometric_v1'}, {'traffic_model': 'whole_route_v1'}),
                 ({'mode': 'detailed', 'motion_model': 'geometric_v1'}, {}),
                 ({'mode': 'simple'}, {}), ({'mode': 'geometric_compatibility', 'motion_model': 'geometric_v1'}, {}),
                 ({'mode': 'automatic'}, {}), ({'motion_model': 'unknown'}, {}),
                 ({'motion_model': 'geometric_v1'}, {'traffic_model': 'unknown'})]
        for simulation, geometry in cases:
            config = {'simulation': simulation, 'geometry': geometry}
            with self.subTest(config=config), self.assertRaises(ValueError):
                resolve_simulation_mode(config)
            self.assertTrue(mode_input_findings(config))

    def test_malformed_mode_containers_are_findings_and_resolver_errors(self):
        for config in (None, [], {'simulation': None}, {'simulation': {'mode': False}},
                       {'simulation': {'mode': []}}, {'simulation': {'motion_model': 'geometric_v1'}, 'geometry': []}):
            with self.subTest(config=config), self.assertRaises(ValueError):
                resolve_simulation_mode(config)
            self.assertTrue(mode_input_findings(config))

    def test_detailed_requires_explicit_settings_even_when_legacy_geometry_was_valid(self):
        config = dynamics_config()
        self.assertEqual([], geometry_input_findings(config))
        original = copy.deepcopy(config)
        preview = preview_mode_change(config, 'detailed')
        paths = {path for path, _ in preview['findings']}
        self.assertIn('/amrs/0/movement/schema_version', paths)
        self.assertIn('/amrs/0/manoeuvring/reference_point', paths)
        self.assertIn('/amrs/0/manoeuvring/wall_clearance_m', paths)
        self.assertIn('/amrs/0/manoeuvring/robot_clearance_m', paths)
        self.assertIn('/geometry/initial_placements', paths)
        self.assertEqual(original, config)
        self.assertEqual(config['amrs'], preview['config']['amrs'])
        with self.assertRaisesRegex(ValueError, 'Detailed mode'):
            validate_geometry_inputs(preview['config'])

    def test_complete_explicit_detailed_inputs_pass_full_geometry_checks(self):
        config = detailed_config()
        self.assertEqual([], mode_input_findings(config))
        self.assertEqual([], geometry_input_findings(config))
        validate_geometry_inputs(config)

    def test_separate_clearances_allow_overrides_project_defaults_and_mixed_sources(self):
        for source in ('project', 'robot', 'mixed'):
            config = detailed_config()
            manoeuvring = config['amrs'][0]['manoeuvring']
            if source == 'robot':
                del config['geometry']['clearances']
                manoeuvring.update(wall_clearance_m=0, robot_clearance_m=0)
            elif source == 'mixed':
                # Existing project-clearance contract requires both keys when
                # declaring that object; one robot override may replace either.
                manoeuvring['wall_clearance_m'] = .01
            self.assertEqual([], geometry_input_findings(config), source)
        config = detailed_config()
        del config['geometry']['clearances']
        config['amrs'][0]['manoeuvring']['wall_clearance_m'] = 0
        self.assertIn('/amrs/0/manoeuvring/robot_clearance_m',
                      [p for p, _ in mode_input_findings(config)])

    def test_full_physical_checks_still_reject_malformed_and_colliding_inputs(self):
        cases = []
        invalid = detailed_config()
        del invalid['amrs'][0]['movement']['loaded']['reverse_allowed']
        cases.append((invalid, '/amrs/0/movement'))
        invalid = detailed_config()
        invalid['amrs'][0]['manoeuvring']['reference_point']['pivot_axis'] = 'guessed'
        cases.append((invalid, '/amrs/0/manoeuvring/reference_point'))
        invalid = detailed_config()
        invalid['geometry']['clearances']['robot_m'] = -1
        cases.append((invalid, '/geometry/clearances/robot_m'))
        invalid = detailed_config()
        invalid['geometry']['initial_placements'][0]['location'] = 'missing'
        cases.append((invalid, '/geometry/initial_placements/0/location'))
        for config, path in cases:
            with self.subTest(path=path):
                self.assertIn(path, [p for p, _ in geometry_input_findings(config)])

    def test_preview_records_exact_structural_changes_without_fabricating_physics(self):
        config = {'simulation': {'motion_model': 'legacy', 'end_datetime': '2026-01-02'}, 'notes': [1, 2]}
        original = copy.deepcopy(config)
        preview = preview_mode_change(config, 'detailed')
        self.assertEqual(['/simulation/mode', '/simulation/motion_model', '/geometry/traffic_model'],
                         [change['path'] for change in preview['changes']])
        self.assertFalse(preview['changes'][0]['old_present'])
        self.assertIsNone(preview['changes'][0]['old_value'])
        self.assertEqual('legacy', preview['changes'][1]['old_value'])
        self.assertEqual({'traffic_model': 'keep_right_v1'}, preview['config']['geometry'])
        self.assertNotIn('amrs', preview['config'])
        self.assertTrue(preview['findings'])
        self.assertEqual(original, config)
        json.dumps(preview, allow_nan=False)

    def test_apply_allows_incomplete_edit_and_preserves_dormant_engineering_inputs(self):
        config = detailed_config()
        original = copy.deepcopy(config)
        simple = apply_mode_change(config, 'simple')
        self.assertEqual('legacy', simple['simulation']['motion_model'])
        self.assertEqual(config['geometry'], simple['geometry'])
        self.assertEqual(config['amrs'], simple['amrs'])
        self.assertIsNone(resolve_simulation_mode(simple)['traffic_model'])
        restored = apply_mode_change(simple, 'detailed')
        self.assertEqual(config, restored)
        self.assertEqual(original, config)
        incomplete = apply_mode_change({}, 'detailed')
        self.assertTrue(geometry_input_findings(incomplete))

    def test_same_mode_preview_is_idempotent_and_copy_is_independent(self):
        config = detailed_config()
        preview = preview_mode_change(config, 'detailed')
        self.assertEqual([], preview['changes'])
        self.assertEqual([], preview['findings'])
        preview['config']['geometry']['floors'][0]['bounds'][0] = -99
        self.assertNotEqual(-99, config['geometry']['floors'][0]['bounds'][0])

    def test_simple_ignores_dormant_geometry_without_destroying_it(self):
        config = {'simulation': {'mode': 'simple', 'motion_model': 'legacy'},
                  'geometry': {'traffic_model': 'future_extension', 'private': 'preserved'}}
        self.assertEqual([], geometry_input_findings(config))
        self.assertEqual(config, apply_mode_change(config, 'simple'))

    def test_preview_rejects_unknown_target_and_does_not_replace_malformed_objects(self):
        for config, target in (({}, 'compatibility'), ({'simulation': []}, 'simple'),
                               ({'geometry': []}, 'detailed')):
            before = copy.deepcopy(config)
            with self.assertRaises(ValueError): preview_mode_change(config, target)
            self.assertEqual(before, config)


if __name__ == '__main__':
    unittest.main()
