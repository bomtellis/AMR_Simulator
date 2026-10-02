"""External run references survive reopen, relocation and failed saves."""
import copy
import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from amr_project import Project
from amr_project_runs import PreparedRun, link_run, inspect_run, read_json, MANIFEST
from tests.test_engineering_reference import reference_config
from visualiser.project_checks import check_project


class PersistentRunLinkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = Project()
        self.config = reference_config()
        self.project.save(self.root / 'model.amrproj', self.config)

    def prepare(self, project=None):
        project = project or self.project
        draft = PreparedRun(project, project.results_root())
        report = check_project(draft.config)
        report.acknowledge_warnings()
        return draft.commit(report)

    def test_new_run_is_remembered_after_reopen_without_configuration_revision(self):
        revisions = copy.deepcopy(self.project.revisions)
        path = self.prepare()
        reopened = Project.open(self.project.path)
        self.assertEqual(revisions, reopened.revisions)
        self.assertEqual(self.config, reopened.configuration())
        self.assertEqual(1, len(reopened.external_results['runs']))
        ref = reopened.external_results['runs'][0]
        self.assertEqual(path, reopened.resolve_results_location(ref['location']))
        self.assertEqual(ref['run_key'], inspect_run(path, reopened, reference=ref)['run_key'])
        self.assertTrue(ref['location']['relative'])
        with zipfile.ZipFile(reopened.path) as archive:
            self.assertEqual({'manifest.json'} | {f'configs/{r["config"]}.json' for r in revisions}, set(archive.namelist()))

    def test_custom_root_survives_reopen(self):
        custom = self.root / 'elsewhere'
        self.project.set_results_root(custom)
        self.assertEqual(custom, Project.open(self.project.path).results_root())
        self.assertEqual(1, len(self.project.revisions))

    def test_absolute_location_fallback_when_relative_path_is_unavailable(self):
        custom = self.root / 'absolute outputs'
        with patch('amr_project.os.path.relpath', side_effect=ValueError('different drives')):
            self.project.set_results_root(custom)
        reopened = Project.open(self.project.path)
        self.assertFalse(reopened.external_results['root']['relative'])
        self.assertEqual(custom, reopened.results_root())

    def test_failed_run_link_save_discards_only_uncommitted_draft(self):
        draft = PreparedRun(self.project, self.project.results_root())
        report = check_project(draft.config); report.acknowledge_warnings()
        before = self.project.path.read_bytes()
        with patch.object(Project, '_write', side_effect=OSError('cannot save link')):
            with self.assertRaises(OSError):
                draft.commit(report)
        draft.discard()
        self.assertFalse(draft.directory.exists())
        self.assertEqual(before, self.project.path.read_bytes())
        self.assertEqual([], self.project.external_results['runs'])

    def test_bundle_move_preserves_relative_root_and_run_link(self):
        self.project.set_results_root(self.root / 'outputs')
        path = self.prepare()
        destination = self.root / 'relocated'
        destination.mkdir()
        moved_project = destination / 'model.amrproj'
        shutil.move(str(self.project.path), moved_project)
        shutil.move(str(self.root / 'outputs'), destination / 'outputs')
        reopened = Project.open(moved_project)
        ref = reopened.external_results['runs'][0]
        self.assertEqual(destination / 'outputs', reopened.results_root())
        moved_run = destination / 'outputs' / path.name
        self.assertEqual(moved_run, reopened.resolve_results_location(ref['location']))
        inspect_run(moved_run, reopened, reference=ref)

    def test_save_as_rebases_existing_links_without_moving_outputs(self):
        self.project.set_results_root(self.root / 'outputs')
        path = self.prepare()
        target = self.root / 'copy'
        target.mkdir()
        self.project.save(target / 'new-name.amrproj', self.config)
        reopened = Project.open(self.project.path)
        self.assertEqual(self.root / 'outputs', reopened.results_root())
        self.assertEqual(path, reopened.resolve_results_location(reopened.external_results['runs'][0]['location']))
        self.assertTrue((path / MANIFEST).is_file())

    def test_relink_replaces_location_for_same_run_and_is_idempotent(self):
        path = self.prepare()
        key = self.project.external_results['runs'][0]['run_key']
        moved = self.root / 'moved run'
        shutil.move(str(path), moved)
        link_run(self.project, moved, expected_run_key=key)
        original = self.project.path.read_bytes()
        link_run(self.project, moved, expected_run_key=key)
        self.assertEqual(original, self.project.path.read_bytes())
        reopened = Project.open(self.project.path)
        self.assertEqual(1, len(reopened.external_results['runs']))
        self.assertEqual(moved, reopened.resolve_results_location(reopened.external_results['runs'][0]['location']))

    def test_selected_run_cannot_be_replaced_by_another_valid_project_run(self):
        first = self.prepare()
        first_ref = copy.deepcopy(self.project.external_results['runs'][0])
        second = self.prepare()
        original = self.project.path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'different run'):
            link_run(self.project, second, expected_run_key=first_ref['run_key'])
        self.assertEqual(original, self.project.path.read_bytes())
        with self.assertRaisesRegex(ValueError, 'saved run/revision/software'):
            inspect_run(second, self.project, reference=first_ref)
        inspect_run(first, self.project, reference=first_ref)

    def test_software_identity_mismatch_cannot_overwrite_existing_link(self):
        path = self.prepare()
        manifest = read_json(path / MANIFEST)
        manifest['software']['sha256'] = '0' * 64
        (path / MANIFEST).write_text(json.dumps(manifest))
        original = self.project.path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'revision/software'):
            link_run(self.project, path)
        self.assertEqual(original, self.project.path.read_bytes())

    def test_failed_atomic_metadata_save_preserves_disk_and_memory(self):
        path = self.prepare()
        original = self.project.path.read_bytes()
        settings = copy.deepcopy(self.project.external_results)
        with patch('amr_project.os.replace', side_effect=OSError('disk unavailable')):
            with self.assertRaises(OSError):
                self.project.set_results_root(self.root / 'another')
        self.assertEqual(original, self.project.path.read_bytes())
        self.assertEqual(settings, self.project.external_results)
        self.assertTrue((path / MANIFEST).is_file())

    def test_external_project_change_is_not_overwritten_by_linking(self):
        path = self.prepare()
        other = Project.open(self.project.path)
        other.set_results_root(self.root / 'changed elsewhere')
        original = other.path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'changed on disk'):
            self.project.set_results_root(self.root / 'another')
        self.assertEqual(original, other.path.read_bytes())
        self.assertTrue((path / MANIFEST).is_file())

    def test_revision_restore_keeps_run_references_and_original_binding(self):
        path = self.prepare()
        first = self.project.revisions[0]['id']
        changed = copy.deepcopy(self.config)
        changed['amrs'][0]['speed_m_per_sec'] = 3
        self.project.save(self.project.path, changed)
        self.project.restore(first, changed)
        reopened = Project.open(self.project.path)
        self.assertEqual(first, reopened.external_results['runs'][0]['revision_id'])
        inspect_run(path, reopened, reference=reopened.external_results['runs'][0])

    def test_old_archive_without_run_metadata_opens_without_rewriting(self):
        path = self.project.path
        with zipfile.ZipFile(path) as archive:
            entries = {name: archive.read(name) for name in archive.namelist()}
        manifest = json.loads(entries['manifest.json'])
        manifest.pop('external_results')
        entries['manifest.json'] = json.dumps(manifest).encode()
        with zipfile.ZipFile(path, 'w') as archive:
            for name, data in entries.items():
                archive.writestr(name, data)
        before = path.read_bytes()
        reopened = Project.open(path)
        self.assertEqual([], reopened.external_results['runs'])
        self.assertEqual(before, path.read_bytes())

    def test_invalid_metadata_does_not_get_saved(self):
        self.prepare()
        for mutate in (
            lambda data: data.update(version=2),
            lambda data: data['runs'].append(copy.deepcopy(data['runs'][0])),
            lambda data: data['runs'][0].update(revision_id='not-a-revision'),
            lambda data: data['runs'][0].update(software_sha256='bad'),
            lambda data: data.update(root={'relative': True, 'path': 'C:/absolute'}),
        ):
            with self.subTest(mutate=mutate):
                data = copy.deepcopy(self.project.external_results)
                mutate(data)
                before = self.project.path.read_bytes()
                with self.assertRaises(ValueError):
                    self.project._save_external_results(data)
                self.assertEqual(before, self.project.path.read_bytes())


os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'visualiser'))
from PySide6.QtWidgets import QApplication, QMessageBox
from app import AMRGraphEditor
from models import JsonStore
from project_runs_panel import ProjectRunsPanel
from amr_recovery import RecoveryStore


class PersistentRunLinkUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_reopen_missing_link_relink_and_unsaved_edits_remain_independent(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            editor = AMRGraphEditor()
            editor._recovery_store = RecoveryStore(root / 'recovery')
            try:
                editor.store = JsonStore(reference_config())
                editor.project = Project()
                editor.project.save(root / 'model.amrproj', editor.store.data)
                editor.current_json_path = str(editor.project.path)
                editor._mark_saved()
                draft = PreparedRun(editor.project, editor.project.results_root())
                checks = check_project(draft.config); checks.acknowledge_warnings()
                path = draft.commit(checks)
                moved = root / 'moved'
                shutil.move(str(path), moved)
                editor.project = Project.open(editor.project.path)
                panel = ProjectRunsPanel(editor)
                self.assertEqual(1, panel.runs.count())
                self.assertIn('missing or unavailable', panel.runs.item(0).text())
                panel.runs.setCurrentRow(0)
                self.assertIn('run file is missing', panel.details.toPlainText())
                self.assertIn('Locate moved run', panel.details.toPlainText())
                editor.store.data['amrs'][0]['speed_m_per_sec'] = 99
                self.assertTrue(editor.has_unsaved_changes())
                panel.link_run(moved)
                self.assertTrue(editor.has_unsaved_changes())
                self.assertEqual(2, Project.open(editor.project.path).configuration()['amrs'][0]['speed_m_per_sec'])
                self.assertEqual(editor.project._disk_hash, editor._source_disk_hash)
                reopened_panel = ProjectRunsPanel(editor)
                self.assertEqual(1, reopened_panel.runs.count())
                self.assertEqual(moved, reopened_panel.run_paths[0])
            finally:
                with patch.object(editor, '_confirm_unsaved_changes', return_value=True):
                    editor.close()


if __name__ == '__main__':
    unittest.main()
