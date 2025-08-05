"""
Tests for FileManager functionality.
"""

import os
import tempfile
import shutil
from unittest.mock import Mock, patch, MagicMock
import pytest
import pydicom

from fm_dicom.managers.file_manager import FileManager


class TestFileManager:
    """Test FileManager functionality."""
    
    @pytest.fixture
    def file_manager(self, mock_main_window):
        """Create a FileManager instance for testing."""
        return FileManager(mock_main_window)
    
    def test_init(self, file_manager, mock_main_window):
        """Test FileManager initialization."""
        assert file_manager.main_window == mock_main_window
        assert file_manager.config == mock_main_window.config
        assert file_manager.temp_dirs == []
    
    def test_load_single_file_success(self, file_manager, sample_dicom_file):
        """Test successfully loading a single DICOM file."""
        # Mock the files_loaded signal
        file_manager.files_loaded = Mock()
        
        file_manager._load_single_file(sample_dicom_file)
        
        # Should emit files_loaded signal with one file
        file_manager.files_loaded.emit.assert_called_once()
        files = file_manager.files_loaded.emit.call_args[0][0]
        assert len(files) == 1
        assert files[0][0] == sample_dicom_file
        assert isinstance(files[0][1], pydicom.Dataset)
    
    def test_load_single_file_invalid(self, file_manager, temp_dir):
        """Test loading an invalid DICOM file."""
        # Create a non-DICOM file
        invalid_file = os.path.join(temp_dir, 'invalid.txt')
        with open(invalid_file, 'w') as f:
            f.write('This is not a DICOM file')
        
        # Mock the message box
        with patch('fm_dicom.managers.file_manager.FocusAwareMessageBox.critical') as mock_critical:
            file_manager._load_single_file(invalid_file)
            
            # Should show error message
            mock_critical.assert_called_once()
    
    def test_load_path_nonexistent(self, file_manager):
        """Test loading a non-existent path."""
        file_manager.loading_started = Mock()
        file_manager.loading_finished = Mock()
        
        file_manager.load_path('/nonexistent/path')
        
        # Should not emit loading signals for non-existent path
        file_manager.loading_started.emit.assert_not_called()
        file_manager.loading_finished.emit.assert_not_called()
    
    def test_load_path_file(self, file_manager, sample_dicom_file):
        """Test loading a file path."""
        file_manager.loading_started = Mock()
        file_manager.loading_finished = Mock()
        file_manager._load_single_file = Mock()
        
        file_manager.load_path(sample_dicom_file)
        
        # Should call _load_single_file
        file_manager._load_single_file.assert_called_once_with(sample_dicom_file)
        file_manager.loading_started.emit.assert_called_once()
        file_manager.loading_finished.emit.assert_called_once()
    
    def test_load_path_zip_file(self, file_manager, temp_dir):
        """Test loading a ZIP file."""
        zip_file = os.path.join(temp_dir, 'test.zip')
        # Create an empty ZIP file
        import zipfile
        with zipfile.ZipFile(zip_file, 'w') as zf:
            pass
        
        file_manager.loading_started = Mock()
        file_manager.loading_finished = Mock()
        file_manager._load_zip_file = Mock()
        
        file_manager.load_path(zip_file)
        
        # Should call _load_zip_file
        file_manager._load_zip_file.assert_called_once_with(zip_file)
        file_manager.loading_started.emit.assert_called_once()
        file_manager.loading_finished.emit.assert_called_once()
    
    def test_load_path_directory(self, file_manager, temp_dir):
        """Test loading a directory."""
        file_manager.loading_started = Mock()
        file_manager.loading_finished = Mock()
        file_manager._load_directory = Mock()
        
        file_manager.load_path(temp_dir)
        
        # Should call _load_directory
        file_manager._load_directory.assert_called_once_with(temp_dir)
        file_manager.loading_started.emit.assert_called_once()
        file_manager.loading_finished.emit.assert_called_once()
    
    def test_load_path_exception(self, file_manager, sample_dicom_file):
        """Test handling exceptions during path loading."""
        file_manager.loading_started = Mock()
        file_manager.loading_finished = Mock()
        file_manager._load_single_file = Mock(side_effect=Exception("Test error"))
        
        with patch('fm_dicom.managers.file_manager.FocusAwareMessageBox.critical') as mock_critical:
            file_manager.load_path(sample_dicom_file)
            
            # Should show error message and still emit loading_finished
            mock_critical.assert_called_once()
            file_manager.loading_started.emit.assert_called_once()
            file_manager.loading_finished.emit.assert_called_once()
    
    def test_scan_for_individual_dicom_files(self, file_manager, multiple_dicom_files, temp_dir):
        """Test scanning for individual DICOM files."""
        # Create a non-DICOM file to test filtering
        non_dicom_file = os.path.join(temp_dir, 'readme.txt')
        with open(non_dicom_file, 'w') as f:
            f.write('Not a DICOM file')
        
        # Create a ZIP file to test exclusion
        zip_file = os.path.join(temp_dir, 'test.zip')
        import zipfile
        with zipfile.ZipFile(zip_file, 'w') as zf:
            pass
        
        dicom_files = file_manager._scan_for_individual_dicom_files(temp_dir, [zip_file])
        
        # Should find all DICOM files but exclude ZIP and non-DICOM files
        assert len(dicom_files) == len(multiple_dicom_files)
        
        # Verify each returned item is a tuple of (path, dataset)
        for file_path, dataset in dicom_files:
            assert isinstance(file_path, str)
            assert isinstance(dataset, pydicom.Dataset)
            assert file_path in multiple_dicom_files
    
    def test_scan_for_individual_dicom_files_empty_directory(self, file_manager, temp_dir):
        """Test scanning an empty directory."""
        empty_subdir = os.path.join(temp_dir, 'empty')
        os.makedirs(empty_subdir)
        
        dicom_files = file_manager._scan_for_individual_dicom_files(empty_subdir, [])
        
        assert len(dicom_files) == 0
    
    def test_cleanup_temp_dirs(self, file_manager):
        """Test cleaning up temporary directories."""
        # Create temp directories
        temp_dir1 = tempfile.mkdtemp()
        temp_dir2 = tempfile.mkdtemp()
        
        # Add to file manager's temp dirs list
        file_manager.temp_dirs = [temp_dir1, temp_dir2]
        
        # Create some files in the temp dirs
        test_file1 = os.path.join(temp_dir1, 'test.txt')
        test_file2 = os.path.join(temp_dir2, 'test.txt')
        with open(test_file1, 'w') as f:
            f.write('test')
        with open(test_file2, 'w') as f:
            f.write('test')
        
        # Cleanup
        file_manager.cleanup_temp_dirs()
        
        # Directories should be removed
        assert not os.path.exists(temp_dir1)
        assert not os.path.exists(temp_dir2)
        assert len(file_manager.temp_dirs) == 0
    
    def test_cleanup_temp_dirs_nonexistent(self, file_manager):
        """Test cleaning up non-existent temp directories."""
        # Add non-existent directory
        nonexistent_dir = '/tmp/nonexistent_dir_12345'
        file_manager.temp_dirs = [nonexistent_dir]
        
        # Should not raise exception
        file_manager.cleanup_temp_dirs()
        assert len(file_manager.temp_dirs) == 0
    
    def test_get_file_info_success(self, file_manager, sample_dicom_file):
        """Test getting file information."""
        info = file_manager.get_file_info(sample_dicom_file)
        
        assert info is not None
        assert 'size' in info
        assert 'modified' in info
        assert 'name' in info
        assert 'dir' in info
        assert info['name'] == os.path.basename(sample_dicom_file)
        assert info['dir'] == os.path.dirname(sample_dicom_file)
        assert isinstance(info['size'], int)
        assert info['size'] > 0
    
    def test_get_file_info_nonexistent(self, file_manager):
        """Test getting file information for non-existent file."""
        info = file_manager.get_file_info('/nonexistent/file.dcm')
        assert info is None
    
    @patch('fm_dicom.managers.file_manager.QFileDialog.getOpenFileName')
    def test_open_file(self, mock_dialog, file_manager, sample_dicom_file):
        """Test opening a file via dialog."""
        mock_dialog.return_value = (sample_dicom_file, '')
        file_manager.load_path = Mock()
        
        file_manager.open_file()
        
        # Should call QFileDialog and then load_path
        mock_dialog.assert_called_once()
        file_manager.load_path.assert_called_once_with(sample_dicom_file)
    
    @patch('fm_dicom.managers.file_manager.QFileDialog.getOpenFileName')
    def test_open_file_cancelled(self, mock_dialog, file_manager):
        """Test opening a file when dialog is cancelled."""
        mock_dialog.return_value = ('', '')  # Cancelled
        file_manager.load_path = Mock()
        
        file_manager.open_file()
        
        # Should not call load_path when cancelled
        file_manager.load_path.assert_not_called()
    
    @patch('fm_dicom.managers.file_manager.QFileDialog.getExistingDirectory')
    def test_open_directory(self, mock_dialog, file_manager, temp_dir):
        """Test opening a directory via dialog."""
        mock_dialog.return_value = temp_dir
        file_manager.load_path = Mock()
        
        file_manager.open_directory()
        
        # Should call QFileDialog and then load_path
        mock_dialog.assert_called_once()
        file_manager.load_path.assert_called_once_with(temp_dir)
    
    @patch('fm_dicom.managers.file_manager.QFileDialog.getExistingDirectory')
    def test_open_directory_cancelled(self, mock_dialog, file_manager):
        """Test opening a directory when dialog is cancelled."""
        mock_dialog.return_value = ''  # Cancelled
        file_manager.load_path = Mock()
        
        file_manager.open_directory()
        
        # Should not call load_path when cancelled
        file_manager.load_path.assert_not_called()


class TestFileManagerIntegration:
    """Integration tests for FileManager."""
    
    @pytest.fixture
    def file_manager(self, mock_main_window):
        """Create a FileManager instance for testing."""
        return FileManager(mock_main_window)
    
    def test_load_directory_with_mixed_content(self, file_manager, temp_dir, multiple_dicom_files):
        """Test loading a directory with mixed DICOM and non-DICOM files."""
        # Create some non-DICOM files
        with open(os.path.join(temp_dir, 'readme.txt'), 'w') as f:
            f.write('This is a readme file')
        
        with open(os.path.join(temp_dir, 'data.json'), 'w') as f:
            f.write('{"key": "value"}')
        
        file_manager.files_loaded = Mock()
        file_manager._scan_directory_comprehensive = Mock()
        
        file_manager._load_directory(temp_dir)
        
        # Should call comprehensive scan
        file_manager._scan_directory_comprehensive.assert_called_once_with(temp_dir)
    
    def test_signals_emitted(self, file_manager, sample_dicom_file):
        """Test that appropriate signals are emitted."""
        # Create signal mocks
        file_manager.loading_started = Mock()
        file_manager.loading_finished = Mock()
        file_manager.files_loaded = Mock()
        
        # Load a file
        file_manager.load_path(sample_dicom_file)
        
        # Verify signals were emitted
        file_manager.loading_started.emit.assert_called_once()
        file_manager.loading_finished.emit.assert_called_once()
        file_manager.files_loaded.emit.assert_called_once()


class TestFileManagerErrorHandling:
    """Test error handling in FileManager."""
    
    @pytest.fixture
    def file_manager(self, mock_main_window):
        """Create a FileManager instance for testing."""
        return FileManager(mock_main_window)
    
    def test_load_corrupted_dicom_file(self, file_manager, temp_dir):
        """Test loading a corrupted DICOM file."""
        # Create a file that looks like DICOM but is corrupted
        corrupted_file = os.path.join(temp_dir, 'corrupted.dcm')
        with open(corrupted_file, 'wb') as f:
            f.write(b'DICM')  # DICOM header but incomplete
            f.write(b'corrupted data')
        
        with patch('fm_dicom.managers.file_manager.FocusAwareMessageBox.critical') as mock_critical:
            file_manager._load_single_file(corrupted_file)
            
            # Should show error message
            mock_critical.assert_called_once()
    
    def test_permission_error(self, file_manager):
        """Test handling permission errors."""
        with patch('os.path.exists', return_value=True):
            with patch('os.path.isfile', return_value=True):
                with patch('pydicom.dcmread', side_effect=PermissionError("Access denied")):
                    with patch('fm_dicom.managers.file_manager.FocusAwareMessageBox.critical') as mock_critical:
                        file_manager._load_single_file('/restricted/file.dcm')
                        
                        # Should show error message
                        mock_critical.assert_called_once()