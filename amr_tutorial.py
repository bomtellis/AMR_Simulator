"""Checked lessons and atomic, project-local progress; instructions never edit inputs."""
from copy import deepcopy
import json
from pathlib import Path

from amr_project import atomic_write
from amr_run_evidence import config_hash

# id, title, workspace, action, expected; IDs remain stable when copy is revised.
LESSONS = (
 ('create','Create the project','project','Create three floors at 3.5 m. Assign floor-0/1/2 DXFs from the building tutorial. Check the 40 × 20 m outline, then Save as an AMR project.','Three aligned 800 m² drawings and a saved project.'),
 ('workbench','Learn the workbench','layout','Switch floors. Use Fit, grid/object snaps and selection. Explicitly open and close Properties. Make a small node edit, undo it and redo it.','An actual edit and undo/redo, with the controls used.'),
 ('circulation','Draw clean and dirty circulation','layout','Use Corridor to trace the two circulation lanes. Add door nodes and floor service locations. Connect shared transition areas; only lift stops connect floors.','Connected same-floor lanes and service locations on all floors.'),
 ('facilities','Add dispatch, charging and wash facilities','layout','Add Dispatch, charger-equipped AMR bays, Clean store, Dirty receiving and Wash. In Dirty receiving Properties set Wash cycle required to Yes, Wash location to Wash and Wash duration (s) to 60; Apply changes. In Wash Properties set Service capacity (AMRs) to 1 and Apply changes.','Four compatible charging bays and a reachable wash station.'),
 ('transport','Configure transport','configuration','Configure four AMRs and Clean tote/Dirty cart payloads. Add L1 and L2 serving floors 0–2; check dimensions, speed and floor positions. Add the three service departments.','Four compatible robots, two payloads, departments and two complete lifts.'),
 ('policy','Define your flow policy','configuration','In Route profiles define clean and dirty allowed nodes and lifts. Choose dedicated lifts or shared access. Select a policy below only to describe your configuration; it does not alter it.','Payload routes obey the chosen permissions. Empty travel uses the existing model.'),
 ('demand','Generate deliveries and collections','configuration','In Demand generation configure Stores for clean delivery and Linen for dirty collection. Use 06:05, 06:35, 07:05, 07:35, three department scopes and 10-minute targets. Enable clean tote returns after 2 minutes. Open Demand preview.','Deterministic work serving all floors, both flows and return work.'),
 ('run','Check, save and run Simple','simulate','Run Project checks and correct findings. Save and choose Save, check and simulate. Use the two-hour 06:00–08:00 window.','A completed frozen Simple run linked to this project.'),
 ('investigate','Investigate and play back','review','Investigate the completed run. Select tasks and linked payload/lift records. Open Playback and follow a lift trip, charging and post-delivery washing.','Verified evidence includes both lifts, payload transitions, charging and washing.'),
 ('scenarios','Stress the design','configuration','Open Plan lift locations. Review drawing interpretation, confirm it, then evaluate the scenario suite for the current layout. Inspect each floor and flow in Review.','Baseline scenario evidence identifies distance, lift, wash and charging constraints.'),
 ('improve','Improve lift locations','configuration','In Plan lift locations generate sites, inspect connection overlays and evaluate proposals. Read the service guard and create a separate design variant.','A completed comparison and a safely saved improved variant, or an explained absence of improvement.'),
 ('report','Report and hand over','report','Select the frozen run and export PDF and CSV evidence. Reopen your project. Export the lift comparison and retain the original design.','Readable exports, reopened project and retained original run evidence.'),
)

EXTRA_LESSONS = (
 ('Advanced demand','Demand modes, dates, recurrence, scope groups, stock pools and zero-work explanations. Use Demand preview to verify each change.','configuration'),
 ('Inventory and exchanges','Create payload bays; constrain payloads and AMR bays separately. Test stock exhaustion, tracked items, return pools and wait-for-space.','layout'),
 ('Staff and people','Configure staff response/handling, shifts and working hours; preview a people-flow profile and compare a busy interval.','configuration'),
 ('Batching and route restrictions','Configure slots and multi-stop operation, then investigate shared legs and verify every onboard payload restriction.','configuration'),
 ('Drawing tools and layers','Practise Corridor, junctions, doors, copy/move/rotate, bounds, floor drawings, PDF underlays, model locks, DXF visibility and export.','layout'),
 ('Appearance and keyboard','Try themes, enlarged text, Focus canvas, panel proportions and keyboard selection. These preferences do not change simulation inputs.','project'),
 ('Recovery and run outcomes','Recover unsaved work; cancel a run; inspect failed and pending work. Preserve frozen inputs and understand stale checks.','simulate'),
 ('Relinking and evidence','Move a copied run folder, use Locate moved run, compare identities and export all selected evidence pages.','review'),
 ('Report options','Explore report sections, lift CSV, title, drawing heatmaps and insertion into an existing PDF.','report'),
 ('Detailed and historical settings','Read mode readiness and historical-value explanations. This course operates in Simple; Detailed engineering is a separate activity.','configuration'),
)


def _signature(row, identity):
    return {k:deepcopy(v) for k,v in row.items() if k!=identity}


class TutorialSession:
    def __init__(self, path=None):
        self.path=Path(path) if path else None
        self.state=dict(version=1, chapter=0, paused=False, completed={}, bindings={},
                        seen=[], policy='dedicated', run=None, study=None, reopened=False)
        self.warning=''
        self._saved_state=None
        if self.path and self.path.exists():
            try:
                saved=json.loads(self.path.read_text(encoding='utf-8'))
                if (saved.get('version')!=1 or not isinstance(saved.get('bindings'),dict)
                    or not isinstance(saved.get('completed'),dict) or not isinstance(saved.get('seen'),list)
                    or not isinstance(saved.get('chapter'),int) or not 0<=saved['chapter']<len(LESSONS)):
                    raise ValueError('Unsupported tutorial progress.')
                self.state.update(saved)
            except (OSError,ValueError,TypeError) as exc:
                self.warning=f'Progress could not be restored: {exc}. Start a new session or restore the companion file.'

    def save(self):
        if self.path:
            data=json.dumps(self.state,indent=2,allow_nan=False).encode('utf-8')
            if data!=self._saved_state:
                atomic_write(self.path,data)
                self._saved_state=data

    def observe(self, name):
        if name not in self.state['seen']: self.state['seen'].append(name)

    def bind(self, role, config, section, name):
        key='id' if section=='lifts' else 'name'
        rows=config.get(section,[])
        row=next((r for r in rows if r.get(key)==name),None)
        if row is None: raise ValueError('Choose an existing object.')
        self.state['bindings'][role]=dict(section=section,key=key,name=name,snapshot=_signature(row,key))

    def reconcile(self, config):
        missing=[]
        for role,b in self.state['bindings'].items():
            rows=config.get(b['section'],[])
            row=next((r for r in rows if r.get(b['key'])==b['name']),None)
            if row is None:
                matches=[r for r in rows if _signature(r,b['key'])==b['snapshot']]
                if len(matches)==1: row=matches[0]; b['name']=row[b['key']]
                else: missing.append(role); continue
            b['snapshot']=_signature(row,b['key'])
        return missing

    def roles(self, config):
        self.reconcile(config)
        return {k:b['name'] for k,b in self.state['bindings'].items()}

    def seed_bindings(self, config):
        for role,name in [('dispatch','Dispatch'),('clean_store','Clean store'),
                          ('dirty_receiving','Dirty receiving'),('wash','Wash')]:
            if role not in self.state['bindings'] and any(r.get('name')==name for r in config.get('locations',[])):
                self.bind(role,config,'locations',name)
        for floor in range(3):
            for flow in ('clean','dirty'):
                role=f'service_{flow}_{floor}';name=f'{flow.title()}-F{floor}'
                if role not in self.state['bindings'] and any(r.get('name')==name for r in config.get('locations',[])):
                    self.bind(role,config,'locations',name)
        for role,name in [('lift1','L1'),('lift2','L2')]:
            if role not in self.state['bindings'] and any(r.get('id')==name for r in config.get('lifts',[])):
                self.bind(role,config,'lifts',name)

    def check(self, chapter, config, context=None):
        """Return actionable failures, without trusting previously completed flags."""
        context=context or {}; issues=[]
        self.seed_bindings(config)
        missing=self.reconcile(config)
        roles=self.roles(config); locations={r['name']:r for r in config.get('locations',[])}
        def need(condition,message):
            if not condition: issues.append(message)
        key=LESSONS[chapter][0]
        if key in ('facilities','transport','policy','demand'):
            need(not missing,'Rebind missing tutorial objects: '+', '.join(missing))
        if key=='create':
            need(config.get('building',{}).get('floor_count')==3,'Create three floors.')
            need(config.get('building',{}).get('floor_height_m')==3.5,'Set the teaching floor height to 3.5 m.')
            need({r.get('floor') for r in config.get('floor_dxf_files',[])}=={0,1,2},'Assign all three floor DXFs.')
            need(context.get('saved',False),'Save as an AMR project.')
            outlines=[]
            for row in config.get('floor_dxf_files',[]):
                try:
                    from amr_lift_planning_geometry import extract_floor
                    g=extract_floor(row['filepath'],row['floor'])
                    need(abs(g['boundary_area_m2']-800)<.01,f"Floor {row['floor']} needs a closed 800 m² boundary.")
                    points=next(r['points'] for r in g['entities'] if r['role']=='boundary' and r['closed'])
                    bounds=(min(p[0] for p in points),min(p[1] for p in points),max(p[0] for p in points),max(p[1] for p in points))
                    need(abs(bounds[2]-bounds[0]-40)<.01 and abs(bounds[3]-bounds[1]-20)<.01,'Use the 40 × 20 m floor drawings.')
                    outlines.append(bounds)
                except (OSError,ValueError,KeyError) as exc: need(False,f'Drawing needs review: {exc}')
            need(not outlines or all(all(abs(a-b)<.01 for a,b in zip(outlines[0],outline)) for outline in outlines),'Register all floor drawings at a common origin.')
        elif key=='workbench':
            if context.get('history_changes',0)>0:self.observe('layout_edit')
            need('layout_edit' in self.state['seen'],'Make an undoable layout edit.')
            absent=set(('fit','snaps','selection','properties','undo','redo'))-set(self.state['seen'])
            need(not absent,'Practise: '+', '.join(sorted(absent)))
        elif key=='circulation':
            from amr_tutorial_circulation import inspect_all
            issues.extend(r['message'] for r in inspect_all(config,roles))
            need(len(config.get('corridors',{}).get('edges',[]))>=6,'Connect the circulation lanes.')
            need({r.get('floor') for r in config.get('locations',[])}=={0,1,2},'Add service locations on every floor.')
            points={r['name']:r['floor'] for r in config.get('locations',[])+config.get('corridors',{}).get('nodes',[])}
            need(not any(e['from'] in points and e['to'] in points and points[e['from']]!=points[e['to']]
                for e in config.get('corridors',{}).get('edges',[])),'Remove raw cross-floor corridor edges; use lifts.')
            from visualiser.project_checks import check_project
            errors=[f.message for f in check_project(config).findings if f.code in ('GRAPH_DISCONNECTED','CORRIDOR_INPUT','EDGE_CROSS_FLOOR')]
            issues.extend(errors)
            nodes=config.get('corridors',{}).get('nodes',[])
            need({r.get('floor') for r in nodes if r.get('has_door')}=={0,1,2},'Add door nodes on every floor.')
            for floor in (0,1,2):
                known={name for name,f in points.items() if f==floor};graph={name:set() for name in known}
                for edge in config.get('corridors',{}).get('edges',[]):
                    a,b=edge['from'],edge['to']
                    if a in known and b in known:
                        graph[a].add(b);graph[b].add(a)
                seen=set();queue=[next(iter(known))] if known else []
                while queue:
                    node=queue.pop()
                    if node in seen:continue
                    seen.add(node);queue.extend(graph[node]-seen)
                need(bool(known) and seen==known,f'Connect every service, door and circulation node on floor {floor}, including the shared transition.')
        elif key=='facilities':
            from amr_inventory_inputs import inventory_space_is_amr
            need(all(r in roles for r in ('dispatch','clean_store','dirty_receiving','wash')),'Create and bind all four facilities.')
            bays=[b for r in locations.values() for b in r.get('inventory_spaces',[]) if inventory_space_is_amr(b) and b.get('has_charger')]
            need(len(bays)>=4,'Provide four charger-equipped AMR bays.')
            receive=locations.get(roles.get('dirty_receiving'),{})
            need(receive.get('wash_cycle_required') and receive.get('wash_location')==roles.get('wash') and receive.get('wash_cycle_duration_sec',0)>0,
                 'Configure dirty receiving to require a positive-duration wash at the bound station.')
        elif key=='transport':
            need(sum(r.get('quantity',1) for r in config.get('amrs',[]))==4,'Configure four AMRs.')
            need(len(config.get('payloads',[]))>=2,'Define both payload types.')
            need(len(config.get('departments',[]))>=3,'Define the floor departments.')
            need(len(config.get('lifts',[]))>=2 and all(set(r.get('served_floors',[]))=={0,1,2} for r in config.get('lifts',[])),
                 'Provide two lifts serving all three floors.')
            from amr_lift_inputs import lift_input_findings
            issues.extend(msg for _,msg in lift_input_findings(config,require_complete=True,require_speed=True))
            from visualiser.project_checks import check_project
            issues.extend(f.message for f in check_project(config).findings if f.severity=='error')
        elif key=='policy':
            from amr_tutorial_values import route_issues
            issues.extend(route_issues(config,self.state['policy'],roles))
            profiles=config.get('route_profiles',{})
            need(all(profiles.get(k,{}).get('allowed_nodes') for k in ('clean','dirty')),'Define clean and dirty node permissions.')
            a=set(profiles.get('clean',{}).get('allowed_lifts',[])); b=set(profiles.get('dirty',{}).get('allowed_lifts',[]))
            need(bool(a) and bool(b),'Define lift permissions for both flows.')
            need(not a&b if self.state['policy']=='dedicated' else bool(a&b),'Lift permissions do not match your selected policy.')
        elif key=='demand':
            need(config.get('task_generation',{}).get('enabled'),'Enable demand generation.')
            try:
                from simulator import Simulation
                sim=Simulation(config); tasks=sim.task_generation_manager.update_until(7199)
                need(bool(tasks),'Demand configuration generates no teaching work.')
                need({r.task.route_profile for r in tasks}>={'clean','dirty'},'Generate both route profiles.')
                need(any(r.task.return_enabled for r in tasks),'Configure at least one return service.')
            except (ValueError,KeyError,TypeError) as exc: need(False,f'Repair demand inputs: {exc}')
            need('preview' in self.state['seen'],'Open Demand preview and inspect generated work.')
        elif key in ('run','investigate','report'):
            run=context.get('run')
            need(run is not None,'Choose a complete run belonging to this project.')
            if run:
                from amr_project_runs import validate_run_inputs,read_json
                try:
                    manifest,frozen=validate_run_inputs(run)
                    need(manifest.get('status')=='complete','Finish a complete run first.')
                    need(frozen.get('simulation',{}).get('mode')=='simple','Run explicitly in Simple mode.')
                    if key=='run': need(context.get('current_run',False),'Run the current saved revision.')
                    if key=='investigate':
                        from amr_lift_study import run_metrics
                        metrics=run_metrics(run)
                        need(metrics['wash_cycles']>0 and metrics['charging_cycles']>0,'Run must demonstrate washing and charging.')
                        need(len(metrics['lifts'])>=2,'Run must demonstrate both lifts.')
                        need(all(x in self.state['seen'] for x in ('investigation','playback')),'Open investigation and playback for this run.')
                    if key=='report':
                        need(any(Path(run).glob('reports/**/*.pdf')),'Generate a PDF under the selected frozen run.')
                        need(self.state.get('reopened'),'Reopen the saved project to verify handover.')
                    self.state['run']=str(run)
                except (OSError,ValueError,KeyError) as exc: need(False,f'Run evidence unavailable: {exc}')
        elif key in ('scenarios','improve'):
            study=context.get('study')
            need(bool(study),'Open a lift study and evaluate the scenario suite.')
            if study:
                need(not context.get('study_stale',True),'Study inputs changed; reevaluate.')
                need(study.get('baseline_complete',False),'Complete every baseline scenario.')
                if key=='improve':
                    need(study.get('status')=='complete','Complete candidate evaluations.')
                    need(bool(study.get('variant')) or study.get('recommendation') is None,
                         'Create a separate design variant for the recommended proposal.')
        self.state['completed'][key]=dict(passed=not issues, config_hash=config_hash(config), issues=issues)
        self.save()
        return issues

    def restart(self, chapter):
        self.state['completed'].pop(LESSONS[chapter][0],None); self.state['chapter']=chapter
        self.state['action']=0
        self.state['action_checks']={k:v for k,v in self.state.get('action_checks',{}).items() if not k.startswith(f'{chapter}:')}
        self.save()
