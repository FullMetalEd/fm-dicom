# FM-Dicom Test Suite

This directory contains comprehensive tests for the FM-Dicom application to ensure functionality is preserved during UI upgrades and other changes.

## Overview

The test suite is designed to prevent regression during the planned UI upgrade by thoroughly testing:

- Core functionality (DICOM loading, editing, saving)
- Manager classes (DicomManager, FileManager, TreeManager)
- Configuration management
- Anonymization functionality
- Validation functionality
- Worker classes (background processing)
- DICOM operations (DICOMDIR reading, path generation)

## Test Structure

```
tests/
├── README.md                 # This file
├── conftest.py              # Pytest configuration and fixtures
├── test_config.py           # Configuration management tests
├── test_dicom_manager.py    # DicomManager tests
├── test_file_manager.py     # FileManager tests
├── test_tree_manager.py     # TreeManager tests
├── test_dicom_operations.py # Core DICOM operations tests
├── test_anonymization.py    # Anonymization functionality tests
├── test_validation.py       # Validation functionality tests
└── test_workers.py          # Worker classes tests
```

## Running Tests

### Prerequisites

Install test dependencies:
```bash
# Using uv (recommended)
uv sync --extra test

# Or using pip
pip install -e .[test]
```

### Basic Usage

```bash
# Run all tests
python run_tests.py

# Run with coverage report
python run_tests.py --coverage

# Run specific test categories
python run_tests.py --unit        # Unit tests only
python run_tests.py --integration # Integration tests only
python run_tests.py --gui         # GUI-related tests only
python run_tests.py --fast        # Exclude slow tests

# Run specific test files
python run_tests.py tests/test_config.py
python run_tests.py tests/test_dicom_manager.py

# Run with verbose output
python run_tests.py --verbose

# Run using pytest directly
pytest tests/ -v
pytest tests/test_config.py -v
```

### Test Markers

Tests are organized using pytest markers:

- `@pytest.mark.unit` - Unit tests (isolated, fast)
- `@pytest.mark.integration` - Integration tests (test component interaction)
- `@pytest.mark.gui` - GUI-related tests (require Qt application)
- `@pytest.mark.slow` - Tests that take longer to run

### Coverage Reports

When running with `--coverage`, reports are generated in:
- `htmlcov/index.html` - HTML coverage report (open in browser)
- `coverage.xml` - XML coverage report (for CI/CD)
- Terminal output - Summary with missing line numbers

## Test Categories

### Configuration Tests (`test_config.py`)
- Platform-specific config path detection
- Config file loading and parsing
- Default value handling
- Error handling for invalid configs
- Logging setup

### Manager Tests
- **DicomManager** (`test_dicom_manager.py`): DICOM tag loading, editing, filtering
- **FileManager** (`test_file_manager.py`): File loading, ZIP extraction, directory scanning
- **TreeManager** (`test_tree_manager.py`): Tree population, selection handling, hierarchy management

### Core Operations Tests (`test_dicom_operations.py`)
- DICOMDIR reading and parsing
- DICOM path generation
- File hierarchy building
- Error handling for corrupted files

### Feature Tests
- **Anonymization** (`test_anonymization.py`): Template-based anonymization, rule application
- **Validation** (`test_validation.py`): DICOM validation, issue reporting, report generation

### Worker Tests (`test_workers.py`)
- Background processing workers
- Progress reporting
- Cancellation handling
- Error handling in threaded operations

## Test Fixtures

The test suite provides several reusable fixtures:

- `qapp` - Qt application instance for GUI tests
- `temp_dir` - Temporary directory (auto-cleaned)
- `sample_dicom_file` - Single valid DICOM file
- `multiple_dicom_files` - Set of DICOM files for batch operations
- `sample_config` - Sample configuration dictionary
- `mock_main_window` - Mock main window for manager testing

## Mocking Strategy

Tests use extensive mocking to:
- Isolate units under test
- Avoid dependency on external resources
- Speed up test execution
- Control error conditions for testing

Key mocking patterns:
- GUI components (QTableWidget, QTreeWidget, etc.)
- File system operations
- DICOM file reading/writing
- Network operations
- Progress dialogs

## Best Practices

When adding new tests:

1. **Use appropriate markers** - Mark tests with `@pytest.mark.unit`, `@pytest.mark.integration`, etc.
2. **Mock external dependencies** - Don't rely on real files, network, or GUI in unit tests
3. **Test error conditions** - Include tests for failure scenarios
4. **Use fixtures** - Reuse common test data and setup
5. **Descriptive test names** - Make test purpose clear from the name
6. **Test both success and failure paths** - Ensure robust error handling

## Continuous Integration

The test suite is designed to run in CI environments:

- No GUI dependencies in unit tests (use mocking)
- Temporary files are properly cleaned up
- Cross-platform compatibility
- Deterministic test execution

## Troubleshooting

### Common Issues

1. **Qt/GUI related errors**: Make sure you're running tests in a proper Qt environment
2. **Import errors**: Ensure all dependencies are installed (`pip install -e .[test]`)
3. **File permission errors**: Tests create temporary files - ensure write permissions
4. **Platform-specific failures**: Some config tests may behave differently on different OS

### Debug Mode

Run tests with maximum verbosity:
```bash
python run_tests.py --verbose tests/specific_test.py::test_function -s
```

The `-s` flag disables output capture, allowing you to see print statements and debug output.

## Contributing

When modifying the codebase:

1. **Run tests before changes**: Establish baseline
2. **Add tests for new functionality**: Maintain coverage
3. **Update tests for modified behavior**: Keep tests in sync
4. **Run full test suite**: Ensure no regressions
5. **Check coverage**: Aim for high test coverage

## Pre-UI Upgrade Checklist

Before starting the UI upgrade:

- [ ] All tests pass: `python run_tests.py`
- [ ] Coverage is adequate: `python run_tests.py --coverage`
- [ ] No skipped tests due to missing dependencies
- [ ] Tests run on target deployment platform
- [ ] Baseline performance metrics captured

During UI upgrade:

- [ ] Run tests frequently to catch regressions early
- [ ] Update GUI-related tests as needed
- [ ] Maintain backward compatibility where possible
- [ ] Add tests for new UI functionality

After UI upgrade:

- [ ] All tests pass with new UI
- [ ] Performance is maintained or improved
- [ ] New UI features have appropriate test coverage
- [ ] Legacy functionality still works as expected