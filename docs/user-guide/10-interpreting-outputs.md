---
title: Interpreting outputs
nav_order: 4
parent: Investigate and report
---
# Interpreting outputs

Use the [investigation and report workflow](../review-report.md) to open evidence
for a selected saved run. A project run contains frozen configuration and checks,
event CSVs, a manifest, and any later report exports in its external folder.
Exact files depend on output detail and process completion.

## Read outcomes before summaries

Confirm the process status, then distinguish completed tasks, recorded failures
and pending-at-stop work. A completed simulation process can include failed or
unfinished service. A cancelled process is partial observation, not a complete
scenario. Investigate failures before interpreting averages or fleet utilisation.

The event log can record release/assignment, pickup/dropoff, movement, lift waits
and transfer, charging, payload/inventory events and staff travel/handling.
Use **Investigate selected run** to link tasks and identities to event evidence.
Playback checks plausibility against saved inputs; it is not an independent
verification of the real installation.

## What the figures can tell you

| Result | Read alongside it |
| --- | --- |
| Fleet utilisation | Completed/failed/pending demand, charging, observation duration and peaks. |
| Request time and SLA | Recorded release/deadline coverage and unserved requests, not only completed-task averages. |
| Lift use/waiting | Empty repositioning, short peaks, flow permissions and floor-specific demand. |
| Generated demand | Effective category/group/department rules and runtime return requests. |
| Staff handling | Resource assignment, waits, hours and model expansion assumptions; not full porter transport. |
| Inventory/capacity | Actual stock/container identity, receiving spaces, bay entry and collection/return behaviour. |
| Recharge/energy | Battery, charge bays, explicit wait evidence and energy-ledger coverage. |

## Trace exports correctly

Task requests, robot journeys and lift transfers are different counts. Shared
tasks do not multiply a physical lift movement. A journey's assignment time is
dispatch time, not necessarily pickup time. Empty lift repositioning occurs while
the robot waits. Unknown endpoints, weights or return-parent identity must remain
unknown rather than being inferred from an attractive pattern.

Reports include operational KPI CSV exports, journey/flow/movement tables and
SLA evidence where available. Use [KPI definitions](../report-kpis.md) for exact
denominators, exclusions, fallbacks and optional period inputs. Missing evidence
is unavailable, not zero. Printed tables can be shorter than their full CSVs.

## Make a defensible comparison

Confirm demand matches the scenario question, the layout scale is credible and
important routes look plausible. Compare variants under consistent assumptions.
Fleet/charger sizing and cost/energy figures are planning evidence with declared
limits, not proof of a particular product's performance or an optimal design.
