# Lift & Route Analysis

## Purpose and entry points

Open **Lift & Route Analysis** in the main project tree, or choose **Analyse lifts and routes** for a selected saved run on the Simulate page. It is independent of Report. Select Run A, optionally Run B, then open Overview, AMR routes, Route inspector, Lifts or Forced-floor checks. Loading does not run the simulator, generate reports or expand compact logs into CSV.

## User workflow

The editable run selectors accept saved run folders, event CSV files and SQLite event stores. Project-linked runs appear in the selectors. Each successful load preserves its own frozen inputs and saved geometry. Failed loads retain the previous valid views. Filters / time window exposes elapsed seconds, floors, lifts, robots, movement purpose, route profile, endpoints, evidence and compliance filters. Apply filters explicitly. Reset restores the common time window. Selecting a heatmap cell or timeline bar applies the related shared filter; Clear chart selection removes it.

Expand a route group to see its recorded path variants. Select a journey independently for each run; double-click or press Enter to open Route inspector. The two floor plans use their respective saved layouts. Fit route focuses on recorded movement, while Fit shows the whole floor. The floor/lift diagram shows actual transfer endpoints, not every floor a lift passes. Show source events exposes source identifiers, times and lift-selection details. All tables are keyboard-readable and paged at 250 records.

## Floor route drawings

From **Overview**, select **Export floor route drawings…**, choose a saved run, then select PDF, DXF or both. The export uses the applied time window and route filters. A selected floor limits the set to that floor. A leg that starts within the window contributes its full recorded route.

Each floor sheet counts a movement leg once when it uses that floor, including lift boarding and exit. Lift pass-through and lift-car repositioning are excluded. The legend shows trips by recorded payload type, including Empty AMR and Mixed payload. Confirmed simulation outcomes are selected by default. **Include recorded plans** adds separate planned counts and dashed lines on routes supported only by plans.

The PDF has one landscape A1 sheet per floor. The exporter chooses a common round print scale that fits the selected floors. Print at 100% on A1 and use the metre scale bar to check the printed size. The DXFs have editable layers by payload type and preserve the units of the saved CAD drawings. Keep any linked underlay PDFs beside their DXFs. Small offsets make shared corridors legible and are diagrammatic. Open circles mark transfer points, and red crosses identify known ends of geometry gaps. Exports use a new folder outside the saved run.

## Application boundary and design

This is an additive native PySide6 workspace in the existing project browser and central stack. It uses the application's palette, fonts, frozen run verification, sparse event reader, DXF scene renderer, PDF underlay placement and recorded trajectory decoder. The simulator, routing calculations, report commands, project editing and saved formats are unchanged. The established selected-run Review-to-Report shortcut remains available.

## Architecture

`amr_route_analysis` owns reading, reconstruction, policy checks, filtering, aggregation and CSV export. `route_analysis_panel` owns selection and cancellable jobs. `route_analysis_views` owns read-only graphics. Segment, Leg, RunAnalysis and Filters are internal Python interfaces, not new persisted simulation formats. Views never calculate replacement routes.

## Lifecycle and consistency

Background jobs carry a slot and monotonically increasing token. Replacing a source or comparison cancels the obsolete job; its completion cannot overwrite newer state. Cancellation is cooperative at hashing, event-reading and reconstruction boundaries. Drawing parsing completes the current file before checking cancellation. A bounded in-memory cache reuses drawings by their content hash across runs. No cache files are written into source runs.

## Evidence and leg definitions

A leg is a reconstructed location-to-location AMR movement between pickup, drop-off, charging or stowing boundaries within a recorded journey. Empty approaches, deliveries, returns, charging travel and parking/idle returns are included. Local bay motions do not create extra policy journeys. Shared task IDs do not multiply movements. Empty lift repositioning remains a separate physical lift movement and is never a visit by the AMR.

CSV segment status `completed` is not independent proof of execution: the simulator writes planned segments with this status. The workspace labels those plans separately from a confirmed simulation outcome established by a matching task completion or charging arrival. It does not certify physical-world execution. Missing identity, endpoints, continuity, exit evidence or saved policy results in insufficient evidence where that information is needed.

Forced-floor checks run independently for each leg. Starting on the required floor satisfies the rule. An intermediate visit requires a recorded transfer exit; older fixed-mode transfer records use their frozen boarding allowance. Empty car repositioning and merely passing through the required floor do not satisfy it. Saved `required_floor_visited` annotations are cross-checked against the sequence; contradictions remain insufficient evidence. An absent visit is a violation only with complete evidence. Disabled policy is shown explicitly while general route analysis remains available.

## Comparison arithmetic

Both runs use a common elapsed-time window, bounded by the shorter configured horizon or verified stop. Movements are counted by start time. Lift busy duration is clipped to the window, including movements overlapping its start. Route distance and lift waiting describe recorded plans. Journey-time averages use only legs with confirmed simulation outcomes whose whole interval lies within the window; excluded counts are visible. A zero baseline has no percentage difference. Unverified absence is unknown, not zero.

Routes group by origin, destination, purpose and profile, then by recorded edge/lift sequence. IDs are matched literally across runs. Different task IDs or robot assignments are not automatically paired. The Overview lists changed settings, unmatched locations/lifts and changed definitions. Workload release/generation/completion counts remain run-wide within the selected time window, rather than changing their denominator when a robot is filtered. Differences are observations, not proof that forced routing caused a result.

## Read-only and export contracts

Run and sidecar hashes are verified before and after loading. Managed runs use the existing project evidence boundary and verify bound drawing hashes. Standalone external drawings are labelled contextual rather than historical proof. Missing drawings retain saved graph geometry; missing route geometry is shown as a gap without shortest-path substitution. Partial-run future plans never acquire confirmation from a segment status.

Export comparison writes a new folder outside source runs containing comparison.csv, route-comparison.csv, route-variants.csv, journeys.csv, journey-evidence.csv, lift-movements.csv and provenance.json. The export covers every filtered row, not just the visible page. Route comparison distances are metres and durations/waits are seconds. Provenance includes filters, source hashes, coverage notes and frozen configurations. It is staged and renamed only on successful completion; existing output folders are preserved.

## Validation

Automated coverage includes normal and forced-floor routes, same-floor detours, multi-stop leg boundaries, lift exits versus pass-throughs, annotation conflicts, empty repositioning, missing/duplicate evidence, stopped runs, common-window arithmetic, zero baselines, cancellation, file changes, CSV export, independent selection, pagination and main navigation. Real CSV and compact project runs exercise the existing simulator and evidence verifier. Existing routing, report, project workflow, lift evidence and partial-playback checks form the compatibility baseline.

Representative seven-day LTN runs are read without modification. Their full recorded movement totals are 10,999 for the baseline and 18,863 for the forced-floor run. The forced-floor run reconstructs 7,384 applicable legs, all satisfying its required floor. Filtered default-window totals can be lower because activity after the configured horizon is excluded. Visual evidence and measured load/comparison timings are in the task's `outputs/route-analysis` folder.

## Alternatives and limitations

The main route table plus selected floor plan avoids an unreadable overlay of every route. Heatmaps communicate movement volumes; per-lift timelines communicate timing. Timeline bars that occupy the same display position are grouped, with exact individual movement records retained in the table. Large drawings are parsed in the background and can dominate initial load time. The view is usable by keyboard through tables and controls; full assistive-technology certification is not claimed.

## Delivery and rollback

The change installs only the new analysis service, two views, navigation hooks, tests and this guide. Installation checks the original source hashes and retains exact backup copies before replacing files. Rollback restores those copies and removes newly added files listed in the installation manifest. Source runs, project archives and synced references remain unchanged.
