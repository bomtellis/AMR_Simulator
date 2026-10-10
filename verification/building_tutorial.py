"""Isolated non-LTN regressions, complete courses and actual-screen QA."""
import argparse
import json
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]

def qa(output):
    from verification.simple_delivery import MODULES,snapshot
    from verification.run import source_manifest
    from verification.isolated import run_modules
    extra=('test_building_tutorial','test_tutorial_bubble','test_tutorial_circulation','test_tutorial_placement','test_route_profiles','test_lift_contracts','test_lift_evidence',
      'test_lift_trip_cohorts','test_charger_contention','test_required_charge_dispatch','test_scenario_recovery')
    before=snapshot(output);result=run_modules(ROOT/'tests',output,modules=MODULES+extra)
    data=dict(successful=result.wasSuccessful(),source_unchanged=before['files']==source_manifest()['files'],
       cases=result.cases,modules=list(MODULES+extra),excluded='LTN workloads, tests, benchmarks and repairs')
    (output/'qa.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
    return 0 if data['successful'] and data['source_unchanged'] else 1

def capture(output,enlarged=False):
    from copy import deepcopy
    sys.path.insert(0,str(ROOT/'visualiser'))
    from PySide6.QtCore import QCoreApplication,QEvent,Qt
    from PySide6.QtGui import QFont,QFontDatabase
    from PySide6.QtWidgets import QApplication,QPushButton
    from app import AMRGraphEditor
    from amr_tutorial_assets import building_config
    from appearance import controller
    app=QApplication.instance() or QApplication([]);appearance=controller(app,settings=None)
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
    app.setFont(QFont('Segoe UI',18 if enlarged else 10))
    e=AMRGraphEditor();e._drawings_enabled=False;e.store.data=building_config(ROOT/'docs/building-tutorial');e._reset_edit_history()
    e.show();app.processEvents();e.workbench.show_building_course();e.show_lift_planner();planner=e.lift_planner;planner.infer()
    rows=[]
    for theme in ('Light','Dark','High contrast'):
        from dataclasses import replace
        appearance.apply(replace(appearance.value,theme=theme,font_size=18 if enlarged else 10))
        for width,height in ((1024,768),(1600,900)):
            for name,dialog in [('course',e.workbench.quick_start_dialog),('planner',planner)]:
                dialog.show();app.processEvents();dialog.setMaximumSize(16777215,16777215);dialog.resize(width,height);app.processEvents()
                tabs=dialog.tabs
                indices=[2] if name=='course' else range(4)
                for index in indices:
                    tabs.setCurrentIndex(index);app.processEvents()
                    buttons=([dialog.building_course.check,dialog.building_course.next,dialog.building_course.open]
                        if name=='course' else [planner.evaluate,planner.stop,planner.variant,planner.apply])
                    visible=all(b.isVisible() and dialog.rect().contains(b.mapTo(dialog,b.rect().bottomRight())) for b in buttons)
                    rows.append(dict(name=name,tab=index,size=[dialog.width(),dialog.height()],theme=theme,footer_visible=visible))
                    dialog.grab().save(str(output/f'{name}-{theme}-{width}-tab{index}.png'))
                dialog.close()
            course=e.workbench.quick_start_dialog.building_course;course.show_card();course.session.state['action']=1;course.card.refresh()
            course.card.locate();app.processEvents();bubble=course.card
            e.resize(width,height);app.processEvents();bubble.follow()
            frame=e.grab()
            from PySide6.QtGui import QPainter
            painter=QPainter(frame);position=e.mapFromGlobal(bubble.pos());painter.drawPixmap(position,bubble.grab());painter.end()
            frame.save(str(output/f'bubble-{theme}-{width}.png'))
            rows.append(dict(name='bubble',size=[width,height],theme=theme,footer_visible=all(bubble.rect().contains(b.mapTo(bubble,b.rect().bottomRight())) for b in (bubble.next,bubble.check,bubble.pause_button)),target=bubble.target.text() if isinstance(bubble.target,QPushButton) else type(bubble.target).__name__))
            from building_settings import BuildingSettingsDialog
            from PySide6.QtWidgets import QDialogButtonBox
            settings=BuildingSettingsDialog(e,e.store.data);settings.setModal(True);settings.show();app.processEvents();bubble.follow()
            buttons=[settings.buttons.button(role) for role in (QDialogButtonBox.Save,QDialogButtonBox.Cancel)]
            visible=all(b.isVisible() and settings.rect().contains(b.mapTo(settings,b.rect().bottomRight())) for b in buttons)
            def reachable(widget):
                parent=widget.parentWidget()
                while parent:
                    if not parent.rect().contains(widget.mapTo(parent,widget.rect().bottomRight())):return False
                    if parent is settings:break
                    parent=parent.parentWidget()
                return widget.isVisible()
            fields=all(reachable(w) for w in (settings.floor_count,settings.level_height))
            rows.append(dict(name='floor-settings',size=[width,height],theme=theme,footer_visible=visible and fields,floor_control=fields,bubble_tracks_floor_control=bubble.target is settings.floor_count))
            settings.grab().save(str(output/f'floor-settings-{theme}-{width}.png'))
            settings.reject();settings.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
            base=deepcopy(e.store.data)
            for name,empty in (('route-preview',True),('route-repair',False)):
                e.store.data=deepcopy(base)
                if empty:e.store.data['corridors']=dict(auto_connect=False,nodes=[],edges=[])
                else:e.store.data['corridors']['edges']=[edge for edge in e.store.data['corridors']['edges'] if
                    {edge['from'],edge['to']}!={'Clean-J12-F0','Clean-J18-F0'}]
                e._reset_edit_history();e.refresh_canvas();course.chapters.setCurrentIndex(2);course.session.state['action']=0
                bubble.refresh();bubble.locate();e._set_edit_mode('corridor_draw');e.fit_view();app.processEvents()
                if not empty:bubble.check_action()
                bubble.follow();frame=e.grab();painter=QPainter(frame);painter.drawPixmap(e.mapFromGlobal(bubble.pos()),bubble.grab());painter.end()
                frame.save(str(output/f'{name}-{theme}-{width}.png'))
                from PySide6.QtCore import QRect
                card=QRect(bubble.pos(),bubble.size());panes,controls=bubble.obstacles(e)
                target=QRect(bubble.outline.mapToGlobal(bubble.outline.rect().topLeft()),bubble.outline.size())
                rows.append(dict(name=name,size=[width,height],theme=theme,footer_visible=all(bubble.rect().contains(b.mapTo(bubble,b.rect().bottomRight())) for b in (bubble.next,bubble.check,bubble.pause_button)),
                    target_clear=not card.intersects(target),panes_clear=not any(card.intersects(r) for r in panes),
                    controls_clear=not any(card.intersects(r) for r in controls),next_blocked=not bubble.next.isEnabled(),
                    preview_visible=bubble.route_overlay.isVisible()))
            from amr_tutorial_placement import FACILITIES
            from PySide6.QtWidgets import QInputDialog,QLineEdit
            e.store.data=deepcopy(base);names={r[1] for r in FACILITIES}
            e.store.data['locations']=[r for r in e.store.data['locations'] if r['name'] not in names]
            e.store.data['corridors']['edges']=[r for r in e.store.data['corridors']['edges'] if r['from'] not in names and r['to'] not in names]
            e._reset_edit_history();e.refresh_canvas();course.chapters.setCurrentIndex(3);course.session.state['action']=0
            bubble.refresh();bubble.locate();e._set_edit_mode('location');e.fit_view();app.processEvents();bubble._auto_after=0;bubble.follow()
            location_dialog=QInputDialog(e);location_dialog.setWindowTitle('Location');location_dialog.setInputMode(QInputDialog.TextInput)
            location_dialog.setLabelText('Location name:\nFloor 0 · X 3, Y 10 m\nJoins the corridor here with a 0.1 m access link.')
            location_dialog.setModal(True)
            for name,modal in (('facility-preview',False),('location-name',True)):
                if modal:
                    e._pending_insertion=dict(tool='Location',floor=0,x=3,y=10)
                    location_dialog.show();app.processEvents();bubble.follow()
                    from PySide6.QtTest import QTest
                    QTest.qWait(30);bubble.follow()  # Settle show-time label/style layout before capture.
                frame=e.grab();painter=QPainter(frame)
                if modal:painter.drawPixmap(e.mapFromGlobal(location_dialog.pos()),location_dialog.grab())
                painter.drawPixmap(e.mapFromGlobal(bubble.pos()),bubble.grab());painter.end()
                frame.save(str(output/f'{name}-{theme}-{width}.png'))
                card=QRect(bubble.pos(),bubble.size());owner=location_dialog if modal else e;panes,controls=bubble.obstacles(owner)
                target=QRect(bubble.outline.mapToGlobal(bubble.outline.rect().topLeft()),bubble.outline.size())
                rows.append(dict(name=name,size=[width,height],theme=theme,
                    footer_visible=all(bubble.rect().contains(b.mapTo(bubble,b.rect().bottomRight())) for b in (bubble.next,bubble.check,bubble.pause_button)),
                    target_clear=not card.intersects(target),panes_clear=not any(card.intersects(r) for r in panes),
                    controls_clear=not any(card.intersects(r) for r in controls),next_blocked=not bubble.next.isEnabled(),
                    preview_visible=bubble.route_overlay.isVisible(),placement_text_visible=bubble.where.isVisible() and 'Dispatch' in bubble.where.text(),
                    independent_owner=bubble.parentWidget() is e,naming_dialog_clear=not modal or not card.intersects(bubble.visible_rect(location_dialog)),
                    naming_buttons_clear=not modal or not location_dialog.findChild(QDialogButtonBox).buttons()[0].geometry().intersects(location_dialog.findChild(QDialogButtonBox).buttons()[1].geometry())))
            location_dialog.reject();location_dialog.deleteLater();e._pending_insertion=None;QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
            e.store.data=base;e._reset_edit_history();e.refresh_canvas();course.chapters.setCurrentIndex(0);course.session.state['action']=1
            bubble.pause();e.workspace.activate('layout')
    # The majority gate is the default layout, not the remembered proportions
    # of the editor after switching between large and small lesson windows.
    from unittest.mock import patch
    with patch.object(e,'_confirm_unsaved_changes',return_value=True):e.close()
    e.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
    appearance.apply(replace(appearance.value,theme='Light',font_size=10))
    e=AMRGraphEditor();e._drawings_enabled=False;e.resize(1024,768);e.show();app.processEvents();e.grab().save(str(output/'workbench.png'))
    viewport=e.canvas.viewport();fraction=viewport.width()*viewport.height()/(e.width()*e.height())
    rows.append(dict(name='workbench',canvas_fraction=fraction,properties_collapsed=not e.workspace.properties.isVisible()))
    with patch.object(e,'_confirm_unsaved_changes',return_value=True):e.close()
    e.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
    passed=all(r.get('footer_visible',True) and all(r.get(k,True) for k in ('target_clear','panes_clear','controls_clear','next_blocked','preview_visible','placement_text_visible','independent_owner','naming_buttons_clear','naming_dialog_clear')) for r in rows) and fraction>.5
    (output/'visual.json').write_text(json.dumps(dict(passed=passed,scale=os.environ.get('QT_SCALE_FACTOR','1'),enlarged=enlarged,screens=rows),indent=2),encoding='utf-8')
    return 0 if passed else 1

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=('qa','capture','integration'));p.add_argument('--output',type=Path,required=True);p.add_argument('--enlarged',action='store_true')
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True);temporary=a.output/'temp';temporary.mkdir(exist_ok=True)
    os.environ['TMP']=os.environ['TEMP']=str(temporary.resolve());os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    import tempfile
    tempfile.tempdir=str(temporary.resolve())
    if a.action=='qa':return qa(a.output)
    if a.action=='capture':return capture(a.output,a.enlarged)
    from amr_building_smoke import run
    return run(a.output,('dedicated','shared'))

if __name__=='__main__':raise SystemExit(main())
