# Lift stops and same-floor corridor routing

Lift stops are boarding and alighting endpoints, not corridor junctions. An AMR
may approach a stop on its boarding floor and depart from a stop after changing
floor. A same-floor route must never contain an intermediate lift stop.

The simulator excludes intermediate lift stops in both directions of its
bidirectional shortest-path search, including the point where the two searches
meet. This applies to cached and precomputed routes, empty travel, loaded travel,
multi-stop legs, charging travel, assignment estimates and structural feasibility.
Longer permitted corridor routes remain available. A route with no such corridor
connection is infeasible; lift permissions cannot override this restriction.

Task graph checks follow the simulator's approach / one floor-changing lift
journey / departure model. This prevents same-floor lift shortcuts and trips up
and back down to bypass disconnected corridors. Check and Review use these
checks for manual tasks, generated rules and return legs. Their blocked-route
explanation identifies the lift rule when no unrestricted connection exists.

`tests/test_lift_corridor_routing.py` covers directed and bidirectional shortcuts,
search-front meetings, cached failures, longer bypasses, boarding/alighting
endpoints, actual deliveries under both assignment-estimate and precompute modes,
floor-changing deliveries and returns, multi-stop legs, profile restrictions,
manual/generated/return checks, an invalid approach through another lift,
up-and-down detours, and single-floor lifts.

Validation: 178 tests passed across this suite and routing contracts, task graph
navigation, route profiles, lift structure/contracts, multi-stop route rules,
charging replanning, geometric simulation, project checks and project workspace.
