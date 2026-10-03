"""Raw generation inputs must not change meaning during import or execution."""
import copy
import unittest

from amr_sim_task_generation import TaskGenerationManager
from simulator import Simulation
from tests.test_generation_reference import grouped_config
from visualiser.models import JsonStore
from visualiser.project_checks import check_project


class GenerationInputValidationTests(unittest.TestCase):
    def assert_rejected(self, config, path):
        before = copy.deepcopy(config)
        report = check_project(config, include_legacy=False)
        self.assertTrue(any(f.code == 'GENERATION_INPUT' and f.path == path and f.severity == 'error'
                            for f in report.findings), [f.to_dict() for f in report.findings])
        for consumer in (JsonStore, Simulation):
            with self.assertRaises(ValueError) as caught:
                consumer(config)
            self.assertIn(path, str(caught.exception))
        self.assertEqual(before, config)

    def test_boolean_flags_rejected_before_import_or_simulation_coercion(self):
        for field in ('enabled', 'requires_staff', 'return_enabled', 'tracked_item_exchange',
                      'staff_use_custom_working_hours', 'release_next_after_return_pickup'):
            for value in ('false', 'true', 0, 1, None, [], {}):
                with self.subTest(field=field, value=value):
                    config = grouped_config()
                    config['task_generation']['categories']['stores'][field] = value
                    self.assert_rejected(config, '/task_generation/categories/stores/' + field)

    def test_nested_group_and_legacy_staff_flags_are_checked(self):
        config = grouped_config()
        config['task_generation']['categories']['stores']['department_groups'][0]['payload']['requires_staff'] = 'false'
        self.assert_rejected(config, '/task_generation/categories/stores/department_groups/0/payload/requires_staff')
        config = grouped_config()
        config['task_generation']['staff'] = {'enabled': 'false'}
        self.assert_rejected(config, '/task_generation/staff/enabled')
        config = grouped_config()
        config['task_generation']['stores'] = {'staff_required': 'false'}
        self.assert_rejected(config, '/task_generation/stores/staff_required')

    def test_modes_counts_and_durations_reject_uninterpretable_values(self):
        for field, values in [('generation_mode', ['scheduld', 1, None]),
                              ('staff_initial_count', [0, -1, 1.5, True, 'nan']),
                              ('timeframe_payload_multiple', [0, -1, 1.5, False]),
                              ('staff_handling_minutes', [-1, True, 'nan', 'inf']),
                              ('staff_shift_pattern', ['night_shift'])]:
            for value in values:
                with self.subTest(field=field, value=value):
                    config = grouped_config()
                    config['task_generation']['categories']['stores'][field] = value
                    self.assert_rejected(config, '/task_generation/categories/stores/' + field)

    def test_malformed_nested_containers_have_precise_findings(self):
        for key, value in [('categories', []), ('staff_config', []), ('stores', [])]:
            config = grouped_config()
            config['task_generation'][key] = value
            self.assert_rejected(config, '/task_generation/' + key)
        config = grouped_config()
        config['task_generation']['categories']['stores']['department_groups'][0]['payload'] = []
        self.assert_rejected(config, '/task_generation/categories/stores/department_groups/0/payload')

    def test_staff_pattern_scalars_and_custom_hours_are_not_silently_repaired(self):
        for field, value in [('enabled', 'false'), ('walking_speed_m_per_sec', -1)]:
            config = grouped_config()
            config['task_generation']['staff_config'] = {field: value}
            self.assert_rejected(config, '/task_generation/staff_config/' + field)
        config = grouped_config()
        config['task_generation']['staff_config'] = {'shift_patterns': {'none': {'start_time': '25:00'}}}
        self.assert_rejected(config, '/task_generation/staff_config/shift_patterns/none/start_time')

    def test_unsupported_cycle_is_visible_acknowledgeable_and_stales_on_edit(self):
        config = grouped_config()
        config['task_generation']['staff_config'] = {'shift_patterns': {
            'four_on_four_off_12h': {'work_days': 3, 'rest_days': 4}}}
        report = check_project(config, include_legacy=False)
        warning = next(f for f in report.findings if f.code == 'GENERATION_UNSUPPORTED')
        self.assertEqual('warning', warning.severity)
        self.assertEqual('unsupported', warning.kind)
        self.assertTrue(warning.path.endswith('/work_days'))
        self.assertFalse(report.can_run(config))
        report.acknowledge_warnings()
        self.assertTrue(report.can_run(config))
        self.assertEqual(3, JsonStore(config).data['task_generation']['staff_config']['shift_patterns']['four_on_four_off_12h']['work_days'])
        changed = copy.deepcopy(config)
        changed['task_generation']['staff_config']['shift_patterns']['four_on_four_off_12h']['work_days'] = 4
        self.assertEqual(['task_generation'], report.changed_inputs(warning, changed))
        self.assertFalse(report.can_run(changed))

    def test_direct_manager_and_editor_setter_cannot_bypass_validation(self):
        valid = grouped_config()
        sim = Simulation(valid)
        config = copy.deepcopy(valid)
        config['task_generation']['enabled'] = 'false'
        with self.assertRaisesRegex(ValueError, '/task_generation/enabled'):
            TaskGenerationManager(config, sim.clock, sim.locations, sim.payloads)
        store = JsonStore(valid)
        before = copy.deepcopy(store.data)
        with self.assertRaises(ValueError):
            store.set_task_generation(config['task_generation'])
        self.assertEqual(before, store.data)

    def test_valid_false_omission_and_numeric_strings_retain_semantics(self):
        config = grouped_config()
        category = config['task_generation']['categories']['stores']
        category.update(requires_staff=False, staff_initial_count='2', staff_handling_minutes='1.5')
        store = JsonStore(config)
        self.assertFalse(store.data['task_generation']['categories']['stores']['requires_staff'])
        self.assertFalse(any(f.code == 'GENERATION_INPUT' for f in check_project(config).findings))
        sim = Simulation(config)
        task = sim.task_generation_manager.update_until(61)[0].task
        self.assertEqual((False, 2, 1.5), (task.requires_staff, task.staff_initial_count, task.staff_handling_minutes))

    def test_legacy_zero_interval_and_named_waste_streams_remain_valid(self):
        config = grouped_config()
        config['task_generation']['update_interval_sec'] = 0
        config['departments'][0]['waste_streams'] = ['General', {'name': 'Clinical', 'enabled': False}]
        store = JsonStore(config)
        self.assertEqual(0, store.data['task_generation']['update_interval_sec'])
        self.assertFalse(any(f.code == 'GENERATION_INPUT' for f in check_project(config).findings))
        Simulation(config)

    def test_custom_hours_reject_invalid_clock_and_boolean_values(self):
        for field, value in [('enabled', 'false'), ('start_time', '24:00'), ('end_time', '25:00')]:
            config = grouped_config()
            config['task_generation']['categories']['stores']['staff_working_hours'] = {'mon': {field: value}}
            self.assert_rejected(config, '/task_generation/categories/stores/staff_working_hours/mon/' + field)


if __name__ == '__main__':
    unittest.main()
