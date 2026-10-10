"""Layout context actions edit only node permissions and preserve draft isolation."""
from copy import deepcopy
from unittest.mock import patch
import unittest

from tests import test_corridor_editing as editing
from PySide6.QtCore import QPointF,QTimer,Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QMenu


class RouteProfileContextTests(unittest.TestCase):
    setUpClass = classmethod(editing.CorridorEditingUiTests.setUpClass.__func__)
    tearDown = editing.CorridorEditingUiTests.tearDown

    def setUp(self):
        editing.CorridorEditingUiTests.setUp(self)
        self.editor.workspace.activate('layout')
        self.editor._set_edit_mode('select_move')
        self.event.globalPosition.return_value = QPointF(100, 100)
        self.menus = []

    def right_click(self, x, y, choose=None):
        menus = self.menus
        class InspectMenu(QMenu):
            def exec(menu, *_):
                menus.append(menu)
                if choose:
                    selected = choose(menu)
                    selected.trigger()
                    return selected
        with patch('app.QMenu', InspectMenu):
            self.editor.on_right_click(self.event, x, -y)
        return self.menus[-1]

    def profiles(self, menu, label='Add node to route profile'):
        # This Qt binding gives temporary menuAction wrappers ownership of
        # their submenu; keep them alive while inspecting and triggering it.
        menu.inspected_actions = menu.actions()
        return next(action.menu() for action in menu.inspected_actions if action.text() == label)

    def prepare(self):
        self.editor.refresh_canvas()
        self.editor._reset_edit_history()
        self.editor._saved_state = self.editor._configuration_state()

    def test_single_node_menu_updates_navigation_and_is_one_undoable_change(self):
        self.editor.store.data['route_profiles']['clean']['allowed_nodes'] = ['A', 'B']
        self.editor.store.data['route_profiles']['dirty'] = {'allowed_nodes': ['B']}
        self.editor.store.data['tasks'] = [dict(id='T', pickup='A', dropoff='B', payload='Box', route_profile='clean')]
        self.prepare()
        before = deepcopy(self.editor.store.data)
        self.editor.show_project_checks()
        self.editor.workspace.activate('layout')
        checks = self.editor.checks_panel
        checks.check_now()
        self.assertEqual('Blocked', checks.report.route_checks[0]['status'])
        self.right_click(3, 4, lambda menu: self.profiles(menu).actions()[0])
        self.assertEqual(['A', 'B', 'Door'], self.editor.store.data['route_profiles']['clean']['allowed_nodes'])
        expected = deepcopy(before)
        expected['route_profiles']['clean']['allowed_nodes'].append('Door')
        self.assertEqual(expected, self.editor.store.data)
        self.assertTrue(self.editor.has_unsaved_changes())
        self.assertFalse(checks.current())
        self.assertIn('STALE', checks.route_checks_view.summary.text())
        self.assertEqual('clean', self.editor.route_display_combo.currentData())
        self.assertTrue(self.editor.route_view_toolbar.expanded)
        checks.check_now()
        self.assertEqual('Reachable', checks.report.route_checks[0]['status'])
        self.assertEqual(2, len(self.editor.edit_history.entries))
        self.assertTrue(self.editor.undo_edit())
        self.assertEqual(before, self.editor.store.data)
        self.assertTrue(self.editor.redo_edit())
        self.assertEqual(expected, self.editor.store.data)

    def test_multi_selection_adds_only_missing_routable_nodes_without_changing_edges(self):
        self.editor.store.data['route_profiles']['clean']['allowed_nodes'] = ['Door']
        self.editor.store.data['departments'] = [dict(name='Service', floor=0, x=12, y=12)]
        self.prepare()
        before = deepcopy(self.editor.store.data)
        self.editor.selected_point_names = {'Door', 'B', 'Service'}
        self.right_click(100, 100, lambda menu: self.profiles(menu, 'Add selected nodes to route profile').actions()[0])
        expected = deepcopy(before)
        expected['route_profiles']['clean']['allowed_nodes'].append('B')
        self.assertEqual(expected, self.editor.store.data)

    def test_first_node_filter_is_labelled_and_already_included_is_checked_and_disabled(self):
        self.prepare()
        menu = self.right_click(3, 4)
        action = self.profiles(menu).actions()[0]
        self.assertEqual('clean (start node filter)', action.text())
        self.assertIn('Currently all nodes are permitted', action.toolTip())
        self.assertTrue(action.isEnabled())
        self.right_click(3, 4, lambda menu: self.profiles(menu).actions()[0])
        self.assertEqual(['Door'], self.editor.store.data['route_profiles']['clean']['allowed_nodes'])
        menu = self.right_click(3, 4)
        action = self.profiles(menu).actions()[0]
        self.assertTrue(action.isChecked())
        self.assertFalse(action.isEnabled())
        self.assertEqual(2, len(self.editor.edit_history.entries))

    def test_cancel_and_no_profiles_offer_manage_without_changing_configuration(self):
        self.editor.store.data['route_profiles'] = {}
        self.prepare()
        before = deepcopy(self.editor.store.data)
        menu = self.right_click(3, 4)
        actions = self.profiles(menu).actions()
        self.assertEqual(['Manage route profiles…'], [action.text() for action in actions])
        with patch.object(self.editor, 'manage_route_profiles') as manage:
            menu = QMenu()
            self.editor._add_route_profile_node_menu(menu, {'Door'})
            self.profiles(menu).actions()[0].trigger()
        manage.assert_called_once()
        self.assertEqual(before, self.editor.store.data)
        self.assertEqual(1, len(self.editor.edit_history.entries))

    def test_lift_stops_are_routable_but_departments_are_not(self):
        self.editor.store.data['lifts'] = [dict(id='L', floor_locations={'0': dict(x=20, y=20)})]
        self.editor.store.data['departments'] = [dict(name='Service', floor=0, x=12, y=12)]
        self.prepare()
        menu = self.right_click(12, 12)
        self.assertNotIn('Add node to route profile', [action.text() for action in menu.actions()])
        self.right_click(20, 20, lambda menu: self.profiles(menu).actions()[0])
        self.assertEqual(['L-F0'], self.editor.store.data['route_profiles']['clean']['allowed_nodes'])
        self.assertNotIn('allowed_lifts', self.editor.store.data['route_profiles']['clean'])

    def test_unknown_nodes_profiles_and_editing_lock_do_not_modify_permissions(self):
        self.prepare()
        before = deepcopy(self.editor.store.data)
        self.assertFalse(self.editor.add_nodes_to_route_profile('missing', {'Door'}))
        self.assertFalse(self.editor.add_nodes_to_route_profile('clean', {'missing'}))
        with patch.object(self.editor, 'project_editing_locked', return_value=True):
            self.assertFalse(self.editor.add_nodes_to_route_profile('clean', {'Door'}))
        self.assertEqual(before, self.editor.store.data)
        self.assertEqual(1, len(self.editor.edit_history.entries))

    def test_real_popup_profile_action_accepts_a_mouse_click(self):
        self.prepare()
        self.editor.show()
        self.app.processEvents()
        errors = []
        def choose():
            menu = QApplication.activePopupWidget()
            try:
                submenu = self.profiles(menu)
                parent_action = next(a for a in menu.inspected_actions if a.text() == 'Add node to route profile')
                submenu.popup(menu.mapToGlobal(menu.actionGeometry(parent_action).topRight()))
                self.app.processEvents()
                action = submenu.actions()[0]
                QTest.mouseClick(submenu, Qt.LeftButton, pos=submenu.actionGeometry(action).center())
            except Exception as exc:
                errors.append(exc)
            finally:
                menu.close()
        timeout = QTimer(self.editor)
        timeout.setSingleShot(True)
        timeout.timeout.connect(lambda: QApplication.activePopupWidget().close() if QApplication.activePopupWidget() else None)
        timeout.start(1000)
        QTimer.singleShot(0, choose)
        try:
            self.editor.on_right_click(self.event, 3, -4)
        finally:
            timeout.stop()
        self.assertEqual([], errors)
        self.assertEqual(['Door'], self.editor.store.data['route_profiles']['clean']['allowed_nodes'])
        self.assertEqual(2, len(self.editor.edit_history.entries))


if __name__ == '__main__':
    unittest.main()
