"""Render the fully verified saved study as a small, standalone executive summary."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'report'))
from amr_stress_report import verify_stress_sources
from amr_run_evidence import file_hash
from amr_report_stress import append_impact_summary
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak


if __name__ == '__main__':
    verified_path = ROOT / 'verification' / 'lift-shutdown-verified.json'
    verified = json.loads(verified_path.read_text(encoding='utf-8'))
    study = verified['snapshot']['studies'][0]
    target = ROOT / 'output' / 'pdf' / 'lift-shutdown-impact'
    target.mkdir(parents=True, exist_ok=True)
    pdf = target / 'lift-shutdown-impact.pdf'
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle('Small', parent=styles['BodyText'], fontSize=8, leading=10))
    styles['BodyText'].fontSize = 10
    styles['BodyText'].leading = 14
    styles['Heading2'].textColor = colors.HexColor('#17365D')
    story = [Paragraph('Lift shutdown impact', styles['Title']),
        Paragraph('All 8 single-lift shutdowns and all 28 pairs | Seven-day outage study', styles['Heading2']),
        Paragraph('Lift stress study: 1 January 2026, 05:00 to 8 January 2026, 05:00. '
                  'All 36 saved trials were checked against their underlying run evidence. '
                  'The normal-operation baseline met all 3,422 service obligations. '
                  'Both failing pairs missed the same return obligation: return:GEN_STORES_D24_01109.', styles['BodyText']),
        Spacer(1, 5*mm)]
    append_impact_summary(story, study, styles)
    if isinstance(story[-1], PageBreak):
        story.pop()
    story.append(Spacer(1, 4*mm))
    story.append(Paragraph('Source: Lift stress.stress.json. Baseline: ' + study['baseline']['metrics']['run_key'] +
        '. Prepared 14 October 2026. The accompanying JSON contains trial IDs, run references and evidence checksums. '
        'These are results for the saved model and shutdown windows; no additional simulations were run.', styles['Small']))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.HexColor('#536477'))
        canvas.drawString(18*mm, 10*mm, 'AMR simulator | Lift shutdown impact')
        canvas.drawRightString(279*mm, 10*mm, str(doc.page))
        canvas.restoreState()

    SimpleDocTemplate(str(pdf), pagesize=landscape(A4), leftMargin=18*mm, rightMargin=18*mm,
        topMargin=15*mm, bottomMargin=17*mm, title='Lift shutdown impact', author='AMR Simulator').build(
            story, onFirstPage=footer, onLaterPages=footer)
    verify_stress_sources(verified['evidence'])
    (target / 'verified_comparison.json').write_text(json.dumps(verified, indent=2), encoding='utf-8')
    (target / 'summary_manifest.json').write_text(json.dumps(dict(status='complete',
        pdf_sha256=file_hash(pdf), verified_comparison_sha256=file_hash(target / 'verified_comparison.json'),
        summary_code_sha256=file_hash(ROOT / 'report' / 'amr_report_stress.py')), indent=2), encoding='utf-8')
    print(pdf, flush=True)
