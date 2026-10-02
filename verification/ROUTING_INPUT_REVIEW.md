# Checkpoint 2B — routing input validation

Review date: 3 October 2026. Baseline: `0c535fa`.

Project checks, editor import and simulation construction now share routing-input
validation before normalisation. Errors identify the affected JSON path. Invalid
input is not silently converted or saved; the input dictionary remains unchanged.

| Input | Previous behaviour | Corrected behaviour |
| --- | --- | --- |
| `has_door: "false"` | The nonempty string became true. | Reject; use the JSON boolean `false`. |
| String/number/null `auto_connect` or `bidirectional` | Truthiness could enable linking or reverse routes. | Reject; require an actual JSON boolean. |
| Opening of 0.05 m | Silently enlarged to 0.1 m. | Preserve 0.05 m; block a route requiring 0.07 m. |
| Explicit zero, negative, boolean, null, nonfinite or nonnumeric width | Could be clamped or replaced by a default. | Reject before editor normalisation or simulation. |
| Omitted flag or width | Documented defaults applied. | Defaults remain unchanged. |
| Numeric string width such as `"0.05"` | Accepted through numeric conversion. | Retained for compatibility; parsed width stays 0.05 m. |

The width correction applies to corridor widths, node door openings and both
building defaults. The current lane-capacity approximation also retains the actual
width. This does not introduce verified directional lanes or swept geometry.

## Evidence

The complete suite passed **902 tests in 125.993 seconds**. The five new tests in
`tests/test_routing_input_validation.py` first reproduced 51 failing subcases.
They exercise invalid flags and widths through all three entry paths, unchanged
source input after rejection, small defaults and explicit dimensions, the
0.05/0.07 m boundary, valid booleans and numeric-string compatibility.
The final evidence-pack build also passed **902/902 tests in 123.985 seconds**,
with zero broken evidence links. A headless file-open integration check confirmed
the original editor project survives rejection and the dialog names the invalid
field; its result is retained in `latest/routing-input-import.json`.

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_routing_input_validation tests.test_routing_contracts -q
.\.venv\Scripts\python.exe -m verification.run --output verification/latest
```

LTN's one-hour demand horizon still completes four tasks with no failures or
pending tasks in both runs. Its outcome hash is unchanged from checkpoint 1:
`5368460ed4fd5fd466e832b82d3d6358977abfaccbb456d45e268cfb7c0ab474`.
The source project is not saved by these checks. Local outputs are retained in
`latest/routing-input-ltn/` and `latest/routing-input-full.txt`.

## Compatibility and review

Existing valid routing inputs retain their outcomes, except widths below 0.1 m
now retain their physical value and may correctly block previously permitted
travel. Invalid explicit flags/widths must be corrected; there is no silent
string-to-boolean migration. Already saved values enlarged by older versions
cannot be reconstructed from that file alone.

Some interactive width controls still enforce a 0.1 m entry minimum. This remains
an editor consistency item; smaller imported widths are no longer enlarged.
The shared validator covers routing scalars only, not the complete configuration
schema or every effective generation input.

For review, use a copy of a reference file: set a routing flag to the string
`"false"` and confirm the named import error; change it to the boolean `false`
and load again. The editor's failure path leaves the current project in place.
The numerical 0.05/0.07 m reference is a boundary test, not a realistic AMR design.

Next: continue the option audit through generation precedence, calendar boundaries
and return policies. The full inventory, geometric traffic and approved UI/tutorial
sequence remain open.
