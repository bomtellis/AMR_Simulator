"""Pure helpers for reconstructing AMR payload state from CSV rows."""


def onboard_snapshot_is_authoritative(row: dict, parsed_onboard) -> bool:
    """Whether an onboard_payloads cell should replace reconstructed state.

    Older single-stop CSV rows wrote ``[]`` even while the AMR was carrying a
    payload. Multi-stop rows, and non-empty snapshots from newer logs, are
    authoritative.
    """
    if parsed_onboard:
        return True
    event_type = str(row.get("event_type", "") or "").strip().lower()
    multi_stop_ids = str(row.get("multi_stop_task_ids", "") or "").strip()
    return bool(
        event_type.startswith("multi_stop_")
        or multi_stop_ids not in {"", "[]"}
    )


def row_completes_payload_transport(row: dict) -> bool:
    """Return True only for unload/drop-off or whole-task completion rows."""
    event_type = str(row.get("event_type", "") or "").strip().lower()
    segment_type = str(row.get("segment_type", "") or "").strip().lower()
    text = " ".join((event_type, segment_type))
    return bool(
        "dropoff" in text
        or "drop_off" in text
        or "unload" in text
        or event_type in {"task_complete", "multi_stop_complete"}
    )
