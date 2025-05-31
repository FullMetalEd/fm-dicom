"""
DICOM Anonymization User Interface
Provides dialogs for template selection, editing, and batch anonymization.
"""

import os
import logging
from typing import List, Optional
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QTreeWidget, QTreeWidgetItem,
    QTextEdit, QTabWidget, QWidget, QLabel, QProgressDialog, QApplication,
    QHeaderView, QGroupBox, QGridLayout, QLineEdit, QComboBox, QCheckBox,
    QFileDialog, QMessageBox, QSplitter, QFrame, QSpinBox, QTableWidget,
    QTableWidgetItem, QFormLayout, QDialogButtonBox, QListWidget, QListWidgetItem,
    QTextBrowser, QScrollArea
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QIcon, QFont, QColor, QPixmap
import pydicom
from datetime import datetime

# Import ALL needed classes from anonymization module
from .anonymization import (
    AnonymizationTemplate, 
    AnonymizationRule, 
    AnonymizationAction,
    AnonymizationEngine, 
    TemplateManager, 
    AnonymizationResult,
    DateShifter,  # This was missing!
    UIDMapper    # Also add this for completeness
)

class AnonymizationWorker(QThread):
    """Worker thread for anonymization without blocking UI"""
    progress_updated = pyqtSignal(int, str)  # progress, current_file
    anonymization_complete = pyqtSignal(object)  # AnonymizationResult
    
    def __init__(self, template, file_paths):
        super().__init__()
        self.template = template
        self.file_paths = file_paths
        self.engine = AnonymizationEngine()
        self.current_index = 0
        
    def run(self):
        try:
            # Override the engine's file processing to emit progress
            original_anonymize_file = self.engine._anonymize_file
            
            def progress_anonymize_file(file_path, template, result):
                self.current_index += 1
                self.progress_updated.emit(self.current_index, file_path)
                
                # Allow thread to be interrupted
                if self.isInterruptionRequested():
                    return
                    
                return original_anonymize_file(file_path, template, result)
            
            # Replace the method temporarily
            self.engine._anonymize_file = progress_anonymize_file
            
            # Use the original engine method
            result = self.engine.anonymize_collection(self.template, self.file_paths)
            self.anonymization_complete.emit(result)
            
        except Exception as e:
            logging.error(f"Anonymization worker error: {e}", exc_info=True)
            # Create error result
            result = AnonymizationResult()
            result.add_failure("General", f"Anonymization failed: {str(e)}")
            self.anonymization_complete.emit(result)

class AnonymizationProgressDialog(QProgressDialog):
    """Progress dialog for anonymization operations"""
    
    def __init__(self, template, file_paths, parent=None):
        super().__init__("Initializing anonymization...", "Cancel", 0, len(file_paths), parent)
        self.setWindowTitle("DICOM Anonymization")
        self.setMinimumDuration(0)
        self.setAutoClose(False)
        self.setAutoReset(False)
        
        self.template = template
        self.file_paths = file_paths
        self.result = None
        
        # Start anonymization in worker thread
        self.worker = AnonymizationWorker(template, file_paths)
        self.worker.progress_updated.connect(self.update_progress)
        self.worker.anonymization_complete.connect(self.anonymization_finished)
        self.worker.start()
        
        # Cancel handling
        self.canceled.connect(self.cancel_anonymization)
        
    def update_progress(self, progress, current_file):
        self.setValue(progress)
        self.setLabelText(f"Anonymizing: {os.path.basename(current_file)}")
        QApplication.processEvents()
        
    def anonymization_finished(self, result):
        self.result = result
        self.setValue(len(self.file_paths))
        self.setLabelText("Anonymization complete")
        self.accept()
        
    def cancel_anonymization(self):
        if self.worker.isRunning():
            self.worker.requestInterruption()  # Use requestInterruption instead of terminate
            self.worker.wait(3000)  # Wait up to 3 seconds for graceful shutdown
            if self.worker.isRunning():
                self.worker.terminate()  # Force terminate if needed
                self.worker.wait()
        self.reject()

class TemplateSelectionDialog(QDialog):
    """Dialog for selecting an anonymization template"""
    
    def __init__(self, template_manager: TemplateManager, parent=None):
        super().__init__(parent)
        self.template_manager = template_manager
        self.selected_template = None
        
        self.setWindowTitle("Select Anonymization Template")
        self.setModal(True)
        self.resize(800, 600)
        
        self.setup_ui()
        self.populate_templates()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Template list and preview
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)
        
        # Left side: Template list
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        
        left_layout.addWidget(QLabel("Available Templates:"))
        
        self.template_list = QListWidget()
        self.template_list.itemSelectionChanged.connect(self.on_template_selected)
        left_layout.addWidget(self.template_list)
        
        # Template management buttons
        template_buttons = QHBoxLayout()
        
        new_btn = QPushButton("New Template")
        new_btn.clicked.connect(self.create_new_template)
        template_buttons.addWidget(new_btn)
        
        edit_btn = QPushButton("Edit Template")
        edit_btn.clicked.connect(self.edit_template)
        template_buttons.addWidget(edit_btn)
        
        delete_btn = QPushButton("Delete Template")
        delete_btn.clicked.connect(self.delete_template)
        template_buttons.addWidget(delete_btn)
        
        template_buttons.addStretch()
        left_layout.addLayout(template_buttons)
        
        splitter.addWidget(left_widget)
        
        # Right side: Template preview
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        
        right_layout.addWidget(QLabel("Template Details:"))
        
        self.template_preview = QTextBrowser()
        right_layout.addWidget(self.template_preview)
        
        splitter.addWidget(right_widget)
        
        # Dialog buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | 
                                 QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
        # Set initial button states
        buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        self.ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        
    def populate_templates(self):
        """Populate the template list"""
        self.template_list.clear()
        
        for template_name in self.template_manager.get_template_names():
            item = QListWidgetItem(template_name)
            self.template_list.addItem(item)
            
    def on_template_selected(self):
        """Handle template selection"""
        current_item = self.template_list.currentItem()
        if current_item:
            template_name = current_item.text()
            template = self.template_manager.get_template(template_name)
            
            if template:
                self.selected_template = template
                self.show_template_preview(template)
                self.ok_button.setEnabled(True)
            else:
                self.selected_template = None
                self.ok_button.setEnabled(False)
        else:
            self.selected_template = None
            self.ok_button.setEnabled(False)
            
    def show_template_preview(self, template: AnonymizationTemplate):
        """Show template details in preview area"""
        html = f"""
<h2>{template.name}</h2>
<p><strong>Description:</strong> {template.description}</p>
<p><strong>Version:</strong> {template.version}</p>
<p><strong>Created:</strong> {template.created_date.strftime('%Y-%m-%d %H:%M')}</p>
<p><strong>Modified:</strong> {template.modified_date.strftime('%Y-%m-%d %H:%M')}</p>

<h3>Settings:</h3>
<ul>
<li><strong>Date Shift:</strong> {template.date_shift_days if template.date_shift_days else 'None'} days</li>
<li><strong>Preserve Relationships:</strong> {'Yes' if template.preserve_relationships else 'No'}</li>
<li><strong>Remove Private Tags:</strong> {'Yes' if template.remove_private_tags else 'No'}</li>
<li><strong>Remove Curves:</strong> {'Yes' if template.remove_curves else 'No'}</li>
<li><strong>Remove Overlays:</strong> {'Yes' if template.remove_overlays else 'No'}</li>
</ul>

<h3>Anonymization Rules ({len(template.rules)}):</h3>
<table border="1" cellpadding="3" cellspacing="0" style="border-collapse: collapse;">
<tr style="background-color: #f0f0f0;">
<th>Tag</th><th>Action</th><th>Replacement</th><th>Description</th>
</tr>
"""
        
        for rule in template.rules:
            replacement = rule.replacement_value if rule.replacement_value else '-'
            description = rule.description if rule.description else '-'
            html += f"""
<tr>
<td>{rule.tag}</td>
<td>{rule.action}</td>
<td>{replacement}</td>
<td>{description}</td>
</tr>
"""
        
        html += "</table>"
        self.template_preview.setHtml(html)
        
    def create_new_template(self):
        """Create a new template"""
        editor = TemplateEditorDialog(None, self.template_manager, self)
        if editor.exec() == QDialog.DialogCode.Accepted:
            self.populate_templates()
            
    def edit_template(self):
        """Edit the selected template"""
        if self.selected_template:
            editor = TemplateEditorDialog(self.selected_template, self.template_manager, self)
            if editor.exec() == QDialog.DialogCode.Accepted:
                self.populate_templates()
                self.on_template_selected()  # Refresh preview
                
    def delete_template(self):
        """Delete the selected template"""
        if self.selected_template:
            reply = QMessageBox.question(
                self, "Delete Template",
                f"Are you sure you want to delete the template '{self.selected_template.name}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.template_manager.remove_template(self.selected_template.name)
                self.populate_templates()
                self.template_preview.clear()
                self.selected_template = None
                self.ok_button.setEnabled(False)

class TemplateEditorDialog(QDialog):
    """Dialog for creating/editing anonymization templates"""
    
    def __init__(self, template: AnonymizationTemplate, template_manager: TemplateManager, parent=None):
        super().__init__(parent)
        self.template = template
        self.template_manager = template_manager
        self.is_editing = template is not None
        
        if self.is_editing:
            self.setWindowTitle(f"Edit Template: {template.name}")
            # Create a copy to edit
            self.working_template = AnonymizationTemplate.from_dict(template.to_dict())
        else:
            self.setWindowTitle("Create New Template")
            self.working_template = AnonymizationTemplate("New Template")
            
        self.setModal(True)
        self.resize(900, 700)
        
        self.setup_ui()
        self.populate_fields()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Template info section
        info_group = QGroupBox("Template Information")
        info_layout = QFormLayout(info_group)
        
        self.name_edit = QLineEdit()
        info_layout.addRow("Name:", self.name_edit)
        
        self.description_edit = QTextEdit()
        self.description_edit.setMaximumHeight(80)
        info_layout.addRow("Description:", self.description_edit)
        
        self.version_edit = QLineEdit()
        info_layout.addRow("Version:", self.version_edit)
        
        layout.addWidget(info_group)
        
        # Settings section
        settings_group = QGroupBox("Anonymization Settings")
        settings_layout = QFormLayout(settings_group)
        
        # Date shift
        date_layout = QHBoxLayout()
        self.date_shift_enabled = QCheckBox("Enable date shifting")
        self.date_shift_enabled.toggled.connect(self.on_date_shift_toggled)
        date_layout.addWidget(self.date_shift_enabled)
        
        self.date_shift_days = QSpinBox()
        self.date_shift_days.setRange(-3650, 3650)  # +/- 10 years
        self.date_shift_days.setSuffix(" days")
        self.date_shift_days.setEnabled(False)
        date_layout.addWidget(self.date_shift_days)
        
        date_layout.addStretch()
        settings_layout.addRow("Date Shifting:", date_layout)
        
        self.preserve_relationships = QCheckBox("Preserve study/series relationships")
        settings_layout.addRow("", self.preserve_relationships)
        
        self.remove_private_tags = QCheckBox("Remove private tags")
        settings_layout.addRow("", self.remove_private_tags)
        
        self.remove_curves = QCheckBox("Remove curve data")
        settings_layout.addRow("", self.remove_curves)
        
        self.remove_overlays = QCheckBox("Remove overlay data")
        settings_layout.addRow("", self.remove_overlays)
        
        layout.addWidget(settings_group)
        
        # Rules section
        rules_group = QGroupBox("Anonymization Rules")
        rules_layout = QVBoxLayout(rules_group)
        
        # Rules toolbar
        rules_toolbar = QHBoxLayout()
        
        add_rule_btn = QPushButton("Add Rule")
        add_rule_btn.clicked.connect(self.add_rule)
        rules_toolbar.addWidget(add_rule_btn)
        
        edit_rule_btn = QPushButton("Edit Rule")
        edit_rule_btn.clicked.connect(self.edit_rule)
        rules_toolbar.addWidget(edit_rule_btn)
        
        remove_rule_btn = QPushButton("Remove Rule")
        remove_rule_btn.clicked.connect(self.remove_rule)
        rules_toolbar.addWidget(remove_rule_btn)
        
        rules_toolbar.addStretch()
        
        load_preset_btn = QPushButton("Load Preset Rules")
        load_preset_btn.clicked.connect(self.load_preset_rules)
        rules_toolbar.addWidget(load_preset_btn)
        
        rules_layout.addLayout(rules_toolbar)
        
        # Rules table
        self.rules_table = QTableWidget()
        self.rules_table.setColumnCount(4)
        self.rules_table.setHorizontalHeaderLabels(["Tag", "Action", "Replacement", "Description"])
        self.rules_table.horizontalHeader().setStretchLastSection(True)
        self.rules_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.rules_table.itemDoubleClicked.connect(self.edit_rule)
        rules_layout.addWidget(self.rules_table)
        
        layout.addWidget(rules_group)
        
        # Dialog buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | 
                                 QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save_template)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
    def populate_fields(self):
        """Populate fields with template data"""
        self.name_edit.setText(self.working_template.name)
        self.description_edit.setPlainText(self.working_template.description)
        self.version_edit.setText(self.working_template.version)
        
        # Settings
        if self.working_template.date_shift_days is not None:
            self.date_shift_enabled.setChecked(True)
            self.date_shift_days.setValue(self.working_template.date_shift_days)
            self.date_shift_days.setEnabled(True)
        else:
            self.date_shift_enabled.setChecked(False)
            self.date_shift_days.setEnabled(False)
            
        self.preserve_relationships.setChecked(self.working_template.preserve_relationships)
        self.remove_private_tags.setChecked(self.working_template.remove_private_tags)
        self.remove_curves.setChecked(self.working_template.remove_curves)
        self.remove_overlays.setChecked(self.working_template.remove_overlays)
        
        # Rules
        self.populate_rules_table()
        
    def populate_rules_table(self):
        """Populate the rules table"""
        self.rules_table.setRowCount(len(self.working_template.rules))
        
        for row, rule in enumerate(self.working_template.rules):
            self.rules_table.setItem(row, 0, QTableWidgetItem(rule.tag))
            self.rules_table.setItem(row, 1, QTableWidgetItem(rule.action))
            self.rules_table.setItem(row, 2, QTableWidgetItem(rule.replacement_value))
            self.rules_table.setItem(row, 3, QTableWidgetItem(rule.description))
            
    def on_date_shift_toggled(self, checked):
        """Handle date shift checkbox toggle"""
        self.date_shift_days.setEnabled(checked)
        
    def add_rule(self):
        """Add a new anonymization rule"""
        dialog = RuleEditorDialog(None, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.working_template.add_rule(dialog.rule)
            self.populate_rules_table()
            
    def edit_rule(self):
        """Edit the selected rule"""
        current_row = self.rules_table.currentRow()
        if current_row >= 0 and current_row < len(self.working_template.rules):
            rule = self.working_template.rules[current_row]
            dialog = RuleEditorDialog(rule, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.working_template.rules[current_row] = dialog.rule
                self.populate_rules_table()
                
    def remove_rule(self):
        """Remove the selected rule"""
        current_row = self.rules_table.currentRow()
        if current_row >= 0 and current_row < len(self.working_template.rules):
            del self.working_template.rules[current_row]
            self.populate_rules_table()
            
    def load_preset_rules(self):
        """Load preset rules for common tags"""
        preset_dialog = PresetRulesDialog(self)
        if preset_dialog.exec() == QDialog.DialogCode.Accepted:
            for rule in preset_dialog.selected_rules:
                self.working_template.add_rule(rule)
            self.populate_rules_table()
            
    def save_template(self):
        """Save the template"""
        # Validate input
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Invalid Input", "Template name is required.")
            return
            
        # Check for duplicate names (except when editing same template)
        if not self.is_editing or name != self.template.name:
            if name in self.template_manager.get_template_names():
                QMessageBox.warning(self, "Duplicate Name", 
                                  f"A template named '{name}' already exists.")
                return
                
        # Update template
        self.working_template.name = name
        self.working_template.description = self.description_edit.toPlainText()
        self.working_template.version = self.version_edit.text()
        
        # Settings
        if self.date_shift_enabled.isChecked():
            self.working_template.date_shift_days = self.date_shift_days.value()
        else:
            self.working_template.date_shift_days = None
            
        self.working_template.preserve_relationships = self.preserve_relationships.isChecked()
        self.working_template.remove_private_tags = self.remove_private_tags.isChecked()
        self.working_template.remove_curves = self.remove_curves.isChecked()
        self.working_template.remove_overlays = self.remove_overlays.isChecked()
        
        # Save to template manager
        if self.is_editing:
            # Remove old template if name changed
            if name != self.template.name:
                self.template_manager.remove_template(self.template.name)
                
        self.template_manager.add_template(self.working_template)
        
        self.accept()

class RuleEditorDialog(QDialog):
    """Dialog for editing a single anonymization rule"""
    
    def __init__(self, rule: AnonymizationRule, parent=None):
        super().__init__(parent)
        self.rule = rule
        self.is_editing = rule is not None
        
        if self.is_editing:
            self.setWindowTitle("Edit Anonymization Rule")
        else:
            self.setWindowTitle("Add Anonymization Rule")
            
        self.setModal(True)
        self.resize(500, 300)
        
        self.setup_ui()
        if self.is_editing:
            self.populate_fields()
            
    def setup_ui(self):
        layout = QFormLayout(self)
        
        # Tag selection
        tag_layout = QHBoxLayout()
        
        self.tag_edit = QLineEdit()
        self.tag_edit.setPlaceholderText("e.g., PatientName or (0010,0010)")
        tag_layout.addWidget(self.tag_edit)
        
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self.browse_tags)
        tag_layout.addWidget(browse_btn)
        
        layout.addRow("Tag:", tag_layout)
        
        # Action
        self.action_combo = QComboBox()
        self.action_combo.addItems([
            AnonymizationAction.REMOVE,
            AnonymizationAction.BLANK,
            AnonymizationAction.REPLACE,
            AnonymizationAction.HASH,
            AnonymizationAction.KEEP,
            AnonymizationAction.DATE_SHIFT,
            AnonymizationAction.UID_REMAP
        ])
        self.action_combo.currentTextChanged.connect(self.on_action_changed)
        layout.addRow("Action:", self.action_combo)
        
        # Replacement value
        self.replacement_edit = QLineEdit()
        self.replacement_label = QLabel("Replacement Value:")
        layout.addRow(self.replacement_label, self.replacement_edit)
        
        # Description
        self.description_edit = QLineEdit()
        layout.addRow("Description:", self.description_edit)
        
        # Action description
        self.action_description = QLabel()
        self.action_description.setWordWrap(True)
        self.action_description.setStyleSheet("color: gray; font-style: italic;")
        layout.addRow("", self.action_description)
        
        # Update action description
        self.on_action_changed()
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | 
                                 QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept_rule)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
    def populate_fields(self):
        """Populate fields with rule data"""
        self.tag_edit.setText(self.rule.tag)
        
        # Set action
        index = self.action_combo.findText(self.rule.action)
        if index >= 0:
            self.action_combo.setCurrentIndex(index)
            
        self.replacement_edit.setText(self.rule.replacement_value)
        self.description_edit.setText(self.rule.description)
        
    def on_action_changed(self):
        """Update UI based on selected action"""
        action = self.action_combo.currentText()
        
        # Show/hide replacement field based on action
        needs_replacement = action in [AnonymizationAction.REPLACE]
        self.replacement_edit.setVisible(needs_replacement)
        self.replacement_label.setVisible(needs_replacement)
        
        # Update description
        descriptions = {
            AnonymizationAction.REMOVE: "Completely remove this tag from the DICOM file",
            AnonymizationAction.BLANK: "Set tag to empty/default value appropriate for its VR",
            AnonymizationAction.REPLACE: "Replace tag value with specified replacement text",
            AnonymizationAction.HASH: "Replace tag value with SHA256 hash of original value",
            AnonymizationAction.KEEP: "Keep tag value unchanged",
            AnonymizationAction.DATE_SHIFT: "Shift date/time by specified number of days",
            AnonymizationAction.UID_REMAP: "Replace UID with new UID while preserving relationships"
        }
        
        self.action_description.setText(descriptions.get(action, ""))
        
    def browse_tags(self):
        """Open tag browser dialog"""
        browser = TagBrowserDialog(self)
        if browser.exec() == QDialog.DialogCode.Accepted and browser.selected_tag:
            self.tag_edit.setText(browser.selected_tag)
            
    def accept_rule(self):
        """Validate and accept the rule"""
        tag = self.tag_edit.text().strip()
        if not tag:
            QMessageBox.warning(self, "Invalid Input", "Tag is required.")
            return
            
        action = self.action_combo.currentText()
        replacement = self.replacement_edit.text()
        description = self.description_edit.text()
        
        # Create rule
        self.rule = AnonymizationRule(tag, action, replacement, description)
        
        self.accept()

class TagBrowserDialog(QDialog):
    """Dialog for browsing and selecting DICOM tags"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected_tag = None
        
        self.setWindowTitle("Browse DICOM Tags")
        self.setModal(True)
        self.resize(600, 500)
        
        self.setup_ui()
        self.populate_tags()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Search
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Search:"))
        
        self.search_edit = QLineEdit()
        self.search_edit.textChanged.connect(self.filter_tags)
        search_layout.addWidget(self.search_edit)
        
        layout.addLayout(search_layout)
        
        # Tags table
        self.tags_table = QTableWidget()
        self.tags_table.setColumnCount(3)
        self.tags_table.setHorizontalHeaderLabels(["Tag", "Keyword", "Name"])
        self.tags_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tags_table.itemDoubleClicked.connect(self.accept_selection)
        layout.addWidget(self.tags_table)
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | 
                                 QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept_selection)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
    def populate_tags(self):
        """Populate tags table with common DICOM tags"""
        # Common tags for anonymization
        common_tags = [
            ("(0010,0010)", "PatientName", "Patient's Name"),
            ("(0010,0020)", "PatientID", "Patient ID"),
            ("(0010,0030)", "PatientBirthDate", "Patient's Birth Date"),
            ("(0010,0040)", "PatientSex", "Patient's Sex"),
            ("(0010,1010)", "PatientAge", "Patient's Age"),
            ("(0010,1030)", "PatientWeight", "Patient's Weight"),
            ("(0008,0020)", "StudyDate", "Study Date"),
            ("(0008,0030)", "StudyTime", "Study Time"),
            ("(0008,1030)", "StudyDescription", "Study Description"),
            ("(0008,0021)", "SeriesDate", "Series Date"),
            ("(0008,0031)", "SeriesTime", "Series Time"),
            ("(0008,103E)", "SeriesDescription", "Series Description"),
            ("(0008,0060)", "Modality", "Modality"),
            ("(0020,000D)", "StudyInstanceUID", "Study Instance UID"),
            ("(0020,000E)", "SeriesInstanceUID", "Series Instance UID"),
            ("(0008,0018)", "SOPInstanceUID", "SOP Instance UID"),
            ("(0008,0090)", "ReferringPhysicianName", "Referring Physician's Name"),
            ("(0008,1050)", "PerformingPhysicianName", "Performing Physician's Name"),
            ("(0008,1070)", "OperatorsName", "Operators' Name"),
            ("(0008,0080)", "InstitutionName", "Institution Name"),
            ("(0008,1010)", "StationName", "Station Name"),
        ]
        
        self.all_tags = common_tags
        self.filter_tags("")
        
    def filter_tags(self, text=""):
        """Filter tags based on search text"""
        text = text.lower()
        
        filtered_tags = []
        for tag, keyword, name in self.all_tags:
            if (text in tag.lower() or 
                text in keyword.lower() or 
                text in name.lower()):
                filtered_tags.append((tag, keyword, name))
                
        # Populate table
        self.tags_table.setRowCount(len(filtered_tags))
        
        for row, (tag, keyword, name) in enumerate(filtered_tags):
            self.tags_table.setItem(row, 0, QTableWidgetItem(tag))
            self.tags_table.setItem(row, 1, QTableWidgetItem(keyword))
            self.tags_table.setItem(row, 2, QTableWidgetItem(name))
            
        # Resize columns
        self.tags_table.resizeColumnsToContents()
        
    def accept_selection(self):
        """Accept the selected tag"""
        current_row = self.tags_table.currentRow()
        if current_row >= 0:
            keyword_item = self.tags_table.item(current_row, 1)
            if keyword_item:
                self.selected_tag = keyword_item.text()
                self.accept()

class PresetRulesDialog(QDialog):
    """Dialog for selecting preset anonymization rules"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected_rules = []
        
        self.setWindowTitle("Select Preset Rules")
        self.setModal(True)
        self.resize(700, 500)
        
        self.setup_ui()
        self.populate_presets()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        layout.addWidget(QLabel("Select preset rule groups to add:"))
        
        # Preset categories
        self.preset_list = QListWidget()
        self.preset_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        layout.addWidget(self.preset_list)
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | 
                                 QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept_selection)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
    def populate_presets(self):
        """Populate preset categories"""
        presets = [
            "Patient Identification",
            "Physician Information", 
            "Institution Information",
            "Study Information",
            "Series Information",
            "Equipment Information",
            "Private Tags"
        ]
        
        for preset in presets:
            self.preset_list.addItem(preset)
            
    def accept_selection(self):
        """Generate rules based on selected presets"""
        self.selected_rules = []
        
        selected_items = self.preset_list.selectedItems()
        
        for item in selected_items:
            preset_name = item.text()
            rules = self.get_preset_rules(preset_name)
            self.selected_rules.extend(rules)
            
        self.accept()
        
    def get_preset_rules(self, preset_name: str) -> List[AnonymizationRule]:
        """Get rules for a preset category"""
        presets = {
            "Patient Identification": [
                ("PatientName", AnonymizationAction.HASH),
                ("PatientID", AnonymizationAction.HASH),
                ("PatientBirthDate", AnonymizationAction.BLANK),
                ("OtherPatientNames", AnonymizationAction.REMOVE),
                ("OtherPatientIDs", AnonymizationAction.REMOVE),
                ("PatientBirthTime", AnonymizationAction.REMOVE),
                ("PatientComments", AnonymizationAction.REMOVE),
            ],
            "Physician Information": [
                ("ReferringPhysicianName", AnonymizationAction.REMOVE),
                ("PerformingPhysicianName", AnonymizationAction.REMOVE),
                ("OperatorsName", AnonymizationAction.REMOVE),
                ("PhysiciansOfRecord", AnonymizationAction.REMOVE),
            ],
            "Institution Information": [
                ("InstitutionName", AnonymizationAction.REMOVE),
                ("InstitutionAddress", AnonymizationAction.REMOVE),
                ("InstitutionalDepartmentName", AnonymizationAction.REMOVE),
                ("StationName", AnonymizationAction.REMOVE),
            ],
            "Study Information": [
                ("StudyDate", AnonymizationAction.DATE_SHIFT),
                ("StudyInstanceUID", AnonymizationAction.UID_REMAP),
                ("AccessionNumber", AnonymizationAction.HASH),
            ],
            "Series Information": [
                ("SeriesDate", AnonymizationAction.DATE_SHIFT),
                ("SeriesInstanceUID", AnonymizationAction.UID_REMAP),
            ],
            "Equipment Information": [
                ("Manufacturer", AnonymizationAction.KEEP),
                ("ManufacturerModelName", AnonymizationAction.KEEP),
                ("DeviceSerialNumber", AnonymizationAction.REMOVE),
                ("SoftwareVersions", AnonymizationAction.REMOVE),
            ]
        }
        
        rules = []
        for tag, action in presets.get(preset_name, []):
            rule = AnonymizationRule(tag, action, description=f"From {preset_name} preset")
            rules.append(rule)
            
        return rules

class AnonymizationResultsDialog(QDialog):
    """Dialog showing anonymization results"""
    
    def __init__(self, result: AnonymizationResult, parent=None):
        super().__init__(parent)
        self.result = result
        
        self.setWindowTitle("Anonymization Results")
        self.setModal(True)
        self.resize(700, 500)
        
        self.setup_ui()
        self.populate_results()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Summary
        summary = self.result.get_summary()
        summary_text = f"""
<h2>Anonymization Complete</h2>
<p><strong>Total Files:</strong> {summary['total_files']}</p>
<p><strong>Successfully Anonymized:</strong> {summary['anonymized_count']}</p>
<p><strong>Failed:</strong> {summary['failed_count']}</p>
<p><strong>Skipped:</strong> {summary['skipped_count']}</p>
<p><strong>Success Rate:</strong> {summary['success_rate']:.1f}%</p>
"""
        
        if summary['duration_seconds']:
            summary_text += f"<p><strong>Duration:</strong> {summary['duration_seconds']:.1f} seconds</p>"
            
        summary_label = QTextBrowser()
        summary_label.setMaximumHeight(150)
        summary_label.setHtml(summary_text)
        layout.addWidget(summary_label)
        
        # Failed files (if any)
        if self.result.failed_files:
            layout.addWidget(QLabel("Failed/Skipped Files:"))
            
            self.failed_table = QTableWidget()
            self.failed_table.setColumnCount(2)
            self.failed_table.setHorizontalHeaderLabels(["File", "Error"])
            layout.addWidget(self.failed_table)
            
        # Buttons
        button_layout = QHBoxLayout()
        
        if self.result.failed_files:
            export_btn = QPushButton("Export Error Report")
            export_btn.clicked.connect(self.export_errors)
            button_layout.addWidget(export_btn)
            
        button_layout.addStretch()
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        close_btn.setDefault(True)
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
        
    def populate_results(self):
        """Populate the results display"""
        if hasattr(self, 'failed_table') and self.result.failed_files:
            self.failed_table.setRowCount(len(self.result.failed_files))
            
            for row, (file_path, error) in enumerate(self.result.failed_files.items()):
                self.failed_table.setItem(row, 0, QTableWidgetItem(os.path.basename(file_path)))
                self.failed_table.setItem(row, 1, QTableWidgetItem(error))
                
            self.failed_table.resizeColumnsToContents()
            
    def export_errors(self):
        """Export error report"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Error Report",
            f"anonymization_errors_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            "Text Files (*.txt)"
        )
        
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write("Anonymization Error Report\n")
                    f.write("=" * 50 + "\n\n")
                    
                    summary = self.result.get_summary()
                    f.write(f"Total Files: {summary['total_files']}\n")
                    f.write(f"Failed: {summary['failed_count']}\n")
                    f.write(f"Skipped: {summary['skipped_count']}\n\n")
                    
                    f.write("Detailed Errors:\n")
                    f.write("-" * 30 + "\n")
                    
                    for file_path, error in self.result.failed_files.items():
                        f.write(f"File: {file_path}\n")
                        f.write(f"Error: {error}\n\n")
                        
                QMessageBox.information(self, "Export Complete",
                                      f"Error report exported to:\n{file_path}")
                                      
            except Exception as e:
                QMessageBox.critical(self, "Export Error",
                                   f"Failed to export error report:\n{str(e)}")

def run_anonymization(file_paths, template_manager, parent=None):
    """Convenience function to run anonymization with template selection"""
    if not file_paths:
        QMessageBox.warning(parent, "No Files", "No files selected for anonymization.")
        return None
        
    # Select template
    template_dialog = TemplateSelectionDialog(template_manager, parent)
    if template_dialog.exec() != QDialog.DialogCode.Accepted:
        return None
        
    template = template_dialog.selected_template
    if not template:
        return None
        
    # Confirm anonymization
    reply = QMessageBox.question(
        parent, "Confirm Anonymization",
        f"This will anonymize {len(file_paths)} files using template '{template.name}'.\n"
        "This operation modifies files in-place and cannot be undone.\n\n"
        "Are you sure you want to continue?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No
    )
    
    if reply != QMessageBox.StandardButton.Yes:
        return None
        
    # Run anonymization with progress
    progress_dialog = AnonymizationProgressDialog(template, file_paths, parent)
    
    if progress_dialog.exec() == QDialog.DialogCode.Accepted:
        result = progress_dialog.result
        if result:
            # Show results
            results_dialog = AnonymizationResultsDialog(result, parent)
            results_dialog.exec()
            return result
            
    return None