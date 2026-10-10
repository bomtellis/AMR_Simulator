---
title: Model assumptions and limits
nav_order: 1
parent: Troubleshooting and limitations
---
# Known limitations and modelling assumptions

The simulator is a comparative planning tool. Its results apply to the configured
scenario and software revision, not every real-world hospital condition.

## Layout and physical movement

Simple mode uses the configured graph and resource/service assumptions. A DXF
or PDF background does not automatically create a valid route or collision wall.
Check units, known distances, directed connectivity, doors, lift stops and
permissions. Colours and visible layers are not route-access rules.

Detailed mode needs explicit geometric movement, physical inputs, per-robot
placements, reference points and clearances. Switching modes cannot supply
engineering measurements. Unresolved clearance or search limits do not establish
a clear route. A failing requested route does not prove every alternative fails.

The local-manoeuvre direct fallback is an explicit unverified assumption. Keep its
warning and event flags with any result; do not present it as physical feasibility.

## Demand, stock and staffing

Generated workloads depend on dates, categories, department/group overrides,
hours, thresholds, initial stock and return/exchange rules. Demand preview is
useful but does not establish every runtime-dependent return or contention effect.
Reconcile releases and failures in run evidence.

Inventory and bay representations do not establish real storage, cleaning,
marshalling or infection-control suitability. Staff assistance models handling
and related travel, not a complete porter-led transport service. Resource pools
can expand under contention, so a configured initial count is not necessarily a
hard workforce limit. Interpret recorded sizing and fallback behaviour accordingly.

## Lifts, equipment and missing real-world factors

Lift outcomes depend on service timing, repositioning, reservations, dimensions,
permissions, health/repair assumptions and temporal demand. The configured
reliability approximation is not a calibrated stochastic fault model. Neither
task failures nor missing equipment evidence prove an equipment fault rate.

The model does not automatically capture every clinical interruption, ad hoc
workaround, temporary blockage, infection-prevention judgement, human behaviour
or vendor fleet-management rule. Represent relevant assumptions explicitly and
review them with operational staff.

Lift-site proposals are geometrically screened study candidates. They require
separate structural and operational assessment. A better modelled distance is
not a construction approval.

## Reports, partial observation and comparisons

A completed process can still have failed or pending tasks. Cancelled/failed
processes are not complete service evidence. Review outcome coverage and time
cut-offs before comparing utilisation or averages. Partial movement distance can
be estimated by elapsed time; it does not reconstruct exact acceleration.

Fleet/charger sizing is a planning estimate; simulate the proposed alternative.
Energy reflects the configured ledger and excludes some real energy costs.
Financial/reliability results require independent period inputs. Missing evidence
must remain unavailable. Keep the [KPI calculation rules](../report-kpis.md) with
the report.

## Verification boundaries

Project checks detect a useful subset of invalid or risky inputs. Passing them
does not prove every option, workload, contention pattern or clinical assumption.
Historical verification reviews record specific revisions; their earlier gaps
and test counts are not statements of current full-system certification.

Before relying on a result, confirm saved inputs, credible scale/routes, intended
demand, task outcomes, plausible lift/resource use and relevant evidence coverage.
Retain the software revision and compare several controlled scenarios rather
than treating one run as a precise prediction.
