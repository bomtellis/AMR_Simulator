# Physical population and failed-return evidence — review checkpoint

**D030:** stored-stock peaks were being described as total physical population,
excluding carried and staged containers. Registered-but-unissued task IDs were
also included in known-instance totals. The simulator now distinguishes six states:

| State | Meaning | Included in active population? |
| --- | --- | --- |
| Planned | An ID exists, but the container has not been physically issued. | No |
| Stored | Physically stored and tracked in ordinary inventory. | Yes |
| In transit | Picked up, with arrival still outstanding. | Yes |
| Staged | Arrived for service or selected as an exchange empty awaiting return. | Yes |
| Unconfirmed | Task failed after pickup without a confirmed arrival. | Yes, retained conservatively |
| Removed | A mass collection removed the object from the model. | No |

The physical peak is per payload type. Issued instances is cumulative and includes
objects later removed; it excludes planned-only IDs. These metrics are separate
from task count, transfers and currently stored inventory. Unconfirmed means the
model cannot establish arrival, not proof of loss or safe recovery.

Each new full log records the final state of every registered ID. Results
Investigation exposes state counts and links them to contributing event records.
Failed returns retain staged stock and emit `payload_recovery_required`, including
its identity and location. No bay, recovery journey or successful arrival is invented.

**D031:** the report previously deduplicated physical IDs before counting tasks,
so two tasks using one object could report only one task. It now counts tasks and
physical IDs separately. Transported counts require paired departures/arrivals;
seeded inventory is excluded and service arrivals are included.
Missing identity evidence is not replaced with task counts.
Old storage-only population rows cannot establish the new physical metrics and
display a dash. Missing lifecycle evidence in Results Investigation is unknown,
not zero. The aggregate report label explicitly says sum of per-type peaks; those
peaks need not occur at the same time.

## Failed-return example

Open [staged-return-failure.json](scenarios/staged-return-failure.json), save a
disposable project and simulate. One full box travels 10 m at 2 m/s with 2 seconds
for loading and unloading. B initially has one empty box in its single finite bay.
The outbound path is available; the return's `NoReturn` profile permits only A,
so no B→A route exists. This deliberately constrained case should be acknowledged
as such during project checks.

| Observation | Independent expectation |
| --- | --- |
| Pickup | New full box is picked up at **2 seconds**; the original empty remains at B. |
| Arrival | 2 + 10/2 + 2 = **9 seconds**. The full box occupies B's bay; the empty becomes staged. |
| Return | RETURN-T1-1 fails at **9 seconds** because its route is infeasible. |
| Task totals | **1 completed, 1 failed**. |
| Physical totals | **2 issued, peak 2 active; final 1 stored and 1 staged**. No planned, in-transit, unconfirmed or removed objects remain. |
| Recovery evidence | One recovery-required event identifies the staged empty at B. |

The staged empty is not available as ordinary inventory. An explicit recovery
workflow, with space and route checks, is still required; this checkpoint preserves
and explains its state rather than silently returning it to a full bay.

## Evidence and remaining work

Thirteen reference tests cover planned-only cancellation, carried population,
exchange staging, unconfirmed arrival, replacement after removal, identity reuse,
legacy logs, report task/ID separation, and this project raw/editor-normalised.
Before-fix evidence is in `baseline/payload-lifecycle-before-fix.txt` (four failures)
and `baseline/payload-report-evidence-before-fix.txt` (three failures).

The full pack passes **489/489 tests**, with zero broken evidence links.
Six-hour LTN remains **203 completed, zero failed and zero pending**, retaining
the detailed outcome hash
`21cd7e6d1fe83f255ab425307acd0fd1f830f4aa155412eba1767b3996fcf0f6`.
The final run took 16.158 seconds; see `latest/ltn-lifecycle-final/summary.json`.
Its task outcomes are unchanged; lifecycle population and report counts have
deliberately changed to the definitions above.

The saved failure reference preserves inputs and reconciles its one completion
and one failure against events; see `latest/staged-return-reference/summary.json`.
The payload-only PDF was generated with the application report command, rendered
with Poppler and visually checked: **2 runtime payloads, 1 unique transported,
1 task using a transported payload and 2 issued instances**. Labels and explanatory
text are readable without clipping. The PDF is `latest/staged-return-reference/payload-review.pdf`.
Poppler emitted a Symbol-font diagnostic; the reviewed page contains no missing
glyphs. This verifies the changed payload page, not the complete report's layout.

Staff handoff state changes still use the existing handoff execution semantics;
independent staff-action timing and all mixed workflows need further cases.
Staging geometry/capacity and explicit recovery operations remain open. Container
state evidence does not prove physical clearance or replay every past state.
The earlier unexplained preview interruption remains documented in
`baseline/multi-stop-verification-observation.txt`. The full [roadmap](ROADMAP.md)
remains open; automatic warning acknowledgement is not human acceptance.
