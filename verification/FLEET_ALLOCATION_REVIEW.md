# Initial fleet and charger allocation — slice 2AF

Baseline: `42921f6`. This checkpoint verifies distinct initial bay allocation and
charging-location resolution. Fifteen new tests and two option dispositions retain
explicit limits on physical parking and charging throughput.

## Corrections and changed results

Initial bay allocation was greedy. With robots R and Other, a shared bay followed
by an R-only bay could place R in the shared bay and leave Other at the location
point, even though both robots could be accommodated. Initial allocation now
finds a maximum matching between individual robot IDs and compatible bays. It
first maximises charger occupancy, then adds parking without losing occupied
chargers. Existing matches are changed only when an augmenting path needs them.
Configured location order, proximity within each location and bay order resolve
otherwise equivalent runtime choices deterministically.

The old validator counted compatible bays separately for each robot type. One
shared charger could therefore count for multiple types, and two R-1-only bays
could count for a two-robot R fleet. Project Checks now evaluates the whole fleet
with distinct bay identities, including the location in each identity. Same-named
bays at different locations are separate resources; duplicate charging-location
references do not create more resources.

An insufficient simultaneous initial charger allocation is reported as
`CHARGE_START_CAPACITY`, an acknowledgeable warning. It does not assert that every
operating fleet must have one charger per robot. Robots without a matched charger
can start in compatible parking bays, and robots without a bay retain the legacy
start at the first charging location point. This fallback is not physical parking
capacity. Locations without AMR bays have an explicit informational finding for
legacy location-level charging. Unknown charging locations are malformed references
and block running, including names that identify only corridor nodes.

Runtime and editor now share charging-location precedence: a nonempty modern list
or legacy comma-separated string, then `charge_location`, then the first location.
Names are deduplicated in effective resolution. Previously runtime ignored a CSV
string and treated an empty modern list differently from the editor. Explicit
malformed containers are rejected. Drafts may retain unresolved names for repair.
Location rename updates modern list/CSV and legacy charging references.

## Independent capacity references

| Fleet and bays | Expected allocation |
| --- | --- |
| R, Other; shared charger and R-only charger | Both on chargers: R → R-only, Other → shared |
| R, Other; one shared charger | One of two can start on a distinct charger; visible constraint |
| R-1, R-2; two R-1-only chargers | Only R-1 fits; R-2 remains without a bay |
| R; parking followed by a charger | R starts on the charger |
| R, Other; shared charger and R-only parking | Both placed: R → parking, Other → charger |
| Two robots; bay named Bay at A and at B | Two distinct spaces, one robot at each location |
| Zero robots | No charging-space requirement |
| No explicit AMR bays | Legacy location-point starts, explicitly identified |

The matching algorithm is also checked against an independent exhaustive oracle:
all **512 three-robot/three-bay compatibility graphs**, each with all **8 possible
charger/parking splits** (**4,096 cases**). The oracle enumerates every possible
placement, including unplaced robots, rejects duplicate bay use and calculates the
best charger count followed by total placed robots. Each result matches the
production algorithm. Separate references cover deterministic tie handling,
invalid seed assignments, reference errors, renaming and stale findings.

This establishes the stated matching objective. It does not establish a physically
reachable parking manoeuvre, queue capacity, sufficient energy or operational
charging throughput.

## Verification evidence

Initial reproductions are in `latest/fleet-allocation-before.txt`. The focused
fleet, storage, robot, charging, editor and Project Checks suites passed **128
tests**. The full suite passed **1,260 / 1,260 tests in 135.679 seconds**, with
**zero broken evidence links** and unchanged source hashes. Logs are retained in
`latest/fleet-allocation-focused.txt`, `latest/fleet-allocation-pack-build.txt`
and structured `latest/evidence.json`.

Both 60-minute LTN demand-window runs completed four tasks with none failed or
pending. Initialisation took 1.449 and 1.439 seconds. Source/input checksums were
unchanged and both retained outcome hash
`5368460ed4fd5fd466e832b82d3d6358977abfaccbb456d45e268cfb7c0ab474`.
Results are in `latest/fleet-allocation-ltn/`; this bounded regression does not
establish full LTN acceptance or an agreed performance threshold.

## User verification

1. In a project copy with two robot types, define one shared charger bay and one
   bay restricted to the first type. Confirm both receive distinct starting bays,
   leaving the shared bay for the second type.
2. Remove the restricted bay. Confirm Project Checks reports one of two robots
   can start on a distinct charger, and allows a run only after warning acknowledgement.
3. Restrict two bays to one explicit robot ID in a two-robot type. Confirm they
   are not counted as providing a compatible bay for the other robot.
4. Rename a charging location and reopen/check the project. Confirm list, CSV and
   legacy references still identify it. Try an unknown name and confirm a blocking
   reference finding.

## Limits and next work

Matching applies at initial placement. Live charging and return dispatch retain
their existing serial reservation/arrival checks; they do not globally reshuffle
all parked robots. Initial stale occupancy markers retain their existing cleanup
semantics and are not a physical stock-seeding interface. Compatibility uses the
existing rectangular envelope and tolerance, not swept geometry. Unmatched robots
can still share the location point in acknowledged/legacy scenarios.

The exhaustive reference is deliberately small and proves the matching objective,
not all large-project runtime/memory limits. Complete physical parking, charging
queue/throughput, long mixed-workflow conservation and performance acceptance
remain open. Next finish location outlines and remaining input contracts, then
continue the department and workspace gaps. Geometry, approved graph-focused CAD
UI, tutorial and release gates retain their planned order. The unrelated
`ltn.json` edit remains outside this checkpoint.
