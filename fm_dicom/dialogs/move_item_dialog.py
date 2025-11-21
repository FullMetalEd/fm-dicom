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
)
from PyQt6.QtCore import Qt


class MoveItemDialog(QDialog):
    """Simple dialog that allows the user to pick a destination node."""

    def __init__(self, parent, source_level: str, options: list[dict]):
        super().__init__(parent)
        self.setWindowTitle(f"Move {source_level.title()} To...")
        self._selected_path = None
        self._options = options

        layout = QVBoxLayout(self)

        layout.addWidget(
            QLabel(
                "Select the destination where the item should be placed.\n"
                "Use the search box to filter the list."
            )
        )

        self.search_box = QLineEdit(self)
        self.search_box.setPlaceholderText("Search destinations...")
        layout.addWidget(self.search_box)

        self.list_widget = QListWidget(self)
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        layout.addWidget(self.list_widget)

        for option in options:
            item = QListWidgetItem(option["label"])
            item.setData(Qt.ItemDataRole.UserRole, option["path"])
            self.list_widget.addItem(item)

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

    def _apply_filter(self, text: str):
        text = text.lower()
        for index in range(self.list_widget.count()):
            item = self.list_widget.item(index)
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
