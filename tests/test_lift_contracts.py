"""Lift units, duration, envelope boundaries and entry-point validation."""
import copy
import contextlib
import io
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

from amr_lift_inputs import LIFT_SCALARS, lift_display_speed_m_per_sec
from amr_sim_models import Task
from simulator import Simulation
from tests.test_delivery_energy_reference import lift_config
from visualiser.models import JsonStore
from visualiser.project_checks import check_project


class LiftContractTests(unittest.TestCase):
    def test_saved_reference_reconciles_raw_and_editor_runs(self):
        cfg = json.loads((Path(__file__).resolve().parents[1] /
                          'verification/scenarios/lift-contract.json').read_text())
        for data in (cfg, JsonStore(cfg).data):
            sim = Simulation(data)
            with contextlib.redirect_stdout(io.StringIO()):
                sim.run()
            self.assertEqual(1, len(sim.completed_task_records))
            self.assertFalse(sim.failed_tasks)
            # Handling 2 + connector .5 + reposition 2 + 7 boarding + 2 loaded
            # + 7 alighting + connector .5 + handling 2 = 23 seconds.
            self.assertEqual(23, sim.amrs[0].available_time)
            self.assertEqual([(2.5, 20.5)], [(r[0], r[1]) for r in sim.lift_reservations['L1']])

    def test_existing_lift_dialog_defaults_match_runtime(self):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'visualiser'))
        from PySide6.QtWidgets import QApplication, QWidget
        from dialogs import LiftEditorDialog
        app = QApplication.instance() or QApplication([])
        cfg = lift_config()
        for field in ('boarding_time_sec', 'capacity_length_m', 'capacity_width_m', 'capacity_height_m'):
            cfg['lifts'][0].pop(field, None)
        parent = QWidget()
        parent.store = JsonStore(cfg)
        dialog = LiftEditorDialog(parent, cfg['lifts'][0])
        try:
            self.assertEqual((5, 2.8, 1.8, 2.1), tuple(widget.value() for widget in
                (dialog.board_edit, dialog.capacity_length_edit, dialog.capacity_width_edit, dialog.capacity_height_edit)))
            self.assertEqual(.05, dialog.health_speed_penalty_edit.minimum())
        finally:
            dialog.close()
            parent.close()

    def test_invalid_scalars_rejected_at_all_entry_points(self):
        for key in LIFT_SCALARS:
            for value in (True, None, 'bad', 'nan', 'inf', -0.01):
                with self.subTest(key=key, value=value):
                    cfg = lift_config()
                    cfg['lifts'][0][key] = value
                    before = copy.deepcopy(cfg)
                    for consumer in (Simulation, JsonStore):
                        with self.assertRaisesRegex(ValueError, key):
                            consumer(cfg)
                    report = check_project(cfg)
                    self.assertTrue(any(f.code == 'LIFT_INPUT' and f.path == f'/lifts/0/{key}'
                                        for f in report.findings))
                    self.assertEqual(before, cfg)

    def test_physical_fraction_and_positive_boundaries_are_explicit(self):
        for key, value in [('travel_efficiency', 0), ('travel_efficiency', 1.01),
                           ('regen_efficiency', 1.01), ('health_percent', 101),
                           ('health_loss_per_journey_percent', 101),
                           ('minimum_operational_health_percent', 101),
                           ('health_speed_penalty_at_zero', 0.049),
                           ('health_speed_penalty_at_zero', 1.01),
                           ('speed_floors_per_sec', 0), ('capacity_length_m', 0),
                           ('capacity_width_m', 0), ('capacity_height_m', 0)]:
            cfg = lift_config()
            cfg['lifts'][0][key] = value
            with self.subTest(key=key, value=value), self.assertRaisesRegex(ValueError, key):
                Simulation(cfg)

    def test_zero_duration_disabled_reliability_and_numeric_strings_remain_valid(self):
        cfg = lift_config()
        cfg['lifts'][0].update(door_time_sec='0', boarding_time_sec='0',
            speed_floors_per_sec='0.5', health_loss_per_journey_percent=0,
            mean_time_between_failures_hours=0, mean_time_to_repair_hours=0,
            regen_efficiency=0, counterweight_ratio=0, car_mass_kg=0,
            door_power_w=0, standby_power_w=0, travel_efficiency=1,
            health_speed_penalty_at_zero=.05)
        for data in (cfg, JsonStore(cfg).data):
            sim = Simulation(data)
            slot = sim._find_lift_journey_slot(sim.lifts[0], 0, 0, 1)
            self.assertEqual(2, slot['lift_finish'])

    def test_missing_runtime_speed_remains_editable_but_cannot_run(self):
        cfg = lift_config()
        cfg['lifts'][0].pop('speed_floors_per_sec')
        cfg['lifts'][0]['speed_m_per_sec'] = 1
        self.assertNotIn('speed_floors_per_sec', JsonStore(cfg).data['lifts'][0])
        with self.assertRaisesRegex(ValueError, 'speed_floors_per_sec is required'):
            Simulation(cfg)
        report = check_project(cfg)
        self.assertFalse(report.can_run(cfg))
        self.assertTrue(any(f.code == 'LIFT_INPUT' for f in report.findings))

    def test_omitted_fields_keep_runtime_defaults(self):
        cfg = lift_config()
        lift = cfg['lifts'][0]
        for field in LIFT_SCALARS:
            if field != 'speed_floors_per_sec':
                lift.pop(field, None)
        for data in (cfg, JsonStore(cfg).data):
            actual = Simulation(data).lifts[0]
            self.assertEqual((4, 5, 2.8, 1.8, 2.1), (actual.door_time_sec,
                actual.boarding_time_sec, actual.capacity_length_m, actual.capacity_width_m,
                actual.capacity_height_m))
            self.assertEqual((1200, .5, .75, 800, 120, .2), (actual.car_mass_kg,
                actual.counterweight_ratio, actual.travel_efficiency, actual.door_power_w,
                actual.standby_power_w, actual.regen_efficiency))
            self.assertEqual((100, .05, 720, 4, 20, .5), (actual.health_percent,
                actual.health_loss_per_journey_percent, actual.mean_time_between_failures_hours,
                actual.mean_time_to_repair_hours, actual.minimum_operational_health_percent,
                actual.health_speed_penalty_at_zero))

    def test_service_formula_includes_reposition_and_two_handling_phases(self):
        cfg = lift_config()
        cfg['lifts'][0].update(start_floor=1, speed_floors_per_sec=.5,
            door_time_sec=3, boarding_time_sec=4)
        for data in (cfg, JsonStore(cfg).data):
            sim = Simulation(data)
            slot = sim._find_lift_journey_slot(sim.lifts[0], 10, 0, 1)
            # Start 10, reposition 1/.5=2, board 3+4, loaded 2, alight 3+4.
            self.assertEqual((10, 12, 19, 21, 28), tuple(slot[k] for k in
                ('lift_start', 'reposition_finish', 'loaded_start', 'loaded_finish', 'lift_finish')))

    def test_envelope_exact_fit_and_one_dimension_too_small(self):
        cfg = lift_config()
        cfg['amrs'][0].update(length_m=1, width_m=.6, height_m=.5)
        cfg['lifts'][0].update(capacity_length_m=1, capacity_width_m=.7, capacity_height_m=1)
        for field in (None, 'capacity_length_m', 'capacity_width_m', 'capacity_height_m'):
            case = copy.deepcopy(cfg)
            if field:
                case['lifts'][0][field] -= .0001
            sim = Simulation(case)
            plan = sim._estimate_task_for_amr(sim.amrs[0], Task('T', 'A', 'B', 'Box'))
            self.assertEqual(field is None, plan is not None)

    def test_payload_rotation_does_not_rotate_robot_or_stack_heights(self):
        cfg = lift_config()
        cfg['amrs'][0].update(length_m=.8, width_m=.6, height_m=.5)
        cfg['lifts'][0].update(capacity_length_m=.8, capacity_width_m=1, capacity_height_m=1)
        sim = Simulation(cfg)
        lift, robot, box = sim.lifts[0], sim.amrs[0], sim.payloads['Box']
        self.assertFalse(lift.can_fit(box, robot, 'lengthways'))
        self.assertTrue(lift.can_fit(box, robot, 'sideways'))
        robot.length_m = .9
        self.assertFalse(lift.can_fit(box, robot, 'sideways'))

    def test_legacy_size_units_do_not_change_cabin_or_concurrency(self):
        durations = []
        for units in (0, 1, 100):
            cfg = lift_config()
            cfg['amrs'][0].update(quantity=2, multi_stop_enabled=False)
            cfg['lifts'][0].update(capacity_size_units=units, mean_time_between_failures_hours=0)
            cfg['tasks'] = [dict(id=f'T{i}', pickup='A', dropoff='B', payload='Box') for i in (1, 2)]
            report = check_project(cfg)
            self.assertTrue(any(f.code == 'LIFT_LEGACY_CAPACITY' and f.kind == 'unsupported'
                                for f in report.findings))
            sim = Simulation(cfg)
            with contextlib.redirect_stdout(io.StringIO()):
                sim.run()
            durations.append(sorted(a.available_time for a in sim.amrs))
            self.assertEqual([(2.5, 7.5), (7.5, 13.5)],
                             [(r[0], r[1]) for r in sim.lift_reservations['L1']])
        self.assertEqual([[10, 16]] * 3, durations)

    def test_speed_conflict_preserves_runtime_and_tracks_building_dependency(self):
        cfg = lift_config()
        cfg['lifts'][0].update(speed_floors_per_sec=.5, speed_m_per_sec=99)
        sim = Simulation(cfg)
        self.assertEqual(2, sim._lift_vertical_seconds(sim.lifts[0], 0, 1))
        self.assertEqual(1.5, lift_display_speed_m_per_sec(cfg['lifts'][0], 3))
        report = check_project(cfg)
        finding, = [f for f in report.findings if f.code == 'LIFT_SPEED_METADATA']
        report.acknowledge_warnings()
        self.assertTrue(report.can_run(cfg))
        changed = copy.deepcopy(cfg)
        changed['building']['floor_height_m'] = 4
        self.assertEqual(['building'], report.changed_inputs(finding, changed))
        self.assertFalse(report.can_run(changed))

    def test_lift_dialogs_show_effective_speed_even_when_metadata_is_stale(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'visualiser'))
        from dialogs import LiftEditorDialog, LiftListDialog
        lift = dict(speed_floors_per_sec=.5, speed_m_per_sec=99)
        editor = SimpleNamespace(lift=lift, _floor_height_m=lambda: 3)
        listing = SimpleNamespace(store=SimpleNamespace(data={'building': {'floor_height_m': 3}}))
        self.assertEqual(1.5, LiftEditorDialog._default_speed_m_per_sec(editor))
        self.assertEqual(1.5, LiftListDialog._lift_speed_m_per_sec(listing, lift))

    def test_editor_speed_conversion_keeps_exact_travel_time_and_rejects_bad_save(self):
        store = JsonStore(lift_config())
        store.upsert_lift('L1', [0, 1], {0: (1, 0), 1: (1, 0)}, speed_m_per_sec=1)
        sim = Simulation(store.data)
        self.assertEqual(3, sim._lift_vertical_seconds(sim.lifts[0], 0, 1))
        self.assertEqual(1, lift_display_speed_m_per_sec(store.data['lifts'][0], 3))
        before = copy.deepcopy(store.data)
        with self.assertRaisesRegex(ValueError, 'door_time_sec'):
            store.upsert_lift('L1', [0, 1], {0: (1, 0), 1: (1, 0)}, door_time_sec=-1)
        self.assertEqual(before, store.data)


if __name__ == '__main__':
    unittest.main()
