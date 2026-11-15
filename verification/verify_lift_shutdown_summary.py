"""Verify all saved lift-shutdown trials without rerunning simulations."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from amr_stress_report import collect_stress_report

if __name__ == '__main__':
    path = ROOT / 'Lift stress.stress.json'
    state = json.loads(path.read_text(encoding='utf-8'))
    selected = [dict(study_path=str(path), study_root=state['root'],
                     trial_ids=[k for k in state['results'] if k != 'baseline'])]
    snapshot, evidence = collect_stress_report(selected, state['config'])
    output = ROOT / 'verification' / 'lift-shutdown-verified.json'
    output.write_text(json.dumps(dict(snapshot=snapshot, evidence=evidence), indent=2), encoding='utf-8')
    print(f'Verified all {len(selected[0]["trial_ids"])} trials: {output}', flush=True)
