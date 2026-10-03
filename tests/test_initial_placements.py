"""Independent initial footprint and per-instance placement acceptance cases."""
import copy
import unittest

from amr_initial_placements import initial_placement_findings, resolve_initial_placements


def config(quantity=1):
    return {'simulation': {'motion_model': 'geometric_v1'},
            'building': {'charge_location': 'A'},
            'amrs': [{'id': 'R', 'quantity': quantity, 'length_m': 2., 'width_m': 1.,
                      'manoeuvring': {'initial_heading_deg': 0}}],
            'locations': [{'name': 'A', 'floor': 0, 'x': 0., 'y': 0.},
                          {'name': 'B', 'floor': 0, 'x': 2.3, 'y': 0.}],
            'geometry': {'traffic_model': 'keep_right_v1',
                         'clearances': {'wall_m': .1, 'robot_m': .3},
                         'floors': [{'floor': 0, 'bounds': [-5, -5, 5, 5], 'obstacles': []}]}}


def explicit(c):
    c['geometry']['initial_placements'] = [
        {'amr_id': 'R-1', 'location': 'A', 'heading_deg': 0},
        {'amr_id': 'R-2', 'location': 'B', 'heading_deg': 0}]
    return c


class InitialPlacementTests(unittest.TestCase):
    def test_single_robot_retains_checked_first_charger_and_heading(self):
        c = config()
        c['amrs'][0]['manoeuvring']['initial_heading_deg'] = 90
        original = copy.deepcopy(c)
        placement = resolve_initial_placements(c)['R-1']
        self.assertEqual(('A', 0, 0., 0., 90.), tuple(placement[k] for k in
                         ('location', 'floor', 'x', 'y', 'heading_deg')))
        self.assertEqual(original, c)

    def test_multiple_robots_require_explicit_positions(self):
        with self.assertRaisesRegex(ValueError, 'multi-robot'):
            resolve_initial_placements(config(2))

    def test_exact_total_gap_allowed_and_smaller_gap_rejected(self):
        c = explicit(config(2))
        self.assertEqual(2, len(resolve_initial_placements(c)))
        c['locations'][1]['x'] = 2.299
        with self.assertRaisesRegex(ValueError, 'robot separation'):
            resolve_initial_placements(c)

    def test_pair_uses_larger_override_not_sum(self):
        c = explicit(config(2))
        c['amrs'][0]['quantity'] = 1
        other = copy.deepcopy(c['amrs'][0])
        other.update(id='S')
        other['manoeuvring']['robot_clearance_m'] = .6
        c['amrs'].append(other)
        c['geometry']['initial_placements'][1]['amr_id'] = 'S-1'
        c['locations'][1]['x'] = 2.6
        self.assertEqual(2, len(resolve_initial_placements(c)))
        c['locations'][1]['x'] = 2.59
        self.assertTrue(initial_placement_findings(c))

    def test_heading_changes_the_checked_footprint(self):
        c = explicit(config(2))
        c['geometry']['initial_placements'][1]['heading_deg'] = 90
        c['locations'][1]['x'] = 1.8  # 1 m + .5 m half extents + .3 m gap
        self.assertFalse(initial_placement_findings(c))
        c['geometry']['initial_placements'][1]['heading_deg'] = 0
        self.assertTrue(initial_placement_findings(c))

    def test_robots_on_separate_floors_do_not_conflict(self):
        c = explicit(config(2))
        c['locations'][1].update(x=0., floor=1)
        floor = copy.deepcopy(c['geometry']['floors'][0])
        floor['floor'] = 1
        c['geometry']['floors'].append(floor)
        self.assertFalse(initial_placement_findings(c))

    def test_full_body_plus_wall_clearance_checks_bounds_and_obstacles(self):
        c = config()
        c['geometry']['floors'][0]['bounds'][2] = 1.1
        self.assertFalse(initial_placement_findings(c))
        c['geometry']['floors'][0]['bounds'][2] = 1.09
        self.assertTrue(initial_placement_findings(c))
        c = config()
        c['geometry']['floors'][0]['obstacles'] = [[1.1, -.2, 2, .2]]
        self.assertFalse(initial_placement_findings(c))
        c['geometry']['floors'][0]['obstacles'][0][0] = 1.09
        with self.assertRaisesRegex(ValueError, 'obstacle'):
            resolve_initial_placements(c)

    def test_simple_and_whole_route_modes_ignore_dormant_placements(self):
        for mode, traffic in [('legacy', 'keep_right_v1'), ('geometric_v1', 'whole_route_v1')]:
            c = explicit(config(2))
            c['simulation']['motion_model'] = mode
            c['geometry']['traffic_model'] = traffic
            c['geometry']['initial_placements'] = 'invalid but dormant'
            self.assertEqual({}, resolve_initial_placements(c))

    def test_missing_duplicate_unknown_ids_and_invalid_rows_are_findings(self):
        for rows in [[], None, [None], [{'amr_id': []}],
                     [{'amr_id': 'NoSuch-1', 'location': 'A', 'heading_deg': 0}],
                     [{'amr_id': 'R-1', 'location': 'A', 'heading_deg': 0}]*2]:
            with self.subTest(rows=rows):
                c = config(2)
                c['geometry']['initial_placements'] = rows
                self.assertTrue(initial_placement_findings(c))

    def test_bad_locations_headings_and_model_shape_are_findings(self):
        for key, value in [('location', 'Missing'), ('location', []),
                           ('heading_deg', True), ('heading_deg', float('nan'))]:
            c = config()
            c['geometry']['initial_placements'] = [{'amr_id': 'R-1', 'location': 'A', 'heading_deg': 0}]
            c['geometry']['initial_placements'][0][key] = value
            self.assertTrue(initial_placement_findings(c))
        for key in ('amrs', 'locations'):
            c = config()
            c[key] = None
            self.assertTrue(initial_placement_findings(c))
        c = config()
        c['geometry']['floors'][0]['obstacles'] = None
        self.assertTrue(initial_placement_findings(c))

    def test_initial_indefinite_parking_cannot_obstruct_drawn_areas(self):
        c = config()
        c['geometry']['floors'][0]['no_queuing_areas'] = [
            {'id': 'Keep clear', 'bounds': [.9, -.2, 1.5, .2]}]
        # The centre lies outside the area but the robot's full footprint overlaps.
        with self.assertRaisesRegex(ValueError, 'no_queuing_area: Keep clear'):
            resolve_initial_placements(c)

    def test_initial_indefinite_parking_cannot_obstruct_door_or_junction(self):
        for door in (True, False):
            with self.subTest(door=door):
                c = config()
                c['locations'][0].update(has_door=door, door_clear_width_m=2)
                c['corridors'] = {'nodes': [
                    {'name': 'N', 'floor': 0, 'x': 0, 'y': 3},
                    {'name': 'S', 'floor': 0, 'x': 0, 'y': -3}],
                    'edges': [{'from': 'A', 'to': name, 'width_m': 2}
                              for name in (('B',) if door else ('B', 'N', 'S'))]}
                with self.assertRaisesRegex(ValueError, 'protected_door' if door else 'protected_junction'):
                    resolve_initial_placements(c)

    def test_no_work_run_import_and_checks_reject_protected_initial_parking(self):
        from simulator import Simulation
        from tests.test_geometric_traffic import traffic_config
        from visualiser.models import JsonStore
        from visualiser.project_checks import check_project
        c = traffic_config()
        c['tasks'] = []
        c['task_generation'] = {'enabled': False}
        c['geometry']['floors'][0]['no_queuing_areas'] = [
            {'id': 'No initial parking', 'bounds': [-1, -1, 1, 1]}]
        for constructor in (Simulation, JsonStore):
            with self.subTest(constructor=constructor.__name__):
                with self.assertRaisesRegex(ValueError, 'no_queuing_area'):
                    constructor(c)
        self.assertTrue(any(f.code == 'GEOMETRY_INPUT' and 'no_queuing_area' in str(f)
                            for f in check_project(c).findings))


if __name__ == '__main__':
    unittest.main()
