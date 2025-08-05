#!/usr/bin/env python3
"""
Standalone entry point for DICOM Tag Editor
Use this for PyInstaller builds
"""
import sys
import os

# Add the current directory to Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

def main():
    try:
        from PyQt6.QtWidgets import QApplication
        from fm_dicom.main_window import MainWindow
        
        app = QApplication(sys.argv)
        
        # Handle command line arguments
        start_path = None
        if len(sys.argv) > 1:
            start_path = sys.argv[1]
            
        window = MainWindow(start_path=start_path)
        window.show()
        
        return app.exec()
        
    except Exception as e:
        print(f"Error starting application: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())