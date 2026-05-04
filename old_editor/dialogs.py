import json
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk


class PointEditorDialog(simpledialog.Dialog):
    def __init__(self, parent, title, point_name, point):
        self.point_name = point_name
        self.point = point
        self.result = None
        super().__init__(parent, title)

    def body(self, master):
        ttk.Label(master, text="Name").grid(row=0, column=0, sticky="w")
        self.name_var = tk.StringVar(value=self.point_name)
        ttk.Entry(master, textvariable=self.name_var, width=30).grid(row=0, column=1, sticky="ew")

        ttk.Label(master, text="X").grid(row=1, column=0, sticky="w")
        self.x_var = tk.StringVar(value=str(self.point["x"]))
        ttk.Entry(master, textvariable=self.x_var, width=20).grid(row=1, column=1, sticky="ew")

        ttk.Label(master, text="Y").grid(row=2, column=0, sticky="w")
        self.y_var = tk.StringVar(value=str(self.point["y"]))
        ttk.Entry(master, textvariable=self.y_var, width=20).grid(row=2, column=1, sticky="ew")

        ttk.Label(master, text="Floor").grid(row=3, column=0, sticky="w")
        ttk.Label(master, text=str(self.point["floor"])).grid(row=3, column=1, sticky="w")

        ttk.Label(master, text="Kind").grid(row=4, column=0, sticky="w")
        ttk.Label(master, text=self.point.get("kind", "")).grid(row=4, column=1, sticky="w")

        master.columnconfigure(1, weight=1)
        return master

    def validate(self):
        try:
            float(self.x_var.get())
            float(self.y_var.get())
            if not self.name_var.get().strip():
                raise ValueError("Name is required")
            return True
        except Exception as exc:
            messagebox.showerror("Invalid value", str(exc), parent=self)
            return False

    def apply(self):
        self.result = {
            "name": self.name_var.get().strip(),
            "x": float(self.x_var.get()),
            "y": float(self.y_var.get()),
        }


class LiftEditorDialog(simpledialog.Dialog):
    def __init__(self, parent, lift=None, default_floor=0, default_x=0.0, default_y=0.0):
        self.lift = lift
        self.default_floor = default_floor
        self.default_x = default_x
        self.default_y = default_y
        self.result = None
        super().__init__(parent, "Lift Editor")

    def body(self, master):
        lift = self.lift or {}
        floors = lift.get("served_floors", [self.default_floor])
        floor_locations = lift.get("floor_locations", {})

        ttk.Label(master, text="Lift ID").grid(row=0, column=0, sticky="w")
        self.id_var = tk.StringVar(value=lift.get("id", "Lift-1"))
        ttk.Entry(master, textvariable=self.id_var, width=24).grid(row=0, column=1, sticky="ew")

        ttk.Label(master, text="Served floors").grid(row=1, column=0, sticky="w")
        self.floors_var = tk.StringVar(value=", ".join(str(x) for x in floors))
        ttk.Entry(master, textvariable=self.floors_var, width=30).grid(row=1, column=1, sticky="ew")

        ttk.Label(master, text="Speed floors/sec").grid(row=2, column=0, sticky="w")
        self.speed_var = tk.StringVar(value=str(lift.get("speed_floors_per_sec", 0.45)))
        ttk.Entry(master, textvariable=self.speed_var).grid(row=2, column=1, sticky="ew")

        ttk.Label(master, text="Door time sec").grid(row=3, column=0, sticky="w")
        self.door_var = tk.StringVar(value=str(lift.get("door_time_sec", 4)))
        ttk.Entry(master, textvariable=self.door_var).grid(row=3, column=1, sticky="ew")

        ttk.Label(master, text="Boarding time sec").grid(row=4, column=0, sticky="w")
        self.board_var = tk.StringVar(value=str(lift.get("boarding_time_sec", 6)))
        ttk.Entry(master, textvariable=self.board_var).grid(row=4, column=1, sticky="ew")

        ttk.Label(master, text="Capacity size units").grid(row=5, column=0, sticky="w")
        self.capacity_var = tk.StringVar(value=str(lift.get("capacity_size_units", 1.0)))
        ttk.Entry(master, textvariable=self.capacity_var).grid(row=5, column=1, sticky="ew")

        ttk.Label(master, text="Start floor").grid(row=6, column=0, sticky="w")
        self.start_floor_var = tk.StringVar(value=str(lift.get("start_floor", self.default_floor)))
        ttk.Entry(master, textvariable=self.start_floor_var).grid(row=6, column=1, sticky="ew")

        ttk.Label(master, text="Per-floor positions").grid(row=7, column=0, sticky="nw", pady=(8, 0))
        self.pos_text = tk.Text(master, width=40, height=10)
        self.pos_text.grid(row=7, column=1, sticky="nsew", pady=(8, 0))

        if floor_locations:
            payload = {int(k): [v["x"], v["y"]] for k, v in floor_locations.items()}
        else:
            payload = {self.default_floor: [self.default_x, self.default_y]}
        self.pos_text.insert("1.0", json.dumps(payload, indent=2))

        ttk.Label(master, text="Format: {floor: [x, y]}").grid(row=8, column=1, sticky="w")

        master.columnconfigure(1, weight=1)
        return master

    def validate(self):
        try:
            if not self.id_var.get().strip():
                raise ValueError("Lift ID is required")
            floors = [int(x.strip()) for x in self.floors_var.get().split(",") if x.strip()]
            if not floors:
                raise ValueError("At least one served floor is required")
            positions = json.loads(self.pos_text.get("1.0", "end").strip())
            for floor in floors:
                if str(floor) not in {str(k) for k in positions.keys()}:
                    raise ValueError(f"Missing position for floor {floor}")
            float(self.speed_var.get())
            float(self.door_var.get())
            float(self.board_var.get())
            float(self.capacity_var.get())
            int(self.start_floor_var.get())
            return True
        except Exception as exc:
            messagebox.showerror("Invalid lift", str(exc), parent=self)
            return False

    def apply(self):
        floors = [int(x.strip()) for x in self.floors_var.get().split(",") if x.strip()]
        raw_positions = json.loads(self.pos_text.get("1.0", "end").strip())
        floor_locations = {
            int(k): (float(v[0]), float(v[1]))
            for k, v in raw_positions.items()
        }
        self.result = {
            "id": self.id_var.get().strip(),
            "served_floors": floors,
            "speed_floors_per_sec": float(self.speed_var.get()),
            "door_time_sec": float(self.door_var.get()),
            "boarding_time_sec": float(self.board_var.get()),
            "capacity_size_units": float(self.capacity_var.get()),
            "start_floor": int(self.start_floor_var.get()),
            "floor_locations": floor_locations,
        }


class TableListEditor(tk.Toplevel):
    def __init__(self, master, title, columns, items, on_save):
        super().__init__(master)
        self.title(title)
        self.geometry("1100x500")
        self.columns = columns
        self.items = items
        self.on_save = on_save

        self.tree = ttk.Treeview(self, columns=[c[0] for c in columns], show="headings")
        for key, heading, width in columns:
            self.tree.heading(key, text=heading)
            self.tree.column(key, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=8, pady=8)

        for item in self.items:
            self.tree.insert("", "end", values=[self.stringify(item.get(c[0], "")) for c in columns])

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(buttons, text="Add", command=self.add_item).pack(side="left")
        ttk.Button(buttons, text="Edit", command=self.edit_item).pack(side="left", padx=4)
        ttk.Button(buttons, text="Delete", command=self.delete_item).pack(side="left")
        ttk.Button(buttons, text="Save", command=self.save).pack(side="right")

    @staticmethod
    def stringify(value):
        if isinstance(value, (list, dict)):
            return json.dumps(value)
        return str(value)

    def parse_value(self, value):
        value = value.strip()
        if value.startswith("[") or value.startswith("{"):
            return json.loads(value)
        if value == "":
            return ""
        try:
            if "." in value:
                return float(value)
            return int(value)
        except Exception:
            return value

    def prompt_item(self, seed=None):
        seed = seed or {}
        result = {}
        for key, heading, _ in self.columns:
            val = simpledialog.askstring(self.title(), heading, initialvalue=self.stringify(seed.get(key, "")), parent=self)
            if val is None:
                return None
            result[key] = self.parse_value(val)
        return result

    def add_item(self):
        item = self.prompt_item()
        if item is None:
            return
        self.items.append(item)
        self.tree.insert("", "end", values=[self.stringify(item.get(c[0], "")) for c in self.columns])

    def edit_item(self):
        selected = self.tree.selection()
        if not selected:
            return
        idx = self.tree.index(selected[0])
        updated = self.prompt_item(self.items[idx])
        if updated is None:
            return
        self.items[idx] = updated
        self.tree.item(selected[0], values=[self.stringify(updated.get(c[0], "")) for c in self.columns])

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


class RouteProfilesEditor(tk.Toplevel):
    def __init__(self, master, profiles, point_names, lift_ids, on_save):
        super().__init__(master)
        self.title("Route Profiles")
        self.geometry("1100x650")
        self.profiles = json.loads(json.dumps(profiles))
        self.point_names = sorted(point_names)
        self.lift_ids = sorted(lift_ids)
        self.on_save = on_save
        self.current_profile = None

        outer = ttk.Frame(self, padding=8)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(0, weight=1)

        left = ttk.Frame(outer)
        left.grid(row=0, column=0, sticky="ns")
        right = ttk.Frame(outer)
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        right.columnconfigure(0, weight=1)
        right.rowconfigure(6, weight=1)

        self.profile_list = tk.Listbox(left, width=24)
        self.profile_list.pack(fill="y", expand=True)
        self.profile_list.bind("<<ListboxSelect>>", self.on_profile_select)

        btns = ttk.Frame(left)
        btns.pack(fill="x", pady=(8, 0))
        ttk.Button(btns, text="Add", command=self.add_profile).pack(fill="x")
        ttk.Button(btns, text="Delete", command=self.delete_profile).pack(fill="x", pady=4)

        ttk.Label(right, text="Profile name").grid(row=0, column=0, sticky="w")
        self.name_var = tk.StringVar()
        ttk.Entry(right, textvariable=self.name_var).grid(row=1, column=0, sticky="ew")

        ttk.Label(right, text="Allowed lifts (comma separated IDs)").grid(row=2, column=0, sticky="w", pady=(8, 0))
        self.lifts_var = tk.StringVar()
        ttk.Entry(right, textvariable=self.lifts_var).grid(row=3, column=0, sticky="ew")

        ttk.Label(right, text="Allowed nodes (one per line)").grid(row=4, column=0, sticky="w", pady=(8, 0))
        self.nodes_text = tk.Text(right, height=10)
        self.nodes_text.grid(row=5, column=0, sticky="nsew")

        ttk.Label(right, text="Allowed edges as JSON array pairs").grid(row=6, column=0, sticky="nw", pady=(8, 0))
        self.edges_text = tk.Text(right, height=12)
        self.edges_text.grid(row=7, column=0, sticky="nsew")

        lower = ttk.Frame(right)
        lower.grid(row=8, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(lower, text="Apply Changes", command=self.apply_profile_changes).pack(side="left")
        ttk.Button(lower, text="Save All", command=self.save_all).pack(side="right")

        for name in self.profiles.keys():
            self.profile_list.insert("end", name)
        if self.profiles:
            self.profile_list.selection_set(0)
            self.on_profile_select()

    def add_profile(self):
        name = simpledialog.askstring("New profile", "Profile name:", parent=self)
        if not name:
            return
        if name in self.profiles:
            messagebox.showerror("Duplicate", "Profile already exists", parent=self)
            return
        self.profiles[name] = {"allowed_lifts": [], "allowed_nodes": [], "allowed_edges": []}
        self.profile_list.insert("end", name)

    def delete_profile(self):
        sel = self.profile_list.curselection()
        if not sel:
            return
        name = self.profile_list.get(sel[0])
        if name == "default":
            messagebox.showerror("Not allowed", "Cannot delete default profile", parent=self)
            return
        del self.profiles[name]
        self.profile_list.delete(sel[0])
        self.current_profile = None
        self.name_var.set("")
        self.lifts_var.set("")
        self.nodes_text.delete("1.0", "end")
        self.edges_text.delete("1.0", "end")

    def on_profile_select(self, event=None):
        sel = self.profile_list.curselection()
        if not sel:
            return
        name = self.profile_list.get(sel[0])
        self.current_profile = name
        profile = self.profiles[name]
        self.name_var.set(name)
        self.lifts_var.set(", ".join(profile.get("allowed_lifts", [])))
        self.nodes_text.delete("1.0", "end")
        self.nodes_text.insert("1.0", "\n".join(profile.get("allowed_nodes", [])))
        self.edges_text.delete("1.0", "end")
        self.edges_text.insert("1.0", json.dumps(profile.get("allowed_edges", []), indent=2))

    def apply_profile_changes(self):
        if not self.current_profile:
            return
        try:
            new_name = self.name_var.get().strip()
            if not new_name:
                raise ValueError("Profile name is required")
            lifts = [x.strip() for x in self.lifts_var.get().split(",") if x.strip()]
            nodes = [x.strip() for x in self.nodes_text.get("1.0", "end").splitlines() if x.strip()]
            edges = json.loads(self.edges_text.get("1.0", "end").strip() or "[]")
            if not isinstance(edges, list):
                raise ValueError("Allowed edges must be a JSON list")
            payload = {
                "allowed_lifts": lifts,
                "allowed_nodes": nodes,
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
