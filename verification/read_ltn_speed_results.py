import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
state = json.loads((root / 'LTN AMR speed sweep 2026-10-14.stress.json').read_text())
print(json.dumps(dict(status=state['status'], root=state['root'], summary=state.get('speed_sweep'))))
for record in state['results'].values():
    m = record['metrics']
    print(json.dumps(dict(name=record['name'], passed=m['passed'], unmet=m['unmet_count'],
        failed=m['failed'], pending=m['pending'], completed=m['completed'], late=m['late'],
        obligations=len(m['obligations']), added_delay_hours=m['added_delay_sec']/3600,
        latest_finish_hours=m['latest_completion_sec']/3600)))
