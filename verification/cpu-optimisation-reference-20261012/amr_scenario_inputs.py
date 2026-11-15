"""Validate dated scenario windows without silently changing user inputs."""
from datetime import datetime
import math


def scenario_input_findings(config):
    findings = []
    section = config.get('scenario_testing', {})
    if not isinstance(section, dict):
        return [('/scenario_testing', 'Scenario settings must be an object.')]
    for i, scenario in enumerate(section.get('scenarios', []) or []):
        if not isinstance(scenario, dict):
            continue
        for j, event in enumerate(scenario.get('events', []) or []):
            if not isinstance(event, dict):
                continue
            path = f'/scenario_testing/scenarios/{i}/events/{j}'
            if event.get('start_datetime') or event.get('end_datetime'):
                try:
                    start = datetime.fromisoformat(event['start_datetime'])
                    end = datetime.fromisoformat(event['end_datetime'])
                    origin = datetime.fromisoformat(config.get('simulation', {}).get('start_datetime', '2026-01-01T08:00:00'))
                    (start - origin).total_seconds()
                    if end <= start:
                        raise ValueError()
                except (KeyError, TypeError, ValueError):
                    findings.append((path, 'Dated events need valid start/end datetimes, end after start, and timezone offsets compatible with the simulation.'))
            for key, default, upper in [('availability_percent', 100, 100), ('speed_factor', 1, 1)]:
                value = event.get(key, default)
                if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= upper:
                    findings.append((path + '/' + key, f'{key} must be finite and between 0 and {upper}.'))
    return findings
