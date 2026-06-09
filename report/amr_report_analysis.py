from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd
import json

COLUMN_ALIASES = {
    "timestamp": [
        "timestamp",
        "time",
        "event_time",
        "datetime",
        "sim_datetime",
        "sim_time_iso",
        "current_datetime",
        "clock_time",
    ],
    "seconds": [
        "sim_time_s",
        "sim_time_seconds",
        "current_time",
        "time_s",
        "elapsed_seconds",
        "seconds",
    ],
    "amr": [
        "amr",
        "amr_id",
    ],
    "task": ["task", "task_id", "job", "job_id", "consignment_id"],
    "event": ["event", "event_type", "status", "state", "action", "phase"],
    "segment_type": ["segment_type", "segment", "segment_name", "movement_type"],
    "duration": [
        "duration_sec",
        "duration_seconds",
        "segment_duration_s",
        "segment_seconds",
        "elapsed_s",
        "task_duration_sec",
    ],
    "wait": ["wait_time_sec", "wait_seconds", "waiting_s", "queue_s"],
    "lift": ["lift", "lift_id", "elevator", "elevator_id"],
    "from": [
        "from_location",
        "from",
        "from_node",
        "start_node",
        "origin",
        "pickup",
        "source",
    ],
    "to": [
        "to_location",
        "to",
        "to_node",
        "end_node",
        "destination",
        "dropoff",
        "target",
    ],
    "start_floor": ["start_floor", "from_floor", "floor_from"],
    "end_floor": ["end_floor", "to_floor", "floor_to"],
    "outcome": ["outcome", "result", "task_result"],
    "payload": ["payload", "payload_type", "payload_name", "load_type", "load"],
    "distance": ["distance_m", "segment_distance_m", "distance", "travel_distance_m"],
    "energy": [
        "energy_kwh",
        "segment_energy_kwh",
        "energy",
        "consumption_kwh",
        "recharge_energy_kwh",
    ],
    "reason": [
        "failure_reason",
        "reason",
        "failed_reason",
        "fail_reason",
        "pending_reason",
        "message",
        "detail",
        "details",
        "note",
        "notes",
    ],
    "start_x": ["start_x", "from_x", "x_from", "origin_x", "x1"],
    "start_y": ["start_y", "from_y", "y_from", "origin_y", "y1"],
    "end_x": ["end_x", "to_x", "x_to", "destination_x", "x2"],
    "end_y": ["end_y", "to_y", "y_to", "destination_y", "y2"],
}

WAIT_PATTERNS = re.compile(r"wait|queue|queued|blocked|hold|reserve|reservation", re.I)
COMPLETE_PATTERNS = re.compile(
    r"complete|completed|done|success|delivered|released", re.I
)
FAIL_PATTERNS = re.compile(
    r"fail|failed|abort|aborted|cancel|cancelled|stuck|timeout", re.I
)
ASSIGN_PATTERNS = re.compile(r"assign|allocated|accepted|dispatch", re.I)
LIFT_PATTERNS = re.compile(r"lift|elevator", re.I)


@dataclass
class Context:
    cols: Dict[str, Optional[str]]
    has_datetime: bool
    time_col: str


def normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [
        re.sub(r"[^a-z0-9]+", "_", str(c).strip().lower()).strip("_")
        for c in df.columns
    ]
    return df


def pick_col(df: pd.DataFrame, key: str) -> Optional[str]:
    for alias in COLUMN_ALIASES[key]:
        if alias in df.columns:
            return alias
    return None


def parse_time_column(df: pd.DataFrame) -> Tuple[pd.DataFrame, Context]:
    df = normalise_columns(df)
    cols = {k: pick_col(df, k) for k in COLUMN_ALIASES}
    if cols["timestamp"]:
        df["_event_time"] = pd.to_datetime(df[cols["timestamp"]], errors="coerce")
        if df["_event_time"].notna().any():
            return df, Context(cols=cols, has_datetime=True, time_col="_event_time")
    if cols["seconds"]:
        df["_event_time"] = pd.to_numeric(df[cols["seconds"]], errors="coerce")
        return df, Context(cols=cols, has_datetime=False, time_col="_event_time")
    raise ValueError("No usable time column found.")


def fmt_ts(value, has_datetime: bool) -> str:
    if pd.isna(value):
        return "-"
    return (
        # pd.Timestamp(value).strftime("%Y-%m-%d %H:%M:%S")
        pd.Timestamp(value).strftime("%d/%m/%Y %H:%M:%S")
        if has_datetime
        else f"{float(value):,.1f}s"
    )


def fmt_duration(seconds: Optional[float]) -> str:
    if seconds is None or pd.isna(seconds):
        return "-"
    seconds = abs(float(seconds))
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:d}:{s:02d}"


def safe_text(value) -> str:
    if value is None or pd.isna(value):
        return "-"
    text = str(value)
    return text if text.strip() else "-"




def split_payload_names(value) -> List[str]:
    """Return real payload names from a simulator payload cell.

    Multi-stop pickup rows can contain comma-separated payload names, while
    empty/return/charging rows may contain blanks or explicit empty payload
    labels.  Reporting should count physical payloads, not the literal CSV
    cell text.
    """
    if value is None:
        return []
    try:
        if pd.isna(value):
            return []
    except Exception:
        pass

    text = str(value).strip()
    if not text:
        return []

    # Some upstream rows may carry JSON arrays/dicts; accept the common forms
    # without requiring the caller to know which schema version produced them.
    if text.startswith("["):
        try:
            decoded = json.loads(text)
            names: List[str] = []
            if isinstance(decoded, list):
                for item in decoded:
                    if isinstance(item, dict):
                        names.extend(split_payload_names(item.get("payload", "")))
                    else:
                        names.extend(split_payload_names(item))
            return names
        except Exception:
            pass

    empty_tokens = {
        "",
        "-",
        "none",
        "nan",
        "null",
        "empty",
        "no payload",
        "no_payload",
        "empty_payload",
        "__empty__",
        "__empty_payload__",
    }
    names: List[str] = []
    for part in text.split(","):
        name = part.strip()
        normalised = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
        if not name or name.lower() in empty_tokens or normalised in empty_tokens:
            continue
        names.append(name)
    return names


def primary_payload_name(value) -> str:
    names = split_payload_names(value)
    return names[0] if names else "-"


def build_payload_schedule(tasks: pd.DataFrame, payload_weights: Dict[str, float]) -> pd.DataFrame:
    """Build a de-duplicated physical payload schedule.

    The task table is the safe source because each completed delivery appears
    once there.  The raw segment log repeats payload state on every corridor,
    lift and wait row so it must not be used directly for payload counting.
    """
    if tasks is None or tasks.empty:
        return pd.DataFrame(columns=["payload", "tasks", "payload_weight_kg"])

    source = tasks.copy()
    if "outcome" in source.columns and (source["outcome"] == "completed").any():
        source = source[source["outcome"] == "completed"].copy()

    rows: List[dict] = []
    for _, row in source.iterrows():
        task_id = safe_text(row.get("task_id"))
        for payload_name in split_payload_names(row.get("payload")):
            rows.append(
                {
                    "task_id": task_id,
                    "payload": payload_name,
                    "payload_weight_kg": float(payload_weights.get(str(payload_name), 0.0)),
                }
            )

    if not rows:
        return pd.DataFrame(columns=["payload", "tasks", "payload_weight_kg"])

    payload_events = pd.DataFrame(rows).drop_duplicates(["task_id", "payload"])
    payload_schedule = (
        payload_events.groupby("payload", dropna=False)
        .agg(
            tasks=("task_id", "count"),
            payload_weight_kg=("payload_weight_kg", "first"),
        )
        .reset_index()
        .sort_values(["payload"])
    )
    payload_schedule["payload_weight_kg"] = (
        pd.to_numeric(payload_schedule["payload_weight_kg"], errors="coerce")
        .fillna(0.0)
        .round(1)
    )
    return payload_schedule.reset_index(drop=True)



def split_task_ids(value) -> List[str]:
    """Return task IDs from CSV cells that may contain JSON or comma lists."""
    if value is None or pd.isna(value):
        return []
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "-"}:
        return []
    if text.startswith("["):
        try:
            decoded = json.loads(text)
            if isinstance(decoded, list):
                return [str(x).strip() for x in decoded if str(x).strip()]
        except Exception:
            pass
    return [x.strip() for x in text.split(",") if x.strip()]


def _append_unique_stop(stops: List[str], item: str) -> None:
    item = str(item or "").strip()
    if not item or item == "-":
        return
    if not stops or stops[-1] != item:
        stops.append(item)


def build_multi_stop_task_paths(
    df: pd.DataFrame,
    ctx: Context,
    amr_col: str,
    task_col: str,
    from_col: Optional[str],
    to_col: Optional[str],
) -> Dict[str, str]:
    """Build a readable stop path for every task inside a multi-stop batch.

    Multi-stop segment rows use grouped task IDs, so the normal per-task rows
    cannot show the actual route sequence.  This function reconstructs the stop
    sequence from the grouped pickup/dropoff rows and maps it back to each
    component task ID.
    """
    if df is None or df.empty:
        return {}

    multi_stop_col = "multi_stop_task_ids" if "multi_stop_task_ids" in df.columns else None
    route_rows = df[df["_event_text"].astype(str).str.contains("multi_stop_segment", case=False, na=False)].copy()
    if route_rows.empty:
        grouped_task_mask = df[task_col].astype(str).str.contains(",", na=False)
        route_rows = df[grouped_task_mask].copy()
    if route_rows.empty:
        return {}

    route_rows = route_rows.sort_values([amr_col, ctx.time_col]).copy()
    grouped: Dict[Tuple[str, Tuple[str, ...]], List[pd.Series]] = {}
    for _, row in route_rows.iterrows():
        task_ids = split_task_ids(row.get(multi_stop_col)) if multi_stop_col else []
        if not task_ids:
            task_ids = split_task_ids(row.get(task_col))
        if len(task_ids) < 2:
            continue
        key = (safe_text(row.get(amr_col)), tuple(task_ids))
        grouped.setdefault(key, []).append(row)

    paths: Dict[str, str] = {}
    for (_amr, task_ids_tuple), rows in grouped.items():
        rows = sorted(rows, key=lambda r: r.get(ctx.time_col))
        stops: List[str] = []
        for row in rows:
            seg = str(row.get("_segment_text", "") or "").strip().lower()
            event = str(row.get("_event_text", "") or "").strip().lower()
            from_value = safe_text(row.get(from_col)) if from_col else "-"
            to_value = safe_text(row.get(to_col)) if to_col else "-"

            # Only show operational stops, not every graph/corridor node.
            # Pickup/dropoff rows normally have the location in from/to.
            if "pickup" in seg or "pickup" in event:
                loc = to_value if to_value != "-" else from_value
                _append_unique_stop(stops, f"Pickup: {loc}")
            elif "dropoff" in seg or "dropoff" in event:
                loc = to_value if to_value != "-" else from_value
                _append_unique_stop(stops, f"Drop-off: {loc}")
            elif "wait_for_location" in seg or "wait_for_location" in event:
                loc = to_value if to_value != "-" else from_value
                _append_unique_stop(stops, f"Wait: {loc}")

        if not stops:
            # Fallback: use unique from/to locations in time order.
            for row in rows:
                if from_col:
                    _append_unique_stop(stops, safe_text(row.get(from_col)))
                if to_col:
                    _append_unique_stop(stops, safe_text(row.get(to_col)))

        if not stops:
            continue
        path = " → ".join(stops)
        for task_id in task_ids_tuple:
            paths[str(task_id)] = path
    return paths


def _multi_stop_task_ids_from_row(
    row,
    task_col: str,
    multi_stop_col: Optional[str] = None,
) -> List[str]:
    """Extract all task IDs that define a multi-stop batch for a row."""
    ids: List[str] = []
    if multi_stop_col and multi_stop_col in row.index:
        ids = split_task_ids(row.get(multi_stop_col))
    if ids:
        return ids

    details = str(row.get("details", "") or "").strip()
    if details.startswith("{"):
        try:
            decoded = json.loads(details)
            for key in ("multi_stop_task_ids", "task_ids"):
                values = decoded.get(key)
                if isinstance(values, list):
                    ids = [str(x).strip() for x in values if str(x).strip()]
                    if ids:
                        return ids
        except Exception:
            pass

    return split_task_ids(row.get(task_col))


def build_multi_stop_task_leg_overrides(
    df: pd.DataFrame,
    ctx: Context,
    amr_col: str,
    task_col: str,
    from_col: Optional[str],
    to_col: Optional[str],
) -> Dict[str, dict]:
    """Map each task in a multi-stop route to its stop-to-stop leg.

    Task detail should describe the leg that delivered each payload, not the
    whole batch route.  For a pharmacy batch this produces rows such as:

        D7-PHARMACY -> D1-PHARMACY
        D1-PHARMACY -> D2-PHARMACY
        D2-PHARMACY -> D3-PHARMACY

    The returned override also carries leg start/finish/duration so the PDF
    does not repeat the full multi-stop batch duration on every payload row.
    """
    if df is None or df.empty or not from_col or not to_col:
        return {}

    multi_stop_col = "multi_stop_task_ids" if "multi_stop_task_ids" in df.columns else None
    route_rows = df[
        df["_event_text"].astype(str).str.contains(
            r"multi_stop_segment", case=False, na=False
        )
    ].copy()
    if route_rows.empty:
        grouped_task_mask = df[task_col].astype(str).str.contains(",", na=False)
        route_rows = df[grouped_task_mask].copy()
    if route_rows.empty:
        return {}

    grouped: Dict[Tuple[str, Tuple[str, ...]], List[pd.Series]] = {}
    for _, row in route_rows.sort_values([amr_col, ctx.time_col]).iterrows():
        batch_ids = _multi_stop_task_ids_from_row(row, task_col, multi_stop_col)
        if len(batch_ids) < 2:
            continue
        key = (safe_text(row.get(amr_col)), tuple(batch_ids))
        grouped.setdefault(key, []).append(row)

    overrides: Dict[str, dict] = {}

    for (_amr, _batch_ids), rows in grouped.items():
        rows = sorted(rows, key=lambda r: r.get(ctx.time_col))
        current_stop: Optional[str] = None
        current_depart_time = None
        current_wait_s = 0.0

        for row in rows:
            seg = str(row.get("_segment_text", "") or "").strip().lower()
            event = str(row.get("_event_text", "") or "").strip().lower()
            from_value = safe_text(row.get(from_col)) if from_col else "-"
            to_value = safe_text(row.get(to_col)) if to_col else "-"
            stop = to_value if to_value != "-" else from_value
            row_start = row.get(ctx.time_col)
            row_duration = float(pd.to_numeric(row.get("_duration_s", 0.0), errors="coerce") or 0.0)
            row_finish = add_seconds_to_event_time(row_start, row_duration, ctx.has_datetime)
            row_wait = float(pd.to_numeric(row.get("_wait_s", 0.0), errors="coerce") or 0.0)

            if "pickup" in seg or "pickup" in event:
                if stop != "-":
                    current_stop = stop
                # The first delivery leg starts once loading has finished.
                current_depart_time = row_finish
                current_wait_s = 0.0
                continue

            if current_stop is not None and ("wait" in seg or "wait" in event):
                # Count waits between stops against the leg that follows.
                current_wait_s += max(0.0, row_wait or row_duration)
                continue

            if "dropoff" not in seg and "dropoff" not in event:
                continue
            if stop == "-":
                continue

            drop_task_ids = split_task_ids(row.get(task_col))
            if not drop_task_ids:
                # Only use the whole batch as a last resort.  Current simulator
                # drop-off rows should identify the specific delivered task.
                drop_task_ids = _multi_stop_task_ids_from_row(row, task_col, multi_stop_col)

            leg_start = current_depart_time if current_depart_time is not None else row_start
            leg_finish = row_finish
            leg_duration = _duration_between_event_times(leg_start, leg_finish, ctx.has_datetime)
            if leg_duration is None or leg_duration < 0:
                leg_duration = row_duration

            start_stop = current_stop or (from_value if from_value != "-" else None)
            if start_stop:
                for task_id in drop_task_ids:
                    overrides[str(task_id)] = {
                        "origin": start_stop,
                        "destination": stop,
                        "start": leg_start,
                        "finish": leg_finish,
                        "duration_s": float(leg_duration),
                        "wait_s": float(current_wait_s),
                    }

            # The next delivery leg starts after this drop-off is complete.
            current_stop = stop
            current_depart_time = row_finish
            current_wait_s = 0.0

    return overrides


def build_multi_stop_task_endpoint_overrides(
    df: pd.DataFrame,
    ctx: Context,
    amr_col: str,
    task_col: str,
    from_col: Optional[str],
    to_col: Optional[str],
) -> Dict[str, Tuple[str, str]]:
    # Backwards-compatible wrapper for older callers.
    return {
        task_id: (data.get("origin", "-"), data.get("destination", "-"))
        for task_id, data in build_multi_stop_task_leg_overrides(
            df, ctx, amr_col, task_col, from_col, to_col
        ).items()
    }

def time_delta_seconds(start, end, has_datetime: bool) -> Optional[float]:
    if pd.isna(start) or pd.isna(end):
        return None
    return (
        (pd.Timestamp(end) - pd.Timestamp(start)).total_seconds()
        if has_datetime
        else float(end) - float(start)
    )


def event_time_to_float(value, has_datetime: bool) -> Optional[float]:
    if pd.isna(value):
        return None
    return pd.Timestamp(value).timestamp() if has_datetime else float(value)


def add_seconds_to_event_time(value, seconds: float, has_datetime: bool):
    if pd.isna(value):
        return value
    if has_datetime:
        return pd.Timestamp(value) + pd.to_timedelta(float(seconds or 0.0), unit="s")
    return float(value) + float(seconds or 0.0)


def _duration_between_event_times(start, finish, has_datetime: bool) -> Optional[float]:
    return time_delta_seconds(start, finish, has_datetime)


def percentile_95_concurrency(intervals: Iterable[Tuple[float, float]]) -> int:
    events: List[Tuple[float, int]] = []
    for start, end in intervals:
        if (
            start is None
            or end is None
            or pd.isna(start)
            or pd.isna(end)
            or end < start
        ):
            continue
        events.append((float(start), 1))
        events.append((float(end), -1))
    if not events:
        return 0
    events.sort(key=lambda x: (x[0], -x[1]))
    current = 0
    values: List[int] = []
    for _, delta in events:
        current += delta
        values.append(current)
    return int(math.ceil(pd.Series(values).quantile(0.95))) if values else 0


def merge_intervals(intervals: Iterable[Tuple[float, float]], gap_tolerance: float = 1.0) -> List[Tuple[float, float]]:
    clean = sorted(
        (float(start), float(end))
        for start, end in intervals
        if start is not None
        and end is not None
        and not pd.isna(start)
        and not pd.isna(end)
        and float(end) >= float(start)
    )
    if not clean:
        return []

    merged: List[Tuple[float, float]] = []
    cur_start, cur_end = clean[0]
    for start, end in clean[1:]:
        if start <= cur_end + gap_tolerance:
            cur_end = max(cur_end, end)
        else:
            merged.append((cur_start, cur_end))
            cur_start, cur_end = start, end
    merged.append((cur_start, cur_end))
    return merged


def build_amr_busy_intervals(
    df: pd.DataFrame,
    ctx: Context,
    amr_col: str,
) -> Tuple[Dict[str, List[Tuple[float, float]]], pd.DataFrame]:
    """Return actual AMR busy intervals from segment rows.

    Multi-stop logs repeat one route across several component task IDs.  Counting
    task duration therefore overstates AMR demand.  Segment rows are the correct
    source: each AMR is busy once on each corridor, lift, wait, pickup/dropoff or
    charge segment, regardless of how many payload slots are occupied.
    """
    if df is None or df.empty or amr_col not in df.columns:
        return {}, pd.DataFrame(columns=["amr", "route_start", "route_finish", "route_time_s"])

    event_text = df.get("_event_text", pd.Series("", index=df.index)).astype(str)
    seg_text = df.get("_segment_text", pd.Series("", index=df.index)).astype(str)
    duration = pd.to_numeric(df.get("_duration_s", pd.Series(0, index=df.index)), errors="coerce").fillna(0.0)

    segment_mask = (
        event_text.str.contains(r"segment|multi_stop_segment|charge", case=False, na=False)
        | seg_text.str.contains(r"corridor|lift|pickup|dropoff|wait|charge|reposition", case=False, na=False)
    )
    rows = df[segment_mask & df[amr_col].notna() & (duration > 0)].copy()
    if rows.empty:
        return {}, pd.DataFrame(columns=["amr", "route_start", "route_finish", "route_time_s"])

    per_amr: Dict[str, List[Tuple[float, float]]] = {}
    route_rows: List[dict] = []
    for amr, sub in rows.groupby(amr_col, dropna=False):
        intervals: List[Tuple[float, float]] = []
        for idx, row in sub.iterrows():
            start = event_time_to_float(row.get(ctx.time_col), ctx.has_datetime)
            if start is None:
                continue
            end = start + float(duration.loc[idx])
            intervals.append((start, end))
        merged = merge_intervals(intervals, gap_tolerance=1.0)
        amr_name = safe_text(amr)
        per_amr[amr_name] = merged
        for start, end in merged:
            route_rows.append(
                {
                    "amr": amr_name,
                    "route_start": start,
                    "route_finish": end,
                    "route_time_s": end - start,
                }
            )

    return per_amr, pd.DataFrame(route_rows)


def interval_total(intervals: Iterable[Tuple[float, float]]) -> float:
    return float(sum(max(0.0, float(end) - float(start)) for start, end in intervals))


def choose_task_endpoint(
    g: pd.DataFrame,
    ctx: Context,
    from_col: Optional[str],
    to_col: Optional[str],
    which: str,
):
    """Prefer generated/assigned task endpoints over completion/segment state.

    Multi-stop completion rows can describe the route final AMR location.  For
    the task detail table, From/To should describe the delivery request itself.
    """
    if g is None or g.empty:
        return None
    col = from_col if which == "from" else to_col
    if not col or col not in g.columns:
        return None

    preferred = g[
        g.get("_event_text", pd.Series("", index=g.index))
        .astype(str)
        .str.contains(r"task_generated|task_assigned|multi_stop_task_assigned|waste_task_generated|return_task_generated", case=False, na=False)
    ]
    for source in (preferred, g):
        values = [str(v).strip() for v in source[col].dropna().tolist() if str(v).strip() and str(v).strip() != "-"]
        if values:
            return values[0] if which == "from" else values[-1]
    return None


def extract_lift_and_floor(value) -> Tuple[Optional[str], Optional[int]]:
    if value is None or pd.isna(value):
        return None, None
    text = str(value).strip()
    if not text:
        return None, None
    lift_match = re.search(r"([Ll]ift\s*[-_ ]?\d+|\bL\d+\b)", text)
    floor_match = re.search(r"(?:^|[^A-Za-z])(B?\d+)(?:$|[^A-Za-z])", text)
    lift_id = lift_match.group(1).replace(" ", "") if lift_match else None
    floor_no = None
    if floor_match:
        token = floor_match.group(1).upper()
        floor_no = -int(token[1:]) if token.startswith("B") else int(token)
    return lift_id, floor_no


def derive_lift_columns(
    df: pd.DataFrame, cols: Dict[str, Optional[str]]
) -> pd.DataFrame:
    df = df.copy()
    derived_lift: List[Optional[str]] = []
    derived_from_floor: List[Optional[int]] = []
    derived_to_floor: List[Optional[int]] = []
    for _, row in df.iterrows():
        from_lift, from_floor = extract_lift_and_floor(
            row.get(cols["from"]) if cols["from"] else None
        )
        to_lift, to_floor = extract_lift_and_floor(
            row.get(cols["to"]) if cols["to"] else None
        )
        final_lift = (
            safe_text(row.get(cols["lift"]))
            if cols["lift"] and pd.notna(row.get(cols["lift"]))
            else None
        )
        if final_lift == "-":
            final_lift = None
        final_lift = final_lift or from_lift or to_lift
        derived_lift.append(final_lift)
        derived_from_floor.append(from_floor)
        derived_to_floor.append(to_floor)
    df["_lift_id"] = derived_lift
    df["_lift_from_floor"] = derived_from_floor
    df["_lift_to_floor"] = derived_to_floor
    return df


def load_payload_weights(json_path: Path) -> Dict[str, float]:
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    payloads = data.get("payloads", [])
    weights: Dict[str, float] = {}

    for item in payloads:
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        try:
            weights[name] = float(item.get("weight_kg", 0))
        except (TypeError, ValueError):
            weights[name] = 0.0

    return weights


def _to_float(value, default: float = 0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def polygon_area(points: List[dict]) -> float:
    if not points or len(points) < 3:
        return 0.0
    coords = [(_to_float(p.get("dx")), _to_float(p.get("dy"))) for p in points]
    total = 0.0
    for i, (x1, y1) in enumerate(coords):
        x2, y2 = coords[(i + 1) % len(coords)]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def polygon_dimensions(points: List[dict]) -> Tuple[float, float]:
    if not points:
        return 0.0, 0.0
    xs = [_to_float(p.get("dx")) for p in points]
    ys = [_to_float(p.get("dy")) for p in points]
    return max(xs) - min(xs), max(ys) - min(ys)


def load_payload_dimensions(json_path: Path) -> pd.DataFrame:
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    rows: List[dict] = []
    for item in data.get("payloads", []):
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        length = _to_float(item.get("length_m"))
        width = _to_float(item.get("width_m"))
        height = _to_float(item.get("height_m"))
        rows.append(
            {
                "payload": name,
                "payload_weight_kg": _to_float(item.get("weight_kg")),
                "payload_length_m": length,
                "payload_width_m": width,
                "payload_height_m": height,
                "payload_area_m2": round(length * width, 3),
            }
        )
    return pd.DataFrame(rows)


def load_location_catalog(json_path: Path) -> pd.DataFrame:
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    location_to_department: Dict[str, str] = {}
    location_to_category: Dict[str, str] = {}
    for dept in data.get("departments", []):
        dept_name = str(dept.get("name") or dept.get("id") or "-").strip() or "-"
        task_locations = dept.get("task_generation_locations", {}) or {}
        for category, cfg in task_locations.items():
            for loc_name in (cfg or {}).get("pickup_dropoff_locations", []) or []:
                if not loc_name:
                    continue
                location_to_department[str(loc_name)] = dept_name
                location_to_category[str(loc_name)] = str(category).title()

    rows: List[dict] = []
    for loc in data.get("locations", []):
        name = str(loc.get("name", "")).strip()
        if not name:
            continue
        bbox = loc.get("bounding_box", []) or []
        length, width = polygon_dimensions(bbox)
        area = polygon_area(bbox)
        spaces = loc.get("inventory_spaces", None)
        spaces_list = spaces if isinstance(spaces, list) else []
        explicit_spaces = spaces is not None
        inventory_area = sum(
            polygon_area((space or {}).get("points", []) or []) for space in spaces_list
        )
        rows.append(
            {
                "location": name,
                "department": location_to_department.get(name, "-"),
                "category": location_to_category.get(name, "-"),
                "floor": loc.get("floor", "-"),
                "length_m": round(length, 2),
                "width_m": round(width, 2),
                "area_m2": round(area, 2),
                "inventory_spaces_current": len(spaces_list),
                "inventory_area_m2": round(inventory_area, 2),
                "inventory_spaces_defined": explicit_spaces,
            }
        )
    return pd.DataFrame(rows)


def _empty_location_outputs() -> (
    Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]
):
    return (
        pd.DataFrame(
            columns=[
                "department",
                "category",
                "location",
                "floor",
                "length_m",
                "width_m",
                "area_m2",
                "inventory_spaces_current",
                "deliveries_completed",
                "failed_delivery_attempts",
                "capacity_related_failures",
                "utilisation_pct",
                "recommended_area_m2",
                "recommended_inventory_spaces",
            ]
        ),
        pd.DataFrame(
            columns=[
                "time",
                "task_id",
                "amr",
                "department",
                "category",
                "location",
                "payload",
                "payload_length_m",
                "payload_width_m",
                "payload_height_m",
                "payload_area_m2",
                "failure_reason",
            ]
        ),
        pd.DataFrame(
            columns=[
                "department",
                "category",
                "location",
                "current_area_m2",
                "recommended_area_m2",
                "additional_area_m2",
                "current_inventory_spaces",
                "recommended_inventory_spaces",
                "additional_inventory_spaces",
                "reason",
            ]
        ),
        pd.DataFrame(
            columns=[
                "location",
                "payload",
                "payload_length_m",
                "payload_width_m",
                "payload_height_m",
                "failed_count",
            ]
        ),
    )


def build_location_space_analysis(
    tasks: pd.DataFrame,
    location_catalog: Optional[pd.DataFrame],
    payload_dimensions: Optional[pd.DataFrame],
    has_datetime: bool,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if location_catalog is None or location_catalog.empty:
        return _empty_location_outputs()

    loc = location_catalog.copy()
    payload_dims = (
        payload_dimensions.copy() if payload_dimensions is not None else pd.DataFrame()
    )
    if payload_dims.empty:
        payload_dims = pd.DataFrame(
            columns=[
                "payload",
                "payload_length_m",
                "payload_width_m",
                "payload_height_m",
                "payload_area_m2",
            ]
        )

    task_ext = tasks.copy()
    task_ext = task_ext.merge(payload_dims, on="payload", how="left")
    loc_meta = loc[["location", "department", "category"]].copy()
    task_ext = task_ext.merge(
        loc_meta, left_on="destination", right_on="location", how="left"
    )
    task_ext["location"] = task_ext["location"].fillna(task_ext["destination"])
    task_ext["department"] = task_ext["department"].fillna("-")
    task_ext["category"] = task_ext["category"].fillna("-")

    reason_col = "failure_reason" if "failure_reason" in task_ext.columns else None
    if reason_col is None:
        task_ext["failure_reason"] = task_ext.apply(
            lambda r: (
                "Task failed; no detailed reason was present in the CSV event log."
                if r.get("outcome") == "failed"
                else "-"
            ),
            axis=1,
        )

    failed_attempts = task_ext[task_ext["outcome"] == "failed"].copy()
    failed_attempts["capacity_related_failure"] = (
        failed_attempts["failure_reason"]
        .astype(str)
        .str.contains(
            r"invent|space|capacity|full|store|storage|dimension|fit|area",
            case=False,
            na=False,
        )
    )

    delivery_counts = (
        task_ext[task_ext["outcome"] == "completed"]
        .groupby("location", dropna=False)
        .size()
        .reset_index(name="deliveries_completed")
    )
    failed_counts = (
        failed_attempts.groupby("location", dropna=False)
        .size()
        .reset_index(name="failed_delivery_attempts")
    )
    capacity_failed_counts = (
        failed_attempts[failed_attempts["capacity_related_failure"]]
        .groupby("location", dropna=False)
        .size()
        .reset_index(name="capacity_related_failures")
    )
    failed_area = (
        failed_attempts.groupby("location", dropna=False)["payload_area_m2"]
        .sum()
        .reset_index(name="failed_payload_area_m2")
    )
    max_failed_area = (
        failed_attempts.groupby("location", dropna=False)["payload_area_m2"]
        .max()
        .reset_index(name="max_failed_payload_area_m2")
    )

    util = loc.merge(delivery_counts, on="location", how="left")
    util = util.merge(failed_counts, on="location", how="left")
    util = util.merge(capacity_failed_counts, on="location", how="left")
    util = util.merge(failed_area, on="location", how="left")
    util = util.merge(max_failed_area, on="location", how="left")
    for col in [
        "deliveries_completed",
        "failed_delivery_attempts",
        "capacity_related_failures",
    ]:
        util[col] = util[col].fillna(0).astype(int)
    for col in ["failed_payload_area_m2", "max_failed_payload_area_m2", "area_m2"]:
        util[col] = pd.to_numeric(util[col], errors="coerce").fillna(0.0)

    util["inventory_spaces_current"] = (
        pd.to_numeric(util["inventory_spaces_current"], errors="coerce")
        .fillna(0)
        .astype(int)
    )
    inventory_area_numeric = pd.to_numeric(
        util["inventory_area_m2"], errors="coerce"
    ).fillna(0.0)
    location_area_numeric = pd.to_numeric(util["area_m2"], errors="coerce").fillna(0.0)
    util["utilisation_pct"] = (
        (
            inventory_area_numeric.div(
                location_area_numeric.where(location_area_numeric > 0)
            )
            * 100
        )
        .fillna(0)
        .round(1)
    )

    # Capacity recommendation baseline.
    #
    # Do not convert every failed delivery attempt into another permanent
    # inventory space.  A burst of repeated failures at a hub location can turn
    # 19 trolley destinations into hundreds of "recommended" spaces.  Space
    # count is corrected later from simulator peak simultaneous occupancy rows
    # when those rows are available.  This fallback only protects older CSVs
    # that do not contain peak-location metrics.
    util["recommended_area_m2"] = util.apply(
        lambda r: max(
            float(r["area_m2"]),
            float(r["area_m2"]) + (float(r["max_failed_payload_area_m2"]) * 1.30),
        ),
        axis=1,
    ).round(2)
    util["recommended_inventory_spaces"] = util.apply(
        lambda r: max(
            int(r["inventory_spaces_current"]),
            int(r["inventory_spaces_current"]) + (
                1 if int(r["capacity_related_failures"]) > 0 else 0
            ),
            (
                1
                if int(r["failed_delivery_attempts"]) > 0
                else int(r["inventory_spaces_current"])
            ),
        ),
        axis=1,
    ).astype(int)

    failed_detail = (
        failed_attempts[
            [
                "start",
                "task_id",
                "amr",
                "department",
                "category",
                "location",
                "payload",
                "payload_length_m",
                "payload_width_m",
                "payload_height_m",
                "payload_area_m2",
                "failure_reason",
            ]
        ].copy()
        if not failed_attempts.empty
        else pd.DataFrame(
            columns=[
                "start",
                "task_id",
                "amr",
                "department",
                "category",
                "location",
                "payload",
                "payload_length_m",
                "payload_width_m",
                "payload_height_m",
                "payload_area_m2",
                "failure_reason",
            ]
        )
    )
    failed_detail = failed_detail.rename(columns={"start": "time"})
    if not failed_detail.empty:
        failed_detail["time"] = failed_detail["time"].map(
            lambda v: fmt_ts(v, has_datetime) if not pd.isna(v) else "-"
        )
        for c in [
            "payload_length_m",
            "payload_width_m",
            "payload_height_m",
            "payload_area_m2",
        ]:
            failed_detail[c] = (
                pd.to_numeric(failed_detail[c], errors="coerce").fillna(0).round(2)
            )

    failed_payload_sizes = (
        failed_attempts.groupby(
            [
                "location",
                "payload",
                "payload_length_m",
                "payload_width_m",
                "payload_height_m",
            ],
            dropna=False,
        )
        .size()
        .reset_index(name="failed_count")
        .sort_values(["location", "failed_count"], ascending=[True, False])
        if not failed_attempts.empty
        else pd.DataFrame(
            columns=[
                "location",
                "payload",
                "payload_length_m",
                "payload_width_m",
                "payload_height_m",
                "failed_count",
            ]
        )
    )

    recommendations = util.copy()
    recommendations["additional_area_m2"] = (
        (recommendations["recommended_area_m2"] - recommendations["area_m2"])
        .clip(lower=0)
        .round(2)
    )
    recommendations["additional_inventory_spaces"] = (
        (
            recommendations["recommended_inventory_spaces"]
            - recommendations["inventory_spaces_current"]
        )
        .clip(lower=0)
        .astype(int)
    )
    recommendations["reason"] = recommendations.apply(
        lambda r: (
            "Increase storage for failed capacity-related delivery attempts."
            if int(r["capacity_related_failures"]) > 0
            else (
                "Review location: failed deliveries occurred but no capacity keyword was logged."
                if int(r["failed_delivery_attempts"]) > 0
                else "No failed delivery pressure identified."
            )
        ),
        axis=1,
    )
    recommendations = recommendations[
        [
            "department",
            "category",
            "location",
            "area_m2",
            "recommended_area_m2",
            "additional_area_m2",
            "inventory_spaces_current",
            "recommended_inventory_spaces",
            "additional_inventory_spaces",
            "reason",
        ]
    ].rename(
        columns={
            "area_m2": "current_area_m2",
            "inventory_spaces_current": "current_inventory_spaces",
        }
    )

    util = (
        util[
            [
                "department",
                "category",
                "location",
                "floor",
                "length_m",
                "width_m",
                "area_m2",
                "inventory_spaces_current",
                "deliveries_completed",
                "failed_delivery_attempts",
                "capacity_related_failures",
                "utilisation_pct",
                "recommended_area_m2",
                "recommended_inventory_spaces",
            ]
        ]
        .sort_values(["department", "category", "location"])
        .reset_index(drop=True)
    )

    return (
        util,
        failed_detail.reset_index(drop=True),
        recommendations.reset_index(drop=True),
        failed_payload_sizes.reset_index(drop=True),
    )



def build_location_peak_occupancy(
    df: pd.DataFrame,
    ctx: Context,
    location_catalog: Optional[pd.DataFrame] = None,
    payload_dimensions: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Calculate peak location occupancy from payload enter/exit events.

    The simulator is now responsible only for logging physical movements using
    ``location_payload_enter`` and ``location_payload_exit`` rows.  The report
    reconstructs the live set of payload instances at each location over time and
    takes the maximum simultaneous count, area and volume.

    Older CSVs that only contain ``location_space_recommendation`` rows are still
    supported as a fallback.
    """
    columns = [
        "department",
        "category",
        "location",
        "inventory_spaces_disabled",
        "configured_inventory_area_m2",
        "peak_payload_count",
        "peak_area_used_m2",
        "peak_volume_m3",
        "current_area_used_m2",
        "current_volume_m3",
        "recommended_area_m2",
        "recommended_volume_m3",
    ]
    if df is None or df.empty:
        return pd.DataFrame(columns=columns)

    loc_meta = pd.DataFrame(columns=["location", "department", "category", "inventory_area_m2"])
    if location_catalog is not None and not location_catalog.empty:
        keep = [
            c
            for c in ["location", "department", "category", "inventory_area_m2"]
            if c in location_catalog.columns
        ]
        if "location" in keep:
            loc_meta = location_catalog[keep].drop_duplicates("location").copy()

    payload_lookup: Dict[str, Tuple[float, float]] = {}
    if payload_dimensions is not None and not payload_dimensions.empty:
        for _, row in payload_dimensions.iterrows():
            payload_name = str(row.get("payload", "") or "").strip()
            if not payload_name:
                continue
            length = _to_float(row.get("payload_length_m"), 0.0)
            width = _to_float(row.get("payload_width_m"), 0.0)
            height = _to_float(row.get("payload_height_m"), 0.0)
            area = _to_float(row.get("payload_area_m2"), length * width)
            if area <= 0.0:
                area = max(0.0, length) * max(0.0, width)
            payload_lookup[payload_name] = (area, area * max(0.0, height))

    def _clean_location(value) -> str:
        text = str(value or "").strip()
        return "" if text.lower() in {"", "-", "nan", "none", "null"} else text

    def _clean_payload(value) -> str:
        text = str(value or "").strip()
        return "" if text.lower() in {"", "-", "nan", "none", "null", "empty", "__empty_payload__"} else text

    def _instance_key(row: pd.Series, location: str, payload: str, counter: int) -> str:
        instance = str(row.get("payload_instance_id", "") or "").strip()
        if instance and instance.lower() not in {"nan", "none", "null", "-"}:
            return instance
        task_id = str(row.get("task_id", "") or "").strip()
        if task_id and task_id.lower() not in {"nan", "none", "null", "-"}:
            return f"task:{task_id}:{payload}"
        return f"synthetic:{location}:{payload}:{counter}"

    def _configured_area(location: str) -> float:
        if loc_meta.empty or "inventory_area_m2" not in loc_meta.columns:
            return 0.0
        match = loc_meta[loc_meta["location"] == location]
        if match.empty:
            return 0.0
        return round(_to_float(match.iloc[0].get("inventory_area_m2"), 0.0), 2)

    event_text = df.get("_event_text", pd.Series("", index=df.index)).astype(str)
    movement_rows = df[
        event_text.str.fullmatch(r"location_payload_(enter|exit)", case=False, na=False)
    ].copy()

    if movement_rows.empty:
        # Backwards compatibility for reports run against older simulator CSVs.
        final_rows = df[
            event_text.str.fullmatch("location_space_recommendation", case=False, na=False)
        ].copy()
        if final_rows.empty:
            return pd.DataFrame(columns=columns)
        location_source = next(
            (c for c in ("to_location", "end_node", "from_location") if c in final_rows.columns),
            None,
        )
        if location_source is None:
            return pd.DataFrame(columns=columns)
        final_rows["_report_location"] = final_rows[location_source].map(_clean_location)
        final_rows = final_rows[final_rows["_report_location"] != ""].sort_values(ctx.time_col, kind="stable")
        latest_rows = final_rows.drop_duplicates("_report_location", keep="last")

        def num(row: pd.Series, name: str) -> float:
            if name not in row.index:
                return 0.0
            value = pd.to_numeric(pd.Series([row.get(name)]), errors="coerce").iloc[0]
            return 0.0 if pd.isna(value) else float(value)

        rows = []
        for _, row in latest_rows.iterrows():
            location = _clean_location(row.get("_report_location", ""))
            peak_area = num(row, "location_peak_footprint_area_m2") or num(row, "location_payload_footprint_area_m2")
            peak_volume = num(row, "location_peak_volume_m3") or num(row, "location_payload_volume_m3")
            rows.append(
                {
                    "location": location,
                    "inventory_spaces_disabled": str(row.get("location_inventory_spaces_disabled", "")).strip().lower() in {"true", "1", "yes", "y"},
                    "configured_inventory_area_m2": round(num(row, "location_configured_inventory_area_m2") or _configured_area(location), 2),
                    "peak_payload_count": int(round(num(row, "location_peak_payload_count"))),
                    "peak_area_used_m2": round(peak_area, 2),
                    "peak_volume_m3": round(peak_volume, 2),
                    "current_area_used_m2": round(num(row, "location_payload_footprint_area_m2"), 2),
                    "current_volume_m3": round(num(row, "location_payload_volume_m3"), 2),
                    "recommended_area_m2": round((num(row, "location_recommended_area_m2") or peak_area * 1.30), 2),
                    "recommended_volume_m3": round((num(row, "location_recommended_volume_m3") or peak_volume * 1.30), 2),
                }
            )
    else:
        location_source = next(
            (c for c in ("to_location", "end_node", "from_location") if c in movement_rows.columns),
            None,
        )
        if location_source is None:
            return pd.DataFrame(columns=columns)
        movement_rows["_report_location"] = movement_rows[location_source].map(_clean_location)
        movement_rows["_report_payload"] = movement_rows.get("payload", pd.Series("", index=movement_rows.index)).map(_clean_payload)
        movement_rows = movement_rows[
            (movement_rows["_report_location"] != "") & (movement_rows["_report_payload"] != "")
        ].sort_values(ctx.time_col, kind="stable")

        states: Dict[str, Dict[str, Tuple[str, float, float]]] = {}
        peaks: Dict[str, dict] = {}
        synthetic_counter = 0

        def snapshot(location: str) -> None:
            live = states.get(location, {})
            count = len(live)
            area = sum(v[1] for v in live.values())
            volume = sum(v[2] for v in live.values())
            item = peaks.setdefault(
                location,
                {
                    "peak_payload_count": 0,
                    "peak_area_used_m2": 0.0,
                    "peak_volume_m3": 0.0,
                    "current_area_used_m2": 0.0,
                    "current_volume_m3": 0.0,
                },
            )
            item["current_area_used_m2"] = area
            item["current_volume_m3"] = volume
            if count > int(item.get("peak_payload_count", 0)):
                item["peak_payload_count"] = count
            if area > float(item.get("peak_area_used_m2", 0.0)):
                item["peak_area_used_m2"] = area
            if volume > float(item.get("peak_volume_m3", 0.0)):
                item["peak_volume_m3"] = volume

        for _, row in movement_rows.iterrows():
            location = row["_report_location"]
            payload_name = row["_report_payload"]
            area, volume = payload_lookup.get(payload_name, (0.0, 0.0))
            synthetic_counter += 1
            key = _instance_key(row, location, payload_name, synthetic_counter)
            event = str(row.get("_event_text", "") or "").lower()
            live = states.setdefault(location, {})
            if event.endswith("enter"):
                live[key] = (payload_name, area, volume)
            elif event.endswith("exit"):
                # Prefer exact instance removal, but fall back to the first matching
                # payload at that location so legacy rows without instance IDs still
                # form a useful occupancy timeline.
                if key in live:
                    live.pop(key, None)
                else:
                    match = next((k for k, v in live.items() if v[0] == payload_name), None)
                    if match is not None:
                        live.pop(match, None)
            snapshot(location)

        for location in list(states):
            snapshot(location)

        rows = []
        for location, item in peaks.items():
            peak_count = int(item.get("peak_payload_count", 0) or 0)
            peak_area = float(item.get("peak_area_used_m2", 0.0) or 0.0)
            peak_volume = float(item.get("peak_volume_m3", 0.0) or 0.0)
            configured_area = _configured_area(location)
            if peak_count <= 0 and peak_area <= 0.0 and configured_area <= 0.0:
                continue
            rows.append(
                {
                    "location": location,
                    "inventory_spaces_disabled": False,
                    "configured_inventory_area_m2": configured_area,
                    "peak_payload_count": peak_count,
                    "peak_area_used_m2": round(peak_area, 2),
                    "peak_volume_m3": round(peak_volume, 2),
                    "current_area_used_m2": round(float(item.get("current_area_used_m2", 0.0) or 0.0), 2),
                    "current_volume_m3": round(float(item.get("current_volume_m3", 0.0) or 0.0), 2),
                    "recommended_area_m2": round(peak_area * 1.30, 2),
                    "recommended_volume_m3": round(peak_volume * 1.30, 2),
                }
            )

    if not rows:
        return pd.DataFrame(columns=columns)
    peak = pd.DataFrame(rows).drop_duplicates("location", keep="last")
    if not loc_meta.empty:
        merge_cols = [c for c in ["location", "department", "category"] if c in loc_meta.columns]
        peak = peak.merge(loc_meta[merge_cols].drop_duplicates("location"), on="location", how="left")
    else:
        peak["department"] = "-"
        peak["category"] = "-"
    peak["department"] = peak["department"].fillna("-")
    peak["category"] = peak["category"].fillna("-")
    return peak[columns].sort_values(["department", "category", "location"]).reset_index(drop=True)


def apply_peak_occupancy_to_location_outputs(
    location_space_utilisation: pd.DataFrame,
    location_recommendations: pd.DataFrame,
    location_peak_occupancy: pd.DataFrame,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    if location_peak_occupancy is None or location_peak_occupancy.empty:
        return location_space_utilisation, location_recommendations

    peak_cols = [
        "location",
        "inventory_spaces_disabled",
        "configured_inventory_area_m2",
        "peak_payload_count",
        "peak_area_used_m2",
        "peak_volume_m3",
        "recommended_area_m2",
        "recommended_volume_m3",
    ]
    peak = location_peak_occupancy[[c for c in peak_cols if c in location_peak_occupancy.columns]].copy()
    peak = peak.rename(columns={"recommended_area_m2": "peak_recommended_area_m2"})

    util = location_space_utilisation.copy()
    if not util.empty and "location" in util.columns:
        util = util.merge(peak, on="location", how="left")
        for c in ["peak_payload_count", "peak_area_used_m2", "peak_volume_m3", "peak_recommended_area_m2", "recommended_volume_m3", "configured_inventory_area_m2"]:
            if c in util.columns:
                util[c] = pd.to_numeric(util[c], errors="coerce").fillna(0)
        if "peak_recommended_area_m2" in util.columns:
            util["recommended_area_m2"] = util[["recommended_area_m2", "peak_recommended_area_m2"]].max(axis=1).round(2)
        if "peak_payload_count" in util.columns:
            peak_count = pd.to_numeric(util["peak_payload_count"], errors="coerce").fillna(0).astype(int)
            current_spaces = pd.to_numeric(
                util.get("inventory_spaces_current", pd.Series(0, index=util.index)),
                errors="coerce",
            ).fillna(0).astype(int)
            existing_recommendation = pd.to_numeric(
                util.get("recommended_inventory_spaces", pd.Series(0, index=util.index)),
                errors="coerce",
            ).fillna(0).astype(int)

            # Peak simultaneous payload count is the authoritative space count.
            # This prevents repeated failed delivery attempts at a hub from being
            # interpreted as one permanent inventory space per failure.
            peak_space_recommendation = peak_count.where(peak_count > 0, existing_recommendation)
            util["recommended_inventory_spaces"] = pd.concat(
                [current_spaces, peak_space_recommendation], axis=1
            ).max(axis=1).astype(int)
        if "peak_area_used_m2" in util.columns:
            area = pd.to_numeric(util.get("area_m2", 0), errors="coerce").fillna(0)
            util["peak_utilisation_pct"] = (pd.to_numeric(util["peak_area_used_m2"], errors="coerce").fillna(0).div(area.where(area > 0)) * 100).fillna(0).round(1)

    rec = location_recommendations.copy()
    if not rec.empty and "location" in rec.columns:
        rec = rec.merge(peak, on="location", how="left")
        for c in ["peak_payload_count", "peak_area_used_m2", "peak_volume_m3", "peak_recommended_area_m2", "recommended_volume_m3"]:
            if c in rec.columns:
                rec[c] = pd.to_numeric(rec[c], errors="coerce").fillna(0)
        if "peak_recommended_area_m2" in rec.columns:
            rec["recommended_area_m2"] = rec[["recommended_area_m2", "peak_recommended_area_m2"]].max(axis=1).round(2)
            rec["additional_area_m2"] = (rec["recommended_area_m2"] - pd.to_numeric(rec["current_area_m2"], errors="coerce").fillna(0)).clip(lower=0).round(2)
        if "peak_payload_count" in rec.columns:
            peak_count = pd.to_numeric(rec["peak_payload_count"], errors="coerce").fillna(0).astype(int)
            current_spaces = pd.to_numeric(
                rec.get("current_inventory_spaces", pd.Series(0, index=rec.index)),
                errors="coerce",
            ).fillna(0).astype(int)
            existing_recommendation = pd.to_numeric(
                rec.get("recommended_inventory_spaces", pd.Series(0, index=rec.index)),
                errors="coerce",
            ).fillna(0).astype(int)
            peak_space_recommendation = peak_count.where(peak_count > 0, existing_recommendation)
            rec["recommended_inventory_spaces"] = pd.concat(
                [current_spaces, peak_space_recommendation], axis=1
            ).max(axis=1).astype(int)
            rec["additional_inventory_spaces"] = (
                rec["recommended_inventory_spaces"] - current_spaces
            ).clip(lower=0).astype(int)
        if "peak_area_used_m2" in rec.columns:
            rec["reason"] = rec.apply(
                lambda r: "Recommended from peak simultaneous payload storage demand recorded by the simulator; failed delivery attempts are not counted as one space each."
                if float(r.get("peak_area_used_m2", 0) or 0) > 0
                else r.get("reason", "-"),
                axis=1,
            )
    return util, rec

def load_amr_parameters(json_path: Path) -> pd.DataFrame:
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    amrs = data.get("amrs", [])
    rows: List[dict] = []

    for item in amrs:
        rows.append(
            {
                "amr": str(item.get("id", "")).strip() or "-",
                "quantity": int(item.get("quantity", 1) or 1),
                "payload_capacity_kg": item.get("payload_capacity_kg", "-"),
                "payload_capacity_size_units": item.get(
                    "payload_capacity_size_units", "-"
                ),
                "speed_m_per_sec": item.get("speed_m_per_sec", "-"),
                "battery_capacity_kwh": item.get("battery_capacity_kwh", "-"),
                "battery_charge_rate_kw": item.get("battery_charge_rate_kw", "-"),
                "recharge_threshold_percent": item.get(
                    "recharge_threshold_percent", "-"
                ),
                "battery_soc_percent": item.get("battery_soc_percent", "-"),
                "start_location": item.get("start_location", "-"),
            }
        )

    return pd.DataFrame(rows)


def load_floor_dxf_map(json_path: Path) -> Dict[int, str]:
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    rows = data.get("floor_dxf_files", data.get("dxf_files", []))
    floor_map: Dict[int, str] = {}

    for item in rows:
        try:
            floor = int(item.get("floor"))
        except (TypeError, ValueError):
            continue

        path = str(item.get("filepath", "")).strip()
        if not path:
            continue

        floor_map[floor] = path

    return floor_map


def is_lift_wait_row(row: pd.Series) -> bool:
    segment_text = str(row.get("_segment_text", "")).strip().lower()
    event_text = str(row.get("_event_text", "")).strip().lower()

    if "lift" in segment_text and "wait" in segment_text:
        return True
    if "lift" in event_text and "wait" in event_text:
        return True
    if segment_text == "lift_transfer" and float(row.get("_wait_s", 0) or 0) > 0:
        return True
    return False


def extract_congestion_point(
    row: pd.Series,
    cols: Dict[str, Optional[str]],
) -> Tuple[Optional[float], Optional[float], Optional[int]]:
    sx = pd.to_numeric(
        row.get(cols["start_x"]) if cols.get("start_x") else None,
        errors="coerce",
    )
    sy = pd.to_numeric(
        row.get(cols["start_y"]) if cols.get("start_y") else None,
        errors="coerce",
    )
    sf = pd.to_numeric(
        row.get(cols["start_floor"]) if cols.get("start_floor") else None,
        errors="coerce",
    )

    ex = pd.to_numeric(
        row.get(cols["end_x"]) if cols.get("end_x") else None,
        errors="coerce",
    )
    ey = pd.to_numeric(
        row.get(cols["end_y"]) if cols.get("end_y") else None,
        errors="coerce",
    )
    ef = pd.to_numeric(
        row.get(cols["end_floor"]) if cols.get("end_floor") else None,
        errors="coerce",
    )

    if pd.notna(sx) and pd.notna(sy) and pd.notna(sf):
        return float(sx), float(sy), int(sf)

    if pd.notna(ex) and pd.notna(ey) and pd.notna(ef):
        return float(ex), float(ey), int(ef)

    return None, None, None


def analyse(
    csv_path: Path,
    target_amr_util: float,
    target_lift_util: float,
    payload_weights: Optional[Dict[str, float]] = None,
    amr_parameters: Optional[pd.DataFrame] = None,
    floor_dxf_map: Optional[Dict[int, str]] = None,
    location_catalog: Optional[pd.DataFrame] = None,
    payload_dimensions: Optional[pd.DataFrame] = None,
) -> Dict[str, pd.DataFrame]:
    payload_weights = payload_weights or {}
    raw = pd.read_csv(csv_path, low_memory=False)
    df, ctx = parse_time_column(raw)
    df = df.sort_values(ctx.time_col).reset_index(drop=True)
    cols = ctx.cols

    amr_col = cols["amr"]
    task_col = cols["task"]
    if not amr_col or not task_col:
        raise ValueError("CSV must contain AMR and task identifiers.")

    event_col = cols["event"]
    seg_col = cols["segment_type"]
    duration_col = cols["duration"]
    wait_col = cols["wait"]
    from_col = cols["from"]
    to_col = cols["to"]
    outcome_col = cols["outcome"]
    reason_col = cols.get("reason")

    payload_col = cols["payload"]
    distance_col = cols["distance"]
    energy_col = cols["energy"]

    df["_event_text"] = df[event_col].astype(str) if event_col else ""
    df["_segment_text"] = df[seg_col].astype(str) if seg_col else ""
    df["_duration_s"] = (
        pd.to_numeric(df[duration_col], errors="coerce") if duration_col else pd.NA
    )
    df["_distance_m"] = (
        pd.to_numeric(df[distance_col], errors="coerce") if distance_col else 0.0
    )
    df["_energy_kwh"] = (
        pd.to_numeric(df[energy_col], errors="coerce").fillna(0.0)
        if energy_col
        else 0.0
    )
    df["_wait_s"] = (
        pd.to_numeric(df[wait_col], errors="coerce").fillna(0) if wait_col else 0.0
    )

    if not wait_col and duration_col:
        wait_mask = df["_event_text"].str.contains(WAIT_PATTERNS, na=False)
        df.loc[wait_mask, "_wait_s"] = df.loc[wait_mask, "_duration_s"].fillna(0)

    t0 = df[ctx.time_col].dropna().min()
    t1 = df[ctx.time_col].dropna().max()
    horizon_s = max(time_delta_seconds(t0, t1, ctx.has_datetime) or 0.0, 1.0)

    multi_stop_task_paths = build_multi_stop_task_paths(
        df, ctx, amr_col, task_col, from_col, to_col
    )
    multi_stop_task_leg_overrides = build_multi_stop_task_leg_overrides(
        df, ctx, amr_col, task_col, from_col, to_col
    )

    task_rows: List[dict] = []
    active_intervals: List[Tuple[float, float]] = []

    raw_task_ids = [str(x).strip() for x in df[task_col].dropna().tolist() if str(x).strip()]
    single_task_ids = {task_id for task_id in raw_task_ids if "," not in task_id}

    for task_id, g in df[df[task_col].notna()].groupby(task_col, sort=False):
        task_id_text = str(task_id).strip()
        if "," in task_id_text:
            component_ids = [x.strip() for x in task_id_text.split(",") if x.strip()]
            # Grouped multi-pickup segment rows are visualiser state rows, not
            # extra tasks.  When their component task IDs also exist as normal
            # assignment/completion rows, skip the grouped pseudo-task so reports
            # do not count the same payloads multiple times.
            if component_ids and all(x in single_task_ids for x in component_ids):
                continue
        g = g.sort_values(ctx.time_col)
        first = g.iloc[0]
        last = g.iloc[-1]
        start_row = g[g["_event_text"].str.contains(ASSIGN_PATTERNS, na=False)].head(1)
        end_row = g[g["_event_text"].str.contains(COMPLETE_PATTERNS, na=False)].tail(1)
        fail_row = g[g["_event_text"].str.contains(FAIL_PATTERNS, na=False)].tail(1)
        start = (
            start_row.iloc[0][ctx.time_col]
            if not start_row.empty
            else first[ctx.time_col]
        )
        end = last[ctx.time_col]
        outcome = "incomplete"
        if not fail_row.empty:
            end = fail_row.iloc[-1][ctx.time_col]
            outcome = "failed"
        if not end_row.empty:
            end = end_row.iloc[-1][ctx.time_col]
            outcome = "completed"
        if outcome_col and g[outcome_col].notna().any():
            last_outcome = str(g[outcome_col].dropna().iloc[-1]).strip().lower()
            if COMPLETE_PATTERNS.search(last_outcome):
                outcome = "completed"
            elif FAIL_PATTERNS.search(last_outcome):
                outcome = "failed"
        duration_s = time_delta_seconds(start, end, ctx.has_datetime)
        wait_s = float(pd.to_numeric(g["_wait_s"], errors="coerce").fillna(0).sum())
        amr = g[amr_col].dropna().iloc[0] if g[amr_col].notna().any() else "-"
        origin = choose_task_endpoint(g, ctx, from_col, to_col, "from")
        destination = choose_task_endpoint(g, ctx, from_col, to_col, "to")
        multi_stop_leg_override = multi_stop_task_leg_overrides.get(str(task_id))
        if multi_stop_leg_override:
            origin = multi_stop_leg_override.get("origin", origin)
            destination = multi_stop_leg_override.get("destination", destination)
            start = multi_stop_leg_override.get("start", start)
            end = multi_stop_leg_override.get("finish", end)
            duration_s = multi_stop_leg_override.get("duration_s", duration_s)
            wait_s = multi_stop_leg_override.get("wait_s", wait_s)

        payload = (
            primary_payload_name(g[payload_col].dropna().iloc[0])
            if payload_col and g[payload_col].notna().any()
            else "-"
        )
        distance_m = float(
            pd.to_numeric(g["_distance_m"], errors="coerce").fillna(0).sum()
        )
        payload_weight_kg = float(payload_weights.get(str(payload), 0.0))
        failure_reason = "-"
        if outcome == "failed":
            reason_values: List[str] = []
            if reason_col and reason_col in g.columns:
                reason_values.extend(
                    [
                        str(v).strip()
                        for v in g[reason_col].dropna().tolist()
                        if str(v).strip()
                    ]
                )
            event_reasons = [
                str(v).strip()
                for v in g["_event_text"].dropna().tolist()
                if FAIL_PATTERNS.search(str(v))
            ]
            if reason_values:
                failure_reason = reason_values[-1]
            elif event_reasons:
                failure_reason = event_reasons[-1]
            else:
                failure_reason = (
                    "Task failed; no detailed reason was present in the CSV event log."
                )
        task_rows.append(
            {
                "amr": safe_text(amr),
                "task_id": safe_text(task_id),
                "outcome": outcome,
                "failure_reason": failure_reason,
                "start": start,
                "finish": end,
                "duration_s": duration_s,
                "wait_s": wait_s,
                "origin": safe_text(origin),
                "destination": safe_text(destination),
                "route_path": multi_stop_task_paths.get(
                    str(task_id),
                    f"{safe_text(origin)} → {safe_text(destination)}",
                ),
                "payload": safe_text(payload),
                "distance_m": distance_m,
                "payload_weight_kg": payload_weight_kg,
            }
        )
        # Do not add per-task active intervals here.  A multi-stop route can
        # complete several tasks at the same time, so task intervals would count
        # the same AMR route once per payload slot.  Resource recommendations are
        # derived later from actual AMR segment busy intervals.

    # How many tasks did each AMR complete

    tasks = pd.DataFrame(task_rows)
    completed = tasks[tasks["outcome"] == "completed"].copy()
    failed = tasks[tasks["outcome"] == "failed"].copy()

    amr_busy_intervals_by_amr, amr_route_summary = build_amr_busy_intervals(
        df, ctx, amr_col
    )
    active_intervals = [
        interval
        for intervals in amr_busy_intervals_by_amr.values()
        for interval in intervals
    ]
    amr_busy_time_by_amr = {
        amr: interval_total(intervals)
        for amr, intervals in amr_busy_intervals_by_amr.items()
    }
    amr_route_count_by_amr = {
        amr: len(intervals) for amr, intervals in amr_busy_intervals_by_amr.items()
    }

    amr_summary = (
        tasks.groupby("amr", dropna=False)
        .agg(
            tasks_total=("task_id", "count"),
            tasks_completed=("outcome", lambda s: int((s == "completed").sum())),
            tasks_failed=("outcome", lambda s: int((s == "failed").sum())),
            total_task_time_s=("duration_s", "sum"),
            total_wait_s=("wait_s", "sum"),
            avg_task_time_s=("duration_s", "mean"),
            total_distance_km=("distance_m", "sum"),
        )
        .reset_index()
    )
    # Replace duplicated task-duration workload with actual AMR route busy time.
    # For multi-slot AMRs, several completed payload tasks can share one route;
    # summing task durations would overstate AMR demand and fleet size.
    amr_summary["routes"] = amr_summary["amr"].map(amr_route_count_by_amr).fillna(0).astype(int)
    amr_summary["total_route_time_s"] = amr_summary["amr"].map(amr_busy_time_by_amr).fillna(0.0)
    amr_summary["total_task_time_s"] = amr_summary["total_route_time_s"]

    amr_summary["total_distance_km"] = (amr_summary["total_distance_km"] / 1000).round(
        2
    )

    # Utilisation

    amr_utilisation = (
        tasks.groupby("amr", dropna=False)
        .agg(
            tasks_total=("task_id", "count"),
            total_task_time_s=("duration_s", "sum"),
            total_wait_s=("wait_s", "sum"),
        )
        .reset_index()
    )
    amr_utilisation["routes"] = amr_utilisation["amr"].map(amr_route_count_by_amr).fillna(0).astype(int)
    amr_utilisation["total_route_time_s"] = amr_utilisation["amr"].map(amr_busy_time_by_amr).fillna(0.0)
    amr_utilisation["total_task_time_s"] = amr_utilisation["total_route_time_s"]

    amr_utilisation["utilisation_pct"] = (
        amr_utilisation["total_task_time_s"] / horizon_s * 100
    ).round(1)
    amr_utilisation["idle_pct"] = (
        (100 - amr_utilisation["utilisation_pct"]).clip(lower=0).round(1)
    )
    amr_utilisation["wait_share_pct"] = (
        (
            amr_utilisation["total_wait_s"]
            / amr_utilisation["total_task_time_s"].replace(0, pd.NA)
            * 100
        )
        .fillna(0)
        .round(1)
    )

    # How many recharges did the AMR undergo - battery wear

    charge_mask = df["_segment_text"].str.fullmatch(
        r"segment_charge", case=False, na=False
    )

    recharge_energy = (
        df.loc[charge_mask]
        .groupby(amr_col, dropna=False)["_energy_kwh"]
        .sum()
        .reset_index(name="recharge_energy_kwh")
        .rename(columns={amr_col: "amr"})
    )

    amr_summary = amr_summary.merge(recharge_energy, on="amr", how="left")
    amr_summary["recharge_energy_kwh"] = (
        amr_summary["recharge_energy_kwh"].fillna(0.0).round(3)
    )

    recharge_summary = (
        df.loc[charge_mask]
        .groupby(amr_col, dropna=False)
        .agg(
            recharges=("_segment_text", "size"),
            recharge_energy_kwh=("_energy_kwh", "sum"),
            recharge_time_s=("_duration_s", "sum"),
        )
        .reset_index()
        .rename(columns={amr_col: "amr"})
    )

    if recharge_summary.empty:
        recharge_summary = pd.DataFrame(
            columns=["amr", "recharges", "recharge_energy_kwh", "recharge_time_s"]
        )
    else:
        recharge_summary["recharge_energy_kwh"] = (
            recharge_summary["recharge_energy_kwh"].fillna(0.0).round(3)
        )

    recharge_counts = (
        df.loc[charge_mask]
        .groupby(amr_col, dropna=False)
        .size()
        .reset_index(name="recharges")
        .rename(columns={amr_col: "amr"})
    )

    amr_summary = amr_summary.merge(recharge_counts, on="amr", how="left")
    amr_summary["recharges"] = amr_summary["recharges"].fillna(0).astype(int)

    # Lift usage

    df = derive_lift_columns(df, cols)
    lift_mask = df["_segment_text"].str.fullmatch(
        r"lift_transfer|lift_reposition", case=False, na=False
    )
    lift_rows = df.loc[lift_mask].copy()
    lift_rows = lift_rows[lift_rows["_lift_id"].notna()].copy()
    lift_rows["lift_time_s"] = pd.to_numeric(lift_rows["_duration_s"], errors="coerce")
    lift_rows = lift_rows[
        lift_rows["lift_time_s"].notna() & (lift_rows["lift_time_s"] >= 0)
    ].copy()

    if lift_rows.empty:
        lift_summary = pd.DataFrame(
            columns=[
                "lift_id",
                "trips",
                "total_lift_time_s",
                "avg_trip_s",
                "utilisation_pct",
                "idle_pct",
                "lift_energy_kwh",
            ]
        )
    else:
        lift_summary = (
            lift_rows.groupby("lift_id", dropna=False)
            .agg(
                trips=("lift_time_s", "count"),
                total_lift_time_s=("lift_time_s", "sum"),
                avg_trip_s=("lift_time_s", "mean"),
                lift_energy_kwh=("_energy_kwh", "sum"),
            )
            .reset_index()
            .rename(columns={"_lift_id": "lift_id"})
        )
        lift_summary["utilisation_pct"] = (
            lift_summary["total_lift_time_s"] / horizon_s * 100
        ).round(1)
        lift_summary["idle_pct"] = (
            (100 - lift_summary["utilisation_pct"]).clip(lower=0).round(1)
        )
        lift_summary["lift_energy_kwh"] = lift_summary["lift_energy_kwh"].round(4)

    # Lift Wait times

    lift_wait_rows = df[df.apply(is_lift_wait_row, axis=1)].copy()
    lift_wait_rows = lift_wait_rows[lift_wait_rows["_lift_id"].notna()].copy()
    lift_wait_rows["lift_wait_s"] = pd.to_numeric(
        lift_wait_rows["_wait_s"], errors="coerce"
    ).fillna(0)

    lift_wait_rows = lift_wait_rows[lift_wait_rows["lift_wait_s"] > 0].copy()

    if lift_wait_rows.empty:
        lift_wait_schedule = pd.DataFrame(
            columns=["time", "amr", "task_id", "lift_id", "from", "to", "wait_s"]
        )
    else:
        lift_wait_schedule = (
            lift_wait_rows[
                [
                    ctx.time_col,
                    amr_col,
                    task_col,
                    "_lift_id",
                    from_col,
                    to_col,
                    "lift_wait_s",
                ]
            ]
            .rename(
                columns={
                    ctx.time_col: "time",
                    amr_col: "amr",
                    task_col: "task_id",
                    "_lift_id": "lift_id",
                    from_col: "from",
                    to_col: "to",
                    "lift_wait_s": "wait_s",
                }
            )
            .sort_values("time")
            .reset_index(drop=True)
        )

    # Congestion heatmap data
    congestion_mask = df["_event_text"].str.contains(WAIT_PATTERNS, na=False) | df[
        "_segment_text"
    ].str.contains(WAIT_PATTERNS, na=False)

    congestion_rows = df.loc[congestion_mask].copy()

    congestion_points: List[dict] = []
    for _, row in congestion_rows.iterrows():
        x, y, floor = extract_congestion_point(row, cols)
        if x is None or y is None or floor is None:
            continue

        weight = float(pd.to_numeric(row.get("_wait_s", 0), errors="coerce") or 0.0)
        if weight <= 0:
            weight = float(
                pd.to_numeric(row.get("_duration_s", 0), errors="coerce") or 0.0
            )
        if weight <= 0:
            weight = 1.0

        congestion_points.append(
            {
                "floor": int(floor),
                "x": float(x),
                "y": float(y),
                "weight": float(weight),
                "event": safe_text(row.get("_event_text")),
                "segment": safe_text(row.get("_segment_text")),
            }
        )

    if congestion_points:
        congestion_df = pd.DataFrame(congestion_points)

        grid_size = 2.0
        congestion_df["grid_x"] = (congestion_df["x"] / grid_size).round().astype(int)
        congestion_df["grid_y"] = (congestion_df["y"] / grid_size).round().astype(int)

        congestion_heatmap = (
            congestion_df.groupby(["floor", "grid_x", "grid_y"], dropna=False)
            .agg(
                x=("x", "mean"),
                y=("y", "mean"),
                congestion_score=("weight", "sum"),
                event_count=("weight", "size"),
            )
            .reset_index()
            .sort_values(["floor", "congestion_score"], ascending=[True, False])
            .reset_index(drop=True)
        )
    else:
        congestion_heatmap = pd.DataFrame(
            columns=[
                "floor",
                "grid_x",
                "grid_y",
                "x",
                "y",
                "congestion_score",
                "event_count",
            ]
        )

    # Congestion path data for rectangular path overlays
    # Use travelled segments, weighted by congestion-related wait/duration
    path_source = df[
        df["_segment_text"].str.contains(
            r"corridor|lift_transfer|lift_reposition",
            case=False,
            na=False,
        )
    ].copy()

    congestion_path_rows: List[dict] = []
    for _, row in path_source.iterrows():
        sx = pd.to_numeric(
            row.get(cols["start_x"]) if cols.get("start_x") else None,
            errors="coerce",
        )
        sy = pd.to_numeric(
            row.get(cols["start_y"]) if cols.get("start_y") else None,
            errors="coerce",
        )
        sf = pd.to_numeric(
            row.get(cols["start_floor"]) if cols.get("start_floor") else None,
            errors="coerce",
        )

        ex = pd.to_numeric(
            row.get(cols["end_x"]) if cols.get("end_x") else None,
            errors="coerce",
        )
        ey = pd.to_numeric(
            row.get(cols["end_y"]) if cols.get("end_y") else None,
            errors="coerce",
        )
        ef = pd.to_numeric(
            row.get(cols["end_floor"]) if cols.get("end_floor") else None,
            errors="coerce",
        )

        if pd.isna(sf) and pd.notna(ef):
            sf = ef
        if pd.isna(ef) and pd.notna(sf):
            ef = sf

        if pd.isna(sx) or pd.isna(sy) or pd.isna(ex) or pd.isna(ey) or pd.isna(sf):
            continue

        if pd.notna(ef) and int(sf) != int(ef):
            continue

        if float(sx) == float(ex) and float(sy) == float(ey):
            continue

        weight = float(pd.to_numeric(row.get("_wait_s", 0), errors="coerce") or 0.0)
        if weight <= 0:
            weight = float(
                pd.to_numeric(row.get("_duration_s", 0), errors="coerce") or 0.0
            )
        if weight <= 0:
            weight = 1.0

        congestion_path_rows.append(
            {
                "floor": int(sf),
                "x1": float(sx),
                "y1": float(sy),
                "x2": float(ex),
                "y2": float(ey),
                "congestion_score": float(weight),
                "event": safe_text(row.get("_event_text")),
                "segment": safe_text(row.get("_segment_text")),
            }
        )

    congestion_paths = pd.DataFrame(
        congestion_path_rows,
        columns=[
            "floor",
            "x1",
            "y1",
            "x2",
            "y2",
            "congestion_score",
            "event",
            "segment",
        ],
    )

    active_amrs = max(int(tasks["amr"].nunique()), 1)
    total_amr_route_time_s = interval_total(active_intervals)
    workload_based_amrs = int(
        math.ceil(
            total_amr_route_time_s
            / (horizon_s * max(target_amr_util, 0.01))
        )
    )
    peak_route_concurrency_amrs = percentile_95_concurrency(active_intervals)
    recommended_amrs = max(1, workload_based_amrs, peak_route_concurrency_amrs)

    lift_intervals: List[Tuple[float, float]] = []
    for _, row in lift_rows.dropna(subset=["lift_time_s", ctx.time_col]).iterrows():
        start_n = event_time_to_float(row[ctx.time_col], ctx.has_datetime)
        if start_n is not None:
            lift_intervals.append((start_n, start_n + float(row["lift_time_s"])))

    total_lift_time_s = (
        float(lift_rows["lift_time_s"].sum()) if not lift_rows.empty else 0.0
    )
    avg_lift_util = (
        float(lift_summary["utilisation_pct"].mean()) if not lift_summary.empty else 0.0
    )
    workload_based_lifts = (
        int(math.ceil(total_lift_time_s / (horizon_s * max(target_lift_util, 0.01))))
        if total_lift_time_s
        else 0
    )
    recommended_lifts = max(
        1 if total_lift_time_s else 0,
        workload_based_lifts,
        percentile_95_concurrency(lift_intervals),
    )

    summary = pd.DataFrame(
        [
            {"metric": "Simulation start", "value": fmt_ts(t0, ctx.has_datetime)},
            {"metric": "Simulation finish", "value": fmt_ts(t1, ctx.has_datetime)},
            {"metric": "Simulation duration", "value": fmt_duration(horizon_s)},
            {"metric": "AMRs observed", "value": f"{active_amrs}"},
            {"metric": "Tasks total", "value": f"{len(tasks)}"},
            {"metric": "Tasks completed", "value": f"{len(completed)}"},
            {"metric": "Tasks failed", "value": f"{len(failed)}"},
            {"metric": "AMR routes observed", "value": f"{len(amr_route_summary)}"},
            {
                "metric": "Total AMR route time",
                "value": fmt_duration(total_amr_route_time_s),
            },
            {
                "metric": "AMR workload model requirement",
                "value": f"{workload_based_amrs}",
            },
            {
                "metric": "AMR route concurrency requirement",
                "value": f"{peak_route_concurrency_amrs}",
            },
            {
                "metric": "Total waiting time",
                "value": fmt_duration(tasks["wait_s"].sum()),
            },
            {"metric": "Total lift time", "value": fmt_duration(total_lift_time_s)},
            {"metric": "Average lift utilisation", "value": f"{avg_lift_util:.1f}%"},
            {"metric": "Recommended AMRs", "value": f"{recommended_amrs}"},
            {"metric": "Recommended lifts", "value": f"{recommended_lifts}"},
        ]
    )

    methodology = pd.DataFrame(
        [
            {
                "item": "Recommended AMRs",
                "detail": f"Maximum of actual AMR route-time workload and 95th percentile AMR route concurrency using target utilisation {target_amr_util:.0%}. Multi-stop payload tasks sharing one route are counted once for fleet demand.",
            },
            {
                "item": "Recommended lifts",
                "detail": f"Maximum of lift occupancy model and 95th percentile concurrent lift demand using target utilisation {target_lift_util:.0%}.",
            },
            {
                "item": "Lift parsing",
                "detail": "Uses segment_type = lift_transfer and parses lift/floor from from_location and to_location.",
            },
            {
                "item": "Idle percentage",
                "detail": "Calculated against the full simulation duration for each AMR and each lift.",
            },
        ]
    )

    payload_schedule = build_payload_schedule(tasks, payload_weights)

    (
        location_space_utilisation,
        failed_delivery_summary,
        location_recommendations,
        failed_payload_sizes,
    ) = build_location_space_analysis(
        tasks,
        location_catalog,
        payload_dimensions,
        ctx.has_datetime,
    )

    location_peak_occupancy = build_location_peak_occupancy(
        df, ctx, location_catalog, payload_dimensions
    )
    (
        location_space_utilisation,
        location_recommendations,
    ) = apply_peak_occupancy_to_location_outputs(
        location_space_utilisation,
        location_recommendations,
        location_peak_occupancy,
    )

    if not location_space_utilisation.empty:
        over_capacity = int(
            (location_space_utilisation["capacity_related_failures"] > 0).sum()
        )
        additional_spaces = int(
            location_recommendations.get(
                "additional_inventory_spaces", pd.Series(dtype=int)
            ).sum()
        )
        additional_area = float(
            location_recommendations.get(
                "additional_area_m2", pd.Series(dtype=float)
            ).sum()
        )
        capacity_blocked = int(
            location_space_utilisation["capacity_related_failures"].sum()
        )
        summary = pd.concat(
            [
                summary,
                pd.DataFrame(
                    [
                        {
                            "metric": "Deliveries blocked by location capacity",
                            "value": f"{capacity_blocked}",
                        },
                        {
                            "metric": "Locations with capacity failures",
                            "value": f"{over_capacity}",
                        },
                        {
                            "metric": "Additional inventory spaces required",
                            "value": f"{additional_spaces}",
                        },
                        {
                            "metric": "Additional storage area required",
                            "value": f"{additional_area:.2f} m²",
                        },
                    ]
                ),
            ],
            ignore_index=True,
        )

    if not location_peak_occupancy.empty:
        peak_area_required = float(
            pd.to_numeric(
                location_peak_occupancy.get("recommended_area_m2", pd.Series(dtype=float)),
                errors="coerce",
            ).fillna(0.0).sum()
        )
        peak_payload_count = int(
            pd.to_numeric(
                location_peak_occupancy.get("peak_payload_count", pd.Series(dtype=float)),
                errors="coerce",
            ).fillna(0).sum()
        )
        summary = pd.concat(
            [
                summary,
                pd.DataFrame(
                    [
                        {
                            "metric": "Peak stored payloads across locations",
                            "value": f"{peak_payload_count}",
                        },
                        {
                            "metric": "Storage area recommended from peak occupancy",
                            "value": f"{peak_area_required:.2f} m²",
                        },
                    ]
                ),
            ],
            ignore_index=True,
        )

    return {
        "summary": summary,
        "amr_summary": amr_summary,
        "amr_route_summary": amr_route_summary,
        "utilisation_summary": amr_utilisation,
        "lift_summary": lift_summary,
        "tasks": tasks.sort_values(["amr", "start", "task_id"]).reset_index(drop=True),
        "methodology": methodology,
        "payload_schedule": payload_schedule,
        "location_space_utilisation": location_space_utilisation,
        "failed_delivery_summary": failed_delivery_summary,
        "location_recommendations": location_recommendations,
        "location_peak_occupancy": location_peak_occupancy,
        "failed_payload_sizes": failed_payload_sizes,
        "lift_wait_schedule": lift_wait_schedule,
        "recharge_summary": recharge_summary,
        "amr_list": (
            amr_parameters.copy()
            if amr_parameters is not None
            else pd.DataFrame(
                columns=[
                    "amr",
                    "quantity",
                    "payload_capacity_kg",
                    "payload_capacity_size_units",
                    "speed_m_per_sec",
                    "battery_capacity_kwh",
                    "battery_charge_rate_kw",
                    "recharge_threshold_percent",
                    "battery_soc_percent",
                    "start_location",
                ]
            )
        ),
        "congestion_heatmap": congestion_heatmap,
        "congestion_paths": congestion_paths,
        "floor_dxf_map": floor_dxf_map or {},
    }
