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
| D008 | LTN has two exits for one clinical-waste instance before its next recorded entry | Open investigation. Results investigation links both records and marks transfer totals incomplete; underlying tracking behaviour has not been repaired or classified as physical payload loss. |
| D009 | Sorting configuration keys in project, undo and recovery snapshots changed generation category iteration order | Preserve configuration key order in persisted/restored snapshots. Ordered-category acceptance tests reproduce the defect. The project-bound six-hour LTN run now matches the original detailed outcome fingerprint exactly. Previously sorted snapshots cannot reconstruct discarded order; reimport the original JSON for baseline comparisons. |

The original 115-test baseline and before-fix reference failures are in `baseline/`.
Continue individual option contracts and independent cases for other generation
modes, lifts, energy, resource contention and reports. Structured findings are now
available at the Project checks checkpoint described below. The project container,
unified UI, lanes, swept turns, tutorials and illustrated guide remain later stages.
Unknown route profile fallback, lack of explicit clean/dirty shared sections,
time-boundary semantics and approximate lane capacity are explicitly outstanding.

## Project checks checkpoint

In the editor, use **Home → Project checks**. The dock stays open while editing.
Filter by severity or search for an object. Select a finding for its explanation,
consequence, setting path and next action. **Go to affected settings** selects a
graph point or opens the relevant settings editor. Older validator findings that
do not identify a section retain their explanation without precise navigation.
Severity is written in text; it does not depend on colour.

Any configuration edit makes the report stale (checked every 750 ms and again
before actions). Rerunning checks resets warning acknowledgement. Export saves a
JSON record containing findings, stable finding IDs and the configuration hash.

Launcher runs now review the raw configuration before normalisation. Detected
malformed input errors block a run. Warnings describe operational constraints,
missing drawings or unresolved rule references and require acknowledgement.
Each run saves the exact reviewed input bytes as `config.json` and saves findings
and acknowledged warning IDs in `project_checks.json`. The manifest contains
both a file hash and a canonical configuration hash. An external configuration
edit during review prevents launch unless its parsed values still match.
Direct command-line simulation retains its existing behaviour.

Manual review before the next stage:

1. Open LTN without drawings and open Project checks. Its stored linen group
   references to `D26-LINEN` should appear as warnings. Department assignments can
   replace group destinations, so these are not a claim that LTN demand fails.
2. Search for `D26`, select a warning and open its task-generation settings.
3. Edit a setting on a disposable copy. Confirm the checks become stale and
   export/navigation are disabled until checks are rerun.
4. In the launcher, try a copy with robot speed zero: the error must prevent a run.
   Restore a valid speed, recheck, review warnings and run. Inspect its saved checks.
5. Confirm the dock and run dialog are readable with your display scaling and
   keyboard navigation. Automated Qt checks and a local render do not replace this.

This is incremental preflight, not a complete schema or acceptance of every
configuration field. Static directed connectivity and profile allowance unions
are checked; loaded door passage, lift compatibility, dynamic generation
precedence, capacity contention and swept geometry are not proved by preflight.
Existing reference simulation tests still supply those narrower verified claims.
Drawing file availability is checked on recheck, not watched continuously.
All checks become stale together; dependency-specific invalidation is deferred.
Demand preview is now available at the checkpoint described below.

## Demand preview checkpoint

Use **Home → Demand preview → Build preview**. Inspect the task table, hourly
timetable and rule reconciliation; filter by department, category, payload, date
or route profile. Selecting tasks and rules shows their origins, effective settings
and precedence. Unknown runtime-dependent totals remain distinct from zero work.
Edits invalidate the preview and disable export until it is rebuilt.

Follow [the review guide](DEMAND_PREVIEW_REVIEW.md) before the Results investigation
stage. It describes count definitions, the independent count checks, known
limitations and the LTN evidence. To export without opening the editor:

```powershell
.venv/Scripts/python.exe -m amr_demand_preview --config ltn.json --output verification/latest/ltn-demand-preview.json
```

Exports contain the frozen project configuration, so treat them as project data.

## Results investigation checkpoint

The latest checkpoint is [Project-bound simulation](PROJECT_RUNS_REVIEW.md):
save, check and simulate within the editor, frozen revision-bound external runs,
moved-run matching and Results investigation. Persistent run links and the full
project tree remain outstanding.

[Undo and redo](UNDO_REDO_REVIEW.md) provides shared completed-edit
history, keyboard shortcuts, save-aware dirty state and protection against stale
editing windows. Saved revisions remain the cross-session restore mechanism.

[Recovery and unsaved work](RECOVERY_REVIEW.md) provides
30-second recovery copies, Save / Discard / Cancel safeguards and recovery to a
new unsaved document.

[Portable project storage](PROJECT_STORAGE_REVIEW.md) provides
compressed `.amrproj`, deduplicated drawings, atomic saves and revision restore.
Use **Home → Save project as** and **Project revisions**. Results stay external;
use **Export JSON** for the existing launcher and command-line tools.

Use **Home → Results investigation**, or **Investigate Results** in the launcher.
Select the saved run folder or full event CSV. Task timelines distinguish recorded
outcomes from planned route segments. Metric selection opens contributing events;
missing evidence remains explicit, including partial payload-transfer coverage.

New logs have stable event/journey identities and `.csv.run.json` evidence sidecars.
Move the CSV and its sidecar together. Older logs remain readable with weaker,
explicitly labelled evidence. See the [review guide](RESULTS_INVESTIGATION_REVIEW.md)
for definitions, test results and the next user verification gate.

```powershell
.venv/Scripts/python.exe -m amr_results_investigation verification/latest/ltn-investigation --output verification/latest/investigation.json
```
