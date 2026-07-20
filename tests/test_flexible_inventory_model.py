import unittest

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


if __name__ == "__main__":
    unittest.main()
