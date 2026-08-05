# Creating A Simple Manual Task Scenario

## Aim

This page explains how to create a simple scenario based on manually defined
transport tasks.

Manual tasks are the easiest way to learn how the simulator behaves because each
task is explicit. You can see exactly what is supposed to move, where it starts,
where it ends, and when it becomes available.

## When To Use Manual Tasks

Manual tasks are useful when you want to:

- test whether two locations are connected by the route graph
- model a small number of known journeys
- confirm that an AMR type can carry a payload
- check route profiles or lift choices
- create a simple demonstration before using task generation

Manual tasks are less suitable for representing large recurring operational
workloads. For that, task generation is usually a better long-term approach.

## Key Concepts

**Payload**

The thing being moved. The payload must be compatible with at least one AMR type
if the task is to be completed by the fleet.

**Pickup location**

Where the task starts. This should be a named location in the config and should
be connected to the route graph.

**Dropoff location**

Where the task ends. This should also be a named location connected to the route
graph.

**Release time**

The time at which the task becomes available to the simulator. A task released
before the simulation starts may be available immediately.

**Route profile**

An optional routing constraint. For example, a task may be limited to a clean or
dirty route profile.

## Step 1: Start From A Working Config

Use a config that already:

- opens in the editor
- has floor layouts
- has a connected route graph
- has at least one AMR type
- has at least one payload type

It is safer to make a copy of a working config than to create a full hospital
model from scratch.

## Step 2: Identify The Locations

Choose a pickup and dropoff location.

In the editor, check that both locations:

- are on the intended floor
- are positioned correctly on the layout
- are connected to nearby graph nodes
- have names that are easy to recognise

If a location is not connected to the graph, the simulator may be unable to find
a route.

## Step 3: Check The Payload And AMR

Choose the payload for the task.

Check:

- the payload dimensions and mass are plausible
- at least one AMR type can carry it
- the AMR fleet has enough quantity for the scenario being tested

For early testing, use a simple payload and a known compatible AMR type.

## Step 4: Add The Task

Create a manual task with:

- a clear task ID
- pickup location
- dropoff location
- payload type
- release time
- priority
- route profile, if required

Use a small number of tasks at first. One or two tasks are enough to check
connectivity and routing.

## Step 5: Run The Scenario

Run the config from the launcher.

For a simple manual task test, the run should usually finish quickly. If it does
not, check whether the config includes other tasks or task-generation rules.

## Step 6: Review The Output

After the run completes:

- check the run status
- generate a report if needed
- open the visualiser
- confirm that the AMR follows a plausible route
- check whether the task completed or failed

The visualiser is especially useful for simple manual tasks because the expected
movement is easy to follow.

## What To Check

For each manual task, check:

- pickup and dropoff names are correct
- the payload exists
- the AMR fleet can carry the payload
- a route exists between pickup and dropoff
- any route profile still allows a valid route
- the release time is within the simulation period

## Common Problems

**The task fails immediately**

The pickup or dropoff may be unknown, disconnected, or incompatible with the
route graph.

**The AMR takes an unexpected route**

Check route profiles, lift restrictions, and graph edges. The simulator follows
the graph, not the corridor geometry shown in the DXF.

**No AMR takes the task**

The payload may not be compatible with the AMR fleet, or all compatible AMRs may
be unavailable.

**The run includes more activity than expected**

The config may include existing manual tasks or active task-generation rules.

## Modelling Notes

Manual tasks are a good way to test the mechanics of the model. They are also
useful for demonstrating a specific flow. However, they can become hard to
maintain if used to represent a large hospital workload over several days.

For operational scenarios, manual tasks and generated tasks should not be mixed
without a clear reason, otherwise it becomes difficult to understand what demand
the model is actually representing.
