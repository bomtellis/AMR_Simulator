"""Isolated CPU experiment: strengthen Simple lift pruning with an exact lower bound.

Production modules are not edited. The experimental method and its digest are
recorded separately from the engine's application-source fingerprint.
"""
import argparse
import hashlib
import inspect
import json
from pathlib import Path
import sys
import textwrap

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(1, str(ROOT / 'verification'))


def main(output):
    import simulator
    from benchmark_computation import sample

    original = textwrap.dedent(inspect.getsource(
        simulator.Simulation._nearest_compatible_lift_plan))
    marker = '''        if not self.geometric_motion and lift_finish >= best_finish:
            continue
'''
    replacement = marker + '''        if (not self.geometric_motion and not self.scenario_mode
                and self.edge_slowdown_per_amr >= 0.0
                and self.min_congestion_speed_factor <= 1.0
                and math.isfinite(best_finish)):
            bound_route = self._shortest_path_same_floor(
                destination_lift.floor, destination_lift.name, to_loc.name,
                rules=rules,
                minimum_width_m=self._required_corridor_width(amr, payload, orientation),
            )
            self._experiment_bound_counts['tested'] += 1
            if bound_route is None:
                self._experiment_bound_counts['no_route'] += 1
                continue
            speed = max(float(amr.speed_m_per_sec), 1e-9)
            bound_key = (id(bound_route), speed)
            cached_bound = self._experiment_bound_cache.get(bound_key)
            if cached_bound is None:
                # Use the corridor loop's own edge order and arithmetic, rather
                # than dividing the shortest-path aggregate distance. Retaining
                # the route object prevents reuse of its identity in this run.
                duration_bound = 0.0
                for bound_edge in bound_route['edges']:
                    duration_bound += float(bound_edge['distance_m']) / speed
                self._experiment_bound_cache[bound_key] = (bound_route, duration_bound)
            else:
                duration_bound = cached_bound[1]
            if lift_finish + duration_bound >= best_finish:
                self._experiment_bound_counts['additional_pruned'] += 1
                continue
'''
    if original.count(marker) != 1:
        raise RuntimeError('Production pruning method no longer matches the experiment')
    modified = original.replace(marker, replacement)
    namespace = {}
    exec(compile(modified, str(Path(__file__).resolve()) + ':experiment', 'exec'),
         vars(simulator), namespace)
    cls = simulator.Simulation
    cls._nearest_compatible_lift_plan = namespace['_nearest_compatible_lift_plan']
    original_init = cls.__init__
    instances = []

    def init(self, *args, **kwargs):
        self._experiment_bound_counts = dict(tested=0, additional_pruned=0, no_route=0)
        self._experiment_bound_cache = {}
        instances.append(self)
        original_init(self, *args, **kwargs)

    cls.__init__ = init
    sample('cpu', output)
    result = json.loads(output.read_text(encoding='utf-8'))
    result['experimental_override'] = {
        'description': 'Simple non-scenario outgoing-route free-flow lower bound; production unchanged',
        'original_method_sha256': hashlib.sha256(original.encode()).hexdigest(),
        'experimental_method_sha256': hashlib.sha256(modified.encode()).hexdigest(),
        'harness_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'source_binding_note': 'software_sha256 binds the base engine, not this separately recorded override',
        'counts': instances[0]._experiment_bound_counts,
        'cached_bounds': len(instances[0]._experiment_bound_cache),
    }
    reference = json.loads((ROOT / 'verification' / 'ltn-cpu-after-optimisation-final-20261012.json').read_text())
    result['matches_verified_improved_outcomes'] = result['outcome'] == reference['outcome']
    result['matches_verified_inputs'] = result['source_config_sha256'] == reference['source_config_sha256']
    output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in result.items() if key != 'outcome'}, indent=2))
    if not result['matches_verified_improved_outcomes'] or not result['matches_verified_inputs']:
        raise RuntimeError('Experiment failed full-week outcome/input parity')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    main(parser.parse_args().output)
