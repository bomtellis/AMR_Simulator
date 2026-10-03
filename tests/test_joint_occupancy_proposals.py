"""Proposal views never establish admission and never delete moving history."""
import copy
import math
import unittest

from amr_occupancy_ledger import OccupancyLedger
from amr_trajectories import TrajectoryError
from tests.test_occupancy_ledger import initialise, instantaneous, moving, stationary


class JointOccupancyProposalTests(unittest.TestCase):
    def setUp(self):
        self.ledger = initialise(OccupancyLedger(), 'A', 0)
        self.ledger = initialise(self.ledger, 'B', 6)

    def test_omit_parked_future_preserves_past_and_every_third_party_claim(self):
        before = self.ledger.rows()
        proposed = self.ledger.provisional_without_parked_tail('A', 5)
        a = [r for r in proposed.rows() if r['owner'] == 'A']
        self.assertEqual([(0, 5)], [(r['start'], r['end']) for r in a])
        self.assertEqual([r for r in before if r['owner'] == 'B'],
                         [r for r in proposed.rows() if r['owner'] == 'B'])
        self.assertEqual(before, self.ledger.rows())
        self.assertFalse(any(r['owner'] == 'A' and math.isinf(r['end']) for r in proposed.rows()))

    def test_exact_tail_start_removes_only_tail_preserving_instantaneous_completion(self):
        ledger = self.ledger.replace_plan('A', 3,
            [instantaneous('A', 0, 3, length=2), stationary('A', 0, 3)]).ledger
        view = ledger.provisional_without_parked_tail('A', 3)
        a = [r for r in view.rows() if r['owner'] == 'A']
        self.assertEqual([(0, 3, 'stationary'), (3, 3, 'instantaneous')],
                         [(r['start'], r['end'], r['occupancy_kind']) for r in a])

    def test_omission_cannot_preempt_moving_plan_or_invent_unknown_owner(self):
        ledger = self.ledger.replace_plan('A', 0,
            moving('A', 0, 2, 0)+[stationary('A', 2, 2)]).ledger
        original = ledger.rows()
        for owner, time in [('A', 1), ('A', math.nextafter(2, 0)), ('Missing', 0), ('A', -1), ('A', math.inf)]:
            with self.subTest(owner=owner, time=time), self.assertRaises(TrajectoryError):
                ledger.provisional_without_parked_tail(owner, time)
        self.assertEqual(original, ledger.rows())
        at_arrival = ledger.provisional_without_parked_tail('A', 2)
        self.assertEqual([r for r in original if not (r['owner'] == 'A' and math.isinf(r['end']))], at_arrival.rows())

    def test_provisional_replacement_can_overlap_old_partner_tail_but_is_not_admission(self):
        plan = moving('A', 0, 6, 0)+[stationary('A', 6, 6)]
        source = copy.deepcopy(plan)
        self.assertFalse(self.ledger.replace_plan('A', 0, plan).accepted)
        view = self.ledger.provisional_replace_plan('A', 0, plan)
        self.assertEqual(source, plan)
        self.assertEqual([list(point) for point in plan[-1]['polygon']],
                         [r for r in view.rows() if r['owner'] == 'A'][-1]['polygon'])
        self.assertEqual([r for r in self.ledger.rows() if r['owner'] == 'B'],
                         [r for r in view.rows() if r['owner'] == 'B'])
        # A final joint check still catches a partner which did not actually move.
        rejected = self.ledger.replace_plans({'A': (0, plan), 'B': (0, [stationary('B', 6, 0)])})
        self.assertFalse(rejected.accepted)
        self.assertIs(self.ledger, rejected.ledger)

    def test_provisional_replacement_preserves_history_and_rejects_malformed_coverage(self):
        plan = moving('A', 0, 2, 3)+[stationary('A', 2, 5)]
        view = self.ledger.provisional_replace_plan('A', 3, plan)
        initial = next(r for r in view.rows() if r['owner'] == 'A')
        self.assertEqual((0, 3), (initial['start'], initial['end']))
        for owner, start, rows in [('Unknown', 0, [stationary('Unknown', 0, 0)]),
                                 ('A', 0, []), ('A', 0, [stationary('A', 0, 1)]),
                                 ('A', 0, [stationary('B', 0, 0)])]:
            with self.subTest(owner=owner, start=start), self.assertRaises(TrajectoryError):
                self.ledger.provisional_replace_plan(owner, start, rows)
        committed = self.ledger.replace_plan('A', 0,
            moving('A', 0, 2, 0)+[stationary('A', 2, 2)]).ledger
        with self.assertRaises(TrajectoryError):
            committed.provisional_replace_plan('A', .1, [stationary('A', .1, .1)])


if __name__ == '__main__':
    unittest.main()
