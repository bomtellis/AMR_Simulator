"""Numerical layout copying with new-name and geometry previews."""
from PySide6.QtWidgets import QCheckBox
from visualiser.cad_move_input import CadMoveInput
from visualiser.selection_copy import copy_selection
from visualiser.selection_preview import paint_selection_preview


class CadCopyInput(CadMoveInput):
    def __init__(self, editor):
        self.preview_store = None
        super().__init__(editor)
        self.layout().itemAtPosition(0,0).widget().setText('Copy by (m)')
        self.offset.setAccessibleName('Copy selection displacement in metres')
        self.apply_button.setText('Create copy')
        self.occupied = QCheckBox('Copy occupied bays', self)
        self.occupied.setToolTip('Off creates empty bays with the same templates. On copies each bay occupied flag. Fleet and demand rules remain separate.')
        self.layout().addWidget(self.occupied, 2, 0, 1, 4)
        self.occupied.toggled.connect(self.refresh_preview)

    def refresh_preview(self, *_):
        self.preview_store = None
        self.apply_button.setEnabled(False)
        try:
            dx, dy = self.displacement()
            points = self.editor.selection_move_points()
            staged, mapping, edge_count = copy_selection(self.editor.store, points, dx, dy,
                                                         occupied=self.occupied.isChecked())
            self.preview_store = staged
            self.preview_names = set(mapping.values())
            first = staged.all_points()[mapping[sorted(mapping)[0]]]
            self.preview_anchor = (first['x'], first['y'])
            names = ', '.join(list(mapping.values())[:3]) + (', …' if len(mapping) > 3 else '')
            self.preview.setToolTip('\n'.join(f'{old} → {new}' for old,new in mapping.items()))
            self.preview.setText(f'{len(mapping)} points, {edge_count} corridors: {names}. Demand rules unchanged; one undo step.')
            self.apply_button.setEnabled(not self.editor.project_editing_locked())
        except ValueError as exc:
            self.preview.setText(str(exc))
        self.editor.canvas.viewport().update()

    def apply(self):
        try:
            dx, dy = self.displacement()
            if self.editor.copy_selected_by(dx, dy, occupied=self.occupied.isChecked()):
                self.offset.clear()
                self.hide()
        except ValueError as exc:
            self.preview.setText(str(exc))

    def hideEvent(self, event):
        super().hideEvent(event)
        self.preview_store = None
        self.editor.canvas.viewport().update()

    def paint_preview(self, painter):
        if not self.isHidden() and self.preview_store is not None:
            paint_selection_preview(self.editor, painter, self.preview_store,
                                    self.preview_names, self.preview_anchor, 'Copy preview')
