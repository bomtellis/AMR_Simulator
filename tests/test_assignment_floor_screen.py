"""Necessary lift connectivity is screened without declaring task failure."""
import unittest
from unittest.mock import patch

from amr_sim_models import Task
from simulator import Simulation
from verification.workload import workload_config


class AssignmentFloorScreenTests(unittest.TestCase):
    def setUp(self):
        config = workload_config(floors=2,robots_per_floor=1,tasks_per_day=1,days=1)
        config['tasks'] = []
        self.sim = Simulation(config)
        self.robot = self.sim.amrs[0]
        self.task = Task('T','Source-1','Destination-1','Trolley')

    def test_missing_or_worn_lifts_block_only_cross_floor_approach(self):
        for lift in self.sim.lifts:
            lift.health_percent = 19.95
        self.assertFalse(self.sim._candidate_can_reach_pickup_floor(self.robot,self.task,{}))
        self.robot.location_name = 'Source-1'
        self.assertTrue(self.sim._candidate_can_reach_pickup_floor(self.robot,self.task,{}))
        self.sim.lifts = []
        self.robot.location_name = 'Source-0'
        self.assertFalse(self.sim._candidate_can_reach_pickup_floor(self.robot,self.task,{}))

    def test_exact_health_threshold_and_temporary_repairs_remain_candidates(self):
        for lift in self.sim.lifts:
            lift.health_percent = 20
            lift.failed_until = 99999
            lift.available_time = 99999
        self.assertTrue(self.sim._candidate_can_reach_pickup_floor(self.robot,self.task,{}))

    def test_filter_does_not_decide_loaded_leg_or_idle_return_routes(self):
        self.sim.lifts = []
        task = Task('Loaded','Source-0','Destination-1','Trolley')
        self.assertTrue(self.sim._candidate_can_reach_pickup_floor(self.robot,task,{}))
        self.task.is_idle_return = True
        self.assertTrue(self.sim._candidate_can_reach_pickup_floor(self.robot,self.task,{}))

    def test_selection_skips_stranded_robot_then_rechecks_health_next_pass(self):
        self.sim.amrs = [self.robot]
        self.sim._queue_pending_task(self.task)
        for lift in self.sim.lifts:
            lift.health_percent = 19.95
        with patch.object(self.sim,'_estimate_task_for_amr_cached',return_value={'finish_time':100}) as estimate:
            self.assertIsNone(self.sim._select_best_assignment())
            estimate.assert_not_called()
            self.assertFalse(self.sim.failed_tasks)
            self.sim.lifts[0].health_percent = 100
            choice = self.sim._select_best_assignment()
            self.assertIs(self.task,choice[1])
            self.assertEqual(1,estimate.call_count)

    def test_same_floor_task_beyond_blocked_window_is_still_selected(self):
        self.sim.amrs = [self.robot]
        self.sim.lifts = []
        self.sim.max_single_candidate_tasks = 1
        self.sim._queue_pending_task(self.task)
        local = Task('Local','Source-0','Destination-0','Trolley')
        self.sim._queue_pending_task(local)
        chosen = self.sim._select_best_assignment()
        self.assertIsNotNone(chosen)
        self.assertIs(local,chosen[1])
