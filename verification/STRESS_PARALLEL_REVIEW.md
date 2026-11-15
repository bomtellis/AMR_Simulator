# Concurrent stress studies and native acceleration assessment

The workbench runs a baseline first, followed by independent corridor and sample
trials in isolated CPU processes. The default ceiling is eight workers. Refinement
uses fixed batches of eight chosen from the preceding completed batch, independent
of the number of workers actually admitted. Dispatch order is saved before launch;
checkpoint ordering, candidate identities and rankings do not depend on completion
order. An interrupted batch is finished on resume before further refinement.

## Memory and cancellation

Defaults are a **16 GiB study RAM ceiling** and an **8 GiB free-RAM reserve**.
The effective reserve is the larger of the configured reserve and 20% of physical
RAM, capped at half of physical RAM on smaller machines. The study ceiling is also
capped at half of physical RAM. The coordinator admits workers using observed
baseline/trial peak memory with a 50% allowance and a minimum 256 MiB estimate.
It checks active memory and available system RAM about ten times a second.

The Windows workbench places the coordinator and its descendants in a Job Object
with an aggregate committed-memory ceiling. The coordinator additionally contains
trial workers in a separate Job Object. Kill-on-close prevents children surviving
coordinator or application termination. Workers wait for containment before they
load the study or simulate. The source interpreter is launched directly while
retaining the parent's package paths, avoiding Windows virtualenv redirector
processes. Each worker uses one routing thread and one numerical-library thread,
and runs below normal CPU priority.

If the free-RAM reserve or study limit is reached, the study stops, releases worker
memory, and retains completed evidence and the saved batch for resume. Memory
exhaustion is an execution error, not evidence that a scenario is infeasible.
Cancellation terminates all active children and waits for their exit before
returning. Completed child results can be recovered after coordinator interruption.
Compact execution reuses admitted worker processes between independent trials.
Idle worker memory is included in admission and displayed study RAM. Closing the
native process group stops both active and idle workers. Definition caches are
immutable; each trial has fresh operational state and canonical evidence.
Library calls supervise coordinator memory through admission/monitoring; the
workbench's outer Job Object additionally enforces the full process-tree ceiling.

Startup reports input validation and verification of saved trials. Live feedback
shows the current phase, each active trial, simulated time, task outcomes, elapsed
time, requested/active worker counts, RAM consumption, the RAM ceiling and reserve.
Remaining time is estimated from completed trial durations and available worker
capacity. The GUI updates its elapsed timer during lengthy initialization.
The active simulation has a separate progress bar so the baseline remains visible
when the study-wide percentage rounds to zero. The baseline phase explains why
one worker is active; failed baselines open Results with outcome counts and an
action to investigate the saved evidence. The setup explicitly identifies the
New study and run button as the start action.
An exited interpreter can be observed before its Windows launcher signals exit.
The coordinator keeps progress and cancellation responsive during this bounded
grace period instead of reporting a false RAM-monitor failure; the native process
group continues enforcing the memory ceiling throughout.
Unedited setup controls retain their original numeric precision. Display rounding
must not change frozen timing choices and prevent a saved study from starting.

## Could C++ help?

Yes, a native component can release the GIL while operating on native arrays or
containers. It must reacquire the GIL before accessing Python objects or callbacks.
Wrapping the existing dictionary-based simulator without moving its computation
and data ownership to native code would retain the main lock/interaction overhead.
Process isolation already bypasses the GIL between scenario trials.

A controlled profile used four robots, 1,200 static deliveries, two alternative
floor routes and an eight-hour simulation period. All 1,200 tasks completed, with
zero failed or pending work. With cProfile enabled, initialization and simulation
took 5.380 seconds on the inspected Ryzen 9 system. This is a workload observation,
not a performance threshold. Major cumulative costs were:

| Operation | Cumulative seconds |
|---|---:|
| Task assignment | 5.050 |
| Candidate task estimation | 4.375 |
| `deepcopy` | 3.021 |
| Reservation rollback bookkeeping | 2.919 |
| Corridor segment estimation | 0.617 |

The first candidate for native work is a reservation store with compact interval
arrays and a transaction journal, together with batches of pure travel estimates.
An interface should accept numeric node/resource IDs, interval arrays, geometry,
permission masks and scenario boundary arrays; return candidate timings and route
indices; and expose begin/commit/rollback operations without Python callbacks in
the computation region. A binding can release the GIL around those native calls.
Compare every result and rollback against the existing independent reservation,
routing, energy and payload tests before enabling an optional backend.

No C++ compiler, build configuration or binding package is currently configured in
this workspace. No unverified native dependency is introduced by this change.
The assessment is grounded in profiling; a C++ backend needs its own build and
equivalence-validation work.

The subsequent Python compact-execution change implements mutation journals and
removes the broad route-entity snapshots on the delivery workload. Its separate
profile made zero `deepcopy` calls, with exact outcome parity. Updated unprofiled
five-run measurements, including persistent-worker RAM costs, are recorded in
[compact execution verification](COMPACT_EXECUTION.md). The native assessment
above describes the earlier profile, rather than the remaining copying cost.

References: [Windows Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects),
[Job memory limits](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_extended_limit_information),
[pybind11 GIL rules](https://pybind11.readthedocs.io/en/stable/advanced/misc.html#global-interpreter-lock-gil).
