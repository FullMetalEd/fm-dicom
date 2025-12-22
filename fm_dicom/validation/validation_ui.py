"""
DICOM Validation User Interface
Provides dialogs and widgets for displaying validation results.
"""

import os
import logging
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QTreeWidget, QTreeWidgetItem,
    QTextEdit, QTabWidget, QWidget, QLabel, QProgressDialog, QApplication,
    QHeaderView, QGroupBox, QGridLayout, QLineEdit, QComboBox, QCheckBox,
    QFileDialog, QMessageBox, QSplitter, QFrame
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QIcon, QFont, QColor, QPixmap
import csv
import json
from datetime import datetime
import pydicom
from .validation import DicomValidator, ValidationSeverity, CollectionValidationResult
from fm_dicom.widgets.focus_aware import FocusAwareProgressDialog

class ValidationWorker(QThread):
    """Worker thread for running validation without blocking UI"""
    progress_updated = pyqtSignal(int, str)  # progress, current_file
    validation_complete = pyqtSignal(object)  # CollectionValidationResult
    
    def __init__(self, file_paths):
        super().__init__()
        self.file_paths = file_paths
        self.validator = DicomValidator()
        
    def run(self):
        try:
            total_files = len(self.file_paths)
            collection_result = CollectionValidationResult()
            valid_datasets = []
            
            # Validate individual files with progress updates
            for idx, file_path in enumerate(self.file_paths):
                # Emit progress update
                self.progress_updated.emit(idx + 1, file_path)
                
                # Validate the file
                file_result = self.validator.validate_file(file_path)
                collection_result.add_file_result(file_result)
                
                if file_result.dataset is not None:
                    valid_datasets.append((file_result.dataset, file_path))
                    
                # Allow thread to be interrupted
                if self.isInterruptionRequested():
                    return
                    
            # Apply collection-level rules
            for rule in self.validator.rules:
                try:
                    collection_issues = rule.validate_collection(valid_datasets)
                    collection_result.collection_issues.extend(collection_issues)
                except Exception as e:
                    logging.error(f"Error applying collection rule {rule.name}: {e}")
                    
            # Generate statistics
            collection_result.statistics = self.validator._generate_statistics(valid_datasets)
            
            self.validation_complete.emit(collection_result)
            
        except Exception as e:
            logging.error(f"Validation worker error: {e}", exc_info=True)
            # Emit empty result on error
            empty_result = CollectionValidationResult()
            self.validation_complete.emit(empty_result)

class ValidationProgressDialog(FocusAwareProgressDialog):
    """Progress dialog for validation operations"""
    
    def __init__(self, file_paths, parent=None):
        super().__init__("Initializing validation...", "Cancel", 0, len(file_paths), parent, fixed_width=550)
        self.setWindowTitle("DICOM Validation")
        self.setMinimumDuration(0)
        self.setAutoClose(False)
        self.setAutoReset(False)
        
        self.file_paths = file_paths
        self.result = None
        
        # Start validation in worker thread
        self.worker = ValidationWorker(file_paths)
        self.worker.progress_updated.connect(self.update_progress)
        self.worker.validation_complete.connect(self.validation_finished)
        self.worker.start()
        
        # Cancel handling
        self.canceled.connect(self.cancel_validation)
        
    def update_progress(self, progress, current_file):
        self.setValue(progress)
        # Use consistent format with progress count
        progress_text = f"Validating ({progress}/{len(self.file_paths)}): {os.path.basename(current_file)}"
        self.setLabelText(progress_text)
        QApplication.processEvents()
        
    def validation_finished(self, result):
        self.result = result
        self.setValue(len(self.file_paths))
        self.setLabelText("Validation complete")
        self.accept()
        
    def cancel_validation(self):
        if self.worker.isRunning():
            self.worker.requestInterruption()  # Use requestInterruption instead of terminate
            self.worker.wait(3000)  # Wait up to 3 seconds for graceful shutdown
            if self.worker.isRunning():
                self.worker.terminate()  # Force terminate if needed
                self.worker.wait()
        self.reject()

class ValidationResultsWidget(QWidget):
    """Widget for displaying validation results"""
    
    def __init__(self, validation_result: CollectionValidationResult, parent=None):
        super().__init__(parent)
        self.validation_result = validation_result
        self.setup_ui()
        self.populate_results()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Summary section
        self.create_summary_section(layout)
        
        # Main results area
        splitter = QSplitter(Qt.Orientation.Vertical)  # Vertical splitter for dock
        layout.addWidget(splitter)
        
        # Issue tree
        self.create_issue_tree(splitter)
        
        # Details and statistics
        self.create_details_section(splitter)
        
        # Buttons
        self.create_buttons(layout)
        
    def create_summary_section(self, layout):
        """Create the summary section at the top"""
        summary_group = QGroupBox("Validation Summary")
        summary_layout = QGridLayout(summary_group)
        
        summary = self.validation_result.get_summary()
        
        # Create summary labels - Compact version for Dock
        labels = [
            ("Files:", str(summary['total_files'])),
            ("Valid:", str(summary['valid_files'])),
            ("Errors:", str(summary['files_with_errors'])),
            ("Warnings:", str(summary['files_with_warnings']))
        ]
        
        for i, (label_text, value_text) in enumerate(labels):
            label = QLabel(label_text)
            label.setFont(QFont("", 9, QFont.Weight.Bold))
            summary_layout.addWidget(label, 0, i*2)
            
            value = QLabel(value_text)
            if "Errors" in label_text and int(value_text) > 0:
                value.setStyleSheet("color: red; font-weight: bold;")
            elif "Warnings" in label_text and int(value_text) > 0:
                value.setStyleSheet("color: orange; font-weight: bold;")
            elif "Valid" in label_text:
                value.setStyleSheet("color: green; font-weight: bold;")
                
            summary_layout.addWidget(value, 0, i*2 + 1)
            
        layout.addWidget(summary_group)
        
    def create_issue_tree(self, splitter):
        """Create the issue tree widget"""
        tree_widget = QWidget()
        tree_layout = QVBoxLayout(tree_widget)
        tree_layout.setContentsMargins(0, 0, 0, 0)
        
        # Filter controls
        filter_layout = QHBoxLayout()
        
        self.severity_filter = QComboBox()
        self.severity_filter.addItems(["All", "Errors Only", "Warnings Only", "Info Only"])
        self.severity_filter.currentTextChanged.connect(self.filter_issues)
        filter_layout.addWidget(QLabel("Show:"))
        filter_layout.addWidget(self.severity_filter)
        
        tree_layout.addLayout(filter_layout)
        
        # Issues tree
        self.issues_tree = QTreeWidget()
        self.issues_tree.setHeaderLabels(["Issue", "Severity", "Category", "File"])
        self.issues_tree.itemSelectionChanged.connect(self.on_issue_selected)
        tree_layout.addWidget(self.issues_tree)
        
        splitter.addWidget(tree_widget)
        
    def create_details_section(self, splitter):
        """Create the details and statistics section"""
        self.details_tabs = QTabWidget()
        
        # Issue details tab
        self.details_text = QTextEdit()
        self.details_text.setReadOnly(True)
        self.details_tabs.addTab(self.details_text, "Details")
        
        # Statistics tab
        self.stats_text = QTextEdit()
        self.stats_text.setReadOnly(True)
        self.details_tabs.addTab(self.stats_text, "Stats")
        
        splitter.addWidget(self.details_tabs)
        
    def create_buttons(self, layout):
        """Create the button bar"""
        button_layout = QHBoxLayout()
        
        export_btn = QPushButton("Export Report")
        export_btn.clicked.connect(self.export_report)
        button_layout.addWidget(export_btn)
        
        export_csv_btn = QPushButton("Export CSV")
        export_csv_btn.clicked.connect(self.export_csv)
        button_layout.addWidget(export_csv_btn)
        
        layout.addLayout(button_layout)

    def populate_results(self):
        """Populate the widget with validation results"""
        self.issues_tree.clear()
        categories = set()
        
        # Add collection-level issues
        if self.validation_result.collection_issues:
            collection_item = QTreeWidgetItem(["Collection Issues", "", "", ""])
            collection_item.setFont(0, QFont("", 10, QFont.Weight.Bold))
            self.issues_tree.addTopLevelItem(collection_item)
            
            for issue in self.validation_result.collection_issues:
                categories.add(issue.category)
                issue_item = QTreeWidgetItem([
                    issue.message, issue.severity, issue.category, "Collection"
                ])
                self.set_item_color(issue_item, issue.severity)
                collection_item.addChild(issue_item)
                
        # Add file-level issues
        for file_path, file_result in self.validation_result.file_results.items():
            if file_result.issues:
                file_item = QTreeWidgetItem([
                    os.path.basename(file_path), "", "", file_path
                ])
                file_item.setFont(0, QFont("", 9, QFont.Weight.Bold))
                self.issues_tree.addTopLevelItem(file_item)
                
                for issue in file_result.issues:
                    categories.add(issue.category)
                    issue_item = QTreeWidgetItem([
                        issue.message, issue.severity, issue.category, os.path.basename(file_path)
                    ])
                    self.set_item_color(issue_item, issue.severity)
                    issue_item.setData(0, Qt.ItemDataRole.UserRole, issue)
                    file_item.addChild(issue_item)
        
        self.issues_tree.expandAll()
        for i in range(self.issues_tree.columnCount()):
            self.issues_tree.resizeColumnToContents(i)
            
        self.populate_statistics()

    def set_item_color(self, item, severity):
        if severity == ValidationSeverity.ERROR:
            color = QColor(255, 0, 0)
        elif severity == ValidationSeverity.WARNING:
            color = QColor(255, 165, 0)
        else:
            color = QColor(0, 0, 255)
        for col in range(item.columnCount()):
            item.setForeground(col, color)

    def filter_issues(self):
        severity_filter = self.severity_filter.currentText()
        for i in range(self.issues_tree.topLevelItemCount()):
            top_item = self.issues_tree.topLevelItem(i)
            visible_children = 0
            for j in range(top_item.childCount()):
                child = top_item.child(j)
                child_severity = child.text(1)
                
                if severity_filter == "All":
                    show = True
                elif severity_filter == "Errors Only":
                    show = child_severity == ValidationSeverity.ERROR
                elif severity_filter == "Warnings Only":
                    show = child_severity == ValidationSeverity.WARNING
                elif severity_filter == "Info Only":
                    show = child_severity == ValidationSeverity.INFO
                else:
                    show = True
                
                child.setHidden(not show)
                if show: visible_children += 1
            top_item.setHidden(visible_children == 0)

    def on_issue_selected(self):
        current_item = self.issues_tree.currentItem()
        if current_item and current_item.data(0, Qt.ItemDataRole.UserRole):
            issue = current_item.data(0, Qt.ItemDataRole.UserRole)
            self.show_issue_details(issue)

    def show_issue_details(self, issue):
        details = f"<h3>{issue.severity}: {issue.category}</h3>"
        details += f"<p><strong>Message:</strong> {issue.message}</p>"
        details += f"<p><strong>File:</strong> {issue.file_path or 'Collection-level'}</p>"
        if issue.suggested_fix:
            details += f"<p><strong>Suggested Fix:</strong> {issue.suggested_fix}</p>"
        self.details_text.setHtml(details)

    def populate_statistics(self):
        stats = self.validation_result.statistics
        if not stats:
            self.stats_text.setText("No statistics available.")
            return
        
        html = "<h3>Statistics</h3>"
        if 'collection_summary' in stats:
            s = stats['collection_summary']
            html += f"<ul><li>Instances: {s.get('total_instances',0)}</li>"
            html += f"<li>Patients: {s.get('unique_patients',0)}</li></ul>"
        self.stats_text.setHtml(html)

    def export_report(self):
        # Delegate to a standalone helper or a temporary dialog that has the logic
        # For minimal code duplication, we instantiate the dialog hidden
        dlg = ValidationResultsDialog(self.validation_result, self)
        dlg.export_report()

    def export_csv(self):
        dlg = ValidationResultsDialog(self.validation_result, self)
        dlg.export_csv()


class ValidationResultsDialog(QDialog):
    """Main dialog for displaying validation results (Wrapper around Widget)"""
    
    def __init__(self, validation_result: CollectionValidationResult, parent=None):
        super().__init__(parent)
        self.validation_result = validation_result
        self.setWindowTitle("DICOM Validation Results")
        self.setModal(True)
        self.resize(1000, 700)
        
        layout = QVBoxLayout(self)
        self.widget = ValidationResultsWidget(validation_result, self)
        layout.addWidget(self.widget)
        
        buttons = QHBoxLayout()
        buttons.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        buttons.addWidget(close_btn)
        layout.addLayout(buttons)
    
    def export_report(self):
        """Export validation report as HTML"""
        # Create dialog and configure based on user preference
        default_filename = f"validation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        dialog = QFileDialog(self, "Export Validation Report", default_filename, "HTML Files (*.html)")
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setDefaultSuffix("html")
        
        # Configure native dialog preference (check if parent has config)
        if hasattr(self.parent(), 'config') and not self.parent().config.get("file_picker_native", False):
            dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        
        if dialog.exec():
            file_paths = dialog.selectedFiles()
            if not file_paths:
                return
            file_path = file_paths[0]
        else:
            return
        
        if file_path:
            try:
                self.generate_html_report(file_path)
                QMessageBox.information(self, "Export Complete", 
                                      f"Validation report exported to:\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", 
                                   f"Failed to export report:\n{str(e)}")
                
    def export_csv(self):
        """Export validation issues as CSV"""
        # Create dialog and configure based on user preference
        default_filename = f"validation_issues_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        dialog = QFileDialog(self, "Export Issues CSV", default_filename, "CSV Files (*.csv)")
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setDefaultSuffix("csv")
        
        # Configure native dialog preference (check if parent has config)
        if hasattr(self.parent(), 'config') and not self.parent().config.get("file_picker_native", False):
            dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        
        if dialog.exec():
            file_paths = dialog.selectedFiles()
            if not file_paths:
                return
            file_path = file_paths[0]
        else:
            return
        
        if file_path:
            try:
                self.generate_csv_report(file_path)
                QMessageBox.information(self, "Export Complete",
                                      f"Issues exported to:\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error",
                                   f"Failed to export CSV:\n{str(e)}")
                                   
    def generate_html_report(self, file_path):
        """Generate HTML validation report"""
        summary = self.validation_result.get_summary()
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>DICOM Validation Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .summary {{ background: #f0f0f0; padding: 15px; border-radius: 5px; }}
        .error {{ color: red; }}
        .warning {{ color: orange; }}
        .info {{ color: blue; }}
        table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
    </style>
</head>
<body>
    <h1>DICOM Validation Report</h1>
    <p>Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    
    <div class="summary">
        <h2>Summary</h2>
        <p>Total Files: {summary['total_files']}</p>
        <p>Valid Files: {summary['valid_files']}</p>
        <p class="error">Files with Errors: {summary['files_with_errors']}</p>
        <p class="warning">Files with Warnings: {summary['files_with_warnings']}</p>
        <p class="error">Total Errors: {summary['total_errors']}</p>
        <p class="warning">Total Warnings: {summary['total_warnings']}</p>
    </div>
    
    <h2>Issues</h2>
    <table>
        <tr>
            <th>Severity</th>
            <th>Category</th>
            <th>Message</th>
            <th>File</th>
            <th>Tag</th>
            <th>Suggested Fix</th>
        </tr>
"""
        
        # Add collection issues
        for issue in self.validation_result.collection_issues:
            severity_class = issue.severity.lower()
            html += f"""
        <tr class="{severity_class}">
            <td>{issue.severity}</td>
            <td>{issue.category}</td>
            <td>{issue.message}</td>
            <td>Collection</td>
            <td>{issue.tag or ''}</td>
            <td>{issue.suggested_fix or ''}</td>
        </tr>
"""
        
        # Add file issues
        for file_path, file_result in self.validation_result.file_results.items():
            for issue in file_result.issues:
                severity_class = issue.severity.lower()
                html += f"""
        <tr class="{severity_class}">
            <td>{issue.severity}</td>
            <td>{issue.category}</td>
            <td>{issue.message}</td>
            <td>{os.path.basename(file_path)}</td>
            <td>{issue.tag or ''}</td>
            <td>{issue.suggested_fix or ''}</td>
        </tr>
"""
        
        html += """
    </table>
</body>
</html>
"""
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(html)
            
    def generate_csv_report(self, file_path):
        """Generate CSV report of validation issues"""
        with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['Severity', 'Category', 'Message', 'File', 'Tag', 'Suggested Fix'])
            
            # Collection issues
            for issue in self.validation_result.collection_issues:
                writer.writerow([
                    issue.severity,
                    issue.category, 
                    issue.message,
                    'Collection',
                    issue.tag or '',
                    issue.suggested_fix or ''
                ])
                
            # File issues
            for file_path, file_result in self.validation_result.file_results.items():
                for issue in file_result.issues:
                    writer.writerow([
                        issue.severity,
                        issue.category,
                        issue.message,
                        os.path.basename(file_path),
                        issue.tag or '',
                        issue.suggested_fix or ''
                    ])

def run_validation(file_paths, parent=None):
    """Convenience function to run validation with progress dialog"""
    if not file_paths:
        QMessageBox.warning(parent, "No Files", "No files selected for validation.")
        return None
        
    # Show progress dialog
    progress_dialog = ValidationProgressDialog(file_paths, parent)
    
    if progress_dialog.exec() == QDialog.DialogCode.Accepted:
        result = progress_dialog.result
        if result and (result.file_results or result.collection_issues):
            
            # Use Action Center if available on parent window
            if parent and hasattr(parent, 'action_center'):
                # We need to construct the validation widget manually and add it
                # or have a method on action_center to accept result
                if hasattr(parent.action_center, 'show_validation_results'):
                    parent.action_center.show_validation_results(result)
                    parent.action_center.show()
                    return result
            
            # Fallback to dialog
            results_dialog = ValidationResultsDialog(result, parent)
            results_dialog.exec()
            return result
    
    return None
