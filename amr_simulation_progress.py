"""Shared simulation progress samples and the wall-clock ETA estimator."""
from collections import deque
import json
import math
from time import monotonic


PREFIX = 'AMR_PROGRESS '


def publish_progress(message):
    print(PREFIX + json.dumps(message, ensure_ascii=True, allow_nan=False), flush=True)


def sample(phase, label, current=None, total=None, **details):
    return dict(stage=phase, phase=label, current=current, total=total,
                clock=monotonic(), **details)


class ProgressEstimate:
    def __init__(self):
        self.stage = None
        self.label = ''
        self.samples = deque()
        self.received = None
        self.last_advance = None
        self.total = None

    def update(self, message, now):
        stage = message.get('stage')
        if stage != self.stage:
            self.samples.clear()
            self.last_advance = None
        self.stage = stage
        self.label = message.get('phase', '')
        self.received = now
        point, total, stamp = (message.get(key) for key in ('current', 'total', 'clock'))
        if not all(type(n) in (int, float) and math.isfinite(n) for n in (point, total, stamp)) or total <= 0:
            self.samples.clear()
            self.total = None
            return
        if self.samples and (stamp <= self.samples[-1][0] or point < self.samples[-1][1] or total != self.total):
            self.samples.clear()
            self.last_advance = None
        self.total = total
        if not self.samples or point > self.samples[-1][1]:
            self.last_advance = now
            self.samples.append((stamp, point))
        while len(self.samples) > 1 and stamp - self.samples[0][0] > 15:
            self.samples.popleft()

    def display(self, now):
        if self.total is None or not self.samples:
            return None, None, 'Time remaining unavailable for this phase'
        if now - self.last_advance >= 10 or now - self.received >= 10:
            return None, None, 'Waiting for simulation progress'
        first, current = self.samples[0], self.samples[-1]
        span = current[0] - first[0]
        if len(self.samples) < 3 or span < 2 or current[1] <= first[1]:
            return None, None, 'Estimating time remaining…'
        fraction = max(0.0, min(0.99, current[1] / self.total))
        remaining = max(1, math.ceil((self.total - current[1]) * span / (current[1] - first[1])))
        return round(fraction * 100), remaining, ''


def format_remaining(seconds):
    hours, tail = divmod(seconds, 3600)
    minutes, seconds = divmod(tail, 60)
    return f'{hours} h {minutes:02d} min' if hours else f'{minutes} min {seconds:02d} s' if minutes else f'{seconds} s'
