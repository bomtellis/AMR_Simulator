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
) -> Dict[str, pd.DataFrame]:
    raw = pd.read_csv(csv_path)
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

    task_rows: List[dict] = []
    active_intervals: List[Tuple[float, float]] = []

    for task_id, g in df[df[task_col].notna()].groupby(task_col, sort=False):
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
        origin = (
            g[from_col].dropna().iloc[0]
            if from_col and g[from_col].notna().any()
            else None
        )
        destination = (
            g[to_col].dropna().iloc[-1] if to_col and g[to_col].notna().any() else None
        )

        payload = (
            g[payload_col].dropna().iloc[0]
            if payload_col and g[payload_col].notna().any()
            else None
        )
        distance_m = float(
            pd.to_numeric(g["_distance_m"], errors="coerce").fillna(0).sum()
        )
        payload_weight_kg = float(payload_weights.get(str(payload), 0.0))
        task_rows.append(
            {
                "amr": safe_text(amr),
                "task_id": safe_text(task_id),
                "outcome": outcome,
                "start": start,
                "finish": end,
                "duration_s": duration_s,
                "wait_s": wait_s,
                "origin": safe_text(origin),
                "destination": safe_text(destination),
                "payload": safe_text(payload),
                "distance_m": distance_m,
                "payload_weight_kg": payload_weight_kg,
            }
        )
        start_n = event_time_to_float(start, ctx.has_datetime)
        end_n = event_time_to_float(end, ctx.has_datetime)
        if start_n is not None and end_n is not None and end_n >= start_n:
            active_intervals.append((start_n, end_n))

    # How many tasks did each AMR complete

    tasks = pd.DataFrame(task_rows)
    completed = tasks[tasks["outcome"] == "completed"].copy()
    failed = tasks[tasks["outcome"] == "failed"].copy()

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
    workload_based_amrs = int(
        math.ceil(
            tasks["duration_s"].fillna(0).sum()
            / (horizon_s * max(target_amr_util, 0.01))
        )
    )
    recommended_amrs = max(
        1, workload_based_amrs, percentile_95_concurrency(active_intervals)
    )

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
                "detail": f"Maximum of workload model and 95th percentile task concurrency using target utilisation {target_amr_util:.0%}.",
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

    payload_schedule = (
        tasks.groupby(["payload"], dropna=False)
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

    payload_schedule["payload_weight_kg"] = payload_schedule["payload_weight_kg"].round(
        1
    )

    return {
        "summary": summary,
        "amr_summary": amr_summary,
        "utilisation_summary": amr_utilisation,
        "lift_summary": lift_summary,
        "tasks": tasks.sort_values(["amr", "start", "task_id"]).reset_index(drop=True),
        "methodology": methodology,
        "payload_schedule": payload_schedule,
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
