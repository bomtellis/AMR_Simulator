"""Non-modal human study setup, background execution and inspectable evidence."""
from copy import deepcopy
import json
from pathlib import Path
import sys

from PySide6.QtCore import Qt, QProcess, QTimer, QEvent, QAbstractTableModel, QModelIndex
from PySide6.QtGui import QColor, QBrush, QPen
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QWidget,QTabWidget,
    QLabel,QPushButton,QListWidget,QListWidgetItem,QDoubleSpinBox,QSpinBox,QComboBox,QLineEdit,
    QCheckBox,QFileDialog,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,
    QGraphicsView,QGraphicsScene,QScrollArea,QSplitter,QPlainTextEdit,QGridLayout,QSizePolicy,QTableView)

from amr_contingency_inputs import initial_settings,carrying_estimate,validate_settings,DAYS,SHIFT_RULE_FIELDS
from amr_contingency_packing import OPERATOR_DEFAULTS
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


class StudyStatus(QPlainTextEdit):
    """Copyable bounded diagnostics; long errors never grow the dialog."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setAccessibleName('Study status and validation messages')
        self.setFixedHeight(self.fontMetrics().lineSpacing()*3+20)

    def setText(self, value):
        self.setPlainText(value)

    def text(self):
        return self.toPlainText()

    def changeEvent(self,event):
        super().changeEvent(event)
        if event.type()==QEvent.FontChange:
            self.setFixedHeight(self.fontMetrics().lineSpacing()*3+20)


def scroll_form(page):
    scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(page)
    scroll.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)
    return scroll


class TaskTimingModel(QAbstractTableModel):
    """Read result rows on demand instead of allocating cells for a week's work."""
    columns=[('Task','id'),('Service','service'),('Original release','original_release'),('Revised release','release'),
             ('Original deadline','original_deadline'),('Revised deadline','deadline'),
             ('Latest allowed release','latest_allowed_release'),('Reason','timing_reason')]

    def __init__(self,parent=None):
        super().__init__(parent);self.rows=[];self.state=None

    def set_result(self,state,rows):
        self.beginResetModel();self.state=state;self.rows=rows;self.endResetModel()

    def rowCount(self,parent=QModelIndex()):return 0 if parent.isValid() else len(self.rows)
    def columnCount(self,parent=QModelIndex()):return 0 if parent.isValid() else len(self.columns)

    def headerData(self,section,orientation,role=Qt.DisplayRole):
        if role==Qt.DisplayRole:
            return self.columns[section][0] if orientation==Qt.Horizontal else section+1

    def data(self,index,role=Qt.DisplayRole):
        if not index.isValid() or role!=Qt.DisplayRole:return None
        row=self.rows[index.row()];key=self.columns[index.column()][1]
        fallback={'original_release':'release','original_deadline':'deadline','latest_allowed_release':'release'}
        value=row.get(key,row.get(fallback.get(key,'')))
        if key in ('release','deadline',*fallback):return clock(self.state,value)
        return str(value) if value is not None else 'Original timing'


class HumanContingencyDialog(QDialog):
    def __init__(self,editor):
        super().__init__(editor)
        self.editor=editor;self.path=None;self.study=None;self.process=None;self.current_service=None
        self.setWindowTitle('Human contingency study');self.setModal(False);self.resize(1140,800)
        # Each form owns its scrolling; prevent the generic theme wrapper from
        # putting the status and action footer inside another scrolling page.
        self.setProperty('amrScrollWrapped',True)
        self.project_key=(getattr(editor.project,'project_id',None),editor.current_json_path)
        self.profile_values={};self.output_buffer=''
        layout=QVBoxLayout(self)
        intro=QLabel('Uses the project’s Task Generation, payloads and staff settings. '
                     'Two payloads per person are assumed initially. Review the prefilled carrying and shift assumptions, '
                     'then compare dedicated and shared teams.')
        intro.setWordWrap(True);layout.addWidget(intro)
        self.tabs=QTabWidget();layout.addWidget(self.tabs,1)
        page=QWidget();row=QHBoxLayout(page)
        self.services=QListWidget();self.services.setMinimumWidth(180);row.addWidget(self.services,1)
        scroll=QScrollArea();scroll.setWidgetResizable(True);row.addWidget(scroll,3)
        details=QWidget();form=QFormLayout(details);scroll.setWidget(details)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.release_mode=QComboBox()
        self.release_mode.addItem('Keep original task timing','fixed')
        self.release_mode.addItem('Align flexible tasks to staff shifts','staff_aligned')
        self.release_delay=number(120)
        self.release_mode.currentIndexChanged.connect(lambda:self.release_delay.setEnabled(self.release_mode.currentData()=='staff_aligned'))
        form.addRow('Category task timing',self.release_mode)
        form.addRow('Maximum delay (minutes)',self.release_delay)
        timing_note=QLabel('Flexible releases and deadlines move together, by no more than this delay. '
            'Scheduled tasks (such as catering) and explicit tasks retain their fixed times. '
            'Demand, stock consumption and return readiness still use the project’s Task Generation.')
        timing_note.setWordWrap(True);form.addRow(timing_note)
        self.fields={}
        for key,label,integer in [
            ('capacity_count','Payload capacity (count)',True),('capacity_kg','Total payload capacity (kg)',False),
            ('length_m','Corridor carrying length (m)',False),('width_m','Corridor carrying width (m)',False),
            ('height_m','Person + load height (m)',False),
            ('operator_length_m','Person space in lift: length (m)',False),
            ('operator_width_m','Person space in lift: width (m)',False),
            ('operator_height_m','Person space in lift: height (m)',False),
            ('empty_speed_mps','Empty walking speed (m/s)',False),
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
        note=QLabel('Prefilled from resolved service rules: permitted payloads, service base, walking speed and handling. '
                    'Pickup/unloading starts from the project’s load/unload time. '
                    'Editable planning estimate: payloads in line plus 0.6 m for the person; minimum width 0.6 m and height 1.8 m. '
                    'Weight allowance is the selected count × heaviest payload, not an ergonomic limit. '
                    'Inside lifts, payloads are rearranged and rotated as permitted, with separate space for each person. '
                    'Review these values for the carrying equipment you intend to use.')
        note.setWordWrap(True);form.addRow(note)
        self.profile_estimate=None
        self.fields['capacity_count'].valueChanged.connect(self.update_carrying_estimate)
        self.tabs.addTab(page,'Services and carrying')
        self.services.currentTextChanged.connect(self.select_service)
        page=QWidget();form=QFormLayout(page)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.shift_form=form
        self.shift_values={};self.current_shift_team=None
        self.shift_team=QComboBox();form.addRow('Configure team',self.shift_team)
        self.shift_override=QCheckBox('Use independent shift rules for this category');form.addRow(self.shift_override)
        self.shift_mode=QComboBox()
        self.shift_mode.addItem('Search start times and shift lengths','search')
        self.shift_mode.addItem('Use defined start and finish times','periods')
        form.addRow('Shift planning',self.shift_mode)
        self.periods=QPlainTextEdit();self.periods.setMaximumHeight(115)
        self.periods.setPlaceholderText('06:00–14:00\n14:00–22:00\n22:00–06:00')
        self.periods.setAccessibleName('Shift start and finish periods, one per line')
        form.addRow('Start–finish periods (one per line)',self.periods)
        self.lengths=QLineEdit('8');form.addRow('Allowed shift lengths (hours)',self.lengths)
        self.lengths.setToolTip('Allowed shift lengths in hours, separated by commas.')
        self.start_lo=QLineEdit('00:00');self.start_hi=QLineEdit('23:45')
        form.addRow('Earliest shift start (HH:MM)',self.start_lo);form.addRow('Latest shift start (HH:MM)',self.start_hi)
        self.days=QLineEdit(', '.join(DAYS));form.addRow('Active days',self.days)
        self.grid=number(15,True);self.max_people=number(20,True)
        self.break_minutes=number(30);self.break_after=number(4)
        form.addRow('Start-time grid (minutes)',self.grid);form.addRow('Maximum people in this team',self.max_people)
        form.addRow('Break duration (minutes)',self.break_minutes);form.addRow('Break starts after (hours)',self.break_after)
        form.addRow('Shared-team base',self.shared_base)
        self.confirmed=QCheckBox('I have reviewed the carrying assumptions and shift rules');form.addRow(self.confirmed)
        self.shift_team.currentIndexChanged.connect(self.select_shift_team)
        self.shift_override.toggled.connect(self.toggle_shift_override)
        self.shift_mode.currentIndexChanged.connect(self.update_shift_controls)
        note=QLabel('Dedicated category teams operate independently and are simulated together, sharing lift queues. '
                    'Select a category above to give it separate periods, days, breaks and staffing limits. '
                    'The search calculates the number of people in each period. A finish at or before the start means the next day. '
                    'Breaks are reserved at the configured offset. Every round returns to base; '
                    'no overtime is assumed. Shift lengths and active days are prefilled from project staff patterns. '
                    'Start windows, breaks and maximum staffing are editable study assumptions; staff numbers and start times are calculated by the search.')
        note.setWordWrap(True);form.addRow(note);self.tabs.addTab(scroll_form(page),'Shift rules')
        page=QWidget();form=QFormLayout(page)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        note=QLabel('Connected corridors, doors, inherited route permissions and mandatory floor waypoints apply. '
                    'Lift queues use the configured lift dimensions, travel and door times. Compatible units may share a departure. '
                    'Lift packing tries permitted payload rotations and different floor arrangements, including every person; loads are not stacked. '
                    'No extra passenger traffic is invented. Missing routes fail visibly.')
        note.setWordWrap(True);form.addRow(note)
        self.buffer=number(20);self.budget=number(200,True);self.round_limit=number(8,True)
        self.budget.setToolTip('Maximum trials for each comparison. The first is a no-staff baseline; a budget of one cannot produce a staffed recommendation.')
        form.addRow('Buffered walking and handling increase (%)',self.buffer)
        form.addRow('Trial budget per comparison',self.budget);form.addRow('Maximum tasks considered per round',self.round_limit)
        budget_note=QLabel('Each staffed trial simulates the full project period. A budget of one tests only the no-staff baseline; use a larger budget to search for a roster.')
        budget_note.setWordWrap(True);form.addRow(budget_note)
        self.tabs.addTab(scroll_form(page),'Routing and planning margin')
        page=QWidget();results=QVBoxLayout(page)
        self.summary=table();self.summary.setMaximumHeight(190);results.addWidget(self.summary)
        self.result_tabs=QTabWidget();results.addWidget(self.result_tabs,1)
        self.roster=table();self.rounds=table();self.stops=table();self.issues=table();self.metrics=table()
        self.task_timing=QTableView();self.timing_model=TaskTimingModel(self.task_timing);self.task_timing.setModel(self.timing_model)
        self.task_timing.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.task_timing.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.task_timing.horizontalHeader().setStretchLastSection(True)
        self.timeline=QGraphicsView();self.timeline.setAccessibleName('Shift coverage timeline')
        for w,label in [(self.roster,'Shifts'),(self.timeline,'Coverage'),(self.metrics,'Workload and time'),(self.task_timing,'Task timing'),(self.rounds,'Rounds'),(self.stops,'Stops'),(self.issues,'Unresolved work')]:
            self.result_tabs.addTab(w,label)
        self.summary.itemSelectionChanged.connect(self.show_variant)
        self.tabs.addTab(page,'Results')
        self.status=StudyStatus(self)
        self.status.setText('Setup is prefilled from the project. Review the carrying assumptions and shift rules before starting.')
        layout.addWidget(self.status)
        buttons=QGridLayout();layout.addLayout(buttons)
        self.controls=[]
        for title,callback in [('Save settings',self.save_settings),('New study and run…',self.new_study),
                               ('Open study…',self.open_study),('Run / resume',self.run_study),
                               ('Export CSV…',self.csv),('Export PDF…',self.pdf)]:
            b=QPushButton(title);b.clicked.connect(callback)
            index=len(self.controls);buttons.addWidget(b,index//4,index%4);self.controls.append(b)
        self.stop=QPushButton('Stop');self.stop.clicked.connect(self.cancel);self.stop.setEnabled(False);buttons.addWidget(self.stop,1,2)
        self.heartbeat=QTimer(self);self.heartbeat.setInterval(1000);self.heartbeat.timeout.connect(self.check_stale)
        self.set_settings(initial_settings(editor.store.data))
        self.heartbeat.start()

    def running(self):
        return self.process is not None and self.process.state()!=QProcess.NotRunning

    def flush_profile(self):
        if not self.current_service:return
        self.profile_values[self.current_service].update(
            **{k:w.value() for k,w in self.fields.items()},base=self.base.currentData(),
            release_policy=dict(version=1,mode=self.release_mode.currentData(),max_delay_minutes=self.release_delay.value()),
            route_profile=self.route.currentData(),
            payloads=[self.payloads.item(i).text() for i in range(self.payloads.count()) if self.payloads.item(i).checkState()==Qt.Checked])

    def select_service(self,name):
        self.flush_profile();self.current_service=name
        p=self.profile_values.get(name,{})
        policy=p.get('release_policy',dict(mode='fixed',max_delay_minutes=120))
        self.release_mode.setCurrentIndex(max(0,self.release_mode.findData(policy['mode'])))
        self.release_delay.setValue(policy['max_delay_minutes'])
        self.release_delay.setEnabled(policy['mode']=='staff_aligned')
        self.profile_estimate=None
        for k,w in self.fields.items():w.setValue(p.get(k,OPERATOR_DEFAULTS.get(k,0)))
        self.base.setCurrentIndex(max(0,self.base.findData(p.get('base',''))))
        self.route.setCurrentIndex(max(0,self.route.findData(p.get('route_profile'))))
        for i in range(self.payloads.count()):
            item=self.payloads.item(i);item.setCheckState(Qt.Checked if item.text() in p.get('payloads',[]) else Qt.Unchecked)
        self.profile_estimate=carrying_estimate(self.editor.store.data,p.get('payloads',[]),p.get('capacity_count',2))

    def update_carrying_estimate(self,count):
        if self.profile_estimate is None:return
        payloads=[self.payloads.item(i).text() for i in range(self.payloads.count()) if self.payloads.item(i).checkState()==Qt.Checked]
        estimate=carrying_estimate(self.editor.store.data,payloads,count)
        for key,value in estimate.items():
            # Retain dimensions/weight that the user has explicitly changed.
            if abs(self.fields[key].value()-self.profile_estimate[key]) < .001:
                self.fields[key].setValue(value)
        self.profile_estimate=estimate

    def set_settings(self,s):
        self.current_service=None;self.services.blockSignals(True);self.services.clear()
        self.profile_values=deepcopy(s['profiles'])
        for name in self.profile_values:
            item=QListWidgetItem(name);item.setCheckState(Qt.Checked if name in s['services'] else Qt.Unchecked);self.services.addItem(item)
        self.services.blockSignals(False);self.services.setCurrentRow(0)
        self.current_shift_team=None;self.shift_team.blockSignals(True);self.shift_team.clear()
        self.shift_values={'shared':deepcopy(s['shifts'])}
        self.shift_team.addItem('Shared team / category defaults','shared')
        for service,profile in self.profile_values.items():
            self.shift_team.addItem(service,service)
            self.shift_values[service]=deepcopy(profile.get('shift_rules'))
        self.shift_team.blockSignals(False);self.shift_team.setCurrentIndex(0);self.select_shift_team()
        self.shared_base.setCurrentIndex(max(0,self.shared_base.findData(s['shifts']['shared_base'])))
        self.confirmed.setChecked(s['shifts']['confirmed']);self.buffer.setValue(s['buffer_percent']);self.budget.setValue(s['trial_budget']);self.round_limit.setValue(s['max_round_tasks'])

    def read_shift_controls(self):
        periods=[]
        if self.shift_mode.currentData()=='periods':
            for line in self.periods.toPlainText().splitlines():
                if not line.strip():continue
                parts=line.replace('–','-').replace('—','-').split('-')
                if len(parts)!=2:raise ValueError('Enter each shift as HH:MM–HH:MM, one period per line.')
                periods.append(dict(start=parts[0].strip(),end=parts[1].strip()))
            if not periods:raise ValueError('Enter at least one shift start and finish period.')
        return dict(lengths_hours=[float(v.strip()) for v in self.lengths.text().split(',')],
            start_window=[self.start_lo.text(),self.start_hi.text()],days=[v.strip().lower() for v in self.days.text().split(',')],
            grid_minutes=self.grid.value(),max_people=self.max_people.value(),break_minutes=self.break_minutes.value(),
            break_after_hours=self.break_after.value(),periods=periods)

    def flush_shift_team(self):
        if self.current_shift_team is None:return
        self.shift_values[self.current_shift_team]=(self.read_shift_controls() if
            self.current_shift_team=='shared' or self.shift_override.isChecked() else None)

    def select_shift_team(self,*_):
        try:self.flush_shift_team()
        except ValueError as exc:
            self.status.setText(str(exc));self.shift_team.blockSignals(True)
            self.shift_team.setCurrentIndex(self.shift_team.findData(self.current_shift_team));self.shift_team.blockSignals(False)
            return
        self.current_shift_team=self.shift_team.currentData()
        r=dict(self.shift_values['shared']);r.update(self.shift_values.get(self.current_shift_team) or {})
        self.shift_override.blockSignals(True)
        self.shift_override.setChecked(self.current_shift_team!='shared' and self.shift_values.get(self.current_shift_team) is not None)
        self.shift_override.blockSignals(False)
        self.load_shift_controls(r)

    def load_shift_controls(self,r):
        self.shift_mode.setCurrentIndex(1 if r.get('periods') else 0)
        self.periods.setPlainText('\n'.join(p['start']+'–'+p['end'] for p in r.get('periods',[])))
        self.lengths.setText(', '.join(map(str,r['lengths_hours'])))
        self.start_lo.setText(r['start_window'][0]);self.start_hi.setText(r['start_window'][1]);self.days.setText(', '.join(r['days']))
        for widget,key in [(self.grid,'grid_minutes'),(self.max_people,'max_people'),(self.break_minutes,'break_minutes'),(self.break_after,'break_after_hours')]:widget.setValue(r[key])
        self.update_shift_controls()

    def toggle_shift_override(self,enabled):
        if not enabled and self.current_shift_team!='shared':
            self.shift_values[self.current_shift_team]=None
            self.load_shift_controls(self.shift_values['shared'])
        self.update_shift_controls()

    def update_shift_controls(self,*_):
        shared=self.current_shift_team=='shared'
        editable=shared or self.shift_override.isChecked()
        self.shift_override.setVisible(not shared)
        self.shift_mode.setEnabled(editable);self.shared_base.setEnabled(shared)
        periods=self.shift_mode.currentData()=='periods'
        self.periods.setEnabled(editable and periods)
        self.shift_form.setRowVisible(self.periods,periods)
        for widget in (self.lengths,self.start_lo,self.start_hi,self.grid):
            widget.setEnabled(editable and not periods);self.shift_form.setRowVisible(widget,not periods)
        for widget in (self.days,self.max_people,self.break_minutes,self.break_after):widget.setEnabled(editable)

    def settings(self):
        self.flush_profile();self.flush_shift_team()
        for service in self.profile_values:
            self.profile_values[service]['shift_rules']=deepcopy(self.shift_values.get(service))
        return dict(schema_version=1,services=[self.services.item(i).text() for i in range(self.services.count()) if self.services.item(i).checkState()==Qt.Checked],
            profiles=deepcopy(self.profile_values),shifts=dict(**{k:v for k,v in self.shift_values['shared'].items() if k in SHIFT_RULE_FIELDS},
                shared_base=self.shared_base.currentData(),confirmed=self.confirmed.isChecked()),
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
                self.show_progress(message)
            elif line.strip():self.status.setText(line[-1000:])

    def show_progress(self,message):
        if message.get('diagnostics'):
            self.status.setText('Setup prevents a passing roster:\n'+'\n'.join(message['diagnostics']))
        elif message.get('phase')=='simulating':
            best=message.get('best_hours')
            self.status.setText(f"{message['variant'].replace('_',' / ')}: trial {message['trial']} / {message['budget']}. "
                f"Simulated {message['simulated_hours']:g} / {message['horizon_hours']:g} hours; "
                f"{message['completed']} obligations completed. Trial elapsed: {message['elapsed_seconds']:g} s. "
                +(f'Best roster: {best:g} staffed hours.' if best is not None else 'No passing roster found yet.'))
        else:
            self.status.setText(f"{message.get('variant','Study')}: {message.get('trials','')} / {message.get('budget','')} trials. "
                               f"{message.get('unresolved','')} unresolved. {message.get('status','')}")

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
        diagnostics=list(dict.fromkeys(v for record in self.study['variants'].values() for v in record.get('diagnostics',[])))
        if diagnostics:
            self.status.setText('Setup prevents a passing roster:\n'+'\n'.join(diagnostics))
        else:
            self.status.setText(f"Study: {self.study['status']}. Lowest-hours passing roster found; not a proven global minimum.")
        self.tabs.setCurrentIndex(3);self.summary.selectRow(0)

    def show_variant(self):
        index=self.summary.currentRow()
        if not self.study or index<0:return
        record=self.study['variants'].get(VARIANTS[index],{})
        result=record.get('best') or record.get('current')
        if not result:
            for widget in (self.roster,self.rounds,self.stops,self.issues,self.metrics):widget.setRowCount(0)
            self.timing_model.set_result(self.study,[])
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
            if VARIANTS[index].startswith('dedicated'):
                values.extend([[service,'People at peak',totals.get('peak_people',0)],
                               [service,'Staffed hours',f"{totals.get('staffed_hours',0):.3f}"]])
        values.extend([['All services','Tasks with revised deadlines',result.get('retimed_tasks',0)],
                       ['All services','Maximum deadline delay (minutes)',result.get('maximum_deadline_delay_minutes',0)]])
        fill(self.metrics,['Service','Measure','Value'],values)
        fill(self.roster,['Person','Team','Start','End','Breaks','Base'],[
            [r['id'],r['pool'],fmt(r['start']),fmt(r['end']),'; '.join(fmt(a)+' – '+fmt(b) for a,b in r['breaks']),r['base']] for r in result['roster']])
        fill(self.rounds,['Round','Person','Service','Start','End','Tasks','Distance (m)'],[
            [r['id'],r['person'],r['service'],fmt(r['start']),fmt(r['end']),', '.join(r['tasks']),round(r['distance_m'],2)] for r in result['rounds']])
        fill(self.stops,['Round','Person','Service','Action','From','To','Start','End','Task','Lift arrangement'],[
            [r['round'],r['person'],r['service'],r['action'],r['origin'],r['destination'],fmt(r['start']),fmt(r['end']),r.get('task_id',''),r.get('lift_arrangement','')] for r in result['stops']])
        fill(self.issues,['Task','Service','Release','Deadline','Reason'],[
            [r['task'],r['service'],fmt(r['release']),fmt(r['deadline']),r['reason']] for r in result['unresolved']])
        self.timing_model.set_result(self.study,result['tasks'])
        scene=QGraphicsScene(self.timeline);self.timeline.setScene(scene)
        begin=min([r['start'] for r in result['roster']]+[0])
        end=max([r['end'] for r in result['roster']]+[1]);scale=850/(end-begin)
        for i in range(5):
            at=begin+(end-begin)*i/4
            scene.addText(fmt(at)).setPos(180+(at-begin)*scale,-32)
        for i,r in enumerate(result['roster']):
            y=i*30;scene.addText(r['id']+' / '+r['pool']).setPos(0,y)
            scene.addRect(180+(r['start']-begin)*scale,y+4,(r['end']-r['start'])*scale,18,QPen(Qt.NoPen),QBrush(QColor('#527fa5')))
            for a,b in r['breaks']:scene.addRect(180+(a-begin)*scale,y+4,(b-a)*scale,18,QPen(Qt.NoPen),QBrush(QColor('#efbf6b')))
        scene.addText('Blue: staffed shift. Amber: break. Exact dates and times are in Shifts.').setPos(0,len(result['roster'])*30+8)

    def check_stale(self):
        if self.running() or not self.study:return
        try:
            state=load_study(self.path,self.editor.store.data)
            if state['settings'] != self.settings():
                self.status.setText('Setup changed. Displayed results belong to the saved study; create a new study to evaluate these edits.')
        except (ValueError,OSError) as exc:self.status.setText(str(exc))

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
        else:
            self.heartbeat.stop()
            super().closeEvent(event)

    def showEvent(self,event):
        super().showEvent(event)
        self.heartbeat.start()
        QTimer.singleShot(0,self.fit_form_labels)

    def fit_form_labels(self):
        # Let QFormLayout move a field to the next row when space is tight.
        # Wrapped labels beside fixed-height editors can otherwise be clipped
        # by the shared theme after a font/scale change.
        for form in self.findChildren(QFormLayout):
            for row in range(form.rowCount()):
                item=form.itemAt(row,QFormLayout.LabelRole)
                if item and isinstance(item.widget(),QLabel):
                    item.widget().setWordWrap(False)
                    item.widget().setSizePolicy(QSizePolicy.Minimum,QSizePolicy.Preferred)
