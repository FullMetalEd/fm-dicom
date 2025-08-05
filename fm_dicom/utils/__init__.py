"""
Utility modules for FM-Dicom application.

This package contains various utility functions and classes for:
- File dialog management with portal integration
- Environment configuration checking
- Helper functions for common operations
"""

from .file_dialogs import get_file_dialog_manager, FileDialogManager
from .environment_check import get_environment_checker, check_environment_on_startup, EnvironmentChecker

__all__ = [
    'get_file_dialog_manager',
    'FileDialogManager', 
    'get_environment_checker',
    'check_environment_on_startup',
    'EnvironmentChecker'
]