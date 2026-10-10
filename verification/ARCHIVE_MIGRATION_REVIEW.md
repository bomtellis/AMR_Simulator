# Portable archive migration — 4 October 2026

The current `.amrproj` manifest is version 2. It requires explicit
`external_results` metadata, keeping run links as a defined part of the
portable archive. The immediately previous version 1 opens in memory, with
missing run-link metadata defaulting to an empty list. Opening does not rewrite
the file. The editor status says that Save upgrades it to version 2; Save and
Save As write the current manifest without adding a configuration revision
when inputs are unchanged. Unsupported versions name the versions this app can
open and instruct the user to export JSON and drawings in a compatible app.
Version 2 archives missing their required metadata ask the user to restore a
valid backup.

On the supplied 15.2 MB version 1 LTN archive, a copied Save As produced a
version 2 archive with identical configuration, all five embedded drawings and
the same revision history. All three saved-run links still resolve to their
original folders after rebasing. The source SHA-256 remained
`4e21a7bb78e628233e546ac521e52ffeff9dc6421842193301cd6f66551b8c0a`.
Machine-readable evidence is retained at
`installer/build/ltn-migration/migration.json` (ignored build output).
The fresh installed GUI also opened the bundled version 1 LTN input and saved
the bounded exercise as version 2 before simulation and report export.

The project storage, saved-run link, editor lifecycle, workspace, checks and
CAD-focused group passes 104 tests. A broader archive, saved-run, playback,
recovery and evidence group passes 118 tests. These cover read-without-rewrite,
editor upgrade, invalid-current-version metadata and actionable
unsupported-version errors. This closes checkpoint 4's immediately previous
archive migration item. Future schema versions and unsupported configuration
fields may still need separate migration work.
