# Bay classification and dimension policy — slice 2AE

Baseline: `faeadb7`. This checkpoint consolidates AMR/payload bay classification,
legacy AMR references and effective dimensions. Thirteen new tests accompany five
new partial option dispositions and updates to the existing bay contracts.

## Corrections and changed results

A bay with only a parent `amr_type` was recognised as AMR storage by payload fit,
but could be missed by charger counting and operational-charger checks. That
enabled the legacy location-level charger fallback even with `has_charger: false`.
Shared classification now recognises the same AMR bays across runtime storage,
charging, editor compatibility, charger markers and inventory controls.

The supported AMR markers are `stores_amr: true`, `space_type: amr`, a nonempty
parent `amr_type`, or an AMR-marked/template-reference slot. Type tags accept case
and surrounding whitespace; unknown tags reject rather than becoming payload
storage. Any AMR marker makes the bay AMR-only. An explicit false flag does not
override other markers. A charger flag alone does not create an AMR bay.

Legacy slot `amr` references now constrain runtime compatibility as they already
did during some editor saves. Modern `amr_type` wins when present, including a
blank modern value. Parent and effective slot restrictions form the existing union
of permitted type/instance IDs. Editor compatibility recognises that union and
valid instance restrictions, rather than considering only the first type.
Unknown effective aliases block running. A zero-quantity robot type now requires
zero charging bays in the existing editor validator.

Zero bay dimensions retain the established inference convention. Previously raw
numeric zero inferred from points/templates, string `"0"` became a literal zero,
and generic Project Checks rejected both. Numeric and string zero now resolve
identically and preflight permits that bay-specific convention. Modern keys still
win over dimensional aliases before zero inference: a modern zero does not revive
an overridden legacy nonzero value. Payload and AMR dimensions remain strictly
positive. Nonfinite resolved envelopes, including finite points whose subtraction
overflows, are rejected.

Project Checks now explains four constraints:

- Unresolved zero plan length/width leaves the bay unable to fit an ordinary
  positive-size payload or AMR.
- Height **999999 m or greater** is effectively unbounded and does not establish
  a usable vertical-clearance check.
- AMR markers make a mixed definition AMR-only even when it includes payload
  templates; those templates can still contribute inferred height.
- A payload bay's charger flag does not add an AMR bay charger. Legacy
  location-level charging can still apply where no AMR bays exist.

These findings are warnings that can be acknowledged for deliberately constrained
or legacy scenarios. Malformed inputs remain blocking errors. No geometry is
silently inserted and no existing project file is automatically migrated.

## Independent acceptance cases

`test_inventory_classification` covers the following expected decisions:

- Six equivalent AMR marker forms produce AMR-only storage. With no charger flag,
  charger count is **zero** and the AMR is not at an operational charger.
- Legacy alias `R` accepts R and rejects Other. Modern R overrides legacy Other.
- Parent R, instance R-1 and slot unions agree between editor type compatibility
  and runtime robot compatibility in the stated one-instance cases.
- Zero length/width/height with outline points (0,0), (2,3) and a 1 m template
  height resolves to **2 × 3 × 1 m**, including numeric-string zero and import.
- A modern zero length plus legacy length 99 still infers **2 m** from the outline.
  Zero physical payload length remains invalid.
- An unspecified bay resolves to **0 × 0 × 999999 m**, with visible warnings and
  unchanged inputs. The warnings can be acknowledged for an exploratory run.
- Mixed AMR/payload definitions reject payload storage and explain why. A charger
  flag alone retains payload classification and does not add a bay-level charger.
- Zero robots require no charging bays. Extreme finite outline coordinates cannot
  turn into an infinite-size bay.

Initial reproductions are in `latest/inventory-classification-before.txt`. The
focused storage, charging, editor, robot and Project Checks suites passed **128
tests**. The full suite passed **1,245 / 1,245 tests in 134.721 seconds**, with
**zero broken evidence links** and unchanged source hashes. Logs are retained in
`latest/inventory-classification-focused.txt`,
`latest/inventory-classification-pack-build.txt` and structured `latest/evidence.json`.

Both 60-minute LTN demand-window runs completed four tasks with none failed or
pending. Source/input checksums were unchanged and both retained outcome hash
`5368460ed4fd5fd466e832b82d3d6358977abfaccbb456d45e268cfb7c0ab474`.
Results are in `latest/inventory-classification-ltn/`; this bounded regression
does not establish full LTN acceptance.

## User verification

1. In a project copy, use an AMR bay identified only by `amr_type`, with
   `has_charger: false`. Confirm it is shown as AMR storage and does not contribute
   a charger. Add `has_charger: true` only when that bay is intended to charge.
2. Use a legacy slot `amr` reference to one robot type. Confirm another type does
   not fit that bay merely because its footprint fits.
3. Set bay length/width to zero while retaining a known outline. Run Project
   Checks and compare inferred dimensions before and after import.
4. Inspect a bay without adequate dimensions or a known height. Confirm the
   findings distinguish the constrained/legacy geometry from malformed input.

## Limits and next work

This remains envelope fit, not physical polygon containment, packing, stacking or
swept clearance. AMR fit retains a **1e-3 m** tolerance; payload fit uses **1e-6 m**.
The legacy unbounded height remains available with an explicit warning. Mixed
definitions retain AMR precedence for comparison; they do not support simultaneous
AMR and payload storage. Global fleet-to-bay matching, instance-specific charger
allocation and the distinction between charging constraints and malformed input
need further verification. Type-level compatibility is not proof that an entire
fleet can occupy distinct compatible bays simultaneously.

Next verify that fleet/charger allocation and preflight distinction, then complete
location outlines and remaining input contracts before department/workspace gaps.
Geometry, approved graph-focused CAD UI, tutorial and final release gates retain
their planned order. The unrelated `ltn.json` edit remains outside this checkpoint.
