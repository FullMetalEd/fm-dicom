"""Staged changes manager for multi-node editing."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, Iterable, List, Optional, Tuple

ScopeKey = Tuple[str, Tuple[str, ...]]  # (level, node_path)


@dataclass
class StagedChange:
    level: str
    node_path: Tuple[str, ...]
    tag_id: str
    tag_tuple: Tuple[int, int]
    tag_description: str
    old_value: str
    new_value: str
    vr: str
    source_file: Optional[str] = None

    @property
    def scope_key(self) -> ScopeKey:
        return (self.level, tuple(self.node_path))

    def to_dict(self) -> dict:
        data = asdict(self)
        data["node_path"] = list(self.node_path)
        data["scope_display"] = " → ".join(self.node_path)
        data["entry_id"] = self._entry_id()
        return data

    def _entry_id(self) -> str:
        return f"{self.level}|{'/'.join(self.node_path)}|{self.tag_id}"


class StagingManager:
    """Keeps track of staged tag edits grouped by scope (level + node path)."""

    def __init__(self):
        # scope_key -> tag_id -> StagedChange
        self._changes: Dict[ScopeKey, Dict[str, StagedChange]] = {}

    def stage_change(
        self,
        *,
        level: str,
        node_path: Tuple[str, ...],
        tag_id: str,
        tag_tuple: Tuple[int, int],
        tag_description: str,
        old_value: str,
        new_value: str,
        vr: str,
        source_file: Optional[str] = None,
    ):
        """Stage a change for the given scope.

        Empty or reverted values automatically clear the staged entry.
        """
        scope_key = self._make_scope_key(level, node_path)
        scope_changes = self._changes.setdefault(scope_key, {})

        old_val_norm = (old_value or "").strip()
        new_val_norm = (new_value or "").strip()

        if new_val_norm == old_val_norm:
            # Reverted to baseline - remove staged entry
            scope_changes.pop(tag_id, None)
            if not scope_changes:
                self._changes.pop(scope_key, None)
            return

        scope_changes[tag_id] = StagedChange(
            level=level,
            node_path=tuple(node_path),
            tag_id=tag_id,
            tag_tuple=tag_tuple,
            tag_description=tag_description,
            old_value=old_value,
            new_value=new_value,
            vr=vr,
            source_file=source_file,
        )

    def remove_change(self, level: str, node_path: Tuple[str, ...], tag_id: str):
        scope_key = self._make_scope_key(level, node_path)
        scope_changes = self._changes.get(scope_key)
        if not scope_changes:
            return
        scope_changes.pop(tag_id, None)
        if not scope_changes:
            self._changes.pop(scope_key, None)

    def get_change(self, level: str, node_path: Tuple[str, ...], tag_id: str) -> Optional[StagedChange]:
        scope_key = self._make_scope_key(level, node_path)
        scope_changes = self._changes.get(scope_key, {})
        return scope_changes.get(tag_id)

    def get_scope_changes(self, level: str, node_path: Tuple[str, ...]) -> Dict[str, StagedChange]:
        scope_key = self._make_scope_key(level, node_path)
        return self._changes.get(scope_key, {}).copy()

    def has_scope_changes(self, level: str, node_path: Tuple[str, ...]) -> bool:
        scope_key = self._make_scope_key(level, node_path)
        return bool(self._changes.get(scope_key))

    def pop_scope(self, level: str, node_path: Tuple[str, ...]) -> Dict[str, StagedChange]:
        scope_key = self._make_scope_key(level, node_path)
        return self._changes.pop(scope_key, {}).copy()

    def iter_scopes(self) -> Iterable[Tuple[ScopeKey, Dict[str, StagedChange]]]:
        for scope_key, changes in self._changes.items():
            yield scope_key, changes

    def iter_changes(self) -> Iterable[Tuple[str, Tuple[str, ...], StagedChange]]:
        for (level, node_path), tag_map in self._changes.items():
            for change in tag_map.values():
                yield level, node_path, change

    def get_changes_for_path(self, path_tuple: Tuple[str, ...]) -> List[Tuple[str, Tuple[str, ...], Dict[str, StagedChange]]]:
        """Return scopes whose node_path covers the provided file hierarchy."""
        matches: List[Tuple[str, Tuple[str, ...], Dict[str, StagedChange]]] = []
        if not path_tuple:
            return matches
        file_path = tuple(path_tuple)
        for (level, node_path), tag_map in self._changes.items():
            if self._path_matches(node_path, file_path):
                matches.append((level, node_path, tag_map))
        return matches

    def has_changes(self) -> bool:
        return any(self._changes.values())

    def clear_all(self):
        self._changes.clear()

    def to_dict(self) -> List[dict]:
        return [change.to_dict() for _, _, change in self.iter_changes()]

    def all_entries(self) -> List[Tuple[str, Tuple[str, ...], StagedChange]]:
        return list(self.iter_changes())

    @staticmethod
    def _make_scope_key(level: str, node_path: Tuple[str, ...]) -> ScopeKey:
        return (level, tuple(node_path or ()))

    @staticmethod
    def _path_matches(node_path: Tuple[str, ...], file_path: Tuple[str, ...]) -> bool:
        if not node_path:
            return False
        if len(file_path) < len(node_path):
            return False
        return tuple(file_path[: len(node_path)]) == tuple(node_path)
