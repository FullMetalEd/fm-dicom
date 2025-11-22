"""Audit log manager for tracking tag changes and metadata edits."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import List, Dict, Any


@dataclass
class AuditEntry:
    timestamp: str
    action: str
    level: str
    file_path: str
    patient_label: str
    study_description: str
    series_description: str
    tag_id: str
    tag_description: str
    old_value: str
    new_value: str


class AuditLogManager:
    """Stores audit entries for the current session and supports export."""

    def __init__(self):
        self._entries: List[AuditEntry] = []

    def add_entry(self, **kwargs):
        entry = AuditEntry(
            timestamp=datetime.utcnow().isoformat(timespec="seconds"),
            action=kwargs.get("action", "edit"),
            level=kwargs.get("level", "instance"),
            file_path=kwargs.get("file_path", ""),
            patient_label=kwargs.get("patient_label", ""),
            study_description=kwargs.get("study_description", ""),
            series_description=kwargs.get("series_description", ""),
            tag_id=kwargs.get("tag_id", ""),
            tag_description=kwargs.get("tag_description", ""),
            old_value=kwargs.get("old_value", ""),
            new_value=kwargs.get("new_value", ""),
        )
        self._entries.append(entry)

    def get_entries(self) -> List[Dict[str, Any]]:
        return [asdict(entry) for entry in self._entries]

    def clear(self):
        self._entries.clear()

    def export_csv(self, path: str):
        entries = self.get_entries()
        if not entries:
            return
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=entries[0].keys())
            writer.writeheader()
            writer.writerows(entries)

    def export_json(self, path: str):
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.get_entries(), fh, indent=2)
