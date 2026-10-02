"""Independent geometry, permission, resource-reference and undo acceptance cases."""
from copy import deepcopy
import contextlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'visualiser'))
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox
from app import AMRGraphEditor
from models import JsonStore
from corridor_editing import project_fraction, subdivide
from amr_recovery import RecoveryStore
from amr_sim_models import Task
from simulator import Simulation
from tests.test_engineering_reference import reference_config
from tests.test_route_profiles import profile_config


def split_config(config, cuts):
    points = {p['name']: p for p in config['locations'] + config['corridors']['nodes']}
    return subdivide(config, points, cuts)


class CorridorEditingTests(unittest.TestCase):
    def direct(self):
        config = reference_config()
        config['corridors']['edges'] = [dict(zip(('from', 'to'), ('A', 'B')), width_m=3, bidirectional=False)]
        return config

    def test_projection_is_on_line_and_not_grid_rounded(self):
        config = self.direct()
        a, b = config['locations']
        self.assertAlmostEqual(.25, project_fraction(a, b, 1.58, 1.94))
        updated, chains = split_config(config, {('A', 'B'): [.25, .6]})
        points = {p['name']: p for p in updated['corridors']['nodes']}
        self.assertEqual((1.5, 2), (points[chains[('A', 'B')][1]]['x'], points[chains[('A', 'B')][1]]['y']))
        self.assertAlmostEqual(3.6, points[chains[('A', 'B')][2]]['x'])
        self.assertTrue(all('distance_m' not in e for e in updated['corridors']['edges']))

    def test_two_directions_keep_independent_lengths_and_attributes(self):
        config = self.direct()
        config['corridors']['edges'][0].update(distance_m=20, people_profile_ids=['P'], custom={'values': [7]})
        config['corridors']['edges'].append(dict(config['corridors']['edges'][0], **{'from': 'B', 'to': 'A', 'distance_m': 30}))
        original = deepcopy(config)
        updated, chains = split_config(config, {('A', 'B'): [.25, .6]})
        edges = updated['corridors']['edges']
        self.assertEqual([5, 7, 8, 12, 10.5, 7.5], [e['distance_m'] for e in edges])
        self.assertEqual(list(reversed(chains[('A', 'B')])), [edges[3]['from']] + [e['to'] for e in edges[3:]])
        self.assertTrue(all(e['width_m'] == 3 and not e['bidirectional'] and e['people_profile_ids'] == ['P'] for e in edges))
        edges[0]['custom']['values'].append(9)
        self.assertEqual([7], edges[1]['custom']['values'])
        self.assertEqual(original, config)

    def test_doors_stay_at_original_nodes_and_names_avoid_locations(self):
        config = reference_config()
        config['locations'].append(dict(name='C0-1', floor=0, x=30, y=30))
        updated, chains = split_config(config, {('A', 'Door'): [.5], ('B', 'Door'): [.5]})
        self.assertEqual(config['corridors']['nodes'][0], updated['corridors']['nodes'][0])
        self.assertEqual({'C0-2', 'C0-3'}, {chain[1] for chain in chains.values()})
        self.assertTrue(all(not n['has_door'] for n in updated['corridors']['nodes'][1:]))

    def test_reference_lists_preserve_direction_and_unaffected_entries(self):
        config = self.direct()
        config['route_profiles'] = {'clean': {'allowed_edges': [['A', 'B']], 'allowed_nodes': ['A', 'B']},
                                    'dirty': {'allowed_edges': [['B', 'A'], ['B', 'Door']]}}
        updated, chains = split_config(config, {('A', 'B'): [.5]})
        n = chains[('A', 'B')][1]
        self.assertEqual([['A', n], [n, 'B']], updated['route_profiles']['clean']['allowed_edges'])
        self.assertEqual([['B', n], [n, 'A'], ['B', 'Door']], updated['route_profiles']['dirty']['allowed_edges'])
        self.assertEqual(['A', 'B', n], updated['route_profiles']['clean']['allowed_nodes'])

    def test_task_local_and_profile_node_union_is_retained(self):
        for fields in [dict(route_profile='clean'), dict(labels=['dirty'])]:
            with self.subTest(fields=fields):
                config = self.direct()
                config['route_profiles'] = {name: {'allowed_nodes': ['B']} for name in ('clean', 'dirty')}
                config['tasks'] = [dict(allowed_nodes=['A'], **fields)]
                updated, chains = split_config(config, {('A', 'B'): [.5]})
                self.assertEqual(['A', chains[('A', 'B')][1]], updated['tasks'][0]['allowed_nodes'])
                self.assertEqual(['B'], updated['route_profiles']['clean']['allowed_nodes'])

    def test_return_profile_does_not_extend_outbound_local_allowance(self):
        config = self.direct()
        config['route_profiles'] = {'clean': {'allowed_nodes': ['B']}}
        config['tasks'] = [dict(allowed_nodes=['A'], return_route_profile='clean')]
        updated, _ = split_config(config, {('A', 'B'): [.5]})
        self.assertEqual(['A'], updated['tasks'][0]['allowed_nodes'])

    def test_task_profile_union_still_routes_after_split(self):
        config = self.direct()
        config['route_profiles'] = {'clean': {'allowed_nodes': ['B']}}
        config['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box', allowed_nodes=['A'], route_profile='clean')]
        updated, _ = split_config(config, {('A', 'B'): [.5]})
        with contextlib.redirect_stdout(io.StringIO()):
            sim = Simulation(updated)
            sim.run()
        self.assertAlmostEqual(9, sim.completed_task_records[0]['duration_sec'])

    def test_empty_allowance_stays_unrestricted_and_partial_stays_partial(self):
        config = self.direct()
        config['route_profiles'] = {'empty': {'allowed_nodes': []}, 'partial': {'allowed_nodes': ['A']}}
        updated, _ = split_config(config, {('A', 'B'): [.5]})
        self.assertEqual(config['route_profiles'], updated['route_profiles'])

    def test_people_and_scenario_resources_expand_in_all_supported_forms(self):
        config = self.direct()
        config['people'] = {'profiles': [{'corridor_edges': ['A <-> B', ['B', 'A'], 'B -> Door']}]}
        config['scenario_events'] = [dict(resource_type='corridor', **fields) for fields in
                                     [dict(resource_ids=['A -> B']), dict(resource_ids='A -> B, B -> Door'), dict(resource_id='B -> A')]]
        updated, chains = split_config(config, {('A', 'B'): [.5]})
        n = chains[('A', 'B')][1]
        self.assertEqual([f'A -> {n}', f'{n} -> B', f'B -> {n}', f'{n} -> A', 'B -> Door'], updated['people']['profiles'][0]['corridor_edges'])
        self.assertEqual([f'A -> {n}', f'{n} -> B'], updated['scenario_events'][0]['resource_ids'])
        self.assertEqual([f'A -> {n}', f'{n} -> B', 'B -> Door'], updated['scenario_events'][1]['resource_ids'])
        self.assertEqual([f'B -> {n}', f'{n} -> A'], updated['scenario_events'][2]['resource_ids'])
        self.assertNotIn('resource_id', updated['scenario_events'][2])

    def test_bad_cuts_and_missing_edges_leave_input_unchanged(self):
        config = self.direct()
        original = deepcopy(config)
        for cuts in [{}, {('A', 'B'): []}, {('A', 'B'): [0]}, {('A', 'B'): [1]},
                     {('A', 'B'): [float('nan')]}, {('A', 'B'): [.8, .2]}, {('A', 'B'): [.5, .5]},
                     {('A', 'B'): [1e-9]}, {('B', 'A'): [.5]}, {('A', 'Missing'): [.5]},
                     {('A', 'B'): [.5], ('B', 'Door'): [.5]}]:
            with self.subTest(cuts=cuts), self.assertRaises(ValueError):
                split_config(config, cuts)
            self.assertEqual(original, config)

    def test_cross_floor_and_coincident_edges_rejected(self):
        for changes in [dict(floor=1), dict(x=0, y=0), dict(x=float('inf'))]:
            config = self.direct()
            config['locations'][1].update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                split_config(config, {('A', 'B'): [.5]})

    def test_invalid_distance_does_not_partially_modify_store(self):
        store = JsonStore(reference_config())
        store.data['corridors']['edges'][1]['distance_m'] = -1
        original = deepcopy(store.data)
        with self.assertRaises(ValueError):
            store.subdivide_corridors({('A', 'Door'): [.5], ('B', 'Door'): [.5]})
        self.assertEqual(original, store.data)

    def test_one_way_path_and_exact_uncongested_task_duration(self):
        for distance, expected in [(None, 9), (20, 14), (0, 4)]:
            config = self.direct()
            if distance is not None:
                config['corridors']['edges'][0]['distance_m'] = distance
            config['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box')]
            updated, _ = split_config(config, {('A', 'B'): [.25, .6]})
            for candidate in (config, updated):
                with contextlib.redirect_stdout(io.StringIO()):
                    sim = Simulation(candidate)
                    sim.run()
                self.assertFalse(sim.failed_task_ids)
                self.assertAlmostEqual(expected, sim.completed_task_records[0]['duration_sec'])
                self.assertIsNone(sim._shortest_path_same_floor(0, 'B', 'A'))

    def test_door_clearance_is_retained_after_subdivision(self):
        config = reference_config()
        for width, fits in [(.8, True), (.80001, False)]:
            config['payloads'][0]['width_m'] = width
            updated, _ = split_config(config, {('A', 'Door'): [.5], ('B', 'Door'): [.5]})
            sim = Simulation(updated)
            result = sim._same_floor_segments(sim.amrs[0], sim.locations['A'], sim.locations['B'], payload=sim.payloads['Box'], orientation='lengthways')
            self.assertEqual(fits, result is not None)
            if fits:
                self.assertAlmostEqual(10, result[2])

    def test_clean_dirty_and_shared_profile_paths_keep_calculated_distances(self):
        config = profile_config()
        updated, _ = split_config(config, {('A', 'Shared'): [.5], ('Clean', 'Shared'): [.25, .5]})
        sim = Simulation(updated)
        for name, distance in [('clean', 10), ('dirty', 14)]:
            rules = sim._resolve_task_route_rules(Task('T', 'A', 'B', 'Box', route_profile=name))
            self.assertAlmostEqual(distance, sim._shortest_path_same_floor(0, 'A', 'B', rules)['distance_m'])
            self.assertAlmostEqual(distance, sim._shortest_path_same_floor(0, 'B', 'A', rules)['distance_m'])

    def test_people_and_outage_apply_to_every_new_physical_section(self):
        config = self.direct()
        config['people_movements'] = [dict(id='P', corridor_edges=['A <-> B'], people_per_trip=3,
                                          start_time='00:00', end_time='00:01', interval_minutes=1)]
        config['scenario_testing'] = dict(enabled=True, active_scenario='Closed', scenarios=[dict(name='Closed', events=[
            dict(resource_type='corridor', resource_ids=['A -> B'], start_time='00:00', end_time='00:01', availability_percent=0)])])
        updated, chains = split_config(config, {('A', 'B'): [.5]})
        sim = Simulation(updated)
        chain = chains[('A', 'B')]
        for a, b in zip(chain, chain[1:]):
            reservations = sim.people_edge_reservations[sim._physical_edge_key(a, b)]
            self.assertEqual(3, reservations[0]['count'])
            self.assertEqual('P', reservations[0]['movement_id'])
            self.assertEqual(0, sim._scenario_event_state('corridor', f'{a} -> {b}', 30)['availability_percent'])
            self.assertEqual(0, sim._scenario_event_state('corridor', f'{b} -> {a}', 30)['availability_percent'])
            self.assertEqual(100, sim._scenario_event_state('corridor', f'{a} -> {b}', 60)['availability_percent'])

    def test_saved_subdivision_reference_matches_nine_seconds(self):
        import json
        path = Path(__file__).resolve().parents[1] / 'verification/scenarios/corridor-subdivided.json'
        with contextlib.redirect_stdout(io.StringIO()):
            sim = Simulation(json.loads(path.read_text(encoding='utf-8')))
            sim.run()
        self.assertEqual(1, len(sim.completed_task_records))
        self.assertFalse(sim.failed_tasks)
        self.assertAlmostEqual(9, sim.completed_task_records[0]['duration_sec'])


class CorridorEditingUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.editor = AMRGraphEditor()
        self.editor._recovery_store = RecoveryStore(Path(self.temp.name) / 'recovery')
        self.editor._drawings_enabled = False
        self.editor.store = JsonStore(reference_config())
        self.editor.store.data['route_profiles'] = {'clean': {'allowed_edges': [['A', 'Door'], ['Door', 'B']]}}
        self.editor.refresh_canvas()
        self.editor._saved_state = self.editor._configuration_state()
        self.editor._reset_edit_history()
        self.event = Mock()
        self.event.modifiers.return_value = Qt.NoModifier

    def tearDown(self):
        with patch.object(self.editor, '_confirm_unsaved_changes', return_value=True):
            self.editor.close()
        self.temp.cleanup()

    def test_bulk_subdivision_and_all_references_are_one_undo_redo(self):
        before = deepcopy(self.editor.store.data)
        self.editor.selected_edge_keys = {('A', 'Door'), ('B', 'Door')}
        self.assertTrue(self.editor.subdivide_selected_corridors(3))
        after = deepcopy(self.editor.store.data)
        self.assertEqual(6, len(after['corridors']['edges']))
        self.assertEqual(2, len(self.editor.edit_history.entries))
        self.assertTrue(self.editor.undo_edit())
        self.assertEqual(before, self.editor.store.data)
        self.assertTrue(self.editor.redo_edit())
        self.assertEqual(after, self.editor.store.data)

    def test_cancel_and_invalid_edit_do_not_add_history(self):
        self.editor.selected_edge_keys = {('A', 'Door')}
        with patch.object(QInputDialog, 'getInt', return_value=(3, False)):
            self.assertFalse(self.editor.subdivide_selected_corridors())
        with patch.object(QMessageBox, 'information'):
            self.assertFalse(self.editor.split_corridor_at(('A', 'Door'), 0, 0))
        self.assertEqual(1, len(self.editor.edit_history.entries))

    def test_node_tool_inserts_on_edge_and_reuses_existing_endpoint(self):
        self.editor._set_edit_mode('corridor_node')
        self.editor.snap_check.setChecked(True)
        self.editor.on_left_click(self.event, 1.58, -1.94)
        new = self.editor.store.data['corridors']['nodes'][-1]
        self.assertAlmostEqual(1.5, new['x'])
        self.assertAlmostEqual(2, new['y'])
        self.assertEqual(3, len(self.editor.store.data['corridors']['edges']))
        self.assertEqual(2, len(self.editor.edit_history.entries))
        before = deepcopy(self.editor.store.data)
        self.editor.on_left_click(self.event, 0, 0)
        self.assertEqual(before, self.editor.store.data)
        self.assertEqual(2, len(self.editor.edit_history.entries))
