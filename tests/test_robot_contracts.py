"""Independent robot-slot capacity boundaries and raw/editor parity."""
import contextlib
import copy
import io
import unittest

from simulator import Simulation
from tests.test_engineering_reference import reference_config
from visualiser.models import JsonStore
from visualiser.project_checks import check_project


def slot(**changes):
    return dict(dict(name='Deck', payload_capacity_kg=10, payload_length_capacity_m=1,
        payload_width_capacity_m=.7, payload_height_capacity_m=1), **changes)


class RobotContractTests(unittest.TestCase):
    def test_omitted_robot_defaults_and_battery_units_match_after_import(self):
        cfg = reference_config()
        cfg['amrs'] = [dict(id='R', speed_m_per_sec=2, battery_soc_percent=25)]
        for data in (cfg, JsonStore(cfg).data):
            robot, = Simulation(data).amrs
            self.assertEqual((.8, .6, 1.2, 750, 5, 1.5, 20), (robot.length_m, robot.width_m,
                robot.height_m, robot.motor_power_w, robot.battery_capacity_kwh,
                robot.battery_charge_rate_kw, robot.recharge_threshold_percent))
            self.assertEqual(1.25, robot.battery_energy_kwh())
            self.assertEqual(1, robot.min_reserve_energy_kwh())
            self.assertEqual(9000, robot.charge_duration_sec_to_full())
            self.assertEqual((100, 1, 1, 1), tuple(robot.payload_slots[0][key] for key in
                ('payload_capacity_kg', 'payload_length_capacity_m', 'payload_width_capacity_m', 'payload_height_capacity_m')))

    def test_multi_stop_requires_multiple_slots_and_preserves_false(self):
        for count, flag, expected in [(1, True, False), (2, None, True), (2, False, False)]:
            cfg = reference_config()
            cfg['amrs'][0]['payload_slots'] = [slot(name=f'S{i}') for i in range(count)]
            cfg['amrs'][0]['manual_task_compatible'] = count != 1
            if flag is not None:
                cfg['amrs'][0]['multi_stop_enabled'] = flag
            for data in (cfg, JsonStore(cfg).data):
                robot, = Simulation(data).amrs
                self.assertEqual(expected, robot.multi_stop_enabled)
                self.assertEqual(count == 1, robot.manual_task_compatible)

    def test_ignored_start_and_report_mass_are_visible_without_changing_runtime(self):
        cfg = reference_config()
        cfg['amrs'][0].update(start_location='B', weight_kg=500)
        sim = Simulation(cfg)
        self.assertEqual('A', sim.amrs[0].location_name)
        report = check_project(cfg)
        paths = {f.path for f in report.findings if f.code == 'ROBOT_MODEL_SCOPE'}
        self.assertTrue({'/amrs/0/start_location', '/amrs/0/weight_kg'} <= paths)

    def test_invalid_payload_orientations_are_not_replaced_with_default(self):
        for value in ([], None, ['diagonal'], ['sideways', 'bad'], 1):
            cfg = reference_config()
            cfg['payloads'][0]['allowed_carry_orientations'] = value
            for consumer in (Simulation, JsonStore):
                with self.assertRaisesRegex(ValueError, 'allowed_carry_orientations'):
                    consumer(cfg)
            self.assertFalse(check_project(cfg).can_run(cfg))

    def test_legacy_size_fallback_is_preserved_by_editor_import(self):
        cfg = reference_config()
        robot = cfg['amrs'][0]
        robot['payload_size_capacity'] = 2
        for axis in ('length', 'width', 'height'):
            robot.pop(f'payload_{axis}_capacity_m')
        cfg['payloads'][0].update(length_m=1.5, width_m=1.5, height_m=1.5)
        for data in (cfg, JsonStore(cfg).data):
            sim = Simulation(data)
            self.assertTrue(sim._amr_can_carry_payload(sim.amrs[0], sim.payloads['Box']))
            self.assertEqual((2, 2, 2), tuple(sim.amrs[0].payload_slots[0][f'payload_{a}_capacity_m']
                                            for a in ('length', 'width', 'height')))

    def test_explicit_slots_override_top_level_and_legacy_capacities(self):
        cfg = reference_config()
        cfg['amrs'][0].update(payload_size_capacity=99, payload_capacity_kg=999,
                             payload_slots=[slot(payload_capacity_kg=9)])
        for data in (cfg, JsonStore(cfg).data):
            sim = Simulation(data)
            self.assertFalse(sim._amr_can_carry_payload(sim.amrs[0], sim.payloads['Box']))

    def test_weight_and_each_dimension_have_inclusive_boundaries(self):
        for field in (None, 'payload_capacity_kg', 'payload_length_capacity_m',
                      'payload_width_capacity_m', 'payload_height_capacity_m'):
            cfg = reference_config()
            deck = slot()
            if field:
                deck[field] -= .0001
            cfg['amrs'][0]['payload_slots'] = [deck]
            for data in (cfg, JsonStore(cfg).data):
                sim = Simulation(data)
                self.assertEqual(field is None, sim._amr_can_carry_payload(sim.amrs[0], sim.payloads['Box']))

    def test_orientation_is_intersection_of_payload_and_slot_permissions(self):
        cfg = reference_config()
        cfg['amrs'][0]['payload_slots'] = [slot(payload_length_capacity_m=.7,
            payload_width_capacity_m=1, allowed_payload_orientations=['sideways'])]
        for permissions, expected in [(['lengthways'], False), (['sideways'], True),
                                      (['lengthways', 'sideways'], True), ('SIDEWAYS', True)]:
            cfg['payloads'][0]['allowed_carry_orientations'] = permissions
            for data in (cfg, JsonStore(cfg).data):
                sim = Simulation(data)
                self.assertEqual(expected, sim._amr_can_carry_payload(sim.amrs[0], sim.payloads['Box']))

    def test_invalid_slot_shapes_values_and_permissions_reject_without_repair(self):
        cases = [None, {}, [None], [slot(payload_capacity_kg=0)], [slot(payload_length_capacity_m='nan')],
                 [slot(payload_width_capacity_m=True)], [slot(allowed_payload_orientations=[])],
                 [slot(allowed_payload_orientations=['diagonal'])], [slot(), slot()]]
        for slots in cases:
            cfg = reference_config()
            cfg['amrs'][0]['payload_slots'] = slots
            before = copy.deepcopy(cfg)
            for consumer in (Simulation, JsonStore):
                with self.subTest(slots=slots, consumer=consumer.__name__), self.assertRaises(ValueError):
                    consumer(cfg)
            report = check_project(cfg)
            self.assertTrue(any(f.severity == 'error' and '/amrs/0/payload_slots' in f.path for f in report.findings))
            self.assertEqual(before, cfg)

    def test_malformed_robot_values_and_flags_do_not_silently_change_meaning(self):
        for key, values in {
            'quantity': [-1, .5, True, 'nan'], 'multi_stop_enabled': ['false', 0, None],
            'speed_m_per_sec': [0, -1, True, 'inf'], 'payload_capacity_kg': [0, -1],
            'payload_length_capacity_m': [0, 'nan'], 'length_m': [0, 'nan'],
            'motor_power_w': [-1, 'nan'], 'battery_capacity_kwh': [0, 'nan'],
            'battery_charge_rate_kw': [0, -1], 'battery_soc_percent': [-1, 101],
            'recharge_threshold_percent': [-1, 101],
        }.items():
            for value in values:
                cfg = reference_config()
                cfg['amrs'][0][key] = value
                for consumer in (Simulation, JsonStore):
                    with self.subTest(key=key, value=value, consumer=consumer.__name__), self.assertRaises(ValueError):
                        consumer(cfg)
                self.assertTrue(any(f.severity == 'error' and f.path == f'/amrs/0/{key}' for f in check_project(cfg).findings))

    def test_quantity_zero_and_numeric_string_counts_remain_explicit(self):
        for count, expected in [(0, []), ('2', ['R-1', 'R-2'])]:
            cfg = reference_config()
            cfg['amrs'][0]['quantity'] = count
            for data in (cfg, JsonStore(cfg).data):
                self.assertEqual(expected, [robot.id for robot in Simulation(data).amrs])

    def test_robot_id_collisions_and_missing_speed_cannot_run(self):
        cfg = reference_config()
        cfg['amrs'].append(copy.deepcopy(cfg['amrs'][0]))
        for consumer in (Simulation, JsonStore):
            with self.assertRaises(ValueError):
                consumer(cfg)
        cfg = reference_config()
        del cfg['amrs'][0]['speed_m_per_sec']
        JsonStore(cfg)
        with self.assertRaisesRegex(ValueError, 'speed_m_per_sec'):
            Simulation(cfg)
        self.assertFalse(check_project(cfg).can_run(cfg))

    def test_raw_and_imported_speed_reference_finishes_at_nine_seconds(self):
        cfg = reference_config()
        cfg['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box')]
        for data in (cfg, JsonStore(cfg).data):
            sim = Simulation(data)
            with contextlib.redirect_stdout(io.StringIO()):
                sim.run()
            # 10 metres / 2 m/s plus two 2-second handling phases.
            self.assertEqual(9, sim.amrs[0].available_time)
            self.assertEqual(1, len(sim.completed_task_records))

    def test_explicit_empty_slot_list_retains_legacy_single_slot(self):
        cfg = reference_config()
        cfg['amrs'][0]['payload_slots'] = []
        for data in (cfg, JsonStore(cfg).data):
            robot, = Simulation(data).amrs
            self.assertEqual(1, len(robot.payload_slots))
            self.assertTrue(robot.manual_task_compatible)
            self.assertFalse(robot.multi_stop_enabled)

    def test_incomplete_slot_draft_can_open_but_cannot_run(self):
        cfg = reference_config()
        cfg['amrs'][0]['payload_slots'] = [{'name': 'Incomplete'}]
        draft = JsonStore(cfg).data
        self.assertNotIn('payload_capacity_kg', draft['amrs'][0]['payload_slots'][0])
        self.assertEqual(draft, JsonStore(draft).data)
        with self.assertRaisesRegex(ValueError, 'payload_capacity_kg'):
            Simulation(cfg)
        self.assertFalse(check_project(cfg).can_run(cfg))


if __name__ == '__main__':
    unittest.main()
