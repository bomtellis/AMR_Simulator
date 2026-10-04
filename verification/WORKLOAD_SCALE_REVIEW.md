# Operating-scale measurement — 4 October 2026

## Follow-up: charging estimates and final pending state

Charger approach plans now share a cache limited to one read-only selection
pass, keyed by robot and charger. Onward delivery feasibility remains task
specific. A subsequent selection pass and actual charge dispatch recompute
availability. Regression tests show that 19 blocked tasks spanning three windows
need one empty charger-route estimate rather than 19 for the same robot/charger,
and that onward feasibility is independently evaluated for different tasks.

The unchanged full workload has exactly the same outcome hash as the window fix:
`5533ebb0acf18c26ca65e27822bb0029a02be9dbeeb17ca842f33a88d5bfc22c`.
Counts remain 6,455 completed, 457 failed and 88 pending. Execution and exports
took 544.498 seconds versus 550.802 previously; this single-sample difference is
not a substantial performance claim. Reconciliation and input preservation pass.
See `workload-evidence/charge-cache.json`, including final robot/lift state and
every pending task's last recorded estimate reason. **228 focused tests pass**.

All 88 pending requests are Source-5 to Destination-5. The only robots remaining
on floor 5 are Robot-F4-3 and Robot-F4-6 at about 20.09% charge. Both use Source-4
chargers; the floor-5 bays accept Robot-F5 types. All six Robot-F5 robots are on
other floors. Both lifts have 19.95% health after 1,601 journeys each. This is
consistent with 100 - 1,601 * 0.05 percentage points and below the configured
20% minimum. Remaining work therefore lacks an available robot/charger pairing
with sufficient usable energy. These requests remain pending rather than being
silently completed or discarded. A task's last estimate reason refers to the
last considered robot, not an exhaustive explanation of every candidate.

The user-facing investigation still needs explicit final pending-state evidence;
these benchmark snapshots do not retrofit that evidence into the event CSV.
Further runtime investigation and a refreshed full isolated regression baseline
remain open. A separate maintained-resource acceptance scenario would need
explicit assumptions and must preserve this constrained run as evidence.

## Follow-up: candidate-window starvation

The retained diagnostic state reproduced the original 490 pending tasks with no
future events. Eight tasks had a failed charger-access estimate; 482 had no
recorded pending reason. An independent selector regression then proved that a
fully blocked eight-task candidate window hid feasible work beyond it in both
simple and detailed modes.

The scheduler now examines subsequent bounded windows when the current window
has no assignment. Existing precedence within each window, batch preference and
charging decisions are retained. It does not discard blocked tasks or increase
the number of tasks per estimation batch. Tests cover later-window selection,
bounded batches, first-feasible-window precedence and an entirely blocked queue.

The identical full workload after this fix completed **6,455 tasks**, failed
457 and left 88 pending: **402 additional completions**. Completed and failed
events still reconcile with the run summary; input hash and configuration
roundtrip are unchanged. Execution and exports took **550.802 seconds** and
investigation took 3.759 seconds. Peak working set was 906,059,776 bytes. See
`workload-evidence/window-fix.json` and local full evidence under
`latest/workload-scale-window-fix`.

This exposes a substantial runtime regression from examining previously hidden
work. Optimising repeated infeasible estimates and explaining the 88 remaining
pending tasks are open actions; do not restore the bounded-window starvation to
recover the old timing. Lift-wear assumptions remain unchanged and full scale
acceptance still fails. **226 focused tests pass** across scheduling, charging,
deferral, physical-bin returns, routing, geometric traffic and resource recovery.
The full isolated regression baseline has not yet been refreshed for this fix.

## Original baseline

The controlled seven-day workload is reproducible, but **does not pass the
all-tasks-completed gate**. Two fresh-process runs each produced 6,053 completed,
457 failed and 490 pending tasks from 7,000 releases. Preserve this result when
investigating the outstanding work; do not reduce the requested workload.

Run `python -m verification.workload --output verification/latest/<new-folder>`
using the repository environment. Defaults are 10 floors, 60 robots and 1,000
tasks per day for seven days. The command saves/reopens an `.amrproj`, freezes
the inputs through the normal saved-run path, executes the simulator, exports
results and checks investigation reconciliation. A failed completion check
returns exit code 1 while retaining evidence. Existing benchmark folders cannot
be overwritten. Three focused tests cover dimensions, invalid arguments and
small-run repeatability/reconciliation.

## Measured results

| Measurement | Run 1 | Run 2 |
| --- | ---: | ---: |
| Simulation construction, execution and exports | 172.274 s | 172.361 s |
| Investigation loading and reconciliation | 3.511 s | 3.520 s |
| Project save | 0.0413 s | 0.0397 s |
| Project reopen | 0.0209 s | 0.0217 s |
| Project size | 45,321 bytes | 45,321 bytes |
| Peak process working set, including investigation | 869,916,672 bytes | 869,584,896 bytes |

Both runs retain unchanged input bytes, exact configuration roundtrips and
matching completed/failed event-to-summary counts. Run 1 contains 94,042 event
records in a 99,428,752-byte full CSV. Matching input and outcome SHA-256 values
are recorded in `workload-evidence/run1.json` and `run2.json`. Full local evidence
is retained under `latest/workload-scale-run1` and `latest/workload-scale-run2`.
These measurements used Windows 11 and Python 3.13.14 at commit `cc64014`, with
the preserved local simulator/LTN changes and the new benchmark files. They are
not clean-install measurements. No runtime acceptance threshold has been agreed.

## Explanation and next investigation

Both lifts fall below their default 20% operational health threshold on day six.
Default wear is 0.05 percentage points per journey; this fixture does not override
wear or introduce maintenance. The first explicit health failure occurs at
462,960 simulated seconds. Of the 457 failures, 285 explicitly report unavailable
lifts and 172 report no route for an AMR to reach the pickup. Event processing
ends at 554,364 seconds within the configured 604,800-second window.

The 490 pending tasks require a separate investigation of robot availability,
charging access and terminal-pending classification. Their root cause is not
proven by the aggregate counts. This is a retained failed workload acceptance,
not evidence that all tasks are correctly classified or all resource behaviour
is verified. Any new maintained-lift reference must remain a distinct scenario
with explicit assumptions rather than replace this result.

## Scope

The fixture uses simple motion, 100 m straight routes, two lifts, a ten-hour daily
release window and one payload type. Every fourth task goes to the next floor.
It does not measure geometric traffic, walls, drawings, staffing, dynamic demand
or interactive GUI responsiveness. Project-check warnings are acknowledged
automatically for measurement, not approved by a person. The current LTN input
has six floors and 22 robots; realistic LTN regression and drawing performance
remain separate requirements. The wider roadmap remains open.
