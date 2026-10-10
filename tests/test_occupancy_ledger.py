"""Independent time coverage, atomicity and stationary/moving conflict references."""
import copy
import math
import unittest
from dataclasses import FrozenInstanceError

from amr_geometric_occupancy import stationary_claim
from amr_geometric_traffic import swept_cells
from amr_occupancy_ledger import OccupancyLedger
from amr_trajectories import Pose, TrajectoryError, plan_trajectory


def stationary(owner, x, start, end=math.inf, *, floor=0, gap=0, y=0):
    return {**stationary_claim(Pose(x, y, 0), start=start, end=end, owner=owner,
             length_m=1, width_m=1, robot_clearance_m=gap), 'floor': floor}


def moving(owner, x0, x1, start, *, floor=0, y=0):
    path = plan_trajectory([(x0, y), (x1, y)], minimum_radius_m=1,
                          speed_m_per_sec=1, pivot_allowed=True, pivot_speed_deg_per_sec=45)
    return [{**cell, 'owner': owner, 'floor': floor,
             'start': start+cell['start'], 'end': start+cell['end'],
             'occupancy_kind': 'moving'}
            for cell in swept_cells(path, length_m=1, width_m=1, clearance_m=0)]


def instantaneous(owner, x, time, *, length=1, gap=0, floor=0):
    row = stationary_claim(Pose(x, 0, 0), start=time, end=math.inf,
                           owner=owner, length_m=length, width_m=1, robot_clearance_m=gap)
    row.update(end=time, occupancy_kind='instantaneous', floor=floor)
    return row


def path_plan(owner, points, start):
    path = plan_trajectory(points, minimum_radius_m=.5, speed_m_per_sec=1,
                          pivot_allowed=True, pivot_speed_deg_per_sec=45, start_heading_deg=0)
    cells = [{**cell, 'owner': owner, 'floor': 0,
              'start': start+cell['start'], 'end': start+cell['end'], 'occupancy_kind': 'moving'}
             for cell in swept_cells(path, length_m=1, width_m=1, clearance_m=0)]
    pose = path.motions[-1].end
    tail = stationary_claim(pose, start=start+path.duration_sec, end=math.inf,
                            owner=owner, length_m=1, width_m=1)
    return cells+[{**tail, 'floor': 0}]


def initialise(ledger, owner, x, *, floor=0, gap=0, start=0, y=0):
    result = ledger.initialise(owner=owner, floor=floor, pose=Pose(x, y, 0), start=start,
                               length_m=1, width_m=1, robot_clearance_m=gap)
    assert result.accepted, result.conflicts
    return result.ledger


class OccupancyLedgerTests(unittest.TestCase):
    def test_initial_parked_tail_is_indefinite_and_floor_specific(self):
        empty = OccupancyLedger()
        ledger = initialise(empty, 'R', 0)
        self.assertEqual([], empty.rows())
        self.assertEqual((0, math.inf, 'stationary'),
            (ledger.rows()[0]['start'], ledger.rows()[0]['end'], ledger.rows()[0]['occupancy_kind']))
        ledger = initialise(ledger, 'OtherFloor', 0, floor=1)
        self.assertEqual(1, len(ledger.rows(0)))
        self.assertEqual(1, len(ledger.rows(1)))
        self.assertEqual([], ledger.rows(2))

    def test_initial_overlap_rejected_without_mutating_existing_ledger(self):
        ledger = initialise(OccupancyLedger(), 'Parked', 0)
        result = ledger.initialise(owner='New', floor=0, pose=Pose(.5, 0, 0),
            start=0, length_m=1, width_m=1)
        self.assertFalse(result.accepted)
        self.assertIs(ledger, result.ledger)
        self.assertEqual(('Parked',), result.permanent_blockers)
        self.assertIsNone(result.earliest_release)
        conflict = result.conflicts[0]
        self.assertEqual(('New', 'Parked', 0, 0, math.inf),
                         (conflict.owner, conflict.blocking_owner, conflict.floor, conflict.start, conflict.end))
        self.assertTrue(conflict.permanent)

    def test_replace_preserves_stationary_history_and_adds_every_moving_cell_and_tail(self):
        ledger = initialise(OccupancyLedger(), 'R', 0)
        rows = moving('R', 0, 4, 2)+[stationary('R', 4, 6)]
        result = ledger.replace_plan('R', 2, rows)
        self.assertTrue(result.accepted)
        all_rows = result.ledger.rows()
        self.assertEqual((0, 2, 'stationary'),
                         (all_rows[0]['start'], all_rows[0]['end'], all_rows[0]['occupancy_kind']))
        self.assertEqual(18, len(all_rows))  # 16 quarter-second moving cells + history + tail
        for previous, current in zip(all_rows, all_rows[1:]):
            self.assertAlmostEqual(previous['end'], current['start'])
        self.assertEqual(math.inf, all_rows[-1]['end'])
        self.assertEqual(math.inf, ledger.rows()[0]['end'])  # old immutable snapshot remains

    def test_future_plan_replacement_truncates_only_owner_history(self):
        ledger = initialise(OccupancyLedger(), 'R', 0)
        ledger = initialise(ledger, 'Other', 10)
        ledger = ledger.replace_plan('R', 2, moving('R', 0, 4, 2)+[stationary('R', 4, 6)]).ledger
        other_before = [r for r in ledger.rows() if r['owner'] == 'Other']
        result = ledger.replace_plan('R', 8, [stationary('R', 4, 8)])
        self.assertTrue(result.accepted)
        owned = [r for r in result.ledger.rows() if r['owner'] == 'R']
        self.assertEqual((6, 8), (owned[-2]['start'], owned[-2]['end']))
        self.assertEqual((8, math.inf), (owned[-1]['start'], owned[-1]['end']))
        self.assertEqual(other_before, [r for r in result.ledger.rows() if r['owner'] == 'Other'])

    def test_cutting_moving_cell_rejected_but_boundary_replan_is_permitted(self):
        ledger = initialise(OccupancyLedger(), 'R', 0)
        ledger = ledger.replace_plan('R', 2, moving('R', 0, 4, 2)+[stationary('R', 4, 6)]).ledger
        before = ledger.rows()
        with self.assertRaises(TrajectoryError) as error:
            ledger.replace_plan('R', 2.1, [stationary('R', .1, 2.1)])
        self.assertEqual('invalid_input', error.exception.reason)
        self.assertEqual(before, ledger.rows())
        # The supplied boundary pose comes from the caller, not robot attributes.
        result = ledger.replace_plan('R', 2.25, [stationary('R', .25, 2.25)])
        self.assertTrue(result.accepted)
        self.assertEqual(3, len(result.ledger.rows()))

    def test_parked_robot_blocks_motion_not_only_terminal_position(self):
        ledger = initialise(OccupancyLedger(), 'R', 0)
        ledger = initialise(ledger, 'Parked', 3)
        before = ledger.rows()
        proposal = moving('R', 0, 6, 0)+[stationary('R', 6, 6)]
        result = ledger.replace_plan('R', 0, proposal)
        self.assertFalse(result.accepted)
        self.assertEqual(('Parked',), result.permanent_blockers)
        self.assertTrue(all(c.proposed_kind == 'moving' for c in result.conflicts))
        self.assertEqual(before, ledger.rows())
        self.assertIs(ledger, result.ledger)

    def test_terminal_occupancy_conflicts_with_future_movement(self):
        ledger = initialise(OccupancyLedger(), 'R', 0, y=5)
        ledger = initialise(ledger, 'Other', -4)
        other_plan = moving('Other', -4, 4, 10)+[stationary('Other', 4, 18)]
        result = ledger.replace_plan('Other', 10, other_plan)
        self.assertTrue(result.accepted)
        ledger = result.ledger
        # Ledger accepts explicit cells; kinematic/pose continuity is the builder's
        # responsibility. This proposal's tail must still reserve all future time.
        result = ledger.replace_plan('R', 0, [stationary('R', 0, 0)])
        self.assertFalse(result.accepted)
        self.assertTrue(all(c.proposed_kind == 'stationary' and c.blocking_kind == 'moving'
                            for c in result.conflicts))
        self.assertEqual((), result.permanent_blockers)
        self.assertIsNotNone(result.earliest_release)
        self.assertGreater(result.earliest_release, 10)

    def test_next_finite_release_is_not_reported_as_feasible_departure(self):
        ledger = initialise(OccupancyLedger(), 'R', 0)
        ledger = initialise(ledger, 'Other', 4)
        other_plan = moving('Other', 4, 8, 5)+[stationary('Other', 8, 9)]
        ledger = ledger.replace_plan('Other', 5, other_plan).ledger
        proposal = moving('R', 0, 4, 0)+[stationary('R', 4, 4)]
        result = ledger.replace_plan('R', 0, proposal)
        self.assertFalse(result.accepted)
        self.assertEqual(5, result.earliest_release)
        self.assertEqual((), result.permanent_blockers)
        self.assertTrue(any(c.blocking_release > result.earliest_release for c in result.conflicts))
        self.assertFalse(hasattr(result, 'feasible_departure'))

    def test_pair_gap_uses_larger_override_and_boundary_contact_is_allowed(self):
        ledger = initialise(OccupancyLedger(), 'A', 0, gap=.4)
        result = ledger.initialise(owner='B', floor=0, pose=Pose(1.4, 0, 0), start=0,
            length_m=1, width_m=1, robot_clearance_m=.1)
        self.assertTrue(result.accepted)  # 0.4 m physical gap, max(.4,.1), not sum
        result = ledger.initialise(owner='B', floor=0, pose=Pose(1.399, 0, 0), start=0,
            length_m=1, width_m=1, robot_clearance_m=.1)
        self.assertFalse(result.accepted)

    def test_exact_temporal_boundary_does_not_overlap(self):
        ledger = initialise(OccupancyLedger(), 'A', 0)
        ledger = ledger.replace_plan('A', 5, [stationary('A', 0, 5, floor=1)]).ledger
        result = ledger.initialise(owner='B', floor=0, pose=Pose(0, 0, 0), start=5,
                                   length_m=1, width_m=1)
        self.assertTrue(result.accepted)

    def test_snapshot_rows_and_input_mutation_do_not_alter_ledger(self):
        ledger = initialise(OccupancyLedger(), 'R', 0)
        self.assertIs(ledger, ledger.snapshot())
        with self.assertRaises(FrozenInstanceError):
            ledger._claims = ()
        row = stationary('R', 0, 1)
        accepted = ledger.replace_plan('R', 1, [row]).ledger
        frozen = accepted.rows()
        row['polygon'][0] = (99, 99)
        row['end'] = 3
        exported = accepted.rows()
        exported[-1]['polygon'][0][0] = 123
        exported[-1]['start'] = 10
        self.assertEqual(frozen, accepted.rows())

    def test_invalid_coverage_owner_or_tail_is_never_committed(self):
        ledger = initialise(OccupancyLedger(), 'R', 0)
        baseline = ledger.rows()
        bad_plans = [[], [stationary('R', 0, 1)], [stationary('Other', 0, 0)],
                     [stationary('R', 0, 0, 1)],
                     [stationary('R', 0, 0, 1), stationary('R', 0, 2)],
                     [stationary('R', 0, 0, 2), stationary('R', 0, 1)],
                     [stationary('R', 0, 0), stationary('R', 0, 1)]]
        for rows in bad_plans:
            with self.subTest(rows=rows), self.assertRaises(TrajectoryError):
                ledger.replace_plan('R', 0, rows)
            self.assertEqual(baseline, ledger.rows())

    def test_invalid_claim_geometry_and_numbers_do_not_get_silent_fallback(self):
        ledger = initialise(OccupancyLedger(), 'R', 0)
        for update in ({'polygon': [[0, 0], [1, 1], [0, 1], [1, 0]]},
                       {'polygon': [[0, 0], [1, 0], [2, 0]]},
                       {'envelope': [-.4, -.5, .5, .5]},
                       {'start': math.nan}, {'end': True}, {'floor': True},
                       {'robot_clearance_m': -.1}, {'occupancy_kind': 'moving'}):
            row = {**stationary('R', 0, 0), **update}
            with self.subTest(update=update), self.assertRaises(TrajectoryError):
                ledger.replace_plan('R', 0, [row])

    def test_search_limit_leaves_snapshot_unchanged_and_is_not_deadlock(self):
        ledger = initialise(OccupancyLedger(), 'R', 0)
        ledger = initialise(ledger, 'A', 3)
        ledger = initialise(ledger, 'B', 6)
        baseline = copy.deepcopy(ledger.rows())
        with self.assertRaises(TrajectoryError) as error:
            ledger.replace_plan('R', 0, moving('R', 0, 8, 0)+[stationary('R', 8, 8)], max_pair_checks=1)
        self.assertEqual('search_limit', error.exception.reason)
        self.assertEqual(baseline, ledger.rows())

    def test_source_ids_survive_in_structured_conflict_evidence(self):
        ledger = initialise(OccupancyLedger(), 'R', 0)
        ledger = initialise(ledger, 'Other', 3)
        other = stationary('Other', 3, 0)
        other['source_id'] = 'terminal:Other:1'
        ledger = ledger.replace_plan('Other', 0, [other]).ledger
        rows = moving('R', 0, 6, 0)+[stationary('R', 6, 6)]
        for row in rows:
            row['source_id'] = 'journey:R:2'
        result = ledger.replace_plan('R', 0, rows)
        self.assertFalse(result.accepted)
        self.assertEqual(('journey:R:2', 'terminal:Other:1'),
                         (result.conflicts[0].proposed_source_id, result.conflicts[0].blocking_source_id))

    def test_unknown_owner_duplicate_initialisation_and_early_replacement_rejected(self):
        empty = OccupancyLedger()
        with self.assertRaises(TrajectoryError):
            empty.replace_plan('R', 0, [stationary('R', 0, 0)])
        ledger = initialise(empty, 'R', 0, start=2)
        with self.assertRaises(TrajectoryError):
            ledger.initialise(owner='R', floor=0, pose=Pose(0, 0, 0), start=2, length_m=1, width_m=1)
        with self.assertRaises(TrajectoryError):
            ledger.replace_plan('R', 1, [stationary('R', 0, 1)])

    def test_zero_duration_load_cannot_disappear_between_empty_tails(self):
        ledger = initialise(OccupancyLedger(), 'R', 0)
        ledger = initialise(ledger, 'Other', 1.5)
        proposal = [instantaneous('R', 0, 0, length=4), stationary('R', 0, 0)]
        result = ledger.replace_plan('R', 0, proposal)
        self.assertFalse(result.accepted)
        self.assertIs(ledger, result.ledger)
        self.assertEqual(1, len(result.conflicts))
        conflict = result.conflicts[0]
        self.assertEqual((0, 0, 'instantaneous', 'stationary'),
            (conflict.start, conflict.end, conflict.proposed_kind, conflict.blocking_kind))
        self.assertEqual(('Other',), result.permanent_blockers)

    def test_instantaneous_loads_conflict_at_same_time_without_stationary_overlap(self):
        ledger = initialise(OccupancyLedger(), 'A', 0)
        ledger = initialise(ledger, 'B', 4)
        update = ledger.replace_plan('A', 5, [instantaneous('A', 0, 5, length=4), stationary('A', 0, 5)])
        self.assertTrue(update.accepted)
        ledger = update.ledger
        result = ledger.replace_plan('B', 5, [instantaneous('B', 4, 5, length=6), stationary('B', 4, 5)])
        self.assertFalse(result.accepted)
        self.assertEqual(1, len(result.conflicts))
        self.assertEqual(('instantaneous', 'instantaneous', 5, 5),
            (result.conflicts[0].proposed_kind, result.conflicts[0].blocking_kind,
             result.conflicts[0].start, result.conflicts[0].end))
        # Even the adjacent representable timestamp is a distinct event, not an
        # invented epsilon interval. Neither load overlaps the other's empty body.
        later = math.nextafter(5, math.inf)
        result = ledger.replace_plan('B', later, [instantaneous('B', 4, later, length=6), stationary('B', 4, later)])
        self.assertTrue(result.accepted)

    def test_instant_checks_halfopen_interval_start_but_not_end(self):
        ledger = initialise(OccupancyLedger(), 'A', 0, start=2)
        ledger = initialise(ledger, 'R', 3)
        ledger = ledger.replace_plan('A', 5, [stationary('A', 0, 5, floor=1)]).ledger
        for time, expected in ((2, False), (math.nextafter(5, 0), False), (5, True)):
            with self.subTest(time=time):
                result = ledger.replace_plan('R', time, [instantaneous('R', 0, time), stationary('R', 3, time)])
                self.assertEqual(expected, result.accepted)
                if not expected:
                    self.assertEqual(5, result.earliest_release)

    def test_finite_candidate_detects_existing_instant_and_pair_gap(self):
        ledger = initialise(OccupancyLedger(), 'A', 0)
        ledger = initialise(ledger, 'B', 4)
        ledger = ledger.replace_plan('A', 5,
            [instantaneous('A', 0, 5, length=4, gap=.2), stationary('A', 0, 5)]).ledger
        # B occupies [2.1,3.1] at t=5: 0.1 gap to A's instantaneous loaded
        # footprint [−2,2], less than the required 0.2 gap. Empty A remains clear.
        rows = [stationary('B', 2.6, 4, 6), stationary('B', 4, 6)]
        result = ledger.replace_plan('B', 4, rows)
        self.assertFalse(result.accepted)
        self.assertEqual(1, len(result.conflicts))
        self.assertEqual(('stationary', 'instantaneous', 5, 5),
            (result.conflicts[0].proposed_kind, result.conflicts[0].blocking_kind,
             result.conflicts[0].start, result.conflicts[0].end))
        self.assertEqual(5, result.earliest_release)

    def test_instantaneous_history_survives_same_time_next_departure(self):
        ledger = initialise(OccupancyLedger(), 'A', 0)
        ledger = ledger.replace_plan('A', 2,
            [instantaneous('A', 0, 2, length=4), stationary('A', 0, 2)]).ledger
        result = ledger.replace_plan('A', 2, [stationary('A', 0, 2)])
        self.assertTrue(result.accepted)
        events = [row for row in result.ledger.rows() if row['occupancy_kind'] == 'instantaneous']
        self.assertEqual(1, len(events))
        self.assertEqual((2, 2), (events[0]['start'], events[0]['end']))

    def test_only_explicit_equal_finite_instantaneous_times_are_valid(self):
        ledger = initialise(OccupancyLedger(), 'A', 0)
        for update in ({'end': 1}, {'end': math.inf}, {'start': math.inf, 'end': math.inf},
                       {'end': math.nan}, {'end': True}, {'occupancy_kind': 'stationary'}):
            row = {**instantaneous('A', 0, 0), **update}
            with self.subTest(update=update), self.assertRaises(TrajectoryError):
                ledger.replace_plan('A', 0, [row, stationary('A', 0, 0)])

    def test_atomic_disjoint_exchange_succeeds_although_each_single_plan_is_blocked(self):
        ledger = initialise(OccupancyLedger(), 'A', 0)
        ledger = initialise(ledger, 'B', 6)
        # One uses the upper route, the other the lower route. Both vacate their
        # former parked tails, which must not survive as phantom blockers.
        a = path_plan('A', [(0, 0), (0, 3), (6, 3), (6, 0)], 2)
        b = path_plan('B', [(6, 0), (6, -3), (0, -3), (0, 0)], 2)
        self.assertFalse(ledger.replace_plan('A', 2, a).accepted)
        self.assertFalse(ledger.replace_plan('B', 2, b).accepted)
        plans = {'A': (2, a), 'B': (2, b)}
        original = copy.deepcopy(plans)
        result = ledger.replace_plans(plans)
        self.assertTrue(result.accepted)
        self.assertEqual(original, plans)
        self.assertEqual(2, len(ledger.rows()))  # original remains a rollback snapshot
        history = [r for r in result.ledger.rows() if r['end'] == 2]
        self.assertEqual({'A', 'B'}, {r['owner'] for r in history})
        self.assertTrue(all(r['start'] == 0 and r['occupancy_kind'] == 'stationary' for r in history))
        self.assertEqual(result.ledger.rows(), ledger.replace_plans({'B': (2, b), 'A': (2, a)}).ledger.rows())

    def test_joint_crossing_conflict_rejects_whole_batch_without_erasing_tails(self):
        ledger = initialise(OccupancyLedger(), 'A', 0)
        ledger = initialise(ledger, 'B', 6)
        a = moving('A', 0, 6, 0)+[stationary('A', 6, 6)]
        b = moving('B', 6, 0, 0)+[stationary('B', 0, 6)]
        before = ledger.rows()
        result = ledger.replace_plans({'A': (0, a), 'B': (0, b)})
        self.assertFalse(result.accepted)
        self.assertIs(ledger, result.ledger)
        self.assertEqual(before, ledger.rows())
        self.assertEqual({'A', 'B'}, {c.owner for c in result.conflicts})
        self.assertTrue(all(c.proposed_kind == c.blocking_kind == 'moving' for c in result.conflicts))
        self.assertEqual((), result.permanent_blockers)

    def test_joint_replacement_keeps_other_owner_history_until_its_later_departure(self):
        ledger = initialise(OccupancyLedger(), 'A', 0)
        ledger = initialise(ledger, 'B', 6)
        # A tries to reach B before B departs. Replacing B's future at 10 must
        # leave [0,10) occupied, even though both owners occur in this batch.
        a = moving('A', 0, 6, 0)+[stationary('A', 6, 6)]
        b = path_plan('B', [(6, 0), (6, -3), (0, -3), (0, 0)], 10)
        result = ledger.replace_plans({'A': (0, a), 'B': (10, b)})
        self.assertFalse(result.accepted)
        retained = [c for c in result.conflicts if c.owner == 'A' and c.blocking_kind == 'stationary'
                    and c.blocking_release == 10]
        self.assertTrue(retained)
        self.assertIs(ledger, result.ledger)

    def test_joint_plan_checks_unchanged_third_robot_and_preserves_its_snapshot(self):
        ledger = initialise(OccupancyLedger(), 'A', 0)
        ledger = initialise(ledger, 'B', 6)
        ledger = initialise(ledger, 'C', 3, y=3)
        plans = {'A': (0, path_plan('A', [(0, 0), (0, 3), (6, 3), (6, 0)], 0)),
                 'B': (0, path_plan('B', [(6, 0), (6, -3), (0, -3), (0, 0)], 0))}
        result = ledger.replace_plans(plans)
        self.assertFalse(result.accepted)
        self.assertEqual(('C',), result.permanent_blockers)
        self.assertIs(ledger, result.ledger)
        self.assertEqual(3, len(ledger.rows()))

    def test_joint_instantaneous_loads_and_larger_pair_gap_are_checked(self):
        ledger = initialise(OccupancyLedger(), 'A', 0)
        ledger = initialise(ledger, 'B', 4)
        a = [instantaneous('A', 0, 5, length=4, gap=.2), stationary('A', 0, 5)]
        # B's loaded left edge=2.1: gap .1 to A's loaded right edge=2.
        b = [instantaneous('B', 4, 5, length=3.8, gap=.05), stationary('B', 4, 5)]
        result = ledger.replace_plans({'A': (5, a), 'B': (5, b)})
        self.assertFalse(result.accepted)
        self.assertEqual(2, len(result.conflicts))
        self.assertTrue(all(c.start == c.end == 5 and c.proposed_kind == c.blocking_kind == 'instantaneous'
                            for c in result.conflicts))
        b[0] = instantaneous('B', 4, 5, length=3.6, gap=.05)  # exact required gap=.2
        self.assertTrue(ledger.replace_plans({'A': (5, a), 'B': (5, b)}).accepted)

    def test_joint_invalid_second_plan_does_not_partially_accept_first(self):
        ledger = initialise(OccupancyLedger(), 'A', 0)
        ledger = initialise(ledger, 'B', 6)
        original = ledger.rows()
        for bad in ({}, [], {'A': None}, {'A': (0, [])}, {None: (0, [])},
                    {'A': (0, [stationary('A', 0, 0)]), 'Unknown': (0, [stationary('Unknown', 9, 0)])},
                    {'A': (0, [stationary('A', 0, 0)]), 'B': (0, [stationary('B', 6, 1)])}):
            with self.subTest(plans=bad), self.assertRaises(TrajectoryError) as error:
                ledger.replace_plans(bad)
            self.assertEqual('invalid_input', error.exception.reason)
            self.assertEqual(original, ledger.rows())

    def test_joint_cannot_cut_existing_moving_cell_and_search_budget_is_atomic(self):
        ledger = initialise(OccupancyLedger(), 'A', 0)
        ledger = initialise(ledger, 'B', 6)
        ledger = ledger.replace_plan('A', 0, moving('A', 0, 2, 0)+[stationary('A', 2, 2)]).ledger
        original = ledger.rows()
        with self.assertRaises(TrajectoryError) as error:
            ledger.replace_plans({'A': (.1, [stationary('A', .1, .1)]),
                                  'B': (0, [stationary('B', 6, 0)])})
        self.assertEqual('invalid_input', error.exception.reason)
        self.assertEqual(original, ledger.rows())
        plans = {'A': (2, [stationary('A', 2, 2, 3), stationary('A', 2, 3)]),
                 'B': (2, [stationary('B', 6, 2, 3), stationary('B', 6, 3)])}
        with self.assertRaises(TrajectoryError) as error:
            ledger.replace_plans(plans, max_pair_checks=1)
        self.assertEqual('search_limit', error.exception.reason)
        self.assertEqual(original, ledger.rows())


if __name__ == '__main__':
    unittest.main()
