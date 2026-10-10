"""Fleet capacity references: distinct bays, shared restrictions and charger priority."""
import copy
import itertools
import unittest

from simulator import Simulation
from tests.test_engineering_reference import reference_config
from visualiser.models import JsonStore
from visualiser.project_checks import check_project
from amr_fleet_allocation import maximum_bay_assignment


def fleet_config(bays, robots=('R', 'Other')):
    cfg = reference_config()
    cfg['amrs'] = [dict(cfg['amrs'][0], id=name, height_m=.5) for name in robots]
    cfg['locations'][0]['inventory_spaces'] = [dict(name=name, length_m=2, width_m=2,
        height_m=2, stores_amr=True, has_charger=charger,
        payload_slots=[dict(amr_type=allowed)] if allowed else [])
        for name, allowed, charger in bays]
    return cfg


class InitialFleetAllocationTests(unittest.TestCase):
    def homes(self, sim):
        return {r.id: r.home_inventory_space_name for r in sim.amrs}

    def test_shared_bay_is_reassigned_to_satisfy_restricted_robot(self):
        cfg = fleet_config([('Shared', '', True), ('R only', 'R', True)])
        for data in (cfg, JsonStore(cfg).data):
            sim = Simulation(data)
            self.assertEqual({'R-1': 'R only', 'Other-1': 'Shared'}, self.homes(sim))
            self.assertTrue(all(sim._amr_is_at_operational_charger(r) for r in sim.amrs))
            self.assertEqual({'R-1', 'Other-1'}, {s['amr_id'] for s in sim.inventory_spaces_by_location['A']})

    def test_one_shared_charger_cannot_count_once_for_each_type(self):
        cfg = fleet_config([('Shared', '', True)])
        before = copy.deepcopy(cfg)
        report = check_project(cfg)
        finding = next(f for f in report.findings if f.code == 'CHARGE_START_CAPACITY')
        self.assertEqual('warning', finding.severity)
        self.assertIn('1 of 2', finding.message)
        self.assertEqual(before, cfg)
        self.assertFalse(report.can_run(cfg))
        report.acknowledge_warnings()
        self.assertTrue(report.can_run(cfg))
        self.assertEqual(1, sum(bool(x) for x in self.homes(Simulation(cfg)).values()))

    def test_instance_restrictions_cannot_be_counted_for_another_instance(self):
        cfg = fleet_config([('First', 'R-1', True), ('Second', 'R-1', True)], robots=('R',))
        cfg['amrs'][0]['quantity'] = 2
        report = check_project(cfg)
        self.assertTrue(any(f.code == 'CHARGE_START_CAPACITY' and '1 of 2' in f.message for f in report.findings))
        homes = self.homes(Simulation(cfg))
        self.assertEqual('First', homes['R-1'])
        self.assertEqual('', homes['R-2'])

    def test_initial_chargers_are_preferred_over_parking_bays(self):
        cfg = fleet_config([('Parking', '', False), ('Charger', '', True)], robots=('R',))
        sim = Simulation(cfg)
        self.assertEqual({'R-1': 'Charger'}, self.homes(sim))
        self.assertTrue(sim._amr_is_at_operational_charger(sim.amrs[0]))

    def test_parking_can_rearrange_a_charge_match_without_losing_charger_occupancy(self):
        cfg = fleet_config([('Charger', '', True), ('R parking', 'R', False)])
        sim = Simulation(cfg)
        self.assertEqual({'R-1': 'R parking', 'Other-1': 'Charger'}, self.homes(sim))
        self.assertEqual(1, sum(sim._amr_is_at_operational_charger(r) for r in sim.amrs))

    def test_same_bay_name_at_two_locations_is_two_distinct_spaces(self):
        cfg = fleet_config([('Bay', '', True)])
        cfg['locations'][1]['inventory_spaces'] = copy.deepcopy(cfg['locations'][0]['inventory_spaces'])
        cfg['building']['charge_locations'] = ['A', 'B', 'A']
        sim = Simulation(cfg)
        self.assertEqual([('A', 'Bay'), ('B', 'Bay')], [(r.location_name, r.home_inventory_space_name) for r in sim.amrs])
        self.assertFalse(any(f.code == 'CHARGE_START_CAPACITY' for f in check_project(cfg).findings))

    def test_legacy_location_without_amr_bays_remains_explicit_and_runnable(self):
        cfg = reference_config()
        report = check_project(cfg)
        self.assertTrue(any(f.code == 'CHARGE_LEGACY_LAYOUT' and f.severity == 'info' for f in report.findings))
        self.assertFalse(any(f.code == 'CHARGE_START_CAPACITY' for f in report.findings))
        self.assertTrue(report.can_run(cfg))
        self.assertEqual({'R-1': ''}, self.homes(Simulation(cfg)))

    def test_unknown_charging_location_blocks_draft_run(self):
        cfg = reference_config()
        cfg['building']['charge_locations'] = ['Typo']
        JsonStore(cfg)
        with self.assertRaisesRegex(ValueError, 'Typo'):
            Simulation(cfg)
        self.assertTrue(any(f.code == 'CHARGE_INPUT' and f.severity == 'error' for f in check_project(cfg).findings))

    def test_charge_location_resolution_agrees_for_legacy_csv_and_empty_list(self):
        for value, expected in [([], ['B']), ('B,A,B', ['B','A']), (['B','A','B'], ['B','A'])]:
            cfg = reference_config()
            cfg['building'].update(charge_location='B', charge_locations=value)
            store = JsonStore(cfg)
            self.assertEqual(expected, store.charge_locations())
            self.assertEqual(expected, Simulation(cfg).charge_location_names)

    def test_matching_agrees_with_exhaustive_three_robot_three_bay_reference(self):
        # Enumerate all 512 compatibility graphs, then all 8 charger/parking splits.
        # Independent oracle enumerates every possible assignment, including unplaced robots.
        placements = list(itertools.product((None, 0, 1, 2), repeat=3))
        for mask in range(1 << 9):
            graph = {r: [b for b in range(3) if mask & (1 << (3*r+b))] for r in range(3)}
            valid = [p for p in placements if len([b for b in p if b is not None]) == len({b for b in p if b is not None})
                     and all(b is None or b in graph[r] for r,b in enumerate(p))]
            for charger_mask in range(8):
                chargers = {b for b in range(3) if charger_mask & (1 << b)}
                charger_graph = {r: [b for b in graph[r] if b in chargers] for r in graph}
                charge_match = maximum_bay_assignment(charger_graph)
                actual = maximum_bay_assignment(graph, charge_match)
                expected = max((sum(b in chargers for b in p if b is not None),
                                sum(b is not None for b in p)) for p in valid)
                self.assertEqual(expected, (sum(b in chargers for b in actual.values()), len(actual)), (mask, charger_mask))
                self.assertEqual(len(actual), len(set(actual.values())))
                self.assertTrue(all(b in graph[r] for r,b in actual.items()))

    def test_matching_is_deterministic_and_preserves_uncontested_choices(self):
        graph = {'A': ['first','second','third'], 'B': ['first','second','third']}
        self.assertEqual({'A':'first','B':'second'}, maximum_bay_assignment(graph))
        self.assertEqual(maximum_bay_assignment(graph), maximum_bay_assignment(graph))
        with self.assertRaises(ValueError):
            maximum_bay_assignment(graph, {'A':'first','B':'first'})

    def test_zero_fleet_needs_no_capacity_and_no_duplicate_warning(self):
        cfg = fleet_config([('Shared','',True)], robots=('R',))
        cfg['amrs'][0]['quantity'] = 0
        self.assertEqual({}, self.homes(Simulation(cfg)))
        self.assertFalse(any(f.code == 'CHARGE_START_CAPACITY' for f in check_project(cfg).findings))
        cfg['amrs'][0]['quantity'] = 2
        findings = check_project(cfg).findings
        self.assertEqual(1, sum(f.code == 'CHARGE_START_CAPACITY' for f in findings))
        self.assertFalse(any(f.code == 'LEGACY_CHECK' and 'charger-equipped' in f.message for f in findings))

    def test_invalid_charge_location_shapes_reject_without_changing_inputs(self):
        for value in (None, False, 3, {}, [None], ['']):
            cfg = reference_config()
            cfg['building']['charge_locations'] = value
            before = copy.deepcopy(cfg)
            for consumer in (JsonStore, Simulation):
                with self.subTest(value=value, consumer=consumer.__name__), self.assertRaises(ValueError):
                    consumer(cfg)
            self.assertEqual(before, cfg)

    def test_capacity_findings_become_stale_when_a_robot_restriction_changes(self):
        cfg = fleet_config([('Shared','',True)])
        report = check_project(cfg)
        finding = next(f for f in report.findings if f.code == 'CHARGE_START_CAPACITY')
        cfg['amrs'][1]['quantity'] = 0
        self.assertEqual(['amrs'], report.changed_inputs(finding,cfg))
        self.assertFalse(any(f.code == 'CHARGE_START_CAPACITY' for f in check_project(cfg).findings))

    def test_rename_preserves_modern_and_legacy_charging_references(self):
        for value in (['A','B'], 'A,B'):
            cfg = reference_config()
            cfg['building']['charge_locations'] = value
            store = JsonStore(cfg)
            store.rename_point('A','Dock')
            self.assertEqual('Dock',store.data['building']['charge_location'])
            self.assertEqual(['Dock','B'],store.charge_locations())
            self.assertEqual('Dock',Simulation(store.data).amrs[0].location_name)


if __name__ == '__main__':
    unittest.main()
