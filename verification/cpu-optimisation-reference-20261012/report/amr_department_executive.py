"""One A4 executive page for one category, shared by standalone and full PDFs."""
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from html import escape


def executive_data(review, common):
    start, end = (datetime.fromisoformat(common[k]) for k in ('start', 'end'))
    days = []
    day = start.replace(hour=0, minute=0, second=0, microsecond=0)
    while day < end:
        days.append(day)
        day += timedelta(days=1)
    weekly = len(days) > 8
    keys = list(range(7)) if weekly else [d.date().isoformat() for d in days]
    points = defaultdict(list)
    totals = defaultdict(Counter)
    daily = defaultdict(Counter)
    triggers = Counter()
    generated = 0
    for event in review['timetable']:
        stamp = datetime.fromisoformat(event['time'])
        if not start <= stamp < end:
            continue
        lane = 'Schedule' if event['kind'].startswith('Scheduled') else ('Delivery' if event['kind'] == 'Actual delivery' else 'Collection')
        key = stamp.weekday() if weekly else stamp.date().isoformat()
        points[key, lane].append(stamp)
        totals[key][lane] += 1
        if lane in ('Delivery', 'Collection'):
            daily[stamp.date().isoformat()][lane] += 1
    for event in review['events']:
        if not event['generated']:
            continue
        stamp = datetime.fromisoformat(event['generated'])
        if start <= stamp < end:
            generated += 1
            key = stamp.weekday() if weekly else stamp.date().isoformat()
            points[key, 'Generated'].append(stamp)
            totals[key]['Generated'] += 1
            if not event['parent_task']:
                triggers[event['trigger'].replace('_', ' ')] += 1
    pending = sum(e['status'] != 'Completed' for e in review['events'])
    excluded = sum(e['status'] == 'Completed' and not e['in_period'] for e in review['events'])
    served = len({e['department_id'] for e in review['events'] if e['in_period']})
    pattern = '; '.join(f'{count:,} {trigger}' for trigger, count in triggers.most_common())
    statements = [('Demand pattern', (pattern + ' primary tasks generated. Return tasks are shown separately in the audit.') if pattern else 'No primary tasks were generated within the reporting period.')]
    if daily:
        peak = max(daily, key=lambda key: sum(daily[key].values()))
        counts = daily[peak]
        tied = sum(sum(c.values()) == sum(counts.values()) for c in daily.values()) > 1
        peak_description = 'a joint busiest calendar day' if tied else 'the busiest calendar day'
        statements.append(('Peak service', f"{datetime.fromisoformat(peak):%a %d %b}: {counts['Delivery']:,} deliveries and {counts['Collection']:,} collections; {peak_description} in this interval."))
    else:
        statements.append(('Service activity', 'No completed deliveries or collections were recorded within the reporting period.'))
    statements.append(('Review position', f'{pending:,} generated tasks not completed; {excluded:,} completed tasks excluded from interval totals. {served} departments served from {len(review["summary"]) // 2} in category scope.'))
    schedules = sorted({time.strip() for rule in review['rules']
                        if rule['mode'] in {'scheduled', 'scheduled_threshold', 'scheduled_sporadic'}
                        for time in rule['schedule'].split(',') if time.strip()})
    windows = sorted({rule['window'] for rule in review['rules'] if rule['mode'] == 'timeframe' and rule['window'] != '-'})
    if schedules:
        schedule_text = 'Scheduled times: ' + ', '.join(schedules) + '. Configuration release/fill times; department/day rules apply.'
    elif windows:
        schedule_text = 'Configured timeframes: ' + ', '.join(windows) + '. No fixed scheduled release times.'
    else:
        schedule_text = 'No fixed scheduled times. ' + ('Demand-driven events are shown at their actual times.' if review['events'] else 'No category events recorded.')
    return dict(keys=keys, weekly=weekly, points=points, totals=totals, generated=generated, served=served, statements=statements,
                schedule_text=schedule_text, scheduled_times=schedules)


def draw_executive_summary(canvas, review, common):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph

    data = executive_data(review, common)
    width, height = A4
    canvas.setPageSize(A4)
    navy = colors.HexColor('#152A3C')
    muted = colors.HexColor('#566977')
    palette = {name: colors.HexColor(color) for name, color in [
        ('Schedule', '#B57816'), ('Generated', '#8267A3'), ('Delivery', '#1387A5'), ('Collection', '#377B51')]}
    left, right = 36, width - 36

    def text(x, y, content, size=9, bold=False, color=navy):
        canvas.setFillColor(color)
        canvas.setFont('Helvetica-Bold' if bold else 'Helvetica', size)
        canvas.drawString(x, y, content)

    def paragraph(content, top, font=9, leading=12):
        p = Paragraph(content, ParagraphStyle('executive', fontName='Helvetica', fontSize=font, leading=leading, textColor=navy))
        _, h = p.wrap(right - left, 1000)
        p.drawOn(canvas, left, top - h)
        return top - h

    text(left, 807, 'DEPARTMENT SERVICE REVIEW  /  SIMULATED DATA', 8, True, muted)
    # Wrap long category names within a fixed two-line title area.
    title = Paragraph(escape(review['name']) + ' | Executive summary', ParagraphStyle('executiveTitle', fontName='Helvetica-Bold', fontSize=19, leading=22, textColor=navy))
    _, title_height = title.wrap(right - left, 55)
    if title_height > 44:
        title = Paragraph(escape(review['name']) + ' | Executive summary', ParagraphStyle('executiveTitleSmall', fontName='Helvetica-Bold', fontSize=13, leading=15, textColor=navy))
        _, title_height = title.wrap(right - left, 55)
    title.drawOn(canvas, left, 791 - title_height)
    text(left, 736, f"{common['start'][:16]} to {common['end'][:16]}  |  End excluded", 9, color=muted)
    canvas.setStrokeColor(colors.HexColor('#D3DEE5'))
    canvas.line(left, 726, right, 726)

    metrics = [(review['total_deliveries'], 'Deliveries'), (review['total_collections'], 'Collections'),
               (data['served'], 'Departments served'), (data['generated'], 'Tasks generated*')]
    step = (right - left) / 4
    for i, (value, label) in enumerate(metrics):
        x = left + i * step
        text(x, 694, f'{value:,}', 24, True)
        text(x, 677, label, 9, color=muted)

    top = 655
    for label, statement in data['statements']:
        top = paragraph(f'<b>{escape(label)}.</b> {escape(statement)}', top) - 7
    if top < 566:
        raise ValueError('Executive statements exceed the one-page layout; shorten the category trigger labels.')

    paragraph('<b>' + escape(data['schedule_text'].split(':', 1)[0]) + '</b>' +
              (': ' + escape(data['schedule_text'].split(':', 1)[1].strip()) if ':' in data['schedule_text'] else ''), 562, 8.5, 11)

    text(left, 529, 'Weekly event timeline', 13, True)
    text(left, 513, 'Every tick is an event; simultaneous events overlap. D / C = completed daily totals.', 8, color=muted)
    legend = [('Schedule', 'Configured schedule'), ('Generated', 'Tasks generated*'), ('Delivery', 'Actual deliveries'), ('Collection', 'Actual collections')]
    for i, (kind, label) in enumerate(legend):
        x = left + i * step
        canvas.setFillColor(palette[kind])
        canvas.rect(x, 497, 7, 3, stroke=0, fill=1)
        text(x + 11, 495, label, 7.5, color=muted)
    plot_left, plot_right = 102, right - 51
    plot_top, plot_bottom = 477, 190
    plot_width = plot_right - plot_left
    row_height = (plot_top - plot_bottom) / max(1, len(data['keys']))
    text(right - 42, 480, 'D / C', 8, True)
    for i, key in enumerate(data['keys']):
        y = plot_top - i * row_height
        canvas.setFillColor(colors.HexColor('#F2F6F8') if i % 2 == 0 else colors.white)
        canvas.rect(left, y - row_height, right - left, row_height, stroke=0, fill=1)
        day = datetime.fromisoformat(key) if isinstance(key, str) else None
        text(left + 3, y - 14, day.strftime('%a %d %b') if day else ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][key], 8, True)
        counts = data['totals'][key]
        text(right - 44, y - 21, f"{counts['Delivery']} / {counts['Collection']}", 8)
        for hour in range(0, 25, 2):
            x = plot_left + plot_width * hour / 24
            canvas.setStrokeColor(colors.HexColor('#DCE5EB'))
            canvas.setLineWidth(0.4)
            canvas.line(x, y - row_height + 2, x, y - 2)
        for lane, kind in enumerate(palette):
            lane_y = y - 6 - lane * ((row_height - 10) / 4)
            canvas.setStrokeColor(palette[kind])
            canvas.setLineWidth(0.85)
            for stamp in data['points'].get((key, kind), []):
                second = stamp.hour * 3600 + stamp.minute * 60 + stamp.second + stamp.microsecond / 1e6
                x = plot_left + plot_width * second / 86400
                canvas.line(x, lane_y - 2, x, lane_y + 2)
        if not any(data['points'].get((key, kind)) for kind in palette):
            text(plot_left + 7, y - 20, 'No events', 8, color=muted)
    for hour in range(0, 25, 2):
        canvas.setFillColor(muted)
        canvas.setFont('Helvetica', 7.5)
        canvas.drawCentredString(plot_left + plot_width * hour / 24, 178, f'{hour:02}:00')

    extra = 'Multiple weeks are overlaid by calendar weekday. ' if data['weekly'] else 'Calendar dates shown, including partial first/last days. '
    paragraph(escape(extra + '*Generated includes primary and return tasks, including tasks not completed. Configuration schedules are planned release/fill events, not guaranteed deliveries.'), 160, 8, 10.5)
    paragraph('Deliveries use staff final arrival where logged, otherwise AMR drop-off completion. Collections use AMR pickup completion. Empty-container return deliveries are included. The detailed review contains department routes and exact event times.', 120, 8, 10.5)
    paragraph('Schedule: supplied configuration snapshot. Actual service: simulation event log. Current-service figures require owner confirmation.', 77, 8, 10.5)
    canvas.setStrokeColor(colors.HexColor('#D3DEE5'))
    canvas.line(left, 41, right, 41)
    text(left, 27, 'Category review | ' + common['start'][:10] + ' to ' + common['end'][:10], 7.5, color=muted)
    canvas.setFont('Helvetica', 7.5)
    canvas.drawRightString(right, 27, 'Executive summary | 1')


def export_executive_pdf(review, common, path):
    from reportlab.pdfgen.canvas import Canvas
    from reportlab.lib.pagesizes import A4
    canvas = Canvas(str(path), pagesize=A4)
    canvas.setTitle(review['name'] + ' executive summary')
    draw_executive_summary(canvas, review, common)
    canvas.showPage()
    canvas.save()
