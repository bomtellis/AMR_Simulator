"""Acceptance bindings for category, group and department rule contracts."""
import copy
import unittest

from simulator import Simulation
from tests.test_generation_reference import grouped_config
from tests.test_generation_contracts import return_config
from tests.test_tracked_stock_reference import stock_config
from visualiser.models import JsonStore


LAYERS = ('category', 'group', 'department')


def at_layer(config, layer):
    category = config['task_generation']['categories']['stores']
    if layer == 'category':
        category.pop('department_groups', None)
        category.pop('departments', None)
        return category
    if layer == 'department':
        category.pop('department_groups', None)
        category['departments'] = {'D': {'enabled': True}}
        return category['departments']['D']
    return category['department_groups'][0]['payload']


class GenerationLayerTests(unittest.TestCase):
    def test_rate_and_priority_contracts_apply_at_each_rule_layer(self):
        for layer in LAYERS:
            for editor in (False, True):
                with self.subTest(layer=layer, editor=editor):
                    config = grouped_config()
                    at_layer(config, layer).update(generation_mode='sporadic', frequency_per_day=48,
                        volume_per_event_m3=0.2, priority=9, requires_staff=False)
                    manager = Simulation(JsonStore(config).data if editor else config).task_generation_manager
                    records = manager.update_until(3600)
                    self.assertEqual(2, len(records))
                    self.assertEqual([9, 9], [r.task.priority for r in records])
                    self.assertAlmostEqual(0.4, sum(r.task.waste_volume_m3 for r in records))

    def test_return_fields_bind_to_generated_tasks_at_each_layer(self):
        for layer in LAYERS:
            with self.subTest(layer=layer):
                config = return_config()
                at_layer(config, layer).update(scheduled_times=['00:02'], priority=9,
                    return_enabled=True, return_payload='Box', return_delay_minutes=2,
                    return_priority=3, return_route_profile='dirty', requires_staff=False)
                record, = Simulation(config).task_generation_manager.update_until(600)
                task = record.task
                self.assertEqual((120, 9, 'Box', 2, 3, 'dirty'),
                    (task.release_time, task.priority, task.return_payload, task.return_delay_minutes,
                     task.return_priority, task.return_route_profile))

    def test_full_exchange_keeps_its_content_contract_at_each_layer(self):
        for layer in LAYERS:
            with self.subTest(layer=layer):
                config = stock_config()
                at_layer(config, layer).update(tracked_item_exchange=True, exchange_mode='full_exchange')
                manager = Simulation(config).task_generation_manager
                record, = manager.update_until(3600)
                manager.task_state_changed(record.task, 'completed', event_time=3600)
                row, = manager.tracked_item_balance()
                self.assertAlmostEqual(10, row['remaining'])
                self.assertAlmostEqual(2, row['removed'])
                self.assertAlmostEqual(8, row['consumed'])

    def test_empty_schedule_and_global_disable_apply_to_all_layers(self):
        for layer in LAYERS:
            config = grouped_config()
            at_layer(config, layer)['scheduled_times'] = []
            self.assertEqual([], Simulation(config).task_generation_manager.update_until(3600))
            at_layer(config, layer)['scheduled_times'] = ['00:01']
            config['task_generation']['enabled'] = False
            self.assertEqual([], Simulation(config).task_generation_manager.update_until(3600))

    def test_invalid_values_reach_shared_validation_at_each_layer(self):
        for layer in LAYERS:
            for field, value in [('generation_mode', 'unknown'), ('requires_staff', 'false'),
                                 ('frequency_per_day', -1), ('volume_per_event_m3', True),
                                 ('threshold_volume_m3', 'nan'), ('staff_initial_count', 0),
                                 ('return_delay_minutes', -1), ('exchange_mode', 'unknown')]:
                with self.subTest(layer=layer, field=field):
                    config = grouped_config()
                    at_layer(config, layer)[field] = value
                    for consumer in (Simulation, JsonStore):
                        with self.assertRaisesRegex(ValueError, field):
                            consumer(copy.deepcopy(config))

    def test_category_capacity_policy_is_an_explicit_override_exception(self):
        for layer in ('group', 'department'):
            config = grouped_config()
            override = at_layer(config, layer)
            override['dropoff_zone_capacity_policy'] = 'allow_temporary_overflow'
            record, = Simulation(config).task_generation_manager.update_until(60)
            self.assertEqual('wait_for_space', record.task.dropoff_zone_capacity_policy)


if __name__ == '__main__':
    unittest.main()
