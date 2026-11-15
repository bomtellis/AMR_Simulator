"""Policy, independently calculated connector timing, and import-file contracts."""
import contextlib
from copy import deepcopy
import csv
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from amr_floor_routing import lift_plan_journeys, lift_plan_segments
from amr_routing_inputs import validate_routing_inputs
from amr_lift_inputs import validate_lift_inputs
from amr_run_evidence import config_hash, file_hash
from amr_sim_models import Task
from amr_third_party_lift import COLUMNS, export_lift_csv, movement_rows
from simulator import Simulation
from tests.test_floor_waypoints import floor_config


def direct_config(speed_based=False):
    cfg = floor_config(waypoint=False)
    cfg['building'].update(lift_transfer_floor=2, destination_side_lift_floors=[0, 2])
    if speed_based:
        cfg['amrs'][0].update(lift_entry_speed_m_per_sec=.5, lift_exit_speed_m_per_sec=.25)
        cfg['lifts'][0]['transfer_timing_mode'] = 'speed_based'
    return cfg


def two_lifts():
    cfg = direct_config()
    first = deepcopy(cfg['lifts'][0])
    first['id'] = 'NearOrigin'
    second = deepcopy(first)
    second['id'] = 'NearDestination'
    cfg['lifts'] = [first, second]
    cfg['corridors']['edges'] = []
    for lift in cfg['lifts']:
        for floor in lift['served_floors']:
            location = 'A' if floor == 0 else f'B{floor}'
            distance = (1 if floor == 0 else 10) if lift['id'] == 'NearOrigin' else (10 if floor == 0 else 1)
            cfg['corridors']['edges'].append(dict(**{'from': location, 'to': f"{lift['id']}-F{floor}"},
                width_m=3, distance_m=distance))
    return cfg


def plan(sim, origin='A', destination='B3', reserve=False):
    return sim._nearest_compatible_lift_plan(0, sim.amrs[0], sim.locations[origin], sim.locations[destination],
        sim.payloads['Box'], sim._empty_route_rules(), 'lengthways', True)


class LiftRoutingPolicyTests(unittest.TestCase):
    def test_direct_lift_bypasses_transfer_even_when_busy(self):
        sim = Simulation(direct_config())
        sim.lifts[0].available_time = 100
        result = plan(sim)
        self.assertEqual([3], [leg['destination_lift'].floor for leg in lift_plan_journeys(result)])
        self.assertEqual(100, result['lift_start'])

    def test_connection_stops_on_level_two(self):
        cfg = floor_config(transfer=True, waypoint=False)
        cfg['building'].update(lift_transfer_floor=2, destination_side_lift_floors=[2])
        sim = Simulation(cfg)
        result = plan(sim)
        self.assertEqual([2, 3], [leg['destination_lift'].floor for leg in lift_plan_journeys(result)])
        self.assertEqual(['Low', 'High'], [leg['lift'].id for leg in lift_plan_journeys(result)])
        self.assertTrue(sim._route_possible_between_locations(sim.amrs[0], sim.locations['A'], sim.locations['B3'], sim.payloads['Box']))

    def test_unreachable_transfer_blocks_an_otherwise_connecting_route(self):
        cfg = floor_config(transfer=True, waypoint=False)
        cfg['building']['lift_transfer_floor'] = 4
        sim = Simulation(cfg)
        # Low only connects at 2; reaching 4 then 3 is still a valid real stop.
        self.assertEqual([2, 4, 3], [leg['destination_lift'].floor for leg in lift_plan_journeys(plan(sim))])
        cfg['building']['lift_transfer_floor'] = 5
        cfg['lifts'][1]['served_floors'].remove(5)
        cfg['lifts'][1]['floor_locations'].pop('5')
        cfg['corridors']['edges'] = [e for e in cfg['corridors']['edges'] if e['to'] != 'High-F5']
        sim = Simulation(cfg)
        self.assertIsNone(plan(sim))
        self.assertFalse(sim._route_possible_between_locations(sim.amrs[0], sim.locations['A'], sim.locations['B3'], sim.payloads['Box']))

    def test_start_on_transfer_floor_goes_direct(self):
        sim = Simulation(direct_config())
        result = plan(sim, 'B2', 'B3')
        self.assertEqual([3], [leg['destination_lift'].floor for leg in lift_plan_journeys(result)])

    def test_explicit_waypoint_still_applies(self):
        cfg = direct_config()
        cfg['building']['mandatory_floor_waypoints'] = [dict(from_floor=0, to_floors=[3], via_floor=2)]
        self.assertEqual([2, 3], [leg['destination_lift'].floor for leg in lift_plan_journeys(plan(Simulation(cfg)))])

    def test_destination_distance_takes_priority_over_completion(self):
        sim = Simulation(two_lifts())
        sim.lifts[1].available_time = 100
        result = plan(sim)
        self.assertEqual('NearDestination', result['lift'].id)
        self.assertEqual(100, result['lift_start'])
        self.assertEqual(1, result['destination_walking_distance_m'])

    def test_incompatible_or_forbidden_nearest_lift_is_excluded(self):
        cfg = two_lifts()
        cfg['lifts'][1]['capacity_width_m'] = .1
        self.assertEqual('NearOrigin', plan(Simulation(cfg))['lift'].id)
        sim = Simulation(two_lifts())
        rules = sim._empty_route_rules()
        rules['allowed_lifts'] = {'NearOrigin'}
        result = sim._nearest_compatible_lift_plan(0, sim.amrs[0], sim.locations['A'], sim.locations['B3'],
            sim.payloads['Box'], rules, 'lengthways', True)
        self.assertEqual('NearOrigin', result['lift'].id)

    def test_destination_specific_selection_and_cache(self):
        cfg = two_lifts()
        cfg['locations'].append(dict(name='Other', floor=3, x=8, y=0))
        cfg['corridors']['edges'].extend([
            dict(**{'from': 'NearOrigin-F3', 'to': 'Other'}, width_m=3, distance_m=1),
            dict(**{'from': 'NearDestination-F3', 'to': 'Other'}, width_m=3, distance_m=20)])
        sim = Simulation(cfg)
        self.assertEqual('NearDestination', plan(sim)['lift'].id)
        self.assertEqual('NearOrigin', plan(sim, destination='Other')['lift'].id)
        self.assertEqual('NearDestination', plan(sim)['lift'].id)

    def test_disabled_policy_preserves_previous_winner(self):
        cfg = two_lifts()
        cfg['building'].pop('destination_side_lift_floors')
        cfg['building'].pop('lift_transfer_floor')
        self.assertEqual('NearOrigin', plan(Simulation(cfg))['lift'].id)

    def test_equal_distance_and_finish_use_lift_id(self):
        cfg = two_lifts()
        for edge in cfg['corridors']['edges']:
            edge['distance_m'] = 1
        self.assertEqual('NearDestination', plan(Simulation(cfg))['lift'].id)

    def test_same_floor_task_does_not_visit_transfer_floor(self):
        cfg = direct_config()
        cfg['locations'].append(dict(name='Same', floor=0, x=5, y=0))
        cfg['corridors']['edges'].append(dict(**{'from': 'A', 'to': 'Same'}, width_m=3, distance_m=5))
        sim = Simulation(cfg)
        result = sim._estimate_task_for_amr(sim.amrs[0], Task('T', 'A', 'Same', 'Box'), reserve=False)
        self.assertIsNotNone(result)
        self.assertFalse(any(s['type'].startswith('lift_') for s in result['segments']))

    def test_policy_settings_reject_invalid_floors(self):
        for key, value in [('lift_transfer_floor', True), ('lift_transfer_floor', 99),
                           ('destination_side_lift_floors', [2, 2]), ('destination_side_lift_floors', [False])]:
            cfg = direct_config()
            cfg['building'][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                validate_routing_inputs(cfg)


class GraphTransferTimingTests(unittest.TestCase):
    def test_graph_connector_respects_scenario_closure_and_speed(self):
        from tests.test_scenario_study import event, scenario
        closed = scenario(direct_config(True), [event('A -> L-F0', end=60)])
        result = plan(Simulation(closed))
        self.assertGreaterEqual(result['entry_start_sec'], 60)
        slowed = scenario(direct_config(True), [event('A -> L-F0', end=300, availability=100, speed=.5)])
        result = plan(Simulation(slowed))
        self.assertEqual(8, result['entry_time_sec'])
        self.assertEqual(8, result['exit_time_sec'])

    def test_directed_exit_connector_uses_its_own_distance(self):
        cfg = direct_config(True)
        edge = next(e for e in cfg['corridors']['edges'] if e['from'] == 'B3')
        edge['bidirectional'] = False
        cfg['corridors']['edges'].append(dict(**{'from': 'L-F3', 'to': 'B3'},
            bidirectional=False, width_m=3, distance_m=7))
        result = plan(Simulation(cfg))
        self.assertEqual(4, result['entry_time_sec'])
        self.assertEqual(28, result['exit_time_sec'])

    def test_graph_connector_cannot_bypass_clearance_restriction(self):
        cfg = direct_config(True)
        next(e for e in cfg['corridors']['edges'] if e['from'] == 'B3')['width_m'] = .1
        self.assertIsNone(plan(Simulation(cfg)))

    def test_preflight_identifies_missing_connector_and_waypoint_override(self):
        from visualiser.project_checks import check_project
        cfg = direct_config(True)
        cfg['corridors']['edges'] = [e for e in cfg['corridors']['edges'] if e['from'] != 'B3']
        self.assertIn('LIFT_CONNECTOR', {f.code for f in check_project(cfg).findings})
        cfg = direct_config()
        cfg['building']['mandatory_floor_waypoints'] = [dict(from_floor=0, to_floors=[3], via_floor=2)]
        self.assertIn('LIFT_WAYPOINT_OVERRIDE', {f.code for f in check_project(cfg).findings})

    def test_connector_reservation_delays_lift_entry(self):
        sim = Simulation(direct_config(True))
        sim._reserve_corridor_segments(sim.amrs[0], [dict(type='corridor', **{'from': 'A', 'to': 'L-F0'},
            duration=50, distance_m=2)], 0)
        result = plan(sim)
        self.assertGreaterEqual(result['entry_start_sec'], 50)

    def test_connector_edges_are_counted_once_at_distinct_speeds(self):
        cfg = direct_config(True)
        for edge in cfg['corridors']['edges']:
            edge['distance_m'] = 6 if edge['from'] == 'A' else 3
        sim = Simulation(cfg)
        result = plan(sim)
        # Entry 6/.5=12; exit 3/.25=12; vertical 3; two doors 2+2.
        self.assertEqual(12, result['entry_time_sec'])
        self.assertEqual(12, result['exit_time_sec'])
        self.assertEqual(31, result['final_finish'])
        self.assertEqual(0, result['to_lift_sec'])
        self.assertEqual(0, result['from_lift_sec'])
        self.assertEqual(2, result['entry_start_sec'])
        segments, _, distance, _, _ = lift_plan_segments(sim, result, sim.amrs[0], sim.payloads['Box'], 0)
        self.assertEqual(21, distance)  # 6+12 vertical+3
        self.assertEqual(31, sum(s['duration'] for s in segments))
        self.assertEqual(1, len(segments))
        self.assertEqual('A', segments[0]['entry_edge']['from'])
        estimated = sim._nearest_compatible_lift_plan(0, sim.amrs[0], sim.locations['A'], sim.locations['B3'],
            sim.payloads['Box'], sim._empty_route_rules(), 'lengthways', False)
        self.assertEqual(result['final_finish'], estimated['final_finish'])

    def test_read_only_estimate_and_committed_booking_reconcile(self):
        sim = Simulation(direct_config(True))
        before = deepcopy(sim.lift_reservations)
        result = plan(sim)
        self.assertEqual(before, sim.lift_reservations)
        segments, energy, *_ = lift_plan_segments(sim, result, sim.amrs[0], sim.payloads['Box'], 0, reserve=True)
        self.assertEqual(result['lift_finish'], sim.lift_reservations['L'][0][1])
        self.assertAlmostEqual(energy, sum(s.get('energy_kwh', 0) for s in segments))

    def test_speed_based_connecting_trip_exits_to_corridor_before_next_lift(self):
        cfg = floor_config(transfer=True, waypoint=False)
        cfg['building']['lift_transfer_floor'] = 2
        cfg['amrs'][0].update(lift_entry_speed_m_per_sec=.5, lift_exit_speed_m_per_sec=.25)
        for lift in cfg['lifts']:
            lift['transfer_timing_mode'] = 'speed_based'
        sim = Simulation(cfg)
        result = plan(sim)
        legs = lift_plan_journeys(result)
        self.assertEqual([2, 3], [leg['destination_lift'].floor for leg in legs])
        segments, _, _, _, _ = lift_plan_segments(sim, result, sim.amrs[0], sim.payloads['Box'], 0)
        self.assertAlmostEqual(result['final_finish'], sum(s['duration'] for s in segments))

    def test_missing_speed_and_invalid_mode_are_rejected(self):
        for mutate in (lambda c: c['amrs'][0].pop('lift_entry_speed_m_per_sec'),
                       lambda c: c['amrs'][0].update(lift_exit_speed_m_per_sec=0),
                       lambda c: c['lifts'][0].update(transfer_timing_mode='wrong')):
            cfg = direct_config(True)
            mutate(cfg)
            with self.assertRaises(ValueError):
                validate_lift_inputs(cfg)


class ThirdPartyLiftExportTests(unittest.TestCase):
    def config(self):
        return dict(lifts=[dict(id='Lift-7', boarding_time_sec=31, door_time_sec=2)])

    def events(self):
        return [dict(segment_type='lift_transfer', lift_id='Lift-7', sim_time_sec=29024,
            details=json.dumps(dict(**{'from': 'Lift-7-F0', 'to': 'Lift-7-F2'},
                entry_start_sec=29026.49, entry_time_sec=31, exit_time_sec=31))),
            dict(segment_type='lift_reposition', lift_id='Lift-7', sim_time_sec=29000,
                start_floor=0, end_floor=0,
                details=json.dumps(dict(**{'from': 'Lift-7-F2', 'to': 'Lift-7-F0'}, amr_wait_node='A')))]

    def source(self, folder, events=None):
        source = Path(folder) / 'events.csv'
        rows = self.events() if events is None else events
        keys = sorted(set().union(*(row.keys() for row in rows)))
        with source.open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, keys)
            writer.writeheader()
            writer.writerows(rows)
        config = self.config()
        Path(str(source) + '.run.json').write_text(json.dumps(dict(frozen_inputs=config,
            config_sha256=config_hash(config), log_sha256=file_hash(source), log_kind='full',
            logging_enabled=True, reduced_logging=False, run_status='finished')), encoding='utf-8')
        return source

    def test_exact_schema_offsets_concatenation_and_rounding(self):
        rows = movement_rows(self.events(), self.config(), 'Lift-7')
        self.assertEqual(list(COLUMNS), list(rows[0]))
        self.assertEqual('29026,1,3,1500,60,31,31,2', rows[0]['concatenated'])
        event = self.events()[0]
        detail = json.loads(event['details'])
        detail.update(entry_start_sec=29026.5, entry_time_sec=.123456, exit_time_sec=2.5)
        event['details'] = json.dumps(detail)
        self.assertEqual('29027,1,3,1500,60,0.123,2.5,2', movement_rows([event], self.config(), 'Lift-7')[0]['concatenated'])

    def test_reposition_toggle_true_endpoints_and_stable_sort(self):
        rows = movement_rows(self.events(), self.config(), 'Lift-7', True)
        self.assertEqual(2, len(rows))
        self.assertEqual('29000,3,1,1500,60,0,0,2', rows[0]['concatenated'])

    def test_legacy_fixed_timing_and_missing_speed_evidence(self):
        event = self.events()[0]
        detail = json.loads(event['details'])
        for key in ('entry_start_sec', 'entry_time_sec', 'exit_time_sec'):
            detail.pop(key)
        event['details'] = json.dumps(detail)
        self.assertEqual('29026', movement_rows([event], self.config(), 'Lift-7')[0]['Start Seconds'])
        config = self.config()
        config['lifts'][0]['transfer_timing_mode'] = 'speed_based'
        with self.assertRaisesRegex(ValueError, 'repeat the run'):
            movement_rows([event], config, 'Lift-7')

    def test_atomic_csv_quoting_and_frozen_input_integrity(self):
        with tempfile.TemporaryDirectory() as folder:
            source = self.source(folder)
            before = file_hash(source)
            target = Path(folder) / 'third-party.csv'
            self.assertEqual(1, export_lift_csv(source, target, 'Lift-7'))
            with target.open(newline='') as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(8, len(rows[0]))
            self.assertEqual('31,31', rows[0]['Transfer times'])
            self.assertEqual(before, file_hash(source))
            saved = target.read_bytes()
            source.write_text(source.read_text() + '\n')
            with self.assertRaises(ValueError):
                export_lift_csv(source, target, 'Lift-7')
            self.assertEqual(saved, target.read_bytes())

    def test_cli_export_only_does_not_produce_pdf(self):
        with tempfile.TemporaryDirectory() as folder:
            source = self.source(folder)
            target = Path(folder) / 'output.csv'
            app = Path(__file__).resolve().parents[1] / 'amr_app.py'
            result = subprocess.run([sys.executable, str(app), str(source), '--third-party-lift-csv', str(target),
                '--lift-id', 'Lift-7', '--include-lift-reposition'], capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertTrue(target.exists())
            self.assertEqual([], list(Path(folder).glob('*.pdf')))

    def test_missing_evidence_unknown_lift_and_empty_export(self):
        self.assertEqual([], movement_rows([], self.config(), 'Lift-7'))
        with self.assertRaisesRegex(ValueError, 'Unknown lift'):
            movement_rows([], self.config(), 'unknown')
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'old.csv'
            source.write_text('sim_time_sec\n')
            with self.assertRaisesRegex(ValueError, 'configuration evidence'):
                export_lift_csv(source, Path(folder) / 'out.csv', 'Lift-7')


class CompletedRunIntegrationTests(unittest.TestCase):
    def test_compact_run_export_uses_recorded_graph_timing_and_balanced_energy(self):
        from amr_project import Project
        from amr_project_runs import PreparedRun, execute
        from amr_run_review import verified_events
        from report.amr_energy_evidence import read_energy_evidence
        from visualiser.project_checks import check_project
        with tempfile.TemporaryDirectory() as folder:
            cfg = direct_config(True)
            cfg['tasks'] = [dict(id='T', pickup='A', dropoff='B3', payload='Box')]
            project = Project()
            project.save(Path(folder) / 'project.amrproj', cfg)
            prepared = PreparedRun(project, Path(folder) / 'results')
            checks = check_project(prepared.config)
            checks.acknowledge_warnings()
            self.assertTrue(checks.can_run(prepared.config), checks.to_dict())
            directory = prepared.commit(checks)
            with contextlib.redirect_stdout(io.StringIO()):
                sim = execute(directory)
            _, _, events, _ = verified_events(directory)
            target = Path(folder) / 'export.csv'
            self.assertEqual(1, export_lift_csv(directory, target, 'L'))
            with target.open(newline='') as stream:
                row = next(csv.DictReader(stream))
            self.assertEqual('4,8', row['Transfer times'])
            ledger = read_energy_evidence(events)
            self.assertAlmostEqual(sim.amrs[0].total_energy_used_kwh, ledger['sources']['amr_battery']['value_kwh'])
            self.assertTrue(all(row['matches'] for row in ledger['battery']['records']), ledger['battery'])


if __name__ == '__main__':
    unittest.main()
