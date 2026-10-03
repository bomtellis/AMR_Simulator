"""Rejected joint admission publishes no blocker-only movement or evidence."""
import contextlib
import copy
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from amr_occupancy_ledger import OccupancyLedger, PlanUpdate
from amr_sim_models import Task
from simulator import Simulation
from tests.test_geometric_yielding import yielding_config
from tests.test_route_reservation_atomicity import resource_state


def event_payload(value):
    # Pending reasons/estimate diagnostics may change; an existing task event
    # must still reference the same task identity and retain its schedule.
    if isinstance(value, Task):
        return ('task', value.id)
    if isinstance(value, dict):
        return {key: event_payload(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [event_payload(item) for item in value]
    return copy.deepcopy(value)


def state(sim):
    return copy.deepcopy(dict(
        robots=[vars(robot) for robot in sim.amrs],
        resources=resource_state(sim),
        legacy_geometric_claims=dict(sim.geometric_route_reservations),
        events=[(event.time, event.priority, event.event_type, event_payload(event.payload)) for event in sim.events],
        event_counter=sim.event_counter,
        pending=[(priority, release, order, task.id) for priority, release, order, task in sim.pending_tasks],
        charge_intervals=sim.charge_intervals,
        logs=sim.verbose_rows,
        evidence_sequence=sim._evidence_sequence,
        journey_sequence=sim._evidence_journey_sequence,
        task_journeys=sim._task_journeys,
        csv_started=sim._verbose_csv_started,
        csv_rows_written=sim._verbose_rows_written))


class JointAdmissionRollbackTests(unittest.TestCase):
    def prepare(self, csv_path=None):
        sim = Simulation(yielding_config(), verbose=True, verbose_csv_path=csv_path)
        release = next(event for event in sim.events if event.event_type == 'task_release')
        sim._queue_pending_task(release.payload['task'])
        return sim

    def assert_unchanged(self, sim, ledger, previous):
        self.assertIs(ledger, sim.geometric_occupancy)
        self.assertEqual(previous, state(sim))
        self.assertFalse(any(row['event_type'] in ('geometric_yield_started', 'task_assigned')
                             for row in sim.verbose_rows))
        self.assertFalse(any(event.event_type in ('geometric_yield_complete', 'task_complete')
                             for event in sim.events))

    def test_requester_commit_returning_none_does_not_commit_blocker(self):
        sim = self.prepare()
        ledger, previous = sim.geometric_occupancy, state(sim)
        original, injected = sim._estimate_task_for_amr_impl, []

        def reject(amr, task, reserve=False, **kwargs):
            if amr.id == 'R-1' and reserve:
                injected.append(task.id)
                return None
            return original(amr, task, reserve=reserve, **kwargs)

        with patch.object(sim, '_estimate_task_for_amr_impl', side_effect=reject), contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(sim._try_geometric_yield(0))
        self.assertTrue(injected, 'The requester commit must actually be attempted.')
        self.assert_unchanged(sim, ledger, previous)

    def test_failure_after_requester_energy_and_claims_restores_both_robots(self):
        for failure in ('return_none', 'raise'):
            with self.subTest(failure=failure):
                sim = self.prepare()
                ledger, previous = sim.geometric_occupancy, state(sim)
                original, injected = sim._estimate_task_for_amr_impl, []

                def reject_after_commit(amr, task, reserve=False, **kwargs):
                    before_energy = amr.total_energy_used_kwh
                    result = original(amr, task, reserve=reserve, **kwargs)
                    if amr.id == 'R-1' and reserve and result is not None:
                        self.assertGreater(amr.total_energy_used_kwh, before_energy)
                        self.assertTrue(sim.location_reservations)
                        injected.append(task.id)
                        if failure == 'raise':
                            raise RuntimeError('injected after requester energy and reservations')
                        return None
                    return result

                with patch.object(sim, '_estimate_task_for_amr_impl', side_effect=reject_after_commit), \
                     contextlib.redirect_stdout(io.StringIO()):
                    if failure == 'raise':
                        with self.assertRaisesRegex(RuntimeError, 'injected after requester'):
                            sim._try_geometric_yield(0)
                    else:
                        self.assertFalse(sim._try_geometric_yield(0))
                self.assertTrue(injected, 'A real requester reservation must reach the late failure.')
                self.assert_unchanged(sim, ledger, previous)

    def test_final_joint_occupancy_rejection_restores_pre_admission_state(self):
        sim = self.prepare()
        ledger, previous = sim.geometric_occupancy, state(sim)
        original_commit = sim._commit_geometric_yield
        original_replace = OccupancyLedger.replace_plans
        inside_commit, rejected = [], []

        def commit(*args, **kwargs):
            inside_commit.append(True)
            try:
                return original_commit(*args, **kwargs)
            finally:
                inside_commit.pop()

        def reject_joint(current, plans, **kwargs):
            if inside_commit and set(plans) == {'R-1', 'S-1'}:
                rejected.append(tuple(sorted(plans)))
                return PlanUpdate(False, current)
            return original_replace(current, plans, **kwargs)

        with patch.object(sim, '_commit_geometric_yield', side_effect=commit), \
             patch.object(OccupancyLedger, 'replace_plans', autospec=True, side_effect=reject_joint), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(sim._try_geometric_yield(0))
        self.assertTrue(rejected, 'Final two-owner occupancy admission must be exercised.')
        self.assert_unchanged(sim, ledger, previous)

    def test_rejected_admission_never_flushes_fake_yield_rows_to_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'steps.csv'
            sim = self.prepare(str(path))
            sim._flush_verbose_rows_to_csv()
            sim.verbose_row_buffer_size = 1  # Any accidental publication flushes immediately.
            ledger, previous = sim.geometric_occupancy, state(sim)
            original_bytes = path.read_bytes()
            original, injected = sim._estimate_task_for_amr_impl, []

            def reject(amr, task, reserve=False, **kwargs):
                if amr.id == 'R-1' and reserve:
                    injected.append(task.id)
                    return None
                return original(amr, task, reserve=reserve, **kwargs)

            with patch.object(sim, '_estimate_task_for_amr_impl', side_effect=reject), contextlib.redirect_stdout(io.StringIO()):
                self.assertFalse(sim._try_geometric_yield(0))
            self.assertTrue(injected)
            self.assertEqual(original_bytes, path.read_bytes())
            self.assert_unchanged(sim, ledger, previous)


if __name__ == '__main__':
    unittest.main()
