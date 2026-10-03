# Preserve department waste-stream overrides — slice 2AM

## Corrected behaviour

Opening and accepting a department used to materialise threshold mode, zero rates,
empty schedules and boolean defaults for every selected waste stream. This changed
inherited demand without a user edit. It also discarded payload/capacity overrides,
legacy shared-bin IDs and extension metadata. Normalisation now retains sparse
stream settings and copies nested data; a bare stream name becomes a name-only
object with the same inherited meaning.

The nested stream editor now shows absent settings as inherited. Blank numeric
inputs remove that override; explicit zero remains a zero override. Generation
mode has separate Inherit and Default (scheduled) choices. Clear schedule stores
an explicit empty list; Inherit schedule removes the override. Partially checked
initial/shared-container boxes inherit their effective values. Those two controls,
previously constructed but omitted from the form, are now visible. Existing payload,
capacity, fraction, shared-ID aliases and custom metadata survive editing.

Bulk editing now applies only fields the user edits. Unchanged checked streams no
longer copy the first department's rates over all others. New assignments inherit
unless explicit overrides are supplied. Clearing an edited numeric field or
selecting Inherit mode removes only that override from each selected stream. Fields
and streams outside the patch remain intact. Invalid numeric values are rejected
before an edit result is returned. Blank/non-string stream names and duplicate
assignments to the same department now reject import, preflight and runtime rather
than silently selecting/skipping entries.

## Independent demand references

The reference uses 24 m³/day continuous waste, a 0.5 m³ container and an 80% fill
threshold. One hour adds **1 m³**; each collection is **0.4 m³**, so there are **two
collections totalling 0.8 m³**, with the remaining 0.2 m³ below threshold. This
result is unchanged by department acceptance, nested stream acceptance and JSON
normalisation. Previously opening the department could replace 24 with zero and
produce no collections.

A department capacity override of 2 m³ at 50% gives a 1 m³ threshold and **one
collection**. An explicit daily-rate edit from 24 to 48 m³ gives **five 0.4 m³
collections** in an hour. Removing that rate override restores the two-collection
reference. A scheduled override at 00:30 produces **one 0.4 m³ task**; an explicit
empty schedule produces none even if the category has a clock time. Removing mode
and schedule overrides restores threshold inheritance.

Dynamic precedence remains category, group or department rule override, global
stream payload/capacity/fraction defaults, then department stream fields, followed
by derived threshold/event volume. Positive explicit threshold wins over capacity
times fraction. This checkpoint preserves that policy; it does not move department
stream settings below the restored category-wide policy. Legacy department waste
continues using demographic rates and global stream definitions, not these dynamic
per-stream rates. The editor explains that distinction.

## Evidence and user review

Eight initial tests reproduced ten failures against `9f07ad6`; see
`latest/department-waste-before.txt`. Fourteen new tests cover no-op editing,
metadata preservation, sparse bulk changes, inheritance reset, schedule precedence,
blank/default/timeframe mode preservation, malformed identities and invalid rates.
The focused run passes **119 tests**, including nine evidence-schema checks, in
`latest/department-waste-focused.txt`.
An offscreen Qt rendering with an explicitly loaded Segoe UI font was inspected:
`latest/department-waste-dialog.png` (520 × 588 pixels); the controls and explanatory
text fit. This is a dialog inspection, not acceptance of the final CAD UI.

The full pack passes **1,350/1,350 tests** in **150.832 seconds**, with zero broken
evidence links and unchanged source during testing. See `latest/tests.txt`,
`latest/evidence.json` and `latest/department-waste-pack-build.txt`. The option audit
retains 278 unreviewed observed paths; this is not a completion percentage.

Two LTN runs with a 60-minute demand window each complete four tasks, with zero
failed/pending tasks and final simulation time 7928.480894138804 seconds. Assigned
work drains beyond the demand window. Initialization takes 1.375260 / 1.437804
seconds; total runtime 1.734387 / 1.797293 seconds. Both retain outcome hash
`5368460ed4fd5fd466e832b82d3d6358977abfaccbb456d45e268cfb7c0ab474`, unchanged
from the previous checkpoint. Source and input remain unchanged. See
`latest/department-waste-ltn/smoke.json`. This is regression/repeatability evidence,
not independent numerical validation of the full LTN project.

1. Open an existing department whose stream inherits rates. Accept without edits,
   then compare Demand Preview counts and effective settings before/after.
2. In a stream editor, enter a daily-volume override, save and inspect the changed
   demand. Clear the numeric field and save to restore inheritance.
3. Compare Clear schedule with Inherit schedule: explicit no-times and inherited
   clock times should remain distinct in the effective rule.
4. Bulk-select departments with different rates. Accept untouched and confirm the
   rates remain different. Edit one field and confirm other values remain unchanged.

## Limits and next work

The evidence is bounded to sparse overrides and the listed independent demand
references. It does not prove every calendar, mode interaction, physical stock
cycle or report total. Bulk orphaned streams retain their preserve/remove-only
behaviour; explicit-payload orphan handling and missing references need wider audit.
The single editor preserves unsupported-to-edit metadata instead of discarding it;
complete inline editing and bulk previews remain workspace work.

Next audit legacy waste pickup/seeding references and department naming suffixes,
then continue the remaining generation option dispositions and correctness
workspaces. Geometry, approved CAD UI, tutorial and final release gates remain open.
