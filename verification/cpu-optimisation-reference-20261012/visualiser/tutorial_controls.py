"""Tutorial targets resolved from real fields, including closed tabs and lists.

Guidance only reveals a scroll position. Opening a tab, editing a value and
saving remain user actions; a draft never changes the project's completion.
"""
from PySide6.QtCore import Qt, QDateTime
import json
from PySide6.QtWidgets import (QAbstractButton, QAbstractSpinBox, QComboBox,
    QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QPlainTextEdit,
    QScrollArea, QTabWidget)


def reveal(widget):
    if widget is None:return None
    widget.setProperty('amrTutorialHint',None)
    # Outer tabs precede inner tabs: every returned target is currently visible.
    ancestors=[];parent=widget.parentWidget()
    while parent:
        if isinstance(parent,QTabWidget):ancestors.append(parent)
        parent=parent.parentWidget()
    for tabs in reversed(ancestors):
        tabs.tabBar().setProperty('amrTutorialHint',None)
        for index in range(tabs.count()):
            page=tabs.widget(index)
            if page is widget or page.isAncestorOf(widget):
                if tabs.currentIndex()!=index:
                    target=reveal(tabs.tabBar())
                    return (tabs.tabBar(),tabs.tabBar().tabRect(index)) if target else None
                break
    parent=widget.parentWidget()
    while parent:
        if isinstance(parent,QScrollArea):parent.ensureWidgetVisible(widget,0,20)
        parent=parent.parentWidget()
    return (widget,None) if widget.isVisible() else None


def button(root,text):
    return next((w for w in root.findChildren(QAbstractButton)
                 if w.text().replace('&','').rstrip('… .').casefold()==text.rstrip('… .').casefold()),None)


def labelled(root,label):
    for text in root.findChildren(QLabel):
        if text.text().replace('&','').casefold()!=label.casefold():continue
        if text.buddy():return text.buddy()
        for layout in root.findChildren(QFormLayout):
            row,_=layout.getWidgetPosition(text)
            if row<0:continue
            item=layout.itemAt(row,QFormLayout.FieldRole)
            if item is None:continue
            if item.widget():return item.widget()
            if item.layout():
                def controls(part):
                    for n in range(part.count()):
                        child=part.itemAt(n)
                        if child.widget():yield child.widget()
                        elif child.layout():yield from controls(child.layout())
                candidates=list(controls(item.layout()))
                return next((w for w in candidates if isinstance(w,QAbstractButton)),candidates[0] if candidates else None)
    return None


def value(widget):
    if isinstance(widget,QComboBox):return widget.currentData() if widget.currentData() is not None else widget.currentText()
    if isinstance(widget,QAbstractSpinBox) and hasattr(widget,'value'):return widget.value()
    if isinstance(widget,QAbstractButton):return widget.isChecked()
    if isinstance(widget,QPlainTextEdit):return widget.toPlainText().strip()
    if isinstance(widget,QLineEdit):return widget.text().strip()
    return None


def matches(actual,expected):
    if callable(expected):return expected(actual)
    if isinstance(expected,(int,float)) and not isinstance(expected,bool):
        try:return abs(float(actual)-expected)<1e-7
        except (ValueError,TypeError):return False
    return actual==expected


def field_target(widget,expected,display=None):
    target=reveal(widget)
    if not target:return None
    label=widget.accessibleName() or (widget.text() if isinstance(widget,QAbstractButton) else '')
    for layout in widget.window().findChildren(QFormLayout):
        text=layout.labelForField(widget)
        if not label and isinstance(text,QLabel):label=text.text()
    if display is not None or not callable(expected):
        if display is None:
            display='Yes' if expected is True else 'No' if expected is False else f'{expected:g}' if isinstance(expected,(int,float)) else str(expected)
            if isinstance(widget,QComboBox):
                position=widget.findData(expected)
                if position>=0:display=widget.itemText(position)
            suffix=widget.suffix().strip() if hasattr(widget,'suffix') else ''
            if suffix and suffix not in label:display+=' '+suffix
        detail=f'{label or "Field"}: {display}'
        if target[0] is not widget and hasattr(target[0],'tabText'):
            index=target[0].tabAt(target[1].center());detail=f'Open {target[0].tabText(index)} > '+detail
        target[0].setProperty('amrTutorialHint',detail)
    return target


def first_field(dialog,fields):
    for field in fields:
        attribute,expected=field[:2];display=field[2] if len(field)>2 else None
        widget=getattr(dialog,attribute,None)
        if widget is not None and not matches(value(widget),expected):return field_target(widget,expected,display)
    box=dialog.findChild(QDialogButtonBox)
    if box:
        return reveal(box.button(QDialogButtonBox.Save) or box.button(QDialogButtonBox.Ok))
    return reveal(button(dialog,'Save'))


def list_item(widget,predicate):
    for index in range(widget.count()):
        item=widget.item(index)
        if predicate(item):
            widget.scrollToItem(item)
            target=reveal(widget)
            return (widget.viewport(),widget.visualItemRect(item)) if target and target[0] is widget else target
    return reveal(widget)


def dialog_target(bubble,dialog):
    chapter,index,_=bubble.current();name=type(dialog).__name__
    config=bubble.editor.store.data
    roles=bubble.course.session.roles(config)
    if chapter==5 and dialog.inherits('QInputDialog') and type(dialog.parentWidget()).__name__=='RouteProfilesEditorV2':
        parent=dialog.parentWidget();expected='clean' if 'clean' not in parent.profiles else 'dirty'
        widget=dialog.findChild(QLineEdit)
        if widget:widget.setAccessibleName('Profile name')
        if widget and widget.text()!=expected:return field_target(widget,expected)
        return first_field(dialog,[])
    if name=='MultiSelectPicker':
        parent=dialog.parentWidget();parent_name=type(parent).__name__
        wanted=None
        if chapter==4 and index==2 and parent_name=='DepartmentEditorDialog':
            position=parent.location_category_list.currentRow()
            if position>=0:
                key=parent.task_generation_categories[position][0];floor=parent.floor_edit.value()
                wanted={roles.get(f'service_{"clean" if key=="stores" else "dirty"}_{floor}',f'{"Clean" if key=="stores" else "Dirty"}-F{floor}')}
        elif chapter==5 and parent_name=='RouteProfilesEditorV2':
            flow=parent.current_profile
            lifts=['L1','L2'] if bubble.course.session.state['policy']=='shared' else ['L1' if flow=='clean' else 'L2']
            if dialog.windowTitle()=='Pick lifts':wanted=set(lifts)
            elif dialog.windowTitle()=='Pick nodes':
                from amr_tutorial_values import route_nodes
                wanted=route_nodes(config,flow,lifts,roles)
        elif chapter==6 and parent_name in ('TaskGenerationSettingsDialog','BulkDepartmentTaskGenerationDialog'):
            if 'department' in dialog.windowTitle().lower():wanted={option for option in dialog.options if any(option.startswith(identity) for identity in ('D0','D1','D2'))}
            else:wanted={roles.get('dirty_receiving','Dirty receiving')}
        if wanted is not None:
            for option in dialog.options:
                check=dialog.checkboxes.get(option)
                if check and check.isChecked()!=(option in wanted):return field_target(check,option in wanted)
                if check is None and option in wanted:return field_target(dialog.filter_edit,option)
            return first_field(dialog,[])
    if chapter==0 and index==1 and name=='BuildingSettingsDialog':
        return first_field(dialog,[('floor_count',3),('level_height',3.5)])
    if chapter==4:
        if index==0 and name=='AMRPayloadSlotDialog':
            return first_field(dialog,[('weight_spin',100),('length_spin',1.2),('width_spin',.9),('height_spin',1.5),('lengthways_check',True)])
        if index==0 and name=='AMREditorDialog':
            fields=[('id_edit','Teaching AMR'),('quantity_edit',4),('amr_length_edit',1),('amr_width_edit',.7),
                    ('speed_edit',1.5),('motor_power_edit',96),('battery_capacity_edit',.1),('charge_rate_edit',2),
                    ('recharge_threshold_edit',20),('battery_soc_edit',15)]
            for attribute,expected in fields:
                if not matches(value(getattr(dialog,attribute)),expected):return field_target(getattr(dialog,attribute),expected)
            slots=dialog.payload_slots
            if len(slots)!=1 or any(slots[0].get(key)!=expected for key,expected in
                [('payload_capacity_kg',100),('payload_length_capacity_m',1.2),('payload_width_capacity_m',.9),('payload_height_capacity_m',1.5)]):
                if dialog.slots_table.currentRow()<0:return field_target(dialog.slots_table,None,'Select the first slot, then Edit selected')
                return field_target(button(dialog,'Edit selected'),None,'100 kg; length 1.2 m, width 0.9 m, height 1.5 m')
            return first_field(dialog,[])
        if index==1 and name=='PayloadEditorDialog':
            names={r.get('name') for r in config.get('payloads',[])}
            expected='Clean tote' if 'Clean tote' not in names else 'Dirty cart'
            return first_field(dialog,[('name_edit',lambda v:v in ('Clean tote','Dirty cart') or v==expected,expected),
                ('length_edit',.8),('width_edit',.6),('height_edit',1),('weight_edit',20),
                ('lengthways_check',True),('sideways_check',False)])
        if index==2 and name=='DepartmentEditorDialog':
            try:floor=int(dialog.id_edit.text().removeprefix('D'))
            except ValueError:floor=next((n for n in range(3) if f'D{n}' not in {r.get('id') for r in config.get('departments',[])}),0)
            floor=max(0,min(2,floor))
            fields=[('id_edit',f'D{floor}'),('name_edit',f'Floor {floor} service'),('floor_edit',floor),
                    ('enabled_check',True),('operating_start_edit','06:00'),('operating_end_edit','08:00')]
            for attribute,expected in fields:
                if not matches(value(getattr(dialog,attribute)),expected):return field_target(getattr(dialog,attribute),expected)
            for key,location in [('stores',f'Clean-F{floor}'),('linen',f'Dirty-F{floor}')]:
                if location not in dialog.category_location_selections.get(key,[]):
                    titles=[str(item[1]) for item in dialog.task_generation_categories]
                    position=next((n for n,item in enumerate(dialog.task_generation_categories) if item[0]==key),None)
                    if position is None:return None
                    target=reveal(dialog.location_category_list)
                    if target and target[0] is not dialog.location_category_list:return target
                    if dialog.location_category_list.currentRow()!=position:
                        return list_item(dialog.location_category_list,lambda item:item.text()==titles[position])
                    page=dialog.location_category_pages.widget(position)
                    return field_target(button(page,'Select'),None,location)
            return first_field(dialog,[])
        if index==3 and name=='LiftEditorDialog':
            next_name=next((name for name in ('L1','L2') if name not in {r.get('id') for r in config.get('lifts',[])}),'L1')
            fields=[('id_edit',lambda v:v in ('L1','L2'),next_name),('floors_edit',lambda v:{p.strip() for p in str(v).split(',')}=={'0','1','2'},'0,1,2'),
                    ('start_floor_edit',0),('speed_edit',1.75),('door_edit',4),('board_edit',3),
                    ('capacity_length_edit',2),('capacity_width_edit',2),('capacity_height_edit',2.5),('health_loss_edit',0)]
            for field in fields:
                attribute,expected=field[:2]
                if not matches(value(getattr(dialog,attribute)),expected):return field_target(getattr(dialog,attribute),expected,field[2] if len(field)>2 else None)
            expected_x=34 if dialog.id_edit.text()=='L1' else 38
            table=dialog.stop_positions_table
            for row in range(table.rowCount()):
                for column,expected in [(1,expected_x),(2,10)]:
                    if not matches(table.item(row,column).text(),expected):
                        target=reveal(table)
                        if target and target[0] is table:
                            table.scrollToItem(table.item(row,column))
                            table.viewport().setProperty('amrTutorialHint',f'Floor {table.item(row,0).text()} > {"X" if column==1 else "Y"} (m): {expected}')
                            return table.viewport(),table.visualItemRect(table.item(row,column))
                        return target
            return first_field(dialog,[])
        if name in ('AMRListDialog','PayloadListDialog','DepartmentListDialog','LiftListDialog'):
            section={'AMRListDialog':'amrs','PayloadListDialog':'payloads','DepartmentListDialog':'departments','LiftListDialog':'lifts'}[name]
            rows=getattr(dialog,'items',getattr(getattr(dialog,'store',None),'data',{}).get(section,[]))
            identity='name' if section=='payloads' else 'id'
            names={'amrs':['Teaching AMR'],'payloads':['Clean tote','Dirty cart'],'departments':['D0','D1','D2'],'lifts':['L1','L2']}[section]
            if any(name not in {r.get(identity) for r in rows} for name in names):return reveal(button(dialog,'Add'))
            from amr_tutorial_values import transport_issues
            issues=transport_issues(index,{**config,section:rows})
            if issues:
                row=next((n for n,r in enumerate(rows) if str(r.get(identity)) in issues[0]),0)
                if section=='departments':
                    item=dialog._index_to_tree_item.get(row)
                    if item and not item.isSelected():
                        dialog.table.scrollToItem(item);return dialog.table.viewport(),dialog.table.visualItemRect(item)
                elif dialog.table.currentRow()!=row:
                    item=dialog.table.item(row,0);dialog.table.scrollToItem(item)
                    return dialog.table.viewport(),dialog.table.visualItemRect(item)
                return reveal(button(dialog,'Edit') or button(dialog,'Edit selected'))
            return reveal(button(dialog,'Save') or button(dialog,'Close'))
    if chapter==5 and name=='RouteProfilesEditorV2':
        if index==2:return reveal(button(dialog,'Save All'))
        if dialog.current_profile not in ('clean','dirty'):return reveal(button(dialog,'Add'))
        required_lifts=['L1','L2'] if bubble.course.session.state['policy']=='shared' else ['L1' if dialog.current_profile=='clean' else 'L2']
        if index==1 and set(dialog.allowed_lifts)!=set(required_lifts):return field_target(labelled(dialog,'Allowed lifts'),None,', '.join(required_lifts))
        if index in (0,1):
            from amr_tutorial_values import route_nodes,route_edges
            lifts=['L1','L2'] if bubble.course.session.state['policy']=='shared' else ['L1' if dialog.current_profile=='clean' else 'L2']
            missing=route_nodes(config,dialog.current_profile,lifts,roles)-set(dialog.allowed_nodes)
            wrong=set(dialog.allowed_nodes)-route_nodes(config,dialog.current_profile,lifts,roles)
            try:edges={tuple(pair) for pair in json.loads(dialog.edges_text.toPlainText().strip() or '[]')}
            except (ValueError,TypeError):edges=set()
            if missing or wrong or edges!=route_edges(config,dialog.current_profile,lifts,roles):
                return field_target(dialog.graphical_nodes_btn,None,'Select the highlighted nodes and corridor edges on floors 0, 1 and 2; Finish selection')
            saved=dialog.profiles.get(dialog.current_profile,{})
            if set(saved.get('allowed_nodes',[]))!=set(dialog.allowed_nodes) or {tuple(p) for p in saved.get('allowed_edges',[])}!=edges or index==1 and set(saved.get('allowed_lifts',[]))!=set(dialog.allowed_lifts):return reveal(button(dialog,'Apply Changes'))
            from amr_tutorial_values import route_issues
            pending=route_issues({**config,'route_profiles':dialog.profiles},bubble.course.session.state['policy'],roles)
            for flow in ('clean','dirty'):
                if flow!=dialog.current_profile and any(f'> {flow} >' in issue and (index==1 or 'Allowed lifts' not in issue) for issue in pending):
                    return list_item(dialog.profile_list,lambda item:item.text()==flow) if flow in dialog.profiles else reveal(button(dialog,'Add'))
            return reveal(button(dialog,'Save All'))
    if chapter==6 and name in ('TaskGenerationSettingsDialog','BulkDepartmentTaskGenerationDialog'):
        if hasattr(dialog,'global_enabled') and not dialog.global_enabled.isChecked():return field_target(dialog.global_enabled,True)
        key=getattr(dialog,'current_key',getattr(dialog,'category_key',None))
        if key not in ('stores','linen'):
            return list_item(dialog.category_list,lambda item:item.data(Qt.UserRole)=='stores') if hasattr(dialog,'category_list') else None
        if hasattr(dialog,'current_department_id') and not dialog.current_department_id:return reveal(dialog.department_list)
        if name=='BulkDepartmentTaskGenerationDialog' and not dialog.selected_department_ids:return reveal(button(dialog,'Select departments'))
        fields=[('enabled_check',True),('mode_combo','scheduled'),('requires_staff_check',False),('target_time_edit',600)]
        clean=key=='stores'
        if index==0:
            fields += [('payload_combo','Clean tote' if clean else 'Dirty cart'),('route_profile_combo','clean' if clean else 'dirty')]
            if hasattr(dialog,'role_dropoff_radio'):fields += [('role_dropoff_radio' if clean else 'role_pickup_radio',True)]
            if clean:fields += [('pickup_combo',roles.get('clean_store','Clean store'))]
        else:
            fields += [('return_enabled_check',clean)]
            if clean:fields += [('return_payload_combo','Clean tote'),('return_profile_combo','clean'),('return_delay_edit',2)]
        for attribute,expected in fields:
            widget=getattr(dialog,attribute,None)
            if widget is not None and not matches(value(widget),expected):return field_target(widget,expected)
        if index==0 and not clean and not getattr(dialog,'selected_dropoffs',[]):
            return field_target(getattr(dialog,'pick_dropoffs_btn',button(dialog,'Select')),None,roles.get('dirty_receiving','Dirty receiving'))
        if index==1 and set(dialog.scheduled_times)!={'06:05','06:35','07:05','07:35'}:
            return field_target(getattr(dialog,'schedule_button',button(dialog,'Edit times')),None,'06:05, 06:35, 07:05, 07:35')
        if name=='TaskGenerationSettingsDialog':
            from amr_tutorial_values import demand_issues
            pending=demand_issues(index,{**config,'task_generation':dialog.config},roles)
            for wanted_key in ('stores','linen'):
                for identity in ('D0','D1','D2'):
                    if wanted_key==key and identity==dialog.current_department_id:continue
                    cfg=dialog.config['categories'].get(wanted_key,{})
                    scoped=cfg.get('departments',{}).get(identity,{})
                    missing=not scoped.get('enabled') and not any(identity in group.get('departments',[]) and group.get('payload',{}).get('enabled') for group in cfg.get('department_groups',[]))
                    incorrect=any(issue.startswith(f'{wanted_key.title()} > {identity}') for issue in pending)
                    if missing or incorrect:
                        if wanted_key!=key:return list_item(dialog.category_list,lambda item:item.data(Qt.UserRole)==wanted_key)
                        return list_item(dialog.department_list,lambda item:item.data(Qt.UserRole)==identity)
        return first_field(dialog,[])
    if chapter==6 and name=='ScheduledTimesDialog':
        missing=[t for t in ('06:05','06:35','07:05','07:35') if t not in dialog.times]
        if missing:
            if dialog.time_edit.time().toString('HH:mm')==missing[0]:return field_target(button(dialog,'Add time'),None,missing[0])
            return field_target(dialog.time_edit,missing[0],f'{missing[0]} — then click Add time')
        if set(dialog.times)!={'06:05','06:35','07:05','07:35'}:return reveal(dialog.list_widget)
        return first_field(dialog,[])
    if chapter==7 and index==0 and name=='SimulationSettingsDialog':
        if dialog.mode_combo.currentData()!='simple':return field_target(dialog.mode_combo,'simple')
        if dialog.start_datetime_edit.dateTime()!=QDateTime.fromString('2026-01-05T06:00:00',Qt.ISODate):return field_target(dialog.start_datetime_edit,None,'5 January 2026, 06:00')
        if not dialog.use_end_datetime_check.isChecked():return field_target(dialog.use_end_datetime_check,True)
        if dialog.end_datetime_edit.dateTime()!=QDateTime.fromString('2026-01-05T08:00:00',Qt.ISODate):return field_target(dialog.end_datetime_edit,None,'5 January 2026, 08:00')
        return first_field(dialog,[])
    if chapter==7 and index==2 and name=='RunChecksDialog':return reveal(dialog.run_button)
    return None


def workspace_target(bubble):
    chapter,index,_=bubble.current();editor=bubble.editor
    if chapter==5:
        from route_profile_graphics import tutorial_route_target
        target=tutorial_route_target(bubble)
        if target:return target
        menu=editor.workbench.layout_menu
        if menu.isVisible():return menu,menu.actionGeometry(editor.workbench.route_profiles_action)
        return editor.menuBar(),editor.menuBar().actionGeometry(menu.menuAction())
    if chapter==1 and editor.workspace.stage=='layout':
        if index==2:return reveal(editor.snap_controls.master)
        if index==3:
            if not editor.store.all_points():return reveal(editor.cad_toolbar.widgetForAction(editor.cad_toolbar.mode_actions['corridor_node']))
            if not editor.selected_point_name and not editor.selected_point_names:return reveal(editor.canvas.viewport())
            if editor.cad_move_input.isVisible():
                return reveal(editor.cad_move_input.apply_button) if editor.cad_move_input.offset.text().strip()=='0.1,0' else field_target(editor.cad_move_input.offset,'0.1,0')
        if index in (3,5):
            action=editor.workbench.move_action if index==3 else editor.redo_action if 'undo' in bubble.course.session.state['seen'] else editor.undo_action
            menu=editor.workbench.edit_menu
            if menu.isVisible():return menu,menu.actionGeometry(action)
            bar=editor.menuBar();return bar,bar.actionGeometry(menu.menuAction())
    if (chapter,index) in ((7,2),(8,0),(8,2),(11,0)):
        panel=getattr(editor,'project_runs_panel',None)
        if panel and panel.isVisible():
            if (chapter,index)==(7,2):return reveal(panel.start_button)
            if panel.runs.currentRow()<0:return reveal(panel.runs)
            label={(8,0):'Investigate selected run',(8,2):'Playback selected run',(11,0):'Report selected run'}[(chapter,index)]
            return reveal(button(panel,label))
    if (chapter,index)==(7,1):
        panel=getattr(editor,'checks_panel',None)
        if panel and panel.isVisible():return reveal(panel.refresh_button)
    if (chapter,index)==(8,1):
        panel=getattr(editor,'results_panel',None)
        if panel and panel.isVisible():return reveal(panel.follow if panel.selected_evidence and panel.follow.isEnabled() else panel.tasks)
    if (chapter,index)==(6,2):
        panel=getattr(editor,'demand_panel',None)
        if panel and panel.isVisible():return reveal(panel.build_button)
        panel=getattr(editor,'checks_panel',None)
        if panel and panel.isVisible():return reveal(panel.demand_preview_button)
    if (chapter,index)==(11,1):
        panel=getattr(editor,'report_panel',None)
        if panel and panel.isVisible():
            if not any(panel.sections.item(n).checkState()==Qt.Checked for n in range(panel.sections.count())):return reveal(panel.sections)
            return reveal(panel.start)
    planner=getattr(editor,'lift_planner',None)
    if planner and planner.isVisible() and chapter in (9,10,11):
        if chapter in (9,10) and (chapter==10 or index>0):
            if planner.running():
                target=reveal(planner.progress_label)
                if target:target[0].setProperty('amrTutorialHint','Work is running. Follow the progress indicator; Stop cancels while retaining completed evidence.')
                return target
            needed=planner.preparation_needed()
            if needed:
                target=reveal(needed[0])
                if target:target[0].setProperty('amrTutorialHint',needed[1])
                return target
        if chapter==9:
            return reveal(button(planner,'Infer drawings') if index==0 else planner.confirmed if index==1 else planner.evaluate)
        if chapter==10:
            if index==0:
                for key,expected in [('shaft_length_m',2),('shaft_width_m',2),('landing_depth_m',1),('clearance_m',.1)]:
                    if not matches(planner.options[key].value(),expected):return field_target(planner.options[key],expected)
                for checkbox in planner.movable.values():
                    if not checkbox.isChecked():return field_target(checkbox,True)
                return reveal(planner.generate)
            if index==1:return reveal(planner.evaluate)
            return reveal(planner.proposals if planner.proposals.currentRow()<0 else planner.variant)
        if index==2:
            exports=(planner.study or {}).get('tutorial_exports',{})
            return reveal(button(planner,'Export comparison PDF' if exports.get('csv') else 'Export comparison CSV'))
    return None
