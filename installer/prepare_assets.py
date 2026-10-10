"""Generate the shipped practice inputs and help from tracked current source."""
from pathlib import Path
import argparse
import json
import shutil
import sys
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'visualiser'))


def quick_start(output, include_ltn):
    from visualiser.quick_start import EXERCISES, REFERENCE
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak

    output.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / 'docs/quick-start/small-map.json', output / 'small-map.json')
    styles = getSampleStyleSheet()
    styles['BodyText'].leading = 15
    story, markdown = [], []

    def paragraph(text, style='BodyText'):
        text = text.replace('\u2192', ' > ').replace('\u2013', '-').replace('\u2014', '-')
        story.append(Paragraph(escape(text), styles[style]))
        story.append(Spacer(1, 8))
        markdown.append(text + '\n')

    paragraph('AMR Simulator quick start', 'Title')
    paragraph('Start with Help > Building flow tutorial for the current 12-part '
              'three-floor course, or use the small-map exercise below. '
              'Projects and simulation results run locally on your computer.')
    paragraph('Install or extract the application, then open AMRSimulator.exe. '
              'Save your working projects and results outside the application folder.')
    for index, exercise in enumerate(EXERCISES):
        if index == 1 and not include_ltn:
            continue
        paragraph(exercise['title'], 'Heading1')
        for step, (title, action, outcome, _) in enumerate(exercise['steps'], 1):
            paragraph(f'{step}. {title}', 'Heading2')
            paragraph(action)
            paragraph('Expected result: ' + outcome)
        story.append(PageBreak())
    if not include_ltn:
        paragraph('Optional LTN exercise', 'Heading1')
        paragraph('The walkthrough also lists a supplied LTN project. That separate '
                  'project is not included in this public package. Use the small map '
                  'or the fully bundled Building flow tutorial instead.')
    paragraph('Controls reference', 'Heading1')
    for title, body in REFERENCE:
        paragraph(title, 'Heading2')
        paragraph(body)

    def footer(canvas, doc):
        canvas.setFont('Helvetica', 8)
        canvas.drawString(45, 20, 'AMR Simulator | Quick start')
        canvas.drawRightString(550, 20, str(doc.page))

    SimpleDocTemplate(str(output / 'AMR-Simulator-Quick-Start.pdf'), pagesize=A4,
                      title='AMR Simulator quick start', leftMargin=45, rightMargin=45,
                      topMargin=40, bottomMargin=40).build(
                          story, onFirstPage=footer, onLaterPages=footer)
    (output / 'AMR-Simulator-Quick-Start.md').write_text('\n'.join(markdown), encoding='utf-8')


def prepare(output, version, ltn=None):
    from amr_tutorial_assets import generate_assets
    from verification.building_guide import build as build_guide
    from verification.building_coverage import build as build_coverage
    from amr_run_evidence import software_snapshot

    output = Path(output).resolve()
    course = output / 'docs/building-tutorial'
    generate_assets(course)
    # Use tracked screenshots and current instructions, not old local QA output.
    build_guide(evidence=output / 'unused-evidence', output=course)
    build_coverage(course)
    quick_start(output / 'docs/quick-start', bool(ltn))
    shutil.copy2(ROOT / 'LICENSE', output / 'LICENSE')
    if ltn:
        examples = output / 'examples'
        examples.mkdir(exist_ok=True)
        shutil.copy2(ltn, examples / 'ltn.amrproj')
    metadata = dict(version=version, software=software_snapshot(),
                    tutorial_chapters=12, ltn_included=bool(ltn))
    (output / 'release-info.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    (output / 'START-HERE.txt').write_text(
        f'AMR Simulator {version} - Windows x64\n\n'
        'Open AMRSimulator.exe. Python is bundled; no separate installation is needed.\n'
        'Choose Help > Building flow tutorial for the current 12-part guided course.\n'
        'Use Course tools to save a working copy of a starter, checkpoint or reference.\n'
        'Save projects and simulation results outside the application folder.\n'
        'Bundled guides and drawings are in docs\\building-tutorial.\n'
        'The small-map exercise is in docs\\quick-start.\n'
        'The optional supplied LTN project is ' + ('included.\n' if ltn else 'not included.\n') +
        '\nThis feasibility model has modelling limitations; review checks and run evidence.\n'
        'This package is unsigned. Licence: AGPL-3.0; see LICENSE and matching release source.\n',
        encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--ltn-project', type=Path)
    args = parser.parse_args()
    prepare(args.output, args.version, args.ltn_project)
