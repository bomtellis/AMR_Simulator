"""Versioned movement capability editing without invented physical parameters."""
import copy
import math
import unittest

from amr_motion_profiles import MotionProfileError, MotionSettings, profile_for_movement, select_motion_settings
from amr_movement_inputs import (MOVEMENT_PRESETS, movement_preset, apply_movement_preset,
                                  resolve_movement_inputs, migrate_movement_inputs)


def state(**changes):
    values = dict(forward_speed_m_per_sec=2, reverse_speed_m_per_sec=1,
                  acceleration_m_per_sec2=1, braking_m_per_sec2=2,
                  maximum_turn_speed_m_per_sec=1.5, lateral_acceleration_m_per_sec2=.5,
                  pivot_allowed=True, lateral_allowed=True, lateral_speed_m_per_sec=.5,
                  rotation_speed_deg_per_sec=90, angular_acceleration_deg_per_sec2=90,
                  angular_braking_deg_per_sec2=90, minimum_radius_m=2)
    values.update(changes)
    return values


def legacy():
    return {'empty': state(), 'loaded': state(forward_speed_m_per_sec=1, minimum_radius_m=3)}


class MovementInputTests(unittest.TestCase):
    def test_presets_are_exact_capabilities_not_numeric_or_reverse_defaults(self):
        expected = {'steering': (False, False), 'pivoting': (True, False), 'omnidirectional': (True, True)}
        self.assertEqual(tuple(expected), MOVEMENT_PRESETS)
        for name, (pivot, lateral) in expected.items():
            result = movement_preset(name)
            self.assertEqual({'pivot_allowed': pivot, 'lateral_allowed': lateral}, result)
            result['pivot_allowed'] = not pivot
            self.assertEqual(pivot, movement_preset(name)['pivot_allowed'])
        for bad in ('vendor_robot', None, [], True):
            with self.assertRaises(ValueError): movement_preset(bad)

    def test_apply_preset_only_changes_selected_state_flags_without_mutation(self):
        source = legacy()
        source['empty']['reverse_allowed'] = False
        original = copy.deepcopy(source)
        result = apply_movement_preset(source, state='empty', preset='steering')
        expected = copy.deepcopy(source)
        expected['empty'].update(pivot_allowed=False, lateral_allowed=False)
        self.assertEqual(expected, result)
        self.assertEqual(original, source)
        self.assertNotIn('schema_version', result)
        result['loaded']['minimum_radius_m'] = 999
        self.assertEqual(3, source['loaded']['minimum_radius_m'])

    def test_draft_template_does_not_invent_engineering_values_or_other_state(self):
        self.assertEqual({'empty': {'pivot_allowed': True, 'lateral_allowed': True}},
                         apply_movement_preset({}, state='empty', preset='omnidirectional'))
        with self.assertRaises(MotionProfileError):
            resolve_movement_inputs(apply_movement_preset({}, state='empty', preset='steering'))
        for movement, name in ((None, 'empty'), ({'empty': None}, 'empty'), ({}, 'payload')):
            with self.assertRaises(ValueError):
                apply_movement_preset(movement, state=name, preset='steering')

    def test_user_can_override_each_template_capability_independently(self):
        edited = apply_movement_preset(legacy(), state='empty', preset='omnidirectional')
        edited['empty']['pivot_allowed'] = False
        selected = select_motion_settings(edited, loaded=False)
        self.assertFalse(selected.pivot_allowed)
        self.assertTrue(selected.lateral_allowed)
        # Omnidirectional is not a runtime label that can restore the edited flag.
        self.assertNotIn('preset', edited['empty'])

    def test_legacy_reverse_enabled_resolution_is_visible_and_not_persisted(self):
        source = legacy()
        original = copy.deepcopy(source)
        result = resolve_movement_inputs(source)
        self.assertEqual(original, source)
        self.assertEqual(2, result['movement']['schema_version'])
        decisions = [d for d in result['decisions'] if d['code'] == 'LEGACY_REVERSE_ALLOWED']
        self.assertEqual(['/empty/reverse_allowed', '/loaded/reverse_allowed'], [d['path'] for d in decisions])
        self.assertTrue(all(d['value'] is True and d['explanation'] for d in decisions))
        for loaded in (False, True):
            self.assertTrue(select_motion_settings(source, loaded=loaded).reverse_allowed)

    def test_migration_is_idempotent_and_preserves_all_numerical_inputs(self):
        source = legacy()
        source['notes'] = {'author': 'engineering'}
        del source['loaded']['minimum_radius_m']  # Existing geometry fallback is not materialised.
        result = migrate_movement_inputs(source)
        for name in ('empty', 'loaded'):
            actual = dict(result['movement'][name])
            self.assertIs(True, actual.pop('reverse_allowed'))
            self.assertEqual(source[name], actual)
        self.assertEqual(source['notes'], result['movement']['notes'])
        again = migrate_movement_inputs(result['movement'])
        self.assertEqual(result['movement'], again['movement'])
        self.assertEqual([], again['decisions'])

    def test_explicit_legacy_reverse_permission_is_never_overridden(self):
        source = legacy()
        source['empty']['reverse_allowed'] = False
        resolved = resolve_movement_inputs(source)
        self.assertFalse(resolved['movement']['empty']['reverse_allowed'])
        self.assertEqual(['/loaded/reverse_allowed'],
                         [d['path'] for d in resolved['decisions'] if d['code'] == 'LEGACY_REVERSE_ALLOWED'])

    def test_version_two_requires_both_state_reverse_booleans(self):
        for missing in ('empty', 'loaded'):
            source = migrate_movement_inputs(legacy())['movement']
            del source[missing]['reverse_allowed']
            for loaded in (False, True):
                with self.subTest(missing=missing, loaded=loaded), self.assertRaisesRegex(MotionProfileError, missing+'.reverse_allowed'):
                    select_motion_settings(source, loaded=loaded)
        for value in (None, 0, 1, 'true', 'false', math.nan):
            source = migrate_movement_inputs(legacy())['movement']
            source['loaded']['reverse_allowed'] = value
            with self.subTest(value=value), self.assertRaisesRegex(MotionProfileError, 'explicit boolean'):
                select_motion_settings(source, loaded=False)

    def test_unknown_or_malformed_versions_and_incomplete_states_are_rejected(self):
        for version in (0, 3, True, 2.0, '2', None):
            source = {**legacy(), 'schema_version': version}
            with self.subTest(version=version), self.assertRaisesRegex(MotionProfileError, 'schema_version'):
                resolve_movement_inputs(source)
        self.assertEqual(2, resolve_movement_inputs({**legacy(), 'schema_version': 1})['movement']['schema_version'])
        for source in (None, {}, {'empty': state()}, {'empty': state(), 'loaded': None}):
            with self.assertRaises(MotionProfileError): resolve_movement_inputs(source)
        source = legacy()
        del source['loaded']['acceleration_m_per_sec2']
        with self.assertRaisesRegex(MotionProfileError, 'movement.loaded'):
            migrate_movement_inputs(source)

    def test_forward_and_reverse_numerical_profiles_are_unchanged_by_migration(self):
        source = legacy()
        migrated = migrate_movement_inputs(source)['movement']
        for loaded in (False, True):
            before, after = select_motion_settings(source, loaded=loaded), select_motion_settings(migrated, loaded=loaded)
            self.assertEqual(before, after)
            for movement in ('forward', 'reverse', 'lateral', 'pivot'):
                self.assertEqual(profile_for_movement(before, movement=movement, distance=10).to_dict(),
                                 profile_for_movement(after, movement=movement, distance=10).to_dict())
        # D10,v1,a1,b2: accelerate .5m/1s, cruise9.25m/9.25s, brake.25m/.5s.
        p = profile_for_movement(select_motion_settings(migrated, loaded=False), movement='reverse', distance=10)
        self.assertEqual(10.75, p.duration_sec)

    def test_per_state_reverse_permission_rejects_only_forbidden_movement(self):
        source = migrate_movement_inputs(legacy())['movement']
        source['loaded']['reverse_allowed'] = False
        source['loaded']['pivot_allowed'] = False
        empty, loaded = (select_motion_settings(source, loaded=value) for value in (False, True))
        profile_for_movement(empty, movement='reverse', distance=10)
        with self.assertRaises(MotionProfileError) as raised:
            profile_for_movement(loaded, movement='reverse', distance=10)
        self.assertEqual('infeasible_motion', raised.exception.reason)
        # Forbidding stationary pivots must not prohibit ordinary curved travel.
        profile_for_movement(loaded, movement='forward', distance=10, turn_radius_m=3)
        profile_for_movement(loaded, movement='lateral', distance=10)

    def test_existing_direct_settings_callers_retain_reverse_permission(self):
        self.assertTrue(MotionSettings(**state()).reverse_allowed)
        with self.assertRaisesRegex(MotionProfileError, 'explicit boolean'):
            MotionSettings(**state(reverse_allowed=None))

    def test_enabling_template_capability_does_not_supply_its_missing_speed(self):
        source = legacy()
        source['empty'].update(lateral_allowed=False, lateral_speed_m_per_sec=None)
        edited = apply_movement_preset(source, state='empty', preset='omnidirectional')
        self.assertIsNone(edited['empty']['lateral_speed_m_per_sec'])
        with self.assertRaisesRegex(MotionProfileError, 'lateral_speed_m_per_sec'):
            resolve_movement_inputs(edited)


if __name__ == '__main__':
    unittest.main()
