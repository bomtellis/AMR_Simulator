# Storage capacity and rejected route plans — review checkpoint

Multi-stop deliveries now require a distinct compatible free bay for each strict
delivery before the batch is committed. A failed batch leaves its touched route,
bay and lift reservations unchanged, along with lift operating state, energy and
impact counters. An old task assignment cannot overwrite another active bay claim.

A temporarily full compatible bay now causes waiting. A later collection can
release capacity; the original task deferral deadline still applies. With no
deadline and no future collection, the delivery remains pending. A bay that cannot
fit the payload is still a terminal incompatibility.

## Three projects to review

Open each JSON below, save a disposable `.amrproj`, run it and inspect Results
investigation and the payload monitor. The examples have two boxes, one two-slot
AMR and a destination B with finite storage. Both deliveries are released at zero.

| Project | Expected result and independent capacity reasoning |
| --- | --- |
| [One bay with returns](scenarios/storage-return.json) | Four completed tasks: two deliveries plus two returns; no failures. Each delivery must wait for its own free bay. Final stock is two boxes at A and zero at B. |
| [One bay without returns](scenarios/storage-timeout.json) | One completed delivery and one failure at 60 seconds: one bay holds one box and nothing removes it. The one-minute deferral deadline is measured from release, not from each retry. |
| [Two bays](scenarios/storage-two-bays.json) | Two completed deliveries in one shared AMR journey, with two distinct occupied bays at B and no failures. |

In the timeout case, the wait record should identify T2 and the full storage at B.
It describes the reason observed at the start of the assignment wait; it is not
an additive attribution of the entire interval to one resource. Local bay
manoeuvres contribute time, so these cases establish capacity and outcome counts,
not an independent acceptance of manoeuvring durations.

The saved-project reference runs are in `latest/storage-return-reference/`,
`latest/storage-timeout-reference/` and `latest/storage-two-bays-reference/`.
Their frozen inputs, external results and summaries reconcile. Automated warning
acknowledgement in these runs does not record your review or acceptance.

## Defects and acceptance evidence

- **D017:** two tasks could independently estimate the same free bay, and a stale
  assignment could overwrite another task's claim. Batch matching now allocates
  distinct bays, rearranging compatible choices when needed. Strict deliveries
  take precedence over optional overflow use of bays.
- **D018:** rejected multi-stop commits could leave reservations, lift wear or
  failure state, or energy consumption behind. A journal restores touched state
  on rejection or exception; successful commits retain their changes.
- **D019:** a full compatible bay was classified as permanently impossible,
  failing a delivery before a pending return could free it. Waiting now follows
  the original timeout policy, while physical incompatibility still fails.

Seventeen acceptance tests cover these cases, including insufficient battery,
cross-floor lift wear/failure state, an injected late exception, preservation of
older reservations, successful retry, a three-bay matching problem, overflow,
disabled capacity, finite and unlimited waits, and raw/editor-normalised review
projects. Before-fix failures are retained in
`baseline/reservation-atomicity-before-fix.txt` and
`baseline/storage-wait-before-fix.txt`.

The full local verification pack passes **397/397 tests**, with zero broken
feature-to-test evidence links. Regenerate it with
`.venv/Scripts/python.exe -X faulthandler -m verification.run --output verification/latest`.

The six-hour LTN run completes **203 tasks, zero failed and zero pending**. Detailed
outcomes retain hash
`21cd7e6d1fe83f255ab425307acd0fd1f830f4aa155412eba1767b3996fcf0f6`.
Input preservation and summary/event reconciliation pass; this run took about
14 seconds on this machine. See `latest/ltn-storage-reservations/summary.json`.

## Remaining limits

The subsequent [individual/charging checkpoint](SINGLE_CHARGE_ROLLBACK_REVIEW.md)
extends the transaction to single-task, idle-return and charging-route plans.
Joint claims on physical empty bins during exchanges still need their own
failure-path audit. Capacity matching does not search future bay
release times or every interleaved pickup/delivery order. Preliminary estimates
still omit some local manoeuvring costs and need a separate accuracy audit.

This work does not implement geometric lanes, swept turns or a new clean/dirty
classification: access remains defined by route profiles. The earlier unexplained
background-preview process interruption remains an observation in
`baseline/multi-stop-verification-observation.txt`, not a repaired defect.
The complete [roadmap](ROADMAP.md) remains open.
