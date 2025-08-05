"""
Tests for DicomManager functionality.
"""

import os
from unittest.mock import Mock, patch, MagicMock
import pytest
import pydicom
from PyQt6.QtWidgets import QTableWidgetItem
from PyQt6.QtCore import Qt

from fm_dicom.managers.dicom_manager import DicomManager


class TestDicomManager:
    """Test DicomManager functionality."""
    
    @pytest.fixture
    def dicom_manager(self, mock_main_window):
        """Create a DicomManager instance for testing."""
        # Add required attributes to mock window
        mock_main_window.tag_table = Mock()
        mock_main_window.search_bar = Mock()
        mock_main_window.image_label = Mock()
        mock_main_window.frame_selector = Mock()
        mock_main_window.edit_level_combo = Mock()
        mock_main_window.tree = Mock()
        mock_main_window.tree_manager = Mock()
        mock_main_window.save_btn = Mock()
        
        # Mock tag table methods
        mock_main_window.tag_table.setRowCount = Mock()
        mock_main_window.tag_table.rowCount = Mock(return_value=0)
        mock_main_window.tag_table.insertRow = Mock()
        mock_main_window.tag_table.setItem = Mock()
        mock_main_window.tag_table.setColumnWidth = Mock()
        mock_main_window.tag_table.item = Mock()
        mock_main_window.tag_table.itemChanged = Mock()
        mock_main_window.tag_table.itemChanged.connect = Mock()
        
        return DicomManager(mock_main_window)
    
    def test_init(self, dicom_manager, mock_main_window):
        """Test DicomManager initialization."""
        assert dicom_manager.main_window == mock_main_window
        assert dicom_manager.config == mock_main_window.config
        assert dicom_manager.current_file is None
        assert dicom_manager.current_dataset is None
        assert dicom_manager._all_tag_rows == []
        assert dicom_manager._has_unsaved_changes is False
        assert dicom_manager._current_filter_text == ""
    
    def test_load_dicom_tags_success(self, dicom_manager, sample_dicom_file):
        """Test successfully loading DICOM tags."""
        # Mock the methods that will be called
        dicom_manager._update_frame_selector = Mock()
        dicom_manager._populate_tag_table = Mock()
        dicom_manager.display_image = Mock()
        dicom_manager.config = {"show_image_preview": True}
        
        dicom_manager.load_dicom_tags(sample_dicom_file)
        
        # Verify the file was loaded
        assert dicom_manager.current_file == sample_dicom_file
        assert dicom_manager.current_dataset is not None
        assert isinstance(dicom_manager.current_dataset, pydicom.Dataset)
        
        # Verify methods were called
        dicom_manager._update_frame_selector.assert_called_once()
        dicom_manager._populate_tag_table.assert_called_once()
        dicom_manager.display_image.assert_called_once()
    
    def test_load_dicom_tags_no_preview(self, dicom_manager, sample_dicom_file):
        """Test loading DICOM tags without preview."""
        dicom_manager._update_frame_selector = Mock()
        dicom_manager._populate_tag_table = Mock()
        dicom_manager.display_image = Mock()
        dicom_manager.config = {"show_image_preview": False}
        
        dicom_manager.load_dicom_tags(sample_dicom_file)
        
        # Display image should not be called
        dicom_manager.display_image.assert_not_called()
    
    def test_load_dicom_tags_nonexistent_file(self, dicom_manager):
        """Test loading non-existent DICOM file."""
        dicom_manager.clear_tag_table = Mock()
        
        dicom_manager.load_dicom_tags('/nonexistent/file.dcm')
        
        # Should clear tag table and not set current file
        dicom_manager.clear_tag_table.assert_called_once()
        assert dicom_manager.current_file is None
        assert dicom_manager.current_dataset is None
    
    def test_load_dicom_tags_invalid_file(self, dicom_manager, temp_dir):
        """Test loading invalid DICOM file."""
        # Create invalid file
        invalid_file = os.path.join(temp_dir, 'invalid.txt')
        with open(invalid_file, 'w') as f:
            f.write('Not a DICOM file')
        
        dicom_manager.clear_tag_table = Mock()
        
        with patch('fm_dicom.managers.dicom_manager.FocusAwareMessageBox.critical') as mock_critical:
            dicom_manager.load_dicom_tags(invalid_file)
            
            # Should show error and clear table
            mock_critical.assert_called_once()
            dicom_manager.clear_tag_table.assert_called_once()
    
    def test_populate_tag_table(self, dicom_manager, sample_dicom_file):
        """Test populating tag table with DICOM dataset."""
        # Load a real DICOM dataset
        ds = pydicom.dcmread(sample_dicom_file, stop_before_pixels=True)
        
        # Mock table operations
        dicom_manager.tag_table.setRowCount = Mock()
        dicom_manager._refresh_tag_table = Mock()
        
        dicom_manager._populate_tag_table(ds)
        
        # Should have populated _all_tag_rows
        assert len(dicom_manager._all_tag_rows) > 0
        
        # Verify structure of tag rows
        for row_info in dicom_manager._all_tag_rows:
            assert 'elem_obj' in row_info
            assert 'display_row' in row_info
            assert isinstance(row_info['elem_obj'], pydicom.DataElement)
            assert len(row_info['display_row']) == 4  # tag_id, desc, value, new_value
        
        # Should call refresh
        dicom_manager._refresh_tag_table.assert_called_once()
    
    def test_filter_tag_table(self, dicom_manager):
        """Test filtering tag table."""
        dicom_manager._refresh_tag_table = Mock()
        
        # Test filtering
        dicom_manager.filter_tag_table("Patient")
        
        assert dicom_manager._current_filter_text == "patient"
        dicom_manager._refresh_tag_table.assert_called_once()
    
    def test_on_tag_changed(self, dicom_manager):
        """Test handling tag value changes."""
        # Create mock item in new value column (column 3)
        mock_item = Mock()
        mock_item.column.return_value = 3
        
        dicom_manager._on_tag_changed(mock_item)
        
        # Should mark as having unsaved changes
        assert dicom_manager._has_unsaved_changes is True
        
        # Should enable save button
        dicom_manager.main_window.save_btn.setEnabled.assert_called_once_with(True)
    
    def test_on_tag_changed_wrong_column(self, dicom_manager):
        """Test handling changes in non-editable columns."""
        # Create mock item in different column
        mock_item = Mock()
        mock_item.column.return_value = 1  # Description column
        
        dicom_manager._on_tag_changed(mock_item)
        
        # Should not mark as changed
        assert dicom_manager._has_unsaved_changes is False
    
    def test_clear_tag_table(self, dicom_manager):
        """Test clearing tag table."""
        # Set some state first
        dicom_manager.current_file = '/some/file.dcm'
        dicom_manager.current_dataset = Mock()
        dicom_manager._all_tag_rows = [{'test': 'data'}]
        dicom_manager._has_unsaved_changes = True
        
        dicom_manager.clear_tag_table()
        
        # Should clear state
        assert dicom_manager.current_file is None
        assert dicom_manager.current_dataset is None
        assert dicom_manager._all_tag_rows == []
        assert dicom_manager._has_unsaved_changes is False
        
        # Should clear table
        dicom_manager.tag_table.setRowCount.assert_called_with(0)
    
    def test_has_unsaved_changes_property(self, dicom_manager):
        """Test has_unsaved_changes property."""
        # Initially should be False
        assert not dicom_manager.has_unsaved_changes
        
        # Set to True
        dicom_manager._has_unsaved_changes = True
        assert dicom_manager.has_unsaved_changes
    
    def test_refresh_tag_table_with_filter(self, dicom_manager, sample_dicom_file):
        """Test refreshing tag table with filter applied."""
        # Load dataset and populate tags
        ds = pydicom.dcmread(sample_dicom_file, stop_before_pixels=True)
        dicom_manager._populate_tag_table(ds)
        
        # Mock table operations for refresh
        dicom_manager.tag_table.setRowCount = Mock()
        dicom_manager.tag_table.rowCount = Mock(return_value=0)
        dicom_manager.tag_table.insertRow = Mock()
        dicom_manager.tag_table.setItem = Mock()
        dicom_manager.tag_table.setColumnWidth = Mock()
        
        # Set filter
        dicom_manager._current_filter_text = "patient"
        
        dicom_manager._refresh_tag_table()
        
        # Should have set up table
        dicom_manager.tag_table.setRowCount.assert_called_with(0)
        dicom_manager.tag_table.setColumnWidth.assert_called()
    
    def test_refresh_tag_table_no_filter(self, dicom_manager, sample_dicom_file):
        """Test refreshing tag table without filter."""
        # Load dataset and populate tags
        ds = pydicom.dcmread(sample_dicom_file, stop_before_pixels=True)
        dicom_manager._populate_tag_table(ds)
        
        # Mock table operations
        dicom_manager.tag_table.setRowCount = Mock()
        dicom_manager.tag_table.rowCount = Mock(return_value=0)
        dicom_manager.tag_table.insertRow = Mock() 
        dicom_manager.tag_table.setItem = Mock()
        dicom_manager.tag_table.setColumnWidth = Mock()
        
        # No filter
        dicom_manager._current_filter_text = ""
        
        dicom_manager._refresh_tag_table()
        
        # Should process all rows when no filter
        dicom_manager.tag_table.setRowCount.assert_called_with(0)


class TestDicomManagerSignals:
    """Test DicomManager signals."""
    
    @pytest.fixture
    def dicom_manager(self, mock_main_window):
        """Create a DicomManager instance for testing."""
        mock_main_window.tag_table = Mock()
        mock_main_window.search_bar = Mock()
        mock_main_window.image_label = Mock()
        mock_main_window.tag_table.itemChanged = Mock()
        mock_main_window.tag_table.itemChanged.connect = Mock()
        
        return DicomManager(mock_main_window)
    
    def test_tag_data_changed_signal(self, dicom_manager, qapp):
        """Test tag_data_changed signal is emitted."""
        # Connect signal to mock slot
        mock_slot = Mock()
        dicom_manager.tag_data_changed.connect(mock_slot)
        
        # Trigger signal
        dicom_manager.tag_data_changed.emit()
        
        # Process events to ensure signal is delivered
        qapp.processEvents()
        
        # Verify signal was received
        mock_slot.assert_called_once()
    
    def test_image_loaded_signal(self, dicom_manager, qapp):
        """Test image_loaded signal is emitted."""
        # Connect signal to mock slot
        mock_slot = Mock()
        dicom_manager.image_loaded.connect(mock_slot)
        
        # Create mock pixmap
        from PyQt6.QtGui import QPixmap
        mock_pixmap = QPixmap(100, 100)
        
        # Trigger signal
        dicom_manager.image_loaded.emit(mock_pixmap)
        
        # Process events
        qapp.processEvents()
        
        # Verify signal was received
        mock_slot.assert_called_once_with(mock_pixmap)


class TestDicomManagerIntegration:
    """Integration tests for DicomManager."""
    
    @pytest.fixture
    def dicom_manager(self, mock_main_window):
        """Create a DicomManager instance for testing."""
        mock_main_window.tag_table = Mock()
        mock_main_window.search_bar = Mock()
        mock_main_window.image_label = Mock()
        mock_main_window.tag_table.itemChanged = Mock()
        mock_main_window.tag_table.itemChanged.connect = Mock()
        
        return DicomManager(mock_main_window)
    
    def test_full_load_and_filter_workflow(self, dicom_manager, sample_dicom_file):
        """Test complete workflow of loading file and filtering."""
        # Mock display methods
        dicom_manager._update_frame_selector = Mock()
        dicom_manager.display_image = Mock()
        dicom_manager.config = {"show_image_preview": True}
        
        # Mock table operations
        dicom_manager.tag_table.setRowCount = Mock()
        dicom_manager.tag_table.rowCount = Mock(return_value=0)
        dicom_manager.tag_table.insertRow = Mock()
        dicom_manager.tag_table.setItem = Mock()
        dicom_manager.tag_table.setColumnWidth = Mock()
        
        # Load file
        dicom_manager.load_dicom_tags(sample_dicom_file)
        
        # Verify file loaded
        assert dicom_manager.current_file == sample_dicom_file
        assert len(dicom_manager._all_tag_rows) > 0
        
        # Apply filter
        dicom_manager.filter_tag_table("Patient")
        
        # Verify filter applied
        assert dicom_manager._current_filter_text == "patient"
        
        # Clear filter
        dicom_manager.filter_tag_table("")
        
        # Verify filter cleared
        assert dicom_manager._current_filter_text == ""