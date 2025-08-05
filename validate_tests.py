#!/usr/bin/env python3
"""
Test validation script for FM-Dicom.

This script performs basic validation of the test suite setup
to ensure everything is configured correctly.
"""

import sys
import os
from pathlib import Path


def check_test_dependencies():
    """Check if all test dependencies are available."""
    print("Checking test dependencies...")
    
    missing_deps = []
    
    try:
        import pytest
        print("✓ pytest available")
    except ImportError:
        missing_deps.append("pytest")
    
    try:
        import pytestqt
        print("✓ pytest-qt available")
    except ImportError:
        try:
            import pytest_qt
            print("✓ pytest-qt available")
        except ImportError:
            missing_deps.append("pytest-qt")
    
    try:
        import pytest_mock
        print("✓ pytest-mock available")
    except ImportError:
        missing_deps.append("pytest-mock")
    
    try:
        import pytest_cov
        print("✓ pytest-cov available")
    except ImportError:
        missing_deps.append("pytest-cov")
    
    try:
        import pydicom
        print("✓ pydicom available")
    except ImportError:
        missing_deps.append("pydicom")
    
    try:
        from PyQt6.QtWidgets import QApplication
        print("✓ PyQt6 available")
    except ImportError:
        missing_deps.append("PyQt6")
    
    if missing_deps:
        print(f"\n❌ Missing dependencies: {', '.join(missing_deps)}")
        print("Install with: uv sync --extra test")
        return False
    else:
        print("\n✅ All test dependencies are available")
        return True


def check_test_files():
    """Check if all test files exist."""
    print("\nChecking test files...")
    
    test_dir = Path(__file__).parent / "tests"
    expected_files = [
        "conftest.py",
        "test_config.py", 
        "test_dicom_manager.py",
        "test_file_manager.py",
        "test_tree_manager.py",
        "test_dicom_operations.py",
        "test_anonymization.py",
        "test_validation.py",
        "test_workers.py"
    ]
    
    missing_files = []
    
    for test_file in expected_files:
        file_path = test_dir / test_file
        if file_path.exists():
            print(f"✓ {test_file}")
        else:
            missing_files.append(test_file)
            print(f"❌ {test_file}")
    
    if missing_files:
        print(f"\n❌ Missing test files: {', '.join(missing_files)}")
        return False
    else:
        print("\n✅ All test files are present")
        return True


def check_pytest_config():
    """Check if pytest configuration is present."""
    print("\nChecking pytest configuration...")
    
    project_root = Path(__file__).parent
    pytest_ini = project_root / "pytest.ini"
    
    if pytest_ini.exists():
        print("✓ pytest.ini found")
        
        # Check basic configuration
        content = pytest_ini.read_text()
        if "testpaths = tests" in content:
            print("✓ testpaths configured")
        else:
            print("⚠ testpaths not configured")
        
        if "markers" in content:
            print("✓ test markers configured")
        else:
            print("⚠ test markers not configured")
        
        return True
    else:
        print("❌ pytest.ini not found")
        return False


def check_project_structure():
    """Check if the project structure is correct for testing."""
    print("\nChecking project structure...")
    
    project_root = Path(__file__).parent
    
    # Check main package
    fm_dicom_dir = project_root / "fm_dicom"
    if fm_dicom_dir.exists() and fm_dicom_dir.is_dir():
        print("✓ fm_dicom package directory found")
    else:
        print("❌ fm_dicom package directory not found")
        return False
    
    # Check __init__.py
    init_file = fm_dicom_dir / "__init__.py"
    if init_file.exists():
        print("✓ fm_dicom/__init__.py found")
    else:
        print("⚠ fm_dicom/__init__.py not found")
    
    # Check key modules
    key_modules = [
        "managers/dicom_manager.py",
        "managers/file_manager.py", 
        "managers/tree_manager.py",
        "config/config_manager.py"
    ]
    
    for module in key_modules:
        module_path = fm_dicom_dir / module
        if module_path.exists():
            print(f"✓ {module}")
        else:
            print(f"❌ {module}")
            return False
    
    print("\n✅ Project structure looks good")
    return True


def run_basic_test():
    """Run a basic test to verify the setup works."""
    print("\nRunning basic test validation...")
    
    try:
        import subprocess
        result = subprocess.run([
            sys.executable, "-m", "pytest", 
            "tests/test_config.py::TestConfigPath::test_get_config_path_linux",
            "-v", "--tb=short"
        ], capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            print("✅ Basic test passed")
            return True
        else:
            print("❌ Basic test failed:")
            print(result.stdout)
            print(result.stderr)
            return False
    
    except subprocess.TimeoutExpired:
        print("❌ Basic test timed out")
        return False
    except Exception as e:
        print(f"❌ Error running basic test: {e}")
        return False


def main():
    """Run all validation checks."""
    print("FM-Dicom Test Suite Validation")
    print("=" * 40)
    
    checks = [
        ("Dependencies", check_test_dependencies),
        ("Test Files", check_test_files),
        ("Pytest Config", check_pytest_config),
        ("Project Structure", check_project_structure),
        ("Basic Test", run_basic_test)
    ]
    
    passed = 0
    total = len(checks)
    
    for check_name, check_func in checks:
        print(f"\n{check_name}:")
        print("-" * len(check_name))
        
        try:
            if check_func():
                passed += 1
        except Exception as e:
            print(f"❌ Error during {check_name.lower()} check: {e}")
    
    print("\n" + "=" * 40)
    print(f"Validation Results: {passed}/{total} checks passed")
    
    if passed == total:
        print("🎉 Test suite is ready!")
        print("\nNext steps:")
        print("- Run: python run_tests.py")
        print("- Run with coverage: python run_tests.py --coverage")
        return 0
    else:
        print("⚠ Some issues found. Please fix them before running tests.")
        return 1


if __name__ == "__main__":
    sys.exit(main())