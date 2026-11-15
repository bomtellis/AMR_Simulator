"""Departure-scoped lift policy in the planner, checks and Building settings."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFileDialog, QMessageBox

from amr_floor_routing import lift_plan_journeys, lift_policy_key
from amr_project import Project
from amr_routing_inputs import validate_routing_inputs
from amr_sim_models import Task
from simulator import Simulation
from tests import test_building_settings as building
from tests.test_forced_floor import configured, connected_network, plan, rides
from tests.test_lift_integration import two_lifts
from visualiser.project_checks import check_project
from building_settings import BuildingSettingsDialog
from models import JsonStore


KEY = 'forced_floor_lift_preference'


def preference(config, lifts=('NearOrigin',), mode='required', origin=0):
    config['building'].update(force_via_floor_enabled=True, force_via_floor=2)
    config['building'][KEY] = dict(mode=mode, from_floor=origin, lift_ids=list(lifts))
    return config


def lift_ids(value, floor=None):
    return [leg['lift'].id for leg in lift_plan_journeys(value)
            if floor is None or floor in (leg['origin_lift'].floor, leg['destination_lift'].floor)]


def possible(sim, origin='A', destination='B5', rules=None):
    return sim._route_possible_between_locations(sim.amrs[0], sim.locations[origin],
                                                 sim.locations[destination], sim.payloads['Box'], rules)


class LiftPreferenceTests(unittest.TestCase):
    def test_departure_floor_controls_both_hub_directions(self):
        sim = Simulation(preference(two_lifts()))
        self.assertEqual(['NearOrigin'], lift_ids(plan(sim, destination='B2')))
        self.assertEqual(['NearOrigin', 'NearOrigin'], lift_ids(plan(sim), floor=2))
        self.assertEqual(['NearDestination'], lift_ids(plan(sim, 'B1', 'B2')))
        self.assertTrue(possible(sim))

    def test_same_floor_detour_and_connections_away_from_hub(self):
        sim = Simulation(preference(configured(), ['L']))
        self.assertEqual([(0, 2), (2, 0)], rides(plan(sim, destination='C0')))
        self.assertEqual(['L', 'L'], lift_ids(plan(sim, destination='C0'), floor=2))
        sim = Simulation(preference(connected_network(), ['B']))
        value = plan(sim)
        self.assertEqual([(0, 1), (1, 2), (2, 1), (1, 3), (3, 5)], rides(value))
        self.assertEqual(['A', 'B', 'B', 'C', 'D'], lift_ids(value))

    def test_preferred_busy_car_remains_eligible_in_both_modes(self):
        for mode in ('required', 'prefer'):
            with self.subTest(mode=mode):
                sim = Simulation(preference(two_lifts(), mode=mode))
                sim.lifts[0].available_time = 500
                value = plan(sim, destination='B2')
                self.assertEqual(['NearOrigin'], lift_ids(value))
                self.assertGreaterEqual(lift_plan_journeys(value)[0]['lift_start'], 500)

    def test_strict_block_and_fallback_agree_with_project_checks(self):
        for mode, status in (('required', 'Blocked'), ('prefer', 'Reachable')):
            with self.subTest(mode=mode):
                cfg = preference(configured(transfer=True), ['Low'], mode)
                cfg['tasks'] = [dict(id='T', pickup='A', dropoff='B5', payload='Box')]
                sim = Simulation(cfg)
                row = check_project(cfg).route_checks[0]
                self.assertEqual(status, row['status'])
                self.assertEqual(mode == 'prefer', possible(sim))
                if mode == 'prefer':
                    value = plan(sim)
                    self.assertEqual([(0, 2), (2, 5)], rides(value))
                    self.assertEqual(['Low', 'High'], lift_ids(value))
                else:
                    self.assertIn('require one of: Low', row['reason'])
                    self.assertIsNone(plan(sim))
                    self.assertFalse(any(sim.lift_reservations.values()))

    def test_profiles_take_precedence_and_are_distinct_in_caches(self):
        cfg = preference(two_lifts())
        cfg['route_profiles'] = {'dirty': dict(allowed_lifts=['NearDestination']), 'default': {}}
        cfg['tasks'] = [dict(id='P', pickup='A', dropoff='B2', payload='Box', labels=['dirty']),
                        dict(id='U', pickup='A', dropoff='B2', payload='Box', allowed_lifts=['NearDestination'])]
        sim = Simulation(cfg)
        dirty = Task('P', 'A', 'B2', 'Box', labels=['dirty'])
        profiled = sim._resolve_task_route_rules(dirty)
        unprofiled = dict(allowed_lifts={'NearDestination'})
        self.assertFalse(possible(sim, destination='B2', rules=unprofiled))
        self.assertTrue(possible(sim, destination='B2', rules=profiled))
        self.assertNotEqual(sim._rules_cache_key(profiled), sim._rules_cache_key(unprofiled))
        self.assertIsNone(plan(sim, destination='B2', rules=unprofiled))
        self.assertEqual(['NearDestination'], lift_ids(plan(sim, destination='B2', rules=profiled)))
        onboard = sim._onboard_route_rules([dirty, Task('U', 'A', 'B2', 'Box')])
        self.assertEqual(['NearDestination'], lift_ids(plan(sim, destination='B2', rules=onboard)))
        default = sim._resolve_task_route_rules(Task('D', 'A', 'B2', 'Box', route_profile='default'))
        self.assertEqual(['NearDestination'], lift_ids(plan(sim, destination='B2', rules=default)))
        self.assertEqual({'P': 'Reachable', 'U': 'Blocked'},
                         {row['name']: row['status'] for row in check_project(cfg).route_checks})

    def test_disabled_modes_preserve_existing_routes_and_policy_keys(self):
        cfg = preference(two_lifts(), mode='off')
        no_setting = deepcopy(cfg)
        no_setting['building'].pop(KEY)
        self.assertEqual(lift_policy_key(cfg), lift_policy_key(no_setting))
        self.assertEqual(['NearDestination'], lift_ids(plan(Simulation(cfg), destination='B2')))
        cfg['building'][KEY]['mode'] = 'required'
        self.assertNotEqual(lift_policy_key(cfg), lift_policy_key(no_setting))
        cfg['building']['force_via_floor_enabled'] = False
        no_setting['building']['force_via_floor_enabled'] = False
        self.assertEqual(lift_policy_key(cfg), lift_policy_key(no_setting))
        self.assertEqual([(0, 5)], rides(plan(Simulation(cfg))))

    def test_rejects_invalid_active_selections_and_accepts_inactive_references(self):
        for updates, error in (({'from_floor': True}, 'departure floor'),
                               ({'lift_ids': []}, 'at least one lift'),
                               ({'lift_ids': ['Low', 'Low']}, 'once'),
                               ({'lift_ids': ['missing']}, 'Unknown selected lifts'),
                               ({'mode': 'never'}, 'Choose Off')):
            with self.subTest(updates=updates):
                cfg = preference(configured(transfer=True), ['Low'])
                cfg['building'][KEY].update(updates)
                with self.assertRaisesRegex(ValueError, error):
                    validate_routing_inputs(cfg)
        cfg = preference(configured(), ['missing'])
        cfg['building']['force_via_floor_enabled'] = False
        validate_routing_inputs(cfg)


class LiftPreferenceSettingsTests(unittest.TestCase):
    setUpClass = classmethod(building.BuildingSettingsUiTests.setUpClass.__func__)
    setUp = building.BuildingSettingsUiTests.setUp
    tearDown = building.BuildingSettingsUiTests.tearDown

    def select(self, dialog, mode='required'):
        dialog.lift_preference_mode.setCurrentIndex(dialog.lift_preference_mode.findData(mode))
        dialog.lift_preference_floor.setCurrentIndex(dialog.lift_preference_floor.findData(0))
        dialog.lift_preference_lifts.item(0).setCheckState(Qt.Checked)

    def test_off_and_cancel_keep_project_data_and_invalid_save_stays_open(self):
        cfg = configured()
        unchanged = BuildingSettingsDialog(None, cfg)
        unchanged.accept()
        self.assertEqual(cfg, unchanged.result)
        dialog = BuildingSettingsDialog(None, cfg)
        self.assertFalse(dialog.lift_preference_floor.isEnabled())
        dialog.lift_preference_mode.setCurrentIndex(dialog.lift_preference_mode.findData('required'))
        self.assertTrue(dialog.lift_preference_floor.isEnabled())
        with patch.object(QMessageBox, 'warning') as warning:
            dialog.accept()
        warning.assert_called_once()
        self.assertIsNone(dialog.result)
        self.select(dialog)
        dialog.reject()
        self.assertIsNone(dialog.result)
        self.assertNotIn(KEY, cfg['building'])

    def test_preference_undo_redo_save_reopen_and_dormancy(self):
        self.editor.store = JsonStore(configured())
        self.editor._reset_edit_history()
        before = deepcopy(self.editor.store.data)

        def save(dialog):
            self.select(dialog, 'prefer')
            dialog.accept()
            return QDialog.Accepted

        with patch.object(BuildingSettingsDialog, 'exec', new=save):
            self.editor.manage_building_settings()
        after = deepcopy(self.editor.store.data)
        self.assertEqual(dict(mode='prefer', from_floor=0, lift_ids=['L']), after['building'][KEY])
        self.assertTrue(self.editor.undo_edit())
        self.assertEqual(before, self.editor.store.data)
        self.assertTrue(self.editor.redo_edit())
        self.assertEqual(after, self.editor.store.data)
        target = Path(self.temp.name) / 'lift-preference.amrproj'
        with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(target), '')):
            self.assertTrue(self.editor.save_project(save_as=True))
        reopened = BuildingSettingsDialog(None, Project.open(target).configuration())
        self.assertEqual('prefer', reopened.lift_preference_mode.currentData())
        self.assertTrue(reopened.lift_preference_floor.isEnabled())
        reopened.force_via_enabled.setChecked(False)
        self.assertFalse(reopened.lift_preference_mode.isEnabled())
        reopened.accept()
        self.assertFalse(reopened.result['building']['force_via_floor_enabled'])
        self.assertEqual(after['building'][KEY], reopened.result['building'][KEY])
