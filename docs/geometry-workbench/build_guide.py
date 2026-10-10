"""Editable source for the illustrated geometry-workbench tutorial.

Run from repository root: .venv/Scripts/python.exe docs/geometry-workbench/build_guide.py
Screenshots are captured from the actual Qt workbench, not generated mockups.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak
from visualiser.geometry_workbench import GeometryWorkbench


def build():
    source = Path(__file__).resolve().parent
    output = ROOT / 'output/pdf/geometry-workbench-guide.pdf'
    output.parent.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    font_path = Path('C:/Windows/Fonts/segoeui.ttf')
    if font_path.is_file():
        font_id = QFontDatabase.addApplicationFont(str(font_path))
        app.setFont(QFont(QFontDatabase.applicationFontFamilies(font_id)[0], 10))
    window = GeometryWorkbench()
    window.show()
    app.processEvents()
    window.fit()
    app.processEvents()
    window.grab().save(str(source / 'reference.png'))
    window.begin_drawing('route')
    for point in [[0,0], [1,0], [1,1]]:
        window.add_point(point)
    window.finish_drawing()
    window.pivots.setChecked(True)
    window.properties.show()
    app.processEvents()
    window.fit()
    app.processEvents()
    window.grab().save(str(source / 'pivot.png'))
    window.close()

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='TitleBlue', fontName='Helvetica-Bold', fontSize=23, leading=27, textColor=colors.HexColor('#153950'), spaceAfter=12))
    styles.add(ParagraphStyle(name='Deck', fontName='Helvetica', fontSize=11, leading=15, textColor=colors.HexColor('#42566a'), spaceAfter=10))
    styles.add(ParagraphStyle(name='Step', fontName='Helvetica', fontSize=10.5, leading=14, spaceAfter=9))
    styles.add(ParagraphStyle(name='CaptionSmall', fontName='Helvetica', fontSize=9, leading=12, textColor=colors.HexColor('#42566a'), spaceAfter=12))
    story = []
    def paragraph(text, style='Step'):
        story.append(Paragraph(text, styles[style]))
    def screenshot(name):
        story.append(Image(str(source/name), width=499, height=499*820/1280))
        story.append(Spacer(1,10))

    paragraph('Draw and check an AMR manoeuvre', 'TitleBlue')
    paragraph('Working prototype tutorial | 3 October 2026 | Geometry study, not a simulation run', 'Deck')
    paragraph('<b>Launch:</b> from the repository folder, run<br/><font name="Courier">.\\.venv\\Scripts\\python.exe -m visualiser.geometry_workbench</font>')
    paragraph('The drawing fills the main window. Use the toolbar to draw; open the properties or <b>Try the reference</b> panel only when needed. Wheel zooms; drag in inspection mode to pan. <b>Fit</b> restores the complete view.')
    screenshot('reference.png')
    paragraph('Blue: planned trajectory. Dashed grey: requested polyline. Rectangles along the route: loaded footprint plus clearance. Solid grey rectangles: explicitly modelled obstacles.', 'CaptionSmall')
    paragraph('<b>1. Check the reference.</b> Click <b>Example</b>. A 2 m radius quarter-circle replaces the sharp corner. The straights are 4 m each: length = 4 + (2 x pi / 2) + 4 = <b>11.141593 m</b>. At 1 m/s, travel time is <b>11.141593 s</b>. The status must say <b>clear</b>.')
    paragraph('<b>2. Test loaded clearance.</b> Open <b>Robot, load and manoeuvres</b>. The opening is 1.10 m wide. Load width 0.90 m plus 0.05 m clearance per side needs 1.00 m. Change load width to <b>1.01 m</b> and leave the field: required width is 1.11 m and status becomes <b>collision</b>. Undo restores clear.')
    story.append(PageBreak())
    paragraph('Try a tight turn and a permitted pivot', 'TitleBlue')
    paragraph('The same motion objects supply the drawing, exact length, timing and clearance checks.', 'Deck')
    paragraph('<b>3. Draw a short route.</b> Click <b>Draw route</b>. Type <b>0,0</b>, <b>1,0</b>, then <b>1,1</b> in the coordinate box, pressing Enter after each. Click <b>Finish</b>. A 2 m radius cannot fit on the 1 m legs: status must say <b>infeasible_route</b>. No straight-line substitute is accepted.')
    paragraph('<b>4. Permit a pivot.</b> In properties, enable stationary pivots. Leave travel speed at 1 m/s and pivot speed at 45 degrees/s. The orange marker shows a 90-degree pivot. Expected length: <b>2 m</b>. Expected time: 2/1 + 90/45 = <b>4 s</b>.')
    screenshot('pivot.png')
    paragraph('<b>5. Draw and save.</b> <b>Draw obstacle</b> takes two opposite rectangle corners. Shift constrains drawing points; snapping uses a 0.25 m grid. Enter finishes a route; Escape cancels its draft. Completed route, obstacle and parameter changes each support Undo/Redo. <b>Save study</b> writes a separate JSON study; reopening recomputes results, including infeasible studies.')
    paragraph('<b>Interpret results carefully.</b> <b>Collision</b> means the modelled envelope intersects an obstacle. <b>Clearance unresolved</b> or <b>search limit</b> does not mean clear. Exact boundary contact is allowed; add clearance to require separation. The envelope is a centred robot/load rectangle; obstacles are axis-aligned rectangles. No lanes, traffic reservations, reversing, endpoint-heading constraints or simulator playback integration are included yet.', 'CaptionSmall')

    def footer(canvas, doc):
        canvas.setStrokeColor(colors.HexColor('#cbd5df'))
        canvas.line(48,35,547,35)
        canvas.setFont('Helvetica',8)
        canvas.setFillColor(colors.HexColor('#42566a'))
        canvas.drawString(48,23,'AMR geometric workbench | Prototype reference chapter | Editable source retained')
        canvas.drawRightString(547,23,str(doc.page))

    document = SimpleDocTemplate(str(output), pagesize=(595,842), rightMargin=48, leftMargin=48, topMargin=38, bottomMargin=48,
                                title='AMR geometric workbench - illustrated prototype tutorial', author='AMR Simulator project')
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    print(output)


if __name__ == '__main__':
    build()
