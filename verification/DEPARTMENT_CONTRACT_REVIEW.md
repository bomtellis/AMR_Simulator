# Department schedules and demographic inputs — slice 2AI

## Fixes and reference calculations

Department opening intervals now use one resolver in generation and editor
normalisation. An explicit end clock wins over legacy `hours_operated_per_day`.
An earlier end belongs to the next day. Equal clocks retain the existing 24-hour
convention; zero legacy hours therefore also means a full day, not closure.
Disable a department to suppress its generated work.

Previously the editor clamped inferred next-day closing clocks to `24:00`.
A **22:00 + 8 h** department therefore reopened as 22:00–24:00, only two hours.
It now stores **06:00** and retains eight hours. **09:00 + 24 h** stores **09:00**
and retains a full day. **23:45 + 0.5 h** stores **00:15**. Repeated import/default
normalisation is stable. Missing/empty weekday lists continue to mean every day;
overnight openings belong to their start weekday.

Legacy demographic waste uses:

`hourly m³ = alpha × beds + beta × (daily turnover / operating hours) + gamma × staff`

The runtime previously imposed a minimum one-hour denominator even for a shorter
window. A 09:00–09:30 department with 10 beds, daily turnover 2, staff 3 and
coefficients alpha 0.01, beta 0.2, gamma 0.1 now yields:

`0.01 × 10 + 0.2 × (2 / 0.5) + 0.1 × 3 = 1.2 m³/hour`

Over half an hour this is **0.6 m³**, rather than the former **0.4 m³**. A large
collection threshold in the reference leaves that volume in accumulated stock,
so the assertion is independent of task dispatch. One-minute, overnight,
full-day, explicit-end precedence and disabled-department cases are included.

The department dialog no longer truncates fractional bed/staff model values and
now preserves legacy waste coefficients and unedited metadata when accepted.
Previously its replacement object discarded those fields. This does not establish
all department identity/reference/editing behaviour.

## Input contract and scope

- `enabled` must be a JSON boolean.
- Demographic values and alpha/beta/gamma must be finite, nonnegative numbers;
  numeric strings remain supported. Booleans and null are rejected. Fractional
  demographic inputs remain permitted by the existing continuous model.
- Legacy hours must be within 0–24. Its conversion retains minute rounding.
- Clocks allow valid legacy whole-hour strings, H:MM or HH:MM, or blank fallback;
  `24:00` is accepted only as an end clock. Malformed clocks are not silently
  replaced with defaults.
- Weekdays must be a list of abbreviated weekday keys, case-insensitive.
- A combined legacy hourly rate that overflows is blocked before generation.

Checks run before editor import, simulator/task-manager construction and department
upsert. The department dialog reports invalid entries without returning a replacement
object. Project Checks identifies the legacy-only demographic scope: these values
do not automatically define modern category rates or staff-service capacity.

The coefficients are empirical user inputs requiring calibration against measured
data; the arithmetic is verified, not a clinical waste-production model. Modern
category demand and staffing are configured separately. Identity/reference,
floor/coordinate and complete department editing contracts, all mixed modes and
full stock/event/report reconciliation remain open. No release gate closes from
this checkpoint alone.

## Evidence

Eight initial reproductions produced 26 failures before fixes, retained in
`latest/department-contracts-before.txt`. Twelve new tests now pass in a **68-test
focused suite**; all **nine evidence-contract checks** pass. See
`latest/department-contracts-focused.txt` and
`latest/department-contracts-evidence-check.txt`. The full suite passed
**1,296 / 1,296 tests in 136.392 seconds**, with **zero broken evidence links**
and unchanged source hashes during testing. See `latest/tests.txt`,
`latest/department-contracts-pack-build.txt` and `latest/evidence.json`.

The two 60-minute LTN demand-window runs each completed four tasks with zero
failed/pending. Initialisation took 1.361 and 1.426 seconds; total time 1.719 and
1.783 seconds. Both retain outcome hash
`5368460ed4fd5fd466e832b82d3d6358977abfaccbb456d45e268cfb7c0ab474`.
See `latest/department-contracts-ltn/smoke.json`. This bounded regression is not
full LTN acceptance or an agreed performance threshold.

## User verification

1. Import a department with start 22:00, legacy hours 8 and no end clock. Confirm
   the editor shows 06:00 and save/reopen retains the eight-hour interval.
2. Repeat with start 09:00 and 24 hours; confirm the full-day convention survives.
3. Edit a project copy containing legacy waste coefficients and fractional bed/staff
   values. Accept the dialog and verify these values and unedited metadata remain.
4. Enter a negative bed count or malformed clock; confirm the dialog rejects it.
   Review the demographic-scope finding in Project Checks.

## Next work

Finish department identity, reference, floor/coordinate and editing contracts,
then continue the remaining workspace gates. Keep full report coverage/stock
reconciliation open. Geometry, the approved graph-focused CAD UI, tutorial and
release gates retain their order. The unrelated `ltn.json` edit remains excluded.
