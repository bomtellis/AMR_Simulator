"""Independent building/course, geometry and service-guard acceptance cases."""
from copy import deepcopy
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'visualiser'))
from PySide6.QtCore import QCoreApplication,QEvent,Qt
from PySide6.QtWidgets import QApplication,QDialogButtonBox
from amr_tutorial_assets import building_config,generate_assets
from amr_tutorial import TutorialSession,LESSONS
from amr_lift_planning_geometry import extract_floor,masks,connector_path,rect_path,transform,generate_sites,build_proposals
from amr_lift_study import realize_demand,scenario_config,rank_results,SCENARIOS,event_access,input_identity
from visualiser.project_checks import check_project


class BuildingTutorialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.config=generate_assets(self.root)
    def tearDown(self):self.temp.cleanup()

    def test_three_drawings_have_actual_800_metre_area_and_common_registration(self):
        g=[extract_floor(r['filepath'],r['floor']) for r in self.config['floor_dxf_files']]
        self.assertEqual([800,800,800],[r['boundary_area_m2'] for r in g])
        self.assertTrue(all(r['unit_scale']==1 for r in g))
        self.assertTrue((self.root/'building-three-floors.dxf').is_file())
        from amr_project import Project
        for name in ('starter','reference-dedicated','reference-shared','chapter-3','chapter-7'):
            with tempfile.TemporaryDirectory() as cache:
                config=Project.open(self.root/(name+'.amrproj')).materialize(cache)
                self.assertTrue(all(Path(r['filepath']).is_file() for r in config['floor_dxf_files']))

    def test_reference_runs_both_policies_with_charge_wash_and_both_lifts(self):
        from simulator import Simulation
        for policy in ('dedicated','shared'):
            c=building_config(self.root,policy)
            self.assertFalse([f for f in check_project(c).findings if f.severity in ('error','warning')])
            sim=Simulation(c,verbose=True)
            with contextlib.redirect_stdout(io.StringIO()):sim.run()
            self.assertEqual(36,len(sim.completed_task_records));self.assertFalse(sim.failed_tasks);self.assertFalse(sim.pending_tasks)
            self.assertEqual(12,sim.wash_cycles_completed);self.assertGreaterEqual(len(sim.charge_intervals),4)
            self.assertEqual({'L1','L2'},{r['lift_id'] for r in sim.verbose_rows if r['event_type']=='segment_lift_transfer'})

    def test_checked_steps_do_not_complete_when_only_opened(self):
        s=TutorialSession();blank={}
        self.assertTrue(s.check(4,blank))
        self.assertFalse(s.state['completed']['transport']['passed'])

    def test_study_identity_survives_editor_defaults_and_detects_authored_edits(self):
        from visualiser.models import JsonStore
        resolved=JsonStore(self.config).data
        self.assertEqual(input_identity(self.config),input_identity(resolved))
        resolved['lifts'][0]['speed_floors_per_sec'] *= 2
        self.assertNotEqual(input_identity(self.config),input_identity(resolved))

    def test_proposal_connectors_are_reproducible_across_hash_seeds(self):
        import subprocess
        script='''import json,sys
from pathlib import Path
from amr_tutorial_assets import building_config
from amr_lift_study import realize_demand
from amr_lift_planning_geometry import extract_floor,generate_sites,build_proposals
c=building_config(Path(sys.argv[1]));g=[extract_floor(r['filepath'],r['floor']) for r in c['floor_dxf_files']]
s=generate_sites(c,g,{},realize_demand(c));p,o=build_proposals(c,g,s,{})
print(json.dumps(p,sort_keys=True))'''
        values=[]
        for seed in ('1','917'):
            environment=dict(os.environ,PYTHONHASHSEED=seed)
            values.append(subprocess.check_output([sys.executable,'-c',script,str(self.root)],cwd=ROOT,env=environment,text=True))
        self.assertEqual(values[0],values[1])

    def test_atomic_progress_pause_restart_and_rename_binding(self):
        path=self.root/'progress.json';s=TutorialSession(path);s.seed_bindings(self.config)
        row=next(r for r in self.config['locations'] if r['name']=='Wash');row['name']='Renamed station'
        self.assertEqual([],s.reconcile(self.config));self.assertEqual('Renamed station',s.roles(self.config)['wash'])
        self.config['locations'].remove(row);self.assertIn('wash',s.reconcile(self.config))
        s.state['paused']=True;s.save();other=TutorialSession(path);self.assertTrue(other.state['paused'])
        other.state['completed']['create']={'passed':True};other.restart(0);self.assertNotIn('create',other.state['completed'])

    def test_core_configuration_check_and_policy_mismatch(self):
        s=TutorialSession();self.assertEqual([],s.check(0,self.config,{'saved':True}))
        for chapter in (2,3,4,5):self.assertEqual([],s.check(chapter,self.config),LESSONS[chapter][0])
        s.state['policy']='shared';self.assertTrue(s.check(5,self.config))
        s.observe('preview');self.assertEqual([],s.check(6,self.config))

    def test_geometry_units_blocks_and_curves(self):
        import ezdxf
        d=ezdxf.new();d.units=4
        for name in ('BOUNDARY','CIRCULATION','WALLS'):d.layers.new(name)
        block=d.blocks.new('ROOM');block.add_lwpolyline([(0,0),(40000,0),(40000,20000),(0,20000)],close=True,dxfattribs={'layer':'BOUNDARY'})
        d.modelspace().add_blockref('ROOM',(10000,5000))
        d.modelspace().add_lwpolyline([(11000,6000),(49000,6000),(49000,24000),(11000,24000)],close=True,dxfattribs={'layer':'CIRCULATION'})
        d.modelspace().add_circle((30000,15000),1000,dxfattribs={'layer':'WALLS'})
        p=self.root/'mm.dxf';d.saveas(p);g=extract_floor(p,0,registration={'dx':-10,'dy':-5,'rotation_deg':0})
        self.assertEqual(800,g['boundary_area_m2']);self.assertEqual(.001,g['unit_scale'])
        circle=next(r for r in g['entities'] if r['role']=='wall');self.assertGreater(len(circle['points']),20)
        for a,b in zip(circle['points'],circle['points'][1:]+circle['points'][:1]):
            self.assertLessEqual(1-( ((a[0]+b[0])/2-20)**2+((a[1]+b[1])/2-10)**2 )**.5,.01001)

    def test_open_and_ambiguous_boundaries_and_missing_circulation_are_rejected(self):
        import ezdxf
        for mode in ('open','multiple','missing'):
            d=ezdxf.new();d.units=6;m=d.modelspace()
            m.add_lwpolyline([(0,0),(40,0),(40,20),(0,20)],close=mode!='open',dxfattribs={'layer':'BOUNDARY'})
            if mode=='multiple':m.add_lwpolyline([(50,0),(90,0),(90,20),(50,20)],close=True,dxfattribs={'layer':'BOUNDARY'})
            if mode!='missing':m.add_lwpolyline([(1,1),(39,1),(39,19),(1,19)],close=True,dxfattribs={'layer':'CIRCULATION'})
            p=self.root/(mode+'.dxf');d.saveas(p)
            with self.assertRaises(ValueError):extract_floor(p,0)

    def test_connector_routes_around_obstacle_and_cannot_cut_corners(self):
        free=rect_path(5,5,10,10);obstacle=rect_path(5,5,2,6);free=free.subtracted(obstacle)
        route=connector_path((2,5),(8,5),free)
        self.assertIsNotNone(route);self.assertGreater(sum(__import__('math').dist(a,b) for a,b in zip(route,route[1:])),6)
        self.assertIsNone(connector_path((5,5),(8,5),free))

    def test_floor_registration_roundtrip_and_no_feasible_sites(self):
        reg={'dx':10,'dy':-4,'rotation_deg':90};p=transform((2,3),reg);back=transform(p,reg,inverse=True)
        self.assertAlmostEqual(2,back[0]);self.assertAlmostEqual(3,back[1])
        g=[extract_floor(r['filepath'],r['floor']) for r in self.config['floor_dxf_files']]
        o={'shaft_length_m':40,'shaft_width_m':20,'landing_depth_m':1}
        with self.assertRaises(ValueError):generate_sites(self.config,g,o,[])

    def test_proposals_preserve_policy_equipment_and_recalculate_connections(self):
        requests=realize_demand(self.config);g=[extract_floor(r['filepath'],r['floor']) for r in self.config['floor_dxf_files']]
        sites=generate_sites(self.config,g,{},requests);p,overlays=build_proposals(self.config,g,sites,{})
        self.assertEqual(5,len(p));self.assertEqual(8,len(sites))
        for c in p.values():
            self.assertEqual(self.config['tasks'],c['tasks']);self.assertEqual(self.config['amrs'],c['amrs'])
            for before,after in zip(self.config['lifts'],c['lifts']):
                self.assertEqual({k:v for k,v in before.items() if k!='floor_locations'},
                                 {k:v for k,v in after.items() if k!='floor_locations'})
            # Explicit graphical edge permissions follow rebuilt lift access
            # connectors, while other corridor permissions remain intact.
            from route_profile_graphics import edge_pairs
            physical=edge_pairs(c['corridors']['edges'])
            for flow,before in self.config['route_profiles'].items():
                after=c['route_profiles'][flow]
                self.assertEqual(before['allowed_lifts'],after['allowed_lifts'])
                self.assertTrue(set(before['allowed_nodes'])<=set(after['allowed_nodes']))
                self.assertTrue({tuple(pair) for pair in after['allowed_edges']}<=physical)
                retained={tuple(pair) for pair in before['allowed_edges'] if not any('-F' in name and name.startswith(('L1','L2')) for name in pair)}
                self.assertTrue(retained<={tuple(pair) for pair in after['allowed_edges']})
        self.assertTrue(all(overlays.values()))

    def test_requests_are_frozen_including_returns_and_scenarios_do_not_mutate_source(self):
        before=deepcopy(self.config);requests=realize_demand(self.config)
        self.assertEqual(36,len(requests));self.assertTrue(any('return' in r['labels'] for r in requests))
        for name in SCENARIOS:
            c=scenario_config(self.config,requests,name)
            self.assertEqual(72 if name=='peak' else 36,len(c['tasks']))
            self.assertFalse(c['task_generation']['enabled'])
        self.assertEqual(before,self.config)

    def test_outage_access_distinguishes_floor_service_and_uptime(self):
        requests=[dict(pickup='Clean store',dropoff='Clean-F1',flow='clean',service_floor=1)]
        c=scenario_config(self.config,[], 'lift-1-outage')
        self.assertFalse(event_access(c,requests)['1/clean'])
        from amr_tutorial_assets import set_policy
        set_policy(c,'shared');self.assertTrue(event_access(c,requests)['1/clean'])

    def test_source_identity_ignores_path_but_tracks_drawing_bytes(self):
        c=deepcopy(self.config);a=input_identity(c)
        for row in c['floor_dxf_files']:
            p=Path(row['filepath']);target=self.root/('copy-'+p.name);target.write_bytes(p.read_bytes());row['filepath']=str(target)
        self.assertEqual(a,input_identity(c));Path(c['floor_dxf_files'][0]['filepath']).write_bytes(b'changed')
        self.assertNotEqual(a,input_identity(c))

    def test_drawing_generation_is_byte_reproducible(self):
        other=self.root/'again';generate_assets(other)
        for name in ('floor-0.dxf','floor-1.dxf','floor-2.dxf','building-three-floors.dxf'):
            self.assertEqual((self.root/name).read_bytes(),(other/name).read_bytes())

    def test_hatch_circulation_preserves_excluded_hole(self):
        import ezdxf
        doc=ezdxf.new();doc.units=6
        doc.modelspace().add_lwpolyline([(0,0),(20,0),(20,20),(0,20)],close=True,dxfattribs={'layer':'BOUNDARY'})
        h=doc.modelspace().add_hatch(dxfattribs={'layer':'CIRCULATION'})
        h.paths.add_polyline_path([(1,1),(19,1),(19,19),(1,19)],is_closed=True,flags=1)
        h.paths.add_polyline_path([(8,8),(12,8),(12,12),(8,12)],is_closed=True,flags=0)
        path=self.root/'hole.dxf';doc.saveas(path);g=extract_floor(path,0);free=masks(g)[2]
        self.assertTrue(free.contains(rect_path(4,4,1,1)));self.assertFalse(free.contains(rect_path(10,10,1,1)))

    def test_large_analytic_curves_meet_ten_millimetre_deviation(self):
        import ezdxf,math
        doc=ezdxf.new();doc.units=6;m=doc.modelspace()
        for layer in ('BOUNDARY','CIRCULATION'):m.add_lwpolyline([(0,0),(300,0),(300,300),(0,300)],close=True,dxfattribs={'layer':layer})
        m.add_circle((150,150),100,dxfattribs={'layer':'WALLS'})
        hatch=m.add_hatch(dxfattribs={'layer':'EXCLUDED'});edge=hatch.paths.add_edge_path();edge.add_arc((150,150),100,0,360)
        path=self.root/'large-curves.dxf';doc.saveas(path);g=extract_floor(path,0)
        for row in g['entities']:
            if row['role'] not in ('wall','excluded'):continue
            for a,b in zip(row['points'],row['points'][1:]+row['points'][:1]):
                middle=((a[0]+b[0])/2,(a[1]+b[1])/2)
                self.assertLessEqual(abs(math.dist(middle,(150,150))-100),.01)

    def test_bad_progress_is_recoverable_and_instruction_state_is_bounded(self):
        path=self.root/'progress.json';path.write_text(json.dumps(dict(version=1,bindings={},chapter=999,seen=[],completed={})))
        session=TutorialSession(path);self.assertTrue(session.warning);self.assertEqual(0,session.state['chapter'])

    def test_retained_shaft_identity_and_location_are_preserved(self):
        g=[extract_floor(r['filepath'],r['floor']) for r in self.config['floor_dxf_files']]
        requests=realize_demand(self.config);options={'movable':{'L1':False,'L2':True}}
        sites=generate_sites(self.config,g,options,requests);proposals,_=build_proposals(self.config,g,sites,options)
        self.assertTrue(proposals)
        for config in proposals.values():self.assertEqual(self.config['lifts'][0],config['lifts'][0])

    def test_small_graph_metrics_equal_independently_calculated_distance_and_service(self):
        from amr_project import Project
        from amr_project_runs import PreparedRun,execute
        from amr_lift_study import run_metrics
        c=deepcopy(self.config);c['building'].update(floor_count=1,charge_locations=[],load_unload_time_sec=0)
        c['floor_dxf_files']=[];c['lifts']=[];c['departments']=[];c['route_profiles']={}
        c['locations']=[dict(name='A',floor=0,x=0,y=0),dict(name='B',floor=0,x=3,y=4)]
        c['corridors']=dict(auto_connect=False,nodes=[],edges=[dict(**{'from':'A','to':'B'},width_m=3,bidirectional=True)])
        c['amrs'][0].update(quantity=1,battery_capacity_kwh=100,battery_soc_percent=100,speed_m_per_sec=1)
        c['task_generation']['enabled']=False;c['tasks']=[dict(id='T',pickup='A',dropoff='B',payload='Clean tote',release_time=0,target_time=10)]
        project=Project();project.save(self.root/'small.amrproj',c);draft=PreparedRun(project,self.root/'small-runs')
        report=check_project(draft.config);report.acknowledge_warnings();directory=draft.commit(report)
        with contextlib.redirect_stdout(io.StringIO()):execute(directory)
        m=run_metrics(directory);self.assertEqual(1,m['completed']);self.assertEqual(5,m['horizontal_loaded_m'])
        self.assertEqual(0,m['horizontal_empty_m']);self.assertEqual(0,m['vertical_m'])
        self.assertEqual(1,next(iter(m['groups'].values()))['on_time_rate'])

    def test_cancel_resume_relink_and_changed_frozen_drawing(self):
        import shutil
        from amr_lift_study import create_study,evaluate,write_record,relink_result
        path=self.root/'study.json';state=create_study(self.config,path)
        state.update(confirmed=True,geometry=[extract_floor(r['filepath'],r['floor']) for r in self.config['floor_dxf_files']],scenarios=['normal'])
        write_record(path,state);self.assertEqual('cancelled',evaluate(path,cancel=lambda:True)['status'])
        state=evaluate(path);old=state['results']['current']['normal'];key=old['metrics']['run_key']
        self.assertEqual(key,evaluate(path)['results']['current']['normal']['metrics']['run_key'])
        moved=self.root/'moved';shutil.copytree(old['directory'],moved);relink_result(state,'current','normal',moved)
        self.assertEqual(str(moved.resolve()),state['results']['current']['normal']['directory'])
        with (moved/'simulation_steps.csv').open('a',encoding='utf-8') as stream:stream.write('tampered\n')
        with self.assertRaises(ValueError):relink_result(state,'current','normal',moved)
        frozen=Path(state['config']['floor_dxf_files'][0]['filepath']);frozen.write_bytes(frozen.read_bytes()+b'\n')
        with self.assertRaisesRegex(ValueError,'Frozen drawing'):evaluate(path)

    def test_confirmation_and_fixed_equipment_guard_evaluation(self):
        from amr_lift_study import create_study,evaluate,write_record
        path=self.root/'study.json';state=create_study(self.config,path)
        with self.assertRaisesRegex(ValueError,'Confirm'):evaluate(path)
        state.update(confirmed=True,geometry=[extract_floor(r['filepath'],r['floor']) for r in self.config['floor_dxf_files']])
        changed=deepcopy(state['config']);changed['amrs'][0]['quantity']=5;state['proposals']={'different':changed};write_record(path,state)
        with self.assertRaisesRegex(ValueError,'fixed'):evaluate(path)

    def test_atomic_progress_write_retries_transient_windows_lock(self):
        from amr_project import atomic_write
        path=self.root/'progress.json';path.write_bytes(b'old');replace=os.replace;calls=[]
        def locked_once(a,b):
            calls.append(1)
            if len(calls)==1:
                exc=PermissionError('sharing lock');exc.winerror=32;raise exc
            return replace(a,b)
        with patch('amr_project.os.replace',side_effect=locked_once),patch('amr_project.time.sleep'):
            atomic_write(path,b'new')
        self.assertEqual(2,len(calls));self.assertEqual(b'new',path.read_bytes())

    def test_persistent_save_denial_preserves_original_and_removes_temporary(self):
        from amr_project import atomic_write
        path=self.root/'progress.json';path.write_bytes(b'old');exc=PermissionError('persistent lock');exc.winerror=32
        with patch('amr_project.os.replace',side_effect=exc),patch('amr_project.time.sleep'):
            with self.assertRaises(PermissionError):atomic_write(path,b'new')
        self.assertEqual(b'old',path.read_bytes());self.assertFalse(list(self.root.glob('.progress.json.*.tmp')))

    def test_study_playback_and_report_bind_private_revision_without_changing_editor(self):
        from app import AMRGraphEditor
        from amr_project import Project
        from amr_lift_study import create_study,evaluate,write_record
        from PySide6.QtTest import QTest
        project=Project();project.save(self.root/'source.amrproj',self.config)
        path=self.root/'study.json';state=create_study(self.config,path,project.path)
        state.update(confirmed=True,geometry=[extract_floor(r['filepath'],r['floor']) for r in self.config['floor_dxf_files']],scenarios=['normal'])
        write_record(path,state);state=evaluate(path)
        e=AMRGraphEditor();e._drawings_enabled=False
        try:
            self.assertTrue(e.load_json_file(str(project.path),load_drawings=False));before=deepcopy(e.store.data);identity=e.project.project_id
            e.show_lift_planner();planner=e.lift_planner;planner.study=state;planner.refresh_state();planner.scenarios.setCurrentCell(0,0)
            planner.playback()
            for _ in range(200):
                self.app.processEvents()
                if e.playback_panel.viewer is not None:break
                QTest.qWait(10)
            self.assertIsNotNone(e.playback_panel.viewer,e.playback_panel.summary.text())
            planner.report();self.assertEqual(Path(state['results']['current']['normal']['directory']),e.report_panel.run_dir)
            self.assertNotEqual(identity,e.report_panel._run_project.project_id)
            self.assertEqual(identity,e.project.project_id);self.assertEqual(before,e.store.data)
        finally:
            with patch.object(e,'_confirm_unsaved_changes',return_value=True):e.close()
            e.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)

    def test_gui_navigation_is_read_only_and_proposal_apply_is_undoable(self):
        from app import AMRGraphEditor
        e=AMRGraphEditor()
        e._drawings_enabled=False
        try:
            e.store.data=deepcopy(self.config);e._reset_edit_history();before=deepcopy(e.store.data)
            e.workbench.show_building_course();course=e.workbench.quick_start_dialog.building_course
            course.chapters.setCurrentIndex(4);course.highlight();self.assertEqual(before,e.store.data)
            e.show_lift_planner();dialog=e.lift_planner;dialog.infer();self.assertEqual(3,len(dialog.geometries))
            dialog.resize(1024,768);dialog.show();self.app.processEvents()
            for i in range(4):dialog.tabs.setCurrentIndex(i);self.app.processEvents();self.assertTrue(dialog.rect().contains(dialog.evaluate.mapTo(dialog,dialog.evaluate.rect().bottomRight())))
            dialog.close();e.workbench.quick_start_dialog.close()
            c=deepcopy(before);c['lifts'][0]['floor_locations']['0']['x']=30
            self.assertTrue(e.apply_lift_proposal(c));self.assertEqual(30,e.store.data['lifts'][0]['floor_locations']['0']['x'])
            from PySide6.QtTest import QTest
            for _ in range(100):
                self.app.processEvents()
                if not e._history_busy():break
                QTest.qWait(20)
            self.assertTrue(e.undo_edit());self.assertEqual(before,e.store.data)
        finally:
            with patch.object(e,'_confirm_unsaved_changes',return_value=True):e.close()
            e.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)

    def test_bubble_tracks_actual_controls_preserves_focus_and_survives_dialog_close(self):
        from app import AMRGraphEditor
        from PySide6.QtWidgets import QDialog,QFormLayout,QSpinBox
        e=AMRGraphEditor();e._drawings_enabled=False;e.store.data=deepcopy(self.config);e._reset_edit_history();e.show()
        try:
            self.app.processEvents();e.canvas.setFocus();self.app.processEvents();focus=self.app.focusWidget()
            e.workbench.show_building_course();course=e.workbench.quick_start_dialog.building_course;bubble=course.card
            self.assertTrue(bubble.isVisible());self.assertFalse(e.workbench.quick_start_dialog.isVisible())
            from PySide6.QtWidgets import QToolButton
            more=next(w for w in bubble.findChildren(QToolButton) if w.text()=='More')
            self.assertIn('Start from drawings',[a.text() for a in more.menu().actions()])
            self.assertIs(focus,self.app.focusWidget());self.assertFalse(e.workspace.properties.isVisible())
            course.session.state['action']=1;bubble.locate();self.app.processEvents();bubble.follow()
            self.assertEqual('Building settings',bubble.target.text())
            dialog=QDialog(e);dialog.setModal(True);form=QFormLayout(dialog);spin=QSpinBox();form.addRow('Number of floors',spin)
            dialog.show();self.app.processEvents();bubble.follow();self.assertIs(spin,bubble.target)
            self.assertIs(e,bubble.parentWidget());self.assertIs(dialog.windowHandle(),bubble.windowHandle().transientParent());dialog.accept();self.app.processEvents();dialog.deleteLater()
            QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete);bubble.follow();self.assertTrue(bubble.isVisible())
            bubble.pause();self.assertFalse(bubble.isVisible());self.assertFalse(bubble.outline.isVisible())
            before=deepcopy(e.store.data);e.workbench.show_building_course();bubble.advance(1);self.assertEqual(before,e.store.data)
        finally:
            with patch.object(e,'_confirm_unsaved_changes',return_value=True):e.close()
            e.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)

    def test_create_step_next_reveals_floor_settings_and_real_floor_control(self):
        from app import AMRGraphEditor
        from building_settings import BuildingSettingsDialog
        e=AMRGraphEditor();e._drawings_enabled=False;e.show()
        try:
            from amr_project import Project
            e.project=Project()
            e.workspace.activate('project');e.workbench.show_building_course()
            course=e.workbench.quick_start_dialog.building_course;bubble=course.card
            bubble.advance(1);self.app.processEvents()
            self.assertEqual('configuration',e.workspace.stage)
            self.assertEqual('Building settings',bubble.target.text())
            dialog=BuildingSettingsDialog(e,e.store.data);dialog.setModal(True);dialog.show()
            self.app.processEvents();bubble.follow()
            self.assertIs(dialog.floor_count,bubble.target)
            dialog.floor_count.setValue(3);dialog.level_height.setValue(3.5);dialog.accept()
            self.assertEqual(3,dialog.result['building']['floor_count'])
            self.assertEqual(3.5,dialog.result['building']['floor_height_m'])
            dialog.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
        finally:
            with patch.object(e,'_confirm_unsaved_changes',return_value=True):e.close()
            e.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)


class ServiceGuardTests(unittest.TestCase):
    def metric(self,rate=1,distance=100,arrival=0):
        return dict(groups={'1/clean':dict(on_time_rate=rate,completed=1)},horizontal_m=distance,lift_wait_sec=0,
            software_sha256='same',requests=[dict(id='T',release=arrival,target=600,pickup='A',dropoff='B',payload='Box')])
    def test_shorter_with_worse_service_is_ineligible(self):
        r=rank_results({'current':{'normal':{'metrics':self.metric()}},'short':{'normal':{'metrics':self.metric(.5,1)}}},['normal'])
        self.assertFalse(r[0]['eligible'])
    def test_changed_arrivals_cannot_rank_and_incomplete_layout_is_withheld(self):
        r=rank_results({'current':{'normal':{'metrics':self.metric()}},'changed':{'normal':{'metrics':self.metric(1,1,2)}},'partial':{}},['normal'])
        self.assertEqual(1,len(r));self.assertFalse(r[0]['eligible'])
    def test_all_scenarios_and_groups_are_required(self):
        self.assertEqual([],rank_results({'current':{'normal':{'metrics':self.metric()}}}))
    def test_service_first_then_distance_then_wait(self):
        r=rank_results({'current':{'normal':{'metrics':self.metric(.5)}},'a':{'normal':{'metrics':self.metric(1,90)}},'b':{'normal':{'metrics':self.metric(.75,1)}}},['normal'])
        self.assertEqual(['a','b'],[x['id'] for x in r]);self.assertTrue(all(x['eligible'] for x in r))

if __name__=='__main__':unittest.main()
