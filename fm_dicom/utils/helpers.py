from PyQt6.QtWidgets import QTreeWidgetItem


def depth(self):
    """Return the depth of the item in the tree."""
    depth_val = 0  # Renamed to avoid conflict if self is reused
    parent_item = self.parent()  # Use a different variable name
    while parent_item:
        depth_val += 1
        parent_item = parent_item.parent()
    return depth_val


# Add depth method to QTreeWidgetItem
QTreeWidgetItem.depth = depth
