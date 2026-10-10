---
title: What the tool represents
nav_order: 1
parent: Start here
---
# What the tool represents

The AMR Simulator is a comparative feasibility workbench for hospital logistics.
A scenario describes the layout, robot fleet, payloads, task demand, lift access,
inventory and handling assumptions. A saved run records what happened under
those inputs so you can investigate service, resources and bottlenecks.

## The current application

Launch `amr_app.py`. The workbench groups the workflow into Layout,
Configuration, Check, Simulate, Review and Report. The legacy launcher remains
available for existing source workflows, but is not the starting point here.

- **Project:** configuration, drawings and revisions saved in a portable `.amrproj`.
- **JSON configuration:** simulator input, with external drawing references.
- **Layout:** floor drawings and the graph connecting operational locations.
- **Resources:** robots, lifts, charging bays, inventory spaces and staff support.
- **Payload:** the configured item being transported, including physical and handling assumptions.
- **Task:** a request with endpoints, payload, release time, priority and optional target/profile.
- **Demand generation:** rules that create work from calendars, departments or accumulation.
- **Run:** saved execution evidence bound to frozen project inputs; results remain external.

## Start small

Complete the [small-map exercise](../quick-start/AMR-Simulator-Quick-Start.md),
then the [building flow tutorial](../building-tutorial/Building-Flow-Tutorial.md).
Test one route and category before combining whole-hospital demand.

Ask a clear question: will this fleet meet these requests, with this layout and
these restrictions? Keep demand and assumptions consistent when comparing
alternatives. Inspect failed/pending tasks, route scale and lift waits before
treating utilisation or average times as useful evidence.

The current staff feature is staff-assisted handling with related travel; it is
not a complete porter-led logistics model. Simple mode is graph based. Detailed
mode needs explicit geometric inputs and readiness checks. Neither a successful
run nor a visually plausible playback is real-world certification.
