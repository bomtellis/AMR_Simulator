"""Combined snap geometry and visible department/status controls."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from tests import test_corridor_editing as editing
from visualiser.corridor_editing import drawing_target
from visualiser.cad_transform_pick import pick_point


class CombinedSnapGeometryTests(unittest.TestCase):
    def setUp(self):
        self.points = {'A': dict(x=0, y=0, floor=0), 'B': dict(x=10, y=0, floor=0),
                       'C': dict(x=3, y=-4, floor=0), 'D': dict(x=3, y=6, floor=0)}
        self.edges = [dict(zip(('from', 'to'), pair)) for pair in [('A', 'B'), ('C', 'D')]]

    def target(self, x, y, modes, **kwargs):
        return drawing_target(self.points, self.edges, 0, x, y, snap=False,
                              snap_mode=modes, **kwargs)

    def test_endpoint_midpoint_and_intersection_can_all_attract(self):
        modes = ('endpoints', 'midpoints', 'intersections')
        self.assertEqual('A', self.target(.1, .1, modes)['name'])
        self.assertEqual('midpoint', self.target(5.1, .2, modes)['snap_label'])
        self.assertEqual('junction', self.target(3.1, .2, modes)['kind'])
        self.assertEqual('new', self.target(3.1, .2, ('endpoints', 'midpoints'))['kind'])

    def test_nearest_is_fallback_and_specific_targets_compete_by_distance(self):
        modes = ('nearest', 'midpoints', 'perpendicular')
        # Midpoint is closer than the perpendicular foot from (4, 3).
        self.assertEqual((5, 0, 'midpoint'), tuple(self.target(4.8, .1, modes, anchor=(4, 3))[k]
                                                for k in ('x', 'y', 'snap_label')))
        target = self.target(4.1, .1, modes, anchor=(4, 3))
        self.assertEqual((4, 0, 'perpendicular'), tuple(target[k] for k in ('x', 'y', 'snap_label')))
        self.assertEqual('edge', self.target(7, .2, modes)['snap_label'])

    def test_disabled_empty_and_floor_constraints_keep_exact_topology(self):
        for modes, kwargs in [((), {}), (('endpoints', 'midpoints'), {'object_snap': False})]:
            self.assertEqual('new', self.target(.1, .1, modes, **kwargs)['kind'])
            self.assertEqual('point', self.target(0, 0, modes, **kwargs)['kind'])
            self.assertEqual('edge', self.target(7, 0, modes, **kwargs)['kind'])
        self.points['B']['floor'] = 1
        self.assertEqual('new', self.target(5.1, .2, ('endpoints', 'midpoints'))['kind'])
        with self.assertRaises(ValueError):
            self.target(5, 0, ('endpoints', 'unknown'))

    def test_combined_targets_preserve_direction_constraint(self):
        target = self.target(5.1, .2, ('endpoints', 'midpoints', 'perpendicular'),
                             anchor=(0, .2), angle_step=90)
        self.assertAlmostEqual(.2, target['y'])


class CadSnapControlsTests(unittest.TestCase):
    setUpClass = classmethod(editing.CorridorEditingUiTests.setUpClass.__func__)
    setUp = editing.CorridorEditingUiTests.setUp
    tearDown = editing.CorridorEditingUiTests.tearDown

    def test_toggles_combine_presets_and_keep_selections_when_disabled(self):
        editor = self.editor
        controls = editor.snap_controls
        before = deepcopy(editor.store.data)
        history = deepcopy(editor.edit_history.entries)
        controls.buttons['endpoints'].click()
        controls.buttons['midpoints'].click()
        self.assertEqual({'nearest', 'endpoints', 'midpoints'}, set(editor.object_snap_mode.currentData()))
        controls.master.click()
        self.assertFalse(editor.object_snap_check.isChecked())
        self.assertTrue(controls.buttons['midpoints'].isChecked())
        self.assertFalse(controls.buttons['midpoints'].isEnabled())
        editor.cad_toolbar.object_snap_action.trigger()
        self.assertTrue(controls.master.isChecked())
        self.assertTrue(controls.buttons['midpoints'].isEnabled())
        editor.object_snap_mode.setCurrentIndex(editor.object_snap_mode.findData('perpendicular'))
        self.assertEqual(['perpendicular'], [mode for mode, button in controls.buttons.items() if button.isChecked()])
        controls.buttons['perpendicular'].click()
        self.assertEqual((), editor.object_snap_mode.currentData())
        self.assertEqual(before, editor.store.data)
        self.assertEqual(history, editor.edit_history.entries)

    def test_combined_preview_commit_undo_and_transform_use_same_targets(self):
        editor = self.editor
        editor._set_edit_mode('corridor_draw')
        editor.snap_controls.buttons['endpoints'].click()
        editor.snap_controls.buttons['midpoints'].click()
        before = deepcopy(editor.store.data)
        editor.cad_drawing_input.coordinate_edit.setText('.1,.1')
        self.assertEqual('A', editor.corridor_draw_preview['name'])
        self.assertTrue(editor.submit_corridor_coordinate())
        editor.cad_drawing_input.coordinate_edit.setText('1.6,2.1')
        self.assertEqual('midpoint', editor.corridor_draw_preview['snap_label'])
        self.assertEqual((1.5, 2), pick_point(editor, 1.6, -2.1))
        self.assertTrue(editor.submit_corridor_coordinate())
        node = editor.store.all_points()[editor.corridor_draw_start]
        self.assertEqual((1.5, 2), (node['x'], node['y']))
        editor.finish_corridor_drawing()
        self.assertTrue(editor.undo_edit())
        self.assertEqual(before, editor.store.data)

    def test_nearest_fallback_keeps_point_priority_for_draw_and_transform(self):
        editor = self.editor
        editor.snap_controls.buttons['midpoints'].click()
        target = drawing_target(editor.store.all_points(), editor.store.data['corridors']['edges'],
                                0, .1, .05, snap=False, snap_mode=editor.object_snap_mode.currentData())
        self.assertEqual('A', target['name'])
        self.assertEqual((0, 0), pick_point(editor, .1, -.05))

    def test_department_tools_open_existing_manager_and_place_on_current_floor(self):
        editor = self.editor
        toolbar = editor.cad_toolbar
        self.assertIn(toolbar.departments_action, toolbar.departments_menu.actions())
        toolbar.mode_actions['department'].trigger()
        self.assertEqual('department', editor._current_edit_mode())
        editor.floor_spin.setValue(2)
        with patch.object(editor, 'create_department_at_position') as place:
            editor.on_left_click(self.event, 12, -8)
            place.assert_called_once_with(12, 8, 2)
        with patch('app.DepartmentListDialog') as dialog:
            toolbar.departments_action.trigger()
            dialog.return_value.exec.assert_called_once_with()
            self.assertEqual(2, dialog.call_args.kwargs['current_floor'])
            self.assertEqual(editor._save_departments, dialog.call_args.kwargs['on_save'])

    def test_bottom_right_controls_fit_small_window_and_follow_stage_and_run_lock(self):
        editor = self.editor
        editor.resize(1024, 768)
        editor.show()
        self.app.processEvents()
        controls = editor.snap_controls
        self.assertTrue(controls.isVisible())
        rect = controls.rect()
        top_left = controls.mapTo(editor, rect.topLeft())
        bottom_right = controls.mapTo(editor, rect.bottomRight())
        self.assertGreater(top_left.y(), editor.height() - 65)
        self.assertGreater(bottom_right.x(), editor.width() - 60)
        self.assertLess(bottom_right.x(), editor.width())
        for button in (controls.master, *controls.buttons.values()):
            self.assertTrue(button.isVisible())
            self.assertTrue(rect.contains(button.geometry()))
        toolbar_rect = editor.cad_toolbar.rect()
        self.assertTrue(toolbar_rect.contains(editor.cad_toolbar.widgetForAction(editor.cad_toolbar.mode_actions['department']).geometry()))
        with patch.object(editor, 'project_editing_locked', return_value=True):
            editor.workspace._sync_panels()
            self.assertFalse(controls.isEnabled())
            self.assertFalse(editor.cad_toolbar.departments_action.isEnabled())
            self.assertFalse(editor.cad_toolbar.mode_actions['department'].isEnabled())
        editor.workspace.configuration()
        self.assertTrue(controls.isHidden())
        editor.workspace.show_page('layout', editor.canvas)
        self.assertTrue(controls.isVisible())
        self.assertTrue(controls.isEnabled())
