"""Small instruction bubble anchored to live controls, without taking focus."""
from PySide6.QtCore import Qt,QTimer,QRect,QPoint,QPointF,QEvent,QSize
from PySide6.QtGui import QPainter,QPen,QColor
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QToolButton,
    QComboBox,QAbstractButton,QApplication,QFormLayout,QScrollArea,QPlainTextEdit,QMenu,QTabWidget,
    QAbstractSpinBox,QLineEdit,QAbstractItemView,QTabBar,QDockWidget,QDialog)
from PySide6.QtGui import QAction
from amr_tutorial import LESSONS
from amr_tutorial_circulation import CIRCULATION_STEPS,inspect_step,inspect_all
from amr_tutorial_steps import action_issues
from amr_run_evidence import config_hash
from amr_tutorial_placement import placement_step,placement_issues
from amr_inventory_inputs import inventory_space_is_amr
from tutorial_field_guide import DialogFieldGuide
import json
import time

# Each action points to an existing control; a dialog field becomes the target
# only after the user opens that editor. Navigation never changes model inputs.
# selector, concise action, optional live dialog field label.
ACTIONS=(
 (('menu:File','File > New project, or More > Start from drawings to save a working copy.',''),
  ('Building settings','Open Configuration > Building settings. Set Number of floors to 3 and Level height to 3.5 m, then Save.','Number of floors'),
  ('attr:floor_spin','Choose floor 0, 1 and 2. For each, right-click its tree entry > Add DXF and import its individual drawing.',''),
  ('attr:fit','Fit each floor. Confirm 40 x 20 m and alignment at the common origin.',''),
  ('menu:File','File > Save project as. Keep the supplied starter unchanged.','')),
 (('attr:floor_spin','Switch floors, then return to floor 0.',''),
  ('attr:fit','Click Fit to see the whole plan.',''),
  ('attr:object_snap_check','Use Object snap at the bottom right; use Grid snap in the drawing toolbar. Toggle a snap setting to practise.',''),
  ('attr:canvas','Select a node. If the drawing has no nodes, use Transition to place one at (3,10) on floor 0. Edit > Move selected by: enter 0.1,0 in Move by (m), then Apply move.',''),
  ('attr:properties','Click Properties explicitly, inspect the selected node, then collapse it.',''),
  ('attr:undo','Edit > Undo (Ctrl+Z), then Edit > Redo (Ctrl+Y). Undo again to restore the original position. The chapter checks that both actions were used.','')),
 (('action:Corridor','Draw clean circulation at y=7 m and dirty circulation at y=13 m on each floor. Blank Enter finishes a polyline.',''),
  ('action:Junction','Create nodes at x=3,8,10,12,18,24,30,34,38. Add shared transitions at (3,10).',''),
  ('action:Door','Add doors at x=8+2*floor, y=6 and 14, with 1.2 m clear width.',''),
  ('action:Location','Add Clean-F0/1/2 at y=4 and Dirty-F0/1/2 at y=16; x=8+2*floor. Connect each through its door to its own lane.',''),
  ('attr:canvas','Connect same-floor transitions. Never draw an ordinary edge between floors. See More > Guide for the full coordinate table.','')),
 (('action:Location','Place the four ground-floor facilities on their numbered markers. Each joins its corridor; enter the shown name, then Save.',''),
  ('attr:location_spaces','Select Dispatch > Properties > Create / edit spaces. Alternative: right-click Dispatch > Inventory spaces. Read the bay sizes and dashed position previews, then Create four tutorial charging bays > Save and close. Each bay is 1.4 × 1.1 m with 2 m clear height; centres are (2,9.2), (4,9.2), (2,10.8), (4,10.8). Chargers are enabled.',''),
  ('role:dirty_receiving','Select Dirty receiving > Properties. Set Wash cycle required to Yes, Wash location to Wash, and Wash duration (s) to 60. Click Apply changes. These fields wash the AMR after delivery.',''),
  ('role:wash','Select Wash > Properties. Enter 1 in Service capacity (AMRs), then click Apply changes. Wash can serve one AMR at a time.','')),
 (('Robots','Configuration > Robots > Add.\n\nAMR details\n• Name: Teaching AMR\n• Fleet quantity: 4\n• Overall length: 1 m\n• Overall width: 0.7 m\n• Normal travel speed: 1.5 m/s\n• Travel motor power: 96 W\n\nBattery and charging\n• Usable battery capacity: 0.1 kWh\n• Charging power: 2 kW\n• Request charging at: 20%\n• Initial state of charge: 15%\n\nPayload slots > first row > Edit selected\n• Weight capacity: 100 kg\n• Length / width / height: 1.2 / 0.9 / 1.5 m\n\nSave the slot, Save the AMR type, then Save the AMR list.','Fleet quantity'),
  ('Payloads','Configuration > Payloads > Add.\n\nPayload details\n• Name: Clean tote\n• Overall length: 0.8 m\n• Overall width: 0.6 m\n• Overall height: 1 m\n• Loaded weight: 20 kg\n• Lengthways: on; Sideways: off\n\nSave; repeat for Dirty cart, then Save the payload list.','Length'),
  ('Departments','Configuration > Departments > Add.\n\nDetails\n• ID: D0\n• Name: Floor 0 service\n• Floor: 0\n• Enabled: on\n\nHours & waste\n• Operating start: 06:00\n• Operating end: 08:00\n\nTask locations & zones\n• Stores > Select: Clean-F0\n• Linen > Select: Dirty-F0\n\nSave. Repeat D1/Floor 1/Clean-F1/Dirty-F1 and D2/Floor 2/Clean-F2/Dirty-F2, then Save the department list.','Floor'),
  ('Lifts','Configuration > Lifts > Add.\n\nLift and floors\n• Lift name: L1\n• Floors served: 0,1,2\n• Starting floor: 0\n• Vertical travel speed: 1.75 m/s (0.5 floors/s)\n• Door operation time: 4 s\n• AMR boarding / exit time: 3 s\n• Stop table, each floor: X 34 m, Y 10 m\n\nCar and energy\n• Clear car length: 2 m\n• Clear car width: 2 m\n• Clear car height: 2.5 m\n\nHealth and reliability\n• Health lost per journey: 0\n\nSave. Repeat for L2 with X 38 m, Y 10 m on every floor.','Floors served')),
 (('layout:route_profiles','Layout > Route profiles > Add.\n\nProfile attributes — clean\n• Profile name: clean\n• Allowed nodes: clean lanes and doors, Clean-F0/F1/F2, Clean store and permitted lift stops\n• Allowed edges: corridor links between those nodes on floors 0, 1 and 2\n• Allowed lifts: L1 for Dedicated; L1 and L2 for Shared\n\nSelect nodes and edges in Layout\n• Select > Nodes: click each orange-ringed node; blue means selected.\n• Change floors using Floor in the route selection toolbar.\n• Select > Edges: click each dashed orange corridor link.\n• A two-way corridor adds both directions; a one-way corridor keeps its direction.\n• Click again to remove an unintended selection.\n• Finish selection, then Apply Changes.\n\nRepeat for dirty\n• Profile name: dirty\n• Allowed nodes: dirty lanes and doors, Dirty-F0/F1/F2, Dirty receiving, Wash and permitted lift stops\n• Allowed edges: corridor links between those nodes on every floor\n• Allowed lifts: L2 for Dedicated; L1 and L2 for Shared\n\nIf geometry is missing, Cancel selection and close the profile editor first. Use Layout > Add node / transition to place a node and Layout > Add edge between nodes to connect two existing nodes. Reopen the profile and continue graphical selection. Save All after applying both profiles.',''),
  ('layout:route_profiles','Layout > Route profiles. Select each profile.\n\nAllowed lifts > Pick\n• Dedicated: clean uses L1; dirty uses L2.\n• Shared: both profiles use L1 and L2.\n• Graphical selection must include each permitted lift stop and its corridor access edges on floors 0, 1 and 2.\n\nApply Changes for each profile, then Save All. In the tutorial More window choose the matching policy.','Allowed lifts'),
  ('layout:route_profiles','Layout > Route profiles > Save All.\n\nBefore continuing\n• clean and dirty have their graphical node and edge selections applied.\n• Allowed lifts match the policy chosen in More.\n• Save All commits both profiles to the project.\n\nA different policy needs a separate comparison study.','Save All')),
 (('Demand generation','Configuration > Demand generation. Enable automatic task generation. Select Stores, then each department D0/D1/D2.\n\nBasics\n• Enabled: on\n• Generation mode: scheduled\n• Service target (s): 600\n\nLocations & routing\n• Department locations: drop-off\n• Pickup / source location: Clean store\n• Payload: Clean tote\n• Route profile: clean\n\nSchedule & staff\n• Staff handling: off\n\nRepeat for Linen\n• Department locations: pickup/source\n• Drop-off destinations > Select: Dirty receiving\n• Payload: Dirty cart\n• Route profile: dirty\n\nSave.','Scheduled'),
  ('Demand generation','In Demand generation configure each Stores and Linen department D0/D1/D2.\n\nBasics\n• Service target (s): 600\n\nSchedule & staff > Scheduled times > Edit times\n• 06:05\n• 06:35\n• 07:05\n• 07:35\n• Click OK after adding all four times.\n\nReturns & stock — Stores\n• Generate return / exchange task: on\n• Return payload: Clean tote\n• Return route profile: clean\n• Return delay (minutes): 2\n\nKeep Linen returns off. Save. Department actions > Configure multiple is an alternative for shared settings.','Return'),
  ('stage:checks','Open Check and click Demand preview beside Run checks. Then click Build preview.\n\nReview the planned work\n• Departments: D0, D1 and D2\n• Flows: Stores / clean and Linen / dirty\n• Planned releases: 06:05, 06:35, 07:05 and 07:35\n• Stores returns: after 2 minutes (generated during simulation)\n\nUse Tasks, Timetable and Rules and reconciliation to inspect the preview before running.','')),
 (('Simulation settings','Configuration > Simulation settings. Choose Simple. On Run period set Starts to 5 January 2026 06:00, enable End generated demand at a fixed date and time, and set Ends to 5 January 2026 08:00. Save.','Mode'),
  ('stage:checks','Check > Run checks. Select a finding and follow its repair control. Rerun Run checks after applying each repair.',''),
  ('stage:simulate','Use Save, check and simulate. Inspect progress and wait for a retained completed run.','')),
 (('stage:simulate','Select the completed run, then Investigate selected run.',''),
  ('stage:review','Select a task and inspect its linked payload, journey and lift evidence.',''),
  ('stage:simulate','Simulate > select the completed run > Playback selected run. In Playback follow both lifts, AMR charging and post-delivery wash cycles.','')),
 (('Plan lift locations','Open lift planning. Infer drawings, assign layer roles and review each floor overlay.','Infer drawings'),
  ('Plan lift locations','Confirm units, boundary, circulation, exclusions and floor registration. Evaluation requires confirmation.','I reviewed'),
  ('Plan lift locations','Click Evaluate scenarios. Watch the progress indicator above the action buttons: it names the current layout and scenario and shows elapsed time. When Evaluation complete appears, inspect Scenarios for completed/failed/pending and on-time service on every floor and flow. Stop evaluation retains completed evidence for resuming.','Evaluate scenarios')),
 (('Plan lift locations','Plan lift locations > Proposals.\n\nProposal settings\n• Shaft length: 2 m\n• Shaft width: 2 m\n• Landing depth: 1 m\n• Clearance: 0.1 m\n• Move L1 and Move L2: on\n\nClick Generate five layout proposals. Watch the progress indicator above the action buttons as it screens sites and checks layout connectors. The first generated proposal is displayed automatically; select each proposal and inspect Proposal overlay floor on all floors. Stop generation retains earlier proposals.','Generate five'),
  ('Plan lift locations','Evaluate all proposals against identical frozen schedules. Read the service guard before distance changes.','Evaluate scenarios'),
  ('Plan lift locations','Plan lift locations > Proposals. Select a result that passes the Service guard, then click Create design variant and choose a separate project file.','Create design variant')),
 (('stage:simulate','Select a frozen run and choose Report selected run.',''),
  ('stage:report','Choose sections, then Generate report. Read the PDF and lift CSV.',''),
  ('Plan lift locations','Plan lift locations > Evidence. Click Export comparison CSV and save it, then Export comparison PDF and save it. Both exports include the service guard and tradeoffs.','Export comparison'),
  ('menu:File','Save and reopen your project. Retain baseline, variant, tutorial companion, study companion and run folders.','')),
)
ACTIONS=ACTIONS[:2]+(tuple(('action:'+s['tool'],s['instruction'],'') for s in CIRCULATION_STEPS),)+ACTIONS[3:]


class CirculationOverlay(QWidget):
    """Viewport-only hints; mouse and keyboard continue to the real drawing."""
    def __init__(self,canvas):
        super().__init__(canvas.viewport());self.canvas=canvas;self.step=None;self.issue=None;self.next_point=None
        self.setAttribute(Qt.WA_TransparentForMouseEvents);self.setAttribute(Qt.WA_NoSystemBackground)
        self.setFocusPolicy(Qt.NoFocus);self.setAccessibleName('Tutorial route and next click preview')
    def paintEvent(self,event):
        if not self.step:return
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing)
        points=[self.canvas.mapFromScene(QPointF(x,-y)) for x,y in self.step['points']]
        painter.setPen(QPen(QColor('#0077cc'),2,Qt.DashLine))
        if self.step['kind']=='route':
            for a,b in zip(points,points[1:]):painter.drawLine(a,b)
        for n,point in enumerate(points,1):
            active=self.next_point and tuple(self.step['points'][n-1])==tuple(self.next_point)
            painter.setPen(QPen(QColor('#b33b00' if active else '#0077cc'),3 if active else 2))
            painter.setBrush(QColor('#fff5d6' if active else '#ffffff'))
            painter.drawEllipse(point,14 if active else 10,14 if active else 10)
            painter.drawText(QRect(point-QPoint(12,12),QSize(24,24)),Qt.AlignCenter,str(n))
        if self.issue:
            mark=self.next_point or self.issue['point']
            point=self.canvas.mapFromScene(QPointF(mark[0],-mark[1]))
            painter.setPen(QPen(QColor('#b33b00'),3));painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(point,20,20)
            if self.issue.get('start'):
                start=self.canvas.mapFromScene(QPointF(self.issue['start'][0],-self.issue['start'][1]))
                finish=self.canvas.mapFromScene(QPointF(self.issue['point'][0],-self.issue['point'][1]))
                painter.drawLine(start,finish)
            if self.issue.get('path_start'):
                painter.drawLine(self.canvas.mapFromScene(QPointF(self.issue['path_start'][0],-self.issue['path_start'][1])),
                                 self.canvas.mapFromScene(QPointF(self.issue['path_finish'][0],-self.issue['path_finish'][1])))
        if self.next_point:
            p=self.next_point;name=(self.issue or {}).get('expected_name') or (self.issue or {}).get('name')
            if not name and self.step.get('names'):
                name=next((n for n,point in zip(self.step['names'],self.step['points']) if tuple(point)==tuple(p)),None)
            label=f'{name or self.step["tool"]} · F{self.step["floor"]} · ({p[0]:g}, {p[1]:g}) m'
            point=self.canvas.mapFromScene(QPointF(p[0],-p[1]));metrics=painter.fontMetrics()
            badge=QRect(point+QPoint(24,18),QSize(metrics.horizontalAdvance(label)+14,metrics.height()+10))
            badge.moveLeft(max(2,min(badge.left(),self.width()-badge.width()-2)))
            badge.moveTop(max(2,min(badge.top(),self.height()-badge.height()-2)))
            painter.setPen(QPen(QColor('#b33b00'),1));painter.setBrush(QColor('#fff5d6'))
            painter.drawRoundedRect(badge,4,4);painter.drawText(badge,Qt.AlignCenter,label)


class TargetOutline(QWidget):
    def __init__(self,parent):
        super().__init__(parent);self.setAttribute(Qt.WA_TransparentForMouseEvents);self.setAttribute(Qt.WA_NoSystemBackground)
        self.setFocusPolicy(Qt.NoFocus)
    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor('#0077cc'),3,Qt.DashLine));painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(self.rect().adjusted(2,2,-2,-2),5,5)


class DragHandle(QWidget):
    def __init__(self):
        super().__init__();self.setFixedWidth(20);self.setMinimumHeight(20);self.setFocusPolicy(Qt.NoFocus)
    def paintEvent(self,event):
        painter=QPainter(self);painter.setPen(Qt.NoPen);painter.setBrush(self.palette().windowText())
        for x in (6,12):
            for y in (self.height()//2-6,self.height()//2,self.height()//2+6):painter.drawEllipse(QPoint(x,y),1,1)

def place_bubble(size, available, owner, target, panes=(), controls=(), preferred=None):
    """Find clear space, prioritising the target and panes over proximity.

    Scan obstacle edges rather than pixels, so narrow gaps between controls are
    considered too. A crowded window can use neighbouring desktop space. If no
    completely clear position exists, retain access to the target and side panes
    first; the user can also drag the bubble out of the way.
    """
    width,height=size.width(),size.height();gap=10
    bounds=available.adjusted(6,6,-6,-6)
    def clamp(point):
        return QPoint(max(bounds.left(),min(point.x(),bounds.right()-width+1)),
                      max(bounds.top(),min(point.y(),bounds.bottom()-height+1)))
    anchor=preferred if preferred is not None else QPoint(target.right()+gap,target.top())
    obstacles=[r.adjusted(-gap,-gap,gap,gap) for r in (target,*panes,*controls) if not r.isEmpty()]
    ys={bounds.top(),bounds.bottom()-height+1,owner.top(),owner.bottom()-height+1,anchor.y()}
    for rect in obstacles:ys.update((rect.top()-height,rect.bottom()+1))
    points=[clamp(anchor)]
    for y in sorted(ys):
        y=clamp(QPoint(bounds.left(),y)).y()
        # Every free horizontal interval at this height contributes a candidate.
        intervals=sorted((r.left(),r.right()+1) for r in obstacles if r.top()<y+height and r.bottom()>=y)
        left=bounds.left()
        for start,end in intervals+[(bounds.right()+1,bounds.right()+1)]:
            if start-left>=width:
                points.append(clamp(QPoint(max(left,min(anchor.x(),start-width)),y)))
            left=max(left,end)
        # Fallback positions allow meaningful ordering even on a crowded screen.
        points.extend(clamp(QPoint(x,y)) for x in (bounds.left(),bounds.right()-width+1,
                      owner.left(),owner.right()-width+1,anchor.x(),target.left()-width-gap,target.right()+gap))
    def area(rect):return max(0,rect.width())*max(0,rect.height())
    def score(point):
        rect=QRect(point,size)
        overlap=lambda other:area(rect.intersected(other.adjusted(-gap,-gap,gap,gap)))
        # A safe manual position stays where it was put, including outside the
        # editor. Automatic placement favours blank space inside the workbench.
        distance=abs(point.x()-anchor.x())+abs(point.y()-anchor.y())
        return (overlap(target),sum(overlap(r) for r in panes),sum(overlap(r) for r in controls),
                0 if preferred is not None else area(rect)-area(rect.intersected(owner)),distance)
    return min(points,key=score)

class TutorialBubble(QDialog):
    flags=Qt.Tool|Qt.FramelessWindowHint|Qt.WindowStaysOnTopHint
    def __init__(self,course):
        super().__init__(course.editor,self.flags);self.course=course;self.editor=course.editor;self.target=None;self.outline=None
        self._manual_position=None;self._drag_offset=None;self._position_context=None
        self._running=False
        self.field_guide=DialogFieldGuide()
        self.editor.installEventFilter(self)
        self.route_overlay=CirculationOverlay(self.editor.canvas);self._correction=None
        self.setObjectName('buildingTutorialBubble');self.setAccessibleName('Building tutorial instruction bubble')
        self.setProperty('amrInstructionBubble',True)
        self.setAttribute(Qt.WA_StyledBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating);self.setFocusPolicy(Qt.NoFocus)
        self.setWindowModality(Qt.NonModal)
        self.setStyleSheet('#buildingTutorialBubble { border: 2px solid #0077cc; border-radius: 12px; }')
        layout=QVBoxLayout(self);layout.setContentsMargins(12,10,12,10)
        self.chapter=QComboBox();self.chapter.setAccessibleName('Tutorial bubble chapter')
        for n,lesson in enumerate(LESSONS,1):self.chapter.addItem(f'{n}. {lesson[1]}')
        self.chapter.currentIndexChanged.connect(self.chapter_changed)
        heading=QHBoxLayout();self.drag_handle=DragHandle()
        self.drag_handle.setAccessibleName('Move tutorial bubble');self.drag_handle.setToolTip('Drag to move this bubble')
        self.drag_handle.setCursor(Qt.SizeAllCursor);self.drag_handle.installEventFilter(self)
        heading.addWidget(self.drag_handle);heading.addWidget(self.chapter,1);layout.addLayout(heading)
        self.instruction=QLabel();self.instruction.setWordWrap(True);self.instruction.setTextFormat(Qt.PlainText)
        self.instruction.setAlignment(Qt.AlignLeft|Qt.AlignTop)
        self.instruction_scroll=QScrollArea();self.instruction_scroll.setWidgetResizable(True)
        self.instruction_scroll.setFrameShape(QScrollArea.NoFrame)
        self.instruction_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.instruction_scroll.setFocusPolicy(Qt.NoFocus);self.instruction_scroll.setWidget(self.instruction)
        layout.addWidget(self.instruction_scroll)
        self.feedback=QLabel();self.feedback.setWordWrap(True);layout.addWidget(self.feedback)
        self.explanation=QPlainTextEdit();self.explanation.setReadOnly(True);self.explanation.setMaximumHeight(140);self.explanation.hide();layout.addWidget(self.explanation)
        self.where=QLabel();self.where.setWordWrap(True);self.where.setAccessibleName('Tutorial placement name, floor and coordinates');layout.addWidget(self.where)
        row=QHBoxLayout();self.previous=QPushButton('Back');self.next=QPushButton('Next');self.check=QPushButton('Details')
        self.previous.clicked.connect(lambda:self.advance(-1));self.next.clicked.connect(lambda:self.advance(1));self.check.clicked.connect(self.toggle_details)
        for b in (self.previous,self.next,self.check):b.setFocusPolicy(Qt.NoFocus);b.setAutoDefault(False);row.addWidget(b)
        layout.addLayout(row);row=QHBoxLayout();self.locate_button=QPushButton('Show control');self.locate_button.clicked.connect(self.locate)
        self.pause_button=QPushButton('Pause');self.pause_button.clicked.connect(self.pause)
        more=QToolButton();more.setText('More');more.setPopupMode(QToolButton.InstantPopup)
        self.more_button=more
        menu=QMenu(more);menu.addAction('Show explanation / corrections',self.toggle_details)
        menu.addAction('Reset bubble position',self.reset_position)
        menu.addAction('Course reference',self.reference);menu.addActions(course.tools.menu().actions())
        policies=menu.addMenu('Flow policy')
        for label,index in [('Dedicated',0),('Shared',1)]:policies.addAction(label,lambda checked=False,index=index:course.policy.setCurrentIndex(index))
        more.setMenu(menu)
        for b in (self.locate_button,self.pause_button,more):
            b.setFocusPolicy(Qt.NoFocus)
            if isinstance(b,QPushButton):b.setAutoDefault(False)
            row.addWidget(b)
        layout.addLayout(row);self.setFixedWidth(370)
        self.timer=QTimer(self);self.timer.setInterval(250);self.timer.timeout.connect(self.follow)
        self._checking=False;self._auto_token=None;self._auto_after=0
        self._owner=self.editor
        self.course.chapters.currentIndexChanged.connect(self.refresh)
        self.refresh()

    def chapter_changed(self,index):
        old=self.course.chapters.currentIndex()
        if index>old:
            for chapter in range(old,index):
                issues=self.course.session.check(chapter,self.editor.store.data,self.course.context())
                if issues:
                    self.chapter.blockSignals(True);self.chapter.setCurrentIndex(old);self.chapter.blockSignals(False)
                    self.feedback.setText('Finish this chapter first: '+issues[0]);self.show_correction(chapter);return
        self.course.session.state['action']=0;self.course.chapters.setCurrentIndex(index);self.persist();self.refresh();self.locate()
    def persist(self):
        try:self.course.session.save()
        except OSError as exc:self.feedback.setText('Progress could not save: '+str(exc))
    def current(self):
        chapter=max(0,self.course.chapters.currentIndex());actions=ACTIONS[chapter]
        index=max(0,min(int(self.course.session.state.get('action',0)),len(actions)-1))
        return chapter,index,actions[index]
    def refresh(self,*_):
        chapter,index,action=self.current();self.chapter.blockSignals(True);self.chapter.setCurrentIndex(chapter);self.chapter.blockSignals(False)
        self.chapter.setToolTip(self.chapter.currentText())
        self.instruction.setText(f'Action {index+1}/{len(ACTIONS[chapter])}: '+action[1])
        if chapter==2:
            step=CIRCULATION_STEPS[index]
            self.instruction.setText(f"{index+1}/{len(CIRCULATION_STEPS)} — {step['title']}\n{step['instruction']}")
        elif chapter==3 and index==0:
            self.instruction.setText('1/4 — Place the four facilities\nChoose Location; follow the numbered markers.')
        self._instruction_text=self.instruction.text()
        result=self.course.session.state['completed'].get(LESSONS[chapter][0],{})
        self.feedback.setText('This step is checked automatically as you work.')
        self.explanation.setPlainText(action[1]+'\n\n'+self.course.details.toPlainText()+'\n\n'+'\n'.join(result.get('issues',[])))
        self.previous.setEnabled(chapter>0 or index>0)
        checked=self.course.session.state.get('action_checks',{}).get(f'{chapter}:{index}',{})
        self.next.setEnabled(checked.get('passed',False) and checked.get('config_hash')==config_hash(self.editor.store.data)
                             and (chapter<11 or index<len(ACTIONS[chapter])-1))
        self.next.setToolTip('Next chapter' if index==len(ACTIONS[chapter])-1 else 'Next action')
        self.fit_contents()
        if self.isVisible():self.follow()
    def advance(self,direction):
        chapter,index,_=self.current()
        if direction>0 and not self.check_action():return
        index+=direction
        if index<0:chapter=max(0,chapter-1);index=len(ACTIONS[chapter])-1
        elif index>=len(ACTIONS[chapter]):chapter=min(11,chapter+1);index=0
        self.course.chapters.setCurrentIndex(chapter);self.course.session.state['action']=index;self.persist();self.refresh();self.locate()
    def check_chapter(self):
        self.check_action()

    def check_action(self,*,automatic=False):
        if self._checking:return False
        self._checking=True
        try:
            self.course.sync();chapter,index,_=self.current()
            context=self.course.context()
            issues=[message for n in range(index+1) for message in action_issues(self.course.session,chapter,n,self.editor.store.data,context)]
            if chapter==2:
                roles=self.course.session.roles(self.editor.store.data)
                issues=[r['message'] for n in range(index+1) for r in inspect_step(self.editor.store.data,n,roles)]
                if CIRCULATION_STEPS[index]['kind']=='route' and self.editor.corridor_draw_start is not None:
                    issues.append('Finish the current route with Escape before continuing.')
            if not issues and index==len(ACTIONS[chapter])-1:
                issues=self.course.session.check(chapter,self.editor.store.data,self.course.context())
            record=dict(passed=not issues,config_hash=config_hash(self.editor.store.data))
            checks=self.course.session.state.setdefault('action_checks',{})
            if checks.get(f'{chapter}:{index}')!=record:
                checks[f'{chapter}:{index}']=record;self.persist()
            self.refresh()
            self.feedback.setText(issues[0] if issues else 'Step verified. Next is ready when you are.')
            self.fit_contents()
            self.explanation.setPlainText(self.current()[2][1]+'\n\n'+self.course.details.toPlainText()+'\n\n'+'\n'.join(issues))
            if issues:
                if automatic:
                    spatial=[r for n in range(index+1) for r in placement_issues(chapter,n,self.editor.store.data,self.course.session.roles(self.editor.store.data))]
                    self._correction=spatial[0] if spatial and (spatial[0].get('property') or spatial[0].get('connection')) else None
                else:self.show_correction(chapter)
            else:self._correction=None
            return not issues
        except (OSError,ValueError,KeyError,TypeError) as exc:
            self.feedback.setText('Could not verify this step: '+str(exc));self.next.setEnabled(False);return False
        finally:self._checking=False

    def automatic_validation(self):
        if self._checking or time.monotonic()<self._auto_after:return
        self._auto_after=time.monotonic()+.75
        self._checking=True
        try:self.course.sync();context=dict(self.course.context())
        finally:self._checking=False
        study=context.pop('study',None) or {}
        context['study']={k:study.get(k) for k in ('status','confirmed','baseline_complete','variant','recommendation','tutorial_exports')}
        context['proposals']=sorted(study.get('proposals',{}))
        run=context.get('run')
        evidence=[]
        if run:
            from pathlib import Path
            root=Path(run)
            from amr_project_runs import MANIFEST
            for path in [root/MANIFEST,*(root/'reports').rglob('*.pdf'),*(root/'reports').rglob('*.csv')]:
                try:evidence.append((str(path),path.stat().st_mtime_ns,path.stat().st_size))
                except OSError:pass
        session=self.course.session.state
        token=(self.current()[:2],config_hash(self.editor.store.data),self.editor.corridor_draw_start,tuple(session['seen']),session['policy'],
               json.dumps(session['bindings'],sort_keys=True,default=str),json.dumps(context,sort_keys=True,default=str),tuple(evidence))
        if token!=self._auto_token:
            self._auto_token=token;self.check_action(automatic=True)

    def show_correction(self,chapter):
        self._correction=None
        if placement_step(chapter,self.current()[1],self.editor.store.data,self.course.session.roles(self.editor.store.data)):
            roles=self.course.session.roles(self.editor.store.data)
            issues=[r for n in range(self.current()[1]+1) for r in placement_issues(chapter,n,self.editor.store.data,roles)]
            if not issues and chapter==2:issues=inspect_all(self.editor.store.data,roles)
            if issues:
                self._correction=issues[0]
                if self.editor.workspace.stage!='layout':self.editor.workspace.activate('layout')
                self.editor.floor_spin.setValue(self._correction['floor'])
                self.editor.canvas.centerOn(QPointF(self._correction['point'][0],-self._correction['point'][1]))
        self.follow()
    def fit_contents(self):
        # QWidget.adjustSize caps top-level windows using desktop size. Explicit
        # height-for-width keeps wrapped guidance readable on scaled displays.
        layout=self.layout()
        width=max(370,min(470,self.fontMetrics().horizontalAdvance('Show control  Pause  More')+86))
        self.setFixedWidth(width)
        self.instruction.setMinimumHeight(0)
        full_height=self.instruction.heightForWidth(width-42)
        self.instruction.setMinimumHeight(max(0,full_height))
        cap=max(130,int(self.available_geometry(self.editor).height()*.48))
        self.instruction_scroll.setFixedHeight(max(28,min(full_height,cap)))
        layout.invalidate();layout.activate()
        height=layout.totalHeightForWidth(width)
        self.resize(self.width(),height if height>=0 else layout.sizeHint().height())
    def toggle_details(self):self.explanation.setVisible(not self.explanation.isVisible());self.fit_contents();self.follow()
    def reference(self):
        dialog=self.course.window();dialog.tabs.setCurrentWidget(self.course);dialog.show();dialog.raise_()
    def resume(self):
        self.course.sync();self.skip_completed();self.course.session.state['paused']=False;self.persist()
        self._running=True;self.timer.start();self.refresh();self.locate()

    def skip_completed(self):
        """Resume at the first unfinished action, retaining Back for review."""
        chapter,index,_=self.current();start=(chapter,index)
        session=self.course.session;context=self.course.context()
        while chapter<len(ACTIONS):
            completed=session.state['completed'].get(LESSONS[chapter][0],{}).get('passed')
            if completed:
                if chapter==len(ACTIONS)-1:
                    index=len(ACTIONS[chapter])-1;break
                chapter+=1;index=0;continue
            record=session.state.get('action_checks',{}).get(f'{chapter}:{index}',{})
            if not record.get('passed'):break
            # Drawing paths change on reopen. Recheck authored state when its
            # hash changes; workbench interactions remain historical evidence.
            if (record.get('config_hash')!=config_hash(self.editor.store.data) and chapter!=1
                    and action_issues(session,chapter,index,self.editor.store.data,context)):break
            if index==len(ACTIONS[chapter])-1:break
            index+=1
        if (chapter,index)!=start:
            self.course.chapters.setCurrentIndex(chapter)
            session.state['action']=index
            self.persist();self.refresh()
    def pause(self):
        self._running=False;self.course.session.state['paused']=True;self.persist();self.timer.stop();self.hide_aids()
    def hide_aids(self):
        self.hide()
        self.field_guide.clear()
        if self.outline:self.outline.hide()
        self.route_overlay.hide()
    def closeEvent(self,event):
        # This independent instruction window is controlled only by Pause or
        # Restart. Closing another editor must not close its guidance.
        if self._running:event.ignore()
        else:event.accept()

    def reject(self):
        if not self._running:super().reject()

    def dispose(self):
        """Replace only the instruction UI, leaving course progress intact."""
        from shiboken6 import isValid
        self._running=False
        if isValid(self):
            self.timer.stop();self.hide()
            self.editor.removeEventFilter(self)
            owner=self._owner
            if owner and isValid(owner) and owner is not self.editor:owner.removeEventFilter(self)
            self.course.chapters.currentIndexChanged.disconnect(self.refresh)
            self.deleteLater()
        # These hints belong to the canvas/target window, not to this bubble.
        # Clean them up even if a temporary owner already deleted the bubble.
        for hint in (self.outline,self.route_overlay):
            if hint is not None and isValid(hint):hint.hide();hint.deleteLater()
        self.outline=None
        self.field_guide.clear()

    def resolve(self):
        chapter,_,(selector,_,field)=self.current();stage=LESSONS[chapter][2]
        from tutorial_controls import dialog_target, workspace_target, reveal, labelled
        modal=QApplication.activeModalWidget()
        if modal:
            target=dialog_target(self,modal)
            if target:return target
        else:
            target=workspace_target(self)
            if target:return target
        step=placement_step(chapter,self.current()[1],self.editor.store.data,self.course.session.roles(self.editor.store.data))
        if step and self.editor.workspace.stage=='layout' and not QApplication.activeModalWidget():
            issues=placement_issues(chapter,self.current()[1],self.editor.store.data,self.course.session.roles(self.editor.store.data))
            issue=self._correction or (issues[0] if issues else None)
            floor=issue['floor'] if issue else step['floor']
            if self.editor.floor_spin.value()!=floor:return self.editor.floor_spin,None
            if issue:
                field_widget=self.editor.properties_panel.fields.get(issue.get('property'))
                if field_widget and field_widget.isVisible() and self.editor.properties_panel.target==('points',(issue.get('name'),)):
                    return field_widget,None
                if field_widget and field_widget.isVisible() and 'edge_index' in issue and self.editor.properties_panel.target==('edges',(issue['edge_index'],)):
                    return field_widget,None
                mode=('select_move' if issue.get('property') else
                      {'Corridor':'corridor_draw','Door':'door','Location':'location','Department':'department','Lift':'lift','Select':'select_move'}.get(step['tool']))
                if chapter==2 and step['points']==[(3,7),(3,10),(3,13)] and issue['point']==(3,10) and not issue.get('start'):
                    mode='corridor_node'
                if mode and self.editor._current_edit_mode()!=mode:
                    return self.editor.cad_toolbar.widgetForAction(self.editor.cad_toolbar.mode_actions[mode]),None
                point=issue.get('start',issue['point'])
                anchor=self.editor.store.all_points().get(self.editor.corridor_draw_start,{})
                if issue.get('start') and anchor and abs(anchor.get('x',-999)-point[0])<.05 and abs(anchor.get('y',-999)-point[1])<.05:
                    point=issue['point']
                p=self.editor.canvas.mapFromScene(QPointF(point[0],-point[1]))
                return self.editor.canvas.viewport(),QRect(p-QPoint(23,23),QSize(46,46))
        modal=QApplication.activeModalWidget()
        if chapter==3 and self.current()[1] in (2,3) and modal is None:
            index=self.current()[1]
            role='dirty_receiving' if index==2 else 'wash'
            name=self.course.session.roles(self.editor.store.data).get(role)
            panel=self.editor.properties_panel
            target=('points',(name,))
            if panel.selection()==target:
                if self.editor.workspace.properties.isHidden():return self.editor.workspace.properties_tab,None
                if panel.pending and panel.target!=target:return panel.discard_button,None
                if panel.target==target:
                    expected=(('wash_cycle_required',True),('wash_location',self.course.session.roles(self.editor.store.data).get('wash')),
                              ('wash_cycle_duration_sec',60)) if index==2 else (('max_concurrency',1),)
                    for key,value in expected:
                        widget=panel.fields.get(key)
                        if widget is None:continue
                        current=panel.value(widget)
                        if key in ('wash_cycle_duration_sec','max_concurrency'):
                            try:current=float(current)
                            except (TypeError,ValueError):current=None
                        if current!=value:
                            panel.scroll.ensureWidgetVisible(widget,0,20)
                            return widget,None
                    if panel.pending:return panel.apply_button,None
                    widget=panel.fields[expected[0][0]]
                    panel.scroll.ensureWidgetVisible(widget,0,20)
                    return widget,None
        if chapter==3 and self.current()[1]==1:
            from dialogs import InventorySpacesDialog
            if isinstance(modal, InventorySpacesDialog):
                bays=[n for n,space in enumerate(modal.spaces) if inventory_space_is_amr(space)]
                if modal.tutorial_charging_bays and not bays:return modal.tutorial_bays_button,None
                if modal.tutorial_charging_bays and len(bays)>=4 and all(modal.spaces[n].get('has_charger') for n in bays):
                    return next(w for w in modal.findChildren(QPushButton) if w.text()=='Save and close'),None
                if not modal.amr_space_combo.currentText().strip():
                    if modal.space_properties.isHidden():return modal.commands.widgetForAction(modal.properties_action),None
                    return modal.amr_space_combo,None
                label='Add AMR space' if len(bays)<4 else 'Set chargers'
                if len(bays)>=4:
                    if all(modal.spaces[n].get('has_charger') for n in bays):label='Save and close'
                    elif not set(bays)<=modal.selected_space_indices:return modal.space_list,None
                if label=='Add AMR space':return modal.commands.widgetForAction(modal.command_actions[label]),None
                if label=='Set chargers' and modal.space_properties.isHidden():return modal.commands.widgetForAction(modal.properties_action),None
                return next(w for w in modal.findChildren(QPushButton) if w.text()==label),None
            if modal is None:
                dispatch=self.course.session.roles(self.editor.store.data).get('dispatch','Dispatch')
                panel=self.editor.properties_panel
                if panel.selection()==('points',(dispatch,)):
                    if not self.editor.workspace.properties.isHidden() and panel.spaces_button.isVisible():return panel.spaces_button,None
                    return self.editor.workspace.properties_tab,None
                row=self.editor.store.get_location(dispatch)
                if row:
                    p=self.editor.canvas.mapFromScene(QPointF(row['x'],-row['y']))
                    return self.editor.canvas.viewport(),QRect(p-QPoint(23,23),QSize(46,46))
        if modal and chapter==2 and self._correction and self._correction.get('expected_name'):
            from dialogs import PointEditorDialog
            if isinstance(modal,PointEditorDialog):return modal.name_edit,None
        if modal and getattr(self.editor,'_pending_insertion',None):
            field_widget=modal.findChild(QLineEdit)
            if field_widget:return field_widget,None
        if modal is None and selector!='Plan lift locations':
            for widget in self.editor.findChildren(QAbstractButton):
                if widget.text().replace('&','')==selector:
                    target=reveal(widget)
                    if target:return target
        dialogs=[modal] if modal else [w for w in QApplication.topLevelWidgets() if w.isVisible() and w is not self and w is not self.editor and w is not self.course.window()]
        if field:
            for dialog in dialogs:
                if dialog is None:continue
                target=reveal(labelled(dialog,field))
                if target:return target
                for widget in dialog.findChildren(QWidget):
                    if self.isAncestorOf(widget):continue
                    text=widget.text() if isinstance(widget,(QLabel,QAbstractButton)) else ''
                    if field.lower() in text.lower():
                        if isinstance(widget,QLabel):
                            if widget.buddy():
                                target=reveal(widget.buddy())
                                if target:return target
                            parent=widget.parentWidget();form=parent.layout() if parent else None
                            if isinstance(form,QFormLayout):
                                row,role=form.getWidgetPosition(widget);item=form.itemAt(row,QFormLayout.FieldRole)
                                if item and item.widget():
                                    target=reveal(item.widget())
                                    if target:return target
                        target=reveal(widget)
                        if target:return target
        if selector.startswith('menu:'):
            menu=next((a for a in self.editor.menuBar().actions() if a.text().replace('&','')==selector[5:]),None)
            if menu:return self.editor.menuBar(),self.editor.menuBar().actionGeometry(menu)
        if selector.startswith('role:'):
            name=self.course.session.roles(self.editor.store.data).get(selector[5:]);row=next((r for r in self.editor.store.data['locations'] if r['name']==name),None)
            if row and self.editor.workspace.stage=='layout' and self.editor.floor_spin.value()==row['floor']:
                p=self.editor.canvas.mapFromScene(QPointF(row['x'],-row['y']));return self.editor.canvas.viewport(),QRect(p.x()-20,p.y()-20,40,40)
            return self.editor.floor_spin,None
        if selector.startswith('attr:'):
            name=selector[5:];special={'fit':self.editor.cad_toolbar.fit_action,'undo':self.editor.undo_action,'properties':self.editor.workspace.properties_tab}
            widget=special.get(name,getattr(self.editor,name,None))
            if isinstance(widget,QAction):widget=self.editor.cad_toolbar.widgetForAction(widget) or self.editor.workbench.workflow.widgetForAction(widget)
            if widget and widget.isVisible():return widget,None
        if selector.startswith('action:'):
            token=selector[7:]
            for toolbar in (self.editor.cad_toolbar,self.editor.workbench.workflow):
                for action in toolbar.actions():
                    widget=toolbar.widgetForAction(action)
                    if token.lower() in action.text().lower() and widget and widget.isVisible():return widget,None
        for widget in self.editor.findChildren(QAbstractButton):
            if widget.text().replace('&','')==selector:
                target=reveal(widget)
                if target:return target
        if selector.startswith('stage:'):stage=selector[6:]
        if selector.startswith('layout:'):stage='layout'
        action=self.editor.workbench.stages[stage]
        return self.editor.workbench.workflow.widgetForAction(action),None

    def locate(self):
        # Only a requested workspace change. No dialog or Properties opens here.
        self._manual_position=None
        self._correction=None
        chapter,_,action=self.current();stage=LESSONS[chapter][2]
        selector=action[0]
        if selector.startswith('menu:'):stage=self.editor.workspace.stage
        if selector.startswith('stage:'):stage=selector[6:]
        from project_workspace import CONFIGURATION
        if selector in {title for title,_ in CONFIGURATION}:stage='configuration'
        if not QApplication.activeModalWidget() and self.editor.workspace.stage!=stage:self.editor.workspace.activate(stage)
        step=placement_step(chapter,self.current()[1],self.editor.store.data,self.course.session.roles(self.editor.store.data))
        if step and not QApplication.activeModalWidget() and stage=='layout':
            self.editor.floor_spin.setValue(step['floor'])
        widget,rect=self.resolve()
        if widget:
            parent=widget.parentWidget()
            while parent:
                if isinstance(parent,QScrollArea):parent.ensureWidgetVisible(widget);break
                parent=parent.parentWidget()
        self.follow()

    def reset_position(self):self._manual_position=None;self.follow()

    def available_geometry(self,widget):
        screen=widget.screen()
        # Qt's offscreen backend supplies an anonymous placeholder desktop;
        # screen captures instead exercise the requested logical editor size.
        return screen.availableGeometry() if screen and screen.name() else self.editor.frameGeometry()

    def visible_rect(self,widget):
        """Global visible extent, clipped by scroll viewports and ancestors."""
        rect=QRect(widget.mapToGlobal(QPoint()),widget.size());parent=widget
        while parent:
            rect=rect.intersected(QRect(parent.mapToGlobal(QPoint()),parent.size()))
            if parent.isWindow():break
            parent=parent.parentWidget()
        return rect

    def obstacles(self,owner):
        workspace=self.editor.workspace
        panes=[w for w in (workspace.sidebar,workspace.properties,workspace.properties_rail,
                          *self.editor.findChildren(QDockWidget)) if w.isVisible()]
        pane_rects=[self.visible_rect(w) for w in panes]
        controls=[]
        if owner.inherits('QInputDialog'):
            controls.append(self.visible_rect(owner))
        # A modal editor blocks the underlying application's controls. Keep its
        # active fields/buttons clear, along with the permanent side panes.
        for window in (owner,):
            for widget in window.findChildren(QWidget):
                if (widget.window() is not window or not widget.isVisible() or
                    self.isAncestorOf(widget) or any(w.isAncestorOf(widget) for w in panes)):continue
                if isinstance(widget,(QAbstractButton,QAbstractSpinBox,QLineEdit,QComboBox,
                                      QAbstractItemView,QTabBar,QPlainTextEdit)):
                    rect=self.visible_rect(widget)
                    if not rect.isEmpty():controls.append(rect)
        return pane_rects,controls

    def follow(self):
        # Visibility is transient when Qt closes a file/loading dialog or changes
        # a tool window's owner. Only an explicit pause stops the walkthrough.
        if not self._running or self.course.session.state['paused']:
            self.hide_aids();return
        if not self.editor.isVisible() or self.editor.isMinimized():
            self.hide_aids();return
        if self._drag_offset is not None:return
        self.automatic_validation()
        modal=QApplication.activeModalWidget();owner=modal or self.editor
        self.chapter.setEnabled(not modal)
        self.more_button.setEnabled(not modal)
        self.previous.setEnabled(not modal and (self.current()[0]>0 or self.current()[1]>0))
        focus=QApplication.focusWidget();active=QApplication.activeWindow()
        self.set_owner(owner)
        if not self.isVisible():
            self.show()
            if focus and active and active is not self:
                QTimer.singleShot(0,lambda:self.restore_focus(active,focus))
        widget,rect=self.resolve()
        if widget is None:
            self.field_guide.clear();return
        chapter,index,_=self.current();roles=self.course.session.roles(self.editor.store.data)
        checked=self.course.session.state.get('action_checks',{}).get(f'{chapter}:{index}',{})
        self.next.setEnabled(checked.get('passed',False) and checked.get('config_hash')==config_hash(self.editor.store.data)
                             and not modal and (chapter<11 or index<len(ACTIONS[chapter])-1))
        step=placement_step(chapter,index,self.editor.store.data,roles)
        hint=widget.property('amrTutorialHint')
        dialog=widget.window() if isinstance(widget.window(),QDialog) and widget.window() is not self else None
        inline=self.field_guide.show(widget,hint) if dialog else False
        if not dialog:self.field_guide.clear()
        self.instruction.setText(self._instruction_text)
        if dialog:
            prompt=('Enter the value beside the highlighted field. Guidance moves on as each value matches.' if inline else
                    'Open the highlighted tab to continue.' if isinstance(widget,QTabBar) else
                    'Save this editor to keep these values.' if isinstance(widget,QAbstractButton) and widget.text().replace('&','') in ('Save','OK','Save All','Apply Changes') else
                    'Use the highlighted control to continue. Details contains the full action checklist.')
            self.instruction.setText(f'Action {index+1}/{len(ACTIONS[chapter])} — {dialog.windowTitle()}\n'+prompt)
        self.where.setVisible(step is not None or bool(hint))
        if not step and hint:self.where.setText(hint)
        issues=placement_issues(chapter,index,self.editor.store.data,roles) if step else []
        prior=[r for n in range(index) for r in placement_issues(chapter,n,self.editor.store.data,roles)] if step else []
        if step:
            correction=self._correction
            if correction and correction not in issues+prior:self._correction=None;correction=None
            if correction:
                step=next((placement_step(chapter,n,self.editor.store.data,roles) for n in range(index+1)
                           if correction in placement_issues(chapter,n,self.editor.store.data,roles)),step)
            self.route_overlay.step=step;self.route_overlay.issue=correction or (issues[0] if issues else None)
            issue=self.route_overlay.issue;self.route_overlay.next_point=issue.get('start',issue['point']) if issue else None
            anchor=self.editor.store.all_points().get(self.editor.corridor_draw_start,{})
            if issue and issue.get('start') and anchor and abs(anchor.get('x',-999)-issue['start'][0])<.05 and abs(anchor.get('y',-999)-issue['start'][1])<.05:
                self.route_overlay.next_point=issue['point']
            floor=issue['floor'] if issue else step['floor']
            self.route_overlay.step=dict(step,floor=floor)
            point=self.route_overlay.next_point or step['points'][0]
            name=(issue.get('expected_name') or issue.get('name')) if issue else None
            if chapter==2 and step['points']==[(3,7),(3,10),(3,13)] and issue and issue['point']==(3,10) and not issue.get('start'):
                name='Shared transition'
            if not name and step.get('names'):
                name=next((name for name,p in zip(step['names'],step['points']) if tuple(p)==tuple(point)),None)
            self.where.setText(f'{name or step["tool"]} · Floor {floor} · X {point[0]:g}, Y {point[1]:g} m')
            pending=getattr(self.editor,'_pending_insertion',None)
            if pending:
                actual=(pending['x'],pending['y'])
                expected=issue and tuple(point)==tuple(issue.get('point',point))
                wrong=expected and (pending['floor']!=floor or abs(actual[0]-point[0])>.05 or abs(actual[1]-point[1])>.05)
                self.where.setText(self.where.text()+
                    (f'\nClicked: floor {pending["floor"]}, X {actual[0]:g}, Y {actual[1]:g} m. Cancel and use the highlighted position.' if wrong else '\nSave the shown name, or Cancel to discard.'))
            self.route_overlay.setGeometry(self.editor.canvas.viewport().rect())
            self.route_overlay.setVisible(self.editor.workspace.stage=='layout' and self.editor.floor_spin.value()==floor)
            self.route_overlay.raise_();self.route_overlay.update()
            if issues:
                issue=issues[0];point=issue.get('start',issue['point']);anchor=self.editor.store.all_points().get(self.editor.corridor_draw_start,{})
                if issue.get('start') and anchor and abs(anchor.get('x',-999)-point[0])<.05 and abs(anchor.get('y',-999)-point[1])<.05:point=issue['point']
                if chapter==3 and index==0 and issue.get('missing'):
                    self.feedback.setText('Next location: '+issue['name']+'.')
                elif name=='Shared transition':self.feedback.setText('Choose Transition; click marker 2 at (3,10) m.')
                elif issue.get('property') or issue.get('name'):self.feedback.setText(issue['message'])
                else:
                    marker=next((n for n,p in enumerate(step['points'],1) if tuple(p)==tuple(point)),None)
                    self.feedback.setText(('Missing link. ' if issue.get('start') else '')+f"Click {'marker '+str(marker) if marker else 'the highlighted point'} at ({point[0]},{point[1]}) m."+
                        (' Keep 2.4 m width and both directions.' if step['kind']=='route' else ''))
            elif prior:self.feedback.setText('An earlier route changed: '+prior[0]['message'])
            elif step['kind']=='route' and self.editor.corridor_draw_start is not None:
                self.next.setEnabled(False);self.feedback.setText('Route complete. Press Escape to finish drawing; then Next becomes available.')
            elif checked.get('passed'):self.feedback.setText('Step verified automatically. Next is ready when you are.')
        else:self.route_overlay.hide()
        if chapter==5 and self.editor.route_profile_selection_active and self.editor.route_profile_select_edges:
            self.instruction.setText(f'Action {index+1}/{len(ACTIONS[chapter])} — Select route permissions in Layout\n'
                'Select orange nodes and dashed edges; blue means selected. Change floor and selection mode using the toolbar. Finish selection returns to the profile editor.')
        prefix='Save or Cancel this editor before continuing. '
        self.feedback.setText(self.feedback.text().removeprefix(prefix))
        if dialog and hint:
            self.where.setVisible(not inline);self.where.setText(hint)
        if modal:
            self.next.setEnabled(False)
            if not getattr(self.editor,'_pending_insertion',None):self.feedback.setText(prefix+self.feedback.text())
        self.fit_contents()
        window=widget.window()
        if self.outline is None or self.outline.parentWidget() is not window:
            if self.outline:self.outline.hide();self.outline.deleteLater()
            self.outline=TargetOutline(window)
            outline=self.outline
            outline.destroyed.connect(lambda:self.outline_destroyed(outline))
        rect=rect or widget.rect();global_top=widget.mapToGlobal(rect.topLeft());local=window.mapFromGlobal(global_top)
        self.outline.setGeometry(QRect(local,rect.size()).adjusted(-3,-3,3,3));self.outline.show();self.outline.raise_()
        context=(self.current()[:2],owner)
        if context!=self._position_context:self._manual_position=None;self._position_context=context
        target=QRect(global_top,rect.size())
        if widget in (self.editor.canvas,self.editor.canvas.viewport()) and self.current()[2][0]=='attr:canvas':
            # Canvas lessons need room for a small card without covering the
            # centre where the drawing/edit occurs; node highlights stay exact.
            target=QRect(target.center()-QPoint(25,25),QPoint(target.center()+QPoint(25,25)))
        panes,controls=self.obstacles(owner)
        if inline:controls.append(self.visible_rect(self.field_guide.label))
        available=self.available_geometry(widget)
        self.move(place_bubble(self.size(),available,self.visible_rect(owner),target,panes,controls,self._manual_position))
        self.target=widget

    def set_owner(self,owner):
        # QObject ownership stays with the main editor for the bubble's entire
        # lifetime. Native transient ownership alone follows a modal editor.
        from shiboken6 import isValid
        previous=self._owner
        if previous is owner:return
        if previous and isValid(previous) and previous is not self.editor:previous.removeEventFilter(self)
        self._owner=owner
        if owner is not self.editor:owner.installEventFilter(self)
        self.winId();owner.winId()
        self.windowHandle().setTransientParent(owner.windowHandle())
        self.raise_()
        owner.destroyed.connect(lambda:self.owner_destroyed(owner))

    def owner_destroyed(self,owner):
        from shiboken6 import isValid
        if isValid(self) and self._owner is owner and isValid(self.editor):self.set_owner(self.editor)

    def restore_focus(self,window,widget):
        # Some Qt backends activate a reshown tool despite
        # WA_ShowWithoutActivating. Restore only focus that our own show took.
        from shiboken6 import isValid
        if (isValid(self) and isValid(window) and isValid(widget) and
            QApplication.activeWindow() is self and window.isVisible() and
            QApplication.activeModalWidget() in (None,window) and not QApplication.activePopupWidget()):
            window.activateWindow();widget.setFocus(Qt.OtherFocusReason)

    def outline_destroyed(self,outline):
        if self.outline is outline:self.outline=None

    def eventFilter(self,watched,event):
        if watched is self.drag_handle:
            if event.type()==QEvent.MouseButtonPress and event.button()==Qt.LeftButton:
                self._drag_offset=event.globalPosition().toPoint()-self.pos();return True
            if event.type()==QEvent.MouseMove and self._drag_offset is not None:
                point=event.globalPosition().toPoint()-self._drag_offset
                screen=QApplication.screenAt(event.globalPosition().toPoint()) or self.screen()
                bounds=screen.availableGeometry() if screen and screen.name() else self.editor.frameGeometry()
                point=QPoint(max(bounds.left(),min(point.x(),bounds.right()-self.width()+1)),
                             max(bounds.top(),min(point.y(),bounds.bottom()-self.height()+1)))
                self.move(point);self._manual_position=point;return True
            if event.type()==QEvent.MouseButtonRelease and self._drag_offset is not None:
                self._drag_offset=None;self.follow();return True
        if event.type() in (QEvent.Hide,QEvent.Close,QEvent.DeferredDelete):
            if watched is self.editor:
                if event.type()==QEvent.DeferredDelete:
                    self._running=False;self.timer.stop()
                elif event.type()==QEvent.Hide:
                    self.set_owner(self.editor);self.hide_aids()
            elif watched is self._owner:
                self.set_owner(self.editor)
                if self.outline:self.outline.hide()
        return False
