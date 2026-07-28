import math
import unittest

from visualiser.models import JsonStore
from visualiser.pdf_underlay import (
    normalise_pdf_underlay,
    underlay_world_bounds,
    underlay_world_size,
)


class PdfUnderlayGeometryTests(unittest.TestCase):
    def test_a1_at_one_to_one_hundred_uses_dxf_metres(self):
        mapping = {
            "paper_width_mm": 841,
            "paper_height_mm": 594,
            "scale_denominator": 100,
        }
        width, height = underlay_world_size(mapping)
        self.assertAlmostEqual(84.1, width)
        self.assertAlmostEqual(59.4, height)

    def test_rotated_bounds_are_anchored_at_lower_left(self):
        mapping = {
            "paper_width_mm": 1000,
            "paper_height_mm": 500,
            "scale_denominator": 10,
            "x_m": 2,
            "y_m": 3,
            "rotation_deg": 90,
        }
        bounds = underlay_world_bounds(mapping)
        for actual, expected in zip(bounds, (-3.0, 3.0, 2.0, 13.0)):
            self.assertTrue(math.isclose(actual, expected, abs_tol=1e-9))

    def test_normalisation_clamps_page_scale_and_opacity(self):
        mapping = normalise_pdf_underlay(
            {
                "page": 0,
                "paper_width_mm": -2,
                "paper_height_mm": 0,
                "scale_denominator": -100,
                "opacity": 4,
            }
        )
        self.assertEqual(1, mapping["page"])
        self.assertEqual(1.0, mapping["paper_width_mm"])
        self.assertEqual(1.0, mapping["paper_height_mm"])
        self.assertEqual(0.001, mapping["scale_denominator"])
        self.assertEqual(1.0, mapping["opacity"])


class PdfUnderlayStoreTests(unittest.TestCase):
    def test_mapping_is_floor_scoped_and_replaceable(self):
        store = JsonStore()
        store.set_floor_pdf_underlay(
            2,
            {
                "filepath": "plan.pdf",
                "page": 1,
                "paper_width_mm": 841,
                "paper_height_mm": 594,
                "scale_denominator": 100,
            },
        )
        store.set_floor_pdf_underlay(
            2,
            {
                "filepath": "revision.pdf",
                "page": 2,
                "paper_width_mm": 420,
                "paper_height_mm": 297,
                "scale_denominator": 50,
            },
        )
        self.assertEqual(1, len(store.data["floor_pdf_underlays"]))
        self.assertEqual("revision.pdf", store.floor_pdf_underlay(2)["filepath"])
        self.assertFalse(
            any("PDF underlay" in error for error in store.validate())
        )
        store.clear_floor_pdf_underlay(2)
        self.assertIsNone(store.floor_pdf_underlay(2))

    def test_invalid_mapping_is_reported(self):
        store = JsonStore()
        store.data["floor_pdf_underlays"] = [
            {
                "floor": 0,
                "filepath": "",
                "page": 0,
                "paper_width_mm": 0,
                "paper_height_mm": 297,
                "scale_denominator": 0,
            }
        ]
        errors = store.validate()
        self.assertTrue(any("empty filepath" in error for error in errors))
        self.assertTrue(any("invalid page" in error for error in errors))
        self.assertTrue(any("invalid paper width" in error for error in errors))
        self.assertTrue(any("invalid drawing scale" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
