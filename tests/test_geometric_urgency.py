"""Access urgency is independent of a task's estimated completion time.

Exercise the production assignment selector with explicit feasible-route costs.
Geometry and battery feasibility are supplied as candidate-estimator results so
the expected scheduling order does not depend on the routing implementation.
"""
import unittest
from types import SimpleNamespace

from simulator import Simulation


def task(identifier, priority, release=0):
    return SimpleNamespace(id=identifier, priority=priority, release_time=release,
                           dropoff='Destination')


def selector(tasks, finishes, *, detailed=True, robot_ids=('R1',)):
    sim = Simulation.__new__(Simulation)
    sim.geometric_traffic = detailed
    sim.current_time = 100
    sim.max_single_candidate_tasks = 100
    sim.pending_tasks = [(t.priority, t.release_time, index, t)
                         for index, t in enumerate(tasks)]
    sim.amrs = [SimpleNamespace(id=name, is_charging=False) for name in robot_ids]
    sim._pending_task_removed = lambda _task: False
    sim._multi_stop_task_is_eligible = lambda _task: False
    sim._multi_stop_batch_for_amr = lambda _amr, _tasks: None
    sim._needs_post_task_recharge = lambda _amr: False
    sim._task_requires_existing_payload_instance = lambda _task: False
    sim._payload_for_task = lambda _task: None
    sim._task_prefers_multi_stop_amr = lambda _task: False
    sim._task_allowed_for_amr = lambda _task, _amr: True

    def estimates(jobs):
        for job in jobs:
            value = finishes.get((job['task_or_tasks'].id, job['amr'].id))
            yield job, None if value is None else {'finish_time': value}

    sim._estimate_candidate_jobs = estimates
    return sim


class GeometricUrgencyTests(unittest.TestCase):
    def test_more_urgent_slower_task_precedes_less_urgent_fast_task(self):
        urgent, routine = task('Urgent', 1), task('Routine', 100)
        sim = selector([routine, urgent], {('Urgent', 'R1'): 300,
                                          ('Routine', 'R1'): 110})
        self.assertIs(urgent, sim._select_best_assignment()[1])

    def test_infeasible_urgent_task_does_not_block_feasible_routine_work(self):
        urgent, routine = task('Urgent', 1), task('Routine', 100)
        sim = selector([urgent, routine], {('Routine', 'R1'): 110})
        self.assertIs(routine, sim._select_best_assignment()[1])

    def test_equal_priority_selects_longest_waiting_not_fastest_finish(self):
        old, recent = task('Old', 10, 0), task('Recent', 10, 90)
        sim = selector([recent, old], {('Old', 'R1'): 300,
                                      ('Recent', 'R1'): 110})
        self.assertIs(old, sim._select_best_assignment()[1])

    def test_equal_priority_and_release_preserve_queue_insertion_order(self):
        first, second = task('First', 10), task('Second', 10)
        sim = selector([first, second], {('First', 'R1'): 300,
                                        ('Second', 'R1'): 110})
        self.assertIs(first, sim._select_best_assignment()[1])

    def test_fastest_feasible_robot_is_selected_for_the_urgent_task(self):
        urgent, routine = task('Urgent', 1), task('Routine', 100)
        sim = selector([routine, urgent], {
            ('Urgent', 'R1'): 300, ('Urgent', 'R2'): 250,
            ('Routine', 'R1'): 110, ('Routine', 'R2'): 120,
        }, robot_ids=('R1', 'R2'))
        robot, selected, estimate = sim._select_best_assignment()
        self.assertIs(urgent, selected)
        self.assertEqual('R2', robot.id)
        self.assertEqual(250, estimate['finish_time'])

    def test_simple_mode_retains_existing_earliest_finish_comparison(self):
        urgent, routine = task('Urgent', 1), task('Routine', 100)
        sim = selector([urgent, routine], {('Urgent', 'R1'): 300,
                                          ('Routine', 'R1'): 110}, detailed=False)
        self.assertIs(routine, sim._select_best_assignment()[1])

    def charge_selector(self, tasks, finishes, *, detailed=True, robot_ids=('R1',)):
        sim = selector(tasks, {}, detailed=detailed, robot_ids=robot_ids)

        def estimates(jobs):
            for job in jobs:
                yield job, {'_requires_route_charge': True,
                            'required_energy_kwh': 2.0}

        def charge_option(robot, selected, request):
            self.assertEqual(2.0, request['required_energy_kwh'])
            finish = finishes.get((selected.id, robot.id))
            return None if finish is None else {
                '_requires_route_charge': True, 'finish_time': finish,
                'target_charge_location': 'Charger',
            }

        sim._estimate_candidate_jobs = estimates
        sim._required_route_charge_option = charge_option
        return sim

    def test_charging_only_more_urgent_slower_task_has_priority(self):
        urgent, routine = task('Urgent', 1), task('Routine', 100)
        sim = self.charge_selector([routine, urgent], {
            ('Urgent', 'R1'): 500, ('Routine', 'R1'): 150})
        self.assertIs(urgent, sim._select_best_assignment()[1])

    def test_charging_only_infeasible_urgent_task_does_not_block_routine(self):
        urgent, routine = task('Urgent', 1), task('Routine', 100)
        sim = self.charge_selector([urgent, routine], {('Routine', 'R1'): 150})
        self.assertIs(routine, sim._select_best_assignment()[1])

    def test_charging_only_equal_priority_serves_longest_waiting(self):
        old, recent = task('Old', 10, 0), task('Recent', 10, 90)
        sim = self.charge_selector([recent, old], {
            ('Old', 'R1'): 500, ('Recent', 'R1'): 150})
        self.assertIs(old, sim._select_best_assignment()[1])

    def test_charging_only_urgent_task_uses_fastest_feasible_robot(self):
        urgent, routine = task('Urgent', 1), task('Routine', 100)
        sim = self.charge_selector([routine, urgent], {
            ('Urgent', 'R1'): 500, ('Urgent', 'R2'): 400,
            ('Routine', 'R1'): 150, ('Routine', 'R2'): 200,
        }, robot_ids=('R1', 'R2'))
        robot, selected, estimate = sim._select_best_assignment()
        self.assertIs(urgent, selected)
        self.assertEqual('R2', robot.id)
        self.assertEqual(400, estimate['finish_time'])

    def test_charging_only_simple_mode_retains_earliest_finish(self):
        urgent, routine = task('Urgent', 1), task('Routine', 100)
        sim = self.charge_selector([urgent, routine], {
            ('Urgent', 'R1'): 500, ('Routine', 'R1'): 150}, detailed=False)
        self.assertIs(routine, sim._select_best_assignment()[1])


if __name__ == '__main__':
    unittest.main()
