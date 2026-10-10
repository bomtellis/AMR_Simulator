"""Persistent revision review; restore preserves current edits first."""
from pathlib import Path

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QComboBox, QPushButton, QPlainTextEdit, QMessageBox


class ProjectHistoryPanel(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        layout = QVBoxLayout(self)
        from PySide6.QtWidgets import QHBoxLayout
        actions = QHBoxLayout()
        for title, handler in [('Open project / JSON', editor.open_json), ('Save project', editor.save_project),
                               ('Save project as', lambda: editor.save_project(save_as=True)),
                               ('Export JSON', editor.export_project_json), ('Recovery copies', editor.recover_unsaved_work)]:
            button = QPushButton(title)
            button.clicked.connect(handler)
            actions.addWidget(button)
        layout.addLayout(actions)
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
        self.restore_button.setEnabled(project is not None and not self.editor.project_editing_locked())
        self.summary.setText("Save as an AMR project to start revision history." if project is None else
            f"{len(project.revisions)} saved revision(s). Restore saves your current edits first. "
            "If Save fails, keep the editor open; Recovery copies can open an available snapshot, "
            "which you must save to a new file. Simulation results remain external. "
            "Differences are a snapshot; compare again after editing.")
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
        if not self.editor._project_editing_allowed():
            return
        if self.editor._history_busy():
            QMessageBox.information(self, "Finish editing first", "Finish or close the active editor before restoring a revision.")
            return
        try:
            project = self.editor.project
            project.restore(self.revisions.currentData(), self.editor.store.data,
                            base_dir=Path(self.editor.current_json_path).parent)
            self.editor.load_json_file(str(project.path), load_drawings=self.editor._drawings_enabled, check_unsaved=False)
        except Exception as exc:
            QMessageBox.critical(self, "Restore failed", str(exc))
