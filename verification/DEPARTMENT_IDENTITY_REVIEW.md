# Department identity and reference editing — slice 2AJ

## Corrected behaviour

Canvas editing now replaces the department originally opened, even when its ID
changes. Previously an edit from `D` to `New` called an upsert by the new ID,
leaving both records and leaving generation attached to `D`. Replacement now
remaps category override keys, group membership and static-task `department_id`
fields in one candidate before committing it. It does not rename physical graph
nodes or routes when a department label changes.

The independent demand reference still produces exactly **one task at 60 seconds**,
with group priority **7**, attributed to the renamed department. Group precedence
over a priority-22 ordinary override is retained. Conflicting override destinations
reject instead of overwriting settings. A deletion that would orphan an existing
department assignment or static-task reference is rejected; remove those
assignments first. Unreferenced deletion preserves graph locations and other data.

Department list edits copy nested records, so modifying a nested location selection
and cancelling no longer mutates project data. Successive ID edits `D → E → F`
retain the original-to-final mapping `D → F`. Canvas rename is one undo/redo action.
Canvas generated-location work in the final commit callback is restored if that
callback fails validation. Separately initiated placement while a modal dialog is
open remains a distinct operation needing further transaction review.

Department movement retains supplied coordinate precision instead of rounding to
millimetres. An invalid move cannot change either coordinate. Department labels
cannot overwrite graph points in `all_points`; existing label collisions remain
editable for repair but block managed Project Checks. Canvas creation/editing
rejects graph-label conflicts directly.

## Identity and input contract

The effective identity is the nonblank `id`, otherwise `name`. Dynamic and legacy
waste generators now use the same fallback. A name-only legacy reference produces
the expected three 0.2 m³ collections from 0.6 m³ accrued demand instead of being
silently skipped. Missing/blank IDs with valid names also pass identity checks.
Records with neither identity remain editable drafts but cannot run.

Explicit IDs/names must be strings without surrounding whitespace. Nonblank
effective identities and department display names must be unique. Coordinates
must be finite nonboolean numbers; floors must be whole. Defaults for missing
marker coordinates/floor remain zero. Group members must be nonblank unique
strings in a list; different groups can still model separate services for one
department. An unknown group/override department is an acknowledgeable warning
explaining that the assignment generates no department work, rather than silently
appearing valid.

Department marker coordinates are not service destinations. Explicit linked
locations still determine routing. These changes do not remap arbitrary metadata,
external configuration files or immutable saved-run evidence.

## Evidence

Reproductions executed against baseline `adad287` model/dialog code are saved
in `latest/department-identity-before.txt`: two departments instead of one after
an ID edit; group still referencing `D`; x=1.235 instead of 1.23456789; nested
project data changed after cancellation. The reproduction script reads prior Git
source without reverting the worktree.

Fifteen new tests cover identities, reference preservation, one-task demand,
deletion protection, collision rejection, position precision, fallback generation,
incomplete drafts, list cancellation and canvas undo/redo. The focused suites pass
**142 tests**; all **nine evidence checks** pass. See
`latest/department-identity-focused.txt` and
`latest/department-identity-evidence-check.txt`. The first full pack passed 1,310
of 1,311 tests, rejecting a waste-conservation fixture that copied a department
name along with its model inputs. The second department now has a distinct label;
the original 0.6 m³ accrued / 0.5 m³ pending / 0.1 m³ residual assertions are
unchanged. See `latest/department-identity-first-pack-tests.txt` and
`latest/department-identity-volume-check.txt`. The final full pack passed
**1,311 / 1,311 tests in 138.177 seconds**, with **zero broken evidence links**
and unchanged source hashes during testing. See `latest/tests.txt`,
`latest/department-identity-pack-build.txt` and `latest/evidence.json`.

Both 60-minute LTN demand-window runs completed four tasks, zero failed/pending,
with initialisation times 1.340 and 1.422 seconds and total times 1.696 and 1.778
seconds. Both retained outcome hash
`5368460ed4fd5fd466e832b82d3d6358977abfaccbb456d45e268cfb7c0ab474`.
See `latest/department-identity-ltn/smoke.json`. This bounded check does not establish
full LTN acceptance or a performance threshold.

## User verification

1. In a project copy, edit a department used by a generation group. Change its ID
   and name. Confirm one department remains and the group's membership follows it.
   Preview its demand, then undo and redo the edit.
2. Open Departments, alter a nested category/location selection and cancel.
   Confirm the stored selection remains unchanged. Save successive ID changes
   and confirm the original demand rule follows the final ID.
3. Try deleting a referenced department or renaming into an existing override key.
   Confirm the edit is rejected without losing data.
4. Add an unknown department assignment to a disposable project copy and run
   Project Checks. Confirm the no-work warning identifies its exact setting.

## Remaining scope

Complete category-location references and aliases, generated-location placement
transactions, modal staleness and wider deletion/rename coverage remain open.
Managed preflight blocks colliding graph labels; legacy draft loading preserves
them for correction. Shared display-name uniqueness is an editor constraint;
external consumers using duplicate labels must disambiguate them before import.
The full department/workspace gates and demand/event/report reconciliation are
not complete. Keep geometry, the approved graph-focused CAD UI, tutorial and
release work in their planned sequence. The unrelated `ltn.json` edit is excluded.
