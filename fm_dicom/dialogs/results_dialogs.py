"""
Results dialog classes for displaying analysis and performance test results.

This module contains dialog classes that display various test results with export capabilities:
- FileAnalysisResultsDialog: Displays file analysis results with CSV/text export
- PerformanceResultsDialog: Displays performance test results with export capabilities
"""

import csv
import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog,
    QTableWidget, QTableWidgetItem, QLabel, QGroupBox
)
from PyQt6.QtGui import QFont
from fm_dicom.widgets.focus_aware import FocusAwareMessageBox


class FileAnalysisResultsDialog(QDialog):
    """Dialog to display file analysis results with export capabilities"""
    
    def __init__(self, analysis_results, parent=None):
        super().__init__(parent)
        self.analysis_results = analysis_results
        self.setWindowTitle("File Analysis Results")
        self.setModal(True)
        self.resize(900, 600)
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Summary section
        summary_group = QGroupBox("Summary")
        summary_layout = QVBoxLayout(summary_group)
        
        total_files = len(self.analysis_results['files'])
        unique_dimensions = len(self.analysis_results['unique_dimensions'])
        patients_count = len(self.analysis_results['unique_patients'])
        
        summary_text = f"""
        Total Files: {total_files}
        Unique Patients: {patients_count}
        Unique Image Dimensions: {unique_dimensions}
        Size Range: {self.analysis_results['size_range']}
        Large Files (>10MB): {len(self.analysis_results['large_files'])}
        Transfer Syntaxes: {len(self.analysis_results['transfer_syntaxes'])}
        """
        
        summary_label = QLabel(summary_text)
        summary_label.setFont(QFont("monospace"))
        summary_layout.addWidget(summary_label)
        layout.addWidget(summary_group)
        
        # Detailed results table
        results_group = QGroupBox("Detailed File Analysis")
        results_layout = QVBoxLayout(results_group)
        
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(9)
        self.results_table.setHorizontalHeaderLabels([
            "Filename", "Patient ID", "Dimensions", "Bits", "Photometric", 
            "Transfer Syntax", "Uncompressed Size", "File Size", "Compression Ratio"
        ])
        
        # Populate table
        self.results_table.setRowCount(len(self.analysis_results['files']))
        for row, file_info in enumerate(self.analysis_results['files']):
            self.results_table.setItem(row, 0, QTableWidgetItem(file_info['filename']))
            self.results_table.setItem(row, 1, QTableWidgetItem(file_info['patient_id']))
            self.results_table.setItem(row, 2, QTableWidgetItem(file_info['dimensions']))
            self.results_table.setItem(row, 3, QTableWidgetItem(str(file_info['bits'])))
            self.results_table.setItem(row, 4, QTableWidgetItem(file_info['photometric']))
            self.results_table.setItem(row, 5, QTableWidgetItem(file_info['transfer_syntax_name']))
            self.results_table.setItem(row, 6, QTableWidgetItem(f"{file_info['uncompressed_mb']:.1f} MB"))
            self.results_table.setItem(row, 7, QTableWidgetItem(f"{file_info['file_size_mb']:.1f} MB"))
            self.results_table.setItem(row, 8, QTableWidgetItem(f"{file_info['compression_ratio']:.1f}x"))
        
        self.results_table.resizeColumnsToContents()
        results_layout.addWidget(self.results_table)
        layout.addWidget(results_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        export_csv_btn = QPushButton("Export CSV")
        export_csv_btn.clicked.connect(self.export_csv)
        
        export_report_btn = QPushButton("Export Report")
        export_report_btn.clicked.connect(self.export_report)
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        
        button_layout.addWidget(export_csv_btn)
        button_layout.addWidget(export_report_btn)
        button_layout.addStretch()
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
    
    def export_csv(self):
        """Export results to CSV file"""
        filename, _ = self.parent()._get_save_filename(
            "Export Analysis Results", 
            "file_analysis_results.csv", 
            "CSV Files (*.csv)"
        )
        if not filename:
            return
            
        try:
            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                
                # Write header
                headers = [
                    "Filename", "Patient ID", "Dimensions", "Bits", "Photometric",
                    "Transfer Syntax", "Uncompressed Size (MB)", "File Size (MB)", "Compression Ratio"
                ]
                writer.writerow(headers)
                
                # Write data
                for file_info in self.analysis_results['files']:
                    writer.writerow([
                        file_info['filename'],
                        file_info['patient_id'],
                        file_info['dimensions'],
                        file_info['bits'],
                        file_info['photometric'],
                        file_info['transfer_syntax_name'],
                        f"{file_info['uncompressed_mb']:.1f}",
                        f"{file_info['file_size_mb']:.1f}",
                        f"{file_info['compression_ratio']:.1f}"
                    ])
            
            FocusAwareMessageBox.information(self, "Export Complete", f"Analysis results exported to:\n{filename}")
            
        except Exception as e:
            FocusAwareMessageBox.critical(self, "Export Error", f"Failed to export CSV:\n{str(e)}")
    
    def export_report(self):
        """Export detailed report to text file"""
        filename, _ = self.parent()._get_save_filename(
            "Export Analysis Report", 
            "file_analysis_report.txt", 
            "Text Files (*.txt)"
        )
        if not filename:
            return
            
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write("DICOM FILE ANALYSIS REPORT\n")
                f.write("=" * 50 + "\n\n")
                
                # Summary
                f.write("SUMMARY\n")
                f.write("-" * 20 + "\n")
                f.write(f"Total Files: {len(self.analysis_results['files'])}\n")
                f.write(f"Unique Patients: {len(self.analysis_results['unique_patients'])}\n")
                f.write(f"Unique Dimensions: {self.analysis_results['unique_dimensions']}\n")
                f.write(f"Size Range: {self.analysis_results['size_range']}\n")
                f.write(f"Large Files (>10MB): {len(self.analysis_results['large_files'])}\n\n")
                
                # Transfer Syntaxes
                f.write("TRANSFER SYNTAXES\n")
                f.write("-" * 20 + "\n")
                for ts_name, count in self.analysis_results['transfer_syntaxes'].items():
                    f.write(f"  {ts_name}: {count} files\n")
                f.write("\n")
                
                # Large Files
                if self.analysis_results['large_files']:
                    f.write("LARGE FILES (>10MB uncompressed)\n")
                    f.write("-" * 35 + "\n")
                    for file_info in self.analysis_results['large_files']:
                        f.write(f"  {file_info['filename']}: {file_info['dimensions']}, {file_info['uncompressed_mb']:.1f}MB\n")
                    f.write("\n")
                
                # Detailed file list
                f.write("DETAILED FILE LIST\n")
                f.write("-" * 20 + "\n")
                for file_info in self.analysis_results['files']:
                    f.write(f"File: {file_info['filename']}\n")
                    f.write(f"  Patient: {file_info['patient_id']}\n")
                    f.write(f"  Dimensions: {file_info['dimensions']}\n")
                    f.write(f"  Transfer Syntax: {file_info['transfer_syntax_name']}\n")
                    f.write(f"  Size: {file_info['file_size_mb']:.1f}MB (compressed), {file_info['uncompressed_mb']:.1f}MB (uncompressed)\n")
                    f.write(f"  Compression: {file_info['compression_ratio']:.1f}x\n\n")
            
            FocusAwareMessageBox.information(self, "Export Complete", f"Analysis report exported to:\n{filename}")
            
        except Exception as e:
            FocusAwareMessageBox.critical(self, "Export Error", f"Failed to export report:\n{str(e)}")


class PerformanceResultsDialog(QDialog):
    """Dialog to display performance test results with export capabilities"""
    
    def __init__(self, performance_results, parent=None):
        super().__init__(parent)
        self.performance_results = performance_results
        self.setWindowTitle("Performance Test Results")
        self.setModal(True)
        self.resize(800, 500)
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Summary section
        summary_group = QGroupBox("Performance Summary")
        summary_layout = QVBoxLayout(summary_group)
        
        results = self.performance_results
        avg_load_time = sum(r['load_time'] for r in results['files']) / len(results['files'])
        avg_pixel_time = sum(r['pixel_time'] for r in results['files']) / len(results['files'])
        avg_total_time = sum(r['total_time'] for r in results['files']) / len(results['files'])
        
        summary_text = f"""
        Files Tested: {len(results['files'])}
        Average Load Time: {avg_load_time:.3f}s
        Average Pixel Access Time: {avg_pixel_time:.3f}s
        Average Total Time: {avg_total_time:.3f}s
        Slow Files (>0.5s): {len(results['slow_files'])}
        Fastest File: {results['fastest_file']['filename']} ({results['fastest_file']['total_time']:.3f}s)
        Slowest File: {results['slowest_file']['filename']} ({results['slowest_file']['total_time']:.3f}s)
        """
        
        summary_label = QLabel(summary_text)
        summary_label.setFont(QFont("monospace"))
        summary_layout.addWidget(summary_label)
        layout.addWidget(summary_group)
        
        # Performance results table
        results_group = QGroupBox("Detailed Performance Results")
        results_layout = QVBoxLayout(results_group)
        
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(5)
        self.results_table.setHorizontalHeaderLabels([
            "Filename", "Load Time (s)", "Pixel Time (s)", "Total Time (s)", "Status"
        ])
        
        # Populate table (show slowest first)
        sorted_files = sorted(results['files'], key=lambda x: x['total_time'], reverse=True)
        self.results_table.setRowCount(len(sorted_files))
        
        for row, file_info in enumerate(sorted_files):
            self.results_table.setItem(row, 0, QTableWidgetItem(file_info['filename']))
            self.results_table.setItem(row, 1, QTableWidgetItem(f"{file_info['load_time']:.3f}"))
            self.results_table.setItem(row, 2, QTableWidgetItem(f"{file_info['pixel_time']:.3f}"))
            self.results_table.setItem(row, 3, QTableWidgetItem(f"{file_info['total_time']:.3f}"))
            
            # Status based on performance
            if file_info['total_time'] > 0.5:
                status = "Slow"
            elif file_info['total_time'] > 0.1:
                status = "Moderate"
            else:
                status = "Fast"
            self.results_table.setItem(row, 4, QTableWidgetItem(status))
        
        self.results_table.resizeColumnsToContents()
        results_layout.addWidget(self.results_table)
        layout.addWidget(results_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        export_csv_btn = QPushButton("Export CSV")
        export_csv_btn.clicked.connect(self.export_csv)
        
        export_report_btn = QPushButton("Export Report")
        export_report_btn.clicked.connect(self.export_report)
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        
        button_layout.addWidget(export_csv_btn)
        button_layout.addWidget(export_report_btn)
        button_layout.addStretch()
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
    
    def export_csv(self):
        """Export performance results to CSV"""
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Performance Results", "performance_results.csv", "CSV Files (*.csv)"
        )
        if not filename:
            return
            
        try:
            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                
                # Write header
                writer.writerow(["Filename", "Load Time (s)", "Pixel Time (s)", "Total Time (s)", "Status"])
                
                # Write data
                for file_info in self.performance_results['files']:
                    status = "Slow" if file_info['total_time'] > 0.5 else "Moderate" if file_info['total_time'] > 0.1 else "Fast"
                    writer.writerow([
                        file_info['filename'],
                        f"{file_info['load_time']:.3f}",
                        f"{file_info['pixel_time']:.3f}",
                        f"{file_info['total_time']:.3f}",
                        status
                    ])
            
            FocusAwareMessageBox.information(self, "Export Complete", f"Performance results exported to:\n{filename}")
            
        except Exception as e:
            FocusAwareMessageBox.critical(self, "Export Error", f"Failed to export CSV:\n{str(e)}")
    
    def export_report(self):
        """Export detailed performance report"""
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Performance Report", "performance_report.txt", "Text Files (*.txt)"
        )
        if not filename:
            return
            
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                results = self.performance_results
                
                f.write("DICOM PERFORMANCE TEST REPORT\n")
                f.write("=" * 40 + "\n\n")
                
                # Summary
                avg_load = sum(r['load_time'] for r in results['files']) / len(results['files'])
                avg_pixel = sum(r['pixel_time'] for r in results['files']) / len(results['files'])
                avg_total = sum(r['total_time'] for r in results['files']) / len(results['files'])
                
                f.write("PERFORMANCE SUMMARY\n")
                f.write("-" * 20 + "\n")
                f.write(f"Files Tested: {len(results['files'])}\n")
                f.write(f"Average Load Time: {avg_load:.3f}s\n")
                f.write(f"Average Pixel Time: {avg_pixel:.3f}s\n")
                f.write(f"Average Total Time: {avg_total:.3f}s\n")
                f.write(f"Slow Files (>0.5s): {len(results['slow_files'])}\n\n")
                
                # Slow files section
                if results['slow_files']:
                    f.write("SLOW FILES (>0.5s total time)\n")
                    f.write("-" * 30 + "\n")
                    for file_info in results['slow_files']:
                        f.write(f"  {file_info['filename']}: {file_info['total_time']:.3f}s\n")
                    f.write("\n")
                
                # Detailed results
                f.write("DETAILED PERFORMANCE RESULTS\n")
                f.write("-" * 30 + "\n")
                f.write(f"{'Filename':<30} {'Load':<8} {'Pixel':<8} {'Total':<8} {'Status'}\n")
                f.write("-" * 60 + "\n")
                
                sorted_files = sorted(results['files'], key=lambda x: x['total_time'], reverse=True)
                for file_info in sorted_files:
                    status = "Slow" if file_info['total_time'] > 0.5 else "Moderate" if file_info['total_time'] > 0.1 else "Fast"
                    f.write(f"{file_info['filename']:<30} {file_info['load_time']:<8.3f} {file_info['pixel_time']:<8.3f} {file_info['total_time']:<8.3f} {status}\n")
            
            FocusAwareMessageBox.information(self, "Export Complete", f"Performance report exported to:\n{filename}")
            
        except Exception as e:
            FocusAwareMessageBox.critical(self, "Export Error", f"Failed to export report:\n{str(e)}")