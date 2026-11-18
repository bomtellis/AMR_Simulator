"""Floor counts, shared routes, export alignment, and cancellation."""
from collections import Counter
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import ezdxf
from pypdf import PdfReader
from PySide6.QtGui import QColor, QImage
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas

from amr_floor_route_drawings import EMPTY_AMR, MIXED_PAYLOAD, build_floor_drawings, category_paths
from amr_route_analysis import CONFIRMED, PLANNED, Filters, Leg, RunAnalysis, Segment, _hash
from visualiser.dxf_scene import DXFScene
from visualiser.floor_route_export import export_floor_route_drawings


def movement(start, finish, payload='Linen', kind='corridor', **kwargs):
    return Segment('segment', 1, kind, 0, 1, 'AMR', 'journey', (), 'A', 'B', start, finish,
                   1, 'Lift' if kind.startswith('lift_') else '', payload, '', kwargs, {}, True)


def leg(identity, *segments, evidence=CONFIRMED, start=0):
    return Leg(identity, 'AMR', 'journey', (), 'A', 'B', 'Delivery', '', list(segments), start,
               start + 1, 1, 0, evidence, True)


class FloorRouteDrawingTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        source = self.root / 'saved-run' / 'steps.sqlite'
        source.parent.mkdir()
        self.run = RunAnalysis(str(source), 'fingerprint', config={'building': {'floor_count': 4}},
                               metadata={'run_id': 'fixture run'}, duration=100, complete=True)
        self.output = self.root / 'export'

    def test_each_leg_counts_once_per_floor_including_revisited_floor(self):
        self.run.legs = [
            leg('return', movement((0, 0, 0), (10, 0, 0)),
                movement((10, 0, 0), (10, 0, 2), kind='lift_transfer'),
                movement((10, 0, 2), (10, 0, 0), kind='lift_transfer'),
                movement((10, 0, 0), (15, 0, 0)),
                movement((10, 0, 1), (10, 0, 3), kind='lift_reposition')),
            leg('empty', movement((0, 1, 0), (10, 1, 0), '__empty__')),
            leg('mixed', movement((0, 1, 0), (10, 1, 0)),
                movement((10, 1, 0), (15, 1, 0), 'Waste')),
        ]
        floors, unassigned = build_floor_drawings(self.run, Filters())
        self.assertEqual([3, 0, 1, 0], [drawing.total for drawing in floors])
        self.assertEqual(Counter({('payload', 'Linen'): 1, EMPTY_AMR: 1, MIXED_PAYLOAD: 1}), floors[0].confirmed)
        self.assertEqual({(10, 0)}, floors[2].landings)
        self.assertEqual(0, unassigned)
        selected, _ = build_floor_drawings(self.run, Filters(floor=2))
        self.assertEqual([(2, 1)], [(drawing.floor, drawing.total) for drawing in selected])

    def test_shared_partial_overlap_reversed_route_and_branch(self):
        self.run.legs = [
            leg('linen', movement((0, 0, 0), (12, 0, 0))),
            leg('linen-repeat', movement((12, 0, 0), (0, 0, 0))),
            leg('waste', movement((12, 0, 0), (4, 0, 0), 'Waste'),
                movement((4, 0, 0), (4, 3, 0), 'Waste')),
            leg('parallel', movement((4, 0.2, 0), (12, 0.2, 0), 'Supplies')),
        ]
        (floor,), _ = build_floor_drawings(self.run, Filters(floor=0))
        bundled, = [(points, styles) for points, styles in floor.chains if len(styles) == 2]
        self.assertEqual([(4, 0), (12, 0)], bundled[0])
        paths = list(category_paths(floor, 0.3))
        shared = [points for _, _, points in paths if points[0] == (4, 0) and points[-1] == (12, 0)]
        self.assertEqual(2, len(shared))
        self.assertAlmostEqual(0.3, abs(shared[0][1][1] - shared[1][1][1]))
        self.assertEqual(4, floor.total)

    def test_filter_window_and_plan_styles(self):
        segment = movement((0, 0, 0), (12, 0, 0))
        self.run.complete = False
        self.run.legs = [
            leg('first', segment, start=1),
            leg('planned-overlap', segment, evidence=PLANNED, start=2),
            leg('planned-only', replace(segment, payload='Waste'), evidence=PLANNED, start=3),
            leg('other-window', segment, start=10),
        ]
        filters = Filters(start=1, end=10, floor=0, evidence=PLANNED)
        (floor,), _ = build_floor_drawings(self.run, filters)
        self.assertEqual(1, floor.total)
        (floor,), _ = build_floor_drawings(self.run, filters, include_plans=True)
        self.assertEqual((1, 2), (floor.confirmed.total(), floor.planned.total()))
        self.assertEqual({(('payload', 'Linen'), True), (('payload', 'Waste'), False)},
                         {(category, confirmed) for category, confirmed, _ in category_paths(floor, 0.3)})

    def test_missing_locations_do_not_create_replacement_paths(self):
        malformed = replace(movement((0, 0, 0), (10, 0, 0)), trajectory={'motions': [{'kind': 'broken'}]})
        missing_floor = movement((10, 0, 0), (11, 1, None))
        self.run.legs = [leg('partial', malformed, missing_floor)]
        floors, unassigned = build_floor_drawings(self.run, Filters())
        self.assertEqual((1, 1, 1), (floors[0].total, floors[0].gaps, unassigned))
        self.assertFalse(floors[0].chains)
        self.assertEqual({(0, 0), (10, 0)}, floors[0].gap_points)

    def test_both_formats_keep_counts_and_cad_uses_original_millimetres(self):
        base = self.root / 'saved-run' / 'plan.dxf'
        doc = ezdxf.new('R2010')
        doc.units = 4
        doc.modelspace().add_line((0, 0), (20_000, 0))
        doc.saveas(base)
        self.run.drawings[0] = dict(DXFScene.load_content(str(base)), sha256=_hash(base))
        self.run.legs = [leg('linen', movement((2, 1, 0), (10, 1, 0)))]
        export_floor_route_drawings(self.run, Filters(), self.output)
        pdf = PdfReader(self.output / 'amr-floor-routes.pdf')
        self.assertEqual(4, len(pdf.pages))
        self.assertIn('Linen', pdf.pages[0].extract_text())
        self.assertIn('No trips meet', pdf.pages[1].extract_text())
        self.assertAlmostEqual(841 * mm, float(pdf.pages[0].mediabox.width), places=2)
        self.assertAlmostEqual(594 * mm, float(pdf.pages[0].mediabox.height), places=2)
        cad = ezdxf.readfile(self.output / 'floor-0-amr-routes.dxf')
        self.assertEqual(4, cad.units)
        self.assertEqual((20_000, 0, 0), tuple(cad.modelspace().query('LINE[layer=="0"]')[0].dxf.end))
        route, = cad.modelspace().query('LWPOLYLINE[layer=="AMR Route - Linen"]')
        self.assertEqual([(2000, 1000), (10000, 1000)], [tuple(point) for point in route.get_points('xy')])
        self.assertFalse(cad.audit().errors)
        self.assertEqual(1, len(ezdxf.readfile(base).modelspace()))

    def test_pdf_uses_one_exact_scale_and_tighter_lanes_across_floors(self):
        self.run.drawings.update({
            0: dict(bounds=(0, 0, 300, 250), entities=[]),
            1: dict(bounds=(0, 0, 120, 125), entities=[]),
        })
        self.run.legs = [
            leg('floor-0-linen', movement((0, 0, 0), (100, 0, 0))),
            leg('floor-0-waste', movement((0, 0, 0), (100, 0, 0), 'Waste')),
            leg('floor-1-linen', movement((0, 0, 1), (100, 0, 1))),
        ]
        export_floor_route_drawings(self.run, Filters(), self.output, dxf=False)
        pdf = PdfReader(self.output / 'amr-floor-routes.pdf')
        for page in pdf.pages:
            self.assertIn('1:500 at A1 | Print at 100%', page.extract_text())
            operations = page.get_contents().operations
            transforms = [operands for operands, operator in operations
                          if operator == b'cm' and abs(float(operands[0]) - 2 * mm) < 0.00001]
            self.assertEqual(1, len(transforms))
            self.assertAlmostEqual(2 * mm, float(transforms[0][3]), places=5)
            bar_lengths = [float(end[0] - start[0])
                           for (start, move), (end, line) in zip(operations, operations[1:])
                           if move == b'm' and line == b'l' and start[1] == end[1] == 45]
            self.assertEqual(1, len(bar_lengths))
            self.assertAlmostEqual(40 * mm, bar_lengths[0], places=2)
        operations = pdf.pages[0].get_contents().operations
        lane_edges = [float(operands[1]) for operands, operator in operations
                      if operator == b'l' and len(operands) == 2 and 0 < abs(float(operands[1])) < 1]
        # At 1:500, a 0.60 mm paper pitch is 0.30 m in the recorded world coordinates.
        self.assertEqual({-0.15, 0.15}, {round(edge, 3) for edge in lane_edges})

    def test_rotated_pdf_underlay_is_linked_and_packaged_with_cad(self):
        base = self.root / 'saved-run' / 'plan.pdf'
        page = Canvas(str(base), pagesize=(360, 180))
        page.rect(0, 0, 360, 180)
        page.showPage()
        page.save()
        image = QImage(360, 180, QImage.Format.Format_RGB32)
        image.fill(QColor('white'))
        self.run.pdf_drawings[0] = (image, dict(filepath=str(base), page=1, floor=0, x_m=10, y_m=20,
            rotation_deg=35, paper_width_mm=127, paper_height_mm=63.5, scale_denominator=100,
            opacity=0.6, page_width_pt=360, page_height_pt=180, sha256=_hash(base)))
        export_floor_route_drawings(self.run, Filters(floor=0), self.output)
        cad = ezdxf.readfile(self.output / 'floor-0-amr-routes.dxf')
        underlay, = cad.modelspace().query('PDFUNDERLAY')
        definition = cad.entitydb[underlay.dxf.underlay_def_handle]
        self.assertEqual((10, 20, 0), tuple(underlay.dxf.insert))
        self.assertEqual(35, underlay.dxf.rotation)
        self.assertAlmostEqual(100, underlay.dxf.scale_x)
        self.assertEqual(base.read_bytes(), (self.output / definition.dxf.filename).read_bytes())
        self.assertIn('Floor 0', PdfReader(self.output / 'amr-floor-routes.pdf').pages[0].extract_text())

    def test_cancel_mid_export_and_preserve_existing_destination(self):
        cancelled = False

        def progress(message):
            nonlocal cancelled
            if 'floor 1' in message:
                cancelled = True

        with self.assertRaises(InterruptedError):
            export_floor_route_drawings(self.run, Filters(), self.output, cancel=lambda: cancelled, progress=progress)
        self.assertFalse(self.output.exists())
        self.assertEqual(['saved-run'], [item.name for item in self.root.iterdir()])
        self.output.mkdir()
        with self.assertRaises(FileExistsError):
            export_floor_route_drawings(self.run, Filters(), self.output)
        with self.assertRaises(ValueError):
            export_floor_route_drawings(self.run, Filters(), Path(self.run.source).parent / 'inside')
