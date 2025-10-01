"""
Utility dialogs for log viewing and settings editing.
"""

import os
import yaml
import logging
import shutil
import platform
import sys
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QTextEdit, QLabel,
    QCheckBox, QGroupBox, QFormLayout, QApplication, QTabWidget, QWidget, QTreeWidget, QTreeWidgetItem
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, QTimer

from fm_dicom.widgets.focus_aware import FocusAwareMessageBox
from fm_dicom.config.config_manager import get_config_diagnostics, get_config_path, load_config


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
            if config_dir:  # Only try to create directory if path is not empty
                try:
                    os.makedirs(config_dir, exist_ok=True)
                    logging.info(f"Ensured config directory exists: {config_dir}")
                except Exception as dir_error:
                    raise Exception(f"Failed to create config directory '{config_dir}': {dir_error}")
            else:
                # If config_dir is empty, the path is relative - this shouldn't happen with proper paths
                raise Exception(f"Invalid config path - cannot determine directory for '{self.config_file_path}'. This usually indicates a relative path was used instead of an absolute path.")
            
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


class ConfigDiagnosticsDialog(QDialog):
    """Dialog showing configuration diagnostics and troubleshooting information"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuration Diagnostics")
        self.setModal(True)
        self.resize(800, 600)

        self.setup_ui()
        self.load_diagnostics()

    def setup_ui(self):
        """Set up the user interface"""
        layout = QVBoxLayout(self)

        # Create tab widget
        self.tab_widget = QTabWidget()

        # Diagnostics tab
        self.diagnostics_tab = QWidget()
        self.setup_diagnostics_tab()
        self.tab_widget.addTab(self.diagnostics_tab, "Diagnostics")

        # Configuration tab
        self.config_tab = QWidget()
        self.setup_config_tab()
        self.tab_widget.addTab(self.config_tab, "Current Config")

        # Paths tab
        self.paths_tab = QWidget()
        self.setup_paths_tab()
        self.tab_widget.addTab(self.paths_tab, "Path Analysis")

        layout.addWidget(self.tab_widget)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.load_diagnostics)
        button_layout.addWidget(refresh_button)

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        button_layout.addWidget(close_button)

        layout.addLayout(button_layout)

    def setup_diagnostics_tab(self):
        """Set up the diagnostics tab"""
        layout = QVBoxLayout(self.diagnostics_tab)

        # System info
        system_label = QLabel("System Information:")
        system_label.setFont(QFont("", 0, QFont.Weight.Bold))
        layout.addWidget(system_label)

        self.system_info = QTextEdit()
        self.system_info.setMaximumHeight(120)
        self.system_info.setReadOnly(True)
        layout.addWidget(self.system_info)

        # Environment variables
        env_label = QLabel("Environment Variables:")
        env_label.setFont(QFont("", 0, QFont.Weight.Bold))
        layout.addWidget(env_label)

        self.env_tree = QTreeWidget()
        self.env_tree.setHeaderLabels(["Variable", "Value", "Accessible"])
        self.env_tree.setMaximumHeight(150)
        layout.addWidget(self.env_tree)

        # Issues and recommendations
        issues_label = QLabel("Issues and Recommendations:")
        issues_label.setFont(QFont("", 0, QFont.Weight.Bold))
        layout.addWidget(issues_label)

        self.issues_text = QTextEdit()
        self.issues_text.setReadOnly(True)
        layout.addWidget(self.issues_text)

    def setup_config_tab(self):
        """Set up the configuration tab"""
        layout = QVBoxLayout(self.config_tab)

        config_label = QLabel("Current Configuration:")
        config_label.setFont(QFont("", 0, QFont.Weight.Bold))
        layout.addWidget(config_label)

        self.config_text = QTextEdit()
        self.config_text.setReadOnly(True)
        self.config_text.setFont(QFont("Consolas, Monaco, monospace"))
        layout.addWidget(self.config_text)

    def setup_paths_tab(self):
        """Set up the paths analysis tab"""
        layout = QVBoxLayout(self.paths_tab)

        paths_label = QLabel("Configuration Path Analysis:")
        paths_label.setFont(QFont("", 0, QFont.Weight.Bold))
        layout.addWidget(paths_label)

        self.paths_tree = QTreeWidget()
        self.paths_tree.setHeaderLabels(["Path", "Exists", "Writable", "Notes"])
        layout.addWidget(self.paths_tree)

    def load_diagnostics(self):
        """Load and display diagnostic information"""
        try:
            # Load diagnostics
            diagnostics = get_config_diagnostics()
            config = load_config()

            # Update system info
            system_info = [
                f"System: {diagnostics['system']}",
                f"Running from executable: {diagnostics['is_executable']}",
                f"Python executable: {sys.executable}",
                f"Working directory: {os.getcwd()}"
            ]
            self.system_info.setPlainText("\n".join(system_info))

            # Update environment variables
            self.env_tree.clear()
            for var_name, var_info in diagnostics.get('environment_vars', {}).items():
                item = QTreeWidgetItem([
                    var_name,
                    var_info.get('value', 'Not set'),
                    "Yes" if var_info.get('accessible', False) else "No"
                ])
                self.env_tree.addTopLevelItem(item)

            # Update paths analysis
            self.paths_tree.clear()
            for path_info in diagnostics.get('paths_checked', []):
                notes = []
                if path_info.get('exists'):
                    notes.append("File exists")
                if path_info.get('parent_writable'):
                    notes.append("Directory writable")
                elif not path_info.get('exists'):
                    notes.append("Can create new file")

                if not notes:
                    notes.append("Issues detected")

                item = QTreeWidgetItem([
                    path_info.get('path', 'Unknown'),
                    "Yes" if path_info.get('exists') else "No",
                    "Yes" if path_info.get('parent_writable') else "No",
                    ", ".join(notes)
                ])
                self.paths_tree.addTopLevelItem(item)

            # Update issues and recommendations
            issues = []
            config_issues = config.get('_config_issues', {})

            if config_issues.get('using_memory_only'):
                issues.append("⚠️ Configuration could not be saved to disk - using memory only")
                issues.append(f"   Attempted path: {config_issues.get('preferred_path', 'Unknown')}")
                issues.append("   Consider:")
                issues.append("   - Running as administrator")
                issues.append("   - Checking folder permissions")
                issues.append("   - Using portable mode")

            if platform.system() == "Windows" and not diagnostics['is_executable']:
                issues.append("ℹ️ Running from Python script in development mode")
                issues.append("   Config will be created based on APPDATA/user profile")

            if not issues:
                issues.append("✅ No configuration issues detected")

            self.issues_text.setPlainText("\n".join(issues))

            # Update configuration display
            config_display = {}
            for key, value in config.items():
                if not key.startswith('_'):  # Skip internal diagnostic keys
                    config_display[key] = value

            config_yaml = yaml.dump(config_display, default_flow_style=False, sort_keys=True)
            self.config_text.setPlainText(config_yaml)

            # Resize columns
            self.env_tree.resizeColumnToContents(0)
            self.env_tree.resizeColumnToContents(1)
            self.paths_tree.resizeColumnToContents(0)
            self.paths_tree.resizeColumnToContents(1)
            self.paths_tree.resizeColumnToContents(2)

        except Exception as e:
            error_text = f"Error loading diagnostics: {e}"
            self.system_info.setPlainText(error_text)
            self.issues_text.setPlainText(error_text)
            self.config_text.setPlainText(error_text)