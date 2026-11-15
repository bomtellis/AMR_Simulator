"""Frozen-package building course and complete lift-study smoke check."""
from copy import deepcopy
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import traceback

def tutorial_gates(editor,app,config,output):
    """Check the repaired Part 3 gates in the installed Qt application."""
    editor.store.data=deepcopy(config);editor._reset_edit_history()
    editor.show();app.processEvents();editor.workbench.show_building_course()
    course=editor.workbench.quick_start_dialog.building_course;bubble=course.card
    course.chapters.setCurrentIndex(2);editor.floor_spin.setValue(2)
    def poll():
        bubble._auto_after=0;bubble.follow();app.processEvents()
    course.session.state['action']=17;bubble.refresh();poll()
    assert bubble.next.isEnabled(),bubble.feedback.text()
    door=next(r for r in editor.store.data['corridors']['nodes'] if r['name']=='Clean-door-F2')
    door['door_clear_width_m']=.9;poll()
    assert not bubble.next.isEnabled(),'Action 18 must reject a wrong door opening.'
    door['door_clear_width_m']=1.2;poll()
    assert bubble.next.isEnabled(),bubble.feedback.text()
    course.session.state['action']=18
    row=next(r for r in editor.store.data['locations'] if r['name']=='Clean-F2')
    row['name']='Wrong-F1';course.session.state['bindings'].pop('service_clean_2',None)
    for edge in editor.store.data['corridors']['edges']:
        for key in ('from','to'):
            if edge[key]=='Clean-F2':edge[key]='Wrong-F1'
    bubble.refresh();poll()
    assert not bubble.next.isEnabled(),'Action 19 must reject an unbound wrong name.'
    assert 'Clean-F2' in bubble.where.text() and 'Wrong-F1' not in bubble.where.text(),bubble.where.text()
    assert bubble._correction['name']=='Wrong-F1' and bubble._correction['property']=='name'
    bubble.grab().save(str(output/'tutorial-name-repair.png'))
    editor.store.data=deepcopy(config);editor._reset_edit_history()
    course.session.state['action']=18;bubble.refresh();poll()
    assert bubble.next.isEnabled(),bubble.feedback.text()
    course.session.state['bindings']['service_clean_2']=deepcopy(course.session.state['bindings']['service_dirty_1'])
    poll()
    assert course.session.roles(editor.store.data)['service_clean_2']=='Clean-F2'
    assert bubble.next.isEnabled() and 'Dirty-F1' not in bubble.feedback.text(),bubble.feedback.text()
    course.session.state['action']=19;editor._set_edit_mode('corridor_draw')
    editor.corridor_draw_start='Clean-F2';bubble.refresh();poll()
    assert not bubble.next.isEnabled()
    editor.finish_corridor_drawing();poll()
    assert bubble.next.isEnabled(),'Ending a route must recheck completion without another model edit.'
    editor.workbench.quick_start_dialog.close()

def run(output,policies=('dedicated',)):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    try:
        root=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent
        sys.path.insert(0,str(Path(__file__).resolve().parent/'visualiser'))
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance() or QApplication([])
        from PySide6.QtGui import QFont,QFontDatabase
        QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf');app.setFont(QFont('Segoe UI',10))
        from amr_project import Project
        from amr_lift_study import create_study,evaluate,write_record,export_comparison,run_metrics,input_identity,relink_result
        from amr_lift_planning_geometry import extract_floor,generate_sites,build_proposals
        from amr_lift_study_report import export_pdf
        from amr_tutorial import TutorialSession,LESSONS
        from amr_run_evidence import software_snapshot,file_hash
        from amr_project_report import generate,report_sections
        result={'software_sha256':software_snapshot()['sha256'],'policies':{}}
        for policy in policies:
            folder=output/policy;folder.mkdir(exist_ok=True)
            source=root/'docs/building-tutorial'/f'reference-{policy}.amrproj'
            original=file_hash(source)
            config=Project.open(source).materialize(folder/'drawing-cache')
            working=Project();working.save(folder/'building.amrproj',config,label='Tutorial practice')
            path=folder/'building.amrproj.lift-study.json'
            state=create_study(config,path,working.path)
            geometry=[extract_floor(r['filepath'],r['floor']) for r in config['floor_dxf_files']]
            assert [g['boundary_area_m2'] for g in geometry]==[800,800,800]
            options={};sites=generate_sites(state['config'],geometry,options,state['requests'])
            proposals,overlays=build_proposals(state['config'],geometry,sites,options)
            state.update(geometry=geometry,confirmed=True,sites=sites,proposals=proposals,overlays=overlays,options=options)
            write_record(path,state)
            state=evaluate(path,progress=lambda n,total,layout,scenario:print(f'{policy}: {n}/{total} {layout} {scenario}',flush=True))
            assert state['recommendation'],state['explanation']
            best=next(r for r in state['ranking'] if r['id']==state['recommendation'])
            assert best['eligible'] and best['distance_change_m']<0
            variant=Project();variant.save(folder/'improved.amrproj',state['proposals'][best['id']],label='Improved lift locations')
            state['variant']=str(variant.path);write_record(path,state)
            assert file_hash(source)==original
            export_comparison(state,folder/'comparison.csv');export_pdf(state,folder/'comparison.pdf')
            # Exercise the actual project run boundary as well as study scenarios.
            from amr_project_runs import PreparedRun,execute
            from visualiser.project_checks import check_project
            draft=PreparedRun(working,folder/'practice-runs');checks=check_project(draft.config)
            checks.acknowledge_warnings();run_dir=draft.commit(checks)
            with contextlib.redirect_stdout(io.StringIO()):execute(run_dir)
            normal=run_metrics(run_dir)
            assert normal['completed']==36 and normal['failed']==normal['pending']==0
            assert normal['wash_cycles']>=12 and normal['charging_cycles']>=4 and len(normal['lifts'])==2
            with contextlib.redirect_stdout(io.StringIO()):generate(run_dir,run_dir/'reports'/'course',[k for k,_ in report_sections()][:3])
            session=TutorialSession(folder/'building.amrproj.tutorial.json');session.state['policy']=policy;session.state['reopened']=True
            for seen in ('fit','snaps','selection','properties','undo','redo','preview','investigation','playback'):session.observe(seen)
            context=dict(saved=True,history_changes=1,run=run_dir,current_run=True,study=state,study_stale=False)
            for chapter in range(len(LESSONS)):
                problems=session.check(chapter,config,context);assert not problems,(chapter,problems)
            assert len(TutorialSession(session.path).state['completed'])==12
            # Resuming retains registered completed runs and their bytes.
            baseline_key=state['results']['current']['normal']['metrics']['run_key']
            state=evaluate(path);assert state['results']['current']['normal']['metrics']['run_key']==baseline_key
            result['policies'][policy]=dict(recommendation=best,normal=normal,study=str(path),course_chapters=12,comparison_runs=48)
        from app import AMRGraphEditor
        editor=AMRGraphEditor();editor._drawings_enabled=False
        tutorial_gates(editor,app,config,output)
        # Discard only the synthetic, unsaved gate-check fixture above.
        assert editor.load_json_file(str(working.path),load_drawings=False,check_unsaved=False)
        editor.show();app.processEvents();editor.workbench.show_building_course();course=editor.workbench.quick_start_dialog.building_course
        course.session=session;course.show_step();editor.workbench.quick_start_dialog.grab().save(str(output/'installed-course.png'))
        course.card.refresh();app.processEvents();course.card.grab().save(str(output/'installed-bubble.png'))
        editor.show_lift_planner();planner=editor.lift_planner;planner.refresh_state();planner.tabs.setCurrentIndex(1)
        app.processEvents();assert not planner.stale(),'Unchanged reopened study must remain current.'
        planner.grab().save(str(output/'installed-planner.png'))
        for action in (course.check,course.next,planner.evaluate,planner.variant):assert action.text()
        from PySide6.QtTest import QTest
        planner.scenarios.setCurrentCell(0,0);planner.playback()
        for _ in range(300):
            app.processEvents()
            if editor.playback_panel.viewer is not None:break
            QTest.qWait(10)
        assert editor.playback_panel.viewer is not None,editor.playback_panel.summary.text()
        planner.report();assert editor.report_panel.run_dir is not None
        assert editor.report_panel._run_project.project_id!=editor.project.project_id
        editor.show_project_runs();editor.project_runs_panel.refresh_runs()
        course.session.state['run']=str(run_dir)
        assert course.context()['current_run'],'Practice run must bind the actual saved source project.'
        editor.show_project_report(run_dir);assert editor.report_panel._run_project.project_id==editor.project.project_id
        result['gui']=dict(live_bubble=True,study_playback=True,study_report=True,current_project_run=True,
                           tutorial_floor_two_gates=True,tutorial_name_repair=True,tutorial_route_finish=True,
                           tutorial_stale_role_repaired=True)
        planner.close();editor.workbench.quick_start_dialog.close();editor.close()
        result['status']='passed';(output/'smoke.json').write_text(json.dumps(result,indent=2),encoding='utf-8');return 0
    except Exception:
        (output/'error.txt').write_text(traceback.format_exc(),encoding='utf-8');return 1
