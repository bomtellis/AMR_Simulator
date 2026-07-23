# Autonomous Mobile Robot Simulator

***Project licensed under AGPL.***

This script simulates paths taken by autonomous mobile robots around a facility to deliver payloads to destinations.

This uses a graph per floor level and lifts to naviagte the internals of a building.

The graph nodes and edges are ***explictly*** defined in the json file.

# Getting Started

```
    python simulator.py --write-example your_file_name.json
    python simulator.py --config your_file_name.json --verbose --interactive

    ^C to quit and save .csv default name = "simulation_steps.csv"
    Use --verbose-csv path_to_file.csv to name file
```

## Defining the simulation parameters
```
"simulation": {
    "start_datetime": "2026-01-01T08:00:00", # start time of the simulation
    "tick_rate": 120.0 # does nothing currently for future when GUI is implemented
  },
```

## Defining the building

```
  "building": {
    "load_unload_time_sec": 20.0, # how long it takes to drop a payload off
    "floor_height_m": 4.0, # how tall is each floor
    "charge_location": "Stores" # where do you charge the robots up must be a defined location
  },
```

## Defining Locations

`X` is distance from datum in metres

`Y` is distance from datum in metres

```
"locations": [
    ...
    {
      "name": "Stores",
      "floor": 0,
      "x": 0,
      "y": 0
    },
    ...
]
```

## Defining Nodes and Edges

Nodes on the floor are defined as `Cx_y` where `x` is the level number and `y` is the node letter.

Lift edges are defined as `Lift-x-Fy` where `x` is the lift number and `y` is the floor level.

```
{
    "corridors": {
        "nodes": [],
        "edges": [],
        "auto_connect": false
    }
}
```

Nodes must have the four keys to operate

```
"nodes": [
    ...
    {
        "name": "C0-A",
        "floor": 0,
        "x": 4,
        "y": 0
    },
    ...
]
```
Edges must have these two keys to operate. Do not make a circular reference e.g. `C0-C --> C0-B --> C0-B --> C0-C` as this will confuse the pathfinding function

```
"edges": [
    ...
    {
        "from": "C0-C",
        "to": "Pharmacy"
    },
    {
        "from": "Lift-2-F0",
        "to": "C0-C"
    },
    ...
]
```

## Defining payloads

The name used in the definition is used in the task.

```
{
    "name": "food_trolley",
    "weight_kg": 120
    "size_units": 1.0
}
```

## Defining AMRs

AMRs are the robots that move around a facility to transport goods.

```
"amrs": [
    {
      "id": "AMR-A", # unique per type of AMR
      "quantity": 2, # how many do you have, this gets incremented automatically e.g. AMR-A-1..2..3
      "payload_capacity_kg": 150, # total weight bearing capacity, payload > capacity = no go
      "payload_size_capacity": 1.0, # related to payload size factor 
      "speed_m_per_sec": 1.2, # how quick can this thing move
      "motor_power_w": 900, # motor power
      "battery_capacity_kwh": 6.5, # how big are the batteries
      "battery_charge_rate_kw": 2.2, # how quick do they recharge
      "recharge_threshold_percent": 20.0, # when do you want to retire this unit to recharge %
      "battery_soc_percent": 100.0, # inital state %
      "start_location": "Stores" # where does it begin in the simulation
    }
],
```

## Defining Lifts
```
"lifts": [
    {
      "id": "Lift-1", # name of the lift
      "served_floors": [ # how many levels can this lift get to
        0,
        1,
        2,
        3
      ],
      "speed_floors_per_sec": 0.5, # how fast floors per sec linked to distance between floors e.g 4m between floors * 0.5 = 2m/s
      "door_time_sec": 4, # how long does it take for the doors to open
      "boarding_time_sec": 6, # how quickly can the amr get into the lift
      "capacity_size_units": 1.0, # linked to payload size
      "start_floor": 0, # where does the lift start in the simulation
      "floor_locations": { # where is the lift in each level, useful for offsets if plans do not line up.
        "0": {
          "x": 5,
          "y": 2
        },
        "1": {
          "x": 5,
          "y": 2
        },
        "2": {
          "x": 5,
          "y": 2
        },
        "3": {
          "x": 5,
          "y": 2
        }
      }
    },
    ...
  ],
```

## Defining Tasks
```
"tasks": [
    {
      "id": "T1", # can be anything as long as its unique
      "pickup": "Stores", # location as defined earlier
      "dropoff": "Ward-1A", # same as above
      "payload": "food_trolley", # what is it carrying, defined in payloads
      "release_datetime": "2026-01-01T08:00:00", # when does this task get added to the queue
      "priority": 10 # how desparately does this need to be done
    },
]
```

## Department drop-off zones

A department category can associate its normal pickup/drop-off locations with one
or more intermediate drop-off zones. The normal locations remain the final human
destinations; the AMR stages the payload at a zone, department staff complete the
last leg, and return the configured empty/equivalent payload to that zone for the
AMR return journey.

```json
{
  "id": "D1",
  "name": "Ward 1",
  "task_generation_locations": {
    "catering": {
      "pickup_dropoff_locations": ["Ward-1A"],
      "dropoff_zone_locations": ["Ward-1-Drop-Zone"]
    }
  }
}
```

Drop-off zones are ordinary placed locations. Configure their existing
`inventory_spaces` as **Flexible payload spaces** to let different payload types
use any space whose maximum length, width and height they fit. Payloads may rotate
90 degrees in plan. The simulator assigns the smallest available compatible space
first, preserving larger spaces for larger payloads. New and existing department
drop-off-zone spaces default to flexible; other inventory spaces can opt in from
the Inventory Spaces editor. Multiple spaces provide the zone's simultaneous
holding capacity.

In the Department editor, use **New drop-off zone → Create and assign** to name
and place a zone, then assign that one location to any number of selected task
categories in the same operation.

For a generated delivery using a zone:

- `Task.dropoff` and `Task.dropoff_zone` are the AMR staging location.
- `Task.final_destination` is the associated department location.
- staff and a return task are enabled automatically;
- `return_payload` selects the empty/equivalent type, falling back to the outbound
  payload type when it is blank;
- `staff_collection_delay_minutes` adds a configurable response delay between AMR
  drop-off and staff collection;
- staff handling occurs within the configured `return_delay_minutes` window at
  the final destination. The longer of `staff_handling_minutes` and
  `return_delay_minutes` determines the destination dwell, matching the original
  direct-delivery return timing; calculated walking time from the zone and back
  remains additional;
- `dropoff_zone_capacity_policy` can either wait for a compatible free space or
  allow temporary overflow. This setting is category-wide: all departments in
  the category use the same policy, and legacy department override values are
  ignored. Overflow applies only when the payload fits a configured zone space,
  keeps generated tasks from failing during a temporary occupancy peak, and
  remains visible in zone utilisation/shortfall reporting.

Global staff settings provide the walking speed, lift allowance and default
payload-handling time used by every drop-off-zone handoff. A category/department
handling value of `0` uses that global default. The global short-exchange threshold
can hold the delivering AMR at the zone until the returned payload is ready,
preventing it from accepting intervening work during a quick exchange.

Set `staff_department_fallback_enabled` on a category or department override to
let an untracked department team complete the zone-to-department-to-zone handoff
when the primary staff team cannot finish it within its current working period.
`staff_department_fallback_resource_name` controls the label used in event logs.
Fallback assignments are auditable but do not enter the primary staff pool,
consume central staffing capacity, retain movement history, or delay another
department fallback. Once the return payload reaches the zone, its AMR return
task is released and collection is autonomous.

`staff_handoff_only` removes destination dwell for movement-only workflows such
as Linen: the person delivers the incoming trolley, takes the previous return
trolley immediately, and places it in the zone for autonomous AMR collection.
Where a department category has several destination locations, the simulator
orders them by staff graph-route distance from the zone and selects the nearest
available location; an occupied or reserved location causes it to try the next
candidate.

Tracked exchange deliveries leave the newly delivered full payload at the final
destination and bring the previous empty/equivalent payload back to the zone as a
different physical instance. This supports Linen-style full-for-empty swaps while
keeping destination and zone populations stable across repeated visits.
When the same tracked payload is assigned to several department destination
locations, `consumption_per_day` remains the department's total demand. The
simulator divides that demand evenly between the physical resources, tracks each
container's balance independently, and targets replenishment at the resource that
reaches its threshold.

The simulation visualiser shows this handoff when **Show drop-off-zone staff
handoffs** is enabled: the assigned person carries the delivered payload to the
final destination, handles it there, and returns the configured empty/equivalent
payload to the zone. Exchange tasks additionally show the person manoeuvring the
full/empty payload swap, while a held AMR remains visible at the zone. Right-click
a location and select **Payloads → Find maximum
space utilisation** to inspect its peak occupied-space count, peak timestamp, and
the utilisation history of every configured space. The PDF report includes a **Drop-off zone peak occupancy**
section with each zone's maximum occupied spaces and the true simultaneous
maximum across all configured zones.

Static tasks can opt into the same workflow by supplying both `dropoff_zone` and
`final_destination`; the simulator routes their AMR leg to `dropoff_zone`.
