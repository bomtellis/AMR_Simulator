"""Quick utilisation review; evidence loading stays off the GUI thread."""
from threading import Event

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot, Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QTabWidget,
                              QDialogButtonBox, QProgressBar, QTableWidgetItem)

from amr_run_utilisation import load_memory_utilisation
from visualiser.demand_preview_panel import DemandPreviewPanel


class UtilisationSignals(QObject):
    finished = Signal(object, str)


class UtilisationJob(QRunnable):
    def __init__(self, run):
        super().__init__()
        self.source = run
        self.cancelled = Event()
        self.signals = UtilisationSignals()

    def run(self):
        result, error = None, ''
        try:
            result = load_memory_utilisation(self.source, cancel=self.cancelled.is_set)
        except Exception as exc:
            error = str(exc)
        finally:
            self.source = None
        self.signals.finished.emit(result, error)


class RunUtilisationDialog(QDialog):
    def __init__(self, run, parent=None, *, cached=None):
        super().__init__(parent)
        self.setWindowTitle('AMR and lift utilisation')
        self.resize(760, 520)
        self.result_data = None
        self.job = None
        self.closed = False
        layout = QVBoxLayout(self)
        self.source = QLabel(f'{run.name} · In memory · Completed')
        self.source.setWordWrap(True)
        layout.addWidget(self.source)
        self.summary = QLabel('Calculating utilisation from the recorded run…')
        self.summary.setWordWrap(True)
        self.summary.setAccessibleName('Utilisation summary')
        self.summary.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        layout.addWidget(self.summary)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setAccessibleName('Loading utilisation')
        layout.addWidget(self.progress)
        self.tabs = QTabWidget()
        self.tables = {}
        for key, title in (('amrs', 'AMRs'), ('lifts', 'Lifts')):
            table = DemandPreviewPanel.table([title[:-1] if key == 'lifts' else 'AMR',
                                              'Utilisation (%)', 'Busy (min)', 'Idle (min)'])
            table.setAccessibleName(title + ' utilisation')
            self.tables[key] = table
            self.tabs.addTab(table, title)
        layout.addWidget(self.tabs, 1)
        self.basis = QLabel(
            'Busy time includes recorded movement, handling, waiting and charging for AMRs, '
            'and transfers plus empty repositioning for lifts. Overlapping activity counts once. '
            'The window covers the configured simulation period and any work completed after it. '
            'Unused resources are included at 0%.')
        self.basis.setWordWrap(True)
        layout.addWidget(self.basis)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        if cached is not None:
            self.loaded(cached, '')
        else:
            self.job = UtilisationJob(run)
            self.job.signals.finished.connect(self.loaded)
            QThreadPool.globalInstance().start(self.job)

    def done(self, code):
        self.closed = True
        if self.job is not None:
            self.job.cancelled.set()
        super().done(code)

    @Slot(object, str)
    def loaded(self, result, error):
        self.job = None
        if self.closed:
            return
        self.progress.hide()
        if result is None:
            self.summary.setText('Utilisation could not be loaded: ' + error)
            return
        self.result_data = result
        horizon = result['horizon_seconds']
        averages = []
        for index, (key, title) in enumerate((('amrs', 'AMRs'), ('lifts', 'Lifts'))):
            table, rows = self.tables[key], result[key]
            table.setSortingEnabled(False)
            table.setRowCount(len(rows))
            for i, row in enumerate(rows):
                table.setItem(i, 0, QTableWidgetItem(row['id']))
                for j, value in enumerate((row['utilisation_pct'], row['busy_seconds'] / 60,
                                           row['idle_seconds'] / 60), 1):
                    item = QTableWidgetItem('—')
                    if value is not None:
                        item.setData(Qt.DisplayRole, round(value, 2))
                    table.setItem(i, j, item)
            table.setSortingEnabled(True)
            table.sortItems(1, Qt.DescendingOrder)
            self.tabs.setTabText(index, f'{title} ({len(rows)})')
            if not rows:
                averages.append(f'No {title.lower()} in this run')
            elif horizon > 0:
                average = sum(row['busy_seconds'] for row in rows) / (len(rows) * horizon) * 100
                averages.append(f'{title}: {average:.1f}% average')
            else:
                averages.append(f'{title}: no elapsed time')
        self.summary.setText(f'Run window: 0–{horizon:,.3f} s ({horizon / 3600:,.2f} h)\n'
                             + ' · '.join(averages))
