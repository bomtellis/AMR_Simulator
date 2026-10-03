"""Immutable, absolute-time geometric occupancy ledger.

Callers supply proved moving swept cells and explicit stationary footprints; this
module never reads an AMR's current/future attributes or invents a connecting path.
A plan covers every instant from departure through a stationary infinite tail.
An accepted update returns a new ledger. Keeping the previous ledger reference is
a complete rollback snapshot; rejected updates return that same reference.

Conflicts describe conservative swept-cell conflicts, not proof of deadlock.
``earliest_release`` is the next known end of a blocking claim, NOT a feasible
departure time. Indefinite blockers require replanning their owner or reporting
an unresolved blockage, not silently deleting their parked footprint.
"""
from dataclasses import dataclass
import math

from amr_geometric_occupancy import stationary_claim
from amr_geometric_traffic import first_traffic_slot, polygon_bounds, polygons_overlap, MAX_PAIR_CHECKS
from amr_trajectories import EPS, TrajectoryError


def _finite(value, name, nonnegative=False):
    if (not isinstance(value, (int, float)) or isinstance(value, bool)
            or not math.isfinite(value) or (nonnegative and value < 0)):
        raise TrajectoryError('invalid_input', f'{name} must be a finite '
                              f'{"nonnegative " if nonnegative else ""}number.')
    return float(value)


@dataclass(frozen=True)
class OccupancyClaim:
    owner: str
    floor: int
    start: float
    end: float
    polygon: tuple
    envelope: tuple
    robot_clearance_m: float
    occupancy_kind: str
    source_id: str = ''

    def row(self):
        return {'owner': self.owner, 'floor': self.floor, 'start': self.start,
                'end': self.end, 'polygon': [list(p) for p in self.polygon],
                'envelope': list(self.envelope), 'robot_clearance_m': self.robot_clearance_m,
                'occupancy_kind': self.occupancy_kind, 'source_id': self.source_id}


def _claim(row):
    if not isinstance(row, dict):
        raise TrajectoryError('invalid_input', 'Each occupancy claim must be an object.')
    owner, floor = row.get('owner'), row.get('floor')
    if not isinstance(owner, str) or not owner:
        raise TrajectoryError('invalid_input', 'Every occupancy claim needs an owner id.')
    if not isinstance(floor, int) or isinstance(floor, bool):
        raise TrajectoryError('invalid_input', 'Every occupancy claim needs an integer floor id.')
    start = _finite(row.get('start'), 'Claim start', nonnegative=True)
    end = row.get('end')
    kind = row.get('occupancy_kind', 'moving')
    if not isinstance(end, (int, float)) or isinstance(end, bool) or math.isnan(end):
        raise TrajectoryError('invalid_input', 'A claim needs a numeric end time.')
    if kind == 'instantaneous':
        if not math.isfinite(end) or end != start:
            raise TrajectoryError('invalid_input', 'Instantaneous occupancy requires equal finite start/end times.')
    elif kind not in ('moving', 'stationary') or end <= start or (math.isinf(end) and kind != 'stationary'):
        raise TrajectoryError('invalid_input', 'Moving/stationary end must exceed start; only stationary claims may end at +infinity.')
    polygon = row.get('polygon')
    if not isinstance(polygon, (tuple, list)) or len(polygon) < 3:
        raise TrajectoryError('invalid_input', 'A claim needs a nondegenerate convex footprint polygon.')
    points = []
    for point in polygon:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise TrajectoryError('invalid_input', 'Each polygon vertex needs x,y coordinates.')
        points.append(tuple(_finite(v, 'Polygon coordinate') for v in point))
    # SAT requires convex, ordered, nondegenerate polygons. Reject duplicate
    # vertices and nonconvex or self-crossing order instead of accepting bad claims.
    if len(set(points)) != len(points):
        raise TrajectoryError('invalid_input', 'Polygon vertices must be distinct.')
    area = sum(a[0]*b[1]-b[0]*a[1] for a, b in zip(points, points[1:]+points[:1]))
    if abs(area) <= EPS:
        raise TrajectoryError('invalid_input', 'A claim polygon must have nonzero area.')
    direction = 1 if area > 0 else -1
    for a, b in zip(points, points[1:]+points[:1]):
        for c in points:
            if direction*((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])) < -EPS:
                raise TrajectoryError('invalid_input', 'A claim polygon must be convex and consistently ordered.')
    envelope = polygon_bounds(points)
    if 'envelope' in row:
        supplied = row['envelope']
        if (not isinstance(supplied, (list, tuple)) or len(supplied) != 4
                or any(abs(_finite(v, 'Envelope coordinate')-actual) > EPS
                       for v, actual in zip(supplied, envelope))):
            raise TrajectoryError('invalid_input', 'Claim envelope must match its complete polygon.')
    gap = _finite(row.get('robot_clearance_m', 0), 'Robot clearance', nonnegative=True)
    source = row.get('source_id', '')
    if not isinstance(source, str):
        raise TrajectoryError('invalid_input', 'Claim source id must be a string.')
    return OccupancyClaim(owner, floor, start, float(end), tuple(points), envelope, gap, kind, source)


@dataclass(frozen=True)
class OccupancyConflict:
    owner: str
    blocking_owner: str
    floor: int
    start: float
    end: float
    proposed_kind: str
    blocking_kind: str
    blocking_release: float | None
    proposed_source_id: str = ''
    blocking_source_id: str = ''

    @property
    def permanent(self):
        """No known departure in this ledger; not a declaration of deadlock."""
        return self.blocking_release is None


@dataclass(frozen=True)
class PlanUpdate:
    accepted: bool
    ledger: 'OccupancyLedger'
    conflicts: tuple = ()
    earliest_release: float | None = None
    permanent_blockers: tuple = ()


@dataclass(frozen=True)
class OccupancyLedger:
    _claims: tuple = ()

    def rows(self, floor=None):
        """Return independent rows for existing traffic APIs; mutation is harmless."""
        return [claim.row() for claim in self._claims if floor is None or claim.floor == floor]

    def snapshot(self):
        """Immutable rollback snapshot: restore by assigning this ledger reference."""
        return self

    def initialise(self, *, owner, floor, pose, start, length_m, width_m,
                   robot_clearance_m=0, max_pair_checks=MAX_PAIR_CHECKS):
        if any(claim.owner == owner for claim in self._claims):
            raise TrajectoryError('invalid_input', f'{owner} already has an occupancy plan.')
        initial = stationary_claim(pose, start=start, end=math.inf, owner=owner,
                                   length_m=length_m, width_m=width_m,
                                   robot_clearance_m=robot_clearance_m)
        initial['floor'] = floor
        return self._propose(owner, start, [initial], allow_new=True, max_pair_checks=max_pair_checks)

    def replace_plan(self, owner, departure, claims, *, max_pair_checks=MAX_PAIR_CHECKS):
        """Atomically replace one owner's future, preserving history before departure.

        Claims have absolute times and floor ids. Swept cells default to moving;
        stationary/instantaneous rows must say so. Instantaneous load transitions
        have equal finite start/end and are checked at that exact timestamp, with
        no invented epsilon duration. Other intervals are half-open [start,end).
        Adjacent cell boundaries allow EPS numerical
        tolerance. Only a stationary prior interval may be cut short. This ledger
        proves occupancy coverage/conflicts; the caller must prove pose continuity,
        floor transitions and kinematic feasibility before submitting swept cells.
        """
        return self._propose(owner, departure, claims, allow_new=False, max_pair_checks=max_pair_checks)

    def _propose(self, owner, departure, rows, *, allow_new, max_pair_checks):
        if not isinstance(owner, str) or not owner:
            raise TrajectoryError('invalid_input', 'A plan needs a nonempty owner id.')
        departure = _finite(departure, 'Departure', nonnegative=True)
        if not isinstance(rows, (list, tuple)) or not rows:
            raise TrajectoryError('invalid_input', 'A plan needs contiguous claims and a terminal stationary tail.')
        if not isinstance(max_pair_checks, int) or isinstance(max_pair_checks, bool) or max_pair_checks < 1:
            raise TrajectoryError('invalid_input', 'Conflict comparison budget must be a positive integer.')
        proposed = tuple(_claim(row) for row in rows)
        if any(claim.owner != owner for claim in proposed):
            raise TrajectoryError('invalid_input', 'All replacement claims must belong to the selected owner.')
        if abs(proposed[0].start-departure) > EPS:
            raise TrajectoryError('invalid_input', 'A replacement must start exactly at departure.')
        if not math.isinf(proposed[-1].end) or proposed[-1].occupancy_kind != 'stationary':
            raise TrajectoryError('invalid_input', 'A plan must finish with an infinite stationary tail.')
        for previous, current in zip(proposed, proposed[1:]):
            if math.isinf(previous.end) or abs(previous.end-current.start) > EPS:
                raise TrajectoryError('invalid_input', 'Replacement claims must be ordered and contiguous without overlap or gaps.')
        previous_owner = [claim for claim in self._claims if claim.owner == owner]
        if not allow_new and not previous_owner:
            raise TrajectoryError('invalid_input', 'Initialise an explicit stationary pose before replacing a plan.')
        if previous_owner and departure < min(claim.start for claim in previous_owner)-EPS:
            raise TrajectoryError('invalid_input', 'A replacement cannot precede the owner\'s initial occupancy.')
        history = []
        for claim in self._claims:
            # Retain an instantaneous completion at the next departure boundary:
            # its physically present load must not disappear when a new task starts.
            if claim.owner != owner or claim.end <= departure:
                history.append(claim)
            elif claim.start < departure:
                if claim.occupancy_kind != 'stationary':
                    raise TrajectoryError('invalid_input', 'Departure cannot cut an already planned moving cell; supply a motion boundary.')
                history.append(OccupancyClaim(claim.owner, claim.floor, claim.start, departure,
                    claim.polygon, claim.envelope, claim.robot_clearance_m, claim.occupancy_kind, claim.source_id))
        conflicts, checks = [], 0
        for candidate in proposed:
            # A relative cell with start=0 permits the existing traffic scheduler
            # to enforce the same conservative SAT and max(A,B) pair clearance.
            cell = candidate.row()
            cell['start'], cell['end'] = 0, candidate.end-candidate.start
            for other in history:
                if other.owner == owner or other.floor != candidate.floor:
                    continue
                instant = candidate.occupancy_kind == 'instantaneous' or other.occupancy_kind == 'instantaneous'
                if instant:
                    # Exact point membership in the other half-open interval.
                    # EPS widening would fabricate occupancy duration or erase
                    # a real boundary event; equality is intentional here.
                    if candidate.occupancy_kind == other.occupancy_kind == 'instantaneous':
                        simultaneous = candidate.start == other.start
                    elif candidate.occupancy_kind == 'instantaneous':
                        simultaneous = other.start <= candidate.start < other.end
                    else:
                        simultaneous = candidate.start <= other.start < candidate.end
                    if not simultaneous:
                        continue
                elif candidate.end <= other.start+EPS or other.end <= candidate.start+EPS:
                    continue
                checks += 1
                if checks > max_pair_checks:
                    raise TrajectoryError('search_limit', 'Occupancy conflict comparison budget exhausted; no plan was committed.')
                if instant:
                    if not polygons_overlap(candidate.polygon, other.polygon,
                            max(candidate.robot_clearance_m, other.robot_clearance_m)):
                        continue
                else:
                    earliest, _ = first_traffic_slot([other.row()], [cell], candidate.start, owner, 0)
                    if earliest <= candidate.start+EPS:
                        continue
                conflicts.append(OccupancyConflict(owner, other.owner, candidate.floor,
                    max(candidate.start, other.start), min(candidate.end, other.end),
                    candidate.occupancy_kind, other.occupancy_kind,
                    other.end if math.isfinite(other.end) else None,
                    candidate.source_id, other.source_id))
        if conflicts:
            finite = [c.blocking_release for c in conflicts if c.blocking_release is not None]
            return PlanUpdate(False, self, tuple(conflicts), min(finite) if finite else None,
                              tuple(sorted({c.blocking_owner for c in conflicts if c.permanent})))
        return PlanUpdate(True, OccupancyLedger(tuple(history)+proposed))
