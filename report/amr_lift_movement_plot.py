"""Vector stacked movement charts for the optional per-lift PDF section."""
import math
from html import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import Flowable, Paragraph, PageBreak, Spacer

from amr_lift_movement_charts import build_chart_data, selected_charts


class LiftMovementStackedChart(Flowable):
    def __init__(self, chart, width, height, interval_minutes=30, relative=False):
        super().__init__()
        self.chart, self.width, self.height = chart, width, height
        self.interval_minutes, self.relative = interval_minutes, relative

    def wrap(self, width, height):
        self.width = min(self.width, width)
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.saveState()
        c.setFillColor(colors.white)
        c.rect(0, 0, self.width, self.height, fill=1, stroke=0)
        left, bottom = 23*mm, 20*mm
        plot_width = self.width-left-5*mm
        # Wrap the legend independently of the plot and retain stable colours.
        x, y = left, self.height-12
        for series in self.chart['series']:
            label = series['label']
            while stringWidth(label, 'Helvetica', 9) > plot_width-18 and len(label)>4:
                label = label[:-4]+'...'
            size = stringWidth(label,'Helvetica',9)+28
            if x+size > left+plot_width and x>left:
                x, y = left, y-18
            c.setFillColor(colors.HexColor(series['colour']))
            c.rect(x,y-1,9,9,fill=1,stroke=0)
            c.setFillColor(colors.HexColor('#243746'))
            c.setFont('Helvetica',9)
            c.drawString(x+14,y,label)
            x += size
        top = y-24
        plot_height = max(20*mm,top-bottom)
        count = len(self.chart['labels'])
        totals = [sum(s['values'][i] for s in self.chart['series']) for i in range(count)]
        maximum = max(totals,default=0)
        scale_peak = self.chart.get('scale_peak',maximum)
        step = max(1,math.ceil(scale_peak/5))
        ceiling = max(1,math.ceil(scale_peak/step)*step)
        c.setFont('Helvetica',8)
        for tick in range(0,ceiling+1,step):
            yy = bottom+plot_height*tick/ceiling
            c.setStrokeColor(colors.HexColor('#E3E9EF'));c.setLineWidth(.5)
            c.line(left,yy,left+plot_width,yy)
            c.setFillColor(colors.HexColor('#526777'))
            c.drawRightString(left-6,yy-3,str(tick))
        bar_step = plot_width/max(1,count)
        for i in range(count):
            accumulated = 0
            for series in self.chart['series']:
                value = series['values'][i]
                if value:
                    c.setFillColor(colors.HexColor(series['colour']))
                    c.rect(left+i*bar_step+bar_step*.1,bottom+accumulated/ceiling*plot_height,
                           bar_step*.8,value/ceiling*plot_height,fill=1,stroke=0)
                accumulated += value
        c.setStrokeColor(colors.HexColor('#526777'));c.setLineWidth(.7)
        c.line(left,bottom,left+plot_width,bottom)
        c.line(left,bottom,left,bottom+plot_height)
        c.setFillColor(colors.HexColor('#526777'));c.setFont('Helvetica',8)
        every = max(1,120//self.interval_minutes)
        for i,label in enumerate(self.chart['labels']):
            if i%every==0 or i==count-1:
                c.drawCentredString(left+(i+.5)*bar_step,bottom-14,label)
        c.setFont('Helvetica-Bold',9)
        c.drawCentredString(left+plot_width/2,bottom-32,
            'Time within simulation day' if self.relative else 'Time of day')
        c.saveState();c.translate(12,bottom+plot_height/2);c.rotate(90)
        c.drawCentredString(0,0,f'Movements per {self.interval_minutes} minutes');c.restoreState()
        if maximum==0:
            c.setFont('Helvetica',11)
            c.drawCentredString(left+plot_width/2,bottom+plot_height/2,'No recorded movements for this selection.')
        c.restoreState()


def pdf_chart_selections(data, day=None, include_reposition=True, lift_ids=None, daily=False):
    """Keep PDF selection separate from the unchanged Excel count model."""
    requested = set(lift_ids or ())
    missing = requested - set(data['lifts'])
    if missing:
        raise ValueError('PDF chart lift not found in this run: '+', '.join(sorted(missing)))
    # Validate a supplied day even when the run has no recorded observation days.
    combined = selected_charts(data,day,include_reposition)
    days = data['days'] if daily and day in (None,'','All days') else [day]
    by_day = [selected_charts(data,value,include_reposition) for value in days] if daily else [combined]
    charts = [chart for identity in data['lifts'] if not requested or identity in requested
              for values in by_day for chart in values if chart['lift_id']==identity]
    if daily:
        peaks = {}
        for chart in charts:
            peak = max((sum(s['values'][i] for s in chart['series']) for i in range(len(chart['labels']))),default=0)
            peaks[chart['lift_id']] = max(peaks.get(chart['lift_id'],0),peak)
        for chart in charts:
            chart['scale_peak'] = peaks[chart['lift_id']]
    return charts


def append_stacked_charts(story, results, styles, doc, *, config=None, day=None,
                          interval_minutes=30, include_reposition=True, lift_ids=None, daily=False):
    data = results.get('lift_movement_chart_data')
    if data is None:
        data = build_chart_data(results.get('lift_movement_detail'),config,interval_minutes)
    charts = pdf_chart_selections(data,day,include_reposition,lift_ids,daily)
    title = 'Lift movements by purpose - daily charts' if daily else 'Lift movements by purpose - stacked bars'
    story.append(Paragraph(title,styles['Section']))
    scope = ('Each observation day separately' if daily and day in (None,'','All days') else day or
             ('All days combined by clock time' if data['day_mode']=='calendar' else 'All simulation days combined'))
    note = data['note']
    if daily:
        note = note.replace('All days combines '+
            ('clock-time bins' if data['day_mode']=='calendar' else 'time bins within each simulation day')+
            ', without averaging.','Dates are shown separately, including days with no movements. '
            'Charts for the same lift share a vertical scale for comparison.')
    story.append(Paragraph('Day selection: '+escape(scope)+'. '+escape(note)+
        (' Empty lift repositioning is included.' if include_reposition else ' Empty lift repositioning is excluded.'),styles['BodyText']))
    if data['days']:
        story.append(Paragraph('Observation days: '+escape(data['days'][0])+' to '+escape(data['days'][-1])+'.',styles['BodyText']))
    if lift_ids:
        story.append(Paragraph('Selected lifts: '+escape(', '.join(lift_ids))+'.',styles['BodyText']))
    if not charts:
        story.append(Paragraph('No lift charts were available for the selected observation days.',styles['BodyText']))
    width = landscape(A3)[0]-doc.leftMargin-doc.rightMargin
    for index,chart in enumerate(charts):
        if index:
            story.append(PageBreak())
        story.append(Spacer(1,8))
        story.append(Paragraph(escape(chart['lift_id'])+' - '+escape(chart['day'])+
            f" ({chart['total']:,} movements)",styles['Heading3']))
        story.append(LiftMovementStackedChart(chart,width,165*mm,interval_minutes,data['day_mode']=='relative'))
