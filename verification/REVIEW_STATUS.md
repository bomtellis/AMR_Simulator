# Stage 1 clash review — 2 October 2026

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
