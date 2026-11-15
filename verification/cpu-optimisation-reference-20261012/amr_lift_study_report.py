"""Readable comparison PDF, separate from existing frozen-run reports."""
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4,landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak
from xml.sax.saxutils import escape


def export_pdf(state,path):
    styles=getSampleStyleSheet();story=[]
    def text(s,style='BodyText'):return Paragraph(escape(str(s)),styles[style])
    story += [text('Lift location comparison','Title'),Spacer(1,12),text(state.get('explanation','Evaluation not complete.')),
        text('Source identity: '+state['source_identity']['config_hash']),
        text('Fixed request schedules, equipment and flow permissions. Targetless baseline requests receive a 10-minute study target. '
             'Geometrically screened sites require structural review. Washing services AMRs; contamination is not simulated.'),Spacer(1,12)]
    ranking=[['Layout','Service guard','Worst on-time','Distance change (m)','Wait change (s)']]
    for row in state.get('ranking',[]):ranking.append([row['id'],'Eligible' if row['eligible'] else 'Tradeoff',f"{row['worst_service']:.1%}",
        f"{row['distance_change_m']:.1f}",f"{row['wait_change_sec']:.1f}"])
    def table(rows,widths):
        t=Table([[text(c) for c in row] for row in rows],colWidths=widths,repeatRows=1,hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#dae5f4')),
            ('GRID',(0,0),(-1,-1),.4,colors.HexColor('#b0c1d9')),('VALIGN',(0,0),(-1,-1),'TOP'),
            ('LEFTPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]));return t
    story.append(table(ranking,[110,120,110,170,170]))
    for layout,runs in state.get('results',{}).items():
        story += [PageBreak(),text(layout,'Heading1')]
        rows=[['Scenario','Floor / flow','Completed / requests','Failed / pending','On-time','Horizontal (m)','Lift wait (s)']]
        for scenario,run in runs.items():
            m=run['metrics']
            for key,g in m['groups'].items():rows.append([scenario,key,f"{g['completed']} / {g['requests']}",
                f"{g['failed']} / {g['pending']}",f"{g['on_time_rate']:.1%}" if g['on_time_rate'] is not None else 'No target',
                f"{m['horizontal_m']:.1f}",f"{m['lift_wait_sec']:.1f}"])
        story.append(table(rows,[135,105,105,95,75,80,85]))
        story.append(Spacer(1,10));story.append(text('Horizontal totals include empty and loaded movement once per recorded segment. '
            'Service is grouped by department floor when available; destination floors are retained in CSV. '
            'Pending at stop is distinct from failed work. Detailed run identities and events remain in the study companion and run folders.'))
    def footer(canvas,doc):
        canvas.saveState();canvas.setFont('Helvetica',8);canvas.drawString(36,20,'AMR Simulator — frozen lift-study evidence');canvas.drawRightString(805,20,str(doc.page));canvas.restoreState()
    SimpleDocTemplate(str(path),pagesize=landscape(A4),leftMargin=36,rightMargin=36,topMargin=36,bottomMargin=36).build(story,onFirstPage=footer,onLaterPages=footer)
