# Explicit container identity — review checkpoint

**D029:** ordinary outbound tasks could recreate an explicit container ID even
while the original object was stored elsewhere or in transit. Two journeys could
also promise to create the same ID before either picked it up. These cases could
produce duplicate movements while the final inventory displayed only one object.

Registration now remains distinct from physical issuance. A route can exclusively
claim the first creation of an explicit ID, and a batch cannot create it twice.
After physical pickup or seeded storage, ordinary tasks must collect the existing
object from its current location. In-transit, removed and unconfirmed objects
cannot be recreated. Estimates remain non-mutating; rejected commits restore
creation claims, and task failure before pickup releases them. Failure after
pickup leaves the issued identity intact. Generated IDs avoid registered explicit
IDs. Project checks block conflicting payload types for the same task-specified ID.

Internal same-bin service and staged-equivalent return continuations retain their
existing policies. This checkpoint does not add a physical staging area or a
recovery operation for missing containers.

## Review project

Open [explicit-id-reuse.json](scenarios/explicit-id-reuse.json), save a disposable
project and simulate. All three tasks use ordinary outbound settings and name
`BOX-1`. There is one robot; A–B is 10 m, speed is 2 m/s, loading and unloading
take 2 seconds each, and congestion slowdown is explicitly zero. Deferral is
limited to **10 seconds** (one sixth of a minute).

| Task/action | Independent expectation |
| --- | --- |
| DELIVER released at 0 | Creates BOX-1 at pickup time 2; arrives at B at 2 + 10/2 + 2 = **9 seconds**. |
| DUPLICATE released at 1 | Cannot recreate BOX-1 at A. It remains unassigned and fails at its original deadline, 1 + 10 = **11 seconds**. |
| REUSE released at 10 | Collects the existing box at B at 12; arrives at A at 10 + 2 + 10/2 + 2 = **19 seconds**. |
| Final totals | **2 completed, 1 failed**, one physical issued identity stored at A, two paired payload transfers. |

Expected tracking conflicts, unpaired exits and unconfirmed arrivals are all zero.
Before the fix, DUPLICATE could create the same ID again. Legitimate later reuse
remains allowed when the object is physically available at the requested source.

## Evidence and limits

Seventeen tests cover duplicate batch creation, competing robots, location and
transit restrictions, direct pickup protection, ordinary reuse, rejected commits,
failure before/after pickup, definition order versus release order, read-only
estimates, generated-ID collisions, conflicting types and empty-journey IDs. The review project is
tested both raw and editor-normalised. Before-fix evidence records six failures
from eight initial tests at baseline `a619600` in
`baseline/explicit-payload-identity-before-fix.txt`.

The final evidence pack passes **476/476 tests**, with zero broken feature-to-test
links. The saved reference run preserves inputs and reconciles completed/failed
task records against events. Its movement check confirms two paired transfers
and zero conflicts/unpaired exits. See `latest/explicit-id-reuse-reference/`.

The six-hour LTN regression completes **203 tasks with zero failed or pending**,
retaining detailed outcome hash
`21cd7e6d1fe83f255ab425307acd0fd1f830f4aa155412eba1767b3996fcf0f6`.
It took 16.06 seconds; see `latest/ltn-explicit-identity-final/summary.json`.
The final preflight-only empty-journey adjustment was included in the full test
pack after that simulation run; it does not change simulation behavior.

Planned IDs remain in the existing known-instance registry before physical
issuance. Population reports still need a complete lifecycle audit to distinguish
planned, issued, stored, carried, staged and removed objects. The new issued-ID
set protects runtime identity but does not complete that reporting work. Explicit
staging capacity, staged-empty recovery after return failure, delivery/lift energy
attribution and operational-failure reconciliation also remain open.

The full [roadmap](ROADMAP.md) remains open. The earlier unexplained preview
interruption is recorded in `baseline/multi-stop-verification-observation.txt`.
Automated warning acknowledgement does not constitute human acceptance.
