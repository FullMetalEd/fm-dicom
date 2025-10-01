"""
Enhanced file dialog utilities with XDG Desktop Portal integration.

This module provides improved file dialog functionality for better integration
with Linux desktop environments, especially Wayland compositors like Hyprland.
"""

import os
import subprocess
import logging
from typing import Optional, List, Tuple
from PyQt6.QtWidgets import QFileDialog, QWidget
from PyQt6.QtCore import QStandardPaths


class FileDialogManager:
    """Manager class for file dialogs with portal integration"""
    
    def __init__(self, config=None):
        self.config = config or {}
        self._portal_available = None
        
    def _is_portal_available(self) -> bool:
        """Check if XDG Desktop Portal is available"""
        if self._portal_available is not None:
            return self._portal_available
            
        try:
            # Check if portal service is running
            result = subprocess.run(
                ['dbus-send', '--session', '--dest=org.freedesktop.portal.Desktop', 
                 '--print-reply', '/org/freedesktop/portal/desktop', 
                 'org.freedesktop.DBus.Peer.Ping'],
                capture_output=True, timeout=2
            )
            self._portal_available = result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            self._portal_available = False
            
        return self._portal_available
    
    def _is_wayland(self) -> bool:
        """Check if we're running on Wayland"""
        return (
            os.environ.get('WAYLAND_DISPLAY') is not None or
            os.environ.get('QT_QPA_PLATFORM') == 'wayland' or
            'wayland' in os.environ.get('QT_QPA_PLATFORM', '').lower()
        )
    
    def _check_qt_environment(self) -> List[str]:
        """Check Qt environment configuration and return warnings"""
        warnings = []
        
        if self._is_wayland():
            # Check essential Wayland Qt environment variables
            required_vars = {
                'QT_QPA_PLATFORM': 'wayland',
                'QT_QPA_PLATFORMTHEME': ['qt6ct', 'gtk3', 'gnome'],
            }
            
            for var, expected in required_vars.items():
                current = os.environ.get(var)
                if not current:
                    if isinstance(expected, list):
                        warnings.append(f"Missing {var}. Set to one of: {', '.join(expected)}")
                    else:
                        warnings.append(f"Missing {var}. Set to: {expected}")
                elif isinstance(expected, list) and current not in expected:
                    warnings.append(f"{var}={current} may not work well. Try: {', '.join(expected)}")
        
        return warnings
    
    def _use_portal_dialog(self) -> bool:
        """Determine if we should use portal dialog"""
        force_portal = self.config.get('force_portal', False)
        native_enabled = self.config.get('file_picker_native', False)

        # Only use portal if explicitly forced, not when user wants native dialogs
        # Native dialogs should use Qt's native dialog system, not portal
        return (force_portal and not native_enabled)

    def _is_linux(self) -> bool:
        """Check if running on Linux"""
        import platform
        return platform.system().lower() == 'linux'

    def _try_system_file_dialog(self, parent: QWidget, title: str, start_dir: str, filter_str: str, dialog_type: str):
        """Try to use actual system file manager for file dialogs"""
        try:
            import subprocess
            import os

            if dialog_type == 'file':
                # Use zenity for file selection - it integrates with system file manager
                cmd = ['zenity', '--file-selection', f'--title={title}']
                if start_dir and os.path.exists(start_dir):
                    cmd.append(f'--filename={start_dir}/')

                # Add file filters
                if 'DICOM' in filter_str:
                    cmd.extend(['--file-filter=DICOM Files | *.dcm *.dicom'])
                if 'ZIP' in filter_str:
                    cmd.extend(['--file-filter=ZIP Archives | *.zip'])
                cmd.extend(['--file-filter=All Files | *'])

            elif dialog_type == 'directory':
                cmd = ['zenity', '--file-selection', '--directory', f'--title={title}']
                if start_dir and os.path.exists(start_dir):
                    cmd.append(f'--filename={start_dir}/')
            else:
                return None

            # Run the command
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode == 0 and result.stdout.strip():
                selected_path = result.stdout.strip()
                if os.path.exists(selected_path):
                    return selected_path

        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            pass
        except Exception as e:
            import logging
            logging.debug(f"System file dialog failed: {e}")

        return None

    def _portal_open_file(self, parent: QWidget, title: str, start_dir: str, 
                         filter_str: str) -> Optional[str]:
        """Open file using XDG Desktop Portal"""
        try:
            # Use zenity as a fallback portal implementation
            cmd = ['zenity', '--file-selection', f'--title={title}']
            
            if start_dir:
                cmd.append(f'--filename={start_dir}/')
            
            # Convert Qt filter to zenity format
            if 'DICOM' in filter_str:
                cmd.extend(['--file-filter=DICOM Files | *.dcm *.dicom'])
            if 'ZIP' in filter_str:
                cmd.extend(['--file-filter=ZIP Archives | *.zip'])
            cmd.extend(['--file-filter=All Files | *'])
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                return result.stdout.strip()
            else:
                logging.debug(f"Portal dialog cancelled or failed: {result.stderr}")
                return None
                
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logging.warning(f"Portal dialog failed: {e}")
            return None
    
    def _portal_open_directory(self, parent: QWidget, title: str, 
                              start_dir: str) -> Optional[str]:
        """Open directory using XDG Desktop Portal"""
        try:
            cmd = ['zenity', '--file-selection', '--directory', f'--title={title}']
            
            if start_dir:
                cmd.append(f'--filename={start_dir}/')
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                return result.stdout.strip()
            else:
                logging.debug(f"Portal directory dialog cancelled or failed: {result.stderr}")
                return None
                
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logging.warning(f"Portal directory dialog failed: {e}")
            return None
    
    def _portal_save_file(self, parent: QWidget, title: str, default_path: str,
                         filter_str: str) -> Optional[str]:
        """Save file using XDG Desktop Portal"""
        try:
            cmd = ['zenity', '--file-selection', '--save', f'--title={title}']
            
            if default_path:
                cmd.append(f'--filename={default_path}')
            
            # Convert filter for save dialogs
            if 'CSV' in filter_str:
                cmd.extend(['--file-filter=CSV Files | *.csv'])
            elif 'HTML' in filter_str:
                cmd.extend(['--file-filter=HTML Files | *.html'])
            elif 'Text' in filter_str:
                cmd.extend(['--file-filter=Text Files | *.txt'])
            cmd.extend(['--file-filter=All Files | *'])
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                return result.stdout.strip()
            else:
                logging.debug(f"Portal save dialog cancelled or failed: {result.stderr}")
                return None
                
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logging.warning(f"Portal save dialog failed: {e}")
            return None
    
    def open_file_dialog(self, parent: QWidget, title: str, start_dir: str,
                        filter_str: str) -> Optional[str]:
        """Open file dialog with portal integration"""
        # Check environment and warn if needed
        warnings = self._check_qt_environment()
        if warnings:
            from fm_dicom.widgets.focus_aware import FocusAwareMessageBox
            warning_text = "Qt Environment Issues Detected:\n\n" + "\n".join(f"• {w}" for w in warnings)
            warning_text += "\n\nFile dialogs may not use your system file manager."
            FocusAwareMessageBox.warning(parent, "Environment Warning", warning_text)
        
        # If user wants native and we're on Linux, try to use actual system file manager
        native_enabled = self.config.get('file_picker_native', False)
        if native_enabled and self._is_linux():
            result = self._try_system_file_dialog(parent, title, start_dir, filter_str, 'file')
            if result is not None:
                return result

        # Try portal if configured
        if self._use_portal_dialog():
            result = self._portal_open_file(parent, title, start_dir, filter_str)
            if result is not None:
                return result
            # Fall back to Qt dialog if portal fails

        # Use Qt dialog with proper configuration
        dialog = QFileDialog(parent, title, start_dir, filter_str)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)

        # Configure native dialog preference
        if not native_enabled:
            dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        
        if dialog.exec():
            files = dialog.selectedFiles()
            return files[0] if files else None
        return None
    
    def open_directory_dialog(self, parent: QWidget, title: str,
                             start_dir: str) -> Optional[str]:
        """Open directory dialog with system integration"""
        # If user wants native and we're on Linux, try to use actual system file manager
        native_enabled = self.config.get('file_picker_native', False)
        if native_enabled and self._is_linux():
            result = self._try_system_file_dialog(parent, title, start_dir, '', 'directory')
            if result is not None:
                return result

        # Try portal if configured
        if self._use_portal_dialog():
            result = self._portal_open_directory(parent, title, start_dir)
            if result is not None:
                return result

        # Use Qt dialog
        dialog = QFileDialog(parent, title, start_dir)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
        dialog.setFileMode(QFileDialog.FileMode.Directory)

        # Configure native dialog preference
        if not native_enabled:
            dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
        
        # Configure native dialog preference
        native_enabled = self.config.get('file_picker_native', False)
        if not native_enabled:
            dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        
        if dialog.exec():
            dirs = dialog.selectedFiles()
            return dirs[0] if dirs else None
        return None
    
    def save_file_dialog(self, parent: QWidget, title: str, default_path: str,
                        filter_str: str) -> Optional[str]:
        """Save file dialog with portal integration"""
        # Try portal first if configured
        if self._use_portal_dialog():
            result = self._portal_save_file(parent, title, default_path, filter_str)
            if result is not None:
                return result
        
        # Use Qt dialog
        dialog = QFileDialog(parent, title, default_path, filter_str)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        
        # Configure native dialog preference
        native_enabled = self.config.get('file_picker_native', False)
        if not native_enabled:
            dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        
        if dialog.exec():
            files = dialog.selectedFiles()
            return files[0] if files else None
        return None


# Global instance for easy access
_file_dialog_manager = None

def get_file_dialog_manager(config=None):
    """Get global file dialog manager instance"""
    global _file_dialog_manager
    if _file_dialog_manager is None:
        _file_dialog_manager = FileDialogManager(config)
    elif config is not None:
        _file_dialog_manager.config.update(config)
    return _file_dialog_manager