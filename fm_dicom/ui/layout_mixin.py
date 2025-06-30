"""
Mixin class for MainWindow layout and widget setup.

This mixin provides the EXACT same UI layout as the original MainWindow,
preserving all widgets, buttons, and functionality exactly as before.
"""

import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTreeWidget, QTreeWidgetItem,
    QTableWidget, QTableWidgetItem, QLineEdit, QLabel, QGroupBox, QFrame,
    QStatusBar, QPushButton, QComboBox, QCheckBox, QSizePolicy, QGridLayout,
    QToolBar
)
from PyQt6.QtGui import QPixmap, QImage, QIcon, QAction
from PyQt6.QtCore import Qt, QPoint, QSize


class LayoutMixin:
    """Mixin for setting up MainWindow layout and widgets - EXACT match to original"""
    
    def setup_ui_layout(self):
        """Setup the main UI layout exactly as in original MainWindow"""
        # Window setup - EXACT match to original
        self.setWindowTitle("FM DICOM Tag Editor")
        w, h = self.config.get("window_size", [1200, 800])
        self.resize(w, h)
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Toolbar - EXACT match to original
        toolbar = QToolBar("Main Toolbar")
        toolbar.setIconSize(QSize(20, 20))
        self.addToolBar(toolbar)

        open_icon = self.style().standardIcon(self.style().StandardPixmap.SP_DialogOpenButton)
        save_icon = self.style().standardIcon(self.style().StandardPixmap.SP_DialogSaveButton)
        delete_icon = self.style().standardIcon(self.style().StandardPixmap.SP_TrashIcon)
        merge_icon = self.style().standardIcon(self.style().StandardPixmap.SP_FileDialogNewFolder)
        expand_icon = self.style().standardIcon(self.style().StandardPixmap.SP_ArrowDown)
        collapse_icon = self.style().standardIcon(self.style().StandardPixmap.SP_ArrowUp)

        act_open = QAction(open_icon, "Open", self)
        act_open.triggered.connect(self.open_file)
        toolbar.addAction(act_open)

        act_open_dir = QAction(QIcon.fromTheme("folder"), "Open Directory", self)
        act_open_dir.triggered.connect(self.open_directory)
        toolbar.addAction(act_open_dir)

        act_delete = QAction(delete_icon, "Delete", self)
        act_delete.triggered.connect(self.delete_selected_items)
        toolbar.addAction(act_delete)

        act_expand = QAction(expand_icon, "Expand All", self)
        act_expand.triggered.connect(self.tree_expand_all)
        toolbar.addAction(act_expand)

        act_collapse = QAction(collapse_icon, "Collapse All", self)
        act_collapse.triggered.connect(self.tree_collapse_all)
        toolbar.addAction(act_collapse)
        toolbar.addSeparator()

        validate_icon = self.style().standardIcon(self.style().StandardPixmap.SP_DialogApplyButton)
        act_validate = QAction(validate_icon, "Validate", self)
        act_validate.triggered.connect(self.validate_dicom_files)
        toolbar.addAction(act_validate)

        # Analyze Files button
        analyze_icon = self.style().standardIcon(self.style().StandardPixmap.SP_FileDialogInfoView)
        act_analyze = QAction(analyze_icon, "Analyze Files", self)
        act_analyze.triggered.connect(self.analyze_all_loaded_files)
        toolbar.addAction(act_analyze)

        # Test Performance button
        performance_icon = self.style().standardIcon(self.style().StandardPixmap.SP_ComputerIcon)
        act_performance = QAction(performance_icon, "Test Performance", self)
        act_performance.triggered.connect(self.test_loading_performance)
        toolbar.addAction(act_performance)

        toolbar.addSeparator()

        template_icon = self.style().standardIcon(self.style().StandardPixmap.SP_FileDialogDetailedView)
        act_templates = QAction(template_icon, "Manage Templates", self)
        act_templates.triggered.connect(self.manage_templates)
        toolbar.addAction(act_templates)

        logs_icon = self.style().standardIcon(self.style().StandardPixmap.SP_FileDialogDetailedView)
        act_show_logs = QAction(logs_icon, "Show Logs", self)
        act_show_logs.triggered.connect(self.show_log_viewer)
        toolbar.addAction(act_show_logs)

        settings_icon = self.style().standardIcon(self.style().StandardPixmap.SP_ComputerIcon)
        act_settings = QAction(settings_icon, "Settings", self)
        act_settings.triggered.connect(self.open_settings_editor)
        toolbar.addAction(act_settings)

        # Main Splitter - EXACT match to original
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        tree_search_layout = QHBoxLayout()
        self.tree_search_bar = QLineEdit()
        self.tree_search_bar.setPlaceholderText("Search patients/studies/series/instances...")
        self.tree_search_bar.textChanged.connect(self.filter_tree_items)
        tree_search_layout.addWidget(self.tree_search_bar)
        left_layout.addLayout(tree_search_layout)

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
        show_image_preview = bool(self.config.get("show_image_preview", False))
        self.preview_toggle.setChecked(show_image_preview)
        self.preview_toggle.stateChanged.connect(self.save_preview_toggle_state_and_refresh_display)
        left_layout.addWidget(self.preview_toggle)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumHeight(256)
        self.image_label.setVisible(show_image_preview)  # Set initial visibility based on config
        self.image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        left_layout.addWidget(self.image_label)
        main_splitter.addWidget(left_widget)

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
        self.tag_table.setColumnWidth(0, 110)
        self.tag_table.setColumnWidth(1, 220)
        self.tag_table.setColumnWidth(2, 260)
        self.tag_table.setColumnWidth(3, 160)
        self.tag_table.horizontalHeader().setStretchLastSection(True)
        self.tag_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.tag_table.setAlternatingRowColors(True)
        # Original stylesheet
        self.tag_table.setStyleSheet("""
            QTableWidget {
                background-color: #23272a;
                alternate-background-color: #2c2f33;
                color: #f5f5f5;
                selection-background-color: #508cff;
                selection-color: #fff;
                gridline-color: #444;
            }
            QHeaderView::section {
                background-color: #202225;
                color: #f5f5f5;
                font-weight: bold;
            }
        """)
        self.tag_table.cellActivated.connect(self._populate_new_value_on_edit)
        self.tag_table.cellClicked.connect(self._populate_new_value_on_edit)
        right_layout.addWidget(self.tag_table)
        main_splitter.addWidget(right_widget)
        
        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 2)
        layout.addWidget(main_splitter)

        # Grouped Button Layouts - EXACT match to original
        btn_grid = QGridLayout()
        btn_grid.setHorizontalSpacing(32)
        btn_grid.setVerticalSpacing(10)

        edit_group = QGroupBox("Editing")
        edit_layout = QVBoxLayout()
        edit_layout.setSpacing(10)
        self.edit_level_combo = QComboBox()
        self.edit_level_combo.addItems(["Instance", "Series", "Study", "Patient"])
        self.edit_level_combo.setCurrentText("Series")
        edit_layout.addWidget(self.edit_level_combo)
        self.save_btn = QPushButton(save_icon, "Submit Changes")
        self.save_btn.clicked.connect(self.save_tag_changes)
        edit_layout.addWidget(self.save_btn)
        self.anon_btn = QPushButton("Anonymise Patient")
        self.anon_btn.clicked.connect(self.anonymise_selected)
        edit_layout.addWidget(self.anon_btn)
        edit_group.setLayout(edit_layout)

        export_group = QGroupBox("Export/Send")
        export_layout = QVBoxLayout()
        export_layout.setSpacing(10)
        self.save_as_btn = QPushButton(save_icon, "Save As")
        self.save_as_btn.clicked.connect(self.save_as)
        export_layout.addWidget(self.save_as_btn)
        self.dicom_send_btn = QPushButton("DICOM Send")
        self.dicom_send_btn.clicked.connect(self.dicom_send)
        export_layout.addWidget(self.dicom_send_btn)
        export_group.setLayout(export_layout)

        tag_group = QGroupBox("Tags/Batch")
        tag_layout = QVBoxLayout()
        tag_layout.setSpacing(10)
        self.edit_btn = QPushButton("New Tag")
        self.edit_btn.clicked.connect(self.edit_tag)
        tag_layout.addWidget(self.edit_btn)
        
        # Add missing buttons from original
        self.batch_edit_btn = QPushButton("Batch New Tag")
        self.batch_edit_btn.clicked.connect(self.batch_edit_tag)
        tag_layout.addWidget(self.batch_edit_btn)
        
        self.validate_btn = QPushButton("Validate Selected")
        self.validate_btn.clicked.connect(self.validate_dicom_files)
        tag_layout.addWidget(self.validate_btn)
        tag_group.setLayout(tag_layout)

        # Missing standalone buttons
        self.merge_patients_btn = QPushButton(merge_icon, "Merge")
        self.merge_patients_btn.clicked.connect(self.merge_patients)
        self.merge_patients_btn.setMinimumWidth(120)
        self.merge_patients_btn.setMinimumHeight(36)
        
        self.delete_btn = QPushButton(delete_icon, "Delete")
        self.delete_btn.setToolTip("Delete selected patients, studies, series, or instances")
        self.delete_btn.clicked.connect(self.delete_selected_items)
        self.delete_btn.setMinimumWidth(80)
        self.delete_btn.setMinimumHeight(36)

        # Add groups to grid - EXACT match to original positions
        btn_grid.addWidget(edit_group, 0, 0, 2, 1)
        btn_grid.addWidget(export_group, 0, 1)
        btn_grid.addWidget(tag_group, 0, 2)
        btn_grid.addWidget(self.merge_patients_btn, 1, 1, alignment=Qt.AlignmentFlag.AlignLeft)
        btn_grid.addWidget(self.delete_btn, 1, 2, alignment=Qt.AlignmentFlag.AlignLeft)
        
        # Create button bar with proper constraints
        btn_bar = QWidget()
        btn_bar.setLayout(btn_grid)
        btn_bar.setMaximumHeight(170)  # Limit button area height
        btn_bar.setStyleSheet(
            "QGroupBox { font-weight: bold; margin-top: 18px; }"
            "QPushButton { min-height: 36px; min-width: 120px; font-size: 13px; }"
        )
        layout.addWidget(btn_bar)

        # Status bar - EXACT match to original
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

        # Summary label from original
        self.summary_label = QLineEdit()
        self.summary_label.setReadOnly(True)
        self.summary_label.setStyleSheet(
            "background: #202225; color: #f5f5f5; border: none; font-weight: bold;"
        )
        layout.addWidget(self.summary_label)

        logging.info("MainWindow UI initialized")
    
    # Utility methods that were in original
    def tree_expand_all(self):
        """Expand all tree items"""
        if hasattr(self, 'tree'):
            self.tree.expandAll()
    
    def tree_collapse_all(self):
        """Collapse all tree items"""  
        if hasattr(self, 'tree'):
            self.tree.collapseAll()
    
    def save_preview_toggle_state_and_refresh_display(self, state):
        """Handle preview toggle - exact match to original"""
        show_preview = state == Qt.CheckState.Checked.value
        self.config["show_image_preview"] = show_preview
        self.image_label.setVisible(show_preview)
        
        if show_preview and hasattr(self, 'dicom_manager') and self.dicom_manager.current_file:
            # Force UI update before displaying image
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()
            self.dicom_manager.display_image()
        elif not show_preview:
            # Clear image when hiding
            self.image_label.clear()
            self.image_label.setText("Image preview disabled")
    
    def _populate_new_value_on_edit(self, row, column):
        """Populate new value on edit - exact match to original"""
        if column == 2:  # Current value column
            current_item = self.tag_table.item(row, column)
            new_value_item = self.tag_table.item(row, 3)
            if current_item and new_value_item and not new_value_item.text():
                new_value_item.setText(current_item.text())