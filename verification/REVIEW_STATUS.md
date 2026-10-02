# Stage 1 clash review — 2 October 2026

## Later checkpoint — effective demand-rule provenance

- Demand preview now records ordered category/group/department/waste assignments
  and exposes a searchable Effective settings tab with winning values, stored
  source paths and calculation history. Equal-value overrides keep their sources.
  See the [illustrated review](GENERATION_PROVENANCE_REVIEW.md).
- **870 / 870 tests passed**, including 19 new acceptance cases; zero broken
  feature-to-test links. Source fingerprints stayed unchanged during testing.
  Precedence examples, derived waste arithmetic, unknown totals, stale selection,
  older metadata, input preservation and 24 pt desktop sizing are covered.
- Eight small generation-mode comparisons against `226c245` retained identical
  resolved configurations and generated records. They do not establish complete
  runtime-mode coverage. No demand scheduling or simulation calculation changed.
- LTN preview took approximately 0.54 seconds locally: 1,234 planned records,
  264 rules with complete resolved-field histories and 190 rules with unknown
  total demand. Its checksum stayed unchanged. LTN has no independently assessed
  demand count in this preview; record reconciliation alone is not validation.
- Existing waste exceptions are now explicit: fallback thresholds use global
  capacity/fraction, and department waste-stream fields can override the restored
  category policy. Complete task-specific/global staff attribution, implicit
  defaults, inactive rules and all zero-work explanations remain open.
- Actual screens were inspected at 1366 × 900; large text fits 1280 × 800.
  The user's unrelated `ltn.json` edit remains outside this commit. Work pauses
  after this checkpoint at the user's request; the full roadmap remains open.

## Later checkpoint — finding navigation and check dependencies

- Check now preserves its existing report when reopened through the project tree,
  identifies changed inputs for each finding, and lists evaluated/skipped groups
  in Check coverage. Exact object and field navigation respects pending drafts
  and refuses stale array indices. See the [illustrated review](CHECK_WORKFLOW_REVIEW.md).
- **851 / 851 tests passed**, including 26 new acceptance cases; zero broken
  feature-to-test links. Source fingerprints stayed unchanged during the run.
  Cases cover dependency changes, passing/skipped groups, older metadata,
  drawing availability, exact navigation, ambiguous identifiers and large text.
- D054 fixes corridor findings selecting an endpoint instead of the affected
  edge. D055 fixes drawing availability changes leaving checks current when the
  configuration is unchanged. Their before/after baseline is recorded.
- Actual screens were inspected at 1366 × 900; large-text sizing passes at
  1280 × 800. LTN checking took approximately 0.169 seconds and status refresh
  averaged 0.025 seconds locally, leaving the project unmodified. These are
  observations, not performance gates. No simulator algorithm changed.
- Every changed project still requires a full recheck and renewed warning review
  before running. Drawing checks cover availability, not drawing contents.
  Complete option coverage, generation-rule checks, remaining legacy navigation
  and physical traffic verification remain open. The unrelated `ltn.json` edit
  remains outside this checkpoint commit.

## Later checkpoint — route-profile identification

- Layout and frozen-run playback now share profile names, colours, line patterns
  and direction arrows. Project → Route identification provides a searchable
  access table, lift-allowance summary and per-user style controls. See the
  [illustrated review](ROUTE_IDENTIFICATION_REVIEW.md).
- **825 / 825 tests passed**, including 25 new acceptance cases; zero broken
  feature-to-test links. Independent clean/dirty/shared direction sets, physical
  one-way edges, empty/node allowances, automatic connections and their provenance,
  malformed input, style persistence and frozen playback inputs are covered.
- The reference clean and dirty paths remain 10 m and 14 m, giving 9 s and 11 s
  loaded tasks at 2 m/s plus handling. No simulation algorithm changed.
- LTN projects 804 physical sections and three profiles. Opening the combined
  access display took approximately 0.184 seconds locally; saved LTN playback
  loading/display took approximately 0.724 seconds for 9,612 events. Frozen
  configuration checksums remained unchanged. These are observations, not gates.
- Actual screens were inspected at 1366 × 900; 24 pt controls fit a scrollable
  1280 × 800 workspace. Dense label placement, standalone viewer controls and
  verified traffic geometry remain open. Parallel strokes are schematic and do
  not represent implemented lanes. Broad roadmap gates remain open. The unrelated
  `ltn.json` changes remain outside this commit.

## Later checkpoint — saved appearance preferences

- Project → Appearance provides Light, Dark and High contrast presets, adjustable
  interface/map text, checked custom colours, and a scalable or hidden layout
  legend. Preferences live outside project/revision/run inputs. See the illustrated
  [Appearance review](APPEARANCE_REVIEW.md).
- **800 / 800 tests passed**, including 18 new appearance acceptance cases; zero
  broken feature-to-test links. Reference contrast, persistence, corrupt/failed
  settings, live styled controls, pending drafts, project/check isolation, keyboard
  actions, large text and hidden-tab font reductions are covered.
- Actual screens were inspected at 1366 × 900 and 1280 × 800, including 24 pt
  interface text. LTN display application took approximately 0.052 seconds here,
  with underlays disabled, and left the project unmodified. This is a local
  observation, not a performance threshold. No simulator algorithms changed.
- Playback/custom rendering, comprehensive accessibility and route-profile
  labels/patterns remain open. Clean/dirty/shared access continues to be defined
  by route profiles. Broad roadmap gates remain open. The unrelated `ltn.json`
  edit remains outside the checkpoint commit.

## Later checkpoint — configuration objects and route permissions

- Robots, payloads, lifts, static tasks and route profiles now appear in the
  project tree with common contextual fields in the Configuration workspace.
  Route permissions use searchable choices and named edge pairs, with explicit
  unrestricted-empty and directional semantics. See
  [Configuration properties](CONFIGURATION_PROPERTIES_REVIEW.md).
- **782 / 782 tests passed**, including 20 new acceptance cases; zero broken
  feature-to-test links. Independent references verify robot-speed duration,
  payload/door clearance, lift unit conversion, dirty-route timing, missing-edge
  failure and the effect of explicitly unrestricted permissions.
- Scalar edits preserve nested slots, tracked contents and unrelated fields.
  Draft pinning, stale-update rejection, undo, recovery and desktop sizing pass.
- Actual themed screens were inspected at 1366 × 900. Opening the LTN robot
  form took 0.013 seconds and a profile form 0.0629 seconds locally. These are
  measurements, not performance acceptance thresholds. No simulator algorithms
  were changed by this checkpoint.
- Creation/deletion/renaming, nested options and complex schedules remain in the
  full editors. Accessibility, route styling, verified geometry and the wider
  roadmap remain open. The unrelated `ltn.json` edit stays outside this commit.

## Later checkpoint — layout objects and contextual properties

- A searchable layout tree lists points and explicit directed corridor records.
  A contextual panel edits positions, doors, corridor properties and location
  wash settings without modal dialogs; bulk changes have an inline preview.
  See [Layout properties](LAYOUT_PROPERTIES_REVIEW.md).
- **762 / 762 tests passed**, including 26 new acceptance cases, with zero broken
  feature-to-test links. Independent reference results are 11.5 seconds for a
  10 m + 5 m route at 2 m/s plus 4 seconds handling, and 6.5 seconds when the
  first edge explicitly has zero distance. Door and direction consequences pass.
- Drafts retain their original targets, reject stale overwrites, apply in one
  undo step, and participate in save/export and recovery. Existing JSON nulls are
  distinguished from absent settings and remain unchanged unless edited.
- The LTN tree has 2,326 entries including groups. Twenty unchanged refreshes
  averaged 0.00971 seconds locally; this is not a performance acceptance gate.
  Actual themed screenshots were inspected at 1366 × 900; tests cover 1280 × 800
  and a 100-node bulk selection.
- Configuration-object properties, identity/floor changes, wider accessibility,
  verified geometry and the full roadmap remain open. The unrelated `ltn.json`
  change stays outside this commit.

## Later checkpoint — integrated playback

- Review now embeds playback from completed, revision-bound full event logs,
  with its own timeline and local lift/payload monitors. See
  [Project playback](PROJECT_PLAYBACK_REVIEW.md).
- **736 / 736 tests passed**, including 18 new playback acceptance cases;
  zero broken feature-to-test links. Independent positions, backward seeking,
  frozen-input isolation and UI lifecycle checks pass.
- The existing six-hour LTN run loads 9,612 events in approximately 0.4 seconds;
  its 204 completed, zero failed and zero pending outcomes remain unchanged.
  This is a playback check, not a new simulation performance claim.
- Actual themed screenshots were inspected at 1366 × 900. Controls and timeline
  also have automated 1280 × 800 checks. Current editor speed was changed to
  99 m/s during visual review while playback retained the saved run's speed.
- Simulator behaviour is unchanged. Drawing underlays, interruptible/paged
  loading, contextual properties and the broader roadmap gates remain open.
- The unrelated local `ltn.json` change is preserved outside this commit.

## Repository reconciliation

- Reviewed the `testing` working tree against rollback commit `07a059a`.
- Refreshed `origin`: `origin/testing` remains at `2199c36`; no new upstream
  simulator commits had arrived on this branch.
- No unresolved Git entries or conflict markers were found in the reviewed source.
- `origin/main` contains `a44af5b` (user guide) and `d2eb741` (its merge), which are
  not in `testing`. Their additions are confined to `docs/user-guide/`; they do
  not overlap these implementation changes. Route, generation and limitation
  guidance was inspected. The new width and group contracts add detail to that
  guide; they do not establish swept geometry or strict clean/dirty separation.
  These documentation commits were not merged as part of this review.
- The source/configuration fingerprints initially matched the previous Stage 1
  evidence, so no incoming source changes were silently overwritten.

## Interaction found and resolved

Fast assignment estimates and preliminary charging calculations still queried
unrestricted shortest paths after width restrictions had been added to executed
routes. A 20 m passable detour could consequently be estimated as the impassable
10 m shortcut. The affected queries now use the same robot/oriented-payload width
as the executed route. Three regression tests reproduced this before the fix.
The original failing output is `baseline/assignment-before-fix.txt`.

## Verification result

- **147 / 147 tests passed**, with zero broken feature-to-test evidence links.
- **Two six-hour LTN demand windows:** 203 completed, zero failed, zero pending
  tasks in each run. Recorded outcomes match exactly across runs and the prior
  six-hour check. Each run took approximately 12 seconds on the current machine.
- Existing LTN editor validation: zero findings. The original LTN file is unchanged.
- Dependency consistency check passed; whitespace/error checks passed.
- The GitHub workflow has been configured but has not been executed remotely here.

Tested source fingerprint:
`ec340a596d243ee3e0c30e4ec3d2bca634d22ce8cfa943256bb7117c644f8313`

LTN input SHA-256:
`853a68e7e4209d47dfd30b034e4aa5dc1783e303feabd5df9b4860034da87cd1`

Six-hour outcome SHA-256:
`593945bef454f5d602c82f0f15180cbc26285d3711d93102d483635da36faab5`

These remain bounded reference/repeatability checks, not full operational
validation. The simulator can drain assigned work beyond the demand window.
There are still 497 inventoried paths requiring individual semantic review.
The next implementation stage remains subject to the user's verification gate.
