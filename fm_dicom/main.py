import sys
from PyQt6.QtWidgets import QApplication
from fm_dicom.main_window import MainWindow
from fm_dicom.utils.environment_check import check_environment_on_startup

def main():
    app = QApplication(sys.argv)

    # Check environment configuration on startup
    env_result = check_environment_on_startup(show_warnings=True)

    path = sys.argv[1] if len(sys.argv) > 1 else None
    window = MainWindow(start_path=path)
    
    # Show environment warnings if there are significant issues
    if env_result['score'] < 60 and (env_result['issues'] or env_result['warnings']):
        from fm_dicom.utils.environment_check import get_environment_checker
        checker = get_environment_checker()
        warning_text = checker.format_recommendations(env_result)

        from fm_dicom.widgets.focus_aware import FocusAwareMessageBox
        FocusAwareMessageBox.information(
            window,
            "Environment Configuration",
            f"FM-Dicom Environment Check:\n\n{warning_text}"
        )

    # Show configuration issues if any (Windows-specific)
    from fm_dicom.config.config_manager import load_config
    config = load_config()
    if config.get('_config_issues'):
        config_issues = config['_config_issues']
        if not config_issues.get('created_successfully', True):
            from fm_dicom.widgets.focus_aware import FocusAwareMessageBox
            issue_message = (
                "Configuration File Issues:\n\n"
                f"Could not create configuration file at:\n{config_issues.get('preferred_path', 'Unknown path')}\n\n"
                "The application will work but settings won't be saved.\n\n"
                "This may be due to insufficient permissions or a read-only directory.\n"
                "Try running as administrator or check folder permissions."
            )
            FocusAwareMessageBox.warning(
                window,
                "Configuration Warning",
                issue_message
            )
    
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
