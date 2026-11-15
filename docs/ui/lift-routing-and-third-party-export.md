# Lift routing, graph transfer speeds and third-party CSV

## Configure routing

Open **Configuration → Building settings**.

- Set **Transfer floor when a connection is needed** to **Level 2**.
- Tick the boarding floors that should use **Destination-side lift selection**. Tick Level 2 to apply it after a transfer there; tick other floors to apply it before their direct journeys too.
- Save, then save the project and run Project checks.

A suitable direct lift goes straight to the destination floor, even when busy. The AMR waits for that lift. If no suitable direct lift exists, the connecting route must actually stop on the transfer floor. Starting on that floor already satisfies the transfer requirement. Same-floor journeys stay on their floor.

On selected boarding floors, lifts are ranked by the shortest permitted corridor distance from their destination-floor stop to the actual AMR endpoint. The AMR crosses to the chosen lift. Suitability includes the AMR/load envelope, floor coverage, permitted routes and operational checks. Equal-distance choices use earliest completion, then lift ID.

These rules apply to loaded and empty AMR movement, charging and parking. An arrival lift may be reused if it is the selected suitable lift. No minimum horizontal crossing is imposed.

**Mandatory floor waypoints remain separate, strict rules.** Remove any unwanted via-Level-2 mandatory rules if direct lifts should bypass Level 2. Project checks warn when mandatory rules coexist with the conditional transfer setting.

The stored building settings are `lift_transfer_floor` and `destination_side_lift_floors`. Leaving them unset/empty retains the existing routing. Configuration edits use the existing Save, Cancel, Undo/Redo and project revision behavior.

## Configure entry and exit speeds

1. In **Configuration → AMRs**, edit each active AMR type and enter **Lift entry speed** and **Lift exit speed**, in m/s.
2. Edit the relevant lift and select **Transfer timing → AMR speeds and graph edges**.
3. Check that every lift stop has usable incoming and outgoing edges connecting it to the corridor. Save, check and rerun the project.

Entry uses the incoming connector edge at the boarding floor. Exit uses the outgoing connector edge at the destination floor. Each duration is its graph edge distance divided by the corresponding AMR speed; existing traffic and scenario restrictions still apply. Directional edges may have different distances. There are no manual distance fields and car dimensions are not used as travel distances.

Connector travel is included once within the lift service interval, replacing its ordinary corridor traversal. The surrounding corridor travel excludes those connector edges. Lift bookings cover transfer, doors and vertical travel; connector traffic reservations remain active. Entry/exit traction is attributed to the AMR battery separately from lift supply energy. The existing legacy graph lift model represents this as one combined transfer event, with the connector edges and applied times recorded in its details.

Fixed transfer timing remains the default for existing projects. Speed settings alone do not change a fixed-time lift. The AMR JSON fields are `lift_entry_speed_m_per_sec` and `lift_exit_speed_m_per_sec`; the lift field `transfer_timing_mode` accepts `fixed` or `speed_based`.

## Export to third-party software

Select a completed saved run, open its Report view and choose **Export third-party lift CSV…**. Choose one lift or **All lifts — separate CSV files**, and optionally tick **Include empty reposition trips**. Reposition inclusion changes only this output, not simulation behavior. The export runs in the background and uses the run’s saved configuration and recorded events, even if the current editor has changed.

For **All lifts**, choose a destination folder. A new `third-party-lifts-…` subfolder contains one CSV for every configured lift, including a header-only file for an unused lift. Filenames include a numbered prefix and a safe lift name. `export-manifest.json` maps each original lift ID to its CSV and movement count. The original eight-column import format is retained in every CSV. The complete folder is published only after all files and saved evidence have been checked; failures do not publish partial exports or replace previous exports. **Open lift export folder** opens the completed batch.

Columns are **Start Seconds**, **Origin Number**, **Destination Number**, **Load weight**, **% loading factor**, **Transfer times**, **Car not in service**, and **concatenated**.

- Start is the AMR’s entry start, in seconds from simulation start, rounded to the nearest whole second with halves upward.
- Origin and destination are the simulator floor numbers plus 1.
- Load weight is always `1500`, loading factor `60`, and car not in service `2`.
- Transfer times contain `entry,exit` seconds, rounded to three decimal places with trailing zeros removed.
- A concatenated value is, for example, `29026,1,3,1500,60,31,31,2`.
- Included empty reposition trips use their movement start and transfer times `0,0`.

Comma-containing cells are quoted in the CSV. Each physical lift movement appears once. Existing CSV exports are unchanged. Export failure retains the previous completed output. Older fixed-time runs can use their saved boarding and door allowances; missing evidence requires a new fully logged run.

The workbench command line accepts:

```powershell
.\.venv\Scripts\python.exe amr_app.py "path\to\completed-run" --third-party-lift-csv "path\to\lift.csv" --lift-id "Lift-1"
```

Add `--include-lift-reposition` to include empty reposition movements. The same flags are available in the report command line. Inputs may be a completed run folder, a compact event store, or an event CSV with matching saved evidence. Exporting does not rerun the simulation or generate a PDF.

To export all lifts from the command line, supply a new output directory instead of a single filename and lift ID:

```powershell
.\.venv\Scripts\python.exe amr_app.py "path\to\completed-run" --third-party-lifts-dir "path\to\new-lift-export"
```

The all-lifts flag cannot be combined with `--lift-id` or `--third-party-lift-csv`. It also supports `--include-lift-reposition`.

## Verification and practical limits

Focused tests cover direct-lift bypass, real transfer stops, nearest eligible selection, busy lifts, permissions, graph connector distances, no duplicate connector timing, reservations, energy balance, CSV formatting and frozen-input export. UI tests cover Save/reopen, Undo/Redo and background export. Real dialog previews were inspected at standard desktop scale; broader assistive-technology and mixed-display checks were not performed.

A ten-delivery representative case completed all deliveries with zero failures. Destination-side selection increased one lift’s occupied share of a 600-second run from 13.5% to 20.5%, while increasing waiting. Disabled settings reproduced the installed application’s baseline metrics exactly. Results are scenario-dependent and are not a full LTN capacity validation.

Existing project files are not automatically reconfigured, historical runs are not rewritten, and existing packaged executables need rebuilding to distribute the new code. Restart the source application after installation. A checked installation manifest and file-by-file backup support rollback.
