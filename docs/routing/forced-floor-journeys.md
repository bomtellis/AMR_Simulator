# Force every AMR journey via a floor

Implemented 9 November 2026. Restart AMR Simulator, open **Building settings**, check **Force every AMR journey via a floor**, select the **Required floor**, then Save. The selector initially shows Level 2 when that floor exists.

The toggle is off by default and was left off in the current LTN project. Opening or saving an unchanged existing project does not add or enable it. Turning it off restores the existing routing settings, including any existing per-route mandatory waypoints; it does not remove those rules.

## Behaviour

Every actual location-to-location AMR journey must stop and exit on the selected floor. This includes deliveries, returns, empty approaches, batch legs, charging travel and parking/idle returns. A same-floor journey elsewhere goes to the required floor and returns. Starting on the required floor already satisfies the visit, and a journey ending there finishes there. Journeys staying on the required floor use its local corridors. Stationary actions and local bay/loading manoeuvres do not create additional journeys.

Journeys can use multiple lifts before and after the required stop and can revisit floors, including the starting or destination floor. The final lift is selected by the shortest permitted destination-floor corridor route to the actual endpoint. It must be reachable through suitable permitted connections and fit the AMR/load. Busy selected lifts remain eligible. Equally near reachable final lifts are compared by complete journey finish time, then lift ID.

For a sole nearest reachable car, a fully validated direct-to-required-floor/onward route is used where available. Additional connections are searched when needed. The search does not enumerate extra detours once a valid route to the sole nearest car has been established. Time comparison searches remain enabled for equal-distance cars.

While enabled, the ordinary conditional-transfer and destination-side boarding-floor controls are disabled but their saved values are retained. Existing explicit waypoint rules must use the same selected floor; conflicting rules prevent enabling until corrected. An impossible required route is reported as blocked and is never silently bypassed. Lift-car repositioning continues to follow the physical bookings.

Entry/exit timing, connector edges, permissions, reservations, rollback, energy accounting and cancellation remain integrated. Saved lift segments identify the required floor, whether it has been visited and the lift-selection reason. Third-party lift exports use the resulting physical movement evidence.

## Stored configuration and compatibility

`building.force_via_floor_enabled` is a boolean, default false. `building.force_via_floor` is an existing whole floor number, required when enabled. Disabling remembers the selected floor. Save/Cancel, Undo/Redo and project save/reopen are supported. No archive migration is needed. The existing geometric-motion restriction on projects containing lifts remains in force.

The opt-in route search is separate from normal routing. Its cache keys include the enabled policy, required floor and exact endpoint. Corridor queries are reused only inside a read-only search. Landing-and-visit-phase states allow floor revisits, and resource labels retain private car positions, availability, health and repair state. Reliability counters are omitted from equivalent-state comparisons only when a conservative path-length bound proves that no private route can trigger a failure. No reservations are committed by estimates.

## Validation on the current LTN project

The seven-day toggle-off run exactly matches the application before this feature: **4,944 completed tasks, zero failures, 231,099 events**, and identical full-precision hashes for task records, AMRs/energy, lifts, all reservations, inventory and pending work. Only per-run UUIDs were normalised. Original project settings were not changed.

With forced floor 2 enabled, the seven-day run finished in approximately **170 seconds** plus initialisation: **4,424 completed tasks, three task failures, 241,862 events**. Its results intentionally differ from normal operation. All **7,384 checked completed-task movement legs**, including **1,105 same-floor detours**, satisfied the required floor visit. An independent check of **18,863 physical lift movements** found no overlapping bookings or floor discontinuities (2 ms tolerance for displayed event times).

| Recorded outcome | Toggle off | Forced floor 2 |
|---|---:|---:|
| Lift transfers | 6,977 | 11,235 |
| Empty lift reposition movements | 4,022 | 7,628 |
| Average planned lift busy share within seven-day horizon | 4.94% | 7.87% |
| AMR waiting for lifts, total hours | 66.37 | 608.36 |
| Corridor travel, total km | 1,122.79 | 1,198.44 |

Busy share sums recorded service and reposition durations clipped to the configured seven-day horizon across all eight lifts. It describes planned movements, not a physical lift capacity certification. Other totals include work finishing after the horizon. Timing-dependent releases/returns change with the extra travel, so completion counts are outcomes of this dynamic workload rather than a fixed-demand throughput comparison.

All three enabled-run failures were the configured **60-minute deferral limit** while a **Clinical Waste Bin was unavailable at D14-WASTE**. They were not blocked routes. The new policy increases lift use and waiting; no user capacity, battery, timeout or scheduling settings were changed to compensate.

The affected regression suite passed **378 checks**. Two further new checks passed for projected wear/repairs and same-floor preflight consistency. All **28 new feature checks** pass, including multi-lift/floor revisits, actual stops, nearest/equal-distance/busy lifts, endpoint-specific choices, permissions, widths/load fit, graph timing, energy, reservation rollback, cancellation, invalid/conflicting inputs and settings lifecycle. The final focused routing/UI suite passed 68 checks. The dialog was visually inspected in both toggle states.

Machine-readable results and saved pre-feature implementations are under `verification/force-floor-20261109/`. Full traces, comparison snapshots and installation rollback copies remain in the Codex workspace under `force-floor-work/`. Synced project sources and existing user run folders were not edited.
