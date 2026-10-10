"""Optional checked building course; leaves the canvas and normal editors in charge."""
from pathlib import Path
import tempfile

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QListWidget,
    QPlainTextEdit,QPushButton,QComboBox,QMenu,QToolButton,QFileDialog,QMessageBox,
    QInputDialog,QDialog,QToolTip)

from amr_tutorial import TutorialSession,LESSONS,EXTRA_LESSONS
from amr_run_evidence import config_hash


class BuildingCourse(QWidget):
    def __init__(self, editor, parent=None):
        super().__init__(parent); self.editor=editor; self.session=TutorialSession()
        self._project_path=None;self._project_identity=None; self._hash=None; self.card=None
        self._navigation_previous=0
        layout=QVBoxLayout(self)
        intro=QLabel('Build, test and improve a three-floor flow design. Check real results at each step.'); intro.setWordWrap(True)
        layout.addWidget(intro)
        self.chapters=QComboBox(); self.chapters.setAccessibleName('Building course chapter')
        for n,lesson in enumerate(LESSONS,1): self.chapters.addItem(f'{n}. {lesson[1]}')
        layout.addWidget(self.chapters)
        self.details=QPlainTextEdit(); self.details.setReadOnly(True); self.details.setAccessibleName('Building course instructions')
        layout.addWidget(self.details,1)
        self.feedback=QLabel(''); self.feedback.setWordWrap(True); self.feedback.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.feedback)
        row=QHBoxLayout()
        self.previous=QPushButton('Previous'); self.next=QPushButton('Next'); self.check=QPushButton('Check this step')
        self.open=QPushButton('Open workspace')
        for b in (self.previous,self.next,self.check,self.open): row.addWidget(b)
        layout.addLayout(row)
        row=QHBoxLayout(); row.addWidget(QLabel('Flow policy'))
        self.policy=QComboBox(); self.policy.addItem('Dedicated lift permissions','dedicated'); self.policy.addItem('Shared lift permissions','shared')
        self.policy.setToolTip('Describes the route permissions you configure. Selecting this does not change project inputs.')
        row.addWidget(self.policy,1)
        self.tools=QToolButton(); self.tools.setText('Course tools'); self.tools.setPopupMode(QToolButton.InstantPopup)
        menu=QMenu(self.tools)
        for text,fn in [('Start from drawings',lambda:self.open_checkpoint('starter')),
            ('Open chapter checkpoint',self.choose_checkpoint),('Open completed reference',lambda:self.open_checkpoint('reference-'+self.policy.currentData())),
            ('Pause / resume',self.pause),('Restart current chapter',self.restart),
            ('Restart tutorial bubble',self.restart_bubble),
            ('Bind an object',self.bind_role),('Highlight relevant control',self.highlight),
            ('Compact instruction card',self.show_card),('Additional lessons',self.extras)]:
            menu.addAction(text,fn)
        menu.addAction('Illustrated building guide',self.open_guide)
        menu.addAction('Complete interface reference',lambda:self.open_guide('COVERAGE.md'))
        self.tools.setMenu(menu); row.addWidget(self.tools); layout.addLayout(row)
        self.previous.clicked.connect(lambda:self.chapters.setCurrentIndex(max(0,self.chapters.currentIndex()-1)))
        self.next.clicked.connect(self.advance_chapter)
        self.check.clicked.connect(self.check_step); self.open.clicked.connect(self.open_workspace)
        self.chapters.currentIndexChanged.connect(self.show_step); self.policy.currentIndexChanged.connect(self.policy_changed)
        self.chapters.activated.connect(self.gate_chapter_selection)
        self.timer=QTimer(self); self.timer.setInterval(1500); self.timer.timeout.connect(self.sync); self.timer.start()
        self._bind_observers(); self.sync(); self.show_step()

    def _bind_observers(self):
        e=self.editor
        for name,action in [('undo',e.undo_action),('redo',e.redo_action),('fit',e.cad_toolbar.fit_action)]:
            action.triggered.connect(lambda _checked=False,name=name:self.observe(name))
        e.workspace.properties_tab.clicked.connect(lambda:self.observe('properties'))
        for attribute in ('snap_action','object_snap_action'):
            a=getattr(e.cad_toolbar,attribute,None)
            if a: a.triggered.connect(lambda:self.observe('snaps'))
        e.object_snap_check.toggled.connect(lambda:self.observe('snaps'))
        e.floor_spin.valueChanged.connect(lambda floor:self.observe(f'floor:{floor}'))
        e.cad_toolbar.fit_action.triggered.connect(lambda:self.observe(f'fit:{e.floor_spin.value()}'))
        self.session.observe(f'floor:{e.floor_spin.value()}')

    def persist(self):
        try:self.session.save()
        except OSError as exc:self.feedback.setText('Progress could not save: '+str(exc))

    def observe(self,name):
        self.session.observe(name);self.persist()

    def context(self):
        e=self.editor; p=e.project; run=None
        panel=getattr(e,'project_runs_panel',None)
        if panel: run=panel.selected_path()
        if run is None and self.session.state.get('run'): run=Path(self.session.state['run'])
        current=False
        if run and p:
            try:
                from amr_project_runs import inspect_run
                m=inspect_run(run,p)
                current=m['project_binding']['revision_config_sha256']==p.revisions[-1]['config'] and not e.has_unsaved_changes()
            except Exception: run=None
        planner=getattr(e,'lift_planner',None)
        study=planner.study if planner else None
        checks=getattr(e,'checks_panel',None);investigation=getattr(e,'results_panel',None)
        playback=getattr(e,'playback_panel',None);report=getattr(e,'report_panel',None)
        exports=(study or {}).get('tutorial_exports',{})
        source=(investigation.result or {}).get('source') if investigation else None
        investigation_matches=bool(source and run and (Path(source)==Path(run) or Path(source).parent==Path(run)))
        playback_matches=bool(playback and playback.viewer is not None and run and playback.directory is not None and Path(playback.directory)==Path(run))
        report_matches=bool(report and report.run_dir is not None and run and Path(report.run_dir)==Path(run))
        return dict(saved=p is not None and p.path is not None,project_created=p is not None,
            unsaved=e.has_unsaved_changes(),floor=e.floor_spin.value(),properties_open=e.workspace.properties.isVisible(),
            history_changes=len(e.edit_history.entries)-1,checks_current=checks is not None and checks.current(),
            checks_ready=checks is not None and checks.can_run(),investigation_ready=investigation_matches,
            evidence_selected=investigation_matches and investigation.selected_evidence is not None,
            playback_ready=playback_matches,report_ready=report_matches,
            geometry_ready=planner is not None and len(planner.geometries)==3,
            comparison_exports=all(exports.get(k) and Path(exports[k]).is_file() for k in ('pdf','csv')),
            run=run,current_run=current,study=study,study_stale=planner.stale() if planner and study else True)

    def sync(self,*,preserve_progress=False):
        e=self.editor; p=e.project
        path=p.path if p else None
        if path!=self._project_path:
            self.persist()
            previous=self.session.state;identity=p.project_id if p else None
            same_project=identity is not None and identity==self._project_identity
            self._project_path=path
            self.session=TutorialSession(Path(str(path)+'.tutorial.json') if path else None)
            if preserve_progress or (path and same_project and not self.session.path.exists()):
                self.session.state.update(previous)
            elif path and self.session.path.exists(): self.session.state['reopened']=True
            self.chapters.blockSignals(True);self.policy.blockSignals(True)
            self.chapters.setCurrentIndex(min(len(LESSONS)-1,max(0,self.session.state['chapter'])))
            self.policy.setCurrentIndex(self.policy.findData(self.session.state['policy']))
            self.chapters.blockSignals(False);self.policy.blockSignals(False)
            self._hash=None
        self._project_identity=p.project_id if p else None
        if len(e.edit_history.entries)>1:self.session.observe('layout_edit')
        if getattr(e,'selected_point_name',None) or getattr(e,'selected_point_names',None): self.session.observe('selection')
        if not e.workspace.properties.isHidden(): self.session.observe('properties')
        if getattr(e,'demand_panel',None) is not None: self.session.observe('preview')
        if getattr(e,'results_panel',None) is not None: self.session.observe('investigation')
        if getattr(e,'playback_panel',None) is not None and e.playback_panel.viewer is not None: self.session.observe('playback')
        h=config_hash(e.store.data)
        if h!=self._hash:
            self._hash=h; self.session.seed_bindings(e.store.data); self.session.reconcile(e.store.data)
            for n,lesson in enumerate(LESSONS):
                # Workbench completion records past practice. Reopening clears
                # the editor's undo stack, but does not undo that practice.
                if lesson[0] not in ('workbench','run','investigate','report') and self.session.state['completed'].get(lesson[0],{}).get('passed'):
                    self.session.check(n,e.store.data,self.context())
            self.show_step()
        self.persist()

    def show_step(self,*_):
        i=self.chapters.currentIndex(); lesson=LESSONS[i];self._navigation_previous=self.session.state['chapter']
        if i!=self.session.state['chapter']:self.session.state['action']=0
        self.session.state['chapter']=i
        self.details.setPlainText(f'{lesson[1]}\n\nDo this\n{lesson[3]}\n\nExpected result\n{lesson[4]}\n\n'
            'Washing services the AMR after designated deliveries. Payload decontamination and contamination state during empty travel are not simulated. '
            'Use Course tools for checkpoints, rebinding and optional lessons. Opening instructions never changes project inputs.')
        self.previous.setEnabled(i>0); self.next.setEnabled(i<len(LESSONS)-1)
        self.open.setText('Open '+lesson[2].title()); self.check.setEnabled(not self.session.state['paused'])
        result=self.session.state['completed'].get(lesson[0],{})
        self.feedback.setText('Paused — resume from Course tools.' if self.session.state['paused'] else
            'Verified. Continue when ready.' if result.get('passed') else '\n'.join(result.get('issues',[])) or self.session.warning or 'Not checked yet.')
        if self.card:self.card.refresh()
        self.persist()

    def check_step(self):
        try:
            self.sync(); self.session.check(self.chapters.currentIndex(),self.editor.store.data,self.context()); self.show_step()
        except Exception as exc: self.feedback.setText(f'Could not check this step: {exc}')

    def advance_chapter(self):
        self.check_step()
        if self.session.state['completed'].get(LESSONS[self.chapters.currentIndex()][0],{}).get('passed'):
            self.chapters.setCurrentIndex(min(len(LESSONS)-1,self.chapters.currentIndex()+1))

    def gate_chapter_selection(self,index):
        previous=self._navigation_previous
        if index<=previous:return
        for chapter in range(previous,index):
            issues=self.session.check(chapter,self.editor.store.data,self.context())
            if issues:
                self.chapters.setCurrentIndex(previous);self.feedback.setText('Finish this chapter first: '+issues[0]);return

    def open_workspace(self): self.editor.workspace.activate(LESSONS[self.chapters.currentIndex()][2])
    def open_guide(self,name='Building-Flow-Tutorial.pdf'):
        from quick_start import application_root
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        target=application_root()/'docs/building-tutorial'/name
        if target.exists():QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))
        else:self.feedback.setText('Guide is missing from this installation.')
    def policy_changed(self,*_): self.session.state['policy']=self.policy.currentData(); self.session.save()
    def pause(self):
        if self.session.state['paused']:self.show_card()
        elif self.card:self.card.pause()
        else:self.session.state['paused']=True;self.session.save()
        self.show_step()
    def restart(self):
        self.session.restart(self.chapters.currentIndex());self.show_step()
        if self.card:self.card.locate()

    def choose_checkpoint(self):
        name,ok=QInputDialog.getItem(self,'Chapter checkpoint','Working copy of',
            [f'chapter-{n}' for n in (3,4,5,6,7)],0,False)
        if ok:self.open_checkpoint(name)

    def open_checkpoint(self,name):
        from quick_start import application_root
        from amr_project import Project
        source=application_root()/'docs/building-tutorial'/f'{name}.amrproj'
        if not self.editor._project_editing_allowed() or not self.editor._confirm_unsaved_changes(): return
        target,_=QFileDialog.getSaveFileName(self,'Save tutorial working copy',f'{name}-working.amrproj','AMR projects (*.amrproj)')
        if not target:return
        target=Path(target).with_suffix('.amrproj')
        if target.resolve()==source.resolve(): self.feedback.setText('Choose a different path to preserve the supplied example.'); return
        try:
            with tempfile.TemporaryDirectory(prefix='amr-tutorial-') as cache:
                cfg=Project.open(source).materialize(cache)
                p=Project(); p.save(target,cfg,label='Tutorial working copy')
            self.editor.load_json_file(str(target),check_unsaved=False)
            self.sync()
        except Exception as exc:self.feedback.setText(f'Checkpoint could not open: {exc}')

    def bind_role(self):
        roles=['dispatch','clean_store','dirty_receiving','wash','lift1','lift2']+[f'service_{flow}_{floor}' for floor in range(3) for flow in ('clean','dirty')]
        role,ok=QInputDialog.getItem(self,'Tutorial object','Role',roles,0,False)
        if not ok:return
        section='lifts' if role.startswith('lift') else 'locations'; key='id' if section=='lifts' else 'name'
        names=[r[key] for r in self.editor.store.data.get(section,[])]
        if not names:self.feedback.setText('Create an object before binding it.'); return
        name,ok=QInputDialog.getItem(self,'Bind tutorial object',role,names,0,False)
        if ok:self.session.bind(role,self.editor.store.data,section,name); self.session.save(); self.check_step()

    def highlight(self):
        self.show_card();self.card.locate()

    def show_card(self):
        self.sync()
        from shiboken6 import isValid
        if self.card is not None and not isValid(self.card):self.restart_bubble();return
        if self.card is None:
            from tutorial_bubble import TutorialBubble
            self.card=TutorialBubble(self)
        self.card.resume()

    def restart_bubble(self):
        if self.card is not None:self.card.dispose()
        self.card=None
        self.show_card()

    def extras(self):
        name,ok=QInputDialog.getItem(self,'Additional lessons','Lesson',[r[0] for r in EXTRA_LESSONS],0,False)
        if ok:
            row=next(r for r in EXTRA_LESSONS if r[0]==name)
            self.details.setPlainText(name+'\n\n'+row[1]+'\n\nOptional: return to a core chapter whenever ready.')
            self.editor.workspace.activate(row[2])
