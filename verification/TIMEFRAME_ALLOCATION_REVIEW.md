# Checkpoint 2L — active-date allocation and calendar exclusions

Review date: 3 October 2026. Baseline: `7d4d802`.

Timeframe allocation now checks for eligible release dates throughout the
timeframe, including across midnight. Previously pool membership checked only
the nominal starting date while individual tasks checked their actual release
dates. A rule starting on an inactive Monday could therefore lose all of its
otherwise eligible Tuesday slots.

The correction retains the existing group ordinal policy. Enabled members with
some eligible department-open time in the timeframe share the configured slot
count. Each member applies its offset and ordinal to its own available working
duration. Individual releases still obey category weekday and fortnight gates;
excluded slots are not redistributed. This is release planning, not a staff
reservation or a shared-resource optimisation algorithm.

## Independent references

The main reference starts Monday 5 January 2026 at 20:00. Its timeframe and staff
hours are 22:00–06:00, with four tasks. Eight hours divided into four slots gives
Monday 22:00, Tuesday 00:00, 02:00 and 04:00.

| Calendar selection | Expected releases |
| --- | --- |
| Tuesday active | Tuesday 00:00, 02:00, 04:00 — three records |
| Monday active | Monday 22:00 — one record |
| Wednesday active | No records |
| Tuesday active; department only opens Tuesday 00:00–06:00 | Tuesday 00:00, 01:30, 03:00, 04:30 — four records |

The department opening constrains the available duration before spreading. The
category's release-day gate remains a separate filter. This distinction explains
why the last row has four records while the first has three.

A fortnight reference runs to Monday 19 January 2026 at 06:00. Sunday and Monday
are active; seven-day blocks are anchored to the simulation start date. Expected
releases are Monday 5 January 22:00; Sunday 11 January 00:00, 02:00, 04:00 and
22:00; Monday 19 January 00:00, 02:00 and 04:00. The intervening block is skipped.
The last three releases come from a timeframe beginning on the skipped Sunday.

Two departments with two tasks each and windows 09:00–11:00 and 15:00–17:00
share four ordinals. The existing policy gives the first department fractions
0/4 and 1/4 of its two hours (09:00, 09:30), and the second 2/4 and 3/4
(16:00, 16:30). All four tasks are retained. A fully closed department takes no
slots from an open member. These expectations do not claim globally even spacing
or sufficient staff capacity.

## Import and editing correction

The reference audit also found that opening a project could remove weekend
demand. Runtime treats missing or empty category/department `days_active` as
unrestricted, while editor templates inserted Monday–Friday. Imported omitted
values now retain the runtime meaning. Explicit restrictions remain effective,
and an explicit empty group override can clear a category restriction without
overriding a closed department.

The category, bulk demand and department dialogs display an unrestricted empty
list as all seven selected weekdays. New-project and new-department choices keep
their explicit weekday defaults. This change does not reinterpret the separate
global fixed-staff calendar's empty-day normalization.

## Inspectable exclusions

Demand Preview now stores `timeframe_slots` and `timeframe_slot_accounting` on
timeframe rules. Each candidate records its nominal date, pair, payload index,
planned/adjusted release, deadline and disposition. The accounting reconciles
eligible and emitted records and groups exclusions by reason. The existing rule
details show candidate, eligible, excluded and emitted counts and their difference.

For the Tuesday-only reference, four candidates reconcile to three eligible and
emitted records plus one inactive-date exclusion. A preview ending Tuesday 01:00
has one eligible/emitted record, one inactive-date exclusion and two slots outside
the preview. Future slots are not described as lost demand.

Only nominal timeframes intersecting the preview are inventoried. This is an
operational explanation using generator decisions, **not an independent expected
count or staffing-capacity check**. The small references above supply independent
arithmetic. The final audit pass observes slots without emitting tasks or consuming
identifiers; repeated previews preserve source inputs and return identical results.

## Acceptance and review

Twelve tests in `tests/test_timeframe_allocation.py` cover the references, weekday
inheritance, raw/editor parity, wakeups and repeated emission, exclusion accounting,
preview repeatability and the existing dialogs. The focused regression suite passed
85 tests before the final dialog adjustment; full-pack results below cover the
final source.

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_timeframe_allocation -q
.\.venv\Scripts\python.exe -m verification.run --output verification/latest
.\.venv\Scripts\python.exe -m verification.smoke --config ltn.json --minutes 60 --output verification/latest/timeframe-allocation-ltn
```

The full pack passed **1,003 tests in 127.255 seconds**, with **zero broken evidence
links** and unchanged source hashes during execution. Local evidence is in
`latest/timeframe-allocation-pack-build.txt` and `latest/evidence.json`.

Both bounded LTN runs completed four tasks with zero failures or pending tasks,
retaining the baseline outcome hash
`5368460ed4fd5fd466e832b82d3d6358977abfaccbb456d45e268cfb7c0ab474`.
Outputs are in `latest/timeframe-allocation-ltn/`. This proves bounded regression
repeatability, not full LTN acceptance. Unrelated local `ltn.json` edits were preserved.

For manual review, reproduce the Tuesday-only case and inspect Demand Preview's
rule details: four candidates, three eligible/emitted and one excluded. Shorten
the preview to 01:00 to inspect the two future slots. On a project copy with
omitted weekday lists, confirm weekend demand remains after opening/saving and
the relevant dialogs show all seven days.

## Limits and next action

The configuration inventory is still incomplete. Accumulation-mode calendars,
every malformed weekday-list form, runtime staff search fallback and complete
effective-rule import parity remain open. Saved historical projects with explicit
weekday restrictions are not rewritten, since their original intent is unknown.

Next: continue the configuration audit with continuous, threshold and sporadic
demand calculations and their configured-versus-generated reconciliation, before
returning to the wider resource and geometry requirements. Major UI work and
the user tutorial remain after the core engineering gates.
