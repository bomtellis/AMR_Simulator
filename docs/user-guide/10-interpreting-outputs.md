# Interpreting Outputs

## Aim

This page explains the main outputs produced by a simulation run and how the
tool uses them when presenting results.

Outputs should be interpreted together. A report summary, visualiser replay, and
CSV output each tell part of the story.

## Main Output Types

A launcher-managed run can include:

- a copy of the config used for the run
- simulation step CSV output
- visualiser CSV output
- failed task CSV output
- transport matrix or route-related outputs
- run manifest
- report PDF

The exact files depend on the run settings and whether the simulation completed.

## Run Manifest

The run manifest records the basic facts about a run.

It can include:

- run name
- status
- start time
- completion time
- source config
- copied config path
- output file paths
- report status

The launcher uses the manifest to display details for the selected run, allowing
the user to confirm it is the correct run before proceeding to analysis of the
results.

## Simulation Step CSV

The simulation step CSV is the detailed event output from the simulator.

It may contain rows for:

- AMR movement
- task assignment
- pickup and dropoff events
- lift transfer and waiting
- charging
- generated tasks
- failed tasks
- staff travel and handling
- payload and inventory events
- summary rows

This file is detailed and can be large. The report and visualiser provide more
accessible views of the run, while the CSV remains the underlying event record
for investigation.

## Visualiser CSV

The visualiser CSV is used by the visualiser module to replay or display the
run.

It supports checks of:

- whether movement looks plausible
- which routes AMRs used
- whether lifts were used as expected
- whether clean and dirty flows appear separated
- whether AMRs travel to the intended departments or locations

The visualiser is especially useful for spotting route-graph problems.

## Failed Tasks

Failed task output is one of the most important diagnostic sources.

A failed task can indicate:

- unknown pickup or dropoff location
- missing graph connection
- no route under the selected route profile
- incompatible payload and AMR
- location capacity issue
- missing physical container
- resource availability problem

Failed tasks should be reviewed before drawing conclusions from successful
tasks.

## Report PDF

The report module summarises key outputs from a completed run.

Depending on available data, report analysis can include:

- overall simulation summary
- AMR utilisation
- AMR route summary
- lift summary
- lift usage profile
- lift waiting
- generated task summary
- staff handling summary
- failed delivery summary
- location space utilisation
- recharge summary

The report provides an overview suitable for review and communication. The CSV
outputs remain available where specific events need to be traced.

The following sections describe analysis that may appear inside the Report PDF.
They are not separate output files unless a future reporting workflow exports
them separately.

## Report Section: AMR Utilisation

The AMR utilisation section is used to show whether the fleet is busy or
underused.

High utilisation may indicate:

- the fleet is too small
- travel distances are long
- lift waits are significant
- task demand is concentrated into peaks

Low utilisation may indicate:

- the fleet is larger than needed
- demand is low
- task generation is not active
- tasks are failing before assignment

Utilisation should be interpreted alongside task completion and failed tasks.

## Report Section: Lift Use And Waiting

The lift use and waiting sections are used to identify bottlenecks in
multi-floor models.

They can show:

- lift trips
- total lift time
- average lift utilisation
- lift waits
- peak lift demand
- whether specific lifts dominate activity

A scenario may complete all tasks but still create unacceptable lift pressure.

## Report Section: Generated Task Summary

The generated task summary is used to explain demand created during the run.

They can show:

- which categories generated tasks
- how many tasks were generated
- when tasks were released
- whether return tasks were created
- whether generated tasks failed

This is especially important when comparing scenarios with task generation
enabled.

## Report Section: Staff Handling Summary

The staff handling summary is used to explain whether staff assumptions affected
task timing.

It can show:

- staff resource groups
- staff travel events
- staff payload handling events
- wait time for staff availability
- shift pattern effects

This output should be interpreted as staff-assisted handling, not porter-led
transport.

## Report Section: Location Capacity And Inventory

Some report sections describe location capacity or inventory-space behaviour.

These outputs are used to test:

- whether receipt points become overfilled
- whether collection points have enough space
- whether payload instances remain in expected locations
- whether capacity-related failures occur

Capacity problems can be operationally important even when routing works.

## Report Section: Recharge And Energy

Recharge and energy analysis is used to identify whether battery assumptions are
affecting performance.

They can show:

- recharge counts
- recharge time
- recharge energy
- whether AMRs leave tasks to recharge
- whether charging locations become operationally important

Battery assumptions should be checked before using energy results for planning.

## Step 1: Confirm The Run Completed

Start with the run status.

Do not interpret a cancelled or failed run as if it represents a complete
scenario.

## Step 2: Review Failed Tasks

Look at failed tasks before reviewing averages or utilisation.

If many tasks failed, summary statistics may understate the demand that the
scenario was supposed to serve.

## Step 3: Check The Visualiser

The visualiser displays route and lift behaviour so that movement can be checked
for plausibility.

This catches many problems that are hard to see in tables.

## Step 4: Read The Report

The report presents:

- overall task performance
- AMR workload
- lift demand
- generated task demand
- staff and capacity constraints

## Step 5: Compare Against The Scenario Question

Return to the question the scenario was designed to answer.

For example:

- Were receiving departments served on time?
- Were lift waits tolerable?
- Did route restrictions create bottlenecks?
- Did a larger fleet actually improve outcomes?

## Common Problems

**Averages look acceptable but individual tasks fail**

Review failed tasks and task-level timing. Averages can hide operationally
important exceptions.

**AMR utilisation is low but tasks fail**

The issue may be route feasibility, payload compatibility, task timing, or
location capacity rather than fleet size.

**Lift utilisation is modest but waits are high**

Demand may be concentrated into short peaks. Review lift usage by time of day.

**Generated task numbers differ between runs**

Check active categories, department settings, simulation dates, and task
generation modes.

## Modelling Notes

Simulation outputs are evidence for a scenario under a set of assumptions. They
are not proof that real-world operations will behave exactly the same way.

The strongest conclusions come from comparing well-designed scenarios and
checking whether the same pattern appears across several runs.
