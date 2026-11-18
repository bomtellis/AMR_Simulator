"""Print and CAD export for a saved run's floor route drawings."""
from dataclasses import dataclass
from io import BytesIO
import math
from pathlib import Path
import re
from shutil import copyfile
from tempfile import TemporaryDirectory

import ezdxf
from ezdxf.colors import RGB
from PySide6.QtCore import QBuffer, QIODevice
from reportlab.lib.pagesizes import A1, landscape
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas

from amr_floor_route_drawings import (
    FloorDrawing, build_floor_drawings, category_colours, category_paths, drawing_run_name,
)
from amr_route_analysis import _check, _hash
from visualiser.cad_map_style import scale_bar
from visualiser.dxf_scene import DXFScene
from visualiser.pdf_underlay import normalise_pdf_underlay, underlay_world_bounds, underlay_world_size


PAGE_WIDTH, PAGE_HEIGHT = landscape(A1)
MARGIN = 12 * mm
MAP_TOP = PAGE_HEIGHT - 42 * mm
MAP_BOTTOM = 20 * mm
PITCH_MM = 0.60
ROUTE_WIDTH_MM = 0.30
INK = '#172938'
MUTED = '#485868'
RULE = '#CFD7DE'
GAP_COLOUR = '#9C3528'


@dataclass
class FloorSheet:
    drawing: FloorDrawing
    dxf: dict | None
    pdf: tuple | None
    bounds: tuple
    fit_scale: float
    map_right: float
    notes: list[str]
    categories: list
    denominator: int = 1

    @property
    def scale(self):
        return 1000 * mm / self.denominator

    @property
    def pitch(self):
        return PITCH_MM * mm / self.scale


def _sheet(run, drawing, unassigned):
    dxf = run.drawings.get(drawing.floor)
    pdf = run.pdf_drawings.get(drawing.floor)
    bounds = []
    if dxf:
        bounds.append(dxf['bounds'])
    if pdf:
        bounds.append(underlay_world_bounds(pdf[1]))
    points = list(drawing.landings | drawing.gap_points)
    points.extend(point for path, _ in drawing.chains for point in path)
    if points:
        xs, ys = zip(*points)
        bounds.append((min(xs), min(ys), max(xs), max(ys)))
    if not bounds:
        bounds = [(0, 0, 10, 10)]
    x0, y0 = (min(rect[index] for rect in bounds) for index in (0, 1))
    x1, y1 = (max(rect[index] for rect in bounds) for index in (2, 3))
    categories = sorted(drawing.confirmed.keys() | drawing.planned.keys(),
                        key=lambda key: (key[0] != 'payload', key[1].casefold(), key))
    columns = max(1, math.ceil(len(categories) / 34))
    legend_width = 91 * mm + min(columns - 1, 2) * 45 * mm
    map_right = PAGE_WIDTH - MARGIN - legend_width - 6 * mm
    # Reserve room for diagrammatic separation around the plan extents.
    max_bundle = max((len(styles) for _, styles in drawing.chains), default=1)
    padding = (max_bundle * PITCH_MM + 1.5) * mm
    fit_scale = min((map_right - MARGIN - 2 * padding) / max(1, x1 - x0),
                    (MAP_TOP - MAP_BOTTOM - 2 * padding) / max(1, y1 - y0))
    if fit_scale <= 0:
        raise ValueError(f'Floor {drawing.floor} has too many overlapping payload types to fit on an A1 sheet.')
    notes = []
    if not dxf and not pdf:
        notes.append('Saved floor plan unavailable. Route geometry only.')
    if any(warning.startswith(f'Floor {drawing.floor}: external') for warning in run.warnings):
        notes.append('External floor plan supplied as context.')
    if not run.complete:
        notes.append('Saved evidence is incomplete. Counts cover the available records.')
    if drawing.gaps:
        notes.append(f'{drawing.gaps:,} floor trip(s) have route geometry gaps.')
    if unassigned:
        notes.append(f'{unassigned:,} selected leg(s) have missing floor evidence in this export.')
    return FloorSheet(drawing, dxf, pdf, (x0, y0, x1, y1), fit_scale, map_right, notes, categories)


def _print_denominator(sheets):
    """Select the largest useful round print scale that fits every floor."""
    required = max(1, 1000 * mm / min(sheet.fit_scale for sheet in sheets))
    magnitude = 10 ** math.floor(math.log10(required))
    round_steps = (1, 1.25, 1.5, 2, 2.5, 3, 4, 5, 6, 7.5, 10)
    return next(math.ceil(step * magnitude) for step in round_steps if math.ceil(step * magnitude) >= required)


def _filter_text(filters):
    labels = {'floor': 'Floor', 'amr': 'AMR', 'lift': 'Lift', 'purpose': 'Purpose', 'profile': 'Profile',
              'origin': 'Origin', 'destination': 'Destination', 'compliance': 'Forced floor',
              'lift_origin_floor': 'Lift from floor', 'lift_destination_floor': 'Lift to floor'}
    return ' | '.join(f'{label} {getattr(filters, key)}' for key, label in labels.items()
                      if getattr(filters, key) is not None and getattr(filters, key) != '')


def _draw_background(canvas, sheet):
    if sheet.pdf:
        image, entry = sheet.pdf
        placement = normalise_pdf_underlay(entry)
        width, height = underlay_world_size(placement)
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        if not image.save(buffer, 'PNG'):
            raise ValueError('Could not render the saved PDF floor plan.')
        canvas.saveState()
        canvas.translate(placement['x_m'], placement['y_m'])
        canvas.rotate(placement['rotation_deg'])
        canvas.setFillAlpha(placement['opacity'])
        canvas.drawImage(ImageReader(BytesIO(bytes(buffer.data()))), 0, 0, width, height, mask='auto')
        canvas.restoreState()
    if not sheet.dxf:
        return
    geometry = canvas.beginPath()
    canvas.setStrokeColor('#A6B0B9')
    canvas.setLineWidth(0.22 / sheet.scale)
    for entity in sheet.dxf['entities']:
        kind = entity['type']
        if kind == 'LINE':
            geometry.moveTo(*entity['start'])
            geometry.lineTo(*entity['end'])
        elif kind == 'POLYLINE' and entity['points']:
            geometry.moveTo(*entity['points'][0])
            for point in entity['points'][1:]:
                geometry.lineTo(*point)
            if entity.get('closed'):
                geometry.close()
        elif kind in ('ARC', 'CIRCLE'):
            x, y = entity['center']
            radius = entity['radius']
            if kind == 'CIRCLE':
                geometry.circle(x, y, radius)
            else:
                start, end = entity['start_angle'], entity['end_angle']
                geometry.arc(x - radius, y - radius, x + radius, y + radius,
                             start, (end - start) % 360 or 360)
    canvas.drawPath(geometry)
    canvas.setFillColor('#697480')
    for entity in sheet.dxf['entities']:
        if entity['type'] == 'TEXT' and entity['text']:
            x, y = entity['insert']
            height = min(9 / sheet.scale, max(0.22, entity['height']))
            canvas.saveState()
            canvas.translate(x, y)
            canvas.rotate(entity['rotation'])
            canvas.setFont('Helvetica', height)
            canvas.drawString(0, 0, ' '.join(entity['text'].split()))
            canvas.restoreState()


def _draw_map(canvas, sheet, paths, colours, cancel):
    x0, y0, x1, y1 = sheet.bounds
    canvas.saveState()
    canvas.translate((MARGIN + sheet.map_right - (x0 + x1) * sheet.scale) / 2,
                     (MAP_BOTTOM + MAP_TOP - (y0 + y1) * sheet.scale) / 2)
    canvas.scale(sheet.scale, sheet.scale)
    _draw_background(canvas, sheet)
    canvas.setLineWidth(ROUTE_WIDTH_MM * mm / sheet.scale)
    canvas.setLineCap(1)
    canvas.setLineJoin(1)
    for category, confirmed, points in paths:
        _check(cancel)
        canvas.setStrokeColor(colours[category])
        canvas.setDash([] if confirmed else [1.5 * mm / sheet.scale, 1.0 * mm / sheet.scale])
        path = canvas.beginPath()
        path.moveTo(*points[0])
        for point in points[1:]:
            path.lineTo(*point)
        canvas.drawPath(path)
    canvas.setDash([])
    canvas.setStrokeColor(MUTED)
    canvas.setLineWidth(0.2 * mm / sheet.scale)
    for x, y in sorted(sheet.drawing.landings):
        canvas.circle(x, y, 0.85 * mm / sheet.scale, fill=0)
    canvas.setStrokeColor(GAP_COLOUR)
    for x, y in sorted(sheet.drawing.gap_points):
        radius = 1.1 * mm / sheet.scale
        canvas.line(x - radius, y - radius, x + radius, y + radius)
        canvas.line(x - radius, y + radius, x + radius, y - radius)
    canvas.restoreState()


def _pdf_label(canvas, text, x, y, *, size=9, colour=INK, bold=False, width=None, align='left'):
    font = 'Helvetica-Bold' if bold else 'Helvetica'
    text = ' '.join(str(text).split())
    if width is not None and stringWidth(text, font, size) > width:
        size *= width / stringWidth(text, font, size)
    canvas.setFillColor(colour)
    canvas.setFont(font, size)
    draw = canvas.drawRightString if align == 'right' else canvas.drawString
    draw(x, y, text)


def _pdf_legend(canvas, sheet, colours, include_plans):
    left = sheet.map_right + 6 * mm
    width = PAGE_WIDTH - MARGIN - left
    right = left + width
    y = MAP_TOP - 3 * mm
    _pdf_label(canvas, 'Trips by payload type', left, y, size=13, bold=True)
    columns = max(1, math.ceil(len(sheet.categories) / 34))
    column_width = width / columns
    rows = math.ceil(len(sheet.categories) / columns)
    spacing = min(17, 469 / max(rows, 1))
    y -= 24
    if not sheet.categories:
        _pdf_label(canvas, 'No trips meet the export selection.', left, y, colour=MUTED)
        columns = 0
    for col in range(columns):
        x = left + col * column_width
        end = x + column_width - (10 if col + 1 < columns else 0)
        _pdf_label(canvas, 'Payload type', x, y, bold=True, size=8, colour=MUTED)
        _pdf_label(canvas, 'Confirmed' if include_plans else 'Trips', end - (36 if include_plans else 0),
                   y, align='right', size=8, colour=MUTED)
        if include_plans:
            _pdf_label(canvas, 'Planned', end, y, align='right', size=8, colour=MUTED)
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.5)
        canvas.line(x, y - 5, end, y - 5)
        for row, category in enumerate(sheet.categories[col * rows:(col + 1) * rows], 1):
            at = y - 4 - row * spacing
            canvas.setStrokeColor(colours[category])
            canvas.setLineWidth(ROUTE_WIDTH_MM * mm)
            canvas.line(x, at + 2.5, x + 12, at + 2.5)
            _pdf_label(canvas, category[1], x + 18, at, width=end - x - (83 if include_plans else 49))
            _pdf_label(canvas, f'{sheet.drawing.confirmed[category]:,}', end - (36 if include_plans else 0),
                       at, align='right')
            if include_plans:
                _pdf_label(canvas, f'{sheet.drawing.planned[category]:,}', end, at, align='right')
    y -= max(34, 16 + rows * spacing)
    key = []
    if include_plans:
        key.append('Dashed lines show stretches recorded only as plans.')
    if sheet.drawing.landings:
        key.append('Open circles mark lift boarding and exit points.')
    if sheet.drawing.gap_points:
        key.append('Red crosses mark known ends of route geometry gaps.')
    for note in key + sheet.notes:
        for line in simpleSplit(note, 'Helvetica', 8.5, right - left):
            _pdf_label(canvas, line, left, y, size=8.5, colour=MUTED)
            y -= 11
        y -= 4


def _pdf_scale(canvas, sheet):
    metres, length = scale_bar(sheet.scale, target_pixels=68 * mm)
    right = PAGE_WIDTH - MARGIN
    left = right - length
    y = 45
    canvas.setStrokeColor(INK)
    canvas.setLineWidth(0.65)
    canvas.line(left, y, right, y)
    for x in (left, (left + right) / 2, right):
        canvas.line(x, y - 3, x, y + 3)
    _pdf_label(canvas, '0', left, y + 7, size=8)
    _pdf_label(canvas, f'{metres:g} m', right, y + 7, size=8, align='right')
    _pdf_label(canvas, f'1:{sheet.denominator:,} at A1 | Print at 100%', right, 27,
               size=9, bold=True, align='right')


def _pdf_floor(canvas, sheet, paths, colours, run_name, period, filters, include_plans, cancel):
    _pdf_label(canvas, f'Floor {sheet.drawing.floor}  |  AMR routes', MARGIN, PAGE_HEIGHT - 53,
               size=25, bold=True)
    _pdf_label(canvas, run_name, MARGIN, PAGE_HEIGHT - 73, size=10, width=PAGE_WIDTH - 230)
    _pdf_label(canvas, period, MARGIN, PAGE_HEIGHT - 90, size=9, colour=MUTED)
    _pdf_label(canvas, f'{sheet.drawing.total:,}', PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 57,
               size=29, bold=True, align='right')
    _pdf_label(canvas, 'Floor trips', PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 73, size=9, align='right')
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.65)
    canvas.line(MARGIN, MAP_TOP + 8, PAGE_WIDTH - MARGIN, MAP_TOP + 8)
    canvas.line(sheet.map_right + 3 * mm, MAP_TOP, sheet.map_right + 3 * mm, MAP_BOTTOM)
    _draw_map(canvas, sheet, paths, colours, cancel)
    _pdf_legend(canvas, sheet, colours, include_plans)
    if filters:
        _pdf_label(canvas, filters, MARGIN, 42, size=8, width=sheet.map_right - MARGIN, colour=MUTED)
    _pdf_label(canvas, 'One trip per movement leg per floor. Parallel offsets are diagrammatic.',
               MARGIN, 27, size=8.5, colour=MUTED)
    _pdf_scale(canvas, sheet)
    canvas.showPage()


def _add_layer(doc, stem, *, rgb=None):
    name = re.sub(r'[<>/\\":;?*|=`]|[\x00-\x1f]', '_', stem)[:120]
    candidate = name
    suffix = 2
    while candidate in doc.layers:
        candidate = f'{name}_{suffix}'
        suffix += 1
    layer = doc.layers.add(candidate, color=7)
    if rgb:
        layer.rgb = RGB.from_hex(rgb)
    return candidate


def _verify_drawing(path, digest, cancel):
    if digest and _hash(path, cancel) != digest:
        raise ValueError(f'Saved drawing changed after loading: {path.name}. Reload the run and export again.')


def _attach_pdf(doc, sheet, path, units_per_metre, layer, cancel):
    _image, entry = sheet.pdf
    placement = normalise_pdf_underlay(entry)
    source = Path(placement['filepath'])
    relative_name = f'floor-{sheet.drawing.floor}-underlay.pdf'
    staged = path.parent / relative_name
    copyfile(source, staged)
    _verify_drawing(staged, entry.get('sha256'), cancel)
    width, height = underlay_world_size(placement)
    if doc.units:
        # PDF drawing coordinates resolve against physical page size in a unitful DXF.
        metres_per_point = 0.0254 / 72
        source_width = entry['page_width_pt'] * metres_per_point
        source_height = entry['page_height_pt'] * metres_per_point
        sx, sy = width / source_width, height / source_height
    else:
        sx = width * units_per_metre
        sy = sx * (height / width) / (entry['page_height_pt'] / entry['page_width_pt'])
    definition = doc.add_underlay_def(relative_name, name=str(placement['page']))
    underlay = doc.modelspace().add_underlay(
        definition, insert=(placement['x_m'] * units_per_metre, placement['y_m'] * units_per_metre),
        rotation=placement['rotation_deg'], scale=(sx, sy, sx), dxfattribs={'layer': layer},
    )
    underlay.dxf.fade = round(100 * (1 - placement['opacity']))
    return underlay


def _write_dxf(path, sheet, paths, colours, run_name, period, filters, include_plans, cancel):
    if sheet.dxf:
        source = Path(sheet.dxf['path'])
        _verify_drawing(source, sheet.dxf.get('sha256'), cancel)
        doc = ezdxf.readfile(source)
        _verify_drawing(source, sheet.dxf.get('sha256'), cancel)
        if doc.dxfversion < 'AC1024':
            doc.dxfversion = 'AC1024'
    else:
        doc = ezdxf.new('R2010')
        doc.units = 6  # Metres, the simulator's world units.
    units = 1 / DXFScene._detect_dxf_unit_scale(doc)
    msp = doc.modelspace()
    if sheet.pdf:
        layer = _add_layer(doc, 'AMR Floor Underlay')
        underlay = _attach_pdf(doc, sheet, path, units, layer, cancel)
        # A zero sort handle renders last. Use the lowest positive sort handle
        # for the new background and retain the source drawing's ordering.
        ordering = dict(msp.get_redraw_order())
        ordered = sorted((entity for entity in msp if entity is not underlay),
                         key=lambda entity: int(ordering.get(entity.dxf.handle, entity.dxf.handle), 16) or 16 ** 16)
        msp.set_redraw_order({entity.dxf.handle: f'{index:X}'
                              for index, entity in enumerate([underlay, *ordered], 1)})
        doc.header['$SORTENTS'] = int(doc.header.get('$SORTENTS', 0)) | 16
    annotation_layer = _add_layer(doc, 'AMR Route Legend')
    marker_layer = _add_layer(doc, 'AMR Route Evidence Markers', rgb=MUTED)
    layers = {category: _add_layer(doc, f'AMR Route - {category[1]}', rgb=colours[category])
              for category in sheet.categories}
    dash = 'AMR_ROUTE_PLAN_DASH'
    while dash in doc.linetypes:
        dash += '_'
    dash_unit = units * mm / sheet.scale
    if include_plans:
        # Neutralise the source-wide linetype scaling for the exported route dash.
        dash_scale = dash_unit / (doc.header.get('$LTSCALE', 1) or 1)
        doc.linetypes.new(dash, dxfattribs={'description': 'Recorded plan',
                                           'pattern': [2.5 * dash_scale, 1.5 * dash_scale, -dash_scale]})
    for category, confirmed, points in paths:
        _check(cancel)
        attrs = {'layer': layers[category], 'lineweight': round(100 * ROUTE_WIDTH_MM)}
        if not confirmed:
            attrs['linetype'] = dash
        line = msp.add_lwpolyline([(x * units, y * units) for x, y in points], dxfattribs=attrs)
        line.dxf.flags |= 128  # Continue the dash pattern through vertices.
    for x, y in sorted(sheet.drawing.landings):
        msp.add_circle((x * units, y * units), 0.85 * dash_unit, dxfattribs={'layer': marker_layer})
    for x, y in sorted(sheet.drawing.gap_points):
        radius = 1.1 * dash_unit
        for direction in (-1, 1):
            entity = msp.add_line((x * units - radius, y * units - direction * radius),
                                  (x * units + radius, y * units + direction * radius),
                                  dxfattribs={'layer': marker_layer})
            entity.rgb = RGB.from_hex(GAP_COLOUR)
    _cad_legend(doc, sheet, annotation_layer, layers, units, run_name, period, filters, include_plans)
    doc.saveas(path)


def _cad_legend(doc, sheet, layer, layers, units, run_name, period, filters, include_plans):
    msp = doc.modelspace()
    x0, y0, x1, y1 = sheet.bounds
    unit = units / sheet.scale
    x = x1 * units + 24 * unit
    y = y1 * units
    furthest = x

    def row(text, size=8, category=None):
        nonlocal y, furthest
        if category is not None:
            msp.add_line((x, y + 3 * unit), (x + 12 * unit, y + 3 * unit),
                         dxfattribs={'layer': layers[category]})
        at = x + (18 * unit if category is not None else 0)
        text = ' '.join(text.split())
        msp.add_text(text, dxfattribs={'layer': layer, 'height': size * unit, 'insert': (at, y)})
        furthest = max(furthest, at + size * 0.67 * unit * len(text))
        y -= (size + 8) * unit

    row(f'Floor {sheet.drawing.floor} | AMR routes', 15)
    row(f'{sheet.drawing.total:,} floor trips', 12)
    row(run_name)
    row(period)
    if filters:
        row(filters)
    row('Trips by payload type', 10)
    if not sheet.categories:
        row('No trips meet the export selection.')
    for category in sheet.categories:
        count = f'{sheet.drawing.confirmed[category]:,}'
        if include_plans:
            count += f' confirmed / {sheet.drawing.planned[category]:,} planned'
        row(f'{category[1]}   {count}', category=category)
    row('One trip per movement leg per floor. Parallel offsets are diagrammatic.')
    if include_plans:
        row('Dashed lines show stretches recorded only as plans.')
    if sheet.drawing.landings:
        row('Open circles mark lift boarding and exit points.')
    if sheet.drawing.gap_points:
        row('Red crosses mark known ends of route geometry gaps.')
    for note in sheet.notes:
        row(note)
    bottom = min(y, y0 * units)
    span = max(y1 * units - bottom, 0.62 * (furthest - x0 * units))
    doc.set_modelspace_vport(height=span * 1.10, center=((x0 * units + furthest) / 2, (bottom + y1 * units) / 2))


def export_floor_route_drawings(run, filters, directory, *, pdf=True, dxf=True, include_plans=False,
                                cancel=None, progress=None):
    """Write the entire selected set in a staging folder before publishing it."""
    if not pdf and not dxf:
        raise ValueError('Select PDF, DXF, or both.')
    target = Path(directory).resolve()
    source_parent = Path(run.source).resolve().parent
    if target == source_parent or source_parent in target.parents:
        raise ValueError('Choose a destination outside the source run.')
    if target.exists():
        raise FileExistsError('Choose a new export folder. Existing drawings are preserved.')
    if progress:
        progress('Counting saved legs and finding shared route stretches…')
    floors, unassigned = build_floor_drawings(run, filters, include_plans=include_plans, cancel=cancel)
    if not floors:
        raise ValueError('No floor could be identified in the selected run and time window.')
    _check(cancel)
    sheets = [_sheet(run, drawing, unassigned) for drawing in floors]
    denominator = _print_denominator(sheets)
    colours = category_colours(run)
    end = min(run.duration, filters.end) if filters.end is not None else run.duration
    run_name = drawing_run_name(run)
    evidence = 'Confirmed and planned' if include_plans else 'Confirmed simulation outcomes'
    period = f'{filters.start:,.3f}'.rstrip('0').rstrip('.') + ' to ' + f'{end:,.3f}'.rstrip('0').rstrip('.')
    period = f'{period} elapsed seconds | {evidence}'
    filter_text = _filter_text(filters)
    with TemporaryDirectory(prefix='.floor-route-drawings-', dir=target.parent) as temporary:
        staged = Path(temporary) / 'drawings'
        staged.mkdir()
        canvas = Canvas(str(staged / 'amr-floor-routes.pdf'), pagesize=(PAGE_WIDTH, PAGE_HEIGHT)) if pdf else None
        if canvas:
            canvas.setTitle('AMR floor route drawings')
        for index, sheet in enumerate(sheets, 1):
            _check(cancel)
            drawing = sheet.drawing
            if progress:
                progress(f'Drawing floor {drawing.floor} ({index} of {len(sheets)})…')
            sheet.denominator = denominator
            paths = list(category_paths(drawing, sheet.pitch))
            if canvas:
                _pdf_floor(canvas, sheet, paths, colours, run_name, period, filter_text, include_plans, cancel)
            if dxf:
                _write_dxf(staged / f'floor-{drawing.floor}-amr-routes.dxf', sheet, paths, colours,
                           run_name, period, filter_text, include_plans, cancel)
        if canvas:
            canvas.save()
        _check(cancel)
        staged.rename(target)
    return target
