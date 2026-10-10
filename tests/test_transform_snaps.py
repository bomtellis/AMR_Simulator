"""Independent transform snap coordinates; reference picking never edits topology."""
from copy import deepcopy
import unittest
from unittest.mock import patch
from tests import test_corridor_editing as editing
from visualiser.cad_transform_pick import pick_point
from visualiser import model_layers


class TransformSnapTests(unittest.TestCase):
    setUpClass = classmethod(editing.CorridorEditingUiTests.setUpClass.__func__)
    tearDown = editing.CorridorEditingUiTests.tearDown

    def setUp(self):
        editing.CorridorEditingUiTests.setUp(self)
        e = self.editor
        e.store.data['locations'] = []
        e.store.data['corridors']['nodes'] = [dict(name=n,floor=0,x=x,y=y) for n,x,y in
                                             [('L',0,0),('R',10,0),('S',5,-5),('N',5,5)]]
        e.store.data['corridors']['edges'] = [{'from':'L','to':'R'}, {'from':'S','to':'N'}]
        e.snap_check.setChecked(False)
        e.refresh_canvas()

    def snap(self, mode, x,y,anchor=None):
        e = self.editor
        e.object_snap_mode.setCurrentIndex(e.object_snap_mode.findData(mode))
        p = e.world_to_scene(x,y)
        return pick_point(e,p.x(),p.y(),anchor=anchor)

    def test_pointer_snaps_are_coalesced_and_final_click_uses_its_own_position(self):
        e = self.editor
        e.selected_point_names = {'L'}
        e.show_selection_move()
        bar = e.cad_move_input
        bar.begin_mouse()
        p = e.world_to_scene(2,3)
        e.on_left_click(self.event,p.x(),p.y())
        with patch('visualiser.cad_transform_pick.pick_point', wraps=pick_point) as resolve:
            for x in range(10,60):
                p = e.world_to_scene(x,3)
                bar.pointer_moved(p.x(),p.y())
            self.assertEqual(0,resolve.call_count)
            bar.mouse_timer.stop()
            bar._update_mouse_preview()
            self.assertEqual(1,resolve.call_count)
            p = e.world_to_scene(100,3)
            bar.pointer_moved(p.x(),p.y())
            p = e.world_to_scene(22,3)
            e.on_left_click(self.event,p.x(),p.y())
            self.assertEqual(2,resolve.call_count)
        self.assertEqual((20,0),(e.store.all_points()['L']['x'],e.store.all_points()['L']['y']))
        self.assertIsNone(bar.pending_pointer)

    def test_perpendicular_move_uses_base_point_and_preserves_edge_identity(self):
        e = self.editor
        e.selected_point_names = {'L'}
        e.show_selection_move()
        bar = e.cad_move_input
        bar.begin_mouse()
        p = e.world_to_scene(2,3)
        e.on_left_click(self.event,p.x(),p.y())
        e.object_snap_mode.setCurrentIndex(e.object_snap_mode.findData('perpendicular'))
        edges = deepcopy(e.store.data['corridors']['edges'])
        p = e.world_to_scene(2.2,.1)
        e.on_left_click(self.event,p.x(),p.y())
        self.assertEqual((0,-3),(e.store.all_points()['L']['x'],e.store.all_points()['L']['y']))
        self.assertEqual(edges,e.store.data['corridors']['edges'])

    def test_nearest_endpoints_midpoints_and_perpendicular_have_independent_coordinates(self):
        before = deepcopy(self.editor.store.data)
        self.assertEqual((0,0),self.snap('endpoints',.2,.1))
        self.assertEqual((3,0),self.snap('nearest',3,.2))
        self.assertEqual((5,0),self.snap('midpoints',5.2,.2))
        self.assertEqual((2,0),self.snap('perpendicular',2.2,.1,anchor=(2,3)))
        self.assertEqual((2.2,.1),self.snap('perpendicular',2.2,.1))
        self.assertEqual(before,self.editor.store.data)

    def test_intersection_is_only_a_reference_and_does_not_split_corridors(self):
        before = deepcopy(self.editor.store.data)
        self.assertEqual((5,0),self.snap('intersections',5.1,.2))
        self.assertEqual(before,self.editor.store.data)
        self.assertEqual(4,len(self.editor.store.data['corridors']['nodes']))
        self.assertEqual(2,len(self.editor.store.data['corridors']['edges']))

    def test_hidden_edges_do_not_attract_but_visible_lines_with_hidden_endpoints_do(self):
        e = self.editor
        e.store.data = model_layers.set_layer(e.store.data,'Hidden',visible=False)
        e.store.data = model_layers.assign(e.store.data,{'L','R'},set(),'Hidden')
        self.assertEqual((5,0),self.snap('midpoints',5.2,.2))
        self.assertEqual((.2,.1),self.snap('endpoints',.2,.1))
        e.store.data = model_layers.assign(e.store.data,set(),{('L','R'),('N','S')},'Hidden')
        self.assertEqual((5.2,.2),self.snap('midpoints',5.2,.2))
        self.assertEqual((5.1,.2),self.snap('intersections',5.1,.2))

    def test_snap_disabled_and_floor_filter_are_respected(self):
        e = self.editor
        e.object_snap_check.setChecked(False)
        self.assertEqual((5.2,.2),self.snap('midpoints',5.2,.2))
        e.snap_check.setChecked(True)
        e.grid_spacing_spin.setValue(.5)
        self.assertEqual((5.5,.5),self.snap('midpoints',5.4,.4))
        e.object_snap_check.setChecked(True)
        e.floor_spin.setValue(1)
        e.snap_check.setChecked(False)
        self.assertEqual((5.2,.2),self.snap('midpoints',5.2,.2))
