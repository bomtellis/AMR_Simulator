import math
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from dxf_scene import DXFScene
from dialogs import LiftEditorDialog, PointEditorDialog, TableListEditor
from advanced_dialogs import RouteProfilesEditorV2, TaskEditorWindow
from models import JsonStore


class AMRGraphEditor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AMR Simulation Graph Editor")
        self.geometry("1500x920")

        self.store = JsonStore()
        self.current_json_path = None
        self.current_dxf_path = None
        self.dxf_scene = DXFScene()

        self.scale = 5.0
        self.offset_x = 250
        self.offset_y = 250
        self.last_pan = None
        self.selected_for_edge = None
        self.selected_point_name = None
        self.dragging_point_name = None
        self.drag_mode_active = False
        self.edge_delete_start = None

        self._build_ui()
        self.refresh_canvas()

    def _build_ui(self):
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        self.sidebar = ttk.Frame(self, padding=8)
        self.sidebar.grid(row=0, column=0, sticky="ns")
        self.sidebar.columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(self, bg="#111111")
        self.canvas.grid(row=0, column=1, sticky="nsew")
        self.canvas.bind("<Button-1>", self.on_left_click)
        self.canvas.bind("<Double-Button-1>", self.on_double_click)
        self.canvas.bind("<ButtonRelease-1>", self.on_left_release)
        self.canvas.bind("<Button-3>", self.on_right_click)
        self.canvas.bind("<Button-2>", self.on_middle_click)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<B2-Motion>", self.on_middle_drag)
        self.canvas.bind("<ButtonRelease-2>", self.on_middle_release)
        self.canvas.bind("<MouseWheel>", self.on_mousewheel)

        self.mode_var = tk.StringVar(value="select_move")
        self.floor_var = tk.IntVar(value=0)
        self.snap_var = tk.BooleanVar(value=True)
        self.bidirectional_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="Ready")
        self.file_var = tk.StringVar(value="New file")
        self.show_dxf_var = tk.BooleanVar(value=True)
        self.show_labels_var = tk.BooleanVar(value=True)

        self._build_sidebar()

    def _build_sidebar(self):
        row = 0
        ttk.Label(self.sidebar, text="Mode").grid(row=row, column=0, sticky="w")
        row += 1
        ttk.Combobox(
            self.sidebar,
            textvariable=self.mode_var,
            values=[
                "select_move",
                "corridor_node",
                "location",
                "edge",
                "lift",
                "pan",
                "delete",
            ],
            state="readonly",
            width=22,
        ).grid(row=row, column=0, sticky="ew")
        row += 1

        ttk.Label(self.sidebar, text="Floor").grid(
            row=row, column=0, sticky="w", pady=(10, 0)
        )
        row += 1
        floor_row = ttk.Frame(self.sidebar)
        floor_row.grid(row=row, column=0, sticky="ew")
        ttk.Spinbox(
            floor_row, from_=0, to=99, textvariable=self.floor_var, width=10
        ).pack(side="left")
        ttk.Button(floor_row, text="Go", command=self.refresh_canvas).pack(
            side="left", padx=4
        )
        row += 1

        ttk.Checkbutton(self.sidebar, text="Snap to 1.0", variable=self.snap_var).grid(
            row=row, column=0, sticky="w", pady=(10, 0)
        )
        row += 1
        ttk.Checkbutton(
            self.sidebar, text="Bidirectional edges", variable=self.bidirectional_var
        ).grid(row=row, column=0, sticky="w")
        row += 1
        ttk.Checkbutton(
            self.sidebar,
            text="Show DXF",
            variable=self.show_dxf_var,
            command=self.refresh_canvas,
        ).grid(row=row, column=0, sticky="w")
        row += 1
        ttk.Checkbutton(
            self.sidebar,
            text="Show labels",
            variable=self.show_labels_var,
            command=self.refresh_canvas,
        ).grid(row=row, column=0, sticky="w")
        row += 1

        ttk.Separator(self.sidebar).grid(row=row, column=0, sticky="ew", pady=10)
        row += 1

        ttk.Button(self.sidebar, text="Open JSON", command=self.open_json).grid(
            row=row, column=0, sticky="ew"
        )
        row += 1
        ttk.Button(self.sidebar, text="Save JSON", command=self.save_json).grid(
            row=row, column=0, sticky="ew", pady=4
        )
        row += 1
        ttk.Button(self.sidebar, text="Load DXF", command=self.load_dxf).grid(
            row=row, column=0, sticky="ew"
        )
        row += 1
        ttk.Button(self.sidebar, text="Fit View", command=self.fit_view).grid(
            row=row, column=0, sticky="ew", pady=4
        )
        row += 1
        ttk.Button(self.sidebar, text="Validate", command=self.validate_json).grid(
            row=row, column=0, sticky="ew"
        )
        row += 1

        ttk.Separator(self.sidebar).grid(row=row, column=0, sticky="ew", pady=10)
        row += 1

        ttk.Button(self.sidebar, text="Payloads", command=self.manage_payloads).grid(
            row=row, column=0, sticky="ew"
        )
        row += 1
        ttk.Button(self.sidebar, text="AMRs", command=self.manage_amrs).grid(
            row=row, column=0, sticky="ew", pady=4
        )
        row += 1
        ttk.Button(self.sidebar, text="Tasks", command=self.manage_tasks).grid(
            row=row, column=0, sticky="ew"
        )
        row += 1
        ttk.Button(
            self.sidebar, text="Route Profiles", command=self.manage_route_profiles
        ).grid(row=row, column=0, sticky="ew", pady=4)
        row += 1

        ttk.Separator(self.sidebar).grid(row=row, column=0, sticky="ew", pady=10)
        row += 1

        ttk.Label(self.sidebar, text="Current file").grid(row=row, column=0, sticky="w")
        row += 1
        ttk.Label(self.sidebar, textvariable=self.file_var, wraplength=220).grid(
            row=row, column=0, sticky="w"
        )
        row += 1
        ttk.Label(self.sidebar, text="Status").grid(
            row=row, column=0, sticky="w", pady=(10, 0)
        )
        row += 1
        ttk.Label(self.sidebar, textvariable=self.status_var, wraplength=220).grid(
            row=row, column=0, sticky="w"
        )

    def set_status(self, text):
        self.status_var.set(text)

    def world_to_canvas(self, x, y):
        return (x * self.scale) + self.offset_x, (-y * self.scale) + self.offset_y

    def canvas_to_world(self, cx, cy):
        return (cx - self.offset_x) / self.scale, -((cy - self.offset_y) / self.scale)

    def snap(self, x, y):
        if self.snap_var.get():
            return round(x), round(y)
        return round(x, 3), round(y, 3)

    def fit_view(self):
        if self.dxf_scene.bounds:
            canvas_w = max(self.canvas.winfo_width(), 1000)
            canvas_h = max(self.canvas.winfo_height(), 700)
            self.scale, self.offset_x, self.offset_y = self.dxf_scene.fit_transform(
                canvas_w, canvas_h
            )
        else:
            self.scale = 5.0
            self.offset_x = 250
            self.offset_y = 250
        self.refresh_canvas()

    def refresh_canvas(self):
        self.canvas.delete("all")
        floor = self.floor_var.get()
        # self.draw_grid()
        if self.show_dxf_var.get() and self.dxf_scene.entities:
            self.dxf_scene.draw(self.canvas, self.world_to_canvas)
        self.draw_edges(floor)
        self.draw_points(floor)
        self.draw_legend()
        self.file_var.set(self.current_json_path or "New file")

    def draw_grid(self):
        w = self.canvas.winfo_width() or 1000
        h = self.canvas.winfo_height() or 800
        spacing = 50
        for x in range(0, w, spacing):
            self.canvas.create_line(x, 0, x, h, fill="#1d1d1d")
        for y in range(0, h, spacing):
            self.canvas.create_line(0, y, w, y, fill="#1d1d1d")

    def draw_edges(self, floor):
        points = self.store.all_points()
        for edge in self.store.edges_for_floor(floor):
            a = points.get(edge["from"])
            b = points.get(edge["to"])
            if not a or not b:
                continue
            ax, ay = self.world_to_canvas(a["x"], a["y"])
            bx, by = self.world_to_canvas(b["x"], b["y"])
            self.canvas.create_line(ax, ay, bx, by, fill="#6aa9ff", width=2)

    def draw_points(self, floor):
        for name, point in self.store.points_for_floor(floor).items():
            x, y = self.world_to_canvas(point["x"], point["y"])
            selected = name == self.selected_point_name
            kind = point.get("kind")
            if kind == "location":
                r = 6
                self.canvas.create_oval(
                    x - r,
                    y - r,
                    x + r,
                    y + r,
                    fill="#18c37e",
                    outline="#ffffff" if selected else "",
                )
                label_color = "#9bf0cd"
            elif kind == "corridor_node":
                r = 5
                self.canvas.create_rectangle(
                    x - r,
                    y - r,
                    x + r,
                    y + r,
                    fill="#f2c94c",
                    outline="#ffffff" if selected else "",
                )
                label_color = "#ffe8a3"
            else:
                r = 7
                self.canvas.create_polygon(
                    x,
                    y - r,
                    x + r,
                    y,
                    x,
                    y + r,
                    x - r,
                    y,
                    fill="#ff7b72",
                    outline="#ffffff" if selected else "",
                )
                label_color = "#ffb3ae"
            if self.show_labels_var.get():
                self.canvas.create_text(
                    x + 10, y - 8, text=name, anchor="sw", fill=label_color
                )

    def draw_legend(self):
        self.canvas.create_rectangle(10, 10, 300, 128, fill="#151515", outline="#333")
        lines = [
            "Legend",
            "Green circle = location",
            "Yellow square = corridor node",
            "Red diamond = lift node",
            f"Mode: {self.mode_var.get()} | Floor: {self.floor_var.get()}",
            "Double-click a point to edit",
        ]
        y = 20
        for line in lines:
            self.canvas.create_text(20, y, text=line, anchor="nw", fill="white")
            y += 18

    def find_nearest_point_name(self, x, y, floor, radius_world=3.0):
        best = None
        best_dist = radius_world
        for name, point in self.store.points_for_floor(floor).items():
            d = math.hypot(point["x"] - x, point["y"] - y)
            if d <= best_dist:
                best = name
                best_dist = d
        return best

    def on_left_click(self, event):
        mode = self.mode_var.get()
        floor = self.floor_var.get()
        x, y = self.canvas_to_world(event.x, event.y)
        x, y = self.snap(x, y)

        if mode == "pan":
            self.last_pan = (event.x, event.y)
            return

        picked = self.find_nearest_point_name(x, y, floor)
        self.selected_point_name = picked

        if mode == "select_move":
            if picked:
                self.dragging_point_name = picked
                self.drag_mode_active = True
                self.set_status(f"Selected {picked}")
            self.refresh_canvas()
            return

        if mode == "delete":
            if picked:
                if picked.startswith("Lift-") and "-F" in picked:
                    lift_id = picked.rsplit("-F", 1)[0]
                    if messagebox.askyesno("Delete lift", f"Delete entire {lift_id}?"):
                        self.store.delete_lift(lift_id)
                        self.selected_point_name = None
                        self.set_status(f"Deleted {lift_id}")
                else:
                    if messagebox.askyesno("Delete point", f"Delete {picked}?"):
                        self.store.delete_point(picked)
                        self.selected_point_name = None
                        self.set_status(f"Deleted {picked}")
                self.refresh_canvas()
            return

        if mode == "corridor_node":
            name = simpledialog.askstring(
                "Corridor node",
                "Node name:",
                initialvalue=self.store.suggest_next_corridor_name(floor),
                parent=self,
            )
            if not name:
                return
            self.store.add_corridor_node(name, floor, x, y)
            self.set_status(f"Added corridor node {name}")
            self.refresh_canvas()
            return

        if mode == "location":
            name = simpledialog.askstring("Location", "Location name:", parent=self)
            if not name:
                return
            self.store.add_location(name, floor, x, y)
            self.set_status(f"Added location {name}")
            self.refresh_canvas()
            return

        if mode == "edge":
            if not picked:
                self.set_status("No nearby point found")
                return
            if self.selected_for_edge is None:
                self.selected_for_edge = picked
                self.set_status(f"Edge start selected: {picked}")
            else:
                self.store.add_edge(self.selected_for_edge, picked)
                if self.bidirectional_var.get():
                    self.store.add_edge(picked, self.selected_for_edge)
                self.set_status(f"Connected {self.selected_for_edge} -> {picked}")
                self.selected_for_edge = None
                self.refresh_canvas()
            return

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
            if dialog.result:
                self.store.upsert_lift(
                    dialog.result["id"],
                    dialog.result["served_floors"],
                    dialog.result["floor_locations"],
                    dialog.result["speed_floors_per_sec"],
                    dialog.result["door_time_sec"],
                    dialog.result["boarding_time_sec"],
                    dialog.result["capacity_size_units"],
                    dialog.result["start_floor"],
                )
                self.set_status(f"Saved {dialog.result['id']}")
                self.refresh_canvas()
            return

    def on_double_click(self, event):
        floor = self.floor_var.get()
        x, y = self.canvas_to_world(event.x, event.y)
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
            if dialog.result:
                self.store.upsert_lift(
                    dialog.result["id"],
                    dialog.result["served_floors"],
                    dialog.result["floor_locations"],
                    dialog.result["speed_floors_per_sec"],
                    dialog.result["door_time_sec"],
                    dialog.result["boarding_time_sec"],
                    dialog.result["capacity_size_units"],
                    dialog.result["start_floor"],
                )
                self.set_status(f"Edited {dialog.result['id']}")
                self.refresh_canvas()
            return
        dialog = PointEditorDialog(self, f"Edit {picked}", picked, point)
        if dialog.result:
            self.store.set_point_position(
                picked, dialog.result["x"], dialog.result["y"]
            )
            self.store.rename_point(picked, dialog.result["name"])
            self.selected_point_name = dialog.result["name"]
            self.set_status(f"Edited {dialog.result['name']}")
            self.refresh_canvas()

    def on_left_release(self, event):
        self.dragging_point_name = None
        self.drag_mode_active = False
        self.last_pan = None

    def on_right_click(self, event):
        mode = self.mode_var.get()
        floor = self.floor_var.get()
        x, y = self.canvas_to_world(event.x, event.y)
        picked = self.find_nearest_point_name(x, y, floor)

        if mode == "edge":
            if picked and self.edge_delete_start is None:
                self.edge_delete_start = picked
                self.selected_for_edge = None
                self.set_status(f"Edge delete start selected: {picked}")
                return
            if picked and self.edge_delete_start:
                removed = False
                before = len(self.store.data.get("corridors", {}).get("edges", []))
                self.store.remove_edge(self.edge_delete_start, picked)
                after = len(self.store.data.get("corridors", {}).get("edges", []))
                removed = removed or (after < before)
                if self.bidirectional_var.get():
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

        if picked:
            self.selected_point_name = picked
            self.refresh_canvas()

    def on_drag(self, event):
        mode = self.mode_var.get()
        if mode == "pan":
            if self.last_pan is None:
                self.last_pan = (event.x, event.y)
                return
            dx = event.x - self.last_pan[0]
            dy = event.y - self.last_pan[1]
            self.offset_x += dx
            self.offset_y += dy
            self.last_pan = (event.x, event.y)
            self.refresh_canvas()
            return

        if mode == "select_move" and self.drag_mode_active and self.dragging_point_name:
            x, y = self.canvas_to_world(event.x, event.y)
            x, y = self.snap(x, y)
            self.store.set_point_position(self.dragging_point_name, x, y)
            self.refresh_canvas()

    def on_middle_click(self, event):
        self.last_pan = (event.x, event.y)

    def on_middle_drag(self, event):
        if self.last_pan is None:
            self.last_pan = (event.x, event.y)
            return
        dx = event.x - self.last_pan[0]
        dy = event.y - self.last_pan[1]
        self.offset_x += dx
        self.offset_y += dy
        self.last_pan = (event.x, event.y)
        self.refresh_canvas()

    def on_middle_release(self, event):
        self.last_pan = None

    def on_mousewheel(self, event):
        factor = 1.1 if event.delta > 0 else 0.9
        self.scale = max(0.2, min(60, self.scale * factor))
        self.refresh_canvas()

    def open_json(self):
        path = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
        if not path:
            return
        self.store = JsonStore.from_file(path)
        self.current_json_path = path
        self.set_status(f"Opened {Path(path).name}")
        self.refresh_canvas()

    def save_json(self):
        path = self.current_json_path or filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
        )
        if not path:
            return
        self.store.save(path)
        self.current_json_path = path
        self.set_status(f"Saved {Path(path).name}")
        self.refresh_canvas()

    def load_dxf(self):
        path = filedialog.askopenfilename(filetypes=[("DXF files", "*.dxf")])
        if not path:
            return
        try:
            self.dxf_scene.load(path)
            self.current_dxf_path = path
            self.fit_view()
            self.set_status(f"Loaded DXF {Path(path).name}")
        except Exception as exc:
            messagebox.showerror("DXF load failed", str(exc), parent=self)

    def validate_json(self):
        errors = self.store.validate()
        if errors:
            messagebox.showerror(
                "Validation errors", "\n".join(errors[:100]), parent=self
            )
            self.set_status(f"Validation failed with {len(errors)} error(s)")
        else:
            messagebox.showinfo(
                "Validation", "JSON structure is internally consistent.", parent=self
            )
            self.set_status("Validation passed")

    def manage_payloads(self):
        columns = [
            ("name", "Name", 220),
            ("weight_kg", "Weight kg", 120),
            ("size_units", "Size units", 120),
        ]
        TableListEditor(
            self,
            "Payloads",
            columns,
            self.store.data.get("payloads", []),
            self._save_payloads,
        )

    def _save_payloads(self, items):
        self.store.data["payloads"] = items
        self.set_status("Payloads updated")

    def manage_amrs(self):
        columns = [
            ("id", "ID", 120),
            ("quantity", "Quantity", 80),
            ("payload_capacity_kg", "Payload kg", 110),
            ("payload_size_capacity", "Payload size", 110),
            ("speed_m_per_sec", "Speed", 90),
            ("motor_power_w", "Motor W", 90),
            ("battery_capacity_kwh", "Battery kWh", 100),
            ("battery_charge_rate_kw", "Charge kW", 100),
            ("recharge_threshold_percent", "Recharge %", 100),
            ("battery_soc_percent", "SOC %", 80),
            ("start_location", "Start location", 160),
        ]
        TableListEditor(
            self, "AMRs", columns, self.store.data.get("amrs", []), self._save_amrs
        )

    def _save_amrs(self, items):
        self.store.data["amrs"] = items
        self.set_status("AMRs updated")

    def manage_tasks(self):
        location_names = sorted(x["name"] for x in self.store.data.get("locations", []))
        payload_names = sorted(x["name"] for x in self.store.data.get("payloads", []))
        profile_names = [""] + sorted(self.store.data.get("route_profiles", {}).keys())
        TaskEditorWindow(
            self,
            self.store.data.get("tasks", []),
            location_names,
            payload_names,
            profile_names,
            self.store.suggest_next_task_id,
            self._save_tasks,
        )

    # columns = [
    #     ("id", "ID", 90),
    #     ("pickup", "Pickup", 160),
    #     ("dropoff", "Dropoff", 160),
    #     ("payload", "Payload", 140),
    #     ("release_datetime", "Release datetime", 170),
    #     ("target_time", "Target time", 100),
    #     ("priority", "Priority", 80),
    #     ("labels", "Labels", 160),
    #     ("route_profile", "Route profile", 120),
    # ]
    # items = self.store.data.get("tasks", [])
    # if not items:
    #     items.append(
    #         {
    #             "id": self.store.suggest_next_task_id(),
    #             "pickup": "",
    #             "dropoff": "",
    #             "payload": "",
    #             "release_datetime": "2026-01-01T08:00:00",
    #             "target_time": 300,
    #             "priority": 10,
    #             "labels": [""],
    #             "route_profile": "",
    #         }
    #     )
    # TableListEditor(self, "Tasks", columns, items, self._save_tasks)

    def _save_tasks(self, items):
        self.store.data["tasks"] = items
        self.set_status("Tasks updated")

    def manage_route_profiles(self):
        point_names = set(self.store.names_in_use()) | {
            x["name"] for x in self.store.data.get("locations", [])
        }
        lift_ids = {x["id"] for x in self.store.data.get("lifts", [])}
        RouteProfilesEditorV2(
            self,
            self.store.data.get("route_profiles", {}),
            point_names,
            lift_ids,
            self.store.data.get("corridors", {}).get("edges", []),
            self._save_route_profiles,
        )

    def _save_route_profiles(self, profiles):
        self.store.data["route_profiles"] = profiles
        self.set_status("Route profiles updated")


def main():
    app = AMRGraphEditor()
    app.mainloop()
