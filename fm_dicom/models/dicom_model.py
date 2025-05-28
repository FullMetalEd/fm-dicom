import pydicom

class DicomNode:
    def __init__(self, name, dataset=None, children=None):
        self.name = name
        self.dataset = dataset  # pydicom.Dataset or None
        self.children = children if children is not None else []

    def add_child(self, node):
        self.children.append(node)

def load_dicom_file(filepath):
    ds = pydicom.dcmread(filepath)
    return DicomNode(ds.PatientName if 'PatientName' in ds else "Unknown Patient", ds)
