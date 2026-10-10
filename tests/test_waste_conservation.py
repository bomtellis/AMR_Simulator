"""Independent waste threshold and accrued/collected/residual references."""
import copy
import unittest

from simulator import Simulation
from tests.test_generation_provenance import waste_config, active_rule
from visualiser.models import JsonStore


def dynamic_config():
    config = waste_config()
    config['task_generation']['categories']['waste'].update(
        generation_mode='threshold', scheduled_times=[], base_daily_volume_m3=24,
        requires_staff=False, return_enabled=False)
    config['simulation']['end_datetime'] = '2026-01-05T02:00:00'
    return config


def legacy_config():
    config = dynamic_config()
    config['task_generation'] = {'enabled': True, 'department_waste': {'enabled': True, 'priority': 37}}
    config['simulation'].update(start_datetime='2026-01-05T08:00:00', end_datetime='2026-01-06T10:00:00')
    config['departments'][0].update(operating_start_time='09:00', operating_end_time='10:00',
        bed_count=1, waste={'alpha': 0.6, 'pickup_location': 'A', 'dropoff_location': 'B'})
    config['waste_streams'][0].update(container_capacity_m3=1, full_threshold_fraction=0.2)
    return config


class WasteConservationTests(unittest.TestCase):
    def test_effective_department_capacity_and_fraction_determine_threshold(self):
        config = dynamic_config()
        config['departments'][0]['waste_streams'][0].update(container_capacity_m3=2, full_threshold_fraction=0.5)
        for data in (config, JsonStore(config).data):
            sim = Simulation(data)
            records = sim.task_generation_manager.update_until(3600)
            self.assertEqual(1, len(records))
            self.assertAlmostEqual(1, records[0].task.waste_volume_m3)
            rule = active_rule(data)
            self.assertAlmostEqual(1, rule['effective_config']['threshold_volume_m3'])

    def test_explicit_threshold_wins_over_capacity_and_fraction(self):
        config = dynamic_config()
        config['departments'][0]['waste_streams'][0].update(container_capacity_m3=2, full_threshold_fraction=0.5, threshold_volume_m3=0.25)
        records = Simulation(config).task_generation_manager.update_until(3600)
        self.assertEqual(4, len(records))
        self.assertAlmostEqual(1, sum(r.task.waste_volume_m3 for r in records))

    def test_shared_contributors_conserve_one_combined_volume(self):
        config = dynamic_config()
        config['waste_streams'][0].update(container_capacity_m3=1, full_threshold_fraction=0.5)
        config['task_generation']['categories']['waste']['base_daily_volume_m3'] = 7.2
        config['departments'][0]['waste_streams'][0].update(shared_container_group='BIN')
        other = copy.deepcopy(config['departments'][0]); other.update(id='E', name='Other')
        config['departments'].append(other)
        config['task_generation']['categories']['waste']['department_groups'][0]['departments'].append('E')
        sim = Simulation(config)
        records = sim.task_generation_manager.update_until(3600)
        state = sim.task_generation_manager.generators[0].runtime['shared:BIN']
        self.assertEqual(1, len(records))
        self.assertAlmostEqual(0.5, records[0].task.waste_volume_m3)
        self.assertAlmostEqual(0.1, state['volume'])  # .3 + .3 = .5 collected + .1 remaining
        self.assertEqual(2, len(state['contributors']))

    def test_separate_department_bins_do_not_share_subthreshold_volume(self):
        config = dynamic_config()
        config['waste_streams'][0].update(container_capacity_m3=1, full_threshold_fraction=0.5)
        config['task_generation']['categories']['waste']['base_daily_volume_m3'] = 7.2
        other = copy.deepcopy(config['departments'][0]); other.update(id='E', name='Other')
        config['departments'].append(other)
        config['task_generation']['categories']['waste']['department_groups'][0]['departments'].append('E')
        sim = Simulation(config)
        self.assertEqual([], sim.task_generation_manager.update_until(3600))
        states = sim.task_generation_manager.generators[0].runtime
        self.assertEqual(2, len(states))
        self.assertTrue(all(abs(state['volume'] - 0.3) < 1e-10 for state in states.values()))

    def test_legacy_closing_poll_preserves_fill_and_total_until_open(self):
        sim = Simulation(legacy_config())
        manager = sim.task_generation_manager
        self.assertEqual([], manager.update_until(7200))
        state = manager.generators[0].runtime['D']['General']
        self.assertAlmostEqual(0.6, state['fill_m3'])
        self.assertAlmostEqual(0.6, state['generated_m3_total'])
        records = manager.update_until(90000)
        self.assertEqual(3, len(records))
        self.assertEqual(3, state['tasks_created'])
        self.assertAlmostEqual(0.6, sum(r.task.waste_volume_m3 for r in records) + state['fill_m3'])
        self.assertEqual([], manager.update_until(90000))

    def test_legacy_invalid_destination_does_not_destroy_volume_or_count_a_task(self):
        config = legacy_config()
        config['departments'][0]['operating_end_time'] = '12:00'
        config['departments'][0]['waste']['dropoff_location'] = 'Missing'
        sim = Simulation(config)
        self.assertEqual([], sim.task_generation_manager.update_until(7200))
        state = sim.task_generation_manager.generators[0].runtime['D']['General']
        self.assertAlmostEqual(0.6, state['fill_m3'])
        self.assertEqual(0, state['tasks_created'])

    def test_legacy_settings_survive_plain_editor_import(self):
        config = legacy_config()
        restored = JsonStore(config).data
        self.assertEqual({'enabled': True, 'priority': 37}, restored['task_generation']['department_waste'])
        sim = Simulation(restored)
        records = sim.task_generation_manager.update_until(90000)
        self.assertEqual(3, len(records))
        self.assertTrue(all(r.task.priority == 37 for r in records))

    def test_dynamic_invalid_destination_retains_threshold_volume(self):
        config = dynamic_config()
        config['task_generation']['categories']['waste']['dropoff_location'] = 'Missing'
        sim = Simulation(config)
        self.assertEqual([], sim.task_generation_manager.update_until(3600))
        state = sim.task_generation_manager.generators[0].runtime['department:D:General']
        self.assertAlmostEqual(1, state['volume'])

    def test_legacy_disabled_flag_and_priority_survive_save_and_reopen(self):
        import tempfile
        from pathlib import Path
        config = legacy_config()
        config['task_generation']['department_waste']['enabled'] = False
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'project.json'
            JsonStore(config).save(str(path))
            restored = JsonStore.from_file(str(path)).data
        self.assertEqual({'enabled': False, 'priority': 37}, restored['task_generation']['department_waste'])
        self.assertEqual([], Simulation(restored).task_generation_manager.generators)

    def test_missing_waste_overrides_use_global_threshold(self):
        config = dynamic_config()
        records = Simulation(config).task_generation_manager.update_until(3600)
        self.assertEqual(2, len(records))
        self.assertTrue(all(abs(r.task.waste_volume_m3 - 0.4) < 1e-10 for r in records))

    def test_global_and_department_waste_dimensions_reject_invalid_scalars(self):
        for field, values in [('container_capacity_m3', [0, -1, True, 'nan']),
                              ('full_threshold_fraction', [0, 1.1, -1, False, 'inf'])]:
            for value in values:
                for department in (False, True):
                    config = dynamic_config()
                    row = config['departments'][0]['waste_streams'][0] if department else config['waste_streams'][0]
                    row[field] = value
                    for consumer in (Simulation, JsonStore):
                        with self.assertRaisesRegex(ValueError, field):
                            consumer(config)

    def test_shared_and_initial_flags_reject_ambiguous_strings(self):
        for field in ('shared_container', 'initial_container_present'):
            config = dynamic_config()
            config['departments'][0]['waste_streams'][0][field] = 'false'
            with self.assertRaisesRegex(ValueError, field):
                Simulation(config)


if __name__ == '__main__':
    unittest.main()
