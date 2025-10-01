from PyQt6.QtWidgets import QMessageBox, QProgressDialog, QApplication, QLabel
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
    """QProgressDialog that doesn't steal focus unless app is already active

    Enhanced with:
    - Fixed width to prevent resizing when text changes
    - Text truncation with ellipsis for long filenames
    - Tooltips showing full text when truncated
    - Consistent sizing across different progress operations
    """

    def __init__(self, labelText, cancelButtonText, minimum, maximum, parent=None, fixed_width=550):
        super().__init__(labelText, cancelButtonText, minimum, maximum, parent)

        # Configure non-focus-stealing behavior
        self._configure_focus_behavior()

        # Install event filter to handle keyboard events
        self.installEventFilter(self)

        # Configure fixed sizing and text handling
        self._fixed_width = fixed_width
        self._original_label_text = labelText
        self._setup_consistent_sizing()

    def _setup_consistent_sizing(self):
        """Configure consistent dialog sizing"""
        self.setFixedWidth(self._fixed_width)
        self.setMinimumHeight(160)  # Increased height for multi-line text

        # Configure label for text wrapping and multi-line support
        label = self.findChild(QLabel)
        if label:
            label.setWordWrap(True)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            # Set maximum width slightly less than dialog to account for margins
            label.setMaximumWidth(self._fixed_width - 40)
            # Set minimum height to accommodate 2-3 lines of text
            label.setMinimumHeight(60)
            # Allow text to use available vertical space
            from PyQt6.QtWidgets import QSizePolicy
            label.setSizePolicy(label.sizePolicy().horizontalPolicy(), QSizePolicy.Policy.Expanding)

    def setLabelText(self, text):
        """Override setLabelText to handle text truncation and tooltips"""
        # Format text for better multi-line display if it contains DICOM info
        formatted_text = self._format_text_for_display(text)
        truncated_text = self._truncate_text(formatted_text)
        super().setLabelText(truncated_text)

        # Set tooltip if text was truncated
        if truncated_text != formatted_text:
            self.setToolTip(text)
        else:
            self.setToolTip("")

    def _format_text_for_display(self, text):
        """Format text for better multi-line display in progress dialogs"""
        # For DICOM operations, try to use multiple lines for better readability
        if self._contains_dicom_info(text) and len(text) > 70:
            # Split long text into two lines at natural break points
            parts = text.split(': ', 1)
            if len(parts) == 2:
                operation, details = parts
                # If details are long, try to break them sensibly
                if len(details) > 50:
                    # Look for natural break points (path separators, patient info, etc.)
                    if os.path.sep in details:
                        # For file paths, break at directory separator
                        path_parts = details.split(os.path.sep)
                        if len(path_parts) > 2:
                            mid_point = len(path_parts) // 2
                            line1 = os.path.sep.join(path_parts[:mid_point]) + os.path.sep
                            line2 = os.path.sep.join(path_parts[mid_point:])
                            return f"{operation}:\n{line1}\n{line2}"
                    elif ' | ' in details:
                        # For structured info, break at pipe separators
                        info_parts = details.split(' | ')
                        if len(info_parts) > 2:
                            mid_point = len(info_parts) // 2
                            line1 = ' | '.join(info_parts[:mid_point])
                            line2 = ' | '.join(info_parts[mid_point:])
                            return f"{operation}:\n{line1}\n{line2}"

        return text

    def _truncate_text(self, text, max_length=90):
        """Truncate text with ellipsis if too long, preserving important DICOM information"""
        if len(text) <= max_length:
            return text

        # For DICOM progress text, try to preserve important identifiers
        if self._contains_dicom_info(text):
            return self._truncate_dicom_text(text, max_length)

        # For file paths, try to show filename and some of the path
        if os.path.sep in text:
            path_parts = text.split(os.path.sep)
            filename = path_parts[-1]
            if len(filename) <= max_length - 10:  # Leave room for "..." and some path
                remaining_length = max_length - len(filename) - 4  # 4 for "..." + separator
                if remaining_length > 0:
                    partial_path = text[:remaining_length]
                    return f"{partial_path}...{os.path.sep}{filename}"

        # Generic truncation
        return text[:max_length-3] + "..." if len(text) > max_length else text

    def _contains_dicom_info(self, text):
        """Check if text contains DICOM-specific information"""
        dicom_indicators = [
            'Patient', 'Study', 'Series', 'Instance', 'UID',
            '.dcm', '.dicom', 'Anonymizing', 'Validating',
            'CT_', 'MR_', 'US_', 'XA_', 'RF_'  # Common modality prefixes
        ]
        return any(indicator in text for indicator in dicom_indicators)

    def _truncate_dicom_text(self, text, max_length):
        """Smart truncation for DICOM-related text"""
        # Try to preserve important parts: operation, count, and key identifiers
        parts = text.split(': ', 1)  # Split on first colon
        if len(parts) == 2:
            prefix, content = parts

            # Keep the operation prefix (e.g., "Processing (1/10)")
            if len(prefix) < max_length - 20:  # Leave room for content
                remaining_length = max_length - len(prefix) - 3  # 3 for ": "

                # Try to preserve important identifiers in content
                if remaining_length > 10:
                    truncated_content = self._preserve_important_identifiers(content, remaining_length)
                    return f"{prefix}: {truncated_content}"

        # Fallback to generic truncation
        return text[:max_length-3] + "..."

    def _preserve_important_identifiers(self, content, max_length):
        """Preserve important medical/DICOM identifiers when truncating"""
        # Look for patterns like Patient IDs, Series numbers, UIDs
        import re

        # Find important patterns
        uid_match = re.search(r'\d+\.\d+\.\d+[\d\.]*', content)  # UIDs
        patient_match = re.search(r'Patient[\s_]*[:\-]?[\s]*([^\s\-_]+)', content, re.IGNORECASE)
        series_match = re.search(r'Series[\s_]*[:\-]?[\s]*(\d+)', content, re.IGNORECASE)
        instance_match = re.search(r'Instance[\s_]*[:\-]?[\s]*(\d+)', content, re.IGNORECASE)

        # Build truncated version preserving key info
        important_parts = []

        if patient_match and len(important_parts) < 3:
            important_parts.append(f"Pat:{patient_match.group(1)[:8]}")
        if series_match and len(important_parts) < 3:
            important_parts.append(f"Ser:{series_match.group(1)}")
        if instance_match and len(important_parts) < 3:
            important_parts.append(f"Inst:{instance_match.group(1)}")
        if uid_match and len(important_parts) < 2:
            uid_short = uid_match.group(0)
            if len(uid_short) > 12:
                uid_short = uid_short[:8] + "..."
            important_parts.append(f"UID:{uid_short}")

        if important_parts:
            result = " | ".join(important_parts)
            if len(result) <= max_length:
                return result

        # Fallback: just truncate normally
        return content[:max_length-3] + "..." if len(content) > max_length else content
    
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