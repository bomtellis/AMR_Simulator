"""Regression checks for the coordinate frame shared by drawings and heatmaps."""
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import ezdxf
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'report'))
import amr_report_pdf_report as report


class HeatmapAlignmentTests(unittest.TestCase):
    def test_visible_geometry_keeps_world_position_with_hidden_extents(self):
        for units, factor, width, height in ((6, 1, 10, 5), (4, 1000, 10, 5),
                                             (6, 1, .325, .173)):
            with self.subTest(units=units, width=width), tempfile.TemporaryDirectory() as folder:
                source = Path(folder) / 'floor.dxf'
                svg = source.with_suffix('.svg')
                doc = ezdxf.new()
                doc.units = units
                model = doc.modelspace()
                corners = [(100, 200), (100 + width, 200),
                           (100 + width, 200 + height), (100, 200 + height)]
                model.add_lwpolyline([(x * factor, y * factor) for x, y in corners], close=True)
                doc.layers.new('HIDDEN').off()
                model.add_line((150 * factor, 220 * factor), (160 * factor, 230 * factor),
                               dxfattribs={'layer': 'HIDDEN'})
                doc.saveas(source)
                extents = report.render_dxf_to_svg(str(source), str(svg))
                self.assertEqual(extents, report.get_dxf_extents(str(source)))
                self.assert_svg_points(svg, extents, corners)

    def test_fractional_and_small_drawing_bounds_do_not_add_scale_or_origin_error(self):
        for width, height in ((10.325, 5.173), (.325, .173)):
            with self.subTest(width=width), tempfile.TemporaryDirectory() as folder:
                source = Path(folder) / 'floor.dxf'
                svg = source.with_suffix('.svg')
                doc = ezdxf.new()
                doc.units = 6
                corners = [(-7.25, 3.125), (-7.25 + width, 3.125),
                           (-7.25 + width, 3.125 + height), (-7.25, 3.125 + height)]
                doc.modelspace().add_lwpolyline(corners, close=True)
                doc.saveas(source)
                extents = report.render_dxf_to_svg(str(source), str(svg))
                self.assert_svg_points(svg, extents, corners)

    def assert_svg_points(self, svg, extents, expected):
        root = ET.parse(svg).getroot()
        left, top, width, height = map(float, root.attrib['viewBox'].split())
        xmin, xmax, ymin, ymax = extents
        paths = root.findall('.//{http://www.w3.org/2000/svg}path')
        self.assertTrue(paths)
        vertices = []
        for path in paths:
            x, y = 0.0, 0.0
            for command, values in re.findall(r'([MLml])([^MLmlZz]+)', path.attrib['d']):
                numbers = list(map(float, re.findall(r'[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?', values)))
                for px, py in zip(numbers[::2], numbers[1::2]):
                    x, y = (x + px, y + py) if command.islower() else (px, py)
                    vertices.append((x, y))
        world_points = [(xmin + (x - left) / width * (xmax - xmin),
                         ymax - (y - top) / height * (ymax - ymin)) for x, y in vertices]
        for x, y in expected:
            self.assertTrue(any(abs(px - x) < .0001 and abs(py - y) < .0001
                                for px, py in world_points), (x, y, world_points))
        svg_width = float(root.attrib['width'].removesuffix('mm'))
        svg_height = float(root.attrib['height'].removesuffix('mm'))
        self.assertAlmostEqual(svg_width / svg_height, (xmax - xmin) / (ymax - ymin))

    def test_cache_reuses_copies_but_distinguishes_changed_contents(self):
        with tempfile.TemporaryDirectory() as folder:
            a = Path(folder) / 'a' / 'floor.dxf'
            b = Path(folder) / 'b' / 'floor.dxf'
            for source in (a, b):
                source.parent.mkdir()
                source.write_text('one')
                os.utime(source, ns=(1700000000000000000, 1700000000000000000))
            first = report.get_cached_dxf_svg_path(str(a))
            self.assertEqual(first, report.get_cached_dxf_svg_path(str(b)))
            b.write_text('two')
            os.utime(b, ns=(1700000000000000000, 1700000000000000000))
            self.assertNotEqual(first, report.get_cached_dxf_svg_path(str(b)))
            a.write_text('new')
            os.utime(a, ns=(1700000000000000000, 1700000000000000000))
            self.assertNotEqual(first, report.get_cached_dxf_svg_path(str(a)))

    def test_warm_cache_and_cold_cache_use_identical_bounds(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'floor.dxf'
            svg = source.with_suffix('.svg')
            doc = ezdxf.new()
            doc.units = 6
            doc.modelspace().add_lwpolyline([(10, 20), (30, 20), (30, 40)], close=True)
            doc.saveas(source)
            frame = pd.DataFrame([dict(x1=10, y1=20, x2=30, y2=20, congestion_score=1)])
            with patch.object(report, 'get_cached_dxf_svg_path', return_value=svg):
                _, cold = report.prepare_heatmap_floor(0, frame, {0: str(source)})
                with patch.object(report, 'render_dxf_to_svg', side_effect=AssertionError('cache missed')):
                    _, warm = report.prepare_heatmap_floor(0, frame, {0: str(source)})
            self.assertEqual(cold['extents'], warm['extents'])
            self.assertEqual(cold['dxf_drawing'].width, warm['dxf_drawing'].width)
            self.assertIsNotNone(warm['dxf_drawing'])


if __name__ == '__main__':
    unittest.main()
