"""Source-reviewed contracts for the simulation audit backlog.

Rows are field, disposition, units, omitted value and observable effect.
Shared validation and precedence describe the named resolver, not a new schema.
"""


def reviewed_fields():
    fields = {}

    def add(prefix, modes, sources, tests, validation, rows, *, precedence='Explicit value in the selected scope; otherwise the stated default.'):
        for line in rows.strip().splitlines():
            name, disposition, units, default, effect = (part.strip() for part in line.split('|'))
            path = '.'.join(part for part in (prefix, name) if part).replace('.[]', '[]')
            if path in fields:
                raise ValueError(f'Duplicate audit contract {path}')
            fields[path] = dict(classification=disposition, modes=modes, units=units,
                                runtime_default=default, precedence=precedence, validation=validation,
                                meaning=effect, source_symbols=sources.split(), tests=tests.split())

    add('simulation', 'Managed and direct AMR runs', 'amr_simulation_inputs.py:simulation_input_findings amr_simulation_inputs.py:resolved_simulation_settings simulator.py:Simulation._try_assign_tasks', 'test_simulation_run_controls.*', 'Shared validator checks finite numeric bounds, integral counts and explicit legacy checkbox encodings.', """
assignment_continue_delay_sec | runtime | seconds | 0.001 | Minimum delay before another assignment batch is scheduled.
enable_opportunity_charging | runtime | boolean | false | Lets eligible idle robots start opportunistic charging.
generated_task_release_stagger_sec | runtime | seconds | 0.25 | Spacing used when generated releases coincide; explicit value wins over task_release_stagger_sec.
idle_return_check_interval_sec | runtime | seconds | 60 | Controls frequency of idle-return checks.
max_assignments_per_tick | runtime | count | 50; zero means unlimited | Limits work before an assignment continuation event.
max_multi_stop_candidate_tasks | runtime | count | 8 | Limits how many tasks a multi-stop selection considers.
max_single_candidate_tasks | runtime | count | 8 | Controls the size of ordered candidate windows for single-task assignment.
opportunity_charging_check_interval_sec | conditional | seconds | idle_return_check_interval_sec | Controls opportunity charging checks when enabled.
opportunity_charging_idle_period_sec | conditional | seconds | 900 | Idle time required for opportunity charging.
precompute_static_routes | runtime | boolean | true | Enables initial static route warming. Route selection must remain equivalent with it disabled.
reservation_history_retention_sec | runtime | seconds | Greater of 300 and twice the congestion window | Determines historical reservations retained after pruning; configured values are floored at twice the congestion window.
reservation_prune_interval_sec | runtime | seconds | 300 | Interval between pruning passes on the simulation clock.
route_precompute_max_pairs | conditional | count | 100000; zero means no limit | Skips precomputation if the candidate pair count exceeds the nonzero cap.
""")
    add('simulation', 'Managed and direct AMR runs', 'amr_simulation_inputs.py:simulation_input_findings amr_simulation_inputs.py:resolved_simulation_settings simulator.py:Simulation._start_task_deferral_limit simulator.py:Simulation._expire_task_deferral', 'test_task_deferral_settings.* test_task_deferral.*', 'A finite nonnegative duration is required. Zero permits unlimited deferral.', """
max_task_deferral_minutes | conditional | minutes | 60 | Schedules a pending task's deferral timeout once its first deferral starts and expires it if still outstanding.
""")
    add('simulation', 'AMR inventory controls', 'simulator.py:Simulation.__init__ simulator.py:_nested_get_bool simulator.py:_config_contains_enabled_bool_key', 'test_simulation_run_controls.* test_flexible_inventory_model.*', 'The canonical flag uses the shared checkbox validator. Runtime also accepts historical inventory bypass flag names.', """
disable_inventory_spaces | runtime | boolean | false | Excludes configured inventory spaces from execution.
""", precedence='A recognised enabled bypass flag anywhere in configuration can enable bypass, even when an earlier alias is false.')
    add('simulation', 'AMR runs and demand preview', 'amr_simulation_inputs.py:simulation_horizon_seconds amr_simulation_inputs.py:simulation_input_findings', 'test_simulation_run_controls.*', 'ISO datetimes must have compatible timezone offsets and an end at or after start. Duration values must be finite and nonnegative.', """
start_datetime | runtime | ISO datetime | 2026-01-01T08:00:00 | Defines time zero and the calendar used for generated demand.
end_datetime | conditional | ISO datetime | Derive from duration or latest release | Gives the inclusive demand horizon; existing work can drain beyond it.
duration_hours | conditional | hours | Derive from duration_days or latest release | Gives the demand horizon when end_datetime is absent.
duration_days | conditional | days | Latest valid static release plus one day | Gives the demand horizon when end_datetime and duration_hours are absent.
tick_rate | compatibility | configured rate | 120 | Stored by the clock; the event loop advances by event timestamps.
""", precedence='End datetime, then duration_hours, then duration_days, then the static-release fallback. Start and tick rate have independent defaults.')
    add('simulation', 'Simple, Detailed and historical geometric compatibility', 'amr_simulation_modes.py:resolve_simulation_mode amr_simulation_modes.py:mode_input_findings', 'test_simulation_modes.* test_mode_simulation_acceptance.*', 'Explicit Simple requires legacy motion; explicit Detailed requires geometric_v1 and keep-right geometry.', """
mode | conditional | mode identifier | Inferred from motion_model when omitted | Selects the physical and traffic model contract.
motion_model | runtime | model identifier | legacy | Selects graph timing or geometric movement and determines compatibility mode when the explicit mode is absent.
""")
    add('simulation', 'Current and legacy project formats', 'amr_simulation_inputs.py:resolved_simulation_settings simulator.py:Simulation.__init__', 'test_simulation_run_controls.* test_scenario_recovery.*', 'Boolean spellings are validated before managing a run; scenario execution reads scenario_testing.', """
scenario_mode | compatibility | boolean | absent | Legacy simulation key retained by input resolution; the scenario engine reads scenario_testing.enabled.
scenario_enhanced_logging | compatibility | boolean | absent | Legacy key; the scenario evidence writer uses scenario_testing.enhanced_logging.
computation_backend | compatibility | backend identifier | CPU execution | Retired selector removed from runtime settings and retained in historical evidence.
""", precedence='The active scenario configuration is under scenario_testing.')

    add('building', 'AMR travel, storage and lift movement', 'simulator.py:Simulation.__init__ simulator.py:Simulation._same_floor_segments simulator.py:Simulation._find_next_edge_start', 'test_routing_contracts.* test_simulation_run_controls.*', 'Runtime converts numeric values to metres, seconds, whole counts or factors; managed checks also validate the configured layout.', """
amr_centre | runtime | location identifier | AMR_CENTRE | Supplies the normal idle return destination where enabled.
amr_spacing_m | runtime | metres | 1.5 | Dividing by robot speed gives nominal corridor time spacing.
edge_congestion_window_sec | runtime | seconds | 30 | Recent-demand window for corridor slowdown.
edge_max_concurrency | runtime | count | 1 | Fallback capacity for edge reservations; a lane-specific capacity takes precedence when supplied.
edge_slowdown_per_amr | runtime | fraction per robot | 0.15 | Subtracted from nominal speed factor for each recent corridor reservation.
enable_idle_return | runtime | boolean | true | Allows idle-return trips.
floor_height_m | runtime | metres | 4 | Converts vertical floor differences into physical distance, including lift energy calculations.
idle_return_window_sec | conditional | seconds | 300 | Idle-return lookahead used when idle return is enabled.
min_congestion_speed_factor | runtime | fraction | 0.45 | Floor for the congestion component of corridor speed.
minimum_people_speed_factor | conditional | fraction | 0.35 | Lower limit for the people-induced slowdown; runtime bounds it to 0.05–1.
node_clearance_time_sec | runtime | seconds | 0.5 | Clearance interval used for traffic admission.
people_slowdown_per_person | conditional | fraction per person | 0.08 | Sets the per-person corridor slowdown when groups occupy an edge.
""")
    add('building', 'Project workbench', 'visualiser/models.py:JsonStore', 'test_building_tutorial.*', 'Workbench floor setup resolves the floor count from its configuration and existing layouts.', """
floor_count | presentation | count | Derived by project setup when omitted | Preserves configured floor display and layout coverage; routing reads actual locations, edges and lift stops.
""")
    add('building', 'AMR logistics and human-study pickup/unload defaults', 'simulator.py:Simulation.__init__ amr_contingency_inputs.py:default_settings', 'test_payload_action_timing.* test_contingency_timing.*', 'Managed project checks require a nonnegative numeric value; runtime converts it to seconds.', """
load_unload_time_sec | runtime | seconds | 20 | Sets the default pickup and unload action duration and the inferred default for human service profiles.
""")
    add('building', 'Interfloor planning', 'amr_routing_inputs.py:lift_policy_input_findings amr_routing_inputs.py:waypoint_input_findings amr_floor_routing.py:connecting_lift_plan amr_forced_floor.py:forced_lift_plan', 'test_forced_floor.* test_floor_waypoints.* test_forced_floor_lift_preference.*', 'Validate known integer floors and unique lift IDs, compatible waypoint entries, and an applicable origin for a forced-floor preference.', """
destination_side_lift_floors | conditional | floor identifiers | empty | Uses destination walking distance as the first comparison on listed origins.
lift_transfer_floor | conditional | floor identifier | absent | Supplies the legacy connection floor when no applicable waypoint is selected.
force_via_floor_enabled | conditional | boolean | false | Enables all-origin forced landing logic.
force_via_floor | conditional | floor identifier | Required when forced-floor mode is enabled | Identifies the floor the forced route must visit by alighting.
forced_floor_lift_preference | structural | policy object | off | Holds the forced-floor lift preference fields.
forced_floor_lift_preference.mode | conditional | policy identifier | off | Chooses off, prefer (with relaxation) or required for the applicable origin.
forced_floor_lift_preference.from_floor | conditional | floor identifier | Required for active preference | Restricts preference application to journeys originating on this floor.
forced_floor_lift_preference.lift_ids | conditional | lift identifiers | Required for active preference | Identifies the eligible cars for affected forced-stop legs.
mandatory_floor_waypoints | conditional | waypoint list | empty | Selects mandatory alighting floors by origin and destination pair.
mandatory_floor_waypoints[].from_floor | conditional | floor identifier | Required per rule | Matches the origin floor.
mandatory_floor_waypoints[].to_floors | conditional | floor identifiers | Required per rule | Matches the destination floors in that rule.
mandatory_floor_waypoints[].via_floor | conditional | floor identifier | Required per rule | Names the alighting floor required for a matching journey.
""", precedence='Global forced-floor policy takes precedence on its path; route profiles can suppress the forced-floor lift preference. Legacy connecting routes use explicit waypoints before the general connection floor.')
    add('building', 'Bed-lift fallback', 'amr_bed_lifts.py:bed_lift_input_findings amr_bed_lifts.py:select_plan', 'test_bed_lifts.*', 'Threshold must be finite and nonnegative.', """
bed_lift_fallback_wait_sec | conditional | seconds | 300 | Compares predicted FM boarding wait with the configured threshold before considering fallback.
""")
    add('lifts[]', 'AMR lift transfers', 'amr_lift_transfer.py:transfer_input_findings amr_lift_transfer.py:transfer_seconds', 'test_lift_contracts.* test_forced_floor.*', 'Mode must be fixed or speed_based; speed-based transfer requires finite positive robot speed and connector distance.', """
transfer_timing_mode | conditional | mode identifier | fixed | Selects boarding duration per direction or graph connector distance divided by robot speed.
""")
    add('amrs[]', 'AMR lift transfers', 'amr_lift_transfer.py:transfer_input_findings amr_lift_transfer.py:transfer_seconds', 'test_lift_contracts.* test_forced_floor.*', 'Finite positive speed is required for enabled robots when a speed-based lift is present.', """
lift_entry_speed_m_per_sec | conditional | metres/second | Required for speed-based lifts | Divisor for entry connector length.
lift_exit_speed_m_per_sec | conditional | metres/second | Required for speed-based lifts | Divisor for exit connector length.
""")
    add('lifts[]', 'Bed-lift fallback', 'amr_bed_lifts.py:bed_lift_input_findings amr_bed_lifts.py:access_intervals amr_bed_lifts.py:access_slot', 'test_bed_lifts.*', 'Daily recurring time-of-day entries must be valid non-overlapping windows. Overnight windows are allowed.', """
usage_mode | runtime | mode identifier | fm | Classifies the car as FM or a bed-lift fallback.
amr_access_windows | conditional | daily intervals | empty | Defines when AMRs may use a fallback car.
amr_access_windows[].start | conditional | local HH:MM | Required in each interval | Opens the slot.
amr_access_windows[].end | conditional | local HH:MM | Required in each interval | Closes the slot; 24:00 is permitted for end.
""")
    add('', 'AMR runs, projects and applicable studies', 'simulator.py:Simulation.__init__ amr_project.py:Project.materialize', '', 'Each entry is resolved by the corresponding section loader and validator.', """
amrs | structural | robot records | empty | Defines the fleet and the values inherited by assignment and motion.
building | structural | object | Required for execution | Supplies building-wide defaults and rules.
corridors | structural | object | empty | Supplies graph nodes and edges.
departments | structural | department records | empty | Supplies service areas and operating calendars.
lifts | structural | lift records | empty | Defines cars and landings available to routes.
locations | structural | location records | Required for movement | Supplies endpoints, stations and resource places.
payloads | structural | payload records | Required for payload tasks | Defines the payload catalogue.
people_movements | structural | movement profiles | empty | Supplies background movement affecting corridor timing when enabled.
route_profiles | structural | named rule map | empty | Supplies permission overrides keyed by profile identifier.
simulation | structural | object | Runtime defaults | Supplies simulation horizon and execution controls.
tasks | structural | task records | empty | Supplies explicit demand alongside generators.
waste_streams | structural | waste stream records | empty | Supplies the stream catalogue for department waste generation.
""")
    add('simulation', 'Historical simulation configuration', 'simulator.py:Simulation.__init__ amr_simulation_inputs.py:resolved_simulation_settings', 'test_simulation_run_controls.*', 'Legacy stagger values follow the same numeric rules as the canonical field.', """
task_release_stagger_sec | alias | seconds | 0.25 | Fallback for generated_task_release_stagger_sec when the canonical key is absent.
""", precedence='The canonical generated_task_release_stagger_sec key wins when supplied.')
    add('corridors', 'All graph-based motion, plus geometric topology and human routing', 'simulator.py:Simulation._build_floor_graphs simulator.py:Simulation._shortest_people_path_same_floor', 'test_routing_contracts.* test_staff_route_geometry.*', 'Node names and edge endpoints resolve against graph names. Graph construction skips unresolved endpoints.', """
nodes | structural | node records | empty | Adds physical graph vertices.
nodes[].name | runtime | node identifier | Required | Joins an endpoint to the graph.
nodes[].floor | runtime | floor number | Required | Partitions the floor graph.
nodes[].x | runtime | metres | Required | Supplies horizontal edge length and position.
nodes[].y | runtime | metres | Required | Supplies vertical edge length and position.
edges | structural | edge records | empty | Adds edges between the named vertices.
edges[].from | runtime | node identifier | Required | Sets the source of a directed or two-way edge.
edges[].to | runtime | node identifier | Required | Sets the destination of a directed or two-way edge.
edges[].people_area_type | conditional | area kind | none | Determines whether and how people movement applies to the edge.
edges[].people_profile_ids | conditional | profile identifiers | empty | Selects movement profiles considered on the edge.
""")
    add('route_profiles', 'AMR and staff graph routing', 'simulator.py:Simulation._resolve_task_route_rules amr_routing_inputs.py:routing_input_findings', 'test_route_profiles.* test_routing_input_validation.*', 'Profile IDs and edge/node/lift references resolve against the configured graph.', """
* | structural | named object | No override | Supplies permissions for tasks selecting this profile.
""")
    add('locations[]', 'Layout editing, Playback and space reports', 'amr_location_inputs.py:location_outline_points amr_location_inputs.py:location_outline_metrics amr_location_inputs.py:location_input_findings', 'test_location_outlines.*', 'Each point requires a complete finite local or world coordinate pair. Reject overflow during coordinate conversion and metric calculations.', """
bounding_box | presentation | metres | empty | Supplies the location outline and area metrics for drawings and reports. The geometric engine uses explicit floor geometry and resolved local space shapes.
""", precedence='Complete local dx/dy pairs take precedence over legacy world x/y coordinates.')
    add('', 'Project asset materialisation and desktop view', 'amr_project.py:drawing_entries amr_project.py:Project.materialize', 'test_open_without_drawings.* test_pdf_underlay.*', 'Project Check handles missing, invalid or relocated asset references.', """
floor_dxf_files | presentation | asset references per floor | empty | Loads the CAD drawing underlay and contributes asset identity to frozen inputs.
floor_dxf_files[].filepath | presentation | file reference | Required for a drawing | Resolves a drawing using the project asset rules.
floor_dxf_files[].floor | presentation | floor number | Required for a drawing | Associates one underlay with its displayed floor.
floor_pdf_underlays | presentation | PDF asset references | empty | Supplies visual context for drawing authoring and review.
""")
    add('mass_collections', 'AMR inventory and third-party collections', 'simulator.py:Simulation._normalise_mass_collection_configs simulator.py:Simulation._schedule_mass_collection_events simulator.py:Simulation._handle_mass_collection_capacity_tick simulator.py:Simulation._execute_mass_collection_visit', 'test_payload_lifecycle.*', 'Accepts list or items wrapper; skips missing locations and sanitises names, times, thresholds and cadence.', """
 | structural | collection records | empty | Defines third-party visits for eligible locations.
[].id | runtime | identifier | MASS-COLLECTION-n | Identifies the configured visit series in events; name is a legacy fallback.
[].enabled | runtime | boolean | true | Gates visit scheduling.
[].location | runtime | location identifier | Required | Identifies the store to visit; store_location is a legacy fallback.
[].payloads | conditional | payload identifiers | All eligible payloads | Limits visit to matching full payloads; payload_names is a legacy fallback.
[].days_active | conditional | weekdays | All days | Limits checks and visits to configured weekdays; active_days is a legacy fallback.
[].scheduled_times | conditional | local HH:MM values | empty | Schedules timed visits; schedule_times is a legacy fallback.
[].capacity_trigger_count | conditional | payload count | 0 | Controls threshold-based visits and takes precedence over the fraction when positive.
[].capacity_trigger_fraction | conditional | fraction | 0 | Sets the occupancy threshold when no positive count is configured.
[].capacity_check_interval_minutes | conditional | minutes | 15 | Sets the cadence for threshold checks, minimum one minute.
[].replace_with_empty_equivalents | conditional | boolean | true | Controls replenishment of corresponding empty containers.
[].notes | presentation | text | empty | Carries author notes alongside the visit configuration.
""", precedence='Canonical values take precedence over aliases. A positive count takes precedence over fraction for threshold checks.')
    add('payloads[]', 'Generated tracked-item exchanges and human carrying estimates', 'amr_sim_task_generation.py:_payload_tracked_items amr_sim_task_generation.py:_apply_tracked_item_metadata amr_contingency_inputs.py:_service_inputs', 'test_generation_contracts.* test_human_generation_parity.*', 'Named entries must be objects. Exchange payload and source locations resolve in the catalogue and layout.', """
items | conditional | named item definitions | empty | Supplies tracked contents when tracking is enabled.
items.* | structural | item definition | No item | Associates exchange configuration with the named item.
items.*.exchange_payload | conditional | payload identifier | empty | Chooses the item exchange payload and makes it eligible in human carrying estimates.
items.*.source_location | conditional | location identifier | empty | Identifies the source used by tracked stock rules.
""")
    add('tasks[]', 'Explicit AMR jobs and human demand replay', 'amr_sim_models.py:Task simulator.py:Simulation.__init__ amr_sim_time_utils.py:parse_release_time', 'test_explicit_payload_identity.* test_generation_boundaries.*', 'Task construction requires id, pickup, dropoff and payload. Timestamp conversion requires clock-compatible datetimes.', """
id | runtime | task identifier | Required | Identifies the task in events, outcomes and returns.
pickup | runtime | location identifier | Required | Selects the collection location.
dropoff | runtime | location identifier | Required | Selects the destination subject to explicit dropoff-zone handling.
payload | runtime | payload identifier | Required | Determines carrying fit and inventory identity.
release_datetime | conditional | ISO datetime | Use release_time | Converts wall-clock release to elapsed seconds, floored at zero.
release_time | runtime | seconds | 0 | Schedules admission unless release_datetime is supplied. Releases after the horizon are omitted.
target_time | runtime | seconds | 0 | Supplies the task target used in deadline handling and evidence.
priority | runtime | priority number | 100 | Orders pending tasks by ascending priority, then release time and insertion order.
labels | runtime | text labels | empty | Carries evidence and service classification, including human demand grouping.
is_return_task | conditional | boolean | false | Identifies existing return work and affects return handling.
return_enabled | conditional | boolean | false | Allows a return task after delivery, including zone rules that can force it on.
return_payload | conditional | payload identifier | empty | Selects the payload for the return, falling back through task return rules.
waste_stream | runtime | stream identifier | empty | Supplies waste attribution and stream-specific handling.
""", precedence='release_datetime takes precedence over release_time. When both zone and final destination are set, the zone replaces the AMR dropoff and a staffed return is enabled.')
    add('tasks[]', 'Explicit payload identities and staged-stock recovery', 'simulator.py:Simulation._prepare_task_payload_instance amr_sim_models.py:Task', 'test_explicit_payload_identity.* test_staged_recovery.*', 'Recovery requires a literal boolean, payload type and explicit identity, with a matching recoverable record at pickup.', """
payload_instance_id | conditional | instance identifier | empty | Restricts the pickup to the named payload instance; ordinary source creation and normal allocation follow the inventory policy.
recover_staged_payload | conditional | boolean | false | Allows the named container to be collected from eligible failed-return staging under the recovery policy.
""")
    add('waste_streams[]', 'Department waste demand', 'amr_sim_task_generation.py:DepartmentWasteTaskGenerator.container_instance amr_sim_task_generation.py:DepartmentWasteTaskGenerator._create_task_record', 'test_department_waste_contracts.* test_waste_volume_balance.*', 'Stream and payload identifiers must resolve before a waste task can be released.', """
name | runtime | stream identifier | Required to match a department assignment | Joins the stream to department waste demand.
payload | runtime | payload identifier | Required for a runnable stream | Determines container type and carrying requirements.
""")
    _study_fields(add)
    _generation_fields(add)
    _geometry_fields(add)
    add('', 'Direct CLI failure export', 'simulator.py:_find_input_task_csv_path simulator.py:default_failed_tasks_csv_path', '', 'A candidate must be a string ending in .csv after trimming. This code does not load the referenced CSV.', """
task_csv | compatibility | filename | failed_tasks.csv beside the configuration when possible | Derives the name of the default failed-task CSV if an input-task filename is present.
""", precedence='Explicit failure export path takes precedence. The CSV naming helper searches top-level aliases before known nested sections and a guarded recursive fallback.')
    return fields


def _study_fields(add):
    add('human_contingency', 'Human contingency study', 'amr_contingency_inputs.py:initial_settings amr_contingency_inputs.py:default_settings amr_contingency_inputs.py:validate_settings', 'test_human_generation_parity.* test_contingency_performance.*', 'Version 1 requires a nonempty distinct service list, valid service profiles and confirmed shift rules.', """
 | structural | object | empty | Saves human-study settings and a study link.
settings | structural | object | Inferred from current configuration | Supplies the native demand services, resources and roster search settings.
settings.schema_version | conditional | version | 1 | Selects the current settings format.
settings.services | conditional | service identifiers | Active services derived from demand | Chooses the demand included in the study.
settings.buffer_percent | conditional | percent | 20 | Sets the uplift for buffered workload reporting.
settings.trial_budget | conditional | trial count | 200 | Caps roster search.
settings.seed | conditional | nonnegative integer | 0 | Seeds the roster search.
settings.max_round_tasks | conditional | task count | 8 | Caps task combinations in a single round; maximum 12.
settings.profiles | structural | named profiles | Derived per known service | Supplies service-specific routing and staffing.
settings.profiles.* | structural | profile object | Derived for the service | Selects the service's calculation settings.
settings.shifts | structural | roster rules | Derived from staffing | Supplies shared staffing and fallback rules for dedicated pools.
""")
    add('human_contingency.settings.profiles.*', 'Human contingency study', 'amr_contingency_inputs.py:default_settings amr_contingency_inputs.py:carrying_estimate amr_contingency_inputs.py:validate_settings amr_contingency_inputs.py:shift_rules', 'test_contingency_timing.* test_contingency_performance.*', 'Capacities and dimensions must be positive; handling and pickup/unload may be zero. References resolve against input resources.', """
base | conditional | location identifier | Most frequent source base | Sets the route origin and return point.
payloads | conditional | payload identifiers | Derived from demand and exchanges | Limits eligible loads.
capacity_count | conditional | integral count | 2 | Caps tasks carried together.
capacity_kg | conditional | kilograms | Max of 1 and count times heaviest payload | Limits mass per load.
length_m | conditional | metres | Count times longest payload plus 0.6 | Limits envelope length.
width_m | conditional | metres | Max of 0.6 and widest payload | Limits envelope width.
height_m | conditional | metres | Max of 1.8 and tallest payload | Limits envelope height.
operator_length_m | conditional | metres | 0.6 | Sets operator packing length.
operator_width_m | conditional | metres | 0.6 | Sets operator packing width.
operator_height_m | conditional | metres | 1.8 | Sets operator packing height.
empty_speed_mps | conditional | metres/second | Staff walking speed or 1.2 | Sets unloaded walking duration.
loaded_speed_mps | conditional | metres/second | Staff walking speed or 1.2 | Sets loaded walking duration.
pickup_seconds | conditional | seconds | Building load/unload time or 20 | Sets pickup duration.
unload_seconds | conditional | seconds | Building load/unload time or 20 | Sets unload duration.
handling_minutes | conditional | minutes | Category handling, then staff default, then 15 | Sets service handling duration.
route_profile | conditional | profile identifier | None | Overrides the route permissions for this service.
shift_rules | conditional | object | Use shared shift rules | Overlays allowed staffing fields for the dedicated pool.
release_policy | conditional | object | version 1, fixed, 120 minutes | Controls whether supported native releases can move to staff-aligned times.
release_policy.version | conditional | version | 1 | Selects the policy format.
release_policy.mode | conditional | mode | fixed | Preserves native release or enables staff alignment for eligible demand.
release_policy.max_delay_minutes | conditional | minutes | 120 | Bounds permitted release/deadline movement for eligible demand.
""", precedence='Saved fields overlay the inferred profile. Dedicated shift overrides overlay shared settings. Explicit and scheduled demand keep their native release.')
    add('human_contingency.settings.shifts', 'Human contingency study', 'amr_contingency_inputs.py:default_settings amr_contingency_inputs.py:validate_settings amr_contingency_inputs.py:shift_candidates', 'test_contingency_timing.*', 'Validate positive grid and headcount, eligible weekdays, valid periods at most 24 hours and a break ending before shift end.', """
lengths_hours | conditional | hours | Staff shift lengths or [8] | Gives feasible shift lengths when explicit periods are absent.
start_window | conditional | pair of HH:MM values | 00:00 through 23:45 | Bounds grid-based shift starts when explicit periods are absent.
days | conditional | weekdays | Staff pattern days or all days | Limits dates generating shift candidates.
periods | conditional | start/end intervals | empty | Replaces grid-based start/length choices when nonempty.
grid_minutes | conditional | minutes | 15 | Sets spacing between candidate shift starts.
break_minutes | conditional | minutes | 30 | Deducts time from usable staffed intervals.
break_after_hours | conditional | hours | Earlier of 4 and half the shortest default shift | Places the deduction relative to shift start.
max_people | conditional | count | 20 | Caps concurrent staff per pool.
shared_base | conditional | location identifier | Most frequent service base | Sets the shared team's route origin and return.
confirmed | conditional | boolean | false | Requires confirmation before a study can run.
""", precedence='Dedicated profile shift rules can override shared fields. Explicit periods take precedence over start_window and lengths_hours.')
    add('human_contingency', 'Human contingency workbench', 'visualiser/app.py:AMRGraphEditor.save_contingency_settings', 'test_human_contingency_ui.*', 'The saved study verifies its own inputs and results.', """
study_path | presentation | path | No saved study | Links to the last saved study document.
""")


def _generation_fields(add):
    add('task_generation', 'Generated AMR and human demand', 'amr_sim_task_generation.py:TaskGenerationManager._task_generation_cfg amr_sim_task_generation.py:DynamicCategoryTaskGenerator._build_instances amr_generation_inputs.py:generation_input_findings', 'test_generation_contracts.* test_generation_input_validation.*', 'Managed inputs validate generator shape and scoped values. Inactive rules may be retained for editing.', """
 | structural | generator settings | empty | Supplies configuration for the native demand generators.
categories | structural | named rule map | empty | Groups demand rules by service.
categories.* | structural | category object | No category | Supplies common work, timing and resource settings.
categories.*.departments | structural | named override map | empty | Selects overrides by department identity.
categories.*.departments.* | structural | override object | Inherit category | Overlays values for a single department.
categories.*.department_groups | structural | group records | empty | Selects overrides for groups of departments.
categories.*.department_groups[].id | runtime | group identifier | Use group fallback identity | Distinguishes groups and scopes their generated demand.
categories.*.department_groups[].payload | structural | override object | Inherit category | Overlays common task rules for the group.
department_waste | conditional | object | disabled | Enables the separate department-waste generator through its enabled field.
""")
    add('task_generation.categories.*', 'Generated logistics tasks', 'amr_sim_task_generation.py:DynamicCategoryTaskGenerator._append_department_instance amr_sim_task_generation.py:DynamicCategoryTaskGenerator._pickup_locations_from_cfg amr_sim_task_generation.py:DynamicCategoryTaskGenerator._dropoff_locations_from_cfg amr_sim_task_generation.py:DynamicCategoryTaskGenerator._base_task', 'test_generation_reference.* test_generation_provenance.*', 'Referenced locations, route profiles and payloads must resolve for valid tasks to be produced.', """
department_location_role | conditional | pickup or dropoff | dropoff | Selects which task endpoint to derive from the department associations.
pickup_location | conditional | location identifier | empty | Adds the first pickup candidate before pickup_locations.
pickup_locations | conditional | ordered location identifiers | empty | Adds pickup candidates after pickup_location, with duplicate removal.
dropoff_location | conditional | location identifier | empty | Adds the first delivery candidate before dropoff_locations.
dropoff_locations | conditional | ordered location identifiers | empty | Adds delivery candidates after dropoff_location, with duplicate removal.
payload | conditional | payload identifier | empty | Selects the load type of the generated task.
route_profile | conditional | profile identifier | None | Overrides route permissions for generated work.
target_time | conditional | seconds | 0 | Sets the generated task target.
waste_stream | conditional | stream identifier | empty | Supplies stream attribution in generated tasks.
release_next_after_return_pickup | conditional | boolean | false | Gates further demand in supported modes until the linked return is collected.
""")
    add('task_generation.categories.*', 'Generated AMR work using staffed staging zones', 'amr_sim_task_generation.py:DynamicCategoryTaskGenerator._merge_category_with_override amr_sim_task_generation.py:DynamicCategoryTaskGenerator._base_task simulator.py:Simulation._task_allows_dropoff_zone_overflow', 'test_generation_layers.* test_dropoff_zones.*', 'The generated zone task recognises wait_for_space and allow_temporary_overflow, with invalid or blank values resolved to the generator default.', """
dropoff_zone_capacity_policy | conditional | policy identifier | allow_temporary_overflow | Controls whether the robot waits for a compatible free staging slot when its department zone has reached capacity.
""", precedence='The category value takes precedence over a value at either override scope.')
    add('task_generation.categories.*', 'Scheduled and timeframe demand', 'amr_sim_task_generation.py:_scheduled_times_from_cfg amr_sim_task_generation.py:_timeframe_minutes_from_cfg amr_sim_task_generation.py:DynamicCategoryTaskGenerator._calculate_timeframe_instance_task_count', 'test_generation_boundaries.* test_hybrid_generation.*', 'Schedule values normalise to distinct valid times. A timeframe requires parseable start and end; the multiple is floored at 1.', """
schedule_times | alias | local HH:MM values | empty | Historical fallback for scheduled_times.
timeframe_start | conditional | local HH:MM | No active timeframe | Opens the release window.
timeframe_end | conditional | local HH:MM | No active timeframe | Closes the release window.
payload_multiple | alias | count | 1 | Fallback for timeframe_payload_multiple in timeframe workload counts.
timeframe_payload_multiple | conditional | count | payload_multiple or 1 | Repeats valid pickup/drop-off pairs for timeframe work.
""", precedence='scheduled_times outranks schedule_times when present. timeframe_payload_multiple outranks payload_multiple.')
    add('task_generation.categories.*', 'Staffed generated jobs', 'amr_sim_task_generation.py:_normalise_staff_weekly_hours amr_sim_task_generation.py:DynamicCategoryTaskGenerator._base_task amr_generation_inputs.py:generation_input_findings', 'test_generated_staff_hours.* test_staff_calendar_switches.*', 'Staff checkbox encodings and timing are validated or coerced by the generator; working hours are normalised over the seven supported weekdays.', """
staff_collection_delay_minutes | conditional | minutes | 0 | Delays staff collection after a hand-off.
staff_department_fallback_enabled | conditional | boolean | false | Enables the department staff fallback on applicable work.
staff_department_fallback_resource_name | conditional | staff resource name | Department team | Identifies the fallback resource.
staff_handoff_only | conditional | boolean | false | Marks jobs using hand-off only handling.
staff_use_custom_working_hours | conditional | boolean | false | Gates activation of the task-level weekly working hours.
staff_working_hours | conditional | weekday map | Disabled days | Defines available periods when custom hours are selected.
staff_working_hours.* | structural | weekday object | disabled, 09:00–17:00 | Holds one weekday slot.
staff_working_hours.*.enabled | conditional | boolean | false | Enables the selected weekday.
staff_working_hours.*.start_time | conditional | HH:MM | 09:00 | Opens the slot.
staff_working_hours.*.end_time | conditional | HH:MM | 17:00 | Closes the slot.
""")
    add('task_generation.categories.*', 'Editor labels and retained configuration', 'visualiser/models.py:default_task_generation_category amr_sim_task_generation.py:DynamicCategoryTaskGenerator._merge_category_with_override amr_sim_task_generation.py:DynamicCategoryTaskGenerator._base_task', '', 'Saved fields may be carried through configuration and provenance. No matching runtime calculation was found for retired reserve fields.', """
display_name | presentation | text | Editor category label | Names the category in the workbench.
notes | presentation | text | empty | Retains author notes and generator input provenance.
flow_direction | compatibility | direction label | No runtime value | Endpoint rules determine direction.
reserve_management | compatibility | boolean | No runtime value | Generator inventory behaviour uses its active stock and tracking fields.
reserve_max_source | compatibility | source label | No runtime value | The generator does not read this historical stock setting.
reserve_initial_fill_fraction | compatibility | fraction | No runtime value | The generator reads its active initial inventory and tracked-stock inputs.
reserve_trigger_fraction | compatibility | fraction | No runtime value | The active threshold rule reads its own mode configuration.
replenish_to_fraction | compatibility | fraction | No runtime value | No active reader uses this historical setting.
uses_department_waste_streams | presentation | boolean | Category-specific editor value | The editor retains it; the separate runtime waste generator is enabled by department_waste.enabled.
reusable_return_pool_enabled | defective | boolean | Generator does not propagate the value | Exposed setting has no operational effect through generated Task construction.
reusable_return_pool_multiplier | defective | multiplier | Editor default 2 | Exposed setting has no runtime receiver for sizing the reusable return pool.
reusable_return_pool_max | defective | count | Editor default 0 | Exposed setting has no runtime receiver for capping the reusable return pool.
""")
    add('task_generation.staff_config', 'Generated staff work and human-study defaults', 'amr_sim_task_generation.py:_normalise_global_staff_config amr_contingency_inputs.py:default_settings', 'test_generated_staff_hours.* test_staff_shift_boundaries.*', 'Canonical staff_config takes precedence over staff. Valid roster defaults may be supplemented by named patterns.', """
 | structural | object | Normalised staff defaults | Supplies staffing defaults and roster patterns.
shift_patterns | structural | named pattern map | Built-in patterns | Supplies recurring attendance patterns.
shift_patterns.* | structural | pattern object | Named defaults where applicable | Carries timing and rotation days for the selected pattern.
shift_patterns.*.display_name | presentation | text | Pattern label | Names the pattern in the workbench.
""")


def _geometry_fields(add):
    add('geometry', 'Detailed and legacy geometric compatibility', 'amr_geometric_routing.py:geometry_input_findings amr_geometric_occupancy.py:area_input_findings amr_clearances.py:resolved_clearances', 'test_mode_simulation_acceptance.* test_occupancy_simulation.*', 'Version 1 requires floors with unique integer IDs and finite ordered rectangles. Drawn areas need unique IDs and must lie within the floor bounds.', """
 | structural | object | Required in geometric motion | Supplies machine-readable physical space, independently of underlays.
schema_version | conditional | version | Required, 1 | Selects the physical-space model format.
traffic_model | conditional | policy identifier | whole_route_v1 in legacy geometric compatibility | Chooses whole-route claims or Detailed keep-right traffic.
floors | structural | floor records | Required and nonempty | Supplies per-floor geometry.
floors[].floor | runtime | floor number | Required | Joins physical geometry to graph floors.
floors[].bounds | runtime | metre rectangle | Required | Defines the permissible floor envelope.
floors[].obstacles | runtime | metre rectangles | Required, including explicit empty list | Supplies exclusion shapes used in clearance.
floors[].no_queuing_areas | conditional | area records | empty | Defines explicit regions where stopped poses cannot queue.
floors[].no_queuing_areas[].id | conditional | area identifier | Required | Names a drawn region.
floors[].no_queuing_areas[].bounds | conditional | metre rectangle | Required | Defines the region checked for stopping.
floors[].passing_places | conditional | area records | empty | Defines drawn places for route conflict resolution.
floors[].passing_places[].id | conditional | area identifier | Required | Names a passing place.
floors[].passing_places[].bounds | conditional | metre rectangle | Required | Defines the passing place envelope.
""")
    add('geometry.clearances', 'Detailed and legacy geometric compatibility', 'amr_clearances.py:clearance_input_findings amr_clearances.py:resolved_clearances', 'test_mode_simulation_acceptance.*', 'Clearances must be finite and nonnegative. A supplied project block requires both values.', """
 | structural | object | Resolve robot values or legacy margin | Supplies project-wide clearance defaults.
wall_m | conditional | metres | Legacy robot margin if available | Sets wall separation when no robot-specific value exists.
robot_m | conditional | metres | Twice the legacy robot margin if available | Sets the total separation requirement when no robot-specific value exists.
""", precedence='Robot override, then project default, then legacy margin. Pairwise clearance uses the larger total gap.')
    add('geometry', 'Initial poses in Detailed and legacy geometric compatibility', 'amr_initial_placements.py:initial_placement_findings amr_initial_placements.py:resolve_initial_placements', 'test_initial_placements.*', 'Each robot instance needs one valid service location and a finite heading. Reject overlaps, blocked locations and footprints outside the floor.', """
initial_placements | conditional | pose records | Single robot can inherit its first charger and configured heading | Supplies each robot's initial parked occupied footprint.
initial_placements[].amr_id | conditional | expanded robot instance ID | Required | Binds the pose to one fleet instance.
initial_placements[].location | conditional | named location | Required | Chooses pose position and floor.
initial_placements[].heading_deg | conditional | degrees | Required | Rotates the footprint at parking and starts trajectory planning.
""")
    add('scenario_testing', 'Managed and direct scenario runs', 'amr_scenario_inputs.py:scenario_input_findings simulator.py:Simulation.__init__ simulator.py:Simulation._scenario_window simulator.py:Simulation._scenario_event_state', 'test_scenario_recovery.* test_scenario_study.*', 'Dated pairs must be chronological with compatible offsets. Availability is finite 0–100 and speed factor finite 0–1.', """
 | structural | object | empty | Holds scenario definitions and separate stress-study settings.
enabled | runtime | boolean | false | Enables selection of a named scenario.
active_scenario | conditional | scenario name | Normal operation | Selects the matching definition when enabled.
enhanced_logging | runtime | boolean | false | Controls additional scenario logging.
scenarios | structural | scenario list | empty | Supplies definitions available by name.
scenarios[].name | runtime | scenario name | Required to select | Matches the active scenario.
scenarios[].events | structural | event list | empty | Supplies resource overrides for the selected scenario.
scenarios[].events[].availability_percent | conditional | percent | 100 | Scales resource availability in its active window.
scenarios[].events[].speed_factor | conditional | fraction | 1 | Modifies resource movement speed during its active window.
scenarios[].events[].resource_type | conditional | resource type | No matching resource | Selects AMR, lift, corridor or other supported resource type.
scenarios[].events[].resource_ids | conditional | resource identifiers | empty | Scopes the override to the configured resources.
scenarios[].events[].days_active | conditional | weekdays | All days | Restricts recurring windows.
scenarios[].events[].start_time | conditional | HH:MM | Midnight | Starts a recurring override.
scenarios[].events[].end_time | conditional | HH:MM | End of day | Ends a recurring override, including overnight intervals.
scenarios[].events[].start_datetime | conditional | ISO datetime | No dated window | Starts a dated override and takes precedence over weekday recurrence.
scenarios[].events[].end_datetime | conditional | ISO datetime | No dated window | Ends a dated override and is required with start_datetime.
""")
    add('scenario_testing.stress_test', 'Stress combinations and AMR speed sweep', 'amr_scenario_study.py:default_settings amr_scenario_study.py:validated_settings amr_scenario_study.py:domain amr_scenario_study.py:candidate_events', 'test_scenario_study.* test_amr_speed_sweep.*', 'Duration and percentages are finite and deduplicated. Asset pairs must resolve. Search offsets are bounded by the simulation horizon.', """
 | structural | object | Inferred from project | Stores study parameters separate from the selected run scenario.
test_mode | conditional | study mode | combinations | Chooses combinations or the all-AMR speed sweep.
data_mode | conditional | data mode | full | Chooses full or reduced trial evidence.
assets | conditional | resource-kind and identity pairs | All eligible resources | Sets the candidate domain.
durations_minutes | conditional | minutes | 15, 30, 60 and horizon, bounded and deduplicated | Sets override durations.
start_minute | conditional | minutes from start | 0 | Sets first eligible start.
end_minute | conditional | minutes from start | Horizon | Bounds the last eligible interval.
start_step_minutes | conditional | minutes | 60 | Spaces candidate starts.
availability_percent | conditional | percentages | [0, 100] | Sets candidate availability levels.
speed_percent | conditional | percentages | [25, 50, 75, 100] | Sets candidate speed levels.
max_events | conditional | count | 2 | Caps concurrent changes in a candidate; maximum 8.
trial_budget | conditional | count | 100 | Caps search at a positive value up to 100000.
seed | conditional | nonnegative integer | 0 | Seeds candidate selection when the domain exceeds the budget.
workers | conditional | count | 8 | Requests one to 32 CPU workers.
ram_limit_gib | conditional | GiB | 16 | Bounds the study scheduling memory limit.
reserve_ram_gib | conditional | GiB | 8 | Reserves memory from worker admission.
corridor_sweep_scope | conditional | selected or all | selected | Controls the separate individual blockage sweep.
""")
    add('scenario_testing.stress_test', 'Stress study workbench', 'visualiser/app.py:AMRGraphEditor.save_stress_settings', 'test_scenario_stress_ui.*', 'The saved study verifies its own inputs and results.', """
study_path | presentation | path | No saved study | Links to the last saved study document.
""")
