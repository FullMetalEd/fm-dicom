import os
import sys
import yaml
import logging
import platform
from PyQt6.QtCore import QDir


def _is_running_from_executable():
    """Check if we're running from a .exe file (portable mode) vs python script"""
    return getattr(sys, 'frozen', False) or sys.executable.endswith('.exe') and not sys.executable.endswith('python.exe')


def _get_windows_config_path(app_name):
    """Get Windows-specific config path with improved fallback logic"""
    # Try standard Windows app data directory first
    appdata = os.environ.get("APPDATA")
    if appdata and _is_path_accessible(appdata):
        config_path = os.path.join(appdata, app_name, "config.yml")
        if _is_path_writable(os.path.dirname(config_path)):
            return config_path

    # If running from executable and APPDATA failed, try exe directory (portable mode)
    if _is_running_from_executable():
        exe_dir = os.path.dirname(sys.executable)
        if _is_path_writable(exe_dir):
            return os.path.join(exe_dir, app_name, "config.yml")

    # Fallback to user profile directory
    user_profile = os.environ.get("USERPROFILE")
    if user_profile and _is_path_accessible(user_profile):
        config_path = os.path.join(user_profile, f".{app_name}", "config.yml")
        if _is_path_writable(os.path.dirname(config_path)):
            return config_path

    # Final fallback - try temp directory (will work but not persistent)
    import tempfile
    temp_dir = tempfile.gettempdir()
    return os.path.join(temp_dir, app_name, "config.yml")


def _is_path_accessible(path):
    """Check if a path exists and is accessible"""
    try:
        return path and os.path.exists(path) and os.access(path, os.R_OK)
    except (OSError, TypeError):
        return False


def _is_path_writable(path):
    """Check if a directory path is writable (creating parent dirs if needed)"""
    try:
        if not path:
            return False

        # If path exists, check if writable
        if os.path.exists(path):
            return os.access(path, os.W_OK)

        # If path doesn't exist, check if we can create it
        parent_dir = os.path.dirname(path)
        if parent_dir and parent_dir != path:  # Avoid infinite recursion
            return _is_path_writable(parent_dir)

        return False
    except (OSError, TypeError):
        return False


def get_default_user_dir():
    # QDir is imported from PyQt6.QtCore at the top of the file
    return str(QDir.homePath())


def get_config_path():
    """Get the platform-specific configuration file path"""
    system = platform.system()
    app_name = "fm-dicom"

    # Determine platform-specific default paths
    if system == "Windows":
        return _get_windows_config_path(app_name)
    elif system == "Darwin":  # macOS
        return os.path.expanduser(f"~/Library/Application Support/{app_name}/config.yml")
    else:  # Linux/Unix like systems
        xdg_config_home = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
        return os.path.join(xdg_config_home, app_name, "config.yml")


def ensure_dir_exists(file_path):
    if not file_path:
        # Logging might not be set up when this is first called by load_config for default log path
        print(f"Warning (ensure_dir_exists): Called with empty file_path.", file=sys.stderr)
        return False

    try:
        dir_name = os.path.dirname(file_path)
        if not dir_name:
            return False

        # Create directory with proper error handling
        os.makedirs(dir_name, exist_ok=True)

        # Verify the directory was created and is writable
        if os.path.exists(dir_name) and os.access(dir_name, os.W_OK):
            return True
        else:
            print(f"Warning (ensure_dir_exists): Directory {dir_name} exists but is not writable", file=sys.stderr)
            return False

    except PermissionError as e:
        print(f"Warning (ensure_dir_exists): Permission denied creating directory for {file_path}: {e}", file=sys.stderr)
        return False
    except OSError as e:
        print(f"Warning (ensure_dir_exists): OS error creating directory for {file_path}: {e}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"Warning (ensure_dir_exists): Unexpected error creating directory for {file_path}: {e}", file=sys.stderr)
        return False


def get_config_diagnostics():
    """Get diagnostic information about configuration paths and accessibility"""
    system = platform.system()
    app_name = "fm-dicom"
    diagnostics = {
        'system': system,
        'is_executable': _is_running_from_executable(),
        'paths_checked': [],
        'environment_vars': {},
        'errors': []
    }

    if system == "Windows":
        # Check environment variables
        for var_name in ['APPDATA', 'LOCALAPPDATA', 'USERPROFILE']:
            var_value = os.environ.get(var_name)
            diagnostics['environment_vars'][var_name] = {
                'value': var_value,
                'accessible': _is_path_accessible(var_value) if var_value else False
            }

        # Check potential config paths
        potential_paths = [
            _get_windows_config_path(app_name),
        ]

        if _is_running_from_executable():
            potential_paths.append(os.path.join(os.path.dirname(sys.executable), "config.yml"))

        user_profile = os.environ.get("USERPROFILE")
        if user_profile:
            potential_paths.append(os.path.join(user_profile, f".{app_name}", "config.yml"))

        for path in potential_paths:
            path_info = {
                'path': path,
                'exists': os.path.exists(path),
                'parent_writable': _is_path_writable(os.path.dirname(path))
            }
            diagnostics['paths_checked'].append(path_info)

    return diagnostics


def load_config(config_path_override=None):
    system = platform.system()
    app_name = "fm-dicom"

    # Determine platform-specific default paths
    if system == "Windows":
        preferred_config_path = _get_windows_config_path(app_name)

        # For logs, prefer LOCALAPPDATA, then fall back to same logic as config
        log_base = os.environ.get("LOCALAPPDATA")
        if not log_base or not _is_path_accessible(log_base):
            log_base = os.environ.get("APPDATA")
            if not log_base or not _is_path_accessible(log_base):
                if _is_running_from_executable():
                    log_base = os.path.dirname(sys.executable)
                else:
                    log_base = get_default_user_dir()
        default_log_path = os.path.join(log_base, app_name, "logs", f"{app_name}.log")
    elif system == "Darwin":  # macOS
        preferred_config_path = os.path.expanduser(f"~/Library/Application Support/{app_name}/config.yml")
        default_log_path = os.path.expanduser(f"~/Library/Logs/{app_name}/{app_name}.log")
    else:  # Linux/Unix like systems
        xdg_config_home = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
        preferred_config_path = os.path.join(xdg_config_home, app_name, "config.yml")
        
        xdg_state_home = os.environ.get("XDG_STATE_HOME", os.path.expanduser("~/.local/state"))
        default_log_path = os.path.join(xdg_state_home, app_name, "logs", f"{app_name}.log")

    default_user_home_dir = get_default_user_dir()
    default_config_data = {
        "log_path": default_log_path,
        "log_level": "INFO",
        "show_image_preview": False,
        "ae_title": "DCMSCU",
        "destinations": [],
        "window_size": [1200, 800],
        "default_export_dir": os.path.join(default_user_home_dir, "DICOM_Exports"),
        "default_import_dir": os.path.join(default_user_home_dir, "Downloads"),
        "anonymization": {},
        "recent_paths": [],
        "theme": "dark",
        "language": "en",
        "file_picker_native": False  # ADD THIS LINE - False = use Python/Qt picker by default
    }

    paths_to_check = []
    if config_path_override:
        paths_to_check.append(os.path.expanduser(config_path_override))
    
    paths_to_check.append(preferred_config_path)
    if system == "Windows":  # Additional fallback paths for Windows
        # Portable mode - config.yml next to exe
        if _is_running_from_executable():
            paths_to_check.append(os.path.join(os.path.dirname(sys.executable), "config.yml"))

        # Legacy fallback - user profile directory
        user_profile = os.environ.get("USERPROFILE")
        if user_profile:
            paths_to_check.append(os.path.join(user_profile, f".{app_name}", "config.yml"))
    # paths_to_check.append(os.path.join(os.path.dirname(__file__), "config.yml")) # For a bundled default (read-only)

    loaded_user_config = None
    # loaded_config_source_path = None # To know which file was loaded
    for path_to_try in paths_to_check:
        if path_to_try and os.path.exists(path_to_try):
            try:
                with open(path_to_try, "r", encoding="utf-8") as f:
                    content = f.read()
                    if not content.strip():  # Handle truly empty file
                        loaded_user_config = {}
                    else:
                        loaded_user_config = yaml.safe_load(content)
                        if loaded_user_config is None:  # If file had only comments or invalid YAML resulting in None
                            loaded_user_config = {}
                # Use print here as logging might not be set up yet
                print(f"INFO (load_config): Loaded configuration from {path_to_try}", file=sys.stderr)
                # loaded_config_source_path = path_to_try
                break 
            except Exception as e:
                print(f"Warning (load_config): Could not load/parse config from {path_to_try}: {e}", file=sys.stderr)
                loaded_user_config = None  # Ensure reset

    final_config = default_config_data.copy()
    if loaded_user_config is not None:
        final_config.update(loaded_user_config)  # User settings override defaults

    path_keys = ["log_path", "default_export_dir", "default_import_dir"]
    for key in path_keys:
        if key in final_config and final_config[key] is not None:
            final_config[key] = os.path.expanduser(str(final_config[key]))
        elif key not in final_config:  # Key missing entirely
             final_config[key] = default_config_data.get(key)  # Fallback to default's default
             print(f"Warning (load_config): Path key '{key}' missing, using default: {final_config[key]}", file=sys.stderr)
        elif final_config[key] is None and key in default_config_data:  # Key present but explicitly null
            final_config[key] = default_config_data[key]  # Revert to default
            print(f"Info (load_config): Path key '{key}' was null, reverted to default: {final_config[key]}", file=sys.stderr)

    if loaded_user_config is None:  # No config file found or loaded successfully
        print(f"INFO (load_config): No existing config found. Creating default at: {preferred_config_path}", file=sys.stderr)
        config_created = False

        if ensure_dir_exists(preferred_config_path):  # Ensure config directory exists
            try:
                with open(preferred_config_path, "w", encoding="utf-8") as f:
                    yaml.safe_dump(final_config, f, sort_keys=False, allow_unicode=True)
                config_created = True
                if final_config.get("log_path"):  # Ensure default log directory exists
                    ensure_dir_exists(final_config["log_path"])
            except Exception as e:
                print(f"ERROR (load_config): Could not create default config at {preferred_config_path}: {e}", file=sys.stderr)
        else:
            print(f"ERROR (load_config): Could not create dir for default config: {os.path.dirname(preferred_config_path)}. Using in-memory defaults.", file=sys.stderr)

        # Store configuration issues for GUI notification
        final_config['_config_issues'] = {
            'created_successfully': config_created,
            'preferred_path': preferred_config_path,
            'using_memory_only': not config_created
        }
    # Store diagnostic information in config for debugging
    if platform.system() == "Windows":
        final_config['_diagnostics'] = get_config_diagnostics()

    return final_config


def setup_logging(log_path_from_config, log_level_str_from_config):  # Renamed params for clarity
    log_level_str = str(log_level_str_from_config).upper()
    log_level = getattr(logging, log_level_str, logging.INFO)  # Default to INFO if invalid
    
    logger = logging.getLogger()  # Get root logger
    logger.setLevel(log_level)

    if logger.hasHandlers():  # Clear any existing handlers from previous runs or calls
        logger.handlers.clear()

    # Always add StreamHandler for console output
    stream_handler = logging.StreamHandler(sys.stderr)
    # Simple format for console, can be more detailed if needed
    stream_formatter = logging.Formatter("%(asctime)s [%(levelname)-7.7s] %(message)s") 
    stream_handler.setFormatter(stream_formatter)
    logger.addHandler(stream_handler)

    if not log_path_from_config:
        # Logging is already set up with StreamHandler, so use it.
        logging.error("Log path not configured. File logging disabled. Logging to stderr only.")
        return

    # Ensure the log directory exists (critical step before attempting FileHandler)
    if not ensure_dir_exists(log_path_from_config):
        logging.error(f"Could not create log directory for {log_path_from_config}. File logging disabled. Logging to stderr only.")
        return

    # Proceed with FileHandler
    try:
        # mode="w" truncates log on each run. Use mode="a" to append.
        file_handler = logging.FileHandler(log_path_from_config, mode="w", encoding="utf-8")
        # More detailed format for file logs
        file_formatter = logging.Formatter("%(asctime)s [%(levelname)-5.5s] %(name)s (%(module)s.%(funcName)s:%(lineno)d): %(message)s")
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
        # Initial log message to confirm file logging is active
        logging.info(f"File logging initialized. Level: {log_level_str}. Output to: {log_path_from_config}")
    except Exception as e:
        # If FileHandler fails, logging will still go to StreamHandler
        logging.error(f"Could not set up file logger at {log_path_from_config}: {e}. Logging to stderr only.")