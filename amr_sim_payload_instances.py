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
        # Per-location ids are stored in insertion-ordered dictionaries. This
        # keeps pickup order deterministic while making removal O(1) instead of
        # repeatedly scanning and shifting a growing list.
        self._by_location: Dict[str, Dict[str, None]] = {}
        self._counts_by_payload: Dict[str, int] = {}
        self._counts_by_location_payload: Dict[str, Dict[str, int]] = {}
        self._known_payload_names = set()
        # Registry of every physical payload instance that has existed during
        # the simulation.  _records only contains currently stored instances,
        # so reports need this registry to distinguish asset population from
        # task count or movement count.
        self._known_instances: Dict[str, PayloadInstanceRecord] = {}
        # Exact payload reservations are owned by task id.  This prevents two
        # generated tasks from binding to the same shared physical container and
        # allows a failed/deferred task to release only its own reservation.
        self._reservations: Dict[str, str] = {}
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
        self._known_payload_names.add(payload_name)
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
            self._decrement_location_payload_count(previous.location, previous.payload)

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
        self._by_location.setdefault(location_name, {})[instance_id] = None
        self._counts_by_payload[payload_name] = (
            int(self._counts_by_payload.get(payload_name, 0) or 0) + 1
        )
        location_counts = self._counts_by_location_payload.setdefault(location_name, {})
        location_counts[payload_name] = (
            int(location_counts.get(payload_name, 0) or 0) + 1
        )

    def _remove_from_location(self, location_name: str, instance_id: str) -> None:
        ids = self._by_location.get(location_name)
        if ids is None:
            return
        ids.pop(instance_id, None)
        if not ids:
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

    def _decrement_location_payload_count(
        self, location_name: str, payload_name: str
    ) -> None:
        location_name = clean_text(location_name)
        payload_name = normalise_payload_name(payload_name)
        counts = self._counts_by_location_payload.get(location_name)
        if not counts or not payload_name:
            return
        count = int(counts.get(payload_name, 0) or 0) - 1
        if count > 0:
            counts[payload_name] = count
        else:
            counts.pop(payload_name, None)
        if not counts:
            self._counts_by_location_payload.pop(location_name, None)

    def reservation_owner(self, instance_id: str) -> str:
        """Return the task id currently reserving a physical payload instance."""
        return clean_text(self._reservations.get(clean_text(instance_id), ""))

    def is_reserved(self, instance_id: str, excluding_owner: str = "") -> bool:
        """Return True when an instance is reserved by a different task."""
        owner = self.reservation_owner(instance_id)
        excluding_owner = clean_text(excluding_owner)
        return bool(owner and owner != excluding_owner)

    def reserve_instance(self, instance_id: str, task_id: str) -> bool:
        """Atomically reserve an existing payload instance for one task."""
        instance_id = clean_text(instance_id)
        task_id = clean_text(task_id)
        if not instance_id or not task_id or instance_id not in self._records:
            return False
        owner = self.reservation_owner(instance_id)
        if owner and owner != task_id:
            return False
        self._reservations[instance_id] = task_id
        return True

    def release_reservation(self, instance_id: str, task_id: str = "") -> bool:
        """Release a reservation, optionally only when it belongs to task_id."""
        instance_id = clean_text(instance_id)
        task_id = clean_text(task_id)
        owner = self.reservation_owner(instance_id)
        if not owner:
            return False
        if task_id and owner != task_id:
            return False
        self._reservations.pop(instance_id, None)
        return True

    def pickup(
        self,
        location_name: str,
        payload_name: str = "",
        instance_id: str = "",
        reservation_owner: str = "",
    ) -> Optional[PayloadInstanceRecord]:
        location_name = clean_text(location_name)
        payload_name = normalise_payload_name(payload_name)
        instance_id = clean_text(instance_id)
        reservation_owner = clean_text(reservation_owner)

        if instance_id:
            if self.is_reserved(instance_id, excluding_owner=reservation_owner):
                return None
            record = self._records.get(instance_id)
            if not record or record.location != location_name:
                return None
            if payload_name and record.payload != payload_name:
                return None
            self._remove_from_location(location_name, instance_id)
            self._records.pop(instance_id, None)
            self._reservations.pop(instance_id, None)
            self._decrement_payload_count(record.payload)
            self._decrement_location_payload_count(location_name, record.payload)
            record.status = "picked_up"
            return record

        for candidate_id in tuple(self._by_location.get(location_name, {})):
            if self.is_reserved(candidate_id, excluding_owner=reservation_owner):
                continue
            record = self._records.get(candidate_id)
            if not record:
                continue
            if payload_name and record.payload != payload_name:
                continue
            self._remove_from_location(location_name, candidate_id)
            self._records.pop(candidate_id, None)
            self._reservations.pop(candidate_id, None)
            self._decrement_payload_count(record.payload)
            self._decrement_location_payload_count(location_name, record.payload)
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
            for i in self._by_location.get(clean_text(location_name), {})
            if i in self._records
        ]

    def counts_by_payload(self) -> Dict[str, int]:
        return dict(self._counts_by_payload)

    def counts_at(self, location_name: str) -> Dict[str, int]:
        """Return current payload counts at one location without materialising records."""
        return dict(self._counts_by_location_payload.get(clean_text(location_name), {}))

    def known_payload_names(self) -> set:
        """Return payload types that have existed during the simulation."""
        return set(self._known_payload_names)

    def known_records(self) -> List[PayloadInstanceRecord]:
        """Return every physical payload instance observed during runtime."""
        return list(self._known_instances.values())
