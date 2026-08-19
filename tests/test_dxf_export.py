import tempfile
import unittest
from pathlib import Path

import ezdxf

from visualiser.dxf_export import export_all_floors_to_dxf, export_floor_to_dxf


class DxfExportTests(unittest.TestCase):
    def test_exports_editor_geometry_in_world_coordinates_without_background(self):
        data = {
            "floor_dxf_files": [{"floor": 2, "filepath": "background.dxf"}],
            "floor_pdf_underlays": [{"floor": 2, "filepath": "background.pdf"}],
            "corridors": {
                "nodes": [
                    {"name": "N1", "floor": 2, "x": 101.25, "y": -20.5},
                    {"name": "N2", "floor": 2, "x": 105.75, "y": -18.0, "has_door": True},
                    {"name": "OTHER", "floor": 3, "x": 1, "y": 2},
                ],
                "edges": [
                    {"from": "N1", "to": "N2"},
                    {"from": "N2", "to": "N1"},
                    {"from": "N2", "to": "OTHER"},
                ],
            },
            "locations": [
                {
                    "name": "Stores",
                    "floor": 2,
                    "x": 110.0,
                    "y": -12.0,
                    "bounding_box": [
                        {"dx": -1, "dy": -2},
                        {"dx": 1, "dy": -2},
                        {"dx": 1, "dy": 2},
                        {"dx": -1, "dy": 2},
                    ],
                    "inventory_spaces": [
                        {
                            "name": "Bay 1",
                            "points": [
                                {"dx": -0.5, "dy": -0.5},
                                {"dx": 0.5, "dy": -0.5},
                                {"dx": 0.5, "dy": 0.5},
                                {"dx": -0.5, "dy": 0.5},
                            ],
                            "payload_slots": [
                                {"payload": "Trolley", "dx": 0.25, "dy": 0.1}
                            ],
                        }
                    ],
                }
            ],
            "departments": [{"name": "Ward", "floor": 2, "x": 120, "y": 8}],
            "lifts": [{"id": "L1", "floor_locations": {"2": {"x": 99, "y": -5}}}],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "export.dxf"
            counts = export_floor_to_dxf(data, 2, output)
            document = ezdxf.readfile(output)

        self.assertEqual(6, document.header["$INSUNITS"])
        self.assertEqual(1, counts["edges"])
        self.assertEqual(2, counts["corridor_nodes"])
        self.assertEqual(1, counts["locations"])
        self.assertEqual(1, counts["location_bounds"])
        self.assertEqual(1, counts["inventory_spaces"])
        self.assertEqual(1, counts["inventory_slots"])
        self.assertEqual(1, counts["departments"])
        self.assertEqual(1, counts["lifts"])

        modelspace = document.modelspace()
        corridor_lines = list(modelspace.query('LINE[layer=="AMR_CORRIDORS"]'))
        self.assertEqual(1, len(corridor_lines))
        self.assertEqual((101.25, -20.5), tuple(corridor_lines[0].dxf.start)[:2])
        self.assertEqual((105.75, -18.0), tuple(corridor_lines[0].dxf.end)[:2])

        location = list(modelspace.query('CIRCLE[layer=="AMR_LOCATIONS"]'))
        self.assertEqual(1, len(location))
        self.assertEqual((110.0, -12.0), tuple(location[0].dxf.center)[:2])
        self.assertFalse(any("background" in str(entity.dxfattribs()).lower() for entity in modelspace))

    def test_only_exports_requested_floor(self):
        data = {
            "corridors": {"nodes": [], "edges": []},
            "locations": [
                {"name": "F0", "floor": 0, "x": 1, "y": 2},
                {"name": "F1", "floor": 1, "x": 3, "y": 4},
            ],
            "departments": [],
            "lifts": [],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "floor-1.dxf"
            counts = export_floor_to_dxf(data, 1, output)
            document = ezdxf.readfile(output)

        circles = list(document.modelspace().query('CIRCLE[layer=="AMR_LOCATIONS"]'))
        self.assertEqual(1, counts["locations"])
        self.assertEqual(1, len(circles))
        self.assertEqual((3.0, 4.0), tuple(circles[0].dxf.center)[:2])

    def test_selected_units_scale_coordinates_and_header(self):
        data = {
            "corridors": {"nodes": [], "edges": []},
            "locations": [
                {"name": "Point", "floor": 0, "x": 1.25, "y": -2.5}
            ],
            "departments": [],
            "lifts": [],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "millimetres.dxf"
            export_floor_to_dxf(data, 0, output, units="Millimetres")
            document = ezdxf.readfile(output)

        circle = list(
            document.modelspace().query('CIRCLE[layer=="AMR_LOCATIONS"]')
        )[0]
        self.assertEqual(4, document.header["$INSUNITS"])
        self.assertEqual((1250.0, -2500.0), tuple(circle.dxf.center)[:2])
        self.assertEqual(300.0, circle.dxf.radius)

    def test_all_floor_export_uses_sequential_numbered_files(self):
        data = {
            "corridors": {"nodes": [], "edges": []},
            "locations": [
                {"name": "Basement", "floor": -1, "x": 1, "y": 2},
                {"name": "Second", "floor": 2, "x": 3, "y": 4},
            ],
            "departments": [],
            "lifts": [],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            results = export_all_floors_to_dxf(
                data,
                Path(temp_dir) / "layout.dxf",
                units="Feet",
            )
            names = [result["path"].name for result in results]
            existing = [result["path"].exists() for result in results]

        self.assertEqual(["layout_001_F-1.dxf", "layout_002_F2.dxf"], names)
        self.assertEqual([True, True], existing)
        self.assertEqual([-1, 2], [result["floor"] for result in results])


if __name__ == "__main__":
    unittest.main()
