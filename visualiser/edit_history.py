"""Bounded configuration snapshots and completed-operation adapters for the editor."""
from functools import wraps
import hashlib
import json
import zlib


class EditHistory:
    def __init__(self, config, max_steps=100, max_bytes=32 * 1024 * 1024):
        self.max_steps = max(1, max_steps)
        self.max_bytes = max(1, max_bytes)
        self.reset(config)

    @staticmethod
    def snapshot(config, label):
        raw = json.dumps(config, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return {"label": label, "hash": hashlib.sha256(raw).hexdigest(), "data": zlib.compress(raw)}

    @staticmethod
    def unpack(entry):
        return json.loads(zlib.decompress(entry["data"]))

    def reset(self, config):
        self.entries = [self.snapshot(config, "Opened configuration")]
        self.position = 0
        self.trimmed = False

    def record(self, config, label):
        entry = self.snapshot(config, label)
        if entry["hash"] == self.entries[self.position]["hash"]:
            return False
        self.entries = self.entries[:self.position + 1] + [entry]
        self.position += 1
        self._trim()
        return True

    def _trim(self):
        while len(self.entries) > 1 and (len(self.entries) > self.max_steps + 1 or
                sum(len(e["data"]) for e in self.entries) > self.max_bytes):
            if self.position > 0:
                self.entries.pop(0)
                self.position -= 1
            else:
                self.entries.pop()
            self.trimmed = True

    @property
    def undo_label(self):
        return self.entries[self.position]["label"] if self.position > 0 else None

    @property
    def redo_label(self):
        return self.entries[self.position + 1]["label"] if self.position + 1 < len(self.entries) else None

    def undo(self):
        if self.undo_label is None:
            return None
        self.position -= 1
        return self.unpack(self.entries[self.position])

    def redo(self):
        if self.redo_label is None:
            return None
        self.position += 1
        return self.unpack(self.entries[self.position])

    def remap_drawings(self, mapping):
        """Packaging changes physical paths, not the meaning of earlier edits."""
        if not mapping:
            return
        for index, entry in enumerate(self.entries):
            config = self.unpack(entry)
            for section in ("floor_dxf_files", "floor_pdf_underlays"):
                for drawing in config.get(section, []):
                    path = drawing.get("filepath")
                    if path in mapping:
                        drawing["filepath"] = mapping[path]
            self.entries[index] = self.snapshot(config, entry["label"])
        self._trim()


def undoable(label, *, capture_before=True):
    """Group nested editor callbacks into one completed configuration change."""
    def decorate(method):
        @wraps(method)
        def wrapped(self, *args, **kwargs):
            if not hasattr(self, "edit_history"):
                return method(self, *args, **kwargs)
            outer = self._edit_depth == 0
            if outer and capture_before:
                self._commit_history("Configuration changes")
            self._edit_depth += 1
            try:
                return method(self, *args, **kwargs)
            finally:
                self._edit_depth -= 1
                if outer:
                    self._commit_history(label)
        return wrapped
    return decorate
