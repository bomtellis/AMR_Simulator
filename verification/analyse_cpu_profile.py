"""Summarise a CPU cProfile capture without changing simulation code or inputs."""
import argparse
import io
import json
from pathlib import Path
import pstats


def location(key):
    filename, line, name = key
    return dict(file=filename, line=line, function=name)


def analyse(path):
    stats = pstats.Stats(str(path))
    functions = []
    for key, (primitive, calls, own, cumulative, callers) in stats.stats.items():
        incoming = []
        for caller, values in callers.items():
            row = location(caller)
            if isinstance(values, tuple):
                row.update(primitive_calls=values[0], calls=values[1],
                           self_sec=values[2], cumulative_sec=values[3])
            else:
                row['calls'] = values
            incoming.append(row)
        functions.append(dict(**location(key), primitive_calls=primitive, calls=calls,
            self_sec=own, cumulative_sec=cumulative,
            self_percent=100 * own / stats.total_tt,
            cumulative_percent=100 * cumulative / stats.total_tt,
            callers=sorted(incoming, key=lambda row: row.get('cumulative_sec', 0), reverse=True)))
    result = dict(profile=str(path.resolve()), total_profile_sec=stats.total_tt,
                  total_calls=stats.total_calls, primitive_calls=stats.prim_calls,
                  note='Cumulative times include callees and overlap; do not add them. '
                       'Profiler overhead means these seconds are not normal runtime.',
                  functions=sorted(functions, key=lambda row: row['cumulative_sec'], reverse=True))
    path.with_suffix('.summary.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    stream = io.StringIO()
    printable = pstats.Stats(str(path), stream=stream)
    printable.sort_stats('cumulative').print_stats(100)
    printable.sort_stats('tottime').print_stats(100)
    selected = ['_nearest_compatible_lift_plan', '_find_lift_journey_slot',
                '_same_floor_segments', '_select_best_assignment',
                '_estimate_task_for_amr_impl', '_rules_cache_key',
                '_released_task_terminal_failure_reason', 'log_step']
    for name in selected:
        printable.sort_stats('cumulative').print_callers(name).print_callees(name)
    path.with_suffix('.stats.txt').write_text(stream.getvalue(), encoding='utf-8')
    print(json.dumps({key: value for key, value in result.items() if key != 'functions'}, indent=2))
    for row in sorted(functions, key=lambda row: row['self_sec'], reverse=True)[:20]:
        print(f"{row['self_sec']:9.3f}s self {row['cumulative_sec']:9.3f}s inclusive "
              f"{row['calls']:12,d} calls {Path(row['file']).name}:{row['line']} {row['function']}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('profile', type=Path)
    analyse(parser.parse_args().profile)
