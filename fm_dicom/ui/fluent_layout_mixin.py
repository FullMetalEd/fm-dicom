"""
Fluent Layout Mixin for MainWindow.

This mixin extends the existing LayoutMixin to use Fluent Design widgets
when available, with graceful fallback to standard PyQt6 widgets.
"""

import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTreeWidgetItem,
    QTableWidgetItem, QLineEdit, QLabel, QGroupBox, QFrame,
    QStatusBar, QPushButton, QComboBox, QCheckBox, QSizePolicy, QGridLayout,
    QToolBar, QMenuBar, QMenu
)
from PyQt6.QtGui import QPixmap, QImage, QIcon, QAction, QKeySequence
from PyQt6.QtCore import Qt, QPoint, QSize

from .framework import get_widget_factory, get_framework_info, UIFramework

# Import at runtime to avoid circular imports  
import importlib.util


class FluentLayoutMixin:
    """Fluent Design layout mixin that enhances the standard layout with modern widgets"""
    
    def __init__(self):
        # Initialize with framework detection
        self.widget_factory = get_widget_factory()
        self.framework_info = get_framework_info()
        
        # Log framework information
        logging.info(f"UI Framework: {self.framework_info['framework']} (version: {self.framework_info['version']})")
        
        # Call standard layout setup if Fluent not available
        if self.framework_info['framework'] != 'fluent':
            self._setup_standard_layout = True
        else:
            self._setup_standard_layout = False
    
    def setup_ui_layout(self):
        """Setup the main UI layout with Fluent Design widgets when available"""
        # Window setup - use Fluent window if available
        if self.framework_info['framework'] == 'fluent':
            self.setWindowTitle("FM DICOM Tag Editor")
            w, h = self.config.get("window_size", [1200, 800])
            self.resize(w, h)
            
            # Initialize Fluent window features if available
            self._setup_fluent_window()
        else:
            # Fall back to standard setup
            self._setup_standard_ui_layout()
            return
        
        # Create central widget
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Enhanced Menu Bar with Fluent styling
        self.setup_fluent_menu_bar()

        # Modern Navigation Interface (replaces traditional toolbar)
        self.setup_fluent_navigation()

        # Main content splitter
        self.main_splitter = self.create_main_splitter()
        layout.addWidget(self.main_splitter)

        # Enhanced status bar
        self.setup_fluent_status_bar()

        # Apply theme
        self.widget_factory.apply_theme(self, self.config.get("theme", "light"))
    
    def _setup_fluent_window(self):
        """Setup Fluent-specific window features"""
        try:
            import qfluentwidgets as qfw
            
            # Set up window icon if available
            if hasattr(qfw, 'FluentIcon'):
                self.setWindowIcon(QIcon(qfw.FluentIcon.MEDICAL))
                
            # Enable mica effect if available and on Windows
            if hasattr(self, 'setMicaEffectEnabled'):
                self.setMicaEffectEnabled(True)
                
        except ImportError:
            pass  # Fluent features not available
    
    def setup_fluent_menu_bar(self):
        """Setup menu bar with Fluent styling"""
        if self.framework_info['framework'] == 'fluent':
            try:
                import qfluentwidgets as qfw
                
                # Create fluent menu bar if available
                if hasattr(qfw, 'MenuBar'):
                    menu_bar = qfw.MenuBar(self)
                    self.setMenuBar(menu_bar)
                else:
                    # Fall back to enhanced standard menu bar
                    self.setup_menu_bar()
            except ImportError:
                self.setup_menu_bar()
        else:
            self.setup_menu_bar()
    
    def setup_fluent_navigation(self):
        """Setup modern navigation interface"""
        if self.framework_info['framework'] == 'fluent':
            try:
                import qfluentwidgets as qfw
                
                # Create navigation interface if available
                if hasattr(qfw, 'NavigationInterface'):
                    self.navigation = qfw.NavigationInterface(self, showMenuButton=True, showReturnButton=False)
                    
                    # Add navigation items
                    self.add_navigation_items()
                    return
                    
            except ImportError:
                pass
        
        # Fall back to enhanced toolbar
        self.setup_enhanced_toolbar()
    
    def add_navigation_items(self):
        """Add items to fluent navigation interface"""
        try:
            import qfluentwidgets as qfw
            
            # File operations section
            self.navigation.addSeparator()
            
            # Open file
            self.navigation.addItem(
                routeKey="open_file",
                icon=qfw.FluentIcon.FOLDER,
                text="Open File",
                onClick=self.open_file,
                tooltip="Open a DICOM file"
            )
            
            # Open directory
            self.navigation.addItem(
                routeKey="open_directory", 
                icon=qfw.FluentIcon.FOLDER_ADD,
                text="Open Directory",
                onClick=self.open_directory,
                tooltip="Open a directory containing DICOM files"
            )
            
            # Separator
            self.navigation.addSeparator()
            
            # Tools section
            self.navigation.addItem(
                routeKey="validate",
                icon=qfw.FluentIcon.CHECKBOX,
                text="Validate",
                onClick=self.validate_files,
                tooltip="Validate DICOM files"
            )
            
            self.navigation.addItem(
                routeKey="anonymize",
                icon=qfw.FluentIcon.HIDE,
                text="Anonymize", 
                onClick=self.anonymize_files,
                tooltip="Anonymize DICOM files"
            )
            
            # Settings at bottom
            self.navigation.addItem(
                routeKey="settings",
                icon=qfw.FluentIcon.SETTING,
                text="Settings",
                onClick=self.open_settings,
                tooltip="Application settings",
                position=qfw.NavigationItemPosition.BOTTOM
            )
            
        except ImportError:
            pass
    
    def setup_enhanced_toolbar(self):
        """Setup enhanced toolbar as fallback"""
        toolbar = QToolBar("Main Toolbar")
        toolbar.setIconSize(QSize(32, 32))  # Larger icons for modern look
        self.addToolBar(toolbar)

        # File operations with enhanced styling
        open_icon = self.style().standardIcon(self.style().StandardPixmap.SP_DialogOpenButton)
        act_open = QAction(open_icon, "Open File", self)
        act_open.setShortcut(QKeySequence.StandardKey.Open)
        act_open.setToolTip("Open a DICOM file (Ctrl+O)")
        act_open.triggered.connect(self.open_file)
        toolbar.addAction(act_open)

        open_dir_icon = self.style().standardIcon(self.style().StandardPixmap.SP_DirOpenIcon)
        act_open_dir = QAction(open_dir_icon, "Open Directory", self)
        act_open_dir.setShortcut(QKeySequence("Ctrl+Shift+O"))
        act_open_dir.setToolTip("Open directory containing DICOM files (Ctrl+Shift+O)")
        act_open_dir.triggered.connect(self.open_directory)
        toolbar.addAction(act_open_dir)

        toolbar.addSeparator()

        # Validation and anonymization
        validate_icon = self.style().standardIcon(self.style().StandardPixmap.SP_DialogApplyButton)
        act_validate = QAction(validate_icon, "Validate", self)
        act_validate.setShortcut(QKeySequence("Ctrl+V"))
        act_validate.setToolTip("Validate DICOM files (Ctrl+V)")
        act_validate.triggered.connect(self.validate_files)
        toolbar.addAction(act_validate)

        anon_icon = self.style().standardIcon(self.style().StandardPixmap.SP_DialogSaveButton)
        act_anonymize = QAction(anon_icon, "Anonymize", self)
        act_anonymize.setShortcut(QKeySequence("Ctrl+A"))
        act_anonymize.setToolTip("Anonymize DICOM files (Ctrl+A)")
        act_anonymize.triggered.connect(self.anonymize_files)
        toolbar.addAction(act_anonymize)
    
    def create_main_splitter(self):
        """Create the main content splitter with enhanced widgets"""
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left panel: Tree view with search
        left_panel = self.create_tree_panel()
        splitter.addWidget(left_panel)
        
        # Right panel: Tag editor
        right_panel = self.create_tag_panel()
        splitter.addWidget(right_panel)
        
        # Set splitter proportions
        splitter.setSizes([400, 800])
        
        return splitter
    
    def create_tree_panel(self):
        """Create enhanced tree panel with search functionality"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        
        # Search functionality
        search_widget = self.widget_factory.create_search_line_edit(
            parent=panel,
            placeholder="Search DICOM files..."
        )
        search_widget.textChanged.connect(self.filter_tree)
        layout.addWidget(search_widget)
        
        # Enhanced tree widget
        self.tree = self.widget_factory.create_tree_widget(panel)
        self.tree.setHeaderLabels(["DICOM Files", "Patient ID", "Study Date"])
        layout.addWidget(self.tree)
        
        # Store reference for tree manager
        self.tree_widget = self.tree
        
        return panel
    
    def create_tag_panel(self):
        """Create enhanced tag editing panel"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        
        # Tag filter section
        filter_group = QGroupBox("Filter Tags")
        filter_layout = QHBoxLayout(filter_group)
        
        # Enhanced filter widgets
        self.tag_filter = self.widget_factory.create_search_line_edit(
            parent=filter_group,
            placeholder="Filter tags..."
        )
        filter_layout.addWidget(QLabel("Filter:"))
        filter_layout.addWidget(self.tag_filter)
        
        self.show_private_tags = QCheckBox("Show Private Tags")
        filter_layout.addWidget(self.show_private_tags)
        
        layout.addWidget(filter_group)
        
        # Enhanced table widget
        self.table = self.widget_factory.create_table_widget(panel)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Tag", "VR", "Value", "Description"])
        layout.addWidget(self.table)
        
        # Store reference for dicom manager  
        self.tag_table = self.table
        
        return panel
    
    def setup_fluent_status_bar(self):
        """Setup enhanced status bar"""
        if self.framework_info['framework'] == 'fluent':
            try:
                import qfluentwidgets as qfw
                
                # Enhanced status bar with info badges
                status_bar = QStatusBar()
                self.setStatusBar(status_bar)
                
                # Add framework info
                framework_label = QLabel(f"UI: {self.framework_info['framework'].title()}")
                framework_label.setStyleSheet("color: gray; font-size: 10px;")
                status_bar.addPermanentWidget(framework_label)
                
                return
                
            except ImportError:
                pass
        
        # Standard status bar
        status_bar = QStatusBar()
        self.setStatusBar(status_bar)
        status_bar.showMessage(f"FM-Dicom ready - UI Framework: {self.framework_info['framework'].title()}")
    
    def filter_tree(self, text: str):
        """Filter tree view based on search text"""
        # This will be implemented by tree manager
        if hasattr(self, 'tree_manager'):
            self.tree_manager.filter_tree(text)
    
    def show_info_notification(self, title: str, message: str):
        """Show info notification using appropriate method"""
        if self.framework_info['framework'] == 'fluent':
            try:
                import qfluentwidgets as qfw
                
                # Create fluent info bar
                info_bar = qfw.InfoBar.success(
                    title=title,
                    content=message,
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=qfw.InfoBarPosition.TOP,
                    duration=3000,
                    parent=self
                )
                info_bar.show()
                return
                
            except ImportError:
                pass
        
        # Fallback to focus-aware message box
        from fm_dicom.widgets.focus_aware import FocusAwareMessageBox
        FocusAwareMessageBox.information(self, title, message)
    
    def show_error_notification(self, title: str, message: str):
        """Show error notification using appropriate method"""
        if self.framework_info['framework'] == 'fluent':
            try:
                import qfluentwidgets as qfw
                
                info_bar = qfw.InfoBar.error(
                    title=title,  
                    content=message,
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=qfw.InfoBarPosition.TOP,
                    duration=5000,
                    parent=self
                )
                info_bar.show()
                return
                
            except ImportError:
                pass
        
        # Fallback to focus-aware message box
        from fm_dicom.widgets.focus_aware import FocusAwareMessageBox
        FocusAwareMessageBox.critical(self, title, message)
    
    def _setup_standard_ui_layout(self):
        """Setup standard UI layout as fallback"""
        # Import and call standard LayoutMixin setup methods
        from .layout_mixin import LayoutMixin
        
        # Mix in LayoutMixin methods temporarily
        layout_mixin = LayoutMixin()
        
        # Setup window
        self.setWindowTitle("FM DICOM Tag Editor")
        w, h = self.config.get("window_size", [1200, 800])
        self.resize(w, h)
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Modern Menu Bar
        self.setup_menu_bar()

        # Streamlined Toolbar - Essential tools only
        toolbar = QToolBar("Main Toolbar")
        toolbar.setIconSize(QSize(24, 24))
        self.addToolBar(toolbar)

        # Essential file operations
        open_icon = self.style().standardIcon(self.style().StandardPixmap.SP_DialogOpenButton)
        act_open = QAction(open_icon, "Open File", self)
        act_open.setShortcut(QKeySequence.StandardKey.Open)
        act_open.setToolTip("Open a DICOM file (Ctrl+O)")
        act_open.triggered.connect(self.open_file)
        toolbar.addAction(act_open)

        open_dir_icon = self.style().standardIcon(self.style().StandardPixmap.SP_DirOpenIcon)
        act_open_dir = QAction(open_dir_icon, "Open Directory", self)
        act_open_dir.setShortcut(QKeySequence("Ctrl+Shift+O"))
        act_open_dir.setToolTip("Open directory containing DICOM files (Ctrl+Shift+O)")
        act_open_dir.triggered.connect(self.open_directory)
        toolbar.addAction(act_open_dir)

        toolbar.addSeparator()

        # Core layout setup
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(main_splitter)

        # Left Panel: Tree View
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        
        # Search box for tree filtering
        search_box = QLineEdit()
        search_box.setPlaceholderText("Search DICOM files...")
        search_box.textChanged.connect(self.filter_tree)
        left_layout.addWidget(search_box)
        
        # DICOM Tree
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["DICOM Files", "Patient ID", "Study Date"])
        left_layout.addWidget(self.tree)
        
        main_splitter.addWidget(left_panel)
        self.tree_widget = self.tree  # Store reference for compatibility

        # Right Panel: Tag Editor
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        
        # Tag controls
        controls_layout = QHBoxLayout()
        
        # Filter controls
        self.tag_filter = QLineEdit()
        self.tag_filter.setPlaceholderText("Filter tags...")
        controls_layout.addWidget(QLabel("Filter:"))
        controls_layout.addWidget(self.tag_filter)
        
        self.show_private_tags = QCheckBox("Show Private Tags")
        controls_layout.addWidget(self.show_private_tags)
        
        right_layout.addLayout(controls_layout)
        
        # Tag table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Tag", "VR", "Value", "Description"])
        right_layout.addWidget(self.table)
        
        main_splitter.addWidget(right_panel)
        self.tag_table = self.table  # Store reference for compatibility
        
        # Set splitter sizes
        main_splitter.setSizes([400, 800])

        # Status bar
        status_bar = QStatusBar()
        self.setStatusBar(status_bar)
        status_bar.showMessage("FM-Dicom ready - Standard UI")
    
    def setup_menu_bar(self):
        """Setup basic menu bar"""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu('&File')
        
        open_action = QAction('&Open File', self)
        open_action.setShortcut('Ctrl+O')
        open_action.triggered.connect(self.open_file)
        file_menu.addAction(open_action)
        
        open_dir_action = QAction('Open &Directory', self)
        open_dir_action.setShortcut('Ctrl+Shift+O')
        open_dir_action.triggered.connect(self.open_directory)
        file_menu.addAction(open_dir_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction('E&xit', self)
        exit_action.setShortcut('Ctrl+Q')
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
    
    def filter_tree(self, text: str):
        """Filter tree view - to be implemented by tree manager"""
        pass