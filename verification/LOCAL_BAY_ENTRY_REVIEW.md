# Local bay entry preflight — 4 October 2026

Project checks now warns when a location's graph entry falls inside the 0.15 m
expanded axis-aligned obstacle bounds of a drawn inventory bay and the location
has another bay to serve. The finding names the location and covering bay, points
to the bay input, and navigates to the location. Users can review or acknowledge
the warning under the existing check workflow; changing the project makes that
review stale. The check does not edit the project or infer a physical wall.

The current `ltn.json` produces navigable warnings for all seven drop-off zones
identified by the bounded six-hour run: D29, D32, D33, D35, D38, D39 and D41.
Two further locations, D4-STORES and D1-CATERING, also meet the same geometric
condition. This is a risk screen, not a prediction that every task at these
locations fails. The runtime excludes the selected target bay from obstacles;
another drawn bay can still cover the starting graph point. Undrawn synthetic bay
footprints are outside this first warning's scope.

Run `python -m unittest discover -s tests -p test_local_bay_entry_preflight.py -v`
with the project environment. The two tests verify the 0.15 m boundary, relative
coordinates, all seven LTN findings, finding navigation, stale inputs and
unchanged source. All 26 `test_project_checks.py` tests also pass, including a
new actual-editor navigation case from the warning to the affected graph point.
`LOCAL-BAY-ENTRY-01` links the workflow in the feature catalog; its nine catalog
integrity tests pass.
The LTN source and previous run outputs were not changed.
