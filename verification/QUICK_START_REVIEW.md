# Quick-start delivery review — 4 October 2026

The Run investigation reference now explains the task timeline choice for
recorded payload, journey and lift identities. Markdown, DOCX and PDF were
regenerated from the shared in-app text; the PDF remains four pages, and its
updated final page was rendered and visually checked.

Checkpoint 9 now has a source-checkout walkthrough and illustrated guide.
Help → Guided walkthrough opens a nonmodal window with exactly two exercises:
the small map with robot types R1 and R2, and the supplied LTN project. Every
step gives an action, expected state and workspace shortcut. A separate controls
reference covers the topics named in the roadmap. The window also opens the
illustrated PDF from Help.

The small-map input is `docs/quick-start/small-map.json`. Its initial B–C gap
produces `TASK_UNREACHABLE`; joining B–C clears errors and warnings. A direct
reference simulation then completes T1 with zero failed and zero pending tasks.
The LTN exercise uses the supplied portable project, a 05:00–11:00 window and
the navigable `LOCAL_BAY_ENTRY_OVERLAP` findings. An installed six-hour run of
that archive produced 206 completed / 0 failed / 0 pending tasks. The earlier
150 / 15 / 0 engineering reference used the separate working `ltn.json` input;
it is not the bundled exercise archive. Counts can change with edited inputs.

`docs/quick-start/AMR-Simulator-Quick-Start.md`, `.docx` and `.pdf` are built
from the same exercise and reference text as the in-app walkthrough. The guide
uses captures of the delivered workbench. Markdown, DOCX and PDF each contain
all 13 step titles and six reference headings. Word-exported DOCX and generated
PDF were rendered and visually checked at four US Letter pages each. The
guide build script and capture script remain beside the outputs.
The refreshed run-investigation reference explains selected-evidence export
across pages and the current 250,000-event / 300 MiB loader limits; all three
guide formats contain it, and the PDF still renders at four pages.

Focused verification: 88 workbench, walkthrough, project-run/report and Project
checks tests pass. The current development installer contains both exercise
inputs and all three guide formats. Installed GUI checks opened the LTN archive
with all six DXF floors, the six-step LTN walkthrough, the bounded run, event
investigation and a PDF report; the small-map check also passed. See
`OFFLINE_INSTALLER_REVIEW.md`. Physical screen review, the external PDF viewer,
the later user testing phase and seven-day LTN behaviour remain open.
