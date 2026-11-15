"""Non-modal human study setup, background execution and inspectable evidence."""
from copy import deepcopy
import json
from pathlib import Path
import sys

from PySide6.QtCore import Qt, QProcess, QTimer
from PySide6.QtGui import QColor, QBrush, QPen
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QWidget,QTabWidget,
    QLabel,QPushButton,QListWidget,QListWidgetItem,QDoubleSpinBox,QSpinBox,QComboBox,QLineEdit,
    QCheckBox,QFileDialog,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,
    QGraphicsView,QGraphicsScene,QScrollArea,QSplitter)

from amr_contingency_inputs import default_settings,validate_settings,DAYS
from amr_contingency_study import create_study,load_study,VARIANTS
from amr_contingency_report import clock,export_csvs,export_pdf


def number(value=0,integer=False):
    widget=QSpinBox() if integer else QDoubleSpinBox()
    widget.setRange(0,100000)
    if not integer:widget.setDecimals(3)
    widget.setValue(value)
    return widget


def table():
    widget=QTableWidget();widget.setEditTriggers(QAbstractItemView.NoEditTriggers)
    widget.setSelectionBehavior(QAbstractItemView.SelectRows)
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    widget.horizontalHeader().setStretchLastSection(True)
    return widget


def fill(widget, headers, rows):
    widget.clear();widget.setColumnCount(len(headers));widget.setHorizontalHeaderLabels(headers)
    widget.setRowCount(len(rows))
    for row,values in enumerate(rows):
        for col,value in enumerate(values):widget.setItem(row,col,QTableWidgetItem(str(value)))


class HumanContingencyDialog(QDialog):
    def __init__(self,editor):
        super().__init__(editor)
        self.editor=editor;self.path=None;self.study=None;self.process=None;self.current_service=None
        self.setWindowTitle('Human contingency study');self.setModal(False);self.resize(1140,800)
        self.project_key=(getattr(editor.project,'project_id',None),editor.current_json_path)
        self.profile_values={};self.output_buffer=''
        layout=QVBoxLayout(self)
        intro=QLabel('Compare dedicated service teams and a shared team, at current and buffered timings. '
                     'People replace AMRs for the selected services; every round carries one service.')
        intro.setWordWrap(True);layout.addWidget(intro)
        self.tabs=QTabWidget();layout.addWidget(self.tabs,1)
        page=QWidget();row=QHBoxLayout(page)
        self.services=QListWidget();self.services.setMinimumWidth(180);row.addWidget(self.services,1)
        scroll=QScrollArea();scroll.setWidgetResizable(True);row.addWidget(scroll,3)
        details=QWidget();form=QFormLayout(details);scroll.setWidget(details)
        self.fields={}
        for key,label,integer in [
            ('capacity_count','Payload capacity (count)',True),('capacity_kg','Total payload capacity (kg)',False),
            ('length_m','Person + trolley length (m)',False),('width_m','Person + trolley width (m)',False),
            ('height_m','Person + load height (m)',False),('empty_speed_mps','Empty walking speed (m/s)',False),
            ('loaded_speed_mps','Loaded walking speed (m/s)',False),('pickup_seconds','Pickup per payload (seconds)',False),
            ('unload_seconds','Unload per payload (seconds)',False),('handling_minutes','Default department handling (minutes)',False)]:
            w=number(integer=integer);self.fields[key]=w;form.addRow(label,w)
        self.base=QComboBox();self.base.addItem('Select base…','')
        self.shared_base=QComboBox();self.shared_base.addItem('Select shared base…','')
        for loc in editor.store.data.get('locations',[]):
            self.base.addItem(loc['name'],loc['name']);self.shared_base.addItem(loc['name'],loc['name'])
        form.addRow('Service base',self.base)
        self.payloads=QListWidget();self.payloads.setMaximumHeight(140)
        for p in editor.store.data.get('payloads',[]):
            item=QListWidgetItem(p['name']);item.setCheckState(Qt.Unchecked);self.payloads.addItem(item)
        form.addRow('Permitted payloads',self.payloads)
        self.route=QComboBox();self.route.addItem('Inherit task route restrictions',None)
        for name in editor.store.data.get('route_profiles',{}):self.route.addItem(name,name)
        form.addRow('Human route override',self.route)
        note=QLabel('Capacity and envelope must be entered for each selected service. Existing department handling overrides remain effective. '
                    'Equipment is assumed available; one person operates each carrying unit.')
        note.setWordWrap(True);form.addRow(note)
        self.tabs.addTab(page,'Services and carrying')
        self.services.currentTextChanged.connect(self.select_service)
        page=QWidget();form=QFormLayout(page)
        self.lengths=QLineEdit('8');form.addRow('Allowed shift lengths (hours, comma-separated)',self.lengths)
        self.start_lo=QLineEdit('00:00');self.start_hi=QLineEdit('23:45')
        form.addRow('Earliest shift start (HH:MM)',self.start_lo);form.addRow('Latest shift start (HH:MM)',self.start_hi)
        self.days=QLineEdit(', '.join(DAYS));form.addRow('Active days',self.days)
        self.grid=number(15,True);self.max_people=number(20,True)
        self.break_minutes=number(30);self.break_after=number(4)
        form.addRow('Start-time grid (minutes)',self.grid);form.addRow('Maximum simultaneous people',self.max_people)
        form.addRow('Break duration (minutes)',self.break_minutes);form.addRow('Break starts after (hours)',self.break_after)
        form.addRow('Shared-team base',self.shared_base)
        self.confirmed=QCheckBox('I have reviewed these operational shift and break rules');form.addRow(self.confirmed)
        note=QLabel('Shifts may cross midnight. Breaks are reserved at the configured offset. Every round returns to base; '
                    'no overtime is assumed. Staffed hours include breaks. The study uses the project’s demand period.')
        note.setWordWrap(True);form.addRow(note);self.tabs.addTab(page,'Shift rules')
        page=QWidget();form=QFormLayout(page)
        note=QLabel('Connected corridors, doors, inherited route permissions and mandatory floor waypoints apply. '
                    'Lift queues use the configured lift dimensions, travel and door times. Compatible units may share a departure. '
                    'No extra passenger traffic is invented. Missing routes fail visibly.')
        note.setWordWrap(True);form.addRow(note)
        self.buffer=number(20);self.budget=number(200,True);self.round_limit=number(8,True)
        form.addRow('Buffered walking and handling increase (%)',self.buffer)
        form.addRow('Trial budget per comparison',self.budget);form.addRow('Maximum tasks considered per round',self.round_limit)
        self.tabs.addTab(page,'Routing and planning margin')
        page=QWidget();results=QVBoxLayout(page)
        self.summary=table();self.summary.setMaximumHeight(190);results.addWidget(self.summary)
        self.result_tabs=QTabWidget();results.addWidget(self.result_tabs,1)
        self.roster=table();self.rounds=table();self.stops=table();self.issues=table();self.metrics=table()
        self.timeline=QGraphicsView();self.timeline.setAccessibleName('Shift coverage timeline')
        for w,label in [(self.roster,'Shifts'),(self.timeline,'Coverage'),(self.metrics,'Workload and time'),(self.rounds,'Rounds'),(self.stops,'Stops'),(self.issues,'Unresolved work')]:
            self.result_tabs.addTab(w,label)
        self.summary.itemSelectionChanged.connect(self.show_variant)
        self.tabs.addTab(page,'Results')
        self.status=QLabel('Enter carrying capacities and review shift rules before starting.');self.status.setWordWrap(True)
        layout.addWidget(self.status)
        buttons=QHBoxLayout();layout.addLayout(buttons)
        self.controls=[]
        for title,callback in [('Save settings',self.save_settings),('New study and run…',self.new_study),
                               ('Open study…',self.open_study),('Run / resume',self.run_study),
                               ('Export CSV…',self.csv),('Export PDF…',self.pdf)]:
            b=QPushButton(title);b.clicked.connect(callback);buttons.addWidget(b);self.controls.append(b)
        self.stop=QPushButton('Stop');self.stop.clicked.connect(self.cancel);self.stop.setEnabled(False);buttons.addWidget(self.stop)
        self.heartbeat=QTimer(self);self.heartbeat.setInterval(1000);self.heartbeat.timeout.connect(self.check_stale)
        stored=editor.store.data.get('human_contingency',{})
        self.set_settings(stored.get('settings',default_settings(editor.store.data)))
        self.heartbeat.start()

    def running(self):
        return self.process is not None and self.process.state()!=QProcess.NotRunning

    def flush_profile(self):
        if not self.current_service:return
        self.profile_values[self.current_service]=dict(
            **{k:w.value() for k,w in self.fields.items()},base=self.base.currentData(),
            route_profile=self.route.currentData(),
            payloads=[self.payloads.item(i).text() for i in range(self.payloads.count()) if self.payloads.item(i).checkState()==Qt.Checked])

    def select_service(self,name):
        self.flush_profile();self.current_service=name
        p=self.profile_values.get(name,{})
        for k,w in self.fields.items():w.setValue(p.get(k,0))
        self.base.setCurrentIndex(max(0,self.base.findData(p.get('base',''))))
        self.route.setCurrentIndex(max(0,self.route.findData(p.get('route_profile'))))
        for i in range(self.payloads.count()):
            item=self.payloads.item(i);item.setCheckState(Qt.Checked if item.text() in p.get('payloads',[]) else Qt.Unchecked)

    def set_settings(self,s):
        self.current_service=None;self.services.blockSignals(True);self.services.clear()
        self.profile_values=deepcopy(s['profiles'])
        for name in self.profile_values:
            item=QListWidgetItem(name);item.setCheckState(Qt.Checked if name in s['services'] else Qt.Unchecked);self.services.addItem(item)
        self.services.blockSignals(False);self.services.setCurrentRow(0)
        r=s['shifts'];self.lengths.setText(', '.join(map(str,r['lengths_hours'])))
        self.start_lo.setText(r['start_window'][0]);self.start_hi.setText(r['start_window'][1]);self.days.setText(', '.join(r['days']))
        for widget,key in [(self.grid,'grid_minutes'),(self.max_people,'max_people'),(self.break_minutes,'break_minutes'),(self.break_after,'break_after_hours')]:widget.setValue(r[key])
        self.shared_base.setCurrentIndex(max(0,self.shared_base.findData(r['shared_base'])))
        self.confirmed.setChecked(r['confirmed']);self.buffer.setValue(s['buffer_percent']);self.budget.setValue(s['trial_budget']);self.round_limit.setValue(s['max_round_tasks'])

    def settings(self):
        self.flush_profile()
        return dict(schema_version=1,services=[self.services.item(i).text() for i in range(self.services.count()) if self.services.item(i).checkState()==Qt.Checked],
            profiles=deepcopy(self.profile_values),shifts=dict(lengths_hours=[float(v.strip()) for v in self.lengths.text().split(',')],
                start_window=[self.start_lo.text(),self.start_hi.text()],days=[v.strip().lower() for v in self.days.text().split(',')],
                grid_minutes=self.grid.value(),max_people=self.max_people.value(),break_minutes=self.break_minutes.value(),
                break_after_hours=self.break_after.value(),shared_base=self.shared_base.currentData(),confirmed=self.confirmed.isChecked()),
            buffer_percent=self.buffer.value(),trial_budget=self.budget.value(),max_round_tasks=self.round_limit.value(),seed=0)

    def save_settings(self):
        try:
            self.editor.save_contingency_settings(self.settings(),str(self.path) if self.path else None)
            self.status.setText('Contingency settings updated. Save the project to retain them.')
        except Exception as exc:self.status.setText(str(exc))

    def new_study(self):
        if self.running() or not self.editor._project_editing_allowed():return
        try:
            s=validate_settings(self.editor.store.data,self.settings())
            name,_=QFileDialog.getSaveFileName(self,'New human contingency study','human-contingency.json','Study (*.json)')
            if not name:return
            self.study=create_study(self.editor.store.data,s,name);self.path=Path(name)
            self.editor.save_contingency_settings(s,str(self.path));self.run_study()
        except Exception as exc:self.status.setText(str(exc))

    def open_study(self):
        name,_=QFileDialog.getOpenFileName(self,'Open human contingency study','','Study (*.json)')
        if not name:return
        try:
            self.study=load_study(name);self.path=Path(name);self.set_settings(self.study['settings']);self.refresh_results();self.check_stale()
        except Exception as exc:self.status.setText(str(exc))

    def run_study(self):
        if self.running() or not self.path:return
        try:
            saved=load_study(self.path,self.editor.store.data,for_resume=True)
            if saved['settings'] != self.settings():
                raise ValueError('Setup differs from this saved study. Create a new study for the changed settings, or reopen the saved study to resume it.')
            cancel=Path(str(self.path)+'.cancel');cancel.unlink(missing_ok=True)
            self.process=QProcess(self);self.process.setProcessChannelMode(QProcess.MergedChannels)
            self.process.readyReadStandardOutput.connect(self.read_output)
            self.process.finished.connect(self.worker_finished);self.process.errorOccurred.connect(self.process_error)
            root=Path(__file__).resolve().parents[1]
            args=['--human-contingency-study',str(self.path)]
            if not getattr(sys,'frozen',False):args.insert(0,str(root/'amr_app.py'))
            self.process.setWorkingDirectory(str(root));self.process.start(sys.executable,args)
            for b in self.controls:b.setEnabled(False)
            for i in range(3):self.tabs.setTabEnabled(i,False)
            self.stop.setEnabled(True);self.tabs.setCurrentIndex(3)
            self.status.setText('Running human contingency comparisons…')
            self.editor.sync_project_editing_lock()
        except Exception as exc:self.status.setText(str(exc))

    def read_output(self):
        self.output_buffer+=bytes(self.process.readAllStandardOutput()).decode('utf-8',errors='replace')
        lines=self.output_buffer.split('\n');self.output_buffer=lines.pop()[-4000:]
        for line in lines:
            if line.startswith('CONTINGENCY '):
                message=json.loads(line[len('CONTINGENCY '):])
                self.status.setText(f"{message.get('variant','Study')}: {message.get('trials','')} / {message.get('budget','')} trials. "
                                   f"{message.get('unresolved','')} unresolved. {message.get('status','')}")
            elif line.strip():self.status.setText(line[-1000:])

    def worker_finished(self,code=0,*args):
        if self.process:self.read_output()
        process,self.process=self.process,None
        if process:process.deleteLater()
        for b in self.controls:b.setEnabled(True)
        for i in range(3):self.tabs.setTabEnabled(i,True)
        self.stop.setEnabled(False);self.editor.sync_project_editing_lock()
        try:self.study=load_study(self.path);self.refresh_results()
        except Exception as exc:self.status.setText(str(exc))
        if code:self.status.setText('Study failed: '+(self.study or {}).get('error',self.output_buffer))

    def process_error(self,error):
        if error==QProcess.FailedToStart:self.worker_finished(1)

    def cancel(self):
        if self.path and self.running():
            Path(str(self.path)+'.cancel').write_text('cancel',encoding='utf-8')
            self.status.setText('Stopping after the current safe checkpoint…')

    def refresh_results(self):
        if not self.study:return
        rows=[]
        for name in VARIANTS:
            record=self.study['variants'].get(name,{})
            result=record.get('best')
            rows.append([name.replace('_',' / '),record.get('status','Not evaluated'),record.get('trials',0),
                         result['peak_people'] if result else '—',f"{result['staffed_hours']:.2f}" if result else 'No passing roster',
                         result['trips'] if result else '—'])
        fill(self.summary,['Comparison','Search status','Trials','Peak people','Staffed hours','Trips'],rows)
        self.status.setText(f"Study: {self.study['status']}. Lowest-hours passing roster found; not a proven global minimum.")
        self.tabs.setCurrentIndex(3);self.summary.selectRow(0)

    def show_variant(self):
        index=self.summary.currentRow()
        if not self.study or index<0:return
        record=self.study['variants'].get(VARIANTS[index],{})
        result=record.get('best') or record.get('current')
        if not result:
            for widget in (self.roster,self.rounds,self.stops,self.issues,self.metrics):widget.setRowCount(0)
            self.timeline.setScene(QGraphicsScene(self.timeline))
            return
        fmt=lambda v:clock(self.study,v)
        values=[['All services',label,f'{result[key]:.3f}'] for label,key in
            [('Staffed hours','staffed_hours'),('Active hours','active_hours'),('Break hours','break_hours'),
             ('Walking hours','walking_hours'),('Handling hours','handling_hours'),('Lift hours','lift_hours'),
             ('Lift waiting hours','lift_wait_hours'),('Completed obligations','completed'),('Total obligations','obligations')]]
        for service,totals in result.get('services',{}).items():
            values.extend([[service,'Active hours',f"{totals['active_hours']:.3f}"],
                           [service,'Rounds',totals['trips']],[service,'Completed obligations',totals['completed']]])
        fill(self.metrics,['Service','Measure','Value'],values)
        fill(self.roster,['Person','Team','Start','End','Breaks','Base'],[
            [r['id'],r['pool'],fmt(r['start']),fmt(r['end']),'; '.join(fmt(a)+' – '+fmt(b) for a,b in r['breaks']),r['base']] for r in result['roster']])
        fill(self.rounds,['Round','Person','Service','Start','End','Tasks','Distance (m)'],[
            [r['id'],r['person'],r['service'],fmt(r['start']),fmt(r['end']),', '.join(r['tasks']),round(r['distance_m'],2)] for r in result['rounds']])
        fill(self.stops,['Round','Person','Service','Action','From','To','Start','End','Task'],[
            [r['round'],r['person'],r['service'],r['action'],r['origin'],r['destination'],fmt(r['start']),fmt(r['end']),r.get('task_id','')] for r in result['stops']])
        fill(self.issues,['Task','Service','Release','Deadline','Reason'],[
            [r['task'],r['service'],fmt(r['release']),fmt(r['deadline']),r['reason']] for r in result['unresolved']])
        scene=QGraphicsScene(self.timeline);self.timeline.setScene(scene)
        end=max([r['end'] for r in result['roster']]+[1]);scale=850/end
        for i in range(5):
            at=end*i/4
            scene.addText(fmt(at)).setPos(180+at*scale,-32)
        for i,r in enumerate(result['roster']):
            y=i*30;scene.addText(r['id']+' / '+r['pool']).setPos(0,y)
            scene.addRect(180+r['start']*scale,y+4,(r['end']-r['start'])*scale,18,QPen(Qt.NoPen),QBrush(QColor('#527fa5')))
            for a,b in r['breaks']:scene.addRect(180+a*scale,y+4,(b-a)*scale,18,QPen(Qt.NoPen),QBrush(QColor('#efbf6b')))
        scene.addText('Blue: staffed shift. Amber: break. Exact dates and times are in Shifts.').setPos(0,len(result['roster'])*30+8)

    def check_stale(self):
        if self.running() or not self.study:return
        try:
            state=load_study(self.path,self.editor.store.data)
            if state['settings'] != self.settings():
                self.status.setText('Setup changed. Displayed results belong to the saved study; create a new study to evaluate these edits.')
        except ValueError as exc:self.status.setText(str(exc))

    def csv(self):
        if not self.path:return
        name=QFileDialog.getExistingDirectory(self,'Export contingency CSVs')
        if name:
            try:self.status.setText(f'Exported {len(export_csvs(self.path,name))} CSV files.')
            except Exception as exc:self.status.setText(str(exc))

    def pdf(self):
        if not self.path:return
        name,_=QFileDialog.getSaveFileName(self,'Export contingency PDF','human-contingency.pdf','PDF (*.pdf)')
        if name:
            try:export_pdf(self.path,name);self.status.setText('Saved '+name)
            except Exception as exc:self.status.setText(str(exc))

    def closeEvent(self,event):
        if self.running():
            self.status.setText('Stop the study or wait for completion before closing.');event.ignore()
        else:super().closeEvent(event)
