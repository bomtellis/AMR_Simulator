---
title: Check and simulate
nav_order: 6
permalink: /check-simulate/
---
# Check and simulate

## Run current project checks

1. Save your edits and open **Check → Run checks**.
2. Filter by severity or search for a finding. Read its consequence and setting path.
3. Use **Go to affected settings** to repair the input, then rerun checks.
4. Correct errors. Acknowledge a warning only after reviewing its operational
   meaning and accepting that assumption for this run.

Editing makes previous checks stale. Old acknowledgements are not approval of
new inputs. Passing checks does not prove every generated task, resource conflict
or physical movement is valid.

Choose **Demand preview** beside Run checks, then **Build preview**, to inspect
planned releases and timetable/rule reconciliation before committing to a long run.

## Choose a simulation mode

In **Configuration → Simulation settings → Run period**, select the mode and
inspect **Show mode details**.

| Mode | Intended use | Required interpretation |
| --- | --- | --- |
| Simple | Initial connectivity tests and comparative graph-based studies. | Graph distances and configured service/resource rules; not complete swept-footprint certification. |
| Detailed | Explicit geometric movement and traffic studies. | Requires complete movement settings, reference offsets, per-robot initial placements and separate wall/robot clearances. |
| Historical geometric compatibility | Opening older configurations without an explicit mode. | Preserves their older contract; it is not a selectable shortcut to a valid Detailed study. |

Switching mode changes structural settings and reports readiness findings. It
does not invent missing engineering measurements or guarantee that the project
is ready to run. Start the practice exercises in Simple mode. See
[geometry and movement reference](reference/geometry.md) before selecting Detailed.

## Set the run period and initial conditions

Set **Starts** and the intended end of generated demand in **Run period**.
Use a short window while developing a model. An end to demand generation does
not necessarily stop all already released work at that exact time; inspect the
observed run end and outcome records.

**Maximum task deferral** is in **minutes**. `0`, displayed as **Unlimited**,
disables the limit. A positive value limits release-to-AMR-assignment waiting,
including waits for a preceding return pickup. Retries do not reset that timer;
assigned work can continue. Return/collection tasks have their own release timer.

Check **Initial conditions → Inventory and container state**. Initial stock and
seeded physical containers affect whether tasks can pick up real items. Do not
change them between comparisons unless that is the question being tested.

{: .warning }
**Ignore invalid local manoeuvres** defaults to off. Enabling it can replace a
failed local bay path with direct movement; events identify this as
`unverified_direct_fallback`. It is an explicit assumption, not a physical repair.
It does not bypass corridor, door or traffic checks.

## Save a revision-bound run

1. Open **Simulate → Save, check and simulate**.
2. Review the findings for the inputs being saved. Confirm the run only once you
   have corrected errors and reviewed warnings.
3. Wait for the worker to finish. Do not edit the project during the practice run.
4. Select the new saved run and review its process status and task outcomes.

Each run retains its configuration, checks and event evidence in an external
results folder. Later project edits do not alter those frozen inputs. Keep that
folder with the study. If you move it, use the application's relinking controls
and matching evidence; substituting an unrelated log is not a valid recovery.

Use output detail sufficient for your review question. Large models can take a
long time and produce large logs; a cancelled or failed process is not evidence
of completed operational service.

## Distinguish process status from task outcome

- **Completed run:** the simulation worker completed; individual tasks can still
  have failed or remained pending at the observation cut-off.
- **Completed task:** recorded completion for that request.
- **Failed task:** a recorded failure; inspect its cause before interpreting averages.
- **Pending at stop:** outstanding work recorded at the cut-off; it is not a failed task.

Continue with [investigation and reports](review-report.md).
