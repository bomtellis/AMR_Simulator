import json
import time
from pathlib import Path

root = Path(__file__).resolve().parents[1]
while True:
    state = json.loads((root / 'verification/ltn-amr-speed-sweep-progress.json').read_text())
    print(json.dumps(state), flush=True)
    if state.get('phase') == 'Sweep and verified PDF complete':
        break
    time.sleep(30)
