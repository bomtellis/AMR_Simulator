"""Daily trip-request counts from the authoritative demand preview, not dispatch estimates."""
from copy import deepcopy
from datetime import date, datetime, timedelta

from amr_simulation_inputs import DEFAULTS, simulation_horizon_seconds


def run_dates(config):
    start = datetime.fromisoformat(config['simulation'].get('start_datetime', DEFAULTS['start_datetime']))
    end = start + timedelta(seconds=simulation_horizon_seconds(config))
    last = end.date() - timedelta(days=1) if end.time() == datetime.min.time() else end.date()
    return start, end, max(start.date(), last)


def day_trip_preview(config, selected_date, *, source='Demand'):
    """Keep the original run start so recurrence and accumulated demand stay correct."""
    from amr_demand_preview import build_demand_preview
    selected = date.fromisoformat(str(selected_date))
    start, end, last = run_dates(config)
    if not start.date() <= selected <= last:
        raise ValueError('Choose a date within the simulation period.')
    midnight = datetime.combine(selected, datetime.min.time(), start.tzinfo)
    next_day = midnight + timedelta(days=1)
    preview = build_demand_preview(deepcopy(config), end_datetime=min(end, next_day).isoformat())
    return summarise_day(preview, selected, source=source)


def summarise_day(preview, selected_date, *, source='Demand'):
    """Half-open civil days avoid counting a midnight release in both days."""
    selected = date.fromisoformat(str(selected_date))
    generation = preview['frozen_inputs'].get('task_generation', {})
    categories = {}

    def category(key):
        if key not in categories:
            cfg = generation.get('categories', {}).get(key, {})
            categories[key] = dict(key=key, label=cfg.get('display_name') or key.replace('_', ' ').title(),
                trips=0, quantity=0, bins=[0]*96, notes=str(cfg.get('notes', '') or ''),
                scope_notes=[], additional=False, conditional=0)
        return categories[key]

    for key in generation.get('categories', {}):
        category(key)
    from amr_demand_schedule import rules as configured_rules
    for rule in configured_rules(generation, preview['frozen_inputs'].get('departments', [])):
        row = category(rule.category)
        note = str(rule.settings.get('notes', '') or '').strip()
        if note and note != row['notes'] and note not in row['scope_notes']:
            row['scope_notes'].append(note)
    for rule in preview['rules']:
        row = category(rule['category'])
        if rule.get('status') != 'inactive':
            row['additional'] |= rule.get('total_demand') is None
        note = str(rule.get('effective_config', {}).get('notes', '') or '').strip()
        if note and note != row['notes'] and note not in row['scope_notes']:
            row['scope_notes'].append(note)
    for task in preview['tasks']:
        when = datetime.fromisoformat(task['release_datetime'])
        if when.date() != selected:
            continue
        row = category(task['category'])
        row['trips'] += 1
        row['quantity'] += float(task.get('quantity', 1))
        row['bins'][min(95, (when.hour*60 + when.minute)//15)] += 1
        row['conditional'] += task.get('timing', '').startswith('Conditional')
    bins = [sum(row['bins'][index] for row in categories.values()) for index in range(96)]
    return dict(date=selected.isoformat(), source=source, categories=list(categories.values()), bins=bins,
        trips=sum(bins), quantity=sum(row['quantity'] for row in categories.values()),
        conditional=sum(row['conditional'] for row in categories.values()),
        additional=any(row['additional'] for row in categories.values()),
        period_start=preview['start_datetime'], period_end=preview['end_datetime'],
        explanation='Each planned transport request counts as one trip. Load units are shown separately. '
                    'Return journeys and on-demand work may add trips; fleet batching and resource waits can change actual journeys.')


STACK_COLORS = ('#3569aa', '#d47a24', '#318979', '#875aa8', '#c74f5a', '#697787', '#9b8935', '#497e9d')


def stacked_bins(preview, interval=60):
    if interval not in (15,30,60):
        raise ValueError('Choose 15, 30 or 60-minute intervals.')
    size=interval//15
    series=[dict(key=row['key'],label=row['label'],color=STACK_COLORS[index%len(STACK_COLORS)],
                 total=row['trips'],bins=[sum(row['bins'][i:i+size]) for i in range(0,96,size)])
            for index,row in enumerate(preview['categories'])]
    totals=[sum(row['bins'][i] for row in series) for i in range(1440//interval)]
    return series,totals


def chart_scale(totals):
    import math
    maximum=max(1,max(totals,default=0))
    power=10**max(0,math.floor(math.log10(max(1,maximum/5))))
    step=next(value*power for value in (1,2,5,10) if value*power>=maximum/5)
    return step,int(math.ceil(maximum/step)*step)


def write_preview_pdf(path, preview, interval=60):
    """Landscape stacked bar chart followed by complete category notes."""
    from pathlib import Path
    from xml.sax.saxutils import escape
    from reportlab.graphics.shapes import Drawing, Line, Rect, String
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, TableStyle, Spacer
    import reportlab

    font='DayTripPreview'
    font_path=Path('C:/Windows/Fonts/arial.ttf')
    if not font_path.exists():font_path=Path(reportlab.__file__).parent/'fonts/Vera.ttf'
    if font not in pdfmetrics.getRegisteredFontNames():pdfmetrics.registerFont(TTFont(font,str(font_path)))
    page_width,page_height=landscape(A4)
    width=page_width-64
    style=ParagraphStyle('DayTripText',fontName=font,fontSize=9,leading=12,splitLongWords=True)
    paragraph=lambda text:Paragraph(escape(str(text)).replace('\n','<br/>'),style)
    series,totals=stacked_bins(preview,interval)
    step,maximum=chart_scale(totals)
    legend=[]
    x,y=45,24
    for row in series:
        label=f"{row['label']} ({row['total']})"
        item_width=pdfmetrics.stringWidth(label,font,8)+27
        if x+item_width>width-5:x,y=45,y-17
        legend.append((x,y,row,label))
        x+=item_width
    legend_extra=max(0,24-y)
    height=242+legend_extra
    bottom=60+legend_extra
    top=height-24
    drawing=Drawing(width,height)
    for x,y,row,label in legend:
        y+=legend_extra
        drawing.add(Rect(x,y-1,9,9,fillColor=colors.HexColor(row['color']),strokeColor=None))
        drawing.add(String(x+14,y,label,fontName=font,fontSize=8))
    drawing.add(String(0,top+9,'Trips',fontName=font,fontSize=9))
    for count in range(0,maximum+1,step):
        y=bottom+(top-bottom)*count/maximum
        drawing.add(Line(40,y,width-5,y,strokeColor=colors.HexColor('#d6dce1'),strokeWidth=.4))
        drawing.add(String(33,y-3,str(count),fontName=font,fontSize=8,textAnchor='end'))
    chart_width=width-50
    for hour in range(0,25,2):
        x=45+chart_width*hour/24
        drawing.add(String(x,bottom-16,f'{hour:02d}:00',fontName=font,fontSize=8,
                           textAnchor='start' if hour==0 else 'end' if hour==24 else 'middle'))
    bar_width=chart_width/len(totals)
    for index,total in enumerate(totals):
        if not total:continue
        x=45+index*bar_width+bar_width*.14
        accumulated=0
        for row in series:
            value=row['bins'][index]
            if not value:continue
            y=bottom+(top-bottom)*accumulated/maximum
            drawing.add(Rect(x,y,bar_width*.72,(top-bottom)*value/maximum,
                             fillColor=colors.HexColor(row['color']),strokeColor=None))
            accumulated+=value
        if pdfmetrics.stringWidth(str(total),font,7)<bar_width:
            drawing.add(String(x+bar_width*.36,bottom+(top-bottom)*total/maximum+3,str(total),
                               fontName=font,fontSize=7,textAnchor='middle'))
    data=[[paragraph('Category'),paragraph('Planned trips'),paragraph('Configuration notes')]]
    for row in preview['categories']:
        notes=([row['notes']] if row['notes'] else [])+row['scope_notes']
        data.append([paragraph(row['label']),paragraph(str(row['trips'])+(' + variable' if row['additional'] else '')),
                     paragraph('\n'.join(notes) or 'No notes')])
    table=LongTable(data,colWidths=[140,90,width-230],repeatRows=1,splitInRow=1)
    table.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#edf2f6')),('VALIGN',(0,0),(-1,-1),'TOP'),
        ('BOTTOMPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),7),
        ('LINEBELOW',(0,0),(-1,-1),.4,colors.HexColor('#d6dce1'))]))

    def header(canvas,doc):
        canvas.setFont(font,15)
        canvas.drawString(32,page_height-29,f"Demand preview - {preview['date']}")
        canvas.setFont(font,9)
        canvas.drawString(32,page_height-45,
            f"{preview['source']} | {preview['trips']} planned trips | 00:00-24:00 | {interval}-minute stacked bars")
        canvas.setFont(font,7)
        canvas.drawString(32,22,'Planned requests; return journeys and on-demand work may add trips. Actual fleet journeys can differ.')
        canvas.drawRightString(page_width-32,22,f'Page {doc.page}')

    SimpleDocTemplate(str(path),pagesize=landscape(A4),leftMargin=32,rightMargin=32,
        topMargin=62,bottomMargin=38,title='Daily demand preview').build([drawing,Spacer(1,12),table],
                                                                     onFirstPage=header,onLaterPages=header)
