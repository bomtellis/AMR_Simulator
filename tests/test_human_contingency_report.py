import contextlib
import io
from pathlib import Path
import tempfile
import unittest

from pypdf import PdfReader
from amr_project import Project
from amr_project_runs import PreparedRun,execute,read_json
from visualiser.project_checks import check_project
from amr_project_report import generate
from amr_contingency_study import create_study,evaluate_study,load_study
from amr_contingency_report import export_csvs
from tests.test_human_contingency import fixture


class HumanContingencyReportTests(unittest.TestCase):
    def test_embedded_report_and_csv_evidence(self):
        config,settings,_=fixture()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);project=Project();project.save(root/'model.amrproj',config)
            study=root/'study.json';create_study(config,settings,study);state=evaluate_study(study)
            draft=PreparedRun(project,root/'runs');checks=check_project(draft.config,base_path=draft.directory)
            checks.acknowledge_warnings();run=draft.commit(checks)
            with contextlib.redirect_stdout(io.StringIO()):
                execute(run)
                pdf=generate(run,root/'report',['human_contingency'],contingency_study=study)
            text=' '.join(p.extract_text() or '' for p in PdfReader(pdf).pages)
            self.assertIn('Human contingency study',text)
            self.assertIn('dedicated',text);self.assertIn('buffered',text)
            manifest=read_json(root/'report/report_manifest.json')
            self.assertIn('human_contingency',manifest)
            paths=export_csvs(study,root/'csv')
            self.assertEqual(28,len(paths))
            self.assertIn('active_hours',(root/'csv/shared_current_services.csv').read_text(encoding='utf-8-sig'))


if __name__=='__main__':unittest.main()
