"""Capture exact operational hashes for small scenarios on one selected source tree."""
import argparse
import contextlib
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent


def serialisable(value):
    from dataclasses import fields, is_dataclass
    if isinstance(value, float) and not math.isfinite(value):
        return {'special_float': value.hex()}
    if is_dataclass(value):
        return {field.name: serialisable(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, dict):
        return {str(key): serialisable(item) for key, item in value.items()}
    if isinstance(value, set):
        return sorted((serialisable(item) for item in value), key=repr)
    if isinstance(value, (list, tuple)):
        return [serialisable(item) for item in value]
    return value


def capture(source, output):
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(source))
    # Load the chosen engine before helpers can prepend their own workspace.
    from simulator import Simulation
    from amr_run_evidence import software_snapshot, config_hash
    from tests.test_compact_execution import normalise
    from tests.test_route_reservation_atomicity import resource_state
    from verification.benchmark_compact import outcome
    rows = []
    for path in sorted((ROOT / 'verification/scenarios').glob('*.json')):
        config = json.loads(path.read_text(encoding='utf-8-sig'))
        sim = None
        try:
            with contextlib.redirect_stdout(Quiet()):
                sim = Simulation(config, verbose=True)
                sim.run()
            digest = hashlib.sha256()
            count = 0
            for row in sim.verbose_rows:
                digest.update(json.dumps(normalise(row, sim.run_id), sort_keys=True,
                    separators=(',', ':'), allow_nan=False).encode())
                digest.update(b'\n')
                count += 1
            state = dict(resources=resource_state(sim), robots=[vars(robot) for robot in sim.amrs],
                         payload_inventory=vars(sim.payload_instance_store))
            state_hash = hashlib.sha256(json.dumps(normalise(serialisable(state), sim.run_id),
                sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
            rows.append(dict(scenario=path.name, config_sha256=config_hash(config),
                outcome=outcome(sim), events=count, event_sha256=digest.hexdigest(),
                final_state_sha256=state_hash))
        except (ValueError, RuntimeError) as error:
            rows.append(dict(scenario=path.name, rejected=type(error).__name__, reason=str(error)))
        finally:
            if sim is not None and sim.event_store is not None:
                sim.event_store.close()
    output.write_text(json.dumps(dict(source=str(source), software=software_snapshot(),
                                     scenarios=rows), indent=2), encoding='utf-8')
    print(f'Captured {len(rows)} scenarios; {sum("rejected" in row for row in rows)} rejected inputs.', flush=True)


class Quiet:
    def write(self, value):
        return len(value)
    def flush(self):
        pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    capture(args.source.resolve(), args.output)
