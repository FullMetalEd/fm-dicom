import sys
from PyQt6.QtWidgets import QApplication
from fm_dicom.main_window import MainWindow

def main():
    app = QApplication(sys.argv)
    path = sys.argv[1] if len(sys.argv) > 1 else None
    window = MainWindow(start_path=path)
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
