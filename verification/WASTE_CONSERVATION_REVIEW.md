# Checkpoint 2N — waste thresholds and conservation

Review date: 3 October 2026. Baseline: `599694a`.

Dynamic waste threshold derivation now uses effective container capacity and fill
fraction after department stream overrides. Previously provenance showed the
overrides but the fallback calculation still read the global stream values. A
positive explicit threshold continues to take precedence.

The legacy waste generator now retains volume accumulated during an open period
when the poll lands after closing. It also retains fill if it cannot construct a
collection task, and increments its task count only when a record exists. Decimal
threshold equality uses the same relative 1e-12 tolerance as the dynamic path.
Dynamic threshold generation likewise retains volume when no collection record
can be represented, rather than consuming it for an invalid route.

## Independent calculations

| Case | Expected outcome |
| --- | --- |
| Global capacity 0.5 m³, fraction 0.8, no overrides | Threshold 0.4 m³; 1 m³ produces two collections and 0.2 m³ residual |
| Department capacity 2 m³, fraction 0.5 | Threshold 1 m³; 1 m³ produces one collection |
| Same department override, explicit threshold 0.25 m³ | Four collections from 1 m³ |
| Two compatible departments share a bin, each accrues 0.3 m³, threshold 0.5 m³ | One 0.5 m³ collection plus 0.1 m³ residual |
| Same departments have separate bins | No collections; each bin retains 0.3 m³ |
| Legacy rate 0.6 m³/hour, one open hour, threshold 0.2 m³ | Closing poll retains 0.6 m³; next opening produces three records, with no residual |
| Legacy or dynamic collection has an invalid destination | No task record; accrued volume remains available |

The legacy rate reference uses one bed and coefficient alpha 0.6, with beta and
gamma zero. This verifies that reference calculation, not the full coefficient
model. The shared-bin reference uses one stream, one route pair and consistent
container definitions. It does not establish a physical bin-return lifecycle.

Provenance now explains the effective arithmetic and retains the source histories
for capacity and fraction. The earlier global-only calculation test was changed
to assert the corrected independent expectation; the old screenshot in the
provenance review remains historical evidence.

## Import and input contracts

Plain editor import/save no longer replaces a legacy configuration with an enabled
modern Waste template or overwrites its default priority. Missing modern Waste
rules are disabled on import; new-project configurations retain their explicit
defaults. Explicit legacy enablement, disablement and priority survive save/reopen.
An enabled dynamic Waste rule still suppresses the legacy generator as before.

Raw checks now require supplied container capacity to be finite and positive,
and supplied fill fraction to be greater than zero and at most one. The checks
cover global stream definitions and applicable department/rule overrides. Numeric
strings remain accepted; zero, negatives, booleans and non-finite values are
rejected. Shared-container and initial-container flags require actual booleans.
Generation check dependencies now include global waste-stream definitions.

Ten option contracts record the applicable defaults, precedence and scope. The
legacy path still uses global container definitions; department capacity overrides
are a dynamic-generator feature. Editing legacy coefficients through the modern
demand dialog is not verified by the plain import/save acceptance test.

## Acceptance and review

Twelve tests in `tests/test_waste_conservation.py` cover the calculations, shared
versus separate accumulation, legacy closing polls, invalid-route conservation,
plain editor import/save and scalar rejection. Seventy focused regression tests
passed across generation, provenance, accumulation, physical payload references
and editor/export behavior. The full pack verifies the final source below.

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_waste_conservation -q
.\.venv\Scripts\python.exe -m verification.run --output verification/latest
.\.venv\Scripts\python.exe -m verification.smoke --config ltn.json --minutes 60 --output verification/latest/waste-conservation-ltn
```

The full pack passed **1,027 tests in 127.302 seconds**, with **zero broken evidence
links** and unchanged source hashes during execution. Local outputs are
`latest/waste-conservation-pack-build.txt` and `latest/evidence.json`.

Both bounded LTN runs completed four tasks with zero failures or pending tasks,
retaining the baseline outcome hash
`5368460ed4fd5fd466e832b82d3d6358977abfaccbb456d45e268cfb7c0ab474`.
Outputs are in `latest/waste-conservation-ltn/`. This establishes bounded regression
repeatability, not full LTN acceptance. Unrelated local `ltn.json` edits were preserved.

For manual review, use a copy of a dynamic waste project with global capacity
0.5 m³/fraction 0.8 and department overrides 2 m³/fraction 0.5. In Demand Preview's
effective settings, verify a derived threshold of 1 m³ and its explanation. Add
an explicit 0.25 m³ threshold and verify that it wins. Compare generated volumes
and residuals using the reference tests rather than inferring completed transport
from preview counts.

## Remaining limits and next action

Incompatible definitions within a shared group, multiple route-pair collections,
physical initial-container/return handling and legacy demand-dialog migration
remain open. Dynamic lifecycle callback scaffolding is not sufficient proof that
all physical collection cycles are connected correctly. Complete malformed legacy
coefficient validation also remains open. The engineering inventory gate is not
complete and narrow conservation tests do not establish these wider behaviors.

Next: verify shared-bin collection and return lifecycle, including failed pickup,
unreturned bins and conflicting group definitions, before claiming physical waste
conservation. Retain the later geometry, approved UI workflow and tutorial gates.
