"""Add a readable decision summary to the simulator's verified full report."""
import json
import sys
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from amr_project_runs import read_json, write_json
from amr_run_evidence import file_hash
from amr_stress_report import verify_stress_sources
from pypdf import PdfReader, PdfWriter
from pypdf.annotations import Link
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.pdfgen import canvas

OUT = ROOT / 'output/pdf/ltn-amr-speed-sweep-2026-10-14'
STUDY = ROOT / 'LTN AMR speed sweep 2026-10-14.stress.json'
manifest = read_json(OUT / 'report_manifest.json')
assert manifest['status'] == 'complete'
assert file_hash(OUT / 'report.pdf') == manifest['pdf_sha256']
assert file_hash(OUT / 'stress_test_comparison.json') == manifest['stress_comparison_sha256']
verify_stress_sources(manifest['stress_tests'])
state = read_json(STUDY)
assert state['status'] == 'complete' and state['speed_sweep']['complete']
records = {100 if r['kind'] == 'baseline' else round(r['events'][0]['speed_factor'] * 100): r
           for r in state['results'].values()}
assert set(records) == set(range(5, 101, 5))
lowest = min(p for p, r in records.items() if r['metrics']['passed'])
failures = [p for p, r in records.items() if not r['metrics']['passed']]
highest_failure = max(failures, default=None)
continuous_floor = highest_failure + 5 if highest_failure is not None else 5
baseline = records[100]['metrics']
chosen = records[lowest]['metrics']
provenance = read_json(ROOT / 'verification/ltn-amr-speed-sweep-source.json')

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name='SummaryTitle', fontName='Helvetica-Bold', fontSize=22, leading=26,
                         textColor=colors.HexColor('#18354A'), spaceAfter=8))
styles.add(ParagraphStyle(name='SummaryBody', fontName='Helvetica', fontSize=9, leading=12, spaceAfter=7))
styles.add(ParagraphStyle(name='SummarySmall', fontName='Helvetica', fontSize=7.5, leading=10,
                         textColor=colors.HexColor('#475569'), spaceAfter=5))
styles.add(ParagraphStyle(name='SummaryHeading', fontName='Helvetica-Bold', fontSize=11, leading=14,
                         textColor=colors.HexColor('#18354A'), spaceBefore=9, spaceAfter=6))
styles.add(ParagraphStyle(name='SummaryCell', fontName='Helvetica', fontSize=8, leading=10))


def p(text, style='SummaryBody'):
    return Paragraph(text, styles[style])


def duration(seconds):
    hours, minutes = divmod(round(seconds / 60), 60)
    return f'{hours}h {minutes:02d}m'


def table(rows, widths):
    item = Table([[p(escape(str(cell)), 'SummaryCell') for cell in row] for row in rows],
                 colWidths=widths, repeatRows=1, hAlign='LEFT')
    item.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#DFEAF1')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F5F8FA')]),
        ('LINEBELOW', (0, 0), (-1, 0), .5, colors.HexColor('#94A3B8')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6), ('TOPPADDING', (0, 0), (-1, -1), 6),
    ]))
    return item


story = [p('LTN AMR speed sweep', 'SummaryTitle'),
         p('Decision summary | Saved model: ltn.amrproj | 14 October 2026', 'SummarySmall'),
         p(f'<b>Lowest tested passing fleet speed: {lowest}% of configured speed.</b>')]
if lowest < continuous_floor:
    story.append(p(f'<b>The results are not monotonic.</b> Although {lowest}% passed, higher tested levels failed. '
                   f'All tested levels from <b>{continuous_floor}% through 100%</b> passed. '
                   'Use that distinction when interpreting the slowest observed pass; it is not a continuous speed threshold.'))
else:
    story.append(p(f'All tested levels from <b>{lowest}% through 100%</b> passed. '
                   + (f'The next lower level, {lowest - 5}%, failed.' if lowest > 5
                      else 'Speeds below 5% were not tested.')))
story.append(p(f'At {lowest}%, all <b>{len(baseline["obligations"]):,} service obligations</b> were met, '
               f'with {chosen["failed"]} failed and {chosen["pending"]} pending tasks. '
               f'The last completion was <b>{duration(chosen["latest_completion_sec"])}</b> after the simulation start '
               f'(normal operation: {duration(baseline["latest_completion_sec"])}).'))
story.append(p('Test scope and pass criterion', 'SummaryHeading'))
sim = state['config']['simulation']
story.append(p(f'All 22 AMRs were slowed together: 100% baseline, then 95%, 90%, and every 5 percentage points down to 5%. '
               f'Demand ran from {escape(sim["start_datetime"].replace("T", " "))} to '
               f'{escape(sim["end_datetime"].replace("T", " "))} (168 hours). '
               'The slowdown remained active until outstanding work finished; lifts retained their normal settings.'))
story.append(p(f'Passing requires all baseline service obligations to be met, with no failed or pending tasks, under the existing '
               f'<b>{sim.get("max_task_deferral_minutes", 60):g}-minute assignment-deferral limit</b>. '
               '<b>Completion after the 168-hour demand window is allowed.</b> This result therefore does not establish an on-time-delivery SLA.'))
story.append(p(f'Uncongested AMR travel speeds at the {lowest}% passing level', 'SummaryHeading'))
fleet_rows = [['AMR configuration', 'Quantity', 'Configured m/s', f'At {lowest}% (m/s)']]
for amr in state['config']['amrs']:
    speed = float(amr['speed_m_per_sec'])
    fleet_rows.append([amr['id'], amr.get('quantity', 1), f'{speed:g}', f'{speed * lowest / 100:.3f}'])
story.append(table(fleet_rows, [166, 64, 118, 157]))
story.append(p('Key comparisons', 'SummaryHeading'))
selected = {100, lowest, continuous_floor}
if highest_failure is not None:
    selected.add(highest_failure)
if lowest > 5:
    selected.add(lowest - 5)
rows = [['Speed', 'Outcome', 'Unmet', 'Failed', 'Added delay (h)', 'Last finish']]
for speed in sorted(selected, reverse=True):
    m = records[speed]['metrics']
    rows.append([f'{speed}%', 'PASS' if m['passed'] else 'FAIL', m['unmet_count'], m['failed'],
                 f'{m["added_delay_sec"] / 3600:,.1f}', duration(m['latest_completion_sec'])])
story.append(table(rows, [48, 62, 49, 49, 135, 162]))
story.append(Spacer(1, 6))
story.append(p('Added delay is the sum of positive completion-time differences for completed services; it excludes unfinished work. '
               'Last finish is elapsed simulation time. The full verified comparison of all 20 runs and individual trial details follows.', 'SummarySmall'))
story.append(p('<b>Reading unmet counts:</b> These combine unfinished trial obligations, missing expected returns, and baseline '
               'obligations that are missing or have changed service details. They are comparison counts, not unique missed orders '
               'or percentages of the baseline total.', 'SummarySmall'))
story.append(p(f'Source revision: {escape(provenance["revision"]["id"])}. '
               'Reduced data was used for all slowdown trials. The configured model and demand were held fixed.', 'SummarySmall'))

temporary = ROOT / 'tmp/pdfs/ltn-speed-executive-summary.pdf'
temporary.parent.mkdir(parents=True, exist_ok=True)
SimpleDocTemplate(str(temporary), pagesize=A4, leftMargin=45, rightMargin=45,
                  topMargin=38, bottomMargin=36, title='LTN AMR speed sweep - decision summary').build(story)
final = OUT / 'ltn-amr-speed-sweep.pdf'
source_reader = PdfReader(OUT / 'report.pdf')
source_text = [' '.join(page.extract_text().split()) for page in source_reader.pages]
assert 'Contents' in source_text[1]
assert len(PdfReader(temporary).pages) == 1


def source_page(heading):
    matches = [index + 1 for index, text in enumerate(source_text) if index >= 2 and heading in text]
    assert len(matches) == 1, (heading, matches)
    return matches[0]


entries = [('Decision summary', 1, 0), ('Full speed comparison', 3, 0),
           ('Individual trial results', source_page('1.3 Selected trial results'), 0)]
for rank, speed in enumerate(range(95, 0, -5), 1):
    entries.append((f'All AMRs at {speed}% speed',
                    source_page(f'1.3.{rank} All AMRs at {speed}% speed'), 1))
contents_path = temporary.with_name('ltn-speed-contents.pdf')
contents = canvas.Canvas(str(contents_path), pagesize=A4)
width, height = A4
contents.setFillColor(colors.HexColor('#18354A'))
contents.setFont('Helvetica-Bold', 22)
contents.drawString(48, height - 65, 'Contents')
contents.setFont('Helvetica', 9)
contents.drawString(48, height - 86, 'Decision summary and complete verified speed-sweep results')
y = height - 125
links = []
for title, target, level in entries:
    x = 48 + level * 16
    contents.setFont('Helvetica' if level else 'Helvetica-Bold', 10)
    contents.drawString(x, y, title)
    contents.drawRightString(width - 48, y, str(target))
    links.append(((x, y - 4, width - 45, y + 13), target - 1))
    y -= 23 if level else 29
assert y > 60
contents.setFillColor(colors.HexColor('#64748B'))
contents.setFont('Helvetica', 8)
contents.drawRightString(width - 48, 28, 'Page 2')
contents.save()

# Replace the original cover and overflowing contents, retaining every data
# page and its printed page number. Rebuild navigation against the final PDF.
writer = PdfWriter()
writer.add_page(PdfReader(temporary).pages[0])
writer.add_page(PdfReader(contents_path).pages[0])
for page in source_reader.pages[2:]:
    writer.add_page(page, excluded_keys=['/Annots'])
for rect, target in links:
    writer.add_annotation(1, Link(rect=rect, target_page_index=target))
    writer.pages[1]['/Annots'][-1].get_object()['/Dest'][0] = writer.pages[target].indirect_reference
parent = None
for title, target, level in entries:
    item = writer.add_outline_item(title, target - 1, parent=parent if level else None)
    if title == 'Individual trial results':
        parent = item
writer.add_metadata({'/Title': 'LTN AMR speed sweep - findings and verified results'})
with final.open('wb') as stream:
    writer.write(stream)
final_reader = PdfReader(final)
assert len(final_reader.pages) == len(source_reader.pages)
assert len(final_reader.pages[1]['/Annots']) == len(entries)
assert [' '.join(page.extract_text().split()) for page in final_reader.pages[2:]] == source_text[2:]
page_refs = {page.indirect_reference.idnum: index for index, page in enumerate(final_reader.pages)}
for annotation, (_, target) in zip(final_reader.pages[1]['/Annots'], links):
    destination = annotation.get_object()['/Dest'][0]
    assert page_refs[destination.idnum] == target
verify_stress_sources(manifest['stress_tests'])
assert file_hash(OUT / 'report.pdf') == manifest['pdf_sha256']
write_json(OUT / 'executive_summary_manifest.json', dict(status='complete',
    study_sha256=file_hash(STUDY), verified_report_sha256=manifest['pdf_sha256'],
    final_pdf_sha256=file_hash(final), lowest_passing_percent=lowest,
    continuous_passing_floor_percent=continuous_floor, highest_failing_percent=highest_failure,
    navigation_links_verified=len(links), original_data_pages_preserved=True,
    summary_pages=len(PdfReader(temporary).pages), total_pages=len(PdfReader(final).pages)))
print(json.dumps(dict(pdf=str(final), lowest=lowest, continuous_floor=continuous_floor,
                     highest_failure=highest_failure, pages=len(PdfReader(final).pages))))
