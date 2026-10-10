import csv
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "visualiser"))

from PySide6.QtWidgets import QApplication, QMessageBox
from dialogs import TaskGenerationSettingsDialog
from task_generation_export import configuration_rows, write_configuration_csv, write_configuration_pdf


class ConfigurationExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.departments = [{"id": "WARD1", "name": "Ward, One", "bed_count": 0, "waste_streams": [{"name": "Clinical", "enabled": False}]}]
        self.config = {"enabled": True, "categories": {"linen": {
            "display_name": "Linen & towels", "enabled": False,
            "department_groups": [
                {"id": "GROUP-1", "departments": ["WARD1"], "payload": {"scheduled_times": ["08:00", "12:00"]}},
                {"id": "GROUP-2", "departments": ["WARD1"], "payload": {"notes": "Second run\nwith, punctuation"}},
            ],
            "departments": {"WARD1": {"enabled": True, "priority": 42}},
        }}}

    def test_category_report_and_csv_round_trip(self):
        rows = configuration_rows(self.config, self.departments)
        self.assertTrue(any(r[1] == "Service group 2" and r[3] == "Notes" for r in rows))
        self.assertTrue(any(r[3:] == ("Scheduled times", "08:00, 12:00") for r in rows))
        self.assertTrue(any(r[2] == "Ward, One" for r in rows))
        exported = str(rows)
        for internal in ("GROUP-1", "WARD1", "department_groups", "scheduled_times", "waste_streams", "bed_count"):
            self.assertNotIn(internal, exported)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "export.csv"
            write_configuration_csv(path, rows)
            with path.open(encoding="utf-8-sig", newline="") as stream:
                self.assertEqual(list(csv.reader(stream))[1:], [list(row) for row in rows])

    def test_pdf_with_long_values_and_multiple_pages(self):
        from pypdf import PdfReader
        self.config["categories"]["linen"]["notes"] = "Long <note> & detail " * 1800
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "export.pdf"
            write_configuration_pdf(path, configuration_rows(self.config, self.departments))
            reader = PdfReader(path)
            text = "\n".join(page.extract_text() for page in reader.pages)
            self.assertGreater(len(reader.pages), 1)
            for expected in ("Service group 1", "Service group 2", "Ward, One", "12:00"):
                self.assertIn(expected, text)
            self.assertNotIn("GROUP-1", text)

    def test_dialog_export_includes_live_settings_without_saving(self):
        on_save = Mock()
        dialog = TaskGenerationSettingsDialog(None, self.config, [], [], [], self.departments, on_save)
        try:
            dialog.global_enabled.setChecked(False)
            dialog.current_key = "linen"
            dialog.current_department_id = "WARD1"
            dialog._load_category("linen")
            dialog.priority_edit.setText("97")
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "export"
                with patch("dialogs.QFileDialog.getSaveFileName", return_value=(str(path), "CSV files (*.csv)")), patch("dialogs.QMessageBox.information"), patch("dialogs.QMessageBox.critical") as error:
                    dialog.export_configuration_button.click()
                    error.assert_not_called()
                with path.with_suffix(".csv").open(encoding="utf-8-sig", newline="") as stream:
                    rows = list(csv.DictReader(stream))
                self.assertTrue(any(r["Setting"] == "Automatic task generation" and r["Details"] == "Disabled" for r in rows))
                self.assertTrue(any(r["Setting"] == "Priority" and r["Details"] == "97" for r in rows))
                on_save.assert_not_called()
        finally:
            dialog.close()

    def test_cancel_does_not_collect_or_save(self):
        dialog = TaskGenerationSettingsDialog(None, self.config, [], [], [], self.departments, Mock())
        try:
            with patch("dialogs.QFileDialog.getSaveFileName", return_value=("", "")), patch.object(dialog, "_collect_configuration") as collect:
                dialog.export_configuration()
                collect.assert_not_called()
        finally:
            dialog.close()

    def test_return_timing_uses_group_settings_and_category_defaults(self):
        category = self.config["categories"]["linen"]
        category.update(return_enabled=True, return_delay_minutes=45)
        category["department_groups"][0]["payload"]["return_delay_minutes"] = 12.5
        rows = configuration_rows(self.config, self.departments)
        timings = {r[1]: r[4] for r in rows if r[3] == "Return trip timing"}
        self.assertEqual(timings, {
            "Service group 1": "Configured return delay: 12.5 minutes",
            "Service group 2": "Configured return delay: 45 minutes",
        })
        category["department_groups"][0]["payload"].update(return_enabled=False)
        category["return_delay_minutes"] = 0
        rows = configuration_rows(self.config, self.departments)
        self.assertEqual([r[4] for r in rows if r[3] == "Return trip timing"],
                         ["Configured return delay: 0 minutes"])
        del category["return_delay_minutes"]
        self.assertFalse(any(r[3] == "Return trip timing" for r in configuration_rows(self.config, self.departments)))

    def test_shared_groups_show_names_once_and_keep_separate_runs(self):
        category = self.config["categories"]["linen"]
        self.departments.append({"id": "WARD2", "name": "Ward Two"})
        category["department_groups"][0]["departments"].append("WARD2")
        category["departments"]["WARD2"] = {"priority": 999}
        rows = configuration_rows(self.config, self.departments)
        times = [r for r in rows if r[3] == "Scheduled times"]
        self.assertEqual(len(times), 1)
        self.assertEqual(times[0][2], "Ward, One, Ward Two")
        self.assertFalse(any(r[3:] == ("Priority", "999") for r in rows))
        self.assertTrue(any(r[1] == "Service group 2" for r in rows))

    def test_hide_inactive_settings_and_keep_waste_under_its_category(self):
        self.config["categories"]["waste"] = {
            "display_name": "Waste", "departments": {"WARD1": {"enabled": True}},
        }
        self.config["categories"]["linen"].update({
            "requires_staff": False, "staff_initial_count": 500,
            "return_enabled": False, "return_payload": "unused trolley",
            "timeframe_start": "01:23", "threshold_volume_m3": 900,
        })
        rows = configuration_rows(self.config, self.departments)
        self.assertTrue(any(r[0] == "Waste" and r[3] == "Clinical" and "Disabled" in r[4] for r in rows))
        linen = str([r for r in rows if r[0] == "Linen & towels"])
        for hidden in ("Clinical", "500", "unused trolley", "01:23", "900"):
            self.assertNotIn(hidden, linen)

    def test_pdf_filter_controls_format_and_write_errors_are_reported(self):
        dialog = TaskGenerationSettingsDialog(None, self.config, [], [], [], self.departments, Mock())
        try:
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "configuration.csv"
                with patch("dialogs.QFileDialog.getSaveFileName", return_value=(str(path), "PDF documents (*.pdf)")), patch("dialogs.QMessageBox.information"), patch("dialogs.QMessageBox.critical") as error:
                    dialog.export_configuration()
                    error.assert_not_called()
                    self.assertTrue(path.with_suffix(".pdf").read_bytes().startswith(b"%PDF"))
                    self.assertFalse(path.exists())
                with patch("dialogs.QFileDialog.getSaveFileName", return_value=(str(path), "CSV files (*.csv)")), patch("task_generation_export.write_configuration_csv", side_effect=PermissionError("File is open")), patch("dialogs.QMessageBox.critical") as error:
                    dialog.export_configuration()
                    error.assert_called_once()
        finally:
            dialog.close()


if __name__ == "__main__":
    unittest.main()
