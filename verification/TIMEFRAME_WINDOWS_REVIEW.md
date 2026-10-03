# Checkpoint 2K — working periods and out-of-hours demand

Review date: 3 October 2026. Baseline: `707b555`.

Timeframe generation now considers staff shifts beginning on the previous day,
matching runtime handling of overnight shifts. Spreading uses the union of all
available staff/department intersections within the timeframe. Closed gaps do
not consume spacing time, and overlapping periods are counted once.

Previously the generator inspected only the shift starting on the timeframe's
date and retained only the longest department overlap. It could release every
task at timeframe start, or omit available working time. The group allocator
also excluded departments whose only opening was an overnight period from the
previous active day, which could discard three of four configured slots.

## Independent reference arithmetic

Four tasks use ordinal fractions 0, 1/4, 2/4 and 3/4 of available working duration.
The final end is excluded. The following references use Monday 5 January 2026
and Tuesday 6 January 2026; hours are local model wall-clock times.

| Case | Available periods | Expected releases |
| --- | --- | --- |
| Tuesday 00:00–06:00 timeframe, Monday 22:00–06:00 shift | Tuesday 00:00–06:00 | 00:00, 01:30, 03:00, 04:30 |
| Monday 20:00–Tuesday 08:00 timeframe, two custom shifts | Monday 22:00–Tuesday 02:00 and Tuesday 06:00–08:00 | Monday 22:00, 23:30; Tuesday 01:00, 06:30 |
| Same overnight timeframe, continuous staff; department closes 22:00–06:00 | Monday 20:00–22:00 and Tuesday 06:00–08:00 | Monday 20:00, 21:00; Tuesday 06:00, 07:00 |
| Tuesday 00:00–18:00 timeframe with overlapping daily staff periods | Union is 18 hours | 00:00, 04:30, 09:00, 13:30 |

Calendar inspection and generation share this arithmetic. Inspecting wakeups
does not consume tasks, and repeated generation does not duplicate them. Raw
and editor-normalised inputs, wakeup lists and Demand Preview agree in these
references. Generated task details include the actual available periods.

Equal staff start/end times now mean no working period in generation, matching
runtime. Use 00:00–24:00 for a full day. This does not change the separate existing
department/timeframe interpretation of equal endpoints.

Rotating teams work daily through their alternating four-day blocks. A restricted
global rotating `days_active` list was previously applied by generation while
runtime ignored it. Both now follow the runtime rotating-team contract, with an
unsupported finding explaining that the weekday restriction is ignored. Custom
weekly hours remain effective. General work/rest-cycle support remains absent.

## Retained demand is distinct from no work

When enabled staff spreading finds no overlapping staff/department working
period, the existing policy retains the configured demand. It releases at
timeframe start, adjusted to department opening, provided that opening precedes
the deadline. This fallback does **not** authorise out-of-hours staff handling.

For timeframe 07:00–08:00 and staff 09:00–17:00, four tasks release at 07:00;
runtime handling requested then waits until 09:00. Demand Preview now flags all
four records and explains the deadline risk in its summary, rule details and task
explanations. The count covers detected fallback records; zero flags are not a
general feasibility proof, particularly when spreading is disabled.

For timeframe 08:00–18:00 and a department first opening at 18:00, the expected
result is zero tasks. The deadline is exclusive. The preview now explains that
specific rejection rather than only listing several possible calendar causes.
Additional observed reasons cover missing timeframe bounds, excluded release
dates, missing openings and release slots outside the preview period.

## Acceptance and reproduction

Twelve tests in `tests/test_timeframe_calendar_windows.py` cover these references,
fixed/global versus custom overnight hours, overnight department group sizing,
runtime calendar agreement, rotating weekday warnings and visible preview counts.
The pre-fix reproduction is retained locally as `latest/timeframe-windows-before.txt`.
An earlier focused schedule/preview/staff regression run passed 83 tests before
the last diagnostic and warning additions; the full pack below verifies the final source.

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_timeframe_calendar_windows -q
.\.venv\Scripts\python.exe -m verification.run --output verification/latest
.\.venv\Scripts\python.exe -m verification.smoke --config ltn.json --minutes 60 --output verification/latest/timeframe-windows-ltn
```

The full pack passed **991 tests in 127.632 seconds**, with **zero broken evidence
links** and unchanged source hashes during execution. Local outputs are
`latest/timeframe-windows-pack-build.txt` and `latest/evidence.json`.
The inventory still has 476 unreviewed option paths.

Both bounded LTN runs completed four tasks, with zero failures or pending tasks,
retaining outcome hash
`5368460ed4fd5fd466e832b82d3d6358977abfaccbb456d45e268cfb7c0ab474`.
Their outputs are in `latest/timeframe-windows-ltn/`. This is bounded regression
evidence, not complete LTN acceptance. Unrelated local `ltn.json` edits were preserved.

For manual review, use a project copy with the Tuesday timeframe and Monday
overnight staff hours from the first table row. Build Demand Preview and verify
four spaced releases. Then use the 07:00–08:00 case to inspect the warning count
and its rule explanation. No major UI workflow or approved layout was changed.

## Remaining limits and next action

Release spreading is not a staff reservation or a promise of completion before
the deadline. Heterogeneous departments in one shared timeframe group, category
active-day and fortnight transitions, and the bounded runtime hours-search
fallback still need independent acceptance. Complete no-work explanations for
every generator mode remain open. The overall configuration gate is not complete.

Next: verify pooled timeframe rules with different department calendars and
active-day boundaries, checking demand conservation and explaining any exclusions.
The later geometry, approved UI workflows and user tutorial retain their sequence.

A read-only probe after this correction confirmed a remaining allocation defect:
with simulation Monday 20:00–Tuesday 08:00, timeframe 22:00–06:00, four tasks,
custom Monday staff hours 22:00–06:00 and category `days_active=["tue"]`, the
calendar returns no wakeups and the preview has zero tasks. The group membership
check uses the nominal Monday while task eligibility uses the actual release
date. This discrepancy remains open for the next reproducing test and correction;
the passing reference suite above does not establish this boundary's correctness.
