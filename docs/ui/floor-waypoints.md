# Mandatory floor waypoints

AMR Simulator, existing Windows/PySide6 application. This change adds a routing
policy requested for the copied LTN project. It uses the existing Building settings
dialog and `manage_building_settings` controller, including save, undo/redo, run
editing locks and project revision history. The drawing and workspace layout are
unchanged. Native table fields follow the existing application theme.

## Configure the rule

Open **Configuration → Building settings → Mandatory floor waypoints**.
Add a row with From floor **0**, Destination floors **1, 2, 3, 4, 5**, and Via floor
**2**, then Save and save the project. Remove the row to remove the policy.

The copied `ltn-via-floor-2.amrproj` has this rule applied. `ltn.amrproj` is retained.
The persisted configuration is:

```json
"building": {
  "mandatory_floor_waypoints": [
    {"from_floor": 0, "to_floors": [1, 2, 3, 4, 5], "via_floor": 2}
  ]
}
```

This is an actual lift stop, with the existing boarding and alighting times.
Passing floor 2 inside a lift without stopping does not satisfy the rule.
Floor-2 destinations finish there; floor-1 destinations go 0 → 2 → 1.
The policy applies to all cross-floor AMR movements matching the row, including
empty approach, charging and idle return. It does not govern staff walking or
independent people movement. Other origins and same-floor movement are unchanged.

## Connecting lift trips

If a direct lift route is unavailable under the effective profile, the simulator
can search for a connecting route using multiple lift journeys. A waypoint rule
also requires a connecting plan even if a direct route exists. The AMR can use
the same lift again, or travel through a permitted corridor to another lift.
All legs retain permitted nodes, directional edges, lifts, width and payload
capacity checks. An unavailable required waypoint blocks the journey rather
than allowing a direct bypass. Lift stops remain boarding/alighting endpoints;
cyclic lift excursions do not substitute for missing corridor connections.

The planner preserves existing direct routes when no waypoint is required.
Connecting estimates use private overlays for previous lift bookings, car floor,
wear and deterministic repair, without changing shared reservations. Committed
rides use the existing reservation transaction and each ride records its lift
energy, waiting, repositioning and transfer segments. Project navigation checks
recognise the same connections and waypoint requirement. Input checks reject
unknown floors, overlapping rules, duplicate destinations and invalid values.

## Verification and rollback

Tests cover floor 1–5, actual task completion, two different lifts, blocked
permissions, unreachable waypoints, read-only estimates, simultaneous robots,
repair between rides, energy/timing reconciliation, batching, charging, dialog
save/cancel, undo/redo and project reopen. Existing routing, lift scheduling,
charging, project checks and geometric-motion cases are also included.

254 targeted checks passed. One existing charging selection test was separately
confirmed to fail in the unchanged application and excluded from this passing
set: `test_selecting_a_charge_request_does_not_spend_or_reserve` in
`test_required_charge_dispatch.py` (an existing task deferral timeout event).
The LTN audit covered 468 route definitions with zero newly blocked routes and
no input errors. Representative original-LTN routes to all five floors confirmed
the floor-2 stop. This is not a full seven-day LTN capacity simulation.

The settings dialog was checked at the existing desktop density. Additional
display scaling and screen-reader certification are outside this bounded change.
No new background job, renderer, deployment setting or dependency is introduced.

A dated backup in `verification/floor-waypoints-20261020/` preserves the replaced
source files and the copied project before its policy revision. Restore those
files together to roll back the application change; the original LTN project
also remains available.
