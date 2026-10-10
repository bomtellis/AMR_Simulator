---
title: Start here
nav_order: 1
has_children: true
permalink: /
---
# AMR Simulator operating guide

Use the AMR Simulator to explore whether a proposed robot fleet, hospital layout
and logistics workload can meet your operational needs. Build a scenario, check
its assumptions, save a simulation run, and inspect the recorded evidence before
drawing conclusions.

The application runs on your computer. This website explains how to operate it.

[Install and open](install.md){: .btn .btn-primary }
[Run your first simulation](quick-start/AMR-Simulator-Quick-Start.md){: .btn }
[Build a three-floor model](building-tutorial/Building-Flow-Tutorial.md){: .btn }

## Follow the workbench

| Stage | Your action | What to retain |
| --- | --- | --- |
| Layout | Import drawings and connect locations, corridors and lift stops. | A correctly scaled, connected model. |
| Configuration | Define resources, payloads, departments and demand. | Written, defensible operational assumptions. |
| Check | Review findings and preview demand. | Current findings and explanations for accepted warnings. |
| Simulate | Save, check and simulate a project revision. | A completed run and its frozen inputs. |
| Review | Investigate tasks and follow movement in Playback. | Reasons for failed, late or pending work. |
| Report | Export selected report sections and supporting records. | A PDF and CSV evidence from the same saved run. |

## Find the guidance you need

- **Getting started:** [Windows installation](install.md), the
  [small-map exercise](quick-start/AMR-Simulator-Quick-Start.md), and
  [what the tool represents](user-guide/00-start-here.md).
- **Building a scenario:** [projects and layouts](build-model.md),
  [resources and demand](configure.md), and the illustrated
  [building flow tutorial](building-tutorial/Building-Flow-Tutorial.md).
- **Testing feasibility:** [checks and simulation](check-simulate.md),
  [investigation and reports](review-report.md), and
  [controlled comparisons](user-guide/09-designing-scenarios-for-comparison.md).
- **Resolving uncertainty:** [troubleshooting](troubleshooting.md),
  [model limitations](user-guide/11-known-limitations-and-modelling-assumptions.md),
  and [technical reference](technical.md).

Use the search box to find a setting, task outcome or topic. The sidebar groups
the pages by workflow; individual pages also provide section links. You can print
an individual page from your browser.

{: .warning }
A successful simulation is evidence for its configured assumptions. It does not
establish that a hospital, robot product or lift system will perform identically
in practice. Review demand, failed and pending tasks, route scale, and evidence
coverage alongside summary statistics.

## Version and example availability

This edition was reviewed against [main {{ site.data.source.short_commit }}](https://github.com/bomtellis/AMR_Simulator/tree/{{ site.data.source.commit }})
on {{ site.data.source.reviewed }}. Older verification checkpoints record behaviour
at their own revisions; use current controls and rerun your own scenario.

The [small-map JSON](quick-start/small-map.json) and tutorial floor drawings are
tracked practice inputs. Portable tutorial archives are generated locally.
The supplied LTN archive mentioned in the walkthrough requires a separately
distributed development package; it is not a downloadable release here.
