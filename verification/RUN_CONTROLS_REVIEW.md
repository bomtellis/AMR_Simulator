# Run controls and preserved editing — slice 2AO

Imported projects now retain the simulator's defaults rather than acquiring a
fixed editor end date, different assignment chunk size or different release
spacing. New projects still store their explicit chosen defaults. Missing end
means: duration_hours, then duration_days, then one day after the latest static
release (at least one day). Demand Preview uses that same inclusive horizon.
Released transport and returns may finish after it; it is not a hard stop.

Run controls validate before import, Project Checks and runtime construction.
Nonfinite/negative values, fractional counts, invalid dates, mixed aware/naive
timezones and unsupported boolean encodings reject rather than silently clamp.
Explicit legacy checkbox values (true/false strings and 0/1) are decoded
consistently. Candidate minima are one single task and two multi-stop tasks;
assignment limit zero means unlimited. Continuation delay is simulated time,
with a 0.001 second minimum; periodic housekeeping intervals have a one-second
minimum. Reservation retention still protects twice the congestion window.

The settings dialog saves only changed controls, preserving omitted options,
unknown metadata, timezone offsets and numeric precision on an unchanged save.
It now supports unlimited assignment chunks and zero opportunity-charge idle time.
The tick_rate field is labelled legacy metadata: the event loop does not consume
it to pace execution. Playback has separate controls.

Independent references cover the 2-hour/3-day/late-static-release fallbacks,
inclusive 30/60-minute demand (excluding 90 minutes), a 10 m movement at 2 m/s
with two 2-second handling periods finishing at second 10 after release at second
1, no change to that outcome across legacy rate values, and route precomputation
on/off and capped/uncapped comparisons. Malformed inputs and unchanged/edited
dialog saves are exercised at their actual entry points.

This does not verify every scheduling heuristic, charging policy or historical
inventory bypass alias. Zero-length duration or equal start/end retain start-instant
work; Demand Preview still requires a positive window. Radius, swept-footprint,
lane and junction work remains separate. The user has prioritised those features
and the CAD/tutorial deliverables over continuing the full option audit.

The final combined pack passed **1,397 tests in 146.275 seconds**, including the
geometry checkpoint added after reprioritisation. The run-control/boundary/checks
focused set passed 41 tests; the earlier settings/preview set passed 30. The first
full attempt exposed an existing zero-duration snapshot contract and multi-finding
check behaviour; both are preserved in the corrected final implementation.
Before-fix and first-pack logs remain under `verification/latest/run-controls-*`.
