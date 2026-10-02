# Engineering verification — first review gate

This gate establishes repeatable evidence and fixes defects reproduced by small
reference cases. It does **not** complete the feature audit or certify the simulator.
The next stage starts only after the user's review of this checkpoint.

## Review these results

Open `latest/index.html` in a browser. It contains the test results, feature
contracts, limitations and searchable option inventory. `latest/evidence.json`
contains individual outcomes, source hashes, environment versions and test links.
`latest/source-snapshot.zip` preserves the tested code and configurations, including
uncommitted files. The rollback commit before this work is `07a059a`.
Generated `latest/` bundles are ignored by Git and retained locally or uploaded as
CI artifacts; regenerate them with the commands below after cloning. The compact
review record is versioned in `REVIEW_STATUS.md`.

The current inventory distinguishes:

- **Verified reference scope:** specific stated behaviour has independent small-case tests.
- **Partial:** implemented behaviour has gaps in coverage, definitions or functionality.
- **Unsupported:** planned behaviour has not been delivered.
- **Semantic review required:** a setting was discovered but its full contract is not yet reviewed.

The inventory searches editor defaults, the built-in example, `example*.json` and
LTN. A separate literal-key source index helps find additional settings, but those
matches also include output/runtime dictionaries. It is not a complete dataflow
analysis and must not be used to claim every source key is a supported input.
Container paths and leaf settings both appear in the option count.

## Three examples for your verification

Use copies of the JSON projects in `verification/scenarios` with the existing
editor/simulator. All start at A, carry one box to B, travel at 2 m/s, and take
2 seconds each to load and unload. A–Door and Door–B each measure 5 m by the
3–4–5 triangle; the door opening is 0.8 m.

| Project | Expected result | Independent calculation |
| --- | --- | --- |
| `door-pass.json` | One completed task, 9 seconds | 0.7 m box fits; 2 + (5 + 5) / 2 + 2 |
| `door-blocked.json` | One failed task, no completed task | 0.9 m box cannot pass through a 0.8 m opening |
| `door-detour.json` | One completed task, 14 seconds | Use the explicit 20 m alternative; 2 + 20 / 2 + 2 |

In the detour example the explicit edge distance overrides its straight drawing
distance, intentionally exercising the existing distance override feature.
This checks straight passage only: door opening time, safety clearance, turn
radius, height and the swept payload envelope remain outside this claim.

Also review the generation rules: enabled groups run even when category defaults
are disabled; groups do not add an extra category-level task; multiple groups can
deliberately request separate services; category-wide zone capacity policy wins.
Legacy route profiles still union their allow-lists with task allowances, and an
empty list means unrestricted. Strict clean/dirty separation is not yet implemented.

## Reproduce the evidence

From the repository root, using Python 3.13 on Windows:

```powershell
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
.venv/Scripts/python.exe -m verification.run --output verification/latest
.venv/Scripts/python.exe -m verification.smoke --config ltn.json --minutes 360 --output verification/latest/ltn-six-hour
```

The first command declares the previously missing `pypdf` test dependency.
The verification command exits nonzero on a failed test, a broken evidence link
or source changes during the test run. JUnit XML is available for CI consumers.
The smoke command runs the same copied LTN input twice and compares completed,
failed and pending outcomes exactly. It changes only the copy's end datetime;
the original project is checked for changes afterward. Its shorter demand horizon
does not prevent the current simulator from finishing assigned work afterward.
These are repeatability checks, not independently validated LTN results.

The Windows CI workflow installs dependencies in a clean runner and retains the
evidence even on failure. The workflow itself has not yet run on GitHub at this gate.

## Defect record and remaining work

| ID | Finding | Resolution / effect |
| --- | --- | --- |
| D001 | Oversized robot/payload could traverse narrow doors/corridors | Width now participates in shortest-path search and its cache. Wider alternatives remain usable. Impossible tasks fail with width-limit context. |
| D002 | Location capacity counted successive reservations as simultaneous | Sweep simultaneous occupancy over half-open intervals; this can reduce previously artificial waits. |
| D003 | Enabled groups ignored under disabled category defaults | Group activation now follows the same independent enable semantics as department overrides. |
| D004 | Grouped service could also generate a category-level task | Category-only fallback suppressed when groups exist; dynamic waste groups also suppress the legacy waste generator. |
| D005 | Two PDF tests could not import pypdf | Added pinned verification dependency. |
| D006 | LTN regression assumed three bays after the project acquired a fourth | Assert the actual four named bays; no LTN data was changed. |
| D007 | Fast assignment and charging estimates could still use a route rejected by door-width checks | Apply the same oriented robot/payload width to preliminary travel, energy and fast assignment queries. Three regression cases verify detour time, impossible passage and both charging-estimate legs. |

The original 115-test baseline and before-fix reference failures are in `baseline/`.
Priorities after review: continue individual option contracts and independent
cases for other generation modes, lifts, energy, resource contention and reports;
then surface structured findings in the application. The project container,
unified UI, lanes, swept turns, tutorials and illustrated guide remain later stages.
Unknown route profile fallback, lack of explicit clean/dirty shared sections,
time-boundary semantics and approximate lane capacity are explicitly outstanding.
