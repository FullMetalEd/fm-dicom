"""
Utility dialogs for log viewing and settings editing.
"""

import os
import yaml
import logging
import shutil
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QTextEdit, QLabel,
    QCheckBox, QGroupBox, QFormLayout, QApplication
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, QTimer

from fm_dicom.widgets.focus_aware import FocusAwareMessageBox


class LogViewerDialog(QDialog):
    """Live log viewer dialog with tail -f functionality"""
    
    def __init__(self, log_path, parent=None):
        super().__init__(parent)
        self.log_path = log_path
        self.file_position = 0
        self.is_paused = False
        self.auto_scroll = True
        
        self.setWindowTitle(f"Log Viewer - {os.path.basename(log_path)}")
        self.setModal(False)  # Non-modal so user can interact with main app
        self.resize(800, 600)
        
        self.setup_ui()
        self.setup_timer()
        self.load_initial_content()
        
    def setup_ui(self):
        """Setup the UI components"""
        layout = QVBoxLayout(self)
        
        # Toolbar
        toolbar_layout = QHBoxLayout()
        
        self.pause_btn = QPushButton("Pause")
        self.pause_btn.setCheckable(True)
        self.pause_btn.clicked.connect(self.toggle_pause)
        
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self.clear_log_display)
        
        self.auto_scroll_cb = QCheckBox("Auto-scroll")
        self.auto_scroll_cb.setChecked(True)
        self.auto_scroll_cb.stateChanged.connect(self.toggle_auto_scroll)
        
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.force_refresh)
        
        self.copy_btn = QPushButton("Copy All")
        self.copy_btn.clicked.connect(self.copy_to_clipboard)
        
        toolbar_layout.addWidget(self.pause_btn)
        toolbar_layout.addWidget(self.clear_btn)
        toolbar_layout.addWidget(self.auto_scroll_cb)
        toolbar_layout.addWidget(self.refresh_btn)
        toolbar_layout.addWidget(self.copy_btn)
        toolbar_layout.addStretch()
        
        # Status label
        self.status_label = QLabel(f"Watching: {self.log_path}")
        self.status_label.setStyleSheet("QLabel { color: #888; font-size: 10px; }")
        
        # Log content area
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("monospace", 9))
        
        # Set dark theme for log viewer
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #1a1a1a;
                color: #f0f0f0;
                border: 1px solid #444;
                selection-background-color: #0078d4;
            }
        """)
        
        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        
        # Layout
        layout.addLayout(toolbar_layout)
        layout.addWidget(self.status_label)
        layout.addWidget(self.log_text)
        layout.addWidget(close_btn)
        
    def setup_timer(self):
        """Setup timer for periodic log updates"""
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_log_content)
        self.update_timer.start(1000)  # Update every 1 second
        
    def load_initial_content(self):
        """Load initial log content (last 1000 lines)"""
        try:
            if not os.path.exists(self.log_path):
                self.log_text.append(f"Log file does not exist: {self.log_path}")
                return
                
            with open(self.log_path, 'r', encoding='utf-8', errors='ignore') as f:
                # Read last 1000 lines
                lines = f.readlines()
                if len(lines) > 1000:
                    lines = lines[-1000:]
                    self.log_text.append("... (showing last 1000 lines) ...\n")
                
                content = ''.join(lines)
                self.log_text.append(content)
                
                # Set file position to end
                f.seek(0, 2)  # Seek to end
                self.file_position = f.tell()
                
            if self.auto_scroll:
                self.scroll_to_bottom()
                
        except Exception as e:
            self.log_text.append(f"Error reading log file: {e}")
            
    def update_log_content(self):
        """Update log content with new lines (tail -f behavior)"""
        if self.is_paused:
            return
            
        try:
            if not os.path.exists(self.log_path):
                return
                
            with open(self.log_path, 'r', encoding='utf-8', errors='ignore') as f:
                # Check if file was truncated (log rotation)
                f.seek(0, 2)  # Seek to end
                current_size = f.tell()
                
                if current_size < self.file_position:
                    # File was truncated, start from beginning
                    self.file_position = 0
                    self.log_text.append("\n--- Log file was rotated ---\n")
                
                # Read new content
                f.seek(self.file_position)
                new_content = f.read()
                
                if new_content:
                    # Color-code log levels
                    new_content = self.colorize_log_content(new_content)
                    self.log_text.append(new_content)
                    self.file_position = f.tell()
                    
                    if self.auto_scroll:
                        self.scroll_to_bottom()
                        
        except Exception as e:
            # Don't spam errors, just log once
            if not hasattr(self, '_error_logged'):
                self.log_text.append(f"Error updating log: {e}")
                self._error_logged = True
                
    def colorize_log_content(self, content):
        """Add basic color coding for log levels"""
        # This is basic - you could make it more sophisticated
        lines = content.split('\n')
        colored_lines = []
        
        for line in lines:
            if '[ERROR]' in line or '[CRITICAL]' in line:
                colored_lines.append(f'<span style="color: #ff6b6b;">{line}</span>')
            elif '[WARNING]' in line or '[WARN]' in line:
                colored_lines.append(f'<span style="color: #ffa500;">{line}</span>')
            elif '[INFO]' in line:
                colored_lines.append(f'<span style="color: #87ceeb;">{line}</span>')
            elif '[DEBUG]' in line:
                colored_lines.append(f'<span style="color: #98fb98;">{line}</span>')
            else:
                colored_lines.append(line)
        
        return '\n'.join(colored_lines)
    
    def scroll_to_bottom(self):
        """Scroll to bottom of log"""
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        
    def toggle_pause(self, checked):
        """Toggle pause/resume log updates"""
        self.is_paused = checked
        self.pause_btn.setText("Resume" if checked else "Pause")
        
        if checked:
            self.status_label.setText(f"PAUSED - {self.log_path}")
            self.status_label.setStyleSheet("QLabel { color: #ff6b6b; font-size: 10px; }")
        else:
            self.status_label.setText(f"Watching: {self.log_path}")
            self.status_label.setStyleSheet("QLabel { color: #888; font-size: 10px; }")
            
    def toggle_auto_scroll(self, state):
        """Toggle auto-scroll feature"""
        self.auto_scroll = (state == Qt.CheckState.Checked.value)
        
    def clear_log_display(self):
        """Clear the log display (not the actual log file)"""
        self.log_text.clear()
        
    def force_refresh(self):
        """Force refresh the log content"""
        self.log_text.clear()
        self.file_position = 0
        self.load_initial_content()
        
    def copy_to_clipboard(self):
        """Copy all log content to clipboard"""
        clipboard = QApplication.clipboard()
        clipboard.setText(self.log_text.toPlainText())
        
        # Brief status update
        original_text = self.status_label.text()
        self.status_label.setText("Copied to clipboard!")
        QTimer.singleShot(2000, lambda: self.status_label.setText(original_text))
        
    def closeEvent(self, event):
        """Clean up when closing"""
        # Close log viewer if open
        if hasattr(self, 'log_viewer') and self.log_viewer:
            self.log_viewer.close()
            
        if hasattr(self, 'update_timer'):
            self.update_timer.stop()
        event.accept()


class SettingsEditorDialog(QDialog):
    """Dialog for editing application settings as YAML"""
    
    def __init__(self, config_data, config_file_path, parent=None):
        super().__init__(parent)
        self.config_data = config_data
        self.config_file_path = config_file_path
        self.setWindowTitle("Settings Editor")
        self.setModal(True)
        self.resize(800, 600)
        self.setup_ui()
        self.load_yaml_content()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Header with file path
        header_layout = QHBoxLayout()
        header_label = QLabel("Editing configuration file:")
        self.path_label = QLabel(self.config_file_path)
        self.path_label.setStyleSheet("font-family: monospace; color: #888;")
        header_layout.addWidget(header_label)
        header_layout.addWidget(self.path_label)
        header_layout.addStretch()
        layout.addLayout(header_layout)
        
        # YAML editor
        editor_group = QGroupBox("Configuration (YAML Format)")
        editor_layout = QVBoxLayout(editor_group)
        
        self.yaml_editor = QTextEdit()
        self.yaml_editor.setFont(QFont("monospace", 10))
        
        # Basic YAML syntax highlighting
        self._setup_syntax_highlighting()
        
        editor_layout.addWidget(self.yaml_editor)
        layout.addWidget(editor_group)
        
        # Validation status
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: green; font-weight: bold;")
        layout.addWidget(self.status_label)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        validate_btn = QPushButton("Validate YAML")
        validate_btn.clicked.connect(self.validate_yaml)
        
        reset_btn = QPushButton("Reset to Original")
        reset_btn.clicked.connect(self.load_yaml_content)
        
        save_btn = QPushButton("Save & Apply")
        save_btn.clicked.connect(self.save_and_apply)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        
        button_layout.addWidget(validate_btn)
        button_layout.addWidget(reset_btn)
        button_layout.addStretch()
        button_layout.addWidget(save_btn)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
        
        # Auto-validate on text change (with delay)
        self.validation_timer = QTimer()
        self.validation_timer.setSingleShot(True)
        self.validation_timer.timeout.connect(self.validate_yaml_silent)
        self.yaml_editor.textChanged.connect(self._on_text_changed)
    
    def _setup_syntax_highlighting(self):
        """Setup basic YAML syntax highlighting"""
        try:
            # Simple YAML highlighting
            self.yaml_editor.setStyleSheet("""
                QTextEdit {
                    background-color: #2b2b2b;
                    color: #f8f8f2;
                    border: 1px solid #3c3c3c;
                    font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
                    font-size: 11px;
                    line-height: 1.4;
                }
            """)
        except Exception as e:
            logging.warning(f"Could not setup syntax highlighting: {e}")
    
    def load_yaml_content(self):
        """Load current configuration as YAML text"""
        try:
            yaml_content = yaml.dump(self.config_data, default_flow_style=False, sort_keys=False, allow_unicode=True)
            self.yaml_editor.setPlainText(yaml_content)
            self.status_label.setText("✅ Configuration loaded")
            self.status_label.setStyleSheet("color: green; font-weight: bold;")
        except Exception as e:
            self.status_label.setText(f"❌ Error loading config: {e}")
            self.status_label.setStyleSheet("color: red; font-weight: bold;")
    
    def _on_text_changed(self):
        """Called when text changes - start validation timer"""
        self.validation_timer.stop()
        self.validation_timer.start(1000)  # Validate after 1 second of no typing
    
    def validate_yaml_silent(self):
        """Validate YAML without showing success message"""
        try:
            yaml_text = self.yaml_editor.toPlainText()
            yaml.safe_load(yaml_text)
            self.status_label.setText("✅ Valid YAML")
            self.status_label.setStyleSheet("color: green; font-weight: bold;")
            return True
        except yaml.YAMLError as e:
            self.status_label.setText(f"❌ YAML Error: {str(e)}")
            self.status_label.setStyleSheet("color: red; font-weight: bold;")
            return False
        except Exception as e:
            self.status_label.setText(f"❌ Parse Error: {str(e)}")
            self.status_label.setStyleSheet("color: red; font-weight: bold;")
            return False
    
    def validate_yaml(self):
        """Validate YAML and show result"""
        if self.validate_yaml_silent():
            FocusAwareMessageBox.information(self, "Validation Success", "YAML syntax is valid!")
        else:
            FocusAwareMessageBox.warning(self, "Validation Failed", "Please fix the YAML syntax errors before saving.")
    
    def save_and_apply(self):
        """Save the YAML configuration and apply changes"""
        # Validate first
        if not self.validate_yaml_silent():
            reply = FocusAwareMessageBox.question(
                self, "Invalid YAML",
                "The YAML contains syntax errors. Save anyway?",
                FocusAwareMessageBox.StandardButton.Yes | FocusAwareMessageBox.StandardButton.No,
                FocusAwareMessageBox.StandardButton.No
            )
            if reply != FocusAwareMessageBox.StandardButton.Yes:
                return
        
        try:
            # Parse the YAML
            yaml_text = self.yaml_editor.toPlainText()
            new_config = yaml.safe_load(yaml_text)
            
            if new_config is None:
                new_config = {}
            
            # Validate required fields exist
            self._validate_config_structure(new_config)
            
            # Create backup of original file
            backup_path = self.config_file_path + ".backup"
            if os.path.exists(self.config_file_path):
                shutil.copy2(self.config_file_path, backup_path)
                logging.info(f"Created config backup: {backup_path}")
            
            # Ensure directory exists
            config_dir = os.path.dirname(self.config_file_path)
            os.makedirs(config_dir, exist_ok=True)
            
            # Save the new configuration
            with open(self.config_file_path, 'w', encoding='utf-8') as f:
                yaml.dump(new_config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
            
            self.status_label.setText("✅ Configuration saved successfully!")
            self.status_label.setStyleSheet("color: green; font-weight: bold;")
            
            # Return the new config for the parent to apply
            self.new_config = new_config
            
            FocusAwareMessageBox.information(
                self, "Settings Saved",
                f"Configuration saved successfully!\n\n"
                f"File: {self.config_file_path}\n"
                f"Backup: {backup_path}\n\n"
                "Some changes may require restarting the application."
            )
            
            self.accept()
            
        except Exception as e:
            logging.error(f"Failed to save configuration: {e}")
            FocusAwareMessageBox.critical(
                self, "Save Failed",
                f"Failed to save configuration:\n\n{str(e)}\n\n"
                f"Your changes have not been saved."
            )
    
    def _validate_config_structure(self, config):
        """Validate that required configuration keys exist"""
        required_keys = ['log_path', 'log_level', 'ae_title']
        missing_keys = []
        
        for key in required_keys:
            if key not in config or config[key] is None:
                missing_keys.append(key)
        
        if missing_keys:
            reply = FocusAwareMessageBox.question(
                self, "Missing Required Settings",
                f"The following required settings are missing or null:\n\n"
                f"{', '.join(missing_keys)}\n\n"
                f"This may cause the application to malfunction. Continue anyway?",
                FocusAwareMessageBox.StandardButton.Yes | FocusAwareMessageBox.StandardButton.No,
                FocusAwareMessageBox.StandardButton.No
            )
            if reply != FocusAwareMessageBox.StandardButton.Yes:
                raise ValueError(f"Missing required configuration keys: {missing_keys}")