from PyQt6.QtWidgets import QMainWindow, QFileDialog, QWidget, QVBoxLayout, QPushButton, QTextEdit
import pydicom

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DICOM Tag Editor")
        self.resize(800, 600)
        self.central = QWidget()
        self.setCentralWidget(self.central)
        self.layout = QVBoxLayout(self.central)

        self.open_btn = QPushButton("Open DICOM File")
        self.open_btn.clicked.connect(self.open_file)
        self.layout.addWidget(self.open_btn)

        self.tag_view = QTextEdit()
        self.tag_view.setReadOnly(True)
        self.layout.addWidget(self.tag_view)

    def open_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open DICOM File", "", "DICOM Files (*.dcm);;All Files (*)")
        if file_path:
            ds = pydicom.dcmread(file_path)
            tags = "\n".join([f"{elem.tag} {elem.name}: {elem.value}" for elem in ds])
            self.tag_view.setText(tags)
