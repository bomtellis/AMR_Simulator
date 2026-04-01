from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import ezdxf

from PySide6.QtCore import Qt, QDateTime, QTimer, QRectF
from PySide6.QtGui import QAction, QBrush, QColor, QPainterPath, QPen
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFormLayout,
    QGraphicsEllipseItem,
    QGraphicsItemGroup,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QComboBox,
    QSlider,
    QDateTimeEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
    QCheckBox,
)


# ----------------------------
# Data models
# ----------------------------


@dataclass
class Node:
    node_id: str
    x: float
    y: float
    floor: int
    node_type: str = ""


@dataclass
class Edge:
    edge_id: str
    from_node: str
    to_node: str
    floor: int
    edge_type: str = ""


@dataclass
class Segment:
    amr_id: str
    start_time: pd.Timestamp
    end_time: pd.Timestamp
    start_x: float
    start_y: float
    start_floor: int
    end_x: float
    end_y: float
    end_floor: int
    status: str
    task_id: str = ""


@dataclass
class AMRPosition:
    amr_id: str
    x: float
    y: float
    floor: int
    status: str
    task_id: str


# ----------------------------
# Loaders
# ----------------------------


class GraphData:
    def __init__(self) -> None:
        self.nodes: Dict[str, Node] = {}
        self.edges: List[Edge] = []
        self.floors: List[int] = []

    @classmethod
    def from_json(cls, path: str | Path) -> "GraphData":
        obj = cls()
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        for n in data.get("nodes", []):
            node = Node(
                node_id=str(n["id"]),
                x=float(n["x"]),
                y=float(n["y"]),
                floor=int(n["floor"]),
                node_type=str(n.get("type", "")),
            )
            obj.nodes[node.node_id] = node

        for e in data.get("edges", []):
            edge = Edge(
                edge_id=str(e["id"]),
                from_node=str(e["from"]),
                to_node=str(e["to"]),
                floor=int(e["floor"]),
                edge_type=str(e.get("type", "")),
            )
            obj.edges.append(edge)

        obj.floors = sorted({n.floor for n in obj.nodes.values()})
        return obj


class SimulationData:
    REQUIRED_COLUMNS = {
        "amr_id",
        "start_time",
        "end_time",
        "start_x",
        "start_y",
        "start_floor",
        "end_x",
        "end_y",
        "end_floor",
        "status",
    }

    def __init__(self) -> None:
        self.df: pd.DataFrame = pd.DataFrame()
        self.start_time: Optional[pd.Timestamp] = None
        self.end_time: Optional[pd.Timestamp] = None
        self.segments: List[Segment] = []

    @classmethod
    def from_csv(cls, path: str | Path) -> "SimulationData":
        obj = cls()
        df = pd.read_csv(path)

        missing = cls.REQUIRED_COLUMNS - set(df.columns)
        if missing:
            raise ValueError(f"CSV missing columns: {sorted(missing)}")

        df["start_time"] = pd.to_datetime(df["start_time"])
        df["end_time"] = pd.to_datetime(df["end_time"])

        numeric_cols = [
            "start_x",
            "start_y",
            "start_floor",
            "end_x",
            "end_y",
            "end_floor",
        ]
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col])

        if "task_id" not in df.columns:
            df["task_id"] = ""

        df = df.sort_values(["start_time", "amr_id"]).reset_index(drop=True)

        obj.df = df
        obj.start_time = df["start_time"].min()
        obj.end_time = df["end_time"].max()

        obj.segments = [
            Segment(
                amr_id=str(row["amr_id"]),
                start_time=row["start_time"],
                end_time=row["end_time"],
                start_x=float(row["start_x"]),
                start_y=float(row["start_y"]),
                start_floor=int(row["start_floor"]),
                end_x=float(row["end_x"]),
                end_y=float(row["end_y"]),
                end_floor=int(row["end_floor"]),
                status=str(row["status"]),
                task_id=str(row["task_id"]),
            )
            for _, row in df.iterrows()
        ]
        return obj

    def get_active_positions(self, timestamp: pd.Timestamp) -> List[AMRPosition]:
        """
        Returns one interpolated position per AMR that has an active segment at timestamp.
        If multiple rows overlap for an AMR, latest-starting row wins.
        """
        if self.df.empty:
            return []

        active = self.df[
            (self.df["start_time"] <= timestamp) & (self.df["end_time"] >= timestamp)
        ].copy()

        if active.empty:
            return []

        active = active.sort_values(["amr_id", "start_time"])
        active = active.groupby("amr_id", as_index=False).tail(1)

        results: List[AMRPosition] = []

        for _, row in active.iterrows():
            start = row["start_time"]
            end = row["end_time"]

            duration = (end - start).total_seconds()
            if duration <= 0:
                ratio = 1.0
            else:
                ratio = (timestamp - start).total_seconds() / duration
                ratio = max(0.0, min(1.0, ratio))

            start_floor = int(row["start_floor"])
            end_floor = int(row["end_floor"])

            # If changing floor, hold start floor for first half and end floor for second half.
            # This is a simple placeholder for lift logic.
            if start_floor == end_floor:
                floor = start_floor
            else:
                floor = start_floor if ratio < 0.5 else end_floor

            x = (
                float(row["start_x"])
                + (float(row["end_x"]) - float(row["start_x"])) * ratio
            )
            y = (
                float(row["start_y"])
                + (float(row["end_y"]) - float(row["start_y"])) * ratio
            )

            results.append(
                AMRPosition(
                    amr_id=str(row["amr_id"]),
                    x=x,
                    y=y,
                    floor=floor,
                    status=str(row["status"]),
                    task_id=str(row.get("task_id", "")),
                )
            )

        return results


# ----------------------------
# Graphics
# ----------------------------


class FloorScene(QGraphicsScene):
    def __init__(self) -> None:
        super().__init__()
        self.setBackgroundBrush(QBrush(QColor(250, 250, 250)))

        self.dxf_group = QGraphicsItemGroup()
        self.edge_group = QGraphicsItemGroup()
        self.node_group = QGraphicsItemGroup()
        self.amr_group = QGraphicsItemGroup()

        self.addItem(self.dxf_group)
        self.addItem(self.edge_group)
        self.addItem(self.node_group)
        self.addItem(self.amr_group)

        self.show_graph_overlay = True
        self.flip_y = True
        self.amr_items: Dict[str, List] = {}

    def clear_group(self, group: QGraphicsItemGroup) -> None:
        for child in group.childItems():
            self.removeItem(child)

    def _map_y(self, y: float) -> float:
        return -y if self.flip_y else y

    def load_dxf(self, dxf_path: str | Path) -> None:
        self.clear_group(self.dxf_group)

        doc = ezdxf.readfile(str(dxf_path))
        msp = doc.modelspace()

        pen = QPen(QColor(180, 180, 180))
        pen.setWidthF(0.0)

        bounds = []

        for entity in msp:
            dxftype = entity.dxftype()

            try:
                if dxftype == "LINE":
                    x1, y1, _ = entity.dxf.start
                    x2, y2, _ = entity.dxf.end
                    item = QGraphicsLineItem(x1, self._map_y(y1), x2, self._map_y(y2))
                    item.setPen(pen)
                    self.dxf_group.addToGroup(item)
                    bounds.extend([(x1, self._map_y(y1)), (x2, self._map_y(y2))])

                elif dxftype in ("LWPOLYLINE", "POLYLINE"):
                    points = []
                    if dxftype == "LWPOLYLINE":
                        points = [(p[0], p[1]) for p in entity.get_points()]
                        closed = entity.closed
                    else:
                        points = [
                            (v.dxf.location.x, v.dxf.location.y)
                            for v in entity.vertices
                        ]
                        closed = entity.is_closed

                    if len(points) >= 2:
                        path = QPainterPath()
                        x0, y0 = points[0]
                        path.moveTo(x0, self._map_y(y0))
                        bounds.append((x0, self._map_y(y0)))

                        for x, y in points[1:]:
                            path.lineTo(x, self._map_y(y))
                            bounds.append((x, self._map_y(y)))

                        if closed:
                            path.closeSubpath()

                        item = QGraphicsPathItem(path)
                        item.setPen(pen)
                        self.dxf_group.addToGroup(item)

            except Exception:
                # Skip unsupported/problematic entities in this starter version
                continue

        if bounds:
            xs = [p[0] for p in bounds]
            ys = [p[1] for p in bounds]
            self.setSceneRect(
                QRectF(
                    min(xs) - 100,
                    min(ys) - 100,
                    max(xs) - min(xs) + 200,
                    max(ys) - min(ys) + 200,
                )
            )

    def draw_graph(self, graph: Optional[GraphData], floor: int) -> None:
        self.clear_group(self.edge_group)
        self.clear_group(self.node_group)

        if graph is None or not self.show_graph_overlay:
            return

        edge_pen = QPen(QColor(100, 140, 220))
        edge_pen.setWidthF(0.0)

        node_pen = QPen(QColor(20, 20, 20))
        node_brush = QBrush(QColor(255, 210, 80))

        for edge in graph.edges:
            if edge.floor != floor:
                continue
            n1 = graph.nodes.get(edge.from_node)
            n2 = graph.nodes.get(edge.to_node)
            if n1 is None or n2 is None:
                continue

            item = QGraphicsLineItem(n1.x, self._map_y(n1.y), n2.x, self._map_y(n2.y))
            item.setPen(edge_pen)
            self.edge_group.addToGroup(item)

        for node in graph.nodes.values():
            if node.floor != floor:
                continue

            r = 10
            item = QGraphicsEllipseItem(
                node.x - r / 2, self._map_y(node.y) - r / 2, r, r
            )
            item.setPen(node_pen)
            item.setBrush(node_brush)
            self.node_group.addToGroup(item)

    def draw_amrs(self, positions: List[AMRPosition], floor: int) -> None:
        self.clear_group(self.amr_group)
        self.amr_items.clear()

        for pos in positions:
            if pos.floor != floor:
                continue

            r = 28
            ellipse = QGraphicsEllipseItem(
                pos.x - r / 2, self._map_y(pos.y) - r / 2, r, r
            )

            status = pos.status.lower()
            if status == "lift":
                brush = QBrush(QColor(180, 120, 255))
            elif status == "waiting":
                brush = QBrush(QColor(255, 200, 0))
            elif status == "loading":
                brush = QBrush(QColor(0, 190, 140))
            else:
                brush = QBrush(QColor(220, 60, 60))

            ellipse.setBrush(brush)
            ellipse.setPen(QPen(QColor(30, 30, 30)))

            label = QGraphicsSimpleTextItem(pos.amr_id)
            label.setPos(pos.x + 18, self._map_y(pos.y) - 18)

            self.amr_group.addToGroup(ellipse)
            self.amr_group.addToGroup(label)

            self.amr_items[pos.amr_id] = [ellipse, label]


class GraphicsView(QGraphicsView):
    def __init__(self, scene: QGraphicsScene) -> None:
        super().__init__(scene)
        self.setRenderHints(self.renderHints())
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.zoom_factor = 1.15

    def wheelEvent(self, event) -> None:
        if event.angleDelta().y() > 0:
            self.scale(self.zoom_factor, self.zoom_factor)
        else:
            self.scale(1 / self.zoom_factor, 1 / self.zoom_factor)


# ----------------------------
# Main window
# ----------------------------


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("AMR Playback Visualiser")
        self.resize(1400, 900)

        self.graph: Optional[GraphData] = None
        self.simulation: Optional[SimulationData] = None
        self.floor_dxf_files: Dict[int, str] = {}

        self.current_floor = 0
        self.current_time: Optional[pd.Timestamp] = None

        self.timer = QTimer(self)
        self.timer.setInterval(100)  # 10 fps
        self.timer.timeout.connect(self.on_tick)

        self.playback_speed_seconds = 1

        self.scene = FloorScene()
        self.view = GraphicsView(self.scene)

        self._build_ui()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)

        form = QFormLayout()

        self.floor_combo = QComboBox()
        self.floor_combo.currentIndexChanged.connect(self.on_floor_changed)
        form.addRow("Floor", self.floor_combo)

        self.datetime_edit = QDateTimeEdit()
        self.datetime_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.datetime_edit.setCalendarPopup(True)
        self.datetime_edit.dateTimeChanged.connect(self.on_datetime_changed)
        form.addRow("Simulation Time", self.datetime_edit)

        self.speed_spin = QSpinBox()
        self.speed_spin.setRange(-300, 300)
        self.speed_spin.setValue(1)
        self.speed_spin.setSingleStep(1)
        self.speed_spin.setToolTip(
            "Playback speed in simulation seconds per tick. Negative rewinds."
        )
        self.speed_spin.valueChanged.connect(self.on_speed_changed)
        form.addRow("Speed", self.speed_spin)

        self.overlay_checkbox = QCheckBox("Show graph overlay")
        self.overlay_checkbox.setChecked(True)
        self.overlay_checkbox.stateChanged.connect(self.on_overlay_changed)
        form.addRow("", self.overlay_checkbox)

        left_layout.addLayout(form)

        controls_layout = QHBoxLayout()

        self.rewind_btn = QPushButton("⏪")
        self.rewind_btn.clicked.connect(self.rewind)

        self.step_back_btn = QPushButton("◀")
        self.step_back_btn.clicked.connect(self.step_back)

        self.play_btn = QPushButton("Play")
        self.play_btn.clicked.connect(self.toggle_play)

        self.step_forward_btn = QPushButton("▶")
        self.step_forward_btn.clicked.connect(self.step_forward)

        self.fast_forward_btn = QPushButton("⏩")
        self.fast_forward_btn.clicked.connect(self.fast_forward)

        controls_layout.addWidget(self.rewind_btn)
        controls_layout.addWidget(self.step_back_btn)
        controls_layout.addWidget(self.play_btn)
        controls_layout.addWidget(self.step_forward_btn)
        controls_layout.addWidget(self.fast_forward_btn)

        left_layout.addLayout(controls_layout)

        self.timeline_slider = QSlider(Qt.Horizontal)
        self.timeline_slider.setRange(0, 0)
        self.timeline_slider.valueChanged.connect(self.on_slider_changed)
        left_layout.addWidget(self.timeline_slider)

        self.info_label = QLabel("No data loaded.")
        self.info_label.setWordWrap(True)
        left_layout.addWidget(self.info_label)

        left_layout.addStretch()

        main_layout.addWidget(left_panel, 0)
        main_layout.addWidget(self.view, 1)

        self._build_menu()

    def _build_menu(self) -> None:
        menu = self.menuBar()

        file_menu = menu.addMenu("File")

        load_graph_action = QAction("Load Graph JSON", self)
        load_graph_action.triggered.connect(self.load_graph_json)
        file_menu.addAction(load_graph_action)

        load_csv_action = QAction("Load Simulation CSV", self)
        load_csv_action.triggered.connect(self.load_sim_csv)
        file_menu.addAction(load_csv_action)

        load_dxf_action = QAction("Load DXF for Floor...", self)
        load_dxf_action.triggered.connect(self.load_floor_dxf)
        file_menu.addAction(load_dxf_action)

    # ----------------------------
    # Load actions
    # ----------------------------

    def load_graph_json(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select graph JSON", "", "JSON Files (*.json)"
        )
        if not path:
            return
        try:
            self.graph = GraphData.from_json(path)
            self.refresh_floor_list()
            self.refresh_scene()
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Failed to load graph JSON:\n{exc}")

    def load_sim_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select simulation CSV", "", "CSV Files (*.csv)"
        )
        if not path:
            return
        try:
            self.simulation = SimulationData.from_csv(path)
            if self.simulation.start_time is not None:
                self.set_current_time(self.simulation.start_time)
                total_seconds = int(
                    (
                        self.simulation.end_time - self.simulation.start_time
                    ).total_seconds()
                )
                self.timeline_slider.setRange(0, max(total_seconds, 0))
            self.refresh_scene()
        except Exception as exc:
            QMessageBox.critical(
                self, "Error", f"Failed to load simulation CSV:\n{exc}"
            )

    def load_floor_dxf(self) -> None:
        if self.floor_combo.count() == 0:
            QMessageBox.warning(
                self, "No floors", "Load graph JSON first or add floors manually."
            )
            return

        floor = int(self.floor_combo.currentText())
        path, _ = QFileDialog.getOpenFileName(
            self, f"Select DXF for floor {floor}", "", "DXF Files (*.dxf)"
        )
        if not path:
            return

        self.floor_dxf_files[floor] = path
        if floor == self.current_floor:
            self.refresh_scene()

    # ----------------------------
    # UI events
    # ----------------------------

    def on_floor_changed(self) -> None:
        if self.floor_combo.currentText():
            self.current_floor = int(self.floor_combo.currentText())
            self.refresh_scene()

    def on_datetime_changed(self) -> None:
        if self.simulation is None:
            return
        dt = self.datetime_edit.dateTime().toPython()
        self.current_time = pd.Timestamp(dt)
        self.sync_slider_from_time()
        self.refresh_scene()

    def on_speed_changed(self) -> None:
        self.playback_speed_seconds = self.speed_spin.value()

    def on_overlay_changed(self) -> None:
        self.scene.show_graph_overlay = self.overlay_checkbox.isChecked()
        self.refresh_scene()

    def on_slider_changed(self) -> None:
        if self.simulation is None or self.simulation.start_time is None:
            return
        seconds = self.timeline_slider.value()
        ts = self.simulation.start_time + pd.to_timedelta(seconds, unit="s")
        self.set_current_time(ts, update_slider=False)
        self.refresh_scene()

    def on_tick(self) -> None:
        if self.simulation is None or self.current_time is None:
            return

        next_time = self.current_time + pd.to_timedelta(
            self.playback_speed_seconds, unit="s"
        )

        if (
            self.simulation.start_time is not None
            and next_time < self.simulation.start_time
        ):
            next_time = self.simulation.start_time
            self.timer.stop()
            self.play_btn.setText("Play")

        if (
            self.simulation.end_time is not None
            and next_time > self.simulation.end_time
        ):
            next_time = self.simulation.end_time
            self.timer.stop()
            self.play_btn.setText("Play")

        self.set_current_time(next_time)
        self.refresh_scene()

    # ----------------------------
    # Playback controls
    # ----------------------------

    def toggle_play(self) -> None:
        if self.timer.isActive():
            self.timer.stop()
            self.play_btn.setText("Play")
        else:
            self.timer.start()
            self.play_btn.setText("Pause")

    def step_back(self) -> None:
        if self.current_time is None:
            return
        self.set_current_time(self.current_time - pd.to_timedelta(1, unit="s"))
        self.refresh_scene()

    def step_forward(self) -> None:
        if self.current_time is None:
            return
        self.set_current_time(self.current_time + pd.to_timedelta(1, unit="s"))
        self.refresh_scene()

    def rewind(self) -> None:
        self.speed_spin.setValue(-5)

    def fast_forward(self) -> None:
        self.speed_spin.setValue(5)

    # ----------------------------
    # Helpers
    # ----------------------------

    def refresh_floor_list(self) -> None:
        existing = []
        if self.graph is not None:
            existing.extend(self.graph.floors)
        existing.extend(self.floor_dxf_files.keys())

        floors = sorted(set(existing))
        self.floor_combo.blockSignals(True)
        self.floor_combo.clear()
        for f in floors:
            self.floor_combo.addItem(str(f))
        self.floor_combo.blockSignals(False)

        if floors:
            self.current_floor = floors[0]
            self.floor_combo.setCurrentText(str(self.current_floor))

    def set_current_time(
        self, timestamp: pd.Timestamp, update_slider: bool = True
    ) -> None:
        if self.simulation is None:
            return

        if self.simulation.start_time is not None:
            timestamp = max(timestamp, self.simulation.start_time)
        if self.simulation.end_time is not None:
            timestamp = min(timestamp, self.simulation.end_time)

        self.current_time = timestamp

        qdt = QDateTime(
            timestamp.year,
            timestamp.month,
            timestamp.day,
            timestamp.hour,
            timestamp.minute,
            timestamp.second,
        )
        self.datetime_edit.blockSignals(True)
        self.datetime_edit.setDateTime(qdt)
        self.datetime_edit.blockSignals(False)

        if update_slider:
            self.sync_slider_from_time()

    def sync_slider_from_time(self) -> None:
        if (
            self.simulation is None
            or self.current_time is None
            or self.simulation.start_time is None
        ):
            return
        seconds = int((self.current_time - self.simulation.start_time).total_seconds())
        self.timeline_slider.blockSignals(True)
        self.timeline_slider.setValue(max(0, seconds))
        self.timeline_slider.blockSignals(False)

    def refresh_scene(self) -> None:
        # Load floor DXF if present
        dxf_path = self.floor_dxf_files.get(self.current_floor)
        if dxf_path:
            self.scene.load_dxf(dxf_path)

        # Draw graph overlay
        self.scene.draw_graph(self.graph, self.current_floor)

        # Draw AMRs
        floor_positions: List[AMRPosition] = []
        total_active = 0

        if self.simulation is not None and self.current_time is not None:
            all_positions = self.simulation.get_active_positions(self.current_time)
            total_active = len(all_positions)
            floor_positions = [
                p for p in all_positions if p.floor == self.current_floor
            ]

        self.scene.draw_amrs(floor_positions, self.current_floor)

        current_time_str = (
            str(self.current_time) if self.current_time is not None else "N/A"
        )
        self.info_label.setText(
            f"Floor: {self.current_floor}\n"
            f"Simulation time: {current_time_str}\n"
            f"AMRs on floor: {len(floor_positions)}\n"
            f"Total active AMRs: {total_active}\n"
            f"DXF loaded: {'Yes' if dxf_path else 'No'}"
        )

        self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
