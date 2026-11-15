# Archived GPU computation measurements

The GPU simulation option was removed on 12 October 2026. All current simulations
and automated stress tests use CPU. The measurements below are retained as
historical evidence for the removed implementation, not current setup instructions.
The benchmark harness now supports CPU only.

## Full seven-day benchmark

The benchmark uses the current LTN period, **1 January 2026 05:00 through
8 January 2026 05:00**. It preserves existing failures and deferral behavior;
outcome parity does not imply that the project passes its stress baseline.

Five unprofiled fresh processes per option alternate execution order. Measured
run time includes initialization, event execution and canonical evidence
finalisation. Streaming CSV expansion and exhaustive outcome hashing occur after
the timer. Parent process RAM and GPU-service RAM are recorded separately;
their individual peaks are not a simultaneous aggregate measurement. GPU
allocation peaks exclude CUDA context/driver memory.

Raw samples and medians: `computation-ltn-seven-day.json`.

| Median of five fresh processes | CPU | GPU option |
|---|---:|---:|
| Total run, including evidence | 355.466 s | 355.244 s |
| Initialization | 1.600 s | 3.589 s |
| Event execution | 352.338 s | 351.611 s |
| Evidence finalisation | 1.559 s | 1.530 s |
| Parent peak RAM | 414.3 MiB | 466.7 MiB |
| GPU-service peak RAM | — | 310.0 MiB |
| Peak kernel/static-array VRAM | — | 6.0 MiB |
| First streaming steps expansion | 5.769 s | 5.795 s |

All ten samples matched complete task-record, event-row and final-state hashes.
Both options completed 2,935 tasks, failed 4,946 tasks, had zero pending tasks and
ended at 607262.283551107 simulation seconds. Required returns and original
deferral behavior are retained. Existing failed tasks prevent a full-LTN stress
study from advancing beyond its baseline; no failed work was removed to make the
benchmark or study appear successful.

The 0.222 s (0.06%) median difference is smaller than the approximately 7–8 s
spread within each option's samples. **There is no demonstrated overall LTN
speedup.** Each GPU run evaluated 10,162 paths on the GPU and 1,825 through native
CPU search, with no VRAM fallback. Route kernels and GPU transfers together took
approximately 0.06 s; host-side event execution dominates. LTN is Simple mode,
so its geometry-kernel count is zero. Hardware geometry tests exercise that path
separately. These measurements describe the removed implementation.

These timings precede final hardening of exception cleanup and immutable-cache
metadata; route/kernel arithmetic is unchanged. A separate post-hardening full
GPU parity check is recorded in `computation-ltn-post-hardening.json`, with its
timing excluded from these medians. Final regressions also cover the additional
guards. GPU memory and service counters are diagnostic values, not simulation
outcomes, and are excluded from operational parity hashes.

Before removal, the final regression suite passed **403 tests**, including real CUDA route and
geometry batches, settings persistence, speculative-work rollback, stale
environment rejection, VRAM fallback, startup RAM reserves, GPU failure
propagation, constructor cleanup and cancellation of active/idle workers plus
the shared service. It also passed the existing routing/recovery, deferral,
inventory, charging, lift, multi-stop, geometric admission, canonical/legacy
evidence, investigation, playback and project-editing checks. The Computation
tab was visually checked at a compact window size.
