"""Per-action gates: opening an editor is never configuration completion."""
from pathlib import Path


def action_issues(session,chapter,index,config,context):
    issues=[];seen=set(session.state['seen']);building=config.get('building',{})
    def need(ok,text):
        if not ok:issues.append(text)
    session.seed_bindings(config);roles=session.roles(config)
    locations={r['name']:r for r in config.get('locations',[])}
    if chapter==0:
        if index==0:need(context.get('project_created'),'Create a project with File > New project, or save a working copy from Start from drawings.')
        elif index==1:
            need(building.get('floor_count')==3,'Set Number of floors to 3 and Save Building settings.')
            need(building.get('floor_height_m')==3.5,'Set Level height to 3.5 m and Save.')
        elif index==2:need({r.get('floor') for r in config.get('floor_dxf_files',[])}=={0,1,2},'Import an individual floor drawing for floors 0, 1 and 2.')
        elif index==3:
            need({'fit:0','fit:1','fit:2'}<=seen,'Click Fit on each of floors 0, 1 and 2 to inspect dimensions and alignment.')
            # Geometry validation and save are the chapter's final gate.
        else:need(context.get('saved') and not context.get('unsaved'),'Save the current project edits.')
    elif chapter==1:
        if index==0:need({'floor:0','floor:1','floor:2'}<=seen,'Visit floors 0, 1 and 2, then return to floor 0.');need(context.get('floor')==0,'Return to floor 0.')
        elif index==1:need('fit' in seen,'Click Fit.')
        elif index==2:need('snaps' in seen,'Use the grid/object snap controls.')
        elif index==3:need('selection' in seen and (context.get('history_changes',0)>0 or 'layout_edit' in seen),'Select a node and make a small undoable edit.')
        elif index==4:need('properties' in seen and not context.get('properties_open'),'Explicitly open Properties, inspect the node, then collapse it.')
        else:need({'undo','redo'}<=seen,'Use Undo and Redo on the edit.')
    elif chapter==2:
        from amr_tutorial_circulation import inspect_step
        return [r['message'] for r in inspect_step(config,index,roles)]
    elif chapter==3:
        if index==0:
            from amr_tutorial_placement import facility_issues
            issues.extend(r['message'] for r in facility_issues(config,roles))
        elif index==1:
            from amr_inventory_inputs import inventory_space_is_amr
            bays=locations.get(roles.get('dispatch'),{}).get('inventory_spaces',[])
            need(sum(inventory_space_is_amr(b) and b.get('has_charger',False) for b in bays)>=4,'Configure four charger-equipped AMR bays at Dispatch and Apply.')
        elif index==2:
            row=locations.get(roles.get('dirty_receiving'),{})
            need(row.get('wash_cycle_required') and row.get('wash_location')==roles.get('wash') and row.get('wash_cycle_duration_sec')==60,'In Dirty receiving Properties set Wash cycle required to Yes, Wash location to Wash and Wash duration (s) to 60, then click Apply changes.')
        else:need(locations.get(roles.get('wash'),{}).get('max_concurrency')==1,'Select Wash > Properties. Set Service capacity (AMRs) to 1 and click Apply changes.')
    elif chapter==4:
        from amr_tutorial_values import transport_issues
        issues.extend(transport_issues(index,config))
        if index==3:
            from amr_tutorial_placement import placement_issues
            issues.extend(r['message'] for r in placement_issues(chapter,index,config,roles))
    elif chapter==5:
        from amr_tutorial_values import route_issues
        issues.extend(issue for issue in route_issues(config,session.state['policy'],roles) if index!=0 or 'Allowed lifts' not in issue)
    elif chapter==6:
        if index in (0,1):
            from amr_tutorial_values import demand_issues
            issues.extend(demand_issues(index,config,roles))
        else:need('preview' in seen,'Open Demand preview and inspect the generated work.')
    elif chapter==7:
        if index==0:
            simulation=config.get('simulation',{})
            need(simulation.get('mode')=='simple' and simulation.get('start_datetime')=='2026-01-05T06:00:00' and simulation.get('end_datetime')=='2026-01-05T08:00:00','Save Simple mode with 5 January 2026, 06:00–08:00.')
        elif index==1:need(context.get('checks_current') and context.get('checks_ready'),'Run current Project checks and repair blocking findings.')
        else:need(context.get('run') and context.get('current_run'),'Complete a run of the current saved revision.')
    elif chapter==8:
        if index==0:need(context.get('investigation_ready'),'Investigate the selected completed run.')
        elif index==1:need(context.get('evidence_selected'),'Select a task and follow its linked payload or lift evidence.')
        else:need(context.get('playback_ready'),'Open Playback for the selected run.')
    elif chapter==9:
        study=context.get('study') or {}
        if index==0:need(context.get('geometry_ready'),'Infer and review geometry on all three floors.')
        elif index==1:need(study.get('confirmed') and not context.get('study_stale',True),'Confirm the current drawing interpretation.')
        else:
            need(not context.get('study_stale',True),'Infer and confirm the current interpretation before evaluating scenarios.')
            need(study.get('baseline_complete'),'Click Evaluate scenarios and follow the progress indicator until the baseline scenario suite completes.')
    elif chapter==10:
        study=context.get('study') or {}
        if index==0:
            need(not context.get('study_stale',True),'Infer and confirm the current interpretation before generating proposals.')
            need(len(study.get('proposals',{}))>=5,'Click Generate five layout proposals and follow the progress indicator, then review the layouts.')
        elif index==1:need(study.get('status')=='complete' and not context.get('study_stale',True),'Finish every comparable proposal scenario.')
        else:need(study.get('variant') or (study.get('status')=='complete' and study.get('recommendation') is None),'Create a separate variant of the recommended design, or review the explained absence of an improvement.')
    elif chapter==11:
        if index==0:need(context.get('report_ready'),'Open Report for the selected frozen run.')
        elif index==1:
            run=context.get('run');root=Path(run)/'reports' if run else None
            need(root and any(root.rglob('*.pdf')) and any(root.rglob('*.csv')),'Generate the selected run PDF and CSV exports.')
        elif index==2:need(context.get('comparison_exports'),'Export the study comparison as both PDF and CSV.')
        else:need(session.state.get('reopened') and not context.get('unsaved'),'Save and reopen the project with its companions and frozen evidence.')
    return issues
