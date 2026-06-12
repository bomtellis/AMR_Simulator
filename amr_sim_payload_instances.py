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
        self._counts_by_payload: Dict[str, int] = {}
        # Registry of every physical payload instance that has existed during
        # the simulation.  _records only contains currently stored instances,
        # so reports need this registry to distinguish asset population from
        # task count or movement count.
        self._known_instances: Dict[str, PayloadInstanceRecord] = {}
        self._counter = 0

    def make_instance_id(self, payload_name: str, task_id: str = "") -> str:
        self._counter += 1
        base = safe_token(payload_name)
        task = safe_token(task_id) if task_id else f"{self._counter:06d}"
        return f"{base}-{task}-{self._counter:06d}"

    def register_instance(
        self,
        payload_name: str,
        instance_id: str,
        source_task_id: str = "",
        location_name: str = "",
        metadata: Optional[dict] = None,
    ) -> None:
        payload_name = normalise_payload_name(payload_name)
        instance_id = clean_text(instance_id)
        if not payload_name or not instance_id:
            return
        existing = self._known_instances.get(instance_id)
        if existing is None:
            self._known_instances[instance_id] = PayloadInstanceRecord(
                instance_id=instance_id,
                payload=payload_name,
                location=clean_text(location_name),
                source_task_id=clean_text(source_task_id),
                status="known",
                metadata=dict(metadata or {}),
            )
            return
        if not existing.payload:
            existing.payload = payload_name
        if location_name:
            existing.location = clean_text(location_name)
        if source_task_id:
            existing.source_task_id = clean_text(source_task_id)
        if metadata:
            existing.metadata.update(dict(metadata))

    def ensure_task_instance_id(self, task) -> str:
        payload_name = normalise_payload_name(getattr(task, "payload", ""))
        if not payload_name:
            setattr(task, "payload_instance_id", "")
            return ""
        instance_id = clean_text(getattr(task, "payload_instance_id", ""))
        if not instance_id:
            instance_id = self.make_instance_id(payload_name, getattr(task, "id", ""))
            setattr(task, "payload_instance_id", instance_id)
        self.register_instance(payload_name, instance_id, getattr(task, "id", ""))
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
            self._decrement_payload_count(previous.payload)

        self.register_instance(
            payload_name,
            instance_id,
            source_task_id=source_task_id,
            location_name=location_name,
            metadata=metadata,
        )
        self._records[instance_id] = PayloadInstanceRecord(
            instance_id=instance_id,
            payload=payload_name,
            location=location_name,
            source_task_id=clean_text(source_task_id),
            status="stored",
            metadata=dict(metadata or {}),
        )
        self._by_location.setdefault(location_name, []).append(instance_id)
        self._counts_by_payload[payload_name] = (
            int(self._counts_by_payload.get(payload_name, 0) or 0) + 1
        )

    def _remove_from_location(self, location_name: str, instance_id: str) -> None:
        ids = self._by_location.get(location_name, [])
        if instance_id in ids:
            ids.remove(instance_id)
        if not ids and location_name in self._by_location:
            self._by_location.pop(location_name, None)

    def _decrement_payload_count(self, payload_name: str) -> None:
        payload_name = normalise_payload_name(payload_name)
        if not payload_name:
            return
        count = int(self._counts_by_payload.get(payload_name, 0) or 0) - 1
        if count > 0:
            self._counts_by_payload[payload_name] = count
        else:
            self._counts_by_payload.pop(payload_name, None)

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
            self._decrement_payload_count(record.payload)
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
            self._decrement_payload_count(record.payload)
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

    def counts_by_payload(self) -> Dict[str, int]:
        return dict(self._counts_by_payload)

    def known_records(self) -> List[PayloadInstanceRecord]:
        """Return every physical payload instance observed during runtime."""
        return list(self._known_instances.values())
