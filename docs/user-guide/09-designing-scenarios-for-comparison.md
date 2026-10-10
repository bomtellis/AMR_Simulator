---
title: Scenario comparisons
nav_order: 3
parent: Investigate and report
---
# Designing scenarios for comparison

Define the operational question and an acceptable outcome before changing the
model. For example: can a larger fleet reduce late deliveries without excessive
lift waits, or can clean/dirty permissions be maintained with shared lifts?

## Keep a baseline and change one assumption

Save a named baseline project and complete a checked run. Inspect its demand,
failures, pending work and movement before creating alternatives. Use **File →
Save project as** to make separate variant projects and retain each external
results folder. Project revisions help compare configurations but do not replace
the run's frozen inputs.

Use names such as `Baseline`, `Fleet-6`, or `Dedicated-clean-dirty-lifts`.
Record the question, changed assumptions, intended service targets and accepted
warnings in a companion study note. Do not rely on a proposed future field or
launcher feature to retain the comparison's intent.

## Compare like with like

Unless it is the change being tested, retain the same start/end demand window,
active dates, department demand, generator/group rules, initial stock,
payload dimensions, drawings/scale, route graph, staff calendars, simulation
mode, software revision and reporting method.

Build Demand preview for both variants and reconcile the expected releases.
An accidental change in demand can make a fleet improvement look larger or
smaller than it is. Runtime returns must also be reconciled in saved-run evidence.

## Run and review each alternative

1. Save, rerun current checks and inspect the warnings for the variant.
2. Use **Save, check and simulate** and retain the completed revision-bound run.
3. Investigate task outcomes and supporting events, then inspect Playback.
4. Generate comparable report sections from each run's frozen inputs.
5. Compare service/SLA outcomes, failed and pending work, request times, peak
   lift/dispatch waits, fleet utilisation, charging and resource pressure.

Do not choose a fleet only because average utilisation looks attractive. Failed
tasks can artificially reduce measured workload. A short demand window may
omit the peak or late-return workload you intended to test.

## Explain the conclusion and its limits

Keep the changed assumptions, source revision, run identities and evidence limits
with each conclusion. Stress-test uncertain demand, travel, handling and charging
assumptions. Rerun a proposed fleet rather than treating a sizing estimate as a
guarantee. Staff-assisted handling is not full porter-led transport and cannot
establish a like-for-like porter/AMR comparison on its own.

For relocation studies, use [lift planning](../reference/lift-planning.md) and
review service guards across all evaluated floors/flows. A distance reduction
alone is not an acceptable operational or structural design.
