"""
Tests for configuration management functionality.
"""

import os
import sys
import platform
import tempfile
import shutil
from unittest.mock import patch, MagicMock
import yaml
import pytest

from fm_dicom.config.config_manager import (
    get_config_path,
    get_default_user_dir,
    ensure_dir_exists,
    load_config,
    setup_logging
)


class TestConfigPath:
    """Test configuration path detection."""
    
    def test_get_config_path_linux(self):
        """Test config path on Linux."""
        with patch('platform.system', return_value='Linux'):
            with patch.dict(os.environ, {'XDG_CONFIG_HOME': '/custom/config'}):
                path = get_config_path()
                assert path == '/custom/config/fm-dicom/config.yml'
    
    def test_get_config_path_linux_default(self):
        """Test config path on Linux without XDG_CONFIG_HOME."""
        with patch('platform.system', return_value='Linux'):
            with patch.dict(os.environ, {}, clear=True):
                with patch('os.path.expanduser') as mock_expand:
                    mock_expand.return_value = '/home/user/.config'
                    path = get_config_path()
                    assert path == '/home/user/.config/fm-dicom/config.yml'
    
    def test_get_config_path_windows(self):
        """Test config path on Windows."""
        with patch('platform.system', return_value='Windows'):
            with patch.dict(os.environ, {'APPDATA': 'C:\\Users\\user\\AppData\\Roaming'}):
                path = get_config_path()
                assert path == 'C:\\Users\\user\\AppData\\Roaming\\fm-dicom\\config.yml'
    
    def test_get_config_path_windows_portable(self):
        """Test config path on Windows without APPDATA (portable mode)."""
        with patch('platform.system', return_value='Windows'):
            with patch.dict(os.environ, {}, clear=True):
                with patch('sys.executable', 'C:\\app\\fm-dicom.exe'):
                    path = get_config_path()
                    assert path == 'C:\\app\\fm-dicom\\config.yml'
    
    def test_get_config_path_macos(self):
        """Test config path on macOS."""
        with patch('platform.system', return_value='Darwin'):
            with patch('os.path.expanduser') as mock_expand:
                mock_expand.return_value = '/Users/user/Library/Application Support/fm-dicom/config.yml'
                path = get_config_path()
                assert path == '/Users/user/Library/Application Support/fm-dicom/config.yml'


class TestEnsureDirExists:
    """Test directory creation functionality."""
    
    def test_ensure_dir_exists_success(self, temp_dir):
        """Test successful directory creation."""
        test_file_path = os.path.join(temp_dir, 'subdir', 'file.txt')
        result = ensure_dir_exists(test_file_path)
        assert result is True
        assert os.path.exists(os.path.dirname(test_file_path))
    
    def test_ensure_dir_exists_empty_path(self):
        """Test with empty path."""
        result = ensure_dir_exists('')
        assert result is False
    
    def test_ensure_dir_exists_none_path(self):
        """Test with None path."""
        result = ensure_dir_exists(None)
        assert result is False
    
    def test_ensure_dir_exists_already_exists(self, temp_dir):
        """Test with existing directory."""
        test_file_path = os.path.join(temp_dir, 'file.txt')
        result = ensure_dir_exists(test_file_path)
        assert result is True


class TestLoadConfig:
    """Test configuration loading functionality."""
    
    def test_load_config_default(self):
        """Test loading default configuration when no file exists."""
        with patch('os.path.exists', return_value=False):
            with patch('fm_dicom.config.config_manager.ensure_dir_exists', return_value=True):
                with patch('builtins.open', create=True) as mock_open:
                    config = load_config()
                    
                    # Check default values
                    assert config['log_level'] == 'INFO'
                    assert config['show_image_preview'] is False
                    assert config['ae_title'] == 'DCMSCU'
                    assert config['theme'] == 'dark'
                    assert config['language'] == 'en'
                    assert isinstance(config['destinations'], list)
                    assert len(config['destinations']) == 0
    
    def test_load_config_from_file(self, temp_config_file, sample_config):
        """Test loading configuration from existing file."""
        config = load_config(temp_config_file)
        
        assert config['log_level'] == sample_config['log_level']
        assert config['show_image_preview'] == sample_config['show_image_preview']
        assert config['ae_title'] == sample_config['ae_title']
        assert config['theme'] == sample_config['theme']
        assert len(config['destinations']) == 1
    
    def test_load_config_partial_file(self, temp_dir):
        """Test loading configuration with partial config file."""
        partial_config = {
            'theme': 'light',
            'ae_title': 'CUSTOM_AE'
        }
        
        config_path = os.path.join(temp_dir, 'partial_config.yml')
        with open(config_path, 'w') as f:
            yaml.dump(partial_config, f)
        
        config = load_config(config_path)
        
        # Partial config values should override defaults
        assert config['theme'] == 'light'
        assert config['ae_title'] == 'CUSTOM_AE'
        
        # Default values should still be present
        assert config['log_level'] == 'INFO'
        assert config['show_image_preview'] is False
    
    def test_load_config_empty_file(self, temp_dir):
        """Test loading configuration from empty file."""
        config_path = os.path.join(temp_dir, 'empty_config.yml')
        with open(config_path, 'w') as f:
            f.write('')
        
        config = load_config(config_path)
        
        # Should fall back to defaults
        assert config['log_level'] == 'INFO'
        assert config['show_image_preview'] is False
        assert config['ae_title'] == 'DCMSCU'
    
    def test_load_config_invalid_yaml(self, temp_dir):
        """Test loading configuration from invalid YAML file."""
        config_path = os.path.join(temp_dir, 'invalid_config.yml')
        with open(config_path, 'w') as f:
            f.write('invalid: yaml: content: [')
        
        # Suppress logging errors during this test
        with patch('logging.critical'):
            config = load_config(config_path)
        
        # Should fall back to defaults
        assert config['log_level'] == 'INFO'
        assert config['show_image_preview'] is False
    
    def test_load_config_path_expansion(self, temp_dir):
        """Test that paths are properly expanded."""
        test_config = {
            'log_path': '~/test.log',
            'default_export_dir': '~/exports',
            'default_import_dir': '~/imports'
        }
        
        config_path = os.path.join(temp_dir, 'path_config.yml')
        with open(config_path, 'w') as f:
            yaml.dump(test_config, f)
        
        config = load_config(config_path)
        
        # Paths should be expanded
        assert '~' not in config['log_path']
        assert '~' not in config['default_export_dir']
        assert '~' not in config['default_import_dir']


class TestSetupLogging:
    """Test logging setup functionality."""
    
    def test_setup_logging_with_file(self, temp_dir):
        """Test logging setup with file handler."""
        log_path = os.path.join(temp_dir, 'test.log')
        
        with patch('logging.getLogger') as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger
            mock_logger.hasHandlers.return_value = False
            
            setup_logging(log_path, 'DEBUG')
            
            # Should set log level
            mock_logger.setLevel.assert_called()
            
            # Should add handlers
            assert mock_logger.addHandler.call_count == 2  # Stream and file handlers
    
    def test_setup_logging_without_file(self):
        """Test logging setup without file handler."""
        with patch('logging.getLogger') as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger
            mock_logger.hasHandlers.return_value = False
            
            setup_logging(None, 'INFO')
            
            # Should only add stream handler
            assert mock_logger.addHandler.call_count == 1
    
    def test_setup_logging_invalid_level(self, temp_dir):
        """Test logging setup with invalid log level."""
        log_path = os.path.join(temp_dir, 'test.log')
        
        with patch('logging.getLogger') as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger
            mock_logger.hasHandlers.return_value = False
            
            setup_logging(log_path, 'INVALID_LEVEL')
            
            # Should fall back to INFO level
            import logging
            mock_logger.setLevel.assert_called_with(logging.INFO)
    
    def test_setup_logging_clear_existing_handlers(self, temp_dir):
        """Test that existing handlers are cleared."""
        log_path = os.path.join(temp_dir, 'test.log')
        
        with patch('logging.getLogger') as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger
            mock_logger.hasHandlers.return_value = True
            
            setup_logging(log_path, 'INFO')
            
            # Should clear existing handlers
            mock_logger.handlers.clear.assert_called_once()


class TestGetDefaultUserDir:
    """Test default user directory detection."""
    
    def test_get_default_user_dir(self, qapp):
        """Test getting default user directory."""
        from PyQt6.QtCore import QDir
        
        with patch.object(QDir, 'homePath', return_value='/home/user'):
            user_dir = get_default_user_dir()
            assert user_dir == '/home/user'