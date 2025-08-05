from PyQt6.QtWidgets import QMessageBox, QProgressDialog, QApplication
from PyQt6.QtCore import Qt, QEvent
import os


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
        
        # Install event filter to handle keyboard events
        self.installEventFilter(self)
    
    def _configure_focus_behavior(self):
        """Configure the dialog to not steal focus when app doesn't have focus"""
        # If app doesn't have focus, prevent focus stealing and workspace following
        if not self._app_has_focus():
            window_flags = (
                self.windowFlags() | 
                Qt.WindowType.WindowDoesNotAcceptFocus |
                Qt.WindowType.WindowStaysOnTopHint
            )
            
            # Additional Wayland/Hyprland specific flags
            if self._is_wayland():
                window_flags |= Qt.WindowType.Tool
            
            self.setWindowFlags(window_flags)
            self.setModal(False)  # Don't block other apps
        else:
            # App has focus, allow normal behavior but prevent workspace following
            window_flags = self.windowFlags()
            if self._is_wayland():
                window_flags |= Qt.WindowType.Tool
            self.setWindowFlags(window_flags)
    
    def show(self):
        """Override show to recheck focus behavior"""
        self._configure_focus_behavior()
        super().show()
    
    def exec(self):
        """Override exec to recheck focus behavior"""
        self._configure_focus_behavior()
        return super().exec()
    
    def eventFilter(self, obj, event):
        """Filter events to prevent accidental cancellation"""
        if obj == self and event.type() == QEvent.Type.KeyPress:
            # Prevent Enter/Return from canceling the dialog accidentally
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                # Look for cancel button more reliably
                from PyQt6.QtWidgets import QPushButton
                cancel_buttons = self.findChildren(QPushButton)
                cancel_button = None
                
                # Find the cancel button
                for button in cancel_buttons:
                    if button.text().lower() in ['cancel', '&cancel']:
                        cancel_button = button
                        break
                
                # Only allow cancellation if the cancel button has focus
                if cancel_button and cancel_button.hasFocus():
                    return super().eventFilter(obj, event)
                
                # Otherwise, ignore the key press to prevent accidental cancellation
                return True
        return super().eventFilter(obj, event)
    
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
        
        # Wayland/Hyprland specific check - check if we're the focused application
        if self._is_wayland():
            # On Wayland, activeWindow() may not work reliably
            # Check if any of our windows are visible and potentially focused
            for widget in app.topLevelWidgets():
                if widget.isVisible() and not widget.isMinimized():
                    return True
                
        return False
    
    def _is_wayland(self):
        """Check if we're running on Wayland"""
        return (
            os.environ.get('WAYLAND_DISPLAY') is not None or
            os.environ.get('QT_QPA_PLATFORM') == 'wayland' or
            'wayland' in os.environ.get('QT_QPA_PLATFORM', '').lower()
        )