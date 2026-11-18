"""Capture the real pop-out and its complete PDF/PNG exports for visual checks."""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import sys

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'visualiser')]
from PySide6.QtCore import QThreadPool
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication
from visualiser.day_trip_preview import DayTripPreviewDialog
from tests.test_day_schedule import test_font
from tests.test_fm_logistics import fixture
from amr_day_trip_preview import run_dates, write_preview_pdf


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('output',type=Path)
    parser.add_argument('--project',type=Path)
    parser.add_argument('--font-points',type=int,default=9)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    config=json.loads(args.project.read_text(encoding='utf-8-sig')) if args.project else fixture()
    original=deepcopy(config)
    app=QApplication([])
    test_font(app)
    font=QFont(app.font());font.setPointSize(args.font_points);app.setFont(font)
    popup=DayTripPreviewDialog(lambda:config,lambda:'Demand',run_dates(config)[0].weekday())
    popup.show()
    popup.refresh_preview()
    if not QThreadPool.globalInstance().waitForDone(60000):raise RuntimeError('Preview did not finish.')
    app.processEvents()
    app.processEvents()
    if popup.preview is None:raise RuntimeError(popup.status.text())
    popup.grab().save(str(args.output/'preview-window.png'))
    popup.export_to(args.output/'demand-preview.pdf','pdf')
    popup.export_to(args.output/'demand-preview.png','png')
    popup.scroll.verticalScrollBar().setValue(popup.scroll.verticalScrollBar().maximum())
    app.processEvents()
    popup.grab().save(str(args.output/'preview-scrolled.png'))
    # A clearly isolated QA fixture checks long notes and page breaks.
    paginated=deepcopy(popup.preview)
    template=deepcopy(paginated['categories'][0])
    paginated['categories']=[dict(deepcopy(template),key=f'qa-{i}',label=f'Pagination test category {i+1}',
        notes='QA note: '+('Keep service windows aligned with department operating hours. '*8)) for i in range(22)]
    write_preview_pdf(args.output/'pagination-qa.pdf',paginated)
    assert original==config,'Preview and export must not change the project.'
    summary=dict(date=popup.preview['date'],trips=popup.preview['trips'],quantity=popup.preview['quantity'],
                 categories=[dict(category=row['label'],trips=row['trips'],additional=row['additional']) for row in popup.preview['categories']])
    (args.output/'preview-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary,indent=2))
    popup.close()


if __name__=='__main__':main()
