import cProfile
import contextlib
import json
import pstats
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from simulator import Simulation
from amr_stress_execution import QuietOutput
from amr_scenario_study import scenario_config

state = json.loads((ROOT / 'LTN AMR speed sweep 2026-10-14.stress.json').read_text())
config = scenario_config(state['config'], state['pending_batch'][0]['events'], 'Profile only')
started = time.monotonic()


def progress(message):
    if time.monotonic() - started > 60:
        sim.stop_requested = True


with contextlib.redirect_stdout(QuietOutput()):
    sim = Simulation(config, verbose=False, progress_callback=progress, runtime_backend='compact', defer_exports=True)
    sim.progress_update_interval = 1
    profiler = cProfile.Profile()
    profiler.enable()
    sim.run()
    profiler.disable()
profiler.dump_stats(str(ROOT / 'verification/ltn-speed-profile.pstats'))
print('SIM TIME', sim.current_time, 'WALL', time.monotonic() - started)
pstats.Stats(profiler).sort_stats('cumulative').print_stats(35)
