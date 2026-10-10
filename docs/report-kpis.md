# Operational report KPIs

The **Operational KPIs (demand, service, capacity and cost)** report section is
selected by default in both report dialogs. Its CLI section ID is
`operational_kpis`. It contains the eight requested groups, numbered 1.1-1.8.

```powershell
.\.venv\Scripts\python.exe report\amr_report_main.py simulation_steps.csv --config-json config.json --report-sections front_summary,operational_kpis --omit-drawings -o report.pdf
```

Every generated report also writes eight CSVs beside the PDF:
`report_kpi_summary.csv`, `report_kpi_hourly.csv`, `report_kpi_streams.csv`,
`report_kpi_requests.csv`, `report_kpi_overdue.csv`, `report_kpi_queues.csv`,
`report_kpi_routes.csv` and `report_kpi_chargers.csv`. The PDF shows at most 100
overdue, queue and route rows per table; the CSVs retain every record, including
every overdue task and its recorded reason. An absent reason is explicitly
labelled **Reason not recorded**.

## Definitions and evidence

- Demand includes delivery, collection and payload-return requests. Empty AMR
  returns, charging records and grouped multi-stop pseudo-tasks are excluded.
  Peak concurrent demand is the maximum outstanding request count, including
  requests waiting for assignment and those still open at the observation end.
- Request-to-delivery time ends at the task completion event. Recorded release
  time is used when available, including releases recorded before assignment.
  Assignment time is an explicit fallback when the request time is absent.
  Percentiles use pandas' linear interpolation. The stream table includes
  catering, linen, waste, pharmacy, receipt and distribution (the `stores`
  category), and an unclassified row where necessary.
- SLA compliance divides completed on-time tasks by completed, failed or overdue tasks
  with a positive recorded target. Unfinished tasks still within their deadline
  are not assessed yet. Overdue counts include late completions, failed overdue
  tasks and unfinished requests past their deadline. Overdue percentages use
  all requests with a positive recorded deadline as the denominator.
- Fleet utilisation uses assignment-to-completion/failure/end intervals, merged
  per physical AMR. It includes handling and active-task waiting. Charging is
  excluded from task utilisation and included in headroom and sizing estimates.
  The denominator is configured fleet quantity times the observed run duration;
  without configuration it uses the observed fleet and states that limitation.
  Peak utilisation is instantaneous. Hourly fleet use is also supplied.
- Productive utilisation counts loaded movement and pickup/dropoff time against
  the same fleet-time denominator. Empty running uses physical movement distance
  and onboard payload state; carrying an empty container is still carrying a
  payload. Shared segments and duplicate event IDs count once. Lift reposition
  distance is excluded because the AMR is waiting for the lift.
- Fleet distance per delivery includes all unique AMR movement, including empty
  and charging travel, divided by completed delivery/collection tasks. Service
  and route breakdowns allocate each shared segment equally among the completed
  task IDs named on it. Travel without a task ID remains in the fleet KPI.
- Queue totals include dispatch waits and explicit vehicle waits. Lift waiting
  includes the time a suitable lift repositions to collect an AMR. Congestion
  shows only explicitly attributed congestion and pedestrian delay; other door,
  corridor and traffic delay needs a free-flow baseline. Legacy `charge_wait`
  state changes have no queue-exit timestamp: their duration remains unavailable.
  New runs record elapsed finite-bay contention as `segment_wait_for_charger`
  intervals, including waits still open at the observation cut-off. Repeated
  retries do not restart the timer, and non-capacity charging faults are excluded.
  A summary coverage flag distinguishes zero recorded contention from old logs
  with no duration evidence.
- Vehicle sizing is a planning estimate: the greater of instantaneous occupied peak
  and task, charging and empty-repositioning workload at the report's target AMR utilisation, with
  an optional vehicle reserve. Charger sizing uses observed charging peak and
  workload plus one spare, with a location breakdown. Zero recorded charging
  does not establish a required charger count. Neither is an optimisation or a
  guarantee that a different fleet will meet deadlines; rerun that fleet to check.
- Energy per delivery uses the existing fully attributed AMR traction and lift
  supply ledger, divided by completed tasks. It is model energy, excluding
  stationary auxiliaries and charger losses. Incomplete or unattributed energy
  evidence remains unavailable.
- Staff hours use recorded staff busy time, plus supplied additional staff hours.
  Handling alone is labelled **Handling only**. Costs and equipment reliability
  require period inputs: task failures are not automatically equipment faults.
  Missing evidence is never substituted with zero.

Partial-run segments are clipped to the last scenario/battery summary snapshot.
Otherwise the observed event range is used. Future task releases are excluded.
Distance on a partially observed segment is prorated by elapsed time and labelled
as an estimate; it does not reconstruct acceleration or the exact trajectory.

## Optional period inputs

Add `report_kpis` to the matching configuration **before saving/running a project**.
Project reports continue to use their frozen run configuration. Values below
are illustrative; replace them with evidence for exactly the reported period.
They do not alter routing or simulation behaviour.

```json
{
  "report_kpis": {
    "task_streams": {"MANUAL-1": "pharmacy"},
    "payload_streams": {"Medicine trolley": "pharmacy"},
    "additional_staff_hours": 4.0,
    "vehicle_reserve_percent": 15,
    "costs": {
      "currency": "GBP",
      "labour_cost": 1200,
      "energy_cost": 40,
      "maintenance_cost": 100,
      "software_cost": 50,
      "support_cost": 60
    },
    "reliability": {
      "planned_vehicle_hours": 240,
      "unavailable_vehicle_hours": 12,
      "planned_fms_hours": 24,
      "unavailable_fms_hours": 0.25,
      "operating_hours": 228,
      "failure_count": 3,
      "repair_durations_hours": [0.5, 1.0, 2.0]
    }
  }
}
```

`task_streams` and `payload_streams` explicitly classify otherwise ambiguous
requests. Automatic classification uses category/source evidence, generated
task IDs and unambiguous department location mappings.

`additional_staff_hours` covers loading, unloading, monitoring, support,
exceptions and faults that are not already included in the recorded staff
busy hours. An explicit zero confirms that no extra time is required.
Alternatively, `total_staff_hours` supplies the complete staff requirement for
the period when recorded handling hours are unavailable. `staff_hourly_rate`
can replace `labour_cost` when complete staff hours are available through either
method. `total_operating_cost`
can replace the five individual cost components. All costs must cover the
observation period; annual costs must be apportioned before entry.

Availability uses supplied planned vehicle-hours minus unavailable vehicle-hours,
divided by planned vehicle-hours. Unavailable vehicle-hours must include the
vehicle-hours lost during fleet-management-system outages, with overlapping
vehicle and system downtime counted once. Separate system readiness is displayed
when its planned and unavailable hours are also supplied.
MTBF uses operating hours / service-affecting fault count. Zero faults has no
finite MTBF. MTTR averages completed fault-to-restoration durations; open faults
need separate review. Supplied inputs are labelled in the report.
