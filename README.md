# Autonomous Mobile Robot Simulator

***Project licensed under MIT License.***

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