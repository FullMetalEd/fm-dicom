"""
DICOM Tag Browser and Search
Provides searchable interface for DICOM tag selection.
"""

import os
import logging
from typing import List, Tuple, Optional
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem,
    QLineEdit, QLabel, QDialogButtonBox, QHeaderView, QFrame, QGroupBox,
    QRadioButton, QButtonGroup, QFormLayout, QMessageBox, QComboBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
import pydicom

class TagSearchDialog(QDialog):
    """Dialog for searching and selecting DICOM tags"""
    
    def __init__(self, parent=None, title="Select DICOM Tag"):
        super().__init__(parent)
        self.selected_tag = None
        self.selected_keyword = None
        self.selected_name = None
        self.selected_vr = None
        
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(800, 600)
        
        self.setup_ui()
        self.populate_tags()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Search section
        search_group = QGroupBox("Search DICOM Tags")
        search_layout = QVBoxLayout(search_group)
        
        # Search input
        search_input_layout = QHBoxLayout()
        search_input_layout.addWidget(QLabel("Search:"))
        
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Type to search by tag name, keyword, or description...")
        self.search_edit.textChanged.connect(self.filter_tags)
        search_input_layout.addWidget(self.search_edit)
        
        search_layout.addLayout(search_input_layout)
        
        # Category filter
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Category:"))
        
        self.category_filter = QComboBox()
        self.category_filter.addItems([
            "All Categories",
            "Patient Information",
            "Study Information", 
            "Series Information",
            "Image Information",
            "Equipment Information",
            "Acquisition Parameters",
            "Private Tags",
            "Common Tags"
        ])
        self.category_filter.currentTextChanged.connect(self.filter_tags)
        filter_layout.addWidget(self.category_filter)
        
        filter_layout.addStretch()
        search_layout.addLayout(filter_layout)
        
        layout.addWidget(search_group)
        
        # Results table
        results_group = QGroupBox("Search Results")
        results_layout = QVBoxLayout(results_group)
        
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(4)
        self.results_table.setHorizontalHeaderLabels(["Tag ID", "Keyword", "Name", "VR"])
        
        # Set column widths
        header = self.results_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # Tag ID
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # Keyword
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)            # Name
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # VR
        
        self.results_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.itemDoubleClicked.connect(self.accept_selection)
        self.results_table.itemSelectionChanged.connect(self.on_selection_changed)
        
        results_layout.addWidget(self.results_table)
        layout.addWidget(results_group)
        
        # Manual entry section
        manual_group = QGroupBox("Manual Entry")
        manual_layout = QFormLayout(manual_group)
        
        self.manual_tag_edit = QLineEdit()
        self.manual_tag_edit.setPlaceholderText("e.g., (0008,0050) or AccessionNumber")
        manual_layout.addRow("Tag:", self.manual_tag_edit)
        
        manual_btn = QPushButton("Use Manual Entry")
        manual_btn.clicked.connect(self.use_manual_entry)
        manual_layout.addRow("", manual_btn)
        
        layout.addWidget(manual_group)
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | 
                                 QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept_selection)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
        self.ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.ok_button.setEnabled(False)
        
    def populate_tags(self):
        """Populate the tag database"""
        # Comprehensive list of common DICOM tags organized by category
        self.tag_database = [
            # Patient Information
            ("(0010,0010)", "PatientName", "Patient's Name", "PN", "Patient Information"),
            ("(0010,0020)", "PatientID", "Patient ID", "LO", "Patient Information"),
            ("(0010,0030)", "PatientBirthDate", "Patient's Birth Date", "DA", "Patient Information"),
            ("(0010,0032)", "PatientBirthTime", "Patient's Birth Time", "TM", "Patient Information"),
            ("(0010,0040)", "PatientSex", "Patient's Sex", "CS", "Patient Information"),
            ("(0010,1010)", "PatientAge", "Patient's Age", "AS", "Patient Information"),
            ("(0010,1020)", "PatientSize", "Patient's Size", "DS", "Patient Information"),
            ("(0010,1030)", "PatientWeight", "Patient's Weight", "DS", "Patient Information"),
            ("(0010,2160)", "EthnicGroup", "Ethnic Group", "SH", "Patient Information"),
            ("(0010,21B0)", "AdditionalPatientHistory", "Additional Patient History", "LT", "Patient Information"),
            ("(0010,4000)", "PatientComments", "Patient Comments", "LT", "Patient Information"),
            
            # Study Information
            ("(0008,0020)", "StudyDate", "Study Date", "DA", "Study Information"),
            ("(0008,0030)", "StudyTime", "Study Time", "TM", "Study Information"),
            ("(0008,0050)", "AccessionNumber", "Accession Number", "SH", "Study Information"),
            ("(0008,0090)", "ReferringPhysicianName", "Referring Physician's Name", "PN", "Study Information"),
            ("(0008,1030)", "StudyDescription", "Study Description", "LO", "Study Information"),
            ("(0008,1032)", "ProcedureCodeSequence", "Procedure Code Sequence", "SQ", "Study Information"),
            ("(0008,1060)", "NameOfPhysiciansReadingStudy", "Name of Physician(s) Reading Study", "PN", "Study Information"),
            ("(0020,000D)", "StudyInstanceUID", "Study Instance UID", "UI", "Study Information"),
            ("(0020,0010)", "StudyID", "Study ID", "SH", "Study Information"),
            ("(0032,1032)", "RequestingPhysician", "Requesting Physician", "PN", "Study Information"),
            ("(0032,1060)", "RequestedProcedureDescription", "Requested Procedure Description", "LO", "Study Information"),
            
            # Series Information
            ("(0008,0021)", "SeriesDate", "Series Date", "DA", "Series Information"),
            ("(0008,0031)", "SeriesTime", "Series Time", "TM", "Series Information"),
            ("(0008,0060)", "Modality", "Modality", "CS", "Series Information"),
            ("(0008,103E)", "SeriesDescription", "Series Description", "LO", "Series Information"),
            ("(0008,1050)", "PerformingPhysicianName", "Performing Physician's Name", "PN", "Series Information"),
            ("(0008,1070)", "OperatorsName", "Operators' Name", "PN", "Series Information"),
            ("(0018,0015)", "BodyPartExamined", "Body Part Examined", "CS", "Series Information"),
            ("(0018,5100)", "PatientPosition", "Patient Position", "CS", "Series Information"),
            ("(0020,000E)", "SeriesInstanceUID", "Series Instance UID", "UI", "Series Information"),
            ("(0020,0011)", "SeriesNumber", "Series Number", "IS", "Series Information"),
            
            # Image Information
            ("(0008,0008)", "ImageType", "Image Type", "CS", "Image Information"),
            ("(0008,0018)", "SOPInstanceUID", "SOP Instance UID", "UI", "Image Information"),
            ("(0008,0023)", "ContentDate", "Content Date", "DA", "Image Information"),
            ("(0008,0033)", "ContentTime", "Content Time", "TM", "Image Information"),
            ("(0020,0013)", "InstanceNumber", "Instance Number", "IS", "Image Information"),
            ("(0020,0032)", "ImagePositionPatient", "Image Position Patient", "DS", "Image Information"),
            ("(0020,0037)", "ImageOrientationPatient", "Image Orientation Patient", "DS", "Image Information"),
            ("(0028,0002)", "SamplesPerPixel", "Samples per Pixel", "US", "Image Information"),
            ("(0028,0004)", "PhotometricInterpretation", "Photometric Interpretation", "CS", "Image Information"),
            ("(0028,0010)", "Rows", "Rows", "US", "Image Information"),
            ("(0028,0011)", "Columns", "Columns", "US", "Image Information"),
            ("(0028,0030)", "PixelSpacing", "Pixel Spacing", "DS", "Image Information"),
            ("(0028,0100)", "BitsAllocated", "Bits Allocated", "US", "Image Information"),
            ("(0028,0101)", "BitsStored", "Bits Stored", "US", "Image Information"),
            ("(0028,0102)", "HighBit", "High Bit", "US", "Image Information"),
            ("(0028,0103)", "PixelRepresentation", "Pixel Representation", "US", "Image Information"),
            ("(0028,1050)", "WindowCenter", "Window Center", "DS", "Image Information"),
            ("(0028,1051)", "WindowWidth", "Window Width", "DS", "Image Information"),
            
            # Equipment Information
            ("(0008,0070)", "Manufacturer", "Manufacturer", "LO", "Equipment Information"),
            ("(0008,0080)", "InstitutionName", "Institution Name", "LO", "Equipment Information"),
            ("(0008,0081)", "InstitutionAddress", "Institution Address", "ST", "Equipment Information"),
            ("(0008,1010)", "StationName", "Station Name", "SH", "Equipment Information"),
            ("(0008,1040)", "InstitutionalDepartmentName", "Institutional Department Name", "LO", "Equipment Information"),
            ("(0008,1090)", "ManufacturerModelName", "Manufacturer's Model Name", "LO", "Equipment Information"),
            ("(0018,1000)", "DeviceSerialNumber", "Device Serial Number", "LO", "Equipment Information"),
            ("(0018,1020)", "SoftwareVersions", "Software Version(s)", "LO", "Equipment Information"),
            
            # Acquisition Parameters
            ("(0018,0050)", "SliceThickness", "Slice Thickness", "DS", "Acquisition Parameters"),
            ("(0018,0060)", "KVP", "KVP", "DS", "Acquisition Parameters"),
            ("(0018,0080)", "RepetitionTime", "Repetition Time", "DS", "Acquisition Parameters"),
            ("(0018,0081)", "EchoTime", "Echo Time", "DS", "Acquisition Parameters"),
            ("(0018,0087)", "MagneticFieldStrength", "Magnetic Field Strength", "DS", "Acquisition Parameters"),
            ("(0018,1030)", "ProtocolName", "Protocol Name", "LO", "Acquisition Parameters"),
            ("(0018,1150)", "ExposureTime", "Exposure Time", "IS", "Acquisition Parameters"),
            ("(0018,1151)", "XRayTubeCurrent", "X-Ray Tube Current", "IS", "Acquisition Parameters"),
            ("(0018,1152)", "Exposure", "Exposure", "IS", "Acquisition Parameters"),
            ("(0018,1160)", "FilterType", "Filter Type", "SH", "Acquisition Parameters"),
            ("(0018,1210)", "ConvolutionKernel", "Convolution Kernel", "SH", "Acquisition Parameters"),
            
            # Common/Frequently Used
            ("(0002,0010)", "TransferSyntaxUID", "Transfer Syntax UID", "UI", "Common Tags"),
            ("(0008,0005)", "SpecificCharacterSet", "Specific Character Set", "CS", "Common Tags"),
            ("(0008,0016)", "SOPClassUID", "SOP Class UID", "UI", "Common Tags"),
            ("(0020,0052)", "FrameOfReferenceUID", "Frame of Reference UID", "UI", "Common Tags"),
            ("(0028,0301)", "BurnedInAnnotation", "Burned In Annotation", "CS", "Common Tags"),
        ]
        
        # Add tags from pydicom dictionary for completeness
        try:
            for tag, (vr, vm, name, is_retired, keyword) in pydicom.datadict.DicomDictionary.items():
                if not is_retired and keyword:  # Only non-retired tags with keywords
                    # Convert tag to proper Tag object if needed
                    if isinstance(tag, int):
                        # Convert integer to Tag
                        tag_obj = pydicom.tag.Tag(tag)
                    elif isinstance(tag, tuple) and len(tag) == 2:
                        # Convert (group, element) tuple to Tag
                        tag_obj = pydicom.tag.Tag(tag[0], tag[1])
                    else:
                        # Assume it's already a Tag object
                        tag_obj = tag
                    
                    tag_str = f"({tag_obj.group:04X},{tag_obj.element:04X})"
                    
                    # Determine category based on group
                    if tag_obj.group == 0x0010:
                        category = "Patient Information"
                    elif tag_obj.group == 0x0008 and tag_obj.element in [0x0020, 0x0030, 0x0050, 0x0090, 0x1030]:
                        category = "Study Information"
                    elif tag_obj.group == 0x0008 and tag_obj.element in [0x0021, 0x0031, 0x0060, 0x103E]:
                        category = "Series Information"
                    elif tag_obj.group == 0x0008:
                        category = "Common Tags"
                    elif tag_obj.group == 0x0018:
                        category = "Acquisition Parameters"
                    elif tag_obj.group == 0x0020:
                        category = "Image Information"
                    elif tag_obj.group == 0x0028:
                        category = "Image Information"
                    else:
                        category = "Other"
                    
                    # Check if already in our manual list
                    existing = any(existing_tag[0] == tag_str for existing_tag in self.tag_database)
                    if not existing:
                        self.tag_database.append((tag_str, keyword, name, vr, category))
                        
        except Exception as e:
            logging.warning(f"Could not load pydicom dictionary: {e}")
            
        # Sort by tag name for better browsing
        self.tag_database.sort(key=lambda x: x[2].lower())  # Sort by name
        
        # Initial population
        self.filter_tags()
        
    def filter_tags(self, search_text=None):
        """Filter tags based on search criteria"""
        if search_text is None:
            search_text = self.search_edit.text()
            
        search_text = search_text.lower().strip()
        category_filter = self.category_filter.currentText()
        
        # Filter tags
        filtered_tags = []
        for tag_id, keyword, name, vr, category in self.tag_database:
            # Category filter
            if category_filter != "All Categories" and category != category_filter:
                continue
                
            # Search filter
            if search_text:
                searchable_text = f"{tag_id} {keyword} {name}".lower()
                if search_text not in searchable_text:
                    continue
                    
            filtered_tags.append((tag_id, keyword, name, vr, category))
            
        # Populate table
        self.results_table.setRowCount(len(filtered_tags))
        
        for row, (tag_id, keyword, name, vr, category) in enumerate(filtered_tags):
            self.results_table.setItem(row, 0, QTableWidgetItem(tag_id))
            self.results_table.setItem(row, 1, QTableWidgetItem(keyword))
            self.results_table.setItem(row, 2, QTableWidgetItem(name))
            self.results_table.setItem(row, 3, QTableWidgetItem(vr))
            
            # Store full data in UserRole for easy access
            self.results_table.item(row, 0).setData(Qt.ItemDataRole.UserRole, 
                                                   (tag_id, keyword, name, vr, category))
                                                   
        # Highlight search terms
        if search_text:
            for row in range(self.results_table.rowCount()):
                for col in range(self.results_table.columnCount()):
                    item = self.results_table.item(row, col)
                    if item and search_text in item.text().lower():
                        font = item.font()
                        font.setBold(True)
                        item.setFont(font)
                        
    def on_selection_changed(self):
        """Handle selection change"""
        current_row = self.results_table.currentRow()
        if current_row >= 0:
            item = self.results_table.item(current_row, 0)
            if item:
                data = item.data(Qt.ItemDataRole.UserRole)
                if data:
                    try:
                        self.selected_tag, self.selected_keyword, self.selected_name, self.selected_vr, _ = data
                        self.ok_button.setEnabled(True)
                        logging.debug(f"Tag selected: {self.selected_tag}")
                    except (ValueError, TypeError) as e:
                        logging.warning(f"Error unpacking tag selection data: {e}, data: {data}")
                        self.selected_tag = None
                        self.selected_keyword = None
                        self.selected_name = None
                        self.selected_vr = None
                        self.ok_button.setEnabled(False)
                else:
                    logging.debug("No UserRole data found for selected item")
                    self.selected_tag = None
                    self.selected_keyword = None  
                    self.selected_name = None
                    self.selected_vr = None
                    self.ok_button.setEnabled(False)
            else:
                logging.debug("No item found at current row")
                self.selected_tag = None
                self.selected_keyword = None
                self.selected_name = None
                self.selected_vr = None
                self.ok_button.setEnabled(False)
        else:
            self.selected_tag = None
            self.selected_keyword = None
            self.selected_name = None
            self.selected_vr = None
            self.ok_button.setEnabled(False)
            
    def use_manual_entry(self):
        """Use manual tag entry"""
        manual_text = self.manual_tag_edit.text().strip()
        if not manual_text:
            QMessageBox.warning(self, "Manual Entry", "Please enter a tag ID or keyword.")
            return
            
        self.selected_tag = manual_text
        self.selected_keyword = manual_text if not manual_text.startswith('(') else None
        self.selected_name = f"Manual entry: {manual_text}"
        self.selected_vr = None
        self.accept()
        
    def accept_selection(self):
        """Accept the current selection"""
        if self.selected_tag:
            self.accept()
        else:
            QMessageBox.warning(self, "No Selection", "Please select a tag or use manual entry.")
            
    def get_selected_tag_info(self):
        """Get information about the selected tag"""
        return {
            'tag': self.selected_tag,
            'keyword': self.selected_keyword,
            'name': self.selected_name,
            'vr': self.selected_vr
        }

class ValueEntryDialog(QDialog):
    """Dialog for entering tag value with VR-specific validation"""
    
    def __init__(self, tag_info, current_value="", parent=None):
        super().__init__(parent)
        self.tag_info = tag_info
        self.current_value = current_value
        self.new_value = ""
        
        self.setWindowTitle(f"Enter Value for {tag_info['name']}")
        self.setModal(True)
        self.resize(500, 300)
        
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Tag information
        info_group = QGroupBox("Tag Information")
        info_layout = QFormLayout(info_group)
        
        info_layout.addRow("Tag ID:", QLabel(self.tag_info['tag']))
        info_layout.addRow("Keyword:", QLabel(self.tag_info['keyword'] or "N/A"))
        info_layout.addRow("Name:", QLabel(self.tag_info['name']))
        info_layout.addRow("VR:", QLabel(self.tag_info['vr'] or "Unknown"))
        
        layout.addWidget(info_group)
        
        # Value entry
        value_group = QGroupBox("Value Entry")
        value_layout = QFormLayout(value_group)
        
        if self.current_value:
            value_layout.addRow("Current Value:", QLabel(str(self.current_value)))
            
        self.value_edit = QLineEdit()
        self.value_edit.setText(str(self.current_value))
        
        # Add VR-specific help
        vr = self.tag_info.get('vr', '')
        if vr:
            help_text = self.get_vr_help(vr)
            if help_text:
                help_label = QLabel(help_text)
                help_label.setWordWrap(True)
                help_label.setStyleSheet("color: gray; font-style: italic;")
                value_layout.addRow("Format:", help_label)
                
        value_layout.addRow("New Value:", self.value_edit)
        
        layout.addWidget(value_group)
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | 
                                 QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept_value)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
    def get_vr_help(self, vr):
        """Get help text for VR format"""
        vr_help = {
            'DA': 'Date format: YYYYMMDD (e.g., 20231225)',
            'TM': 'Time format: HHMMSS.FFFFFF (e.g., 143000.000000)',
            'DT': 'DateTime format: YYYYMMDDHHMMSS.FFFFFF (e.g., 20231225143000)',
            'PN': 'Person Name format: Family^Given^Middle^Prefix^Suffix',
            'UI': 'UID format: Numbers and dots only (e.g., 1.2.840.10008.1.2)',
            'IS': 'Integer String: Numbers only',
            'DS': 'Decimal String: Numbers with optional decimal point',
            'CS': 'Code String: Usually predefined values',
            'LO': 'Long String: Max 64 characters',
            'SH': 'Short String: Max 16 characters',
            'LT': 'Long Text: Max 10240 characters',
            'ST': 'Short Text: Max 1024 characters',
            'AS': 'Age String: Format like 025Y, 030M, 015W, 120D'
        }
        return vr_help.get(vr, '')
        
    def accept_value(self):
        """Validate and accept the entered value"""
        self.new_value = self.value_edit.text()
        
        # Basic VR validation could be added here
        vr = self.tag_info.get('vr', '')
        if vr and not self.validate_vr_format(self.new_value, vr):
            reply = QMessageBox.question(
                self, "Format Warning",
                f"The entered value may not match the expected format for VR '{vr}'.\n"
                "Do you want to continue anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
                
        self.accept()
        
    def validate_vr_format(self, value, vr):
        """Basic VR format validation"""
        if not value:
            return True  # Empty values are generally OK
            
        try:
            if vr == 'DA' and len(value) == 8:
                # Basic date validation
                int(value)
                return True
            elif vr == 'IS':
                int(value)
                return True
            elif vr == 'DS':
                float(value)
                return True
            elif vr == 'UI':
                # Basic UID validation
                return all(c.isdigit() or c == '.' for c in value)
        except ValueError:
            return False
            
        return True  # Default to allowing the value