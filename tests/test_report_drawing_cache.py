"""Vector output, cache invalidation, and repeated report-pass regressions."""
from concurrent.futures import ThreadPoolExecutor
import copy
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import ezdxf
import pandas as pd
from pypdf import PdfReader
from reportlab.graphics import renderPDF
from reportlab.graphics.shapes import Drawing, Group, Rect
from reportlab.lib.colors import Color
from reportlab.pdfgen.canvas import Canvas
from svglib.svglib import NoStrokePath

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'report'))
import amr_report_pdf_report as report
import amr_report_drawing_cache as cache


class DrawingCacheTests(unittest.TestCase):
    def fixture(self, folder):
        source = Path(folder) / 'floor.dxf'
        svg = source.with_suffix('.svg')
        doc = ezdxf.new()
        doc.units = 6
        doc.modelspace().add_lwpolyline([(10, 20), (30, 20), (30, 40)], close=True)
        doc.saveas(source)
        frame = pd.DataFrame([dict(x1=10, y1=20, x2=30, y2=20, congestion_score=1)])
        return source, svg, frame

    def test_warm_preparation_skips_dxf_bounds_and_svg_parsing(self):
        with tempfile.TemporaryDirectory() as folder:
            source, svg, frame = self.fixture(folder)
            with patch.object(report, 'get_cached_dxf_svg_path', return_value=svg):
                _, cold = report.prepare_heatmap_floor(0, frame, {0: str(source)})
                with patch.object(report, 'get_dxf_extents', side_effect=AssertionError('bounds repeated')), \
                     patch.object(report, 'render_dxf_to_svg', side_effect=AssertionError('render repeated')), \
                     patch.object(report, 'svg2rlg', side_effect=AssertionError('SVG parsing repeated')):
                    _, warm = report.prepare_heatmap_floor(0, frame, {0: str(source)})
                self.assertIsNotNone(warm['dxf_drawing'])
                self.assertEqual(cold['extents'], warm['extents'])
                self.assertEqual(self.pdf_commands(cold['dxf_drawing']), self.pdf_commands(warm['dxf_drawing']))

    @staticmethod
    def pdf_commands(drawing):
        reader = PdfReader(io.BytesIO(renderPDF.drawToString(drawing)))
        return reader.pages[0].get_contents().get_data()

    def test_scene_roundtrip_preserves_transforms_colours_and_unclosed_fills(self):
        drawing = Drawing(100, 100)
        group = Group()
        group.translate(12, 17)
        group.rotate(30)
        group.add(Rect(5, 6, 20, 30, fillColor=Color(.2, .5, .7, .4), strokeWidth=2))
        path = NoStrokePath(fillColor=Color(.8, .2, .1))
        path.moveTo(3, 4)
        path.lineTo(25, 40)
        path.lineTo(40, 10)
        group.add(path)
        drawing.add(group)
        with tempfile.TemporaryDirectory() as folder:
            svg = Path(folder) / 'source.svg'
            svg.write_text('source identity')
            cache.save_scene(svg, drawing)
            restored = cache.load_scene(svg)
            self.assertIsNotNone(restored)
            self.assertEqual(self.pdf_commands(drawing), self.pdf_commands(restored))
            report.thin_drawing_strokes(drawing, .5)
            report.thin_drawing_strokes(restored, .5)
            self.assertEqual(self.pdf_commands(drawing), self.pdf_commands(restored))

    def test_changed_svg_invalidates_both_caches(self):
        with tempfile.TemporaryDirectory() as folder:
            svg = Path(folder) / 'floor.svg'
            svg.write_text('old')
            cache.save_bounds(svg, (0, 1, 0, 1))
            cache.save_scene(svg, Drawing(1, 1))
            svg.write_text('changed')
            self.assertIsNone(cache.load_bounds(svg))
            self.assertIsNone(cache.load_scene(svg))

    def test_corrupt_caches_are_rebuilt(self):
        with tempfile.TemporaryDirectory() as folder:
            source, svg, frame = self.fixture(folder)
            with patch.object(report, 'get_cached_dxf_svg_path', return_value=svg):
                report.prepare_heatmap_floor(0, frame, {0: str(source)})
                svg.with_suffix('.bounds.json').write_text('{broken')
                svg.with_suffix('.scene.json.gz').write_bytes(b'broken')
                _, prepared = report.prepare_heatmap_floor(0, frame, {0: str(source)})
                self.assertIsNotNone(prepared['dxf_drawing'])
                self.assertIsNotNone(cache.load_scene(svg))
                self.assertEqual(cache.load_bounds(svg), prepared['extents'])

    def test_unwritable_cache_does_not_prevent_drawing_load(self):
        with tempfile.TemporaryDirectory() as folder:
            source, svg, frame = self.fixture(folder)
            report.render_dxf_to_svg(str(source), str(svg))
            with patch.object(report, 'get_cached_dxf_svg_path', return_value=svg), \
                 patch.object(cache, '_atomic_write', side_effect=PermissionError('read only')):
                _, prepared = report.prepare_heatmap_floor(0, frame, {0: str(source)})
                self.assertIsNotNone(prepared['dxf_drawing'])

    def test_parallel_floors_prepare_one_shared_drawing(self):
        shared = cache.DrawingPreparationCache()
        value = object()
        prepare = Mock(return_value=value)
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(lambda _: shared.get('same drawing', prepare), range(8)))
        prepare.assert_called_once()
        self.assertTrue(all(item is value for item in results))

    def test_layout_passes_reuse_scaled_copy_without_changing_source(self):
        drawing = Drawing(100, 100)
        drawing.add(Rect(0, 0, 100, 100, strokeWidth=2))
        original = self.pdf_commands(drawing)
        frame = pd.DataFrame([dict(x1=10, y1=20, x2=30, y2=20, congestion_score=1)])
        flow = report.FloorOverlayFlowable(frame, '0', drawing, (0, 100, 0, 100), 400, 400)
        with patch.object(report.copy, 'deepcopy', wraps=copy.deepcopy) as copied:
            for _ in range(2):
                canvas = Canvas(io.BytesIO())
                flow.drawOn(canvas, 0, 0)
                canvas.save()
            copied.assert_called_once()
            flow.width = flow.height = 800
            flow.drawOn(Canvas(io.BytesIO()), 0, 0)
            self.assertEqual(2, copied.call_count)
        self.assertEqual(original, self.pdf_commands(drawing))


if __name__ == '__main__':
    unittest.main()
