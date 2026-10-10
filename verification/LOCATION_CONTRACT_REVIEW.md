# Location inputs and wash capacity — slice 2AD

Baseline: `9278fda`. This checkpoint verifies location scalars and specific
post-delivery washing behaviour, with sixteen new tests and nine option
dispositions. The full location/traffic model remains incomplete.

## Corrections and changed results

Wash service previously ignored `locations[].max_concurrency`. A robot could wash
at a station already at its configured service capacity. Positive wash service now
waits for available capacity, records the wait in its route, and reserves the
service interval only when the route commits. Rejected late commits roll back
the wash reservation with the other route resources. Pickup, dropoff and washing
share this service capacity. Waiting is not modelled physical queue occupancy.

An unknown explicit wash target previously fell back silently to the task dropoff.
It now blocks raw simulation and Project Checks. The editor keeps an unresolved
target visible for correction, and renaming a location updates wash references.
A valid but unreachable wash station remains a route-planning failure; no fallback
journey or resource commitment is created.

Location input checks now reject duplicate/blank identities, nonfinite coordinates,
fractional floors or capacities, nonpositive service capacities, negative/nonfinite
wash durations, boolean numbers, non-boolean wash flags and malformed references.
Missing name/floor and unresolved references may remain in editable drafts.
Integer numeric strings remain supported for floors and capacities; fractional
numeric coordinates and durations remain supported. Missing raw x/y still default
to zero, while existing Project Checks requires them; that policy remains explicit.

The wash dialog now calls its empty-target option **Use task drop-off**, matching
runtime. It permits zero duration, preserves unavailable targets, accommodates
imported durations above one day, and preserves full imported duration precision
when unchanged. Previously zero was rejected, subsecond values were rounded, long
values were capped, and unavailable targets were silently replaced by the default.
Contextual help explains the dropoff rule's precedence and target service capacity.

Location-level `people_area_type` does not restrict current routes. Project Checks
and the dialog now explain that it is stored metadata. People routing checks
corridor-edge classifications; AMR access uses route profiles. Invalid location
classification strings are rejected instead of silently becoming `none`.

## Independent timing references

The saved `scenarios/location-wash.json` uses these independent quantities:

| Phase | Calculation | End time |
| --- | --- | --- |
| Pickup at A | 2 seconds | 2 s |
| Loaded A → B | 10 m / 2 m/s | 7 s |
| Dropoff at B | 2 seconds | **9 s** |
| Empty B → Wash | 10 m / 2 m/s | 14 s |
| Wash at an available station | 7 seconds | **21 s** |

With station capacity one and an existing reservation `[0,20)`, the same task
waits six seconds and washes during `[20,27)`, completing at **27 seconds**.
With capacity two, one existing reservation permits completion at 21; two existing
reservations require completion at 27. Speculative estimates leave resources
unchanged, and a deliberately rejected late commit restores all tracked resources.

Physical delivery and its event record remain at **9 seconds**, before wash travel,
waiting or completion. Both raw and editor-imported scenarios are exercised.
Zero wash duration still permits target transfer, ending at 14 seconds without a
wash-service reservation. An omitted duration means 300 seconds, ending at 314.
When both pickup and dropoff require washing, the dropoff settings win. An empty
target means the task dropoff even when the pickup supplied the wash rule.

The tests also establish the retained legacy boundary: the wash transfer is
unloaded and does not inherit the loaded task's route profile. This is documented
behaviour for comparison, not a verified clean/dirty decontamination workflow.
Wash-triggering tasks remain ineligible for multi-stop batching.

## Verification evidence

Initial reproductions are retained in `latest/location-contract-before.txt`.
The focused location, bay, editing, Project Checks, payload timing, reservation and
engineering-reference suites passed **148 tests**. The full suite passed
**1,232 / 1,232 tests in 133.406 seconds**, with **zero broken evidence links**
and unchanged source hashes. Results are in `latest/location-contract-focused.txt`,
`latest/location-contract-pack-build.txt` and structured `latest/evidence.json`.
There are **318 observed option paths awaiting individual review**; this is not a
count of missing features.

Both 60-minute LTN demand-window runs completed four tasks with none failed or
pending. Source/input checksums were unchanged and both retained outcome hash
`5368460ed4fd5fd466e832b82d3d6358977abfaccbb456d45e268cfb7c0ab474`.
Results are in `latest/location-contract-ltn/`; this bounded regression does not
establish full LTN acceptance.

## User verification

1. Open a copy of `verification/scenarios/location-wash.json` and run Project
   Checks, then simulate. Confirm one completed delivery, one wash cycle, delivery
   at second 9 and completion at second 21, ending at Wash.
2. Change B's wash target to an unknown name in a project copy. Confirm the precise
   reference error blocks running and the editor retains the unresolved value.
3. Restore Wash, rename that location, and confirm B's wash target follows it.
4. Inspect the wash controls with zero, fractional or long durations. Saving an
   unchanged imported duration must preserve it. Zero skips service; it does not
   disable the configured transfer.
5. Set a location people classification and read its Project Checks explanation.
   Use corridor people settings or AMR route profiles for actual access policy.

## Limits and next work

This is general engineering verification of the stated scheduling model, not
validation of wash efficacy, infection control or physical decontamination.
Service intervals do not establish physical queue space, swept clearance,
local-manoeuvre/service timing alignment or complete mixed-workflow contention.
No alternate wash-only route profile is introduced. General rename/delete reference
coverage, all coordinate-dialog precision, bounding outlines and the missing-x/y
policy remain open. Preserving a wash reference on rename does not close the
entire editor command audit.

Next resolve remaining bay classification, legacy slot aliases and zero-dimension
policy, then finish location outlines/remaining input contracts and continue the
department and workspace gaps. Geometry, approved graph-focused CAD UI, tutorial
and final release gates retain their planned order. The unrelated `ltn.json` edit
remains outside this checkpoint.
