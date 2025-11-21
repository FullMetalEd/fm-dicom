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
    QToolBar, QMenuBar, QMenu
)
from PyQt6.QtGui import QPixmap, QImage, QIcon, QAction, QKeySequence
from PyQt6.QtCore import Qt, QPoint, QSize

from fm_dicom import __version__
from fm_dicom.ui.icon_loader import themed_icon


class LayoutMixin:
    """Mixin for setting up MainWindow layout and widgets - EXACT match to original"""
    
    def setup_ui_layout(self):
        """Setup the main UI layout exactly as in original MainWindow"""
        # Window setup - EXACT match to original
        self.setWindowTitle("FM DICOM Tag Editor")
        w, h = self.config.get("window_size", [1200, 800])
        self.resize(w, h)
        central = QWidget()
        central.setObjectName("CentralWidget")
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        # Modern Menu Bar
        self.setup_menu_bar()

        # Streamlined Toolbar - Essential tools only
        toolbar = QToolBar("Main Toolbar")
        toolbar.setIconSize(QSize(24, 24))  # Slightly larger for better visibility
        self.addToolBar(toolbar)

        style = self.style()

        # Essential file operations
        open_icon = themed_icon(
            "open-file",
            style.standardIcon(style.StandardPixmap.SP_DialogOpenButton)
        )
        act_open = QAction(open_icon, "Open File", self)
        act_open.setShortcut(QKeySequence.StandardKey.Open)
        act_open.setToolTip("Open a DICOM file (Ctrl+O)")
        act_open.triggered.connect(self.open_file)
        toolbar.addAction(act_open)

        open_dir_icon = themed_icon(
            "open-folder",
            style.standardIcon(style.StandardPixmap.SP_DirOpenIcon)
        )
        act_open_dir = QAction(open_dir_icon, "Open Directory", self)
        act_open_dir.setShortcut(QKeySequence("Ctrl+Shift+O"))
        act_open_dir.setToolTip("Open a directory (Ctrl+Shift+O)")
        act_open_dir.triggered.connect(self.open_directory)
        toolbar.addAction(act_open_dir)

        toolbar.addSeparator()

        # Save changes
        save_icon = themed_icon(
            "save",
            style.standardIcon(style.StandardPixmap.SP_DialogSaveButton)
        )
        self.toolbar_save_action = QAction(save_icon, "Save Changes", self)
        self.toolbar_save_action.setShortcut(QKeySequence.StandardKey.Save)
        self.toolbar_save_action.setToolTip("Save tag changes (Ctrl+S)")
        self.toolbar_save_action.setEnabled(False)  # Disabled by default
        self.toolbar_save_action.triggered.connect(self.save_tag_changes)
        toolbar.addAction(self.toolbar_save_action)

        toolbar.addSeparator()

        # Tree refresh
        refresh_icon = themed_icon(
            "refresh",
            style.standardIcon(style.StandardPixmap.SP_BrowserReload)
        )
        act_refresh = QAction(refresh_icon, "Refresh", self)
        act_refresh.setShortcut(QKeySequence.StandardKey.Refresh)
        act_refresh.setToolTip("Refresh tree from disk (F5)")
        act_refresh.triggered.connect(self._refresh_tree_view)
        toolbar.addAction(act_refresh)

        toolbar.addSeparator()

        # Logs and Settings
        logs_icon = themed_icon(
            "logs",
            style.standardIcon(style.StandardPixmap.SP_MessageBoxInformation)
        )
        act_show_logs = QAction(logs_icon, "Show Logs", self)
        act_show_logs.setShortcut(QKeySequence("Ctrl+L"))
        act_show_logs.setToolTip("View application logs (Ctrl+L)")
        act_show_logs.triggered.connect(self.show_log_viewer)
        toolbar.addAction(act_show_logs)

        settings_icon = themed_icon(
            "settings",
            style.standardIcon(style.StandardPixmap.SP_ComputerIcon)
        )
        act_settings = QAction(settings_icon, "Settings", self)
        act_settings.setShortcut(QKeySequence.StandardKey.Preferences)
        act_settings.setToolTip("Open preferences")
        act_settings.triggered.connect(self.open_settings_editor)
        toolbar.addAction(act_settings)

        # Main Splitter - EXACT match to original
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.setHandleWidth(12)
        main_splitter.setChildrenCollapsible(False)
        left_widget = QWidget()
        left_widget.setObjectName("SurfacePanel")
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(12, 12, 12, 12)
        left_layout.setSpacing(12)

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
        self.image_label.setObjectName("ImagePreview")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumHeight(256)
        self.image_label.setVisible(show_image_preview)  # Set initial visibility based on config
        self.image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        if show_image_preview:
            self.image_label.setText("Select an instance to preview")
        else:
            self.image_label.setText("Image preview disabled")
        left_layout.addWidget(self.image_label)
        main_splitter.addWidget(left_widget)

        right_widget = QWidget()
        right_widget.setObjectName("SurfacePanel")
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(12, 12, 12, 12)
        right_layout.setSpacing(12)

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
        self.tag_table.cellActivated.connect(self._populate_new_value_on_edit)
        self.tag_table.cellClicked.connect(self._populate_new_value_on_edit)
        # Add context menu support
        self.tag_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tag_table.customContextMenuRequested.connect(self.show_tag_table_context_menu)
        right_layout.addWidget(self.tag_table)
        main_splitter.addWidget(right_widget)
        
        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 2)
        layout.addWidget(main_splitter)

        # Compact Edit Level Control Bar (replacing button groups)
        edit_control_layout = QHBoxLayout()
        edit_control_layout.setContentsMargins(12, 4, 12, 4)
        edit_control_layout.setSpacing(12)
        
        # Edit level selector with label
        edit_level_label = QLabel("Edit Level:")
        edit_level_label.setObjectName("FormLabel")
        edit_control_layout.addWidget(edit_level_label)
        
        self.edit_level_combo = QComboBox()
        self.edit_level_combo.addItems(["Instance", "Series", "Study", "Patient"])
        self.edit_level_combo.setCurrentText(self.config.get("default_edit_level", "Series"))
        self.edit_level_combo.setToolTip("Select the level at which tag changes will be applied")
        edit_control_layout.addWidget(self.edit_level_combo)
        
        edit_control_layout.addStretch()  # Push everything to the left
        
        # Create the control bar widget
        edit_control_bar = QWidget()
        edit_control_bar.setObjectName("ControlBar")
        edit_control_bar.setLayout(edit_control_layout)
        edit_control_bar.setMaximumHeight(40)
        layout.addWidget(edit_control_bar)
        
        # Create placeholder buttons for compatibility (hidden/unused)
        # These are needed for existing code that references them
        self.save_btn = QPushButton()  # Hidden placeholder
        self.save_btn.setVisible(False)
        self.anon_btn = QPushButton()  # Hidden placeholder  
        self.anon_btn.setVisible(False)
        self.save_as_btn = QPushButton()  # Hidden placeholder
        self.save_as_btn.setVisible(False)
        self.dicom_send_btn = QPushButton()  # Hidden placeholder
        self.dicom_send_btn.setVisible(False)
        self.edit_btn = QPushButton()  # Hidden placeholder
        self.edit_btn.setVisible(False)
        self.batch_edit_btn = QPushButton()  # Hidden placeholder
        self.batch_edit_btn.setVisible(False)
        self.validate_btn = QPushButton()  # Hidden placeholder
        self.validate_btn.setVisible(False)
        self.merge_patients_btn = QPushButton()  # Hidden placeholder
        self.merge_patients_btn.setVisible(False)
        self.delete_btn = QPushButton()  # Hidden placeholder
        self.delete_btn.setVisible(False)

        # Enhanced Status Bar
        self.status_bar = QStatusBar()
        self.status_bar.setObjectName("PrimaryStatusBar")
        self.setStatusBar(self.status_bar)
        
        # Left: Current operation status
        self.status_bar.showMessage("Ready")
        
        # Center: File count and selection info
        self.file_info_label = QLabel("No files loaded")
        self.status_bar.addPermanentWidget(self.file_info_label)
        
        # Right: Progress indicator (initially hidden)
        self.progress_label = QLabel("")
        self.progress_label.setVisible(False)
        self.status_bar.addPermanentWidget(self.progress_label)

        # Enhanced Summary Display (replacing simple summary label)
        self.summary_display = QWidget()
        self.summary_display.setObjectName("SummaryBar")
        self.summary_display.setMaximumHeight(35)
        summary_layout = QHBoxLayout(self.summary_display)
        summary_layout.setContentsMargins(10, 5, 10, 5)
        
        # Summary text
        self.summary_label = QLabel("No DICOM files loaded")
        self.summary_label.setObjectName("SummaryLabel")
        summary_layout.addWidget(self.summary_label)
        
        summary_layout.addStretch()
        
        # Quick stats display
        self.stats_label = QLabel("")
        self.stats_label.setObjectName("SummaryStats")
        summary_layout.addWidget(self.stats_label)
        
        layout.addWidget(self.summary_display)

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
    
    def setup_menu_bar(self):
        """Setup modern menu bar with comprehensive menu structure"""
        menubar = self.menuBar()
        
        # File Menu
        file_menu = menubar.addMenu("&File")
        
        # Open actions
        open_action = QAction("&Open File...", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.setStatusTip("Open a DICOM file")
        open_action.triggered.connect(self.open_file)
        file_menu.addAction(open_action)
        
        open_dir_action = QAction("Open &Directory...", self)
        open_dir_action.setShortcut(QKeySequence("Ctrl+Shift+O"))
        open_dir_action.setStatusTip("Open a directory containing DICOM files")
        open_dir_action.triggered.connect(self.open_directory)
        file_menu.addAction(open_dir_action)

        file_menu.addSeparator()

        # Add Menu (for appending files to existing dataset)
        add_menu = menubar.addMenu("&Add")

        # Add File
        add_file_action = QAction("&Add File...", self)
        add_file_action.setShortcut(QKeySequence("Ctrl+Shift+A"))
        add_file_action.setStatusTip("Add a DICOM file to currently loaded files")
        add_file_action.triggered.connect(self.append_file)
        add_menu.addAction(add_file_action)

        # Add Directory
        add_dir_action = QAction("Add &Directory...", self)
        add_dir_action.setShortcut(QKeySequence("Ctrl+Shift+D"))
        add_dir_action.setStatusTip("Add a directory containing DICOM files to currently loaded files")
        add_dir_action.triggered.connect(self.append_directory)
        add_menu.addAction(add_dir_action)

        add_menu.addSeparator()

        # Add ZIP Archive
        add_zip_action = QAction("Add &ZIP Archive...", self)
        add_zip_action.setStatusTip("Add DICOM files from a ZIP archive to currently loaded files")
        add_zip_action.triggered.connect(self.append_file)  # ZIP files are handled by append_file
        add_menu.addAction(add_zip_action)

        file_menu.addSeparator()
        
        # Save actions
        save_action = QAction("&Save Changes", self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.setStatusTip("Save tag changes to current files")
        save_action.triggered.connect(self.save_tag_changes)
        file_menu.addAction(save_action)
        
        save_as_action = QAction("Save &As...", self)
        save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        save_as_action.setStatusTip("Save selected files to a new location")
        save_as_action.triggered.connect(self.save_as)
        file_menu.addAction(save_as_action)
        
        file_menu.addSeparator()
        
        # Exit
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        exit_action.setStatusTip("Exit the application")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Edit Menu
        edit_menu = menubar.addMenu("&Edit")
        
        # Tag actions
        new_tag_action = QAction("&New Tag...", self)
        new_tag_action.setShortcut(QKeySequence("Ctrl+T"))
        new_tag_action.setStatusTip("Add a new tag to the current instance")
        new_tag_action.triggered.connect(self.edit_tag)
        edit_menu.addAction(new_tag_action)
        
        batch_tag_action = QAction("&Batch New Tag...", self)
        batch_tag_action.setShortcut(QKeySequence("Ctrl+Shift+T"))
        batch_tag_action.setStatusTip("Add a new tag to multiple selected files")
        batch_tag_action.triggered.connect(self.batch_edit_tag)
        edit_menu.addAction(batch_tag_action)
        
        edit_menu.addSeparator()
        
        # Patient operations
        anonymize_action = QAction("&Anonymize Patient", self)
        anonymize_action.setShortcut(QKeySequence("Ctrl+A"))
        anonymize_action.setStatusTip("Anonymize selected patient data")
        anonymize_action.triggered.connect(self.anonymise_selected)
        edit_menu.addAction(anonymize_action)
        
        merge_action = QAction("&Merge Selected", self)
        merge_action.setShortcut(QKeySequence("Ctrl+M"))
        merge_action.setStatusTip("Merge selected patients or studies")
        merge_action.triggered.connect(self.merge_patients)
        edit_menu.addAction(merge_action)
        
        edit_menu.addSeparator()
        
        # Delete
        delete_action = QAction("&Delete Selected", self)
        delete_action.setShortcut(QKeySequence.StandardKey.Delete)
        delete_action.setStatusTip("Delete selected items")
        delete_action.triggered.connect(self.delete_selected_items)
        edit_menu.addAction(delete_action)
        
        edit_menu.addSeparator()
        
        # Clear search
        clear_search_action = QAction("&Clear Search Filter", self)
        clear_search_action.setShortcut(QKeySequence("Escape"))
        clear_search_action.setStatusTip("Clear the current search filter")
        clear_search_action.triggered.connect(self._clear_all_search_filters)
        edit_menu.addAction(clear_search_action)
        
        # View Menu
        view_menu = menubar.addMenu("&View")
        
        # Image preview toggle
        self.preview_action = QAction("Show &Image Preview", self)
        self.preview_action.setCheckable(True)
        self.preview_action.setShortcut(QKeySequence("Ctrl+I"))
        self.preview_action.setStatusTip("Toggle image preview panel")
        self.preview_action.triggered.connect(self._toggle_image_preview)
        view_menu.addAction(self.preview_action)
        
        view_menu.addSeparator()
        
        # Tree operations
        expand_action = QAction("&Expand All", self)
        expand_action.setShortcut(QKeySequence("Ctrl+E"))
        expand_action.setStatusTip("Expand all tree items")
        expand_action.triggered.connect(self.tree_expand_all)
        view_menu.addAction(expand_action)
        
        collapse_action = QAction("&Collapse All", self)
        collapse_action.setShortcut(QKeySequence("Ctrl+Shift+E"))
        collapse_action.setStatusTip("Collapse all tree items")
        collapse_action.triggered.connect(self.tree_collapse_all)
        view_menu.addAction(collapse_action)
        
        view_menu.addSeparator()
        
        # Refresh
        refresh_action = QAction("&Refresh Tree", self)
        refresh_action.setShortcut(QKeySequence.StandardKey.Refresh)
        refresh_action.setStatusTip("Refresh the tree from disk")
        refresh_action.triggered.connect(self._refresh_tree_view)
        view_menu.addAction(refresh_action)
        
        view_menu.addSeparator()
        
        # Logs and Settings
        logs_action = QAction("Show &Logs", self)
        logs_action.setShortcut(QKeySequence("Ctrl+L"))
        logs_action.setStatusTip("View application logs")
        logs_action.triggered.connect(self.show_log_viewer)
        view_menu.addAction(logs_action)
        
        settings_action = QAction("&Preferences...", self)
        settings_action.setShortcut(QKeySequence.StandardKey.Preferences)
        settings_action.setStatusTip("Open application settings")
        settings_action.triggered.connect(self.open_settings_editor)
        view_menu.addAction(settings_action)
        
        # Tools Menu
        tools_menu = menubar.addMenu("&Tools")
        
        validate_action = QAction("&Validate Selected", self)
        validate_action.setShortcut(QKeySequence("Ctrl+V"))
        validate_action.setStatusTip("Validate selected DICOM files")
        validate_action.triggered.connect(self.validate_dicom_files)
        tools_menu.addAction(validate_action)
        
        tools_menu.addSeparator()
        
        templates_action = QAction("Manage &Templates...", self)
        templates_action.setStatusTip("Manage anonymization templates")
        templates_action.triggered.connect(self.manage_templates)
        tools_menu.addAction(templates_action)
        
        tools_menu.addSeparator()
        
        tag_search_action = QAction("Tag &Search...", self)
        tag_search_action.setShortcut(QKeySequence.StandardKey.Find)
        tag_search_action.setStatusTip("Search for DICOM tags")
        tag_search_action.triggered.connect(self._open_tag_search)
        tools_menu.addAction(tag_search_action)
        
        # Analysis Menu
        analysis_menu = menubar.addMenu("&Analysis")
        
        analyze_action = QAction("&Analyze All Files", self)
        analyze_action.setShortcut(QKeySequence("Ctrl+Alt+A"))
        analyze_action.setStatusTip("Analyze all loaded DICOM files")
        analyze_action.triggered.connect(self.analyze_all_loaded_files)
        analysis_menu.addAction(analyze_action)
        
        performance_action = QAction("Test &Performance", self)
        performance_action.setShortcut(QKeySequence("Ctrl+Alt+P"))
        performance_action.setStatusTip("Test loading performance")
        performance_action.triggered.connect(self.test_loading_performance)
        analysis_menu.addAction(performance_action)
        
        # Send Menu
        send_menu = menubar.addMenu("&Send")
        
        dicom_send_action = QAction("&DICOM Send...", self)
        dicom_send_action.setShortcut(QKeySequence("Ctrl+D"))
        dicom_send_action.setStatusTip("Send files via DICOM protocol")
        dicom_send_action.triggered.connect(self.dicom_send)
        send_menu.addAction(dicom_send_action)
        
        send_menu.addSeparator()
        
        # Export submenu
        export_menu = send_menu.addMenu("&Export Options")
        
        export_zip_action = QAction("Export as &ZIP", self)
        export_zip_action.setStatusTip("Export selected files as ZIP archive")
        export_zip_action.triggered.connect(lambda: self._export_as_type("zip"))
        export_menu.addAction(export_zip_action)
        
        export_dicomdir_action = QAction("Export as &DICOMDIR", self)
        export_dicomdir_action.setStatusTip("Export selected files as DICOMDIR")
        export_dicomdir_action.triggered.connect(lambda: self._export_as_type("dicomdir_zip"))
        export_menu.addAction(export_dicomdir_action)
        
        export_selection_action = QAction("Export &Selection...", self)
        export_selection_action.setStatusTip("Export with custom selection")
        export_selection_action.triggered.connect(self.save_as)
        export_menu.addAction(export_selection_action)
        
        # Version Menu (replaces Help menu)
        version_menu = menubar.addMenu(f"&Version: {__version__}")

        about_action = QAction("&About", self)
        about_action.setStatusTip("About this application")
        about_action.triggered.connect(self._show_about)
        version_menu.addAction(about_action)
        
        # Store references for enabling/disabling
        self.save_action = save_action  # Menu save action
        # Also disable toolbar save action initially
        if hasattr(self, 'toolbar_save_action'):
            self.toolbar_save_action.setEnabled(False)
        self.preview_action.setChecked(self.config.get("show_image_preview", False))
    
    def _clear_all_search_filters(self):
        """Clear all search filters"""
        if hasattr(self, 'search_bar') and self.search_bar:
            self.search_bar.clear()
        if hasattr(self, 'tree_search_bar') and self.tree_search_bar:
            self.tree_search_bar.clear()
    
    def _toggle_image_preview(self, checked):
        """Toggle image preview from menu"""
        if hasattr(self, 'preview_toggle'):
            self.preview_toggle.setChecked(checked)
    
    def _refresh_tree_view(self):
        """Refresh tree view from menu"""
        if hasattr(self, 'tree_manager') and self.tree_manager:
            if hasattr(self, "prepare_for_tree_refresh"):
                self.prepare_for_tree_refresh()
            self.tree_manager.refresh_tree()
    
    def _open_tag_search(self):
        """Open tag search dialog from menu"""
        if hasattr(self, 'dicom_manager') and self.dicom_manager:
            self.dicom_manager.show_tag_search_dialog()
    
    def _export_as_type(self, export_type):
        """Export with specific type"""
        # This will need to be implemented to call the appropriate export method
        # For now, delegate to save_as which handles export options
        self.save_as()
    
    def _show_about(self):
        """Show enhanced about dialog with comprehensive information"""
        from PyQt6.QtWidgets import QMessageBox

        about_text = f"""<h2>FM DICOM Tag Editor</h2>
        <p><b>Version: {__version__}</b></p>

        <p>A comprehensive DICOM file management and editing application built with PyQt6.</p>

        <h3>Key Features:</h3>
        <ul>
            <li>🔍 <b>DICOM File Viewing:</b> Browse and examine DICOM files and directories</li>
            <li>✏️ <b>Tag Editing:</b> Edit DICOM tags with real-time validation</li>
            <li>🔒 <b>Anonymization:</b> Remove or modify patient information for privacy</li>
            <li>✅ <b>Validation:</b> Comprehensive DICOM compliance checking</li>
            <li>🌐 <b>Network Operations:</b> Send DICOM files via DICOM C-STORE protocol</li>
            <li>📁 <b>Archive Support:</b> Direct ZIP archive browsing and editing</li>
            <li>🎨 <b>Modern Interface:</b> Dark/light themes with intuitive layout</li>
            <li>📊 <b>Hierarchical View:</b> Patient → Study → Series → Instance organization</li>
            <li>🔄 <b>Duplication System:</b> Advanced DICOM data duplication with UID management</li>
        </ul>

        <h3>Technical Information:</h3>
        <ul>
            <li><b>Framework:</b> PyQt6 with Qt6 integration</li>
            <li><b>DICOM Library:</b> pydicom + pynetdicom</li>
            <li><b>Image Processing:</b> Pillow + GDCM for JPEG2000 support</li>
            <li><b>Platform:</b> Cross-platform (Linux, Windows, macOS)</li>
        </ul>

        <p><i>Designed for medical professionals, researchers, and DICOM developers.</i></p>
        """

        QMessageBox.about(self, f"About FM DICOM Tag Editor v{__version__}", about_text)
    
    def enable_save_actions(self, enabled=True):
        """Enable or disable both menu and toolbar save actions"""
        if hasattr(self, 'save_action'):
            self.save_action.setEnabled(enabled)
        if hasattr(self, 'toolbar_save_action'):
            self.toolbar_save_action.setEnabled(enabled)
    
    def update_file_info_display(self, total_files=0, selected_count=0, current_file=None):
        """Update the file information display in status bar"""
        if not hasattr(self, 'file_info_label'):
            return
            
        if total_files == 0:
            self.file_info_label.setText("No files loaded")
        elif selected_count > 0:
            self.file_info_label.setText(f"{total_files} files | {selected_count} selected")
        else:
            self.file_info_label.setText(f"{total_files} files")
            
        # Update summary display
        if hasattr(self, 'summary_label'):
            if total_files == 0:
                self.summary_label.setText("No DICOM files loaded")
            elif current_file:
                filename = current_file.split('/')[-1] if '/' in current_file else current_file
                self.summary_label.setText(f"Current: {filename}")
            else:
                self.summary_label.setText(f"{total_files} DICOM files loaded")
    
    def update_stats_display(self, patients=0, studies=0, series=0, instances=0, total_size_gb=0):
        """Update the statistics display"""
        if not hasattr(self, 'stats_label'):
            return
            
        if patients > 0:
            # Format size appropriately
            if total_size_gb >= 0.01:
                size_str = f"{total_size_gb:.2f} GB"
            else:
                size_mb = total_size_gb * 1024
                size_str = f"{size_mb:.1f} MB"
            
            stats_text = f"{patients}P • {studies}St • {series}Se • {instances}I • {size_str}"
            self.stats_label.setText(stats_text)
        else:
            self.stats_label.setText("")
    
    def show_progress_status(self, message="", show=True):
        """Show or hide progress status"""
        if not hasattr(self, 'progress_label'):
            return
            
        if show and message:
            self.progress_label.setText(f"⚡ {message}")
            self.progress_label.setVisible(True)
        else:
            self.progress_label.setVisible(False)
    
    def update_operation_status(self, message, timeout=0):
        """Update the main status bar message"""
        if hasattr(self, 'status_bar'):
            self.status_bar.showMessage(message, timeout)
