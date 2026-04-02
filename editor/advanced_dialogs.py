import json
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from copy import deepcopy
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

    def pick_nodes(self):
        picker = MultiSelectPicker(
            self,
            "Pick nodes",
            self.point_names,
            self.allowed_nodes,
            group_resolver=self._group_for_item,
        )

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
        self.location_names = location_names
        self.payload_names = payload_names
        self.profile_names = profile_names
        self.seed = seed or {}
        self.default_task_id = default_task_id
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
