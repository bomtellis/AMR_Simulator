import contextlib
import json
import random
import sys
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from simulator import Simulation
from amr_scenario_study import scenario_config
from amr_stress_execution import QuietOutput
import amr_scenario_routing

state = json.loads((ROOT / 'LTN AMR speed sweep 2026-10-14.stress.json').read_text())
config = scenario_config(state['config'], state['pending_batch'][0]['events'], 'Route equivalence')
with contextlib.redirect_stdout(QuietOutput()):
    sim = Simulation(config, verbose=False, runtime_backend='compact', defer_exports=True)
rng = random.Random(1984)
pairs = [(a, b) for a in sim.locations.values() for b in sim.locations.values()
         if a.floor == b.floor and a.name != b.name]
pairs = rng.sample(pairs, min(60, len(pairs)))
timings = dict(optimized=0.0, original=0.0)
try:
    for index, (start, end) in enumerate(pairs):
        amr = sim.amrs[index % len(sim.amrs)]
        requested = (0, 15000, 86400, 864000)[index % 4]
        payload = next(iter(sim.payloads.values()))
        if index % 3 == 0:
            graph = sim.floor_graphs[start.floor]
            for edge in graph.get(start.name, ()):
                sim.edge_reservations[sim._physical_edge_key(start.name, edge['to'])].append(
                    (requested, requested + 120, 'equivalence-traffic'))
        def route():
            return sim._same_floor_segments(amr, start, end, payload=payload, start_time_value=requested)
        begin = time.monotonic()
        optimized = route()
        timings['optimized'] += time.monotonic() - begin
        with patch.object(amr_scenario_routing, 'constant_amr_state', return_value=None):
            begin = time.monotonic()
            original = route()
            timings['original'] += time.monotonic() - begin
        assert optimized == original, (start.name, end.name, requested, optimized, original)
    print(json.dumps(dict(exact_route_comparisons=len(pairs), seconds=timings), indent=2))
finally:
    if sim.routing_executor:
        sim.routing_executor.shutdown()
    if sim.event_store:
        sim.event_store.close()
