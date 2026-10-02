# Checkpoint 2A — routing and door option audit

Review date: 3 October 2026. Baseline: `f52631b`.
Follow-up: [slice 2B](ROUTING_INPUT_REVIEW.md) corrects the routing boolean and
width-coercion defects identified here. The findings below are the historical audit.
This is the first bounded slice of checkpoint 2. It improves acceptance coverage
and traceability; it does not close the full configuration inventory.

## What changed

Sixteen option contracts now record units, intended behaviour, precedence,
runtime defaults, editor/import behaviour, validation, limitations, source symbols,
support disposition, review date and acceptance-test links:

- Automatic connection; edge distance, width and direction.
- Door enablement and opening; building corridor and door width defaults.
- Profile node, edge and lift permissions.
- Task node, edge and lift additions; outbound and return profile selection.

Expand a setting's **Contract and acceptance evidence** section in the generated
[verification pack](latest/index.html). Search for `door_clear_width_m`,
`auto_connect` or `route_profile` to review the audited options. The same data is
retained in `latest/options.json` and `latest/evidence.json`. Stale option test
patterns now fail the evidence build, as stale feature test patterns already did.
A partial contract is not promoted by passing reference cases.

The inventory distinguishes **reviewed contracts**, earlier **documented
descriptions**, and **observed fields requiring semantic review**. Its outstanding
count now includes earlier descriptions that lack an individual traced review.
An increased outstanding count therefore does not imply lost functionality.
Discovery remains example/default based plus source-key candidates; it is not yet
an exhaustive schema of every runtime input.

## Independently specified acceptance cases

The complete evidence build passed **897 tests in 124.714 seconds**, with **zero
broken feature or option evidence links**. All tested source hashes remained
unchanged during the build. The inventory currently contains 526 observed or
documented paths, of which 16 have individual traced reviews; the remaining 510
still need that level of review. These are option paths, not missing-feature counts.

The new tests cover default door opening 0.9 m, explicit building/node override,
default corridor width 2.4 m, explicit edge override, disabled/missing door flags,
and the minimum of adjacent door openings in both directions. A door cannot widen
a narrower corridor. Node and directed-edge permissions both apply; a permitted
profile cannot override a narrow door or silently use another profile's branch.
Raw invalid numeric widths produce blocking findings before normalisation.

One test exposed a documentation defect: new blank editor projects explicitly set
`corridors.auto_connect=false`, but **importing a file with this field omitted
retains the omission**. The simulator then uses its default `true`. The contract
previously described these as if every editor-loaded file received the new-project
default. The corrected test distinguishes raw omission, imported omission, a new
blank project and explicit false. No runtime behaviour was changed in this slice.

Run the focused checks with:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_routing_contracts tests.test_verification_evidence -q
```

Rebuild all test results and linked evidence with:

```powershell
.\.venv\Scripts\python.exe -m verification.run --output verification/latest
```

The pack now also links checkpoint 1's local-route safety and software-fingerprint
tests to explicit feature entries. No application code or simulation policy was
changed in checkpoint 2A; existing local `ltn.json` edits remain untouched.

## Unresolved validation and support boundaries

| Finding | Current behaviour | Next work |
| --- | --- | --- |
| Routing boolean strings | Values such as the string `"false"` can be treated as true by loader truthiness. Valid JSON booleans are the supported reference inputs. | Decide a consistent reject/explicit legacy-conversion policy and enforce it before editor normalisation and simulator use. |
| Small/invalid widths | The loader clamps widths below 0.1 m; zero-like values may use defaults. Raw checks reject nonpositive/nonfinite values but allow positive sub-0.1 m widths. | Align input validation, documented admissible ranges and loader behaviour; retain exact invalid-input evidence. |
| Import normalisation | An invalid raw value can be clamped or converted before later checks see it. | Audit the load/check boundary so malformed input is not silently legitimised. |
| Route-profile interactions | Ordinary loaded and return paths, shared membership and onboard intersections have reference cases; broader seeded/runtime combinations remain open. | Continue independent generation/return acceptance coverage. |

These limitations remain explicit in each affected contract. This audit does not
claim verified keep-right lanes, loaded swept footprints, turning radii or a
physical clean/dirty state. Shared access is membership in applicable route
profiles, not a competing classification system.

Read-only reproduction confirmed that `has_door="false"` becomes true and a
0.05 m opening becomes 0.1 m; neither raw input currently produces a blocking
Project checks finding. These observations identify defects to close next,
not acceptable physical modelling assumptions.

## User review and next slice

Review the expanded option details and the distinction between a new project's
defaults and imported omissions. The next bounded slice addresses the routing
input-validation findings above, before expanding the option audit to generation
precedence, schedules, returns and resource contention. Final UI rework and the
tutorial remain after the core-feature gate.
