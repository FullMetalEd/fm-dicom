# CLI entry point for fm-dtedit and python -m dicomtageditor

import sys
import typer

# Apply pydicom patches before importing other modules that use pydicom
try:
    from .utils.pydicom_patch import apply_pydicom_patch
    apply_pydicom_patch()
except ImportError:
    pass

from .main_window import MainWindow
from PyQt6.QtWidgets import QApplication

app_cli = typer.Typer(help="DICOM Tag Editor CLI")

def launch_gui(
    path: str = typer.Option(None, "--path", "-p", help="DICOM file, ZIP, or directory to open")
):
    """Launch the DICOM Tag Editor GUI."""
    app = QApplication(sys.argv)
    window = MainWindow(start_path=path)
    window.show()
    sys.exit(app.exec())

# Set the default callback to launch the GUI
@app_cli.callback()
def main(
    path: str = typer.Option(None, "--path", "-p", help="DICOM file, ZIP, or directory to open")
):
    launch_gui(path)

# Optionally, keep 'gui' as an explicit command for discoverability
@app_cli.command()
def gui(
    path: str = typer.Option(None, "--path", "-p", help="DICOM file, ZIP, or directory to open")
):
    """Launch the DICOM Tag Editor GUI."""
    launch_gui(path)

if __name__ == "__main__":
    app_cli()
