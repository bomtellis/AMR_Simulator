import os
from pathlib import Path
import sys
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
root = Path.cwd()
sys.path.append(str(root / '.venv/Lib/site-packages'))
sys.path.insert(0, str(root / 'report'))
from PySide6.QtWidgets import QApplication, QDialog, QCheckBox, QComboBox
from PySide6.QtGui import QFontDatabase, QFont
import amr_report_main
app = QApplication([])
QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
app.setFont(QFont('Segoe UI', 9))
def inspect(dialog):
    dialog.show()
    app.processEvents()
    assert dialog.department_review_format.currentData() == 'both'
    dialog.department_review_only_check.setChecked(True)
    assert dialog.department_review_check.isChecked()
    assert [dialog.department_review_format.itemData(i) for i in range(3)] == ['both', 'pdf', 'xlsx']
    assert dialog.generate_btn.geometry().bottom() <= dialog.height()
    dialog.grab().save(str(root / 'outputs/01a08aff-b34c-7592-a0ce-f0b36922ba20/department_reviews/previews/report_dialog.png'))
    print('Report dialog controls verified:', dialog.size().width(), dialog.size().height())
    dialog.close()
    return 0
QDialog.exec = inspect
amr_report_main.launch_report_generator_dialog()
