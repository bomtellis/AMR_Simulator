import contextlib
import io
import unittest
from types import SimpleNamespace

from amr_sim_models import Event, Task
from simulator import Simulation
from tests import test_dropoff_zones


class TaskDeferralTests(unittest.TestCase):
    @staticmethod
    def config(limit=1.0, generated=False):
        config = test_dropoff_zones.DropoffZoneTests._config()
        config["simulation"]["max_task_deferral_minutes"] = limit
        config["task_generation"]["enabled"] = generated
        return config

    @staticmethod
    def run_sim(sim):
        with contextlib.redirect_stdout(io.StringIO()):
            sim.run()

    @staticmethod
    def task(task_id="T1", release=120.0):
        return Task(task_id, "Store", "Zone", "Trolley", release_time=release)

    def test_busy_amr_task_fails_at_deadline_and_is_not_released_again(self):
        sim = Simulation(self.config(), verbose=True)
        task = self.task()
        sim.amrs[0].available_time = 600
        sim.amrs[0].exchange_hold_until = 600
        sim.schedule_task_release(task)
        self.run_sim(sim)
        failures = [r for r in sim.verbose_rows if r["event_type"] == "task_failed"]
        self.assertEqual(1, len(failures))
        self.assertEqual(180.0, failures[0]["sim_time_sec"])
        self.assertIn("Task deferral limit exceeded (1 min)", failures[0]["details"])
        self.assertIn("waited 60 s", failures[0]["details"])
        self.assertFalse(sim.completed_task_records)
        self.assertFalse(sim._task_deferrals)
        count = len(sim.verbose_rows)
        sim._handle_event(Event(600, 9999, "task_release", {"task": task}))
        self.assertFalse(any(r["event_type"] == "task_released" for r in sim.verbose_rows[count:]))

    def test_unlimited_preserves_long_wait(self):
        config = self.config()
        del config["simulation"]["max_task_deferral_minutes"]
        sim = Simulation(config, verbose=True)
        sim.amrs[0].available_time = 600
        sim.amrs[0].exchange_hold_until = 600
        sim.schedule_task_release(self.task())
        self.assertFalse(any(e.event_type == "task_deferral_timeout" for e in sim.events))
        self.run_sim(sim)
        self.assertFalse(sim.failed_task_ids)
        self.assertEqual(1, len(sim.completed_task_records))

    def test_assignment_cancels_timer_without_extending_simulation(self):
        sims = []
        for limit in (0, 1000):
            sim = Simulation(self.config(limit), verbose=True)
            sim.schedule_task_release(self.task())
            self.run_sim(sim)
            self.assertFalse(sim.failed_task_ids)
            self.assertEqual(1, len(sim.completed_task_records))
            self.assertFalse(sim._task_deferrals)
            sims.append(sim)
        self.assertEqual(sims[0].current_time, sims[1].current_time)

    def test_assignment_at_exact_deadline_fails_even_with_earlier_wait_event(self):
        sim = Simulation(self.config(), verbose=True)
        sim.amrs[0].available_time = 180
        sim.amrs[0].exchange_hold_until = 180
        sim.push_event(180, "assignment_continue", {})
        sim.schedule_task_release(self.task())
        self.run_sim(sim)
        self.assertEqual({"T1"}, sim.failed_task_ids)
        self.assertFalse(sim.completed_task_records)

    def test_released_from_deferral_keeps_original_deadline(self):
        sim = Simulation(self.config(), verbose=True)
        task = self.task()
        task.generator_scheduled_release_time = 120
        task.generator_release_spacing_key = "dropoff:Zone"
        sim._start_task_deferral_limit(task)
        sim._schedule_generated_task_record(
            SimpleNamespace(task=task, released_from_deferral=True),
            release_time_override=150,
        )
        sim.amrs[0].available_time = 600
        sim.amrs[0].exchange_hold_until = 600
        self.run_sim(sim)
        failure = next(r for r in sim.verbose_rows if r["event_type"] == "task_failed")
        self.assertEqual(180, failure["sim_time_sec"])
        self.assertEqual(150, task.release_time)

    def test_queued_generated_timeout_does_not_resurrect_after_return_pickup(self):
        config = self.config(generated=True)
        category = config["task_generation"]["categories"]["stores"]["departments"]["D1"]
        category.update(scheduled_times=["00:01", "00:02", "00:03"],
                        release_next_after_return_pickup=True, staff_handling_minutes=5)
        sim = Simulation(config, verbose=True)
        self.run_sim(sim)
        deferred = [r for r in sim.verbose_rows if r["event_type"] == "task_release_deferred"]
        self.assertEqual(2, len(deferred))
        self.assertEqual({r["task_id"] for r in deferred}, sim.failed_task_ids)
        for row in deferred:
            task_rows = [r for r in sim.verbose_rows if r.get("task_id") == row["task_id"]]
            failures = [r for r in task_rows if r["event_type"] == "task_failed"]
            self.assertEqual(1, len(failures))
            self.assertEqual(row["sim_time_sec"] + 60, failures[0]["sim_time_sec"])
            self.assertFalse(any(r["event_type"] in ("task_released", "task_deferred_released") for r in task_rows))
        # The already-assigned delivery and its later collection both complete.
        self.assertEqual(2, len(sim.completed_task_records))
        self.assertTrue(any(r["event_type"] == "return_payload_picked_up" for r in sim.verbose_rows))

    def test_return_timer_starts_at_own_release_not_outbound_schedule(self):
        sim = Simulation(self.config(), verbose=True)
        task = self.task("RETURN", release=600)
        task.is_return_task = True
        task.generator_scheduled_release_time = 60
        sim.amrs[0].available_time = 900
        sim.amrs[0].exchange_hold_until = 900
        sim.schedule_task_release(task)
        self.run_sim(sim)
        failure = next(r for r in sim.verbose_rows if r["event_type"] == "task_failed")
        self.assertEqual(660, failure["sim_time_sec"])

    def test_idle_parking_excluded(self):
        sim = Simulation(self.config())
        task = self.task()
        task.is_idle_return = True
        sim.schedule_task_release(task)
        self.assertFalse(sim._task_deferrals)

    def test_invalid_limits_rejected(self):
        for limit in (-1, float("nan"), float("inf")):
            with self.subTest(limit=limit), self.assertRaisesRegex(ValueError, "max_task_deferral_minutes"):
                Simulation(self.config(limit))


if __name__ == "__main__":
    unittest.main()
