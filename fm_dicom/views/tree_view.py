from PyQt6.QtWidgets import QTreeWidget, QTreeWidgetItem

class DicomTreeView(QTreeWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderLabels(["DICOM Hierarchy"])

    def load_hierarchy(self, root_node):
        self.clear()
        def add_items(parent_item, node):
            item = QTreeWidgetItem([node.name])
            parent_item.addChild(item)
            for child in node.children:
                add_items(item, child)
        root_item = QTreeWidgetItem([root_node.name])
        self.addTopLevelItem(root_item)
        for child in root_node.children:
            add_items(root_item, child)
        self.expandAll()
