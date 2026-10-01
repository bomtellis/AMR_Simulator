import os
import sys
import unittest
from copy import deepcopy
from types import SimpleNamespace
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "visualiser"))

from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtCore import Qt, QCoreApplication, QEvent

from dialogs import InventorySpacesDialog, LocationSpacesManagerDialog
from models import JsonStore
from inventory_spaces_manager import resize_space, space_geometry, similar_layout


class _EditorStub(QWidget):
    def __init__(self, store):
        super().__init__()
        self.store = store
        self.loaded_dxf_floor = 0
        self.dxf_scene = None


class LocationSpacesManagerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.store = JsonStore(
            {
                "departments": [
                    {
                        "id": "D1",
                        "task_generation_locations": {
                            "stores": {
                                "dropoff_zone_locations": ["Zone"],
                            }
                        },
                    }
                ],
                "payloads": [
                    {
                        "name": "Trolley",
                        "length_m": 1.0,
                        "width_m": 0.6,
                        "height_m": 1.2,
                    }
                ],
                "amrs": [
                    {
                        "name": "AMR",
                        "length_m": 1.0,
                        "width_m": 0.7,
                        "height_m": 0.5,
                    }
                ],
                "locations": [
                    {
                        "name": "Zone",
                        "floor": 0,
                        "x": 0,
                        "y": 0,
                        "inventory_spaces": [
                            {
                                "name": "Payload bay",
                                "points": [
                                    {"dx": -0.5, "dy": -0.3},
                                    {"dx": 0.5, "dy": -0.3},
                                    {"dx": 0.5, "dy": 0.3},
                                    {"dx": -0.5, "dy": 0.3},
                                ],
                                "payload_slots": [
                                    {"payload": "Trolley", "dx": 0, "dy": 0}
                                ],
                                "height_m": 1.2,
                                "flexible": False,
                            },
                            {
                                "name": "Charging bay",
                                "points": [
                                    {"dx": 1.5, "dy": -0.35},
                                    {"dx": 2.5, "dy": -0.35},
                                    {"dx": 2.5, "dy": 0.35},
                                    {"dx": 1.5, "dy": 0.35},
                                ],
                                "payload_slots": [
                                    {
                                        "slot_type": "amr",
                                        "amr_type": "AMR",
                                        "dx": 2,
                                        "dy": 0,
                                    }
                                ],
                                "space_type": "amr",
                                "stores_amr": True,
                                "amr_type": "AMR",
                                "has_charger": True,
                                "height_m": 0.5,
                            },
                        ],
                    },
                    {
                        "name": "Empty location",
                        "floor": 1,
                        "x": 5,
                        "y": 5,
                    },
                ],
            }
        )
        self.editor = _EditorStub(self.store)

    def tearDown(self):
        self.editor.close()
        self.editor.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_manager_summarises_all_locations_and_dropoff_spaces(self):
        dialog = LocationSpacesManagerDialog(self.editor)
        rows = {row["name"]: row for row in dialog._location_rows()}

        self.assertEqual({"Zone", "Empty location"}, set(rows))
        self.assertEqual("Drop-off zone", rows["Zone"]["role"])
        self.assertEqual(2, rows["Zone"]["total"])
        self.assertEqual(1, rows["Zone"]["payload"])
        self.assertEqual(1, rows["Zone"]["amr"])
        self.assertEqual(1, rows["Zone"]["chargers"])
        dialog.close()

    def test_height_can_be_changed_for_fixed_and_amr_spaces_in_bulk(self):
        dialog = InventorySpacesDialog(self.editor, "Zone")
        dialog.select_space(0)
        self.assertFalse(dialog.height_edit.isReadOnly())

        dialog._set_space_selection({0, 1}, current_index=0)
        dialog.height_edit.setText("2.4")
        dialog.apply_height_to_selected_spaces()
        dialog.finish()

        spaces = self.store.get_location_inventory_spaces("Zone")
        self.assertEqual([2.4, 2.4], [space["height_m"] for space in spaces])

    def manager_at_zone(self):
        dialog = LocationSpacesManagerDialog(self.editor)
        for row in range(dialog.table.rowCount()):
            if dialog.table.item(row, 0).text() == "Zone":
                dialog.table.setCurrentCell(row, 0)
        return dialog

    def test_detach_edit_navigate_and_save_preserve_geometry_and_amr(self):
        original = self.store.get_location_inventory_spaces("Zone")
        dialog = self.manager_at_zone()
        dialog.spaces_table.selectRow(0)
        dialog.detach_payloads()
        self.assertEqual([0], dialog.selected_space_indices())
        detached = dialog.current_spaces()[0]
        self.assertEqual([], detached['payload_slots'])
        self.assertTrue(detached['flexible'])
        self.assertEqual(original[0]['points'], detached['points'])
        dialog.spaces_table.item(0, 5).setText('37')
        dialog.spaces_table.item(0, 2).setText('1.8')
        dialog.spaces_table.item(0, 3).setText('0.9')
        geometry = space_geometry(dialog.current_spaces()[0])
        self.assertAlmostEqual(0, geometry[0], places=5)
        self.assertAlmostEqual(0, geometry[1], places=5)
        self.assertAlmostEqual(1.8, geometry[2], places=5)
        self.assertAlmostEqual(0.9, geometry[3], places=5)
        self.assertAlmostEqual(37, geometry[4], places=4)
        # Navigation does not write to the source store or lose draft edits.
        other = next(i for i in range(dialog.table.rowCount()) if dialog.table.item(i, 0).text() != 'Zone')
        dialog.table.setCurrentCell(other, 0)
        self.assertEqual(original, self.store.get_location_inventory_spaces('Zone'))
        dialog.accept()
        saved = self.store.get_location_inventory_spaces('Zone')
        self.assertTrue(saved[0]['flexible'])
        self.assertEqual([], saved[0]['payload_slots'])
        self.assertEqual(1.8, saved[0]['length_m'])
        self.assertEqual(original[1], saved[1])
        self.assertAlmostEqual(37, space_geometry(saved[0])[4], places=1)

    def test_cancel_discards_global_edits(self):
        original = deepcopy(self.store.data)
        dialog = self.manager_at_zone()
        dialog.scope_combo.setCurrentText('All locations')
        dialog.detach_payloads()
        dialog.length_spin.setValue(2)
        dialog.width_spin.setValue(1.5)
        dialog.apply_dimensions()
        dialog.reject()
        self.assertEqual(original, self.store.data)

    def test_bulk_scope_leaves_other_locations_and_chargers_unchanged(self):
        self.store.get_location('Empty location')['inventory_spaces'] = deepcopy(
            self.store.get_location_inventory_spaces('Zone'))
        dialog = self.manager_at_zone()
        dialog.scope_combo.setCurrentText('Current location')
        dialog.detach_payloads()
        dialog.length_spin.setValue(2)
        dialog.width_spin.setValue(1.5)
        dialog.apply_dimensions()
        other = dialog.store.get_location_inventory_spaces('Empty location')
        self.assertFalse(other[0]['flexible'])
        self.assertEqual([], dialog.current_spaces()[0]['payload_slots'])
        self.assertEqual(2, dialog.current_spaces()[0]['length_m'])
        self.assertTrue(dialog.current_spaces()[1]['has_charger'])
        dialog.scope_combo.setCurrentText('All locations')
        dialog.detach_payloads()
        dialog.apply_dimensions()
        other = dialog.store.get_location_inventory_spaces('Empty location')
        self.assertEqual(2, other[0]['length_m'])
        self.assertEqual(1.5, other[0]['width_m'])
        self.assertTrue(other[1]['has_charger'])
        dialog.reject()

    def test_similar_locations_match_count_orientation_and_selected_scope(self):
        spaces = self.store.get_location_inventory_spaces('Zone')
        self.store.get_location('Empty location')['inventory_spaces'] = deepcopy(spaces)
        dialog = self.manager_at_zone()
        dialog.select_similar_locations()
        self.assertEqual({'Zone', 'Empty location'}, set(dialog.selected_location_names()))
        self.assertEqual('Selected locations', dialog.scope_combo.currentText())
        dialog.detach_payloads()
        dialog.length_spin.setValue(2.5)
        dialog.apply_dimensions()
        for name in ('Zone', 'Empty location'):
            self.assertEqual(2.5, dialog.store.get_location_inventory_spaces(name)[0]['length_m'])
        dialog.reject()

    def test_similarity_wraparound_reordering_and_count_mismatch(self):
        bay = self.store.get_location_inventory_spaces('Zone')[0]
        def oriented(angle):
            result = deepcopy(bay)
            resize_space(result, 1, 0.6, angle)
            return result
        self.assertTrue(similar_layout([oriented(179), oriented(90)],
                                       [oriented(91), oriented(1)], 2.1))
        self.assertFalse(similar_layout([oriented(179)], [oriented(10)], 2))
        self.assertFalse(similar_layout([oriented(0)], [oriented(0), oriented(0)]))
        self.assertFalse(similar_layout([], []))

    def test_invalid_dimensions_rejected_and_payload_can_be_reattached(self):
        dialog = self.manager_at_zone()
        dialog.spaces_table.selectRow(0)
        dialog.detach_payloads()
        original = deepcopy(dialog.current_spaces()[0])
        for value in ('-1', 'nan', 'abc', 'inf'):
            dialog.spaces_table.item(0, 2).setText(value)
            self.assertEqual(original, dialog.current_spaces()[0])
        dialog.payload_combo.setCurrentText('Trolley')
        dialog.attach_payload()
        space = dialog.current_spaces()[0]
        self.assertFalse(space['flexible'])
        self.assertEqual('Trolley', space['payload_slots'][0]['payload'])
        self.assertAlmostEqual(1, space_geometry(space)[2], places=4)
        dialog.reject()

    def test_add_duplicate_delete_and_amr_charger_persist(self):
        self.store.data['amrs'][0]['id'] = 'AMR-TYPE-1'
        dialog = self.manager_at_zone()
        dialog.add_space()
        self.assertEqual(3, len(dialog.current_spaces()))
        self.assertEqual([2], dialog.selected_space_indices())
        dialog.duplicate_spaces()
        self.assertEqual(4, len(dialog.current_spaces()))
        dialog.spaces_table.selectRow(3)
        dialog.delete_spaces()
        self.assertEqual(3, len(dialog.current_spaces()))
        dialog.amr_combo.setCurrentText('AMR-TYPE-1')
        dialog.add_amr_space()
        dialog.spaces_table.item(3, 7).setCheckState(Qt.Checked)
        dialog.accept()
        spaces = self.store.get_location_inventory_spaces('Zone')
        self.assertTrue(spaces[2]['flexible'])
        self.assertEqual('AMR-TYPE-1', spaces[3]['amr_type'])
        self.assertTrue(spaces[3]['has_charger'])

    def test_detached_rotated_bay_accepts_other_payload_turned_ninety_degrees(self):
        from simulator import Simulation
        original = self.store.get_location('Zone')['inventory_spaces'][0]
        resize_space(original, 1.2, 0.6, 35)
        # Legacy footprints sometimes stored their larger axis-aligned envelope.
        original['length_m'] = original['width_m'] = 2.0
        dialog = self.manager_at_zone()
        dialog.spaces_table.selectRow(0)
        dialog.detach_payloads()
        dialog.accept()
        space = self.store.get_location_inventory_spaces('Zone')[0]
        self.assertEqual((1.2, 0.6), (space['length_m'], space['width_m']))
        simulation = Simulation.__new__(Simulation)
        rotated = SimpleNamespace(name='Other trolley', length_m=0.55, width_m=1.1, height_m=1)
        oversized = SimpleNamespace(name='Wide trolley', length_m=1.3, width_m=0.7, height_m=1)
        self.assertTrue(simulation._inventory_space_can_fit_payload(space, rotated))
        self.assertFalse(simulation._inventory_space_can_fit_payload(space, oversized))


if __name__ == "__main__":
    unittest.main()
