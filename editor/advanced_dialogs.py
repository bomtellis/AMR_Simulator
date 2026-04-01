import json
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk


class MultiSelectPicker(tk.Toplevel):
    def __init__(self, parent, title, options, selected=None):
        super().__init__(parent)
        self.title(title)
        self.geometry("420x520")
        self.result = None
        self.options = list(options)
        self.selected = set(selected or [])
        self.visible_options = []

        outer = ttk.Frame(self, padding=8)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)

        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", lambda *_: self.refresh())
        ttk.Entry(outer, textvariable=self.filter_var).grid(
            row=0, column=0, sticky="ew"
        )

        self.listbox = tk.Listbox(outer, selectmode="extended")
        self.listbox.grid(row=1, column=0, sticky="nsew", pady=8)

        btns = ttk.Frame(outer)
        btns.grid(row=2, column=0, sticky="ew")
        ttk.Button(btns, text="All", command=self.select_all).pack(side="left")
        ttk.Button(btns, text="None", command=self.clear_all).pack(side="left", padx=4)
        ttk.Button(btns, text="OK", command=self.finish).pack(side="right")

        self.refresh()

    def refresh(self):
        filter_text = self.filter_var.get().strip().lower()
        self.listbox.delete(0, "end")
        self.visible_options = []
        for item in self.options:
            if filter_text and filter_text not in item.lower():
                continue
            self.visible_options.append(item)
            self.listbox.insert("end", item)
        for idx, item in enumerate(self.visible_options):
            if item in self.selected:
                self.listbox.selection_set(idx)

    def select_all(self):
        self.listbox.select_set(0, "end")

    def clear_all(self):
        self.listbox.selection_clear(0, "end")

    def finish(self):
        self.result = [self.visible_options[i] for i in self.listbox.curselection()]
        self.destroy()


class RouteProfilesEditorV2(tk.Toplevel):
    def __init__(
        self, master, profiles, point_names, lift_ids, corridor_edges, on_save
    ):
        super().__init__(master)
        self.title("Route Profiles")
        self.geometry("1200x720")
        self.profiles = json.loads(json.dumps(profiles))
        self.point_names = sorted(point_names)
        self.lift_ids = sorted(lift_ids)
        self.corridor_edges = corridor_edges
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
            self, "Pick lifts", self.lift_ids, self.allowed_lifts
        )
        self.wait_window(picker)
        if picker.result is not None:
            self.allowed_lifts = picker.result
            self.lifts_summary_var.set(self.summarize(self.allowed_lifts))

    def pick_nodes(self):
        picker = MultiSelectPicker(
            self, "Pick nodes", self.point_names, self.allowed_nodes
        )
        self.wait_window(picker)
        if picker.result is not None:
            self.allowed_nodes = picker.result
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


class TaskFormDialog(simpledialog.Dialog):
    def __init__(
        self,
        parent,
        location_names,
        payload_names,
        profile_names,
        seed=None,
        default_task_id="T1",
    ):
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
        self.pickup_var = tk.StringVar(value=self.seed.get("pickup", ""))
        ttk.Combobox(
            master,
            textvariable=self.pickup_var,
            values=self.location_names,
            state="readonly",
        ).grid(row=1, column=1, sticky="ew")

        ttk.Label(master, text="Dropoff").grid(row=2, column=0, sticky="w")
        self.dropoff_var = tk.StringVar(value=self.seed.get("dropoff", ""))
        ttk.Combobox(
            master,
            textvariable=self.dropoff_var,
            values=self.location_names,
            state="readonly",
        ).grid(row=2, column=1, sticky="ew")

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
        )
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
            default_task_id=self.suggest_task_id(),
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
            default_task_id=self.items[idx].get("id", self.suggest_task_id()),
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
