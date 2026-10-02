# Project checks review gate — 2 October 2026

This checkpoint adds structured preflight to the existing editor and launcher.
It does not complete the broader feature inventory or the unified application.
The preceding committed checkpoint is `cf0827f`; the original rollback point is
`07a059a`.

## Delivered

- A persistent editor dock with severity and text filters, explanations,
  consequences, setting paths, affected-object navigation and JSON export.
- Non-mutating checks for section shapes, identifiers, selected numeric values,
  schedules, references, static directed connectivity, profile allowances,
  payload/AMR compatibility and drawing availability.
- A stale indicator after edits; stale findings cannot be exported or used to
  navigate. Rerunning checks clears earlier warning acknowledgements.
- Launcher preflight that blocks detected invalid input and requires warning
  acknowledgement. Saved run inputs and findings share a configuration hash;
  the manifest also records the exact input file hash.
- Acceptance tests for intentional constraints, malformed inputs, profile
  unions, stale acknowledgement, UI navigation, cancelled launches, changes
  during review and preservation of the checked run input.

## LTN finding requiring modeller review

The `LINEN-D26-SHARED-WASTE` group stores `D26-LINEN` in both its single and list
destination fields, but that location does not exist. These produce two warnings
with distinct setting paths. The generator can replace group destinations with
department assignments. Preflight does not yet resolve effective generation
precedence, so it neither claims a failed service nor silently repairs the rule.
LTN is unchanged. Inspect this group and the D26 department assignments during
review; the next Demand preview stage should expose the effective destination.

## Verification and scope

The generated `latest/index.html` and `latest/evidence.json` contain current test
results and source fingerprints. `latest/ltn-project-checks.json` contains the
raw-input LTN findings with no implied user acknowledgement. The checks dialog
was rendered locally and inspected at 1000 × 720; Windows display scaling and
real keyboard use still need user verification.

The checker deliberately remains partial. It does not prove all option semantics,
effective demand, resource contention, loaded paths, swept geometry, or all lift
compatibility. Existing legacy diagnostics may lack a precise navigation target.
All checks invalidate together, and external drawings are rechecked on request.
The editor checks its in-memory model; launcher preflight checks raw saved JSON.
Direct CLI runs retain existing behaviour. The launcher's pre-existing fixed
workspace location remains a portability limitation for the unified-project stage.

## User verification gate

Follow the five manual checks in `README.md` under **Project checks checkpoint**.
Pause implementation here for user review before proceeding to Demand preview.
