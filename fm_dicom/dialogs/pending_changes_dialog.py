from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QHBoxLayout,
    QPushButton,
)
from PyQt6.QtCore import Qt


class PendingChangesDialog(QDialog):
    def __init__(
        self,
        parent,
        staging_manager,
        commit_callback,
        discard_callback,
        commit_entry_callback,
        discard_entry_callback,
    ):
        super().__init__(parent)
        self.setWindowTitle("Pending Changes")
        self.setMinimumSize(960, 520)
        self.staging_manager = staging_manager
        self.commit_callback = commit_callback
        self.discard_callback = discard_callback
        self.commit_entry_callback = commit_entry_callback
        self.discard_entry_callback = discard_entry_callback
        self._entry_map = {}

        layout = QVBoxLayout(self)
        self.table = QTableWidget(self)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)

        button_row = QHBoxLayout()
        self.commit_btn = QPushButton("Commit All", self)
        self.discard_btn = QPushButton("Discard All", self)
        self.close_btn = QPushButton("Close", self)
        button_row.addWidget(self.commit_btn)
        button_row.addWidget(self.discard_btn)
        button_row.addStretch()
        button_row.addWidget(self.close_btn)
        layout.addLayout(button_row)

        self.commit_btn.clicked.connect(self._commit_all)
        self.discard_btn.clicked.connect(self._discard_all)
        self.close_btn.clicked.connect(self.accept)

        self._populate()

    def _populate(self):
        entries = self.staging_manager.to_dict()
        self._entry_map = {entry["entry_id"]: entry for entry in entries}

        headers = ["Scope", "Tag", "Description", "Old Value", "New Value", "Commit", "Discard"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(entries))

        for row, entry in enumerate(entries):
            scope_text = f"{entry.get('level', '')}: {entry.get('scope_display', '')}"
            tag_text = entry.get("tag_id", "")
            desc_text = entry.get("tag_description", "")
            old_value = entry.get("old_value", "")
            new_value = entry.get("new_value", "")

            scope_item = QTableWidgetItem(scope_text)
            tag_item = QTableWidgetItem(tag_text)
            desc_item = QTableWidgetItem(desc_text)
            old_item = QTableWidgetItem(str(old_value))
            new_item = QTableWidgetItem(str(new_value))

            for col, item in enumerate([scope_item, tag_item, desc_item, old_item, new_item]):
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
                self.table.setItem(row, col, item)

            commit_button = QPushButton("Commit", self)
            commit_button.clicked.connect(lambda _, entry_id=entry["entry_id"]: self._commit_entry(entry_id))
            self.table.setCellWidget(row, 5, commit_button)

            discard_button = QPushButton("Discard", self)
            discard_button.clicked.connect(lambda _, entry_id=entry["entry_id"]: self._discard_entry(entry_id))
            self.table.setCellWidget(row, 6, discard_button)

        self.table.resizeColumnsToContents()
        has_entries = bool(entries)
        self.commit_btn.setEnabled(has_entries)
        self.discard_btn.setEnabled(has_entries)

    def _commit_all(self):
        self.commit_callback()
        self._populate()

    def _discard_all(self):
        self.discard_callback()
        self._populate()

    def _commit_entry(self, entry_id: str):
        entry = self._entry_map.get(entry_id)
        if not entry:
            return
        self.commit_entry_callback(entry)
        self._populate()

    def _discard_entry(self, entry_id: str):
        entry = self._entry_map.get(entry_id)
        if not entry:
            return
        self.discard_entry_callback(entry)
        self._populate()
