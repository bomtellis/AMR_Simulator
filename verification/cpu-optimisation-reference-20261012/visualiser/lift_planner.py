"""Optional lift study with explicit geometry confirmation and frozen evidence."""
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import sys
import tempfile
import re
import time

from PySide6.QtCore import QProcess,QProcessEnvironment,QTimer,QRectF,Qt,QThreadPool,Slot
from PySide6.QtGui import QColor,QBrush,QPen,QPainterPath
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QTabWidget,QWidget,
    QFormLayout,QComboBox,QDoubleSpinBox,QTableWidget,QTableWidgetItem,QGraphicsView,QGraphicsScene,
    QPushButton,QPlainTextEdit,QFileDialog,QMessageBox,QCheckBox,QScrollArea,QInputDialog,QGridLayout,QHeaderView,QProgressBar)

from amr_lift_planning_geometry import (ROLES,default_role,extract_floor,_shape,
    generate_sites,build_proposals,transform)
from amr_lift_study import (create_study,input_identity,write_record,export_comparison,relink_result)


class LiftPlanner(QDialog):
    def __init__(self,editor):
        super().__init__(editor);self.editor=editor;self.study=None;self.path=None;self.process=None
        self._proposal_job=None;self._work_message='';self._work_started=0
        self._worker_output='';self._worker_line='';self._worker_error='';self._evaluation_cancelled=False
        self.geometries=[];self._geometry_identity=None;self._layer_floor=None;self.layer_roles={};self.registrations={};self.units={}
        self.exclusions={};self._reading=False
        self.setWindowTitle('Plan lift locations');self.resize(1050,730);self.setModal(False)
        # Each tab already scrolls; retain the fixed action footer when the
        # application's generic small-screen dialog polishing runs later.
        self.setProperty('amrScrollWrapped',True)
        layout=QVBoxLayout(self)
        self.status=QLabel('Infer and review drawing geometry before evaluating aligned lift sites.');self.status.setWordWrap(True);layout.addWidget(self.status)
        self.tabs=QTabWidget();layout.addWidget(self.tabs,1)
        page=QWidget();v=QVBoxLayout(page);self.tabs.addTab(page,'Interpretation')
        row=QHBoxLayout();self.floor=QComboBox();self.floor.setAccessibleName('Planning drawing floor')
        row.addWidget(QLabel('Floor'));row.addWidget(self.floor)
        infer=QPushButton('Infer drawings');infer.clicked.connect(self.infer);row.addWidget(infer);self.infer_button=infer
        register=QPushButton('Align floor…');register.clicked.connect(self.align_floor);row.addWidget(register);self.register_button=register
        exclude=QPushButton('Exclude area…');exclude.clicked.connect(self.exclude_area);row.addWidget(exclude);self.exclude_button=exclude
        row.addStretch();v.addLayout(row)
        self.layers=QTableWidget(0,2);self.layers.setHorizontalHeaderLabels(['DXF layer','Planning role']);self.layers.setMaximumHeight(180)
        self.layers.horizontalHeader().setStretchLastSection(True);v.addWidget(self.layers)
        self.geometry_scene=QGraphicsScene(self);self.geometry_view=QGraphicsView(self.geometry_scene);v.addWidget(self.geometry_view,1)
        self.confirmed=QCheckBox('I reviewed units, boundaries, circulation, exclusions and floor alignment.');v.addWidget(self.confirmed)
        self.confirmed.toggled.connect(self.confirm)
        self.floor.currentIndexChanged.connect(self.show_floor)

        page=QWidget();v=QVBoxLayout(page);self.tabs.addTab(page,'Proposals')
        self.proposal_floor=QComboBox();self.proposal_floor.setAccessibleName('Proposal overlay floor')
        self.proposal_floor.currentIndexChanged.connect(lambda i:self.floor.setCurrentIndex(i));v.addWidget(self.proposal_floor)
        form=QFormLayout();self.options={}
        for key,label,value in [('shaft_length_m','Shaft length',2),('shaft_width_m','Shaft width',2),
            ('landing_depth_m','Landing depth',1),('clearance_m','Clearance',.1)]:
            spin=QDoubleSpinBox();spin.setRange(0 if key=='clearance_m' else .1,30);spin.setDecimals(2);spin.setSuffix(' m');spin.setValue(value)
            form.addRow(label,spin);self.options[key]=spin;spin.valueChanged.connect(self.option_changed)
        v.addLayout(form);self.retained=QHBoxLayout();v.addLayout(self.retained);self.movable={}
        self.generate=QPushButton('Generate five layout proposals');self.generate.clicked.connect(self.propose);v.addWidget(self.generate)
        self.proposals=QTableWidget(0,5);self.proposals.setHorizontalHeaderLabels(['Layout','Service guard','Worst on-time','Distance change (m)','Lift wait change (s)'])
        self.proposals.horizontalHeader().setStretchLastSection(True);self.proposals.setSelectionBehavior(QTableWidget.SelectRows)
        self.proposals.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.proposals.currentCellChanged.connect(self.proposal_selected);v.addWidget(self.proposals)
        self.proposal_scene=QGraphicsScene(self);self.proposal_view=QGraphicsView(self.proposal_scene);v.addWidget(self.proposal_view,1)
        note=QLabel('Sites are geometrically screened proposals. Review structural feasibility. Lift count, equipment and flow permissions stay fixed.');note.setWordWrap(True);v.addWidget(note)

        page=QWidget();v=QVBoxLayout(page);self.tabs.addTab(page,'Scenarios')
        self.scenarios=QTableWidget(0,7);self.scenarios.setHorizontalHeaderLabels(['Layout','Scenario','Floor / flow','Completed','Failed / pending','On-time','Horizontal (m)'])
        self.scenarios.horizontalHeader().setStretchLastSection(True);self.scenarios.setSelectionBehavior(QTableWidget.SelectRows);v.addWidget(self.scenarios,1)
        self.scenarios.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        row=QHBoxLayout()
        for label,fn in [('Investigate run',self.investigate),('Playback run',self.playback),('Report run',self.report),('Locate moved run…',self.relink)]:
            b=QPushButton(label);b.clicked.connect(fn);row.addWidget(b)
        v.addLayout(row)
        note=QLabel('Service is compared for each department floor and flow; destination floors remain in the CSV evidence. '
            'Washing applies to AMRs. Relocation cannot restore a prohibited backup route or add lift capacity.');note.setWordWrap(True);v.addWidget(note)
        page=QWidget();v=QVBoxLayout(page);self.tabs.addTab(page,'Evidence')
        self.details=QPlainTextEdit();self.details.setReadOnly(True);v.addWidget(self.details)
        row=QHBoxLayout()
        for label,fn in [('Export comparison CSV…',self.export),('Export comparison PDF…',self.export_pdf)]:
            b=QPushButton(label);b.clicked.connect(fn);row.addWidget(b)
        v.addLayout(row)
        self.progress_label=QLabel('Confirm the current drawing interpretation before generating proposals or evaluating scenarios.')
        self.progress_label.setWordWrap(True);self.progress_label.setTextFormat(Qt.PlainText)
        self.progress_label.setAccessibleName('Lift planning progress');layout.addWidget(self.progress_label)
        self.progress=QProgressBar();self.progress.setAccessibleName('Lift planning progress indicator');self.progress.hide();layout.addWidget(self.progress)
        row=QGridLayout();self.evaluate=QPushButton('Evaluate scenarios');self.evaluate.clicked.connect(self.start)
        self.stop=QPushButton('Stop evaluation');self.stop.clicked.connect(self.cancel)
        self.variant=QPushButton('Create design variant…');self.variant.clicked.connect(self.create_variant)
        self.apply=QPushButton('Apply selected layout');self.apply.clicked.connect(self.apply_selected)
        close=QPushButton('Close');close.clicked.connect(self.close)
        self.close_button=close
        row.addWidget(self.evaluate,0,0);row.addWidget(self.stop,0,1);row.addWidget(close,0,2,2,1)
        row.addWidget(self.variant,1,0);row.addWidget(self.apply,1,1)
        layout.addLayout(row)
        for n in range(self.tabs.count()):
            page=self.tabs.widget(n);label=self.tabs.tabText(n);self.tabs.removeTab(n)
            scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(page);self.tabs.insertTab(n,scroll,label)
        for lift in editor.store.data.get('lifts',[]):
            b=QCheckBox('Move '+lift['id']);b.setChecked(True);b.toggled.connect(self.option_changed);self.retained.addWidget(b);self.movable[lift['id']]=b
        for name,spin in self.options.items():
            if editor.store.data.get('lifts'):spin.setValue(editor.store.data['lifts'][0].get({'clearance_m':'shaft_clearance_m'}.get(name,name),spin.value()))
        self.refresh_project();self.timer=QTimer(self);self.timer.setInterval(1500);self.timer.timeout.connect(self.refresh_state);self.timer.start()

    def running(self):return self.process is not None or self._proposal_job is not None

    @Slot(str,int)
    def work_feedback(self,message,value=None):
        self._work_message=message;self.status.setText(message);self.progress_label.setText(message)
        self.progress.show();self.progress.setRange(0,0 if value is None else 100)
        if value is not None:self.progress.setValue(value)

    def preparation_needed(self):
        if self.running():return None
        if self.study and self.study.get('confirmed') and not self.stale():return None
        try:inferred=self._geometry_identity==input_identity(self.editor.store.data) and bool(self.geometries)
        except (OSError,ValueError):inferred=False
        if not inferred or self.study and self.stale():
            return self.infer_button,'Infer drawings, review every floor, then confirm the current interpretation.'
        return self.confirmed,'Review the floor overlays and tick the interpretation confirmation to save and freeze the study.'

    def refresh_project(self):
        if self.running():return
        p=self.editor.project
        path=Path(str(p.path)+'.lift-study.json') if p and p.path else None
        if path!=self.path:
            self.study=None;self.geometries=[];self.layer_roles={};self.registrations={};self.units={};self._layer_floor=None
            self.exclusions={};self._geometry_identity=None
            self.confirmed.blockSignals(True);self.confirmed.setChecked(False);self.confirmed.blockSignals(False)
            self.proposals.setRowCount(0);self.scenarios.setRowCount(0);self.details.clear()
        self.path=path
        if self.path and self.path.exists():
            try:
                s=json.loads(self.path.read_text(encoding='utf-8'))
                if s.get('version')!=1:raise ValueError('Unsupported lift study.')
                self.study=s;self.geometries=s.get('geometry') or [];self.exclusions=s.get('options',{}).get('excluded',{})
                self.layer_roles={g['floor']:g['roles'] for g in self.geometries}
                self.registrations={g['floor']:g['registration'] for g in self.geometries}
                self.units={g['floor']:g['unit_scale'] for g in self.geometries}
                self._geometry_identity=s['source_identity']
                self.confirmed.blockSignals(True);self.confirmed.setChecked(s.get('confirmed',False));self.confirmed.blockSignals(False)
            except (OSError,ValueError,KeyError) as exc:self.status.setText(f'Study could not restore: {exc}')
        self.populate_floors();self.refresh_state()

    def stale(self):
        if not self.study:return True
        try:
            from amr_run_evidence import software_snapshot
            return (self.study['source_identity']!=input_identity(self.editor.store.data)
                or self.study['software_sha256']!=software_snapshot()['sha256'])
        except (OSError,ValueError,KeyError):return True

    def populate_floors(self):
        self._reading=True;self.floor.clear();self.proposal_floor.blockSignals(True);self.proposal_floor.clear()
        for row in self.editor.store.data.get('floor_dxf_files',[]):
            self.floor.addItem(f"Floor {row['floor']}",row['floor']);self.proposal_floor.addItem(f"Overlay: floor {row['floor']}",row['floor'])
        self.proposal_floor.blockSignals(False)
        self._reading=False;self.show_floor()

    def capture_roles(self):
        if self._layer_floor is None:return
        self.layer_roles[self._layer_floor]={self.layers.item(n,0).text():self.layers.cellWidget(n,1).currentText() for n in range(self.layers.rowCount())}

    def show_floor(self,*_):
        if self._reading:return
        self.capture_roles();floor=self.floor.currentData();self._layer_floor=floor
        self.layers.setRowCount(0)
        row=next((r for r in self.editor.store.data.get('floor_dxf_files',[]) if r['floor']==floor),None)
        if row:
            try:
                import ezdxf
                doc=ezdxf.readfile(row['filepath'])
                names=sorted({str(layer.dxf.name) for layer in doc.layers}|set(self.layer_roles.get(floor,{})))
                for name in names:
                    n=self.layers.rowCount();self.layers.insertRow(n);item=QTableWidgetItem(name);item.setFlags(item.flags()&~Qt.ItemIsEditable);self.layers.setItem(n,0,item)
                    combo=QComboBox();combo.addItems(ROLES);combo.setCurrentText(self.layer_roles.get(floor,{}).get(name,default_role(name)))
                    combo.currentIndexChanged.connect(self.invalidate_geometry);self.layers.setCellWidget(n,1,combo)
            except (OSError,ValueError) as exc:self.status.setText(str(exc))
        self.draw_geometry(self.geometry_scene,self.geometry_view,floor)
        self.proposal_floor.blockSignals(True);self.proposal_floor.setCurrentIndex(self.floor.currentIndex());self.proposal_floor.blockSignals(False)
        if self.study:self.draw_geometry(self.proposal_scene,self.proposal_view,floor,self.selected_proposal())

    def invalidate_geometry(self,*_):
        self.confirmed.blockSignals(True);self.confirmed.setChecked(False);self.confirmed.blockSignals(False)
        self._geometry_identity=None
        if self.study:
            self.study['confirmed']=False
            if self.path:write_record(self.path,self.study)
        self.refresh_state()

    def infer(self):
        if self.running():return
        self.capture_roles()
        try:
            config=self.editor.store.data;geometries=[]
            for row in config.get('floor_dxf_files',[]):
                f=row['floor'];geometries.append(extract_floor(row['filepath'],f,self.layer_roles.get(f),
                    self.registrations.get(f),self.units.get(f)))
            if not geometries:raise ValueError('Assign floor drawings first.')
            self.geometries=geometries;self._geometry_identity=input_identity(config)
            self.layer_roles={g['floor']:g['roles'] for g in geometries};self.show_floor()
            self.status.setText('Geometry inferred. Review every floor overlay and confirm the interpretation.')
            self.confirmed.blockSignals(True);self.confirmed.setChecked(False);self.confirmed.blockSignals(False)
            self.refresh_state()
        except Exception as exc:self.status.setText(f'Drawing interpretation needs repair: {exc}');self.invalidate_geometry()

    def align_floor(self):
        f=self.floor.currentData()
        if f is None:return
        values=self.registrations.get(f,dict(dx=0,dy=0,rotation_deg=0))
        for key,label in [('dx','X offset (m)'),('dy','Y offset (m)'),('rotation_deg','Rotation (degrees)')]:
            value,ok=QInputDialog.getDouble(self,'Register drawing floor',label,values[key],-10000,10000,3)
            if not ok:return
            values[key]=value
        self.registrations[f]=values
        scale,ok=QInputDialog.getDouble(self,'Confirm drawing units','Drawing-unit to metres scale (1 = metres; 0.001 = mm)',self.units.get(f,1),.000001,1000,6)
        if not ok:return
        self.units[f]=scale;self.invalidate_geometry();self.infer()

    def exclude_area(self):
        f=self.floor.currentData()
        if f is None:return
        text,ok=QInputDialog.getText(self,'Exclude planning area','Registered bounds: xmin,ymin,xmax,ymax (m). Blank clears floor exclusions.')
        if not ok:return
        try:
            values=[float(s.strip()) for s in text.split(',')] if text.strip() else []
            if values and (len(values)!=4 or values[0]>=values[2] or values[1]>=values[3]):raise ValueError('Use ordered rectangle bounds.')
            self.exclusions[str(f)]=[values] if values else [];self.invalidate_geometry();self.infer()
        except ValueError as exc:self.status.setText(str(exc))

    def option_values(self):
        return {**{key:spin.value() for key,spin in self.options.items()},'excluded':deepcopy(self.exclusions),
                'movable':{key:b.isChecked() for key,b in self.movable.items()}}

    def option_changed(self,*_):
        if self.study:
            self.study['proposals']={};self.study.pop('ranking',None);self.study['recommendation']=None
            self.study['results']={k:v for k,v in self.study['results'].items() if k=='current'}
            self.study['status']='ready';self.study['options']=self.option_values()
            if self.path:write_record(self.path,self.study)
        self.refresh_state()

    def confirm(self,checked):
        if self._reading:return
        if not checked:
            if self.study:self.study['confirmed']=False;write_record(self.path,self.study)
            self.refresh_state();return
        try:
            if self._geometry_identity!=input_identity(self.editor.store.data):raise ValueError('Infer the current drawing/configuration first.')
            if not self.editor.save_project():raise ValueError('Save the source project before creating a study.')
            path=Path(str(self.editor.project.path)+'.lift-study.json')
            if self.study and not self.stale() and self.study.get('geometry')==self.geometries:
                self.study['confirmed']=True;self.study['options']=self.option_values()
            else:
                if path.exists():
                    backup=path.with_name(path.name+'.'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.previous')
                    backup.write_bytes(path.read_bytes())
                self.path=path;self.study=create_study(self.editor.store.data,path,self.editor.project.path)
                self.study.update(geometry=deepcopy(self.geometries),confirmed=True,options=self.option_values())
            self.path=path;write_record(self.path,self.study)
            self.status.setText('Interpretation confirmed. Baseline arrivals and return requests are frozen; targetless requests use the study’s 10-minute target.')
            self.refresh_state()
        except Exception as exc:
            self.confirmed.blockSignals(True);self.confirmed.setChecked(False);self.confirmed.blockSignals(False)
            self.status.setText(f'Confirmation could not complete: {exc}');self.refresh_state()

    def propose(self):
        if self.running():return
        try:
            if not self.study or not self.study.get('confirmed') or self.stale():raise ValueError('Confirm current drawing interpretation first.')
            from lift_proposal_job import ProposalJob
            opts=self.option_values();self._proposal_options=opts
            job=ProposalJob(deepcopy(self.study['config']),deepcopy(self.geometries),deepcopy(opts),deepcopy(self.study['requests']))
            self._proposal_job=job;self._work_started=time.monotonic()
            job.signals.progress.connect(self.work_feedback);job.signals.finished.connect(self.proposals_finished)
            self.work_feedback('Generating layout proposals: screening shaft and landing sites…',0)
            self.editor.sync_project_editing_lock();self.refresh_state()
            QThreadPool.globalInstance().start(job)
        except Exception as exc:
            self._proposal_job=None;self.progress.hide()
            self.status.setText(f'Proposals need review: {exc}');self._work_message=self.status.text()
            self.progress_label.setText(self.status.text());self.refresh_state()

    @Slot(object,str,bool)
    def proposals_finished(self,result,error,cancelled):
        self._proposal_job=None
        try:
            if cancelled:raise ValueError(error)
            if error:raise ValueError(error)
            if self.stale():raise ValueError('Study inputs changed during generation. Infer and confirm the current interpretation again.')
            sites,proposals,overlays=result;updated=deepcopy(self.study)
            updated.update(sites=sites,proposals=proposals,overlays=overlays,options=self._proposal_options,status='ready')
            updated['results']={k:v for k,v in updated['results'].items() if k=='current'}
            updated.pop('ranking',None);updated['recommendation']=None;updated.pop('error',None)
            write_record(self.path,updated);self.study=updated
            self.refresh_state();self.tabs.setCurrentIndex(1)
            if self.proposals.rowCount():self.proposals.setCurrentCell(0,0);self.proposal_selected()
            self.work_feedback(f'Generated {len(proposals)} layout proposals from {len(sites)} aligned sites. Select a layout and inspect its overlay on each floor.',100)
        except Exception as exc:
            message=str(exc) if cancelled else f'Proposal generation failed: {exc}'
            self._work_message=message
            self.status.setText(message);self.progress_label.setText(message);self.progress.hide()
        finally:self.editor.sync_project_editing_lock();self.refresh_state()

    def start(self):
        if self.running():return
        if not self.study or self.stale() or not self.study.get('confirmed'):
            self.status.setText('Evaluation requires the current drawing interpretation to be inferred and confirmed.')
            self.progress_label.setText(self.status.text());return
        self._worker_output='';self._worker_line='';self._worker_error='';self._evaluation_cancelled=False
        self._work_started=time.monotonic()
        count=(1+len(self.study.get('proposals',{})))*len(self.study['scenarios'])
        self.work_feedback(f'Starting evaluation of {count} layout/scenario combinations…')
        self.process=QProcess(self);self.process.setProcessChannelMode(QProcess.MergedChannels)
        environment=QProcessEnvironment.systemEnvironment();environment.insert('PYTHONIOENCODING','utf-8');environment.insert('PYTHONUNBUFFERED','1')
        self.process.setProcessEnvironment(environment)
        self.process.readyReadStandardOutput.connect(self.read_progress)
        # "finished" belongs to QDialog's native signal; a Python callback
        # with that name can be bypassed by Qt's signal/slot dispatch.
        self.process.finished.connect(self.evaluation_finished);self.process.errorOccurred.connect(self.process_error)
        self.editor.sync_project_editing_lock()
        if getattr(sys,'frozen',False):self.process.start(str(Path(sys.executable).with_name('AMRSimulatorWorker.exe')),['--lift-study',str(self.path)])
        else:self.process.start(sys.executable,['-u',str(Path(__file__).resolve().parents[1]/'amr_lift_study.py'),str(self.path)])
        self.refresh_state()

    def read_progress(self):
        if self.process:
            text=bytes(self.process.readAllStandardOutput()).decode('utf-8',errors='replace')
            self._worker_output=(self._worker_output+text)[-8000:];self._worker_line+=text
            lines=self._worker_line.split('\n');self._worker_line=lines.pop()
            for line in lines:
                line=line.strip()
                if not line:continue
                self.details.appendPlainText(line)
                match=re.match(r'^(\d+)/(\d+):\s*(.+)',line)
                if match:
                    number,total=int(match[1]),int(match[2])
                    self.work_feedback(f'Evaluating {number}/{total}: {match[3]}',int(100*(number-1)/max(total,1)))

    def process_error(self,error):
        if self.process:self._worker_error=self.process.errorString()
        if error==QProcess.FailedToStart:self.evaluation_finished(-1,QProcess.NormalExit)

    def evaluation_finished(self,code,exit_status=QProcess.NormalExit):
        if self.process is None:return
        self.read_progress();p=self.process;self.process=None;p.deleteLater()
        try:
            self.study=json.loads(self.path.read_text(encoding='utf-8'))
            if self._evaluation_cancelled:
                self.study['status']='cancelled';write_record(self.path,self.study)
                self.status.setText('Evaluation stopped. Completed scenario evidence is retained; Evaluate scenarios resumes remaining work.')
                self.progress_label.setText(self.status.text());self.progress.hide()
            elif code!=0 or exit_status!=QProcess.NormalExit or self.study.get('status')!='complete':
                detail=self.study.get('error') or self._worker_error or self._worker_output.strip().split('\n')[-1] or f'Worker exited with code {code} before completing the study.'
                self.study.update(status='failed',error=detail);write_record(self.path,self.study)
                self.status.setText('Evaluation failed: '+detail);self.progress_label.setText(self.status.text());self.progress.hide()
            else:
                self.work_feedback('Evaluation complete. '+(self.study.get('explanation') or 'Review every floor and flow in Scenarios.'),100)
                self.tabs.setCurrentIndex(2)
        except Exception as exc:
            self.status.setText('Evaluation could not finish: '+str(exc));self.progress_label.setText(self.status.text());self.progress.hide()
        self._work_message=self.status.text()
        self.editor.sync_project_editing_lock();self.refresh_state()

    def cancel(self):
        if self._proposal_job:
            self._proposal_job.cancelled.set();self.work_feedback('Stopping proposal generation…');return
        if self.process:
            self._evaluation_cancelled=True
            worker=self.process;worker.kill();worker.waitForFinished(5000)
            self.study=json.loads(self.path.read_text(encoding='utf-8'));self.study['status']='cancelled';write_record(self.path,self.study)
            from amr_project_runs import finish_run,read_json
            root=Path(self.study['root'])/'runs'
            for manifest in root.glob('*/run_manifest.json'):
                if read_json(manifest)['status'] in ('prepared','running'):finish_run(manifest.parent,-1,cancelled=True)

    def refresh_state(self):
        valid=bool(self.study and self.study.get('confirmed') and not self.stale());busy=self.running()
        self.generate.setEnabled(valid and not busy);self.evaluate.setEnabled(valid and not busy);self.stop.setEnabled(busy)
        self.generate.setText('Generating proposals…' if self._proposal_job else 'Generate five layout proposals')
        self.evaluate.setText('Evaluating scenarios…' if self.process else 'Evaluate scenarios')
        self.stop.setText('Stop generation' if self._proposal_job else 'Stop evaluation')
        self.close_button.setEnabled(not busy)
        for widget in (self.infer_button,self.register_button,self.exclude_button,self.layers,*self.movable.values()):widget.setEnabled(not busy)
        if busy:
            self.progress_label.setText(f'{self._work_message} ({int(time.monotonic()-self._work_started)} s elapsed)')
        elif not valid:
            needed=self.preparation_needed();self.progress_label.setText(needed[1] if needed else 'Confirm the current drawing interpretation.')
        elif not self._work_message:
            self.progress_label.setText('Ready. Generate layout proposals or evaluate the frozen scenario suite; progress appears here.')
        selected=self.selected_proposal();rank=next((r for r in (self.study or {}).get('ranking',[]) if r['id']==selected),None)
        usable=valid and not busy and self.study.get('status')=='complete' and rank and rank['eligible']
        self.variant.setEnabled(bool(usable));self.apply.setEnabled(bool(usable))
        self.confirmed.setEnabled(not busy)
        for spin in self.options.values():spin.setEnabled(not busy)
        if busy:return
        if self.study:
            self.proposals.blockSignals(True);self.proposals.setRowCount(0)
            ranked={r['id']:r for r in self.study.get('ranking',[])}
            for name in self.study['proposals']:
                r=ranked.get(name);n=self.proposals.rowCount();self.proposals.insertRow(n)
                values=[name,'Eligible' if r and r['eligible'] else 'Tradeoff' if r else 'Not evaluated',
                    f"{r['worst_service']:.1%}" if r else '—',f"{r['distance_change_m']:.1f}" if r else '—',f"{r['wait_change_sec']:.1f}" if r else '—']
                for col,value in enumerate(values):self.proposals.setItem(n,col,QTableWidgetItem(value))
            self.proposals.blockSignals(False)
            if selected:
                for n in range(self.proposals.rowCount()):
                    if self.proposals.item(n,0).text()==selected:self.proposals.setCurrentCell(n,0);break
            previous_row=self.scenarios.currentRow()
            self.scenarios.setRowCount(0);self._run_rows=[]
            for name,runs in self.study['results'].items():
                for scenario,run in runs.items():
                    for key,g in run['metrics']['groups'].items():
                        n=self.scenarios.rowCount();self.scenarios.insertRow(n);self._run_rows.append((name,scenario))
                        values=[name,scenario,key,str(g['completed']),f"{g['failed']} / {g['pending']}",
                            f"{g['on_time_rate']:.1%}" if g['on_time_rate'] is not None else 'No target',f"{run['metrics']['horizontal_m']:.1f}"]
                        for col,value in enumerate(values):self.scenarios.setItem(n,col,QTableWidgetItem(value))
            if 0<=previous_row<self.scenarios.rowCount():self.scenarios.setCurrentCell(previous_row,0)
            details={k:v for k,v in self.study.items() if k in ('status','source_identity','software_sha256','ranking','explanation','error','variant')}
            try:
                name,scenario,run=self.selected_run()
                details['selected_run']=dict(layout=name,scenario=scenario,directory=run['directory'],
                    metrics={k:v for k,v in run['metrics'].items() if k!='requests'})
            except ValueError:pass
            text=json.dumps(details,indent=2)
            if self.details.toPlainText()!=text:self.details.setPlainText(text)
            if self.stale():self.status.setText('Study is stale: project inputs or drawing bytes changed. Infer and confirm a new study; old runs remain retained.')

    def selected_proposal(self):
        n=self.proposals.currentRow();return self.proposals.item(n,0).text() if n>=0 and self.proposals.item(n,0) else None

    def closeEvent(self,event):
        if self.running():
            self.progress_label.setText('Work is running. Use Stop generation or Stop evaluation before closing the planner.')
            event.ignore();return
        super().closeEvent(event)

    def proposal_selected(self,*_):
        if not self.study:return
        self.draw_geometry(self.proposal_scene,self.proposal_view,self.floor.currentData(),self.selected_proposal())
        valid=not self.stale() and not self.running() and self.study.get('status')=='complete'
        r=next((r for r in self.study.get('ranking',[]) if r['id']==self.selected_proposal()),{})
        self.variant.setEnabled(valid and r.get('eligible',False));self.apply.setEnabled(valid and r.get('eligible',False))

    def draw_geometry(self,scene,view,floor,proposal=None):
        scene.clear();g=next((g for g in self.geometries if g['floor']==floor),None)
        if not g:return
        colors={'boundary':'#333333','wall':'#555555','opening':'#5ba06b','circulation':'#b9def8','excluded':'#f3b4b4','shaft':'#ccaff0'}
        for row in g['entities']:
            if row['role']=='ignore':continue
            color=QColor(colors[row['role']]);color.setAlpha(75 if row['role']=='circulation' else 160)
            scene.addPath(_shape(row),QPen(QColor(colors[row['role']]),.06),QBrush(Qt.NoBrush) if row['role']=='boundary' else QBrush(color))
        for bounds in self.exclusions.get(str(floor),[]):scene.addRect(QRectF(bounds[0],bounds[1],bounds[2]-bounds[0],bounds[3]-bounds[1]),QPen(QColor('#d00000'),.1),QBrush(QColor(240,80,80,100)))
        if self.study:
            for site in self.study.get('sites',[]):scene.addEllipse(site['x']-.2,site['y']-.2,.4,.4,QPen(QColor('#003f8c'),.1))
            for lift in self.study.get('proposals',{}).get(proposal,{}).get('lifts',[]):
                pos=lift['floor_locations'].get(str(floor))
                if pos:
                    x,y=transform((pos['x'],pos['y']),g['registration']);options=self.study.get('options',{})
                    length=options.get('shaft_length_m',2);width=options.get('shaft_width_m',2)
                    scene.addRect(QRectF(x-length/2,y-width/2,length,width),QPen(QColor('#005fc4'),.12),QBrush(QColor(30,130,220,80)))
                    label=scene.addText(lift['id']);label.setScale(.05);label.setPos(x,y)
            for row in self.study.get('overlays',{}).get(proposal,[]):
                if row['floor']!=floor:continue
                p=QPainterPath();p.moveTo(*row['path'][0])
                for point in row['path'][1:]:p.lineTo(*point)
                scene.addPath(p,QPen(QColor('#005fc4'),.18))
        view.fitInView(scene.itemsBoundingRect(),Qt.KeepAspectRatio)

    def selected_run(self):
        n=self.scenarios.currentRow()
        if not self.study or n<0 or n>=len(self._run_rows):raise ValueError('Select a scenario evidence row.')
        name,scenario=self._run_rows[n];return name,scenario,self.study['results'][name][scenario]

    def investigate(self):
        try:
            from amr_results_investigation import load_investigation
            _,_,run=self.selected_run();self.editor.show_results_investigation();self.editor.results_panel.accept_result(load_investigation(run['directory']))
        except Exception as exc:self.status.setText(str(exc))
    def playback(self):
        try:
            from amr_project import Project
            _,_,run=self.selected_run();self.editor.show_project_playback()
            self.editor.playback_panel._study_context=Project.open(run['project'])
            self.editor.playback_panel.load(run['directory'])
        except Exception as exc:self.status.setText(str(exc))
    def report(self):
        try:
            from amr_project import Project
            _,_,run=self.selected_run();self.editor.show_project_report()
            self.editor.report_panel._study_context=Project.open(run['project'])
            self.editor.report_panel.set_run(run['directory'])
        except Exception as exc:self.status.setText(str(exc))
    def relink(self):
        try:
            name,scenario,_=self.selected_run();directory=QFileDialog.getExistingDirectory(self,'Locate moved study run')
            if directory:relink_result(self.study,name,scenario,directory);write_record(self.path,self.study);self.refresh_state()
        except Exception as exc:self.status.setText(str(exc))

    def create_variant(self):
        name=self.selected_proposal()
        if self.stale() or not self.variant.isEnabled() or not name:return
        target,_=QFileDialog.getSaveFileName(self,'Save separate design variant',name+'.amrproj','AMR projects (*.amrproj)')
        if not target:return
        target=Path(target).with_suffix('.amrproj')
        if self.editor.project and target.resolve()==self.editor.project.path.resolve():self.status.setText('Choose a different file to preserve the source design.');return
        try:
            from amr_project import Project
            p=Project();p.save(target,self.study['proposals'][name],label='Lift location variant')
            self.study['variant']=str(target);write_record(self.path,self.study);self.status.setText('Separate variant saved; source project and runs preserved.')
        except Exception as exc:self.status.setText(str(exc))

    def apply_selected(self):
        if self.stale() or not self.apply.isEnabled():return
        self.editor.apply_lift_proposal(self.study['proposals'][self.selected_proposal()]);self.refresh_state()

    def export(self):
        if not self.study:return
        target,_=QFileDialog.getSaveFileName(self,'Export lift comparison','lift-comparison.csv','CSV (*.csv)')
        if target:
            try:
                export_comparison(self.study,target)
                self.study.setdefault('tutorial_exports',{})['csv']=str(Path(target).resolve());write_record(self.path,self.study)
            except Exception as exc:self.status.setText(str(exc))

    def export_pdf(self):
        if not self.study:return
        target,_=QFileDialog.getSaveFileName(self,'Export lift comparison PDF','lift-comparison.pdf','PDF (*.pdf)')
        if target:
            try:
                from amr_lift_study_report import export_pdf
                export_pdf(self.study,target)
                self.study.setdefault('tutorial_exports',{})['pdf']=str(Path(target).resolve());write_record(self.path,self.study)
            except Exception as exc:self.status.setText(str(exc))
