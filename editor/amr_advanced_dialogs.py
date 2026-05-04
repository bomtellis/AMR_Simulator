import calendar
import json
from copy import deepcopy
from datetime import datetime, timedelta
from typing import Callable, Optional

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QAction, QBrush, QColor, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFormLayout, QGraphicsScene, QGraphicsView, QGridLayout, QGroupBox,
    QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMenu, QMessageBox, QPushButton, QScrollArea, QSizePolicy,
    QTableWidget, QTableWidgetItem, QTextEdit, QToolButton, QVBoxLayout, QWidget
)


class MultiSelectPicker(QDialog):
    def __init__(self, parent, title, options, selected=None, group_resolver=None, single_select=False):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(560, 640)
        self.options = sorted(list(options))
        self.selected = set(selected or [])
        self.group_resolver = group_resolver or (lambda item: "Other")
        self.single_select = single_select
        self.result = None
        self.checkboxes = {}
        self.visible = []
        self._build()
        self.refresh()

    def _build(self):
        layout = QVBoxLayout(self)
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter...")
        self.filter_edit.textChanged.connect(self.refresh)
        layout.addWidget(self.filter_edit)
        row = QHBoxLayout()
        for text, slot in [("All", self.select_all), ("None", self.clear_all), ("Select visible", self.select_visible), ("Clear visible", self.clear_visible)]:
            btn = QPushButton(text); btn.clicked.connect(slot); row.addWidget(btn)
        layout.addLayout(row)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        self.body = QWidget(); self.body_layout = QVBoxLayout(self.body); self.body_layout.addStretch(1)
        self.scroll.setWidget(self.body)
        layout.addWidget(self.scroll, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def refresh(self):
        while self.body_layout.count():
            item = self.body_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        filter_text = self.filter_edit.text().strip().lower()
        self.visible = []
        grouped = {}
        for item in self.options:
            if filter_text and filter_text not in item.lower():
                continue
            grouped.setdefault(self.group_resolver(item), []).append(item)
        for group_name in sorted(grouped):
            box = QGroupBox(f"{group_name} ({len(grouped[group_name])})")
            v = QVBoxLayout(box)
            tools = QHBoxLayout()
            all_btn = QPushButton("All"); none_btn = QPushButton("None")
            all_btn.clicked.connect(lambda _=False, items=list(grouped[group_name]): self._set_items(items, True))
            none_btn.clicked.connect(lambda _=False, items=list(grouped[group_name]): self._set_items(items, False))
            tools.addWidget(all_btn); tools.addWidget(none_btn); tools.addStretch(1); v.addLayout(tools)
            for name in sorted(grouped[group_name]):
                chk = self.checkboxes.get(name)
                if chk is None:
                    chk = QCheckBox(name); chk.setChecked(name in self.selected); self.checkboxes[name] = chk
                    if self.single_select:
                        chk.stateChanged.connect(lambda _state, n=name: self._single_checked(n))
                v.addWidget(chk); self.visible.append(name)
            self.body_layout.addWidget(box)
        self.body_layout.addStretch(1)

    def _single_checked(self, checked_name):
        if not self.checkboxes.get(checked_name).isChecked():
            return
        for name, chk in self.checkboxes.items():
            if name != checked_name:
                chk.blockSignals(True); chk.setChecked(False); chk.blockSignals(False)

    def _set_items(self, items, value):
        for name in items:
            if name in self.checkboxes:
                self.checkboxes[name].setChecked(value)

    def select_all(self): self._set_items(self.options, True)
    def clear_all(self): self._set_items(self.options, False)
    def select_visible(self): self._set_items(self.visible, True)
    def clear_visible(self): self._set_items(self.visible, False)

    def accept(self):
        self.result = [name for name, chk in self.checkboxes.items() if chk.isChecked()]
        super().accept()


class TaskFormDialog(QDialog):
    def __init__(self, parent, location_names, payload_names, profile_names, seed=None, default_task_id="T1", group_resolver=None):
        super().__init__(parent)
        self.setWindowTitle("Task")
        self.resize(620, 420)
        self.location_names = sorted(location_names)
        self.payload_names = sorted(payload_names)
        self.profile_names = list(profile_names)
        self.seed = seed or {}
        self.default_task_id = default_task_id
        self.group_resolver = group_resolver or (lambda item: "Other")
        self.result = None
        self._build()

    def _build(self):
        layout = QVBoxLayout(self); form = QFormLayout()
        self.id_edit = QLineEdit(str(self.seed.get("id", self.default_task_id)))
        self.pickup_edit = QLineEdit(str(self.seed.get("pickup", ""))); self.pickup_edit.setReadOnly(True)
        self.dropoff_edit = QLineEdit(str(self.seed.get("dropoff", ""))); self.dropoff_edit.setReadOnly(True)
        form.addRow("ID", self.id_edit)
        form.addRow("Pickup", self._pick_row(self.pickup_edit, self._pick_pickup))
        form.addRow("Dropoff", self._pick_row(self.dropoff_edit, self._pick_dropoff))
        self.payload_combo = QComboBox(); self.payload_combo.addItems(self.payload_names); self.payload_combo.setCurrentText(str(self.seed.get("payload", "")))
        self.release_edit = QLineEdit(str(self.seed.get("release_datetime", "2026-01-01T08:00:00")))
        self.target_edit = QLineEdit(str(self.seed.get("target_time", 300)))
        self.priority_edit = QLineEdit(str(self.seed.get("priority", 10)))
        self.labels_edit = QLineEdit(", ".join(self.seed.get("labels", [""])))
        self.profile_combo = QComboBox(); self.profile_combo.addItems(self.profile_names); self.profile_combo.setCurrentText(str(self.seed.get("route_profile", "")))
        form.addRow("Payload", self.payload_combo)
        form.addRow("Release datetime", self.release_edit)
        form.addRow("Target time", self.target_edit)
        form.addRow("Priority", self.priority_edit)
        form.addRow("Labels comma separated", self.labels_edit)
        form.addRow("Route profile", self.profile_combo)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel); buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _pick_row(self, edit, slot):
        w = QWidget(); h = QHBoxLayout(w); h.setContentsMargins(0,0,0,0); h.addWidget(edit, 1)
        btn = QPushButton("Select..."); btn.clicked.connect(slot); h.addWidget(btn); return w

    def _pick_pickup(self): self._pick_into(self.pickup_edit, "Select pickup")
    def _pick_dropoff(self): self._pick_into(self.dropoff_edit, "Select dropoff")
    def _pick_into(self, edit, title):
        dlg = MultiSelectPicker(self, title, self.location_names, selected=[edit.text()] if edit.text() else [], group_resolver=self.group_resolver, single_select=True)
        if dlg.exec() and dlg.result:
            edit.setText(dlg.result[0])

    def accept(self):
        try:
            if not self.id_edit.text().strip(): raise ValueError("ID is required")
            if not self.pickup_edit.text().strip(): raise ValueError("Pickup is required")
            if not self.dropoff_edit.text().strip(): raise ValueError("Dropoff is required")
            if not self.payload_combo.currentText().strip(): raise ValueError("Payload is required")
            self.result = {
                "id": self.id_edit.text().strip(),
                "pickup": self.pickup_edit.text().strip(),
                "dropoff": self.dropoff_edit.text().strip(),
                "payload": self.payload_combo.currentText().strip(),
                "release_datetime": self.release_edit.text().strip(),
                "target_time": int(self.target_edit.text()),
                "priority": int(self.priority_edit.text()),
                "labels": [x.strip() for x in self.labels_edit.text().split(",")],
                "route_profile": self.profile_combo.currentText().strip(),
            }
            super().accept()
        except Exception as exc:
            QMessageBox.critical(self, "Invalid task", str(exc))


class BulkOneToManyTaskDialog(QDialog):
    def __init__(self, parent, location_names, payload_names, profile_names, group_resolver=None, default_task_id="T1"):
        super().__init__(parent)
        self.setWindowTitle("Create One-to-Many Tasks")
        self.location_names = sorted(location_names); self.selected_dropoffs = []
        self.payload_names = sorted(payload_names); self.profile_names = list(profile_names)
        self.group_resolver = group_resolver or (lambda item: "Other")
        self.result = None
        self.default_task_id = default_task_id
        self._build()

    def _build(self):
        layout = QVBoxLayout(self); form = QFormLayout()
        self.id_edit = QLineEdit(self.default_task_id)
        self.pickup_combo = QComboBox(); self.pickup_combo.addItems(self.location_names)
        self.dropoff_label = QLabel("None selected"); pick = QPushButton("Select..."); pick.clicked.connect(self._pick_dropoffs)
        drop = QWidget(); h=QHBoxLayout(drop); h.setContentsMargins(0,0,0,0); h.addWidget(self.dropoff_label,1); h.addWidget(pick)
        self.payload_combo = QComboBox(); self.payload_combo.addItems(self.payload_names)
        self.release_edit = QLineEdit("2026-01-01T08:00:00"); self.target_edit = QLineEdit("300"); self.priority_edit = QLineEdit("10")
        self.labels_edit = QLineEdit(""); self.profile_combo = QComboBox(); self.profile_combo.addItems(self.profile_names)
        for label, widget in [("Base task ID", self.id_edit), ("Pickup", self.pickup_combo), ("Dropoffs", drop), ("Payload", self.payload_combo), ("Release datetime", self.release_edit), ("Target time", self.target_edit), ("Priority", self.priority_edit), ("Labels comma separated", self.labels_edit), ("Route profile", self.profile_combo)]:
            form.addRow(label, widget)
        layout.addLayout(form)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel); buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)

    def _pick_dropoffs(self):
        dlg = MultiSelectPicker(self, "Select dropoffs", self.location_names, selected=self.selected_dropoffs, group_resolver=self.group_resolver)
        if dlg.exec():
            self.selected_dropoffs = sorted(dlg.result or [])
            self.dropoff_label.setText(", ".join(self.selected_dropoffs[:4]) if len(self.selected_dropoffs) <= 4 else f"{len(self.selected_dropoffs)} selected")

    def accept(self):
        try:
            if not self.id_edit.text().strip(): raise ValueError("Base task ID is required")
            if not self.pickup_combo.currentText().strip(): raise ValueError("Pickup is required")
            if not self.selected_dropoffs: raise ValueError("Select at least one dropoff")
            if self.pickup_combo.currentText() in self.selected_dropoffs: raise ValueError("Pickup cannot also be a dropoff")
            labels = [x.strip() for x in self.labels_edit.text().split(",")] if self.labels_edit.text().strip() else [""]
            self.result = {"base_id": self.id_edit.text().strip(), "pickup": self.pickup_combo.currentText(), "dropoffs": list(self.selected_dropoffs), "payload": self.payload_combo.currentText(), "release_datetime": self.release_edit.text().strip(), "target_time": int(self.target_edit.text()), "priority": int(self.priority_edit.text()), "labels": labels, "route_profile": self.profile_combo.currentText().strip()}
            super().accept()
        except Exception as exc:
            QMessageBox.critical(self, "Invalid bulk task", str(exc))


class RouteProfilesEditorV2(QWidget):
    def __init__(self, master, profiles, point_names, lift_ids, corridor_edges, on_save, floor_map=None):
        super().__init__(master, Qt.Window)
        self.setWindowTitle("Route Profiles")
        self.resize(1200, 720)
        self.profiles = json.loads(json.dumps(profiles)); self.point_names=sorted(point_names); self.lift_ids=sorted(lift_ids)
        self.corridor_edges=corridor_edges; self.floor_map=floor_map or {}; self.on_save=on_save
        self.current_profile=None; self.allowed_lifts=[]; self.allowed_nodes=[]
        self._build(); self.refresh_profiles()

    def _build(self):
        layout=QHBoxLayout(self)
        left=QVBoxLayout(); self.profile_list=QListWidget(); self.profile_list.currentItemChanged.connect(self.on_profile_select); left.addWidget(self.profile_list,1)
        add=QPushButton("Add"); add.clicked.connect(self.add_profile); delete=QPushButton("Delete"); delete.clicked.connect(self.delete_profile); left.addWidget(add); left.addWidget(delete); layout.addLayout(left)
        right=QVBoxLayout(); layout.addLayout(right,1)
        right.addWidget(QLabel("Profile name")); self.name_edit=QLineEdit(); right.addWidget(self.name_edit)
        self.lifts_summary=QLabel("None"); self.nodes_summary=QLabel("None"); self.nodes_summary.setWordWrap(True)
        right.addLayout(self._summary_row("Allowed lifts", self.lifts_summary, self.pick_lifts))
        right.addLayout(self._summary_row("Allowed nodes", self.nodes_summary, self.pick_nodes))
        right.addWidget(QLabel("Allowed edges as JSON array pairs")); self.edges_text=QTextEdit(); right.addWidget(self.edges_text,1)
        row=QHBoxLayout(); gen=QPushButton("Generate from selected nodes"); gen.clicked.connect(self.fill_edges_from_nodes); clear=QPushButton("Clear edges"); clear.clicked.connect(lambda: self.edges_text.clear()); row.addWidget(gen); row.addWidget(clear); row.addStretch(1); right.addLayout(row)
        bottom=QHBoxLayout(); apply=QPushButton("Apply Changes"); apply.clicked.connect(self.apply_profile_changes); save=QPushButton("Save All"); save.clicked.connect(self.save_all); bottom.addWidget(apply); bottom.addStretch(1); bottom.addWidget(save); right.addLayout(bottom)

    def _summary_row(self, title, label, slot):
        row=QHBoxLayout(); row.addWidget(QLabel(title)); row.addWidget(label,1); btn=QPushButton("Pick"); btn.clicked.connect(slot); row.addWidget(btn); return row
    def summarize(self, values): return "None" if not values else (", ".join(values) if len(values)<=6 else f"{len(values)} selected")
    def _group_for_item(self, item):
        floor=self.floor_map.get(item); return "Other" if floor is None else f"Floor {floor}"
    def refresh_profiles(self):
        self.profile_list.clear(); self.profile_list.addItems(list(self.profiles.keys()))
        if self.profile_list.count(): self.profile_list.setCurrentRow(0)
    def add_profile(self):
        name, ok = QInputDialog.getText(self, "New profile", "Profile name:")
        if ok and name.strip():
            if name in self.profiles: QMessageBox.critical(self,"Duplicate","Profile already exists"); return
            self.profiles[name] = {"allowed_lifts": [], "allowed_nodes": [], "allowed_edges": []}; self.refresh_profiles()
    def delete_profile(self):
        item=self.profile_list.currentItem();
        if not item: return
        name=item.text()
        if name=="default": QMessageBox.critical(self,"Not allowed","Cannot delete default profile"); return
        del self.profiles[name]; self.refresh_profiles()
    def on_profile_select(self, item, _prev=None):
        if not item: return
        name=item.text(); self.current_profile=name; profile=self.profiles[name]
        self.name_edit.setText(name); self.allowed_lifts=list(profile.get("allowed_lifts", [])); self.allowed_nodes=list(profile.get("allowed_nodes", []))
        self.lifts_summary.setText(self.summarize(self.allowed_lifts)); self.nodes_summary.setText(self.summarize(self.allowed_nodes)); self.edges_text.setPlainText(json.dumps(profile.get("allowed_edges", []), indent=2))
    def pick_lifts(self):
        dlg=MultiSelectPicker(self,"Pick lifts",self.lift_ids,self.allowed_lifts,group_resolver=self._group_for_item)
        if dlg.exec(): self.allowed_lifts=sorted(dlg.result or []); self.lifts_summary.setText(self.summarize(self.allowed_lifts))
    def pick_nodes(self):
        dlg=MultiSelectPicker(self,"Pick nodes",self.point_names,self.allowed_nodes,group_resolver=self._group_for_item)
        if dlg.exec(): self.allowed_nodes=sorted(dlg.result or []); self.nodes_summary.setText(self.summarize(self.allowed_nodes))
    def fill_edges_from_nodes(self):
        allowed=set(self.allowed_nodes); edges=[[e["from"],e["to"]] for e in self.corridor_edges if e.get("from") in allowed and e.get("to") in allowed]
        self.edges_text.setPlainText(json.dumps(edges, indent=2))
    def apply_profile_changes(self):
        if not self.current_profile: return
        try:
            new_name=self.name_edit.text().strip();
            if not new_name: raise ValueError("Profile name is required")
            edges=json.loads(self.edges_text.toPlainText().strip() or "[]")
            if not isinstance(edges, list): raise ValueError("Allowed edges must be a JSON list")
            payload={"allowed_lifts":list(self.allowed_lifts),"allowed_nodes":list(self.allowed_nodes),"allowed_edges":edges}
            if new_name != self.current_profile:
                del self.profiles[self.current_profile]; self.profiles[new_name]=payload; self.current_profile=new_name; self.refresh_profiles()
            else: self.profiles[self.current_profile]=payload
        except Exception as exc: QMessageBox.critical(self,"Invalid profile",str(exc))
    def save_all(self): self.apply_profile_changes(); self.on_save(self.profiles); self.close()


class MultiDaySelectDialog(QDialog):
    def __init__(self, parent, initial_date=None):
        super().__init__(parent)
        self.setWindowTitle("Select target days"); self.resize(820, 560)
        base=initial_date or datetime.now(); self.display_year=base.year; self.display_month=base.month; self.selected_dates=set(); self.result=None; self.last_clicked_date=None
        self._build(); self.refresh()
    def _build(self):
        layout=QVBoxLayout(self); top=QHBoxLayout()
        for text, slot in [("◀", self.prev_month),("Today", self.go_to_today),("▶", self.next_month)]:
            b=QPushButton(text); b.clicked.connect(slot); top.addWidget(b)
        self.title_label=QLabel(); self.title_label.setStyleSheet("font-weight:bold"); top.addWidget(self.title_label); top.addStretch(1)
        sm=QPushButton("Select displayed month"); sm.clicked.connect(self.select_displayed_month); ca=QPushButton("Clear all"); ca.clicked.connect(self.clear_selection); top.addWidget(sm); top.addWidget(ca); layout.addLayout(top)
        self.grid_widget=QWidget(); self.grid=QGridLayout(self.grid_widget); layout.addWidget(self.grid_widget,1)
        bottom=QHBoxLayout(); self.summary=QLabel("No days selected"); bottom.addWidget(self.summary); bottom.addStretch(1)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel); buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); bottom.addWidget(buttons); layout.addLayout(bottom)
    def prev_month(self): self.display_year, self.display_month = (self.display_year-1,12) if self.display_month==1 else (self.display_year,self.display_month-1); self.refresh()
    def next_month(self): self.display_year, self.display_month = (self.display_year+1,1) if self.display_month==12 else (self.display_year,self.display_month+1); self.refresh()
    def go_to_today(self): t=datetime.now(); self.display_year=t.year; self.display_month=t.month; self.refresh()
    def clear_selection(self): self.selected_dates.clear(); self.refresh()
    def select_displayed_month(self):
        for d in calendar.Calendar(firstweekday=0).itermonthdates(self.display_year,self.display_month):
            if d.month==self.display_month: self.selected_dates.add(d.isoformat())
        self.refresh()
    def toggle_date(self, d, extend=False):
        if extend and self.last_clicked_date is not None:
            cur=min(self.last_clicked_date,d); end=max(self.last_clicked_date,d)
            while cur<=end: self.selected_dates.add(cur.isoformat()); cur+=timedelta(days=1)
        else:
            k=d.isoformat(); self.selected_dates.remove(k) if k in self.selected_dates else self.selected_dates.add(k)
        self.last_clicked_date=d; self.refresh()
    def refresh(self):
        while self.grid.count():
            item=self.grid.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self.title_label.setText(f"{calendar.month_name[self.display_month]} {self.display_year}")
        for c,name in enumerate(["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]): self.grid.addWidget(QLabel(name, alignment=Qt.AlignCenter),0,c)
        today=datetime.now().date(); days=list(calendar.Calendar(firstweekday=0).itermonthdates(self.display_year,self.display_month))[:42]
        for i,d in enumerate(days):
            r=(i//7)+1; c=i%7; btn=QPushButton((str(d.day)+(" •" if d==today else ""))); btn.setEnabled(d.month==self.display_month); btn.setCheckable(True); btn.setChecked(d.isoformat() in self.selected_dates)
            btn.clicked.connect(lambda _=False, day=d: self.toggle_date(day, bool(QApplicationKeyboard.shift())))
            self.grid.addWidget(btn,r,c)
        count=len(self.selected_dates); self.summary.setText("No days selected" if count==0 else (", ".join(sorted(self.selected_dates)) if count<=6 else f"{count} days selected"))
    def accept(self): self.result=sorted(self.selected_dates); super().accept()

class QApplicationKeyboard:
    @staticmethod
    def shift():
        from PySide6.QtWidgets import QApplication
        return QApplication.keyboardModifiers() & Qt.ShiftModifier


class TaskEditorWindow(QWidget):
    def __init__(self, master, items, location_names, payload_names, profile_names, suggest_task_id, on_save, floor_map=None):
        super().__init__(master, Qt.Window); self.setWindowTitle("Tasks"); self.resize(1200,520)
        self.items=items; self.location_names=location_names; self.payload_names=payload_names; self.profile_names=profile_names; self.suggest_task_id=suggest_task_id; self.on_save=on_save; self.floor_map=floor_map or {}
        self._build(); self.refresh()
    def _build(self):
        layout=QVBoxLayout(self); self.columns=["id","pickup","dropoff","payload","release_datetime","target_time","priority","labels","route_profile"]
        self.table=QTableWidget(0,len(self.columns)); self.table.setHorizontalHeaderLabels([c.replace("_"," ").title() for c in self.columns]); self.table.setSelectionBehavior(QAbstractItemView.SelectRows); self.table.setSelectionMode(QAbstractItemView.ExtendedSelection); self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive); self.table.doubleClicked.connect(lambda _idx: self.edit_item()); layout.addWidget(self.table)
        row=QHBoxLayout();
        for text,slot in [("Add",self.add_item),("Edit",self.edit_item),("Delete",self.delete_item),("Duplicate x Times",self._duplicate_selected_item),("One to Many",self._create_one_to_many_tasks),("Schedule Return Trip",self._schedule_return_trips)]:
            b=QPushButton(text); b.clicked.connect(slot); row.addWidget(b)
        row.addStretch(1); save=QPushButton("Save"); save.clicked.connect(self.save); row.addWidget(save); layout.addLayout(row)
    def _group_for_location(self,item): floor=self.floor_map.get(item); return "Other" if floor is None else f"Floor {floor}"
    def refresh(self):
        self.table.setRowCount(0)
        for item in self.items:
            r=self.table.rowCount(); self.table.insertRow(r)
            vals=[item.get("id",""),item.get("pickup",""),item.get("dropoff",""),item.get("payload",""),item.get("release_datetime",""),item.get("target_time",""),item.get("priority",""),", ".join(item.get("labels",[])),item.get("route_profile","")]
            for c,v in enumerate(vals): self.table.setItem(r,c,QTableWidgetItem(str(v)))
    def selected_rows(self): return sorted({idx.row() for idx in self.table.selectionModel().selectedRows()})
    def _next_task_id(self,reserved_ids=None):
        reserved_ids=set(reserved_ids or []); nums=[]
        for task in self.items:
            tid=str(task.get("id",""));
            if tid.startswith("T") and tid[1:].isdigit(): nums.append(int(tid[1:]))
        for tid in reserved_ids:
            tid=str(tid)
            if tid.startswith("T") and tid[1:].isdigit(): nums.append(int(tid[1:]))
        return f"T{max(nums, default=0)+1}"
    def add_item(self):
        d=TaskFormDialog(self,self.location_names,self.payload_names,self.profile_names,default_task_id=self._next_task_id(),group_resolver=self._group_for_location)
        if d.exec() and d.result: self.items.append(d.result); self.refresh()
    def edit_item(self):
        rows=self.selected_rows();
        if not rows: return
        idx=rows[0]; d=TaskFormDialog(self,self.location_names,self.payload_names,self.profile_names,seed=self.items[idx],default_task_id=self.items[idx].get("id",self._next_task_id()),group_resolver=self._group_for_location)
        if d.exec() and d.result: self.items[idx]=d.result; self.refresh()
    def delete_item(self):
        rows=self.selected_rows();
        if not rows: return
        for idx in reversed(rows): del self.items[idx]
        self.refresh()
    def save(self): self.on_save(self.items); self.close()
    def _duplicate_selected_item(self):
        rows=self.selected_rows();
        if not rows: QMessageBox.critical(self,"No task selected","Select a task to duplicate."); return
        count,ok=QInputDialog.getInt(self,"Duplicate task","How many copies do you want to create?",1,1)
        if not ok: return
        source=self.items[rows[0]]; reserved={str(t.get("id","")) for t in self.items}; insert_at=rows[0]+1
        new=[]
        for _ in range(count):
            cp=deepcopy(source); cp["id"]=self._next_task_id(reserved); reserved.add(cp["id"]); new.append(cp)
        for off,cp in enumerate(new): self.items.insert(insert_at+off,cp)
        self.refresh()
    def _create_one_to_many_tasks(self):
        d=BulkOneToManyTaskDialog(self,self.location_names,self.payload_names,self.profile_names,group_resolver=self._group_for_location,default_task_id=self._next_task_id())
        if not d.exec() or not d.result: return
        payload=d.result; reserved={str(t.get("id","")) for t in self.items}
        for dropoff in payload["dropoffs"]:
            new_id=self._next_task_id(reserved); reserved.add(new_id)
            self.items.append({"id":new_id,"pickup":payload["pickup"],"dropoff":dropoff,"payload":payload["payload"],"release_datetime":payload["release_datetime"],"target_time":payload["target_time"],"priority":payload["priority"],"labels":list(payload["labels"]),"route_profile":payload["route_profile"]})
        self.refresh()
    def _parse_return_delay(self,text):
        parts=(text or "").strip().split(":")
        if len(parts)!=3: raise ValueError("Delay must be in HH:MM:SS format")
        h,m,s=[int(x) for x in parts]; return timedelta(hours=h,minutes=m,seconds=s)
    def _schedule_return_trips(self):
        rows=self.selected_rows();
        if not rows: QMessageBox.critical(self,"No task selected","Select one or more tasks first."); return
        text,ok=QInputDialog.getText(self,"Return trip delay","Enter delay as HH:MM:SS",text="00:30:00")
        if not ok: return
        try: delay=self._parse_return_delay(text)
        except Exception as exc: QMessageBox.critical(self,"Invalid delay",str(exc)); return
        reserved={str(t.get("id","")) for t in self.items}
        for idx in rows:
            src=self.items[idx]; cp=deepcopy(src); cp["id"]=self._next_task_id(reserved); reserved.add(cp["id"]); cp["pickup"]=src.get("dropoff",""); cp["dropoff"]=src.get("pickup",""); cp["release_datetime"]=(datetime.fromisoformat(src.get("release_datetime","2026-01-01T08:00:00"))+delay).isoformat(timespec="seconds"); self.items.append(cp)
        self.refresh()


class TaskPlannerDialog(QWidget):
    def __init__(self, master, items, location_names, payload_names, profile_names, suggest_task_id, on_save, floor_map=None):
        super().__init__(master, Qt.Window); self.setWindowTitle("Task Planner"); self.resize(1450,760)
        self.items=items; self.location_names=sorted(location_names); self.payload_names=payload_names; self.profile_names=profile_names; self.suggest_task_id=suggest_task_id; self.on_save=on_save; self.floor_map=floor_map or {}; self.day_start=self._initial_day(); self.hour_width=90; self.row_height=38; self.header_height=36; self.left_width=220; self.selected_task_index=None; self.selected_row_name=None; self.copied_task=None; self.task_items={}; self._row_y_positions={}
        self.grouped_rows=self._build_grouped_rows(); self._build(); self.refresh_matrix()
    def _build(self):
        layout=QVBoxLayout(self); top=QHBoxLayout()
        for text,slot in [("◀ Day",lambda:self.shift_day(-1)),("Today",self.go_to_today),("Day ▶",lambda:self.shift_day(1)),("Copy Day...",self.copy_day_tasks_to_other_day),("- Hour Width",lambda:self.adjust_hour_width(-10)),("+ Hour Width",lambda:self.adjust_hour_width(10)),("Copy",self.copy_selected_task),("Paste",self.paste_to_selected_row),("Delete",self.delete_selected_task)]:
            b=QPushButton(text); b.clicked.connect(slot); top.addWidget(b)
        top.addStretch(1); self.date_label=QLabel(); self.date_label.setStyleSheet("font-weight:bold"); top.addWidget(self.date_label); save=QPushButton("Save"); save.clicked.connect(self.save); top.addWidget(save); layout.addLayout(top)
        self.scene=QGraphicsScene(self); self.view=QGraphicsView(self.scene); self.view.setContextMenuPolicy(Qt.CustomContextMenu); self.view.customContextMenuRequested.connect(self.on_context_menu); self.view.mouseDoubleClickEvent=self._view_double_click; self.view.mousePressEvent=self._view_mouse_press; layout.addWidget(self.view,1)
        self.status=QLabel("Double-click a cell to create a task."); layout.addWidget(self.status)
    def _build_grouped_rows(self):
        grouped={}
        for name in self.location_names:
            floor=self.floor_map.get(name); grouped.setdefault(f"Floor {floor}" if floor is not None else "Other",[]).append(name)
        ordered=[]
        for group in sorted(grouped): ordered.append(("header",group)); ordered += [("row",x) for x in sorted(grouped[group])]
        return ordered
    def _group_for_location(self,item): floor=self.floor_map.get(item); return "Other" if floor is None else f"Floor {floor}"
    def _initial_day(self):
        for task in self.items:
            dt=self._task_datetime(task)
            if dt: return dt.replace(hour=0,minute=0,second=0,microsecond=0)
        return datetime.now().replace(hour=0,minute=0,second=0,microsecond=0)
    def _task_datetime(self,task):
        try: return datetime.fromisoformat(str(task.get("release_datetime","")).strip())
        except Exception: return None
    def _format_cell_datetime(self,dt): return dt.replace(second=0,microsecond=0).isoformat(timespec="seconds")
    def _snap_to_grid(self,dt): return dt.replace(minute=(dt.minute//15)*15,second=0,microsecond=0)
    def shift_day(self,d): self.day_start+=timedelta(days=d); self.refresh_matrix()
    def go_to_today(self): self.day_start=datetime.now().replace(hour=0,minute=0,second=0,microsecond=0); self.refresh_matrix()
    def adjust_hour_width(self,d): self.hour_width=max(40,min(220,self.hour_width+d)); self.refresh_matrix()
    def save(self): self.on_save(self.items); self.status.setText("Tasks saved")
    def _next_task_id(self,reserved_ids=None):
        reserved=set(reserved_ids or []); nums=[]
        for t in list(self.items)+[{"id":x} for x in reserved]:
            tid=str(t.get("id",""));
            if tid.startswith("T") and tid[1:].isdigit(): nums.append(int(tid[1:]))
        return f"T{max(nums, default=0)+1}"
    def _visible_tasks_for_day(self): return [(i,t) for i,t in enumerate(self.items) if (dt:=self._task_datetime(t)) and self.day_start<=dt<self.day_start+timedelta(days=1)]
    def _calculate_row_lane_counts(self):
        slots={}; counts={}
        for idx,t in self._visible_tasks_for_day():
            dt=self._task_datetime(t); row=str(t.get("dropoff","")).strip();
            if row: slots.setdefault((row,dt.replace(second=0,microsecond=0)),[]).append(idx)
        for (row,_),ids in slots.items(): counts[row]=max(counts.get(row,1),len(ids))
        return counts
    def refresh_matrix(self):
        self.scene.clear(); self.task_items={}; self._row_y_positions={}; self.date_label.setText(self.day_start.strftime("%A %d %B %Y"))
        total_width=self.left_width+24*self.hour_width; counts=self._calculate_row_lane_counts(); y=self.header_height
        self.scene.addRect(0,0,self.left_width,self.header_height,QPen(QColor("#c8c8c8")),QBrush(QColor("#ececec"))); self.scene.addText("Departments / drop-off").setPos(10,8)
        for h in range(24):
            x=self.left_width+h*self.hour_width; self.scene.addRect(x,0,self.hour_width,self.header_height,QPen(QColor("#d6d6d6")),QBrush(QColor("#f4f4f4" if h%2==0 else "#fbfbfb"))); self.scene.addText(f"{h:02d}:00").setPos(x+self.hour_width/2-18,8)
        row_index=0
        for kind,name in self.grouped_rows:
            if kind=="header":
                self.scene.addRect(0,y,total_width,24,QPen(QColor("#b0b7c5")),QBrush(QColor("#d0d7e5"))); self.scene.addText(name).setPos(10,y+3); y+=24; continue
            lanes=max(1,counts.get(name,1)); rh=max(self.row_height,lanes*18); self._row_y_positions[name]=(y,y+rh,rh)
            self.scene.addRect(0,y,self.left_width,rh,QPen(QColor("#d6d6d6")),QBrush(QColor("#dcecff" if self.selected_row_name==name else "#f5f5f5"))); self.scene.addText(name).setPos(10,y+rh/2-10)
            self.scene.addRect(self.left_width,y,total_width-self.left_width,rh,QPen(QColor("#ececec")),QBrush(QColor("#ffffff" if row_index%2==0 else "#fafafa")))
            for h in range(25): self.scene.addLine(self.left_width+h*self.hour_width,y,self.left_width+h*self.hour_width,y+rh,QPen(QColor("#e2e2e2")))
            y+=rh; row_index+=1
        self._draw_task_blocks(); self.scene.setSceneRect(QRectF(0,0,total_width,max(y,500)))
    def _draw_task_blocks(self):
        visible=self._visible_tasks_for_day(); slots={}; lane_lookup={}; row_counts={}
        for idx,t in visible:
            dt=self._task_datetime(t); row=str(t.get("dropoff","")).strip();
            if row: slots.setdefault((row,dt.replace(second=0,microsecond=0)),[]).append((idx,t))
        for (row,_),items in slots.items():
            items.sort(key=lambda it:(self._task_datetime(it[1]) or self.day_start, str(it[1].get("id","")))) ; row_counts[row]=max(row_counts.get(row,1),len(items))
            for lane,(idx,_t) in enumerate(items): lane_lookup[idx]=lane
        colors=["#2e7d32","#1976d2","#f57c00","#7b1fa2","#c2185b","#00838f","#6d4c41","#455a64"]
        for idx,t in visible:
            dt=self._task_datetime(t); row=str(t.get("dropoff","")).strip()
            if row not in self._row_y_positions: continue
            lane_count=max(1,row_counts.get(row,1)); lane=lane_lookup.get(idx,0); x1=self.left_width+((dt-self.day_start).total_seconds()/3600)*self.hour_width; w=max(30,(max(int(t.get("target_time",300)),60)/3600)*self.hour_width)
            ry1,ry2,rh=self._row_y_positions[row]; inner_top=ry1+4; lane_h=max(12,(rh-8)/lane_count); y1=inner_top+lane*lane_h; y2=y1+lane_h-2
            item=self.scene.addRect(x1,y1,w,y2-y1,QPen(QColor("#000000" if idx==self.selected_task_index else "#244028"),2 if idx==self.selected_task_index else 1),QBrush(QColor(colors[lane%len(colors)]))); item.setData(0,idx); txt=self.scene.addText(f"{t.get('id','')}  {t.get('pickup','')}"); txt.setDefaultTextColor(QColor("white")); txt.setPos(x1+4,y1); txt.setData(0,idx); self.task_items[idx]=(item,txt)
    def _scene_pos(self,event): return self.view.mapToScene(event.position().toPoint() if hasattr(event,'position') else event.pos())
    def _task_at(self,pos):
        for item in self.scene.items(pos):
            data=item.data(0)
            if data is not None: return int(data)
        return None
    def _row_name_from_y(self,y):
        for name,(y1,y2,_rh) in self._row_y_positions.items():
            if y1<=y<y2: return name
        return None
    def _datetime_from_x(self,x):
        if x<self.left_width: return self.day_start
        minutes=max(0,min(int(round(((x-self.left_width)/self.hour_width)*60)),24*60-1)); return self._snap_to_grid(self.day_start+timedelta(minutes=minutes))
    def _view_mouse_press(self,event):
        pos=self._scene_pos(event); idx=self._task_at(pos); self.selected_row_name=self._row_name_from_y(pos.y())
        if idx is not None: self.selected_task_index=idx; self.status.setText(f"Selected {self.items[idx].get('id','')} → {self.items[idx].get('dropoff','')}")
        else: self.selected_task_index=None; self.status.setText(f"Selected destination row: {self.selected_row_name}" if self.selected_row_name else "")
        self.refresh_matrix(); QGraphicsView.mousePressEvent(self.view,event)
    def _view_double_click(self,event):
        pos=self._scene_pos(event); idx=self._task_at(pos)
        if idx is not None:
            d=TaskFormDialog(self,self.location_names,self.payload_names,self.profile_names,seed=deepcopy(self.items[idx]),default_task_id=self.items[idx].get("id",self._next_task_id()),group_resolver=self._group_for_location)
            if d.exec() and d.result: self.items[idx]=d.result; self.selected_task_index=idx; self.selected_row_name=d.result.get("dropoff",""); self.refresh_matrix()
            return
        row=self._row_name_from_y(pos.y())
        if row: self._create_task_for_row(row,self._datetime_from_x(pos.x()))
    def on_context_menu(self,point):
        pos=self.view.mapToScene(point); idx=self._task_at(pos); row=self._row_name_from_y(pos.y()); when=self._datetime_from_x(pos.x()); menu=QMenu(self)
        if idx is not None:
            self.selected_task_index=idx; menu.addAction("Copy", self.copy_selected_task); menu.addAction("Delete", self.delete_selected_task)
        else:
            if self.copied_task and row: menu.addAction(f"Paste to {row}", lambda: self.paste_to_row(row,when))
            if row: menu.addAction(f"Create task at {row}", lambda: self._create_task_for_row(row,when))
        if not menu.isEmpty(): menu.exec(self.view.mapToGlobal(point))
    def _create_task_for_row(self,row,when=None):
        d=TaskFormDialog(self,self.location_names,self.payload_names,self.profile_names,seed={"dropoff":row,"release_datetime":self._format_cell_datetime(when or self.day_start)},default_task_id=self._next_task_id(),group_resolver=self._group_for_location)
        if d.exec() and d.result: self.items.append(d.result); self.selected_task_index=len(self.items)-1; self.selected_row_name=row; self.refresh_matrix()
    def copy_selected_task(self):
        if self.selected_task_index is None: self.status.setText("Select a task first"); return
        self.copied_task=deepcopy(self.items[self.selected_task_index]); self.status.setText(f"Copied {self.copied_task.get('id','')}")
    def paste_to_selected_row(self):
        if not self.selected_row_name: self.status.setText("Select a destination row first"); return
        self.paste_to_row(self.selected_row_name)
    def paste_to_row(self,row,when=None):
        if not self.copied_task: self.status.setText("Copy a task first"); return
        cp=deepcopy(self.copied_task); cp["id"]=self._next_task_id(); cp["dropoff"]=row
        if when is not None: cp["release_datetime"]=self._format_cell_datetime(when)
        self.items.append(cp); self.selected_task_index=len(self.items)-1; self.selected_row_name=row; self.refresh_matrix()
    def delete_selected_task(self):
        if self.selected_task_index is None: return
        del self.items[self.selected_task_index]; self.selected_task_index=None; self.refresh_matrix()
    def _tasks_for_exact_day(self,day): return [(i,t,self._task_datetime(t)) for i,t in enumerate(self.items) if (dt:=self._task_datetime(t)) and day<=dt<day+timedelta(days=1)]
    def copy_day_tasks_to_other_day(self):
        source=self.day_start; src=self._tasks_for_exact_day(source)
        if not src: QMessageBox.information(self,"Copy day","There are no tasks on the displayed day to copy."); return
        picker=MultiDaySelectDialog(self,initial_date=source+timedelta(days=1))
        if not picker.exec() or not picker.result: return
        targets=[]
        for text in picker.result:
            dt=datetime.fromisoformat(text).replace(hour=0,minute=0,second=0,microsecond=0)
            if dt!=source: targets.append(dt)
        reserved={str(t.get("id","")) for t in self.items}; created=[]
        for target in targets:
            for _idx,task,_dt in src:
                cp=deepcopy(task); offset=self._task_datetime(task)-source; cp["id"]=self._next_task_id(reserved); reserved.add(cp["id"]); cp["release_datetime"]=(target+offset).replace(second=0,microsecond=0).isoformat(timespec="seconds"); created.append(cp)
        self.items.extend(created); self.status.setText(f"Copied {len(src)} task(s) to {len(targets)} day(s)"); self.refresh_matrix()
