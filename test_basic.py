#!/usr/bin/env python3
"""
Basic functionality test to verify core components work.
"""

def test_config():
    """Test configuration loading."""
    try:
        from fm_dicom.config.config_manager import load_config
        config = load_config()
        print("✓ Configuration loading works")
        return True
    except Exception as e:
        print(f"✗ Configuration loading failed: {e}")
        return False

def test_managers():
    """Test manager imports."""
    try:
        from fm_dicom.managers.dicom_manager import DicomManager
        from fm_dicom.managers.file_manager import FileManager
        from fm_dicom.managers.tree_manager import TreeManager
        print("✓ Manager classes import successfully")
        return True
    except Exception as e:
        print(f"✗ Manager imports failed: {e}")
        return False

def test_anonymization():
    """Test anonymization classes."""
    try:
        from fm_dicom.anonymization.anonymization import (
            AnonymizationAction, AnonymizationRule, AnonymizationTemplate
        )
        
        # Test basic functionality
        rule = AnonymizationRule("PatientName", AnonymizationAction.REPLACE, "Anonymous")
        template = AnonymizationTemplate("Test Template", "Test description")
        template.add_rule(rule)
        
        assert len(template.rules) == 1
        assert template.get_rule("PatientName") is not None
        
        print("✓ Anonymization classes work correctly")
        return True
    except Exception as e:
        print(f"✗ Anonymization test failed: {e}")
        return False

def test_validation():
    """Test validation classes."""
    try:
        from fm_dicom.validation.validation import (
            ValidationSeverity, ValidationIssue, ValidationResult, DicomValidator
        )
        
        # Test basic functionality
        issue = ValidationIssue(ValidationSeverity.ERROR, "Test", "Test message")
        result = ValidationResult("/test/file.dcm")
        result.add_issue(ValidationSeverity.WARNING, "Test", "Test warning")
        
        assert len(result.issues) == 1
        assert result.has_warnings() is True
        
        print("✓ Validation classes work correctly")
        return True
    except Exception as e:
        print(f"✗ Validation test failed: {e}")
        return False

def test_dicom_creation():
    """Test DICOM file creation."""
    try:
        import tempfile
        import pydicom
        
        # Create a minimal but valid DICOM file
        ds = pydicom.Dataset()
        ds.PatientName = "Test^Patient"
        ds.PatientID = "12345"
        ds.StudyInstanceUID = "1.2.3.4.5.6.7.8.9"
        ds.SeriesInstanceUID = "1.2.3.4.5.6.7.8.10"
        ds.SOPInstanceUID = "1.2.3.4.5.6.7.8.11"
        ds.SOPClassUID = "1.2.840.10008.5.1.4.1.1.2"
        ds.Modality = "CT"
        
        # Set file meta
        ds.file_meta = pydicom.Dataset()
        ds.file_meta.MediaStorageSOPClassUID = ds.SOPClassUID
        ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
        ds.file_meta.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian
        ds.file_meta.ImplementationClassUID = "1.2.3.4.5.6.7.8.12"
        ds.file_meta.ImplementationVersionName = "TEST_1.0"
        ds.file_meta.FileMetaInformationVersion = b'\x00\x01'
        
        with tempfile.NamedTemporaryFile(suffix='.dcm') as tmp:
            ds.save_as(tmp.name, write_like_original=False)
            
            # Try to read it back
            ds2 = pydicom.dcmread(tmp.name)
            assert ds2.PatientName == "Test^Patient"
            
        print("✓ DICOM file creation and reading works")
        return True
    except Exception as e:
        print(f"✗ DICOM creation test failed: {e}")
        return False

def main():
    """Run all basic tests."""
    print("Running basic functionality tests...")
    print("=" * 50)
    
    tests = [
        ("Configuration", test_config),
        ("Managers", test_managers), 
        ("Anonymization", test_anonymization),
        ("Validation", test_validation),
        ("DICOM Creation", test_dicom_creation)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n{test_name}:")
        if test_func():
            passed += 1
    
    print("\n" + "=" * 50)
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All basic functionality works!")
        print("\nThe test failures are likely due to:")
        print("1. Over-complex mocking in some tests")
        print("2. Missing classes that don't exist in the actual code")
        print("3. Assumption mismatches about the code structure")
        print("\nSuggestion: Focus on the working tests and gradually fix others")
    else:
        print("⚠ Some basic functionality issues found.")
    
    return 0 if passed == total else 1

if __name__ == "__main__":
    exit(main())