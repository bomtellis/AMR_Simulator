"""Human contingency CSVs and a reusable section for the existing PDF report."""
import csv
from datetime import datetime, timedelta
from pathlib import Path
from xml.sax.saxutils import escape

from amr_contingency_study import load_study, VARIANTS


def clock(state, seconds):
    if seconds is None:
        return ''
    return (datetime.fromisoformat(state['configuration']['simulation']['start_datetime'])+
            timedelta(seconds=seconds)).strftime('%Y-%m-%d %H:%M:%S')


def export_csvs(path, directory):
    state = load_study(path)
    directory = Path(directory);directory.mkdir(parents=True, exist_ok=True)
    outputs = []
    for name, record in state['variants'].items():
        result = record['best'] or record['current']
        if result is None:
            continue
        exports={kind:result[kind] for kind in ('roster','rounds','stops','tasks','unresolved')}
        exports['services']=[dict(service=k,**v) for k,v in result.get('services',{}).items()]
        exports['summary']=[{k:v for k,v in result.items() if isinstance(v,(int,float,str,bool))}]
        if record.get('diagnostics'):
            exports['diagnostics']=[dict(reason=message) for message in record['diagnostics']]
        for kind,rows in exports.items():
            target=directory/f'{name}_{kind}.csv'
            with target.open('w',newline='',encoding='utf-8-sig') as stream:
                fields=list(dict.fromkeys(k for row in rows for k in row))
                writer=csv.DictWriter(stream,fieldnames=fields)
                writer.writeheader()
                for row in rows:
                    values={k:('; '.join(map(str,v)) if isinstance(v,list) else v) for k,v in row.items()}
                    for key in ('start','end','release','deadline','completed','original_release','original_deadline',
                                'latest_allowed_release','planning_release','planning_deadline'):
                        if key in values:
                            values[key]=clock(state,values[key])
                    # Prevent spreadsheet formula execution in user-controlled labels.
                    writer.writerow({k:("'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v) for k,v in values.items()})
            outputs.append(target)
    return outputs


def append_contingency_story(story, state, styles):
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle, CondPageBreak
    from reportlab.lib import colors
    def text(value, style='BodyText'):
        return Paragraph(escape(str(value)),styles[style])
    def table(rows, widths):
        t=Table([[text(v) for v in row] for row in rows], colWidths=widths,repeatRows=1,hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e8eef4')),
            ('VALIGN',(0,0),(-1,-1),'TOP'),('BOTTOMPADDING',(0,0),(-1,-1),6),
            ('LINEBELOW',(0,0),(-1,0),.5,colors.grey)]))
        story.extend([t,Spacer(1,12)])
    story.append(text('Human contingency study','Heading1'))
    story.append(text('Lowest staffed-hours passing rosters found; these are bounded search results, not proven global minima. '
                      f"Study status: {state['status']}. Buffered walking and handling: +{state['settings']['buffer_percent']:g}%.") )
    for service in state['settings']['services']:
        policy=state['settings']['profiles'][service].get('release_policy',{})
        if policy.get('mode')=='staff_aligned':
            story.append(text(f"{service}: flexible transport releases and deadlines may move together by up to "
                f"{policy['max_delay_minutes']:g} minutes to match staffing. Scheduled and explicit tasks stay fixed. "
                'Demand and stock consumption remain on the original clock.'))
    for message in dict.fromkeys(v for record in state['variants'].values() for v in record.get('diagnostics',[])):
        story.append(text(message))
    summary=[['Arrangement / timing','Search','People at peak','Staffed hours','Trips']]
    for name in VARIANTS:
        record=state['variants'].get(name,{})
        result=record.get('best')
        summary.append([name.replace('_',' / '),record.get('status','Not evaluated'),
            result['peak_people'] if result else 'No passing roster',
            f"{result['staffed_hours']:.2f}" if result else '—',result['trips'] if result else '—'])
    table(summary,[135,105,95,80,65])
    for name,record in state['variants'].items():
        result=record['best'] or record['current']
        if result is None:continue
        story.append(CondPageBreak(190))
        story.append(text(name.replace('_',' / '),'Heading2'))
        story.append(text(f"Trials: {record['trials']}. Completed obligations: {result['completed']} / {result['obligations']}. "
                          f"Active hours: {result['active_hours']:.2f}; breaks: {result['break_hours']:.2f}; "
                          f"lift waiting: {result['lift_wait_hours']:.2f}."))
        story.append(text(f"Tasks with revised deadlines: {result.get('retimed_tasks',0)}; "
            f"largest deadline delay: {result.get('maximum_deadline_delay_minutes',0):g} minutes. "
            'Original and revised task times are available in the task CSV and Task timing view.'))
        grouped={}
        for r in result['roster']:
            key=(r['pool'],clock(state,r['start']),clock(state,r['end']))
            grouped[key]=grouped.get(key,0)+1
        table([['Team','Shift start','Shift end','People']]+[[*k,v] for k,v in sorted(grouped.items())], [110,155,155,60])
        table([['Service','Active hours','Rounds','Completed']]+[
            [service,f"{values['active_hours']:.2f}",values['trips'],values['completed']]
            for service,values in result.get('services',{}).items()], [200,100,80,100])
        if name.startswith('dedicated'):
            table([['Independent category team','People at peak','Staffed hours']]+[
                [service,values.get('peak_people',0),f"{values.get('staffed_hours',0):.2f}"]
                for service,values in result.get('services',{}).items()], [240,120,120])
        for issue in result['unresolved'][:12]:
            story.append(text(f"{issue['service']} / {issue['task']}: {issue['reason']}"))
    story.append(text('One person per carrying unit; equipment availability assumed. Staff numbers describe shift coverage, '
                      'not total employed establishment. Each round contains one service. Additional passenger demand is not inferred.'))
    story.append(text('Workload identity: '+state['workload_sha256']))


def export_pdf(path, output):
    from reportlab.platypus import SimpleDocTemplate
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.pagesizes import A4
    story=[]
    append_contingency_story(story,load_study(path),getSampleStyleSheet())
    SimpleDocTemplate(str(output),pagesize=A4,leftMargin=48,rightMargin=48,topMargin=42,bottomMargin=42).build(story)


def collect_contingency_report(path, config):
    if not path:
        raise ValueError('Select a human contingency study for the PDF.')
    return load_study(path,config)
