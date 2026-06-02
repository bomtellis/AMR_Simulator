from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import re

EMPTY_PAYLOAD_NAME = "__empty__"


def clean_text(value) -> str:
    return str(value or "").strip()


def is_empty_payload_name(payload_name: str) -> bool:
    return clean_text(payload_name) in {
        "",
        EMPTY_PAYLOAD_NAME,
        "none",
        "None",
        "NONE",
        "-",
        "empty",
        "EMPTY",
    }


def normalise_payload_name(payload_name: str) -> str:
    return "" if is_empty_payload_name(payload_name) else clean_text(payload_name)


def safe_token(value: str) -> str:
    text = clean_text(value)
    text = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")
    return text or "PAYLOAD"


@dataclass
class PayloadInstanceRecord:
    instance_id: str
    payload: str
    location: str
    source_task_id: str = ""
    status: str = "stored"
    metadata: Dict[str, object] = field(default_factory=dict)


class PayloadInstanceStore:
    """Tracks exact physical payload objects by payload_instance_id."""

    def __init__(self):
        self._records: Dict[str, PayloadInstanceRecord] = {}
        self._by_location: Dict[str, List[str]] = {}
        self._counter = 0

    def make_instance_id(self, payload_name: str, task_id: str = "") -> str:
        self._counter += 1
        base = safe_token(payload_name)
        task = safe_token(task_id) if task_id else f"{self._counter:06d}"
        return f"{base}-{task}-{self._counter:06d}"

    def ensure_task_instance_id(self, task) -> str:
        payload_name = normalise_payload_name(getattr(task, "payload", ""))
        if not payload_name:
            setattr(task, "payload_instance_id", "")
            return ""
        instance_id = clean_text(getattr(task, "payload_instance_id", ""))
        if not instance_id:
            instance_id = self.make_instance_id(payload_name, getattr(task, "id", ""))
            setattr(task, "payload_instance_id", instance_id)
        return instance_id

    def store(
        self,
        location_name: str,
        payload_name: str,
        instance_id: str,
        source_task_id: str = "",
        metadata: Optional[dict] = None,
    ) -> None:
        location_name = clean_text(location_name)
        payload_name = normalise_payload_name(payload_name)
        instance_id = clean_text(instance_id)
        if not location_name or not payload_name or not instance_id:
            return

        previous = self._records.get(instance_id)
        if previous:
            self._remove_from_location(previous.location, instance_id)

        self._records[instance_id] = PayloadInstanceRecord(
            instance_id=instance_id,
            payload=payload_name,
            location=location_name,
            source_task_id=clean_text(source_task_id),
            status="stored",
            metadata=dict(metadata or {}),
        )
        self._by_location.setdefault(location_name, []).append(instance_id)

    def _remove_from_location(self, location_name: str, instance_id: str) -> None:
        ids = self._by_location.get(location_name, [])
        if instance_id in ids:
            ids.remove(instance_id)
        if not ids and location_name in self._by_location:
            self._by_location.pop(location_name, None)

    def pickup(
        self, location_name: str, payload_name: str = "", instance_id: str = ""
    ) -> Optional[PayloadInstanceRecord]:
        location_name = clean_text(location_name)
        payload_name = normalise_payload_name(payload_name)
        instance_id = clean_text(instance_id)

        if instance_id:
            record = self._records.get(instance_id)
            if not record or record.location != location_name:
                return None
            if payload_name and record.payload != payload_name:
                return None
            self._remove_from_location(location_name, instance_id)
            self._records.pop(instance_id, None)
            record.status = "picked_up"
            return record

        for candidate_id in list(self._by_location.get(location_name, [])):
            record = self._records.get(candidate_id)
            if not record:
                continue
            if payload_name and record.payload != payload_name:
                continue
            self._remove_from_location(location_name, candidate_id)
            self._records.pop(candidate_id, None)
            record.status = "picked_up"
            return record

        return None

    def has_instance_at(
        self, location_name: str, instance_id: str, payload_name: str = ""
    ) -> bool:
        record = self._records.get(clean_text(instance_id))
        if not record:
            return False
        if record.location != clean_text(location_name):
            return False
        payload_name = normalise_payload_name(payload_name)
        return not payload_name or record.payload == payload_name

    def records_at(self, location_name: str) -> List[PayloadInstanceRecord]:
        return [
            self._records[i]
            for i in self._by_location.get(clean_text(location_name), [])
            if i in self._records
        ]
