from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QRadioButton, QButtonGroup, 
    QDialogButtonBox, QFormLayout, QComboBox, QLineEdit
)
from fm_dicom.widgets.focus_aware import FocusAwareMessageBox


class PrimarySelectionDialog(QDialog):
    def __init__(self, parent, items, item_type):
        super().__init__(parent)
        self.setWindowTitle(f"Select Primary {item_type}")
        self.setModal(True)
        
        layout = QVBoxLayout(self)
        
        label = QLabel(f"Select which {item_type.lower()} to use as primary (whose metadata will be kept):")
        layout.addWidget(label)
        
        self.button_group = QButtonGroup()
        self.radio_buttons = []
        
        for i, item in enumerate(items):
            radio = QRadioButton(item.text(0))  # Display the tree item text
            if i == 0:  # Default to first
                radio.setChecked(True)
            self.button_group.addButton(radio, i)
            self.radio_buttons.append(radio)
            layout.addWidget(radio)
        
        # OK/Cancel buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
    def get_selected_index(self):
        """Return the index of the selected primary item"""
        return self.button_group.checkedId()


class DicomSendDialog(QDialog):
    """DICOM Send configuration dialog"""
    
    def __init__(self, parent=None, config=None):
        super().__init__(parent)
        self.setWindowTitle("DICOM Send")
        layout = QFormLayout(self)

        self.destinations = config.get("destinations", []) if config else []
        self.dest_combo = QComboBox()
        self.dest_combo.addItem("Manual Entry")
        for dest in self.destinations:
            label = dest.get("label") or f"{dest.get('ae_title','')}@{dest.get('host','')}:{dest.get('port','')}"
            self.dest_combo.addItem(label)
        self.dest_combo.currentIndexChanged.connect(self._on_dest_changed)
        layout.addRow("Destination:", self.dest_combo)

        default_ae = config.get("ae_title", "DCMSCU") if config else "DCMSCU"
        self.ae_title = QLineEdit(default_ae)
        self.ae_title.setToolTip(
            "Calling AE Title: This is the Application Entity Title your system presents to the remote DICOM server. "
            "It identifies your workstation or application to the remote PACS. "
            "If unsure, use a unique name or the default."
        )
        self.remote_ae = QLineEdit("DCMRCVR")
        self.host = QLineEdit("127.0.0.1")
        self.port = QLineEdit("104")
        layout.addRow("Calling AE Title:", self.ae_title)
        layout.addRow("Remote AE Title:", self.remote_ae)
        layout.addRow("Remote Host:", self.host)
        layout.addRow("Remote Port:", self.port)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        # Initialize fields based on current selection if destinations exist
        if self.destinations:
            self._on_dest_changed(self.dest_combo.currentIndex())

    def _on_dest_changed(self, idx):
        config_ae_default = "DCMSCU"  # Fallback if not in config
        if hasattr(self, 'parentWidget') and hasattr(self.parentWidget(), 'config'):  # Access main window config
             config_ae_default = self.parentWidget().config.get("ae_title", "DCMSCU")

        if idx == 0 or not self.destinations:  # Manual entry selected or no destinations defined
            # Set to defaults or clear for manual entry
            self.remote_ae.setText("DCMRCVR")  # Or some other default
            self.host.setText("127.0.0.1")
            self.port.setText("104")
            self.ae_title.setText(config_ae_default)  # Use global default calling AE
            return
        
        # idx-1 because "Manual Entry" is at index 0
        dest = self.destinations[idx-1] 
        self.remote_ae.setText(str(dest.get("ae_title", "DCMRCVR")))
        self.host.setText(str(dest.get("host", "127.0.0.1")))
        self.port.setText(str(dest.get("port", "104")))
        # Use destination-specific calling AE if provided, else global default
        self.ae_title.setText(str(dest.get("calling_ae_title", config_ae_default)))

    def get_params(self):
        try:
            port_val = int(self.port.text().strip())
            if not (0 < port_val < 65536):
                raise ValueError("Port out of range")
        except ValueError:
            FocusAwareMessageBox.critical(self, "Invalid Port", "Port must be a number between 1 and 65535.")
            return None  # Indicate error
        
        return (
            self.ae_title.text().strip(),
            self.remote_ae.text().strip(),
            self.host.text().strip(),
            port_val  # Already int
        )


class SplitItemDialog(QDialog):
    """Dialog to capture metadata for a newly split container."""

    def __init__(self, parent, target_level: str, initial_values: dict = None):
        super().__init__(parent)
        self.setWindowTitle(f"Split to New {target_level.title()}")
        self.target_level = target_level
        initial_values = initial_values or {}

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.fields = {}

        if target_level == "patient":
            self.fields["patient_name"] = QLineEdit(initial_values.get("patient_name", ""))
            self.fields["patient_name"].setPlaceholderText("New Patient Name")
            self.fields["patient_id"] = QLineEdit(initial_values.get("patient_id", ""))
            self.fields["patient_id"].setPlaceholderText("New Patient ID")
            form.addRow("Patient Name:", self.fields["patient_name"])
            form.addRow("Patient ID:", self.fields["patient_id"])

        elif target_level == "study":
            self.fields["study_desc"] = QLineEdit(initial_values.get("study_desc", "New Study"))
            self.fields["accession"] = QLineEdit(initial_values.get("accession", ""))
            form.addRow("Study Description:", self.fields["study_desc"])
            form.addRow("Accession Number:", self.fields["accession"])

        elif target_level == "series":
            self.fields["series_desc"] = QLineEdit(initial_values.get("series_desc", "New Series"))
            self.fields["modality"] = QLineEdit(initial_values.get("modality", ""))
            form.addRow("Series Description:", self.fields["series_desc"])
            form.addRow("Modality:", self.fields["modality"])

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_values(self) -> dict:
        """Return the user-provided values."""
        return {k: v.text().strip() for k, v in self.fields.items()}
