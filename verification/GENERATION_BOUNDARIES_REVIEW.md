# Generation boundary review

D013 fixes omitted demand in the final partial generation interval. D014 remains
open: demand polling can delay assignment of work with an earlier scheduled time.
These are separate claims; passing count tests does not prove timing correctness.

## Independent cases

All cases use the existing 10 m A–Door–B reference, one robot at 2 m/s and
2 seconds each to load and unload. Default polling is 900 seconds.

| Horizon | Schedule in seconds | Expected generated and completed tasks |
| --- | --- | --- |
| 600 | 60 | 1 |
| 1,000 | 60, 960 | 2, each once |
| 600 | 600, 660 | 1: the horizon is inclusive, 660 is excluded |
| 900 | 60, 900 | 2, each once |
| 600, generation disabled | 60 | 0 |
| 0 | 0, 60 | 1: only the start-time task |

Before-fix evidence in `baseline/generation-boundaries-before-fix.txt` records
three failures. `tests/test_generation_boundaries.py` checks actual simulator
releases and completed IDs, rather than calling the generator alone.

The horizon limits demand creation; it does not stop already released tasks from
finishing. No future poll is scheduled after the inclusive boundary, and an
existing poll exactly at that boundary is not duplicated.

## Timing limitation requiring further work

Open `scenarios/generation-final-interval.json`, save a disposable project and
run it. It should complete one task with 10 m of travel and 9 seconds of service:
`2 + 10 / 2 + 2 = 9`. Its scheduled release is 00:01, but the current polling
implementation discovers it at 00:10, starts it then, and finishes at 00:10:09.
This late start is a recorded limitation, not the intended exact-time behaviour.

Before D013 this project silently generated zero tasks. For horizons that are
exact multiples of the interval, D013 leaves the polling sequence unchanged.
Cross-day scheduling, timeframe allocation and state-dependent volume generation
still require independent coverage. Do not generalise these six simple schedule
cases to all modes or use them to sign off service-level timing.

Review the task count, actual start/finish, and distinction between demand horizon
and run completion. The remaining full roadmap is in `ROADMAP.md`.

## Recorded verification

- Full local pack: **338/338 tests passed**, no broken evidence links.
- Saved-project reference: one completed task, no failures or pending work;
  summary and completion events reconcile, source JSON unchanged. Evidence:
  `latest/generation-boundary-reference/summary.json`.
- Six-hour LTN: **203 completed, 0 failed, 0 pending**; detailed task outcomes
  unchanged, hash `593945bef454f5d602c82f0f15180cbc26285d3711d93102d483635da36faab5`.
  Evidence: `latest/ltn-generation-boundaries/summary.json`.
- These runs automatically acknowledged engineering-reference warnings; this
  does not record a human review or acceptance of the remaining timing defect.
