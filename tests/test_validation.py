"""
Simplified tests for validation functionality that match the actual implementation.
"""

import os
from unittest.mock import Mock, patch, MagicMock
import pytest
import pydicom
from datetime import datetime

from fm_dicom.validation.validation import (
    ValidationSeverity,
    ValidationIssue,
    ValidationResult,
    DicomValidator,
    CollectionValidationResult
)


class TestValidationSeverity:
    """Test ValidationSeverity constants."""
    
    def test_severity_constants(self):
        """Test that severity constants are defined correctly."""
        assert ValidationSeverity.ERROR == "Error"
        assert ValidationSeverity.WARNING == "Warning"
        assert ValidationSeverity.INFO == "Info"


class TestValidationIssue:
    """Test ValidationIssue functionality."""
    
    def test_init_basic(self):
        """Test ValidationIssue initialization with basic parameters."""
        issue = ValidationIssue(
            severity=ValidationSeverity.ERROR,
            category="Missing Tag",
            message="PatientName is missing"
        )
        
        assert issue.severity == ValidationSeverity.ERROR
        assert issue.category == "Missing Tag"
        assert issue.message == "PatientName is missing"
        assert issue.tag is None
        assert issue.file_path is None
        assert issue.suggested_fix is None
        assert isinstance(issue.timestamp, datetime)
    
    def test_str_representation(self):
        """Test string representation of ValidationIssue."""
        issue = ValidationIssue(
            severity=ValidationSeverity.ERROR,
            category="Missing Tag",
            message="Required tag is missing"
        )
        
        expected_str = "[Error] Missing Tag: Required tag is missing"
        assert str(issue) == expected_str


class TestValidationResult:
    """Test ValidationResult functionality."""
    
    def test_init(self):
        """Test ValidationResult initialization."""
        result = ValidationResult("/path/to/file.dcm")
        
        assert result.file_path == "/path/to/file.dcm"
        assert result.issues == []
        assert result.is_valid_dicom is True
        assert result.dataset is None
    
    def test_add_issue(self):
        """Test adding issue to result."""
        result = ValidationResult("/test/file.dcm")
        
        result.add_issue(
            severity=ValidationSeverity.ERROR,
            category="Missing Tag",
            message="PatientName is missing"
        )
        
        assert len(result.issues) == 1
        issue = result.issues[0]
        assert issue.severity == ValidationSeverity.ERROR
        assert issue.file_path == "/test/file.dcm"
    
    def test_has_errors(self):
        """Test has_errors method."""
        result = ValidationResult("/test/file.dcm")
        
        # No errors initially
        assert result.has_errors() is False
        
        # Add error
        result.add_issue(ValidationSeverity.ERROR, "Error", "Error message")
        assert result.has_errors() is True
    
    def test_has_warnings(self):
        """Test has_warnings method."""
        result = ValidationResult("/test/file.dcm")
        
        # No warnings initially
        assert result.has_warnings() is False
        
        # Add warning
        result.add_issue(ValidationSeverity.WARNING, "Warning", "Warning message")
        assert result.has_warnings() is True


class TestDicomValidator:
    """Test DicomValidator functionality."""
    
    def test_init(self):
        """Test DicomValidator initialization."""
        validator = DicomValidator()
        
        # Should have loaded standard rules
        assert len(validator.rules) > 0
        
        # Should have expected rule types
        rule_names = [rule.name for rule in validator.rules]
        assert "Required Tags" in rule_names
        assert "UID Format" in rule_names
    
    def test_validate_file_nonexistent(self):
        """Test validating non-existent file."""
        validator = DicomValidator()
        result = validator.validate_file("/nonexistent/file.dcm")
        
        assert result.has_errors() is True
        assert any("does not exist" in issue.message for issue in result.issues)
    
    def test_validate_file_invalid(self, temp_dir):
        """Test validating invalid DICOM file."""
        # Create invalid file
        invalid_file = os.path.join(temp_dir, 'invalid.txt')
        with open(invalid_file, 'w') as f:
            f.write('Not a DICOM file')
        
        validator = DicomValidator()
        result = validator.validate_file(invalid_file)
        
        assert result.is_valid_dicom is False
        assert result.has_errors() is True
    
    @pytest.mark.slow
    def test_validate_file_success(self, sample_dicom_file):
        """Test validating valid DICOM file."""
        validator = DicomValidator()
        result = validator.validate_file(sample_dicom_file)
        
        # Should successfully read the file
        assert result.dataset is not None
        assert isinstance(result.dataset, pydicom.Dataset)
        
        # May have warnings but should not have format errors
        format_errors = [issue for issue in result.issues 
                        if issue.category == "DICOM Format"]
        assert len(format_errors) == 0
    
    @pytest.mark.slow
    def test_validate_collection(self, multiple_dicom_files):
        """Test validating collection of DICOM files."""
        validator = DicomValidator()
        result = validator.validate_collection(multiple_dicom_files)
        
        assert isinstance(result, CollectionValidationResult)
        assert len(result.file_results) == len(multiple_dicom_files)
        
        # Should have generated statistics
        assert hasattr(result, 'statistics')


class TestCollectionValidationResult:
    """Test CollectionValidationResult functionality."""
    
    def test_init(self):
        """Test CollectionValidationResult initialization."""
        result = CollectionValidationResult()
        
        assert result.file_results == {}
        assert result.collection_issues == []
        assert result.statistics == {}
    
    def test_add_file_result(self):
        """Test adding file result."""
        collection_result = CollectionValidationResult()
        file_result = ValidationResult("/test/file.dcm")
        
        collection_result.add_file_result(file_result)
        
        assert "/test/file.dcm" in collection_result.file_results
        assert collection_result.file_results["/test/file.dcm"] == file_result
    
    def test_add_collection_issue(self):
        """Test adding collection issue."""
        collection_result = CollectionValidationResult()
        
        collection_result.add_collection_issue(
            ValidationSeverity.ERROR,
            "Duplicate",
            "Duplicate UIDs found"
        )
        
        assert len(collection_result.collection_issues) == 1
        issue = collection_result.collection_issues[0]
        assert issue.severity == ValidationSeverity.ERROR
        assert issue.category == "Duplicate"
    
    def test_get_summary(self):
        """Test getting validation summary."""
        collection_result = CollectionValidationResult()
        
        # Add some file results
        file_result1 = ValidationResult("/file1.dcm")
        file_result2 = ValidationResult("/file2.dcm")
        file_result2.add_issue(ValidationSeverity.ERROR, "Error", "Test error")
        
        collection_result.add_file_result(file_result1)
        collection_result.add_file_result(file_result2)
        
        summary = collection_result.get_summary()
        
        assert summary['total_files'] == 2
        assert summary['files_with_errors'] == 1
        assert summary['valid_files'] == 1


class TestValidationIntegration:
    """Integration tests for validation functionality."""
    
    @pytest.mark.integration
    @pytest.mark.slow
    def test_complete_validation_workflow(self, multiple_dicom_files):
        """Test complete validation workflow."""
        validator = DicomValidator()
        
        # Validate collection
        collection_result = validator.validate_collection(multiple_dicom_files)
        
        # Should have results for all files
        assert len(collection_result.file_results) == len(multiple_dicom_files)
        
        # Should have summary statistics
        summary = collection_result.get_summary()
        assert summary['total_files'] == len(multiple_dicom_files)
        assert 'files_with_errors' in summary
        assert 'files_with_warnings' in summary
    
    @pytest.mark.integration
    def test_validation_with_mixed_files(self, temp_dir, sample_dicom_file):
        """Test validation with mix of valid and invalid files."""
        # Create invalid file
        invalid_file = os.path.join(temp_dir, 'invalid.txt')
        with open(invalid_file, 'w') as f:
            f.write('Not DICOM')
        
        files = [sample_dicom_file, invalid_file]
        
        validator = DicomValidator()
        result = validator.validate_collection(files)
        
        # Should have results for both files
        assert len(result.file_results) == 2
        
        # Invalid file should have errors
        invalid_result = result.file_results[invalid_file]
        assert invalid_result.has_errors() is True
        assert invalid_result.is_valid_dicom is False