"""FM preference, full booking windows, read-only planning and run evidence."""
from copy import deepcopy
from datetime import datetime
import contextlib
import io
import math
from pathlib import Path
import tempfile
import unittest

from amr_bed_lifts import access_intervals, window_intervals
from amr_floor_routing import lift_plan_journeys, lift_plan_segments, lift_policy_key
from amr_lift_inputs import validate_lift_inputs
from amr_sim_models import Task
from simulator import Simulation
from tests.test_floor_waypoints import floor_config
from tests.test_lift_integration import two_lifts


ALL_DAY = [{'start': '00:00', 'end': '24:00'}]


def config(speed=False, forced=False):
    cfg = floor_config(waypoint=False)
    bed = deepcopy(cfg['lifts'][0])
    bed.update(id='Bed', usage_mode='bed_fallback', amr_access_windows=deepcopy(ALL_DAY))
    cfg['lifts'].append(bed)
    cfg['corridors']['edges'] += [dict(edge, to=edge['to'].replace('L-F', 'Bed-F'))
                                  for edge in list(cfg['corridors']['edges'])]
    if speed:
        cfg['amrs'][0].update(lift_entry_speed_m_per_sec=.5, lift_exit_speed_m_per_sec=.25)
        for lift in cfg['lifts']:
            lift['transfer_timing_mode'] = 'speed_based'
    if forced:
        cfg['building'].update(force_via_floor_enabled=True, force_via_floor=2)
    return cfg


def plan(sim, ready=0, destination='B3', payload='Box', rules=None, collect=True):
    return sim._nearest_compatible_lift_plan(ready, sim.amrs[0], sim.locations['A'],
        sim.locations[destination], sim.payloads[payload], rules, 'lengthways', collect)


def ids(value):
    return [leg['lift'].id for leg in lift_plan_journeys(value)]


class BedLiftRoutingTests(unittest.TestCase):
    def test_fm_below_at_and_above_limit(self):
        for wait in (299, 300, 301):
            sim = Simulation(config())
            sim.lifts[0].available_time = wait + 1 - 2  # 1 s approach, 2 s door before entry
            value = plan(sim)
            self.assertEqual(['Bed'] if wait > 300 else ['L'], ids(value))
            if wait > 300:
                self.assertEqual(301, value['predicted_fm_wait_sec'])
                self.assertEqual('fm_wait_limit', value['bed_fallback_reason'])
                self.assertGreater(value['estimated_time_saved_sec'], 0)
            self.assertFalse(any(sim.lift_reservations.values()))

    def test_slower_and_tied_bed_stay_fm(self):
        for available in (350, 351):
            sim = Simulation(config())
            sim.lifts[0].available_time = 350
            sim.lifts[1].available_time = available
            self.assertEqual(['L'], ids(plan(sim)))

    def test_reposition_is_part_of_predicted_wait(self):
        cfg = config()
        cfg['lifts'][0]['start_floor'] = 5
        cfg['building']['bed_lift_fallback_wait_sec'] = 4
        sim = Simulation(cfg)
        value = plan(sim)
        self.assertEqual(['Bed'], ids(value))
        self.assertEqual(7, value['predicted_fm_wait_sec'])

    def test_no_fm_comparison_is_unknown(self):
        sim = Simulation(config())
        sim.lifts[0].health_percent = 0
        value = plan(sim)
        self.assertEqual(['Bed'], ids(value))
        self.assertEqual('no_usable_fm_route', value['bed_fallback_reason'])
        self.assertIsNone(value['predicted_fm_wait_sec'])
        self.assertIsNone(value['estimated_time_saved_sec'])

    def test_no_windows_preserves_fm_or_returns_no_plan(self):
        cfg = config()
        cfg['lifts'][1]['amr_access_windows'] = []
        sim = Simulation(cfg)
        sim.lifts[0].available_time = 350
        self.assertEqual(['L'], ids(plan(sim)))
        sim.lifts[0].health_percent = 0
        self.assertIsNone(plan(sim))

    def test_permissions_capacity_and_outage_are_not_overridden(self):
        for restriction in ('permissions', 'capacity', 'outage'):
            sim = Simulation(config())
            sim.lifts[0].available_time = 350
            rules = {'allowed_lifts': {'L'}} if restriction == 'permissions' else None
            if restriction == 'capacity':
                sim.lifts[1].capacity_width_m = .1
            if restriction == 'outage':
                sim.lifts[1].health_percent = 0
            self.assertEqual(['L'], ids(plan(sim, rules=rules)))
        sim.lifts[0].health_percent = 0
        self.assertIsNone(plan(sim, rules={'blocked_route_dimensions': {'allowed_lifts'}}))

    def test_empty_amr_uses_same_fallback_rule(self):
        sim = Simulation(config())
        sim.lifts[0].available_time = 350
        self.assertEqual(['Bed'], ids(plan(sim, payload='__empty__')))

    def test_destination_distance_does_not_hide_faster_fallback(self):
        cfg = two_lifts()
        cfg['lifts'][0].update(usage_mode='bed_fallback', amr_access_windows=deepcopy(ALL_DAY))
        sim = Simulation(cfg)
        sim.lifts[1].available_time = 350
        self.assertEqual(['NearOrigin'], ids(plan(sim)))

    def test_quicker_fm_alternative_wins_without_using_a_bed_lift(self):
        cfg = two_lifts()
        bed = deepcopy(cfg['lifts'][0])
        bed.update(id='Bed', usage_mode='bed_fallback', amr_access_windows=deepcopy(ALL_DAY))
        cfg['lifts'].append(bed)
        cfg['corridors']['edges'] += [dict(edge, to=edge['to'].replace('NearOrigin-', 'Bed-'))
                                      for edge in list(cfg['corridors']['edges']) if edge['to'].startswith('NearOrigin-')]
        sim = Simulation(cfg)
        sim.lifts[1].available_time = 350
        value = plan(sim)
        self.assertEqual(['NearOrigin'], ids(value))
        self.assertNotIn('bed_fallback_reason', value)

    def test_forced_floor_and_required_lift_selection(self):
        for mode in ('off', 'prefer', 'required'):
            cfg = config(forced=True)
            cfg['building']['forced_floor_lift_preference'] = dict(mode=mode, from_floor=0, lift_ids=['L'])
            sim = Simulation(cfg)
            sim.lifts[0].available_time = 350
            value = plan(sim)
            self.assertEqual(['L', 'L'] if mode == 'required' else ['Bed', 'Bed'], ids(value))
            self.assertEqual([2, 3], [leg['destination_lift'].floor for leg in lift_plan_journeys(value)])

    def test_connecting_waits_are_summed(self):
        cfg = floor_config(transfer=True)
        bed = deepcopy(config()['lifts'][1])
        cfg['lifts'].append(bed)
        cfg['corridors']['edges'] += [dict(edge) for edge in config()['corridors']['edges'] if edge['to'].startswith('Bed-')]
        sim = Simulation(cfg)
        sim.lifts[0].available_time = 201
        sim.lifts[1].available_time = 401
        value = plan(sim)
        self.assertIn('Bed', ids(value))
        self.assertGreater(value['predicted_fm_wait_sec'], 300)
        self.assertEqual([2, 3], [leg['destination_lift'].floor for leg in lift_plan_journeys(value)])

    def test_estimates_and_commit_share_choice_without_speculative_bookings(self):
        for speed in (False, True):
            sim = Simulation(config(speed))
            sim.lifts[0].available_time = 350
            before = deepcopy(sim.lift_reservations)
            estimated, detailed = plan(sim, collect=False), plan(sim)
            self.assertEqual(ids(estimated), ids(detailed))
            self.assertAlmostEqual(estimated['final_finish'], detailed['final_finish'])
            self.assertEqual(before, sim.lift_reservations)
            segments, *_ = lift_plan_segments(sim, detailed, sim.amrs[0], sim.payloads['Box'], 0, reserve=True)
            self.assertEqual(1, len(sim.lift_reservations['Bed']))
            self.assertFalse(sim.lift_reservations['L'])
            transfer = next(s for s in segments if s['type'] == 'lift_transfer')
            self.assertEqual('fm_wait_limit', transfer['bed_fallback_reason'])
            second = plan(sim)
            leg = lift_plan_journeys(second)[0]
            self.assertGreaterEqual(leg['lift_start'], detailed['lift_finish'])

    def test_legacy_configuration_has_identical_policy_and_routes(self):
        original = floor_config(waypoint=False)
        explicit = deepcopy(original)
        explicit['lifts'][0]['usage_mode'] = 'fm'
        self.assertEqual(lift_policy_key(original), lift_policy_key(explicit))
        a, b = plan(Simulation(original)), plan(Simulation(explicit))
        self.assertEqual(a['final_finish'], b['final_finish'])
        self.assertEqual(a['to_lift_segments'], b['to_lift_segments'])
        changed = config()
        first = lift_policy_key(changed)
        changed['building']['bed_lift_fallback_wait_sec'] = 120
        self.assertNotEqual(first, lift_policy_key(changed))

    def test_scenario_outage_and_connector_reservation_respect_access(self):
        from tests.test_scenario_study import scenario, event
        cfg = config()
        closure = dict(event('Bed', end=600), resource_type='lift')
        sim = Simulation(scenario(cfg, [closure]))
        sim.lifts[0].available_time = 350
        self.assertEqual(['L'], ids(plan(sim)))
        cfg = config(speed=True)
        cfg['lifts'][1]['amr_access_windows'] = [{'start': '00:00', 'end': '00:01'}]
        sim = Simulation(cfg)
        sim.lifts[0].health_percent = 0
        sim._reserve_corridor_segments(sim.amrs[0], [dict(type='corridor', **{'from': 'A', 'to': 'Bed-F0'},
            duration=55, distance_m=2)], 0)
        self.assertIsNone(plan(sim))

    def test_geometric_motion_keeps_existing_lift_restriction(self):
        cfg = config()
        cfg['simulation']['motion_model'] = 'geometric_v1'
        cfg['amrs'][0]['manoeuvring'] = dict(minimum_radius_m=.2, pivot_allowed=True, pivot_speed_deg_per_sec=90, clearance_m=.05)
        cfg['geometry'] = dict(schema_version=1, floors=[dict(floor=f, bounds=[-20,-20,30,20], obstacles=[]) for f in range(6)])
        with self.assertRaisesRegex(ValueError, 'lifts interaction with geometric motion'):
            Simulation(cfg)


class BedLiftWindowTests(unittest.TestCase):
    def sim(self, windows, start='2026-01-05T00:00:00', end='2026-01-08T00:00:00', speed=False):
        cfg = config(speed)
        cfg['simulation'].update(start_datetime=start, end_datetime=end)
        cfg['lifts'][1]['amr_access_windows'] = windows
        sim = Simulation(cfg)
        sim.lifts[0].health_percent = 0
        return sim

    def slot(self, sim, ready, **options):
        return sim._find_lift_journey_slot(sim.lifts[1], ready, 0, 3, amr=sim.amrs[0], **options)

    def test_whole_booking_fits_and_exact_end_allowed(self):
        sim = self.sim([{'start': '00:01', 'end': '00:02'}])
        self.assertEqual(60, self.slot(sim, 0)['lift_start'])
        self.assertEqual(120, self.slot(sim, 111)['lift_finish'])
        self.assertEqual(86460, self.slot(sim, 111.001)['lift_start'])

    def test_overnight_and_multi_day_use_simulation_clock(self):
        sim = self.sim([{'start': '23:00', 'end': '01:00'}], start='2026-01-05T00:30:00')
        self.assertEqual(0, self.slot(sim, 0)['lift_start'])
        self.assertEqual(22.5 * 3600, self.slot(sim, 1800)['lift_start'])
        self.assertEqual(46.5 * 3600, self.slot(sim, 1800 + 86400)['lift_start'])

    def test_multiple_windows_and_no_slot_before_horizon(self):
        sim = self.sim([{'start': '00:01', 'end': '00:02'}, {'start': '00:04', 'end': '00:05'}], end='2026-01-05T00:05:00')
        self.assertEqual(240, self.slot(sim, 115)['lift_start'])
        self.assertTrue(math.isinf(self.slot(sim, 295)['lift_finish']))

    def test_reposition_and_speed_based_transfers_must_fit(self):
        sim = self.sim([{'start': '00:01', 'end': '00:02'}], end='2026-01-05T00:03:00')
        sim.lift_initial_floors['Bed'] = 5
        self.assertEqual(120, self.slot(sim, 106)['lift_finish'])
        self.assertTrue(math.isinf(self.slot(sim, 107)['lift_finish']))
        sim = self.sim([{'start': '00:01', 'end': '00:02'}], end='2026-01-05T00:03:00', speed=True)
        value = plan(sim, ready=100)
        self.assertEqual(['Bed'], ids(value))
        self.assertLessEqual(value['lift_finish'], 120)
        self.assertIsNone(plan(sim, ready=110))

    def test_too_long_booking_terminates_without_booking(self):
        sim = self.sim([{'start': '00:01', 'end': '00:02'}])
        sim.lifts[1].boarding_time_sec = 40
        self.assertTrue(math.isinf(self.slot(sim, 0)['lift_finish']))
        self.assertFalse(any(sim.lift_reservations.values()))

    def test_all_day_and_adjacent_windows_do_not_create_midnight_gap(self):
        for windows in (ALL_DAY, [{'start': '00:00', 'end': '12:00'}, {'start': '12:00', 'end': '24:00'}]):
            sim = self.sim(windows)
            self.assertEqual(86404, self.slot(sim, 86395)['lift_finish'])

    def test_validation_rejects_overlap_invalid_time_mode_and_limit(self):
        for windows in ([{'start': '23:00', 'end': '02:00'}, {'start': '01:00', 'end': '03:00'}],
                        [{'start': '01:00', 'end': '01:00'}], [{'start': '24:00', 'end': '01:00'}],
                        [{'start': 'noon', 'end': '13:00'}], 'all day'):
            with self.assertRaises(ValueError):
                window_intervals(windows)
        for field, value in (('usage_mode', 'other'), ('amr_access_windows', [{}])):
            cfg = config()
            cfg['lifts'][1][field] = value
            with self.assertRaises(ValueError):
                validate_lift_inputs(cfg)
        for limit in (-1, True, float('nan'), '300'):
            cfg = config()
            cfg['building']['bed_lift_fallback_wait_sec'] = limit
            with self.assertRaises(ValueError):
                validate_lift_inputs(cfg)

    def test_project_checks_separate_structure_from_access(self):
        from visualiser.project_checks import check_project
        cfg = floor_config(waypoint=False)
        cfg['lifts'][0].update(usage_mode='bed_fallback', amr_access_windows=[])
        cfg['tasks'] = [dict(id='T', pickup='A', dropoff='B3', payload='Box')]
        checks = check_project(cfg)
        self.assertEqual('Reachable', checks.route_checks[0]['status'])
        self.assertTrue(any(f.code == 'BED_LIFT_ACCESS' for f in checks.findings))
        self.assertIsNone(plan(Simulation(cfg)))


class BedLiftEvidenceTests(unittest.TestCase):
    def test_completed_run_retains_fallback_evidence_and_counts(self):
        from amr_project import Project
        from amr_project_runs import PreparedRun, execute
        from amr_route_analysis import load_analysis, summarize, Filters
        from visualiser.project_checks import check_project
        cfg = floor_config(waypoint=False)
        cfg['lifts'][0].update(usage_mode='bed_fallback', amr_access_windows=deepcopy(ALL_DAY))
        cfg['tasks'] = [dict(id='T', pickup='A', dropoff='B3', payload='Box')]
        with tempfile.TemporaryDirectory() as folder:
            project = Project()
            project.save(Path(folder) / 'project.amrproj', cfg)
            prepared = PreparedRun(project, Path(folder) / 'results')
            checks = check_project(prepared.config)
            checks.acknowledge_warnings()
            directory = prepared.commit(checks)
            with contextlib.redirect_stdout(io.StringIO()):
                execute(directory)
            run = load_analysis(directory, drawings=False)
            result = summarize(run, Filters())
            self.assertEqual(1, result['metrics']['Bed-lift fallback journeys'])
            self.assertEqual(1, result['metrics']['Bed-lift fallback transfers'])
            transfer = next(s for s in run.movements if s.kind == 'lift_transfer')
            self.assertEqual('no_usable_fm_route', transfer.detail['bed_fallback_reason'])
            self.assertIsNone(transfer.detail['estimated_time_saved_sec'])
