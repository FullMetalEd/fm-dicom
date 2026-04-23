"""Dialog to select destination for moving studies/series/instances."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QDialogButtonBox,
    QWidget,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


class MoveItemDialog(QDialog):
    """Simple dialog that allows the user to pick a destination node."""

    def __init__(self, parent, source_level: str, count: int, options: list[dict]):
        super().__init__(parent)
        self.setWindowTitle(f"Move {source_level.title()} (x{count}) To...")
        self.resize(550, 450)
        self._selected_path = None
        self._options = options

        layout = QVBoxLayout(self)

        layout.addWidget(
            QLabel(
                f"Moving {count} {source_level}(s).\n"
                "Select the destination and use the search box to filter."
            )
        )

        self.search_box = QLineEdit(self)
        self.search_box.setPlaceholderText("Search destinations...")
        layout.addWidget(self.search_box)

        self.list_widget = QListWidget(self)
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        # Use a taller row for extra info
        self.list_widget.setSpacing(2)
        layout.addWidget(self.list_widget)

        for option in options:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, option["path"])
            
            # Use search text in a simplified hidden label for filtering
            search_content = f"{option['label']} {option.get('patient_name', '')} {option.get('patient_id', '')} {option.get('accession', '')}"
            item.setText(search_content) # Still used for filter logic but will be obscured by widget
            
            # Create custom widget for the row
            row_widget = QWidget()
            row_layout = QVBoxLayout(row_widget)
            row_layout.setContentsMargins(10, 5, 10, 5)
            row_layout.setSpacing(1)
            
            title_label = QLabel(option["label"])
            title_font = QFont()
            title_font.setBold(True)
            title_label.setFont(title_font)
            row_layout.addWidget(title_label)
            
            metadata = self._format_metadata(option)
            if metadata:
                meta_label = QLabel(metadata)
                meta_label.setStyleSheet("color: #888; font-size: 11px;")
                row_layout.addWidget(meta_label)
            
            item.setSizeHint(row_widget.sizeHint())
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, row_widget)

        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        layout.addWidget(self.buttons)

        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(self.list_widget.count() > 0)

        self.search_box.textChanged.connect(self._apply_filter)
        self.list_widget.currentItemChanged.connect(self._on_selection_changed)

    def _format_metadata(self, option: dict) -> str:
        """Helper to create a rich metadata string based on level."""
        level = option.get("level")
        parts = []
        
        if level == "patient":
            if option.get("patient_id"): parts.append(f"ID: {option['patient_id']}")
            if option.get("patient_dob"): parts.append(f"DOB: {option['patient_dob']}")
            
        elif level == "study":
            if option.get("patient_name"): parts.append(f"Name: {option['patient_name']}")
            if option.get("patient_id"): parts.append(f"ID: {option['patient_id']}")
            if option.get("study_date"): parts.append(f"Date: {option['study_date']}")
            if option.get("accession"): parts.append(f"Acc: {option['accession']}")
            
        elif level == "series":
            if option.get("patient_name"): parts.append(f"Name: {option['patient_name']}")
            if option.get("study_date"): parts.append(f"Date: {option['study_date']}")
            if option.get("series_desc"): parts.append(f"Series: {option['series_desc']}")

        return " | ".join(parts)

    def _apply_filter(self, text: str):
        text = text.lower()
        for index in range(self.list_widget.count()):
            item = self.list_widget.item(index)
            # The item.text() contains the combined search string we set earlier
            item.setHidden(text not in item.text().lower())

        # Ensure something visible is selected
        for index in range(self.list_widget.count()):
            item = self.list_widget.item(index)
            if not item.isHidden():
                self.list_widget.setCurrentItem(item)
                break

    def _on_selection_changed(self, current, _previous):
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(current is not None)

    def get_selected_path(self):
        item = self.list_widget.currentItem()
        if not item:
            return None
        return tuple(item.data(Qt.ItemDataRole.UserRole))
