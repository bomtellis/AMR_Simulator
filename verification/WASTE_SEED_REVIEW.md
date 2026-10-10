# Checkpoint 2P — initial bins follow resolved demand

Review date: 3 October 2026. Baseline: `8eec034`.

Initial bins for modern Waste services now use the same resolved definitions as
generated demand. Previously seeding independently read raw department fields,
so inherited pickup locations, shared-group identifiers and initial-presence flags
could produce missing, misplaced or unused physical bins. A disabled contributor
could also choose the type of a shared bin before an active contributor was seen.

The first reproducing run had five failing tests and one error across seven tests.
The errors included the previous shared-definition check treating a disabled
department as an active contributor. The final acceptance module has eleven tests.

## Effective initial-stock behavior

Modern Waste uses the existing category/group/department/stream resolver. There is
no second implementation of override precedence in the seed path. The generator
manager is constructed before initial waste bins are created, so incompatible
active shared definitions reject initialization before choosing a physical bin.

| Setting or condition | Verified initial-stock outcome |
| --- | --- |
| Category pickup A; no duplicate raw department pickup | One bin at A and two successful collection/return cycles |
| Group overrides route to B → A; obsolete raw pickup A remains | Bin starts and returns at B |
| Category initial presence false; stream field omitted | No initial stock; ordinary collections issue their own payloads |
| Stream presence true; category false | Stream override wins; one physical bin completes both cycles |
| Group supplies shared ID; stream field omitted | Seed and tasks use the same inherited shared identity |
| Disabled stream or department appears first with another payload | It cannot choose the active shared bin type or cause a shared-definition conflict |
| Enabled modern category with disabled group, or global generation disabled with a declared enabled modern service | No modern rule-owned bin or task is created |
| Automatic shared stream has pickup list A,C | One bin uses the full `pickup:General:A,C` identity; both collection/return cycles preserve it |
| A cannot fit the shared bin; C is the next configured pickup | The bin starts at C and returns to C through both cycles |
| No configured pickup can fit an initial bin | No bin or replacement is fabricated; both collections expire at their deferral limits |

Shared bins use the first viable pickup in the resolved input order. Group
deduplication happens before claiming another inventory space, so a repeated
contributor does not temporarily claim and clear an unrelated bay. Nonshared
department seeds retain their existing location suffix for compatibility.

Initial stock is not inferred from a task count. Tests compare physical identity
sets, locations, completion/failure counts and initial events. Category pickup
inheritance is also verified through plain editor import. The earlier wrong-group
reservation test now explicitly adds its second department to the active service;
an unassigned department no longer supplies stock to a modern Waste service.

## Compatibility boundary

An enabled modern Waste definition owns initial bins through its resolved active
instances, including when the global generation switch temporarily disables it.
If no modern Waste category/group/department rule is enabled, the legacy/custom
seed adapter remains in use. Existing custom services carrying waste metadata and
legacy department waste still use raw department seed definitions. This is an
explicit compatibility boundary, not a claim that those paths share modern
inheritance. Broader legacy migration requires separate acceptance tests.

Disabling a department now excludes it from active shared-definition conflicts.
Its calendar behavior already prevents generation; the change aligns validation
and seeding with that behavior. This does not validate every malformed enabled flag
or every non-waste department option.

## Verification and manual review

Eleven tests in `tests/test_waste_seed_resolution.py` cover the table. The focused
run passed **48 tests in 0.954 seconds**, including previous shared-bin, physical
payload-conservation and waste-threshold references.

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_waste_seed_resolution -q
.\.venv\Scripts\python.exe -m verification.run --output verification/latest
.\.venv\Scripts\python.exe -m verification.smoke --config ltn.json --minutes 60 --output verification/latest/waste-seed-ltn
```

The full pack passed **1,053 / 1,053 tests in 127.718 seconds**, with **zero broken
evidence links** and unchanged source hashes during execution. The inventory still
has 457 unreviewed option entries; this is an audit count, not a missing-feature count.
Evidence files are
`latest/waste-seed-before.txt`, `latest/waste-seed-focused.txt`,
`latest/waste-seed-pack-build.txt` and `latest/evidence.json`.

Both bounded LTN runs completed four tasks with zero failures or pending tasks,
retaining outcome hash
`5368460ed4fd5fd466e832b82d3d6358977abfaccbb456d45e268cfb7c0ab474`.
Outputs are in `latest/waste-seed-ltn/`. This is bounded regression evidence, not
full LTN acceptance. Unrelated local `ltn.json` edits remain unchanged and excluded
from the commit.

For manual review, make a copy of
[the shared-bin reference](scenarios/shared-bin-return.json). Remove department
`waste_pickup_locations`; leave category pickup A. Both collection/return cycles
should still complete, with the same single bin returning at 336 seconds. Then
remove the stream's `shared_container_group` and set the group payload override to
`shared_container_group: INHERITED`; verify one physical identity remains through
both cycles. Use full event evidence, not Demand Preview counts, for this review.

## Remaining work

Threshold volume is consumed when a collection record is generated. Reconcile
that volume against completed, failed and pending physical collections and residual
stock next. Multi-pair waste-volume accounting and tracked-item consumption remain
open; successful identity checks cannot establish those balances.

Multiple independent department bins, orphaned stream references, all inventory
priority combinations and legacy/custom migration remain incomplete. Unavailable
initial space currently leads to waiting/failure; a dedicated preflight warning
explaining missing seeded stock remains a UI/checks improvement. The global seed
flag's malformed scalar validation also remains open.

The engineering feature audit, geometric traffic, approved CAD workflows, final
tutorial and release validation retain their existing gates.
