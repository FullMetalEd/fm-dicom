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
    
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
