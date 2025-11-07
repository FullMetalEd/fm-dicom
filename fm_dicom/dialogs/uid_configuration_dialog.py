"""
UID Configuration Dialog

This dialog allows users to configure how DICOM UIDs should be handled
during duplication operations.
"""

import logging
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QCheckBox, QRadioButton, QButtonGroup,
    QPushButton, QGroupBox, QTextEdit, QFrame,
    QSpacerItem, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from fm_dicom.managers.duplication_manager import UIDConfiguration, UIDHandlingMode


class UIDConfigurationDialog(QDialog):
    """Dialog for configuring UID handling during DICOM duplication"""

    configuration_accepted = pyqtSignal(object)  # UIDConfiguration

    def __init__(self, parent=None, duplication_level: str = "mixed"):
        super().__init__(parent)
        self.duplication_level = duplication_level
        self.uid_config = UIDConfiguration()

        self.setWindowTitle("Configure UID Handling for Duplication")
        self.setModal(True)
        self.setMinimumWidth(700)
        self.setMinimumHeight(800)
        self.resize(700, 800)  # Force initial size

        self._setup_ui()
        self._connect_signals()
        self._update_ui_from_config()

        # Set smart copy as default after UI initialization
        self._set_default_preset()

    def _setup_ui(self):
        """Setup the user interface"""
        layout = QVBoxLayout(self)

        # Header
        header_label = QLabel("Configure UID Handling for DICOM Duplication")
        header_font = QFont()
        header_font.setPointSize(12)
        header_font.setBold(True)
        header_label.setFont(header_font)
        header_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header_label)

        # Context information
        context_label = QLabel(f"Duplication Level: {self.duplication_level.title()}")
        context_label.setStyleSheet("color: #666; font-style: italic;")
        context_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(context_label)

        layout.addItem(QSpacerItem(0, 10, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed))

        # Quick presets section
        self._setup_presets_section(layout)

        # Custom configuration section
        self._setup_custom_config_section(layout)

        # Advanced options
        self._setup_advanced_options(layout)

        # Help text
        self._setup_help_section(layout)

        # Buttons
        self._setup_buttons(layout)

    def _setup_presets_section(self, layout):
        """Setup the quick presets section"""
        presets_group = QGroupBox("Quick Presets")
        presets_layout = QVBoxLayout(presets_group)

        self.preset_group = QButtonGroup(self)

        # Define presets
        presets = [
            ("keep_all", "Keep All Original UIDs",
             "Maintain all relationships - use when copying for reference"),
            ("regenerate_all", "Generate All New UIDs",
             "Create completely independent copies - use for new patients"),
            ("regenerate_instance_only", "New Instance UIDs Only",
             "Keep study/series relationships - use for duplicate instances"),
            ("smart_copy", "Smart Copy (Recommended)",
             "Generate new instance UIDs, keep series relationships when appropriate")
        ]

        smart_copy_button = None
        for idx, (preset_id, title, description) in enumerate(presets):
            radio = QRadioButton(title)
            radio.setProperty("preset_id", preset_id)
            if preset_id == "smart_copy":  # Default to smart copy (recommended)
                radio.setChecked(True)
                smart_copy_button = radio
            self.preset_group.addButton(radio, idx)
            presets_layout.addWidget(radio)

            # Description label
            desc_label = QLabel(f"  └ {description}")
            desc_label.setStyleSheet("color: #666; font-size: 9pt; margin-left: 20px;")
            presets_layout.addWidget(desc_label)

        layout.addWidget(presets_group)

        # Store the smart copy button for later use
        self._smart_copy_button = smart_copy_button

    def _setup_custom_config_section(self, layout):
        """Setup the custom configuration section"""
        self.custom_group = QGroupBox("Custom Configuration")
        custom_layout = QGridLayout(self.custom_group)

        # Create checkboxes for each UID type
        self.patient_id_cb = QCheckBox("Generate New Patient ID")
        self.study_uid_cb = QCheckBox("Generate New Study Instance UID")
        self.series_uid_cb = QCheckBox("Generate New Series Instance UID")
        self.instance_uid_cb = QCheckBox("Generate New SOP Instance UID")

        # Add explanatory text for each
        uid_explanations = [
            ("Patient ID", "Changes the patient identifier - creates a new patient"),
            ("Study UID", "Changes the study identifier - creates a new study"),
            ("Series UID", "Changes the series identifier - creates a new series"),
            ("Instance UID", "Changes the instance identifier - creates a new instance")
        ]

        checkboxes = [
            self.patient_id_cb, self.study_uid_cb,
            self.series_uid_cb, self.instance_uid_cb
        ]

        for idx, (checkbox, (name, explanation)) in enumerate(zip(checkboxes, uid_explanations)):
            custom_layout.addWidget(checkbox, idx, 0)

            explanation_label = QLabel(explanation)
            explanation_label.setStyleSheet("color: #666; font-size: 9pt;")
            custom_layout.addWidget(explanation_label, idx, 1)

        # Initially disabled - enabled when "Custom" is selected
        self.custom_group.setEnabled(False)
        layout.addWidget(self.custom_group)

    def _setup_advanced_options(self, layout):
        """Setup advanced options section"""
        advanced_group = QGroupBox("Advanced Options")
        advanced_layout = QVBoxLayout(advanced_group)

        self.preserve_relationships_cb = QCheckBox("Preserve Parent-Child Relationships")
        self.preserve_relationships_cb.setChecked(True)
        self.preserve_relationships_cb.setToolTip(
            "Ensure that duplicated instances maintain proper relationships "
            "with their parent study/series when UIDs are regenerated"
        )
        advanced_layout.addWidget(self.preserve_relationships_cb)

        self.add_suffix_cb = QCheckBox("Add '_COPY' Suffix to Descriptions")
        self.add_suffix_cb.setToolTip(
            "Add '_COPY' suffix to Study Description, Series Description, "
            "and other text fields to clearly identify duplicated data"
        )
        advanced_layout.addWidget(self.add_suffix_cb)

        layout.addWidget(advanced_group)

    def _setup_help_section(self, layout):
        """Setup help text section"""
        help_group = QGroupBox("What This Means")
        help_layout = QVBoxLayout(help_group)

        help_text = QTextEdit()
        help_text.setReadOnly(True)
        help_text.setMaximumHeight(120)
        help_text.setHtml("""
        <p><b>Patient ID:</b> Unique identifier for the patient. Change this to create a new patient record.</p>
        <p><b>Study UID:</b> Identifies a study (imaging session). Change this to create a separate study.</p>
        <p><b>Series UID:</b> Identifies a series within a study. Change this to create a new series.</p>
        <p><b>Instance UID:</b> Identifies individual DICOM objects. Usually changed for all duplicates.</p>
        <br>
        <p><i>Use case example:</i> To duplicate a dose report from one CT study to another,
        keep the Patient ID but generate new Study and Series UIDs.</p>
        """)
        help_layout.addWidget(help_text)

        layout.addWidget(help_group)

    def _setup_buttons(self, layout):
        """Setup dialog buttons"""
        button_layout = QHBoxLayout()

        # Add stretch to push buttons to the right
        button_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)

        self.ok_btn = QPushButton("Apply Configuration")
        self.ok_btn.clicked.connect(self.accept)
        self.ok_btn.setDefault(True)
        button_layout.addWidget(self.ok_btn)

        layout.addLayout(button_layout)

    def _connect_signals(self):
        """Connect UI signals"""
        # Preset radio button changes
        self.preset_group.buttonClicked.connect(self._on_preset_changed)

        # Custom checkboxes
        for checkbox in [self.patient_id_cb, self.study_uid_cb,
                        self.series_uid_cb, self.instance_uid_cb]:
            checkbox.toggled.connect(self._on_custom_config_changed)

        # Advanced options
        self.preserve_relationships_cb.toggled.connect(self._update_config)
        self.add_suffix_cb.toggled.connect(self._update_config)

    def _on_preset_changed(self, button):
        """Handle preset selection changes"""
        preset_id = button.property("preset_id")

        if preset_id == "keep_all":
            self._set_custom_checkboxes(False, False, False, False)
            self.custom_group.setEnabled(False)

        elif preset_id == "regenerate_all":
            self._set_custom_checkboxes(True, True, True, True)
            self.custom_group.setEnabled(False)

        elif preset_id == "regenerate_instance_only":
            self._set_custom_checkboxes(False, False, False, True)
            self.custom_group.setEnabled(False)

        elif preset_id == "smart_copy":
            # Smart logic based on duplication level
            if self.duplication_level == "patient":
                self._set_custom_checkboxes(True, True, True, True)
            elif self.duplication_level == "study":
                self._set_custom_checkboxes(False, True, True, True)
            elif self.duplication_level == "series":
                self._set_custom_checkboxes(False, False, True, True)
            else:  # instance or mixed
                self._set_custom_checkboxes(False, False, False, True)
            self.custom_group.setEnabled(False)

        self._update_config()

    def _set_custom_checkboxes(self, patient: bool, study: bool, series: bool, instance: bool):
        """Set the state of custom checkboxes"""
        self.patient_id_cb.setChecked(patient)
        self.study_uid_cb.setChecked(study)
        self.series_uid_cb.setChecked(series)
        self.instance_uid_cb.setChecked(instance)

    def _on_custom_config_changed(self):
        """Handle custom configuration changes"""
        # Enable custom group when any checkbox changes
        self.custom_group.setEnabled(True)

        # Clear preset selection
        if self.preset_group.checkedButton():
            self.preset_group.setExclusive(False)
            self.preset_group.checkedButton().setChecked(False)
            self.preset_group.setExclusive(True)

        self._update_config()

    def _update_config(self):
        """Update the internal configuration based on UI state"""
        self.uid_config.regenerate_patient_id = self.patient_id_cb.isChecked()
        self.uid_config.regenerate_study_uid = self.study_uid_cb.isChecked()
        self.uid_config.regenerate_series_uid = self.series_uid_cb.isChecked()
        self.uid_config.regenerate_instance_uid = self.instance_uid_cb.isChecked()

        self.uid_config.preserve_relationships = self.preserve_relationships_cb.isChecked()
        self.uid_config.add_derived_suffix = self.add_suffix_cb.isChecked()

    def _update_ui_from_config(self):
        """Update UI elements based on current configuration"""
        self.patient_id_cb.setChecked(self.uid_config.regenerate_patient_id)
        self.study_uid_cb.setChecked(self.uid_config.regenerate_study_uid)
        self.series_uid_cb.setChecked(self.uid_config.regenerate_series_uid)
        self.instance_uid_cb.setChecked(self.uid_config.regenerate_instance_uid)

        self.preserve_relationships_cb.setChecked(self.uid_config.preserve_relationships)
        self.add_suffix_cb.setChecked(self.uid_config.add_derived_suffix)

    def _set_default_preset(self):
        """Set smart copy as the default preset after UI initialization"""
        if hasattr(self, '_smart_copy_button') and self._smart_copy_button:
            # Ensure it's checked
            self._smart_copy_button.setChecked(True)
            # Apply the preset configuration explicitly
            self._on_preset_changed(self._smart_copy_button)
            logging.debug("Applied smart copy as default preset")

    def get_configuration(self) -> UIDConfiguration:
        """Get the current UID configuration"""
        self._update_config()
        return self.uid_config

    def set_configuration(self, config: UIDConfiguration):
        """Set the UID configuration"""
        self.uid_config = config
        self._update_ui_from_config()

    def accept(self):
        """Handle dialog acceptance"""
        try:
            # Validate configuration
            config = self.get_configuration()

            # Emit configuration
            self.configuration_accepted.emit(config)

            logging.info(f"UID configuration accepted: {config}")
            super().accept()

        except Exception as e:
            logging.error(f"Failed to accept UID configuration: {e}")

    @staticmethod
    def get_uid_configuration(parent=None,
                             duplication_level: str = "mixed") -> Optional[UIDConfiguration]:
        """
        Static method to show the dialog and return configuration

        Args:
            parent: Parent widget
            duplication_level: Level of duplication (patient/study/series/instance/mixed)

        Returns:
            UIDConfiguration if accepted, None if cancelled
        """
        dialog = UIDConfigurationDialog(parent, duplication_level)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.get_configuration()

        return None