import json
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from copy import deepcopy
import calendar
from datetime import datetime, timedelta


class MultiSelectPicker(tk.Toplevel):
    def __init__(self, parent, title, options, selected=None, group_resolver=None):
        super().__init__(parent)
        self.title(title)
        self.geometry("520x620")
        self.result = None
        self.options = list(options)
        self.selected = set(selected or [])
        self.group_resolver = group_resolver or (lambda item: "Other")
        self.vars = {}
        self.visible = []

        outer = ttk.Frame(self, padding=8)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(2, weight=1)

        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", lambda *_: self.refresh())
        ttk.Entry(outer, textvariable=self.filter_var).grid(
            row=0, column=0, sticky="ew"
        )

        tools = ttk.Frame(outer)
        tools.grid(row=1, column=0, sticky="ew", pady=(8, 6))
        ttk.Button(tools, text="All", command=self.select_all).pack(side="left")
        ttk.Button(tools, text="None", command=self.clear_all).pack(side="left", padx=4)
        ttk.Button(tools, text="Select visible", command=self.select_visible).pack(
            side="left", padx=4
        )
        ttk.Button(tools, text="Clear visible", command=self.clear_visible).pack(
            side="left"
        )

        self.canvas = tk.Canvas(outer)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=self.canvas.yview)
        self.frame = ttk.Frame(self.canvas)

        self.frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )

        self.canvas.create_window((0, 0), window=self.frame, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)

        self.canvas.grid(row=2, column=0, sticky="nsew")
        scrollbar.grid(row=2, column=1, sticky="ns")

        btns = ttk.Frame(outer)
        btns.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(btns, text="OK", command=self.finish).pack(side="right")

        self.refresh()

    def refresh(self):
        for child in self.frame.winfo_children():
            child.destroy()

        filter_text = self.filter_var.get().strip().lower()
        self.visible = []

        grouped = {}
        for item in self.options:
            if filter_text and filter_text not in item.lower():
                continue
            group_name = self.group_resolver(item)
            grouped.setdefault(group_name, []).append(item)

        def make_group_toggle(items, value):
            def _toggle():
                for name in items:
                    if name in self.vars:
                        self.vars[name].set(value)
                    else:
                        self.vars[name] = tk.BooleanVar(value=value)

            return _toggle

        row = 0
        for group_name in sorted(grouped.keys(), key=str):
            items = sorted(grouped[group_name])

            header = ttk.Frame(self.frame)
            header.grid(row=row, column=0, sticky="ew", pady=(6, 2))
            header.columnconfigure(0, weight=1)

            ttk.Label(header, text=f"{group_name} ({len(items)})").grid(
                row=0, column=0, sticky="w"
            )
            ttk.Button(
                header, text="All", width=5, command=make_group_toggle(items, True)
            ).grid(row=0, column=1, padx=2)
            ttk.Button(
                header, text="None", width=5, command=make_group_toggle(items, False)
            ).grid(row=0, column=2)
            row += 1

            for item in items:
                var = self.vars.get(item)
                if var is None:
                    var = tk.BooleanVar(value=(item in self.selected))
                    self.vars[item] = var

                chk = ttk.Checkbutton(self.frame, text=item, variable=var)
                chk.grid(row=row, column=0, sticky="w", padx=(18, 0))
                self.visible.append(item)
                row += 1

    def select_all(self):
        for item in self.options:
            var = self.vars.get(item)
            if var is None:
                self.vars[item] = tk.BooleanVar(value=True)
            else:
                var.set(True)

    def clear_all(self):
        for item in self.options:
            var = self.vars.get(item)
            if var is None:
                self.vars[item] = tk.BooleanVar(value=False)
            else:
                var.set(False)

    def select_visible(self):
        for item in self.visible:
            if item in self.vars:
                self.vars[item].set(True)

    def clear_visible(self):
        for item in self.visible:
            if item in self.vars:
                self.vars[item].set(False)

    def finish(self):
        self.result = [item for item, var in self.vars.items() if var.get()]
        self.destroy()


class RouteProfilesEditorV2(tk.Toplevel):
    def __init__(
        self,
        master,
        profiles,
        point_names,
        lift_ids,
        corridor_edges,
        on_save,
        floor_map=None,
    ):
        super().__init__(master)
        self.title("Route Profiles")
        self.geometry("1200x720")
        self.profiles = json.loads(json.dumps(profiles))
        self.point_names = sorted(point_names)
        self.lift_ids = sorted(lift_ids)
        self.corridor_edges = corridor_edges
        self.floor_map = floor_map or {}
        self.on_save = on_save
        self.current_profile = None
        self.allowed_lifts = []
        self.allowed_nodes = []

        outer = ttk.Frame(self, padding=8)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(0, weight=1)

        left = ttk.Frame(outer)
        left.grid(row=0, column=0, sticky="ns")
        right = ttk.Frame(outer)
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        right.columnconfigure(0, weight=1)
        right.rowconfigure(5, weight=1)

        self.profile_list = tk.Listbox(left, width=24)
        self.profile_list.pack(fill="y", expand=True)
        self.profile_list.bind("<<ListboxSelect>>", self.on_profile_select)

        btns = ttk.Frame(left)
        btns.pack(fill="x", pady=(8, 0))
        ttk.Button(btns, text="Add", command=self.add_profile).pack(fill="x")
        ttk.Button(btns, text="Delete", command=self.delete_profile).pack(
            fill="x", pady=4
        )

        ttk.Label(right, text="Profile name").grid(row=0, column=0, sticky="w")
        self.name_var = tk.StringVar()
        ttk.Entry(right, textvariable=self.name_var).grid(row=1, column=0, sticky="ew")

        lifts_row = ttk.Frame(right)
        lifts_row.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        lifts_row.columnconfigure(1, weight=1)
        ttk.Label(lifts_row, text="Allowed lifts").grid(row=0, column=0, sticky="w")
        self.lifts_summary_var = tk.StringVar(value="None")
        ttk.Label(lifts_row, textvariable=self.lifts_summary_var).grid(
            row=0, column=1, sticky="w"
        )
        ttk.Button(lifts_row, text="Pick", command=self.pick_lifts).grid(
            row=0, column=2
        )

        nodes_row = ttk.Frame(right)
        nodes_row.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        nodes_row.columnconfigure(1, weight=1)
        ttk.Label(nodes_row, text="Allowed nodes").grid(row=0, column=0, sticky="w")
        self.nodes_summary_var = tk.StringVar(value="None")
        ttk.Label(nodes_row, textvariable=self.nodes_summary_var, wraplength=700).grid(
            row=0, column=1, sticky="w"
        )
        ttk.Button(nodes_row, text="Pick", command=self.pick_nodes).grid(
            row=0, column=2
        )

        ttk.Label(right, text="Allowed edges as JSON array pairs").grid(
            row=4, column=0, sticky="w", pady=(10, 0)
        )
        self.edges_text = tk.Text(right, height=14)
        self.edges_text.grid(row=5, column=0, sticky="nsew")

        edge_btns = ttk.Frame(right)
        edge_btns.grid(row=6, column=0, sticky="ew", pady=(6, 0))
        ttk.Button(
            edge_btns,
            text="Generate from selected nodes",
            command=self.fill_edges_from_nodes,
        ).pack(side="left")
        ttk.Button(
            edge_btns,
            text="Clear edges",
            command=lambda: self.edges_text.delete("1.0", "end"),
        ).pack(side="left", padx=4)

        lower = ttk.Frame(right)
        lower.grid(row=7, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(
            lower, text="Apply Changes", command=self.apply_profile_changes
        ).pack(side="left")
        ttk.Button(lower, text="Save All", command=self.save_all).pack(side="right")

        for name in self.profiles.keys():
            self.profile_list.insert("end", name)
        if self.profiles:
            self.profile_list.selection_set(0)
            self.on_profile_select()

    def summarize(self, values):
        if not values:
            return "None"
        if len(values) <= 6:
            return ", ".join(values)
        return f"{len(values)} selected"

    def add_profile(self):
        name = simpledialog.askstring("New profile", "Profile name:", parent=self)
        if not name:
            return
        if name in self.profiles:
            messagebox.showerror("Duplicate", "Profile already exists", parent=self)
            return
        self.profiles[name] = {
            "allowed_lifts": [],
            "allowed_nodes": [],
            "allowed_edges": [],
        }
        self.profile_list.insert("end", name)

    def delete_profile(self):
        sel = self.profile_list.curselection()
        if not sel:
            return
        name = self.profile_list.get(sel[0])
        if name == "default":
            messagebox.showerror(
                "Not allowed", "Cannot delete default profile", parent=self
            )
            return
        del self.profiles[name]
        self.profile_list.delete(sel[0])
        self.current_profile = None

    def pick_lifts(self):
        picker = MultiSelectPicker(
            self,
            "Pick lifts",
            self.lift_ids,
            self.allowed_lifts,
            group_resolver=self._group_for_item,
        )

        self.wait_window(picker)

        if picker.result is not None:
            self.allowed_lifts = sorted(picker.result)
            self.lifts_summary_var.set(self.summarize(self.allowed_lifts))

    def pick_nodes(self):
        picker = MultiSelectPicker(
            self,
            "Pick nodes",
            self.point_names,
            self.allowed_nodes,
            group_resolver=self._group_for_item,
        )

        self.wait_window(picker)

        if picker.result is not None:
            self.allowed_nodes = sorted(picker.result)
            self.nodes_summary_var.set(self.summarize(self.allowed_nodes))

    def fill_edges_from_nodes(self):
        profile_edges = []
        allowed = set(self.allowed_nodes)
        for edge in self.corridor_edges:
            if edge["from"] in allowed and edge["to"] in allowed:
                profile_edges.append([edge["from"], edge["to"]])
        self.edges_text.delete("1.0", "end")
        self.edges_text.insert("1.0", json.dumps(profile_edges, indent=2))

    def on_profile_select(self, event=None):
        sel = self.profile_list.curselection()
        if not sel:
            return
        name = self.profile_list.get(sel[0])
        self.current_profile = name
        profile = self.profiles[name]
        self.name_var.set(name)
        self.allowed_lifts = list(profile.get("allowed_lifts", []))
        self.allowed_nodes = list(profile.get("allowed_nodes", []))
        self.lifts_summary_var.set(self.summarize(self.allowed_lifts))
        self.nodes_summary_var.set(self.summarize(self.allowed_nodes))
        self.edges_text.delete("1.0", "end")
        self.edges_text.insert(
            "1.0", json.dumps(profile.get("allowed_edges", []), indent=2)
        )

    def apply_profile_changes(self):
        if not self.current_profile:
            return
        try:
            new_name = self.name_var.get().strip()
            if not new_name:
                raise ValueError("Profile name is required")
            edges = json.loads(self.edges_text.get("1.0", "end").strip() or "[]")
            if not isinstance(edges, list):
                raise ValueError("Allowed edges must be a JSON list")
            payload = {
                "allowed_lifts": list(self.allowed_lifts),
                "allowed_nodes": list(self.allowed_nodes),
                "allowed_edges": edges,
            }
            if new_name != self.current_profile:
                self.profiles[new_name] = payload
                del self.profiles[self.current_profile]
                idx = self.profile_list.curselection()[0]
                self.profile_list.delete(idx)
                self.profile_list.insert(idx, new_name)
                self.profile_list.selection_set(idx)
                self.current_profile = new_name
            else:
                self.profiles[self.current_profile] = payload
        except Exception as exc:
            messagebox.showerror("Invalid profile", str(exc), parent=self)

    def save_all(self):
        self.apply_profile_changes()
        self.on_save(self.profiles)
        self.destroy()

    def _group_for_item(self, item):
        floor = self.floor_map.get(item)
        if floor is None:
            return "Other"
        return f"Floor {floor}"


class TaskFormDialog(simpledialog.Dialog):
    def __init__(
        self,
        parent,
        location_names,
        payload_names,
        profile_names,
        seed=None,
        default_task_id="T1",
        group_resolver=None,
    ):
        self.location_names = location_names
        self.payload_names = payload_names
        self.profile_names = profile_names
        self.seed = seed or {}
        self.default_task_id = default_task_id
        self.group_resolver = group_resolver or (lambda item: "Other")
        self.result = None
        super().__init__(parent, "Task")

    def body(self, master):
        ttk.Label(master, text="ID").grid(row=0, column=0, sticky="w")
        self.id_var = tk.StringVar(value=self.seed.get("id", self.default_task_id))
        ttk.Entry(master, textvariable=self.id_var).grid(row=0, column=1, sticky="ew")

        ttk.Label(master, text="Pickup").grid(row=1, column=0, sticky="w")
        pickup_row = ttk.Frame(master)
        pickup_row.grid(row=1, column=1, sticky="ew")
        pickup_row.columnconfigure(0, weight=1)

        self.pickup_var = tk.StringVar(value=self.seed.get("pickup", ""))
        ttk.Entry(pickup_row, textvariable=self.pickup_var, state="readonly").grid(
            row=0, column=0, sticky="ew"
        )
        ttk.Button(pickup_row, text="Select...", command=self._pick_pickup).grid(
            row=0, column=1, padx=(8, 0)
        )

        ttk.Label(master, text="Dropoff").grid(row=2, column=0, sticky="w")
        dropoff_row = ttk.Frame(master)
        dropoff_row.grid(row=2, column=1, sticky="ew")
        dropoff_row.columnconfigure(0, weight=1)

        self.dropoff_var = tk.StringVar(value=self.seed.get("dropoff", ""))
        ttk.Entry(dropoff_row, textvariable=self.dropoff_var, state="readonly").grid(
            row=0, column=0, sticky="ew"
        )
        ttk.Button(dropoff_row, text="Select...", command=self._pick_dropoff).grid(
            row=0, column=1, padx=(8, 0)
        )

        ttk.Label(master, text="Payload").grid(row=3, column=0, sticky="w")
        self.payload_var = tk.StringVar(value=self.seed.get("payload", ""))
        ttk.Combobox(
            master,
            textvariable=self.payload_var,
            values=self.payload_names,
            state="readonly",
        ).grid(row=3, column=1, sticky="ew")

        ttk.Label(master, text="Release datetime").grid(row=4, column=0, sticky="w")
        self.release_var = tk.StringVar(
            value=self.seed.get("release_datetime", "2026-01-01T08:00:00")
        )
        ttk.Entry(master, textvariable=self.release_var).grid(
            row=4, column=1, sticky="ew"
        )

        ttk.Label(master, text="Target time").grid(row=5, column=0, sticky="w")
        self.target_var = tk.StringVar(value=str(self.seed.get("target_time", 300)))
        ttk.Entry(master, textvariable=self.target_var).grid(
            row=5, column=1, sticky="ew"
        )

        ttk.Label(master, text="Priority").grid(row=6, column=0, sticky="w")
        self.priority_var = tk.StringVar(value=str(self.seed.get("priority", 10)))
        ttk.Entry(master, textvariable=self.priority_var).grid(
            row=6, column=1, sticky="ew"
        )

        ttk.Label(master, text="Labels comma separated").grid(
            row=7, column=0, sticky="w"
        )
        self.labels_var = tk.StringVar(value=", ".join(self.seed.get("labels", [""])))
        ttk.Entry(master, textvariable=self.labels_var).grid(
            row=7, column=1, sticky="ew"
        )

        ttk.Label(master, text="Route profile").grid(row=8, column=0, sticky="w")
        self.route_profile_var = tk.StringVar(value=self.seed.get("route_profile", ""))
        ttk.Combobox(
            master,
            textvariable=self.route_profile_var,
            values=self.profile_names,
            state="readonly",
        ).grid(row=8, column=1, sticky="ew")

        master.columnconfigure(1, weight=1)
        return master

    def validate(self):
        try:
            if not self.id_var.get().strip():
                raise ValueError("ID is required")
            if not self.pickup_var.get().strip():
                raise ValueError("Pickup is required")
            if not self.dropoff_var.get().strip():
                raise ValueError("Dropoff is required")
            if not self.payload_var.get().strip():
                raise ValueError("Payload is required")
            int(self.target_var.get())
            int(self.priority_var.get())
            return True
        except Exception as exc:
            messagebox.showerror("Invalid task", str(exc), parent=self)
            return False

    def apply(self):
        labels = [x.strip() for x in self.labels_var.get().split(",")]
        self.result = {
            "id": self.id_var.get().strip(),
            "pickup": self.pickup_var.get().strip(),
            "dropoff": self.dropoff_var.get().strip(),
            "payload": self.payload_var.get().strip(),
            "release_datetime": self.release_var.get().strip(),
            "target_time": int(self.target_var.get()),
            "priority": int(self.priority_var.get()),
            "labels": labels,
            "route_profile": self.route_profile_var.get().strip(),
        }

    def _pick_pickup(self):
        picker = MultiSelectPicker(
            self,
            "Select pickup",
            self.location_names,
            selected=[self.pickup_var.get()] if self.pickup_var.get() else [],
            group_resolver=self.group_resolver,
        )
        self.wait_window(picker)
        if picker.result:
            self.pickup_var.set(picker.result[0])

    def _pick_dropoff(self):
        picker = MultiSelectPicker(
            self,
            "Select dropoff",
            self.location_names,
            selected=[self.dropoff_var.get()] if self.dropoff_var.get() else [],
            group_resolver=self.group_resolver,
        )
        self.wait_window(picker)
        if picker.result:
            self.dropoff_var.set(picker.result[0])


class BulkOneToManyTaskDialog(simpledialog.Dialog):
    def __init__(
        self,
        parent,
        location_names,
        payload_names,
        profile_names,
        group_resolver=None,
        default_task_id="T1",
    ):
        self.location_names = sorted(location_names)
        self.payload_names = sorted(payload_names)
        self.profile_names = list(profile_names)
        self.group_resolver = group_resolver or (lambda item: "Other")
        self.default_task_id = default_task_id
        self.selected_dropoffs = []
        self.result = None
        super().__init__(parent, "Create One-to-Many Tasks")

    def body(self, master):
        ttk.Label(master, text="Base task ID").grid(row=0, column=0, sticky="w")
        self.id_var = tk.StringVar(value=self.default_task_id)
        ttk.Entry(master, textvariable=self.id_var).grid(row=0, column=1, sticky="ew")

        ttk.Label(master, text="Pickup").grid(row=1, column=0, sticky="w")
        self.pickup_var = tk.StringVar()
        ttk.Combobox(
            master,
            textvariable=self.pickup_var,
            values=self.location_names,
            state="readonly",
        ).grid(row=1, column=1, sticky="ew")

        ttk.Label(master, text="Dropoffs").grid(row=2, column=0, sticky="w")
        dropoff_row = ttk.Frame(master)
        dropoff_row.grid(row=2, column=1, sticky="ew")
        dropoff_row.columnconfigure(0, weight=1)

        self.dropoff_summary_var = tk.StringVar(value="None selected")
        ttk.Label(
            dropoff_row,
            textvariable=self.dropoff_summary_var,
            wraplength=320,
        ).grid(row=0, column=0, sticky="w")

        ttk.Button(
            dropoff_row,
            text="Select...",
            command=self._pick_dropoffs,
        ).grid(row=0, column=1, padx=(8, 0))

        ttk.Label(master, text="Payload").grid(row=3, column=0, sticky="w")
        self.payload_var = tk.StringVar()
        ttk.Combobox(
            master,
            textvariable=self.payload_var,
            values=self.payload_names,
            state="readonly",
        ).grid(row=3, column=1, sticky="ew")

        ttk.Label(master, text="Release datetime").grid(row=4, column=0, sticky="w")
        self.release_var = tk.StringVar(value="2026-01-01T08:00:00")
        ttk.Entry(master, textvariable=self.release_var).grid(
            row=4, column=1, sticky="ew"
        )

        ttk.Label(master, text="Target time").grid(row=5, column=0, sticky="w")
        self.target_var = tk.StringVar(value="300")
        ttk.Entry(master, textvariable=self.target_var).grid(
            row=5, column=1, sticky="ew"
        )

        ttk.Label(master, text="Priority").grid(row=6, column=0, sticky="w")
        self.priority_var = tk.StringVar(value="10")
        ttk.Entry(master, textvariable=self.priority_var).grid(
            row=6, column=1, sticky="ew"
        )

        ttk.Label(master, text="Labels comma separated").grid(
            row=7, column=0, sticky="w"
        )
        self.labels_var = tk.StringVar(value="")
        ttk.Entry(master, textvariable=self.labels_var).grid(
            row=7, column=1, sticky="ew"
        )

        ttk.Label(master, text="Route profile").grid(row=8, column=0, sticky="w")
        self.route_profile_var = tk.StringVar(value="")
        ttk.Combobox(
            master,
            textvariable=self.route_profile_var,
            values=self.profile_names,
            state="readonly",
        ).grid(row=8, column=1, sticky="ew")

        master.columnconfigure(1, weight=1)
        return master

    def _pick_dropoffs(self):
        picker = MultiSelectPicker(
            self,
            "Select dropoffs",
            self.location_names,
            selected=self.selected_dropoffs,
            group_resolver=self.group_resolver,
        )
        self.wait_window(picker)
        if picker.result is not None:
            self.selected_dropoffs = sorted(picker.result)
            if self.selected_dropoffs:
                if len(self.selected_dropoffs) <= 4:
                    self.dropoff_summary_var.set(", ".join(self.selected_dropoffs))
                else:
                    self.dropoff_summary_var.set(
                        f"{len(self.selected_dropoffs)} selected"
                    )
            else:
                self.dropoff_summary_var.set("None selected")

    def validate(self):
        try:
            if not self.id_var.get().strip():
                raise ValueError("Base task ID is required")
            if not self.pickup_var.get().strip():
                raise ValueError("Pickup is required")
            if not self.payload_var.get().strip():
                raise ValueError("Payload is required")
            if not self.selected_dropoffs:
                raise ValueError("Select at least one dropoff")
            if self.pickup_var.get().strip() in self.selected_dropoffs:
                raise ValueError("Pickup cannot also be a dropoff")
            int(self.target_var.get())
            int(self.priority_var.get())
            return True
        except Exception as exc:
            messagebox.showerror("Invalid bulk task", str(exc), parent=self)
            return False

    def apply(self):
        labels = (
            [x.strip() for x in self.labels_var.get().split(",")]
            if self.labels_var.get().strip()
            else [""]
        )
        self.result = {
            "base_id": self.id_var.get().strip(),
            "pickup": self.pickup_var.get().strip(),
            "dropoffs": list(self.selected_dropoffs),
            "payload": self.payload_var.get().strip(),
            "release_datetime": self.release_var.get().strip(),
            "target_time": int(self.target_var.get()),
            "priority": int(self.priority_var.get()),
            "labels": labels,
            "route_profile": self.route_profile_var.get().strip(),
        }


class MultiDaySelectDialog(tk.Toplevel):
    def __init__(self, parent, initial_date=None):
        super().__init__(parent)
        self.title("Select target days")
        self.geometry("820x560")
        self.transient(parent)
        self.grab_set()

        base = initial_date or datetime.now()
        self.display_year = base.year
        self.display_month = base.month
        self.selected_dates = set()
        self.result = None

        self.last_clicked_date = None

        outer = ttk.Frame(self, padding=8)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)

        header = ttk.Frame(outer)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Button(header, text="◀", command=self.prev_month).pack(side="left")
        ttk.Button(header, text="Today", command=self.go_to_today).pack(
            side="left", padx=4
        )
        ttk.Button(header, text="▶", command=self.next_month).pack(side="left")

        self.title_var = tk.StringVar()
        ttk.Label(header, textvariable=self.title_var, font=("Arial", 11, "bold")).pack(
            side="left", padx=12
        )

        ttk.Button(
            header,
            text="Select displayed month",
            command=self.select_displayed_month,
        ).pack(side="right")
        ttk.Button(
            header,
            text="Clear all",
            command=self.clear_selection,
        ).pack(side="right", padx=4)

        self.calendar_frame = ttk.Frame(outer)
        self.calendar_frame.grid(row=1, column=0, sticky="nsew")
        self.calendar_frame.columnconfigure(0, weight=1)
        self.calendar_frame.rowconfigure(1, weight=1)

        footer = ttk.Frame(outer)
        footer.grid(row=2, column=0, sticky="ew", pady=(8, 0))

        self.summary_var = tk.StringVar(value="No days selected")
        ttk.Label(footer, textvariable=self.summary_var).pack(side="left")

        ttk.Button(footer, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(footer, text="OK", command=self.finish).pack(side="right", padx=4)

        self.refresh()

    def prev_month(self):
        if self.display_month == 1:
            self.display_month = 12
            self.display_year -= 1
        else:
            self.display_month -= 1
        self.refresh()

    def next_month(self):
        if self.display_month == 12:
            self.display_month = 1
            self.display_year += 1
        else:
            self.display_month += 1
        self.refresh()

    def go_to_today(self):
        today = datetime.now()
        self.display_year = today.year
        self.display_month = today.month
        self.refresh()

    def clear_selection(self):
        self.selected_dates.clear()
        self.refresh()

    def select_displayed_month(self):
        cal = calendar.Calendar(firstweekday=0)
        for dt in cal.itermonthdates(self.display_year, self.display_month):
            if dt.month == self.display_month:
                self.selected_dates.add(dt.isoformat())
        self.refresh()

    def toggle_date(self, date_obj, extend_range=False):
        key = date_obj.isoformat()

        if extend_range and self.last_clicked_date is not None:
            start_date = min(self.last_clicked_date, date_obj)
            end_date = max(self.last_clicked_date, date_obj)
            current = start_date
            while current <= end_date:
                self.selected_dates.add(current.isoformat())
                current = current + timedelta(days=1)
        else:
            if key in self.selected_dates:
                self.selected_dates.remove(key)
            else:
                self.selected_dates.add(key)

        self.last_clicked_date = date_obj
        self.refresh()

    def on_day_button_click(self, date_obj, event=None):
        extend_range = bool(event and (event.state & 0x0001))
        self.toggle_date(date_obj, extend_range=extend_range)
        return "break"

    def refresh(self):
        for child in self.calendar_frame.winfo_children():
            child.destroy()

        self.title_var.set(
            f"{calendar.month_name[self.display_month]} {self.display_year}"
        )

        header = ttk.Frame(self.calendar_frame)
        header.grid(row=0, column=0, sticky="ew")
        for col in range(7):
            header.columnconfigure(col, weight=1)

        for col, day_name in enumerate(
            ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        ):
            ttk.Label(header, text=day_name, anchor="center").grid(
                row=0, column=col, sticky="ew", padx=2, pady=2
            )

        grid = ttk.Frame(self.calendar_frame)
        grid.grid(row=1, column=0, sticky="nsew")
        for col in range(7):
            grid.columnconfigure(col, weight=1)
        for row in range(6):
            grid.rowconfigure(row, weight=1)

        cal = calendar.Calendar(firstweekday=0)
        month_days = list(cal.itermonthdates(self.display_year, self.display_month))

        today = datetime.now().date()

        for index, date_obj in enumerate(month_days[:42]):
            row = index // 7
            col = index % 7
            in_month = date_obj.month == self.display_month
            is_today = date_obj == today
            is_selected = date_obj.isoformat() in self.selected_dates

            text = str(date_obj.day)
            if is_today:
                text = f"{date_obj.day} •"

            btn = tk.Button(
                grid,
                text=text,
                relief="sunken" if is_selected else "raised",
                bd=2 if is_selected else 1,
                state="normal" if in_month else "disabled",
                bg="#dcecff" if is_selected else "#ffffff",
                activebackground="#c8defa",
            )
            btn.bind(
                "<Button-1>",
                lambda event, d=date_obj: self.on_day_button_click(d, event),
            )
            btn.grid(row=row, column=col, sticky="nsew", padx=2, pady=2)

        count = len(self.selected_dates)
        if count == 0:
            self.summary_var.set("No days selected")
        elif count <= 6:
            labels = sorted(self.selected_dates)
            self.summary_var.set(", ".join(labels))
        else:
            self.summary_var.set(f"{count} days selected")

    def finish(self):
        self.result = sorted(self.selected_dates)
        self.destroy()


class TaskPlannerDialog(tk.Toplevel):
    def __init__(
        self,
        master,
        items,
        location_names,
        payload_names,
        profile_names,
        suggest_task_id,
        on_save,
        floor_map=None,
    ):
        super().__init__(master)
        self.title("Task Planner")
        self.geometry("1450x760")
        self.items = items
        self.location_names = sorted(location_names)
        self.floor_map = floor_map or {}
        self.grouped_rows = self._build_grouped_rows()
        self.payload_names = payload_names
        self.profile_names = profile_names
        self.suggest_task_id = suggest_task_id
        self.on_save = on_save

        self.day_start = self._initial_day()
        self.hour_width = 90
        self.row_height = 38
        self.header_height = 36
        self.left_width = 220
        self.selected_task_index = None
        self.selected_task_rect_id = None
        self.selected_row_name = None
        self.copied_task = None
        self._context_row_name = None
        self._context_task_index = None
        self._context_datetime = None
        self.task_canvas_ids = {}
        self.task_fill_palette = [
            "#2e7d32",  # 1st
            "#1976d2",  # 2nd
            "#f57c00",  # 3rd
            "#7b1fa2",  # 4th
            "#c2185b",  # 5th
            "#00838f",  # 6th
            "#6d4c41",  # 7th
            "#455a64",  # 8th
        ]

        self._build_ui()
        self._bind_events()
        self.refresh_matrix()

    def _build_ui(self):
        outer = ttk.Frame(self, padding=8)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(outer)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        ttk.Button(toolbar, text="◀ Day", command=lambda: self.shift_day(-1)).pack(
            side="left"
        )
        ttk.Button(toolbar, text="Today", command=self.go_to_today).pack(
            side="left", padx=4
        )
        ttk.Button(toolbar, text="Day ▶", command=lambda: self.shift_day(1)).pack(
            side="left"
        )

        ttk.Button(
            toolbar, text="Copy Day...", command=self.copy_day_tasks_to_other_day
        ).pack(side="left", padx=(10, 0))

        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=10)

        ttk.Button(
            toolbar, text="- Hour Width", command=lambda: self.adjust_hour_width(-10)
        ).pack(side="left")
        ttk.Button(
            toolbar, text="+ Hour Width", command=lambda: self.adjust_hour_width(10)
        ).pack(side="left", padx=4)

        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=10)

        ttk.Button(toolbar, text="Copy", command=self.copy_selected_task).pack(
            side="left"
        )
        ttk.Button(toolbar, text="Paste", command=self.paste_to_selected_row).pack(
            side="left", padx=4
        )
        ttk.Button(toolbar, text="Delete", command=self.delete_selected_task).pack(
            side="left"
        )
        ttk.Button(toolbar, text="Save", command=self.save).pack(side="right")

        self.date_var = tk.StringVar()
        ttk.Label(toolbar, textvariable=self.date_var, font=("Arial", 11, "bold")).pack(
            side="right", padx=(0, 12)
        )

        canvas_frame = ttk.Frame(outer)
        canvas_frame.grid(row=1, column=0, sticky="nsew")
        canvas_frame.columnconfigure(0, weight=1)
        canvas_frame.rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(
            canvas_frame,
            bg="#ffffff",
            highlightthickness=1,
            highlightbackground="#b8b8b8",
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")

        y_scroll = ttk.Scrollbar(
            canvas_frame, orient="vertical", command=self.canvas.yview
        )
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll = ttk.Scrollbar(
            canvas_frame, orient="horizontal", command=self.canvas.xview
        )
        x_scroll.grid(row=1, column=0, sticky="ew")
        self.canvas.configure(xscrollcommand=x_scroll.set, yscrollcommand=y_scroll.set)

        self.status_var = tk.StringVar(value="Double-click a cell to create a task.")
        ttk.Label(outer, textvariable=self.status_var).grid(
            row=2, column=0, sticky="ew", pady=(8, 0)
        )

        self.menu = tk.Menu(self, tearoff=0)

    def _build_grouped_rows(self):
        grouped = {}

        for name in self.location_names:
            floor = self.floor_map.get(name)
            key = f"Floor {floor}" if floor is not None else "Other"
            grouped.setdefault(key, []).append(name)

        ordered = []
        for floor in sorted(grouped.keys()):
            ordered.append(("header", floor))
            for loc in sorted(grouped[floor]):
                ordered.append(("row", loc))

        return ordered

    def _bind_events(self):
        self.canvas.bind("<Double-Button-1>", self.on_canvas_double_click)
        self.canvas.bind("<Button-1>", self.on_canvas_left_click)
        self.canvas.bind("<Button-3>", self.on_canvas_right_click)
        self.bind("<Delete>", lambda event: self.delete_selected_task())
        self.bind("<Control-c>", lambda event: self.copy_selected_task())
        self.bind("<Control-C>", lambda event: self.copy_selected_task())
        self.bind("<Control-v>", lambda event: self.paste_to_selected_row())
        self.bind("<Control-V>", lambda event: self.paste_to_selected_row())
        self.canvas.bind("<MouseWheel>", self.on_mousewheel)
        self.canvas.bind("<Shift-MouseWheel>", self.on_shift_mousewheel)
        self.canvas.bind("<Button-4>", self.on_mousewheel_linux)
        self.canvas.bind("<Button-5>", self.on_mousewheel_linux)
        self.canvas.bind("<Shift-Button-4>", self.on_shift_mousewheel_linux)
        self.canvas.bind("<Shift-Button-5>", self.on_shift_mousewheel_linux)

    def on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-event.delta / 120), "units")
        return "break"

    def on_shift_mousewheel(self, event):
        self.canvas.xview_scroll(int(-event.delta / 120), "units")
        return "break"

    def on_mousewheel_linux(self, event):
        if event.num == 4:
            self.canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self.canvas.yview_scroll(1, "units")
        return "break"

    def on_shift_mousewheel_linux(self, event):
        if event.num == 4:
            self.canvas.xview_scroll(-1, "units")
        elif event.num == 5:
            self.canvas.xview_scroll(1, "units")
        return "break"

    def _initial_day(self):
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        for task in self.items:
            dt = self._task_datetime(task)
            if dt is not None:
                return dt.replace(hour=0, minute=0, second=0, microsecond=0)
        return today

    def shift_day(self, days):
        self.day_start = self.day_start + timedelta(days=days)
        self.refresh_matrix()

    def go_to_today(self):
        self.day_start = datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        self.refresh_matrix()

    def adjust_hour_width(self, delta):
        self.hour_width = max(40, min(220, self.hour_width + delta))
        self.refresh_matrix()

    def save(self):
        self.on_save(self.items)
        self.status_var.set("Tasks saved")

    def _next_task_id(self, reserved_ids=None):
        reserved_ids = set(reserved_ids or [])
        nums = []
        for task in self.items:
            task_id = str(task.get("id", ""))
            if task_id.startswith("T") and task_id[1:].isdigit():
                nums.append(int(task_id[1:]))
        for task_id in reserved_ids:
            task_id = str(task_id)
            if task_id.startswith("T") and task_id[1:].isdigit():
                nums.append(int(task_id[1:]))
        return f"T{max(nums, default=0) + 1}"

    def _task_datetime(self, task):
        try:
            return datetime.fromisoformat(str(task.get("release_datetime", "")).strip())
        except Exception:
            return None

    def _format_cell_datetime(self, dt):
        return dt.replace(second=0, microsecond=0).isoformat(timespec="seconds")

    def _snap_to_grid(self, dt):
        minute = (dt.minute // 15) * 15
        return dt.replace(minute=minute, second=0, microsecond=0)

    def tasks_for_day(self):
        start = self.day_start
        end = start + timedelta(days=1)
        rows = []
        for idx, task in enumerate(self.items):
            dt = self._task_datetime(task)
            if dt is None:
                continue
            if start <= dt < end:
                rows.append((idx, task, dt))
        return rows

    def refresh_matrix(self):
        self.canvas.delete("all")
        self.task_canvas_ids = {}
        self.date_var.set(self.day_start.strftime("%A %d %B %Y"))

        total_width = self.left_width + (24 * self.hour_width)
        row_lane_count = self._calculate_row_lane_counts()
        total_height = self.header_height

        for kind, name in self.grouped_rows:
            if kind == "header":
                total_height += 24
            else:
                lanes = max(1, row_lane_count.get(name, 1))
                total_height += max(self.row_height, lanes * 18)

        self.canvas.configure(scrollregion=(0, 0, total_width, total_height))

        self.canvas.create_rectangle(
            0, 0, self.left_width, self.header_height, fill="#ececec", outline="#c8c8c8"
        )
        self.canvas.create_text(
            10,
            self.header_height / 2,
            text="Departments / drop-off",
            anchor="w",
            font=("Arial", 10, "bold"),
        )

        for hour in range(24):
            x1 = self.left_width + (hour * self.hour_width)
            x2 = x1 + self.hour_width
            fill = "#f4f4f4" if hour % 2 == 0 else "#fbfbfb"
            self.canvas.create_rectangle(
                x1, 0, x2, self.header_height, fill=fill, outline="#d6d6d6"
            )
            self.canvas.create_text(
                (x1 + x2) / 2,
                self.header_height / 2,
                text=f"{hour:02d}:00",
                font=("Arial", 10, "bold"),
            )

        y_cursor = self.header_height
        row_index = 0
        self._row_y_positions = {}

        for kind, name in self.grouped_rows:
            if kind == "header":
                y1 = y_cursor
                y2 = y1 + 24

                self.canvas.create_rectangle(
                    0, y1, total_width, y2, fill="#d0d7e5", outline="#b0b7c5"
                )
                self.canvas.create_text(
                    10, (y1 + y2) / 2, text=name, anchor="w", font=("Arial", 10, "bold")
                )

                y_cursor = y2
                continue

            lanes = max(1, row_lane_count.get(name, 1))
            row_height = max(self.row_height, lanes * 18)

            y1 = y_cursor
            y2 = y1 + row_height
            self._row_y_positions[name] = (y1, y2, row_height)

            fill = "#ffffff" if row_index % 2 == 0 else "#fafafa"
            label_fill = "#f5f5f5" if self.selected_row_name != name else "#dcecff"

            self.canvas.create_rectangle(
                0, y1, self.left_width, y2, fill=label_fill, outline="#d6d6d6"
            )
            self.canvas.create_text(10, (y1 + y2) / 2, text=name, anchor="w")
            self.canvas.create_rectangle(
                self.left_width, y1, total_width, y2, fill=fill, outline="#ececec"
            )

            for hour in range(25):
                x = self.left_width + (hour * self.hour_width)
                self.canvas.create_line(x, y1, x, y2, fill="#e2e2e2")

            y_cursor = y2
            row_index += 1

        self._draw_task_blocks()

    def _task_fill_for_lane(self, lane_index):
        return self.task_fill_palette[lane_index % len(self.task_fill_palette)]

    def _visible_tasks_for_day(self):
        results = []
        task_list = getattr(self, "items", [])

        for idx, task in enumerate(task_list):
            dt = self._task_datetime(task)
            if dt is None:
                continue

            if self.day_start <= dt < (self.day_start + timedelta(days=1)):
                results.append((idx, task))

        return results

    def _draw_task_blocks(self):
        visible_tasks = self._visible_tasks_for_day()
        if not visible_tasks:
            return

        tasks_by_slot = {}
        row_lane_count = {}

        for idx, task in visible_tasks:
            dt = self._task_datetime(task)
            if dt is None:
                continue

            row_name = str(task.get("dropoff", "")).strip()
            if not row_name:
                continue

            slot_key = (
                row_name,
                dt.replace(second=0, microsecond=0),
            )
            tasks_by_slot.setdefault(slot_key, []).append((idx, task))

        lane_lookup = {}
        for (row_name, _slot_dt), slot_tasks in tasks_by_slot.items():
            slot_tasks.sort(
                key=lambda item: (
                    self._task_datetime(item[1]) or self.day_start,
                    str(item[1].get("id", "")),
                )
            )
            row_lane_count[row_name] = max(
                row_lane_count.get(row_name, 1), len(slot_tasks)
            )
            for lane_index, (idx, _task) in enumerate(slot_tasks):
                lane_lookup[idx] = lane_index

        for idx, task in visible_tasks:
            dt = self._task_datetime(task)
            if dt is None:
                continue

            row_name = str(task.get("dropoff", "")).strip()
            if row_name not in self.location_names:
                continue

            lane_count = max(1, row_lane_count.get(row_name, 1))
            lane_index = lane_lookup.get(idx, 0)

            x1 = self.left_width + (
                ((dt - self.day_start).total_seconds() / 3600.0) * self.hour_width
            )
            block_width = max(
                30,
                (max(int(task.get("target_time", 300)), 60) / 3600.0) * self.hour_width,
            )
            x2 = x1 + block_width

            if row_name not in self._row_y_positions:
                continue

            y1_row, y2_row, row_height = self._row_y_positions[row_name]

            inner_top = y1_row + 4
            inner_height = max(12, row_height - 8)

            lane_height = max(12, inner_height / lane_count)

            y1 = inner_top + (lane_index * lane_height)
            y2 = y1 + lane_height - 2

            selected = idx == self.selected_task_index
            fill = self._task_fill_for_lane(lane_index)
            outline = "#000000" if selected else "#244028"

            rect_id = self.canvas.create_rectangle(
                x1,
                y1,
                x2,
                y2,
                fill=fill,
                outline=outline,
                width=2 if selected else 1,
                tags=("task", f"task_{idx}"),
            )

            label = f"{task.get('id', '')}  {task.get('pickup', '')}"
            text_y = (y1 + y2) / 2
            text_id = self.canvas.create_text(
                x1 + 4,
                text_y,
                text=label,
                anchor="w",
                fill="white",
                font=("Arial", 9, "bold" if selected else "normal"),
                tags=("task", f"task_{idx}"),
            )

            self.task_canvas_ids[idx] = (rect_id, text_id)

    def _row_name_from_y(self, canvas_y):
        if canvas_y < self.header_height:
            return None

        for name, (y1, y2, _row_height) in getattr(
            self, "_row_y_positions", {}
        ).items():
            if y1 <= canvas_y < y2:
                return name

        return None

    def _datetime_from_x(self, canvas_x):
        if canvas_x < self.left_width:
            return self.day_start
        hour_offset = (canvas_x - self.left_width) / float(self.hour_width)
        minutes = max(0, min(int(round(hour_offset * 60)), (24 * 60) - 1))
        return self._snap_to_grid(self.day_start + timedelta(minutes=minutes))

    def _task_index_from_event(self, event):
        current = self.canvas.find_withtag("current")
        if not current:
            return None
        tags = self.canvas.gettags(current[0])
        for tag in tags:
            if tag.startswith("task_"):
                try:
                    return int(tag.split("_", 1)[1])
                except Exception:
                    return None
        return None

    def on_canvas_left_click(self, event):
        self.canvas.focus_set()
        canvas_x = self.canvas.canvasx(event.x)
        canvas_y = self.canvas.canvasy(event.y)
        task_index = self._task_index_from_event(event)
        self.selected_row_name = self._row_name_from_y(canvas_y)
        if task_index is not None:
            self.selected_task_index = task_index
            task = self.items[task_index]
            self.status_var.set(
                f"Selected {task.get('id', '')} → {task.get('dropoff', '')}"
            )
        else:
            self.selected_task_index = None
            if self.selected_row_name:
                self.status_var.set(
                    f"Selected destination row: {self.selected_row_name}"
                )
        self.refresh_matrix()

    def on_canvas_double_click(self, event):
        self.canvas.focus_set()
        canvas_x = self.canvas.canvasx(event.x)
        canvas_y = self.canvas.canvasy(event.y)

        task_index = self._task_index_from_event(event)
        if task_index is not None:
            dialog = TaskFormDialog(
                self,
                self.location_names,
                self.payload_names,
                self.profile_names,
                seed=deepcopy(self.items[task_index]),
                default_task_id=self.items[task_index].get("id", self._next_task_id()),
                group_resolver=self._group_for_location,
            )
            if dialog.result:
                self.items[task_index] = dialog.result
                self.selected_task_index = task_index
                self.selected_row_name = dialog.result.get("dropoff", "")
                self.status_var.set(f"Updated {dialog.result.get('id', '')}")
                self.refresh_matrix()
            return

        row_name = self._row_name_from_y(canvas_y)
        if not row_name:
            return

        when = self._datetime_from_x(canvas_x)
        seed = {
            "dropoff": row_name,
            "release_datetime": self._format_cell_datetime(when),
        }
        dialog = TaskFormDialog(
            self,
            self.location_names,
            self.payload_names,
            self.profile_names,
            seed=seed,
            default_task_id=self._next_task_id(),
            group_resolver=self._group_for_location,
        )
        if dialog.result:
            self.items.append(dialog.result)
            self.selected_task_index = len(self.items) - 1
            self.selected_row_name = dialog.result.get("dropoff", "")
            self.status_var.set(f"Created {dialog.result.get('id', '')}")
            self.refresh_matrix()

    def on_canvas_right_click(self, event):
        self.canvas.focus_set()
        canvas_y = self.canvas.canvasy(event.y)
        canvas_x = self.canvas.canvasx(event.x)
        self._context_row_name = self._row_name_from_y(canvas_y)
        self._context_datetime = self._datetime_from_x(canvas_x)
        self._context_task_index = self._task_index_from_event(event)
        self.menu.delete(0, "end")

        if self._context_task_index is not None:
            self.selected_task_index = self._context_task_index
            self.refresh_matrix()
            self.menu.add_command(label="Copy", command=self.copy_selected_task)
            self.menu.add_command(label="Delete", command=self.delete_selected_task)
        else:
            if self.copied_task and self._context_row_name:
                self.menu.add_command(
                    label=f"Paste to {self._context_row_name}",
                    command=lambda: self.paste_to_row(
                        self._context_row_name,
                        self._context_datetime,
                    ),
                )
            if self._context_row_name:
                self.menu.add_command(
                    label=f"Create task at {self._context_row_name}",
                    command=lambda: self._create_task_for_row(
                        self._context_row_name,
                        self._context_datetime,
                    ),
                )

        if self.menu.index("end") is not None:
            self.menu.tk_popup(event.x_root, event.y_root)

    def _create_task_for_row(self, row_name, when=None):
        when = when or self.day_start
        seed = {
            "dropoff": row_name,
            "release_datetime": self._format_cell_datetime(when),
        }
        dialog = TaskFormDialog(
            self,
            self.location_names,
            self.payload_names,
            self.profile_names,
            seed=seed,
            default_task_id=self._next_task_id(),
            group_resolver=self._group_for_location,
        )
        if dialog.result:
            self.items.append(dialog.result)
            self.selected_task_index = len(self.items) - 1
            self.selected_row_name = row_name
            self.refresh_matrix()

    def copy_selected_task(self):
        if self.selected_task_index is None:
            self.status_var.set("Select a task first")
            return
        self.copied_task = deepcopy(self.items[self.selected_task_index])
        self.status_var.set(f"Copied {self.copied_task.get('id', '')}")

    def paste_to_selected_row(self):
        if not self.selected_row_name:
            self.status_var.set("Select a destination row first")
            return
        self.paste_to_row(self.selected_row_name)

    def paste_to_row(self, row_name, when=None):
        if not self.copied_task:
            self.status_var.set("Copy a task first")
            return
        copied = deepcopy(self.copied_task)
        copied["id"] = self._next_task_id()
        copied["dropoff"] = row_name
        if when is not None:
            copied["release_datetime"] = self._format_cell_datetime(when)
        self.items.append(copied)
        self.selected_task_index = len(self.items) - 1
        self.selected_row_name = row_name
        self.status_var.set(
            f"Pasted {copied.get('id', '')} to {row_name} at "
            f"{copied.get('release_datetime', '')}"
        )
        self.refresh_matrix()

    def delete_selected_task(self):
        if self.selected_task_index is None:
            self.status_var.set("Select a task first")
            return
        task = self.items[self.selected_task_index]
        if not messagebox.askyesno(
            "Delete task",
            f"Delete task {task.get('id', '')}?",
            parent=self,
        ):
            return
        del self.items[self.selected_task_index]
        self.selected_task_index = None
        self.status_var.set("Task deleted")
        self.refresh_matrix()

    def _group_for_location(self, item):
        floor = getattr(self, "floor_map", {}).get(item)
        if floor is None:
            return "Other"
        return f"Floor {floor}"

    def _calculate_row_lane_counts(self):
        visible_tasks = self._visible_tasks_for_day()
        tasks_by_slot = {}
        row_lane_count = {}

        for idx, task in visible_tasks:
            dt = self._task_datetime(task)
            if dt is None:
                continue

            row_name = str(task.get("dropoff", "")).strip()
            if not row_name:
                continue

            slot_key = (row_name, dt.replace(second=0, microsecond=0))
            tasks_by_slot.setdefault(slot_key, []).append(idx)

        for (row_name, _slot_dt), task_indexes in tasks_by_slot.items():
            row_lane_count[row_name] = max(
                row_lane_count.get(row_name, 1),
                len(task_indexes),
            )

        return row_lane_count

    def _tasks_for_exact_day(self, day_start):
        day_end = day_start + timedelta(days=1)
        results = []
        for idx, task in enumerate(self.items):
            dt = self._task_datetime(task)
            if dt is None:
                continue
            if day_start <= dt < day_end:
                results.append((idx, task, dt))
        return results

    def _shift_task_to_day(
        self, task, source_day_start, target_day_start, reserved_ids
    ):
        copied = deepcopy(task)
        original_dt = self._task_datetime(task)
        if original_dt is None:
            return None

        offset = original_dt - source_day_start
        new_dt = target_day_start + offset

        new_id = self._next_task_id(reserved_ids)
        reserved_ids.add(new_id)

        copied["id"] = new_id
        copied["release_datetime"] = new_dt.replace(second=0, microsecond=0).isoformat(
            timespec="seconds"
        )
        return copied

    def copy_day_tasks_to_other_day(self):
        source_day_start = self.day_start
        source_tasks = self._tasks_for_exact_day(source_day_start)

        if not source_tasks:
            messagebox.showinfo(
                "Copy day",
                "There are no tasks on the displayed day to copy.",
                parent=self,
            )
            return

        picker = MultiDaySelectDialog(
            self,
            initial_date=source_day_start + timedelta(days=1),
        )
        self.wait_window(picker)

        if not picker.result:
            return

        target_day_starts = []
        for text in picker.result:
            try:
                dt = datetime.fromisoformat(text).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                if dt != source_day_start:
                    target_day_starts.append(dt)
            except Exception:
                continue

        if not target_day_starts:
            messagebox.showerror(
                "Invalid selection",
                "Select at least one target day different from the current day.",
                parent=self,
            )
            return

        existing_summary = []
        for target_day_start in target_day_starts:
            existing_target_tasks = self._tasks_for_exact_day(target_day_start)
            if existing_target_tasks:
                existing_summary.append(
                    f"{target_day_start.strftime('%Y-%m-%d')} ({len(existing_target_tasks)} existing)"
                )

        if existing_summary:
            if not messagebox.askyesno(
                "Some target days already have tasks",
                "These days already contain tasks:\n\n"
                + "\n".join(existing_summary)
                + "\n\nCopy the current day's tasks as additional tasks?",
                parent=self,
            ):
                return

        if not messagebox.askyesno(
            "Confirm copy day",
            (
                f"Copy {len(source_tasks)} task(s) from "
                f"{source_day_start.strftime('%Y-%m-%d')} to "
                f"{len(target_day_starts)} selected day(s)?"
            ),
            parent=self,
        ):
            return

        reserved_ids = {str(task.get("id", "")) for task in self.items}
        created = []

        for target_day_start in target_day_starts:
            for _idx, task, _dt in source_tasks:
                copied = self._shift_task_to_day(
                    task,
                    source_day_start,
                    target_day_start,
                    reserved_ids,
                )
                if copied is not None:
                    created.append(copied)

        self.items.extend(created)
        self.status_var.set(
            f"Copied {len(source_tasks)} task(s) to {len(target_day_starts)} day(s)"
        )
        self.refresh_matrix()


class TaskEditorWindow(tk.Toplevel):
    def __init__(
        self,
        master,
        items,
        location_names,
        payload_names,
        profile_names,
        suggest_task_id,
        on_save,
        floor_map=None,
    ):
        super().__init__(master)
        self.title("Tasks")
        self.geometry("1200x520")
        self.items = items
        self.location_names = location_names
        self.payload_names = payload_names
        self.profile_names = profile_names
        self.suggest_task_id = suggest_task_id
        self.on_save = on_save
        self.floor_map = floor_map or {}

        self.tree = ttk.Treeview(
            self,
            columns=[
                "id",
                "pickup",
                "dropoff",
                "payload",
                "release_datetime",
                "target_time",
                "priority",
                "labels",
                "route_profile",
            ],
            show="headings",
            selectmode="extended",
        )
        self.tree.bind("<Double-1>", self._on_tree_double_click)

        for key, heading, width in [
            ("id", "ID", 90),
            ("pickup", "Pickup", 150),
            ("dropoff", "Dropoff", 150),
            ("payload", "Payload", 130),
            ("release_datetime", "Release datetime", 170),
            ("target_time", "Target time", 90),
            ("priority", "Priority", 80),
            ("labels", "Labels", 150),
            ("route_profile", "Route profile", 120),
        ]:
            self.tree.heading(key, text=heading)
            self.tree.column(key, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=8, pady=8)

        for item in self.items:
            self._insert_tree_item(item)

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(buttons, text="Add", command=self.add_item).pack(side="left")
        ttk.Button(buttons, text="Edit", command=self.edit_item).pack(
            side="left", padx=4
        )
        ttk.Button(buttons, text="Delete", command=self.delete_item).pack(side="left")
        ttk.Button(
            buttons, text="Duplicate x Times", command=self._duplicate_selected_item
        ).pack(side="left", padx=4)
        ttk.Button(
            buttons, text="One to Many", command=self._create_one_to_many_tasks
        ).pack(side="left", padx=4)
        ttk.Button(
            buttons, text="Schedule Return Trip", command=self._schedule_return_trips
        ).pack(side="left", padx=4)
        ttk.Button(buttons, text="Save", command=self.save).pack(side="right")

    def _insert_tree_item(self, item):
        self.tree.insert(
            "",
            "end",
            values=[
                item.get("id", ""),
                item.get("pickup", ""),
                item.get("dropoff", ""),
                item.get("payload", ""),
                item.get("release_datetime", ""),
                item.get("target_time", ""),
                item.get("priority", ""),
                ", ".join(item.get("labels", [])),
                item.get("route_profile", ""),
            ],
        )

    def add_item(self):
        dialog = TaskFormDialog(
            self,
            self.location_names,
            self.payload_names,
            self.profile_names,
            default_task_id=self._next_task_id(),
            group_resolver=self._group_for_location,
        )
        if dialog.result:
            self.items.append(dialog.result)
            self._insert_tree_item(dialog.result)

    def edit_item(self):
        selected = self.tree.selection()
        if not selected:
            return
        idx = self.tree.index(selected[0])
        dialog = TaskFormDialog(
            self,
            self.location_names,
            self.payload_names,
            self.profile_names,
            seed=self.items[idx],
            default_task_id=self.items[idx].get("id", self._next_task_id()),
            group_resolver=self._group_for_location,
        )
        if dialog.result:
            self.items[idx] = dialog.result
            self.tree.item(
                selected[0],
                values=[
                    dialog.result.get("id", ""),
                    dialog.result.get("pickup", ""),
                    dialog.result.get("dropoff", ""),
                    dialog.result.get("payload", ""),
                    dialog.result.get("release_datetime", ""),
                    dialog.result.get("target_time", ""),
                    dialog.result.get("priority", ""),
                    ", ".join(dialog.result.get("labels", [])),
                    dialog.result.get("route_profile", ""),
                ],
            )

    def _parse_return_delay(self, text):
        value = (text or "").strip()
        if not value:
            raise ValueError("Delay is required")

        parts = value.split(":")
        if len(parts) != 3:
            raise ValueError("Delay must be in HH:MM:SS format")

        hours, minutes, seconds = [int(x) for x in parts]
        return timedelta(hours=hours, minutes=minutes, seconds=seconds)

    def delete_item(self):
        selected = self.tree.selection()
        if not selected:
            return
        idx = self.tree.index(selected[0])
        del self.items[idx]
        self.tree.delete(selected[0])

    def save(self):
        self.on_save(self.items)
        self.destroy()

    def _refresh_tree(self):
        for item_id in self.tree.get_children():
            self.tree.delete(item_id)

        for item in self.items:
            self._insert_tree_item(item)

    def _next_task_id(self, reserved_ids=None):
        reserved_ids = set(reserved_ids or [])
        nums = []

        for task in self.items:
            task_id = str(task.get("id", ""))
            if task_id.startswith("T") and task_id[1:].isdigit():
                nums.append(int(task_id[1:]))

        for task_id in reserved_ids:
            task_id = str(task_id)
            if task_id.startswith("T") and task_id[1:].isdigit():
                nums.append(int(task_id[1:]))

        next_num = max(nums, default=0) + 1
        return f"T{next_num}"

    def _duplicate_selected_item(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showerror(
                "No task selected", "Select a task to duplicate.", parent=self
            )
            return

        idx = self.tree.index(selected[0])
        source_task = self.items[idx]

        count = simpledialog.askinteger(
            "Duplicate task",
            "How many copies do you want to create?",
            parent=self,
            minvalue=1,
            initialvalue=1,
        )
        if count is None:
            return

        insert_at = idx + 1
        new_items = []
        reserved_ids = {str(task.get("id", "")) for task in self.items}

        for _ in range(count):
            copied = deepcopy(source_task)
            new_id = self._next_task_id(reserved_ids)
            copied["id"] = new_id
            reserved_ids.add(new_id)
            new_items.append(copied)

        for offset, copied in enumerate(new_items):
            self.items.insert(insert_at + offset, copied)

        self._refresh_tree()

    def _on_tree_double_click(self, event):
        item_id = self.tree.identify_row(event.y)
        if not item_id:
            return
        self.tree.selection_set(item_id)
        self.edit_item()

    def _group_for_location(self, item):
        floor = getattr(self, "floor_map", {}).get(item)
        if floor is None:
            return "Other"
        return f"Floor {floor}"

    def _create_one_to_many_tasks(self):
        dialog = BulkOneToManyTaskDialog(
            self,
            self.location_names,
            self.payload_names,
            self.profile_names,
            group_resolver=self._group_for_location,
            default_task_id=(
                self._next_task_id() if hasattr(self, "_next_task_id") else "T1"
            ),
        )
        if not dialog.result:
            return

        payload = dialog.result
        reserved_ids = {str(task.get("id", "")) for task in self.items}
        created = []

        for dropoff in payload["dropoffs"]:
            if hasattr(self, "_next_task_id"):
                new_id = self._next_task_id(reserved_ids)
            else:
                nums = []
                for existing_id in reserved_ids:
                    if (
                        str(existing_id).startswith("T")
                        and str(existing_id)[1:].isdigit()
                    ):
                        nums.append(int(str(existing_id)[1:]))
                new_id = f"T{max(nums, default=0) + 1}"

            reserved_ids.add(new_id)

            created.append(
                {
                    "id": new_id,
                    "pickup": payload["pickup"],
                    "dropoff": dropoff,
                    "payload": payload["payload"],
                    "release_datetime": payload["release_datetime"],
                    "target_time": payload["target_time"],
                    "priority": payload["priority"],
                    "labels": list(payload["labels"]),
                    "route_profile": payload["route_profile"],
                }
            )

        self.items.extend(created)
        if hasattr(self, "_refresh_tree"):
            self._refresh_tree()
        else:
            for task in created:
                self._insert_tree_item(task)

    def _apply_delay_to_release_datetime(self, release_datetime_text, delay):
        base_dt = datetime.fromisoformat(release_datetime_text)
        new_dt = base_dt + delay
        return new_dt.isoformat(timespec="seconds")

    def _schedule_return_trips(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showerror(
                "No task selected", "Select one or more tasks first.", parent=self
            )
            return

        delay_text = simpledialog.askstring(
            "Return trip delay",
            "Enter delay as HH:MM:SS",
            parent=self,
            initialvalue="00:30:00",
        )
        if delay_text is None:
            return

        try:
            delay = self._parse_return_delay(delay_text)
        except Exception as exc:
            messagebox.showerror("Invalid delay", str(exc), parent=self)
            return

        selected_indexes = sorted(self.tree.index(item_id) for item_id in selected)
        reserved_ids = {str(task.get("id", "")) for task in self.items}
        new_tasks = []

        for idx in selected_indexes:
            source_task = self.items[idx]
            copied = deepcopy(source_task)

            if hasattr(self, "_next_task_id"):
                new_id = self._next_task_id(reserved_ids)
            else:
                nums = []
                for existing_id in reserved_ids:
                    existing_id = str(existing_id)
                    if existing_id.startswith("T") and existing_id[1:].isdigit():
                        nums.append(int(existing_id[1:]))
                new_id = f"T{max(nums, default=0) + 1}"

            reserved_ids.add(new_id)

            copied["id"] = new_id
            copied["pickup"] = source_task.get("dropoff", "")
            copied["dropoff"] = source_task.get("pickup", "")
            copied["release_datetime"] = self._apply_delay_to_release_datetime(
                source_task.get("release_datetime", "2026-01-01T08:00:00"),
                delay,
            )

            new_tasks.append(copied)

        self.items.extend(new_tasks)

        if hasattr(self, "_refresh_tree"):
            self._refresh_tree()
        else:
            for task in new_tasks:
                self._insert_tree_item(task)
