# Complete interface coverage inventory

Every declared workspace, dialog, active command and labelled control is indexed below. Runtime-generated objects (floors, locations, payloads, run rows and layer names) inherit the lesson of their containing control. Menu actions built from data tables inherit their workspace lesson; use the contextual reference in that workspace. Legacy standalone windows are included for compatibility. This inventory does not enable Detailed simulation or LTN testing.

For any field: use its visible label and tooltip, retain units, inspect validation feedback, and use Save/Cancel to commit or discard the whole dialog. For list editors: select an item before Edit/Delete, use Add for a new object, and verify changes with Project checks and Demand preview. For canvas commands: Escape cancels an unfinished gesture; selection alone leaves Properties collapsed; Undo/Redo verify committed edits. For frozen evidence: select a registered run, investigate linked records, and keep original inputs when comparing variants. Each optional lesson is available from Course tools > Additional lessons.

| Interface | Kind | Lesson / contextual reference | Source |
|---|---|---|---|
| MultiSelectPicker | Workspace / dialog | Drawing tools and layers | visualiser/advanced_dialogs.py:99 |
| RouteProfilesEditorV2 | Workspace / dialog | Batching and route restrictions | visualiser/advanced_dialogs.py:284 |
| TaskFormDialog | Workspace / dialog | Advanced demand | visualiser/advanced_dialogs.py:558 |
| BulkOneToManyTaskDialog | Workspace / dialog | Advanced demand | visualiser/advanced_dialogs.py:707 |
| MultiDaySelectDialog | Workspace / dialog | Drawing tools and layers | visualiser/advanced_dialogs.py:820 |
| TaskPlannerDialog | Workspace / dialog | Advanced demand | visualiser/advanced_dialogs.py:941 |
| EditMultipleTasksDialog | Workspace / dialog | Advanced demand | visualiser/advanced_dialogs.py:1587 |
| TaskEditorWindow | Workspace / dialog | Advanced demand | visualiser/advanced_dialogs.py:1677 |
| Route Profiles | setWindowTitle | Batching and route restrictions | visualiser/advanced_dialogs.py:298 |
| Profiles define the allowed routes: include a shared section in each profile that may use it. Empty lists mean unrestricted; edge pairs are directional. Task allowances extend profile allowances. Profiles apply after pickup. Empty approach, charging and idle-return journeys are unrestricted by profiles. Set a return profile explicitly when a return must follow a particular route. | QLabel | Advanced demand | visualiser/advanced_dialogs.py:311 |
| Add | QPushButton | Drawing tools and layers | visualiser/advanced_dialogs.py:331 |
| Delete | QPushButton | Drawing tools and layers | visualiser/advanced_dialogs.py:332 |
| Profile name | addRow | Batching and route restrictions | visualiser/advanced_dialogs.py:344 |
| None | QLabel | Drawing tools and layers | visualiser/advanced_dialogs.py:347 |
| Pick | QPushButton | Drawing tools and layers | visualiser/advanced_dialogs.py:348 |
| Allowed lifts | addRow | Main chapters 5, 6, 10, 11 | visualiser/advanced_dialogs.py:352 |
| None | QLabel | Drawing tools and layers | visualiser/advanced_dialogs.py:355 |
| Pick | QPushButton | Drawing tools and layers | visualiser/advanced_dialogs.py:357 |
| Allowed nodes | addRow | Drawing tools and layers | visualiser/advanced_dialogs.py:361 |
| Graphical... | QPushButton | Drawing tools and layers | visualiser/advanced_dialogs.py:363 |
| Generate from selected nodes | QPushButton | Drawing tools and layers | visualiser/advanced_dialogs.py:372 |
| Clear edges | QPushButton | Drawing tools and layers | visualiser/advanced_dialogs.py:373 |
| Apply Changes | QPushButton | Drawing tools and layers | visualiser/advanced_dialogs.py:382 |
| Save All | QPushButton | Recovery and run outcomes | visualiser/advanced_dialogs.py:383 |
| Task | setWindowTitle | Advanced demand | visualiser/advanced_dialogs.py:570 |
| Select... | QPushButton | Drawing tools and layers | visualiser/advanced_dialogs.py:588 |
| Select... | QPushButton | Drawing tools and layers | visualiser/advanced_dialogs.py:596 |
| Target journey or completion allowance in seconds. | setToolTip | Drawing tools and layers | visualiser/advanced_dialogs.py:610 |
| Lower or higher values are interpreted using the existing simulator priority rules. | setToolTip | Drawing tools and layers | visualiser/advanced_dialogs.py:614 |
| Physical container ID | setAccessibleName | Drawing tools and layers | visualiser/advanced_dialogs.py:622 |
| Recover a container staged after a failed return | QCheckBox | Drawing tools and layers | visualiser/advanced_dialogs.py:623 |
| Use the exact container ID and pickup location from run evidence. The new run must reach that staged recovery state. Normal route, robot and storage checks apply; unconfirmed arrivals cannot be recovered with this option. | setToolTip | Relinking and evidence | visualiser/advanced_dialogs.py:625 |
| ID | addRow | Drawing tools and layers | visualiser/advanced_dialogs.py:629 |
| Pickup | addRow | Drawing tools and layers | visualiser/advanced_dialogs.py:630 |
| Dropoff | addRow | Drawing tools and layers | visualiser/advanced_dialogs.py:631 |
| Payload | addRow | Inventory and exchanges | visualiser/advanced_dialogs.py:632 |
| Release date and time | addRow | Drawing tools and layers | visualiser/advanced_dialogs.py:633 |
| Target allowance | addRow | Drawing tools and layers | visualiser/advanced_dialogs.py:634 |
| Priority | addRow | Drawing tools and layers | visualiser/advanced_dialogs.py:635 |
| Labels (comma-separated) | addRow | Drawing tools and layers | visualiser/advanced_dialogs.py:636 |
| Route profile | addRow | Batching and route restrictions | visualiser/advanced_dialogs.py:637 |
| Container ID | addRow | Drawing tools and layers | visualiser/advanced_dialogs.py:638 |
| Recovery | addRow | Recovery and run outcomes | visualiser/advanced_dialogs.py:639 |
| Create One-to-Many Tasks | setWindowTitle | Advanced demand | visualiser/advanced_dialogs.py:718 |
| None selected | QLabel | Drawing tools and layers | visualiser/advanced_dialogs.py:736 |
| Select... | QPushButton | Drawing tools and layers | visualiser/advanced_dialogs.py:738 |
| Base task ID | addRow | Advanced demand | visualiser/advanced_dialogs.py:752 |
| Pickup | addRow | Drawing tools and layers | visualiser/advanced_dialogs.py:753 |
| Dropoffs | addRow | Drawing tools and layers | visualiser/advanced_dialogs.py:754 |
| Payload | addRow | Inventory and exchanges | visualiser/advanced_dialogs.py:755 |
| Release date and time | addRow | Drawing tools and layers | visualiser/advanced_dialogs.py:756 |
| Target allowance | addRow | Drawing tools and layers | visualiser/advanced_dialogs.py:757 |
| Priority | addRow | Drawing tools and layers | visualiser/advanced_dialogs.py:758 |
| Labels (comma-separated) | addRow | Drawing tools and layers | visualiser/advanced_dialogs.py:759 |
| Route profile | addRow | Batching and route restrictions | visualiser/advanced_dialogs.py:760 |
| Select target days | setWindowTitle | Drawing tools and layers | visualiser/advanced_dialogs.py:823 |
| Select displayed month | QPushButton | Drawing tools and layers | visualiser/advanced_dialogs.py:846 |
| Clear all | QPushButton | Drawing tools and layers | visualiser/advanced_dialogs.py:847 |
| No days selected | QLabel | Drawing tools and layers | visualiser/advanced_dialogs.py:860 |
| Task Planner | setWindowTitle | Advanced demand | visualiser/advanced_dialogs.py:955 |
| Copy Day... | QPushButton | Drawing tools and layers | visualiser/advanced_dialogs.py:998 |
| Copy | QPushButton | Drawing tools and layers | visualiser/advanced_dialogs.py:1002 |
| Paste | QPushButton | Drawing tools and layers | visualiser/advanced_dialogs.py:1003 |
| Delete | QPushButton | Drawing tools and layers | visualiser/advanced_dialogs.py:1004 |
| Save | QPushButton | Recovery and run outcomes | visualiser/advanced_dialogs.py:1012 |
| Double-click a cell to create a task. | QLabel | Advanced demand | visualiser/advanced_dialogs.py:1033 |
| Copy | addAction | Drawing tools and layers | visualiser/advanced_dialogs.py:1181 |
| Delete | addAction | Drawing tools and layers | visualiser/advanced_dialogs.py:1182 |
| Edit Multiple Tasks | setWindowTitle | Advanced demand | visualiser/advanced_dialogs.py:1590 |
| Update release date and time | QCheckBox | Drawing tools and layers | visualiser/advanced_dialogs.py:1599 |
| Release date and time | addRow | Drawing tools and layers | visualiser/advanced_dialogs.py:1606 |
| Update target allowance | QCheckBox | Drawing tools and layers | visualiser/advanced_dialogs.py:1608 |
| Target allowance | addRow | Drawing tools and layers | visualiser/advanced_dialogs.py:1615 |
| Update priority | QCheckBox | Drawing tools and layers | visualiser/advanced_dialogs.py:1617 |
| Priority | addRow | Drawing tools and layers | visualiser/advanced_dialogs.py:1624 |
| Update labels | QCheckBox | Drawing tools and layers | visualiser/advanced_dialogs.py:1626 |
| Labels (comma-separated) | addRow | Drawing tools and layers | visualiser/advanced_dialogs.py:1633 |
| Update route profile | QCheckBox | Batching and route restrictions | visualiser/advanced_dialogs.py:1635 |
| Route profile | addRow | Batching and route restrictions | visualiser/advanced_dialogs.py:1644 |
| Tasks | setWindowTitle | Advanced demand | visualiser/advanced_dialogs.py:1705 |
| Save | QPushButton | Recovery and run outcomes | visualiser/advanced_dialogs.py:1747 |
| Edit | addAction | Drawing tools and layers | visualiser/advanced_dialogs.py:1889 |
| Delete | addAction | Drawing tools and layers | visualiser/advanced_dialogs.py:1893 |
| All | QPushButton | Drawing tools and layers | visualiser/advanced_dialogs.py:172 |
| None | QPushButton | Drawing tools and layers | visualiser/advanced_dialogs.py:173 |
| Allowed edges as JSON array pairs | QLabel | Drawing tools and layers | visualiser/advanced_dialogs.py:367 |
| Copy | addAction | Drawing tools and layers | visualiser/advanced_dialogs.py:1391 |
| Delete | addAction | Drawing tools and layers | visualiser/advanced_dialogs.py:1392 |
| Edit Multiple | addAction | Drawing tools and layers | visualiser/advanced_dialogs.py:1892 |
| TaskJumpDialog | Workspace / dialog | Advanced demand | visualiser/amr_sim_visualiser_pyside6.py:1430 |
| TasksByLocationDepartmentDialog | Workspace / dialog | Advanced demand | visualiser/amr_sim_visualiser_pyside6.py:1653 |
| LiftShaftWidget | Workspace / dialog | Main chapters 5, 6, 10, 11 | visualiser/amr_sim_visualiser_pyside6.py:1815 |
| LocationInventoryPayloadDialog | Workspace / dialog | Inventory and exchanges | visualiser/amr_sim_visualiser_pyside6.py:1882 |
| LocationInventorySpacesDialog | Workspace / dialog | Inventory and exchanges | visualiser/amr_sim_visualiser_pyside6.py:1956 |
| PayloadSpaceMaximumUtilisationDialog | Workspace / dialog | Inventory and exchanges | visualiser/amr_sim_visualiser_pyside6.py:2019 |
| AmrPayloadMonitorDialog | Workspace / dialog | Inventory and exchanges | visualiser/amr_sim_visualiser_pyside6.py:2093 |
| LiftMonitorDialog | Workspace / dialog | Main chapters 5, 6, 10, 11 | visualiser/amr_sim_visualiser_pyside6.py:2177 |
| AmrTimelineWidget | Workspace / dialog | Relinking and evidence | visualiser/amr_sim_visualiser_pyside6.py:2249 |
| AuxiliaryTimelineWindow | Workspace / dialog | Relinking and evidence | visualiser/amr_sim_visualiser_pyside6.py:2584 |
| FailedTasksDialog | Workspace / dialog | Advanced demand | visualiser/amr_sim_visualiser_pyside6.py:2772 |
| LocationInventoryPayloadDialog | Workspace / dialog | Inventory and exchanges | visualiser/amr_sim_visualiser_pyside6.py:2883 |
| SimulationVisualizer | Workspace / dialog | Drawing tools and layers | visualiser/amr_sim_visualiser_pyside6.py:2972 |
| Tasks by AMR | setWindowTitle | Advanced demand | visualiser/amr_sim_visualiser_pyside6.py:1433 |
| Tasks by location / department | setWindowTitle | Advanced demand | visualiser/amr_sim_visualiser_pyside6.py:1672 |
| Close | QPushButton | Drawing tools and layers | visualiser/amr_sim_visualiser_pyside6.py:1716 |
| Close | QPushButton | Drawing tools and layers | visualiser/amr_sim_visualiser_pyside6.py:1933 |
| Close | QPushButton | Drawing tools and layers | visualiser/amr_sim_visualiser_pyside6.py:1996 |
| Close | QPushButton | Drawing tools and layers | visualiser/amr_sim_visualiser_pyside6.py:2085 |
| AMR Payload Monitor | setWindowTitle | Inventory and exchanges | visualiser/amr_sim_visualiser_pyside6.py:2110 |
| No simulation loaded | QLabel | Drawing tools and layers | visualiser/amr_sim_visualiser_pyside6.py:2116 |
| Close | QPushButton | Drawing tools and layers | visualiser/amr_sim_visualiser_pyside6.py:2132 |
| Lift Monitor | setWindowTitle | Main chapters 5, 6, 10, 11 | visualiser/amr_sim_visualiser_pyside6.py:2180 |
| AMR Timeline | setWindowTitle | Relinking and evidence | visualiser/amr_sim_visualiser_pyside6.py:2590 |
| Failed tasks | setWindowTitle | Advanced demand | visualiser/amr_sim_visualiser_pyside6.py:2787 |
| View at destination | QPushButton | Drawing tools and layers | visualiser/amr_sim_visualiser_pyside6.py:2828 |
| Close | QPushButton | Drawing tools and layers | visualiser/amr_sim_visualiser_pyside6.py:2832 |
| Close | QPushButton | Drawing tools and layers | visualiser/amr_sim_visualiser_pyside6.py:2919 |
| AMR Simulation Visualiser (PySide6) | setWindowTitle | Drawing tools and layers | visualiser/amr_sim_visualiser_pyside6.py:2975 |
| Show DXF | QCheckBox | Drawing tools and layers | visualiser/amr_sim_visualiser_pyside6.py:3211 |
| Show labels | QCheckBox | Drawing tools and layers | visualiser/amr_sim_visualiser_pyside6.py:3216 |
| Follow slider time | QCheckBox | Drawing tools and layers | visualiser/amr_sim_visualiser_pyside6.py:3221 |
| Show AMR box | QCheckBox | Drawing tools and layers | visualiser/amr_sim_visualiser_pyside6.py:3224 |
| Show AMR charge state | QCheckBox | Inventory and exchanges | visualiser/amr_sim_visualiser_pyside6.py:3229 |
| Draw AMR battery percentage/charging state labels. Leave off for faster playback on large logs. | setToolTip | Relinking and evidence | visualiser/amr_sim_visualiser_pyside6.py:3231 |
| Show seeded waste containers | QCheckBox | Drawing tools and layers | visualiser/amr_sim_visualiser_pyside6.py:3237 |
| Show payloads in room spaces | QCheckBox | Inventory and exchanges | visualiser/amr_sim_visualiser_pyside6.py:3244 |
| Show drop-off-zone staff handoffs | QCheckBox | Staff and people | visualiser/amr_sim_visualiser_pyside6.py:3249 |
| Animate the person carrying a payload from its drop-off zone to the final destination, manoeuvring full/empty exchanges, and returning the empty/equivalent payload. | setToolTip | Staff and people | visualiser/amr_sim_visualiser_pyside6.py:3253 |
| Update waste fill rate during playback | QCheckBox | Relinking and evidence | visualiser/amr_sim_visualiser_pyside6.py:3261 |
| AMR size is taken from each AMR definition | QLabel | Drawing tools and layers | visualiser/amr_sim_visualiser_pyside6.py:3266 |
| Enable follow | QCheckBox | Drawing tools and layers | visualiser/amr_sim_visualiser_pyside6.py:3275 |
| No simulation loaded | QLabel | Drawing tools and layers | visualiser/amr_sim_visualiser_pyside6.py:3279 |
| No files loaded | QLabel | Drawing tools and layers | visualiser/amr_sim_visualiser_pyside6.py:3296 |
| Ready | QLabel | Drawing tools and layers | visualiser/amr_sim_visualiser_pyside6.py:3301 |
| Timeline | QLabel | Relinking and evidence | visualiser/amr_sim_visualiser_pyside6.py:3342 |
| Connecting to the separate timeline GUI process... | QLabel | Relinking and evidence | visualiser/amr_sim_visualiser_pyside6.py:3387 |
| Loading DXFs | setWindowTitle | Drawing tools and layers | visualiser/amr_sim_visualiser_pyside6.py:3585 |
| Show AMRs at node | addAction | Drawing tools and layers | visualiser/amr_sim_visualiser_pyside6.py:8433 |
| Show drop-off tasks at location | addAction | Advanced demand | visualiser/amr_sim_visualiser_pyside6.py:8438 |
| Show pickup tasks at location | addAction | Advanced demand | visualiser/amr_sim_visualiser_pyside6.py:8443 |
| Group by | QLabel | Drawing tools and layers | visualiser/amr_sim_visualiser_pyside6.py:1682 |
| Filter | QLabel | Drawing tools and layers | visualiser/amr_sim_visualiser_pyside6.py:1688 |
| Waiting AMRs | QLabel | Drawing tools and layers | visualiser/amr_sim_visualiser_pyside6.py:2211 |
| Filter | QLabel | Drawing tools and layers | visualiser/amr_sim_visualiser_pyside6.py:2802 |
| Floor | QLabel | Main chapters 1, 2, 3 | visualiser/amr_sim_visualiser_pyside6.py:3205 |
| Follow AMR | QLabel | Drawing tools and layers | visualiser/amr_sim_visualiser_pyside6.py:3270 |
| Playback speed (sim seconds / real second) | QLabel | Relinking and evidence | visualiser/amr_sim_visualiser_pyside6.py:3288 |
| Loaded files | QLabel | Drawing tools and layers | visualiser/amr_sim_visualiser_pyside6.py:3295 |
| Status | QLabel | Drawing tools and layers | visualiser/amr_sim_visualiser_pyside6.py:3300 |
| Zoom | QLabel | Appearance and keyboard | visualiser/amr_sim_visualiser_pyside6.py:3384 |
| View inventory spaces | addAction | Inventory and exchanges | visualiser/amr_sim_visualiser_pyside6.py:8451 |
| Payloads | addMenu | Inventory and exchanges | visualiser/amr_sim_visualiser_pyside6.py:8457 |
| View current payloads | addAction | Inventory and exchanges | visualiser/amr_sim_visualiser_pyside6.py:8458 |
| Find maximum space utilisation | addAction | Drawing tools and layers | visualiser/amr_sim_visualiser_pyside6.py:8464 |
| VulkanViewportWidget | Workspace / dialog | Drawing tools and layers | visualiser/amr_vulkan_viewport.py:118 |
| DXFLoadingDialog | Workspace / dialog | Drawing tools and layers | visualiser/app.py:181 |
| AMRGraphEditor | Workspace / dialog | Drawing tools and layers | visualiser/app.py:368 |
| Loading DXFs | setWindowTitle | Drawing tools and layers | visualiser/app.py:185 |
| Loading DXF files... | QLabel | Drawing tools and layers | visualiser/app.py:192 |
| 0 / 0 | QLabel | Drawing tools and layers | visualiser/app.py:201 |
| AMR Engineering Project | setWindowTitle | Recovery and run outcomes | visualiser/app.py:373 |
| Choose what a mouse click does in the topology editor. | setToolTip | Drawing tools and layers | visualiser/app.py:951 |
| Grid snap | QCheckBox | Main chapters 1, 2, 3 | visualiser/app.py:956 |
| Drawing grid spacing in metres | setAccessibleName | Drawing tools and layers | visualiser/app.py:963 |
| Placement grid spacing; typed coordinates bypass this grid. The display grid adapts to zoom independently. | setToolTip | Appearance and keyboard | visualiser/app.py:964 |
| Object snap | QCheckBox | Main chapters 1, 2, 3 | visualiser/app.py:965 |
| Object snap preset | setAccessibleName | Main chapters 1, 2, 3 | visualiser/app.py:968 |
| Choose a single preset here, or combine targets using the bottom-right object snap toggles. Perpendicular requires a current route endpoint. Exact overlaps always reuse or split existing geometry. | setToolTip | Batching and route restrictions | visualiser/app.py:971 |
| Attract corridor, node and door placement to nearby graph points and edges. Exact coincidences still connect to avoid duplicate topology. | setToolTip | Main chapters 1, 2, 3 | visualiser/app.py:974 |
| Chain edge creation | QCheckBox | Drawing tools and layers | visualiser/app.py:979 |
| Bidirectional edges | QCheckBox | Drawing tools and layers | visualiser/app.py:981 |
| Connect crossings while drawing corridors | QCheckBox | Main chapters 1, 2, 3 | visualiser/app.py:983 |
| Create shared junctions at crossings along each new segment. Previewed junctions and corridor splits form one undoable edit. Off leaves crossings unconnected. | setToolTip | Relinking and evidence | visualiser/app.py:984 |
| Show DXF | QCheckBox | Drawing tools and layers | visualiser/app.py:986 |
| Show PDF underlay | QCheckBox | Report options | visualiser/app.py:988 |
| Show labels | QCheckBox | Drawing tools and layers | visualiser/app.py:990 |
| Graph object name visibility | setAccessibleName | Drawing tools and layers | visualiser/app.py:993 |
| Filter graph names without hiding objects. Selected corridor endpoints and selected route-profile points are included. Door symbols and profile labels are separate. | setToolTip | Batching and route restrictions | visualiser/app.py:996 |
| Show location bounding boxes | QCheckBox | Drawing tools and layers | visualiser/app.py:999 |
| Show charging spaces | QCheckBox | Inventory and exchanges | visualiser/app.py:1001 |
| Undo | QAction | Drawing tools and layers | visualiser/app.py:1116 |
| Redo | QAction | Drawing tools and layers | visualiser/app.py:1119 |
| Undo | QPushButton | Drawing tools and layers | visualiser/app.py:1123 |
| Redo | QPushButton | Drawing tools and layers | visualiser/app.py:1124 |
| Cancel current CAD command | QAction | Recovery and run outcomes | visualiser/app.py:1151 |
| Route profile display | setAccessibleName | Batching and route restrictions | visualiser/app.py:1159 |
| Show profile labels | QCheckBox | Batching and route restrictions | visualiser/app.py:1163 |
| Classify selected corridors | QPushButton | Main chapters 1, 2, 3 | visualiser/app.py:1196 |
| Set selected door nodes | QPushButton | Main chapters 1, 2, 3 | visualiser/app.py:1209 |
| Mark as door… | addAction | Main chapters 1, 2, 3 | visualiser/app.py:1211 |
| Remove door classification | addAction | Main chapters 1, 2, 3 | visualiser/app.py:1212 |
| Simulation running — project editing is locked. Stop the run in Simulate or wait for it to finish. | QLabel | Recovery and run outcomes | visualiser/app.py:1303 |
| Simulation project editing lock | setAccessibleName | Recovery and run outcomes | visualiser/app.py:1305 |
| Ready | QLabel | Drawing tools and layers | visualiser/app.py:1309 |
| New file | QLabel | Drawing tools and layers | visualiser/app.py:1311 |
| Current JSON file | setToolTip | Drawing tools and layers | visualiser/app.py:1312 |
| Finish corridor route | QAction | Batching and route restrictions | visualiser/app.py:1386 |
| Apply route profile selection | addAction | Batching and route restrictions | visualiser/app.py:4142 |
| Cancel route profile selection | addAction | Recovery and run outcomes | visualiser/app.py:4143 |
| Show all edge connections | addAction | Drawing tools and layers | visualiser/app.py:4361 |
| Create department here | addAction | Drawing tools and layers | visualiser/app.py:4362 |
| Edit selected corridor widths / doors | addAction | Main chapters 1, 2, 3 | visualiser/app.py:4182 |
| Create people movement profile | addAction | Staff and people | visualiser/app.py:4186 |
| Add selection to scenario | addAction | Drawing tools and layers | visualiser/app.py:4190 |
| Classify corridor use | addMenu | Main chapters 1, 2, 3 | visualiser/app.py:4194 |
| Clear selection | addAction | Drawing tools and layers | visualiser/app.py:4216 |
| Draw / replace bounding box | addAction | Drawing tools and layers | visualiser/app.py:4243 |
| Edit department | addAction | Drawing tools and layers | visualiser/app.py:4321 |
| Delete department | addAction | Drawing tools and layers | visualiser/app.py:4322 |
| Add / edit room bounding box | addAction | Drawing tools and layers | visualiser/app.py:4348 |
| Draw rectangular boundary | addAction | Drawing tools and layers | visualiser/app.py:4349 |
| Inventory spaces | addAction | Inventory and exchanges | visualiser/app.py:4355 |
| Insert node here | addAction | Drawing tools and layers | visualiser/app.py:4174 |
| Create junction at crossing | addAction | Drawing tools and layers | visualiser/app.py:4176 |
| Split selected corridors at midpoint | addAction | Main chapters 1, 2, 3 | visualiser/app.py:4178 |
| Subdivide selected corridors… | addAction | Main chapters 1, 2, 3 | visualiser/app.py:4179 |
| Door nodes | addMenu | Main chapters 1, 2, 3 | visualiser/app.py:4206 |
| Mark selected nodes as doors… | addAction | Main chapters 1, 2, 3 | visualiser/app.py:4207 |
| Remove door classification | addAction | Main chapters 1, 2, 3 | visualiser/app.py:4211 |
| Edit existing bounding box | addAction | Drawing tools and layers | visualiser/app.py:4247 |
| Remove bounding box | addAction | Drawing tools and layers | visualiser/app.py:4248 |
| Cancel current bounding box drawing | addAction | Recovery and run outcomes | visualiser/app.py:4251 |
| Remove room bounding box | addAction | Drawing tools and layers | visualiser/app.py:4353 |
| AppearancePanel | Workspace / dialog | Appearance and keyboard | visualiser/appearance_panel.py:8 |
| Appearance | QLabel | Appearance and keyboard | visualiser/appearance_panel.py:13 |
| Display preferences are saved for this Windows user, separately from projects and simulation results. Choose a preset, adjust text, then Apply. Blank interface/background colours and auto map text use the preset. | QLabel | Recovery and run outcomes | visualiser/appearance_panel.py:16 |
| &Theme | addRow | Appearance and keyboard | visualiser/appearance_panel.py:32 |
| &Interface text | addRow | Drawing tools and layers | visualiser/appearance_panel.py:36 |
| &Layout map text | addRow | Drawing tools and layers | visualiser/appearance_panel.py:40 |
| Show layout map legend | QCheckBox | Drawing tools and layers | visualiser/appearance_panel.py:58 |
| Show adaptive metre grid | QCheckBox | Drawing tools and layers | visualiser/appearance_panel.py:60 |
| Preview: project objects, labels and instructions | QLabel | Relinking and evidence | visualiser/appearance_panel.py:62 |
| Presets apply to standard application controls and dialogs. Layout labels and the legend have their own text size and colour. Robot playback, timelines, drawing underlays and some legacy custom controls retain their existing rendering. Contrast checks cover the theme backgrounds, not imported drawings. This is not a claim of complete accessibility compliance. | QLabel | Appearance and keyboard | visualiser/appearance_panel.py:70 |
| Use &defaults | QPushButton | Drawing tools and layers | visualiser/appearance_panel.py:80 |
| &Revert draft | QPushButton | Drawing tools and layers | visualiser/appearance_panel.py:81 |
| &Apply appearance | QPushButton | Appearance and keyboard | visualiser/appearance_panel.py:82 |
| Choose… | QPushButton | Drawing tools and layers | visualiser/appearance_panel.py:52 |
| BoundaryInput | Workspace / dialog | Drawing tools and layers | visualiser/boundary_input.py:7 |
| Boundary vertex coordinates in metres | setAccessibleName | Drawing tools and layers | visualiser/boundary_input.py:15 |
| Absolute coordinates or displacement from the last vertex. Angles are counterclockwise from east. Typed vertices bypass snapping. Enter adds a vertex; blank Enter finishes; Escape cancels. | setToolTip | Recovery and run outcomes | visualiser/boundary_input.py:16 |
| Boundary (m) | QLabel | Drawing tools and layers | visualiser/boundary_input.py:19 |
| Add point | QPushButton | Drawing tools and layers | visualiser/boundary_input.py:21 |
| Undo point | QPushButton | Drawing tools and layers | visualiser/boundary_input.py:22 |
| Finish | QPushButton | Drawing tools and layers | visualiser/boundary_input.py:23 |
| Save the added vertices as a closed polygon. Add any pending coordinate first. | setToolTip | Recovery and run outcomes | visualiser/boundary_input.py:24 |
| Cancel | QPushButton | Recovery and run outcomes | visualiser/boundary_input.py:25 |
| Boundary draft coordinates and input errors | setAccessibleName | Drawing tools and layers | visualiser/boundary_input.py:28 |
| BuildingSettingsDialog | Workspace / dialog | Main chapters 1, 2, 3 | visualiser/building_settings.py:68 |
| Building settings | setWindowTitle | Main chapters 1, 2, 3 | visualiser/building_settings.py:71 |
| Level height is the vertical distance between adjacent floors and applies to every level. Lift speeds in metres per second are kept; travel times and vertical distances use the new height. | QLabel | Main chapters 5, 6, 10, 11 | visualiser/building_settings.py:75 |
| Number of floors | setAccessibleName | Main chapters 1, 2, 3 | visualiser/building_settings.py:83 |
| Number of floors | addRow | Main chapters 1, 2, 3 | visualiser/building_settings.py:91 |
| Level height in metres | setAccessibleName | Drawing tools and layers | visualiser/building_settings.py:96 |
| Level height | addRow | Drawing tools and layers | visualiser/building_settings.py:103 |
| BuildingCourse | Workspace / dialog | Main chapters 1, 2, 3 | visualiser/building_tutorial_panel.py:14 |
| Build, test and improve a three-floor flow design. Check real results at each step. | QLabel | Recovery and run outcomes | visualiser/building_tutorial_panel.py:20 |
| Building course chapter | setAccessibleName | Main chapters 1, 2, 3 | visualiser/building_tutorial_panel.py:22 |
| Building course instructions | setAccessibleName | Main chapters 1, 2, 3 | visualiser/building_tutorial_panel.py:25 |
| Previous | QPushButton | Drawing tools and layers | visualiser/building_tutorial_panel.py:30 |
| Next | QPushButton | Drawing tools and layers | visualiser/building_tutorial_panel.py:30 |
| Check this step | QPushButton | Recovery and run outcomes | visualiser/building_tutorial_panel.py:30 |
| Open workspace | QPushButton | Drawing tools and layers | visualiser/building_tutorial_panel.py:31 |
| Dedicated lift permissions | addItem | Main chapters 5, 6, 10, 11 | visualiser/building_tutorial_panel.py:35 |
| Shared lift permissions | addItem | Main chapters 5, 6, 10, 11 | visualiser/building_tutorial_panel.py:35 |
| Describes the route permissions you configure. Selecting this does not change project inputs. | setToolTip | Recovery and run outcomes | visualiser/building_tutorial_panel.py:36 |
| Illustrated building guide | addAction | Main chapters 1, 2, 3 | visualiser/building_tutorial_panel.py:47 |
| Complete interface reference | addAction | Drawing tools and layers | visualiser/building_tutorial_panel.py:48 |
| Flow policy | QLabel | Drawing tools and layers | visualiser/building_tutorial_panel.py:34 |
| Copy selection displacement in metres | setAccessibleName | Drawing tools and layers | visualiser/cad_copy_input.py:13 |
| Copy occupied bays | QCheckBox | Inventory and exchanges | visualiser/cad_copy_input.py:15 |
| Off creates empty bays with the same templates. On copies each bay occupied flag. Fleet and demand rules remain separate. | setToolTip | Advanced demand | visualiser/cad_copy_input.py:16 |
| CadDrawingInput | Workspace / dialog | Drawing tools and layers | visualiser/cad_drawing_input.py:62 |
| Next point (m) | QLabel | Drawing tools and layers | visualiser/cad_drawing_input.py:72 |
| Corridor drawing direction constraint | setAccessibleName | Main chapters 1, 2, 3 | visualiser/cad_drawing_input.py:74 |
| Constrain mouse placement from the current route end. Grid applies first; object snapping must retain the constrained direction. Typed coordinates override direction and grid. | setToolTip | Batching and route restrictions | visualiser/cad_drawing_input.py:78 |
| Corridor coordinate entry in metres | setAccessibleName | Main chapters 1, 2, 3 | visualiser/cad_drawing_input.py:82 |
| Absolute X,Y; relative @dx,dy; polar @length<angle. Angles: 0° east, 90° north. Enter places a point; blank Enter finishes; Escape cancels the draft. Typed points bypass grid and direction constraints. Object snapping follows the Object snap setting; review the actual endpoint before Enter. | setToolTip | Relinking and evidence | visualiser/cad_drawing_input.py:83 |
| Drawing coordinates, snapping and input errors | setAccessibleName | Main chapters 1, 2, 3 | visualiser/cad_drawing_input.py:90 |
| CadEndpointInput | Workspace / dialog | Drawing tools and layers | visualiser/cad_endpoint_input.py:7 |
| Free corridor endpoint to trim or extend | setAccessibleName | Main chapters 1, 2, 3 | visualiser/cad_endpoint_input.py:17 |
| Boundary corridor | setAccessibleName | Main chapters 1, 2, 3 | visualiser/cad_endpoint_input.py:19 |
| Pick boundary | QPushButton | Drawing tools and layers | visualiser/cad_endpoint_input.py:20 |
| Apply | QPushButton | Drawing tools and layers | visualiser/cad_endpoint_input.py:21 |
| Cancel | QPushButton | Recovery and run outcomes | visualiser/cad_endpoint_input.py:22 |
| Choose or pick a corridor | addItem | Main chapters 1, 2, 3 | visualiser/cad_endpoint_input.py:43 |
| Endpoint | QLabel | Drawing tools and layers | visualiser/cad_endpoint_input.py:23 |
| Boundary | QLabel | Drawing tools and layers | visualiser/cad_endpoint_input.py:23 |
| CadMoveInput | Workspace / dialog | Drawing tools and layers | visualiser/cad_move_input.py:9 |
| Move selection displacement in metres | setAccessibleName | Drawing tools and layers | visualiser/cad_move_input.py:24 |
| Translation in metres; positive X east, positive Y north. Grid and direction constraints do not alter these values. | setToolTip | Drawing tools and layers | visualiser/cad_move_input.py:26 |
| Apply move | QPushButton | Drawing tools and layers | visualiser/cad_move_input.py:29 |
| Cancel | QPushButton | Recovery and run outcomes | visualiser/cad_move_input.py:30 |
| Pick destination | QPushButton | Drawing tools and layers | visualiser/cad_move_input.py:31 |
| Click a base point, then a destination. Uses the selected grid/object snap mode; perpendicular uses the base point. Reference picks never split corridors. Escape or right-click cancels. | setToolTip | Recovery and run outcomes | visualiser/cad_move_input.py:32 |
| Move by (m) | QLabel | Drawing tools and layers | visualiser/cad_move_input.py:33 |
| CadRotateInput | Workspace / dialog | Drawing tools and layers | visualiser/cad_rotate_input.py:10 |
| Rotation centre X,Y in metres | setAccessibleName | Drawing tools and layers | visualiser/cad_rotate_input.py:25 |
| Absolute world coordinates in metres. Initially the centre of the selected point extents; edit to choose another pivot. | setToolTip | Drawing tools and layers | visualiser/cad_rotate_input.py:27 |
| Rotation angle in degrees counterclockwise | setAccessibleName | Drawing tools and layers | visualiser/cad_rotate_input.py:29 |
| Counterclockwise degrees; negative values rotate clockwise. Typed values bypass snapping. | setToolTip | Main chapters 1, 2, 3 | visualiser/cad_rotate_input.py:32 |
| Apply rotation | QPushButton | Drawing tools and layers | visualiser/cad_rotate_input.py:33 |
| Cancel | QPushButton | Recovery and run outcomes | visualiser/cad_rotate_input.py:34 |
| Pick rotation | QPushButton | Drawing tools and layers | visualiser/cad_rotate_input.py:35 |
| Click centre, reference direction, then target direction to apply. Uses the selected grid/object snap mode; perpendicular uses the centre. Reference picks never split corridors. Escape cancels. | setToolTip | Recovery and run outcomes | visualiser/cad_rotate_input.py:36 |
| Centre (m) | QLabel | Drawing tools and layers | visualiser/cad_rotate_input.py:39 |
| Angle (°) | QLabel | Drawing tools and layers | visualiser/cad_rotate_input.py:39 |
| CadSnapControls | Workspace / dialog | Main chapters 1, 2, 3 | visualiser/cad_snap_controls.py:5 |
| Object snap targets | setAccessibleName | Main chapters 1, 2, 3 | visualiser/cad_snap_controls.py:10 |
| Enable object snapping | setAccessibleName | Main chapters 1, 2, 3 | visualiser/cad_snap_controls.py:16 |
| Enable object snapping using any combination of the adjacent targets. Disabling keeps your chosen targets. | setToolTip | Main chapters 1, 2, 3 | visualiser/cad_snap_controls.py:17 |
| Combined targets | addItem | Drawing tools and layers | visualiser/cad_snap_controls.py:41 |
| CAD drawing commands | setAccessibleName | Drawing tools and layers | visualiser/cad_toolbar.py:13 |
| Manage departments… | QAction | Drawing tools and layers | visualiser/cad_toolbar.py:35 |
| Add, edit or remove departments and their workflow locations. | setToolTip | Drawing tools and layers | visualiser/cad_toolbar.py:36 |
| Fit | command | Drawing tools and layers | visualiser/cad_toolbar.py:45 |
| Floor  | QLabel | Main chapters 1, 2, 3 | visualiser/cad_toolbar.py:48 |
| Current floor | setAccessibleName | Main chapters 1, 2, 3 | visualiser/cad_toolbar.py:51 |
| Current drawing floor. This is the same floor selection used by the project tree. | setToolTip | Recovery and run outcomes | visualiser/cad_toolbar.py:52 |
| Grid snap | command | Main chapters 1, 2, 3 | visualiser/cad_toolbar.py:54 |
| Object snap | command | Main chapters 1, 2, 3 | visualiser/cad_toolbar.py:59 |
| Grid | command | Drawing tools and layers | visualiser/cad_toolbar.py:66 |
| Properties | command | Main chapters 1, 2, 3 | visualiser/cad_toolbar.py:71 |
| Check | command | Recovery and run outcomes | visualiser/cad_toolbar.py:73 |
| Project tree | command | Recovery and run outcomes | visualiser/cad_toolbar.py:75 |
| More tools | command | Drawing tools and layers | visualiser/cad_toolbar.py:77 |
| Focus canvas | command | Appearance and keyboard | visualiser/cad_toolbar.py:79 |
| Show or hide selection properties | setAccessibleName | Main chapters 1, 2, 3 | visualiser/cad_workbench.py:15 |
| Open selection properties. Closing this panel keeps any unapplied draft. | setToolTip | Main chapters 1, 2, 3 | visualiser/cad_workbench.py:16 |
| Project workflow stages | setAccessibleName | Recovery and run outcomes | visualiser/cad_workbench.py:44 |
| Save | action | Recovery and run outcomes | visualiser/cad_workbench.py:49 |
| Interface text size | setAccessibleName | Appearance and keyboard | visualiser/cad_workbench.py:76 |
| Change interface text size. Saved as a personal preference, not project data. | setToolTip | Appearance and keyboard | visualiser/cad_workbench.py:77 |
| Interface colour theme | setAccessibleName | Appearance and keyboard | visualiser/cad_workbench.py:81 |
| Choose an accessible application theme. Personal appearance does not change simulation inputs. | setToolTip | Appearance and keyboard | visualiser/cad_workbench.py:82 |
| Help | action | Drawing tools and layers | visualiser/cad_workbench.py:89 |
| Appearance… | action | Appearance and keyboard | visualiser/cad_workbench.py:91 |
| Project checks · Not checked | QLabel | Recovery and run outcomes | visualiser/cad_workbench.py:98 |
| Current project check status | setAccessibleName | Recovery and run outcomes | visualiser/cad_workbench.py:100 |
| Open checks | QPushButton | Recovery and run outcomes | visualiser/cad_workbench.py:102 |
| Open checks for the current project. Drawing and selection do not run checks automatically. | setToolTip | Recovery and run outcomes | visualiser/cad_workbench.py:104 |
| &File | addMenu | Drawing tools and layers | visualiser/cad_workbench.py:137 |
| New project | action | Recovery and run outcomes | visualiser/cad_workbench.py:138 |
| Open project / JSON… | action | Recovery and run outcomes | visualiser/cad_workbench.py:141 |
| Save project as… | action | Recovery and run outcomes | visualiser/cad_workbench.py:145 |
| &Edit | addMenu | Drawing tools and layers | visualiser/cad_workbench.py:154 |
| Delete selected | action | Drawing tools and layers | visualiser/cad_workbench.py:157 |
| Move selected by… | action | Drawing tools and layers | visualiser/cad_workbench.py:162 |
| Rotate selected… | action | Drawing tools and layers | visualiser/cad_workbench.py:167 |
| Copy selected by… | action | Drawing tools and layers | visualiser/cad_workbench.py:170 |
| Trim / extend corridor… | action | Main chapters 1, 2, 3 | visualiser/cad_workbench.py:173 |
| &View | addMenu | Drawing tools and layers | visualiser/cad_workbench.py:179 |
| Zoom to selection | action | Appearance and keyboard | visualiser/cad_workbench.py:181 |
| Object names | addMenu | Drawing tools and layers | visualiser/cad_workbench.py:193 |
| Map key | action | Drawing tools and layers | visualiser/cad_workbench.py:205 |
| &Help | addMenu | Drawing tools and layers | visualiser/cad_workbench.py:212 |
| Guided walkthrough… | action | Drawing tools and layers | visualiser/cad_workbench.py:213 |
| Restart tutorial bubble | action | Main chapters 1, 2 | visualiser/cad_workbench.py:218 |
| Text  | QLabel | Drawing tools and layers | visualiser/cad_workbench.py:85 |
| Theme  | QLabel | Appearance and keyboard | visualiser/cad_workbench.py:87 |
| Export JSON… | action | Report options | visualiser/cad_workbench.py:148 |
| Recover unsaved work… | action | Recovery and run outcomes | visualiser/cad_workbench.py:151 |
| Close window | action | Drawing tools and layers | visualiser/cad_workbench.py:153 |
| Clear selection | action | Drawing tools and layers | visualiser/cad_workbench.py:177 |
| Model layers… | action | Drawing tools and layers | visualiser/cad_workbench.py:184 |
| DXF layers… | action | Drawing tools and layers | visualiser/cad_workbench.py:186 |
| Building flow tutorial… | action | Main chapters 1, 2 | visualiser/cad_workbench.py:216 |
| Model scope and checks | action | Recovery and run outcomes | visualiser/cad_workbench.py:222 |
| Settings sections | setAccessibleName | Drawing tools and layers | visualiser/compact_forms.py:21 |
| DemandPreviewPanel | Workspace / dialog | Relinking and evidence | visualiser/demand_preview_panel.py:87 |
| Inspect planned demand before simulation. Runtime-dependent demand and returns remain unknown; these are not completed movements. | QLabel | Recovery and run outcomes | visualiser/demand_preview_panel.py:95 |
| Build preview | QPushButton | Relinking and evidence | visualiser/demand_preview_panel.py:99 |
| Preview end date and time, ISO format | setAccessibleName | Relinking and evidence | visualiser/demand_preview_panel.py:103 |
| Export preview… | QPushButton | Report options | visualiser/demand_preview_panel.py:105 |
| Build a preview to inspect demand. Maximum 31 days and 20,000 task records. | QLabel | Relinking and evidence | visualiser/demand_preview_panel.py:113 |
| Search demand | setAccessibleName | Advanced demand | visualiser/demand_preview_panel.py:118 |
| Tasks | addTab | Advanced demand | visualiser/demand_preview_panel.py:137 |
| Timetable | addTab | Drawing tools and layers | visualiser/demand_preview_panel.py:138 |
| Rules and reconciliation | addTab | Drawing tools and layers | visualiser/demand_preview_panel.py:139 |
| Select a task or rule to inspect its resolved rule settings. | QLabel | Advanced demand | visualiser/demand_preview_panel.py:142 |
| Search effective rule settings | setAccessibleName | Drawing tools and layers | visualiser/demand_preview_panel.py:147 |
| Effective settings | addTab | Drawing tools and layers | visualiser/demand_preview_panel.py:151 |
| Demand origin, effective values and precedence | setAccessibleName | Advanced demand | visualiser/demand_preview_panel.py:161 |
| DayOfWeekSelector | Workspace / dialog | Drawing tools and layers | visualiser/dialogs.py:170 |
| PeopleProfilePreview | Workspace / dialog | Relinking and evidence | visualiser/dialogs.py:214 |
| ScheduledTimesDialog | Workspace / dialog | Staff and people | visualiser/dialogs.py:386 |
| StaffWeeklyHoursDialog | Workspace / dialog | Staff and people | visualiser/dialogs.py:537 |
| GlobalStaffConfigDialog | Workspace / dialog | Staff and people | visualiser/dialogs.py:631 |
| BulkDepartmentTaskGenerationDialog | Workspace / dialog | Advanced demand | visualiser/dialogs.py:902 |
| ConfiguredGroupSelectDialog | Workspace / dialog | Drawing tools and layers | visualiser/dialogs.py:1994 |
| TaskGenerationSettingsDialog | Workspace / dialog | Advanced demand | visualiser/dialogs.py:2032 |
| PointEditorDialog | Workspace / dialog | Drawing tools and layers | visualiser/dialogs.py:4558 |
| EdgeConnectionsDialog | Workspace / dialog | Drawing tools and layers | visualiser/dialogs.py:4741 |
| LiftEditorDialog | Workspace / dialog | Main chapters 5, 6, 10, 11 | visualiser/dialogs.py:4842 |
| LiftListDialog | Workspace / dialog | Main chapters 5, 6, 10, 11 | visualiser/dialogs.py:5189 |
| AMRPayloadSlotDialog | Workspace / dialog | Inventory and exchanges | visualiser/dialogs.py:5406 |
| AMREditorDialog | Workspace / dialog | Drawing tools and layers | visualiser/dialogs.py:5505 |
| PayloadTrackedItemDialog | Workspace / dialog | Inventory and exchanges | visualiser/dialogs.py:5842 |
| PayloadEditorDialog | Workspace / dialog | Inventory and exchanges | visualiser/dialogs.py:5988 |
| PayloadListDialog | Workspace / dialog | Inventory and exchanges | visualiser/dialogs.py:6288 |
| AMRListDialog | Workspace / dialog | Drawing tools and layers | visualiser/dialogs.py:6448 |
| TableListEditor | Workspace / dialog | Drawing tools and layers | visualiser/dialogs.py:6577 |
| RouteProfilesEditor | Workspace / dialog | Batching and route restrictions | visualiser/dialogs.py:6694 |
| PeopleMovementEditorDialog | Workspace / dialog | Staff and people | visualiser/dialogs.py:6708 |
| PeopleMovementListDialog | Workspace / dialog | Staff and people | visualiser/dialogs.py:7202 |
| ScenarioEventDialog | Workspace / dialog | Drawing tools and layers | visualiser/dialogs.py:7429 |
| ScenarioTestingDialog | Workspace / dialog | Drawing tools and layers | visualiser/dialogs.py:7714 |
| CorridorSettingsDialog | Workspace / dialog | Main chapters 1, 2, 3 | visualiser/dialogs.py:8157 |
| SimulationSettingsDialog | Workspace / dialog | Drawing tools and layers | visualiser/dialogs.py:8647 |
| WasteStreamEditorDialog | Workspace / dialog | Drawing tools and layers | visualiser/dialogs.py:9089 |
| WasteStreamListDialog | Workspace / dialog | Drawing tools and layers | visualiser/dialogs.py:9159 |
| MassCollectionEditorDialog | Workspace / dialog | Drawing tools and layers | visualiser/dialogs.py:9268 |
| MassCollectionListDialog | Workspace / dialog | Drawing tools and layers | visualiser/dialogs.py:9492 |
| DepartmentWasteStreamSettingsDialog | Workspace / dialog | Drawing tools and layers | visualiser/dialogs.py:9614 |
| DepartmentWasteStreamItemDialog | Workspace / dialog | Drawing tools and layers | visualiser/dialogs.py:9757 |
| DepartmentDropoffZoneCreationDialog | Workspace / dialog | Drawing tools and layers | visualiser/dialogs.py:10022 |
| DepartmentEditorDialog | Workspace / dialog | Drawing tools and layers | visualiser/dialogs.py:10183 |
| BulkDepartmentWasteStreamControlDialog | Workspace / dialog | Drawing tools and layers | visualiser/dialogs.py:10961 |
| TaskCategoryCommonLocationWizard | Workspace / dialog | Advanced demand | visualiser/dialogs.py:11491 |
| TaskCategorySharedBinGroupWizard | Workspace / dialog | Advanced demand | visualiser/dialogs.py:11810 |
| DepartmentListDialog | Workspace / dialog | Drawing tools and layers | visualiser/dialogs.py:12283 |
| ArrayInventorySpacesDialog | Workspace / dialog | Inventory and exchanges | visualiser/dialogs.py:13346 |
| InventorySpacesDialog | Workspace / dialog | Inventory and exchanges | visualiser/dialogs.py:13466 |
| Available first assigns a separate service. Batch same location shares overlapping services at one location; minimise movement also prefers the previous person when arrival times tie. Busy teams grow automatically. | setToolTip | Staff and people | visualiser/dialogs.py:111 |
| Scheduled times | setWindowTitle | Staff and people | visualiser/dialogs.py:389 |
| Add time | QPushButton | Drawing tools and layers | visualiser/dialogs.py:406 |
| Remove selected | QPushButton | Drawing tools and layers | visualiser/dialogs.py:418 |
| Clear all | QPushButton | Drawing tools and layers | visualiser/dialogs.py:419 |
| Sort | QPushButton | Drawing tools and layers | visualiser/dialogs.py:420 |
| Staff working hours by day | setWindowTitle | Staff and people | visualiser/dialogs.py:546 |
| Override the global shift hours for this category or department. These hours control timeframe task spacing and the actual times at which staff can travel to and handle delivered payloads. | QLabel | Advanced demand | visualiser/dialogs.py:552 |
| Use these custom working hours | QCheckBox | Drawing tools and layers | visualiser/dialogs.py:560 |
| Global staff configuration | setWindowTitle | Staff and people | visualiser/dialogs.py:646 |
| These working patterns are shared by every task-generation category that requires staff. Timeframe tasks can be spread across the selected pattern's working window instead of all being released at the beginning of the day. | QLabel | Advanced demand | visualiser/dialogs.py:652 |
| Enable global staff working patterns | QCheckBox | Staff and people | visualiser/dialogs.py:661 |
| When disabled, generated staff tasks use one team with all-day availability. Custom weekly hours still apply. This does not disable required staff handling. | setToolTip | Advanced demand | visualiser/dialogs.py:662 |
| Evenly space staff-assisted timeframe tasks across working hours | QCheckBox | Advanced demand | visualiser/dialogs.py:669 |
| Spread timeframe releases across the overlap with global or custom staff hours. Turning this off releases tasks at the timeframe start; runtime staff still observe their working hours. Fixed scheduled times are unchanged. | setToolTip | Recovery and run outcomes | visualiser/dialogs.py:672 |
| Walking speed | addRow | Drawing tools and layers | visualiser/dialogs.py:724 |
| Lift wait allowance | addRow | Main chapters 5, 6, 10, 11 | visualiser/dialogs.py:725 |
| Default payload handling | addRow | Inventory and exchanges | visualiser/dialogs.py:726 |
| Hold AMR for short exchange | addRow | Inventory and exchanges | visualiser/dialogs.py:727 |
| Start | addRow | Drawing tools and layers | visualiser/dialogs.py:739 |
| Finish | addRow | Drawing tools and layers | visualiser/dialogs.py:740 |
| Working days | addRow | Drawing tools and layers | visualiser/dialogs.py:744 |
| Shift start | addRow | Staff and people | visualiser/dialogs.py:756 |
| Shift finish | addRow | Staff and people | visualiser/dialogs.py:757 |
| Two alternating teams are rostered. Team A and Team B swap every four days from the simulation start date. | QLabel | Drawing tools and layers | visualiser/dialogs.py:758 |
| Cycle | addRow | Drawing tools and layers | visualiser/dialogs.py:763 |
| No departments selected | QLabel | Drawing tools and layers | visualiser/dialogs.py:981 |
| Select departments... | QPushButton | Drawing tools and layers | visualiser/dialogs.py:983 |
| Use department locations as pickup/source | QCheckBox | Drawing tools and layers | visualiser/dialogs.py:992 |
| Use department locations as drop-off | QCheckBox | Drawing tools and layers | visualiser/dialogs.py:993 |
| Enabled | QCheckBox | Drawing tools and layers | visualiser/dialogs.py:1012 |
| None selected | QLabel | Drawing tools and layers | visualiser/dialogs.py:1027 |
| Select... | QPushButton | Drawing tools and layers | visualiser/dialogs.py:1030 |
| Clear | QPushButton | Drawing tools and layers | visualiser/dialogs.py:1033 |
| Select... | QPushButton | Drawing tools and layers | visualiser/dialogs.py:1044 |
| Clear | QPushButton | Drawing tools and layers | visualiser/dialogs.py:1047 |
| Generate tracked item exchange tasks | QCheckBox | Advanced demand | visualiser/dialogs.py:1058 |
| Generate return / exchange task | QCheckBox | Advanced demand | visualiser/dialogs.py:1084 |
| Release the next task after the preceding return clears the shared space | QCheckBox | Advanced demand | visualiser/dialogs.py:1098 |
| For lower-priority workflows sharing a drop-off zone, hold each later generated task until the preceding return has collected its payload from the zone inventory space. Categories without this option remain unaffected and can retain priority. | setToolTip | Advanced demand | visualiser/dialogs.py:1101 |
| Movement-only handoff (no destination dwell) | QCheckBox | Drawing tools and layers | visualiser/dialogs.py:1117 |
| Staff deliver the incoming payload and immediately transport the return payload back to the drop-off zone. | setToolTip | Staff and people | visualiser/dialogs.py:1120 |
| Allow temporary overflow | addItem | Drawing tools and layers | visualiser/dialogs.py:1131 |
| Wait for a compatible free space | addItem | Drawing tools and layers | visualiser/dialogs.py:1134 |
| Assign category staff for delivered payload handling | QCheckBox | Advanced demand | visualiser/dialogs.py:1147 |
| Use a separate staff pool for this category. Staff are reserved for delivered payload handling at the drop-off location. | setToolTip | Advanced demand | visualiser/dialogs.py:1148 |
| Use an untracked department team outside primary staff hours | QCheckBox | Staff and people | visualiser/dialogs.py:1161 |
| When the primary team cannot complete a drop-off-zone hand-off in its current working period, department staff move the payload between the zone and department. They are not added to the central staff pool. | setToolTip | Staff and people | visualiser/dialogs.py:1164 |
| Select how staff are grouped into shift teams for delivered payload handling. | setToolTip | Staff and people | visualiser/dialogs.py:1192 |
| Edit... | QPushButton | Drawing tools and layers | visualiser/dialogs.py:1210 |
| Reuse returned payloads as a capped source pool | QCheckBox | Inventory and exchanges | visualiser/dialogs.py:1215 |
| Use for simple non-item-tracked flows such as catering trolleys. Returned payloads replenish the pickup/source pool instead of accumulating as unlimited new physical stock. | setToolTip | Inventory and exchanges | visualiser/dialogs.py:1218 |
| Optional hard cap for the source pool. Use 0 for automatic: selected departments × multiplier. | setToolTip | Drawing tools and layers | visualiser/dialogs.py:1232 |
| Run every fortnight | QCheckBox | Recovery and run outcomes | visualiser/dialogs.py:1252 |
| When enabled, generated tasks run in week 1, skip week 2, then repeat every other week from the simulation start date. | setToolTip | Recovery and run outcomes | visualiser/dialogs.py:1253 |
| Edit times... | QPushButton | Drawing tools and layers | visualiser/dialogs.py:1265 |
| Clear | QPushButton | Drawing tools and layers | visualiser/dialogs.py:1267 |
| Starting people on shift for this category. This is a staffing estimate, not a fixed capacity: the simulation adds people when everyone is busy. | setToolTip | Advanced demand | visualiser/dialogs.py:1310 |
| Enabled | addRow | Drawing tools and layers | visualiser/dialogs.py:1324 |
| Generation mode | addRow | Advanced demand | visualiser/dialogs.py:1325 |
| Priority | addRow | Drawing tools and layers | visualiser/dialogs.py:1326 |
| Pickup / source locations | addRow | Drawing tools and layers | visualiser/dialogs.py:1327 |
| Drop-off destinations | addRow | Drawing tools and layers | visualiser/dialogs.py:1328 |
| Payload | addRow | Inventory and exchanges | visualiser/dialogs.py:1329 |
| Tracked item exchange | addRow | Inventory and exchanges | visualiser/dialogs.py:1330 |
| Exchange mode | addRow | Inventory and exchanges | visualiser/dialogs.py:1331 |
| Route profile | addRow | Batching and route restrictions | visualiser/dialogs.py:1332 |
| Return task | addRow | Advanced demand | visualiser/dialogs.py:1333 |
| Return payload | addRow | Inventory and exchanges | visualiser/dialogs.py:1334 |
| Return delay (minutes) | addRow | Drawing tools and layers | visualiser/dialogs.py:1335 |
| Shared-zone release spacing | addRow | Drawing tools and layers | visualiser/dialogs.py:1336 |
| Staff handling | addRow | Staff and people | visualiser/dialogs.py:1340 |
| Collection response delay (minutes) | addRow | Drawing tools and layers | visualiser/dialogs.py:1341 |
| Handling time (minutes) | addRow | Drawing tools and layers | visualiser/dialogs.py:1342 |
| Handoff timing | addRow | Drawing tools and layers | visualiser/dialogs.py:1343 |
| Initial staff count | addRow | Staff and people | visualiser/dialogs.py:1344 |
| Staff resource name | addRow | Staff and people | visualiser/dialogs.py:1345 |
| Out-of-hours fallback | addRow | Drawing tools and layers | visualiser/dialogs.py:1346 |
| Fallback resource name | addRow | Drawing tools and layers | visualiser/dialogs.py:1347 |
| Staff movement | addRow | Staff and people | visualiser/dialogs.py:1351 |
| Shift pattern | addRow | Staff and people | visualiser/dialogs.py:1352 |
| Working hours by day | addRow | Drawing tools and layers | visualiser/dialogs.py:1353 |
| Reusable return pool | addRow | Drawing tools and layers | visualiser/dialogs.py:1354 |
| Pool multiplier | addRow | Drawing tools and layers | visualiser/dialogs.py:1355 |
| Pool hard cap (0 = auto) | addRow | Drawing tools and layers | visualiser/dialogs.py:1356 |
| Days active | addRow | Drawing tools and layers | visualiser/dialogs.py:1357 |
| Fortnightly recurrence | addRow | Advanced demand | visualiser/dialogs.py:1358 |
| Scheduled times | addRow | Staff and people | visualiser/dialogs.py:1359 |
| Frequency per day | addRow | Drawing tools and layers | visualiser/dialogs.py:1360 |
| Volume per event m³ | addRow | Drawing tools and layers | visualiser/dialogs.py:1361 |
| Threshold volume m³ | addRow | Drawing tools and layers | visualiser/dialogs.py:1362 |
| Base daily volume m³ | addRow | Drawing tools and layers | visualiser/dialogs.py:1363 |
| Timeframe start HH:MM | addRow | Drawing tools and layers | visualiser/dialogs.py:1364 |
| Timeframe end HH:MM | addRow | Drawing tools and layers | visualiser/dialogs.py:1365 |
| Payload multiple | addRow | Inventory and exchanges | visualiser/dialogs.py:1366 |
| Notes | addRow | Drawing tools and layers | visualiser/dialogs.py:1367 |
| For Waste, stream-specific generation settings are applied from Departments → Manage waste streams. This dialog only applies collection routing, destination, priority and return-task settings to the selected departments. | QLabel | Advanced demand | visualiser/dialogs.py:1369 |
| Task generation parameters | setWindowTitle | Advanced demand | visualiser/dialogs.py:2076 |
| Enable automatic task generation | QCheckBox | Advanced demand | visualiser/dialogs.py:2094 |
| Global staff configuration... | QPushButton | Staff and people | visualiser/dialogs.py:2101 |
| Add | QPushButton | Drawing tools and layers | visualiser/dialogs.py:2127 |
| Delete | QPushButton | Drawing tools and layers | visualiser/dialogs.py:2128 |
| Department or configured group scope | setAccessibleName | Advanced demand | visualiser/dialogs.py:2157 |
| Select a department to configure department-specific task generation | QLabel | Advanced demand | visualiser/dialogs.py:2161 |
| Enabled | QCheckBox | Drawing tools and layers | visualiser/dialogs.py:2187 |
| Use department locations as pickup/source | QCheckBox | Drawing tools and layers | visualiser/dialogs.py:2193 |
| Use department locations as drop-off | QCheckBox | Drawing tools and layers | visualiser/dialogs.py:2194 |
| None selected | QLabel | Drawing tools and layers | visualiser/dialogs.py:2210 |
| Select... | QPushButton | Drawing tools and layers | visualiser/dialogs.py:2214 |
| Clear | QPushButton | Drawing tools and layers | visualiser/dialogs.py:2217 |
| Generate tracked item exchange tasks | QCheckBox | Advanced demand | visualiser/dialogs.py:2227 |
| Generate return / exchange task | QCheckBox | Advanced demand | visualiser/dialogs.py:2244 |
| Release the next task after the preceding return clears the shared space | QCheckBox | Advanced demand | visualiser/dialogs.py:2249 |
| Use for lower-priority categories that share a drop-off zone. The next generated task waits until the preceding return collects its payload from the zone inventory space. Unchecked priority categories continue to release normally. | setToolTip | Recovery and run outcomes | visualiser/dialogs.py:2252 |
| Movement-only handoff (no destination dwell) | QCheckBox | Drawing tools and layers | visualiser/dialogs.py:2259 |
| Staff deliver the incoming payload and immediately transport the return payload back to the drop-off zone. | setToolTip | Staff and people | visualiser/dialogs.py:2262 |
| Allow temporary overflow | addItem | Drawing tools and layers | visualiser/dialogs.py:2268 |
| Wait for a compatible free space | addItem | Drawing tools and layers | visualiser/dialogs.py:2271 |
| Temporary overflow keeps staff-assisted drop-off-zone tasks moving when all compatible bays are occupied. Excess occupancy remains visible in the drop-off-zone utilisation report. | setToolTip | Report options | visualiser/dialogs.py:2274 |
| Assign category staff for delivered payload handling | QCheckBox | Advanced demand | visualiser/dialogs.py:2279 |
| Use a separate staff pool for this category. Staff are reserved for delivered payload handling at the drop-off location. | setToolTip | Advanced demand | visualiser/dialogs.py:2280 |
| Use an untracked department team outside primary staff hours | QCheckBox | Staff and people | visualiser/dialogs.py:2286 |
| When the primary team cannot complete a drop-off-zone hand-off in its current working period, department staff move the payload between the zone and department. They are not added to the central staff pool. | setToolTip | Staff and people | visualiser/dialogs.py:2289 |
| Select how staff are grouped into shift teams for delivered payload handling. | setToolTip | Staff and people | visualiser/dialogs.py:2304 |
| Edit... | QPushButton | Drawing tools and layers | visualiser/dialogs.py:2314 |
| Reuse returned payloads as a capped source pool | QCheckBox | Inventory and exchanges | visualiser/dialogs.py:2319 |
| Use for simple non-item-tracked flows such as catering trolleys. Returned payloads replenish the pickup/source pool instead of accumulating as unlimited new physical stock. | setToolTip | Inventory and exchanges | visualiser/dialogs.py:2322 |
| Optional hard cap for the source pool. Use 0 for automatic: selected departments × multiplier. | setToolTip | Drawing tools and layers | visualiser/dialogs.py:2329 |
| Run every fortnight | QCheckBox | Recovery and run outcomes | visualiser/dialogs.py:2344 |
| When enabled, generated tasks run in week 1, skip week 2, then repeat every other week from the simulation start date. | setToolTip | Recovery and run outcomes | visualiser/dialogs.py:2345 |
| No times selected | QLabel | Drawing tools and layers | visualiser/dialogs.py:2354 |
| Edit times... | QPushButton | Drawing tools and layers | visualiser/dialogs.py:2357 |
| Clear | QPushButton | Drawing tools and layers | visualiser/dialogs.py:2360 |
| Starting people on shift for this category. This is a staffing estimate, not a fixed capacity: the simulation adds people when everyone is busy. | setToolTip | Advanced demand | visualiser/dialogs.py:2394 |
| Category enabled | addRow | Advanced demand | visualiser/dialogs.py:2408 |
| Display name | addRow | Drawing tools and layers | visualiser/dialogs.py:2409 |
| Generation mode | addRow | Advanced demand | visualiser/dialogs.py:2410 |
| Priority | addRow | Drawing tools and layers | visualiser/dialogs.py:2411 |
| Department location role | addRow | Drawing tools and layers | visualiser/dialogs.py:2412 |
| Pickup / source location | addRow | Drawing tools and layers | visualiser/dialogs.py:2413 |
| Drop-off destinations | addRow | Drawing tools and layers | visualiser/dialogs.py:2414 |
| Payload | addRow | Inventory and exchanges | visualiser/dialogs.py:2415 |
| Tracked item exchange | addRow | Inventory and exchanges | visualiser/dialogs.py:2416 |
| Exchange mode | addRow | Inventory and exchanges | visualiser/dialogs.py:2417 |
| Route profile | addRow | Batching and route restrictions | visualiser/dialogs.py:2418 |
| Return task | addRow | Advanced demand | visualiser/dialogs.py:2419 |
| Return payload | addRow | Inventory and exchanges | visualiser/dialogs.py:2420 |
| Return delay (minutes) | addRow | Drawing tools and layers | visualiser/dialogs.py:2421 |
| Shared-zone release spacing | addRow | Drawing tools and layers | visualiser/dialogs.py:2422 |
| Staff handling | addRow | Staff and people | visualiser/dialogs.py:2426 |
| Collection response delay (minutes) | addRow | Drawing tools and layers | visualiser/dialogs.py:2427 |
| Handling time (minutes) | addRow | Drawing tools and layers | visualiser/dialogs.py:2428 |
| Handoff timing | addRow | Drawing tools and layers | visualiser/dialogs.py:2429 |
| Category-wide drop-off-zone capacity | addRow | Advanced demand | visualiser/dialogs.py:2430 |
| Initial staff count | addRow | Staff and people | visualiser/dialogs.py:2434 |
| Staff resource name | addRow | Staff and people | visualiser/dialogs.py:2435 |
| Out-of-hours fallback | addRow | Drawing tools and layers | visualiser/dialogs.py:2436 |
| Fallback resource name | addRow | Drawing tools and layers | visualiser/dialogs.py:2437 |
| Staff movement | addRow | Staff and people | visualiser/dialogs.py:2441 |
| Shift pattern | addRow | Staff and people | visualiser/dialogs.py:2442 |
| Working hours by day | addRow | Drawing tools and layers | visualiser/dialogs.py:2443 |
| Reusable return pool | addRow | Drawing tools and layers | visualiser/dialogs.py:2444 |
| Pool multiplier | addRow | Drawing tools and layers | visualiser/dialogs.py:2445 |
| Pool hard cap (0 = auto) | addRow | Drawing tools and layers | visualiser/dialogs.py:2446 |
| Days active | addRow | Drawing tools and layers | visualiser/dialogs.py:2447 |
| Fortnightly recurrence | addRow | Advanced demand | visualiser/dialogs.py:2448 |
| Scheduled times | addRow | Staff and people | visualiser/dialogs.py:2450 |
| Frequency per day | addRow | Drawing tools and layers | visualiser/dialogs.py:2452 |
| Volume per event m³ | addRow | Drawing tools and layers | visualiser/dialogs.py:2453 |
| Threshold volume m³ | addRow | Drawing tools and layers | visualiser/dialogs.py:2454 |
| Base daily volume m³ | addRow | Drawing tools and layers | visualiser/dialogs.py:2455 |
| Timeframe start HH:MM | addRow | Drawing tools and layers | visualiser/dialogs.py:2456 |
| Timeframe end HH:MM | addRow | Drawing tools and layers | visualiser/dialogs.py:2457 |
| Payload multiple | addRow | Inventory and exchanges | visualiser/dialogs.py:2458 |
| Notes | addRow | Drawing tools and layers | visualiser/dialogs.py:2459 |
| Waste task generation uses the waste streams assigned in the Departments dialog. Edit generation mode, frequency, volume per event, threshold and scheduled times via Departments → Manage waste streams. The Waste category here only controls enablement, priority, pickup/drop-off role, destinations, route profile and return task settings. | QLabel | Advanced demand | visualiser/dialogs.py:2461 |
| Schedule times are comma-separated HH:MM values. Timeframe mode releases non-staff tasks at the start of the active-day window. Staff-assisted timeframe tasks are evenly spaced across the applicable category/department working hours (or the global shift pattern when no override is selected) and remain due before the effective timeframe end. Drop-off destinations can contain multiple locations; the first is also saved as dropoff_location for compatibility with existing generators. Configure multiple can be used more than once for the same category and department; each configured group creates an additional run in the simulator. For Waste, stream-specific generated volume is configured on the departments' waste streams, not on the task-generation category override. | QLabel | Recovery and run outcomes | visualiser/dialogs.py:2470 |
| Name | addRow | Drawing tools and layers | visualiser/dialogs.py:4598 |
| X coordinate | addRow | Drawing tools and layers | visualiser/dialogs.py:4599 |
| Y coordinate | addRow | Drawing tools and layers | visualiser/dialogs.py:4600 |
| Floor | addRow | Main chapters 1, 2, 3 | visualiser/dialogs.py:4601 |
| Point type | addRow | Drawing tools and layers | visualiser/dialogs.py:4602 |
| Delete selected | QPushButton | Drawing tools and layers | visualiser/dialogs.py:4776 |
| Close | QPushButton | Drawing tools and layers | visualiser/dialogs.py:4777 |
| Lift and floors | addTab | Main chapters 5, 6, 10, 11 | visualiser/dialogs.py:4872 |
| Comma-separated floor numbers. Existing floor coordinates are retained; new floors use the clicked position. | setToolTip | Main chapters 1, 2, 3 | visualiser/dialogs.py:4881 |
| Lift name | addRow | Main chapters 5, 6, 10, 11 | visualiser/dialogs.py:4889 |
| Floors served | addRow | Main chapters 1, 2, 3 | visualiser/dialogs.py:4890 |
| Starting floor | addRow | Main chapters 1, 2, 3 | visualiser/dialogs.py:4891 |
| Vertical travel speed | addRow | Drawing tools and layers | visualiser/dialogs.py:4911 |
| Door operation time | addRow | Main chapters 1, 2, 3 | visualiser/dialogs.py:4912 |
| AMR boarding / exit time | addRow | Drawing tools and layers | visualiser/dialogs.py:4913 |
| Automatically generated from the floors served. Existing positions are retained. | setToolTip | Main chapters 1, 2, 3 | visualiser/dialogs.py:4921 |
| Car and energy | addTab | Drawing tools and layers | visualiser/dialogs.py:4934 |
| Clear car length | addRow | Drawing tools and layers | visualiser/dialogs.py:4953 |
| Clear car width | addRow | Drawing tools and layers | visualiser/dialogs.py:4954 |
| Clear car height | addRow | Drawing tools and layers | visualiser/dialogs.py:4955 |
| Lift car mass | addRow | Main chapters 5, 6, 10, 11 | visualiser/dialogs.py:4987 |
| Counterweight ratio | addRow | Drawing tools and layers | visualiser/dialogs.py:4988 |
| Travel efficiency | addRow | Drawing tools and layers | visualiser/dialogs.py:4989 |
| Door-system power | addRow | Main chapters 1, 2, 3 | visualiser/dialogs.py:4990 |
| Stationary power | addRow | Drawing tools and layers | visualiser/dialogs.py:4991 |
| Regenerative efficiency | addRow | Drawing tools and layers | visualiser/dialogs.py:4992 |
| Health and reliability | addTab | Drawing tools and layers | visualiser/dialogs.py:4997 |
| Initial health | addRow | Drawing tools and layers | visualiser/dialogs.py:5020 |
| Health lost per journey | addRow | Drawing tools and layers | visualiser/dialogs.py:5021 |
| Unavailable below | addRow | Drawing tools and layers | visualiser/dialogs.py:5022 |
| Speed factor at 0% health | addRow | Drawing tools and layers | visualiser/dialogs.py:5023 |
| Mean time between failures | addRow | Drawing tools and layers | visualiser/dialogs.py:5037 |
| Mean repair duration | addRow | Drawing tools and layers | visualiser/dialogs.py:5038 |
| Lifts | setWindowTitle | Main chapters 5, 6, 10, 11 | visualiser/dialogs.py:5192 |
| Close | QPushButton | Drawing tools and layers | visualiser/dialogs.py:5226 |
| Payload slot | setWindowTitle | Inventory and exchanges | visualiser/dialogs.py:5412 |
| Lengthways | QCheckBox | Drawing tools and layers | visualiser/dialogs.py:5451 |
| Sideways | QCheckBox | Drawing tools and layers | visualiser/dialogs.py:5452 |
| Slot name | addRow | Drawing tools and layers | visualiser/dialogs.py:5458 |
| Maximum payload weight | addRow | Inventory and exchanges | visualiser/dialogs.py:5459 |
| Clear carrying length | addRow | Drawing tools and layers | visualiser/dialogs.py:5460 |
| Clear carrying width | addRow | Drawing tools and layers | visualiser/dialogs.py:5461 |
| Clear carrying height | addRow | Drawing tools and layers | visualiser/dialogs.py:5462 |
| Supported orientations | addRow | Drawing tools and layers | visualiser/dialogs.py:5463 |
| AMR details | addTab | Drawing tools and layers | visualiser/dialogs.py:5529 |
| AMR type name | addRow | Drawing tools and layers | visualiser/dialogs.py:5539 |
| Fleet quantity | addRow | Drawing tools and layers | visualiser/dialogs.py:5540 |
| Overall length | addRow | Drawing tools and layers | visualiser/dialogs.py:5566 |
| Overall width | addRow | Drawing tools and layers | visualiser/dialogs.py:5567 |
| Overall height | addRow | Drawing tools and layers | visualiser/dialogs.py:5568 |
| Unloaded weight | addRow | Drawing tools and layers | visualiser/dialogs.py:5575 |
| Normal travel speed | addRow | Drawing tools and layers | visualiser/dialogs.py:5576 |
| Travel motor power | addRow | Drawing tools and layers | visualiser/dialogs.py:5577 |
| Detailed capabilities | addTab | Detailed and historical settings | visualiser/dialogs.py:5586 |
| Battery and charging | addTab | Inventory and exchanges | visualiser/dialogs.py:5589 |
| Usable battery capacity | addRow | Drawing tools and layers | visualiser/dialogs.py:5613 |
| Charging power | addRow | Inventory and exchanges | visualiser/dialogs.py:5614 |
| Request charging at | addRow | Inventory and exchanges | visualiser/dialogs.py:5615 |
| Initial state of charge | addRow | Inventory and exchanges | visualiser/dialogs.py:5616 |
| Indicative full-charge time | addRow | Inventory and exchanges | visualiser/dialogs.py:5617 |
| Payload slots | addTab | Inventory and exchanges | visualiser/dialogs.py:5631 |
| Allow tasks to be batched into one multi-stop route when several slots are available | QCheckBox | Advanced demand | visualiser/dialogs.py:5658 |
| Tracked item | setWindowTitle | Drawing tools and layers | visualiser/dialogs.py:5856 |
| Item name | addRow | Drawing tools and layers | visualiser/dialogs.py:5896 |
| Maximum stock | addRow | Inventory and exchanges | visualiser/dialogs.py:5897 |
| Top-up threshold | addRow | Drawing tools and layers | visualiser/dialogs.py:5898 |
| Demand pattern | addRow | Advanced demand | visualiser/dialogs.py:5899 |
| Average daily consumption | addRow | Drawing tools and layers | visualiser/dialogs.py:5900 |
| No exchange payload | addItem | Inventory and exchanges | visualiser/dialogs.py:5906 |
| No source selected | QLabel | Drawing tools and layers | visualiser/dialogs.py:5916 |
| Choose source… | QPushButton | Drawing tools and layers | visualiser/dialogs.py:5918 |
| Clear | QPushButton | Drawing tools and layers | visualiser/dialogs.py:5920 |
| Exchange payload | addRow | Inventory and exchanges | visualiser/dialogs.py:5925 |
| Source location | addRow | Drawing tools and layers | visualiser/dialogs.py:5926 |
| Payload details | addTab | Inventory and exchanges | visualiser/dialogs.py:6011 |
| Payload name | addRow | Inventory and exchanges | visualiser/dialogs.py:6034 |
| Loaded weight | addRow | Drawing tools and layers | visualiser/dialogs.py:6035 |
| Overall length | addRow | Drawing tools and layers | visualiser/dialogs.py:6036 |
| Overall width | addRow | Drawing tools and layers | visualiser/dialogs.py:6037 |
| Overall height | addRow | Drawing tools and layers | visualiser/dialogs.py:6038 |
| Lengthways | QCheckBox | Drawing tools and layers | visualiser/dialogs.py:6055 |
| Sideways | QCheckBox | Drawing tools and layers | visualiser/dialogs.py:6056 |
| Prefer an AMR with several payload slots when one is available | QCheckBox | Inventory and exchanges | visualiser/dialogs.py:6062 |
| Permitted carrying orientation | addRow | Drawing tools and layers | visualiser/dialogs.py:6068 |
| Multi-stop preference | addRow | Drawing tools and layers | visualiser/dialogs.py:6069 |
| Tracked contents | addTab | Drawing tools and layers | visualiser/dialogs.py:6080 |
| Track stock or consumable items held inside this payload | QCheckBox | Inventory and exchanges | visualiser/dialogs.py:6082 |
| Enable this for payloads whose contents deplete and trigger replenishment tasks. | setToolTip | Advanced demand | visualiser/dialogs.py:6086 |
| Add tracked item | QPushButton | Drawing tools and layers | visualiser/dialogs.py:6113 |
| Edit selected | QPushButton | Drawing tools and layers | visualiser/dialogs.py:6114 |
| Delete selected | QPushButton | Drawing tools and layers | visualiser/dialogs.py:6115 |
| Payloads | setWindowTitle | Inventory and exchanges | visualiser/dialogs.py:6302 |
| Add | QPushButton | Drawing tools and layers | visualiser/dialogs.py:6328 |
| Edit | QPushButton | Drawing tools and layers | visualiser/dialogs.py:6329 |
| Delete | QPushButton | Drawing tools and layers | visualiser/dialogs.py:6330 |
| Save | QPushButton | Recovery and run outcomes | visualiser/dialogs.py:6331 |
| AMRs | setWindowTitle | Drawing tools and layers | visualiser/dialogs.py:6465 |
| Add | QPushButton | Drawing tools and layers | visualiser/dialogs.py:6491 |
| Edit | QPushButton | Drawing tools and layers | visualiser/dialogs.py:6492 |
| Delete | QPushButton | Drawing tools and layers | visualiser/dialogs.py:6493 |
| Save | QPushButton | Recovery and run outcomes | visualiser/dialogs.py:6494 |
| Add | QPushButton | Drawing tools and layers | visualiser/dialogs.py:6601 |
| Edit | QPushButton | Drawing tools and layers | visualiser/dialogs.py:6602 |
| Delete | QPushButton | Drawing tools and layers | visualiser/dialogs.py:6603 |
| Save | QPushButton | Recovery and run outcomes | visualiser/dialogs.py:6604 |
| People movement profile | setWindowTitle | Staff and people | visualiser/dialogs.py:6735 |
| Profile and timeframe | addTab | Batching and route restrictions | visualiser/dialogs.py:6786 |
| A unique name used when assigning this profile to corridor assets. | setToolTip | Batching and route restrictions | visualiser/dialogs.py:6793 |
| Use this profile in simulations | QCheckBox | Batching and route restrictions | visualiser/dialogs.py:6794 |
| Staff only | addItem | Staff and people | visualiser/dialogs.py:6797 |
| Public only | addItem | Drawing tools and layers | visualiser/dialogs.py:6798 |
| Mixed staff and public | addItem | Staff and people | visualiser/dialogs.py:6799 |
| Profile name | addRow | Batching and route restrictions | visualiser/dialogs.py:6804 |
| People using the route | addRow | Staff and people | visualiser/dialogs.py:6805 |
| Status | addRow | Drawing tools and layers | visualiser/dialogs.py:6806 |
| Preset | addRow | Drawing tools and layers | visualiser/dialogs.py:6829 |
| Timeframe description | addRow | Drawing tools and layers | visualiser/dialogs.py:6830 |
| Starts | addRow | Drawing tools and layers | visualiser/dialogs.py:6831 |
| Ends | addRow | Drawing tools and layers | visualiser/dialogs.py:6832 |
| Active days | addRow | Drawing tools and layers | visualiser/dialogs.py:6833 |
| Route or corridor assets | addTab | Batching and route restrictions | visualiser/dialogs.py:6845 |
| Route people between two locations | addItem | Staff and people | visualiser/dialogs.py:6851 |
| Apply the profile directly to selected corridors | addItem | Batching and route restrictions | visualiser/dialogs.py:6852 |
| Select a start location… | addItem | Drawing tools and layers | visualiser/dialogs.py:6856 |
| Select an end location… | addItem | Drawing tools and layers | visualiser/dialogs.py:6860 |
| Select corridor assets… | QPushButton | Main chapters 1, 2, 3 | visualiser/dialogs.py:6874 |
| Clear selection | QPushButton | Drawing tools and layers | visualiser/dialogs.py:6876 |
| Application method | addRow | Drawing tools and layers | visualiser/dialogs.py:6884 |
| Start location | addRow | Drawing tools and layers | visualiser/dialogs.py:6885 |
| End location | addRow | Drawing tools and layers | visualiser/dialogs.py:6886 |
| Corridor assets | addRow | Main chapters 1, 2, 3 | visualiser/dialogs.py:6887 |
| Flow profile | addTab | Batching and route restrictions | visualiser/dialogs.py:6900 |
| People represented at the quietest point of the profile. | setToolTip | Staff and people | visualiser/dialogs.py:6915 |
| Maximum people represented by one movement interval. | setToolTip | Staff and people | visualiser/dialogs.py:6921 |
| How often a group enters the route during the active timeframe. | setToolTip | Batching and route restrictions | visualiser/dialogs.py:6928 |
| Fit the ramp automatically to the full daily timeframe | QCheckBox | Drawing tools and layers | visualiser/dialogs.py:6940 |
| Ramp up reaches the peak at the end of the timeframe; ramp down starts at the peak and reaches the quiet value at the end; ramp up/down reaches the peak at the midpoint. | setToolTip | Drawing tools and layers | visualiser/dialogs.py:6958 |
| Profile shape | addRow | Batching and route restrictions | visualiser/dialogs.py:6963 |
| Quiet-period people per interval | addRow | Staff and people | visualiser/dialogs.py:6964 |
| Peak people per interval | addRow | Staff and people | visualiser/dialogs.py:6965 |
| Movement interval | addRow | Drawing tools and layers | visualiser/dialogs.py:6966 |
| Timeframe alignment | addRow | Drawing tools and layers | visualiser/dialogs.py:6967 |
| Manual ramp-up duration | addRow | Drawing tools and layers | visualiser/dialogs.py:6968 |
| Manual ramp-down duration | addRow | Drawing tools and layers | visualiser/dialogs.py:6969 |
| AMR interaction | addTab | Drawing tools and layers | visualiser/dialogs.py:7002 |
| Average walking speed used to reserve each corridor segment. | setToolTip | Main chapters 1, 2, 3 | visualiser/dialogs.py:7011 |
| Maximum AMR speed while this people profile overlaps the route. Additional crowding slowdown is applied from the people count. | setToolTip | Staff and people | visualiser/dialogs.py:7018 |
| Average walking speed | addRow | Drawing tools and layers | visualiser/dialogs.py:7022 |
| AMR speed while sharing the route | addRow | Batching and route restrictions | visualiser/dialogs.py:7023 |
| People movement profiles | setWindowTitle | Staff and people | visualiser/dialogs.py:7212 |
| Scenario event | setWindowTitle | Drawing tools and layers | visualiser/dialogs.py:7440 |
| Assets and effect | addTab | Drawing tools and layers | visualiser/dialogs.py:7460 |
| Select assets… | QPushButton | Drawing tools and layers | visualiser/dialogs.py:7481 |
| Clear | QPushButton | Drawing tools and layers | visualiser/dialogs.py:7483 |
| Asset type | addRow | Drawing tools and layers | visualiser/dialogs.py:7490 |
| Selected assets | addRow | Drawing tools and layers | visualiser/dialogs.py:7491 |
| 0% makes the selected assets unavailable. Values between 0% and 100% reduce effective capacity. | setToolTip | Drawing tools and layers | visualiser/dialogs.py:7506 |
| 100% is normal speed. 50% doubles travel or lift movement time while the event is active. | setToolTip | Main chapters 5, 6, 10, 11 | visualiser/dialogs.py:7516 |
| Common event | addRow | Drawing tools and layers | visualiser/dialogs.py:7521 |
| Availability | addRow | Drawing tools and layers | visualiser/dialogs.py:7522 |
| Operating speed | addRow | Drawing tools and layers | visualiser/dialogs.py:7523 |
| Result | addRow | Drawing tools and layers | visualiser/dialogs.py:7524 |
| Schedule and notes | addTab | Staff and people | visualiser/dialogs.py:7529 |
| Starts | addRow | Drawing tools and layers | visualiser/dialogs.py:7544 |
| Ends | addRow | Drawing tools and layers | visualiser/dialogs.py:7545 |
| Active days | addRow | Drawing tools and layers | visualiser/dialogs.py:7546 |
| Scenario testing | setWindowTitle | Drawing tools and layers | visualiser/dialogs.py:7724 |
| Run the selected scenario | QCheckBox | Recovery and run outcomes | visualiser/dialogs.py:7765 |
| When cleared, the simulator uses normal operation even if a scenario is selected. | setToolTip | Drawing tools and layers | visualiser/dialogs.py:7767 |
| Include detailed payload-transition logging | QCheckBox | Detailed and historical settings | visualiser/dialogs.py:7770 |
| Scenario runs normally use compact CSV logging. Enable this only when checking payload state changes. | setToolTip | Recovery and run outcomes | visualiser/dialogs.py:7772 |
| New | QPushButton | Drawing tools and layers | visualiser/dialogs.py:7785 |
| Duplicate | QPushButton | Drawing tools and layers | visualiser/dialogs.py:7787 |
| Rename | QPushButton | Drawing tools and layers | visualiser/dialogs.py:7789 |
| Delete | QPushButton | Drawing tools and layers | visualiser/dialogs.py:7791 |
| Add event | QPushButton | Drawing tools and layers | visualiser/dialogs.py:7828 |
| Add current topology selection | QPushButton | Drawing tools and layers | visualiser/dialogs.py:7830 |
| Creates an event using the corridor edges or door nodes currently selected in the topology view. | setToolTip | Main chapters 1, 2, 3 | visualiser/dialogs.py:7836 |
| Edit | QPushButton | Drawing tools and layers | visualiser/dialogs.py:7839 |
| Delete | QPushButton | Drawing tools and layers | visualiser/dialogs.py:7841 |
| Normal operation | addItem | Drawing tools and layers | visualiser/dialogs.py:7868 |
| Corridors, doors and people use | setWindowTitle | Staff and people | visualiser/dialogs.py:8177 |
| Corridors | addTab | Main chapters 1, 2, 3 | visualiser/dialogs.py:8240 |
| Select corridor assets… | QPushButton | Main chapters 1, 2, 3 | visualiser/dialogs.py:8247 |
| Leave unchanged | addItem | Drawing tools and layers | visualiser/dialogs.py:8277 |
| Two-way / bidirectional | addItem | Drawing tools and layers | visualiser/dialogs.py:8278 |
| One-way | addItem | Drawing tools and layers | visualiser/dialogs.py:8279 |
| Nominal clear corridor width before door restrictions. | setToolTip | Batching and route restrictions | visualiser/dialogs.py:8285 |
| Leave unchanged | addItem | Drawing tools and layers | visualiser/dialogs.py:8287 |
| Leave unchanged | QLabel | Drawing tools and layers | visualiser/dialogs.py:8294 |
| Choose… | QPushButton | Drawing tools and layers | visualiser/dialogs.py:8296 |
| Clear profiles | QPushButton | Batching and route restrictions | visualiser/dialogs.py:8298 |
| Apply to selected corridors | QPushButton | Main chapters 1, 2, 3 | visualiser/dialogs.py:8304 |
| Door openings | addTab | Main chapters 1, 2, 3 | visualiser/dialogs.py:8328 |
| Select corridor nodes… | QPushButton | Main chapters 1, 2, 3 | visualiser/dialogs.py:8334 |
| Leave unchanged | addItem | Drawing tools and layers | visualiser/dialogs.py:8356 |
| This node is a door opening | addItem | Main chapters 1, 2, 3 | visualiser/dialogs.py:8357 |
| This node is not a door | addItem | Main chapters 1, 2, 3 | visualiser/dialogs.py:8358 |
| Measure the narrowest clear opening available to the AMR, not the nominal door-set size. | setToolTip | Main chapters 1, 2, 3 | visualiser/dialogs.py:8364 |
| Apply to selected nodes | QPushButton | Drawing tools and layers | visualiser/dialogs.py:8367 |
| Simulation settings | setWindowTitle | Drawing tools and layers | visualiser/dialogs.py:8650 |
| Run period | addTab | Recovery and run outcomes | visualiser/dialogs.py:8678 |
| Simple — graph-based simulation | addItem | Drawing tools and layers | visualiser/dialogs.py:8686 |
| Detailed — geometric traffic | addItem | Detailed and historical settings | visualiser/dialogs.py:8687 |
| Simple uses graph travel. Detailed requires explicit geometry, robot motion and traffic settings. Switching modes preserves dormant project data; review the changes below. | setToolTip | Detailed and historical settings | visualiser/dialogs.py:8700 |
| Simulation mode | addRow | Drawing tools and layers | visualiser/dialogs.py:8702 |
| Simulation mode changes and readiness findings | setAccessibleName | Drawing tools and layers | visualiser/dialogs.py:8708 |
| Show complete mode changes and readiness findings | setAccessibleName | Drawing tools and layers | visualiser/dialogs.py:8713 |
| End generated demand at a fixed date and time | QCheckBox | Advanced demand | visualiser/dialogs.py:8729 |
| Retained metadata for compatibility. The current event-driven simulator does not use this value to pace execution or change AMR travel speed. Playback has separate controls. | setToolTip | Relinking and evidence | visualiser/dialogs.py:8748 |
| Adds a small spacing between tasks generated for exactly the same instant. | setToolTip | Advanced demand | visualiser/dialogs.py:8759 |
| Starts | addRow | Drawing tools and layers | visualiser/dialogs.py:8764 |
| End condition | addRow | Drawing tools and layers | visualiser/dialogs.py:8765 |
| Ends | addRow | Drawing tools and layers | visualiser/dialogs.py:8766 |
| Legacy rate (metadata) | addRow | Drawing tools and layers | visualiser/dialogs.py:8767 |
| Same-time task release spacing | addRow | Advanced demand | visualiser/dialogs.py:8771 |
| Fail a service task if it has not been assigned to an AMR within this time of its scheduled release. Includes waiting for a preceding return pickup and waiting for assignment; release from deferral does not restart the timer. Assigned journeys continue. Zero leaves the wait unlimited. | setToolTip | Advanced demand | visualiser/dialogs.py:8778 |
| Maximum task deferral | addRow | Advanced demand | visualiser/dialogs.py:8784 |
| Performance | addTab | Drawing tools and layers | visualiser/dialogs.py:8796 |
| Prepare commonly used routes before the run | QCheckBox | Recovery and run outcomes | visualiser/dialogs.py:8800 |
| Reduces route-search pauses during the simulation at the cost of some startup work. | setToolTip | Batching and route restrictions | visualiser/dialogs.py:8802 |
| Route precomputation | addRow | Batching and route restrictions | visualiser/dialogs.py:8811 |
| Maximum route pairs | addRow | Batching and route restrictions | visualiser/dialogs.py:8812 |
| Tasks estimated in each ordered batch. If a whole batch has no feasible assignment, later batches are checked; this does not limit the total pending queue. | setToolTip | Recovery and run outcomes | visualiser/dialogs.py:8827 |
| Multi-stop tasks considered together | addRow | Advanced demand | visualiser/dialogs.py:8844 |
| Single tasks considered together | addRow | Advanced demand | visualiser/dialogs.py:8845 |
| Assignments processed per cycle | addRow | Drawing tools and layers | visualiser/dialogs.py:8846 |
| Simulated delay before next assignment cycle | addRow | Recovery and run outcomes | visualiser/dialogs.py:8847 |
| Charging | addTab | Inventory and exchanges | visualiser/dialogs.py:8858 |
| Recharge an AMR when it has remained inactive | QCheckBox | Inventory and exchanges | visualiser/dialogs.py:8862 |
| Uses otherwise idle time to recharge AMRs that are below full charge. Released work takes priority over starting a new opportunity charge. | setToolTip | Inventory and exchanges | visualiser/dialogs.py:8868 |
| An AMR must have no work for this long before it becomes eligible. One eligible AMR is admitted per scheduler check to avoid synchronized fleet charging. | setToolTip | Recovery and run outcomes | visualiser/dialogs.py:8889 |
| Charging policy | addRow | Inventory and exchanges | visualiser/dialogs.py:8899 |
| Inactive before charging | addRow | Inventory and exchanges | visualiser/dialogs.py:8902 |
| Initial conditions | addTab | Drawing tools and layers | visualiser/dialogs.py:8917 |
| Place waste containers at department pickup locations when the simulation starts | QCheckBox | Drawing tools and layers | visualiser/dialogs.py:8921 |
| Use this when departments are assumed to begin the model with an empty physical waste container available. | setToolTip | Drawing tools and layers | visualiser/dialogs.py:8927 |
| Ignore finite inventory-space capacity during the simulation | QCheckBox | Inventory and exchanges | visualiser/dialogs.py:8930 |
| Location boundaries and spaces remain saved and available to reports, but slot occupancy does not block tasks. | setToolTip | Report options | visualiser/dialogs.py:8941 |
| Ignore invalid local manoeuvres (unverified direct movement) | QCheckBox | Drawing tools and layers | visualiser/dialogs.py:8947 |
| If a local inventory-bay path fails, use direct movement and mark its event details as unverified. Travel time and distance are retained. Corridor, door and traffic restrictions still apply. | setToolTip | Inventory and exchanges | visualiser/dialogs.py:8950 |
| Spawn payloads when pickup stock is exhausted | QCheckBox | Inventory and exchanges | visualiser/dialogs.py:8954 |
| Supply a new payload at pickup when no eligible unreserved stock remains. Additions are recorded in payload population evidence. Exact container IDs, staged recovery and reserved empty-bin exchanges still require their physical stock. | setToolTip | Relinking and evidence | visualiser/dialogs.py:8957 |
| Waste Stream | setWindowTitle | Drawing tools and layers | visualiser/dialogs.py:9092 |
| Waste stream name | addRow | Drawing tools and layers | visualiser/dialogs.py:9124 |
| Container payload | addRow | Inventory and exchanges | visualiser/dialogs.py:9125 |
| Container capacity | addRow | Drawing tools and layers | visualiser/dialogs.py:9126 |
| Full threshold | addRow | Drawing tools and layers | visualiser/dialogs.py:9127 |
| Waste Streams | setWindowTitle | Drawing tools and layers | visualiser/dialogs.py:9162 |
| Add | QPushButton | Drawing tools and layers | visualiser/dialogs.py:9192 |
| Edit | QPushButton | Drawing tools and layers | visualiser/dialogs.py:9193 |
| Delete | QPushButton | Drawing tools and layers | visualiser/dialogs.py:9194 |
| Save | QPushButton | Recovery and run outcomes | visualiser/dialogs.py:9195 |
| Mass collection / bin rotation | setWindowTitle | Drawing tools and layers | visualiser/dialogs.py:9288 |
| Enabled | QCheckBox | Drawing tools and layers | visualiser/dialogs.py:9301 |
| Select... | QPushButton | Drawing tools and layers | visualiser/dialogs.py:9311 |
| Clear | QPushButton | Drawing tools and layers | visualiser/dialogs.py:9313 |
| Edit times... | QPushButton | Drawing tools and layers | visualiser/dialogs.py:9325 |
| Clear | QPushButton | Drawing tools and layers | visualiser/dialogs.py:9326 |
| Replace collected used/full bins with empty equivalents | QCheckBox | Drawing tools and layers | visualiser/dialogs.py:9358 |
| ID | addRow | Drawing tools and layers | visualiser/dialogs.py:9383 |
| Enabled | addRow | Drawing tools and layers | visualiser/dialogs.py:9384 |
| Bin store location | addRow | Drawing tools and layers | visualiser/dialogs.py:9385 |
| Payload types | addRow | Inventory and exchanges | visualiser/dialogs.py:9386 |
| Days active | addRow | Drawing tools and layers | visualiser/dialogs.py:9387 |
| Scheduled collection times | addRow | Staff and people | visualiser/dialogs.py:9388 |
| Capacity trigger | addRow | Drawing tools and layers | visualiser/dialogs.py:9389 |
| Full-bin trigger | addRow | Drawing tools and layers | visualiser/dialogs.py:9390 |
| Capacity check interval | addRow | Recovery and run outcomes | visualiser/dialogs.py:9391 |
| Exchange | addRow | Inventory and exchanges | visualiser/dialogs.py:9392 |
| Notes | addRow | Drawing tools and layers | visualiser/dialogs.py:9393 |
| At each visit the simulator removes all used/full matching payload instances from the store and creates the same number of empty replacement instances. Capacity triggers use the number of configured inventory spaces at the selected location, unless a trigger count is entered. | QLabel | Inventory and exchanges | visualiser/dialogs.py:9395 |
| Mass collections / bin rotations | setWindowTitle | Drawing tools and layers | visualiser/dialogs.py:9495 |
| Add | QPushButton | Drawing tools and layers | visualiser/dialogs.py:9523 |
| Edit | QPushButton | Drawing tools and layers | visualiser/dialogs.py:9524 |
| Delete | QPushButton | Drawing tools and layers | visualiser/dialogs.py:9525 |
| Save | QPushButton | Recovery and run outcomes | visualiser/dialogs.py:9526 |
| Department waste stream generation | setWindowTitle | Advanced demand | visualiser/dialogs.py:9628 |
| Add stream | QPushButton | Drawing tools and layers | visualiser/dialogs.py:9658 |
| Edit selected | QPushButton | Drawing tools and layers | visualiser/dialogs.py:9659 |
| Delete selected | QPushButton | Drawing tools and layers | visualiser/dialogs.py:9660 |
| Waste stream generation settings | setWindowTitle | Advanced demand | visualiser/dialogs.py:9771 |
| Container/bin is present at the department when simulation starts | QCheckBox | Drawing tools and layers | visualiser/dialogs.py:9799 |
| Share this physical bin/container with other departments | QCheckBox | Drawing tools and layers | visualiser/dialogs.py:9805 |
| Edit times... | QPushButton | Drawing tools and layers | visualiser/dialogs.py:9826 |
| Clear | QPushButton | Drawing tools and layers | visualiser/dialogs.py:9827 |
| Inherit | QPushButton | Drawing tools and layers | visualiser/dialogs.py:9828 |
| Blank numeric fields and partially checked boxes inherit the effective rule settings. Use Demand Preview to inspect the resolved values. These generation overrides apply to modern Waste rules; legacy department waste uses demographic rates and global stream definitions. | QLabel | Relinking and evidence | visualiser/dialogs.py:9844 |
| Waste stream | addRow | Drawing tools and layers | visualiser/dialogs.py:9850 |
| Generation mode | addRow | Advanced demand | visualiser/dialogs.py:9851 |
| Frequency per day | addRow | Drawing tools and layers | visualiser/dialogs.py:9852 |
| Volume per event m³ | addRow | Drawing tools and layers | visualiser/dialogs.py:9853 |
| Threshold volume m³ | addRow | Drawing tools and layers | visualiser/dialogs.py:9854 |
| Base daily volume m³ | addRow | Drawing tools and layers | visualiser/dialogs.py:9855 |
| Scheduled times | addRow | Staff and people | visualiser/dialogs.py:9856 |
| Shared bin group | addRow | Drawing tools and layers | visualiser/dialogs.py:9859 |
| Assign department drop-off zone | setWindowTitle | Drawing tools and layers | visualiser/dialogs.py:10034 |
| Create a new drop-off zone | addItem | Drawing tools and layers | visualiser/dialogs.py:10055 |
| Drop-off zone | addRow | Drawing tools and layers | visualiser/dialogs.py:10058 |
| New zone location name | addRow | Drawing tools and layers | visualiser/dialogs.py:10062 |
| Select an existing drop-off zone or create a new one, then choose every task category that should stage its deliveries there. | QLabel | Advanced demand | visualiser/dialogs.py:10064 |
| Select all | QPushButton | Drawing tools and layers | visualiser/dialogs.py:10091 |
| Clear | QPushButton | Drawing tools and layers | visualiser/dialogs.py:10092 |
| Department | setWindowTitle | Drawing tools and layers | visualiser/dialogs.py:10209 |
| Task location category | setAccessibleName | Advanced demand | visualiser/dialogs.py:10262 |
| Task locations && zones | addTab | Advanced demand | visualiser/dialogs.py:10269 |
| Enabled | QCheckBox | Drawing tools and layers | visualiser/dialogs.py:10275 |
| 24.00 h | QLabel | Drawing tools and layers | visualiser/dialogs.py:10294 |
| None selected | QLabel | Drawing tools and layers | visualiser/dialogs.py:10311 |
| Select... | QPushButton | Drawing tools and layers | visualiser/dialogs.py:10313 |
| Department ID | addRow | Drawing tools and layers | visualiser/dialogs.py:10321 |
| Department name | addRow | Drawing tools and layers | visualiser/dialogs.py:10322 |
| Floor | addRow | Main chapters 1, 2, 3 | visualiser/dialogs.py:10323 |
| Status | addRow | Drawing tools and layers | visualiser/dialogs.py:10324 |
| Bed count | addRow | Drawing tools and layers | visualiser/dialogs.py:10325 |
| Patient turnover | addRow | Drawing tools and layers | visualiser/dialogs.py:10326 |
| Staff count | addRow | Staff and people | visualiser/dialogs.py:10327 |
| Operating start | addRow | Drawing tools and layers | visualiser/dialogs.py:10328 |
| Operating end | addRow | Drawing tools and layers | visualiser/dialogs.py:10329 |
| Calculated operating hours | addRow | Drawing tools and layers | visualiser/dialogs.py:10330 |
| Days active | addRow | Drawing tools and layers | visualiser/dialogs.py:10331 |
| Assigned waste streams | addRow | Drawing tools and layers | visualiser/dialogs.py:10332 |
| Waste streams drive Waste task generation. Configure the generation mode, frequency, volume per event, threshold and scheduled times here rather than in the Task Generation category override. | QLabel | Advanced demand | visualiser/dialogs.py:10333 |
| Select or create one staged-delivery location and assign it to several categories. | QLabel | Drawing tools and layers | visualiser/dialogs.py:10419 |
| Select or create... | QPushButton | Drawing tools and layers | visualiser/dialogs.py:10423 |
| Reuse an existing drop-off zone or create a new one, then assign it to several categories. | setToolTip | Drawing tools and layers | visualiser/dialogs.py:10424 |
| Shared drop-off zone | addRow | Drawing tools and layers | visualiser/dialogs.py:10431 |
| Placed pickup/drop-off locations and new zones stay provisional. Choose Save here, then Save in the Departments list to add both to the project. Undo removes that saved department edit and its new locations together. | QLabel | Recovery and run outcomes | visualiser/dialogs.py:10433 |
| Department location save instructions | setAccessibleName | Recovery and run outcomes | visualiser/dialogs.py:10439 |
| X | addRow | Drawing tools and layers | visualiser/dialogs.py:10442 |
| Y | addRow | Drawing tools and layers | visualiser/dialogs.py:10443 |
| Manage waste streams for selected departments | setWindowTitle | Drawing tools and layers | visualiser/dialogs.py:10991 |
| Tick a stream to assign it to all selected departments. Untick a stream to remove it from all selected departments. A partially ticked stream is currently assigned to only some departments; leave it partially ticked to make no assignment/settings change. For checked streams, only fields you edit are applied to all selected departments. Blank untouched fields mean unchanged. Clearing an edited numeric field restores inheritance. New assignments inherit the effective rule unless you supply overrides. Deleted/orphaned streams are shown so they can be unchecked and removed. If selected departments use different shared bin groups, those groups are preserved unless you edit that field. | QLabel | Recovery and run outcomes | visualiser/dialogs.py:11017 |
| Assign all | QPushButton | Drawing tools and layers | visualiser/dialogs.py:11061 |
| Remove all | QPushButton | Drawing tools and layers | visualiser/dialogs.py:11062 |
| Leave mixed unchanged | QPushButton | Drawing tools and layers | visualiser/dialogs.py:11063 |
| Task category shared-location wizard | setWindowTitle | Advanced demand | visualiser/dialogs.py:11505 |
| Assign the same pickup / drop-off location to several departments for a task generation category. This is useful where multiple departments share one store, bin, collection point or common drop-off location. | QLabel | Advanced demand | visualiser/dialogs.py:11520 |
| Task category | addRow | Advanced demand | visualiser/dialogs.py:11534 |
| None selected | QLabel | Drawing tools and layers | visualiser/dialogs.py:11537 |
| Select shared location... | QPushButton | Drawing tools and layers | visualiser/dialogs.py:11539 |
| Clear | QPushButton | Drawing tools and layers | visualiser/dialogs.py:11541 |
| Shared location(s) | addRow | Drawing tools and layers | visualiser/dialogs.py:11546 |
| Replace existing assignments for this category | QCheckBox | Advanced demand | visualiser/dialogs.py:11549 |
| Only enabled departments | QCheckBox | Drawing tools and layers | visualiser/dialogs.py:11553 |
| Options | addRow | Drawing tools and layers | visualiser/dialogs.py:11558 |
| Select all | QPushButton | Drawing tools and layers | visualiser/dialogs.py:11562 |
| Select none | QPushButton | Drawing tools and layers | visualiser/dialogs.py:11563 |
| Select current floor | QPushButton | Main chapters 1, 2, 3 | visualiser/dialogs.py:11564 |
| Select departments already using category | QPushButton | Advanced demand | visualiser/dialogs.py:11565 |
| Auto shared bin groups from category locations | setWindowTitle | Advanced demand | visualiser/dialogs.py:11823 |
| Find departments that already share the same assigned task-category location, then write a matching shared bin group for each assigned waste stream. Different waste streams receive different physical-bin group IDs. This does not change the existing category location assignments. | QLabel | Advanced demand | visualiser/dialogs.py:11838 |
| Source task category | addRow | Advanced demand | visualiser/dialogs.py:11858 |
| All assigned waste streams | QLabel | Drawing tools and layers | visualiser/dialogs.py:11861 |
| Select streams... | QPushButton | Drawing tools and layers | visualiser/dialogs.py:11863 |
| All | QPushButton | Drawing tools and layers | visualiser/dialogs.py:11865 |
| Waste streams to update | addRow | Drawing tools and layers | visualiser/dialogs.py:11870 |
| Shared bin group prefix | addRow | Drawing tools and layers | visualiser/dialogs.py:11873 |
| Only enabled departments | QCheckBox | Drawing tools and layers | visualiser/dialogs.py:11876 |
| Only selected departments | QCheckBox | Drawing tools and layers | visualiser/dialogs.py:11878 |
| Overwrite existing shared bin groups | QCheckBox | Drawing tools and layers | visualiser/dialogs.py:11880 |
| Options | addRow | Drawing tools and layers | visualiser/dialogs.py:11892 |
| Refresh preview | QPushButton | Relinking and evidence | visualiser/dialogs.py:11896 |
| Select all groups | QPushButton | Drawing tools and layers | visualiser/dialogs.py:11897 |
| Select none | QPushButton | Drawing tools and layers | visualiser/dialogs.py:11898 |
| Select current floor groups | QPushButton | Main chapters 1, 2, 3 | visualiser/dialogs.py:11899 |
| Departments | setWindowTitle | Drawing tools and layers | visualiser/dialogs.py:12298 |
| Enable selected | QPushButton | Drawing tools and layers | visualiser/dialogs.py:12341 |
| Disable selected | QPushButton | Drawing tools and layers | visualiser/dialogs.py:12342 |
| Enable every selected department. Changes are applied when Save is pressed. | setToolTip | Recovery and run outcomes | visualiser/dialogs.py:12343 |
| Disable every selected department. Changes are applied when Save is pressed. | setToolTip | Recovery and run outcomes | visualiser/dialogs.py:12346 |
| Add | QPushButton | Drawing tools and layers | visualiser/dialogs.py:12356 |
| Edit | QPushButton | Drawing tools and layers | visualiser/dialogs.py:12357 |
| Delete | QPushButton | Drawing tools and layers | visualiser/dialogs.py:12358 |
| Save | QPushButton | Recovery and run outcomes | visualiser/dialogs.py:12359 |
| Auto assign locations | QPushButton | Drawing tools and layers | visualiser/dialogs.py:12361 |
| Task category wizard... | QPushButton | Advanced demand | visualiser/dialogs.py:12362 |
| Auto shared bin groups... | QPushButton | Drawing tools and layers | visualiser/dialogs.py:12363 |
| Manage waste streams... | QPushButton | Drawing tools and layers | visualiser/dialogs.py:12364 |
| Export CSV | QPushButton | Report options | visualiser/dialogs.py:12365 |
| Create inventory space array | setWindowTitle | Inventory and exchanges | visualiser/dialogs.py:13349 |
| Type | addRow | Drawing tools and layers | visualiser/dialogs.py:13390 |
| Payload / AMR | addRow | Inventory and exchanges | visualiser/dialogs.py:13391 |
| Quantity | addRow | Drawing tools and layers | visualiser/dialogs.py:13392 |
| Alignment | addRow | Drawing tools and layers | visualiser/dialogs.py:13393 |
| Grid columns | addRow | Drawing tools and layers | visualiser/dialogs.py:13394 |
| Horizontal spacing (m) | addRow | Drawing tools and layers | visualiser/dialogs.py:13395 |
| Vertical spacing (m) | addRow | Drawing tools and layers | visualiser/dialogs.py:13396 |
| Rotation ° | addRow | Drawing tools and layers | visualiser/dialogs.py:13397 |
| Spacing is the clear gap between adjacent AMR/payload footprints. Grid uses the column count, then wraps to the next row. | QLabel | Inventory and exchanges | visualiser/dialogs.py:13399 |
| New space | QPushButton | Drawing tools and layers | visualiser/dialogs.py:13527 |
| Save current | QPushButton | Recovery and run outcomes | visualiser/dialogs.py:13529 |
| Copy selected | QPushButton | Drawing tools and layers | visualiser/dialogs.py:13530 |
| Paste copy | QPushButton | Drawing tools and layers | visualiser/dialogs.py:13531 |
| Delete selected | QPushButton | Drawing tools and layers | visualiser/dialogs.py:13532 |
| Save and close | QPushButton | Recovery and run outcomes | visualiser/dialogs.py:13533 |
| Rectangular snap | QCheckBox | Main chapters 1, 2, 3 | visualiser/dialogs.py:13557 |
| Lock size | QCheckBox | Drawing tools and layers | visualiser/dialogs.py:13567 |
| Apply height to selected | QPushButton | Drawing tools and layers | visualiser/dialogs.py:13568 |
| Maximum clear height for this space in metres. This can be set independently for fixed, flexible and AMR spaces. | setToolTip | Drawing tools and layers | visualiser/dialogs.py:13576 |
| Set the entered maximum height on every selected inventory space. | setToolTip | Inventory and exchanges | visualiser/dialogs.py:13580 |
| Flexible payload space (assign any payload that fits its maximum dimensions) | QCheckBox | Inventory and exchanges | visualiser/dialogs.py:13598 |
| Ignore the template payload type and select this space by maximum length, width and height. Payloads may rotate 90 degrees in plan. | setToolTip | Inventory and exchanges | visualiser/dialogs.py:13601 |
| Free-angle rotation in degrees for the selected payload inventory space | setToolTip | Inventory and exchanges | visualiser/dialogs.py:13610 |
| -5° | QPushButton | Drawing tools and layers | visualiser/dialogs.py:13614 |
| +5° | QPushButton | Drawing tools and layers | visualiser/dialogs.py:13615 |
| Add payload | QPushButton | Inventory and exchanges | visualiser/dialogs.py:13627 |
| Auto align | QPushButton | Drawing tools and layers | visualiser/dialogs.py:13628 |
| Add AMR space | QPushButton | Drawing tools and layers | visualiser/dialogs.py:13641 |
| Create an inventory space sized to the selected AMR so this location can store / park AMRs. | setToolTip | Inventory and exchanges | visualiser/dialogs.py:13642 |
| Array... | QPushButton | Drawing tools and layers | visualiser/dialogs.py:13644 |
| Create multiple payload or AMR spaces with a chosen spacing and alignment. | setToolTip | Inventory and exchanges | visualiser/dialogs.py:13645 |
| Selected AMR space(s) contain chargers | QCheckBox | Inventory and exchanges | visualiser/dialogs.py:13654 |
| Only AMR spaces with this enabled can recharge an AMR. Other AMR spaces remain parking/stowage bays. | setToolTip | Inventory and exchanges | visualiser/dialogs.py:13655 |
| Set chargers | QPushButton | Inventory and exchanges | visualiser/dialogs.py:13660 |
| Clear chargers | QPushButton | Inventory and exchanges | visualiser/dialogs.py:13661 |
| Mark as AMR | QPushButton | Drawing tools and layers | visualiser/dialogs.py:13662 |
| Apply charger enabled to all selected compatible AMR spaces. | setToolTip | Inventory and exchanges | visualiser/dialogs.py:13663 |
| Apply charger disabled to all selected AMR spaces. | setToolTip | Inventory and exchanges | visualiser/dialogs.py:13664 |
| Mark all selected inventory spaces as AMR spaces using the selected AMR type. | setToolTip | Inventory and exchanges | visualiser/dialogs.py:13665 |
| Auto arrange payload capacity... | QPushButton | Inventory and exchanges | visualiser/dialogs.py:13669 |
| Create the requested number of payload spaces while reserving AMR approach and movement clearance. | setToolTip | Inventory and exchanges | visualiser/dialogs.py:13670 |
| Inventory spaces are fixed footprints. Use Add payload or Add AMR space, then drag to position it or use the rotate handle / angle field. | QLabel | Inventory and exchanges | visualiser/dialogs.py:13695 |
| Copy | addAction | Drawing tools and layers | visualiser/dialogs.py:14955 |
| Paste | addAction | Drawing tools and layers | visualiser/dialogs.py:14956 |
| Delete | addAction | Drawing tools and layers | visualiser/dialogs.py:14957 |
| Scheduled task times over a 24 hour day | QLabel | Advanced demand | visualiser/dialogs.py:397 |
| Working | QLabel | Drawing tools and layers | visualiser/dialogs.py:565 |
| Day | QLabel | Drawing tools and layers | visualiser/dialogs.py:566 |
| Start | QLabel | Drawing tools and layers | visualiser/dialogs.py:567 |
| Finish | QLabel | Drawing tools and layers | visualiser/dialogs.py:568 |
| Fixed working-hours pattern | QLabel | Drawing tools and layers | visualiser/dialogs.py:734 |
| 4 on / 4 off, 12-hour pattern | QLabel | Drawing tools and layers | visualiser/dialogs.py:747 |
| Categories | QLabel | Drawing tools and layers | visualiser/dialogs.py:2119 |
| Department / configured group | QLabel | Drawing tools and layers | visualiser/dialogs.py:2139 |
| Length | addRow | Drawing tools and layers | visualiser/dialogs.py:4611 |
| Width | addRow | Drawing tools and layers | visualiser/dialogs.py:4612 |
| Area | addRow | Drawing tools and layers | visualiser/dialogs.py:4613 |
| Stored location metadata. Current people routing uses corridor-edge classifications; this location setting does not restrict access. | setToolTip | Staff and people | visualiser/dialogs.py:4628 |
| Require the AMR to complete a wash cycle after visiting this location | QCheckBox | Inventory and exchanges | visualiser/dialogs.py:4632 |
| Use task drop-off | addItem | Advanced demand | visualiser/dialogs.py:4643 |
| Washing follows delivery. If both pickup and drop-off require washing, the drop-off rule wins. An empty target uses the task drop-off. | setToolTip | Advanced demand | visualiser/dialogs.py:4644 |
| People using this area | addRow | Staff and people | visualiser/dialogs.py:4660 |
| Infection / hazardous-area control | addRow | Drawing tools and layers | visualiser/dialogs.py:4661 |
| Wash-cycle duration | addRow | Inventory and exchanges | visualiser/dialogs.py:4662 |
| Wash location | addRow | Inventory and exchanges | visualiser/dialogs.py:4663 |
| Existing floor positions are kept. A newly added floor uses the X/Y position where the lift was created. | QLabel | Main chapters 5, 6, 10, 11 | visualiser/dialogs.py:4926 |
| Selected scenario | QLabel | Drawing tools and layers | visualiser/dialogs.py:7782 |
| Description | QLabel | Drawing tools and layers | visualiser/dialogs.py:7802 |
| Find | QLabel | Drawing tools and layers | visualiser/dialogs.py:8249 |
| Traffic direction | QLabel | Drawing tools and layers | visualiser/dialogs.py:8307 |
| Nominal clear width | QLabel | Drawing tools and layers | visualiser/dialogs.py:8309 |
| People classification | QLabel | Staff and people | visualiser/dialogs.py:8311 |
| Assigned people profiles | QLabel | Staff and people | visualiser/dialogs.py:8313 |
| Find | QLabel | Drawing tools and layers | visualiser/dialogs.py:8336 |
| Door classification | QLabel | Main chapters 1, 2, 3 | visualiser/dialogs.py:8369 |
| Clear opening width | QLabel | Drawing tools and layers | visualiser/dialogs.py:8371 |
| Historical geometric comparison | addItem | Drawing tools and layers | visualiser/dialogs.py:8695 |
| None selected | QLabel | Drawing tools and layers | visualiser/dialogs.py:10359 |
| Select... | QPushButton | Drawing tools and layers | visualiser/dialogs.py:10362 |
| Place... | QPushButton | Drawing tools and layers | visualiser/dialogs.py:10377 |
| Place location on the DXF/editor scene | setToolTip | Drawing tools and layers | visualiser/dialogs.py:10378 |
| Direct delivery (no zone) | QLabel | Drawing tools and layers | visualiser/dialogs.py:10397 |
| Select... | QPushButton | Drawing tools and layers | visualiser/dialogs.py:10399 |
| Select one or more flexible staging locations where the AMR leaves payloads for department staff to complete the final leg. | setToolTip | Staff and people | visualiser/dialogs.py:10400 |
| Present | QCheckBox | Drawing tools and layers | visualiser/dialogs.py:11216 |
| Edit... | QPushButton | Drawing tools and layers | visualiser/dialogs.py:11245 |
| Clear | QPushButton | Drawing tools and layers | visualiser/dialogs.py:11246 |
| Minimum departments per group | QLabel | Drawing tools and layers | visualiser/dialogs.py:11889 |
| Inventory spaces | QLabel | Inventory and exchanges | visualiser/dialogs.py:13524 |
| Space name | QLabel | Drawing tools and layers | visualiser/dialogs.py:13554 |
| Length | QLabel | Drawing tools and layers | visualiser/dialogs.py:13587 |
| Width | QLabel | Drawing tools and layers | visualiser/dialogs.py:13589 |
| Max height | QLabel | Drawing tools and layers | visualiser/dialogs.py:13591 |
| Rotation ° | QLabel | Drawing tools and layers | visualiser/dialogs.py:13618 |
| Payload | QLabel | Inventory and exchanges | visualiser/dialogs.py:13631 |
| AMR | QLabel | Drawing tools and layers | visualiser/dialogs.py:13647 |
| This node represents a door or other local width restriction | QCheckBox | Batching and route restrictions | visualiser/dialogs.py:4671 |
| Restriction | addRow | Batching and route restrictions | visualiser/dialogs.py:4680 |
| Clear opening width | addRow | Drawing tools and layers | visualiser/dialogs.py:4681 |
| Uses the corridor assets currently selected in the topology view. | setToolTip | Main chapters 1, 2, 3 | visualiser/dialogs.py:7262 |
| invalid | addItem | Drawing tools and layers | visualiser/dialogs.py:8698 |
| Suffix | QLabel | Drawing tools and layers | visualiser/dialogs.py:10385 |
| Restricted by a door opening at one of the corridor endpoints. | setToolTip | Main chapters 1, 2, 3 | visualiser/dialogs.py:8403 |
| Show DXF underlay | QCheckBox | Drawing tools and layers | visualiser/dxf_layers.py:145 |
| Find a DXF layer | setAccessibleName | Drawing tools and layers | visualiser/dxf_layers.py:152 |
| DXF layers; checked layers are visible | setAccessibleName | Recovery and run outcomes | visualiser/dxf_layers.py:155 |
| Underlay display only. Route permissions and simulation geometry are unchanged. Choices follow this drawing path on this computer. | QLabel | Batching and route restrictions | visualiser/dxf_layers.py:165 |
| GeometryWorkbench | Workspace / dialog | Drawing tools and layers | visualiser/geometry_workbench.py:131 |
| AMR geometric workbench — workflow prototype | setWindowTitle | Drawing tools and layers | visualiser/geometry_workbench.py:134 |
| Snap 0.25 m | QCheckBox | Main chapters 1, 2, 3 | visualiser/geometry_workbench.py:155 |
| Add route or obstacle point using X and Y coordinates in metres | setAccessibleName | Batching and route restrictions | visualiser/geometry_workbench.py:161 |
| Permit stationary pivots when a turn cannot fit | QCheckBox | Drawing tools and layers | visualiser/geometry_workbench.py:184 |
| Body centre | addItem | Drawing tools and layers | visualiser/geometry_workbench.py:200 |
| Turning reference point | addItem | Drawing tools and layers | visualiser/geometry_workbench.py:201 |
| Pivot about | addRow | Drawing tools and layers | visualiser/geometry_workbench.py:204 |
| Load and robot share a centred rectangular envelope. Drawn rectangles are explicit obstacles. Export simulation creates a separate geometric project. This study previews forward paths and permitted pivots. | QLabel | Report options | visualiser/geometry_workbench.py:206 |
| X 0.00 m    Y 0.00 m | QLabel | Drawing tools and layers | visualiser/geometry_workbench.py:239 |
| Radius and travel speed refer to the marked reference point. Offsets use the robot body frame; the load remains centred. | QLabel | Drawing tools and layers | visualiser/geometry_workbench.py:205 |
| LocationSpacesManagerDialog | Workspace / dialog | Drawing tools and layers | visualiser/inventory_spaces_manager.py:87 |
| Locations & Inventory Spaces | setWindowTitle | Inventory and exchanges | visualiser/inventory_spaces_manager.py:101 |
| Browse locations on the left and edit spaces on the right. Detach a payload to accept any payload that fits, including a 90° turn. Changes stay in this dialog until Save all. | QLabel | Recovery and run outcomes | visualiser/inventory_spaces_manager.py:106 |
| Select similar locations | QPushButton | Drawing tools and layers | visualiser/inventory_spaces_manager.py:134 |
| Select locations with the same number of payload spaces and matching orientations within this tolerance. AMR spaces are excluded; position, payload type and dimensions do not affect the match. | setToolTip | Inventory and exchanges | visualiser/inventory_spaces_manager.py:135 |
| Select a location | QLabel | Drawing tools and layers | visualiser/inventory_spaces_manager.py:145 |
| Attach payload to selected | QPushButton | Inventory and exchanges | visualiser/inventory_spaces_manager.py:170 |
| Add AMR space | QPushButton | Drawing tools and layers | visualiser/inventory_spaces_manager.py:179 |
| Detach payloads in scope | QPushButton | Advanced demand | visualiser/inventory_spaces_manager.py:196 |
| Apply dimensions to flexible spaces in scope | QPushButton | Advanced demand | visualiser/inventory_spaces_manager.py:198 |
| Fixed payload and AMR dimensions follow their templates. Detach payloads before resizing. Angles rotate the bay around its centre. | QLabel | Inventory and exchanges | visualiser/inventory_spaces_manager.py:211 |
| Length m | QLabel | Drawing tools and layers | visualiser/inventory_spaces_manager.py:189 |
| Width m | QLabel | Drawing tools and layers | visualiser/inventory_spaces_manager.py:191 |
| LiftPlanner | Workspace / dialog | Main chapters 5, 6, 10, 11 | visualiser/lift_planner.py:20 |
| Plan lift locations | setWindowTitle | Main chapters 5, 6, 10, 11 | visualiser/lift_planner.py:25 |
| Infer and review drawing geometry before evaluating aligned lift sites. | QLabel | Relinking and evidence | visualiser/lift_planner.py:30 |
| Interpretation | addTab | Drawing tools and layers | visualiser/lift_planner.py:32 |
| Planning drawing floor | setAccessibleName | Main chapters 5, 6, 10, 11 | visualiser/lift_planner.py:33 |
| Infer drawings | QPushButton | Drawing tools and layers | visualiser/lift_planner.py:35 |
| Align floor… | QPushButton | Main chapters 1, 2, 3 | visualiser/lift_planner.py:36 |
| Exclude area… | QPushButton | Drawing tools and layers | visualiser/lift_planner.py:37 |
| I reviewed units, boundaries, circulation, exclusions and floor alignment. | QCheckBox | Relinking and evidence | visualiser/lift_planner.py:42 |
| Proposals | addTab | Main chapters 5, 6, 10, 11 | visualiser/lift_planner.py:46 |
| Proposal overlay floor | setAccessibleName | Main chapters 5, 6, 10, 11 | visualiser/lift_planner.py:47 |
| Generate five layout proposals | QPushButton | Main chapters 5, 6, 10, 11 | visualiser/lift_planner.py:55 |
| Sites are geometrically screened proposals. Review structural feasibility. Lift count, equipment and flow permissions stay fixed. | QLabel | Relinking and evidence | visualiser/lift_planner.py:61 |
| Scenarios | addTab | Drawing tools and layers | visualiser/lift_planner.py:63 |
| Service is compared for each department floor and flow; destination floors remain in the CSV evidence. Washing applies to AMRs. Relocation cannot restore a prohibited backup route or add lift capacity. | QLabel | Relinking and evidence | visualiser/lift_planner.py:71 |
| Evidence | addTab | Relinking and evidence | visualiser/lift_planner.py:73 |
| Evaluate scenarios | QPushButton | Drawing tools and layers | visualiser/lift_planner.py:79 |
| Stop evaluation | QPushButton | Drawing tools and layers | visualiser/lift_planner.py:80 |
| Create design variant… | QPushButton | Drawing tools and layers | visualiser/lift_planner.py:81 |
| Apply selected layout | QPushButton | Drawing tools and layers | visualiser/lift_planner.py:82 |
| Close | QPushButton | Drawing tools and layers | visualiser/lift_planner.py:83 |
| Floor | QLabel | Main chapters 1, 2, 3 | visualiser/lift_planner.py:34 |
| Model layer | setAccessibleName | Drawing tools and layers | visualiser/model_layer_panel.py:20 |
| Use for new drawing | QPushButton | Drawing tools and layers | visualiser/model_layer_panel.py:25 |
| Visible | QCheckBox | Drawing tools and layers | visualiser/model_layer_panel.py:27 |
| Locked against editing | QCheckBox | Drawing tools and layers | visualiser/model_layer_panel.py:28 |
| Assign selected objects | QPushButton | Drawing tools and layers | visualiser/model_layer_panel.py:31 |
| Line style… | QPushButton | Drawing tools and layers | visualiser/model_layer_panel.py:33 |
| Layer line colour | setAccessibleName | Drawing tools and layers | visualiser/model_layer_panel.py:40 |
| Layer line pattern | setAccessibleName | Drawing tools and layers | visualiser/model_layer_panel.py:43 |
| Layer line width in screen pixels | setAccessibleName | Drawing tools and layers | visualiser/model_layer_panel.py:48 |
| Colour | addRow | Drawing tools and layers | visualiser/model_layer_panel.py:49 |
| Pattern | addRow | Drawing tools and layers | visualiser/model_layer_panel.py:50 |
| Width | addRow | Drawing tools and layers | visualiser/model_layer_panel.py:51 |
| Apply line style | QPushButton | Drawing tools and layers | visualiser/model_layer_panel.py:52 |
| Restore theme style | QPushButton | Appearance and keyboard | visualiser/model_layer_panel.py:53 |
| Applies to corridors and location outlines. Blank colour follows the theme. Custom colours stay fixed; choose a visible colour and a distinct pattern. Selection and route-profile overlays keep their own styles. | QLabel | Appearance and keyboard | visualiser/model_layer_panel.py:56 |
| New model layer name | setAccessibleName | Drawing tools and layers | visualiser/model_layer_panel.py:69 |
| Add layer | QPushButton | Drawing tools and layers | visualiser/model_layer_panel.py:71 |
| Rename layer | QPushButton | Drawing tools and layers | visualiser/model_layer_panel.py:74 |
| Rename the selected layer using the name entered above. | setToolTip | Drawing tools and layers | visualiser/model_layer_panel.py:75 |
| Destination for removed layer contents | setAccessibleName | Drawing tools and layers | visualiser/model_layer_panel.py:79 |
| Move contents and remove layer | QPushButton | Drawing tools and layers | visualiser/model_layer_panel.py:84 |
| Layers control display and editing only. Clean/dirty/shared access stays in route profiles. New drawing uses the current layer; copies and split corridors retain their source layers. Undo restores layer edits too. | QLabel | Batching and route restrictions | visualiser/model_layer_panel.py:89 |
| Project layer | QLabel | Recovery and run outcomes | visualiser/model_layer_panel.py:18 |
| Move contents to | QLabel | Drawing tools and layers | visualiser/model_layer_panel.py:77 |
| MovementCapabilities | Workspace / dialog | Drawing tools and layers | visualiser/movement_capabilities.py:11 |
| Curved steering can remain permitted when stationary pivots are disabled. Available route searches and physical clearance still constrain every manoeuvre. | QLabel | Batching and route restrictions | visualiser/movement_capabilities.py:63 |
| Choose a capability preset | addItem | Drawing tools and layers | visualiser/movement_capabilities.py:44 |
| Apply preset to this state | QPushButton | Drawing tools and layers | visualiser/movement_capabilities.py:48 |
| Preset | addRow | Drawing tools and layers | visualiser/movement_capabilities.py:50 |
| PdfUnderlayDialog | Workspace / dialog | Report options | visualiser/pdf_underlay.py:158 |
| PDF underlay settings | setWindowTitle | Report options | visualiser/pdf_underlay.py:164 |
| The DXF/editor world uses metres. Paper dimensions and the plotted scale are converted to metres automatically. X and Y locate the lower-left paper corner. | QLabel | Drawing tools and layers | visualiser/pdf_underlay.py:168 |
| Page | addRow | Drawing tools and layers | visualiser/pdf_underlay.py:196 |
| Paper size | addRow | Drawing tools and layers | visualiser/pdf_underlay.py:197 |
| Orientation | addRow | Drawing tools and layers | visualiser/pdf_underlay.py:198 |
| Paper width (mm) | addRow | Drawing tools and layers | visualiser/pdf_underlay.py:199 |
| Paper height (mm) | addRow | Drawing tools and layers | visualiser/pdf_underlay.py:200 |
| Drawing scale (1 :) | addRow | Drawing tools and layers | visualiser/pdf_underlay.py:201 |
| Lower-left X (m) | addRow | Drawing tools and layers | visualiser/pdf_underlay.py:202 |
| Lower-left Y (m) | addRow | Drawing tools and layers | visualiser/pdf_underlay.py:203 |
| Rotation (degrees) | addRow | Drawing tools and layers | visualiser/pdf_underlay.py:204 |
| Opacity | addRow | Drawing tools and layers | visualiser/pdf_underlay.py:205 |
| ProjectChecksPanel | Workspace / dialog | Recovery and run outcomes | visualiser/project_checks_panel.py:20 |
| RunChecksDialog | Workspace / dialog | Recovery and run outcomes | visualiser/project_checks_panel.py:270 |
| Project checks | setWindowTitle | Recovery and run outcomes | visualiser/project_checks_panel.py:33 |
| Check inputs before running. Errors need correction; warnings can describe an intentional constraint study. | QLabel | Recovery and run outcomes | visualiser/project_checks_panel.py:35 |
| Not checked | QLabel | Recovery and run outcomes | visualiser/project_checks_panel.py:38 |
| Run checks | QPushButton | Recovery and run outcomes | visualiser/project_checks_panel.py:45 |
| Filter project findings | setAccessibleName | Recovery and run outcomes | visualiser/project_checks_panel.py:49 |
| Findings | addTab | Drawing tools and layers | visualiser/project_checks_panel.py:72 |
| Check coverage | addTab | Recovery and run outcomes | visualiser/project_checks_panel.py:82 |
| Finding explanation and suggested action | setAccessibleName | Drawing tools and layers | visualiser/project_checks_panel.py:86 |
| Go to affected settings | QPushButton | Drawing tools and layers | visualiser/project_checks_panel.py:90 |
| Export findings… | QPushButton | Report options | visualiser/project_checks_panel.py:92 |
| Warnings reviewed | QCheckBox | Relinking and evidence | visualiser/project_checks_panel.py:97 |
| I have reviewed the warnings for this configuration | setAccessibleName | Relinking and evidence | visualiser/project_checks_panel.py:98 |
| Acknowledge the warnings for this checked configuration. Changes require a fresh review. | setToolTip | Relinking and evidence | visualiser/project_checks_panel.py:99 |
| Project checks before simulation | setWindowTitle | Recovery and run outcomes | visualiser/project_checks_panel.py:273 |
| Cancel | QPushButton | Recovery and run outcomes | visualiser/project_checks_panel.py:281 |
| Run this checked configuration | QPushButton | Recovery and run outcomes | visualiser/project_checks_panel.py:283 |
| ProjectHistoryPanel | Workspace / dialog | Recovery and run outcomes | visualiser/project_history_panel.py:7 |
| Saved revision | setAccessibleName | Recovery and run outcomes | visualiser/project_history_panel.py:25 |
| Compare with current edits | QPushButton | Drawing tools and layers | visualiser/project_history_panel.py:27 |
| Configuration differences | setAccessibleName | Drawing tools and layers | visualiser/project_history_panel.py:32 |
| Preserve edits and restore selected revision | QPushButton | Drawing tools and layers | visualiser/project_history_panel.py:34 |
| ProjectPlaybackPanel | Workspace / dialog | Relinking and evidence | visualiser/project_playback_panel.py:540 |
| Project playback currently shows model geometry. Drawing underlays remain available in Layout. | setToolTip | Relinking and evidence | visualiser/project_playback_panel.py:223 |
| Optional calculation from frozen configuration; this is not recorded inventory evidence. | setToolTip | Relinking and evidence | visualiser/project_playback_panel.py:226 |
| Frozen run route profile display | setAccessibleName | Recovery and run outcomes | visualiser/project_playback_panel.py:235 |
| Show profile labels | QCheckBox | Batching and route restrictions | visualiser/project_playback_panel.py:236 |
| Simulation seconds per real second | setToolTip | Drawing tools and layers | visualiser/project_playback_panel.py:292 |
| Show legend | addAction | Drawing tools and layers | visualiser/project_playback_panel.py:313 |
| Follow selected AMR | setAccessibleName | Drawing tools and layers | visualiser/project_playback_panel.py:329 |
| Select a completed or stopped run in Simulate, then choose Playback selected run. | QLabel | Relinking and evidence | visualiser/project_playback_panel.py:553 |
| Speed | QLabel | Drawing tools and layers | visualiser/project_playback_panel.py:291 |
| Floor | QLabel | Main chapters 1, 2, 3 | visualiser/project_playback_panel.py:305 |
| Timeline | QLabel | Relinking and evidence | visualiser/project_playback_panel.py:362 |
| ProjectPropertiesPanel | Workspace / dialog | Recovery and run outcomes | visualiser/project_properties_panel.py:8 |
| Layout properties | QLabel | Main chapters 1, 2, 3 | visualiser/project_properties_panel.py:20 |
| Select an object in the tree or layout. | QLabel | Drawing tools and layers | visualiser/project_properties_panel.py:23 |
| Apply changes | QPushButton | Drawing tools and layers | visualiser/project_properties_panel.py:37 |
| Discard draft | QPushButton | Drawing tools and layers | visualiser/project_properties_panel.py:39 |
| Clean / dirty / shared access is defined by Route profiles in Configuration. Changing people occupancy does not change those profiles. | QLabel | Staff and people | visualiser/project_properties_panel.py:167 |
| Default | QPushButton | Drawing tools and layers | visualiser/project_properties_panel.py:146 |
| Remove this explicit override from all selected records. | setToolTip | Drawing tools and layers | visualiser/project_properties_panel.py:147 |
| Use default / unset | addItem | Drawing tools and layers | visualiser/project_properties_panel.py:116 |
| This property requires an explicit value. | setToolTip | Drawing tools and layers | visualiser/project_properties_panel.py:150 |
| Mixed — leave unchanged | addItem | Drawing tools and layers | visualiser/project_properties_panel.py:115 |
| Existing null — unchanged | addItem | Drawing tools and layers | visualiser/project_properties_panel.py:126 |
| ProjectReportPanel | Workspace / dialog | Report options | visualiser/project_report_panel.py:14 |
| Select a completed run in Simulate, then choose Report selected run. Reports use its frozen inputs, not current edits. | QLabel | Report options | visualiser/project_report_panel.py:27 |
| Choose run in Simulate | QPushButton | Recovery and run outcomes | visualiser/project_report_panel.py:31 |
| Generate report | QPushButton | Report options | visualiser/project_report_panel.py:33 |
| Stop generation | QPushButton | Advanced demand | visualiser/project_report_panel.py:36 |
| Open generated PDF | QPushButton | Report options | visualiser/project_report_panel.py:39 |
| Export 5-minute lift usage CSV | QPushButton | Report options | visualiser/project_report_panel.py:46 |
| Export the existing five-minute and hourly per-lift trip and travel tables without generating a PDF. | setToolTip | Report options | visualiser/project_report_panel.py:47 |
| Open lift usage CSV | QPushButton | Main chapters 5, 6, 10, 11 | visualiser/project_report_panel.py:50 |
| Report title | addRow | Report options | visualiser/project_report_panel.py:60 |
| Browse PDF... | QPushButton | Report options | visualiser/project_report_panel.py:65 |
| Existing PDF | addRow | Report options | visualiser/project_report_panel.py:72 |
| Insert after page (0 = before first) | addRow | Drawing tools and layers | visualiser/project_report_panel.py:77 |
| Insert selected sections as a supplement with its own title, linked contents and numbering. Existing pages are reused; the combined PDF is saved as a new report. | QLabel | Report options | visualiser/project_report_panel.py:79 |
| Report sections to include | setAccessibleName | Report options | visualiser/project_report_panel.py:83 |
| Include frozen drawing underlays in heatmaps | QCheckBox | Report options | visualiser/project_report_panel.py:91 |
| ProjectRunsPanel | Workspace / dialog | Recovery and run outcomes | visualiser/project_runs_panel.py:12 |
| Save a project to start a revision-bound simulation. | QLabel | Recovery and run outcomes | visualiser/project_runs_panel.py:22 |
| Save, check and simulate | QPushButton | Recovery and run outcomes | visualiser/project_runs_panel.py:26 |
| Stop run | QPushButton | Recovery and run outcomes | visualiser/project_runs_panel.py:28 |
| If a run folder moves, select its missing entry and choose Locate moved run. Playback opens recorded evidence read-only. Choose Report selected run, then Generate report to export from the run’s frozen inputs. | QLabel | Report options | visualiser/project_runs_panel.py:43 |
| Runs belonging to this project's saved revisions | setAccessibleName | Recovery and run outcomes | visualiser/project_runs_panel.py:50 |
| NewProjectDialog | Workspace / dialog | Recovery and run outcomes | visualiser/project_setup.py:16 |
| New project setup | setWindowTitle | Recovery and run outcomes | visualiser/project_setup.py:21 |
| Choose the number of floors and optionally assign a DXF or PDF background to each. You can configure the rest of the project with the existing dialogs, or skip this setup entirely. | QLabel | Report options | visualiser/project_setup.py:25 |
| Number of floors | setAccessibleName | Main chapters 1, 2, 3 | visualiser/project_setup.py:34 |
| Number of floors | addRow | Main chapters 1, 2, 3 | visualiser/project_setup.py:35 |
| Floor height | addRow | Main chapters 1, 2, 3 | visualiser/project_setup.py:41 |
| Floors are numbered from 0. Drawing assignments are optional. | QLabel | Main chapters 1, 2, 3 | visualiser/project_setup.py:43 |
| Project floors and drawing assignments | setAccessibleName | Recovery and run outcomes | visualiser/project_setup.py:48 |
| Start an empty project and use the existing dialogs. | setToolTip | Recovery and run outcomes | visualiser/project_setup.py:60 |
| ProjectWorkspace | Workspace / dialog | Recovery and run outcomes | visualiser/project_workspace.py:20 |
| Project | QLabel | Recovery and run outcomes | visualiser/project_workspace.py:55 |
| ‹ | QPushButton | Drawing tools and layers | visualiser/project_workspace.py:58 |
| Collapse project tree | setAccessibleName | Recovery and run outcomes | visualiser/project_workspace.py:59 |
| Collapse the project tree. Restore it from View → Project tree. | setToolTip | Recovery and run outcomes | visualiser/project_workspace.py:60 |
| Unsaved project | QLabel | Recovery and run outcomes | visualiser/project_workspace.py:65 |
| Filter project objects | setAccessibleName | Recovery and run outcomes | visualiser/project_workspace.py:70 |
| Project workflow and floors | setAccessibleName | Recovery and run outcomes | visualiser/project_workspace.py:77 |
| Previous | QPushButton | Drawing tools and layers | visualiser/project_workspace.py:108 |
| Next | QPushButton | Drawing tools and layers | visualiser/project_workspace.py:109 |
| Imported JSON validation issues | setAccessibleName | Drawing tools and layers | visualiser/project_workspace.py:123 |
| Recheck | QPushButton | Recovery and run outcomes | visualiser/project_workspace.py:130 |
| Recheck imported JSON validation | setAccessibleName | Recovery and run outcomes | visualiser/project_workspace.py:131 |
| Hide | QPushButton | Drawing tools and layers | visualiser/project_workspace.py:134 |
| Hide imported JSON validation issues | setAccessibleName | Drawing tools and layers | visualiser/project_workspace.py:135 |
| Imported JSON validation details | setAccessibleName | Drawing tools and layers | visualiser/project_workspace.py:141 |
| Edit the inputs, then recheck here before running Project checks. These issues reflect the import or last recheck. | setToolTip | Recovery and run outcomes | visualiser/project_workspace.py:177 |
| Add DXF… | command | Drawing tools and layers | visualiser/project_workspace.py:245 |
| Guide this floor… | command | Main chapters 1, 2, 3 | visualiser/project_workspace.py:246 |
| Change DXF… | command | Drawing tools and layers | visualiser/project_workspace.py:249 |
| Clear floor DXF | command | Main chapters 1, 2, 3 | visualiser/project_workspace.py:250 |
| DXF layers… | command | Drawing tools and layers | visualiser/project_workspace.py:252 |
| Edit demand-generation rules, schedules and category settings. | setToolTip | Advanced demand | visualiser/project_workspace.py:518 |
| Select a robot, payload, lift, task or route profile under Configuration in the project tree to edit its properties here. Changes share the project undo history. The full editors below provide nested slots, schedules and other options. Preview demand and run checks before simulation. | QLabel | Relinking and evidence | visualiser/project_workspace.py:594 |
| PropertyChoices | Workspace / dialog | Drawing tools and layers | visualiser/property_choices.py:9 |
| Select shown | QPushButton | Drawing tools and layers | visualiser/property_choices.py:39 |
| Clear all | QPushButton | Drawing tools and layers | visualiser/property_choices.py:41 |
| Add named edge permission | QPushButton | Drawing tools and layers | visualiser/property_choices.py:57 |
| Adds a directional allowance between named nodes; it does not create a physical link. | setToolTip | Drawing tools and layers | visualiser/property_choices.py:58 |
| → | QLabel | Drawing tools and layers | visualiser/property_choices.py:54 |
| QuickStartDialog | Workspace / dialog | Drawing tools and layers | visualiser/quick_start.py:96 |
| Guided walkthrough | setWindowTitle | Drawing tools and layers | visualiser/quick_start.py:100 |
| Follow an exercise or the checked building course while keeping this window open. Each step states an action and the expected application state. | QLabel | Recovery and run outcomes | visualiser/quick_start.py:104 |
| Walkthrough exercise | setAccessibleName | Drawing tools and layers | visualiser/quick_start.py:113 |
| Walkthrough steps | setAccessibleName | Drawing tools and layers | visualiser/quick_start.py:119 |
| Walkthrough action and expected state | setAccessibleName | Drawing tools and layers | visualiser/quick_start.py:122 |
| Previous step | QPushButton | Drawing tools and layers | visualiser/quick_start.py:127 |
| Next step | QPushButton | Drawing tools and layers | visualiser/quick_start.py:128 |
| Open workspace | QPushButton | Drawing tools and layers | visualiser/quick_start.py:129 |
| Exercises | addTab | Drawing tools and layers | visualiser/quick_start.py:136 |
| Quick reference for project controls | setAccessibleName | Recovery and run outcomes | visualiser/quick_start.py:139 |
| Controls reference | addTab | Drawing tools and layers | visualiser/quick_start.py:141 |
| Building course | addTab | Main chapters 1, 2, 3 | visualiser/quick_start.py:144 |
| Open exercise project | QPushButton | Recovery and run outcomes | visualiser/quick_start.py:146 |
| Open illustrated guide | QPushButton | Drawing tools and layers | visualiser/quick_start.py:149 |
| RectangleInput | Workspace / dialog | Drawing tools and layers | visualiser/rectangle_input.py:7 |
| Location rectangle dimensions and rotation | setAccessibleName | Drawing tools and layers | visualiser/rectangle_input.py:15 |
| Metres, then optional counterclockwise degrees from east. Centred on the location. Grid snapping is bypassed. | setToolTip | Main chapters 1, 2, 3 | visualiser/rectangle_input.py:16 |
| Apply dimensions | QPushButton | Drawing tools and layers | visualiser/rectangle_input.py:19 |
| Cancel | QPushButton | Recovery and run outcomes | visualiser/rectangle_input.py:20 |
| Rectangle (m, °) | QLabel | Drawing tools and layers | visualiser/rectangle_input.py:21 |
| Exact dimensions and rotation, centred on the selected location. | setToolTip | Drawing tools and layers | visualiser/rectangle_input.py:22 |
| ResultsInvestigationPanel | Workspace / dialog | Relinking and evidence | visualiser/results_investigation_panel.py:66 |
| Open event CSV… | QPushButton | Drawing tools and layers | visualiser/results_investigation_panel.py:80 |
| Open run folder… | QPushButton | Recovery and run outcomes | visualiser/results_investigation_panel.py:82 |
| Export investigation… | QPushButton | Report options | visualiser/results_investigation_panel.py:84 |
| Export selected evidence… | QPushButton | Report options | visualiser/results_investigation_panel.py:87 |
| Export all evidence for the selected task, metric or lift | setAccessibleName | Report options | visualiser/results_investigation_panel.py:88 |
| Exports every event in the selected timeline, including events on other pages. | setToolTip | Report options | visualiser/results_investigation_panel.py:89 |
| Open a saved run to investigate recorded events. Planned segments and confirmed task outcomes are separate evidence. | QLabel | Relinking and evidence | visualiser/results_investigation_panel.py:102 |
| Investigation log and event page limits | setAccessibleName | Relinking and evidence | visualiser/results_investigation_panel.py:110 |
| Filter result tasks | setAccessibleName | Advanced demand | visualiser/results_investigation_panel.py:115 |
| Lift movement consistency checks | setAccessibleName | Recovery and run outcomes | visualiser/results_investigation_panel.py:128 |
| Tasks | addTab | Advanced demand | visualiser/results_investigation_panel.py:131 |
| Metrics | addTab | Drawing tools and layers | visualiser/results_investigation_panel.py:132 |
| Lift checks | addTab | Recovery and run outcomes | visualiser/results_investigation_panel.py:133 |
| Run evidence | addTab | Relinking and evidence | visualiser/results_investigation_panel.py:134 |
| Select a task or metric to see its supporting events. | QLabel | Advanced demand | visualiser/results_investigation_panel.py:138 |
| Follow task, payload, journey or lift evidence | setAccessibleName | Relinking and evidence | visualiser/results_investigation_panel.py:143 |
| Choose an identity linked to this task to inspect every matching record in the saved log. | setToolTip | Recovery and run outcomes | visualiser/results_investigation_panel.py:144 |
| Previous page | QPushButton | Drawing tools and layers | visualiser/results_investigation_panel.py:149 |
| Next page | QPushButton | Drawing tools and layers | visualiser/results_investigation_panel.py:150 |
| Timeline event page | setAccessibleName | Relinking and evidence | visualiser/results_investigation_panel.py:154 |
| No events | QLabel | Drawing tools and layers | visualiser/results_investigation_panel.py:155 |
| Selected event explanation and evidence identity | setAccessibleName | Relinking and evidence | visualiser/results_investigation_panel.py:173 |
| Lift studies… | QPushButton | Main chapters 5, 6, 10, 11 | visualiser/results_investigation_panel.py:95 |
| RouteDisplayPanel | Workspace / dialog | Batching and route restrictions | visualiser/route_display_panel.py:9 |
| Route identification | QLabel | Batching and route restrictions | visualiser/route_display_panel.py:14 |
| Profile to inspect and display | setAccessibleName | Batching and route restrictions | visualiser/route_display_panel.py:25 |
| Route label and line colour | setAccessibleName | Batching and route restrictions | visualiser/route_display_panel.py:34 |
| Route line pattern | setAccessibleName | Batching and route restrictions | visualiser/route_display_panel.py:37 |
| Choose colour… | QPushButton | Drawing tools and layers | visualiser/route_display_panel.py:38 |
| Save style | QPushButton | Recovery and run outcomes | visualiser/route_display_panel.py:41 |
| Default style | QPushButton | Drawing tools and layers | visualiser/route_display_panel.py:43 |
| Colour | addRow | Drawing tools and layers | visualiser/route_display_panel.py:48 |
| Line pattern | addRow | Drawing tools and layers | visualiser/route_display_panel.py:49 |
| Filter profile access records | setAccessibleName | Batching and route restrictions | visualiser/route_display_panel.py:62 |
| Show selected profile in Layout | QPushButton | Batching and route restrictions | visualiser/route_display_panel.py:76 |
| CirculationOverlay | Workspace / dialog | Drawing tools and layers | visualiser/tutorial_bubble.py:70 |
| TargetOutline | Workspace / dialog | Drawing tools and layers | visualiser/tutorial_bubble.py:114 |
| DragHandle | Workspace / dialog | Drawing tools and layers | visualiser/tutorial_bubble.py:124 |
| TutorialBubble | Workspace / dialog | Main chapters 1, 2 | visualiser/tutorial_bubble.py:173 |
| Tutorial route and next click preview | setAccessibleName | Main chapters 1, 2 | visualiser/tutorial_bubble.py:75 |
| Building tutorial instruction bubble | setAccessibleName | Main chapters 1, 2 | visualiser/tutorial_bubble.py:181 |
| Tutorial bubble chapter | setAccessibleName | Main chapters 1, 2 | visualiser/tutorial_bubble.py:188 |
| Move tutorial bubble | setAccessibleName | Main chapters 1, 2 | visualiser/tutorial_bubble.py:192 |
| Drag to move this bubble | setToolTip | Main chapters 1, 2 | visualiser/tutorial_bubble.py:192 |
| Tutorial placement name, floor and coordinates | setAccessibleName | Main chapters 1, 2 | visualiser/tutorial_bubble.py:198 |
| Back | QPushButton | Drawing tools and layers | visualiser/tutorial_bubble.py:199 |
| Next | QPushButton | Drawing tools and layers | visualiser/tutorial_bubble.py:199 |
| Details | QPushButton | Drawing tools and layers | visualiser/tutorial_bubble.py:199 |
| Show control | QPushButton | Drawing tools and layers | visualiser/tutorial_bubble.py:202 |
| Pause | QPushButton | Drawing tools and layers | visualiser/tutorial_bubble.py:203 |
| Show explanation / corrections | addAction | Drawing tools and layers | visualiser/tutorial_bubble.py:206 |
| Reset bubble position | addAction | Main chapters 1, 2 | visualiser/tutorial_bubble.py:207 |
| Course reference | addAction | Drawing tools and layers | visualiser/tutorial_bubble.py:208 |
| Flow policy | addMenu | Drawing tools and layers | visualiser/tutorial_bubble.py:209 |
