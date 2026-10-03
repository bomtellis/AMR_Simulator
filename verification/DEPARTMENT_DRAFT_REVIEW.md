# Shared provisional locations and stale department drafts — slice 2AL

## Corrected behaviour

A provisional location can be shared by multiple department drafts before the
Departments list is saved. Deleting its originating draft now transfers the one
pending creation record to a surviving department that effectively references it.
The supplied name, coordinates and floor are preserved. Further deletion transfers
it again if needed; the eventual save creates the point exactly once. If no
surviving department uses it, the provisional point is discarded and removed from
the available-location choices. Shadowed legacy aliases do not keep a point alive.
Conflicting pending positions with the same name reject deletion without changing
the drafts. Existing project locations are never deleted by this operation.

Department dialogs now capture their owning project and parent department-list
state when opened. Accept/Save checks that those states still match. A changed
project, a replacement project store (even with identical contents), or a changed
parent list causes a visible error instead of overwriting newer work. The dialog
and pending input remain available; cancel and reopen to edit the current data.
Child seeds are independent copies. Ordinary placement and selection changes
within the child do not modify its owners and therefore do not invalidate it.

## Acceptance evidence

The initial seven tests reproduce six failures against `5f75b25`; see
`latest/department-drafts-before.txt`. Ten new tests cover shared zone/service
references, unused points, explicit empty alias precedence, multiple survivors,
repeated owner deletion, conflicting placements, stale project/list state,
replacement-project identity and retained draft input. The focused run passes
83 tests, including department contracts, placement undo/cancellation and nine
evidence-schema checks: `latest/department-drafts-focused.txt`.

The full pack passes **1,336/1,336 tests** in **141.099 seconds**, with zero broken
evidence links and unchanged source during testing. See `latest/tests.txt`,
`latest/evidence.json` and `latest/department-drafts-pack-build.txt`.

Two 60-minute demand-window LTN smoke runs each complete four tasks, with zero
failed/pending tasks and final simulation time 7928.480894138804 seconds (assigned
work drains beyond the demand window). Initialization takes 1.373653 / 1.426335
seconds; total runtime 1.733969 / 1.784558 seconds. Both retain outcome hash
`5368460ed4fd5fd466e832b82d3d6358977abfaccbb456d45e268cfb7c0ab474`, unchanged
from the prior checkpoint. Source/input remain unchanged. See
`latest/department-drafts-ltn/smoke.json`. This is repeatability/regression evidence,
not independent numerical validation of LTN.

## User verification

1. Add a provisional department and place a drop-off zone from its editor.
   Accept the child editor without saving the Departments list.
2. Edit another department and select that zone. Accept, then delete the new
   originating department draft. Save the list: the shared zone should exist once
   and remain assigned to the surviving department.
3. Repeat without assigning the point elsewhere. Deleting its originating draft
   should remove it from the available-location choices and Save should not create
   it. Cancelling the list should leave the project unchanged in either case.
4. Existing referenced departments retain their deletion protection: remove demand
   or task assignments before deleting them. Undo/redo applies to the complete
   accepted list change as established in slice 2AK.

Stale-state cases are exercised through controlled state changes in automated Qt
tests; the normal modal workflow may prevent those changes through ordinary clicks.

## Scope and next checkpoint

This closes the shared provisional-owner and stale department-dialog cases left
open by slice 2AK. It does not implement general merge/conflict resolution for all
application dialogs, provisional canvas overlays or the final CAD interaction
design. Drafts remain local to the open modal workflow; recovery of unaccepted
modal inputs is not claimed. Core configuration/report acceptance, workspace gates,
geometry, approved UI, tutorial and final release validation remain open.

Next: continue the department waste-stream and task-generation option audit, with
independent expected demand and explicit option dispositions, then the remaining
correctness workspace gaps.
