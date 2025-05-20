from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog,
    QTreeWidget, QTreeWidgetItem, QTableWidget, QTableWidgetItem, QMessageBox, QLineEdit, QInputDialog, QComboBox, QLabel, QCheckBox, QSizePolicy, QSplitter,
    QDialog, QFormLayout, QDialogButtonBox
)
from PyQt6.QtGui import QPixmap, QImage
from PyQt6.QtCore import QDir, Qt
import pydicom
import zipfile
import tempfile
import os
import shutil
import numpy as np
import sys
import yaml

# Add import for pynetdicom
try:
    from pynetdicom import AE, AllStoragePresentationContexts
    from pynetdicom.sop_class import Verification
    VERIFICATION_SOP_CLASS = Verification
    STORAGE_CONTEXTS = AllStoragePresentationContexts
except Exception as e:
    print("PYNETDICOM IMPORT ERROR:", e, file=sys.stderr)
    AE = None
    STORAGE_CONTEXTS = []
    VERIFICATION_SOP_CLASS = None

class DicomSendDialog(QDialog):
    def __init__(self, parent=None, config_path=None):
        super().__init__(parent)
        self.setWindowTitle("DICOM Send")
        layout = QFormLayout(self)

        # Load destinations from YAML config
        self.destinations = []
        # Always try both absolute and relative paths
        config_paths = []
        if config_path:
            config_paths.append(config_path)
        # Also try relative to the app.py file
        if config_path and not os.path.isabs(config_path):
            config_paths.append(os.path.join(os.path.dirname(__file__), config_path))
        # Default locations
        config_paths.append(os.path.expanduser("~/.dicom_send_destinations.yaml"))
        config_paths.append(os.path.join(os.path.dirname(__file__), "dicom_send_destinations.yaml"))

        for path in config_paths:
            if os.path.exists(path):
                try:
                    with open(path, "r") as f:
                        self.destinations = yaml.safe_load(f) or []
                    print(f"Loaded DICOM send destinations from: {path}", file=sys.stderr)
                    break
                except Exception as e:
                    print("Failed to load DICOM send config:", e, file=sys.stderr)
                    self.destinations = []

        self.dest_combo = QComboBox()
        self.dest_combo.addItem("Manual Entry")
        for dest in self.destinations:
            label = dest.get("label") or f"{dest.get('ae_title','')}@{dest.get('host','')}:{dest.get('port','')}"
            self.dest_combo.addItem(label)
        self.dest_combo.currentIndexChanged.connect(self._on_dest_changed)
        layout.addRow("Destination:", self.dest_combo)

        self.ae_title = QLineEdit("DCMSCU")
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

    def _on_dest_changed(self, idx):
        if idx == 0:
            # Manual entry
            return
        dest = self.destinations[idx-1]
        self.remote_ae.setText(str(dest.get("ae_title", "")))
        self.host.setText(str(dest.get("host", "")))
        self.port.setText(str(dest.get("port", "")))
        if "calling_ae_title" in dest:
            self.ae_title.setText(str(dest.get("calling_ae_title", "")))
        else:
            self.ae_title.setText("DCMSCU")

    def get_params(self):
        return (
            self.ae_title.text().strip(),
            self.remote_ae.text().strip(),
            self.host.text().strip(),
            int(self.port.text().strip())
        )

class MainWindow(QMainWindow):
    def __init__(self, start_path=None):
        super().__init__()
        self.setWindowTitle("DICOM Tag Editor")
        self.resize(1200, 800)
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Top button row: 2 columns
        top_btn_row = QHBoxLayout()
        open_btn = QPushButton("Open DICOM File/ZIP")
        open_btn.clicked.connect(self.open_file)
        top_btn_row.addWidget(open_btn)

        open_dir_btn = QPushButton("Open DICOM Directory")
        open_dir_btn.clicked.connect(self.open_directory)
        top_btn_row.addWidget(open_dir_btn)

        layout.addLayout(top_btn_row)

        # Splitter for tree and image preview (left), tag table (right)
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # Tree and preview toggle/preview
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Patient", "Study", "Series", "Instance"])
        self.tree.itemSelectionChanged.connect(self.display_selected_tree_file)
        self.tree.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        left_layout.addWidget(self.tree)

        self.preview_toggle = QCheckBox("Show Image Preview")
        self.preview_toggle.setChecked(False)
        self.preview_toggle.stateChanged.connect(self.display_selected_tree_file)
        left_layout.addWidget(self.preview_toggle)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumHeight(256)
        self.image_label.setVisible(False)
        self.image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        left_layout.addWidget(self.image_label)

        main_splitter.addWidget(left_widget)

        # Tag table (right side of splitter)
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search tags by ID or description...")
        self.search_bar.textChanged.connect(self.filter_tag_table)
        right_layout.addWidget(self.search_bar)

        self.tag_table = QTableWidget()
        self.tag_table.setColumnCount(4)
        self.tag_table.setHorizontalHeaderLabels(["Tag ID", "Description", "Value", "New Value"])
        self.tag_table.horizontalHeader().setStretchLastSection(True)
        self.tag_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.tag_table.setAlternatingRowColors(True)
        self.tag_table.cellActivated.connect(self._populate_new_value_on_edit)
        self.tag_table.cellClicked.connect(self._populate_new_value_on_edit)
        right_layout.addWidget(self.tag_table)

        main_splitter.addWidget(right_widget)
        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 2)
        layout.addWidget(main_splitter)

        # Button grid layout (3 columns)
        btn_grid = QHBoxLayout()

        # Column 1
        col1 = QVBoxLayout()
        self.edit_level_combo = QComboBox()
        self.edit_level_combo.addItems(["Instance", "Series", "Study", "Patient"])
        self.edit_level_combo.setCurrentText("Series")
        col1.addWidget(self.edit_level_combo)

        self.save_btn = QPushButton("Submit Changes")
        self.save_btn.clicked.connect(self.save_tag_changes)
        col1.addWidget(self.save_btn)

        btn_grid.addLayout(col1)

        # Column 2
        col2 = QVBoxLayout()
        self.save_as_btn = QPushButton("Save As")
        self.save_as_btn.clicked.connect(self.save_as)
        col2.addWidget(self.save_as_btn)

        self.dicom_send_btn = QPushButton("DICOM Send")
        self.dicom_send_btn.clicked.connect(self.dicom_send)
        col2.addWidget(self.dicom_send_btn)

        btn_grid.addLayout(col2)

        # Column 3
        col3 = QVBoxLayout()
        self.edit_btn = QPushButton("New Tag")
        self.edit_btn.clicked.connect(self.edit_tag)
        col3.addWidget(self.edit_btn)

        self.batch_edit_btn = QPushButton("Batch New Tag")
        self.batch_edit_btn.clicked.connect(self.batch_edit_tag)
        col3.addWidget(self.batch_edit_btn)

        btn_grid.addLayout(col3)

        layout.addLayout(btn_grid)

        # Summary info label
        self.summary_label = QLineEdit()
        self.summary_label.setReadOnly(True)
        self.summary_label.setStyleSheet("background: #f0f0f0; border: none; font-weight: bold;")
        layout.addWidget(self.summary_label)

        self.loaded_files = []
        self.file_metadata = {}
        self.temp_dir = None
        self.current_filepath = None
        self.current_ds = None
        self._all_tag_rows = []  # Store all tag rows for filtering

        self.dicom_send_config_path = os.path.expanduser("~/.dicom_send_destinations.yaml")

        if start_path:
            self.load_path_on_start(start_path)

    def _populate_new_value_on_edit(self, row, col):
        """Auto-populate the 'New Value' cell with the current value when clicked if empty."""
        if col != 3:  # Only handle clicks on the "New Value" column
            return
        new_value_item = self.tag_table.item(row, 3)
        current_value_item = self.tag_table.item(row, 2)
        if new_value_item and current_value_item and not new_value_item.text().strip():
            new_value_item.setText(current_value_item.text())

    def load_path_on_start(self, path):
        path = os.path.expanduser(path)
        if os.path.isfile(path):
            if path.lower().endswith('.zip'):
                self.clear_loaded_files()
                self.temp_dir = tempfile.mkdtemp()
                try:
                    with zipfile.ZipFile(path, 'r') as zip_ref:
                        zip_ref.extractall(self.temp_dir)
                    dcm_files = []
                    for root, dirs, files in os.walk(self.temp_dir):
                        for name in files:
                            if name.lower().endswith('.dcm'):
                                dcm_files.append(os.path.join(root, name))
                    if not dcm_files:
                        QMessageBox.warning(self, "No DICOM", "No DICOM (.dcm) files found in ZIP archive.")
                        return
                    self.loaded_files = [(f, self.temp_dir) for f in dcm_files]
                    self.populate_tree(dcm_files)
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Error reading ZIP: {e}")
                    self.cleanup_temp_dir()
            elif path.lower().endswith('.dcm'):
                self.clear_loaded_files()
                self.loaded_files = [(path, None)]
                self.populate_tree([path])
            else:
                QMessageBox.warning(self, "Unsupported", "Only .dcm and .zip files are supported.")
        elif os.path.isdir(path):
            self.clear_loaded_files()
            dcm_files = []
            for root, dirs, files in os.walk(path):
                for name in files:
                    if name.lower().endswith('.dcm'):
                        dcm_files.append(os.path.join(root, name))
            if not dcm_files:
                QMessageBox.warning(self, "No DICOM", "No DICOM (.dcm) files found in directory.")
                return
            self.loaded_files = [(f, None) for f in dcm_files]
            self.populate_tree(dcm_files)
        else:
            QMessageBox.warning(self, "Not Found", f"Path does not exist: {path}")

    def open_file(self):
        dialog = QFileDialog(self, "Open DICOM or ZIP File", QDir.homePath(), "DICOM Files (*.dcm);;ZIP Archives (*.zip);;All Files (*)")
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        if dialog.exec():
            file_paths = dialog.selectedFiles()
            if file_paths:
                file_path = file_paths[0]
                self.clear_loaded_files()
                if file_path.lower().endswith('.zip'):
                    self.temp_dir = tempfile.mkdtemp()
                    try:
                        with zipfile.ZipFile(file_path, 'r') as zip_ref:
                            zip_ref.extractall(self.temp_dir)
                        dcm_files = []
                        for root, dirs, files in os.walk(self.temp_dir):
                            for name in files:
                                if name.lower().endswith('.dcm'):
                                    dcm_files.append(os.path.join(root, name))
                        if not dcm_files:
                            self.tag_view.setText("No DICOM (.dcm) files found in ZIP archive.")
                            return
                        self.loaded_files = [(f, self.temp_dir) for f in dcm_files]
                        self.populate_tree(dcm_files)
                    except Exception as e:
                        self.tag_view.setText(f"Error reading ZIP: {e}")
                        self.cleanup_temp_dir()
                else:
                    self.loaded_files = [(file_path, None)]
                    self.populate_tree([file_path])

    def open_directory(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Open DICOM Directory", QDir.homePath())
        if dir_path:
            self.clear_loaded_files()
            dcm_files = []
            for root, dirs, files in os.walk(dir_path):
                for name in files:
                    if name.lower().endswith('.dcm'):
                        dcm_files.append(os.path.join(root, name))
            if not dcm_files:
                self.tag_view.setText("No DICOM (.dcm) files found in directory.")
                return
            self.loaded_files = [(f, None) for f in dcm_files]
            self.populate_tree(dcm_files)

    def populate_tree(self, files):
        self.tree.clear()
        # Build hierarchy: Patient > Study > Series > Instance (with descriptions)
        hierarchy = {}
        self.file_metadata = {}
        modalities = set()
        for f in files:
            try:
                ds = pydicom.dcmread(f, stop_before_pixels=True)
                patient_id = getattr(ds, "PatientID", "Unknown ID")
                patient_name = getattr(ds, "PatientName", "Unknown Name")
                patient_label = f"{patient_name} ({patient_id})"

                study_uid = getattr(ds, "StudyInstanceUID", "Unknown StudyUID")
                study_desc = getattr(ds, "StudyDescription", "No Study Description")
                study_label = f"{study_desc} [{study_uid}]"

                series_uid = getattr(ds, "SeriesInstanceUID", "Unknown SeriesUID")
                series_desc = getattr(ds, "SeriesDescription", "No Series Description")
                series_label = f"{series_desc} [{series_uid}]"

                instance_number = getattr(ds, "InstanceNumber", None)
                sop_uid = getattr(ds, "SOPInstanceUID", os.path.basename(f))
                if instance_number is not None:
                    instance_label = f"Instance {instance_number} [{sop_uid}]"
                else:
                    instance_label = f"{os.path.basename(f)} [{sop_uid}]"

                modality = getattr(ds, "Modality", None)
                if modality:
                    modalities.add(str(modality))

                self.file_metadata[f] = (patient_label, study_label, series_label, instance_label)
                hierarchy.setdefault(patient_label, {}).setdefault(study_label, {}).setdefault(series_label, {})[instance_label] = f
            except Exception:
                continue

        for patient, studies in hierarchy.items():
            patient_item = QTreeWidgetItem([patient])
            self.tree.addTopLevelItem(patient_item)
            for study, series_dict in studies.items():
                study_item = QTreeWidgetItem([patient, study])
                patient_item.addChild(study_item)
                for series, instances in series_dict.items():
                    series_item = QTreeWidgetItem([patient, study, series])
                    study_item.addChild(series_item)
                    for instance, filepath in sorted(instances.items()):
                        instance_item = QTreeWidgetItem([patient, study, series, str(instance)])
                        instance_item.setData(0, 1000, filepath)  # Store filepath in user role
                        series_item.addChild(instance_item)
        self.tree.expandAll()

        # --- Summary info ---
        patient_count = len(hierarchy)
        study_count = sum(len(studies) for studies in hierarchy.values())
        series_count = sum(len(series_dict) for studies in hierarchy.values() for series_dict in studies.values())
        instance_count = len(files)
        modality_str = ", ".join(sorted(modalities)) if modalities else "Unknown"
        self.summary_label.setText(
            f"Patients: {patient_count} | Studies: {study_count} | Series: {series_count} | Instances: {instance_count} | Modalities: {modality_str}"
        )

    def display_selected_file(self, row):
        if row < 0 or row >= len(self.loaded_files):
            self.tag_view.clear()
            return
        file_path, _ = self.loaded_files[row]
        try:
            ds = pydicom.dcmread(file_path)
            tags = []
            for elem in ds:
                if elem.tag == (0x7fe0, 0x0010):  # Pixel Data
                    tags.append(f"{elem.tag} {elem.name}: <Pixel Data not shown>")
                elif elem.VR == "OB" or elem.VR == "OW" or elem.VR == "UN":
                    tags.append(f"{elem.tag} {elem.name}: <Binary data not shown>")
                else:
                    tags.append(f"{elem.tag} {elem.name}: {elem.value}")
            self.tag_view.setText("\n".join(tags))
        except Exception as e:
            self.tag_view.setText(f"Error reading file: {e}")

    def display_selected_tree_file(self):
        selected = self.tree.selectedItems()
        if not selected:
            self.tag_table.setRowCount(0)
            self.current_filepath = None
            self.current_ds = None
            self.image_label.clear()
            self.image_label.setVisible(False)
            return
        item = selected[0]
        filepath = item.data(0, 1000)
        if not filepath:
            self.tag_table.setRowCount(0)
            self.current_filepath = None
            self.current_ds = None
            self.image_label.clear()
            self.image_label.setVisible(False)
            return
        try:
            ds = pydicom.dcmread(filepath)
            self.current_filepath = filepath
            self.current_ds = ds
            self.populate_tag_table(ds)
            # Image preview
            if self.preview_toggle.isChecked():
                pixmap = self._get_dicom_pixmap(ds)
                if pixmap:
                    self.image_label.setPixmap(pixmap.scaledToHeight(256, Qt.TransformationMode.SmoothTransformation))
                    self.image_label.setVisible(True)
                else:
                    self.image_label.clear()
                    self.image_label.setVisible(False)
            else:
                self.image_label.clear()
                self.image_label.setVisible(False)
        except Exception as e:
            self.tag_table.setRowCount(0)
            self.current_filepath = None
            self.current_ds = None
            self.image_label.clear()
            self.image_label.setVisible(False)
            QMessageBox.critical(self, "Error", f"Error reading file: {e}")

    def _get_dicom_pixmap(self, ds):
        try:
            if 'PixelData' not in ds:
                return None
            arr = ds.pixel_array
            # Handle monochrome and RGB
            if arr.ndim == 2:
                # Grayscale
                arr = self._normalize_grayscale(arr)
                h, w = arr.shape
                qimg = QImage(arr.data, w, h, w, QImage.Format.Format_Grayscale8)
            elif arr.ndim == 3:
                if arr.shape[2] == 3:
                    # RGB
                    h, w, c = arr.shape
                    qimg = QImage(arr.data, w, h, 3 * w, QImage.Format.Format_RGB888)
                else:
                    return None
            else:
                return None
            return QPixmap.fromImage(qimg)
        except Exception:
            return None

    def _normalize_grayscale(self, arr):
        arr = arr.astype(np.float32)
        arr -= arr.min()
        if arr.max() > 0:
            arr /= arr.max()
        arr = (arr * 255).astype(np.uint8)
        return arr

    def populate_tag_table(self, ds):
        self.tag_table.setRowCount(0)
        self._all_tag_rows = []
        for elem in ds:
            if elem.tag == (0x7fe0, 0x0010):
                value = "<Pixel Data not shown>"
            elif elem.VR in ("OB", "OW", "UN"):
                value = "<Binary data not shown>"
            else:
                value = str(elem.value)
            tag_id = f"({elem.tag.group:04X},{elem.tag.element:04X})"
            desc = elem.name
            row = [tag_id, desc, value, ""]
            self._all_tag_rows.append((elem, row))
        self.apply_tag_table_filter()

    def filter_tag_table(self, text):
        self.apply_tag_table_filter()

    def apply_tag_table_filter(self):
        filter_text = self.search_bar.text().lower()
        self.tag_table.setRowCount(0)
        for elem, row in self._all_tag_rows:
            tag_id, desc, value, _ = row
            if filter_text in tag_id.lower() or filter_text in desc.lower():
                row_idx = self.tag_table.rowCount()
                self.tag_table.insertRow(row_idx)
                self.tag_table.setItem(row_idx, 0, QTableWidgetItem(tag_id))
                self.tag_table.setItem(row_idx, 1, QTableWidgetItem(desc))
                self.tag_table.setItem(row_idx, 2, QTableWidgetItem(value))
                new_value_item = QTableWidgetItem("")
                if elem.tag == (0x7fe0, 0x0010) or elem.VR in ("OB", "OW", "UN"):
                    new_value_item.setFlags(new_value_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.tag_table.setItem(row_idx, 3, new_value_item)

    def save_tag_changes(self):
        if not self.current_ds or not self.current_filepath:
            QMessageBox.warning(self, "No File", "No DICOM file selected.")
            return

        # Determine editing level and target tree node
        level = self.edit_level_combo.currentText()
        selected = self.tree.selectedItems()
        if not selected:
            QMessageBox.warning(self, "No Selection", "Please select a node in the tree.")
            return
        tree_item = selected[0]

        # Find the node at the requested level
        level_map = {"Patient": 0, "Study": 1, "Series": 2, "Instance": 3}
        target_level = level_map[level]
        # Traverse up to the correct level
        while tree_item.parent() and tree_item.depth() > target_level:
            tree_item = tree_item.parent()
        # Traverse down to the first child at the correct level if needed
        while tree_item.childCount() > 0 and tree_item.depth() < target_level:
            tree_item = tree_item.child(0)

        # Collect all instance filepaths under this node
        filepaths = self._collect_instance_filepaths(tree_item)
        if not filepaths:
            QMessageBox.warning(self, "No Instances", "No DICOM instances found under this node.")
            return

        # Gather edits from the tag table
        edits = []
        for i in range(self.tag_table.rowCount()):
            new_value = self.tag_table.item(i, 3)
            if new_value and new_value.text().strip() != "":
                tag_id = self.tag_table.item(i, 0).text()
                try:
                    group, elem = tag_id[1:-1].split(",")
                    tag = (int(group, 16), int(elem, 16))
                    edits.append((tag, new_value.text()))
                except Exception as e:
                    QMessageBox.warning(self, "Error", f"Failed to parse tag {tag_id}: {e}")

        if not edits:
            QMessageBox.information(self, "No Changes", "No tags were changed.")
            return

        updated_count = 0
        failed_files = []
        for fp in filepaths:
            try:
                ds = pydicom.dcmread(fp)
                updated = False
                for tag, new_val in edits:
                    if tag in ds:
                        old_type = type(ds[tag].value)
                        ds[tag].value = old_type(new_val)
                        updated = True
                if updated:
                    ds.save_as(fp)
                    updated_count += 1
            except Exception as e:
                failed_files.append(fp)
        QMessageBox.information(self, "Batch Edit Complete", f"Updated {updated_count} files.\nFailed: {len(failed_files)}")
        self.display_selected_tree_file()

    def edit_tag(self):
        selected = self.tree.selectedItems()
        if not selected:
            QMessageBox.warning(self, "No Selection", "Please select an instance in the tree.")
            return
        item = selected[0]
        filepath = item.data(0, 1000)
        if not filepath:
            QMessageBox.warning(self, "No Instance", "Please select an instance node.")
            return
        try:
            ds = pydicom.dcmread(filepath)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not read file: {e}")
            return

        tag_str, ok = QInputDialog.getText(self, "Edit Tag", "Enter tag name or (gggg,eeee):")
        if not ok or not tag_str.strip():
            return

        # Try to resolve tag
        tag = None
        if ',' in tag_str:
            try:
                group, elem = tag_str.replace('(', '').replace(')', '').split(',')
                tag = (int(group, 16), int(elem, 16))
            except Exception:
                QMessageBox.warning(self, "Invalid Tag", "Tag format should be (gggg,eeee) in hex.")
                return
        else:
            # Try to find by name
            for elem in ds:
                if elem.name.lower() == tag_str.strip().lower():
                    tag = elem.tag
                    break
            if tag is None:
                QMessageBox.warning(self, "Not Found", f"Tag '{tag_str}' not found by name.")
                return

        if tag not in ds:
            QMessageBox.warning(self, "Not Found", f"Tag {tag} not found in this file.")
            return

        old_value = str(ds[tag].value)
        new_value, ok = QInputDialog.getText(self, "Edit Tag", f"Current value: {old_value}\nEnter new value:")
        if not ok:
            return

        try:
            ds[tag].value = type(ds[tag].value)(new_value)
            ds.save_as(filepath)
            QMessageBox.information(self, "Success", f"Tag {tag} updated.")
            self.display_selected_tree_file()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to update tag: {e}")

    def batch_edit_tag(self):
        selected = self.tree.selectedItems()
        if not selected:
            QMessageBox.warning(self, "No Selection", "Please select a node in the tree.")
            return
        item = selected[0]
        filepaths = self._collect_instance_filepaths(item)
        if not filepaths:
            QMessageBox.warning(self, "No Instances", "No DICOM instances found under this node.")
            return

        tag_str, ok = QInputDialog.getText(self, "Batch Edit Tag", "Enter tag name or (gggg,eeee):")
        if not ok or not tag_str.strip():
            return

        # Try to resolve tag for the first file
        tag = None
        ds_sample = None
        try:
            ds_sample = pydicom.dcmread(filepaths[0])
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not read sample file: {e}")
            return

        if ',' in tag_str:
            try:
                group, elem = tag_str.replace('(', '').replace(')', '').split(',')
                tag = (int(group, 16), int(elem, 16))
            except Exception:
                QMessageBox.warning(self, "Invalid Tag", "Tag format should be (gggg,eeee) in hex.")
                return
        else:
            for elem in ds_sample:
                if elem.name.lower() == tag_str.strip().lower():
                    tag = elem.tag
                    break
            if tag is None:
                QMessageBox.warning(self, "Not Found", f"Tag '{tag_str}' not found by name.")
                return

        if tag not in ds_sample:
            QMessageBox.warning(self, "Not Found", f"Tag {tag} not found in these files.")
            return

        old_value = str(ds_sample[tag].value)
        new_value, ok = QInputDialog.getText(self, "Batch Edit Tag", f"Current value (first file): {old_value}\nEnter new value to apply to all:")
        if not ok:
            return

        updated_count = 0
        failed_files = []
        for fp in filepaths:
            try:
                ds = pydicom.dcmread(fp)
                if tag in ds:
                    old_type = type(ds[tag].value)
                    ds[tag].value = old_type(new_value)
                    ds.save_as(fp)
                    updated_count += 1
            except Exception as e:
                failed_files.append(fp)
        QMessageBox.information(self, "Batch Edit Complete", f"Updated {updated_count} files.\nFailed: {len(failed_files)}")
        self.display_selected_tree_file()

    def save_as(self):
        selected = self.tree.selectedItems()
        if not selected:
            QMessageBox.warning(self, "No Selection", "Please select a node in the tree to export.")
            return
        tree_item = selected[0]

        # Always traverse up to the patient node (depth 0)
        while tree_item.parent():
            tree_item = tree_item.parent()

        filepaths = self._collect_instance_filepaths(tree_item)
        if not filepaths:
            QMessageBox.warning(self, "No Instances", "No DICOM instances found under this node.")
            return

        export_type, ok = QInputDialog.getItem(self, "Export Type", "Export as:", ["Directory", "ZIP"], 0, False)
        if not ok:
            return

        if export_type == "Directory":
            dialog = QFileDialog(self, "Select Export Directory", QDir.homePath())
            dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
            dialog.setFileMode(QFileDialog.FileMode.Directory)
            dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
            if dialog.exec():
                dirs = dialog.selectedFiles()
                if not dirs:
                    return
                out_dir = dirs[0]
                for fp in filepaths:
                    try:
                        ds = pydicom.dcmread(fp)
                        out_path = os.path.join(out_dir, os.path.basename(fp))
                        ds.save_as(out_path)
                    except Exception as e:
                        QMessageBox.warning(self, "Export Error", f"Failed to export {fp}: {e}")
                QMessageBox.information(self, "Export Complete", f"Exported {len(filepaths)} files to {out_dir}")
        else:  # ZIP
            dialog = QFileDialog(self, "Save ZIP Archive", QDir.homePath(), "ZIP Archives (*.zip)")
            dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
            dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
            if dialog.exec():
                files = dialog.selectedFiles()
                if not files:
                    return
                out_zip = files[0]
                if not out_zip.lower().endswith('.zip'):
                    out_zip += '.zip'
                try:
                    import zipfile
                    with zipfile.ZipFile(out_zip, 'w') as zipf:
                        for fp in filepaths:
                            ds = pydicom.dcmread(fp)
                            temp_path = os.path.basename(fp)
                            ds.save_as(temp_path)
                            zipf.write(temp_path, arcname=os.path.basename(fp))
                            os.remove(temp_path)
                    QMessageBox.information(self, "Export Complete", f"Exported {len(filepaths)} files to {out_zip}")
                except Exception as e:
                    QMessageBox.critical(self, "Export Error", f"Failed to create ZIP: {e}")

    def dicom_send(self):
        print("Python executable:", sys.executable, file=sys.stderr)
        print("sys.path:", sys.path, file=sys.stderr)
        print("AE:", AE, "STORAGE_CONTEXTS:", STORAGE_CONTEXTS, file=sys.stderr)
        if AE is None or not STORAGE_CONTEXTS or VERIFICATION_SOP_CLASS is None:
            QMessageBox.critical(
                self,
                "Missing Dependency",
                "pynetdicom is required for DICOM send.\n"
                "Check your environment and restart the application.\n"
                "Python executable: {}\n"
                "sys.path: {}".format(sys.executable, sys.path)
            )
            return
        selected = self.tree.selectedItems()
        if not selected:
            QMessageBox.warning(self, "No Selection", "Please select a node in the tree to send.")
            return
        tree_item = selected[0]
        # Always traverse up to the patient node (depth 0)
        while tree_item.parent():
            tree_item = tree_item.parent()
        filepaths = self._collect_instance_filepaths(tree_item)
        if not filepaths:
            QMessageBox.warning(self, "No Instances", "No DICOM instances found under this node.")
            return

        dlg = DicomSendDialog(self, config_path=self.dicom_send_config_path)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        calling_ae, remote_ae, host, port = dlg.get_params()

        ae = AE(ae_title=calling_ae)
        sop_classes = set()
        for fp in filepaths:
            try:
                ds = pydicom.dcmread(fp, stop_before_pixels=True)
                sop_classes.add(ds.SOPClassUID)
            except Exception as e:
                print(f"Failed to read SOPClassUID from {fp}: {e}", file=sys.stderr)
        # If no SOP classes found, abort
        if not sop_classes:
            QMessageBox.critical(self, "DICOM Send", "No valid SOP Class UIDs found in selected files.")
            return
        # Print SOP classes for debugging
        print("SOP Classes to request:", sop_classes, file=sys.stderr)
        for cx in STORAGE_CONTEXTS:
            if getattr(cx, "abstract_syntax", None) in sop_classes:
                ae.add_requested_context(cx.abstract_syntax)
        ae.add_requested_context(VERIFICATION_SOP_CLASS)

        assoc = ae.associate(host, port, ae_title=remote_ae)
        if not assoc.is_established:
            QMessageBox.critical(self, "DICOM Send", f"Association to {host}:{port} ({remote_ae}) failed.")
            return

        sent = 0
        failed = []
        failed_details = []
        for fp in filepaths:
            try:
                ds = pydicom.dcmread(fp)
                status = assoc.send_c_store(ds)
                status_code = getattr(status, "Status", None)
                # Add more detailed status code explanations
                status_meaning = {
                    0x0000: "Success",
                    0xB000: "Warning: Coercion of Data Elements",
                    0xA700: "Refused: Out of Resources",
                    0xA900: "Error: Data Set does not match SOP Class",
                    0xC000: "Error: Cannot Understand",
                    0xA778: "Refused: Move Destination unknown (check AE Title, Host, Port, or permissions)"
                }
                meaning = status_meaning.get(status_code, f"Unknown/Other (0x{status_code:04X})" if status_code is not None else "No status")
                if status_code in [0x0000, 0xB000]:
                    sent += 1
                else:
                    failed.append(fp)
                    failed_details.append(f"{os.path.basename(fp)}: status=0x{status_code:04X} ({meaning})")
            except Exception as e:
                failed.append(fp)
                failed_details.append(f"{os.path.basename(fp)}: {e}")
        assoc.release()
        msg = f"Sent: {sent}\nFailed: {len(failed)}"
        if failed_details:
            msg += "\n\nDetails:\n" + "\n".join(failed_details)
        QMessageBox.information(self, "DICOM Send", msg)

    def _collect_instance_filepaths(self, tree_item):
        """Recursively collect all instance filepaths under the given tree item."""
        filepaths = []
        def collect(item):
            fp = item.data(0, 1000)
            if fp:
                filepaths.append(fp)
            for i in range(item.childCount()):
                collect(item.child(i))
        collect(tree_item)
        return filepaths

    def clear_loaded_files(self):
        self.cleanup_temp_dir()
        # Remove self.file_list.clear()
        self.loaded_files = []
        self.cleanup_temp_dir()
        self.tree.clear()

    def cleanup_temp_dir(self):
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

# Add this helper method to QTreeWidgetItem to get depth
# (You can add this at the bottom of the file or near the class definition)
def _qtreewidgetitem_depth(item):
    """Return the depth of the item in the tree."""
    depth = 0
    while item.parent():
        depth += 1
        item = item.parent()
    return depth

QTreeWidgetItem.depth = _qtreewidgetitem_depth
