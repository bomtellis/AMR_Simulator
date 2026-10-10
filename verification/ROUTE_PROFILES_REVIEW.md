# Route profiles checkpoint — 2 October 2026

Route profiles define clean, dirty and shared access. A shared corridor is
included in each profile that may use it; no additional classification is needed.
This checkpoint verifies reference graph routes, not physical contamination
control, swept footprints or the entire routing feature.

## What changed

- Unknown effective route profiles now raise an explicit input error before a
  task can be scheduled or assigned. This covers explicit names, the implicit
  dirty-label fallback, effective generated tasks and active return profiles.
  Invalid input halts the run; it is not an ordinary unreachable-task outcome.
- Project checks identify a missing implicit dirty profile and explain shared
  access and the existing empty/return policy.
- **Generate from selected nodes** now includes both directions of two-way
  corridors, preserves one-way direction and removes duplicate edge pairs.
- The profile editor explains that empty lists mean unrestricted and that task
  allow-lists extend the profile. Existing saved edge lists are not rewritten.

The defect reproductions are in `baseline/route-profiles-before-fix.txt`.
D010 and D011 are recorded in the main verification README.

## Verification result

- **319 / 319 tests passed**, including 19 new route-profile acceptance tests;
  zero broken feature-to-test evidence links.
- Two six-hour LTN demand windows each completed **203 tasks**, with zero failed
  or pending tasks. Both matched the previously recorded detailed outcome hash:
  `593945bef454f5d602c82f0f15180cbc26285d3711d93102d483635da36faab5`.
- Local elapsed times were 11.55 s and 11.80 s. These are observations from this
  machine, not release performance guarantees. Assigned work drains beyond the
  six-hour demand window under existing simulator semantics.
- The updated dialog was rendered and visually checked. The four saved scenarios
  were executed by the acceptance suite against the expectations below.
- Evidence is in `latest/index.html` and `latest/ltn-route-profiles/`.
  The existing user edit to `ltn.json` was preserved and excluded from this commit.

## Behaviour retained and made explicit

| Journey or setting | Effective policy |
| --- | --- |
| Delivery after pickup | Explicit task profile; otherwise the `dirty` profile if the task has the `dirty` label; otherwise unrestricted |
| Empty approach to pickup | Unrestricted by route profiles; graph direction and physical width checks still apply |
| Empty charging, wash transfer and idle return | Unrestricted by route profiles; other routing constraints still apply |
| Ordinary payload return | `return_route_profile`; if blank, the return's copied labels can select `dirty`. A blank return profile does not automatically inherit a clean outbound profile |
| Seeded waste-container return | Existing preparation can populate a blank return profile from the outbound profile |
| Shared section | Allowed by each applicable profile |
| Empty node, edge or lift list | No restriction from that list |
| Task allow-lists | Union with profile lists; can intentionally widen access |
| Profile edge pair | Directed, even when the underlying corridor is two-way |

Profile names are exact identifiers. `clean` and `dirty` are examples; only the
existing lowercase `dirty` label fallback has special behaviour. Unknown names
must not be used to request an unrestricted journey: use a blank profile or an
explicitly unrestricted profile instead.

## Your review

Open disposable copies of these JSON files in the editor, then use **Project
runs → Save, check and simulate**. Save each as its own `.amrproj` file.

| Reference file | Expected outcome |
| --- | --- |
| `scenarios/profiles-clean.json` | One completed task in 9 s, A → Shared → Clean → B |
| `scenarios/profiles-dirty.json` | One completed task in 11 s, A → Shared → Dirty → B |
| `scenarios/profiles-return.json` | Outbound clean task takes 9 s; dirty return takes 11 s; both finish by 20 s |
| `scenarios/profiles-blocked.json` | Delivery fails; no unrestricted shortcut is used |

Independent arithmetic: shared stem = 2 m; clean branch = 4 + 4 m; dirty branch =
6 + 6 m. Speed = 2 m/s; pickup and drop-off each take 2 s. Therefore clean =
2 + 10/2 + 2 = 9 s, dirty = 2 + 14/2 + 2 = 11 s. A separate 1 m shortcut is
excluded by both profiles. Congestion slowdown is explicitly disabled in these
cases to isolate route selection. Explicit lengths intentionally differ from the
drawing coordinates, as in the earlier distance-override reference cases.

In **Route profiles**, select the shared stem and a branch, then generate edges.
Both directions should appear for two-way corridors. A one-way corridor should
produce only its configured direction. Review before applying, because this
operation replaces the edge list, including deliberate one-way profile choices.

In a disposable copy, change a task profile to a missing name. Project checks
must block it. For generated tasks, a missing stored default may be overridden
by a valid group value, so the engine validates the effective task at scheduling.

## Remaining limits

- Lift selection, multi-stop combinations, seeded waste-return inheritance and
  charging/idle-return interactions need broader independent acceptance cases.
  `MULTI_STOP_ROUTING_REVIEW.md` now covers per-leg onboard node/edge/lift
  intersections and rejects forbidden shared routes without widening permissions.
- Empty journeys have no selectable profile policy yet. This checkpoint records
  existing behaviour rather than silently changing established projects.
- Preflight does not resolve all effective generated or runtime return settings.
  An invalid generated profile can therefore stop a run after earlier valid work;
  such a run must be treated as failed/partial evidence.
- The separate LTN payload-tracking conflict D008 was later resolved; see
  `PAYLOAD_SERVICE_REVIEW.md` for the repair and its verified scope.
- Route colour/pattern presentation, shared geometric trajectories and swept
  clearance remain future checkpoints.

Run `python -m verification.run --output verification/latest` to reproduce the
complete evidence pack. The automated cases in `tests/test_route_profiles.py`
cover delivery/return arithmetic, shared branches, directed edges, cache
separation, explicit overrides, empty approaches, invalid profiles and editor
edge generation. This is a review checkpoint, not completion of the full roadmap.
