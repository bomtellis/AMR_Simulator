"""
AMR Simulator app
"""

import json
from copy import deepcopy
import math
import sys
import tempfile
import hashlib
from amr_inventory_inputs import inventory_space_is_amr
from pathlib import Path

import os
from concurrent.futures import ProcessPoolExecutor, as_completed

from PySide6.QtCore import (
    QObject,
    QPoint,
    QPointF,
    Qt,
    Signal,
    QRect,
    QThread,
    Slot,
    QRectF,
    QTimer,
    QStandardPaths,
)
from PySide6.QtGui import QAction, QColor, QBrush, QPainter, QPen, QFont, QFontMetrics, QPolygonF, QKeySequence
from edit_history import EditHistory, undoable
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDockWidget,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGraphicsItem,
    QGraphicsPolygonItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QDoubleSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QInputDialog,
    QLayout,
    QMenu,
)

from dxf_scene import DXFScene
from dxf_export import (
    DXF_UNIT_SPECS,
    all_floor_output_paths,
    export_all_floors_to_dxf,
    export_floor_to_dxf,
)
from pdf_underlay import (
    MovablePdfUnderlayItem,
    PdfUnderlayDialog,
    normalise_pdf_underlay,
    render_pdf_page,
    underlay_world_bounds,
)
from dialogs import (
    EdgeConnectionsDialog,
    LiftEditorDialog,
    LiftListDialog,
    PointEditorDialog,
    TableListEditor,
    DepartmentEditorDialog,
    WasteStreamEditorDialog,
    WasteStreamListDialog,
    MassCollectionListDialog,
    DepartmentListDialog,
    AMRListDialog,
    AMREditorDialog,
    LocationSpacesManagerDialog,
    InventorySpacesDialog,
    TaskGenerationSettingsDialog,
    PayloadListDialog,
    SimulationSettingsDialog,
    PeopleMovementListDialog,
    ScenarioTestingDialog,
    CorridorSettingsDialog,
    collect_department_dropoff_zone_names,
)
from advanced_dialogs import (
    MultiSelectPicker,
    RouteProfilesEditorV2,
    TaskEditorWindow,
    TaskPlannerDialog,
)
from models import JsonStore
from ui_theme import install_application_theme, polish_dialog as _polish_dialog


def _load_dxf_floor_process(args):
    floor, path = args
    try:
        payload = DXFScene.load_content(path)
        return {
            "ok": True,
            "floor": int(floor),
            "path": str(path),
            "entities": payload["entities"],
            "bounds": payload["bounds"],
            "error": "",
        }
    except Exception as exc:
        return {
            "ok": False,
            "floor": int(floor),
            "path": str(path),
            "entities": None,
            "bounds": None,
            "error": str(exc),
        }


class DXFLoadWorker(QObject):
    loaded = Signal(int, str, object, object)
    failed = Signal(int, str, str)
    finished_batch = Signal()

    @Slot(object)
    def load_floors(self, jobs):
        jobs = list(jobs or [])
        if not jobs:
            self.finished_batch.emit()
            return

        worker_count = min(len(jobs), max(1, (os.cpu_count() or 2) - 1))

        try:
            with ProcessPoolExecutor(max_workers=worker_count) as pool:
                futures = [pool.submit(_load_dxf_floor_process, job) for job in jobs]

                for future in as_completed(futures):
                    result = future.result()
                    floor = int(result["floor"])
                    path = str(result["path"])

                    if result.get("ok"):
                        self.loaded.emit(
                            floor,
                            path,
                            result["entities"],
                            result["bounds"],
                        )
                    else:
                        self.failed.emit(
                            floor,
                            path,
                            str(result.get("error", "Unknown DXF load error")),
                        )
        finally:
            self.finished_batch.emit()


class DXFLoadingDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._completed = False
        self.setWindowTitle("Loading DXFs")
        self.setWindowModality(Qt.ApplicationModal)
        self.setWindowFlag(Qt.WindowCloseButtonHint, False)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        self.message_label = QLabel("Loading DXF files...")
        self.message_label.setWordWrap(True)
        layout.addWidget(self.message_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.detail_label = QLabel("0 / 0")
        layout.addWidget(self.detail_label)
        _polish_dialog(self)

    def update_progress(self, current, total, message, failed_count=0):
        total = max(1, int(total))
        current = max(0, min(int(current), total))
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(current)
        self.message_label.setText(message)
        detail = f"{current} / {total} loaded"
        if failed_count:
            detail += f" ({failed_count} failed)"
        self.detail_label.setText(detail)

    def mark_complete(self):
        self._completed = True
        self.accept()

    def reject(self):
        if self._completed:
            super().reject()

    def closeEvent(self, event):
        if self._completed:
            super().closeEvent(event)
        else:
            event.ignore()


class EditorGraphicsView(QGraphicsView):
    leftClicked = Signal(object, float, float)
    leftDoubleClicked = Signal(object, float, float)
    leftReleased = Signal(object)
    rightClicked = Signal(object, float, float)
    middleClicked = Signal(object)
    middleDragged = Signal(object)
    middleReleased = Signal(object)
    mouseWheelScrolled = Signal(object)
    mouseDragged = Signal(object, float, float)
    pointerMoved = Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHint(QPainter.Antialiasing, False)
        self.setBackgroundBrush(QBrush(QColor("#fbfdff")))
        self._overlay_provider = None
        self.setDragMode(QGraphicsView.NoDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self._middle_panning = False
        self._last_middle_pos = None
        self.setMouseTracking(True)

    def drawBackground(self, painter, rect):
        super().drawBackground(painter, rect)
        if not getattr(self, '_show_map_grid', False):
            return
        from cad_map_style import adaptive_grid
        scale = math.hypot(self.transform().m11(), self.transform().m12())
        _, lines = adaptive_grid((rect.left(),rect.top(),rect.right(),rect.bottom()), scale)
        style = self._map_style
        painter.save()
        for x0,y0,x1,y1,major in lines:
            pen = QPen(QColor(style['major' if major else 'minor']), 1)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.drawLine(QPointF(x0,y0),QPointF(x1,y1))
        painter.restore()

    def mousePressEvent(self, event):
        editor = self.window()
        if event.button() != Qt.MiddleButton and getattr(editor, 'project_editing_locked', lambda: False)():
            editor._project_editing_allowed()
            event.accept()
            return
        scene_pos = self.mapToScene(event.position().toPoint())
        if event.button() == Qt.LeftButton:
            self.leftClicked.emit(event, scene_pos.x(), scene_pos.y())
        elif event.button() == Qt.RightButton:
            self.rightClicked.emit(event, scene_pos.x(), scene_pos.y())
        elif event.button() == Qt.MiddleButton:
            self._middle_panning = True
            self._last_middle_pos = event.position().toPoint()
            self.middleClicked.emit(event)
        if event.button() == Qt.LeftButton and self._cad_select_mode():
            event.accept()
            return
        super().mousePressEvent(event)

    def _cad_select_mode(self):
        editor = self.window()
        return (hasattr(editor, '_current_edit_mode') and editor._current_edit_mode() == 'select_move'
                and not editor.route_profile_selection_active and not editor.department_location_placement_active)

    def set_cad_selection_overlay(self, start=None, end=None):
        self._cad_selection_overlay = None if start is None else (QPointF(start), QPointF(end))
        self.viewport().update()

    def mouseDoubleClickEvent(self, event):
        editor = self.window()
        if getattr(editor, 'project_editing_locked', lambda: False)():
            event.accept()
            return
        scene_pos = self.mapToScene(event.position().toPoint())
        if event.button() == Qt.LeftButton:
            self.leftDoubleClicked.emit(event, scene_pos.x(), scene_pos.y())
        super().mouseDoubleClickEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.leftReleased.emit(event)
        elif event.button() == Qt.MiddleButton:
            self._middle_panning = False
            self._last_middle_pos = None
            self.middleReleased.emit(event)
        if event.button() == Qt.LeftButton and self._cad_select_mode():
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        scene_pos = self.mapToScene(event.position().toPoint())
        self.pointerMoved.emit(scene_pos.x(), scene_pos.y())
        if self._middle_panning and self._last_middle_pos is not None:
            self.middleDragged.emit(event)
        if getattr(self.window(), 'project_editing_locked', lambda: False)():
            event.accept()
            return
        if event.buttons() & Qt.LeftButton:
            self.mouseDragged.emit(event, scene_pos.x(), scene_pos.y())
            if self._cad_select_mode():
                event.accept()
                return
        # Graph tools do their own picking. Native hover dispatch asks Qt to
        # hit-test every detailed DXF path beneath the pointer on every move.
        # Only PDF alignment uses native item mouse interaction.
        editor = self.window()
        if hasattr(editor, '_current_edit_mode') and editor._current_edit_mode() != 'pdf_underlay_align':
            event.accept()
            return
        super().mouseMoveEvent(event)

    def wheelEvent(self, event):
        self.mouseWheelScrolled.emit(event)
        event.accept()

    def set_overlay_provider(self, overlay_provider):
        self._overlay_provider = overlay_provider
        self.viewport().update()

    def drawForeground(self, painter, rect):
        super().drawForeground(painter, rect)
        if self._overlay_provider:
            painter.save()
            painter.resetTransform()
            self._overlay_provider(painter, self.viewport().rect())
            painter.restore()
        overlay = getattr(self, '_cad_selection_overlay', None)
        if overlay is not None:
            from cad_selection import paint_rectangle
            painter.save()
            painter.resetTransform()
            paint_rectangle(painter, *overlay)
            painter.restore()


class AMRGraphEditor(QMainWindow):
    _request_dxf_batch_load = Signal(object)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("AMR Engineering Project")
        self.setProperty('amrProjectWorkspace', True)
        self.resize(1500, 920)
        from appearance import controller
        self.appearance = controller()
        from route_display import styles_for
        self.route_styles = styles_for(self.appearance)
        self._route_access_cache = None
        self.route_preview_error = ''

        self.store = JsonStore()
        self.current_json_path = None
        self.project = None
        self._project_cache = None
        self._drawings_enabled = True
        self.current_dxf_path = None
        self.loaded_dxf_floor = None
        self.dxf_scene = DXFScene()
        self._dxf_cache = {}
        self._dxf_loading_floors = set()
        self._pending_fit_after_load = False
        self._last_requested_floor = None
        self._loading_dialog = None
        self._loading_batch_floors = set()
        self._loading_batch_failed = set()
        self._loading_batch_active = False
        self._pdf_pixmap_cache = {}
        self._pdf_render_errors = {}

        self.route_profile_selection_active = False
        self.route_profile_allowed_point_names = set()
        self.route_profile_selected_nodes = set()
        self.route_profile_selection_callback = None
        self.route_profile_return_window = None
        self.route_profile_selection_rect_start = None
        self.route_profile_selection_rect_item = None

        self.department_location_placement_active = False
        self.department_location_placement_name = None
        self.department_location_placement_category_key = None
        self.department_location_placement_callback = None
        self.department_location_placement_return_dialog = None

        self._dxf_thread = QThread(self)
        self._dxf_worker = DXFLoadWorker()
        self._dxf_worker.moveToThread(self._dxf_thread)
        self._dxf_worker.loaded.connect(self._on_dxf_loaded)
        self._dxf_worker.failed.connect(self._on_dxf_failed)
        self._request_dxf_batch_load.connect(self._dxf_worker.load_floors)
        self._dxf_worker.finished_batch.connect(self._update_loading_dialog)
        self._dxf_thread.start()

        self.scale = 5.0
        self.offset_x = 250
        self.offset_y = 250
        self.last_pan = None
        self.selected_for_edge = None
        self.corridor_draw_start = None
        self.corridor_draw_preview = None
        self.selected_point_name = None
        self.selected_point_names = set()
        self.selected_edge_keys = set()
        self.topology_selection_rect_start = None
        self.topology_selection_rect_item = None
        self.dragging_point_name = None
        self.drag_mode_active = False
        self.edge_delete_start = None
        self.bounding_box_location_name = None
        self.bounding_box_points = []
        self.dragging_bounding_box_point_index = None

        self._item_lookup = {}
        self._point_item_lookup = {}

        self._build_ui()
        self.refresh_canvas()
        self._edit_depth = 0
        self._history_restoring = False
        self.edit_history = EditHistory(self.store.data)
        self._update_history_actions()
        self._saved_state = self._configuration_state()
        self._source_disk_hash = None
        self._recovery_store = None
        self._recovery_last_state = None
        self._recovery_status = "No recovery copy yet"
        self._recovered_work = False
        self._dirty_timer = QTimer(self)
        self._dirty_timer.timeout.connect(self._update_unsaved_indicator)
        self._dirty_timer.start(2000)
        self._recovery_timer = QTimer(self)
        self._recovery_timer.timeout.connect(self.capture_recovery)
        self._recovery_timer.start(30000)
        self._drag_refresh_timer = QTimer(self)
        self._drag_refresh_timer.setSingleShot(True)
        self._drag_refresh_timer.setInterval(16)
        self._drag_refresh_timer.timeout.connect(lambda: self.refresh_canvas(update_panels=False))
        QTimer.singleShot(0, self._announce_recovery)
        self.appearance.changed.connect(self._appearance_changed)
        self.route_styles.changed.connect(self.refresh_canvas)

    def _appearance_changed(self, _value):
        self.refresh_canvas()

    def show_appearance(self):
        if not hasattr(self, 'appearance_panel'):
            from appearance_panel import AppearancePanel
            self.appearance_panel = AppearancePanel(self.appearance, self)
        self.workspace.show_page('appearance', self.appearance_panel)

    def route_access_model(self):
        from route_display import access_preview
        data = self.store.data
        key = json.dumps({name: data.get(name) for name in ('locations', 'lifts', 'corridors', 'route_profiles')}, sort_keys=True)
        if self._route_access_cache is None or key != self._route_access_cache[0]:
            self._route_access_cache = (key, access_preview(data))
        return self._route_access_cache[1]

    def show_route_identification(self):
        if not hasattr(self, 'route_display_panel'):
            from route_display_panel import RouteDisplayPanel
            self.route_display_panel = RouteDisplayPanel(self)
            self.route_display_scroll = QScrollArea(self)
            self.route_display_scroll.setWidgetResizable(True)
            self.route_display_scroll.setWidget(self.route_display_panel)
        else:
            self.route_display_panel.refresh()
        self.workspace.show_page('route_display', self.route_display_scroll)

    def _configuration_state(self):
        # Comparison also works for malformed numeric input opened for repair.
        # Persistent saves and recovery still reject non-finite JSON values.
        return json.dumps(self.store.data, ensure_ascii=False)

    def project_editing_locked(self):
        panel = getattr(self, 'project_runs_panel', None)
        return panel is not None and panel.running()

    def _project_editing_allowed(self):
        if self.project_editing_locked():
            self.set_status('Project editing is locked while simulation runs. Stop the run or wait for it to finish.')
            return False
        return True

    def sync_project_editing_lock(self):
        locked = self.project_editing_locked()
        if locked:
            self._cancel_cad_transients()
            self._clear_corridor_drawing()
            self.cad_move_input.hide()
        self.run_lock_label.setVisible(locked)
        self.workspace._sync_panels()
        self._update_history_actions()

    def _history_busy(self):
        return (self.project_editing_locked() or self._edit_depth > 0 or QApplication.activeModalWidget() is not None or
                QApplication.mouseButtons() != Qt.NoButton or self.drag_mode_active or
                bool(self.dragging_point_name) or bool(self.bounding_box_location_name) or bool(getattr(self, '_rectangle_draft', None)) or
                self.department_location_placement_active or self.route_profile_selection_active or
                any(window.isVisible() and not window.property('amrEmbeddedPlayback') for window in self.findChildren(QMainWindow)))

    def _update_history_actions(self):
        if not hasattr(self, "edit_history"):
            return
        busy = self._history_busy()
        for action, prefix, label in ((self.undo_action, "Undo", self.edit_history.undo_label),
                                      (self.redo_action, "Redo", self.edit_history.redo_label)):
            action.setText(f"{prefix}: {label}" if label else prefix)
            action.setEnabled(bool(label) and not busy)
            action.setToolTip("Finish or close the active editor before undo/redo." if busy else
                "Up to 100 changes / 32 MiB, in this editor session. Saved revisions remain separate." +
                (" Older steps have expired." if self.edit_history.trimmed else ""))

    def _commit_history(self, label="Configuration changes"):
        if not hasattr(self, "edit_history") or self._history_restoring:
            return
        if not self._history_busy():
            self.edit_history.record(self.store.data, label)
        self._update_history_actions()

    def _reset_edit_history(self):
        self._clear_corridor_drawing()
        self.edit_history.reset(self.store.data)
        self._update_history_actions()

    def _apply_history(self, redo=False):
        if not self._project_editing_allowed():
            return False
        if self._history_busy():
            self.set_status("Finish or close the active editor before undo/redo.")
            return False
        self._commit_history()
        label = self.edit_history.redo_label if redo else self.edit_history.undo_label
        config = self.edit_history.redo() if redo else self.edit_history.undo()
        if config is None:
            return False
        self._history_restoring = True
        try:
            dxf_changed = self.store.data.get('floor_dxf_files', []) != config.get('floor_dxf_files', [])
            self.store.data = config
            self.selected_point_name = None
            self.selected_point_names.clear()
            self.selected_edge_keys.clear()
            self.selected_for_edge = None
            self._clear_corridor_drawing()
            if dxf_changed:
                self._clear_dxf_cache()
            # PDF rasters are keyed by file and page; placement edits and
            # unrelated model changes can reuse them unchanged.
            self.refresh_canvas()
            if dxf_changed:
                self._queue_all_floor_dxf_loads(active_floor=self.floor_spin.value(), force_reload=False)
            self._update_unsaved_indicator()
            for name in ("checks_panel", "demand_panel"):
                panel = getattr(self, name, None)
                if panel is not None:
                    panel.check_staleness()
            self.set_status(f"{'Redid' if redo else 'Undid'}: {label}")
        finally:
            self._history_restoring = False
            self._update_history_actions()
        return True

    def undo_edit(self):
        return self._apply_history()

    def redo_edit(self):
        return self._apply_history(redo=True)

    def has_unsaved_changes(self):
        if hasattr(self, 'properties_panel') and self.properties_panel.pending:
            return True
        try:
            return self._configuration_state() != self._saved_state
        except (TypeError, ValueError):
            return True

    def _get_recovery_store(self):
        if self._recovery_store is None:
            root = str(Path(__file__).resolve().parents[1])
            if root not in sys.path:
                sys.path.insert(0, root)
            from amr_recovery import RecoveryStore
            folder = Path(QStandardPaths.writableLocation(QStandardPaths.GenericDataLocation)) / "AMR Simulator" / "recovery"
            self._recovery_store = RecoveryStore(folder)
        return self._recovery_store

    def _announce_recovery(self):
        try:
            count = len(self._get_recovery_store().list_snapshots())
            if count:
                self.set_status(f"{count} recovery copy/copies available — Home → Recover unsaved work")
        except Exception as exc:
            self.set_status(f"Recovery folder unavailable: {exc}")

    def _update_unsaved_indicator(self):
        self._commit_history()
        dirty = self.has_unsaved_changes()
        project_name = Path(self.current_json_path).name if self.current_json_path else 'New project'
        self.setWindowTitle(f"AMR Engineering — {project_name}" + (" — Unsaved changes" if dirty else ""))
        self.file_label.setText(project_name + (" • Unsaved changes" if dirty else ""))
        self.file_label.setToolTip((self.current_json_path or 'Not saved') + '\n' + self._recovery_status)
        if hasattr(self, 'workspace'):
            self.workspace.refresh(dirty)

    def _discard_own_recovery(self):
        if self._recovery_store is not None:
            try:
                self._recovery_store.discard()
            except OSError as exc:
                self.set_status(f"Saved work is safe, but an old recovery copy could not be removed: {exc}")
        self._recovery_last_state = None

    def _mark_saved(self):
        self._saved_state = self._configuration_state()
        if self.current_json_path:
            self._source_disk_hash = hashlib.sha256(Path(self.current_json_path).read_bytes()).hexdigest()
        else:
            self._source_disk_hash = None
        self._discard_own_recovery()
        self._recovery_status = "No unsaved work awaiting recovery"
        self._update_unsaved_indicator()
        if hasattr(self, 'project_runs_panel'):
            self.project_runs_panel.refresh_runs()

    def capture_recovery(self):
        # Avoid capturing a half-finished drag or modal editor operation.
        if QApplication.activeModalWidget() is not None or self.dragging_point_name or self.drag_mode_active:
            return False
        if not self.has_unsaved_changes():
            self._discard_own_recovery()
            return False
        try:
            recovery_config = self.properties_panel.recovery_config() if hasattr(self, 'properties_panel') else self.store.data
            state = json.dumps(recovery_config, ensure_ascii=False)
            if state == self._recovery_last_state:
                return True
            revision = self.project.revisions[-1]["id"] if self.project else None
            body = self._get_recovery_store().capture(recovery_config, source_path=self.current_json_path,
                source_hash=self._source_disk_hash, revision_id=revision)
            self._recovery_last_state = state
            self._recovery_status = f"Recovery copy: {body['captured_utc']}" + (
                f"; {len(body['warnings'])} drawing(s) could not be copied" if body['warnings'] else "")
            if hasattr(self, 'properties_panel') and self.properties_panel.pending:
                self._recovery_status += '; includes unapplied property values'
            if body['warnings']:
                self.set_status(self._recovery_status)
            self._update_unsaved_indicator()
            return True
        except Exception as exc:
            self._recovery_status = f"Recovery failed; save your work manually: {exc}"
            self.set_status(self._recovery_status)
            self.file_label.setToolTip(self._recovery_status)
            return False

    @undoable('Edit object properties')
    def apply_layout_properties(self, updated):
        self.store.data = updated
        self.refresh_canvas()
        self.set_status('Object properties applied. Undo restores the previous values.')

    def _finish_property_draft(self):
        return not hasattr(self, 'properties_panel') or self.properties_panel.apply()

    def _confirm_unsaved_changes(self):
        if self.route_profile_selection_active or self.department_location_placement_active:
            QMessageBox.information(self, 'Finish drawing selection first',
                'Finish or cancel the route-profile selection or department placement before changing projects or closing. '
                'Use the canvas right-click controls to return to its editor.')
            return False
        if not self._finish_property_draft():
            return False
        if hasattr(self, 'report_panel') and self.report_panel.running():
            QMessageBox.information(self, 'Report running', 'Stop report generation or wait for it to finish before changing projects or closing the application.')
            return False
        if hasattr(self, 'project_runs_panel') and self.project_runs_panel.running():
            QMessageBox.information(self, "Simulation running", "Stop the run or wait for it to finish before opening another project or closing the editor.")
            return False
        if any(window.isVisible() and not window.property('amrEmbeddedPlayback') for window in self.findChildren(QMainWindow)):
            QMessageBox.information(self, "Finish editing first",
                "Close the task editor or planner before opening another project or closing the main editor. This keeps its pending edits with the correct project.")
            return False
        if not self.has_unsaved_changes():
            return True
        choice = QMessageBox.warning(self, "Unsaved changes",
            "Save your changes before continuing? Discard removes this editor's recovery copy.\n\n" + self._recovery_status,
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Cancel)
        if choice == QMessageBox.Save:
            return bool(self.save_json())
        return choice == QMessageBox.Discard

    def recover_unsaved_work(self):
        recovery = self._get_recovery_store()
        rows = recovery.list_snapshots()
        if not rows:
            QMessageBox.information(self, "Recovery", "No recovery copies are available.")
            return
        labels = [f"{i + 1}. {row['captured_utc'][:19]} UTC | {row['source']}" + (" — unreadable" if row['error'] else "")
                  for i, row in enumerate(rows)]
        selected, accepted = QInputDialog.getItem(self, "Recover unsaved work",
            "Choose a copy. Recovery opens as unsaved work; save it to a new file.", labels, 0, False)
        if not accepted:
            return
        self.load_recovery_snapshot(rows[labels.index(selected)]["path"])

    def load_recovery_snapshot(self, path):
        cache = tempfile.TemporaryDirectory(prefix="amr-recovered-")
        try:
            config, body = self._get_recovery_store().recover(path, cache.name)
            # Stage valid inputs before asking to replace the current workspace.
            staged = Path(cache.name) / "recovered.json"
            staged.write_text(json.dumps(config, ensure_ascii=False, allow_nan=False), encoding="utf-8")
            if not self.load_json_file(str(staged), load_drawings=False):
                cache.cleanup()
                return False
            if self._project_cache is None:
                self._project_cache = []
            self._project_cache.append(cache)
            self.current_json_path = None
            self._saved_state = None
            self._source_disk_hash = None
            self._recovered_work = True
            self._update_unsaved_indicator()
            self.capture_recovery()
            message = "Recovered unsaved work. Save to a new file; the original remains unchanged. Drawings are available through Load configured drawings."
            source = body.get("source_path")
            if source and body.get("source_hash"):
                try:
                    if hashlib.sha256(Path(source).read_bytes()).hexdigest() != body['source_hash']:
                        message += " The original file has changed since these edits began."
                except OSError:
                    message += " The original file is no longer available."
            if body['warnings']:
                message += "\n\n" + "\n".join(body['warnings'])
            self.set_status(message)
            QMessageBox.information(self, "Recovery opened", message)
            return True
        except Exception as exc:
            cache.cleanup()
            QMessageBox.critical(self, "Recovery failed", str(exc))
            return False

    def _build_ui(self):
        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.scene = QGraphicsScene(self)
        self.canvas = EditorGraphicsView(self)
        self.canvas.setScene(self.scene)
        self.canvas.set_overlay_provider(self.draw_overlay_panels)

        self.canvas.leftClicked.connect(self.on_left_click)
        self.canvas.leftDoubleClicked.connect(self.on_double_click)
        self.canvas.leftReleased.connect(self.on_left_release)
        self.canvas.pointerMoved.connect(self.preview_location_rectangle)
        self.canvas.rightClicked.connect(self.on_right_click)
        self.canvas.middleClicked.connect(self.on_middle_click)
        self.canvas.middleDragged.connect(self.on_middle_drag)
        self.canvas.middleReleased.connect(self.on_middle_release)
        self.canvas.mouseWheelScrolled.connect(self.on_mousewheel)
        self.canvas.mouseDragged.connect(self.on_drag)
        self.canvas.pointerMoved.connect(self.preview_corridor_drawing)

        self.mode_combo = QComboBox()
        self.mode_combo.setMinimumWidth(230)
        edit_modes = [
            ("Select and move", "select_move", "Select, multi-select, drag and edit existing items."),
            ("Draw corridor route", "corridor_draw", "Click successive points to draw connected corridors. Existing points and edges snap automatically. Right-click or Escape finishes."),
            ("Add corridor node", "corridor_node", "Place a graph node used by corridor routes and door openings."),
            ("Add door", "door", "Place a door node or insert a door opening into an existing corridor."),
            ("Add location", "location", "Place a general simulation location."),
            ("Draw location boundary", "location_bbox", "Draw or replace the usable boundary around a location."),
            ("Draw rectangular location boundary", "location_rectangle", "Choose a location, then two opposite corners. Escape cancels."),
            ("Add department location", "department", "Place a location associated with a department workflow."),
            ("Connect corridor", "edge", "Create a corridor edge between graph nodes."),
            ("Add lift", "lift", "Place or edit a lift access point."),
            (
                "Align PDF underlay",
                "pdf_underlay_align",
                "Drag the current floor's PDF underlay to align its lower-left point.",
            ),
            ("Pan view", "pan", "Move around the drawing without selecting assets."),
            ("Delete items", "delete", "Delete the item clicked in the drawing."),
        ]
        for label, value, tooltip in edit_modes:
            self.mode_combo.addItem(label, value)
            self.mode_combo.setItemData(self.mode_combo.count() - 1, tooltip, Qt.ToolTipRole)
        self.mode_combo.setToolTip("Choose what a mouse click does in the topology editor.")
        self.mode_combo.currentIndexChanged.connect(self.on_edit_mode_changed)
        self.floor_spin = QSpinBox()
        self.floor_spin.setRange(0, 99)
        self.floor_spin.valueChanged.connect(self.on_floor_changed)
        self.snap_check = QCheckBox("Grid snap")
        self.snap_check.setChecked(True)
        self.grid_spacing_spin = QDoubleSpinBox()
        self.grid_spacing_spin.setDecimals(3)
        self.grid_spacing_spin.setRange(.001, 1000)
        self.grid_spacing_spin.setValue(1.0)
        self.grid_spacing_spin.setSuffix(' m')
        self.grid_spacing_spin.setAccessibleName('Drawing grid spacing in metres')
        self.grid_spacing_spin.setToolTip('Placement grid spacing; typed coordinates bypass this grid. The display grid adapts to zoom independently.')
        self.object_snap_check = QCheckBox('Object snap')
        self.object_snap_check.setChecked(True)
        self.object_snap_mode = QComboBox()
        self.object_snap_mode.setAccessibleName('Object snap target')
        for title, value in [('Nearest point or edge', 'nearest'), ('Endpoints / graph points', 'endpoints'), ('Corridor midpoints', 'midpoints'), ('Perpendicular from route end', 'perpendicular'), ('Intersections (connect junction)', 'intersections')]:
            self.object_snap_mode.addItem(title, value)
        self.object_snap_mode.setToolTip('Choose nearby targets for corridor, node and door placement. Perpendicular requires a current route endpoint and stays within the target corridor. Exact overlaps always reuse or split existing geometry.')
        self.object_snap_mode.currentIndexChanged.connect(self.on_snap_settings_changed)
        self.object_snap_check.toggled.connect(self.object_snap_mode.setEnabled)
        self.object_snap_check.setToolTip('Attract corridor, node and door placement to nearby graph points and edges. Exact coincidences still connect to avoid duplicate topology.')
        self.snap_check.toggled.connect(self.on_snap_settings_changed)
        self.object_snap_check.toggled.connect(self.on_snap_settings_changed)
        self.grid_spacing_spin.valueChanged.connect(self.on_snap_settings_changed)

        self.chain_edges_check = QCheckBox("Chain edge creation")
        self.chain_edges_check.setChecked(True)
        self.bidirectional_check = QCheckBox("Bidirectional edges")
        self.bidirectional_check.setChecked(True)
        self.show_dxf_check = QCheckBox("Show DXF")
        self.show_dxf_check.setChecked(True)
        self.show_pdf_check = QCheckBox("Show PDF underlay")
        self.show_pdf_check.setChecked(True)
        self.show_labels_check = QCheckBox("Show labels")
        self.show_labels_check.setChecked(True)
        self.object_label_mode = QComboBox()
        self.object_label_mode.setAccessibleName('Graph object name visibility')
        for title, value in [('All object names', 'all'), ('Locations, departments, lifts and doors', 'key'), ('Selected objects only', 'selected')]:
            self.object_label_mode.addItem(title, value)
        self.object_label_mode.setToolTip('Filter graph names without hiding objects. Selected corridor endpoints and selected route-profile points are included. Door symbols and profile labels are separate.')
        self.object_label_mode.currentIndexChanged.connect(self.refresh_canvas)
        self.show_labels_check.toggled.connect(self.object_label_mode.setEnabled)
        self.show_location_bounds_check = QCheckBox("Show location bounding boxes")
        self.show_location_bounds_check.setChecked(True)
        self.show_charging_spaces_check = QCheckBox("Show charging spaces")
        self.show_charging_spaces_check.setChecked(True)
        self.show_dxf_check.toggled.connect(self.refresh_canvas)
        self.show_pdf_check.toggled.connect(self.refresh_canvas)
        self.show_labels_check.toggled.connect(self.refresh_canvas)
        self.show_location_bounds_check.toggled.connect(self.refresh_canvas)
        self.show_charging_spaces_check.toggled.connect(self.refresh_canvas)

        self.ribbon_tabs = QTabWidget()
        self.ribbon_tabs.setDocumentMode(True)
        self.ribbon_tabs.tabBar().setUsesScrollButtons(True)
        self.ribbon_tabs.setElideMode(Qt.ElideRight)
        self.ribbon_tabs.setMinimumHeight(160)
        self.ribbon_tabs.setMaximumHeight(240)
        layout.addWidget(self.ribbon_tabs)

        ribbon_pages = []

        def create_page(title):
            scroll = QScrollArea()
            scroll.setWidgetResizable(False)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            scroll.setFrameShape(QFrame.NoFrame)
            content = QWidget()
            content.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
            page_layout = QHBoxLayout(content)
            page_layout.setSizeConstraint(QLayout.SetMinimumSize)
            page_layout.setContentsMargins(6, 5, 6, 5)
            page_layout.setSpacing(6)
            scroll.setWidget(content)
            self.ribbon_tabs.addTab(scroll, title)
            ribbon_pages.append((content, page_layout))
            return page_layout

        def add_group(page_layout, title, widgets, columns=2):
            box = QGroupBox(title)
            grid = QGridLayout(box)
            grid.setContentsMargins(7, 6, 7, 6)
            grid.setHorizontalSpacing(5)
            grid.setVerticalSpacing(4)
            row = 0
            col = 0
            for widget in widgets:
                if isinstance(widget, tuple):
                    label, control = widget
                    grid.addWidget(QLabel(label), row, col)
                    grid.addWidget(control, row, col + 1)
                    row += 1
                    col = 0
                    continue
                grid.addWidget(widget, row, col)
                col += 1
                if col >= columns:
                    row += 1
                    col = 0
            page_layout.addWidget(box)
            return box

        def button(text, handler, tooltip=""):
            control = QPushButton(text)
            control.clicked.connect(handler)
            if tooltip:
                control.setToolTip(tooltip)
            return control

        home = create_page("Home")
        add_group(
            home,
            "File",
            [
                button("Open project / JSON", self.open_json),
                button(
                    "Open without drawings",
                    lambda: self.open_json(load_drawings=False),
                    "Open a configuration without loading DXF drawings or PDF backgrounds. Saved drawing paths are preserved.",
                ),
                button("Save", self.save_json),
                button("Save project as", lambda: self.save_project(save_as=True)),
                button("Export JSON", self.export_project_json),
                button("Project revisions", self.show_project_revisions),
                button("Recover unsaved work", self.recover_unsaved_work),
                button(
                    "Export floor DXF",
                    self.export_current_floor_dxf,
                    "Export the editable geometry on the current floor in your chosen units. Background DXF/PDF artwork is excluded.",
                ),
                button(
                    "Export all floors DXF",
                    self.export_all_floors_dxf,
                    "Export every configured floor to a separate, sequentially numbered DXF file. Background DXF/PDF artwork is excluded.",
                ),
                button("Project checks", self.validate_json),
                button("Demand preview", self.show_demand_preview),
                button("Results investigation", self.show_results_investigation),
                button("Project runs", self.show_project_runs),
            ],
            columns=3,
        )
        add_group(
            home,
            "Drawing",
            [
                button("Map DXF to floor", self.load_dxf),
                button("Clear floor DXF", self.clear_floor_dxf),
                button("Import PDF underlay", self.load_pdf_underlay),
                button("PDF settings", self.edit_pdf_underlay),
                button("Clear floor PDF", self.clear_floor_pdf_underlay),
                button("Fit view", self.fit_view),
                button("Load configured drawings", self.load_configured_drawings),
            ],
            columns=3,
        )

        edit = create_page("Edit")
        self.undo_action = QAction("Undo", self)
        self.undo_action.setShortcut(QKeySequence.Undo)
        self.undo_action.triggered.connect(self.undo_edit)
        self.redo_action = QAction("Redo", self)
        self.redo_action.setShortcuts([QKeySequence.Redo, QKeySequence("Ctrl+Shift+Z")])
        self.redo_action.triggered.connect(self.redo_edit)
        self.addActions([self.undo_action, self.redo_action])
        undo_button = QPushButton("Undo")
        redo_button = QPushButton("Redo")
        for control, action in ((undo_button, self.undo_action), (redo_button, self.redo_action)):
            control.clicked.connect(action.trigger)
            def sync(control=control, action=action):
                control.setText(action.text())
                control.setEnabled(action.isEnabled())
                control.setToolTip(action.toolTip())
            action.changed.connect(sync)
            sync()
        add_group(edit, "History", [undo_button, redo_button], columns=1)
        add_group(edit, "Placement", [("Mode", self.mode_combo)], columns=2)
        add_group(
            edit,
            "Drawing behaviour",
            [self.snap_check, ("Spacing", self.grid_spacing_spin), self.object_snap_check, self.object_snap_mode, self.bidirectional_check, self.chain_edges_check],
            columns=1,
        )
        add_group(edit, "Corridor sections", [
            button("Create crossing junction", self.create_selected_junction,
                   "Join two selected crossing corridors on one floor. Retains directions, widths and references; one undo step."),
            button("Split at midpoint", lambda: self.subdivide_selected_corridors(2),
                   "Insert one node per selected corridor. Retains attributes and references; Undo restores all changes."),
            button("Subdivide selected…", self.subdivide_selected_corridors,
                   "Divide each selected corridor into equal sections. Added sections can change traffic reservations."),
        ], columns=1)
        add_group(edit, "Draw route", [button("Finish route", self.finish_corridor_drawing,
                  "Finish the current chain (Escape or right-click). Placed segments remain; Undo removes the last step.")], columns=1)
        self.finish_route_action = QAction("Cancel current CAD command", self)
        self.finish_route_action.setShortcut(QKeySequence("Escape"))
        self.finish_route_action.setEnabled(True)
        self.finish_route_action.triggered.connect(self.cancel_cad_command)
        self.addAction(self.finish_route_action)

        view = create_page("View")
        self.route_display_combo = QComboBox()
        self.route_display_combo.setAccessibleName('Route profile display')
        self.route_display_combo.setMinimumContentsLength(20)
        self.route_display_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.route_display_combo.currentIndexChanged.connect(self.refresh_canvas)
        self.route_labels_check = QCheckBox('Show profile labels')
        self.route_labels_check.setChecked(True)
        self.route_labels_check.toggled.connect(self.refresh_canvas)
        add_group(view, 'Profile access (schematic)', [self.route_display_combo, self.route_labels_check,
                  button('Route identification…', self.show_route_identification)], columns=1)
        add_group(
            view,
            "Display",
            [
                self.show_pdf_check,
                self.show_dxf_check,
                self.show_labels_check,
                self.object_label_mode,
                self.show_location_bounds_check,
                self.show_charging_spaces_check,
            ],
            columns=2,
        )
        add_group(view, "Navigation", [button("Fit view", self.fit_view)], columns=1)

        simulation = create_page("Simulation")
        add_group(
            simulation,
            "Configuration",
            [
                button("Simulation settings", self.manage_simulation_settings),
                button("Scenario testing", self.manage_scenario_testing),
                button("People movement", self.manage_people_movement),
                button("Corridor widths and doors", self.manage_corridor_settings),
            ],
            columns=2,
        )
        classification_button = QPushButton("Classify selected corridors")
        classification_menu = QMenu(classification_button)
        for label, value in [
            ("No restriction", "none"),
            ("Staff", "staff"),
            ("Public", "public"),
            ("Mixed staff/public", "both"),
        ]:
            action = classification_menu.addAction(label)
            action.triggered.connect(
                lambda _checked=False, area=value: self.classify_selected_corridors(area)
            )
        classification_button.setMenu(classification_menu)
        door_button = QPushButton("Set selected door nodes")
        door_menu = QMenu(door_button)
        mark_door = door_menu.addAction("Mark as door…")
        clear_door = door_menu.addAction("Remove door classification")
        mark_door.triggered.connect(self.mark_selected_nodes_as_doors)
        clear_door.triggered.connect(self.clear_selected_node_doors)
        door_button.setMenu(door_menu)
        add_group(
            simulation,
            "Topology selection",
            [
                button("Scenario from selection", self.manage_scenario_testing),
                button("People profile from selection", self.create_people_profile_from_selection),
                button("Edit selected corridors", self.manage_corridor_settings),
                classification_button,
                door_button,
                button("Clear selection", self.clear_topology_selection),
            ],
            columns=2,
        )

        assets = create_page("Assets")
        add_group(
            assets,
            "AMR system",
            [
                button("AMRs", self.manage_amrs),
                button("Payloads", self.manage_payloads),
                button("Locations & spaces", self.manage_location_spaces),
                button("Charging locations", self.manage_charging_locations),
                button("Lifts", self.manage_lifts),
            ],
            columns=2,
        )

        operations = create_page("Operations")
        add_group(
            operations,
            "Tasks and routing",
            [
                button("Tasks", self.manage_tasks),
                button("Task planner", self.manage_task_planner),
                button("Task generation", self.manage_task_generation),
                button("Route profiles", self.manage_route_profiles),
            ],
            columns=2,
        )

        services = create_page("Services")
        add_group(
            services,
            "Departments and waste",
            [
                button("Departments", self.manage_departments),
                button("Waste streams", self.manage_waste_streams),
                button("Mass collections", self.manage_mass_collections),
            ],
            columns=3,
        )

        for content, page_layout in ribbon_pages:
            page_layout.addStretch(1)
            content.adjustSize()

        from project_workspace import ProjectWorkspace
        self.workspace = ProjectWorkspace(self, self.canvas)
        from cad_toolbar import CadToolBar
        self.cad_toolbar = CadToolBar(self)
        self.workspace.central_layout.insertWidget(0, self.cad_toolbar)
        self.workspace._sync_panels()
        layout.addWidget(self.workspace, 1)
        layout.addWidget(self.ensure_cad_drawing_input())
        from visualiser.cad_move_input import CadMoveInput
        self.cad_move_input = CadMoveInput(self)
        layout.addWidget(self.cad_move_input)
        from visualiser.rectangle_input import RectangleInput
        self.rectangle_input = RectangleInput(self)
        layout.addWidget(self.rectangle_input)

        self.run_lock_label = QLabel('Simulation running — project editing is locked. Stop the run in Simulate or wait for it to finish.')
        self.run_lock_label.setWordWrap(True)
        self.run_lock_label.setAccessibleName('Simulation project editing lock')
        self.run_lock_label.hide()
        layout.addWidget(self.run_lock_label)

        self.status_label = QLabel("Ready")
        self.status_label.setMinimumWidth(240)
        self.file_label = QLabel("New file")
        self.file_label.setToolTip("Current JSON file")
        self.statusBar().addWidget(self.status_label, 1)
        self.statusBar().addPermanentWidget(self.file_label)
        from cad_workbench import CadWorkbench
        self.workbench = CadWorkbench(self)
        layout.insertWidget(0, self.workbench.workflow)
        self.workspace._sync_panels()

    def _current_edit_mode(self):
        return str(self.mode_combo.currentData() or "select_move")

    def _set_edit_mode(self, value):
        if hasattr(self, 'workspace'):
            self.workspace.show_page('layout', self.canvas)
        index = self.mode_combo.findData(str(value))
        if index >= 0:
            self.mode_combo.setCurrentIndex(index)

    def _clear_corridor_drawing(self):
        self._rectangle_draft = None
        if hasattr(self, 'rectangle_input'):
            self.rectangle_input.hide()
            self.rectangle_input.dimensions.clear()
        self.corridor_draw_start = None
        self.corridor_draw_preview = None
        if hasattr(self, 'cad_drawing_input'):
            self.cad_drawing_input.coordinate_edit.clear()
            self.cad_drawing_input.feedback('Click or type a start point. Typed input bypasses grid; object snapping follows the Object snap setting.')
        if hasattr(self, 'canvas'):
            self.canvas.viewport().update()

    def on_edit_mode_changed(self, *_):
        if hasattr(self, 'cad_move_input'):
            self.cad_move_input.hide()
        self._clear_corridor_drawing()
        drawing = (self._current_edit_mode() == 'corridor_draw'
                   and getattr(getattr(self, 'workspace', None), 'stage', 'layout') == 'layout')
        if hasattr(self, 'cad_drawing_input'):
            self.cad_drawing_input.setVisible(drawing)
            self.cad_drawing_input.setEnabled(drawing)
        if hasattr(self, 'finish_route_enter_action'):
            self.finish_route_enter_action.setEnabled(drawing)
        self.selected_for_edge = None
        self.edge_delete_start = None
        self.refresh_canvas()

    def ensure_cad_drawing_input(self):
        if not hasattr(self, 'cad_drawing_input'):
            drawing = (self._current_edit_mode() == 'corridor_draw'
                       and getattr(getattr(self, 'workspace', None), 'stage', 'layout') == 'layout')
            from cad_drawing_input import CadDrawingInput
            self.cad_drawing_input = CadDrawingInput(self)
            self.cad_drawing_input.submitted.connect(self.submit_corridor_coordinate)
            self.cad_drawing_input.cancelled.connect(self.cancel_cad_command)
            self.cad_drawing_input.draftChanged.connect(self.preview_typed_corridor)
            self.cad_drawing_input.direction.currentIndexChanged.connect(self.on_snap_settings_changed)
            self.cad_drawing_input.setVisible(drawing)
            self.cad_drawing_input.setEnabled(drawing)
            self.cad_drawing_input.feedback('Click or type a start point. Typed input bypasses grid; object snapping follows the Object snap setting.')
            self.finish_route_enter_action = QAction('Finish corridor route', self.canvas)
            self.finish_route_enter_action.setShortcuts([QKeySequence('Return'), QKeySequence('Enter')])
            self.finish_route_enter_action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            self.finish_route_enter_action.setEnabled(drawing)
            self.finish_route_enter_action.triggered.connect(self.finish_corridor_drawing)
            self.canvas.addAction(self.finish_route_enter_action)
        return self.cad_drawing_input

    def cancel_cad_command(self, *_):
        if getattr(self, '_rectangle_draft', None):
            self._rectangle_draft = None
            self.rectangle_input.hide()
            self.canvas.viewport().update()
            self.set_status('Rectangle cancelled; the original location boundary is unchanged.')
            return True
        if hasattr(self, 'cad_move_input') and not self.cad_move_input.isHidden():
            self.cad_move_input.hide()
            return True
        if self.cancel_cad_drag():
            return True
        cancel_selection = getattr(self, 'cancel_cad_selection', None)
        if cancel_selection is not None and cancel_selection():
            return True
        if self._current_edit_mode() == 'corridor_draw':
            self.finish_corridor_drawing()
            return True
        return False

    def _typed_corridor_target(self, text):
        from cad_drawing_input import parse_coordinate
        from corridor_editing import drawing_target
        start = self.store.all_points().get(self.corridor_draw_start)
        anchor = (float(start['x']), float(start['y'])) if start else None
        point = parse_coordinate(text, anchor)
        if point is None:
            return None, None
        target = drawing_target(self.store.all_points(), self.store.data['corridors']['edges'],
                                self.floor_spin.value(), *point, snap=False, exact=True,
                                grid_spacing=self.grid_spacing_spin.value(), object_snap=self.object_snap_check.isChecked(), snap_mode=self.object_snap_mode.currentData(), anchor=anchor)
        return point, target

    def _corridor_drawing_feedback(self, target, *, typed=False):
        kind = {'point': 'Object snap: existing point', 'edge': 'Object snap: corridor split', 'junction': 'Object snap: intersection (connect junction)',
                'new': 'Typed exact point' if typed else ('Constrained point' if target.get('angle_step') else
                        ('Grid point' if self.snap_check.isChecked() else 'Free point'))}[target['kind']]
        if target.get('snap_label') == 'midpoint':
            kind = 'Object snap: corridor midpoint (split)'
        elif target.get('snap_label') == 'perpendicular':
            kind = 'Object snap: perpendicular ' + ('(split)' if target['kind'] == 'edge' else '(existing endpoint)')
        text = f"{kind} | X {target['x']:.12g}, Y {target['y']:.12g} m"
        start = self.store.all_points().get(self.corridor_draw_start)
        if start:
            dx, dy = target['x'] - float(start['x']), target['y'] - float(start['y'])
            text += f' | {math.hypot(dx,dy):.6g} m at {math.degrees(math.atan2(dy,dx)) % 360:.6g}°'
        if typed:
            text += ' | grid bypassed; direction constraint bypassed'
        elif target.get('angle_step'):
            text += f" | direction constrained to {target['angle_step']:g}° increments"
        if self.object_snap_check.isChecked() and self.object_snap_mode.currentData() == 'perpendicular' and not start:
            text += ' | perpendicular snap needs a route start'
        if hasattr(self, 'cad_drawing_input'):
            self.cad_drawing_input.feedback(text)
        return text

    def preview_typed_corridor(self, text):
        if (self._current_edit_mode() != 'corridor_draw'
                or getattr(getattr(self, 'workspace', None), 'stage', 'layout') != 'layout'):
            return
        try:
            _, target = self._typed_corridor_target(text)
            self.corridor_draw_preview = target
            if target:
                self._corridor_drawing_feedback(target, typed=True)
            else:
                self.cad_drawing_input.feedback('Type a point; blank Enter finishes the route. Escape cancels the draft.')
        except (ValueError, KeyError, TypeError) as exc:
            self.corridor_draw_preview = None
            self.cad_drawing_input.feedback(str(exc), error=True)
        self.canvas.viewport().update()

    def submit_corridor_coordinate(self):
        if (self._current_edit_mode() != 'corridor_draw'
                or getattr(getattr(self, 'workspace', None), 'stage', 'layout') != 'layout'):
            return False
        text = self.cad_drawing_input.coordinate_edit.text()
        try:
            point, target = self._typed_corridor_target(text)
        except (ValueError, KeyError, TypeError) as exc:
            self.cad_drawing_input.feedback(str(exc), error=True)
            return False
        if point is None:
            self.finish_corridor_drawing()
            return True
        feedback = self._corridor_drawing_feedback(target, typed=True)
        if not self.draw_next_corridor(*point, exact=True):
            self.cad_drawing_input.feedback(self.status_label.text(), error=True)
            return False
        self.cad_drawing_input.coordinate_edit.clear()
        self.cad_drawing_input.feedback('Placed: ' + feedback)
        return True

    def finish_corridor_drawing(self, *_):
        if self._current_edit_mode() != 'corridor_draw':
            return
        self._clear_corridor_drawing()
        self.set_status('Route finished. Click to start another route; Undo removes the last placed step.')

    def preview_corridor_drawing(self, sx, sy):
        if self._current_edit_mode() != 'corridor_draw':
            return
        if hasattr(self, 'cad_drawing_input') and self.cad_drawing_input.coordinate_edit.text().strip():
            return
        from corridor_editing import drawing_target
        x, y = self.scene_to_world(sx, sy)
        try:
            start = self.store.all_points().get(self.corridor_draw_start)
            self.corridor_draw_preview = drawing_target(self.store.all_points(), self.store.data['corridors']['edges'],
                self.floor_spin.value(), x, y, self.snap_check.isChecked(),
                grid_spacing=self.grid_spacing_spin.value(), object_snap=self.object_snap_check.isChecked(), snap_mode=self.object_snap_mode.currentData(),
                anchor=(start['x'], start['y']) if start else None, angle_step=self.corridor_angle_step())
            self._corridor_drawing_feedback(self.corridor_draw_preview)
        except (ValueError, KeyError, TypeError):
            self.corridor_draw_preview = None
        self.canvas.viewport().update()

    @undoable('Draw corridor step')
    def draw_next_corridor(self, x, y, *, exact=False):
        try:
            target = self.store.draw_corridor_step(self.corridor_draw_start, self.floor_spin.value(), x, y,
                snap=False if exact else self.snap_check.isChecked(),
                bidirectional=self.bidirectional_check.isChecked(), exact=exact,
                grid_spacing=self.grid_spacing_spin.value(), object_snap=self.object_snap_check.isChecked(), snap_mode=self.object_snap_mode.currentData(),
                angle_step=self.corridor_angle_step())
        except (ValueError, KeyError, TypeError) as exc:
            self.set_status(f'Route was not changed: {exc}')
            return False
        self.corridor_draw_start = target['name']
        self.corridor_draw_preview = None
        if not exact and hasattr(self, 'cad_drawing_input'):
            self.cad_drawing_input.coordinate_edit.clear()
        self.selected_point_name = target['name']
        self.selected_point_names = {target['name']}
        self.selected_edge_keys.clear()
        self.refresh_canvas()
        self.set_status(f"Route end: {target['name']}. Click the next point; right-click or Escape finishes. Existing directions and profiles are retained.")
        return True

    def corridor_angle_step(self):
        return self.cad_drawing_input.direction.currentData() if hasattr(self, 'cad_drawing_input') else None

    def set_status(self, text):
        self.status_label.setText(text)

    @staticmethod
    def _physical_edge_key(from_name, to_name):
        a = str(from_name or "").strip()
        b = str(to_name or "").strip()
        return tuple(sorted((a, b)))

    def _edge_label_for_key(self, key):
        for edge in self.store.data.get("corridors", {}).get("edges", []):
            if self._physical_edge_key(edge.get("from"), edge.get("to")) == key:
                return f"{edge.get('from', '')} -> {edge.get('to', '')}"
        return f"{key[0]} -> {key[1]}"

    def _selected_corridor_keys(self, include_incident_nodes=True):
        keys = set(self.selected_edge_keys)
        if include_incident_nodes:
            node_names = set(self.selected_point_names)
            for edge in self.store.data.get("corridors", {}).get("edges", []):
                if edge.get("from") in node_names or edge.get("to") in node_names:
                    keys.add(self._physical_edge_key(edge.get("from"), edge.get("to")))
        return keys

    def selected_corridor_labels(self, include_incident_nodes=True):
        return sorted(
            self._edge_label_for_key(key)
            for key in self._selected_corridor_keys(include_incident_nodes)
        )

    def selected_corridor_node_names(self):
        points = self.store.all_points()
        return sorted(
            name
            for name in self.selected_point_names
            if points.get(name, {}).get("kind") == "corridor_node"
        )

    def topology_selection_payload(self):
        return {
            "corridor": self.selected_corridor_labels(include_incident_nodes=False),
            "corridor_node": self.selected_corridor_node_names(),
        }

    @undoable('Delete selected objects')
    def delete_selected(self):
        if (self.workspace.stage != 'layout' or self._current_edit_mode() != 'select_move'
                or self.route_profile_selection_active or self.department_location_placement_active
                or self.dragging_point_name or self.drag_mode_active):
            return False
        if not self._finish_property_draft():
            return False
        points = self.store.all_points()
        names = set(self.selected_point_names) & points.keys()
        edges = set(self.selected_edge_keys)
        if not names and not edges:
            return False
        lifts = {points[name]['lift_id'] for name in names if points[name]['kind'] == 'lift_node'}
        detail = f'Delete {len(names)} selected point(s) and {len(edges)} selected corridor(s)?'
        if lifts:
            detail += '\nEntire lifts, including all floors: ' + ', '.join(sorted(lifts))
        detail += '\nConnected edges and associated references are handled by the existing deletion rules. Undo restores this operation.'
        if QMessageBox.question(self, 'Delete selected', detail,
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return False
        # Stage the whole selection: a protected department must not leave
        # earlier deletions applied when its reference check rejects removal.
        staged = deepcopy(self.store)
        try:
            from amr_department_inputs import department_identity
            for name in sorted(names):
                if points[name]['kind'] == 'department':
                    department = next(d for d in staged.data['departments'] if d.get('name') == name)
                    staged.delete_department(department_identity(department))
                elif points[name]['kind'] != 'lift_node':
                    staged.delete_point(name)
            for lift in sorted(lifts):
                staged.delete_lift(lift)
            for a, b in edges:
                staged.remove_edge(a, b)
                staged.remove_edge(b, a)
        except ValueError as exc:
            QMessageBox.warning(self, 'Selection was not deleted', str(exc))
            return False
        self.store.data = staged.data
        self.properties_panel.reset()
        self.clear_topology_selection()
        self.set_status('Deleted selection. Undo restores the selected objects and their connections.')
        return True

    def clear_topology_selection(self):
        self.selected_point_names.clear()
        self.selected_edge_keys.clear()
        self.selected_point_name = None
        self.dragging_point_name = None
        self.drag_mode_active = False
        self.set_status("Topology selection cleared")
        self.refresh_canvas()

    def _apply_corridor_cuts(self, cuts):
        try:
            chains = self.store.subdivide_corridors(cuts)
        except (ValueError, TypeError, KeyError) as exc:
            QMessageBox.information(self, "Corridors were not changed", str(exc))
            return False
        self.selected_point_names = {name for chain in chains.values() for name in chain[1:-1]}
        self.selected_point_name = next(iter(sorted(self.selected_point_names)), None)
        self.selected_edge_keys = {self._physical_edge_key(a, b) for chain in chains.values() for a, b in zip(chain, chain[1:])}
        self.selected_for_edge = None
        self.set_status(f"Inserted {len(self.selected_point_names)} node(s) in {len(chains)} corridor(s). Undo restores the original routes and references.")
        self.refresh_canvas()
        return True

    @undoable("Subdivide corridors")
    def subdivide_selected_corridors(self, sections=None):
        keys = set(self.selected_edge_keys)
        if not keys:
            self.set_status("Select one or more corridor edges before subdividing.")
            return False
        # QPushButton.clicked supplies a bool; it is not a section count.
        if sections is None or isinstance(sections, bool):
            sections, accepted = QInputDialog.getInt(self, "Subdivide selected corridors",
                f"Sections per corridor ({len(keys)} selected).\nEach corridor gains sections minus one nodes. Widths, directions and route references are retained.\nTraffic reservation and people-occupancy timing may change with the new sections.",
                2, 2, 100)
            if not accepted:
                return False
        if type(sections) is not int or not 2 <= sections <= 100:
            return False
        return self._apply_corridor_cuts({key: [i / sections for i in range(1, sections)] for key in keys})

    @undoable('Create crossing junction')
    def create_selected_junction(self):
        if (self.workspace.stage != 'layout' or self.drag_mode_active
                or not self._finish_property_draft()):
            return False
        from corridor_editing import create_crossing_junction
        try:
            points = self.store.all_points()
            if any(int(points[name]['floor']) != self.floor_spin.value()
                   for key in self.selected_edge_keys for name in key):
                raise ValueError('Select crossing corridors on the active floor.')
            updated, chains = create_crossing_junction(self.store.data, points, self.selected_edge_keys)
        except (ValueError, KeyError, TypeError) as exc:
            self.set_status(f'Junction was not created: {exc}')
            return False
        self.store.data = updated
        self.selected_point_names = {name for chain in chains.values() for name in chain[1:-1]}
        self.selected_point_name = next(iter(self.selected_point_names))
        self.selected_edge_keys = {self._physical_edge_key(a, b) for chain in chains.values() for a, b in zip(chain, chain[1:])}
        self.refresh_canvas()
        self.set_status(f'Created junction {self.selected_point_name}. The selected routes now connect; directions and profile restrictions are retained.')
        return True

    @undoable("Insert corridor node")
    def split_corridor_at(self, key, x, y):
        from corridor_editing import project_fraction
        points = self.store.all_points()
        try:
            fraction = project_fraction(points[key[0]], points[key[1]], x, y)
        except (ValueError, KeyError, TypeError) as exc:
            QMessageBox.information(self, "Corridor was not changed", str(exc))
            return False
        return self._apply_corridor_cuts({key: [fraction]})

    def find_nearest_edge_key(self, x, y, floor, radius_world=0.45):
        points = self.store.all_points()
        best_key = None
        best_distance = float(radius_world)
        visited = set()
        for edge in self.store.data.get("corridors", {}).get("edges", []):
            a = points.get(edge.get("from"))
            b = points.get(edge.get("to"))
            if not a or not b:
                continue
            if int(a.get("floor", -1)) != int(floor) or int(b.get("floor", -1)) != int(floor):
                continue
            key = self._physical_edge_key(edge.get("from"), edge.get("to"))
            if key in visited:
                continue
            visited.add(key)
            ax, ay = float(a.get("x", 0.0)), float(a.get("y", 0.0))
            bx, by = float(b.get("x", 0.0)), float(b.get("y", 0.0))
            dx, dy = bx - ax, by - ay
            length_sq = dx * dx + dy * dy
            if length_sq <= 1e-12:
                distance = math.hypot(x - ax, y - ay)
            else:
                t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / length_sq))
                px, py = ax + t * dx, ay + t * dy
                distance = math.hypot(x - px, y - py)
            if distance <= best_distance:
                best_distance = distance
                best_key = key
        return best_key

    @undoable("Classify corridors")
    def classify_selected_corridors(self, area_type):
        keys = self._selected_corridor_keys(include_incident_nodes=True)
        if not keys:
            QMessageBox.information(
                self,
                "Corridor classification",
                "Select one or more corridor edges or corridor nodes first.",
            )
            return
        area = str(area_type or "none").lower()
        if area == "mixed":
            area = "both"
        updated = 0
        for edge in self.store.data.get("corridors", {}).get("edges", []):
            if self._physical_edge_key(edge.get("from"), edge.get("to")) in keys:
                edge["people_area_type"] = area
                updated += 1
        self.set_status(f"Classified {len(keys)} corridor asset(s) as {area}")
        self.refresh_canvas()

    @undoable("Set door openings")
    def mark_selected_nodes_as_doors(self):
        names = self.selected_corridor_node_names()
        if not names:
            QMessageBox.information(
                self, "Door nodes", "Select one or more corridor nodes first."
            )
            return
        default_width = float(
            self.store.data.get("building", {}).get("default_door_clear_width_m", 0.9)
            or 0.9
        )
        width, ok = QInputDialog.getDouble(
            self,
            "Door clear opening",
            "Clear opening width (m):",
            default_width,
            0.1,
            20.0,
            3,
        )
        if not ok:
            return
        for node in self.store.data.get("corridors", {}).get("nodes", []):
            if node.get("name") in names:
                node["has_door"] = True
                node["door_clear_width_m"] = float(width)
        self.set_status(f"Marked {len(names)} corridor node(s) as {width:.3f} m doors")
        self.refresh_canvas()

    @undoable("Set door openings")
    def clear_selected_node_doors(self):
        names = self.selected_corridor_node_names()
        if not names:
            QMessageBox.information(
                self, "Door nodes", "Select one or more corridor nodes first."
            )
            return
        for node in self.store.data.get("corridors", {}).get("nodes", []):
            if node.get("name") in names:
                node["has_door"] = False
        self.set_status(f"Removed door classification from {len(names)} node(s)")
        self.refresh_canvas()

    @undoable("Edit people profiles")
    def create_people_profile_from_selection(self):
        selected = self.selected_corridor_labels(include_incident_nodes=True)
        if not selected:
            QMessageBox.information(
                self,
                "People movement",
                "Select one or more corridor edges or corridor nodes first.",
            )
            return
        locations = sorted(self.store.all_points().keys())
        corridor_options = sorted(
            {
                f"{edge.get('from', '')} -> {edge.get('to', '')}"
                for edge in self.store.data.get("corridors", {}).get("edges", [])
                if edge.get("from") and edge.get("to")
            }
        )
        seed = {"id": f"PEOPLE-{len(self.store.people_movements()) + 1}"}
        from dialogs import PeopleMovementEditorDialog

        dialog = PeopleMovementEditorDialog(
            self,
            locations,
            corridor_options,
            seed=seed,
            initially_selected_corridors=selected,
        )
        if dialog.exec() == QDialog.Accepted and dialog.result:
            movements = list(self.store.people_movements())
            movements.append(dialog.result)
            self.store.set_people_movements(movements)
            profile_id = dialog.result.get("id", "")
            selected_keys = self._selected_corridor_keys(include_incident_nodes=True)
            for edge in self.store.data.get("corridors", {}).get("edges", []):
                if self._physical_edge_key(edge.get("from"), edge.get("to")) in selected_keys:
                    profile_ids = list(edge.get("people_profile_ids", []) or [])
                    if profile_id and profile_id not in profile_ids:
                        profile_ids.append(profile_id)
                    edge["people_profile_ids"] = profile_ids
                    group = str(dialog.result.get("group_type", "staff") or "staff")
                    edge["people_area_type"] = "both" if group == "both" else group
            self.set_status(
                f"Created people profile {profile_id} for {len(selected_keys)} corridor asset(s)"
            )
            self.refresh_canvas()

    def start_department_location_placement(
        self,
        location_name,
        category_key,
        callback,
        return_dialog=None,
    ):
        self.department_location_placement_active = True
        self.department_location_placement_name = str(location_name).strip()
        self.department_location_placement_category_key = str(category_key).strip()
        self.department_location_placement_callback = callback
        self.department_location_placement_return_dialog = return_dialog

        self._set_edit_mode("select_move")
        self.set_status(
            f"Click the DXF/editor scene to place location {self.department_location_placement_name}"
        )

    def cancel_department_location_placement(self):
        self.department_location_placement_active = False
        self.department_location_placement_name = None
        self.department_location_placement_category_key = None
        self.department_location_placement_callback = None

        dialog = self.department_location_placement_return_dialog
        self.department_location_placement_return_dialog = None

        if dialog is not None:
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()

        self.set_status("Department location placement cancelled")

    def finish_department_location_placement(self, x, y, floor):
        if not self.department_location_placement_active:
            return False

        location_name = self.department_location_placement_name
        category_key = self.department_location_placement_category_key
        callback = self.department_location_placement_callback
        dialog = self.department_location_placement_return_dialog

        self.department_location_placement_active = False
        self.department_location_placement_name = None
        self.department_location_placement_category_key = None
        self.department_location_placement_callback = None
        self.department_location_placement_return_dialog = None

        payload = dict(category=category_key, name=location_name, floor=floor, x=x, y=y)

        if location_name in self.store.names_in_use():
            QMessageBox.critical(
                self,
                "Duplicate location",
                f"A point or location named '{location_name}' already exists.",
            )
            if dialog is not None:
                dialog.show()
                dialog.raise_()
                dialog.activateWindow()
            return True

        if callable(callback):
            callback(category_key, payload)

        if dialog is not None:
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()

        self.set_status(f"Location {location_name} is provisional until the department is saved")
        self.refresh_canvas()
        return True

    def task_generation_category_pairs(self):
        task_generation = (
            self.store.task_generation()
            if hasattr(self.store, "task_generation")
            else self.store.data.setdefault("task_generation", {})
        )

        pairs = []
        for key, item in task_generation.get("categories", {}).items():
            if not isinstance(item, dict):
                continue
            label = str(item.get("display_name", "")).strip() or str(key).title()
            suffix = str(
                item.get("department_location_suffix", f"-{key.upper()}")
            ).strip()
            pairs.append((str(key), label, suffix))

        return sorted(pairs, key=lambda x: x[1].lower())

    def department_dropoff_zone_names(self):
        return collect_department_dropoff_zone_names(
            self.store.data.get("departments", [])
        )

    def on_floor_changed(self, *_):
        if hasattr(self, 'cad_move_input'):
            self.cad_move_input.hide()
        self._clear_corridor_drawing()
        self.selected_for_edge = None
        self.edge_delete_start = None
        self.refresh_canvas()
        self._queue_all_floor_dxf_loads(
            active_floor=self.floor_spin.value(), force_reload=False
        )

    def floor_pdf_underlay_entries(self):
        return self.store.data.get("floor_pdf_underlays", [])

    def get_floor_pdf_underlay(self, floor):
        for entry in self.floor_pdf_underlay_entries():
            try:
                if int(entry.get("floor")) == int(floor):
                    return normalise_pdf_underlay(entry)
            except Exception:
                continue
        return None

    @undoable("Edit drawing mapping")
    def set_floor_pdf_underlay(self, floor, mapping):
        payload = normalise_pdf_underlay({**mapping, "floor": int(floor)})
        entries = self.store.data.setdefault("floor_pdf_underlays", [])
        for entry in entries:
            try:
                if int(entry.get("floor")) == int(floor):
                    entry.clear()
                    entry.update(payload)
                    return
            except Exception:
                continue
        entries.append(payload)
        entries.sort(key=lambda item: int(item.get("floor", 0)))

    @undoable("Edit drawing mapping")
    def clear_floor_pdf_underlay_mapping(self, floor):
        self.store.data["floor_pdf_underlays"] = [
            entry
            for entry in self.floor_pdf_underlay_entries()
            if int(entry.get("floor", -(10**9))) != int(floor)
        ]

    def _pdf_pixmap(self, mapping):
        key = (mapping["filepath"], int(mapping["page"]))
        cached = self._pdf_pixmap_cache.get(key)
        if cached is not None:
            return cached
        pixmap, page_count = render_pdf_page(
            mapping["filepath"], mapping["page"]
        )
        self._pdf_pixmap_cache[key] = (pixmap, page_count)
        self._pdf_render_errors.pop(key, None)
        return pixmap, page_count

    @undoable("Move PDF underlay", capture_before=False)
    def _pdf_underlay_moved(self, floor, x_m, y_m):
        mapping = self.get_floor_pdf_underlay(floor)
        if mapping is None:
            return
        mapping["x_m"] = round(float(x_m), 4)
        mapping["y_m"] = round(float(y_m), 4)
        self.set_floor_pdf_underlay(floor, mapping)
        self.set_status(
            f"PDF underlay aligned at ({mapping['x_m']:.3f}, "
            f"{mapping['y_m']:.3f}) m on floor {floor}"
        )

    def draw_pdf_underlay(self, floor):
        if not self._drawings_enabled:
            return
        mapping = self.get_floor_pdf_underlay(floor)
        if mapping is None or not mapping["filepath"]:
            return
        key = (mapping["filepath"], int(mapping["page"]))
        try:
            pixmap, _page_count = self._pdf_pixmap(mapping)
        except Exception as exc:
            message = str(exc)
            if self._pdf_render_errors.get(key) != message:
                self._pdf_render_errors[key] = message
                self.set_status(
                    f"Could not load PDF underlay {Path(mapping['filepath']).name}: "
                    f"{message}"
                )
            return
        movable = self._current_edit_mode() == "pdf_underlay_align"
        item = MovablePdfUnderlayItem(
            pixmap,
            mapping,
            movable=movable,
            moved_callback=lambda x, y, target_floor=int(floor): (
                self._pdf_underlay_moved(target_floor, x, y)
            ),
        )
        self.scene.addItem(item)

    def floor_dxf_entries(self):
        return self.store.data.get("floor_dxf_files", [])

    def get_floor_dxf_path(self, floor):
        for entry in self.floor_dxf_entries():
            try:
                if int(entry.get("floor")) == int(floor):
                    path = (entry.get("filepath") or "").strip()
                    return path or None
            except Exception:
                continue
        return None

    @undoable("Edit drawing mapping")
    def set_floor_dxf_path(self, floor, filepath):
        entries = self.store.data.setdefault("floor_dxf_files", [])
        payload = {"floor": int(floor), "filepath": str(filepath)}
        for entry in entries:
            try:
                if int(entry.get("floor")) == int(floor):
                    entry.clear()
                    entry.update(payload)
                    return
            except Exception:
                continue
        entries.append(payload)
        entries.sort(key=lambda item: int(item.get("floor", 0)))

    @undoable("Edit drawing mapping")
    def clear_floor_dxf_mapping(self, floor):
        self.store.data["floor_dxf_files"] = [
            entry
            for entry in self.floor_dxf_entries()
            if int(entry.get("floor", -(10**9))) != int(floor)
        ]

    def _all_mapped_floors(self):
        floors = []
        for entry in self.floor_dxf_entries():
            try:
                floor = int(entry.get("floor"))
            except Exception:
                continue
            if self.get_floor_dxf_path(floor):
                floors.append(floor)
        return sorted(set(floors))

    def _ensure_loading_dialog(self):
        if self._loading_dialog is None:
            self._loading_dialog = DXFLoadingDialog(self)
        return self._loading_dialog

    def _update_loading_dialog(self):
        if not self._loading_batch_active:
            return
        dialog = self._ensure_loading_dialog()
        total = len(self._loading_batch_floors)
        completed = 0
        for floor in self._loading_batch_floors:
            path = self.get_floor_dxf_path(floor)
            cached = self._dxf_cache.get(floor)
            if cached and path and cached.get("path") == path:
                completed += 1
            elif floor in self._loading_batch_failed:
                completed += 1
        failed_count = len(self._loading_batch_failed)
        pending = max(0, total - completed)
        message = f"Loading {total} DXF file(s)..."
        if pending:
            message = f"Loading {pending} remaining DXF file(s)..."
        elif failed_count:
            message = "Finished loading DXFs with some failures."
        else:
            message = "Finished loading all DXFs."
        dialog.update_progress(completed, total, message, failed_count=failed_count)
        if total > 0 and not dialog.isVisible():
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()
        QApplication.processEvents()
        if total > 0 and completed >= total:
            dialog.mark_complete()
            self._loading_batch_active = False

    def _start_loading_batch(self, floors):
        target_floors = []
        for floor in floors:
            floor = int(floor)
            path = self.get_floor_dxf_path(floor)
            if path:
                target_floors.append(floor)
        target_floors = sorted(set(target_floors))
        if not target_floors:
            return
        self._loading_batch_floors = set(target_floors)
        self._loading_batch_failed = set()
        self._loading_batch_active = True
        dialog = self._ensure_loading_dialog()
        dialog._completed = False
        self._update_loading_dialog()

    def _queue_all_floor_dxf_loads(self, active_floor=None, force_reload=False):
        if not self._drawings_enabled:
            return
        floors = self._all_mapped_floors()
        if not floors:
            return

        if active_floor is not None:
            active_floor = int(active_floor)
            floors = [active_floor] + [
                int(floor) for floor in floors if int(floor) != active_floor
            ]

        jobs = []

        for floor in floors:
            floor = int(floor)
            path = self.get_floor_dxf_path(floor)
            if not path:
                continue

            cached = self._dxf_cache.get(floor)
            force_this = bool(
                force_reload and active_floor is not None and floor == int(active_floor)
            )

            if (not force_this) and cached and cached.get("path") == path:
                if active_floor is not None and floor == int(active_floor):
                    self._set_active_dxf_floor(floor)
                continue

            if floor in self._dxf_loading_floors:
                continue

            self._dxf_loading_floors.add(floor)
            jobs.append((floor, path))

        if not jobs:
            self._update_loading_dialog()
            return

        self._start_loading_batch([floor for floor, _path in jobs])

        if active_floor is not None:
            self.set_status("Loading DXFs using multiple processes...")

        self._request_dxf_batch_load.emit(jobs)
        self._update_loading_dialog()

    def _clear_dxf_cache(self):
        self._dxf_cache.clear()
        self._dxf_loading_floors.clear()
        self._loading_batch_floors.clear()
        self._loading_batch_failed.clear()
        self._loading_batch_active = False
        if self._loading_dialog is not None and self._loading_dialog.isVisible():
            self._loading_dialog.mark_complete()
        self.current_dxf_path = None
        self.loaded_dxf_floor = None
        self.dxf_scene.clear()

    def _set_active_dxf_floor(self, floor):
        floor = int(floor)
        cached = self._dxf_cache.get(floor)
        if not cached:
            self.current_dxf_path = None
            self.loaded_dxf_floor = None
            self.dxf_scene.clear()
            return False
        self.current_dxf_path = cached["path"]
        self.loaded_dxf_floor = floor
        self.dxf_scene.set_content(cached["path"], cached["entities"], cached["bounds"])
        return True

    def request_floor_dxf_load(self, floor, force_reload=False, prefetch=False):
        if not self._drawings_enabled:
            return False
        floor = int(floor)
        path = self.get_floor_dxf_path(floor)

        if not path:
            if not prefetch and floor == self.floor_spin.value():
                self.dxf_scene.clear()
                self.current_dxf_path = None
                self.loaded_dxf_floor = None
            return False

        cached = self._dxf_cache.get(floor)
        if (not force_reload) and cached and cached.get("path") == path:
            if not prefetch and floor == self.floor_spin.value():
                self._set_active_dxf_floor(floor)
            return True

        if floor in self._dxf_loading_floors:
            self._update_loading_dialog()
            return False

        self._dxf_loading_floors.add(floor)
        self._start_loading_batch([floor])

        if not prefetch and floor == self.floor_spin.value():
            self.set_status(f"Loading DXF for floor {floor}...")

        self._request_dxf_batch_load.emit([(floor, path)])
        self._update_loading_dialog()
        return False

    def ensure_floor_dxf_loaded(self, floor, force_reload=False):
        if not self._drawings_enabled:
            return False
        floor = int(floor)
        path = self.get_floor_dxf_path(floor)
        if not path:
            if floor == self.floor_spin.value():
                self.dxf_scene.clear()
                self.current_dxf_path = None
                self.loaded_dxf_floor = None
            return False

        cached = self._dxf_cache.get(floor)
        if (not force_reload) and cached and cached.get("path") == path:
            return self._set_active_dxf_floor(floor)

        self.request_floor_dxf_load(floor, force_reload=force_reload, prefetch=False)
        return False

    def _prefetch_other_floor_dxfs(self, active_floor):
        for entry in self.floor_dxf_entries():
            try:
                floor = int(entry.get("floor"))
            except Exception:
                continue
            if floor == int(active_floor):
                continue
            self.request_floor_dxf_load(floor, prefetch=True)

    @Slot(int, str, object, object)
    def _on_dxf_loaded(self, floor, path, entities, bounds):
        if not self._drawings_enabled or self.get_floor_dxf_path(floor) != path:
            return
        floor = int(floor)
        self._dxf_loading_floors.discard(floor)
        self._loading_batch_failed.discard(floor)
        self._dxf_cache[floor] = {
            "path": path,
            "entities": list(entities or []),
            "bounds": bounds,
        }

        if self.get_floor_dxf_path(floor) != path:
            return

        if floor == self.floor_spin.value():
            self._set_active_dxf_floor(floor)
            self.refresh_canvas()
            if self._pending_fit_after_load:
                self._pending_fit_after_load = False
                self.fit_view()
            else:
                self.set_status(f"Loaded DXF {Path(path).name} for floor {floor}")

        self._prefetch_other_floor_dxfs(floor)
        self._update_loading_dialog()

    @Slot(int, str, str)
    def _on_dxf_failed(self, floor, path, error):
        if not self._drawings_enabled or self.get_floor_dxf_path(floor) != path:
            return
        floor = int(floor)
        self._dxf_loading_floors.discard(floor)
        self._loading_batch_failed.add(floor)
        cached = self._dxf_cache.get(floor)
        if cached and cached.get("path") == path:
            self._dxf_cache.pop(floor, None)
        if floor == self.floor_spin.value():
            self.dxf_scene.clear()
            self.current_dxf_path = None
            self.loaded_dxf_floor = None
            self.refresh_canvas()
            self.set_status(f"Failed to load DXF for floor {floor}: {error}")
        self._update_loading_dialog()

    def world_to_scene(self, x, y):
        return QPointF(float(x), -float(y))

    def scene_to_world(self, sx, sy):
        return float(sx), -float(sy)

    def on_snap_settings_changed(self, *_):
        self.corridor_draw_preview = None
        if hasattr(self, 'cad_drawing_input'):
            self.preview_typed_corridor(self.cad_drawing_input.coordinate_edit.text())
        if hasattr(self, 'canvas'):
            self.canvas.viewport().update()

    def snap(self, x, y):
        if self.snap_check.isChecked():
            spacing = self.grid_spacing_spin.value()
            return round(round(x / spacing) * spacing, 12), round(round(y / spacing) * spacing, 12)
        return round(x, 3), round(y, 3)

    def _content_bounds(self, floor):
        bounds = []
        if self._drawings_enabled and self.dxf_scene.bounds and self.loaded_dxf_floor == int(floor):
            bounds.append(self.dxf_scene.bounds)

        pdf_mapping = self.get_floor_pdf_underlay(floor)
        if self._drawings_enabled and pdf_mapping and pdf_mapping.get("filepath"):
            bounds.append(underlay_world_bounds(pdf_mapping))

        floor_points = self.store.points_for_floor(floor)
        if floor_points:
            xs = [float(p["x"]) for p in floor_points.values()]
            ys = [float(p["y"]) for p in floor_points.values()]
            bounds.append((min(xs), min(ys), max(xs), max(ys)))

        if self.show_location_bounds_check.isChecked():
            for location in self.store.locations_for_floor(floor):
                outline = self.store.get_location_bounding_box_points(location['name']) or []
                if len(outline) >= 3:
                    xs = [float(point['x']) for point in outline]
                    ys = [float(point['y']) for point in outline]
                    bounds.append((min(xs), min(ys), max(xs), max(ys)))

        if not bounds:
            return None

        min_x = min(b[0] for b in bounds)
        min_y = min(b[1] for b in bounds)
        max_x = max(b[2] for b in bounds)
        max_y = max(b[3] for b in bounds)
        return min_x, min_y, max_x, max_y

    def _scene_rect_for_floor(self, floor, padding=8.0):
        bounds = self._content_bounds(floor)
        if not bounds:
            return None
        min_x, min_y, max_x, max_y = bounds
        return self._scene_rect_from_bounds(
            (min_x, min_y, max_x, max_y), padding=padding
        )

    def _scene_rect_from_bounds(self, bounds, padding=8.0):
        min_x, min_y, max_x, max_y = bounds
        return QRectF(
            min_x - padding,
            -(max_y + padding),
            max(1.0, (max_x - min_x) + (padding * 2)),
            max(1.0, (max_y - min_y) + (padding * 2)),
        )

    def fit_view(self):
        floor = self.floor_spin.value()
        ready = self.ensure_floor_dxf_loaded(floor)
        bounds = self._content_bounds(floor)
        padding = max(1.0, max(bounds[2]-bounds[0], bounds[3]-bounds[1]) * .08) if bounds else 1.0
        rect = self._scene_rect_for_floor(floor, padding=padding)
        if self._drawings_enabled and rect is None and not ready and self.get_floor_dxf_path(floor):
            self._pending_fit_after_load = True
            return
        if (
            rect is not None
            and not rect.isNull()
            and rect.width() > 0
            and rect.height() > 0
        ):
            self.canvas.resetTransform()
            self.canvas.fitInView(rect, Qt.KeepAspectRatio)
            self.scene.setSceneRect(rect.adjusted(-40, -40, 40, 40))
            self.canvas.viewport().update()
        self.refresh_canvas()

    def selection_view_rect(self):
        """Finite active-floor selection bounds, independent of drawing underlays."""
        points = self.store.points_for_floor(self.floor_spin.value())
        names = set(self.selected_point_names)
        names.add(self.selected_point_name)
        current_edges = {self._physical_edge_key(e['from'], e['to'])
                         for e in self.store.data.get('corridors', {}).get('edges', [])}
        for key in self.selected_edge_keys & current_edges:
            names.update(key)
        coordinates = []
        for name in names:
            point = points.get(name)
            if point is None:
                continue
            coordinates.append((float(point['x']), float(point['y'])))
            if point.get('kind') == 'location':
                coordinates.extend((float(p['x']), float(p['y']))
                                   for p in self.store.get_location_bounding_box_points(name))
        if not coordinates:
            return None
        if not all(math.isfinite(v) for xy in coordinates for v in xy):
            raise ValueError('Selection has non-finite coordinates; repair them in Properties or Project checks.')
        left, right = min(x for x, _ in coordinates), max(x for x, _ in coordinates)
        bottom, top = min(y for _, y in coordinates), max(y for _, y in coordinates)
        padding = max(1., max(right-left, top-bottom)*.08)
        return QRectF(left-padding, -top-padding, right-left+2*padding, top-bottom+2*padding)

    def fit_selection(self):
        if self.workspace.stage != 'layout':
            self.set_status('Open Layout to zoom to selected graph objects.')
            return False
        try:
            rect = self.selection_view_rect()
        except (ValueError, TypeError, KeyError) as exc:
            self.set_status(f'Cannot zoom to selection: {exc}')
            return False
        if rect is None:
            self.set_status('Select points or corridors on this floor before zooming to selection.')
            return False
        self.scene.setSceneRect(self.scene.sceneRect().united(rect.adjusted(-40, -40, 40, 40)))
        self.canvas.resetTransform()
        self.canvas.fitInView(rect, Qt.KeepAspectRatio)
        self.canvas.viewport().update()
        self.set_status('Zoomed to selection on the current floor.')
        return True

    def refresh_canvas(self, *, update_panels=True):
        if hasattr(self, 'cad_move_input') and not self.cad_move_input.isHidden():
            self.cad_move_input.refresh_preview()
        from route_display import populate_choices
        from cad_map_style import map_colours
        populate_choices(self.route_display_combo, self.store.data)
        floor = self.floor_spin.value()
        self.ensure_floor_dxf_loaded(floor)
        source = self._dxf_cache.get(int(floor)) if (self._drawings_enabled and self.show_dxf_check.isChecked()
                                                   and self.loaded_dxf_floor == int(floor)) else None
        retained = (source is not None and source is getattr(self, '_rendered_dxf_source', None))
        drawing_items = getattr(self, '_rendered_dxf_items', []) if retained else []
        for item in drawing_items:
            self.scene.removeItem(item)
        self.scene.clear()
        for item in drawing_items:
            self.scene.addItem(item)
        self._rendered_dxf_source = source
        self._rendered_dxf_items = drawing_items
        self._item_lookup = {}
        self._point_item_lookup = {}
        self._map_colours = map_colours(self.appearance.value)
        self.canvas._map_style = self._map_colours
        self.canvas._show_map_grid = self.appearance.value.show_grid
        self.scene.setBackgroundBrush(QBrush(QColor(self._map_colours['background'])))
        self.canvas.setBackgroundBrush(QBrush(QColor(self._map_colours['background'])))
        rect = self._scene_rect_for_floor(floor, padding=8.0)
        if rect is not None:
            self.scene.setSceneRect(rect.adjusted(-40, -40, 40, 40))
        if self.show_pdf_check.isChecked():
            self.draw_pdf_underlay(floor)
        if (
            self._drawings_enabled
            and self.show_dxf_check.isChecked()
            and self.loaded_dxf_floor == int(floor)
            and self.dxf_scene.entities
        ):
            if not retained:
                self._rendered_dxf_items = self.dxf_scene.populate_graphics_scene(
                    self.scene, self.canvas.transform().m11()
                )
        if self.show_location_bounds_check.isChecked():
            self.draw_location_bounding_boxes(floor)
        self.draw_temporary_location_bounding_box(floor)
        self.draw_edges(floor)
        self.draw_route_access(floor)
        self.draw_points(floor)
        if self.show_charging_spaces_check.isChecked():
            self.draw_charging_space_markers(floor)
        self.file_label.setText(Path(self.current_json_path).name if self.current_json_path else "New project")
        self.file_label.setToolTip(self.current_json_path or 'Not saved')
        self.canvas.viewport().update()
        if update_panels and hasattr(self, 'workspace'):
            self.workspace.refresh()

    def draw_route_access(self, floor):
        from route_display import populate_choices, draw_access
        from cad_map_style import ContrastRouteStyles
        populate_choices(self.route_display_combo, self.store.data)
        selected = self.route_display_combo.currentData()
        self.route_preview_error = ''
        if selected is None:
            return
        try:
            points, sections, _rules = self.route_access_model()
            styles = ContrastRouteStyles(self.route_styles, self._map_colours['background'])
            items = draw_access(self.scene, points, sections, floor, selected, styles,
                                self.world_to_scene, self.appearance.value.map_font_size, self.route_labels_check.isChecked(),
                                label_background=self._map_colours['background'])
            for item, section in items:
                if section['source'] is not None:
                    self._item_lookup[item] = ('edge', section['source'])
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            self.route_preview_error = 'Profile preview unavailable: ' + str(exc)

    def draw_charging_space_markers(self, floor):
        """Overlay a compact charger count beside locations with charger-equipped AMR bays."""
        for location in self.store.locations_for_floor(floor):
            spaces = list(location.get("inventory_spaces", []) or [])
            chargers = [
                space for space in spaces
                if isinstance(space, dict)
                and inventory_space_is_amr(space)
                and bool(space.get("has_charger", False))
            ]
            if not chargers:
                continue
            point = self.world_to_scene(float(location.get("x", 0.0)), float(location.get("y", 0.0)))
            label = self.scene.addText(f"⚡ {len(chargers)}")
            label.setDefaultTextColor(QColor(self._map_colours['text']))
            label.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
            label.setPos(point.x() + 0.35, point.y() - 0.75)
            label.setZValue(40)

    def _edge_rows_for_point(self, point_name):
        points = self.store.all_points()
        results = []
        for edge in self.store.data.get("corridors", {}).get("edges", []):
            if edge.get("from") != point_name and edge.get("to") != point_name:
                continue
            from_name = edge.get("from", "")
            to_name = edge.get("to", "")
            from_point = points.get(from_name)
            to_point = points.get(to_name)
            from_floor = from_point.get("floor", "") if from_point else ""
            to_floor = to_point.get("floor", "") if to_point else ""
            results.append(
                {
                    "from": from_name,
                    "from_floor": from_floor,
                    "to": to_name,
                    "to_floor": to_floor,
                    "cross_floor": (
                        from_point is not None
                        and to_point is not None
                        and int(from_floor) != int(to_floor)
                    ),
                }
            )
        results.sort(
            key=lambda edge: (
                str(edge.get("from_floor", "")),
                str(edge.get("from", "")),
                str(edge.get("to_floor", "")),
                str(edge.get("to", "")),
            )
        )
        return results

    @undoable("Delete corridor links")
    def _delete_edge_connections(self, edges):
        removed = 0
        for edge in edges:
            before = len(self.store.data.get("corridors", {}).get("edges", []))
            self.store.remove_edge(edge.get("from", ""), edge.get("to", ""))
            after = len(self.store.data.get("corridors", {}).get("edges", []))
            if after < before:
                removed += 1
        self.refresh_canvas()
        self.set_status(f"Deleted {removed} edge connection(s)")

    def _show_edge_connections_dialog(self, point_name):
        dialog = EdgeConnectionsDialog(
            self,
            point_name,
            self._edge_rows_for_point(point_name),
            self._delete_edge_connections,
        )
        dialog.exec()

    def find_nearest_bounding_box_point_index(self, x, y, radius_world=0.6):
        if not self.bounding_box_location_name:
            return None

        best_index = None
        best_dist = radius_world

        for idx, point in enumerate(self.bounding_box_points):
            d = math.hypot(float(point["x"]) - x, float(point["y"]) - y)
            if d <= best_dist:
                best_index = idx
                best_dist = d

        return best_index

    def draw_location_bounding_boxes(self, floor):
        pen = QPen(QColor(self._map_colours['muted']), 1.5)
        pen.setCosmetic(True)
        fill = QColor(self._map_colours['panel'])
        fill.setAlpha(220)
        brush = QBrush(fill)
        for location in self.store.locations_for_floor(floor):
            points = self.store.get_location_bounding_box_points(location["name"]) or []
            if len(points) < 3:
                continue
            poly = QPolygonF([self.world_to_scene(p["x"], p["y"]) for p in points])
            item = QGraphicsPolygonItem(poly)
            item.setPen(pen)
            item.setBrush(brush)
            item.setZValue(-5)
            self.scene.addItem(item)
            self._item_lookup[item] = (
                "location_bounding_box",
                location.get("name", ""),
            )

    def draw_temporary_location_bounding_box(self, floor):
        if self._current_edit_mode() != "location_bbox":
            return
        if not self.bounding_box_location_name or not self.bounding_box_points:
            return
        location = self.store.get_location(self.bounding_box_location_name)
        if not location or int(location.get("floor", -1)) != int(floor):
            return

        pts = [self.world_to_scene(p["x"], p["y"]) for p in self.bounding_box_points]
        pen = QPen(QColor(self._map_colours['accent']), 0)
        pen.setStyle(Qt.DashLine)
        fill = QColor(self._map_colours['accent'])
        fill.setAlpha(35)
        brush = QBrush(fill) if len(pts) >= 3 else Qt.NoBrush

        # if len(pts) == 1:
        #     p = pts[0]
        #     self.scene.addEllipse(p.x() - 0.15, p.y() - 0.15, 0.3, 0.3, pen, QBrush(QColor("#ffdd57")))
        #     return

        poly = QPolygonF(pts)
        item = QGraphicsPolygonItem(poly)
        item.setPen(pen)
        item.setBrush(brush)
        item.setZValue(-4)
        self.scene.addItem(item)

        for idx, p in enumerate(pts):
            handle_pen = QPen(QColor(self._map_colours['text']), 0)
            handle_brush = QBrush(
                QColor(self._map_colours['lift'])
                if idx == self.dragging_bounding_box_point_index
                else QColor(self._map_colours['accent'])
            )
            handle = self.scene.addEllipse(
                p.x() - 0.18,
                p.y() - 0.18,
                0.36,
                0.36,
                handle_pen,
                handle_brush,
            )
            handle.setZValue(20)
            self._item_lookup[handle] = ("location_bounding_box_point", idx)

    def start_location_bounding_box_draw(self, location_name, keep_existing=False):
        location = self.store.get_location(location_name)
        if location is None:
            return
        self.bounding_box_location_name = location_name
        existing = self.store.get_location_bounding_box_points(location_name)
        self.bounding_box_points = [dict(p) for p in existing] if keep_existing else []
        self._set_edit_mode("location_bbox")
        self.show_location_bounds_check.setChecked(True)
        self.set_status(
            f"Drawing bounding box for {location_name}. Left-click points, right-click empty space to finish."
        )
        self.refresh_canvas()

    def start_location_rectangle(self, name):
        location = self.store.get_location(name)
        if location is None or int(location['floor']) != self.floor_spin.value():
            self.set_status('Choose a location on the active floor.')
            return False
        if not self._finish_property_draft():
            return False
        self._set_edit_mode('location_rectangle')
        self.bounding_box_location_name = None
        self.bounding_box_points = []
        location = self.store.get_location(name)
        self._rectangle_draft = dict(name=name, original=deepcopy(location), first=None, second=None)
        self.rectangle_input.dimensions.clear()
        self.rectangle_input.preview()
        self.rectangle_input.show()
        self.set_status(f'Rectangle for {name}: click the first corner, then the opposite corner. Escape cancels.')
        return True

    def preview_location_rectangle(self, sx, sy):
        draft = getattr(self, '_rectangle_draft', None)
        if hasattr(self, 'rectangle_input') and self.rectangle_input.dimensions.text().strip():
            return
        if draft and draft['first'] is not None:
            draft['second'] = self.snap(*self.scene_to_world(sx, sy))
            self.canvas.viewport().update()

    @undoable('Draw rectangular location boundary')
    def place_location_rectangle_corner(self, x, y):
        draft = getattr(self, '_rectangle_draft', None)
        if not draft:
            name = self.find_nearest_point_name(x, y, self.floor_spin.value(), radius_world=.45)
            return self.start_location_rectangle(name) if name else False
        if self.rectangle_input.dimensions.text().strip():
            self.set_status('Apply the typed dimensions, or clear them to draw by corners.')
            return False
        if self.store.get_location(draft['name']) != draft['original']:
            self._rectangle_draft = None
            self.rectangle_input.hide()
            self.set_status('Location changed while drawing; start the rectangle again.')
            self.canvas.viewport().update()
            return False
        x, y = self.snap(x, y)
        if draft['first'] is None:
            draft['first'] = draft['second'] = (x, y)
            self.set_status('Click the opposite corner to apply the rectangle. Escape cancels.')
            self.canvas.viewport().update()
            return True
        from visualiser.location_drawing import rectangle_points
        try:
            points = rectangle_points(draft['first'], (x, y))
        except (ValueError, TypeError) as exc:
            self.set_status(f'Rectangle was not applied: {exc}')
            return False
        return self.apply_location_rectangle(points)

    @undoable('Draw rectangular location boundary')
    def apply_location_rectangle(self, points):
        draft = getattr(self, '_rectangle_draft', None)
        if not draft or self.workspace.stage != 'layout' or self._current_edit_mode() != 'location_rectangle':
            return False
        if self.store.get_location(draft['name']) != draft['original']:
            self.set_status('Location changed; cancel and select it again.')
            return False
        try:
            self.store.set_location_bounding_box(draft['name'], points)
        except (ValueError, TypeError) as exc:
            self.set_status(f'Rectangle was not applied: {exc}')
            return False
        name = draft['name']
        self._rectangle_draft = None
        self.show_location_bounds_check.setChecked(True)
        self._set_edit_mode('select_move')
        self.refresh_canvas()
        self.set_status(f'Saved rectangular boundary for {name}. Undo restores the previous boundary.')
        return True

    @undoable("Edit location boundary")
    def finish_location_bounding_box_draw(self):
        name = self.bounding_box_location_name
        if not name:
            return
        if len(self.bounding_box_points) < 3:
            QMessageBox.critical(
                self,
                "Bounding box",
                "Add at least three points for a room bounding box.",
            )
            return
        self.store.set_location_bounding_box(name, self.bounding_box_points)
        self.bounding_box_location_name = None
        self.bounding_box_points = []
        self._set_edit_mode("select_move")
        self.set_status(f"Saved bounding box for {name}")
        self.refresh_canvas()

    def cancel_location_bounding_box_draw(self):
        name = self.bounding_box_location_name
        self.bounding_box_location_name = None
        self.bounding_box_points = []
        self.set_status(
            f"Cancelled bounding box drawing for {name}"
            if name
            else "Bounding box drawing cancelled"
        )
        self.refresh_canvas()

    def draw_edges(self, floor):
        points = self.store.all_points()
        colour_by_area = {key: QColor(self._map_colours[key]) for key in ('none','staff','public','both')}
        pen_cross_floor = QPen(QColor(self._map_colours['lift']), 0)
        for edge in self.store.data.get("corridors", {}).get("edges", []):
            a = points.get(edge["from"])
            b = points.get(edge["to"])
            if not a or not b:
                continue
            a_floor = int(a["floor"])
            b_floor = int(b["floor"])
            if int(floor) not in {a_floor, b_floor}:
                continue
            pa = self.world_to_scene(a["x"], a["y"])
            pb = self.world_to_scene(b["x"], b["y"])
            key = self._physical_edge_key(edge.get("from"), edge.get("to"))
            if key in self.selected_edge_keys:
                pen = QPen(QColor(self._map_colours['accent']), 3)
                pen.setCosmetic(True)
            elif a_floor != b_floor:
                pen = pen_cross_floor
            else:
                area = str(edge.get("people_area_type", "none") or "none").lower()
                colour = QColor(self._map_colours['muted']) if self.route_display_combo.currentData() is not None else colour_by_area.get(area, colour_by_area['none'])
                pen = QPen(colour, 1.5)
                pen.setCosmetic(True)
            item = self.scene.addLine(pa.x(), pa.y(), pb.x(), pb.y(), pen)
            item.setZValue(5 if key in self.selected_edge_keys else 0)
            self._item_lookup[item] = ("edge", edge)
            if not edge.get('bidirectional', True) and pa != pb:
                arrow = QGraphicsPolygonItem(QPolygonF([QPointF(5, 0), QPointF(-5, -4), QPointF(-5, 4)]))
                arrow.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
                arrow.setPos((pa + pb) / 2)
                arrow.setRotation(math.degrees(math.atan2(pb.y() - pa.y(), pb.x() - pa.x())))
                arrow.setPen(QPen(pen.color(), 1))
                arrow.setBrush(QBrush(pen.color()))
                arrow.setZValue(6)
                self.scene.addItem(arrow)
                self._item_lookup[arrow] = ('edge', edge)

    def draw_points(self, floor):
        label_mode = self.object_label_mode.currentData()
        selected_names = set(self.selected_point_names)
        selected_names.add(self.selected_point_name)
        selected_names.update(name for key in self.selected_edge_keys for name in key)
        if self.route_profile_selection_active:
            selected_names.update(self.route_profile_selected_nodes)
        self._point_name_labels = {}
        for name, point in self.store.points_for_floor(floor).items():
            pos = self.world_to_scene(point["x"], point["y"])
            selected = name in self.selected_point_names or name == self.selected_point_name
            route_selected = (
                self.route_profile_selection_active
                and name in self.route_profile_selected_nodes
            )
            route_allowed = (
                not self.route_profile_selection_active
                or name in self.route_profile_allowed_point_names
            )
            kind = point.get("kind")
            outline = QPen(
                (
                    QColor(self._map_colours['accent'])
                    if route_selected or selected
                    else QColor("transparent")
                ),
                0.12 if selected else 0,
            )
            if kind == "location":
                r = 0.3
                item = self.scene.addEllipse(
                    pos.x() - r,
                    pos.y() - r,
                    2 * r,
                    2 * r,
                    outline,
                    QBrush(QColor(self._map_colours['location'])),
                )
                label_color = QColor("#9bf0cd")
            elif kind == "corridor_node":
                r = 0.3
                has_door = bool(point.get("has_door", False))
                item = self.scene.addRect(
                    pos.x() - r,
                    pos.y() - r,
                    2 * r,
                    2 * r,
                    outline,
                    QBrush(QColor(self._map_colours['door' if has_door else 'node'])),
                )
                label_color = QColor("#ffd180") if has_door else QColor("#ffe8a3")
                if has_door:
                    door_text = QGraphicsSimpleTextItem("D")
                    door_text.setBrush(QBrush(QColor(self._map_colours['text'])))
                    door_text.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
                    door_text.setPos(pos.x() - 0.12, pos.y() - 0.55)
                    door_text.setZValue(35)
                    self.scene.addItem(door_text)
                    self._item_lookup[door_text] = ("point_label", name)
            elif kind == "department":
                poly = QPolygonF(
                    [
                        QPointF(pos.x(), pos.y() - 0.9),
                        QPointF(pos.x() + 0.9, pos.y()),
                        QPointF(pos.x(), pos.y() + 0.9),
                        QPointF(pos.x() - 0.9, pos.y()),
                    ]
                )
                item = QGraphicsPolygonItem(poly)
                item.setBrush(QBrush(QColor(self._map_colours['department'])))
                item.setPen(outline if selected else QPen(QColor(self._map_colours['department']), 0.08))
                self.scene.addItem(item)
                label_color = QColor("#bff7f2")
            else:
                r = 0.3
                poly = [
                    QPointF(pos.x(), pos.y() - r),
                    QPointF(pos.x() + r, pos.y()),
                    QPointF(pos.x(), pos.y() + r),
                    QPointF(pos.x() - r, pos.y()),
                ]
                item = QGraphicsPolygonItem()
                item.setPolygon(QPolygonF(poly))
                item.setPen(outline)
                item.setBrush(QBrush(QColor(self._map_colours['lift'])))
                self.scene.addItem(item)
                label_color = QColor("#ffb3ae")
            if not route_allowed:
                item.setOpacity(0.3)
            item.setFlag(QGraphicsItem.ItemIgnoresTransformations, False)
            item.setZValue(30 if route_selected or selected else 10)
            self._item_lookup[item] = ("point", name)
            self._point_item_lookup[name] = item
            show_name = (label_mode == 'all' or name in selected_names or
                         (label_mode == 'key' and (kind != 'corridor_node' or point.get('has_door'))))
            if self.show_labels_check.isChecked() and show_name:
                label = name
                if kind == 'corridor_node' and point.get('has_door') and point.get('door_clear_width_m') is not None:
                    label += f" · {point['door_clear_width_m']} m"
                text = QGraphicsSimpleTextItem(label)
                text.setBrush(QColor(self._map_colours['text']))
                font = QFont(QApplication.font())
                font.setPixelSize(self.appearance.value.map_font_size)
                text.setFont(font)
                text.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
                text.setPos(pos.x() + 0.5, pos.y())
                self.scene.addItem(text)
                self._item_lookup[text] = ("point_label", name)
                self._point_name_labels[name] = text

    def draw_overlay_panels(self, painter, viewport_rect):
        draft = getattr(self, '_rectangle_draft', None)
        if draft and draft.get('numeric_points'):
            polygon = QPolygonF([QPointF(self.canvas.mapFromScene(self.world_to_scene(p['x'],p['y'])))
                                 for p in draft['numeric_points']])
            painter.setPen(QPen(QColor(self._map_colours['accent']), 2, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawPolygon(polygon)
        elif draft and draft['first'] is not None and draft['second'] is not None:
            first, second = draft['first'], draft['second']
            a = self.canvas.mapFromScene(self.world_to_scene(*first))
            b = self.canvas.mapFromScene(self.world_to_scene(*second))
            painter.setPen(QPen(QColor(self._map_colours['accent']), 2, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(QRectF(QPointF(a), QPointF(b)).normalized())
            painter.drawText(b + QPoint(12,-12), f'{abs(second[0]-first[0]):.6g} × {abs(second[1]-first[1]):.6g} m')
        target = self.corridor_draw_preview
        if self._current_edit_mode() == 'corridor_draw' and target:
            endpoint = self.canvas.mapFromScene(self.world_to_scene(target['x'], target['y']))
            start = self.store.all_points().get(self.corridor_draw_start)
            painter.setPen(QPen(QColor(self._map_colours['accent']), 2, Qt.DashLine))
            if start:
                origin = self.canvas.mapFromScene(self.world_to_scene(start['x'], start['y']))
                painter.drawLine(origin, endpoint)
            painter.drawEllipse(endpoint, 7, 7)
            label = {'point': 'Reuse point', 'edge': 'Join corridor', 'junction': 'Connect intersection', 'new': 'Place node'}[target['kind']]
            painter.drawText(endpoint + QPoint(12, -12), label)
        from cad_map_style import compact_legend, scale_bar
        style = self._map_colours
        font = QFont(QApplication.font())
        font.setPixelSize(self.appearance.value.map_font_size)
        metrics = QFontMetrics(font)
        self.canvas.setToolTip('')
        if self.appearance.value.show_legend:
            profile = self.route_display_combo.currentText() if self.route_display_combo.currentData() is not None else None
            lines = compact_legend(profile)
            width = min(300, max(160, viewport_rect.width()//3))
            height = 16 + len(lines)*(metrics.height()+4)
            self._draw_overlay_box(painter, max(12,viewport_rect.width()-width-12),
                max(12,viewport_rect.height()-height-12), width, lines, style['border'], style['text'])
        # Errors are independent of the optional key and stay visible at the top.
        if self.route_preview_error:
            self._draw_overlay_box(painter,12,12,min(600,viewport_rect.width()-24),
                ['Map preview error',self.route_preview_error],style['lift'],style['text'])
        scale = math.hypot(self.canvas.transform().m11(),self.canvas.transform().m12())
        bar = scale_bar(scale)
        if bar and viewport_rect.width() >= 360 and viewport_rect.height() >= 120:
            metres, pixels = bar
            painter.save()
            painter.setFont(font)
            painter.setPen(QPen(QColor(style['text']),1.5))
            painter.setBrush(QBrush(QColor(style['panel'])))
            x,y = 22,viewport_rect.height()-25
            painter.drawRoundedRect(QRectF(x-10,y-metrics.height()-38,max(155,pixels+25),metrics.height()+55),4,4)
            painter.drawLine(QPointF(x,y),QPointF(x+pixels,y))
            painter.drawLine(QPointF(x,y-4),QPointF(x,y+4))
            painter.drawLine(QPointF(x+pixels,y-4),QPointF(x+pixels,y+4))
            painter.drawText(QPointF(x,y-8),f'{metres:g} m')
            # +Y is the model axis, not an assumed geographic north orientation.
            transform = self.canvas.transform()
            vector = transform.map(QPointF(0,-1))-transform.map(QPointF(0,0))
            magnitude = math.hypot(vector.x(),vector.y())
            if magnitude:
                origin = QPointF(x+10,y-metrics.height()-15)
                tip = origin + vector*(12/magnitude)
                painter.drawLine(origin,tip)
                painter.drawEllipse(tip,2,2)
                painter.drawText(QPointF(x+28,y-metrics.height()-17),'+Y (model)')
            painter.restore()

    def _draw_overlay_box(self, painter, x, y, w, lines, border_color, title_color):
        margin_x = 10
        margin_y = 8
        painter.save()
        font = QFont(QApplication.font())
        font.setPixelSize(self.appearance.value.map_font_size)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        line_h = metrics.height() + 4
        # Keep the legend inside the viewport at large text sizes. Truncation is
        # explicit; the complete legend remains available in the canvas tooltip.
        available_w = max(40, self.canvas.viewport().width() - x - 12)
        w = min(available_w, w)
        count = max(1, (self.canvas.viewport().height() - y - 12 - 2 * margin_y) // line_h)
        shown = lines[:count]
        if len(lines) > count:
            shown[-1] = '… Full legend: hover over map'
        self.canvas.setToolTip('\n'.join(filter(None, [self.canvas.toolTip(), '\n'.join(lines)])))
        box_h = (margin_y * 2) + (len(shown) * line_h)
        painter.setPen(QPen(QColor(border_color), 1))
        painter.setBrush(QBrush(QColor(self._map_colours['panel'])))
        painter.drawRoundedRect(QRect(x, y, w, box_h),4,4)

        for i, line in enumerate(shown):
            painter.setPen(QColor(title_color))
            painter.drawText(x + margin_x, y + margin_y + metrics.ascent() + (i * line_h),
                             metrics.elidedText(line, Qt.ElideRight, max(1, w - 2 * margin_x)))

        painter.restore()

    def find_nearest_point_name(self, x, y, floor, radius_world=3.0):
        best = None
        best_dist = radius_world
        for name, point in self.store.points_for_floor(floor).items():
            d = math.hypot(point["x"] - x, point["y"] - y)
            if d <= best_dist:
                best = name
                best_dist = d
        return best

    def _item_at_scene(self, sx, sy):
        return self.canvas.itemAt(self.canvas.mapFromScene(QPointF(sx, sy)))

    @undoable("Edit department locations")
    def create_department_at_point(self, point_name):
        point = self.store.all_points().get(point_name)
        if not point:
            return

        location_names = sorted(x["name"] for x in self.store.data.get("locations", []))
        waste_stream_names = sorted(
            x["name"] for x in self.store.data.get("waste_streams", [])
        )

        dialog = DepartmentEditorDialog(
            self,
            location_names=location_names,
            waste_stream_names=waste_stream_names,
            current_floor=self.floor_spin.value(),
            default_department_id=self.store.suggest_next_department_id(),
            default_x=point["x"],
            default_y=point["y"],
            group_resolver=lambda item: f"Floor {self.build_floor_map(self.store.data).get(item, 'Other')}",
            task_generation_categories=self.task_generation_category_pairs(),
            existing_dropoff_zone_names=self.department_dropoff_zone_names(),
        )
        if dialog.exec() == QDialog.Accepted and dialog.result:
            if dialog.result["name"] in self.store.names_in_use():
                QMessageBox.critical(
                    self, "Duplicate name", "Department name already exists"
                )
                return
            if not self._commit_department_edit(dialog.result):
                return
            self.set_status(f"Added department {dialog.result['name']}")
            self.refresh_canvas()

    @undoable("Edit department locations")
    def create_department_at_position(self, x, y, floor):
        location_names = sorted(x["name"] for x in self.store.data.get("locations", []))
        waste_stream_names = sorted(
            x["name"] for x in self.store.data.get("waste_streams", [])
        )

        dialog = DepartmentEditorDialog(
            self,
            location_names=location_names,
            waste_stream_names=waste_stream_names,
            current_floor=floor,
            default_department_id=self.store.suggest_next_department_id(),
            default_x=x,
            default_y=y,
            group_resolver=lambda item: f"Floor {self.build_floor_map(self.store.data).get(item, 'Other')}",
            task_generation_categories=self.task_generation_category_pairs(),
            existing_dropoff_zone_names=self.department_dropoff_zone_names(),
        )
        if dialog.exec() == QDialog.Accepted and dialog.result:
            dept_name = str(dialog.result.get("name", "")).strip()
            if dept_name in self.store.names_in_use():
                QMessageBox.critical(
                    self, "Duplicate name", "Department name already exists"
                )
                return
            if not self._commit_department_edit(dialog.result):
                return
            self.selected_point_name = dept_name
            self.set_status(f"Added department {dept_name}")
            self.refresh_canvas()

    @undoable("Edit department locations")
    def edit_department_by_name(self, dept_name):
        dept = next(
            (
                x
                for x in self.store.data.get("departments", [])
                if str(x.get("name", "")).strip() == str(dept_name).strip()
            ),
            None,
        )
        if not dept:
            return

        location_names = sorted(x["name"] for x in self.store.data.get("locations", []))
        waste_stream_names = sorted(
            x["name"] for x in self.store.data.get("waste_streams", [])
        )

        dialog = DepartmentEditorDialog(
            self,
            location_names=location_names,
            waste_stream_names=waste_stream_names,
            current_floor=self.floor_spin.value(),
            seed=dept,
            default_department_id=str(dept.get("id", "")),
            default_x=float(dept.get("x", 0.0)),
            default_y=float(dept.get("y", 0.0)),
            group_resolver=lambda item: f"Floor {self.build_floor_map(self.store.data).get(item, 'Other')}",
            task_generation_categories=self.task_generation_category_pairs(),
            existing_dropoff_zone_names=self.department_dropoff_zone_names(),
        )
        if dialog.exec() == QDialog.Accepted and dialog.result:
            for other in self.store.data.get("departments", []):
                if other is dept:
                    continue
                if (
                    str(other.get("id", "")).strip()
                    == str(dialog.result.get("id", "")).strip()
                ):
                    QMessageBox.critical(
                        self, "Duplicate", "Department ID already exists"
                    )
                    return
                if (
                    str(other.get("name", "")).strip()
                    == str(dialog.result.get("name", "")).strip()
                ):
                    QMessageBox.critical(
                        self, "Duplicate", "Department name already exists"
                    )
                    return

            old_name = str(dept.get("name", "")).strip()
            new_name = str(dialog.result.get("name", "")).strip()

            from amr_department_inputs import department_identity
            if not self._commit_department_edit(dialog.result, previous_id=department_identity(dept)):
                return
            self.selected_point_name = new_name

            self.set_status(f"Edited department {new_name}")
            self.refresh_canvas()

    def _commit_department_edit(self, result, *, previous_id=None):
        from amr_department_inputs import department_identity
        before = deepcopy(self.store.data)
        proposed = deepcopy(result)
        try:
            if previous_id is None and any(department_identity(row) == department_identity(proposed)
                    for row in before.get('departments', [])):
                raise ValueError('Department ID already exists.')
            occupied_names = {p['name'] for p in before.get('locations', [])}
            occupied_names.update(p['name'] for p in before.get('corridors', {}).get('nodes', []))
            for lift in before.get('lifts', []):
                occupied_names.update(f"{lift['id']}-F{floor}" for floor in lift.get('floor_locations', {}))
            if proposed.get('name') in occupied_names:
                raise ValueError('Department name conflicts with a graph location or corridor node.')
            self.store.upsert_department(proposed, previous_id=previous_id)
        except ValueError as exc:
            self.store.data = before
            QMessageBox.critical(self, 'Invalid department', str(exc))
            return False
        return True

    @undoable("Edit layout")
    def on_left_click(self, event, sx, sy):
        if hasattr(self, 'workspace'):
            self.workspace.selected_edge_record = None
            self.workspace.selected_configuration = None
        mode = self._current_edit_mode()
        floor = self.floor_spin.value()
        raw_x, raw_y = self.scene_to_world(sx, sy)
        x, y = self.snap(raw_x, raw_y)

        if mode == 'location_rectangle':
            self.place_location_rectangle_corner(raw_x, raw_y)
            return

        if self.department_location_placement_active:
            self.finish_department_location_placement(x, y, floor)
            return

        if self.route_profile_selection_active:
            picked = self._route_profile_pickable_point_at(raw_x, raw_y, floor)

            if picked:
                if not (event.modifiers() & Qt.ControlModifier):
                    self.route_profile_selected_nodes.clear()

                if picked in self.route_profile_selected_nodes:
                    self.route_profile_selected_nodes.remove(picked)
                else:
                    self.route_profile_selected_nodes.add(picked)

                self.set_status(
                    f"Route profile selection: {len(self.route_profile_selected_nodes)} node(s)"
                )
                self.refresh_canvas()

            return

        if mode == "pan":
            self.last_pan = event.position().toPoint()
            return
        if mode == "pdf_underlay_align":
            return

        if mode == 'corridor_draw':
            self.draw_next_corridor(raw_x, raw_y)
            return

        if mode == 'door':
            from corridor_editing import draw_step
            try:
                # Reuse the corridor drawing transaction so splitting preserves
                # directed attributes and all profile/resource references.
                updated, target = draw_step(
                    self.store.data, self.store.all_points(), None, floor,
                    raw_x, raw_y, snap=self.snap_check.isChecked(),
                    grid_spacing=self.grid_spacing_spin.value(), object_snap=self.object_snap_check.isChecked(), snap_mode=self.object_snap_mode.currentData())
                node = next((node for node in updated['corridors']['nodes']
                             if node['name'] == target['name']), None)
                if node is None:
                    raise ValueError('Place a door on a corridor node or link, not a location or lift.')
                width = node.get('door_clear_width_m')
                if width is None:
                    width = float(updated.get('building', {}).get('default_door_clear_width_m', .9) or .9)
                if isinstance(width, bool) or not math.isfinite(float(width)) or float(width) <= 0:
                    raise ValueError('Set a positive finite door clear width before placing this door.')
                node['has_door'] = True
                node['door_clear_width_m'] = width
            except (ValueError, TypeError, KeyError) as exc:
                self.set_status(f'Door was not placed: {exc}')
                return
            self.store.data = updated
            self.selected_point_name = target['name']
            self.selected_point_names = {target['name']}
            self.selected_edge_keys.clear()
            self.set_status(f"Door {target['name']}: clear width {float(width):g} m. Edit width in Properties.")
            self.refresh_canvas()
            return

        # Insertion needs a precise endpoint hit; the broad selection radius
        # otherwise consumes every click on corridors shorter than six metres.
        if mode == 'select_move':
            from cad_selection import editor_paths, point_hit
            viewport_point = QPointF(self.canvas.mapFromScene(QPointF(sx, sy)))
            hit = point_hit(editor_paths(self), viewport_point)
            picked = hit[1] if hit and hit[0] == 'point' else None
            picked_edge = hit[1] if hit and hit[0] == 'edge' else None
        else:
            picked = self.find_nearest_point_name(raw_x, raw_y, floor, radius_world=0.45 if mode == "corridor_node" else 3.0)
            picked_edge = None if picked else self.find_nearest_edge_key(raw_x, raw_y, floor)

        if mode == "select_move":
            self._ensure_cad_selection_connections()
            additive = bool(
                event.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier)
            )
            self.dragging_point_name = None
            self.drag_mode_active = False
            self._cad_drag_offset = None
            if picked is None and picked_edge is None:
                self._begin_cad_selection(event, viewport_point)
            if picked:
                if not additive and picked not in self.selected_point_names:
                    self.selected_point_names.clear()
                    self.selected_edge_keys.clear()
                if additive and picked in self.selected_point_names:
                    self.selected_point_names.remove(picked)
                    self.selected_point_name = None
                else:
                    self.selected_point_names.add(picked)
                    self.selected_point_name = picked
                    if not additive:
                        self._begin_point_drag(picked, raw_x, raw_y)
                self.set_status(
                    f"Selected {len(self.selected_point_names)} node(s) and "
                    f"{len(self.selected_edge_keys)} corridor(s)"
                )
            elif picked_edge is not None:
                if not additive and picked_edge not in self.selected_edge_keys:
                    self.selected_point_names.clear()
                    self.selected_edge_keys.clear()
                    self.selected_point_name = None
                if additive and picked_edge in self.selected_edge_keys:
                    self.selected_edge_keys.remove(picked_edge)
                else:
                    self.selected_edge_keys.add(picked_edge)
                    if not additive:
                        self._begin_point_drag(picked_edge[0], raw_x, raw_y)
                self.set_status(
                    f"Selected {len(self.selected_point_names)} node(s) and "
                    f"{len(self.selected_edge_keys)} corridor(s)"
                )
            elif not additive:
                self.selected_point_names.clear()
                self.selected_edge_keys.clear()
                self.selected_point_name = None
                self.set_status("Selection cleared")
            self.refresh_canvas()
            return

        self.selected_point_name = picked

        if mode == "delete":
            if picked:
                if picked.startswith("Lift-") and "-F" in picked:
                    lift_id = picked.rsplit("-F", 1)[0]
                    if (
                        QMessageBox.question(
                            self, "Delete lift", f"Delete entire {lift_id}?"
                        )
                        == QMessageBox.Yes
                    ):
                        self.store.delete_lift(lift_id)
                        self.selected_point_name = None
                        self.set_status(f"Deleted {lift_id}")
                else:
                    if (
                        QMessageBox.question(self, "Delete point", f"Delete {picked}?")
                        == QMessageBox.Yes
                    ):
                        cleanup = self.store.delete_point(picked)
                        self.selected_point_name = None
                        removed_refs = 0
                        if isinstance(cleanup, dict):
                            removed_refs = sum(
                                int(cleanup.get(key, 0) or 0)
                                for key in (
                                    "department_references_removed",
                                    "task_generation_references_removed",
                                    "building_references_removed",
                                    "mass_collection_references_removed",
                                )
                            )
                        suffix = (
                            f" and removed {removed_refs} redundant reference(s)"
                            if removed_refs
                            else ""
                        )
                        self.set_status(f"Deleted {picked}{suffix}")
                self.refresh_canvas()
            return

        if mode == "corridor_node":
            from corridor_editing import draw_step
            try:
                updated, target = draw_step(self.store.data, self.store.all_points(), None, floor,
                    raw_x, raw_y, snap=self.snap_check.isChecked(),
                    grid_spacing=self.grid_spacing_spin.value(), object_snap=self.object_snap_check.isChecked(), snap_mode=self.object_snap_mode.currentData())
            except (ValueError, KeyError, TypeError) as exc:
                self.set_status(f'Node was not changed: {exc}')
                return
            self.store.data = updated
            self.selected_point_name = target['name']
            self.set_status(f"{'Using existing point' if target['kind'] == 'point' else 'Added corridor node'} {target['name']}")
            self.refresh_canvas()
            return

        if mode == "location":
            name, ok = QInputDialog.getText(self, "Location", "Location name:")
            if not ok or not name:
                return
            self.store.add_location(name, floor, x, y)
            self.set_status(f"Added location {name}")
            self.refresh_canvas()
            return

        if mode == "location_bbox":
            if not self.bounding_box_location_name:
                if picked:
                    picked_point = self.store.all_points().get(picked, {})
                    if picked_point.get("kind") == "location":
                        self.start_location_bounding_box_draw(
                            picked, keep_existing=False
                        )
                    else:
                        self.set_status("Pick a location before drawing a bounding box")
                else:
                    self.set_status(
                        "Right-click a location and choose draw bounding box, or left-click a location first"
                    )
                return

            location = self.store.get_location(self.bounding_box_location_name)
            if not location or int(location.get("floor", -1)) != int(floor):
                self.set_status("Bounding box location is not on the current floor")
                return

            hit_index = self.find_nearest_bounding_box_point_index(x, y)
            if hit_index is not None:
                self.dragging_bounding_box_point_index = hit_index
                self.set_status(
                    f"Dragging bounding box point {hit_index + 1} for {self.bounding_box_location_name}"
                )
                self.refresh_canvas()
                return

            self.bounding_box_points.append({"x": x, "y": y})
            self.set_status(
                f"Added point {len(self.bounding_box_points)} for {self.bounding_box_location_name}"
            )
            self.refresh_canvas()
            return

        if mode == "department":
            existing = self.find_nearest_point_name(x, y, floor)
            if existing:
                point = self.store.all_points().get(existing, {})
                if point.get("kind") == "department":
                    self.edit_department_by_name(existing)
                    return

            self.create_department_at_position(x, y, floor)
            return

        if mode == "edge":
            if not picked:
                self.set_status("No nearby point found")
                return

            picked_point = self.store.all_points().get(picked, {})
            if picked_point.get("kind") == "department":
                self.set_status("Departments cannot be connected by corridor edges")
                return

            if self.selected_for_edge is None:
                self.selected_for_edge = picked
                self.set_status(f"Edge start selected: {picked}")
            else:
                start_point = self.store.all_points().get(self.selected_for_edge, {})
                if start_point.get("kind") == "department":
                    self.set_status("Departments cannot be connected by corridor edges")
                    self.selected_for_edge = None
                    return

                start = self.selected_for_edge

                try:
                    created = self.store.connect_corridor(start, picked, self.bidirectional_check.isChecked())
                except (ValueError, TypeError, KeyError) as exc:
                    self.set_status(f'Corridor was not changed: {exc}')
                    return

                if self.chain_edges_check.isChecked():
                    self.selected_for_edge = picked
                    self.set_status(
                        f"{'Connected' if created else 'Reused existing corridor'} {start} -> {picked}. Chain start now: {picked}"
                    )
                else:
                    self.selected_for_edge = None
                    self.set_status(f"{'Connected' if created else 'Reused existing corridor'} {start} -> {picked}")

                self.refresh_canvas()

        if mode == "lift":
            existing_lift = None
            if picked and picked.startswith("Lift-") and "-F" in picked:
                lift_id = picked.rsplit("-F", 1)[0]
                for item in self.store.data.get("lifts", []):
                    if item["id"] == lift_id:
                        existing_lift = item
                        break
            dialog = LiftEditorDialog(
                self, existing_lift, default_floor=floor, default_x=x, default_y=y
            )
            if dialog.exec() == QDialog.Accepted and dialog.result:
                self._save_lift_result(dialog.result, old_id=existing_lift.get("id") if existing_lift else None)
                self.set_status(f"Saved {dialog.result['id']}")
                self.refresh_canvas()
            return

    @undoable("Edit layout")
    def on_double_click(self, event, sx, sy):
        if self._current_edit_mode() == 'corridor_draw':
            self.finish_corridor_drawing()
            return
        floor = self.floor_spin.value()
        x, y = self.scene_to_world(sx, sy)
        picked = self.find_nearest_point_name(x, y, floor)
        if not picked:
            return
        point = self.store.all_points()[picked]
        if point.get("kind") == "lift_node":
            lift_id = point["lift_id"]
            existing_lift = next(
                (x for x in self.store.data.get("lifts", []) if x["id"] == lift_id),
                None,
            )
            dialog = LiftEditorDialog(
                self,
                existing_lift,
                default_floor=floor,
                default_x=point["x"],
                default_y=point["y"],
            )
            if dialog.exec() == QDialog.Accepted and dialog.result:
                self._save_lift_result(dialog.result, old_id=existing_lift.get("id") if existing_lift else None)
                self.set_status(f"Edited {dialog.result['id']}")
                self.refresh_canvas()
            return
        if point.get("kind") == "department":
            self.edit_department_by_name(picked)
            return
        dialog = PointEditorDialog(self, f"Edit {picked}", picked, point)
        if dialog.exec() == QDialog.Accepted and dialog.result:
            self.store.set_point_position(
                picked, dialog.result["x"], dialog.result["y"]
            )
            if point.get("kind") == "location":
                location = self.store.get_location(picked)
                if location is not None:
                    for key in ("wash_cycle_required", "wash_cycle_duration_sec", "wash_location", "people_area_type"):
                        if key in dialog.result:
                            location[key] = dialog.result[key]
            elif point.get("kind") == "corridor_node":
                for node in self.store.data.get("corridors", {}).get("nodes", []):
                    if node.get("name") == picked:
                        for key in ("has_door", "door_clear_width_m"):
                            if key in dialog.result:
                                node[key] = dialog.result[key]
                        break
            self.store.rename_point(picked, dialog.result["name"])
            if picked in self.selected_point_names:
                self.selected_point_names.remove(picked)
                self.selected_point_names.add(dialog.result["name"])
            self.selected_point_name = dialog.result["name"]
            self.set_status(f"Edited {dialog.result['name']}")
            self.refresh_canvas()

    def _begin_cad_selection(self, event, position):
        self.cancel_cad_selection()
        self._cad_selection_gesture = dict(start=QPointF(position), end=QPointF(position),
            points=set(self.selected_point_names), edges=set(self.selected_edge_keys),
            primary=self.selected_point_name, active=False,
            toggle=bool(event.modifiers() & (Qt.ShiftModifier | Qt.ControlModifier)))
        self._ensure_cad_selection_connections()

    def _ensure_cad_selection_connections(self):
        if not getattr(self, '_cad_selection_signals_connected', False):
            self.floor_spin.valueChanged.connect(self._cancel_cad_transients)
            self.mode_combo.currentIndexChanged.connect(self._cancel_cad_transients)
            self._cad_selection_signals_connected = True

    def _cancel_cad_transients(self, *_):
        self.cancel_cad_drag()
        self.cancel_cad_selection()
        self._cad_drag_offset = None
        self.dragging_point_name = None
        self.drag_mode_active = False

    def _begin_point_drag(self, anchor, raw_x, raw_y):
        if not self._project_editing_allowed():
            return False
        points = self.store.all_points()
        selected = self.selection_move_points()
        selected[anchor] = points[anchor]
        self._cad_drag_origins = {name: (point['x'], point['y']) for name, point in selected.items()}
        self.dragging_point_name = anchor
        self.drag_mode_active = True
        point = points[anchor]
        self._cad_drag_offset = (raw_x - float(point['x']), raw_y - float(point['y']))

    def selection_move_points(self):
        points = self.store.all_points()
        names = set(self.selected_point_names)
        for edge in self.selected_edge_keys:
            names.update(edge)
        floor = self.floor_spin.value()
        return {name: points[name] for name in names if name in points and int(points[name]['floor']) == floor}

    def show_selection_move(self):
        if self.workspace.stage != 'layout' or self._current_edit_mode() != 'select_move' or self.drag_mode_active:
            return
        self.cad_move_input.refresh_preview()
        self.cad_move_input.show()
        self.cad_move_input.offset.setFocus()

    @undoable('Move selected objects by displacement')
    def move_selected_by(self, dx, dy):
        if (self.workspace.stage != 'layout' or self._current_edit_mode() != 'select_move'
                or self.drag_mode_active or self.route_profile_selection_active
                or self.department_location_placement_active):
            return False
        if not all(math.isfinite(v) for v in (dx, dy)):
            raise ValueError('Displacement must contain finite numbers.')
        if (dx, dy) == (0, 0) or not self._finish_property_draft():
            return False
        points = self.selection_move_points()
        if not points:
            return False
        staged = deepcopy(self.store)
        for name, point in points.items():
            x, y = float(point['x']) + dx, float(point['y']) + dy
            if not all(math.isfinite(v) for v in (x, y)):
                raise ValueError('The resulting coordinates must be finite.')
            staged.set_point_position(name, x, y, exact=True)
        self.store.data = staged.data
        self.refresh_canvas()
        self.set_status(f'Moved {len(points)} selected points by X {dx:+g}, Y {dy:+g} m.')
        return True

    def cancel_cad_drag(self):
        origins = getattr(self, '_cad_drag_origins', None)
        if not origins:
            return False
        for name, (x, y) in origins.items():
            self.store.set_point_position(name, x, y, exact=True)
        self._cad_drag_origins = None
        self._cad_drag_offset = None
        self.dragging_point_name = None
        self.drag_mode_active = False
        self._drag_refresh_timer.stop()
        self.refresh_canvas()
        self.set_status('Move cancelled; selected objects restored.')
        return True

    def cancel_cad_selection(self, *_):
        gesture = getattr(self, '_cad_selection_gesture', None)
        if gesture is None:
            return False
        self._cad_selection_gesture = None
        self.selected_point_names = set(gesture['points'])
        self.selected_edge_keys = set(gesture['edges'])
        self.selected_point_name = gesture['primary']
        self.canvas.set_cad_selection_overlay()
        self._cad_drag_offset = None
        self.dragging_point_name = None
        self.drag_mode_active = False
        self.refresh_canvas()
        self.set_status('Selection cancelled; previous selection restored.')
        return True

    def _finish_cad_selection(self, event):
        gesture = getattr(self, '_cad_selection_gesture', None)
        if gesture is None:
            return False
        self._cad_selection_gesture = None
        self.canvas.set_cad_selection_overlay()
        if gesture['active']:
            from cad_selection import editor_paths, rectangle_hits
            position = event.position()
            end = QPointF(position) if isinstance(position, (QPoint, QPointF)) else gesture['end']
            hits = rectangle_hits(editor_paths(self), gesture['start'], end)
            points = {identity for kind, identity in hits if kind == 'point'}
            edges = {identity for kind, identity in hits if kind == 'edge'}
            self.selected_point_names = gesture['points'] ^ points if gesture['toggle'] else points
            self.selected_edge_keys = gesture['edges'] ^ edges if gesture['toggle'] else edges
            self.selected_point_name = next(iter(sorted(self.selected_point_names)), None)
        self.dragging_point_name = None
        self.drag_mode_active = False
        self.refresh_canvas()
        self.set_status(f'Selected {len(self.selected_point_names)} point(s) and {len(self.selected_edge_keys)} corridor(s).')
        return True

    @undoable("Move layout item", capture_before=False)
    def on_left_release(self, event):
        if self._finish_cad_selection(event):
            return
        if self.route_profile_selection_active:
            if self.route_profile_selection_rect_item is not None:
                rect = self.route_profile_selection_rect_item.rect()
                keep_existing = bool(event.modifiers() & Qt.ControlModifier)

                if not keep_existing:
                    self.route_profile_selected_nodes.clear()

                floor = self.floor_spin.value()

                for name, point in self.store.points_for_floor(floor).items():
                    if name not in self.route_profile_allowed_point_names:
                        continue

                    pos = self.world_to_scene(point["x"], point["y"])
                    if rect.contains(pos):
                        self.route_profile_selected_nodes.add(name)

                self.scene.removeItem(self.route_profile_selection_rect_item)
                self.route_profile_selection_rect_item = None
                self.route_profile_selection_rect_start = None

                self.set_status(
                    f"Route profile selection: {len(self.route_profile_selected_nodes)} node(s)"
                )
                self.refresh_canvas()

            return

        was_dragging = bool(self.dragging_point_name or self.dragging_bounding_box_point_index is not None)
        self._drag_refresh_timer.stop()
        self._cad_drag_origins = None
        self.dragging_point_name = None
        self.drag_mode_active = False
        self._cad_drag_offset = None
        self.dragging_bounding_box_point_index = None
        self.last_pan = None
        if was_dragging:
            self.refresh_canvas()

    @undoable("Edit layout")
    def on_right_click(self, event, sx, sy):
        mode = self._current_edit_mode()
        if mode == 'location_rectangle':
            self.cancel_cad_command()
            return
        if mode == 'corridor_draw':
            self.finish_corridor_drawing()
            return
        floor = self.floor_spin.value()
        x, y = self.scene_to_world(sx, sy)
        picked = self.find_nearest_point_name(x, y, floor)
        picked_edge = None if picked else self.find_nearest_edge_key(x, y, floor)

        if self.department_location_placement_active:
            self.cancel_department_location_placement()
            return

        if self.route_profile_selection_active:
            if picked:
                return

            menu = QMenu(self)
            finish_action = menu.addAction("Apply route profile selection")
            cancel_action = menu.addAction("Cancel route profile selection")

            action = menu.exec(event.globalPosition().toPoint())

            if action == finish_action:
                self._finish_route_profile_graphical_selection()
            elif action == cancel_action:
                self._cancel_route_profile_graphical_selection()

            return
        if mode == "pdf_underlay_align":
            return

        if mode == "select_move":
            if picked and picked not in self.selected_point_names:
                self.selected_point_names = {picked}
                self.selected_edge_keys.clear()
                self.selected_point_name = picked
            elif picked_edge is not None and picked_edge not in self.selected_edge_keys:
                self.selected_edge_keys = {picked_edge}
                self.selected_point_names.clear()
                self.selected_point_name = None
            if self.selected_edge_keys or len(self.selected_point_names) > 1 or (not picked and self.selected_point_names):
                menu = QMenu(self)
                menu.addAction(self.workbench.delete_action)
                menu.addAction(self.workbench.move_action)
                menu.addAction(self.workbench.fit_selection_action)
                menu.addSeparator()
                if picked_edge is not None:
                    menu.addAction("Insert node here", lambda: self.split_corridor_at(picked_edge, x, y))
                if self.selected_edge_keys:
                    junction = menu.addAction('Create junction at crossing', self.create_selected_junction)
                    junction.setEnabled(len(self.selected_edge_keys) == 2)
                    menu.addAction("Split selected corridors at midpoint", lambda: self.subdivide_selected_corridors(2))
                    menu.addAction("Subdivide selected corridors…", self.subdivide_selected_corridors)
                    menu.addSeparator()
                menu.addAction(
                    "Edit selected corridor widths / doors",
                    self.manage_corridor_settings,
                )
                menu.addAction(
                    "Create people movement profile",
                    self.create_people_profile_from_selection,
                )
                menu.addAction(
                    "Add selection to scenario",
                    self.manage_scenario_testing,
                )
                classify_menu = menu.addMenu("Classify corridor use")
                for label, area in [
                    ("No restriction", "none"),
                    ("Staff", "staff"),
                    ("Public", "public"),
                    ("Mixed staff/public", "both"),
                ]:
                    action = classify_menu.addAction(label)
                    action.triggered.connect(
                        lambda _checked=False, value=area: self.classify_selected_corridors(value)
                    )
                if self.selected_corridor_node_names():
                    door_menu = menu.addMenu("Door nodes")
                    door_menu.addAction(
                        "Mark selected nodes as doors…",
                        self.mark_selected_nodes_as_doors,
                    )
                    door_menu.addAction(
                        "Remove door classification",
                        self.clear_selected_node_doors,
                    )
                menu.addSeparator()
                menu.addAction("Clear selection", self.clear_topology_selection)
                menu.exec(event.globalPosition().toPoint())
                self.refresh_canvas()
                return

        if mode == "location_bbox" and self.bounding_box_location_name:
            hit_index = self.find_nearest_bounding_box_point_index(x, y)

            if hit_index is not None:
                removed = self.bounding_box_points.pop(hit_index)
                self.dragging_bounding_box_point_index = None
                self.set_status(
                    f"Removed bounding box point {hit_index + 1} "
                    f"from {self.bounding_box_location_name}"
                )
                self.refresh_canvas()
                return
        if mode == "location_bbox":
            if not picked:
                if self.bounding_box_location_name:
                    self.finish_location_bounding_box_draw()
                return
            picked_point = self.store.all_points().get(picked, {})
            if picked_point.get("kind") == "location":
                self.selected_point_name = picked
                self.refresh_canvas()
                menu = QMenu(self)
                draw_action = menu.addAction("Draw / replace bounding box")
                edit_action = None
                remove_action = None
                if self.store.get_location(picked).get("bounding_box"):
                    edit_action = menu.addAction("Edit existing bounding box")
                    remove_action = menu.addAction("Remove bounding box")
                cancel_action = None
                if self.bounding_box_location_name:
                    cancel_action = menu.addAction(
                        "Cancel current bounding box drawing"
                    )
                action = menu.exec(event.globalPosition().toPoint())
                if action == draw_action:
                    self.start_location_bounding_box_draw(picked, keep_existing=False)
                elif edit_action is not None and action == edit_action:
                    self.start_location_bounding_box_draw(picked, keep_existing=True)
                elif remove_action is not None and action == remove_action:
                    self.store.remove_location_bounding_box(picked)
                    self.set_status(f"Removed bounding box for {picked}")
                    self.refresh_canvas()
                elif cancel_action is not None and action == cancel_action:
                    self.cancel_location_bounding_box_draw()
                return

        if mode == "edge":
            # Right click empty space cancels edge chaining
            if not picked:
                if self.selected_for_edge is not None:
                    self.selected_for_edge = None
                    self.edge_delete_start = None
                    self.set_status("Edge chaining cancelled")
                return
            if picked and self.edge_delete_start is None:
                picked_point = self.store.all_points().get(picked, {})
                if picked_point.get("kind") == "department":
                    self.set_status("Departments cannot be connected by corridor edges")
                    return
                self.edge_delete_start = picked
                self.selected_for_edge = None
                self.set_status(f"Edge delete start selected: {picked}")
                return

            if picked:
                picked_point = self.store.all_points().get(picked, {})
                if picked_point.get("kind") == "department":
                    self.set_status("Departments cannot be connected by corridor edges")
                    return

            if picked and self.edge_delete_start:
                removed = False
                before = len(self.store.data.get("corridors", {}).get("edges", []))
                self.store.remove_edge(self.edge_delete_start, picked)
                after = len(self.store.data.get("corridors", {}).get("edges", []))
                removed = removed or (after < before)
                if self.bidirectional_check.isChecked():
                    before = len(self.store.data.get("corridors", {}).get("edges", []))
                    self.store.remove_edge(picked, self.edge_delete_start)
                    after = len(self.store.data.get("corridors", {}).get("edges", []))
                    removed = removed or (after < before)
                self.edge_delete_start = None
                self.set_status(
                    "Edge removed" if removed else "No matching edge to remove"
                )
                self.refresh_canvas()
                return
        if mode == "select_move" and picked:
            self.selected_point_name = picked
            self.refresh_canvas()
            point = self.store.all_points().get(picked, {})
            menu = QMenu(self)
            menu.addAction(self.workbench.delete_action)
            menu.addAction(self.workbench.move_action)
            menu.addAction(self.workbench.fit_selection_action)
            menu.addSeparator()

            if point.get("kind") == "department":
                edit_department_action = menu.addAction("Edit department")
                delete_department_action = menu.addAction("Delete department")
                action = menu.exec(event.globalPosition().toPoint())

                if action == edit_department_action:
                    self.edit_department_by_name(picked)
                elif action == delete_department_action:
                    dept = next(
                        (
                            x
                            for x in self.store.data.get("departments", [])
                            if x.get("name") == picked
                        ),
                        None,
                    )
                    if dept:
                        from amr_department_inputs import department_identity
                        try:
                            self.store.delete_department(department_identity(dept))
                        except ValueError as exc:
                            QMessageBox.critical(self, 'Department is in use', str(exc))
                            return
                        self.set_status(f"Deleted department {picked}")
                        self.refresh_canvas()
                return

            if point.get("kind") == "location":
                draw_bounds_action = menu.addAction("Add / edit room bounding box")
                menu.addAction('Draw rectangular boundary', lambda: self.start_location_rectangle(picked))
                remove_bounds_action = None
                location = self.store.get_location(picked)
                if location and location.get("bounding_box"):
                    remove_bounds_action = menu.addAction("Remove room bounding box")
                menu.addSeparator()
                inventory_spaces_action = menu.addAction("Inventory spaces")
                menu.addSeparator()
            else:
                draw_bounds_action = None
                remove_bounds_action = None

            show_edges_action = menu.addAction("Show all edge connections")
            create_department_action = menu.addAction("Create department here")
            action = menu.exec(event.globalPosition().toPoint())

            if draw_bounds_action is not None and action == draw_bounds_action:
                self.start_location_bounding_box_draw(
                    picked,
                    keep_existing=bool(
                        self.store.get_location(picked).get("bounding_box")
                    ),
                )
            elif remove_bounds_action is not None and action == remove_bounds_action:
                self.store.remove_location_bounding_box(picked)
                self.set_status(f"Removed bounding box for {picked}")
                self.refresh_canvas()
            elif point.get("kind") == "location" and action == inventory_spaces_action:
                dialog = InventorySpacesDialog(self, picked)
                if dialog.exec() == QDialog.Accepted:
                    self.set_status(f"Updated inventory spaces for {picked}")
                    self.refresh_canvas()
            elif action == show_edges_action:
                self._show_edge_connections_dialog(picked)
            elif action == create_department_action:
                point = self.store.all_points().get(picked)
                if point:
                    self.create_department_at_position(
                        float(point["x"]),
                        float(point["y"]),
                        int(point["floor"]),
                    )
            return
        if picked:
            self.selected_point_name = picked
            self.refresh_canvas()

    def on_drag(self, event, sx, sy):
        if self.project_editing_locked():
            return
        gesture = getattr(self, '_cad_selection_gesture', None)
        if gesture is not None:
            from cad_selection import DRAG_THRESHOLD_PX
            gesture['end'] = QPointF(self.canvas.mapFromScene(QPointF(sx, sy)))
            delta = gesture['end'] - gesture['start']
            if math.hypot(delta.x(), delta.y()) >= DRAG_THRESHOLD_PX:
                gesture['active'] = True
                self.canvas.set_cad_selection_overlay(gesture['start'], gesture['end'])
            return
        if self.route_profile_selection_active:
            if not (event.modifiers() & Qt.AltModifier):
                return

            scene_pos = self.canvas.mapToScene(event.position().toPoint())

            if self.route_profile_selection_rect_start is None:
                self.route_profile_selection_rect_start = scene_pos
                self.route_profile_selection_rect_item = self.scene.addRect(
                    QRectF(scene_pos, scene_pos),
                    QPen(QColor("#00e5ff"), 0),
                    QBrush(QColor(0, 229, 255, 35)),
                )
                self.route_profile_selection_rect_item.setZValue(200)
                return

            rect = QRectF(
                self.route_profile_selection_rect_start, scene_pos
            ).normalized()

            if self.route_profile_selection_rect_item is not None:
                self.route_profile_selection_rect_item.setRect(rect)

            return
        mode = self._current_edit_mode()
        if mode == "pdf_underlay_align":
            return
        if mode == "pan":
            current = event.position().toPoint()
            if self.last_pan is None:
                self.last_pan = current
                return
            dx = current.x() - self.last_pan.x()
            dy = current.y() - self.last_pan.y()
            self.canvas.horizontalScrollBar().setValue(
                self.canvas.horizontalScrollBar().value() - dx
            )
            self.canvas.verticalScrollBar().setValue(
                self.canvas.verticalScrollBar().value() - dy
            )
            self.last_pan = current
            self.canvas.viewport().update()
            return
        if (
            mode == "location_bbox"
            and self.dragging_bounding_box_point_index is not None
            and self.bounding_box_location_name
        ):
            x, y = self.scene_to_world(sx, sy)
            x, y = self.snap(x, y)

            idx = self.dragging_bounding_box_point_index
            if 0 <= idx < len(self.bounding_box_points):
                self.bounding_box_points[idx] = {"x": x, "y": y}
                self._schedule_drag_refresh()
            return
        if mode == "select_move" and self.drag_mode_active and self.dragging_point_name:
            x, y = self.scene_to_world(sx, sy)
            offset = getattr(self, '_cad_drag_offset', None)
            if offset is not None:
                x, y = x-offset[0], y-offset[1]
            x, y = self.snap(x, y)
            origins = getattr(self, '_cad_drag_origins', None)
            if origins and self.dragging_point_name in origins:
                ox, oy = origins[self.dragging_point_name]
                dx, dy = x - ox, y - oy
                for name, (px, py) in origins.items():
                    self.store.set_point_position(name, px + dx, py + dy, exact=True)
            else:
                self.store.set_point_position(self.dragging_point_name, x, y)
            self._schedule_drag_refresh()

    def _schedule_drag_refresh(self):
        # Keep the model exact on every move while coalescing render work.
        # Release always flushes the final position and contextual panels.
        if not self._drag_refresh_timer.isActive():
            self._drag_refresh_timer.start()

    def on_middle_click(self, event):
        self.last_pan = event.position().toPoint()

    def on_middle_drag(self, event):
        current = event.position().toPoint()
        if self.last_pan is None:
            self.last_pan = current
            return
        dx = current.x() - self.last_pan.x()
        dy = current.y() - self.last_pan.y()
        self.canvas.horizontalScrollBar().setValue(
            self.canvas.horizontalScrollBar().value() - dx
        )
        self.canvas.verticalScrollBar().setValue(
            self.canvas.verticalScrollBar().value() - dy
        )
        self.last_pan = current
        self.canvas.viewport().update()

    def on_middle_release(self, event):
        self.last_pan = None
        self.canvas.viewport().update()

    def on_mousewheel(self, event):
        factor = 1.1 if event.angleDelta().y() > 0 else 0.9
        self.canvas.scale(factor, factor)
        self.canvas.viewport().update()

    def _show_config_validation_warning(self, path: str, errors: list[str]) -> None:
        preview_limit = 50
        shown_errors = errors[:preview_limit]
        message_lines = [
            f"{Path(path).name} was opened, but validation found {len(errors)} issue(s).",
            "",
            "You can continue editing the file and use Validate JSON after making changes.",
            "",
            *shown_errors,
        ]
        if len(errors) > preview_limit:
            message_lines.append(
                f"... plus {len(errors) - preview_limit} additional issue(s)."
            )
        QMessageBox.warning(
            self,
            "Config opened with validation issues",
            "\n".join(message_lines),
        )

    def load_json_file(self, path: str, *, load_drawings: bool = True, check_unsaved: bool = True) -> bool:
        if check_unsaved and not self._confirm_unsaved_changes():
            return False
        project = None
        cache = None
        try:
            if Path(path).suffix.lower() == ".amrproj":
                root = str(Path(__file__).resolve().parents[1])
                if root not in sys.path:
                    sys.path.insert(0, root)
                from amr_project import Project
                project = Project.open(path)
                cache = tempfile.TemporaryDirectory(prefix="amr-project-")
                store = JsonStore(project.materialize(cache.name))
            else:
                store = JsonStore.from_file(path)
        except json.JSONDecodeError as exc:
            QMessageBox.critical(
                self,
                "Could not open JSON",
                f"{Path(path).name} is not valid JSON.\n\n{exc}",
            )
            self.set_status("JSON open failed: invalid JSON syntax")
            return False
        except OSError as exc:
            QMessageBox.critical(
                self,
                "Could not open JSON",
                f"{Path(path).name} could not be read.\n\n{exc}",
            )
            self.set_status("JSON open failed: file could not be read")
            return False
        except Exception as exc:
            if cache is not None:
                cache.cleanup()
            QMessageBox.critical(
                self,
                "Could not open project or JSON",
                f"{Path(path).name} could not be loaded.\n\n{exc}",
            )
            self.set_status("JSON open failed")
            return False

        if not isinstance(store.data, dict):
            QMessageBox.critical(
                self,
                "Could not open JSON",
                f"{Path(path).name} is valid JSON, but the top-level value is not an object.",
            )
            self.set_status("JSON open failed: top-level value is not an object")
            return False

        try:
            validation_errors = store.validate()
        except Exception as exc:
            validation_errors = [
                f"Validation could not complete. The file was opened for editing, but some editor features may need missing fields to be repaired first: {exc}"
            ]

        return self._replace_document(store, path, project=project, cache=cache,
                                      load_drawings=load_drawings, validation_errors=validation_errors)

    def new_project(self):
        """Start a fresh authoring document after protecting the current one."""
        if not self._confirm_unsaved_changes():
            return False
        return self._replace_document(JsonStore(), None)

    def _replace_document(self, store, path, *, project=None, cache=None,
                          load_drawings=True, validation_errors=()):
        if hasattr(self, 'playback_panel'):
            self.playback_panel.reset()
        if hasattr(self, 'properties_panel'):
            self.properties_panel.reset()
            self.workspace.selected_edge_record = None
            self.workspace.selected_configuration = None
        self.store = store
        self._recovered_work = False
        self.project = project
        # Retain previous drawing caches until shutdown: background workers may
        # still be reading files belonging to the previous open project.
        if cache is not None:
            if self._project_cache is None:
                self._project_cache = []
            self._project_cache.append(cache)
        if hasattr(self, "project_history_panel"):
            self.project_history_panel.refresh()
        self._drawings_enabled = load_drawings
        self.current_json_path = path
        self.selected_point_name = None
        self.selected_point_names.clear()
        self.selected_edge_keys.clear()
        self.dragging_point_name = None
        self.drag_mode_active = False
        self.selected_for_edge = None
        self.edge_delete_start = None
        self.bounding_box_location_name = None
        self.bounding_box_points = []
        self.dragging_bounding_box_point_index = None
        self._clear_corridor_drawing()
        self._clear_dxf_cache()
        self._pdf_pixmap_cache.clear()
        self._pdf_render_errors.clear()
        if path is None:
            self.floor_spin.setValue(0)
        self._set_edit_mode('select_move')
        current_floor = self.floor_spin.value()
        self._pending_fit_after_load = load_drawings and bool(self.get_floor_dxf_path(current_floor))
        self._queue_all_floor_dxf_loads(active_floor=current_floor, force_reload=False)
        if validation_errors:
            self.set_status(
                f"Opened {Path(path).name} with {len(validation_errors)} validation issue(s)"
            )
            self._show_config_validation_warning(path, validation_errors)
        elif path is not None:
            suffix = " without drawings" if not load_drawings else ""
            self.set_status(f"Opened {Path(path).name}{suffix}")
        else:
            self.set_status('New project. Draw the layout, configure robots and demand, then run Project checks before simulation.')
        self.refresh_canvas()
        self.fit_view()
        self._reset_edit_history()
        self._mark_saved()
        return True

    def open_json(self, *, load_drawings=True):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open project or JSON" if load_drawings else "Open configuration without drawings", "", "AMR projects and JSON (*.amrproj *.json);;AMR projects (*.amrproj);;JSON files (*.json)"
        )
        if not path:
            return
        self.load_json_file(path, load_drawings=load_drawings)

    def load_configured_drawings(self):
        self._drawings_enabled = True
        floor = self.floor_spin.value()
        self._pending_fit_after_load = bool(self.get_floor_dxf_path(floor))
        self._queue_all_floor_dxf_loads(active_floor=floor)
        self.refresh_canvas()
        self.fit_view()

    def save_json(self):
        if not self._project_editing_allowed():
            return False
        if not self._finish_property_draft():
            return False
        self._commit_history()
        if self.project is not None or (not self.current_json_path and not self._recovered_work):
            return self.save_project()
        path = self.current_json_path
        if not path:
            path, _ = QFileDialog.getSaveFileName(
                self, "Save JSON", "", "JSON files (*.json)"
            )
        if not path:
            return False
        try:
            if self.current_json_path and self._source_disk_hash is not None:
                if hashlib.sha256(Path(path).read_bytes()).hexdigest() != self._source_disk_hash:
                    raise ValueError("Configuration changed on disk. Save as a project or export to a new JSON file before reopening it.")
            if self._recovered_work:
                from amr_project import Project
                Project().export_json(path, self.store.data)
                # Recovery drawing caches are temporary; JSON needs durable copies.
                exported = json.loads(Path(path).read_text(encoding="utf-8"))
                remapped = {}
                for key in ("floor_dxf_files", "floor_pdf_underlays"):
                    for old, new in zip(self.store.data.get(key, []), exported.get(key, [])):
                        if old.get("filepath") and new.get("filepath"):
                            remapped[old["filepath"]] = new["filepath"]
                self.edit_history.remap_drawings(remapped)
                self.store.data = exported
                self._recovered_work = False
            else:
                self.store.save(path)
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return False
        self.current_json_path = path
        self.set_status(f"Saved {Path(path).name}")
        self.refresh_canvas()
        self._mark_saved()
        return True

    def save_project(self, *, save_as=False):
        if not self._project_editing_allowed():
            return False
        if not self._finish_property_draft():
            return False
        self._commit_history()
        root = str(Path(__file__).resolve().parents[1])
        if root not in sys.path:
            sys.path.insert(0, root)
        from amr_project import Project
        path = str(self.project.path) if self.project is not None else ""
        if save_as or not path:
            suggested = str(Path(self.current_json_path).with_suffix(".amrproj")) if self.current_json_path else "project.amrproj"
            path, _ = QFileDialog.getSaveFileName(self, "Save portable project", suggested, "AMR projects (*.amrproj)")
        if not path:
            return False
        try:
            project = self.project or Project()
            project.save(path, self.store.data, base_dir=Path(self.current_json_path).parent if self.current_json_path else Path.cwd())
            self.project = project
            self.current_json_path = str(project.path)
            cache = self._project_cache[-1] if self._project_cache else tempfile.TemporaryDirectory(prefix="amr-project-")
            portable = project.materialize(cache.name)
            remapped = {}
            for key in ("floor_dxf_files", "floor_pdf_underlays"):
                if key in portable:
                    for old, new in zip(self.store.data.get(key, []), portable[key]):
                        if old.get("filepath") and new.get("filepath"):
                            remapped[old["filepath"]] = new["filepath"]
                    self.store.data[key] = portable[key]
            self.edit_history.remap_drawings(remapped)
            if self._project_cache is None:
                self._project_cache = []
            if cache not in self._project_cache:
                self._project_cache.append(cache)
            self.set_status(f"Saved {project.path.name} — {len(project.revisions)} revision(s)")
            if hasattr(self, "project_history_panel"):
                self.project_history_panel.refresh()
            self.refresh_canvas()
            self._mark_saved()
            self._recovered_work = False
            return True
        except Exception as exc:
            QMessageBox.critical(self, "Project save failed", f"The project was not saved.\n\n{exc}")
            return False

    def export_project_json(self):
        if not self._finish_property_draft():
            return
        root = str(Path(__file__).resolve().parents[1])
        if root not in sys.path:
            sys.path.insert(0, root)
        from amr_project import Project
        path, _ = QFileDialog.getSaveFileName(self, "Export JSON with drawings", "", "JSON files (*.json)")
        if not path:
            return
        try:
            (self.project or Project()).export_json(path, self.store.data,
                base_dir=Path(self.current_json_path).parent if self.current_json_path else Path.cwd())
            self.set_status(f"Exported {Path(path).name} and drawing files; open project unchanged")
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))

    def show_project_revisions(self):
        from project_history_panel import ProjectHistoryPanel
        if not hasattr(self, "project_history_panel"):
            self.project_history_panel = ProjectHistoryPanel(self)
        self.project_history_panel.refresh()
        self.workspace.show_page('project', self.project_history_panel)

    def show_project_runs(self):
        root = str(Path(__file__).resolve().parents[1])
        if root not in sys.path:
            sys.path.insert(0, root)
        from project_runs_panel import ProjectRunsPanel
        if not hasattr(self, 'project_runs_panel'):
            self.project_runs_panel = ProjectRunsPanel(self)
        self.project_runs_panel.refresh_runs()
        self.workspace.show_page('simulate', self.project_runs_panel)

    def show_project_report(self, path=None):
        root = str(Path(__file__).resolve().parents[1])
        if root not in sys.path:
            sys.path.insert(0, root)
        from project_report_panel import ProjectReportPanel
        if not hasattr(self, 'report_panel'):
            self.report_panel = ProjectReportPanel(self)
        if path is not None:
            self.report_panel.set_run(path)
        self.workspace.show_page('report', self.report_panel)

    def show_project_playback(self, path=None):
        root = str(Path(__file__).resolve().parents[1])
        if root not in sys.path:
            sys.path.insert(0, root)
        from project_playback_panel import ProjectPlaybackPanel
        if not hasattr(self, 'playback_panel'):
            self.playback_panel = ProjectPlaybackPanel(self)
        self.workspace.show_page('playback', self.playback_panel)
        if path is not None:
            self.playback_panel.load(path)

    def _ask_dxf_units(self):
        units, accepted = QInputDialog.getItem(
            self,
            "DXF units",
            "Choose the units for the exported DXF:",
            list(DXF_UNIT_SPECS),
            0,
            False,
        )
        return str(units) if accepted else None

    def export_current_floor_dxf(self):
        floor = int(self.floor_spin.value())
        units = self._ask_dxf_units()
        if units is None:
            return
        if self.current_json_path:
            json_path = Path(self.current_json_path)
            suggested_path = json_path.with_name(f"{json_path.stem}_floor_{floor}.dxf")
        else:
            suggested_path = Path(f"amr_layout_floor_{floor}.dxf")

        path, _ = QFileDialog.getSaveFileName(
            self,
            f"Export floor {floor} to DXF",
            str(suggested_path),
            "DXF files (*.dxf)",
        )
        if not path:
            return
        if not Path(path).suffix:
            path = f"{path}.dxf"

        try:
            counts = export_floor_to_dxf(
                self.store.data,
                floor,
                path,
                units=units,
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "DXF export failed",
                f"Could not export floor {floor} to DXF.\n\n{exc}",
            )
            self.set_status(f"DXF export failed for floor {floor}")
            return

        self.set_status(
            f"Exported floor {floor} to {Path(path).name} "
            f"({counts['total']} editable item(s), backgrounds excluded)"
        )
        QMessageBox.information(
            self,
            "DXF export complete",
            f"Exported floor {floor} to:\n{path}\n\n"
            "The mapped DXF/PDF background was excluded. Editor geometry uses "
            f"the same world coordinates, converted to {units.lower()}.",
        )

    def export_all_floors_dxf(self):
        units = self._ask_dxf_units()
        if units is None:
            return

        if self.current_json_path:
            json_path = Path(self.current_json_path)
            suggested_path = json_path.with_name(f"{json_path.stem}_floors.dxf")
        else:
            suggested_path = Path("amr_layout_floors.dxf")
        base_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export all floors to separate DXF files",
            str(suggested_path),
            "DXF files (*.dxf)",
        )
        if not base_path:
            return

        try:
            planned_outputs = all_floor_output_paths(self.store.data, base_path)
        except Exception as exc:
            QMessageBox.warning(self, "Nothing to export", str(exc))
            return
        existing_outputs = [
            output_path
            for _sequence, _floor, output_path in planned_outputs
            if output_path.exists()
        ]
        if existing_outputs:
            answer = QMessageBox.question(
                self,
                "Replace existing DXF files?",
                f"{len(existing_outputs)} sequential export file(s) already exist "
                "and will be replaced. Continue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return

        try:
            results = export_all_floors_to_dxf(
                self.store.data,
                base_path,
                units=units,
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "DXF export failed",
                f"Could not export all floors to DXF.\n\n{exc}",
            )
            self.set_status("All-floor DXF export failed")
            return

        first_path = results[0]["path"]
        last_path = results[-1]["path"]
        self.set_status(
            f"Exported {len(results)} floors as sequential DXF files "
            f"({units.lower()}, backgrounds excluded)"
        )
        QMessageBox.information(
            self,
            "DXF export complete",
            f"Exported {len(results)} floor(s) as separate DXF files.\n\n"
            f"First: {first_path.name}\nLast: {last_path.name}\n"
            f"Folder: {first_path.parent}\nUnits: {units}\n\n"
            "Mapped DXF/PDF backgrounds were excluded.",
        )

    @undoable("Edit simulation settings")
    def manage_simulation_settings(self):
        dialog = SimulationSettingsDialog(
            self,
            self.store.data.get("simulation"),
            full_config=self.store.data,
        )
        if dialog.exec() == QDialog.Accepted and dialog.result is not None:
            updated = deepcopy(self.store.data)
            project_result = getattr(dialog, 'project_result', None)
            if isinstance(project_result, dict):
                for section in ('simulation', 'geometry'):
                    if section in project_result:
                        updated[section] = deepcopy(project_result[section])
                    else:
                        updated.pop(section, None)
            else:  # Compatibility with existing simulation-only dialog callers.
                updated['simulation'] = dialog.result
            self.store.data = updated
            end_text = dialog.result.get("end_datetime", "") or "not set"
            self.set_status(f"Simulation settings updated; demand end: {end_text}")

    @undoable("Edit scenarios")
    def manage_scenario_testing(self):
        dialog = ScenarioTestingDialog(
            self,
            self.store.scenario_testing(),
            self.store.data,
            topology_selection=self.topology_selection_payload(),
        )
        if dialog.exec() == QDialog.Accepted and dialog.result is not None:
            self.store.set_scenario_testing(dialog.result)
            simulation = self.store.data.setdefault("simulation", {})
            simulation["scenario_mode"] = bool(dialog.result.get("enabled", False))
            simulation["scenario_enhanced_logging"] = bool(dialog.result.get("enhanced_logging", False))
            self.set_status(
                f"Scenario testing set to {dialog.result.get('active_scenario', 'Normal operation')}"
            )

    @undoable("Edit people profiles")
    def manage_people_movement(self):
        locations = sorted(self.store.all_points().keys())
        corridor_options = sorted(
            {
                f"{edge.get('from', '')} -> {edge.get('to', '')}"
                for edge in self.store.data.get("corridors", {}).get("edges", [])
                if edge.get("from") and edge.get("to")
            }
        )
        dialog = PeopleMovementListDialog(
            self,
            locations,
            corridor_options,
            self.store.people_movements(),
            initially_selected_corridors=self.selected_corridor_labels(
                include_incident_nodes=True
            ),
        )
        if dialog.exec() == QDialog.Accepted and dialog.result is not None:
            self.store.set_people_movements(dialog.result)
            profile_by_edge = {}
            valid_profile_ids = {
                str(profile.get("id", "") or "").strip()
                for profile in dialog.result
                if str(profile.get("id", "") or "").strip()
            }
            direct_profile_ids = {
                str(profile.get("id", "") or "").strip()
                for profile in dialog.result
                if str(profile.get("id", "") or "").strip()
                and bool(profile.get("corridor_edges", []) or [])
            }
            for profile in dialog.result:
                if not bool(profile.get("enabled", True)):
                    continue
                group_type = str(profile.get("group_type", "staff") or "staff").strip().lower()
                if group_type == "mixed":
                    group_type = "both"
                profile_id = str(profile.get("id", "") or "").strip()
                for label in profile.get("corridor_edges", []) or []:
                    if " -> " not in str(label):
                        continue
                    start, end = str(label).split(" -> ", 1)
                    key = self._physical_edge_key(start, end)
                    entry = profile_by_edge.setdefault(key, {"types": set(), "profiles": set()})
                    entry["types"].add(group_type)
                    if profile_id:
                        entry["profiles"].add(profile_id)
            for edge in self.store.data.get("corridors", {}).get("edges", []):
                key = self._physical_edge_key(edge.get("from"), edge.get("to"))
                entry = profile_by_edge.get(key)
                retained_profiles = {
                    str(profile_id).strip()
                    for profile_id in edge.get("people_profile_ids", []) or []
                    if str(profile_id).strip() in valid_profile_ids
                    and str(profile_id).strip() not in direct_profile_ids
                }
                if entry is not None:
                    types = entry["types"]
                    edge["people_area_type"] = (
                        "both" if "both" in types or len(types) > 1 else next(iter(types), "none")
                    )
                    retained_profiles.update(entry["profiles"])
                edge["people_profile_ids"] = sorted(retained_profiles)
            self.store.ensure_corridor_defaults()
            self.set_status(f"Updated {len(dialog.result)} people movement profile(s)")
            self.refresh_canvas()

    @undoable("Edit corridor settings")
    def manage_corridor_settings(self):
        building = self.store.data.setdefault("building", {})
        corridors = self.store.data.setdefault("corridors", {})
        dialog = CorridorSettingsDialog(
            self,
            corridors.setdefault("edges", []),
            corridors.setdefault("nodes", []),
            default_width=float(
                building.get("default_corridor_width_m", 2.4) or 2.4
            ),
            default_door_width=float(
                building.get("default_door_clear_width_m", 0.9) or 0.9
            ),
            people_profiles=[
                item.get("id", "") for item in self.store.people_movements()
            ],
            initially_selected_edges=[
                f"{edge.get('from', '')} -> {edge.get('to', '')}"
                for edge in corridors.setdefault("edges", [])
                if self._physical_edge_key(edge.get("from"), edge.get("to"))
                in self._selected_corridor_keys(include_incident_nodes=False)
            ],
            initially_selected_nodes=self.selected_corridor_node_names(),
        )
        if dialog.exec() == QDialog.Accepted and dialog.result is not None:
            self.store.data["corridors"]["edges"] = dialog.result.get("edges", [])
            self.store.data["corridors"]["nodes"] = dialog.result.get("nodes", [])
            self.store.ensure_corridor_defaults()
            self.set_status(
                "Corridor widths, door openings, lane behaviour and people occupancy updated"
            )
            self.refresh_canvas()

    @undoable("Edit drawing mapping")
    def load_pdf_underlay(self):
        floor = self.floor_spin.value()
        existing = self.get_floor_pdf_underlay(floor)
        initialdir = ""
        if existing and existing.get("filepath"):
            initialdir = str(Path(existing["filepath"]).expanduser().parent)
        path, _ = QFileDialog.getOpenFileName(
            self, "Select PDF underlay", initialdir, "PDF files (*.pdf)"
        )
        if not path:
            return
        initial = {
            **(existing or {}),
            "floor": floor,
            "filepath": path,
            "page": 1,
        }
        try:
            _pixmap, page_count = self._pdf_pixmap(normalise_pdf_underlay(initial))
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Could not import PDF",
                f"{Path(path).name} could not be rendered.\n\n{exc}",
            )
            self.set_status("PDF underlay import failed")
            return
        dialog = PdfUnderlayDialog(self, initial, page_count=page_count)
        if dialog.exec() != QDialog.Accepted:
            return
        mapping = dialog.mapping(floor, path)
        self.set_floor_pdf_underlay(floor, mapping)
        self._drawings_enabled = True
        self._set_edit_mode("pdf_underlay_align")
        self.refresh_canvas()
        self.fit_view()
        width_m = mapping["paper_width_mm"] * mapping["scale_denominator"] / 1000.0
        height_m = mapping["paper_height_mm"] * mapping["scale_denominator"] / 1000.0
        self.set_status(
            f"Imported {Path(path).name} on floor {floor} at "
            f"{width_m:.3f} x {height_m:.3f} m; drag it to align"
        )

    @undoable("Edit drawing mapping")
    def edit_pdf_underlay(self):
        floor = self.floor_spin.value()
        mapping = self.get_floor_pdf_underlay(floor)
        if mapping is None:
            self.set_status(f"No PDF underlay mapped to floor {floor}")
            return
        try:
            _pixmap, page_count = self._pdf_pixmap(mapping)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Could not open PDF settings",
                f"{Path(mapping['filepath']).name} could not be rendered.\n\n{exc}",
            )
            return
        dialog = PdfUnderlayDialog(self, mapping, page_count=page_count)
        if dialog.exec() != QDialog.Accepted:
            return
        updated = dialog.mapping(floor, mapping["filepath"])
        self.set_floor_pdf_underlay(floor, updated)
        self._drawings_enabled = True
        self.refresh_canvas()
        self.set_status(f"Updated PDF underlay settings for floor {floor}")

    @undoable("Edit drawing mapping")
    def clear_floor_pdf_underlay(self):
        floor = self.floor_spin.value()
        mapping = self.get_floor_pdf_underlay(floor)
        if mapping is None:
            self.set_status(f"No PDF underlay mapped to floor {floor}")
            return
        if (
            QMessageBox.question(
                self,
                "Clear floor PDF underlay",
                f"Remove the PDF underlay mapping for floor {floor}?",
            )
            != QMessageBox.Yes
        ):
            return
        self.clear_floor_pdf_underlay_mapping(floor)
        self.set_status(f"Removed PDF underlay from floor {floor}")
        self.refresh_canvas()

    @undoable("Edit drawing mapping")
    def load_dxf(self):
        floor = self.floor_spin.value()
        initialdir = ""
        existing = self.get_floor_dxf_path(floor)
        if existing:
            try:
                initialdir = str(Path(existing).expanduser().resolve().parent)
            except Exception:
                initialdir = str(Path(existing).expanduser().parent)
        path, _ = QFileDialog.getOpenFileName(
            self, "Select DXF", initialdir, "DXF files (*.dxf)"
        )
        if not path:
            return
        self.set_floor_dxf_path(floor, path)
        self._drawings_enabled = True
        self._dxf_cache.pop(int(floor), None)
        if self.loaded_dxf_floor == int(floor):
            self.dxf_scene.clear()
            self.current_dxf_path = None
            self.loaded_dxf_floor = None
        self._pending_fit_after_load = True
        self._queue_all_floor_dxf_loads(active_floor=floor, force_reload=True)
        self.refresh_canvas()
        self.set_status(f"Mapped DXF {Path(path).name} to floor {floor}")

    @undoable("Edit drawing mapping")
    def clear_floor_dxf(self):
        floor = self.floor_spin.value()
        existing = self.get_floor_dxf_path(floor)
        if not existing:
            self.set_status(f"No DXF mapped to floor {floor}")
            return
        if (
            QMessageBox.question(
                self, "Clear floor DXF", f"Remove DXF mapping for floor {floor}?"
            )
            != QMessageBox.Yes
        ):
            return
        self.clear_floor_dxf_mapping(floor)
        self._dxf_cache.pop(int(floor), None)
        self._dxf_loading_floors.discard(int(floor))
        if self.loaded_dxf_floor == int(floor):
            self.dxf_scene.clear()
            self.current_dxf_path = None
            self.loaded_dxf_floor = None
        self.set_status(f"Removed DXF mapping from floor {floor}")
        self.refresh_canvas()

    def show_results_investigation(self):
        root = str(Path(__file__).resolve().parents[1])
        if root not in sys.path:
            sys.path.insert(0, root)
        from results_investigation_panel import ResultsInvestigationPanel
        if not hasattr(self, 'results_panel'):
            self.results_panel = ResultsInvestigationPanel(self)
        self.workspace.show_page('review', self.results_panel)
        self.set_status('Results investigation opened. Select a saved run or event CSV.')

    def show_demand_preview(self):
        # The editor also runs directly from visualiser/amr_editor_main.py.
        root = str(Path(__file__).resolve().parents[1])
        if root not in sys.path:
            sys.path.insert(0, root)
        from demand_preview_panel import DemandPreviewPanel
        if not hasattr(self, 'demand_panel'):
            self.demand_panel = DemandPreviewPanel(lambda: self.store.data, self)
            self.demand_scroll = QScrollArea(self)
            self.demand_scroll.setWidgetResizable(True)
            self.demand_scroll.setWidget(self.demand_panel)
        self.workspace.show_page('demand', self.demand_scroll)
        self.set_status('Demand preview opened. Build a preview to inspect planned demand.')

    def show_project_checks(self):
        if not hasattr(self, 'checks_panel'):
            self.validate_json()
            return
        self.checks_panel.check_staleness()
        self.workspace.show_page('checks', self.checks_panel)
        self.set_status('Review existing findings or choose Run checks to evaluate the current inputs.')

    def validate_json(self):
        from project_checks_panel import ProjectChecksPanel
        if not hasattr(self, 'checks_panel'):
            self.checks_panel = ProjectChecksPanel(
                lambda: self.store.data, self,
                lambda: Path(self.current_json_path).parent if self.current_json_path else None)
            self.checks_panel.navigate.connect(self.navigate_check_finding)
        else:
            self.checks_panel.check_now()
        self.workspace.show_page('checks', self.checks_panel)
        self.set_status('Project checks opened; select a finding to investigate.')

    def navigate_check_finding(self, finding):
        if hasattr(self, 'checks_panel') and not self.checks_panel.finding_current(finding):
            self.set_status('This finding needs a recheck before navigating to its recorded object.')
            return False
        from check_navigation import destination
        try:
            target = destination(self.store.data, finding)
        except (ValueError, TypeError, KeyError, AttributeError):
            target = None
        if target is not None:
            if target.kind in {'point', 'edge'}:
                self.workspace.select_object((target.kind, target.key))
            else:
                self.workspace.select_configuration(target.kind, target.key)
            panel = self.properties_panel
            expected = ('points', (target.key,)) if target.kind == 'point' else ('edges', (target.key,)) if target.kind == 'edge' else (target.kind, (target.key,))
            field = panel.fields.get(target.field) if panel.target == expected else None
            if field is not None:
                focus = getattr(field, 'search', field)
                panel.scroll.ensureWidgetVisible(focus)
                focus.setFocus(Qt.OtherFocusReason)
                if isinstance(field, QLineEdit):
                    field.selectAll()
                self.set_status(f'{finding.message} — {finding.path}')
            elif panel.pending and panel.target != expected:
                self.set_status('Your existing property draft is retained. Apply or discard it before editing the affected object.')
            else:
                self.set_status(f'{finding.message} — {finding.path}. Use the full editor for fields not shown here.')
            return True
        if finding.code in {'DUPLICATE', 'IDENTIFIER'} and finding.section in {'corridors', 'locations', 'lifts'}:
            self.set_status('This graph object has no unambiguous identifier. Repair its identity in the full editor before selecting it on the map. ' + finding.path)
            return False
        handlers = {
            'simulation': self.manage_simulation_settings,
            'corridors': self.manage_corridor_settings,
            'building': self.manage_corridor_settings,
            'amrs': self.manage_amrs, 'payloads': self.manage_payloads,
            'lifts': self.manage_lifts, 'tasks': self.manage_tasks,
            'task_generation': self.manage_task_generation,
            'route_profiles': self.manage_route_profiles,
            'departments': self.manage_departments,
            'waste_streams': self.manage_waste_streams,
            'mass_collections': self.manage_mass_collections,
            'people_movements': self.manage_people_movement,
            'scenario_testing': self.manage_scenario_testing,
        }
        handler = handlers.get(finding.section)
        if handler:
            handler()
        else:
            self.set_status(f'{finding.path}: {finding.action}')

    @undoable("Edit payloads")
    def manage_payloads(self):
        location_names = sorted(
            str(x.get("name", "")).strip()
            for x in self.store.data.get("locations", [])
            if str(x.get("name", "")).strip()
        )

        dialog = PayloadListDialog(
            self,
            self.store.data.get("payloads", []),
            self._save_payloads,
            location_names=location_names,
        )
        dialog.exec()

    @undoable("Edit payloads")
    def _save_payloads(self, items):
        self.store.data["payloads"] = items
        self.set_status("Payloads updated")

    @undoable("Edit lifts")
    def manage_lifts(self):
        dialog = LiftListDialog(self, self.store, self._lifts_changed)
        dialog.exec()

    @undoable("Edit lifts")
    def _lifts_changed(self):
        self.set_status("Lifts updated")
        self.refresh_canvas()

    @undoable("Edit lifts")
    def _save_lift_result(self, result, old_id=None):
        if old_id and old_id != result["id"]:
            self.store.delete_lift(old_id)
        self.store.upsert_lift(
            result["id"],
            result["served_floors"],
            result["floor_locations"],
            result["speed_m_per_sec"],
            result["door_time_sec"],
            result["boarding_time_sec"],
            result["capacity_length_m"],
            result["capacity_width_m"],
            result["capacity_height_m"],
            result["car_mass_kg"],
            result["counterweight_ratio"],
            result["travel_efficiency"],
            result["door_power_w"],
            result["standby_power_w"],
            result["regen_efficiency"],
            result["health_percent"],
            result["health_loss_per_journey_percent"],
            result["mean_time_between_failures_hours"],
            result["mean_time_to_repair_hours"],
            result["minimum_operational_health_percent"],
            result["health_speed_penalty_at_zero"],
            result["start_floor"],
        )

    @undoable("Edit AMRs")
    def manage_amrs(self):
        location_names = sorted(x["name"] for x in self.store.data.get("locations", []))

        dialog = AMRListDialog(
            self,
            self.store.data.get("amrs", []),
            location_names,
            self._save_amrs,
        )
        dialog.exec()

    @undoable("Edit AMRs")
    def _save_amrs(self, items):
        self.store.data["amrs"] = items
        if hasattr(self.store, "ensure_amr_defaults"):
            self.store.ensure_amr_defaults()
        self.set_status("AMRs updated")

    def build_floor_map(self, store):
        floor_map = {}
        for item in store.get("locations", []):
            floor_map[item["name"]] = int(item["floor"])
        for item in store.get("corridors", {}).get("nodes", []):
            floor_map[item["name"]] = int(item["floor"])
        for item in store.get("departments", []):
            name = str(item.get("name", "")).strip()
            if name:
                floor_map[name] = int(item.get("floor", 0))
        for lift in store.get("lifts", []):
            for floor_str in lift.get("floor_locations", {}).keys():
                floor_map[f"{lift['id']}-F{floor_str}"] = int(floor_str)
        return floor_map

    def _manual_task_amr_available(self):
        if not hasattr(self.store, "has_manual_task_compatible_amr"):
            return True
        return self.store.has_manual_task_compatible_amr()

    def manage_tasks(self):
        locations = self.store.data.get("locations", [])
        location_names = sorted(x["name"] for x in locations)
        payload_names = sorted(x["name"] for x in self.store.data.get("payloads", []))
        profile_names = [""] + sorted(self.store.data.get("route_profiles", {}).keys())
        floor_map = self.build_floor_map(self.store.data)
        TaskEditorWindow(
            self,
            self.store.data.get("tasks", []),
            location_names,
            payload_names,
            profile_names,
            self.store.suggest_next_task_id,
            self._save_tasks,
            floor_map=floor_map,
            manual_single_payload_available=self._manual_task_amr_available(),
        )

    @undoable("Edit tasks")
    def _save_tasks(self, items):
        self.store.data["tasks"] = items
        self.set_status("Tasks updated")

    def manage_task_planner(self):
        locations = self.store.data.get("locations", [])
        location_names = sorted(x["name"] for x in locations)
        payload_names = sorted(x["name"] for x in self.store.data.get("payloads", []))
        profile_names = [""] + sorted(self.store.data.get("route_profiles", {}).keys())
        floor_map = self.build_floor_map(self.store.data)
        for item in locations:
            floor_map[item["name"]] = int(item["floor"])
        TaskPlannerDialog(
            self,
            self.store.data.get("tasks", []),
            location_names,
            payload_names,
            profile_names,
            self.store.suggest_next_task_id,
            self._save_tasks,
            floor_map=floor_map,
            manual_single_payload_available=self._manual_task_amr_available(),
        )

    @undoable("Edit task generation")
    def manage_task_generation(self):
        locations = self.store.data.get("locations", [])
        location_names = sorted(x["name"] for x in locations)
        payload_names = sorted(x["name"] for x in self.store.data.get("payloads", []))
        profile_names = sorted(self.store.data.get("route_profiles", {}).keys())

        if hasattr(self.store, "task_generation"):
            task_generation = self.store.task_generation()
        else:
            task_generation = self.store.data.setdefault("task_generation", {})

        dialog = TaskGenerationSettingsDialog(
            self,
            task_generation,
            location_names,
            payload_names,
            profile_names,
            self.store.data.get("departments", []),
            self._save_task_generation,
        )
        dialog.exec()

    @undoable("Edit task generation")
    def _save_task_generation(self, config):
        if hasattr(self.store, "set_task_generation"):
            self.store.set_task_generation(config)
        else:
            self.store.data["task_generation"] = config
        self.set_status("Task generation parameters updated")

    @undoable("Edit route profiles")
    def manage_route_profiles(self):
        point_names = set(self.store.names_in_use()) | {
            x["name"] for x in self.store.data.get("locations", [])
        }
        lift_ids = {x["id"] for x in self.store.data.get("lifts", [])}
        floor_map = self.build_floor_map(self.store.data)
        dialog = RouteProfilesEditorV2(
            self,
            self.store.data.get("route_profiles", {}),
            point_names,
            lift_ids,
            self.store.data.get("corridors", {}).get("edges", []),
            self._save_route_profiles,
            floor_map=floor_map,
        )
        dialog.exec()

    @undoable("Edit route profiles")
    def _save_route_profiles(self, profiles):
        self.store.data["route_profiles"] = profiles
        self.set_status("Route profiles updated")

    def closeEvent(self, event):
        if not self._confirm_unsaved_changes():
            event.ignore()
            return
        self._dirty_timer.stop()
        self._recovery_timer.stop()
        if hasattr(self, 'playback_panel'):
            self.playback_panel.reset()
        self._discard_own_recovery()
        try:
            self._dxf_thread.quit()
            self._dxf_thread.wait(2000)
        except Exception:
            pass
        if self._project_cache and not self._dxf_thread.isRunning():
            for cache in self._project_cache:
                cache.cleanup()
            self._project_cache = None
        super().closeEvent(event)

    @undoable("Edit mass collections")
    def manage_mass_collections(self):
        dialog = MassCollectionListDialog(
            self,
            [loc["name"] for loc in self.store.data.get("locations", [])],
            [payload["name"] for payload in self.store.data.get("payloads", [])],
            self.store.data.setdefault("mass_collections", []),
            lambda items: self.store.data.__setitem__("mass_collections", items),
        )
        dialog.exec()

    @undoable("Edit waste streams")
    def manage_waste_streams(self):
        payload_names = sorted(x["name"] for x in self.store.data.get("payloads", []))
        items = list(self.store.data.get("waste_streams", []))
        dialog = WasteStreamListDialog(
            self, payload_names, items, self._save_waste_streams
        )
        dialog.exec()

    @undoable("Edit waste streams")
    def _save_waste_streams(self, items):
        self.store.data["waste_streams"] = items
        self.set_status("Waste streams updated")

    @undoable("Edit department locations")
    def manage_departments(self):
        location_names = sorted(x["name"] for x in self.store.data.get("locations", []))
        waste_stream_names = sorted(
            x["name"] for x in self.store.data.get("waste_streams", [])
        )
        dialog = DepartmentListDialog(
            self,
            self.store.data.get("departments", []),
            location_names,
            waste_stream_names,
            current_floor=self.floor_spin.value(),
            on_save=self._save_departments,
            suggest_department_id=self.store.suggest_next_department_id,
            group_resolver=lambda item: f"Floor {self.build_floor_map(self.store.data).get(item, 'Other')}",
            task_generation_categories=self.task_generation_category_pairs(),
        )
        dialog.exec()

    @undoable("Edit inventory spaces")
    def manage_location_spaces(self):
        dialog = LocationSpacesManagerDialog(self)
        dialog.exec()

    @undoable("Edit department locations")
    def _save_departments(self, items, *, id_changes=None):
        self.store.replace_departments(items, id_changes=id_changes)
        self.set_status("Departments updated")
        self.refresh_canvas()

    @undoable("Edit charging locations")
    def manage_charging_locations(self):
        location_names = sorted(x["name"] for x in self.store.data.get("locations", []))

        picker = MultiSelectPicker(
            self,
            "Charging Locations",
            location_names,
            selected=self.store.charge_locations(),
            group_resolver=lambda item: f"Floor {self.build_floor_map(self.store.data).get(item, 'Other')}",
        )

        if picker.exec() == QDialog.Accepted and picker.result is not None:
            self.store.set_charge_locations(sorted(picker.result))
            self.set_status(f"Updated {len(picker.result)} charging location(s)")

    def start_route_profile_graphical_selection(
        self,
        allowed_point_names,
        selected_nodes,
        callback,
        return_window=None,
    ):
        self.route_profile_selection_active = True
        self.route_profile_allowed_point_names = set(allowed_point_names or [])
        self.route_profile_selected_nodes = set(selected_nodes or [])
        self.route_profile_selection_callback = callback
        self.route_profile_return_window = return_window
        self.route_profile_selection_rect_start = None
        self.route_profile_selection_rect_item = None

        self._set_edit_mode("select_move")
        self.set_status(
            "Route profile graphical selection: click nodes, Ctrl-click to add/remove, "
            "Alt-drag for rectangle selection, Ctrl+Alt-drag to add to selection, "
            "right-click empty space to finish."
        )
        self.refresh_canvas()

    def _route_profile_pickable_point_at(self, x, y, floor):
        picked = self.find_nearest_point_name(x, y, floor, radius_world=1.0)
        if not picked:
            return None

        if picked not in self.route_profile_allowed_point_names:
            return None

        return picked

    def _finish_route_profile_graphical_selection(self):
        selected = set(self.route_profile_selected_nodes)

        callback = self.route_profile_selection_callback
        return_window = self.route_profile_return_window

        self.route_profile_selection_active = False
        self.route_profile_allowed_point_names = set()
        self.route_profile_selected_nodes = set()
        self.route_profile_selection_callback = None
        self.route_profile_return_window = None
        self.route_profile_selection_rect_start = None

        if self.route_profile_selection_rect_item is not None:
            try:
                self.scene.removeItem(self.route_profile_selection_rect_item)
            except Exception:
                pass
        self.route_profile_selection_rect_item = None

        self.set_status(f"Route profile selection applied: {len(selected)} node(s)")
        self.refresh_canvas()

        if callback:
            callback(selected)

        if return_window:
            return_window.show()
            return_window.raise_()
            return_window.activateWindow()

    def _cancel_route_profile_graphical_selection(self):
        return_window = self.route_profile_return_window

        self.route_profile_selection_active = False
        self.route_profile_allowed_point_names = set()
        self.route_profile_selected_nodes = set()
        self.route_profile_selection_callback = None
        self.route_profile_return_window = None
        self.route_profile_selection_rect_start = None

        if self.route_profile_selection_rect_item is not None:
            try:
                self.scene.removeItem(self.route_profile_selection_rect_item)
            except Exception:
                pass
        self.route_profile_selection_rect_item = None

        self.set_status("Route profile graphical selection cancelled")
        self.refresh_canvas()

        if return_window:
            return_window.show()
            return_window.raise_()
            return_window.activateWindow()


def main(project_path=None, *, load_drawings=True):
    app = QApplication.instance() or QApplication(sys.argv)
    from appearance import controller, user_settings
    controller(app, settings=user_settings())
    install_application_theme(app)
    window = AMRGraphEditor()
    window.show()
    if project_path is not None:
        window.load_json_file(str(project_path), load_drawings=load_drawings)
    return app.exec()
