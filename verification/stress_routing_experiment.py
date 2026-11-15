"""Measure the lift-only route fix in memory, without changing a running app."""
import argparse
import contextlib
from datetime import datetime, timedelta
import inspect
import json
from pathlib import Path
import sys
import tempfile
import textwrap
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def install(*, before=False):
    import simulator
    original = textwrap.dedent(inspect.getsource(simulator.Simulation._same_floor_segments))
    guard = ("    # Lift events are applied by lift planning; they do not change floor routes.\n"
             "    scenario_routing = self.scenario_mode and any(\n"
             "        event.get('resource_type') in ('corridor', 'corridor_node', 'amr')\n"
             "        for event in self.scenario_events)\n")
    if 'scenario_routing = ' in original:
        if not before:
            return original, original
        source = original.replace(guard, '').replace('if scenario_routing', 'if self.scenario_mode')
    else:
        if before:
            return original, original
        marker = '    required_width = self._required_corridor_width(amr,payload,orientation)'
        source = original.replace(marker, guard + marker)
        source = source.replace('if self.scenario_mode and not self.geometric_motion:',
                                'if scenario_routing and not self.geometric_motion:')
        source = source.replace('if self.scenario_mode:', 'if scenario_routing:')
    namespace = {}
    exec(compile(source, str(Path(__file__)) + ':prototype', 'exec'), vars(simulator), namespace)
    simulator.Simulation._same_floor_segments = namespace['_same_floor_segments']
    return original, source


def sample(mode, output, hours=4):
    if mode in ('before', 'fixed'):
        install(before=mode == 'before')
    from simulator import Simulation
    from benchmark_compact import Quiet, outcome
    state = json.loads((ROOT / 'lift.stress.json').read_text())
    spec = state['pending_batch'][0]
    from amr_scenario_study import scenario_config
    cfg = scenario_config(state['config'], spec['events'], 'Performance sample')
    # Four hours of real LTN demand, before either chosen disruption begins.
    start = datetime.fromisoformat(cfg['simulation']['start_datetime'])
    cfg['simulation']['end_datetime'] = (start + timedelta(hours=hours)).isoformat()
    if mode == 'normal':
        cfg = scenario_config(cfg, [], 'Normal operation')
    with tempfile.TemporaryDirectory(dir=ROOT / 'tmp') as temporary:
        with contextlib.redirect_stdout(Quiet()):
            begin = time.perf_counter()
            sim = Simulation(cfg, verbose=True, verbose_csv_path=str(Path(temporary) / 'events.csv'),
                             runtime_backend='compact', defer_exports=True)
            initialized = time.perf_counter()
            sim.run()
            executed = time.perf_counter()
            sim.write_verbose_csv()
        # Metadata labels are expected to differ between normal and scenario runs.
        def operational(value):
            if isinstance(value, dict):
                return {k:operational(v) for k,v in value.items() if k not in
                        ('scenario_mode', 'scenario_name', 'scenario_reason')}
            if isinstance(value, (list, tuple)):
                return [operational(v) for v in value]
            return value
        sim.completed_task_records = operational(sim.completed_task_records)
        result = dict(mode=mode, initialisation_sec=initialized-begin,
                      execution_sec=executed-initialized, outcome=outcome(sim))
    output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=('normal', 'before', 'fixed'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--hours', type=float, default=4)
    args = parser.parse_args()
    sample(args.mode, args.output, args.hours)
