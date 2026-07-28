import os
import sys
import unittest
from pathlib import Path


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "visualiser"))

from PySide6.QtWidgets import QApplication

from dialogs import (
    DepartmentDropoffZoneCreationDialog,
    collect_department_dropoff_zone_names,
)


class DepartmentDropoffZoneDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_existing_zone_can_be_assigned_to_multiple_categories(self):
        dialog = DepartmentDropoffZoneCreationDialog(
            None,
            [
                ("supplies", "Supplies", "-SUPPLIES"),
                ("waste", "Waste", "-WASTE"),
            ],
            suggested_name="D1-DROP-ZONE",
            existing_location_names=["Zone A"],
            existing_dropoff_zone_names=["Zone A"],
        )
        dialog.zone_choice_combo.setCurrentIndex(
            dialog.zone_choice_combo.findData("Zone A")
        )
        dialog._set_all_categories_checked(True)

        dialog.accept()

        self.assertEqual(
            {
                "name": "Zone A",
                "category_keys": ["supplies", "waste"],
                "create_new": False,
            },
            dialog.result,
        )

    def test_existing_zone_names_are_collected_from_all_departments(self):
        departments = [
                {
                    "task_generation_locations": {
                        "supplies": {"dropoff_zone_locations": ["Zone B", "Zone A"]}
                    }
                },
                {
                    "task_generation_locations": {
                        "waste": {"drop_off_zone_locations": "Zone A"},
                        "meals": {"dropoff_zone_locations": ["Zone C"]},
                    }
                },
            ]

        self.assertEqual(
            ["Zone A", "Zone B", "Zone C"],
            collect_department_dropoff_zone_names(departments),
        )


if __name__ == "__main__":
    unittest.main()
