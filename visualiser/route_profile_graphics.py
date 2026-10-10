"""Draft route permissions selected on the existing CAD layout."""
from PySide6.QtCore import Qt,QPoint,QRect,QSize
from PySide6.QtGui import QColor,QPainter,QPen
from PySide6.QtWidgets import QWidget,QToolBar,QLabel,QComboBox,QPushButton,QMenu,QSpinBox
import math


def edge_pairs(edges,nodes=None):
    pairs=set()
    for edge in edges:
        a,b=edge['from'],edge['to']
        if nodes is not None and not {a,b}<=set(nodes):continue
        pairs.add((a,b))
        if edge.get('bidirectional',True):pairs.add((b,a))
    return pairs


class RoutePermissionOverlay(QWidget):
    def __init__(self,editor):
        super().__init__(editor.canvas.viewport());self.editor=editor
        self.nodes=set();self.edges=set()
        self.setAttribute(Qt.WA_TransparentForMouseEvents);self.setAttribute(Qt.WA_NoSystemBackground)
        self.setFocusPolicy(Qt.NoFocus);self.setAccessibleName('Required tutorial route nodes and edges')
    def paintEvent(self,event):
        editor=self.editor;points=editor.store.points_for_floor(editor.floor_spin.value())
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing)
        def screen(name):
            p=points[name];return editor.canvas.mapFromScene(editor.world_to_scene(p['x'],p['y']))
        drawn=set()
        for a,b in sorted(self.edges):
            if a not in points or b not in points or frozenset((a,b)) in drawn:continue
            drawn.add(frozenset((a,b)))
            selected=(a,b) in editor.route_profile_selected_edges
            painter.setPen(QPen(QColor('#0077cc' if selected else '#b45309'),4,Qt.SolidLine if selected else Qt.DashLine))
            if screen(a)==screen(b):painter.drawEllipse(screen(a),18,18)
            else:painter.drawLine(screen(a),screen(b))
        for name in sorted(self.nodes&set(points)):
            selected=name in editor.route_profile_selected_nodes
            painter.setPen(QPen(QColor('#0077cc' if selected else '#b45309'),2))
            painter.setBrush(Qt.NoBrush);painter.drawEllipse(screen(name),12,12)


class RoutePermissionSelection:
    def __init__(self,editor):
        self.editor=editor;self.overlay=RoutePermissionOverlay(editor)
        self.toolbar=QToolBar('Route profile selection',editor);self.toolbar.setObjectName('routePermissionToolbar')
        self.toolbar.setMovable(False);editor.addToolBarBreak(Qt.TopToolBarArea)
        editor.addToolBar(Qt.TopToolBarArea,self.toolbar)
        self.title=QLabel();self.toolbar.addWidget(self.title)
        self.toolbar.addWidget(QLabel(' Floor '));self.floor=QSpinBox()
        self.floor.setAccessibleName('Route permission drawing floor')
        self.floor.valueChanged.connect(editor.floor_spin.setValue)
        editor.floor_spin.valueChanged.connect(self.floor.setValue);self.toolbar.addWidget(self.floor)
        self.toolbar.addWidget(QLabel(' Select '));self.mode=QComboBox()
        self.mode.addItems(['Nodes','Edges']);self.mode.setAccessibleName('Route permission selection mode')
        self.toolbar.addWidget(self.mode);self.counts=QLabel();self.toolbar.addWidget(self.counts)
        self.finish=QPushButton('Finish selection');self.cancel=QPushButton('Cancel selection')
        self.finish.clicked.connect(editor._finish_route_profile_graphical_selection)
        self.cancel.clicked.connect(editor._cancel_route_profile_graphical_selection)
        self.toolbar.addWidget(self.finish);self.toolbar.addWidget(self.cancel);self.toolbar.hide();self.overlay.hide()
    def start(self,name):
        self.editor.workspace.activate('layout')
        self.floor.setRange(0,max((int(p['floor']) for p in self.editor.store.all_points().values()),default=0))
        self.floor.setValue(self.editor.floor_spin.value())
        self.mode.setCurrentIndex(0);self.title.setText(f' Route profile: {name or "draft"}  ')
        self.overlay.nodes=set();self.overlay.edges=set()
        actions=[action for mode,action in self.editor.cad_toolbar.mode_actions.items() if mode!='select_move']
        actions += [self.editor.workbench.add_node_action,self.editor.workbench.add_edge_action,self.editor.workbench.route_profiles_action]
        self._action_states=[(action,action.isEnabled()) for action in actions]
        for action,_ in self._action_states:action.setEnabled(False)
        self.toolbar.show();self.update()
    def stop(self):
        self.toolbar.hide();self.overlay.hide();self.overlay.nodes=set();self.overlay.edges=set()
        for action,enabled in self._action_states:action.setEnabled(enabled)
    def update(self):
        editor=self.editor
        self.counts.setText(f'  {len(editor.route_profile_selected_nodes)} nodes · {len(editor.route_profile_selected_edges)} directed edges  ')
        self.overlay.setGeometry(editor.canvas.viewport().rect())
        self.overlay.setVisible(bool(self.overlay.nodes or self.overlay.edges))
        self.overlay.raise_();self.overlay.update()
    def toggle_edge(self,key):
        editor=self.editor
        edges=[e for e in editor.store.data.get('corridors',{}).get('edges',[])
               if editor._physical_edge_key(e['from'],e['to'])==key]
        pairs=edge_pairs(edges)
        if not pairs or not set(key)<=editor.route_profile_allowed_point_names:return
        if any(pair in editor.route_profile_selected_edges for pair in pairs):
            editor.route_profile_selected_edges.difference_update(pairs)
        else:
            editor.route_profile_selected_edges.update(pairs);editor.route_profile_selected_nodes.update(key)
    def choose(self,choices,x,y):
        if len(choices)==1:return choices[0][1]
        menu=QMenu(self.editor);options={}
        for text,key in choices:options[menu.addAction(text)]=key
        point=self.editor.canvas.mapToGlobal(self.editor.canvas.mapFromScene(self.editor.world_to_scene(x,y)))
        action=menu.exec(point);return options.get(action)
    def pick_node(self,x,y,floor):
        from visualiser.model_layers import definitions,layer_name
        layers=definitions(self.editor.store.data)
        candidates=[(math.hypot(p['x']-x,p['y']-y),name) for name,p in self.editor.store.points_for_floor(floor).items()
                    if name in self.editor.route_profile_allowed_point_names and layers[layer_name(p)]['visible']]
        distance=min((d for d,_ in candidates),default=2)
        if distance>1:return None
        choices=[(name,name) for d,name in sorted(candidates) if d<=distance+1e-6]
        return self.choose(choices,x,y)
    def pick_edge(self,x,y,floor):
        editor=self.editor;points=editor.store.points_for_floor(floor);candidates={}
        from visualiser.model_layers import definitions,layer_name
        layers=definitions(editor.store.data)
        for edge in editor.store.data.get('corridors',{}).get('edges',[]):
            a,b=edge['from'],edge['to']
            if a not in points or b not in points or not layers[layer_name(edge)]['visible']:continue
            pa,pb=points[a],points[b];dx,dy=pb['x']-pa['x'],pb['y']-pa['y'];length=dx*dx+dy*dy
            t=max(0,min(1,((x-pa['x'])*dx+(y-pa['y'])*dy)/length)) if length else 0
            distance=math.hypot(x-pa['x']-t*dx,y-pa['y']-t*dy)
            if distance<=.45:
                key=editor._physical_edge_key(a,b)
                candidates[key]=(distance,f'{a} {"↔" if edge.get("bidirectional",True) else "→"} {b}')
        nearest=min((d for d,_ in candidates.values()),default=1)
        choices=[(text,key) for key,(distance,text) in sorted(candidates.items()) if distance<=nearest+.03]
        return self.choose(choices,x,y) if choices else None
    def click(self,x,y,floor):
        editor=self.editor
        if self.mode.currentText()=='Edges':
            key=self.pick_edge(x,y,floor)
            if key:self.toggle_edge(key)
        else:
            name=self.pick_node(x,y,floor)
            if name in editor.route_profile_selected_nodes:
                editor.route_profile_selected_nodes.remove(name)
                editor.route_profile_selected_edges={pair for pair in editor.route_profile_selected_edges if name not in pair}
            elif name:editor.route_profile_selected_nodes.add(name)
        self.update();editor.refresh_canvas()
    def rectangle(self,rect,floor,keep):
        editor=self.editor;points=editor.store.points_for_floor(floor)
        if not keep:
            # A floor-by-floor selection must retain completed earlier floors.
            local=set(points)
            editor.route_profile_selected_nodes.difference_update(local)
            editor.route_profile_selected_edges={p for p in editor.route_profile_selected_edges if not set(p)&local}
        inside={name for name,p in points.items() if name in editor.route_profile_allowed_point_names
                and rect.contains(editor.world_to_scene(p['x'],p['y']))}
        editor.route_profile_selected_nodes.update(inside)
        if self.mode.currentText()=='Edges':
            editor.route_profile_selected_edges.update(edge_pairs(editor.store.data.get('corridors',{}).get('edges',[]),inside))
        self.update()


def tutorial_route_target(bubble):
    """Guide real canvas clicks; never select permissions on the user's behalf."""
    from tutorial_controls import reveal
    from amr_tutorial_values import route_nodes,route_edges
    editor=bubble.editor;chapter,index,_=bubble.current()
    if chapter!=5 or not editor.route_profile_selection_active or not editor.route_profile_select_edges:return None
    dialog=editor.route_profile_return_window;flow=dialog.current_profile
    if flow not in ('clean','dirty'):return None
    lifts=['L1','L2'] if bubble.course.session.state['policy']=='shared' else ['L1' if flow=='clean' else 'L2']
    roles=bubble.course.session.roles(editor.store.data)
    nodes=route_nodes(editor.store.data,flow,lifts,roles);edges=route_edges(editor.store.data,flow,lifts,roles)
    guide=editor.route_permission_selection;guide.overlay.nodes=nodes;guide.overlay.edges=edges;guide.update()
    selected=editor.route_profile_selected_nodes;chosen=editor.route_profile_selected_edges
    # Removing unintended permissions is part of the teaching flow as well.
    wrong=sorted(selected-nodes);missing=sorted(nodes-selected)
    pairs=sorted(chosen-edges) or sorted(edges-chosen)
    points=editor.store.all_points()
    if wrong or missing:
        name=(wrong or missing)[0];p=points.get(name)
        mode=0;tip=f'{"Remove" if wrong else "Select"} node {name}'
    elif pairs:
        a,b=pairs[0];pa,pb=points.get(a),points.get(b)
        p=dict(floor=pa['floor'],x=(pa['x']+pb['x'])/2,y=(pa['y']+pb['y'])/2) if pa and pb else None
        mode=1;tip=f'{"Remove" if chosen-edges else "Select"} edge {a} → {b}'
    else:
        target=reveal(guide.finish)
        if target:target[0].setProperty('amrTutorialHint',f'{flow}: nodes and edges match. Finish selection, then Apply Changes.')
        return target
    if p and int(p['floor'])!=editor.floor_spin.value():
        target=reveal(guide.floor)
        if target:target[0].setProperty('amrTutorialHint',f'{flow}: choose floor {p["floor"]} — {tip}.')
        return target
    if guide.mode.currentIndex()!=mode:
        target=reveal(guide.mode)
        if target:target[0].setProperty('amrTutorialHint',f'{flow}: Select > {guide.mode.itemText(mode)} — {tip}.')
        return target
    if p:
        pixel=editor.canvas.mapFromScene(editor.world_to_scene(p['x'],p['y']))
        target=editor.canvas.viewport();target.setProperty('amrTutorialHint',f'{flow} · Floor {p["floor"]} · {tip}. Click to toggle; selected permissions are blue.')
        return target,QRect(pixel-QPoint(14,14),QSize(28,28))
    return reveal(guide.cancel)
