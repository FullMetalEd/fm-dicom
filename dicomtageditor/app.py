from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog,
    QTreeWidget, QTreeWidgetItem, QTableWidget, QTableWidgetItem, QMessageBox, QLineEdit, QInputDialog, QComboBox, QLabel, QCheckBox, QSizePolicy, QSplitter,
    QDialog, QFormLayout, QDialogButtonBox, QProgressDialog,
    QApplication, QToolBar, QGroupBox, QFrame, QStatusBar, QStyle, QMenu
)
from PyQt6.QtGui import QPixmap, QImage, QIcon, QPalette, QColor, QFont, QAction
from PyQt6.QtCore import QDir, Qt, QPoint, QSize
import pydicom
import zipfile
import tempfile
import os
import shutil
import numpy as np
import sys
import yaml
from pydicom.dataelem import DataElement
from pydicom.uid import generate_uid
import datetime
import logging

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

# Add depth method to QTreeWidgetItem
def depth(self):
    """Return the depth of the item in the tree."""
    depth = 0
    while self.parent():
        depth += 1
        self = self.parent()
    return depth

QTreeWidgetItem.depth = depth

def set_dark_palette(app):
    palette = QPalette()
    # Use a uniform dark background
    background = QColor(32, 34, 37)
    palette.setColor(QPalette.ColorRole.Window, background)
    palette.setColor(QPalette.ColorRole.Base, background)
    palette.setColor(QPalette.ColorRole.AlternateBase, background)
    palette.setColor(QPalette.ColorRole.Button, background)
    palette.setColor(QPalette.ColorRole.ToolTipBase, background)
    # Make all text very light for contrast
    light_text = QColor(245, 245, 245)
    palette.setColor(QPalette.ColorRole.WindowText, light_text)
    palette.setColor(QPalette.ColorRole.Text, light_text)
    palette.setColor(QPalette.ColorRole.ButtonText, light_text)
    palette.setColor(QPalette.ColorRole.ToolTipText, light_text)
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    # Highlight and links
    palette.setColor(QPalette.ColorRole.Highlight, QColor(80, 140, 255))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 85, 85))
    # Disabled text
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(100, 100, 100))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(100, 100, 100))
    app.setPalette(palette)

def load_config(config_path=None):
    # Try user config, then local config, then defaults
    paths = []
    if config_path:
        paths.append(config_path)
    paths.append(os.path.expanduser("~/.dicomtageditor/config.yml"))
    paths.append(os.path.join(os.path.dirname(__file__), "config.yml"))
    for path in paths:
        if os.path.exists(path):
            with open(path, "r") as f:
                return yaml.safe_load(f) or {}
    # Defaults if no config found
    return {
        "log_path": os.path.expanduser("~/.dicomtageditor/dicomtageditor.log"),
        "log_level": "INFO",
        "show_image_preview": False,
        "ae_title": "DCMSCU",
        "destinations": [],
        "window_size": [1200, 800],
        "default_export_dir": str(QDir.homePath()),
        "default_import_dir": str(QDir.homePath()),
        "anonymization": {},
        "recent_paths": [],
        "theme": "light",
        "language": "en"
    }

def setup_logging(log_path, log_level):
    # Truncate log file on each run
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(log_path, mode="w", encoding="utf-8"),
            logging.StreamHandler(sys.stderr)
        ]
    )

class DicomSendDialog(QDialog):
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
    def __init__(self, start_path=None, config_path=None):
        self.config = load_config(config_path)
        setup_logging(self.config.get("log_path"), self.config.get("log_level"))
        logging.info("Application started")
        
        # Set config attributes early
        self.dicom_send_config = self.config
        self.default_export_dir = os.path.expanduser(self.config.get("default_export_dir", str(QDir.homePath())))
        self.default_import_dir = os.path.expanduser(self.config.get("default_import_dir", str(QDir.homePath())))

        super().__init__()
        self.setWindowTitle("DICOM Tag Editor")
        w, h = self.config.get("window_size", [1200, 800])
        self.resize(w, h)
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # --- Modern Qt Style/Theme ---
        QApplication.setStyle("Fusion")
        set_dark_palette(QApplication.instance())

        # --- Toolbar for Common Actions ---
        toolbar = QToolBar("Main Toolbar")
        toolbar.setIconSize(QSize(20, 20))
        self.addToolBar(toolbar)

        open_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton)
        save_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton)
        delete_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon)
        merge_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogNewFolder)
        expand_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown)
        collapse_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowUp)

        act_open = QAction(open_icon, "Open", self)
        act_open.triggered.connect(self.open_file)
        toolbar.addAction(act_open)

        act_open_dir = QAction(QIcon.fromTheme("folder"), "Open Directory", self)
        act_open_dir.triggered.connect(self.open_directory)
        toolbar.addAction(act_open_dir)

        act_save = QAction(save_icon, "Save As", self)
        act_save.triggered.connect(self.save_as)
        toolbar.addAction(act_save)

        act_delete = QAction(delete_icon, "Delete", self)
        act_delete.triggered.connect(self.delete_selected_items)
        toolbar.addAction(act_delete)

        act_merge = QAction(merge_icon, "Merge Patients", self)
        act_merge.triggered.connect(self.merge_patients)
        toolbar.addAction(act_merge)

        act_expand = QAction(expand_icon, "Expand All", self)
        act_expand.triggered.connect(self.tree_expand_all)
        toolbar.addAction(act_expand)

        act_collapse = QAction(collapse_icon, "Collapse All", self)
        act_collapse.triggered.connect(self.tree_collapse_all)
        toolbar.addAction(act_collapse)

        toolbar.addSeparator()

        # --- Main Splitter ---
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # --- Tree Search/Filter ---
        tree_search_layout = QHBoxLayout()
        self.tree_search_bar = QLineEdit()
        self.tree_search_bar.setPlaceholderText("Search patients/studies/series/instances...")
        self.tree_search_bar.textChanged.connect(self.filter_tree_items)
        tree_search_layout.addWidget(self.tree_search_bar)
        left_layout.addLayout(tree_search_layout)

        # --- Tree Widget ---
        self.tree = QTreeWidget()
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.tree.setHeaderLabels(["Patient", "Study", "Series", "Instance"])
        self.tree.itemSelectionChanged.connect(self.display_selected_tree_file)
        self.tree.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.tree.setAlternatingRowColors(True)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_tree_context_menu)
        left_layout.addWidget(self.tree)

        self.preview_toggle = QCheckBox("Show Image Preview")
        self.preview_toggle.setChecked(bool(self.config.get("show_image_preview", False)))
        self.preview_toggle.stateChanged.connect(self.display_selected_tree_file)
        left_layout.addWidget(self.preview_toggle)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumHeight(256)
        self.image_label.setVisible(False)
        self.image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        left_layout.addWidget(self.image_label)

        main_splitter.addWidget(left_widget)

        # --- Tag Table and Search ---
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

        # --- Grouped Button Layouts ---
        btn_grid = QHBoxLayout()

        # Column 1: Editing
        col1 = QVBoxLayout()
        edit_group = QGroupBox("Editing")
        edit_layout = QVBoxLayout()
        self.edit_level_combo = QComboBox()
        self.edit_level_combo.addItems(["Instance", "Series", "Study", "Patient"])
        self.edit_level_combo.setCurrentText("Series")
        edit_layout.addWidget(self.edit_level_combo)

        self.save_btn = QPushButton(QIcon(save_icon), "Submit Changes")
        self.save_btn.clicked.connect(self.save_tag_changes)
        edit_layout.addWidget(self.save_btn)

        self.anon_btn = QPushButton("Anonymise Patient")
        self.anon_btn.clicked.connect(self.anonymise_selected)
        edit_layout.addWidget(self.anon_btn)
        edit_group.setLayout(edit_layout)
        col1.addWidget(edit_group)
        btn_grid.addLayout(col1)

        # Column 2: Export/Send
        col2 = QVBoxLayout()
        export_group = QGroupBox("Export/Send")
        export_layout = QVBoxLayout()
        self.save_as_btn = QPushButton(QIcon(save_icon), "Save As")
        self.save_as_btn.clicked.connect(self.save_as)
        export_layout.addWidget(self.save_as_btn)

        self.dicom_send_btn = QPushButton("DICOM Send")
        self.dicom_send_btn.clicked.connect(self.dicom_send)
        export_layout.addWidget(self.dicom_send_btn)
        export_group.setLayout(export_layout)
        col2.addWidget(export_group)
        btn_grid.addLayout(col2)

        # Column 3: Tag/Batch/Merge/Delete
        col3 = QVBoxLayout()
        tag_group = QGroupBox("Tags/Batch")
        tag_layout = QVBoxLayout()
        self.edit_btn = QPushButton("New Tag")
        self.edit_btn.clicked.connect(self.edit_tag)
        tag_layout.addWidget(self.edit_btn)

        self.batch_edit_btn = QPushButton("Batch New Tag")
        self.batch_edit_btn.clicked.connect(self.batch_edit_tag)
        tag_layout.addWidget(self.batch_edit_btn)
        tag_group.setLayout(tag_layout)
        col3.addWidget(tag_group)

        self.merge_patients_btn = QPushButton(QIcon(merge_icon), "Merge Patients")
        self.merge_patients_btn.clicked.connect(self.merge_patients)
        col3.addWidget(self.merge_patients_btn)

        self.delete_btn = QPushButton(QIcon(delete_icon), "Delete")
        self.delete_btn.setToolTip("Delete selected patients, studies, series, or instances")
        self.delete_btn.clicked.connect(self.delete_selected_items)
        col3.addWidget(self.delete_btn)

        btn_grid.addLayout(col3)
        layout.addLayout(btn_grid)

        # --- Status Bar ---
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Ready")

        # --- Summary label ---
        self.summary_label = QLineEdit()
        self.summary_label.setReadOnly(True)
        self.summary_label.setStyleSheet(
            "background: #202225; color: #f5f5f5; border: none; font-weight: bold;"
        )
        layout.addWidget(self.summary_label)

        # Set white text and dark background for search bars
        searchbar_style = (
            "background: #202225; color: #f5f5f5; border: 1px solid #444;"
            "selection-background-color: #508cff;"
            "selection-color: #fff;"
        )
        self.tree_search_bar.setStyleSheet(searchbar_style)
        self.search_bar.setStyleSheet(searchbar_style)

        # --- Initial Load ---
        self.loaded_files = []
        self.file_metadata = {}
        self.temp_dir = None
        self.current_filepath = None
        self.current_ds = None
        self._all_tag_rows = []  # Store all tag rows for filtering

        if start_path:
            self.load_path_on_start(start_path)

        logging.info("MainWindow initialized")

    def tree_expand_all(self):
        """Expand all items in the tree."""
        self.tree.expandAll()

    def tree_collapse_all(self):
        """Collapse all items in the tree."""
        self.tree.collapseAll()

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
                    # Progress dialog for extracting and scanning ZIP
                    all_files = []
                    for root, dirs, files in os.walk(self.temp_dir):
                        for name in files:
                            all_files.append(os.path.join(root, name))
                    progress = QProgressDialog("Scanning ZIP for DICOM files...", "Cancel", 0, len(all_files), self)
                    progress.setWindowTitle("Loading ZIP")
                    progress.setMinimumDuration(0)
                    progress.setValue(0)
                    for idx, f in enumerate(all_files):
                        if progress.wasCanceled():
                            break
                        if f.lower().endswith('.dcm'):
                            dcm_files.append(f)
                        progress.setValue(idx + 1)
                        QApplication.processEvents()
                    progress.close()
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
            # Progress dialog for scanning directory
            all_files = []
            for root, dirs, files in os.walk(path):
                for name in files:
                    all_files.append(os.path.join(root, name))
            progress = QProgressDialog("Scanning directory for DICOM files...", "Cancel", 0, len(all_files), self)
            progress.setWindowTitle("Loading Directory")
            progress.setMinimumDuration(0)
            progress.setValue(0)
            for idx, f in enumerate(all_files):
                if progress.wasCanceled():
                    break
                if f.lower().endswith('.dcm'):
                    dcm_files.append(f)
                progress.setValue(idx + 1)
                QApplication.processEvents()
            progress.close()
            if not dcm_files:
                QMessageBox.warning(self, "No DICOM", "No DICOM (.dcm) files found in directory.")
                return
            self.loaded_files = [(f, None) for f in dcm_files]
            self.populate_tree(dcm_files)
        else:
            QMessageBox.warning(self, "Not Found", f"Path does not exist: {path}")

    def open_file(self):
        dialog = QFileDialog(self, "Open DICOM or ZIP File", self.default_import_dir, "DICOM Files (*.dcm);;ZIP Archives (*.zip);;All Files (*)")
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
                        all_files = []
                        for root, dirs, files in os.walk(self.temp_dir):
                            for name in files:
                                all_files.append(os.path.join(root, name))
                        progress = QProgressDialog("Scanning ZIP for DICOM files...", "Cancel", 0, len(all_files), self)
                        progress.setWindowTitle("Loading ZIP")
                        progress.setMinimumDuration(0)
                        progress.setValue(0)
                        for idx, f in enumerate(all_files):
                            if progress.wasCanceled():
                                break
                            if f.lower().endswith('.dcm'):
                                dcm_files.append(f)
                            progress.setValue(idx + 1)
                            QApplication.processEvents()
                        progress.close()
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
            all_files = []
            for root, dirs, files in os.walk(dir_path):
                for name in files:
                    all_files.append(os.path.join(root, name))
            progress = QProgressDialog("Scanning directory for DICOM files...", "Cancel", 0, len(all_files), self)
            progress.setWindowTitle("Loading Directory")
            progress.setMinimumDuration(0)
            progress.setValue(0)
            for idx, f in enumerate(all_files):
                if progress.wasCanceled():
                    break
                if f.lower().endswith('.dcm'):
                    dcm_files.append(f)
                progress.setValue(idx + 1)
                QApplication.processEvents()
            progress.close()
            if not dcm_files:
                self.tag_view.setText("No DICOM (.dcm) files found in directory.")
                return
            self.loaded_files = [(f, None) for f in dcm_files]
            self.populate_tree(dcm_files)

    def show_tree_context_menu(self, pos: QPoint):
        item = self.tree.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        delete_action = QAction(QIcon.fromTheme("edit-delete"), "Delete", self)
        delete_action.triggered.connect(self.delete_selected_items)
        menu.addAction(delete_action)
        if item.depth() == 0:
            merge_action = QAction("Merge Patients", self)
            merge_action.triggered.connect(self.merge_patients)
            menu.addAction(merge_action)
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def filter_tree_items(self, text):
        # Simple filter: hide items that don't match text in any column
        def match(item):
            for col in range(item.columnCount()):
                if text.lower() in item.text(col).lower():
                    return True
            for i in range(item.childCount()):
                if match(item.child(i)):
                    return True
            return False

        def filter_item(item):
            visible = match(item) if text else True
            item.setHidden(not visible)
            for i in range(item.childCount()):
                filter_item(item.child(i))

        for i in range(self.tree.topLevelItemCount()):
            filter_item(self.tree.topLevelItem(i))

    def populate_tree(self, files):
        self.tree.clear()
        hierarchy = {}
        self.file_metadata = {}
        modalities = set()
        progress = QProgressDialog("Loading DICOM headers...", "Cancel", 0, len(files), self)
        progress.setWindowTitle("Loading DICOM Files")
        progress.setMinimumDuration(0)
        progress.setValue(0)
        for idx, f in enumerate(files):
            if progress.wasCanceled():
                break
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
            progress.setValue(idx + 1)
            QApplication.processEvents()
        progress.close()

        # --- Improved Tree Appearance: icons, bold fonts ---
        patient_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)
        study_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon)
        series_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DriveHDIcon)
        instance_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView)

        for patient, studies in hierarchy.items():
            patient_item = QTreeWidgetItem([patient])
            patient_item.setIcon(0, patient_icon)
            font = patient_item.font(0)
            font.setBold(True)
            patient_item.setFont(0, font)
            self.tree.addTopLevelItem(patient_item)
            for study, series_dict in studies.items():
                study_item = QTreeWidgetItem([patient, study])
                study_item.setIcon(1, study_icon)
                font2 = study_item.font(1)
                font2.setBold(True)
                study_item.setFont(1, font2)
                patient_item.addChild(study_item)
                for series, instances in series_dict.items():
                    series_item = QTreeWidgetItem([patient, study, series])
                    series_item.setIcon(2, series_icon)
                    study_item.addChild(series_item)
                    for instance, filepath in sorted(instances.items()):
                        instance_item = QTreeWidgetItem([patient, study, series, str(instance)])
                        instance_item.setIcon(3, instance_icon)
                        instance_item.setData(0, 1000, filepath)
                        series_item.addChild(instance_item)
        self.tree.expandAll()

        # --- Summary info ---
        patient_count = len(hierarchy)
        study_count = sum(len(studies) for studies in hierarchy.values())
        series_count = sum(len(series_dict) for studies in hierarchy.values() for series_dict in studies.values())
        instance_count = len(files)
        modality_str = ", ".join(sorted(modalities)) if modalities else "Unknown"
        total_bytes = sum(os.path.getsize(f) for f in files if os.path.exists(f))
        if total_bytes < 1024 * 1024 * 1024:
            size_str = f"{total_bytes / (1024 * 1024):.2f} MB"
        else:
            size_str = f"{total_bytes / (1024 * 1024 * 1024):.2f} GB"
        self.summary_label.setText(
            f"Patients: {patient_count} | Studies: {study_count} | Series: {series_count} | Instances: {instance_count} | Modalities: {modality_str} | Size: {size_str}"
        )
        self.statusBar().showMessage(f"Loaded {instance_count} instances.")

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
            dialog = QFileDialog(self, "Select Export Directory", self.default_export_dir)
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
            dialog = QFileDialog(self, "Save ZIP Archive", self.default_export_dir, "ZIP Archives (*.zip)")
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
        logging.info("DICOM send initiated")
        if AE is None or not STORAGE_CONTEXTS or VERIFICATION_SOP_CLASS is None:
            logging.error("pynetdicom not available")
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

        dlg = DicomSendDialog(self, config=self.dicom_send_config)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        calling_ae, remote_ae, host, port = dlg.get_params()
        logging.info(f"Sending {len(filepaths)} files to {host}:{port} AE={remote_ae}")

        ae = AE(ae_title=calling_ae)
        sop_classes = set()
        for fp in filepaths:
            try:
                ds = pydicom.dcmread(fp, stop_before_pixels=True)
                sop_classes.add(ds.SOPClassUID)
            except Exception as e:
                logging.error(f"Failed to read SOPClassUID from {fp}: {e}")
        if not sop_classes:
            QMessageBox.critical(self, "DICOM Send", "No valid SOP Class UIDs found in selected files.")
            return
        for cx in STORAGE_CONTEXTS:
            if getattr(cx, "abstract_syntax", None) in sop_classes:
                ae.add_requested_context(cx.abstract_syntax)
        ae.add_requested_context(VERIFICATION_SOP_CLASS)

        assoc = ae.associate(host, port, ae_title=remote_ae)
        if not assoc.is_established:
            logging.error(f"Association to {host}:{port} ({remote_ae}) failed")
            QMessageBox.critical(self, "DICOM Send", f"Association to {host}:{port} ({remote_ae}) failed.")
            return

        # --- Progress Dialog ---
        total_files = len(filepaths)
        total_bytes = sum(os.path.getsize(fp) for fp in filepaths if os.path.exists(fp))
        mb_total = total_bytes / (1024 * 1024)
        progress = QProgressDialog("Sending DICOM files...", "Cancel", 0, total_files, self)
        progress.setWindowTitle("DICOM Send Progress")
        progress.setMinimumDuration(0)
        progress.setValue(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.setLabelText(f"Sent 0/{total_files} images, 0.0/{mb_total:.1f} MB")

        sent = 0
        sent_bytes = 0
        failed = []
        failed_details = []
        for idx, fp in enumerate(filepaths):
            if progress.wasCanceled():
                failed_details.append("User cancelled operation.")
                break
            try:
                ds = pydicom.dcmread(fp)
                status = assoc.send_c_store(ds)
                status_code = getattr(status, "Status", None)
                file_size = os.path.getsize(fp) if os.path.exists(fp) else 0
                if status_code in [0x0000, 0xB000]:
                    sent += 1
                    sent_bytes += file_size
                else:
                    failed.append(fp)
                    failed_details.append(f"{os.path.basename(fp)}: status=0x{status_code:04X}")
            except Exception as e:
                failed.append(fp)
                failed_details.append(f"{os.path.basename(fp)}: {e}")
                logging.error(f"Send failed for {fp}: {e}", exc_info=True)
            # Update progress bar and label
            progress.setValue(idx + 1)
            mb_sent = sent_bytes / (1024 * 1024)
            progress.setLabelText(f"Sent {sent}/{total_files} images, {mb_sent:.1f}/{mb_total:.1f} MB")
            QApplication.processEvents()
        assoc.release()
        progress.close()
        msg = f"Sent: {sent}\nFailed: {len(failed)}"
        if failed_details:
            msg += "\n\nDetails:\n" + "\n".join(failed_details)
        logging.info(f"DICOM send complete: {msg}")
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

    def anonymise_selected(self):
        selected = self.tree.selectedItems()
        if not selected:
            QMessageBox.warning(self, "No Selection", "Please select a node in the tree to anonymise.")
            return
        # Always traverse up to the patient node (depth 0)
        tree_item = selected[0]
        while tree_item.parent():
            tree_item = tree_item.parent()
        filepaths = self._collect_instance_filepaths(tree_item)
        if not filepaths:
            QMessageBox.warning(self, "No Instances", "No DICOM instances found under this patient.")
            return

        # Confirm with user
        reply = QMessageBox.question(
            self,
            "Confirm Anonymization",
            f"This will irreversibly anonymize {len(filepaths)} files in-place.\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # Tags to anonymize (add more as needed)
        tags_to_blank = [
            (0x0010, 0x0010),  # PatientName
            (0x0010, 0x0020),  # PatientID
            (0x0010, 0x0030),  # PatientBirthDate
            (0x0010, 0x0032),  # PatientBirthTime
            (0x0010, 0x0040),  # PatientSex
            (0x0010, 0x1000),  # OtherPatientIDs
            (0x0010, 0x1001),  # OtherPatientNames
            (0x0010, 0x2160),  # EthnicGroup
            (0x0010, 0x4000),  # PatientComments
            (0x0008, 0x0090),  # ReferringPhysicianName
            (0x0008, 0x0050),  # AccessionNumber
            (0x0008, 0x0080),  # InstitutionName
            (0x0008, 0x0081),  # InstitutionAddress
            (0x0008, 0x1040),  # InstitutionalDepartmentName
            (0x0008, 0x1070),  # OperatorsName
            (0x0008, 0x1030),  # StudyDescription
            (0x0008, 0x103E),  # SeriesDescription
            (0x0020, 0x0010),  # StudyID
            (0x0020, 0x000D),  # StudyInstanceUID (will be replaced)
            (0x0020, 0x000E),  # SeriesInstanceUID (will be replaced)
            (0x0008, 0x0018),  # SOPInstanceUID (will be replaced)
        ]

        # Generate unique anonymization prefix
        now = datetime.datetime.now()
        anon_prefix = f"ANON_{now.strftime('%Y%m%d_%H%M%S')}"

        # Generate new UIDs for Study, Series, Instance
        new_study_uid = generate_uid()
        series_uid_map = {}
        instance_uid_map = {}

        updated = 0
        failed = []
        for idx, fp in enumerate(filepaths):
            try:
                ds = pydicom.dcmread(fp)
                # Fill tags with unique placeholders
                for tag in tags_to_blank:
                    if tag in ds:
                        # For UID fields, handle below
                        if tag in [(0x0020, 0x000D), (0x0020, 0x000E), (0x0008, 0x0018)]:
                            continue
                        # Use tag-specific placeholder, but truncate to 16 chars for VR SH
                        value = None
                        if tag == (0x0010, 0x0010):  # PatientName
                            value = f"{anon_prefix}_PATIENT"
                        elif tag == (0x0010, 0x0020):  # PatientID
                            value = f"{anon_prefix}_PID"
                        elif tag == (0x0010, 0x0030):  # PatientBirthDate
                            value = "19000101"
                        elif tag == (0x0010, 0x0032):  # PatientBirthTime
                            value = "000000"
                        elif tag == (0x0010, 0x0040):  # PatientSex
                            value = "O"
                        elif tag == (0x0020, 0x0010):  # StudyID
                            value = f"{anon_prefix}_STUDY"
                        elif tag == (0x0008, 0x0050):  # AccessionNumber
                            value = f"{anon_prefix}_ACC"
                        elif tag == (0x0008, 0x1030):  # StudyDescription
                            value = f"{anon_prefix}_STUDY_DESC"
                        elif tag == (0x0008, 0x103E):  # SeriesDescription
                            value = f"{anon_prefix}_SERIES_DESC"
                        else:
                            value = f"{anon_prefix}_{idx}"

                        # Truncate value for VR SH (Short String, max 16 chars)
                        vr = ds[tag].VR if hasattr(ds[tag], "VR") else None
                        if vr == "SH" and len(value) > 16:
                            value = value[:16]
                        ds[tag].value = value
                # Replace StudyInstanceUID
                ds.StudyInstanceUID = new_study_uid
                # Replace SeriesInstanceUID (unique per series)
                old_series_uid = getattr(ds, "SeriesInstanceUID", None)
                if old_series_uid not in series_uid_map:
                    series_uid_map[old_series_uid] = generate_uid()
                ds.SeriesInstanceUID = series_uid_map[old_series_uid]
                # Replace SOPInstanceUID (unique per instance)
                old_instance_uid = getattr(ds, "SOPInstanceUID", None)
                if old_instance_uid not in instance_uid_map:
                    instance_uid_map[old_instance_uid] = generate_uid()
                ds.SOPInstanceUID = instance_uid_map[old_instance_uid]
                # Optionally, update MediaStorageSOPInstanceUID if present
                if hasattr(ds, "file_meta") and hasattr(ds.file_meta, "MediaStorageSOPInstanceUID"):
                    ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
                ds.save_as(fp)
                updated += 1
            except Exception as e:
                failed.append(f"{os.path.basename(fp)}: {e}")

        msg = f"Anonymization complete.\nFiles updated: {updated}\nFailed: {len(failed)}"
        if failed:
            msg += "\n\nDetails:\n" + "\n".join(failed)
        QMessageBox.information(self, "Anonymization", msg)
        self.display_selected_tree_file()

    def merge_patients(self):
        # Enable multi-selection for patient nodes
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.MultiSelection)
        selected = self.tree.selectedItems()
        # Only allow patient-level nodes (depth 0)
        patient_nodes = [item for item in selected if item.depth() == 0]
        if len(patient_nodes) < 2:
            QMessageBox.warning(self, "Merge Patients", "Select at least two patient nodes to merge.\n\nHold Ctrl or Shift to select multiple patients.")
            return

        # Gather patient labels and ask user which to keep
        patient_labels = [item.text(0) for item in patient_nodes]
        primary_idx, ok = QInputDialog.getItem(
            self, "Merge Patients", "Select primary patient (whose metadata to keep):", patient_labels, 0, False
        )
        if not ok:
            return
        primary_label = primary_idx
        primary_node = next(item for item in patient_nodes if item.text(0) == primary_label)

        # Get PatientID/PatientName from primary
        primary_fp = None
        for i in range(primary_node.childCount()):
            study_item = primary_node.child(i)
            for j in range(study_item.childCount()):
                series_item = study_item.child(j)
                for k in range(series_item.childCount()):
                    instance_item = series_item.child(k)
                    fp = instance_item.data(0, 1000)
                    if fp:
                        primary_fp = fp
                        break
                if primary_fp:
                    break
            if primary_fp:
                break
        if not primary_fp:
            QMessageBox.warning(self, "Merge Patients", "Could not find a file for the primary patient.")
            return
        try:
            ds_primary = pydicom.dcmread(primary_fp, stop_before_pixels=True)
            primary_id = getattr(ds_primary, "PatientID", "")
            primary_name = getattr(ds_primary, "PatientName", "")
        except Exception as e:
            QMessageBox.critical(self, "Merge Patients", f"Failed to read primary patient file: {e}")
            return

        # Collect all files under secondary patients
        files_to_update = []
        for node in patient_nodes:
            if node is primary_node:
                continue
            for i in range(node.childCount()):
                study_item = node.child(i)
                for j in range(study_item.childCount()):
                    series_item = study_item.child(j)
                    for k in range(series_item.childCount()):
                        instance_item = series_item.child(k)
                        fp = instance_item.data(0, 1000)
                        if fp:
                            files_to_update.append(fp)

        # Confirm
        reply = QMessageBox.question(
            self,
            "Confirm Merge",
            f"This will update {len(files_to_update)} files to PatientID '{primary_id}' and PatientName '{primary_name}'.\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # Update files with progress dialog
        updated = 0
        failed = []
        progress = QProgressDialog("Merging patients...", "Cancel", 0, len(files_to_update), self)
        progress.setWindowTitle("Merging Patients")
        progress.setMinimumDuration(0)
        progress.setValue(0)
        for idx, fp in enumerate(files_to_update):
            if progress.wasCanceled():
                break
            try:
                ds = pydicom.dcmread(fp)
                ds.PatientID = primary_id
                ds.PatientName = primary_name
                ds.save_as(fp)
                updated += 1
            except Exception as e:
                failed.append(f"{os.path.basename(fp)}: {e}")
            progress.setValue(idx + 1)
            QApplication.processEvents()
        progress.close()

        # Remove merged patient nodes from tree and reload
        for node in patient_nodes:
            if node is not primary_node:
                idx = self.tree.indexOfTopLevelItem(node)
                self.tree.takeTopLevelItem(idx)

        msg = f"Merged {len(patient_nodes)} patients.\nFiles updated: {updated}\nFailed: {len(failed)}"
        if failed:
            msg += "\n\nDetails:\n" + "\n".join(failed)
        QMessageBox.information(self, "Merge Patients", msg)
        # Optionally, reload tree from loaded_files to refresh summary
        self.populate_tree([f for f, _ in self.loaded_files])
        # Restore standard selection behavior
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)

    def delete_selected_items(self):
        selected = self.tree.selectedItems()
        if not selected:
            QMessageBox.warning(self, "Delete", "Please select one or more items to delete.")
            return

        # Collect all unique filepaths to delete, and count by type
        files_to_delete = set()
        patient_count = study_count = series_count = instance_count = 0
        for item in selected:
            depth = item.depth()
            if depth == 0:
                # Patient
                patient_count += 1
                files_to_delete.update(self._collect_instance_filepaths(item))
            elif depth == 1:
                # Study
                study_count += 1
                files_to_delete.update(self._collect_instance_filepaths(item))
            elif depth == 2:
                # Series
                series_count += 1
                files_to_delete.update(self._collect_instance_filepaths(item))
            elif depth == 3:
                # Instance
                instance_count += 1
                fp = item.data(0, 1000)
                if fp:
                    files_to_delete.add(fp)

        if not files_to_delete:
            QMessageBox.warning(self, "Delete", "No files found to delete for the selected items.")
            return

        # Confirmation dialog
        msg = []
        if patient_count:
            msg.append(f"{patient_count} patient(s)")
        if study_count:
            msg.append(f"{study_count} study(ies)")
        if series_count:
            msg.append(f"{series_count} series")
        if instance_count:
            msg.append(f"{instance_count} instance(s)")
        msg_str = ", ".join(msg)
        confirm = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Delete {msg_str}?\nThis will permanently delete {len(files_to_delete)} file(s) from disk. This cannot be undone.\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        # Progress dialog for deletion
        progress = QProgressDialog("Deleting files...", "Cancel", 0, len(files_to_delete), self)
        progress.setWindowTitle("Deleting")
        progress.setMinimumDuration(0)
        progress.setValue(0)
        deleted = 0
        failed = []
        files_to_delete = list(files_to_delete)
        for idx, fp in enumerate(files_to_delete):
            if progress.wasCanceled():
                break
            try:
                if os.path.exists(fp):
                    os.remove(fp)
                # Remove from loaded_files
                self.loaded_files = [t for t in self.loaded_files if t[0] != fp]
                deleted += 1
            except Exception as e:
                failed.append(f"{os.path.basename(fp)}: {e}")
            progress.setValue(idx + 1)
            QApplication.processEvents()
        progress.close()

        # Remove deleted nodes from tree
        for item in selected:
            parent = item.parent()
            if parent:
                parent.removeChild(item)
            else:
                idx = self.tree.indexOfTopLevelItem(item)
                self.tree.takeTopLevelItem(idx)

        # Refresh UI
        self.populate_tree([f for f, _ in self.loaded_files])
        self.tag_table.setRowCount(0)
        self.image_label.clear()
        self.image_label.setVisible(False)
        self.current_filepath = None
        self.current_ds = None

        msg = f"Deleted {deleted} file(s)."
        if failed:
            msg += "\n\nFailed:\n" + "\n".join(failed)
        QMessageBox.information(self, "Delete", msg)

