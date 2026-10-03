# Checkpoint 2F — staff report reconciliation

Review date: 3 October 2026. Baseline: `9b0edf6`.

The report now includes recorded payload exchanges as well as handling, preserves
explicit Linen assignments, and uses recorded initial roster counts and shift
multipliers ahead of configuration metadata. Previously exchanges were omitted,
Linen events outside configured hours could disappear or become ward collections,
and a category default could inflate the initial roster despite different effective
settings in the run. Legacy inferred timetable entries remain a separate unresolved
compatibility path; they are not acceptance evidence for recorded assignments.

## Reference calculations and evidence

Fourteen tests in `tests/test_staff_reporting.py` construct real simulator bookings,
log them using the simulator, and feed those rows into the report analysis. A CSV
roundtrip exercises the actual writer and parser. Expectations include:

| Reference | Required result |
| --- | --- |
| One 60 s payload exchange | One handling record in both summary and timetable |
| Logged initial count 1; two overlapping separate services; category metadata says 9 | Initial 1, required 2, added 1 |
| Logged multiplier 1; supplied metadata says 2 | Required count remains 1 |
| Same person handles 100–160 and 110–190 | Task handling 60 + 80 = 140 s; busy handling union 100–190 = 90 s |
| Different people handle those same intervals | Busy handling 60 + 80 = 140 s |
| Missing person or invalid interval | Busy handling unknown, not zero |
| Explicit Linen event outside supplied category hours | Preserve the event and its recorded team |
| Untracked department fallback, including the old `-team-untracked` identifier | Do not invent a planned staff member; busy handling remains unknown |
| Four-day blocks A, B, A | Two rostered people for one person per team; team A retains its identity |
| Exact four-day boundary and work-period deferral into the new block | Team B is selected in these reference cases |

New handling events export `staff_working_hours_fallback` and
`staff_resource_tracked`. Old logs have no proven fallback status; reports say so.
Summary rows expose contributing `event_ids` for traceability. Recorded busy
handling time unions intervals separately for each identified person, then sums
those unions. It excludes travel and is limited to supplied handling records.
It is not a whole-run utilisation percentage or proof of log completeness.

The PDF uses “Handling records” rather than “Handled payloads”, and separates
summed task handling from recorded busy handling. It displays unknown evidence
and schedule-fallback notes. A one-page preview was generated through the report
analysis and PDF builder and visually inspected after Poppler rendering. It covers
shared handling, exchange, unusable working hours and untracked department staff.
The preview is a planner/report fixture, not a full operational acceptance run.
Local QA outputs are `latest/staff-report-preview.pdf` and its CSV/PNG companions.

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_staff_reporting -q
.\.venv\Scripts\python.exe -m verification.run --output verification/latest
.\.venv\Scripts\python.exe -m verification.smoke --config ltn.json --minutes 60 --output verification/latest/staff-report-ltn
```

The full pack passed **943 tests in 129.733 seconds**, with **zero broken evidence
links** and unchanged source hashes during testing. Both bounded LTN runs
completed four tasks with zero failures or pending tasks, retaining outcome hash
`5368460ed4fd5fd466e832b82d3d6358977abfaccbb456d45e268cfb7c0ab474`.
Logs are in `latest/staff-report-pack-build.txt` and `latest/staff-report-ltn/`.
The source `ltn.json` and its unrelated local changes were preserved.

## Remaining defect found during boundary review

Follow-up: [Checkpoint 2G](STAFF_SHIFT_REVIEW.md) corrects the travel/team defect
below and extends acceptance to overnight and non-midnight-origin boundaries.
The reproduction remains here as historical evidence.

Travel can defer a booking into another four-day team block while the allocator
retains the roster chosen for its original baseline time. Reproduction with the
10 m A–B reference and 1.2 m/s walking speed:

1. Use `four_on_four_off_12h` with legacy direct-task all-day hours. Team A books B
   from 345540 to 345595 s, finishing five seconds before the four-day boundary.
2. Request a one-second service at A at 345599 s.
3. The working-period planner moves the walk to 345600–345608.333 s and handling
   to 345608.333–345609.333 s, but records `stores-shift-A-person-1`.
4. The allocator's own team function returns B at that actual handling start.

This is an unresolved simulator defect, not covered by the passing exact-boundary
or pre-travel work-period-deferral cases. Next checkpoint: reproduce it in an
acceptance test, select the roster for the actual permissible service window, and
verify reservations and logs remain consistent. Do not claim shift correctness
until travel and overnight boundaries are covered.

Heterogeneous schedules in one category pool, mixed tracked/untracked records,
complete-run staff utilisation, legacy synthetic timetable explanations and UI
navigation from staff metrics remain open. The broader feature audit, verified
geometry, approved UI rework and tutorial keep their agreed sequence.
