# Legacy waste stock, references and location naming — slice 2AN

## Physical stock and collection agreement

Active legacy department-waste services now resolve their initial bins from the
same global stream payload used by collection tasks. A department stream payload
override no longer seeds a different type while the legacy task asks for the global
type. Legacy demographic rates and global container capacity/fraction remain the
demand/threshold contract. Project Checks identifies supplied modern per-stream
rate, payload, capacity and enablement overrides that legacy generation does not
consume, so the retained settings require explicit acknowledgement.

Initial-presence opt-out now reaches the generated task as well as seeding. With
`initial_container_present: false`, no initial bin is created and outbound tasks
can issue stock normally. With presence enabled, legacy tasks carry the same bin
group identity as the seed and return that physical bin. Active shared definitions
with incompatible physical type/capacity/threshold/presence reject when legacy
seeding is enabled. Sharing a physical legacy bin does not merge independent
departmental waste-volume pools.

Explicit additional pickups retain their stock meaning. Independent bins may be
seeded at each configured location; automatic sharing remains per stream and
pickup; an explicitly named shared group seeds once, preferring its active legacy
collection pickup. Collection routes themselves still use only singular
`waste.pickup_location` and `waste.dropoff_location`. Additional stock locations do
not multiply legacy collection routes.

Without an active legacy or modern waste rule, the existing custom/static stock
adapter remains available. The global initial-stock switch controls that stock
independently of legacy task-generation enablement. Disabling legacy generation
does not remove explicitly configured custom stock. Modern rule-owned stock keeps
its previously verified enablement semantics.

## References and naming

The custom stock adapter now resolves modern category pickup keys before their
aliases, including an explicit empty modern value. Scalars are whole literal
names. It combines the effective category source with legacy singular/plural waste
pickups and department-level `waste_pickup_locations`, removing duplicates.
Unknown locations cannot fabricate stock.

Legacy pickup fields require strings or lists of strings, as appropriate; null,
numeric, boolean and object-valued names reject before import/run. Renaming handles
whole scalar names and plural legacy routing fields without splitting names into
characters. Deleting references clears these fields without reviving aliases.
Managed checks identify missing actual route references and explain additional
stock input scope. `waste.dropoff_locations` remains stored metadata without a
runtime consumer and is explicitly surfaced as unsupported.

Department category naming suffixes require string values. Auto-assignment retains
existing scalar/alias selections, zone settings and metadata while adding existing
locations that match `department ID + suffix` exactly or with an underscore
extension. Similar prefixes without the underscore do not match. This operation
assigns references; it does not rename or create graph points. The option inventory
now canonicalises suffix category keys with `*`, rather than counting every category
name as a separate option.

## Independent references and evidence

The legacy reference has one bed, alpha=24 m³/(bed·hour), a global 0.5 m³ container
and 80% threshold. Each minute accrues 0.4 m³ and releases one collection. Over two
minutes, one initially present bin serves **two collections and two returns**, with
**four completed task records**, no failures and the same one physical ID back at
the source. Initial-presence opt-out produces **two outbound completed tasks** and
**two issued physical IDs**, with no seed. Two departments sharing one explicit bin
still accrue 0.4 m³ each per minute, yielding two legacy collection requests, not a
combined dynamic accumulation pool.

Sixteen new tests cover these stock/identity outcomes, disabled-generation custom
stock, extra independent and automatic-shared bins, explicit-group conflicts, scalar
aliases, rename/deletion, invalid input, findings and suffix assignment. The initial
exploratory reproduction is `latest/legacy-waste-seeding-before.txt`; the final
contract deliberately retains disabled-generation custom stock. A fixture's renamed
charging reference was corrected before final acceptance. The focused run passes
112 tests, including nine evidence checks, in
`latest/legacy-waste-seeding-focused.txt`.

The final pack passes **1,366/1,366 tests** in **143.740 seconds**, with zero broken
evidence links and unchanged source during testing. See `latest/tests.txt`,
`latest/evidence.json` and `latest/legacy-waste-seeding-pack-build.txt`. An earlier
full pass is retained as `latest/legacy-waste-seeding-first-pack-tests.txt`; the
final run includes the correction that directs legacy shared-bin findings to
Departments. The targeted navigation/check suites pass 56 tests in
`latest/legacy-waste-navigation-check.txt`.

Two final LTN runs with a 60-minute demand window each complete four tasks with zero
failed/pending tasks, final simulation time 7928.480894138804 seconds and outcome
hash `5368460ed4fd5fd466e832b82d3d6358977abfaccbb456d45e268cfb7c0ab474`,
unchanged from the prior checkpoint. Assigned work drains beyond the demand window.
Initialization takes 1.374762 / 1.451547 seconds and total runtime 1.727196 /
1.810498 seconds. Source and input remain unchanged. See
`latest/legacy-waste-seeding-ltn/smoke.json`. This is regression/repeatability
evidence, not independent numerical validation of the full LTN project.

## User verification

1. Review a legacy department using the initial-bin option. Confirm its global
   stream payload matches the seeded bin and its actual collection pickup is used.
2. Compare presence enabled/disabled using the two-minute reference expectations
   above. Inspect physical IDs as well as task counts, including return tasks.
3. Review Project Checks for retained modern per-stream settings in a legacy rule.
   Set the intended global/legacy values, switch to modern rules, or acknowledge
   deliberately unused settings.
4. In Departments, auto-assign a custom suffix and check that existing selections
   remain, only exact/underscore matches are added, and Cancel preserves the project.

## Limits and next work

Custom stock without an active service retains its raw adapter and still needs
wider cross-service contention/reference verification. These tests do not prove
every legacy/custom mixing arrangement, multi-location shared-bin route, stock
report, calendar or geometric path. Legacy volume pools remain separate even for
one shared physical bin. Department stream generation overrides remain a modern
feature; this checkpoint does not migrate legacy rates or change their precedence.

Continue simulation run-control contracts, including dates, scheduling limits and
inventory/charging switches, then the remaining generation/workspace gates.
Report reconciliation, geometric traffic, the approved CAD UI, tutorial and
final release validation remain open.
