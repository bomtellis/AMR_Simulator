import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "visualiser"))

from PySide6.QtWidgets import QApplication, QWidget

from dialogs import InventorySpacesDialog, LocationSpacesManagerDialog
from models import JsonStore


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


if __name__ == "__main__":
    unittest.main()
