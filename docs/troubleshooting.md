---
title: Troubleshooting and limitations
nav_order: 8
has_children: true
permalink: /troubleshooting/
---
# Troubleshooting and limitations

| Symptom | What to check | Next action |
| --- | --- | --- |
| Python or `py -3.13` is unavailable | Installed Python version and Windows launcher. | Install Python 3.13, reopen PowerShell and follow the installation page. |
| A module cannot be imported | Which Python executable you launched and whether pip finished. | Use `.venv\Scripts\python.exe` for both installation and launch. |
| Installer download cannot be found | No installer release is published at the reviewed revision. | Use source setup or obtain a versioned development package from your project team. |
| LTN drawings are missing | Source JSON may refer to machine-specific external files. | Obtain the supplied portable project; use the self-contained small map meanwhile. |
| Layout is empty or wrong size | Drawing path, selected floor/page, units, scale and alignment. | Repair the underlay; verify a known distance before drawing routes. |
| Project save cannot package drawings | Referenced external files must exist. | Relink them before portable save; `--without-drawings` only skips rendering. |
| A route looks connected but fails | Actual directed graph edges, endpoints, profile permissions and lift stops. | Run checks and inspect the affected settings; use a one-task test. |
| No demand appears | Global/category enablement, dates, department hours, endpoint assignments and overrides. | Build Demand preview and read zero-work and rule-reconciliation explanations. |
| Unexpectedly high demand | Multiple enabled generators, returns, exchanges and shared-container rules. | Isolate one workflow and reconcile its expected releases. |
| Low utilisation with poor service | Failed tasks, incompatible payloads, stock availability, route restrictions and waits. | Inspect request outcomes before increasing fleet size. |
| Charger or inventory pressure | Reachability, compatible spaces, bay geometry and seeded stock. | Inspect the affected location and evidence; capacity does not imply manoeuvre clearance. |
| Checks cannot approve a run | Errors, unreviewed warnings, or findings made stale by editing. | Repair, rerun checks, and review the current warning set. |
| Detailed mode is not ready | Explicit engineering movement inputs, placements and clearances. | Read mode details and correct findings; start with Simple for graph exercises. |
| Report or Playback rejects a run | Completion status and integrity of its frozen inputs/logs. | Select matching completed evidence; retain the original results folder. |
| Investigation rejects a large log | The 250,000-event/300 MiB limits. | Run a focused shorter study; do not treat an incomplete log as full service evidence. |
| A long simulation seems stuck | Size, output detail, demand window and worker progress. | Develop with a short window; inspect process messages before cancelling. |

## Review a finding without hiding it

In **Check**, search for the finding code, inspect its consequence and use
**Go to affected settings**. For `LOCAL_BAY_ENTRY_OVERLAP`, review actual spaces
and entry paths at the named location. A bay-bound warning is not proof every
task fails, but suppressing its physical path check is not a layout repair.

If you deliberately enable **Ignore invalid local manoeuvres**, retain the
warning and event fallback flags with the conclusion. Rerun the scenario after
correcting the underlying geometry.

## Preserve evidence when asking for help

Retain the application source revision, project revision, run status, finding
code, task ID and relevant event export. Keep the frozen configuration and log
with the results folder. Describe the expected result and actual result.
Share only the operational data appropriate for the recipient.

Read [known limitations and assumptions](user-guide/11-known-limitations-and-modelling-assumptions.md)
before using a study for a decision. For developers, the
[verification inventory](https://github.com/bomtellis/AMR_Simulator/tree/main/verification)
records checkpoint-specific contracts, evidence and outstanding work; historical
test counts are not a current full-system certification.
