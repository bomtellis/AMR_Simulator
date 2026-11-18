"""Render day-schedule evidence using the real Qt widget, without changing a project."""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'visualiser')]
from PySide6.QtCore import QThreadPool
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication
from visualiser.dialogs import TaskGenerationSettingsDialog
from tests.test_day_schedule import window_config, test_font
from tests.test_fm_logistics import fixture


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('output',type=Path)
    parser.add_argument('--project',type=Path)
    parser.add_argument('--font-points',type=int,default=9)
    parser.add_argument('--width',type=int,default=1240)
    parser.add_argument('--height',type=int,default=900)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    app=QApplication([])
    test_font(app)
    font=QFont(app.font())
    font.setPointSize(args.font_points)
    app.setFont(font)
    # Use desktop dimensions instead of the offscreen plugin's 800px screen.
    patch('ui_theme._fit_to_screen',lambda dialog:None).start()
    patch('ui_theme._make_small_screen_scrollable',lambda dialog:None).start()
    records=[]
    for name,config,planned in [('demand',window_config(),False),('fm',fixture(),True)]:
        if name=='demand' and args.project:
            config=json.loads(args.project.read_text(encoding='utf-8-sig'))
        original=deepcopy(config)
        dialog=TaskGenerationSettingsDialog(None,config['task_generation'],
            [row['name'] for row in config['locations']],
            [row['name'] for row in config.get('payloads',[])],list(config.get('route_profiles',{})),
            config['departments'],lambda value:None,project_configuration=lambda:config)
        dialog.resize(args.width,args.height)
        dialog.show()
        dialog.schedule_tabs.setCurrentWidget(dialog.day_schedule)
        app.processEvents()
        panel=dialog.day_schedule
        if planned:
            panel.calculate(True)
            if not QThreadPool.globalInstance().waitForDone(60000):
                raise RuntimeError('FM preview did not finish.')
            app.processEvents()
            if panel.comparison is None:
                raise RuntimeError(panel.status.text())
            panel.options.setCurrentIndex(panel.options.findData('coordinated'))
            app.processEvents()
        path=args.output/(name+'.png')
        dialog.grab().save(str(path))
        records.append(dict(view=name,width=dialog.width(),height=dialog.height(),
                            screenshot=str(path.resolve()),status=panel.status.text()))
        assert config==original,'Rendering must not alter project inputs'
        dialog.reject()
    (args.output/'layout.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
    print(json.dumps(records,indent=2))


if __name__=='__main__':
    main()
