"""Optional automatic junctions along a newly drawn corridor."""
from copy import deepcopy
import unittest
from tests import test_corridor_editing as editing
from tests.test_crossing_junction import crossing
from visualiser.models import JsonStore
from visualiser.corridor_editing import draw_step, route_crossings


def scenario():
    config = crossing()
    config['corridors']['edges'] = [config['corridors']['edges'][1]]
    config['locations'] += [dict(name='E',floor=0,x=7,y=-3),dict(name='F',floor=0,x=7,y=7)]
    config['corridors']['edges'].append(dict({'from':'E','to':'F'},width_m=1.8,bidirectional=False,distance_m=50))
    return config


class DrawCrossingTests(unittest.TestCase):
    def test_two_ordered_crossings_preserve_attributes_and_profiles(self):
        config = scenario()
        before = deepcopy(config)
        points = JsonStore(config).all_points()
        self.assertEqual([(4,0),(7,0)], route_crossings(points,config['corridors']['edges'],0,(0,0),(10,0)))
        updated, target = draw_step(config,points,'A',0,10,0,connect_crossings=True)
        self.assertEqual(before, config)
        self.assertEqual('B',target['name'])
        self.assertEqual(2,len(updated['corridors']['nodes']))
        self.assertEqual(7,len(updated['corridors']['edges']))
        old_vertical = updated['corridors']['edges'][:4]
        self.assertEqual([9,21,15,35],[e['distance_m'] for e in old_vertical])
        self.assertEqual([True,True,False,False],[e['bidirectional'] for e in old_vertical])
        names = {n['x']:n['name'] for n in updated['corridors']['nodes']}
        self.assertIn(names[4],updated['route_profiles']['dirty']['allowed_nodes'])
        self.assertNotIn(names[7],updated['route_profiles']['dirty']['allowed_nodes'])
        self.assertEqual([('A',names[4]),(names[4],names[7]),(names[7],'B')],
                         [(e['from'],e['to']) for e in updated['corridors']['edges'][4:]])

    def test_default_retains_unconnected_crossings(self):
        config = scenario()
        updated, _ = draw_step(config,JsonStore(config).all_points(),'A',0,10,0)
        self.assertEqual([],updated['corridors']['nodes'])
        self.assertEqual(3,len(updated['corridors']['edges']))

    def test_existing_door_reused_and_ambiguous_second_crossing_rolls_back(self):
        config = scenario()
        config['corridors']['nodes'] = [dict(name='Door',floor=0,x=4,y=0,has_door=True,door_clear_width_m=.7)]
        updated, _ = draw_step(config,JsonStore(config).all_points(),'A',0,10,0,connect_crossings=True)
        self.assertEqual(config['corridors']['nodes'][0],updated['corridors']['nodes'][0])
        config['corridors']['nodes'] += [dict(name=n,floor=0,x=7,y=0) for n in ('X','Y')]
        store = JsonStore(config)
        before = deepcopy(store.data)
        with self.assertRaises(ValueError):
            store.draw_corridor_step('A',0,10,0,connect_crossings=True)
        self.assertEqual(before,store.data)

    def test_floor_filter_and_overlapping_route_rejection(self):
        config = scenario()
        points = JsonStore(config).all_points()
        for n in ('C','D','E','F'):
            points[n]['floor'] = 1
        self.assertEqual([],route_crossings(points,config['corridors']['edges'],0,(0,0),(10,0)))
        with self.assertRaisesRegex(ValueError,'overlaps'):
            route_crossings(JsonStore(config).all_points(),config['corridors']['edges'],0,(4,-2),(4,5))


class DrawCrossingUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = editing.QApplication.instance() or editing.QApplication([])

    setUp = editing.CorridorEditingUiTests.setUp
    tearDown = editing.CorridorEditingUiTests.tearDown

    def test_preview_complete_segment_and_splits_are_one_undo(self):
        self.editor.store = JsonStore(scenario())
        self.editor.refresh_canvas()
        self.editor._reset_edit_history()
        self.editor._set_edit_mode('corridor_draw')
        self.assertFalse(self.editor.connect_crossings_check.isChecked())
        self.editor.draw_next_corridor(0,0)
        before = deepcopy(self.editor.store.data)
        self.editor.connect_crossings_check.setChecked(True)
        self.editor.cad_drawing_input.coordinate_edit.setText('10,0')
        self.assertEqual([(4,0),(7,0)],self.editor.corridor_draw_preview['crossings'])
        self.assertIn('2 junction',self.editor.cad_drawing_input.feedback_label.text())
        self.assertEqual(before,self.editor.store.data)
        self.assertTrue(self.editor.submit_corridor_coordinate())
        self.assertEqual(7,len(self.editor.store.data['corridors']['edges']))
        self.editor.finish_corridor_drawing()
        self.assertEqual(2,len(self.editor.edit_history.entries))
        self.assertTrue(self.editor.undo_edit())
        self.assertEqual(before,self.editor.store.data)
