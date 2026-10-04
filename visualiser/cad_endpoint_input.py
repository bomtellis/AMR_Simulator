"""Inline preview and confirmation of a corridor endpoint trim/extension."""
from PySide6.QtWidgets import QWidget,QGridLayout,QLabel,QComboBox,QPushButton
from visualiser.corridor_endpoint import free_endpoints,trim_extend
from visualiser.selection_preview import paint_selection_preview


class CadEndpointInput(QWidget):
    def __init__(self,editor):
        super().__init__(editor)
        self.editor = editor
        self.mouse_stage = None
        self.preview_store = None
        self.source = None
        self.loading = False
        layout = QGridLayout(self)
        self.endpoint = QComboBox(self)
        self.endpoint.setAccessibleName('Free corridor endpoint to trim or extend')
        self.boundary = QComboBox(self)
        self.boundary.setAccessibleName('Boundary corridor')
        self.pick = QPushButton('Pick boundary',self)
        self.apply_button = QPushButton('Apply',self)
        cancel = QPushButton('Cancel',self)
        for column,widget in enumerate((QLabel('Endpoint'),self.endpoint,QLabel('Boundary'),self.boundary,self.pick,self.apply_button,cancel)):
            layout.addWidget(widget,0,column)
        layout.setColumnStretch(3,1)
        self.preview = QLabel(self)
        self.preview.setWordWrap(True)
        layout.addWidget(self.preview,1,0,1,7)
        self.endpoint.currentIndexChanged.connect(self.refresh_preview)
        self.boundary.currentIndexChanged.connect(self.refresh_preview)
        self.pick.clicked.connect(self.begin_pick)
        self.apply_button.clicked.connect(self.apply)
        cancel.clicked.connect(self.hide)
        self.hide()

    def start(self,source):
        self.hide()
        self.source = source
        self.loading = True
        self.endpoint.clear()
        self.endpoint.addItems(free_endpoints(self.editor.store,source))
        self.boundary.clear()
        self.boundary.addItem('Choose or pick a corridor',None)
        edges = self.editor.store.edges_for_floor(self.editor.floor_spin.value())
        for key in sorted({tuple(sorted((e['from'],e['to']))) for e in edges}-{source}):
            self.boundary.addItem(' ↔ '.join(key),key)
        self.loading = False
        self.show()
        self.refresh_preview()

    def refresh_preview(self,*_):
        if self.loading:
            return
        self.preview_store = None
        self.apply_button.setEnabled(False)
        try:
            if not self.endpoint.currentText():
                raise ValueError('The selected corridor has no free corridor-node endpoint.')
            boundary = self.boundary.currentData()
            if boundary is None:
                raise ValueError('Choose the boundary corridor. Only its interior can be joined.')
            self.preview_store,self.result = trim_extend(self.editor.store,self.source,self.endpoint.currentText(),boundary)
            r = self.result
            self.preview.setText(f'{r["operation"]} {r["endpoint"]}: {r["old_length"]:g} → {r["new_length"]:g} m. '
                'Connects and splits the boundary. Source distance overrides scale proportionally; other crossings are unchanged. One undo step.')
            self.apply_button.setEnabled(not self.editor.project_editing_locked())
        except ValueError as error:
            self.preview.setText(str(error))
        self.editor.canvas.viewport().update()

    def begin_pick(self):
        self.mouse_stage = 'boundary'
        self.editor.set_status('Click a boundary corridor, then review the preview and Apply. Escape cancels.')
        self.editor.canvas.setFocus()

    def mouse_click(self,sx,sy):
        x,y = self.editor.scene_to_world(sx,sy)
        key = self.editor.find_nearest_edge_key(x,y,self.editor.floor_spin.value())
        index = next((i for i in range(1,self.boundary.count())
                      if tuple(self.boundary.itemData(i)) == key),-1) if key is not None else -1
        if index < 1:
            self.preview.setText('Pick a different visible boundary corridor.')
            return
        self.mouse_stage = None
        self.boundary.setCurrentIndex(index)
        self.refresh_preview()

    def apply(self):
        if self.editor.trim_extend_selected_corridor(self.source,self.endpoint.currentText(),self.boundary.currentData()):
            self.hide()

    def hide(self):
        self.mouse_stage = None
        self.preview_store = None
        super().hide()
        self.editor.canvas.viewport().update()

    def hideEvent(self,event):
        self.mouse_stage = None
        self.preview_store = None
        super().hideEvent(event)

    def paint_preview(self,painter):
        if not self.isHidden() and self.preview_store is not None:
            r = self.result
            paint_selection_preview(self.editor,painter,self.preview_store,{r['endpoint']},(r['x'],r['y']),r['operation']+' preview')
