"""
Mixin class for MainWindow menu and toolbar setup.

This mixin provides all menu and toolbar creation functionality,
keeping UI setup logic organized and reusable.
"""

from PyQt6.QtWidgets import QToolBar, QMenu
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtCore import QSize


class MenuToolbarMixin:
    """Mixin for setting up menus and toolbars in MainWindow"""
    
    def setup_menus(self):
        """Setup all application menus"""
        menubar = self.menuBar()
        
        # File menu
        self._setup_file_menu(menubar)
        
        # Edit menu  
        self._setup_edit_menu(menubar)
        
        # View menu
        self._setup_view_menu(menubar)
        
        # Tools menu
        self._setup_tools_menu(menubar)
        
        # Help menu
        self._setup_help_menu(menubar)
    
    def _setup_file_menu(self, menubar):
        """Setup File menu"""
        file_menu = menubar.addMenu("&File")
        
        # Open File
        open_action = QAction("&Open File...", self)
        open_action.setShortcut("Ctrl+O")
        open_action.setStatusTip("Open a DICOM file")
        open_action.triggered.connect(self.open_file)
        file_menu.addAction(open_action)
        
        # Open Directory  
        open_dir_action = QAction("Open &Directory...", self)
        open_dir_action.setShortcut("Ctrl+D")
        open_dir_action.setStatusTip("Open a directory containing DICOM files")
        open_dir_action.triggered.connect(self.open_directory)
        file_menu.addAction(open_dir_action)
        
        file_menu.addSeparator()
        
        # Recent files submenu would go here
        
        file_menu.addSeparator()
        
        # Exit
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.setStatusTip("Exit the application")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
    
    def _setup_edit_menu(self, menubar):
        """Setup Edit menu"""
        edit_menu = menubar.addMenu("&Edit")
        
        # Delete
        delete_action = QAction("&Delete Selected", self)
        delete_action.setShortcut("Delete")
        delete_action.setStatusTip("Delete selected items")
        delete_action.triggered.connect(self.delete_selected_items)
        edit_menu.addAction(delete_action)
        
        edit_menu.addSeparator()
        
        # Settings
        settings_action = QAction("&Settings...", self)
        settings_action.setStatusTip("Open application settings")
        settings_action.triggered.connect(self.show_settings_dialog)
        edit_menu.addAction(settings_action)
    
    def _setup_view_menu(self, menubar):
        """Setup View menu"""
        view_menu = menubar.addMenu("&View")
        
        # Expand All
        expand_action = QAction("&Expand All", self)
        expand_action.setStatusTip("Expand all tree items")
        expand_action.triggered.connect(self.tree_expand_all)
        view_menu.addAction(expand_action)
        
        # Collapse All
        collapse_action = QAction("&Collapse All", self)
        collapse_action.setStatusTip("Collapse all tree items")
        collapse_action.triggered.connect(self.tree_collapse_all)
        view_menu.addAction(collapse_action)
        
        view_menu.addSeparator()
        
        # Theme submenu
        theme_menu = view_menu.addMenu("&Theme")
        
        dark_theme_action = QAction("&Dark", self)
        dark_theme_action.setCheckable(True)
        dark_theme_action.setChecked(self.config.get("theme", "dark") == "dark")
        dark_theme_action.triggered.connect(lambda: self.apply_theme("dark"))
        theme_menu.addAction(dark_theme_action)
        
        light_theme_action = QAction("&Light", self)
        light_theme_action.setCheckable(True)
        light_theme_action.setChecked(self.config.get("theme", "dark") == "light")
        light_theme_action.triggered.connect(lambda: self.apply_theme("light"))
        theme_menu.addAction(light_theme_action)
    
    def _setup_tools_menu(self, menubar):
        """Setup Tools menu"""
        tools_menu = menubar.addMenu("&Tools")
        
        # Validation
        validate_action = QAction("&Validate Selected", self)
        validate_action.setStatusTip("Validate selected DICOM files")
        validate_action.triggered.connect(self.validate_selected_items)
        tools_menu.addAction(validate_action)
        
        # Anonymization
        anonymize_action = QAction("&Anonymize Selected", self)
        anonymize_action.setStatusTip("Anonymize selected DICOM files")
        anonymize_action.triggered.connect(self.anonymize_selected_items)
        tools_menu.addAction(anonymize_action)
        
        tools_menu.addSeparator()
        
        # Tag Search
        tag_search_action = QAction("&Tag Search", self)
        tag_search_action.setShortcut("Ctrl+F")
        tag_search_action.setStatusTip("Search for DICOM tags")
        tag_search_action.triggered.connect(self.show_tag_search_dialog)
        tools_menu.addAction(tag_search_action)
        
        tools_menu.addSeparator()
        
        # DICOM Send
        send_action = QAction("DICOM &Send", self)
        send_action.setStatusTip("Send DICOM files to remote destination")
        send_action.triggered.connect(self.show_dicom_send_dialog)
        tools_menu.addAction(send_action)
        
        tools_menu.addSeparator()
        
        # Export
        export_action = QAction("&Export Selected", self)
        export_action.setStatusTip("Export selected files")
        export_action.triggered.connect(self.export_files)
        tools_menu.addAction(export_action)
    
    def _setup_help_menu(self, menubar):
        """Setup Help menu"""
        help_menu = menubar.addMenu("&Help")

        # View Logs
        logs_action = QAction("View &Logs", self)
        logs_action.setStatusTip("Open log viewer")
        logs_action.triggered.connect(self.show_log_viewer)
        help_menu.addAction(logs_action)

        # Configuration Diagnostics
        diagnostics_action = QAction("Configuration &Diagnostics", self)
        diagnostics_action.setStatusTip("Show configuration diagnostics and troubleshooting information")
        diagnostics_action.triggered.connect(self.show_config_diagnostics)
        help_menu.addAction(diagnostics_action)

        help_menu.addSeparator()

        # About
        about_action = QAction("&About", self)
        about_action.setStatusTip("About this application")
        about_action.triggered.connect(self.show_about_dialog)
        help_menu.addAction(about_action)
    
    def setup_toolbar(self):
        """Setup main application toolbar"""
        toolbar = QToolBar("Main Toolbar")
        toolbar.setIconSize(QSize(20, 20))
        self.addToolBar(toolbar)
        
        # Get standard icons
        open_icon = self.style().standardIcon(self.style().StandardPixmap.SP_DialogOpenButton)
        save_icon = self.style().standardIcon(self.style().StandardPixmap.SP_DialogSaveButton)
        delete_icon = self.style().standardIcon(self.style().StandardPixmap.SP_TrashIcon)
        merge_icon = self.style().standardIcon(self.style().StandardPixmap.SP_FileDialogNewFolder)
        expand_icon = self.style().standardIcon(self.style().StandardPixmap.SP_ArrowDown)
        collapse_icon = self.style().standardIcon(self.style().StandardPixmap.SP_ArrowUp)
        
        # Open File
        act_open = QAction(open_icon, "Open", self)
        act_open.setToolTip("Open DICOM file")
        act_open.triggered.connect(self.open_file)
        toolbar.addAction(act_open)
        
        # Open Directory
        act_open_dir = QAction(QIcon.fromTheme("folder"), "Open Directory", self)
        act_open_dir.setToolTip("Open directory")
        act_open_dir.triggered.connect(self.open_directory)
        toolbar.addAction(act_open_dir)
        
        toolbar.addSeparator()
        
        # Delete
        act_delete = QAction(delete_icon, "Delete", self)
        act_delete.setToolTip("Delete selected items")
        act_delete.triggered.connect(self.delete_selected_items)
        toolbar.addAction(act_delete)
        
        toolbar.addSeparator()
        
        # Expand All
        act_expand = QAction(expand_icon, "Expand All", self)
        act_expand.setToolTip("Expand all tree items")
        act_expand.triggered.connect(self.tree_expand_all)
        toolbar.addAction(act_expand)
        
        # Collapse All
        act_collapse = QAction(collapse_icon, "Collapse All", self)
        act_collapse.setToolTip("Collapse all tree items")
        act_collapse.triggered.connect(self.tree_collapse_all)
        toolbar.addAction(act_collapse)
        
        toolbar.addSeparator()
        
        # Export
        act_export = QAction(save_icon, "Export", self)
        act_export.setToolTip("Export selected files")
        act_export.triggered.connect(self.export_files)
        toolbar.addAction(act_export)
        
        # DICOM Send
        act_send = QAction("Send", self)
        act_send.setToolTip("Send DICOM files")
        act_send.triggered.connect(self.show_dicom_send_dialog)
        toolbar.addAction(act_send)
        
        toolbar.addSeparator()
        
        # Validation
        act_validate = QAction("Validate", self)
        act_validate.setToolTip("Validate selected files")
        act_validate.triggered.connect(self.validate_selected_items)
        toolbar.addAction(act_validate)
        
        # Anonymize
        act_anonymize = QAction("Anonymize", self)
        act_anonymize.setToolTip("Anonymize selected files")
        act_anonymize.triggered.connect(self.anonymize_selected_items)
        toolbar.addAction(act_anonymize)
        
        # Store toolbar reference
        self.main_toolbar = toolbar
    
    def apply_theme(self, theme_name):
        """Apply a theme and update config"""
        from fm_dicom.themes.theme_manager import set_dark_palette, set_light_palette
        from PyQt6.QtWidgets import QApplication
        
        if theme_name == "dark":
            set_dark_palette(QApplication.instance())
        else:
            set_light_palette(QApplication.instance())
        
        # Update config
        self.config["theme"] = theme_name
        # Note: Would need to implement config saving in a manager class
    
    def show_about_dialog(self):
        """Show about dialog"""
        from fm_dicom.widgets.focus_aware import FocusAwareMessageBox
        FocusAwareMessageBox.information(
            self, 
            "About FM-DICOM",
            "FM-DICOM Tag Editor\n\n"
            "A DICOM file management and editing application.\n\n"
            "Features:\n"
            "• DICOM file viewing and editing\n"
            "• File validation and anonymization\n"  
            "• DICOM network operations\n"
            "• ZIP archive support"
        )