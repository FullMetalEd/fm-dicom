# CLI entry point for fm-dtedit and python -m dicomtageditor

import sys
from .app import MainWindow
from PyQt6.QtWidgets import QApplication

def main():
    import argparse
    parser = argparse.ArgumentParser(description="DICOM Tag Editor")
    parser.add_argument("path", nargs="?", help="DICOM file, ZIP, or directory to open")
    args = parser.parse_args()
    app = QApplication(sys.argv)
    window = MainWindow(start_path=args.path)
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
