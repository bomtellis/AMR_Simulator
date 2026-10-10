"""Independent trim/extend distances, connectivity, restrictions and undo."""
from copy import deepcopy
import unittest
from tests import test_corridor_editing as editing
from visualiser.corridor_endpoint import trim_extend
from visualiser.model_layers import set_layer,assign


def scenario(boundary_x=4):
    config = editing.reference_config()
    config['corridors']['nodes'] = [dict(name='Tip',floor=0,x=2,y=0,has_door=True,door_clear_width_m=.9),
        dict(name='C',floor=0,x=boundary_x,y=-2),dict(name='D',floor=0,x=boundary_x,y=2)]
    config['corridors']['edges'] = [{'from':'A','to':'Tip','bidirectional':False,'distance_m':6,'width_m':2},
        {'from':'Tip','to':'A','bidirectional':False,'distance_m':10,'width_m':3},
        {'from':'C','to':'D','bidirectional':False,'distance_m':8,'width_m':4}]
    config['route_profiles'] = {'clean':dict(allowed_nodes=['A','Tip','C','D'],allowed_edges=[['A','Tip'],['C','D']])}
    return config


class EndpointGeometryTests(unittest.TestCase):
    def test_simulator_uses_joined_directed_path_and_retained_door_restriction(self):
        config = scenario()
        destination = config['corridors']['nodes'].pop()
        config['locations'].append(destination)
        before = editing.Simulation(config)
        self.assertIsNone(before._same_floor_segments(before.amrs[0],before.locations['A'],before.locations['D']))
        staged,_ = trim_extend(editing.JsonStore(config),('A','Tip'),'Tip',('C','D'))
        sim = editing.Simulation(staged.data)
        segments,duration,distance = sim._same_floor_segments(sim.amrs[0],sim.locations['A'],sim.locations['D'])
        self.assertEqual(16,distance)  # source 6 * 2 + half of boundary 8
        self.assertEqual(8,duration)  # 16 metres / 2 metres per second
        self.assertEqual([('A','Tip'),('Tip','D')],[(s['from'],s['to']) for s in segments])
        self.assertIsNone(sim._same_floor_segments(sim.amrs[0],sim.locations['D'],sim.locations['A']))
        wide = deepcopy(staged.data)
        wide['amrs'][0]['width_m'] = 1.0
        blocked = editing.Simulation(wide)
        self.assertIsNone(blocked._same_floor_segments(blocked.amrs[0],blocked.locations['A'],blocked.locations['D']))

    def test_extension_preserves_identity_attributes_and_rewrites_boundary_access(self):
        store = editing.JsonStore(scenario())
        before = deepcopy(store.data)
        staged,result = trim_extend(store,('A','Tip'),'Tip',('C','D'))
        self.assertEqual('Extend',result['operation'])
        self.assertEqual((2,4),(result['old_length'],result['new_length']))
        self.assertEqual([12,20,4,4],[e['distance_m'] for e in staged.data['corridors']['edges']])
        self.assertEqual([2,3,4,4],[e['width_m'] for e in staged.data['corridors']['edges']])
        self.assertTrue(all(not e['bidirectional'] for e in staged.data['corridors']['edges']))
        self.assertEqual(['C','Tip','D'],result['boundary_chain'])
        self.assertEqual([['A','Tip'],['C','Tip'],['Tip','D']],staged.data['route_profiles']['clean']['allowed_edges'])
        self.assertEqual(.9,staged.all_points()['Tip']['door_clear_width_m'])
        self.assertEqual(3,len(staged.data['corridors']['nodes']))
        self.assertEqual(before,store.data)

    def test_trim_has_independent_half_length_expectation(self):
        staged,result = trim_extend(editing.JsonStore(scenario(1)),('A','Tip'),'Tip',('C','D'))
        self.assertEqual('Trim',result['operation'])
        self.assertEqual((1,0),(staged.all_points()['Tip']['x'],staged.all_points()['Tip']['y']))
        self.assertEqual([3,5,4,4],[e['distance_m'] for e in staged.data['corridors']['edges']])

    def test_invalid_junction_parallel_occupied_behind_and_locked_boundary_reject(self):
        for case in ('junction','parallel','occupied','behind','locked','auto','other_floor','boundary_end'):
            config = scenario(-1 if case == 'behind' else 4)
            if case == 'junction':
                config['corridors']['edges'].append({'from':'Tip','to':'B'})
            elif case == 'parallel':
                config['corridors']['nodes'][1].update(x=3,y=1)
                config['corridors']['nodes'][2].update(x=4,y=1)
            elif case == 'occupied':
                config['corridors']['nodes'].append(dict(name='Existing',floor=0,x=4,y=0))
            elif case == 'locked':
                config = assign(set_layer(config,'Locked',locked=True),set(),{('C','D')},'Locked')
            elif case == 'auto':
                config['corridors']['auto_connect'] = True
            elif case == 'other_floor':
                config['corridors']['nodes'][1]['floor'] = 1
            elif case == 'boundary_end':
                config['corridors']['nodes'][1]['y'] = 0
            store = editing.JsonStore(config)
            before = deepcopy(store.data)
            with self.subTest(case=case),self.assertRaises(ValueError):
                trim_extend(store,('A','Tip'),'Tip',('C','D'))
            self.assertEqual(before,store.data)


class EndpointUiTests(unittest.TestCase):
    setUpClass = classmethod(editing.CorridorEditingUiTests.setUpClass.__func__)
    tearDown = editing.CorridorEditingUiTests.tearDown

    def setUp(self):
        editing.CorridorEditingUiTests.setUp(self)
        self.editor.store = editing.JsonStore(scenario())
        self.editor.refresh_canvas()
        self.editor._reset_edit_history()
        self.editor.selected_edge_keys = {('A','Tip')}

    def test_boundary_pick_preview_and_apply_are_one_undo(self):
        e = self.editor
        before = deepcopy(e.store.data)
        e.workbench.endpoint_action.trigger()
        bar = e.cad_endpoint_input
        self.assertEqual('Tip',bar.endpoint.currentText())
        bar.begin_pick()
        p = e.world_to_scene(4,0)
        e.on_left_click(self.event,p.x(),p.y())
        self.assertIsNone(bar.mouse_stage)
        self.assertTrue(bar.apply_button.isEnabled())
        preview = deepcopy(bar.preview_store.data)
        self.assertEqual(before,e.store.data)
        bar.apply_button.click()
        self.assertEqual(preview,e.store.data)
        self.assertEqual(2,len(e.edit_history.entries))
        self.assertTrue(e.undo_edit())
        self.assertEqual(before,e.store.data)
        self.assertTrue(e.redo_edit())
        self.assertEqual(preview,e.store.data)

    def test_cancel_floor_change_and_invalid_boundary_preserve_inputs(self):
        e = self.editor
        before = deepcopy(e.store.data)
        e.show_corridor_endpoint()
        self.assertFalse(e.cad_endpoint_input.apply_button.isEnabled())
        e.cad_endpoint_input.begin_pick()
        e.on_right_click(self.event,0,0)
        self.assertTrue(e.cad_endpoint_input.isHidden())
        e.show_corridor_endpoint()
        e.floor_spin.setValue(1)
        self.assertTrue(e.cad_endpoint_input.isHidden())
        self.assertEqual(before,e.store.data)
