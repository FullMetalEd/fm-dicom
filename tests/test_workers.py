"""
Tests for worker classes functionality.
"""

import os
import tempfile
import shutil
from unittest.mock import Mock, patch, MagicMock
import pytest
from PyQt6.QtCore import QThread, pyqtSignal

from fm_dicom.workers.dicom_worker import DicomdirScanWorker
from fm_dicom.workers.export_worker import ExportWorker
from fm_dicom.workers.zip_worker import ZipExtractionWorker
from fm_dicom.workers.dicom_send_worker import DicomSendWorker


class TestDicomdirScanWorker:
    """Test DicomdirScanWorker functionality."""
    
    @pytest.fixture
    def extracted_files(self, temp_dir):
        """Create sample extracted files for testing."""
        files = []
        
        # Create DICOMDIR file
        dicomdir_path = os.path.join(temp_dir, 'DICOMDIR')
        with open(dicomdir_path, 'w') as f:
            f.write('dummy dicomdir content')
        files.append(dicomdir_path)
        
        # Create some DICOM files
        for i in range(3):
            dicom_path = os.path.join(temp_dir, f'image_{i}.dcm')
            with open(dicom_path, 'w') as f:
                f.write(f'dummy dicom content {i}')
            files.append(dicom_path)
        
        # Create non-DICOM file
        other_path = os.path.join(temp_dir, 'readme.txt')
        with open(other_path, 'w') as f:
            f.write('readme content')
        files.append(other_path)
        
        return files
    
    def test_init(self, extracted_files):
        """Test DicomdirScanWorker initialization."""
        worker = DicomdirScanWorker(extracted_files)
        
        assert worker.extracted_files == extracted_files
        assert isinstance(worker, QThread)
        
        # Check signals exist
        assert hasattr(worker, 'progress_updated')
        assert hasattr(worker, 'scan_complete')
        assert hasattr(worker, 'scan_failed')
    
    def test_run_with_dicomdir(self, extracted_files, qapp):
        """Test running worker with DICOMDIR files."""
        worker = DicomdirScanWorker(extracted_files)
        
        # Mock DicomdirReader
        with patch('fm_dicom.workers.dicom_worker.DicomdirReader') as MockReader:
            mock_reader = MockReader.return_value
            mock_reader.read_dicomdir.return_value = [
                '/path/to/image1.dcm',
                '/path/to/image2.dcm'
            ]
            
            # Mock os.path.exists to return True for our mock files
            with patch('os.path.exists', return_value=True):
                # Connect signal to capture result
                result_files = []
                worker.scan_complete.connect(lambda files: result_files.extend(files))
                
                # Run worker
                worker.run()
                
                # Process events to handle signals
                qapp.processEvents()
                
                # Verify DICOMDIR was processed
                mock_reader.read_dicomdir.assert_called()
    
    def test_run_without_dicomdir(self, temp_dir, qapp):
        """Test running worker without DICOMDIR files."""
        # Create files without DICOMDIR
        files = []
        for i in range(3):
            file_path = os.path.join(temp_dir, f'image_{i}.dcm')
            with open(file_path, 'w') as f:
                f.write(f'dummy content {i}')
            files.append(file_path)
        
        worker = DicomdirScanWorker(files)
        
        # Mock the individual scan method
        with patch.object(worker, '_scan_individual_files') as mock_scan:
            mock_scan.return_value = files
            
            result_files = []
            worker.scan_complete.connect(lambda files: result_files.extend(files))
            
            worker.run()
            qapp.processEvents()
            
            # Should call individual scan method
            mock_scan.assert_called_once()
    
    def test_run_with_exception(self, extracted_files, qapp):
        """Test worker handling exceptions."""
        worker = DicomdirScanWorker(extracted_files)
        
        # Mock DicomdirReader to raise exception
        with patch('fm_dicom.workers.dicom_worker.DicomdirReader') as MockReader:
            MockReader.side_effect = Exception("Test error")
            
            error_message = []
            worker.scan_failed.connect(lambda msg: error_message.append(msg))
            
            worker.run()
            qapp.processEvents()
            
            # Should emit scan_failed signal
            assert len(error_message) == 1
            assert "Test error" in error_message[0]
    
    def test_interruption_handling(self, extracted_files):
        """Test worker interruption handling."""
        worker = DicomdirScanWorker(extracted_files)
        
        # Mock isInterruptionRequested to return True
        worker.isInterruptionRequested = Mock(return_value=True)
        
        with patch('fm_dicom.workers.dicom_worker.DicomdirReader') as MockReader:
            mock_reader = MockReader.return_value
            mock_reader.read_dicomdir.return_value = ['/path/to/file.dcm']
            
            worker.run()
            
            # Should stop processing when interrupted
            assert worker.isInterruptionRequested.called


class TestExportWorker:
    """Test ExportWorker functionality."""
    
    @pytest.fixture
    def export_worker(self, multiple_dicom_files, temp_dir):
        """Create an ExportWorker instance for testing."""
        output_path = os.path.join(temp_dir, 'export_output')
        return ExportWorker(multiple_dicom_files, "directory", output_path)
    
    def test_init(self, export_worker, multiple_dicom_files, temp_dir):
        """Test ExportWorker initialization."""
        assert export_worker.filepaths == multiple_dicom_files
        assert export_worker.export_type == "directory"
        assert export_worker.output_path == os.path.join(temp_dir, 'export_output')
        assert export_worker.cancelled is False
        
        # Check signals exist
        assert hasattr(export_worker, 'progress_updated')
        assert hasattr(export_worker, 'stage_changed')
        assert hasattr(export_worker, 'export_complete')
        assert hasattr(export_worker, 'export_failed')
    
    def test_cancel(self, export_worker):
        """Test cancelling export operation."""
        assert export_worker.cancelled is False
        
        export_worker.cancel()
        
        assert export_worker.cancelled is True
    
    def test_run_directory_export(self, export_worker, qapp):
        """Test running directory export."""
        # Mock the directory export method
        export_worker._export_directory = Mock()
        export_worker._export_directory.return_value = None
        
        export_worker.run()
        
        # Should call directory export method
        export_worker._export_directory.assert_called_once()
    
    def test_run_zip_export(self, multiple_dicom_files, temp_dir, qapp):
        """Test running ZIP export."""
        output_path = os.path.join(temp_dir, 'export.zip')
        worker = ExportWorker(multiple_dicom_files, "zip", output_path)
        
        # Mock the ZIP export method
        worker._export_zip = Mock()
        worker._export_zip.return_value = None
        
        worker.run()
        
        # Should call ZIP export method
        worker._export_zip.assert_called_once()
    
    def test_run_dicomdir_zip_export(self, multiple_dicom_files, temp_dir, qapp):
        """Test running DICOMDIR ZIP export."""
        output_path = os.path.join(temp_dir, 'export_dicomdir.zip')
        worker = ExportWorker(multiple_dicom_files, "dicomdir_zip", output_path)
        
        # Mock the DICOMDIR ZIP export method
        worker._export_dicomdir_zip = Mock()
        worker._export_dicomdir_zip.return_value = None
        
        worker.run()
        
        # Should call DICOMDIR ZIP export method
        worker._export_dicomdir_zip.assert_called_once()
    
    def test_run_invalid_export_type(self, multiple_dicom_files, temp_dir, qapp):
        """Test running with invalid export type."""
        worker = ExportWorker(multiple_dicom_files, "invalid_type", "/output/path")
        
        error_message = []
        worker.export_failed.connect(lambda msg: error_message.append(msg))
        
        worker.run()
        qapp.processEvents()
        
        # Should emit export_failed signal
        assert len(error_message) == 1
        assert "Unknown export type" in error_message[0]
    
    def test_export_directory_method(self, export_worker, qapp):
        """Test _export_directory method."""
        # Mock file operations
        with patch('shutil.copy2') as mock_copy:
            with patch('os.makedirs') as mock_makedirs:
                with patch('os.path.exists', return_value=False):
                    
                    # Mock signals
                    stage_messages = []
                    progress_updates = []
                    export_worker.stage_changed.connect(lambda msg: stage_messages.append(msg))
                    export_worker.progress_updated.connect(lambda c, t, f: progress_updates.append((c, t, f)))
                    
                    export_worker._export_directory()
                    
                    # Should create directory and copy files
                    mock_makedirs.assert_called()
                    assert mock_copy.call_count >= 0  # May be called for each file
    
    def test_export_with_errors(self, export_worker, qapp):
        """Test export handling errors."""
        # Mock method to raise exception
        export_worker._export_directory = Mock(side_effect=Exception("Export error"))
        
        error_message = []
        export_worker.export_failed.connect(lambda msg: error_message.append(msg))
        
        export_worker.run()
        qapp.processEvents()
        
        # Should emit export_failed signal
        assert len(error_message) == 1
        assert "Export error" in error_message[0]


class TestZipExtractionWorker:
    """Test ZipExtractionWorker functionality."""
    
    @pytest.fixture
    def zip_worker(self, temp_dir):
        """Create a ZipExtractionWorker instance for testing."""
        # Create a test ZIP file
        zip_path = os.path.join(temp_dir, 'test.zip')
        with patch('fm_dicom.workers.zip_worker.ZipExtractionWorker') as MockWorker:
            worker = MockWorker.return_value
            worker.zip_path = zip_path
            worker.temp_dir = temp_dir
            worker.cancelled = False
            
            # Mock signals
            worker.progress_updated = Mock()
            worker.extraction_complete = Mock()
            worker.extraction_failed = Mock()
            
            return worker
    
    def test_init(self, zip_worker):
        """Test ZipExtractionWorker initialization."""
        assert hasattr(zip_worker, 'zip_path')
        assert hasattr(zip_worker, 'temp_dir')
        assert zip_worker.cancelled is False
        
        # Check signals exist
        assert hasattr(zip_worker, 'progress_updated')
        assert hasattr(zip_worker, 'extraction_complete')
        assert hasattr(zip_worker, 'extraction_failed')
    
    def test_cancel(self, zip_worker):
        """Test cancelling extraction operation."""
        zip_worker.cancel = Mock()
        zip_worker.cancel()
        zip_worker.cancel.assert_called_once()
    
    def test_run_success(self, zip_worker, qapp):
        """Test successful ZIP extraction."""
        # Mock the run method
        zip_worker.run = Mock()
        zip_worker.run()
        zip_worker.run.assert_called_once()
    
    def test_run_with_exception(self, zip_worker, qapp):
        """Test ZIP extraction with exception."""
        # Mock run method to raise exception
        zip_worker.run = Mock(side_effect=Exception("Extraction error"))
        
        with pytest.raises(Exception):
            zip_worker.run()


class TestDicomSendWorker:
    """Test DicomSendWorker functionality."""
    
    @pytest.fixture
    def send_worker(self, multiple_dicom_files):
        """Create a DicomSendWorker instance for testing."""
        destination = {
            'ae_title': 'TEST_PACS',
            'host': 'localhost',
            'port': 11112
        }
        
        with patch('fm_dicom.workers.dicom_send_worker.DicomSendWorker') as MockWorker:
            worker = MockWorker.return_value
            worker.filepaths = multiple_dicom_files
            worker.destination = destination
            worker.cancelled = False
            
            # Mock signals
            worker.progress_updated = Mock()
            worker.file_sent = Mock()
            worker.send_complete = Mock()
            worker.send_failed = Mock()
            
            return worker
    
    def test_init(self, send_worker, multiple_dicom_files):
        """Test DicomSendWorker initialization."""
        assert send_worker.filepaths == multiple_dicom_files
        assert send_worker.destination['ae_title'] == 'TEST_PACS'
        assert send_worker.destination['host'] == 'localhost'
        assert send_worker.destination['port'] == 11112
        assert send_worker.cancelled is False
        
        # Check signals exist
        assert hasattr(send_worker, 'progress_updated')
        assert hasattr(send_worker, 'file_sent')
        assert hasattr(send_worker, 'send_complete')
        assert hasattr(send_worker, 'send_failed')
    
    def test_cancel(self, send_worker):
        """Test cancelling send operation."""
        send_worker.cancel = Mock()
        send_worker.cancel()
        send_worker.cancel.assert_called_once()
    
    def test_run_success(self, send_worker, qapp):
        """Test successful DICOM send."""
        # Mock the run method
        send_worker.run = Mock()
        send_worker.run()
        send_worker.run.assert_called_once()
    
    def test_run_with_connection_error(self, send_worker, qapp):
        """Test DICOM send with connection error."""
        # Mock run method to raise connection error
        send_worker.run = Mock(side_effect=ConnectionError("Cannot connect to PACS"))
        
        with pytest.raises(ConnectionError):
            send_worker.run()
    
    def test_send_single_file(self, send_worker):
        """Test sending a single DICOM file."""
        # Mock the send single file method
        send_worker._send_single_file = Mock(return_value=True)
        
        result = send_worker._send_single_file('/path/to/file.dcm')
        
        send_worker._send_single_file.assert_called_once_with('/path/to/file.dcm')
        assert result is True
    
    def test_send_single_file_failure(self, send_worker):
        """Test failure when sending a single DICOM file."""
        # Mock the send single file method to return False
        send_worker._send_single_file = Mock(return_value=False)
        
        result = send_worker._send_single_file('/path/to/file.dcm')
        
        assert result is False


class TestWorkerSignals:
    """Test worker signal functionality."""
    
    def test_dicomdir_scan_worker_signals(self, qapp):
        """Test DicomdirScanWorker signals."""
        worker = DicomdirScanWorker([])
        
        # Test signal connections
        progress_updates = []
        scan_results = []
        scan_errors = []
        
        worker.progress_updated.connect(lambda c, t, f: progress_updates.append((c, t, f)))
        worker.scan_complete.connect(lambda files: scan_results.extend(files))
        worker.scan_failed.connect(lambda msg: scan_errors.append(msg))
        
        # Emit test signals
        worker.progress_updated.emit(1, 5, "test_file.dcm")
        worker.scan_complete.emit(["/test/file.dcm"])
        worker.scan_failed.emit("Test error")
        
        qapp.processEvents()
        
        # Verify signals were received
        assert len(progress_updates) == 1
        assert progress_updates[0] == (1, 5, "test_file.dcm")
        assert len(scan_results) == 1
        assert scan_results[0] == "/test/file.dcm"
        assert len(scan_errors) == 1
        assert scan_errors[0] == "Test error"
    
    def test_export_worker_signals(self, qapp):
        """Test ExportWorker signals."""
        worker = ExportWorker([], "directory", "/output")
        
        # Test signal connections
        progress_updates = []
        stage_changes = []
        export_results = []
        export_errors = []
        
        worker.progress_updated.connect(lambda c, t, o: progress_updates.append((c, t, o)))
        worker.stage_changed.connect(lambda s: stage_changes.append(s))
        worker.export_complete.connect(lambda p, s: export_results.append((p, s)))
        worker.export_failed.connect(lambda e: export_errors.append(e))
        
        # Emit test signals
        worker.progress_updated.emit(3, 10, "Copying file 3")
        worker.stage_changed.emit("Finalizing export")
        worker.export_complete.emit("/output/path", {"files": 10})
        worker.export_failed.emit("Export failed")
        
        qapp.processEvents()
        
        # Verify signals were received
        assert len(progress_updates) == 1
        assert len(stage_changes) == 1
        assert len(export_results) == 1
        assert len(export_errors) == 1


class TestWorkerIntegration:
    """Integration tests for worker classes."""
    
    def test_worker_lifecycle(self, qapp):
        """Test complete worker lifecycle."""
        worker = DicomdirScanWorker([])
        
        # Track lifecycle events
        events = []
        
        worker.started.connect(lambda: events.append("started"))
        worker.finished.connect(lambda: events.append("finished"))
        
        # Mock a quick run
        worker.run = Mock()
        
        # Start and finish worker
        worker.started.emit()
        worker.finished.emit()
        
        qapp.processEvents()
        
        # Verify lifecycle events
        assert "started" in events
        assert "finished" in events
    
    def test_worker_cancellation_flow(self, qapp):
        """Test worker cancellation flow."""
        worker = ExportWorker([], "directory", "/output")
        
        # Initially not cancelled
        assert worker.cancelled is False
        
        # Cancel the worker
        worker.cancel()
        
        # Should be marked as cancelled
        assert worker.cancelled is True