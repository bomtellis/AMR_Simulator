import json
import unittest
from pathlib import Path

from visualiser.models import JsonStore


class FlexibleInventoryModelTests(unittest.TestCase):
    def test_dropoff_space_defaults_to_flexible_and_dimensions_persist(self):
        store = JsonStore(
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
                "locations": [
                    {
                        "name": "Zone",
                        "floor": 0,
                        "x": 0,
                        "y": 0,
                        "inventory_spaces": [
                            {
                                "name": "Existing",
                                "points": [
                                    {"dx": 0, "dy": 0},
                                    {"dx": 1, "dy": 0},
                                    {"dx": 1, "dy": 1},
                                    {"dx": 0, "dy": 1},
                                ],
                            }
                        ],
                    }
                ],
            }
        )
        self.assertTrue(
            store.get_location_inventory_spaces("Zone")[0]["flexible"]
        )

        store.set_location_inventory_spaces(
            "Zone",
            [
                {
                    "name": "Maximum envelope",
                    "points": [
                        {"dx": 0, "dy": 0},
                        {"dx": 1.4, "dy": 0},
                        {"dx": 1.4, "dy": 0.9},
                        {"dx": 0, "dy": 0.9},
                    ],
                    "length_m": 1.4,
                    "width_m": 0.9,
                    "height_m": 1.8,
                    "flexible": True,
                    "payload_slots": [{"payload": "Template"}],
                }
            ],
        )
        saved = store.get_location_inventory_spaces("Zone")[0]
        self.assertTrue(saved["flexible"])
        self.assertEqual(1.4, saved["length_m"])
        self.assertEqual(0.9, saved["width_m"])
        self.assertEqual(1.8, saved["height_m"])

    def test_ltn_shared_drop_zone_spaces_fit_the_linen_trolley(self):
        project_root = Path(__file__).resolve().parents[1]
        with (project_root / "ltn.json").open(encoding="utf-8") as stream:
            config = json.load(stream)

        zone = next(
            location
            for location in config["locations"]
            if location["name"] == "D39-DROP-ZONE"
        )
        linen = next(
            payload
            for payload in config["payloads"]
            if payload["name"] == "Linen Trolley"
        )

        compatible_spaces = []
        for space in zone["inventory_spaces"]:
            normal_fit = (
                linen["length_m"] <= space["length_m"]
                and linen["width_m"] <= space["width_m"]
            )
            rotated_fit = (
                linen["length_m"] <= space["width_m"]
                and linen["width_m"] <= space["length_m"]
            )
            if (
                space.get("flexible", False)
                and (normal_fit or rotated_fit)
                and linen["height_m"] <= space["height_m"]
            ):
                compatible_spaces.append(space["name"])

        self.assertEqual(3, len(compatible_spaces))


if __name__ == "__main__":
    unittest.main()
