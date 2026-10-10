# Configuration audit consolidation — slice 2X

Baseline: `70b031a`. This checkpoint strengthens the evidence pack and records
generation option dispositions. Simulator behaviour is unchanged.

## Reviewed scope

Thirty-one group and department option paths now have explicit partial contracts
linked to their previously reviewed base fields. The resolver starts from category
defaults and applies a group payload or a standalone department override. A group's
department membership suppresses the standalone override even when that group is
disabled. Global disable wins. Waste stream settings can apply later overlays.
Category-wide drop-off capacity policy is an explicit merge exception; it is not
assumed to behave like other fields.

Six acceptance tests exercise category, group and department layers. Independent
expectations include two 0.2 m³ events in an active hour at 48 events/day, return
release at 120 seconds with configured return fields, and a full-content exchange
with 8 consumed, 2 removed and 10 remaining. Other cases cover empty schedules,
global disable, invalid values in raw simulation and editor import, and the
category capacity-policy exception. Existing field-specific tests remain linked.
These representative cases do not establish every field combination, staff
workflow, calendar interaction or mixed-stock scenario.

Stale limitations now acknowledge the existing tracked-stock receipts and separate
direct-event and pooled-waste accounting. Their remaining boundaries stay explicit.

## Inspectable evidence

Source references now resolve actual qualified Python definitions and line numbers.
A matching comment or a method on the wrong class cannot satisfy a reference.
Missing definitions fail the pack's evidence-link gate. Tests exercise genuine,
missing and misleading references, and verify that passing tests cannot promote
partial or unreviewed dispositions.

Open `latest/index.html` and inspect **Configuration audit remaining**. The family
table separates reviewed from unreviewed paths and shows linked passing evidence.
`latest/audit-backlog.json` retains the exact outstanding paths. In the option
inventory, expand a group/department contract to inspect its related base contract,
precedence, limitations, source definition locations and test outcomes.

The inventory still observes defaults, examples, the local LTN project and explicit
contracts; source-key candidates are discovery aids. Container paths, per-day fields
and inherited settings are included. This is not an exhaustive schema, a missing
feature count or a completion percentage. AST resolution establishes that a
definition exists, not that its implementation meets the contract.

## Verification and next work

The full suite passed **1,150 / 1,150 tests in 133.902 seconds**, with **zero broken
evidence links** and unchanged source hashes during execution. The complete pack
took 136.085 seconds. Logs are in `latest/config-audit-pack-build.txt` and
`latest/tests.txt`; structured results are in `latest/evidence.json`.

The current inventory has **539 paths: 116 reviewed and 423 awaiting individual
review**. Reviewed dispositions are 106 partial, 8 verified within reference scope
and 2 unsupported. The largest remaining families are task generation (180), lifts
(41), departments (39), locations (36), robots (28) and simulation settings (20).
These counts include structural paths and remain scoped to the observed inputs.

The pack includes LTN load/check; the unchanged simulator does not require another bounded runtime
benchmark in this checkpoint. The previous bounded LTN result remains historical
evidence, not full LTN acceptance. Local `ltn.json` edits remain outside the commit.

Next: audit lift fields against existing resource/movement tests and independent
timing/capacity references. Continue robot, location and department dispositions
and workspace gaps before the geometry, approved CAD UI, tutorial and final
release gates. Partial generation contracts retain their stated open work.
