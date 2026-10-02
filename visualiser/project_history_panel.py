"""Persistent revision review; restore preserves current edits first."""
from pathlib import Path

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QComboBox, QPushButton, QPlainTextEdit, QMessageBox


class ProjectHistoryPanel(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        layout = QVBoxLayout(self)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.revisions = QComboBox()
        self.revisions.setAccessibleName("Saved revision")
        layout.addWidget(self.revisions)
        self.compare_button = QPushButton("Compare with current edits")
        self.compare_button.clicked.connect(self.compare)
        layout.addWidget(self.compare_button)
        self.changes = QPlainTextEdit()
        self.changes.setReadOnly(True)
        self.changes.setAccessibleName("Configuration differences")
        layout.addWidget(self.changes)
        self.restore_button = QPushButton("Preserve edits and restore selected revision")
        self.restore_button.clicked.connect(self.restore)
        layout.addWidget(self.restore_button)
        self.refresh()

    def refresh(self):
        self.revisions.clear()
        self.changes.clear()
        project = self.editor.project
        self.compare_button.setEnabled(project is not None)
        self.restore_button.setEnabled(project is not None)
        self.summary.setText("Save as an AMR project to start revision history." if project is None else
            f"{len(project.revisions)} saved revision(s). Restore saves your current edits first. Simulation results remain external. Differences are a snapshot; compare again after editing.")
        if project is not None:
            for rev in reversed(project.revisions):
                self.revisions.addItem(f"{rev['created_utc'][:19]} UTC | {rev['label']} | {rev['id'][:8]}", rev["id"])

    def compare(self):
        try:
            result = self.editor.project.compare(self.revisions.currentData(), self.editor.store.data,
                                                  base_dir=Path(self.editor.current_json_path).parent)
            self.changes.setPlainText(result or "No configuration differences.")
        except Exception as exc:
            QMessageBox.critical(self, "Comparison failed", str(exc))

    def restore(self):
        try:
            project = self.editor.project
            project.restore(self.revisions.currentData(), self.editor.store.data,
                            base_dir=Path(self.editor.current_json_path).parent)
            self.editor.load_json_file(str(project.path), load_drawings=self.editor._drawings_enabled, check_unsaved=False)
        except Exception as exc:
            QMessageBox.critical(self, "Restore failed", str(exc))
