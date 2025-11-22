from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QHBoxLayout,
    QPushButton,
    QFileDialog,
)


class AuditLogDialog(QDialog):
    """Displays audit log entries with export/clear actions."""

    def __init__(self, parent, audit_manager):
        super().__init__(parent)
        self.setWindowTitle("Audit Log")
        self.audit_manager = audit_manager

        layout = QVBoxLayout(self)
        self.table = QTableWidget(self)
        layout.addWidget(self.table)

        button_row = QHBoxLayout()
        self.export_csv_btn = QPushButton("Export CSV", self)
        self.export_json_btn = QPushButton("Export JSON", self)
        self.clear_btn = QPushButton("Clear", self)
        self.close_btn = QPushButton("Close", self)
        button_row.addWidget(self.export_csv_btn)
        button_row.addWidget(self.export_json_btn)
        button_row.addWidget(self.clear_btn)
        button_row.addStretch()
        button_row.addWidget(self.close_btn)
        layout.addLayout(button_row)

        self.export_csv_btn.clicked.connect(self._export_csv)
        self.export_json_btn.clicked.connect(self._export_json)
        self.clear_btn.clicked.connect(self._clear)
        self.close_btn.clicked.connect(self.accept)

        self._populate()

    def _populate(self):
        entries = self.audit_manager.get_entries()
        headers = [
            "timestamp",
            "action",
            "level",
            "file_path",
            "patient_label",
            "study_description",
            "series_description",
            "tag_id",
            "tag_description",
            "old_value",
            "new_value",
        ]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels([h.replace("_", " ").title() for h in headers])
        self.table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            for col, key in enumerate(headers):
                item = QTableWidgetItem(str(entry.get(key, "")))
                item.setFlags(item.flags() ^ item.flags() & ~item.flags())
                self.table.setItem(row, col, item)
        self.table.resizeColumnsToContents()

    def _export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Audit CSV", "audit_log.csv", "CSV Files (*.csv)")
        if path:
            self.audit_manager.export_csv(path)

    def _export_json(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Audit JSON", "audit_log.json", "JSON Files (*.json)")
        if path:
            self.audit_manager.export_json(path)

    def _clear(self):
        self.audit_manager.clear()
        self._populate()
