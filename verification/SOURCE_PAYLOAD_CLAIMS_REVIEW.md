# Existing source-container ownership — review checkpoint

**D028:** a source availability check could pass for multiple journeys without
claiming the container. Competing tasks could both be assigned before pickup;
a batch could promise two pickups of one physical object. One task then failed
at pickup instead of waiting for stock under its original deadline.

Tasks requiring existing stock now reserve distinct source containers when a
route commits. Read-only estimates do not reserve or bind stock. Exact identities
and empty-only pickups take precedence over flexible pickups. Flexible pickups
prefer full containers when empties are needed for exchange. A source pickup and
an empty exchange cannot promise the same object. Rejected commits restore task
bindings, resource state and previous claims; failure before pickup releases the
task's claim. Claims do not move stock: the existing action events do that.

## Review one box with competing collectors

Open [source-one-box.json](scenarios/source-one-box.json), save a disposable
project and simulate. This extends the previous wash-timing reference with a
third robot and a second collector. A–B is 10 m, speed is 2 m/s, loading/unloading
takes 2 seconds per action, and B requires a 60-second wash at B. Both collectors
request the same `BOX-1` at 10 seconds. Deferral is limited to 60 seconds.

| Observation | Independent expectation |
| --- | --- |
| DELIVER pickup and arrival | Pickup at 2; arrival at B at 2 + 10/2 + 2 = **9 seconds**. |
| DELIVER completion | Arrival plus wash: 9 + 60 = **69 seconds**. |
| COLLECT assignment | **10 seconds**, while DELIVER is still washing. |
| COLLECT pickup | 10 + empty approach 5 + loading 2 = **17 seconds**. |
| COLLECT arrival at A | 17 + loaded travel 5 + unloading 2 = **24 seconds**. |
| COLLECT completion | 24 + travel to B for washing 5 + wash 60 = **89 seconds**. |
| COMPETING-COLLECT | Never assigned; original deadline 10 + 60 = **70 seconds**, then fails for unavailable stock. |
| Totals | **2 completed, 1 failed**, one known physical box, two paired physical transfers. |

There should be no tracking conflicts, unpaired exits or unconfirmed arrivals.
The spare robot cannot collect an already claimed box. This is source ownership
verification; it does not verify wash-area capacity. Automated evidence is in
`latest/source-one-box-reference/`.

## Automated evidence and scope

Sixteen tests cover exact and anonymous sources, distinct batch bindings,
opposite pickup order, empty-only rules, exchange interactions, foreign and
pre-existing claims, rollback, failure cleanup and reuse. A separate reference
moves one box A→B→A→B, with arrivals at **9, 19 and 34 seconds** and one physical
identity throughout. The review project is tested raw and editor-normalised.
Before-fix evidence is in `baseline/source-payload-claims-before-fix.txt`:
six failures from eight initial tests at baseline commit `e3fc9cd`.

The full verification pack passes **459/459 tests**, with zero broken evidence
links. The saved reference preserves frozen inputs, reconciles completed/failed
task records and events, and confirms two paired transfers with zero tracking
conflicts or unpaired exits; see `latest/source-one-box-reference/summary.json`
and `movement-check.json` in that directory.

Six-hour LTN remains **203 completed, zero failed and zero pending**. Its detailed
outcome hash remains
`21cd7e6d1fe83f255ab425307acd0fd1f830f4aa155412eba1767b3996fcf0f6`.
The run took 14.59 seconds; see `latest/ltn-source-claims-final/summary.json`.
This unchanged bounded result does not imply that projects with competing source
pickups will retain their previous outcomes.

This scope covers `is_return_task` and `requires_existing_payload_instance`.
The existing `creates_new_payload_instance` override remains. Ordinary outbound
tasks may create new stock at source; explicit-ID collision/reuse rules in that
path still need correction and independent tests. Do not interpret this checkpoint
as universal physical-identity conservation. Generated shared-container binding
retains its existing empty-container policy.

Staged-empty recovery after return failure, explicit staging capacity, delivery
lift-energy attribution and operational-failure reconciliation remain open.
Unconfirmed arrivals still indicate missing evidence, and robot plans are not
recomputed after an in-transit failure. The full [roadmap](ROADMAP.md) remains open.
The earlier unexplained preview interruption remains documented in
`baseline/multi-stop-verification-observation.txt`. Automated warning acknowledgement
does not constitute human acceptance.
