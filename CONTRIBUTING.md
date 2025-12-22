# Contributing to FM-DICOM

Thank you for your interest in contributing! This document provides guidelines for setting up your development environment and submitting changes.

## Development Environment

We support two primary workflows: **Nix** (recommended for Linux) and **uv** (standard Python).

### Option 1: Nix (Reproducible)
1.  Ensure [Nix](https://nixos.org/download.html) is installed and flakes are enabled.
2.  Clone the repository.
3.  Enter the shell:
    ```bash
    nix develop
    ```
    This provides Python 3.12, Qt6 libraries, and all dependencies.

### Option 2: UV / Standard Python
1.  Install [uv](https://github.com/astral-sh/uv).
2.  Sync dependencies:
    ```bash
    uv sync
    ```
3.  Run the application:
    ```bash
    uv run -m fm_dicom.main
    ```

## Architecture Overview

*   **MV Pattern**: The app loosely follows a Model-View pattern, but uses "Managers" to handle business logic.
    *   `managers/`: Contains logic for DICOM operations (`dicom_manager.py`), file handling (`file_manager.py`), and tree state (`tree_manager.py`).
    *   `views/` & `widgets/`: Pure UI components.
*   **Communication**: 
    *   Managers should ideally use **Signals** to communicate updates to the UI, rather than modifying widgets directly.
    *   Avoid blocking the main thread for long operations (use `workers/` or `utils/threaded_processor.py`).

## Coding Standards

*   **Style**: Follow PEP 8.
*   **Type Hinting**: Please add type hints to new functions and classes.
*   **Error Handling**:
    *   Avoid bare `except:` blocks.
    *   Handle I/O and Network errors explicitly.
    *   Use `FocusAwareMessageBox` for errors that need user attention.

## Running Tests

Run the full test suite:
```bash
python run_tests.py
```

Run specific tests:
```bash
python -m pytest tests/test_dicom_manager.py
```

## Pull Request Process

1.  Create a new branch for your feature or fix.
2.  Ensure existing tests pass.
3.  Add new tests if you are adding functionality.
4.  Submit a Pull Request with a clear description of the changes.
