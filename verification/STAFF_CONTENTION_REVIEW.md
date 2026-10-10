# Checkpoint 2E — staff contention and batch safety

Review date: 3 October 2026. Baseline: `310b28f`.

The existing staff model estimates required staffing. `staff_initial_count` seeds
a category pool; it is not a cap. When every person is busy, another person is
added. When someone is free but must walk to the job, handling waits for travel.
The dialogs now explain this distinction beside the count and movement settings.

Pools are keyed by category, not by resource label. The first booking determines
the pool's initial count and label. Group overrides still reach generated tasks,
but later tasks do not reset an already-created pool. Six category/group option
contracts now record these rules, defaults, limitations and test links.

## Reproduced defects and changed results

All times below are seconds after midnight on Monday 5 January 2026. Reference
locations A and B are 10 m apart. Direct planner calls deliberately reserve jobs
out of chronological order, as future service reservations may already exist
when another job is planned.

| Reference | Previous result | Required result |
| --- | --- | --- |
| Book B at 100–200, then A at 300–310, then request B at 150 for 200 s | The saved B batch reused the person booked at A and extended to 350; location history was overwritten | A keeps its person; another person serves B at 150–350 |
| Book B at 300–360, then request B at 100 for 60 s | Earlier work waited until 300 to join a future batch | Earlier work runs at 100–160 with another person |
| Book B at 50–250; request another B service at 100 for 50 s with hours 00:00–00:03 | The shared finish became 250, outside the incoming task's working period | A separate service runs at 100–150 |

These three cases failed before the correction. A new booking now invalidates
that person's previous batch entries. Sharing requires an overlapping service
already in progress at the incoming task's permitted start, and the shared finish
must fit its working period. This retains the existing conservative sizing model;
it does not insert tasks into gaps in a person's reservation calendar.

## Independent acceptance references

`tests/test_staff_contention.py` contains twelve tests, including:

- One busy person expands to two for separate overlapping services; an initial
  count of two allows two bookings before adding a third person.
- Under both sharing policies, B services 100–160 and 110–190 use one person,
  reserved until 190. Touching intervals 100–160 and 160–180 reuse without batching.
- A free person at B at 160 walks 10 m at 1.2 m/s and reaches A at
  168.333 s. No extra person is added merely to avoid that walk.
- A 120 s service requested at 16:59 with 09:00–17:00 hours waits until 09:00
  the next day. An unusable weekly schedule explicitly marks the existing
  `working_hours_fallback` in the returned booking.
- Different labels within one category do not split its pool; equal labels in
  different categories do not merge people. Group count/name/movement overrides
  reach the planner through both raw and editor-normalised inputs.

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_staff_contention -q
.\.venv\Scripts\python.exe -m verification.run --output verification/latest
.\.venv\Scripts\python.exe -m verification.smoke --config ltn.json --minutes 60 --output verification/latest/staff-contention-ltn
```

The full evidence pack passed **929 tests in 126.322 seconds**, with **zero broken
evidence links**. Two bounded LTN runs each completed four tasks with no failures
or pending tasks, retaining outcome hash
`5368460ed4fd5fd466e832b82d3d6358977abfaccbb456d45e268cfb7c0ab474`.
Local evidence is in `latest/staff-contention-pack-build.txt`, `latest/index.html`
and `latest/staff-contention-ltn/`. This bounded regression is not full LTN
acceptance. The source `ltn.json` and its unrelated local changes were preserved.

## Boundaries and next work

Historical logs are unchanged. Affected projects can now report more staff,
earlier handling for previously delayed jobs, and different return timings.
Automatic expansion remains intentional; fixed-capacity staff queueing is not
implemented by these settings.

This is not a globally optimal staffing schedule. Nonchronological planning can
overestimate staff because gaps are not reused. Batch records retain per-task
finishes; extending a batch does not revise earlier task records retroactively.
Summing overlapping handling durations is therefore not an independently verified
measure of staff busy time. The hours search still falls back after its bounded
search; accepting that metadata as valid capacity evidence would be incorrect.
Staff travel retains approximate distances and lift-wait assumptions, and this
checkpoint does not validate cross-floor physical staff capacity.

Next: reconcile staff assignment intervals with reported staffing/utilisation
metrics and audit shift-team boundaries. Continue the wider generation/return
and resource audit before the geometric traffic and approved UI work.
