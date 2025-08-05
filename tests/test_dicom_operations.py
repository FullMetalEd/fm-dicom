"""
Tests for DICOM operations functionality.
"""

import os
import tempfile
import shutil
from unittest.mock import Mock, patch, MagicMock
import pytest
import pydicom

from fm_dicom.core.dicomdir_reader import DicomdirReader
from fm_dicom.core.path_generator import DicomPathGenerator


class TestDicomdirReader:
    """Test DicomdirReader functionality."""
    
    @pytest.fixture
    def dicomdir_reader(self):
        """Create a DicomdirReader instance for testing."""
        return DicomdirReader()
    
    def test_init(self, dicomdir_reader):
        """Test DicomdirReader initialization."""
        assert dicomdir_reader.dicomdir_path is None
        assert dicomdir_reader.base_directory is None
    
    def test_find_dicomdir_success(self, dicomdir_reader, temp_dir):
        """Test finding DICOMDIR files."""
        # Create DICOMDIR files in different locations
        dicomdir1 = os.path.join(temp_dir, 'DICOMDIR')
        dicomdir2 = os.path.join(temp_dir, 'subdir', 'DICOMDIR')
        
        os.makedirs(os.path.dirname(dicomdir2), exist_ok=True)
        
        # Create the files
        with open(dicomdir1, 'w') as f:
            f.write('dummy dicomdir')
        with open(dicomdir2, 'w') as f:
            f.write('dummy dicomdir')
        
        # Also create some non-DICOMDIR files
        with open(os.path.join(temp_dir, 'other_file.txt'), 'w') as f:
            f.write('not a dicomdir')
        
        found_files = dicomdir_reader.find_dicomdir(temp_dir)
        
        # Should find both DICOMDIR files
        assert len(found_files) == 2
        assert dicomdir1 in found_files
        assert dicomdir2 in found_files
    
    def test_find_dicomdir_case_insensitive(self, dicomdir_reader, temp_dir):
        """Test finding DICOMDIR files with different cases."""
        # Create DICOMDIR files with different cases
        files_to_create = ['DICOMDIR', 'dicomdir', 'DicomDir']
        expected_files = []
        
        for filename in files_to_create:
            filepath = os.path.join(temp_dir, filename)
            with open(filepath, 'w') as f:
                f.write('dummy dicomdir')
            expected_files.append(filepath)
        
        found_files = dicomdir_reader.find_dicomdir(temp_dir)
        
        # Should find all variations (depending on filesystem case sensitivity)
        assert len(found_files) >= 1  # At least one should be found
        
        # Check that actual DICOMDIR (uppercase) is found
        dicomdir_upper = os.path.join(temp_dir, 'DICOMDIR')
        assert dicomdir_upper in found_files
    
    def test_find_dicomdir_empty_directory(self, dicomdir_reader, temp_dir):
        """Test finding DICOMDIR in empty directory."""
        found_files = dicomdir_reader.find_dicomdir(temp_dir)
        assert found_files == []
    
    def test_find_dicomdir_nonexistent_directory(self, dicomdir_reader):
        """Test finding DICOMDIR in non-existent directory."""
        with pytest.raises(OSError):
            dicomdir_reader.find_dicomdir('/nonexistent/directory')
    
    def test_read_dicomdir_success(self, dicomdir_reader, temp_dir):
        """Test reading a valid DICOMDIR file."""
        # Create a minimal DICOMDIR dataset
        ds = pydicom.Dataset()
        ds.DirectoryRecordSequence = pydicom.Sequence()
        
        # Add a directory record
        record = pydicom.Dataset()
        record.DirectoryRecordType = "IMAGE"
        record.ReferencedFileID = ["IMAGES", "IM001.DCM"]
        ds.DirectoryRecordSequence.append(record)
        
        # Create file meta information
        ds.file_meta = pydicom.Dataset()
        ds.file_meta.MediaStorageSOPClassUID = pydicom.uid.MediaStorageDirectoryStorage
        ds.file_meta.MediaStorageSOPInstanceUID = "1.2.3.4.5"
        ds.file_meta.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian
        ds.file_meta.ImplementationClassUID = "1.2.3.4"
        
        # Save DICOMDIR
        dicomdir_path = os.path.join(temp_dir, 'DICOMDIR')
        ds.save_as(dicomdir_path)
        
        # Mock the _extract_file_path method to return expected paths
        dicomdir_reader._extract_file_path = Mock(return_value='/path/to/image.dcm')
        
        file_paths = dicomdir_reader.read_dicomdir(dicomdir_path)
        
        # Should return file paths
        assert len(file_paths) == 1
        assert file_paths[0] == '/path/to/image.dcm'
        assert dicomdir_reader.dicomdir_path == dicomdir_path
        assert dicomdir_reader.base_directory == temp_dir
    
    def test_read_dicomdir_no_directory_sequence(self, dicomdir_reader, temp_dir):
        """Test reading DICOMDIR without DirectoryRecordSequence."""
        # Create minimal DICOMDIR without DirectoryRecordSequence
        ds = pydicom.Dataset()
        ds.file_meta = pydicom.Dataset()
        ds.file_meta.MediaStorageSOPClassUID = pydicom.uid.MediaStorageDirectoryStorage
        ds.file_meta.MediaStorageSOPInstanceUID = "1.2.3.4.5"
        ds.file_meta.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian
        ds.file_meta.ImplementationClassUID = "1.2.3.4"
        
        dicomdir_path = os.path.join(temp_dir, 'DICOMDIR')
        ds.save_as(dicomdir_path)
        
        file_paths = dicomdir_reader.read_dicomdir(dicomdir_path)
        
        # Should return empty list
        assert file_paths == []
    
    def test_read_dicomdir_invalid_file(self, dicomdir_reader, temp_dir):
        """Test reading invalid DICOMDIR file."""
        # Create invalid DICOMDIR file
        invalid_dicomdir = os.path.join(temp_dir, 'DICOMDIR')
        with open(invalid_dicomdir, 'w') as f:
            f.write('This is not a valid DICOM file')
        
        file_paths = dicomdir_reader.read_dicomdir(invalid_dicomdir)
        
        # Should return empty list
        assert file_paths == []
    
    def test_read_dicomdir_nonexistent_file(self, dicomdir_reader):
        """Test reading non-existent DICOMDIR file."""
        file_paths = dicomdir_reader.read_dicomdir('/nonexistent/DICOMDIR')
        
        # Should return empty list
        assert file_paths == []
    
    def test_extract_file_path_with_referenced_file_id(self, dicomdir_reader, temp_dir):
        """Test extracting file path from directory record."""
        dicomdir_reader.base_directory = temp_dir
        
        # Create directory record with ReferencedFileID
        record = pydicom.Dataset()
        record.ReferencedFileID = ["IMAGES", "SUBDIR", "IMAGE.DCM"]
        
        file_path = dicomdir_reader._extract_file_path(record)
        
        # Should construct proper file path
        expected_path = os.path.join(temp_dir, "IMAGES", "SUBDIR", "IMAGE.DCM")
        assert file_path == expected_path
    
    def test_extract_file_path_no_referenced_file_id(self, dicomdir_reader):
        """Test extracting file path from record without ReferencedFileID."""
        # Create directory record without ReferencedFileID
        record = pydicom.Dataset()
        
        file_path = dicomdir_reader._extract_file_path(record)
        
        # Should return None
        assert file_path is None


class TestDicomPathGenerator:
    """Test DicomPathGenerator functionality."""
    
    def test_generate_paths_single_file(self, sample_dicom_file):
        """Test generating paths for single DICOM file."""
        paths = DicomPathGenerator.generate_paths([sample_dicom_file])
        
        # Should return dictionary with original path as key
        assert isinstance(paths, dict)
        assert sample_dicom_file in paths
        
        # Generated path should follow DICOM standard structure
        generated_path = paths[sample_dicom_file]
        assert "DICOM/" in generated_path
        assert "PAT" in generated_path
        assert "STU" in generated_path
        assert "SER" in generated_path
        assert "IMG" in generated_path
    
    def test_generate_paths_multiple_files(self, multiple_dicom_files):
        """Test generating paths for multiple DICOM files."""
        paths = DicomPathGenerator.generate_paths(multiple_dicom_files)
        
        # Should return paths for all files
        assert len(paths) == len(multiple_dicom_files)
        
        # All original files should be keys
        for file_path in multiple_dicom_files:
            assert file_path in paths
            assert "DICOM/" in paths[file_path]
    
    def test_generate_paths_empty_list(self):
        """Test generating paths for empty file list."""
        paths = DicomPathGenerator.generate_paths([])
        
        # Should return empty dictionary
        assert paths == {}
    
    def test_generate_paths_invalid_file(self, temp_dir):
        """Test generating paths for invalid DICOM file."""
        # Create non-DICOM file
        invalid_file = os.path.join(temp_dir, 'invalid.txt')
        with open(invalid_file, 'w') as f:
            f.write('Not a DICOM file')
        
        paths = DicomPathGenerator.generate_paths([invalid_file])
        
        # Should handle invalid file gracefully
        # Depending on implementation, might return empty dict or skip the file
        assert isinstance(paths, dict)
    
    def test_generate_paths_hierarchy_grouping(self, temp_dir):
        """Test that files with same patient/study/series are grouped correctly."""
        # Create multiple DICOM files with same patient but different series
        files = []
        
        for i in range(2):
            ds = pydicom.Dataset()
            ds.PatientID = "PAT001"
            ds.PatientName = "Test^Patient"
            ds.StudyInstanceUID = "1.2.3.4.5.6.7.8.9"
            ds.SeriesInstanceUID = f"1.2.3.4.5.6.7.8.10.{i}"
            ds.SOPInstanceUID = f"1.2.3.4.5.6.7.8.11.{i}"
            ds.InstanceNumber = str(i + 1)
            ds.StudyDescription = "Test Study"
            ds.SeriesDescription = f"Test Series {i + 1}"
            
            # Set file meta
            ds.file_meta = pydicom.Dataset()
            ds.file_meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.2"
            ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
            ds.file_meta.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian
            ds.file_meta.ImplementationClassUID = "1.2.3.4.5.6.7.8.12"
            
            file_path = os.path.join(temp_dir, f'test_{i}.dcm')
            ds.save_as(file_path)
            files.append(file_path)
        
        paths = DicomPathGenerator.generate_paths(files)
        
        # Both files should have paths generated
        assert len(paths) == 2
        
        # Both should have same patient directory but different series
        path1 = paths[files[0]]
        path2 = paths[files[1]]
        
        # Should both contain the same patient identifier
        assert "PAT00001" in path1
        assert "PAT00001" in path2
        
        # Should have different series numbers
        assert path1 != path2  # Different series should have different paths


class TestDicomOperationsIntegration:
    """Integration tests for DICOM operations."""
    
    def test_dicomdir_and_path_generation_workflow(self, temp_dir, multiple_dicom_files):
        """Test complete workflow of DICOMDIR reading and path generation."""
        # Create a DICOMDIR that references the test files
        dicomdir_reader = DicomdirReader()
        
        # Mock reading DICOMDIR to return our test files
        with patch.object(dicomdir_reader, 'read_dicomdir', return_value=multiple_dicom_files):
            dicomdir_path = os.path.join(temp_dir, 'DICOMDIR')
            
            # Read files from DICOMDIR
            referenced_files = dicomdir_reader.read_dicomdir(dicomdir_path)
            
            # Generate standard paths for the files
            generated_paths = DicomPathGenerator.generate_paths(referenced_files)
            
            # Verify the complete workflow
            assert len(referenced_files) == len(multiple_dicom_files)
            assert len(generated_paths) == len(multiple_dicom_files)
            
            # Each original file should have a generated path
            for original_file in referenced_files:
                assert original_file in generated_paths
                assert "DICOM/" in generated_paths[original_file]
    
    def test_error_handling_in_operations(self, temp_dir):
        """Test error handling in DICOM operations."""
        dicomdir_reader = DicomdirReader()
        
        # Test with corrupted DICOM file
        corrupted_file = os.path.join(temp_dir, 'corrupted.dcm')
        with open(corrupted_file, 'wb') as f:
            f.write(b'DICM')  # Partial DICOM header
            f.write(b'corrupted data')
        
        # Should handle corrupted file gracefully
        paths = DicomPathGenerator.generate_paths([corrupted_file])
        assert isinstance(paths, dict)  # Should not crash
        
        # Test DICOMDIR reader with non-existent file
        files = dicomdir_reader.read_dicomdir('/nonexistent/DICOMDIR')
        assert files == []  # Should return empty list, not crash