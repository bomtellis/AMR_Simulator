import unittest

from visualiser.staff_route_geometry import (
    interpolate_staff_route,
    person_position_behind_payload,
    shortest_staff_route_points,
)


class StaffRouteGeometryTests(unittest.TestCase):
    def test_route_follows_corridor_corner(self):
        points = {
            "Zone": {"name": "Zone", "floor": 0, "x": 0, "y": 0},
            "Corner": {"name": "Corner", "floor": 0, "x": 10, "y": 0},
            "Ward": {"name": "Ward", "floor": 0, "x": 10, "y": 10},
        }
        layout = {
            "corridors": {
                "auto_connect": False,
                "nodes": [{"name": "Corner", "floor": 0, "x": 10, "y": 0}],
                "edges": [
                    {"from": "Zone", "to": "Corner", "bidirectional": True},
                    {"from": "Corner", "to": "Ward", "bidirectional": True},
                ],
            }
        }

        route = shortest_staff_route_points(layout, points, "Zone", "Ward")

        self.assertEqual(["Zone", "Corner", "Ward"], [p["name"] for p in route])
        first_leg = interpolate_staff_route(route, 0.25)
        second_leg = interpolate_staff_route(route, 0.75)
        self.assertEqual((5.0, 0.0), (first_leg["x"], first_leg["y"]))
        self.assertEqual((1.0, 0.0), (first_leg["heading_dx"], first_leg["heading_dy"]))
        self.assertEqual((10.0, 5.0), (second_leg["x"], second_leg["y"]))
        self.assertEqual((0.0, 1.0), (second_leg["heading_dx"], second_leg["heading_dy"]))

    def test_person_is_positioned_behind_payload(self):
        x, y = person_position_behind_payload(10.0, 5.0, 1.0, 0.0, 1.2)
        self.assertAlmostEqual(9.1, x)
        self.assertAlmostEqual(5.0, y)


if __name__ == "__main__":
    unittest.main()
