"""Paper-width allocation, wrapping and continuation pages for report tables."""
from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd
from pypdf import PdfReader
from reportlab.lib.pagesizes import A3, A4, landscape
from reportlab.lib.units import mm
from reportlab.platypus import NextPageTemplate, PageBreak

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'report'))
from amr_report_pdf_report import (NumberedDocTemplate, PageWidthTable, make_styles,
                                   payload_timetable_table, table_from_df)


class ReportTableWidthTests(unittest.TestCase):
    def setUp(self):
        self.styles = make_styles()

    def test_all_paper_templates_use_available_width_and_keep_column_proportions(self):
        table = table_from_df(pd.DataFrame({'Metric': ['Tasks'], 'Result': [42]}),
                              [70 * mm, 100 * mm], self.styles)
        for paper in (A4, landscape(A4), A3, landscape(A3), A4):
            available = paper[0] - 30 * mm - 12
            width, _height = table.wrap(available, 600)
            self.assertAlmostEqual(available, width)
            self.assertAlmostEqual(available, sum(table._colWidths))
            self.assertAlmostEqual(.7, table._colWidths[0] / table._colWidths[1])

    def test_dense_headers_keep_whole_words_and_long_text_wraps_inside_columns(self):
        frame = pd.DataFrame({'Recommended spaces': ['A long explanatory value ' * 40],
                              'Floor': ['0'], 'Value': ['1']})
        table = table_from_df(frame, [5 * mm, 100 * mm, 100 * mm], self.styles)
        available = landscape(A3)[0] - 30 * mm - 12
        width, height = table.wrap(available, 600)
        self.assertAlmostEqual(available, width)
        self.assertGreater(height, 40)
        self.assertGreaterEqual(table._colWidths[0], table._report_column_minimums[0])
        for value, column_width in zip(table._cellvalues[1], table._colWidths):
            paragraph = value[0]
            self.assertLessEqual(paragraph.width + 12, column_width + .001)

    def test_split_pieces_fill_width_repeat_headers_and_preserve_all_rows(self):
        frame = pd.DataFrame({'Location': [f'Ward-{i:03d}' for i in range(90)],
                              'Explanation': ['A recorded delivery with a retained destination.'] * 90})
        table = table_from_df(frame, [45 * mm, 80 * mm], self.styles)
        available = landscape(A3)[0] - 30 * mm - 12
        table.wrap(available, 250)
        pieces = table.split(available, 250)
        self.assertEqual(2, len(pieces))
        self.assertTrue(all(isinstance(piece, PageWidthTable) for piece in pieces))
        self.assertEqual(92, sum(len(piece._cellvalues) for piece in pieces))  # two repeated headers
        for piece in pieces:
            self.assertAlmostEqual(available, piece.wrap(available, 600)[0])
            self.assertEqual(1, piece.repeatRows)
            self.assertEqual('Location', piece._cellvalues[0][0][0].getPlainText())

    def test_weekly_timetable_fills_a3_and_retains_every_continuation_entry(self):
        entries = [f'08:{i:02d}|Pickup {i}|Delivery {i}' for i in range(30)]
        frame = pd.DataFrame([dict(batch='Person A', Mon='\n'.join(entries))])
        table = payload_timetable_table(frame, self.styles)
        available = landscape(A3)[0] - 30 * mm - 12
        self.assertAlmostEqual(available, table.wrap(available, 600)[0])
        self.assertEqual(9, len(table._cellvalues))
        text = ' '.join(cell[0].getPlainText() for row in table._cellvalues[1:] for cell in row)
        for i in range(30):
            self.assertIn(f'Delivery {i}', text)

    def test_rendered_all_pages_have_margin_aligned_full_width_tables(self):
        root = Path(__file__).resolve().parents[1] / 'tmp'
        with tempfile.TemporaryDirectory(dir=root) as folder:
            path = Path(folder) / 'widths.pdf'
            doc = NumberedDocTemplate(str(path), pagesize=A4, leftMargin=15 * mm,
                rightMargin=15 * mm, topMargin=18 * mm, bottomMargin=15 * mm, title='Table width check')
            story = []
            for template in ('standard', 'landscape', 'a3_portrait', 'a3_landscape'):
                if story:
                    story.extend([NextPageTemplate(template), PageBreak()])
                frame = pd.DataFrame({'Location': [f'{template}-Ward-{i:03d}' for i in range(65)],
                                      'Result': ['A recorded delivery.'] * 65})
                story.append(table_from_df(frame, [35 * mm, 60 * mm], self.styles))
            doc.build(story)
            reader = PdfReader(path)
            self.assertGreater(len(reader.pages), 4)
            text = '\n'.join(page.extract_text() for page in reader.pages)
            for template in ('standard', 'landscape', 'a3_portrait', 'a3_landscape'):
                for i in range(65):
                    self.assertIn(f'{template}-Ward-{i:03d}', text)
            for page in reader.pages:
                colour = None
                start = None
                lines = []

                def visit(op, args, cm, tm):
                    nonlocal colour, start
                    if op == b'RG':
                        colour = tuple(float(v) for v in args)
                    elif op in (b'm', b'l'):
                        x, y = map(float, args)
                        point = (cm[0] * x + cm[2] * y + cm[4], cm[1] * x + cm[3] * y + cm[5])
                        if op == b'm':
                            start = point
                        elif colour and all(abs(a - b) < .001 for a, b in zip(colour, (.721569, .8, .894118))):
                            if start and abs(point[1] - start[1]) < .001:
                                lines.append(sorted((start[0], point[0])))
                            start = point

                page.extract_text(visitor_operand_before=visit)
                self.assertTrue(lines)
                for left, right in lines:
                    self.assertAlmostEqual(15 * mm + 6, left, places=3)
                    self.assertAlmostEqual(float(page.mediabox.width) - 15 * mm - 6, right, places=3)


if __name__ == '__main__':
    unittest.main()
