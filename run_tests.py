#!/usr/bin/env python3
"""
Test runner for FM-Dicom tests.

This script provides a convenient way to run tests with different configurations
and generate coverage reports.
"""

import sys
import subprocess
import argparse
from pathlib import Path


def run_tests(test_args=None, coverage=False, verbose=False, markers=None):
    """Run the test suite with specified options."""
    
    # Build pytest command
    cmd = [sys.executable, "-m", "pytest"]
    
    # Add test directory
    cmd.append("tests/")
    
    # Add coverage if requested
    if coverage:
        cmd.extend([
            "--cov=fm_dicom",
            "--cov-report=html:htmlcov",
            "--cov-report=term-missing",
            "--cov-report=xml:coverage.xml"
        ])
    
    # Add verbosity
    if verbose:
        cmd.append("-v")
    else:
        cmd.append("-q")
    
    # Add markers filter
    if markers:
        cmd.extend(["-m", markers])
    
    # Add any additional arguments
    if test_args:
        cmd.extend(test_args)
    
    print(f"Running: {' '.join(cmd)}")
    print("-" * 50)
    
    # Run the tests
    result = subprocess.run(cmd, capture_output=False)
    return result.returncode


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Run FM-Dicom tests")
    
    parser.add_argument(
        "--coverage", "-c",
        action="store_true",
        help="Generate coverage report"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Run tests in verbose mode"
    )
    
    parser.add_argument(
        "--unit",
        action="store_const",
        const="unit",
        dest="markers",
        help="Run only unit tests"
    )
    
    parser.add_argument(
        "--integration",
        action="store_const",
        const="integration", 
        dest="markers",
        help="Run only integration tests"
    )
    
    parser.add_argument(
        "--gui",
        action="store_const",
        const="gui",
        dest="markers", 
        help="Run only GUI tests"
    )
    
    parser.add_argument(
        "--fast",
        action="store_const",
        const="not slow",
        dest="markers",
        help="Run only fast tests (exclude slow tests)"
    )
    
    parser.add_argument(
        "test_args",
        nargs="*",
        help="Additional arguments to pass to pytest"
    )
    
    args = parser.parse_args()
    
    # Check if test dependencies are available
    try:
        import pytest
        try:
            import pytestqt
        except ImportError:
            import pytest_qt
        import pytest_mock
    except ImportError as e:
        print(f"Error: Missing test dependency: {e}")
        print("Install test dependencies with: uv sync --extra test")
        print("Or with pip: pip install -e .[test]")
        return 1
    
    # Run tests
    return run_tests(
        test_args=args.test_args,
        coverage=args.coverage,
        verbose=args.verbose,
        markers=args.markers
    )


if __name__ == "__main__":
    sys.exit(main())