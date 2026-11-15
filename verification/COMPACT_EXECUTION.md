# Compact execution and transactional rollback

The compact backend is a representation change. It preserves generation order,
random-number consumption, task identities, routing restrictions, inventory,
returns, deadlines and geometric calculations. The reference backend keeps broad
snapshots and eager exports for differential checks and benchmarks.

## Runtime and rollback

`compile_runtime_inputs` owns its inputs, separates presentation fields, and
reuses immutable definitions in an order-sensitive, mode/version-bound cache.
Fresh mutable loader state is created for every simulation. Frozen robot settings
are shared; operational robot/lift attribute writes are journalled on first change.
Sorted insertions are undone in reverse order at their original positions.
Geometric histories that are only appended use a saved boundary. Immutable
occupancy ledgers retain their existing reference-based rollback. Unconverted
mutable values use `deepcopy` with a shared memo.

Tentative log records are staged until reservation admission succeeds. Rejected
commits restore event identifiers and discard tentative events, symbols and
layouts. No timing approximation or reduced geometry is introduced.

## Canonical evidence and exports

Each managed run writes a separate SQLite store containing ordered events,
full-precision event times, interned identifiers, shared layouts and sparse value
changes. The hot logger builds a positional vector rather than a wide dictionary.
Writes are batched at 1,000 events or one second. Finalisation closes the writer
before hashing and publishing version-2 evidence. Interrupted unsealed prefixes
cannot establish completion.

Reporting state is captured in compressed chunks; it is not a pre-generated CSV.
Exports stream events or reporting chunks and retain existing CSV fields and
formatting. Export cache entries bind both outputs and sidecars to the canonical
checksum. Atomic temporary files protect completed outputs. Corrupt canonical
evidence or modified cached outputs are rejected rather than trusted.

Explicit output expansion runs in a contained subprocess with a 2 GiB committed-memory
ceiling, a free-system-RAM reserve, cancellation and parent-death protection. The
simulation completion status is independent of export success. Existing version-1
CSV evidence still uses the original verification boundary.

New SQLite stores use storage format 3 with bounded compressed blocks and
event-type-specific defaults. Evidence sidecars remain schema 2 and bind the
actual storage version and event count. Formats 1 and 2 remain readable.
Investigation and project Playback read canonical events directly. Report readers
stream the legacy CSV representation through the existing parser without writing
a CSV to disk. Explicit CSV exports retain the contained expansion process.
See [output size verification](OUTPUT_SIZE_REVIEW.md).

## Validation and measurement

Differential checks cover Simple/Detailed operational event equivalence and exact
export equivalence. Atomicity tests cover duplicate insertions, missing keys,
dynamic attributes, nested mutable fallbacks, charging, lifts, multi-stop routes,
joint geometric admission and preservation of prior reservations.

The reproducible benchmark command is:

```powershell
.\.venv\Scripts\python.exe verification/benchmark_compact.py --repeats 5
```

The harness alternates backends, uses fresh processes, excludes profiling from
wall-time comparisons and verifies complete route/energy outcome hashes. The
eight-worker study also compares candidate order, ranking and metrics. Study RAM
is the highest monitored aggregate usage; ordinary runs use Windows process peak
memory. First-view expansion time is measured separately from simulation completion.
Detailed timings and raw samples are recorded in `compact-benchmark.json`.

### Measured results, 12 October 2026

All 40 unprofiled samples passed outcome parity. These are medians of five fresh
processes per backend, measured on the Ryzen 9 9955HX3D Windows workbench with
61.7 GiB physical RAM and Python 3.13. The reference backend includes its original
eager export cost; the compact backend includes canonical evidence finalisation.
First-view times cover streaming steps and playback materialisation, excluding
process startup, GUI parsing and rendering.

| Workload | Reference run | Compact run | Reference / compact RAM | Evidence size change | First expansion |
|---|---:|---:|---:|---:|---:|
| 1,200 deliveries, four robots | 2.227 s | 1.606 s | 65.7 / 50.2 MiB | 46.5% smaller | 0.764 s |
| LTN, one day | 23.751 s | 22.208 s | 228.3 / 226.5 MiB | 47.0% smaller | 1.380 s |
| Detailed geometry, 120 tasks | 0.420 s | 0.445 s | 109.8 / 110.0 MiB | 47.5% smaller | 0.083 s |
| Eight-worker study, 18 trials | 15.168 s | 9.343 s | 266.4 / 289.7 MiB aggregate | 2.4% larger | deferred |

The delivery model takes 27.9% less time and uses 23.6% less peak RAM. LTN takes
6.5% less time; the stress study takes 38.4% less time. Gains depend on the model.
The small Detailed model takes 25 ms (6.0%) longer: creating/sealing SQLite and
capturing reporting state add a fixed cost while geometry computation remains
unchanged. This cost is visible on a sub-second workload, so uniform speed gains
are not claimed. Its additional measured peak RAM is 0.2 MiB.

Persistent stress workers retain interpreter and immutable-model allocations
between trials. This trades 8.8% more monitored aggregate RAM for less startup
work; idle workers count toward RAM admission and the existing process-group
limit. SQLite headers and per-run metadata also increase evidence size on these
very small study trials. Completed evidence remains independent of expansion.

The LTN input is the current `ltn.json`, copied in memory with its end set one day
after its start. Its existing failures are retained identically by both backends;
the benchmark does not claim that LTN passes the stress criterion. An older
`ltn_profile_1day.json` fixture was rejected by current validation because of
conflicting shared-container definitions and was not used for these medians.

A separate cProfile run on the delivery workload measured reference `deepcopy`
at 2.992 cumulative seconds across 2,980,693 recursive calls (14,377 top-level
calls). Compact execution made zero calls on this workload. Profiled timings are
excluded from the wall-time table, and safe fallback copies remain for mutable
structures in other models. The reference option remains available with
`--runtime-backend reference` for future differential checks.

The broad regression run passed 372 tests covering compact execution, canonical
and legacy evidence, interruption/export cancellation, playback, investigation,
stress search, routing/recovery, deferral, inventory, charging, lifts, multi-stop
and joint geometric rollback. Exact event/CSV comparisons include Detailed mode.
Follow-up checks passed 107 tests after extending containment to command-line and
report readers and adding compiler-version rejection; two additional cases cover
these paths. Explicit simulator CLI filenames are preserved by bounded, atomic
publication after child-process expansion.
