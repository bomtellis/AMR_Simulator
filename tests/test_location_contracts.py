"""Location input and post-delivery washing references, with hand timing balances."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from amr_sim_models import Task
from simulator import Simulation
from tests.test_engineering_reference import reference_config
from tests.test_route_reservation_atomicity import resource_state
from visualiser.models import JsonStore
from visualiser.project_checks import check_project


def wash_config():
    cfg = reference_config()
    cfg['locations'].append(dict(name='Wash', floor=0, x=12, y=16, max_concurrency=1))
    cfg['corridors']['edges'].append(dict(**{'from': 'B', 'to': 'Wash'}, width_m=3))
    cfg['locations'][1].update(wash_cycle_required=True, wash_location='Wash', wash_cycle_duration_sec=7)
    cfg['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box')]
    return cfg


class LocationContractTests(unittest.TestCase):
    def test_unknown_wash_target_remains_editable_but_cannot_run(self):
        cfg = wash_config()
        cfg['locations'][1]['wash_location'] = 'Typo'
        for data in (cfg, JsonStore(cfg).data):
            with self.assertRaisesRegex(ValueError, 'Typo'):
                Simulation(data)
            report = check_project(data)
            self.assertTrue(any(f.code == 'LOCATION_INPUT' and f.path == '/locations/1/wash_location'
                                for f in report.findings))

    def test_explicit_malformed_location_inputs_reject_before_normalisation(self):
        for key, values in {
            'x': [True, 'nan', None], 'y': [False, 'inf'],
            'floor': [True, 1.5, None, '1.5'], 'max_concurrency': [0, -1, 1.5, True, 'nan'],
            'wash_cycle_required': ['false', 0, None],
            'wash_cycle_duration_sec': [-1, True, 'nan', None],
            'wash_location': [False, ' Wash ', []], 'people_area_type': ['stafff', False, None],
        }.items():
            for value in values:
                cfg = reference_config()
                cfg['locations'][0][key] = value
                before = copy.deepcopy(cfg)
                for consumer in (Simulation, JsonStore):
                    with self.subTest(key=key, value=value, consumer=consumer.__name__), self.assertRaises(ValueError):
                        consumer(cfg)
                self.assertEqual(before, cfg)
                self.assertTrue(any(f.severity == 'error' and f.path == f'/locations/0/{key}'
                                    for f in check_project(cfg).findings))

    def test_location_names_are_unique_and_unambiguous(self):
        for name in ('', ' A', None, 5, 'B'):
            cfg = reference_config()
            cfg['locations'][0]['name'] = name
            for consumer in (Simulation, JsonStore):
                with self.subTest(name=name, consumer=consumer.__name__), self.assertRaises(ValueError):
                    consumer(cfg)

    def test_missing_floor_is_a_draft_not_a_runnable_location(self):
        cfg = reference_config()
        del cfg['locations'][0]['floor']
        JsonStore(cfg)
        with self.assertRaisesRegex(ValueError, 'floor'):
            Simulation(cfg)
        self.assertFalse(check_project(cfg).can_run(cfg))

    def test_defaults_numeric_strings_and_people_classification(self):
        cfg = reference_config()
        cfg['locations'][0].update(floor='0', x='0.125', max_concurrency='2', people_area_type=' STAFF ')
        for data in (cfg, JsonStore(cfg).data):
            sim = Simulation(data)
            self.assertEqual((0, .125, 'staff'), (sim.locations['A'].floor, sim.locations['A'].x, sim.locations['A'].people_area_type))
            self.assertEqual(2, sim.location_max_concurrency['A'])
            self.assertEqual(999999, sim.location_max_concurrency['B'])
            self.assertFalse(sim.locations['B'].wash_cycle_required)
            self.assertEqual(300, sim.locations['B'].wash_cycle_duration_sec)

    def test_wash_transfer_and_service_timing_with_frozen_delivery_receipt(self):
        cfg = wash_config()
        for data in (cfg, JsonStore(cfg).data):
            sim = Simulation(data, verbose=True)
            # A->B = 10 m / 2 m/s; 2 s pickup + 2 s dropoff -> receipt at 9.
            # B->Wash = another 10 m / 2 m/s; wait until 20 then wash 7 -> 27.
            sim._reserve_location('Wash', 0, 20)
            with contextlib.redirect_stdout(io.StringIO()):
                sim.run()
            self.assertEqual(27, sim.amrs[0].available_time)
            self.assertEqual('Wash', sim.amrs[0].location_name)
            self.assertEqual(1, sim.wash_cycles_completed)
            receipts = [r['sim_time_sec'] for r in sim.verbose_rows if r['event_type'] == 'location_payload_enter']
            self.assertEqual([9], receipts)
            self.assertEqual([27], [r['sim_time_sec'] for r in sim.verbose_rows if r['event_type'] == 'task_complete'])

    def test_wash_capacity_estimates_do_not_reserve_and_commits_do(self):
        for capacity, occupied, finish in ((1, 1, 27), (2, 1, 21), (2, 2, 27)):
            cfg = wash_config()
            cfg['locations'][2]['max_concurrency'] = capacity
            sim = Simulation(cfg)
            for _ in range(occupied):
                sim._reserve_location('Wash', 0, 20)
            before = resource_state(sim)
            task = Task('T', 'A', 'B', 'Box')
            estimated = sim._estimate_task_for_amr(sim.amrs[0], task, reserve=False)
            self.assertEqual(finish, estimated['finish_time'])
            self.assertEqual(before, resource_state(sim))
            committed = sim._estimate_task_for_amr(sim.amrs[0], task, reserve=True)
            self.assertEqual(finish, committed['finish_time'])
            self.assertIn((finish - 7, finish), sim.location_reservations['Wash'])
            self.assertEqual(finish, sum(s['duration'] for s in committed['segments']))

    def test_failed_commit_rolls_back_wash_reservation(self):
        sim = Simulation(wash_config())
        sim._reserve_location('Wash', 0, 20)
        before = resource_state(sim)
        with patch.object(sim, '_record_committed_segment_impacts', side_effect=RuntimeError('Late failure')), contextlib.redirect_stdout(io.StringIO()):
            self.assertIsNone(sim._estimate_task_for_amr(sim.amrs[0], Task('T', 'A', 'B', 'Box'), reserve=True))
        self.assertEqual(before, resource_state(sim))

    def test_dropoff_trigger_wins_and_empty_target_means_dropoff(self):
        for both, duration in ((False, 7), (True, 11)):
            cfg = reference_config()
            cfg['locations'][0].update(wash_cycle_required=True, wash_cycle_duration_sec=7)
            if both:
                cfg['locations'][1].update(wash_cycle_required=True, wash_cycle_duration_sec=11)
            sim = Simulation(cfg)
            task = Task('T', 'A', 'B', 'Box')
            self.assertFalse(sim._multi_stop_task_is_eligible(task))
            estimate = sim._estimate_task_for_amr(sim.amrs[0], task)
            wash, = [s for s in estimate['segments'] if s['type'] == 'wash_cycle']
            self.assertEqual(('B', duration, 'B' if both else 'A'), (wash['location'], wash['duration'], wash['wash_trigger_location']))
            self.assertEqual(9 + duration, estimate['finish_time'])

    def test_zero_duration_still_transfers_without_reserving_a_wash_interval(self):
        cfg = wash_config()
        cfg['locations'][1]['wash_cycle_duration_sec'] = 0
        sim = Simulation(cfg)
        sim._reserve_location('Wash', 0, 20)
        result = sim._estimate_task_for_amr(sim.amrs[0], Task('T', 'A', 'B', 'Box'), reserve=True)
        self.assertEqual((14, 'Wash'), (result['finish_time'], result['end_location']))
        self.assertFalse(any(s['type'] == 'wash_cycle' for s in result['segments']))
        self.assertEqual([(0, 20)], sim.location_reservations['Wash'])

    def test_saved_wash_reference_takes_twenty_one_seconds(self):
        cfg = json.loads((Path(__file__).resolve().parents[1] /
                          'verification/scenarios/location-wash.json').read_text())
        for data in (cfg, JsonStore(cfg).data):
            sim = Simulation(data)
            with contextlib.redirect_stdout(io.StringIO()):
                sim.run()
            self.assertEqual(1, len(sim.completed_task_records))
            self.assertEqual(21, sim.amrs[0].available_time)
            self.assertEqual(1, sim.wash_cycles_completed)

    def test_unreachable_wash_has_no_fallback_or_committed_resources(self):
        cfg = wash_config()
        cfg['corridors']['edges'].pop()
        sim = Simulation(cfg)
        task = Task('T', 'A', 'B', 'Box')
        before = resource_state(sim)
        self.assertIsNone(sim._estimate_task_for_amr(sim.amrs[0], task, reserve=True))
        self.assertIn('No route to wash location Wash', task.pending_reason)
        self.assertEqual(before, resource_state(sim))

    def test_default_wash_time_and_legacy_unloaded_profile_scope(self):
        cfg = wash_config()
        del cfg['locations'][1]['wash_cycle_duration_sec']
        cfg['route_profiles'] = {'clean': {'allowed_nodes': ['A', 'Door', 'B']}}
        sim = Simulation(cfg)
        result = sim._estimate_task_for_amr(sim.amrs[0], Task('T', 'A', 'B', 'Box', route_profile='clean'))
        self.assertEqual(314, result['finish_time'])  # 9 + 5 unloaded + 300 wash.
        self.assertEqual('Wash', result['end_location'])

    def test_location_people_classification_does_not_restrict_routes(self):
        cfg = reference_config()
        cfg['locations'][1]['people_area_type'] = 'public'
        sim = Simulation(cfg)
        self.assertEqual(10, sim._shortest_people_path_same_floor(0, 'A', 'B', 'staff')['distance_m'])
        report = check_project(cfg)
        self.assertTrue(any(f.code == 'LOCATION_MODEL_SCOPE' and f.kind == 'unsupported'
                            and f.path == '/locations/1/people_area_type' for f in report.findings))
        cfg['corridors']['edges'][1]['people_area_type'] = 'public'
        self.assertIsNone(Simulation(cfg)._shortest_people_path_same_floor(0, 'A', 'B', 'staff'))

    def test_rename_updates_wash_references(self):
        store = JsonStore(wash_config())
        store.rename_point('Wash', 'Decontamination')
        self.assertEqual('Decontamination', store.get_location('B')['wash_location'])
        Simulation(store.data)

    def test_wash_dialog_preserves_zero_precision_and_missing_target(self):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'visualiser'))
        from PySide6.QtWidgets import QApplication, QDialog
        from dialogs import PointEditorDialog
        app = QApplication.instance() or QApplication([])
        for duration in (0, .0000004, 100000):
            point = dict(kind='location', x=0, y=0, wash_cycle_required=True,
                         wash_cycle_duration_sec=duration, wash_location='Missing')
            dialog = PointEditorDialog(None, 'Edit location', 'B', point)
            with patch('dialogs.QMessageBox.warning') as warning:
                dialog.accept()
            self.assertFalse(warning.called)
            self.assertEqual(QDialog.Accepted, QDialog.result(dialog))
            self.assertEqual(duration, dialog.result['wash_cycle_duration_sec'])
            self.assertEqual('Missing', dialog.result['wash_location'])
            self.assertEqual('Use task drop-off', dialog.wash_location_combo.itemText(0))
            dialog.close()


if __name__ == '__main__':
    unittest.main()
