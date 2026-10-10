# Physical pickup, arrival and exchange timing — review checkpoint

Inventory now changes at scheduled pickup and drop-off actions, independently of
journey completion. This applies to individual tasks and each batch member.
Completion fallbacks are idempotent and do not repeat stock movements.

**D026:** movements were usually applied at journey completion, with log times
backdated to pickup/drop-off. Source stock could remain available after pickup;
destination stock could remain unavailable during a later wash or batch leg.
Action events now change live stock and reassess waiting work at the proper time.
Exchange empties remain claimed in their bays until outbound arrival, then are
staged for return. Failure after pickup records `payload_arrival_unconfirmed`;
source stock is not recreated and destination arrival is not invented. Failed
batch members cannot later complete.

**D027:** deliveries without returns could consume an empty bin merely to free
its bay. Equivalent-bin exchange now requires an enabled return of the same
payload type; a blank return-payload setting uses the outbound type. Otherwise,
delivery needs ordinary free storage. Same-bin service keeps its separate policy.

## Stock available while a delivery robot washes

Open [payload-before-wash-completion.json](scenarios/payload-before-wash-completion.json),
save a disposable project and simulate. Two robots share one physical box,
`BOX-1`. A–B is 10 m, speed is 2 m/s, each load/unload takes 2 seconds, and B
requires a 60-second wash at B. These are model times, not equipment measurements.

| Action | Independent expectation |
| --- | --- |
| First pickup | Box leaves A at **2 seconds**. |
| First delivery | 2 + 10/2 + 2 = **9 seconds**, when the box becomes available at B. |
| First journey completion | Washing ends at 9 + 60 = **69 seconds**. |
| Second assignment | COLLECT starts at its **10-second release**, while the first robot is still washing. |
| Second delivery | Empty approach 5 + pickup 2 + loaded travel 5 + drop-off 2 = 14 seconds after release; the box reaches A at **24 seconds**. |
| Second journey completion | Return to B's configured wash location, then wash: 24 + 5 + 60 = **89 seconds**. |

Expect two completed tasks and two paired transfers, with no failures, unpaired
exits or tracking conflicts. Evidence: `latest/payload-before-wash-reference/`.
This case verifies stock availability, not wash-area capacity.

## A delivery without a return preserves empty stock

Open [no-return-keeps-empty-stock.json](scenarios/no-return-keeps-empty-stock.json).
The only destination bay contains one empty, with no return or collection to
remove it. Expect **zero completions and one timeout at 60 seconds**. The original
empty remains stored and there are no physical transfers. Evidence:
`latest/no-return-stock-reference/`. A separate test confirms that a free second
bay allows delivery without consuming the empty in the first bay.

## Evidence and remaining limits

Ten tests inspect live stock between events, wash/batch timing, exchange stock
before arrival, no-return capacity, idempotency and failure after pickup. Both
review projects are tested raw and editor-normalised. Before-fix failures are in
`baseline/payload-action-timing-before-fix.txt`.

The full pack passes **443/443 tests**, with zero broken feature-to-test links.
Saved-project examples preserve inputs and reconcile task summaries with events.
Six-hour LTN remains **203 completed, zero failed and zero pending**, retaining
detailed outcome hash
`21cd7e6d1fe83f255ab425307acd0fd1f830f4aa155412eba1767b3996fcf0f6`.
The final run took about 15 seconds; see
`latest/ltn-payload-action-timing-final/summary.json`. Inventory-dependent projects
may change results even though this bounded LTN window does not.

Explicit staging geometry/capacity after arrival and recovery of staged empties
after a return fails remain open. Unconfirmed arrival is missing evidence, not
proof of loss or recovery. Robot movements and resource reservations are not yet
replanned after an in-transit failure. Arbitrary pre-existing source-instance
claims, delivery/lift energy attribution and operational-failure reconciliation
also need further cases. Old logs cannot reconstruct missing live-state changes.

The full [roadmap](ROADMAP.md) remains open. The earlier unexplained preview
interruption remains in `baseline/multi-stop-verification-observation.txt`.
Automated warning acknowledgement does not record human acceptance.
