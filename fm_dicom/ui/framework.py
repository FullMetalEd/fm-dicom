"""
UI Framework abstraction layer for FM-Dicom.

This module provides runtime detection of available UI frameworks and creates
appropriate widgets based on what's available. Supports graceful degradation
from Fluent Design widgets to standard PyQt6 widgets.
"""

import logging
from typing import Optional, Union, Any, Dict, Callable
from enum import Enum

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import QObject


class UIFramework(Enum):
    """Available UI frameworks"""
    FLUENT = "fluent"
    STANDARD = "standard"


class FrameworkDetector:
    """Detects available UI frameworks at runtime"""
    
    _instance = None
    _framework_cache: Optional[UIFramework] = None
    _fluent_available: Optional[bool] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def is_fluent_available(self) -> bool:
        """Check if PyQt6-Fluent-Widgets is available"""
        if self._fluent_available is not None:
            return self._fluent_available
            
        try:
            import qfluentwidgets
            self._fluent_available = True
            logging.info("PyQt6-Fluent-Widgets detected - modern UI enabled")
        except ImportError:
            self._fluent_available = False
            logging.info("PyQt6-Fluent-Widgets not available - using standard PyQt6 widgets")
            
        return self._fluent_available
    
    def get_framework(self) -> UIFramework:
        """Get the best available UI framework"""
        if self._framework_cache is not None:
            return self._framework_cache
            
        if self.is_fluent_available():
            self._framework_cache = UIFramework.FLUENT
        else:
            self._framework_cache = UIFramework.STANDARD
            
        return self._framework_cache
    
    def force_framework(self, framework: UIFramework):
        """Force a specific framework (mainly for testing)"""
        self._framework_cache = framework
        if framework == UIFramework.FLUENT:
            self._fluent_available = True
        else:
            self._fluent_available = False


class WidgetFactory:
    """Factory for creating widgets based on available framework"""
    
    def __init__(self):
        self.detector = FrameworkDetector()
        self._widget_cache: Dict[str, Any] = {}
    
    def _get_fluent_module(self, module_name: str = None):
        """Get fluent widgets module or specific submodule"""
        try:
            if module_name:
                return getattr(__import__('qfluentwidgets', fromlist=[module_name]), module_name)
            else:
                return __import__('qfluentwidgets')
        except ImportError:
            return None
    
    def _get_standard_module(self):
        """Get standard PyQt6 widgets module"""
        return __import__('PyQt6.QtWidgets', fromlist=['QtWidgets'])
    
    def create_main_window(self, *args, **kwargs):
        """Create main application window"""
        if self.detector.get_framework() == UIFramework.FLUENT:
            fluent_widgets = self._get_fluent_module()
            if fluent_widgets and hasattr(fluent_widgets, 'FluentWindow'):
                return fluent_widgets.FluentWindow(*args, **kwargs)
        
        # Fallback to standard
        from PyQt6.QtWidgets import QMainWindow
        return QMainWindow(*args, **kwargs)
    
    def create_push_button(self, text: str, parent: Optional[QWidget] = None, primary: bool = False):
        """Create a push button (primary or secondary)"""
        if self.detector.get_framework() == UIFramework.FLUENT:
            fluent_widgets = self._get_fluent_module()
            if fluent_widgets:
                if primary and hasattr(fluent_widgets, 'PrimaryPushButton'):
                    return fluent_widgets.PrimaryPushButton(text, parent)
                elif hasattr(fluent_widgets, 'PushButton'):
                    return fluent_widgets.PushButton(text, parent)
        
        # Fallback to standard
        from PyQt6.QtWidgets import QPushButton
        button = QPushButton(text, parent)
        if primary:
            button.setProperty("primary", True)  # For CSS styling
        return button
    
    def create_line_edit(self, parent: Optional[QWidget] = None, placeholder: str = ""):
        """Create a line edit widget"""
        if self.detector.get_framework() == UIFramework.FLUENT:
            fluent_widgets = self._get_fluent_module()
            if fluent_widgets and hasattr(fluent_widgets, 'LineEdit'):
                widget = fluent_widgets.LineEdit(parent)
                if placeholder:
                    widget.setPlaceholderText(placeholder)
                return widget
        
        # Fallback to standard
        from PyQt6.QtWidgets import QLineEdit
        widget = QLineEdit(parent)
        if placeholder:
            widget.setPlaceholderText(placeholder)
        return widget
    
    def create_search_line_edit(self, parent: Optional[QWidget] = None, placeholder: str = "Search..."):
        """Create a search line edit widget"""
        if self.detector.get_framework() == UIFramework.FLUENT:
            fluent_widgets = self._get_fluent_module()
            if fluent_widgets and hasattr(fluent_widgets, 'SearchLineEdit'):
                widget = fluent_widgets.SearchLineEdit(parent)
                if placeholder:
                    widget.setPlaceholderText(placeholder)
                return widget
        
        # Fallback to enhanced standard line edit
        from PyQt6.QtWidgets import QLineEdit
        from PyQt6.QtGui import QAction
        widget = QLineEdit(parent)
        if placeholder:
            widget.setPlaceholderText(placeholder)
        
        # Add search icon if possible
        try:
            search_action = QAction(widget)
            search_action.setIcon(widget.style().standardIcon(widget.style().StandardPixmap.SP_FileDialogDetailedView))
            widget.addAction(search_action, QLineEdit.ActionPosition.LeadingPosition)
        except:
            pass  # Ignore icon issues
            
        return widget
    
    def create_combo_box(self, parent: Optional[QWidget] = None):
        """Create a combo box widget"""
        if self.detector.get_framework() == UIFramework.FLUENT:
            fluent_widgets = self._get_fluent_module()
            if fluent_widgets and hasattr(fluent_widgets, 'ComboBox'):
                return fluent_widgets.ComboBox(parent)
        
        # Fallback to standard
        from PyQt6.QtWidgets import QComboBox
        return QComboBox(parent)
    
    def create_tree_widget(self, parent: Optional[QWidget] = None):
        """Create a tree widget"""
        if self.detector.get_framework() == UIFramework.FLUENT:
            fluent_widgets = self._get_fluent_module()
            if fluent_widgets and hasattr(fluent_widgets, 'TreeWidget'):
                return fluent_widgets.TreeWidget(parent)
        
        # Fallback to standard
        from PyQt6.QtWidgets import QTreeWidget
        return QTreeWidget(parent)
    
    def create_table_widget(self, parent: Optional[QWidget] = None):
        """Create a table widget"""
        if self.detector.get_framework() == UIFramework.FLUENT:
            fluent_widgets = self._get_fluent_module()
            if fluent_widgets and hasattr(fluent_widgets, 'TableWidget'):
                return fluent_widgets.TableWidget(parent)
        
        # Fallback to standard
        from PyQt6.QtWidgets import QTableWidget
        return QTableWidget(parent)
    
    def create_progress_dialog(self, label_text: str, cancel_text: str, minimum: int, maximum: int, parent: Optional[QWidget] = None):
        """Create a progress dialog"""
        if self.detector.get_framework() == UIFramework.FLUENT:
            fluent_widgets = self._get_fluent_module()
            # Note: Fluent widgets might not have direct progress dialog, 
            # we'll use our focus-aware implementation in both cases
        
        # Always use our enhanced focus-aware progress dialog for now
        from fm_dicom.widgets.focus_aware import FocusAwareProgressDialog
        return FocusAwareProgressDialog(label_text, cancel_text, minimum, maximum, parent)
    
    def create_info_bar(self, title: str, content: str, parent: Optional[QWidget] = None):
        """Create an info bar for notifications"""
        if self.detector.get_framework() == UIFramework.FLUENT:
            fluent_widgets = self._get_fluent_module()
            if fluent_widgets and hasattr(fluent_widgets, 'InfoBar'):
                # Fluent InfoBar needs specific positioning
                return fluent_widgets.InfoBar.success(
                    title=title,
                    content=content,
                    orient=fluent_widgets.Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=fluent_widgets.InfoBarPosition.TOP,
                    duration=3000,
                    parent=parent
                )
        
        # Fallback to message box for now
        from fm_dicom.widgets.focus_aware import FocusAwareMessageBox
        return FocusAwareMessageBox.information(parent, title, content)
    
    def apply_theme(self, widget: QWidget, theme: str = "light"):
        """Apply theme to widget"""
        if self.detector.get_framework() == UIFramework.FLUENT:
            fluent_widgets = self._get_fluent_module()
            if fluent_widgets and hasattr(fluent_widgets, 'setTheme'):
                if theme == "dark":
                    fluent_widgets.setTheme(fluent_widgets.Theme.DARK)
                else:
                    fluent_widgets.setTheme(fluent_widgets.Theme.LIGHT)
                return
        
        # Fallback to existing theme system
        if theme == "dark":
            from fm_dicom.themes.theme_manager import set_dark_palette
            set_dark_palette(widget)
        else:
            from fm_dicom.themes.theme_manager import set_light_palette
            set_light_palette(widget)


# Global factory instance
_widget_factory: Optional[WidgetFactory] = None

def get_widget_factory() -> WidgetFactory:
    """Get global widget factory instance"""
    global _widget_factory
    if _widget_factory is None:
        _widget_factory = WidgetFactory()
    return _widget_factory

def get_framework_info() -> Dict[str, Any]:
    """Get information about current framework"""
    detector = FrameworkDetector()
    framework = detector.get_framework()
    
    return {
        'framework': framework.value,
        'fluent_available': detector.is_fluent_available(),
        'version': _get_framework_version(framework)
    }

def _get_framework_version(framework: UIFramework) -> str:
    """Get version of current framework"""
    if framework == UIFramework.FLUENT:
        try:
            import qfluentwidgets
            return getattr(qfluentwidgets, '__version__', 'unknown')
        except ImportError:
            return 'not available'
    else:
        try:
            from PyQt6.QtCore import QT_VERSION_STR
            return QT_VERSION_STR
        except ImportError:
            return 'unknown'