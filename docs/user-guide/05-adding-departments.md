# Adding Departments

## Aim

This page explains what departments represent in a scenario config and why they
matter when building more realistic hospital workloads.

Departments are not just labels on the floorplan. They can provide operational
data used by task generation, waste calculations, and scenario interpretation.

## When To Use Departments

Use departments when a scenario needs to represent demand from hospital areas
rather than only a fixed list of manual tasks.

Departments are useful for modelling:

- recurring deliveries to clinical areas
- waste generation from wards or departments
- task generation by service category
- operating hours and active days
- demand linked to beds, patient turnover, or staff count

If a scenario only tests one or two known journeys, manual tasks may be enough.

## Key Concepts

**Department**

A hospital area or service area that may generate demand.

**Department location**

A graph or layout location associated with the department. Departments may have
different locations for different task categories.

**Operating hours**

The times when the department is considered active. These can influence when
generated tasks are released.

**Active days**

The days of the week when the department is active.

**Demand fields**

Fields such as bed count, patient turnover, and staff count can be used by waste
or activity models.

## Common Department Fields

A department may include:

- name or identifier
- floor
- enabled status
- operating start and end time
- active days
- bed count
- patient turnover
- staff count
- task-generation locations
- waste stream settings

The exact fields used depend on which generation features are enabled.

## Department Locations

Task generation often needs to know where a department should receive or send
items.

For example, a department might need different locations for:

- pharmacy deliveries
- linen deliveries
- waste collection
- stores deliveries
- clean returns
- dirty returns

These are stored as task-generation locations. They let generated tasks use the
right pickup or dropoff location for each workflow.

## Operating Hours And Active Days

The task generation code checks whether departments are active.

Operating hours and active days can affect:

- whether a generated task should be created
- when a task is released
- how activity is spread across a time period
- whether a task is treated as outside normal hours

For simple early scenarios, use broad operating hours and keep active days easy
to understand. More precise operating assumptions can be added once the basic
scenario works.

## Bed Count, Turnover, And Staff Count

Some generator logic uses department demand fields.

For department waste modelling, the code includes a waste-rate calculation based
on:

- bed count
- patient turnover
- staff count
- waste coefficients

This means these values should not be treated as decorative metadata. If they
are used by an active generator, they can change the amount of simulated work.

## Step 1: Decide What The Department Represents

Before adding a department, decide whether it represents:

- a ward
- a clinical department
- a service area
- a theatre area
- a collection or receipt zone
- another operational grouping

The model will be easier to understand if department names match operational
language used by staff.

## Step 2: Assign Locations

Link the department to the locations needed by the intended workflows.

Check that those locations:

- exist in the config
- are on the correct floor
- are connected to the route graph
- are appropriate for the workflow being modelled

Avoid using the same location for several workflows unless that is the intended
operational assumption.

## Step 3: Set Operating Assumptions

Set active days and operating times.

For a first pass, choose values that are easy to defend. If the department is
expected to receive deliveries throughout the day, make the operating window
wide enough for those tasks.

## Step 4: Add Demand Assumptions

If the department will be used for waste or volume-based generation, check the
demand fields carefully.

Do not add bed count, turnover, or staff count values just to fill the form.
They should reflect the modelling assumption being tested.

## Step 5: Test With A Small Scenario

After adding or editing departments, run a small scenario before running a full
hospital model.

Check:

- generated tasks use the expected departments
- pickup and dropoff locations are correct
- tasks are released during the expected operating periods
- waste or volume assumptions create plausible demand

## Common Problems

**Generated tasks go to the wrong place**

Check the department task-generation locations and category overrides.

**No tasks are generated for a department**

The department may be disabled, outside active days, outside operating hours, or
missing the required category location.

**Waste demand looks too high or too low**

Check bed count, patient turnover, staff count, and waste coefficients.

**A department exists but has no operational effect**

Departments only affect the simulation when referenced by active task-generation
or waste-generation rules.

## Modelling Notes

Departments are a bridge between hospital operations and the route model. They
help turn a floorplan into a scenario that reflects clinical and logistical
demand.

For comparative modelling, keep department assumptions consistent between
scenarios unless the comparison is specifically testing a change in departmental
demand.
