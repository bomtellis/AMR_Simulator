"""Reference schedules: each active rule emits exactly one task at 00:01."""
import copy
import unittest

from simulator import Simulation
from tests.test_engineering_reference import reference_config


def grouped_config(enabled=True):
    config = reference_config()
    config["departments"] = [{"id": "D", "name": "Department", "enabled": True,
                              "operating_start_time": "00:00", "operating_end_time": "24:00"}]
    config["task_generation"] = {"enabled": True, "categories": {"stores": {
        "enabled": enabled, "generation_mode": "scheduled", "scheduled_times": ["00:01"],
        "pickup_location": "A", "dropoff_location": "B", "payload": "Box",
        "priority": 40, "dropoff_zone_capacity_policy": "wait_for_space",
        "department_groups": [{"id": "G", "departments": ["D"],
                               "payload": {"enabled": True, "priority": 7}}],
    }}}
    return config


class GenerationReferenceTests(unittest.TestCase):
    def records(self, config):
        manager = Simulation(config).task_generation_manager
        return manager, manager.update_until(61)

    def test_group_does_not_also_generate_category_default_task(self):
        _manager, records = self.records(grouped_config())
        self.assertEqual(1, len(records))
        self.assertEqual("D", records[0].task.department_id)
        self.assertEqual(60, records[0].task.release_time)

    def test_enabled_group_runs_when_category_default_is_disabled(self):
        _manager, records = self.records(grouped_config(enabled=False))
        self.assertEqual(1, len(records))

    def test_global_disabled_prevents_group_generation(self):
        config = grouped_config()
        config["task_generation"]["enabled"] = False
        self.assertEqual([], self.records(config)[1])

    def test_group_override_wins_and_category_wide_policy_is_preserved(self):
        config = grouped_config()
        category = config["task_generation"]["categories"]["stores"]
        category["departments"] = {"D": {"enabled": True, "priority": 99}}
        category["department_groups"][0]["payload"]["dropoff_zone_capacity_policy"] = "allow_temporary_overflow"
        manager, records = self.records(config)
        self.assertEqual(1, len(records))
        self.assertEqual(7, records[0].task.priority)
        self.assertEqual("wait_for_space", records[0].task.dropoff_zone_capacity_policy)
        self.assertEqual([], manager.update_until(61))  # polling does not re-emit

    def test_two_groups_are_two_deliberate_services(self):
        config = grouped_config(enabled=False)
        category = config["task_generation"]["categories"]["stores"]
        second = copy.deepcopy(category["department_groups"][0])
        second["id"] = "G2"
        second["payload"]["scheduled_times"] = ["00:02"]
        category["department_groups"].append(second)
        manager = Simulation(config).task_generation_manager
        records = manager.update_until(121)
        self.assertEqual([60, 120], sorted(r.task.release_time for r in records))
        self.assertEqual(2, len({r.task.id for r in records}))

    def test_enabled_waste_group_suppresses_legacy_generator(self):
        config = grouped_config(enabled=False)
        config["task_generation"]["categories"]["waste"] = config["task_generation"]["categories"].pop("stores")
        config["waste_streams"] = [{"name": "General", "payload": "Box"}]
        manager = Simulation(config).task_generation_manager
        self.assertEqual(["dynamic_category"], [g.generator_type for g in manager.generators])


if __name__ == "__main__":
    unittest.main()
