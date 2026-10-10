# Department location contracts and provisional placement — slice 2AK

Combined workflow update (4 October 2026): a department child editor now states
that newly placed service locations and zones remain provisional until the
Departments list is saved, and that one Undo removes the accepted edit together.
An application-level check places both kinds of point, saves the parent list,
undoes/redoes once, saves a `.amrproj`, then reopens it in the editor. The
service and zone assignments, coordinates and unlisted category metadata remain
available. The archive preserves the exact saved department record; editor
import adds canonical fields to legacy category entries without losing their
effective selections. Forty-nine focused location/draft/storage tests pass.

## Behaviour and independent expectations

Department category location assignments now use the same resolution in raw
simulation, JSON import, editing and report attribution. The modern service key
`pickup_dropoff_locations` takes precedence over `locations`; the modern zone key
`dropoff_zone_locations` takes precedence over `drop_off_zone_locations`. Explicit
empty modern lists override populated aliases. A scalar means one whole location
name, including commas; a category scalar/list is legacy service shorthand.
Whitespace is trimmed and duplicates removed in first-seen order.

The small reference generates exactly one task at 60 seconds. Assigning `Ward Bay`
routes delivery there before and after editor import. Adding `Zone X` produces an
AMR leg ending at that zone and retains `Ward Bay` as the final staff destination.
An empty service override retains the category destination `B`: it does not disable
the category. Reports attribute the same service location and identify the same
zone. Missing effective location references block managed Project Checks, with a
path to the assignment; shadowed aliases do not create effective references.
Malformed values reject import and runtime without mutating the input.

Deleting a reference or explicitly clearing a selection no longer combines it
with old alias values. Visible category metadata and unlisted categories survive
dialog acceptance. Opening a legacy waste department no longer silently derives
modern destinations from old waste pickup/dropoff fields.

## Editing transaction

Clicking to place a department service point or drop-off zone now records a
provisional position in the child dialog. The project and parent list remain
unchanged. Child OK transfers the draft to the list; reopening retains its pending
locations. Cancel at either level leaves project data unchanged. Save validates
all department changes and pending locations in an isolated candidate, then commits
them together. A failed Save retains the draft for correction. One undo/redo
restores/reapplies the accepted department and locations together.

Generated names cannot collide with existing or proposed locations, corridor nodes,
lift stops or department labels. Coordinates must be finite nonboolean values and
floors whole numbers. No coordinate rounding occurs in this placement path. Pending
creation metadata is removed from committed departments. Generated points still
need graph connections and any required capacity settings.

## Evidence

The original eight contract tests reproduced 13 failing assertions and five errors
in `latest/department-locations-before.txt`. The transaction reproduction records
four failures in `latest/department-locations-transaction-before.txt`: an invalid
pending location could be saved, removed references reappeared, and graphical
placement mutated the project before acceptance.

Fifteen new tests cover aliases, scalar names, empty precedence, reference checks,
report attribution, rename/deletion, malformed inputs, provisional location
validation, nested dialog cancellation, retry, reopening and one-step undo/redo.
The focused run passes 90 tests, including nine verification-evidence checks, in
`latest/department-locations-focused.txt`. The final pack passes **1,326/1,326**
tests in **139.772 seconds**, with zero broken evidence links and unchanged source
during testing. See `latest/tests.txt`, `latest/evidence.json` and
`latest/department-locations-pack-build.txt`. The option audit retains 285
unreviewed observed paths; this is not a feature count or completion percentage.

Two LTN smoke runs use a 60-minute demand window and both complete four tasks with
zero failed or pending tasks. Initialization takes 1.373739 / 1.459181 seconds and
total runtime 1.730150 / 1.815354 seconds. Both finish at simulation time
7928.480894138804 seconds because assigned work drains beyond the demand horizon.
Both retain outcome hash
`5368460ed4fd5fd466e832b82d3d6358977abfaccbb456d45e268cfb7c0ab474`, matching
the previous checkpoint. Source and input remain unchanged. See
`latest/department-locations-ltn/smoke.json`. This is repeatability/regression
evidence, not independent numerical validation of LTN.

## User verification

1. Open Departments, edit an existing department and clear its selected service
   location. Accept and Save; reopen and confirm it stays cleared.
2. Place a new service location on the graph from the department editor. Cancel
   the department, then the list. Confirm no point or assignment was added.
3. Repeat and accept the child editor. Reopen it before list Save: the provisional
   assignment should remain. Save the list and confirm the point appears.
4. Undo once: the point and department assignment should disappear together.
   Redo once: both should return. Repeat with a drop-off zone.
5. Run Project Checks before simulation. A missing effective destination should
   identify the department assignment requiring correction.

## Limits and next work

This is not complete department/workspace or report reconciliation acceptance.
Raw simulation enforces assignment shapes; missing-reference blocking belongs to
managed preflight. Unknown category assignments can remain unused. Legacy waste
fields retain their separate semantics. Sharing provisional points across owners,
deleting their originating draft and general stale modal edits require further
review. Provisional positions are not yet drawn as a persistent canvas overlay.
The supported dialog path reports their provisional status and retains selections.

Follow-up: [slice 2AL](DEPARTMENT_DRAFT_REVIEW.md) closes shared provisional-owner
deletion and stale department-dialog acceptance with additional tests. Other modal
workflows and provisional canvas overlays remain outside these checkpoints.

Continue the remaining configuration audit and workspace gaps, retaining full
report event-coverage/stock reconciliation, calendar/staffing and mixed-stock
limitations. Geometry, approved CAD UI, tutorial and final release gates remain
in their planned order.
