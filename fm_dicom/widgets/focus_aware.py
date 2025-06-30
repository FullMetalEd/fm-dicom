from PyQt6.QtWidgets import QMessageBox, QProgressDialog, QApplication
from PyQt6.QtCore import Qt


class FocusAwareMessageBox(QMessageBox):
    """QMessageBox that doesn't steal focus unless app is already active"""
    
    def __init__(self, icon, title, text, buttons=QMessageBox.StandardButton.Ok, parent=None):
        super().__init__(icon, title, text, buttons, parent)
        
        # If app doesn't have focus, prevent focus stealing
        if not self._app_has_focus():
            self.setWindowFlags(
                self.windowFlags() | 
                Qt.WindowType.WindowDoesNotAcceptFocus
            )
    
    def _app_has_focus(self):
        """Check if our app currently has focus"""
        return QApplication.activeWindow() is not None
    
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
        
        # If app doesn't have focus, prevent focus stealing
        if not self._app_has_focus():
            self.setWindowFlags(
                self.windowFlags() | 
                Qt.WindowType.WindowDoesNotAcceptFocus
            )
            self.setModal(False)  # Don't block other apps
    
    def _app_has_focus(self):
        """Check if our app currently has focus"""
        return QApplication.activeWindow() is not None