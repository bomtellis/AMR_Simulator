"""Explicit staff choices override legacy Stores fallback without losing omission."""
import contextlib
import io
import unittest

from amr_sim_models import Task
from simulator import Simulation
from tests.test_engineering_reference import reference_config
from tests.test_generation_contracts import return_config
from visualiser.models import JsonStore


class StaffRequirementTests(unittest.TestCase):
    def test_direct_task_distinguishes_omission_false_and_true(self):
        sim = Simulation(reference_config())
        self.assertIsNotNone(sim._task_staff_handling_config(Task('T', 'A', 'B', 'Box', labels=['stores'])))
        self.assertIsNone(sim._task_staff_handling_config(Task('T', 'A', 'B', 'Box', labels=['stores'], requires_staff=False)))
        self.assertIsNotNone(sim._task_staff_handling_config(Task('T', 'A', 'B', 'Box', requires_staff=True)))
        self.assertIsNone(sim._task_staff_handling_config(Task('T', 'A', 'B', 'Box')))

    def test_import_preserves_unspecified_choice_across_repeated_roundtrips(self):
        cfg = return_config()
        for _ in range(3):
            cfg = JsonStore(cfg).data
            self.assertNotIn('requires_staff', cfg['task_generation']['categories']['stores'])
        cfg['task_generation']['categories']['stores']['requires_staff'] = False
        self.assertIs(False, JsonStore(cfg).data['task_generation']['categories']['stores']['requires_staff'])
        self.assertIs(True, JsonStore().data['task_generation']['categories']['stores']['requires_staff'])

    def test_generated_returns_and_staff_records_obey_effective_choice(self):
        for normalise in (False, True):
            for choice, expected_start, assignments in [(None, '00:04:09.000', 1),
                                                         (False, '00:02:09.000', 0),
                                                         (True, '00:04:09.000', 1)]:
                with self.subTest(editor=normalise, choice=choice):
                    cfg = return_config()
                    cfg['task_generation']['staff_config'] = {'enabled': True, 'shift_patterns': {
                        'none': {'start_time': '00:00', 'end_time': '24:00', 'days_active': ['mon']}}}
                    category = cfg['task_generation']['categories']['stores']
                    category.update(staff_handling_minutes=3, staff_shift_pattern='none')
                    if choice is not None:
                        category['requires_staff'] = choice
                    if normalise:
                        cfg = JsonStore(cfg).data
                    with contextlib.redirect_stdout(io.StringIO()):
                        sim = Simulation(cfg, verbose=True)
                        sim.run()
                    self.assertFalse(sim.failed_tasks)
                    self.assertEqual(2, len(sim.completed_task_records))
                    self.assertEqual('2026-01-05 '+expected_start, sim.completed_task_records[1]['start_datetime'])
                    records = [r for r in sim.verbose_rows if r['event_type'] in
                               {'staff_payload_handling', 'staff_payload_exchange'}]
                    self.assertEqual(assignments, len(records))
                    if assignments:
                        self.assertEqual(180, records[0]['duration_sec'])

    def test_group_false_overrides_category_true_and_legacy_stores(self):
        cfg = return_config()
        category = cfg['task_generation']['categories']['stores']
        category['requires_staff'] = True
        category['department_groups'][0]['payload']['requires_staff'] = False
        for data in (cfg, JsonStore(cfg).data):
            sim = Simulation(data)
            task = sim.task_generation_manager.update_until(61)[0].task
            self.assertFalse(task.requires_staff)
            self.assertIsNone(sim._task_staff_handling_config(task))

    def test_static_false_is_respected_during_simulation_loading(self):
        cfg = reference_config()
        cfg['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box', labels=['stores'], requires_staff=False)]
        sim = Simulation(cfg)
        task = sim.events[0].payload.get('task')
        if task is None:
            task = next(e.payload['task'] for e in sim.events if 'task' in e.payload)
        self.assertIsNone(sim._task_staff_handling_config(task))

    def test_zone_handoff_still_requires_staff_when_task_flag_is_false(self):
        cfg = reference_config()
        cfg['locations'].append(dict(name='Final', floor=0, x=10, y=10))
        cfg['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box',
                            requires_staff=False, dropoff_zone='B', final_destination='Final')]
        sim = Simulation(cfg)
        task = next(e.payload['task'] for e in sim.events if 'task' in e.payload)
        self.assertTrue(task.requires_staff)
        self.assertIsNotNone(sim._task_staff_handling_config(task))


if __name__ == '__main__':
    unittest.main()
