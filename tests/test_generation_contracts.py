"""Independent effective-rule and completion-relative return expectations."""
import contextlib
import copy
import io
import unittest

from amr_demand_preview import build_demand_preview
from simulator import Simulation
from tests.test_generation_reference import grouped_config
from tests.test_route_profiles import profile_config
from visualiser.models import JsonStore


def return_config():
    cfg = profile_config()
    grouped = grouped_config()
    cfg['departments'] = grouped['departments']
    cfg['task_generation'] = grouped['task_generation']
    cfg['simulation']['task_release_stagger_sec'] = 0
    cfg['task_generation']['categories']['stores'].update(
        route_profile='clean', return_enabled=True, return_payload='Box', return_delay_minutes=1)
    return cfg


class GenerationContractTests(unittest.TestCase):
    def records(self, cfg):
        return Simulation(cfg).task_generation_manager.update_until(600)

    def test_empty_group_schedule_replaces_category_schedule(self):
        cfg = grouped_config()
        cfg['task_generation']['categories']['stores']['department_groups'][0]['payload']['scheduled_times'] = []
        self.assertEqual([], self.records(cfg))
        self.assertEqual(0, build_demand_preview(cfg)['totals']['planned_task_records'])

    def test_disabled_group_suppresses_standalone_department_and_category_default(self):
        cfg = grouped_config()
        cat = cfg['task_generation']['categories']['stores']
        cat['departments'] = {'D': {'enabled': True, 'scheduled_times': ['00:02']}}
        cat['department_groups'][0]['payload']['enabled'] = False
        self.assertEqual([], self.records(cfg))

    def test_enabled_department_overrides_disabled_category_default(self):
        cfg = grouped_config(enabled=False)
        cat = cfg['task_generation']['categories']['stores']
        cat.pop('department_groups')
        cat['departments'] = {'D': {'enabled': True, 'priority': 9, 'scheduled_times': ['00:02']}}
        records = self.records(cfg)
        self.assertEqual([(120, 9)], [(r.task.release_time, r.task.priority) for r in records])

    def test_group_schedule_and_return_settings_replace_category_values(self):
        cfg = return_config()
        group = cfg['task_generation']['categories']['stores']['department_groups'][0]['payload']
        group.update(scheduled_times=['00:02'], return_delay_minutes=2, return_priority=3, return_route_profile='dirty')
        records = self.records(cfg)
        self.assertEqual(1, len(records))
        task = records[0].task
        self.assertEqual((120, 7, 2, 3, 'dirty'), (task.release_time, task.priority,
            task.return_delay_minutes, task.return_priority, task.return_route_profile))

    def test_generated_return_omission_inherits_but_explicit_blank_remains_blank(self):
        for value, expected in [(None, 'clean'), ('', ''), ('dirty', 'dirty')]:
            cfg = return_config()
            if value is not None:
                cfg['task_generation']['categories']['stores']['return_route_profile'] = value
            task = self.records(cfg)[0].task
            self.assertEqual(expected, task.return_route_profile)
            self.assertEqual(7, task.return_priority)

    def test_return_delay_starts_at_arrival_and_profile_controls_return_duration(self):
        for normalise in (False, True):
            for profile, seconds in [(None, 9), ('', 4.5), ('dirty', 11)]:
                with self.subTest(editor=normalise, profile=profile):
                    cfg = return_config()
                    if profile is not None:
                        cfg['task_generation']['categories']['stores']['return_route_profile'] = profile
                    if normalise:
                        cfg = JsonStore(copy.deepcopy(cfg)).data
                    with contextlib.redirect_stdout(io.StringIO()):
                        sim = Simulation(cfg, verbose=True)
                        sim.run()
                    self.assertFalse(sim.failed_task_ids)
                    self.assertEqual(2, len(sim.completed_task_records))
                    outward, returned = sim.completed_task_records
                    # Outbound release 60 + service 4 + clean travel 10/2 = 69.
                    # Return release is arrival 69 + 1 minute = 129, not 120.
                    self.assertEqual('2026-01-05 00:01:09.000', outward['finish_datetime'])
                    self.assertEqual('2026-01-05 00:02:09.000', returned['start_datetime'])
                    self.assertEqual(seconds, returned['duration_sec'])

    def test_generated_return_without_payload_is_not_invented(self):
        cfg = return_config()
        cfg['task_generation']['categories']['stores'].pop('return_payload')
        self.assertFalse(self.records(cfg)[0].task.return_enabled)

    def test_import_does_not_add_staff_but_new_project_template_retains_it(self):
        cfg = return_config()
        self.assertFalse(self.records(cfg)[0].task.requires_staff)
        self.assertFalse(self.records(JsonStore(cfg).data)[0].task.requires_staff)
        self.assertEqual(0, self.records(JsonStore(cfg).data)[0].task.staff_handling_minutes)
        self.assertTrue(JsonStore().data['task_generation']['categories']['stores']['requires_staff'])
        self.assertEqual(15, JsonStore().data['task_generation']['categories']['stores']['staff_handling_minutes'])
        cfg['task_generation']['categories']['stores']['requires_staff'] = True
        cfg['task_generation']['categories']['stores']['staff_handling_minutes'] = 3
        self.assertTrue(self.records(JsonStore(cfg).data)[0].task.requires_staff)
        self.assertEqual(3, self.records(JsonStore(cfg).data)[0].task.staff_handling_minutes)

    def test_group_staff_settings_override_imported_category_defaults(self):
        cfg = return_config()
        cfg['task_generation']['categories']['stores']['department_groups'][0]['payload'].update(
            requires_staff=True, staff_handling_minutes=2)
        task = self.records(JsonStore(cfg).data)[0].task
        self.assertTrue(task.requires_staff)
        self.assertEqual(2, task.staff_handling_minutes)


if __name__ == '__main__':
    unittest.main()
