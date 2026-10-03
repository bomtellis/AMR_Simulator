# Physical payloads and storage envelopes — slice 2AB

Baseline: `41af3e8`. Physical payload input checks and shared bay-envelope inference
now connect payload dimensions to consistent raw/editor storage decisions. Eighteen
new dispositions retain their partial or unsupported scope.

## Corrections and changed results

An omitted payload height means `size_units`, or 1 m if that legacy field is also
omitted. Bay inference previously ignored that rule and substituted 999999 m when
its template lacked explicit `height_m`. A flexible bay inferred from a legacy
2 m-high payload could therefore accept a 2.01 m-high load. Both runtime and editor
now infer 2 m and reject that taller load. Explicit bay heights remain authoritative.
Without any known template, the old practically-unbounded sentinel remains and is
an explicit outstanding model limitation.

Editor import also rounded inferred bay dimensions to three decimal places and
ignored legacy `length`, `width`, `height` and `flexible_payloads` values. This could
change whether a load fit after opening the project. A shared resolver now retains
precision, respects modern-field precedence over aliases, and preserves the
legacy flexibility setting. It retains runtime's current zero-as-inference rule;
full bay input validation remains for the next audit.

Payload input checks reject negative/nonfinite mass, nonpositive/nonfinite physical
dimensions, booleans passed as numbers, malformed preference flags, duplicate names
and names reserved for empty-load handling. Zero mass remains a valid idealised
reference. Numeric strings remain accepted. Missing name/mass can remain in an
editable draft but block running; raw import does not silently fill them.

Project Checks now identifies unused `payloads[].volume_m3` and inventory-space
`capacity_volume_m3`. Neither overrides dimensions or adds bay capacity. Geometric
storage volume uses physical dimensions; configured demand volumes remain separate.

## Independent references

Thirteen new tests in `tests/test_payload_contracts.py` cover inputs, draft reopen,
dimension defaults and precedence, shared inference, aliases, precision and fit:

- Legacy size 2 with explicit width 0.5 resolves to **2 × 0.5 × 2 m**.
- Fully omitted dimensions resolve to **1 × 1 × 1 m**.
- A bay inferred from a 2 m template rejects a **2.01 m** load, including through
  the actual free-bay selector.
- A **1.0004 × 0.7004 × 1.0004 m** inferred bay retains those values after import.
- Exact fit is accepted; a **0.0001 m** shortfall in any dimension is rejected.
  The existing **1e-6 m** numerical tolerance is explicit and separately exercised.
- Storage permits plan rotation independently of AMR carrying orientation. Typed
  bays enforce template payload names; flexible bays permit other fitting types;
  AMR-only bays reject payload storage.
- One **2 × 0.5 × 3 m** stored object contributes **3 m³**, even if its unused
  volume metadata says 999 and its bay's unused volume capacity says 0.01.

Initial failures are retained in `latest/payload-contract-before.txt`. The focused
physical-payload, robot, bay, drop-off, checks and reservation suites passed
**93 tests**. The full suite passed **1,204 / 1,204 tests in 133.855 seconds**,
with **zero broken evidence links** and unchanged source hashes. The complete
pack took 136.126 seconds; logs are in `latest/payload-contract-pack-build.txt`
and structured results in `latest/evidence.json`. The observed inventory retains
339 paths awaiting individual review; this is not a count of missing features.

Both 60-minute LTN demand-window runs completed four tasks with none failed or
pending, preserving outcome hash
`5368460ed4fd5fd466e832b82d3d6358977abfaccbb456d45e268cfb7c0ab474`.
Source and input checksums remained unchanged. Results are in
`latest/payload-contract-ltn/`; this bounded regression is not full LTN acceptance.

## User verification

1. Use a copy of a project with a flexible bay whose template payload has
   `size_units: 2` and no explicit height; omit the bay height too. Confirm its
   inferred height is 2 m before and after editor import.
2. Try a different payload 2.01 m high. Confirm no compatible bay is selected.
3. Inspect a bay with precise inferred dimensions or legacy dimension aliases,
   then save/reopen and compare its resolved dimensions.
4. Try invalid physical payload dimensions through JSON import. Confirm a specific
   input error rather than a load that silently fits or a later calculation failure.

## Limits and next work

This remains axis-aligned envelope checking, with free plan rotation in storage.
It does not verify swept polygon clearance, stacking, arbitrary packing, physical
shaft alignment or calibrated energy. Full bay schema/reference validation,
malformed points, zero-dimension policy and the unknown-height sentinel remain open.
Inferred-dimension precision is fixed; all dialog precision/range preservation is
not yet established. Scheduling preference contention also remains under audit.

Next complete location/bay input contracts and their reference/occupancy checks,
then continue department and workspace gaps before geometry, the approved CAD UI,
tutorial and final release gates. Unrelated `ltn.json` edits remain outside this
checkpoint; no project migration is silently applied to that file.
