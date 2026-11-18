"""Native run table retaining the selection interface used by the workflow."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem


class RunTable(QTableWidget):
    currentRowChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(0, 5, parent)
        self.setHorizontalHeaderLabels(['Name', 'Date and time', 'Storage', 'Status', 'Note'])
        self.horizontalHeaderItem(1).setToolTip('Run creation time in your computer local time zone')
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.setWordWrap(False)
        self.verticalHeader().hide()
        self.verticalHeader().setDefaultSectionSize(32)
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        self.setColumnWidth(1, 165)
        self.setColumnWidth(2, 95)
        self.setColumnWidth(3, 155)
        self.currentCellChanged.connect(lambda row, *_: self.currentRowChanged.emit(row))

    def count(self):
        return self.rowCount()

    def item(self, row, column=0):
        return super().item(row, column)

    def setCurrentRow(self, row):
        self.setCurrentCell(row, 0)

    def clear(self):
        self.setRowCount(0)

    def append_run(self, values, tooltip):
        row = self.rowCount()
        self.insertRow(row)
        for column, text in enumerate(values):
            item = QTableWidgetItem(text)
            item.setToolTip(tooltip if column == 0 else text)
            self.setItem(row, column, item)
