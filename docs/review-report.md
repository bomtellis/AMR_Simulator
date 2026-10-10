---
title: Investigate and report
nav_order: 7
has_children: true
permalink: /review-report/
---
# Investigate and report

## Investigate the saved run

In **Simulate**, select the intended run and choose **Investigate selected run**.
Review the saved input revision and run status before comparing numbers. Filter
tasks by outcome or search for an ID, then open its supporting event evidence.

Follow the task timeline's recorded payload, journey or lift identity. A task
request, robot trip and lift movement are different things: several tasks may
share a physical movement. Pending-at-stop work is shown separately from failures.

Timelines page **500 events** at a time. **Export selected evidence** includes
all pages for the selected task, related identity, metric or lift check. Logs
above **250,000 events or 300 MiB** are rejected rather than silently truncated.
Use a bounded run for focused investigation when necessary.

**Review → Route checks** checks static navigation against the saved run input
snapshot. Reachable does not establish that a recorded journey physically
completed. A log without a frozen input snapshot has no verified route coverage;
current editable settings are not substituted.

## Inspect Playback

Choose **Playback selected run**. The map uses frozen inputs. Seek with the
timeline and change floors to follow corridors, lift travel, charging and washing.
**Display** controls visibility and the optional legend; **Inspect** opens task,
lift and payload monitors. Drag the divider above the timeline to resize it.

Check one familiar route against real distances, watch an outbound and return
journey, and inspect failed or unexpectedly late work. Playback illustrates
recorded events; it does not independently certify the physical installation.

## Export the report

1. Return to Simulate, select the completed run and choose **Report selected run**.
2. Select the sections needed for the feasibility question and choose
   **Generate report**. For a first review include demand, service, utilisation,
   failed delivery and relevant lift/charging sections.
3. Use **Open generated PDF** and retain its supporting CSVs in the selected
   run's reports folder.

Project reporting uses the frozen run configuration, not current project edits.
For a standalone CSV report, supply the JSON used for that run. Missing evidence
is unavailable, not zero. Retain the report's coverage notes when sharing results.

Read [operational KPI definitions](report-kpis.md) for demand, service, capacity,
efficiency, bottlenecks, reliability, resources and cost/sustainability. Read
[report structure and PDF insertion](report-structure.md) for SLA assignments,
section selection and adding a supplement to an existing PDF.

## Exports for further analysis

| Output | Use and interpretation |
| --- | --- |
| Event CSV | Trace actual recorded requests, assignment, movement, handling and failures. |
| KPI CSVs | Full rows supporting summary, hourly, stream, request, overdue, queue, route and charger tables. PDF tables may show only a subset. |
| Journey/journey-flow CSVs | Task-level origins, destinations, departments, outcomes and identifiable returns. Counts represent requests, not lift trips. |
| Lift movements CSV | One row per logged transfer or empty reposition; shared tasks do not create duplicate trips. |
| Lift usage CSV | Choose **Export 5-minute lift usage CSV** for five-minute and hourly cohorts without generating a PDF. |
| Department category reviews | Export per-category department PDFs and/or Excel files using the report dialog's category review options. |

For lift travel only, choose **Lift travel CSV** and **Export lift travel CSV only
(skip PDF)** in the reporting dialog. Supply matching JSON when resolving robot
and payload weights. Empty repositioning is lift travel while the requesting
robot waits; unknown endpoints or weights remain labelled/blank as documented.

For category reviews choose **Export category reviews** and a PDF/Excel format;
**Reviews only** skips the main report and lift exports. Even an inactive
configured category can have a clearly empty review.

## Draw a feasibility conclusion

Review task completion and pending/failed work before fleet utilisation. Inspect
peak lift and dispatch waits, not only daily averages. Confirm that demand was
actually generated for the intended departments and dates. Compare alternatives
under consistent inputs and explain the assumptions that changed.

Fleet/charger sizing is a planning estimate. Rerun the proposed fleet rather
than treating a report estimate as an optimisation guarantee. Energy reflects
the model ledger; costs and equipment reliability require their own period inputs.

See [interpreting outputs](user-guide/10-interpreting-outputs.md) and
[designing comparisons](user-guide/09-designing-scenarios-for-comparison.md).
