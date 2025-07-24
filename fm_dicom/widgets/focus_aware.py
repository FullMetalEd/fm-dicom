from PyQt6.QtWidgets import QMessageBox, QProgressDialog, QApplication
from PyQt6.QtCore import Qt


class FocusAwareMessageBox(QMessageBox):
    """QMessageBox that doesn't steal focus unless app is already active"""
    
    def __init__(self, icon, title, text, buttons=QMessageBox.StandardButton.Ok, parent=None):
        super().__init__(icon, title, text, buttons, parent)
        
        # Configure non-focus-stealing behavior
        self._configure_focus_behavior()
    
    def _configure_focus_behavior(self):
        """Configure the dialog to not steal focus when app doesn't have focus"""
        # If app doesn't have focus, prevent focus stealing
        if not self._app_has_focus():
            self.setWindowFlags(
                self.windowFlags() | 
                Qt.WindowType.WindowDoesNotAcceptFocus
            )
    
    def show(self):
        """Override show to recheck focus behavior"""
        self._configure_focus_behavior()
        super().show()
    
    def exec(self):
        """Override exec to recheck focus behavior"""
        self._configure_focus_behavior()
        return super().exec()
    
    def _app_has_focus(self):
        """Check if our app currently has focus"""
        app = QApplication.instance()
        if app is None:
            return False
        
        # Check if any of our app's windows have focus
        active_window = app.activeWindow()
        if active_window is not None:
            return True
        
        # Additional check: see if any top-level widgets are active
        for widget in app.topLevelWidgets():
            if widget.isActiveWindow():
                return True
                
        return False
    
    @staticmethod
    def information(parent, title, text, *args, **kwargs):
        """Drop-in replacement for QMessageBox.information"""
        msgbox = FocusAwareMessageBox(QMessageBox.Icon.Information, title, text, parent=parent)
        return msgbox.exec()
    
    @staticmethod
    def warning(parent, title, text, *args, **kwargs):
        """Drop-in replacement for QMessageBox.warning"""
        msgbox = FocusAwareMessageBox(QMessageBox.Icon.Warning, title, text, parent=parent)
        return msgbox.exec()
    
    @staticmethod
    def critical(parent, title, text, *args, **kwargs):
        """Drop-in replacement for QMessageBox.critical"""
        msgbox = FocusAwareMessageBox(QMessageBox.Icon.Critical, title, text, parent=parent)
        return msgbox.exec()
    
    @staticmethod
    def question(parent, title, text, buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, defaultButton=QMessageBox.StandardButton.NoButton, *args, **kwargs):
        """Drop-in replacement for QMessageBox.question"""
        msgbox = FocusAwareMessageBox(QMessageBox.Icon.Question, title, text, buttons, parent)
        if defaultButton != QMessageBox.StandardButton.NoButton:
            msgbox.setDefaultButton(defaultButton)
        return msgbox.exec()


class FocusAwareProgressDialog(QProgressDialog):
    """QProgressDialog that doesn't steal focus unless app is already active"""
    
    def __init__(self, labelText, cancelButtonText, minimum, maximum, parent=None):
        super().__init__(labelText, cancelButtonText, minimum, maximum, parent)
        
        # Configure non-focus-stealing behavior
        self._configure_focus_behavior()
    
    def _configure_focus_behavior(self):
        """Configure the dialog to not steal focus when app doesn't have focus"""
        # If app doesn't have focus, prevent focus stealing
        if not self._app_has_focus():
            self.setWindowFlags(
                self.windowFlags() | 
                Qt.WindowType.WindowDoesNotAcceptFocus
            )
            self.setModal(False)  # Don't block other apps
    
    def show(self):
        """Override show to recheck focus behavior"""
        self._configure_focus_behavior()
        super().show()
    
    def exec(self):
        """Override exec to recheck focus behavior"""
        self._configure_focus_behavior()
        return super().exec()
    
    def _app_has_focus(self):
        """Check if our app currently has focus"""
        app = QApplication.instance()
        if app is None:
            return False
        
        # Check if any of our app's windows have focus
        active_window = app.activeWindow()
        if active_window is not None:
            return True
        
        # Additional check: see if any top-level widgets are active
        for widget in app.topLevelWidgets():
            if widget.isActiveWindow():
                return True
                
        return False