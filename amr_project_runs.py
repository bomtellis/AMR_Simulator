"""Project-bound external runs; prepared inputs are verified again before execution."""
from datetime import datetime, timezone
import argparse
import json
from pathlib import Path
import shutil
import tempfile
import uuid

from amr_project import Project, atomic_write, configuration_bytes, digest
from amr_run_evidence import config_hash, file_hash, software_snapshot

MANIFEST = "run_manifest.json"
OUTPUTS = {"steps_csv": "simulation_steps.csv", "visualiser_csv": "visualiser_steps.csv",
           "failed_tasks_csv": "failed_tasks.csv", "transport_matrix_csv": "transport_matrix.csv",
           "route_lengths_csv": "route_lengths.csv", "charger_estimate_csv": "charger_estimate.csv",
           "scenario_impact_csv": "scenario_impact.csv"}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    atomic_write(path, json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False).encode("utf-8"))


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class PreparedRun:
    """Private draft until checks are accepted. Cancelling removes only this draft."""
    def __init__(self, project, results_root):
        if project.path is None:
            raise ValueError("Save the project before preparing a run")
        self.root = Path(results_root).resolve()
        self.project = project
        self.root.mkdir(parents=True, exist_ok=True)
        self.directory = Path(tempfile.mkdtemp(prefix="run_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_", dir=self.root))
        self.committed = False
        try:
            # Open the saved bytes independently, detecting unsaved/external changes.
            saved = Project.open(project.path)
            if saved._disk_hash != project._disk_hash:
                raise ValueError("Project changed on disk. Reopen or save a new copy before running.")
            revision = saved.revisions[-1]
            self.binding = {"run_key": uuid.uuid4().hex, "project_id": saved.project_id, "revision_id": revision["id"],
                            "revision_config_sha256": revision["config"]}
            portable = saved.configuration()
            self.config = saved.materialize(self.directory / "drawings")
            write_json(self.directory / "project_configuration.json", portable)
            write_json(self.directory / "config.json", self.config)
            self.manifest = {"schema_version": 1, "kind": "amr_project_run", "run_key": self.binding["run_key"],
                             "name": self.directory.name, "status": "prepared", "created_at": timestamp(),
                             "project_binding": self.binding, "config_source": str(saved.path),
                             "config_copy": "config.json", "config_sha256": file_hash(self.directory / "config.json"),
                             "config_object_sha256": config_hash(self.config), "software": software_snapshot(),
                             "outputs": OUTPUTS.copy()}
        except Exception:
            self.discard()
            raise

    def commit(self, report):
        if self.committed:
            raise ValueError("This run has already been prepared")
        frozen = read_json(self.directory / "config.json")
        if (file_hash(self.directory / "config.json") != self.manifest["config_sha256"] or
                config_hash(frozen) != self.manifest["config_object_sha256"] or not report.can_run(frozen)):
            raise ValueError("Inputs or checks changed; review the run again")
        record = report.to_dict()
        write_json(self.directory / "project_checks.json", record)
        self.manifest["project_checks"] = "project_checks.json"
        self.manifest["checks_sha256"] = file_hash(self.directory / "project_checks.json")
        self.manifest["checked_config_sha256"] = report.config_hash
        write_json(self.directory / MANIFEST, self.manifest)
        link_run(self.project, self.directory)
        self.committed = True
        return self.directory

    def discard(self):
        if not self.committed and self.directory.exists():
            target = self.directory.resolve()
            if target.parent != self.root or not target.name.startswith("run_"):
                raise ValueError("Refusing to remove a directory outside this run's results folder")
            shutil.rmtree(target)


def validate_run_inputs(directory, *, require_current_software=False, verify_drawings=True):
    directory = Path(directory).resolve()
    manifest = read_json(directory / MANIFEST)
    if manifest.get("schema_version") != 1 or manifest.get("kind") != "amr_project_run":
        raise ValueError("Unsupported project-run manifest")
    config = read_json(directory / "config.json")
    if file_hash(directory / "config.json") != manifest["config_sha256"] or config_hash(config) != manifest["config_object_sha256"]:
        raise ValueError("Frozen run inputs have changed")
    portable = read_json(directory / "project_configuration.json")
    binding = manifest["project_binding"]
    if manifest.get("run_key") != binding.get("run_key"):
        raise ValueError("Run identity does not match its project binding")
    if digest(configuration_bytes(portable)) != binding["revision_config_sha256"]:
        raise ValueError("Saved revision configuration has changed")
    # Relocate only drawing paths when reading a moved run; content stays bound.
    from amr_project import drawing_entries, asset_hash
    projected = json.loads(json.dumps(config))
    projected_drawings = list(drawing_entries(projected))
    portable_drawings = list(drawing_entries(portable))
    if len(projected_drawings) != len(portable_drawings):
        raise ValueError("Run drawings do not match the project revision")
    for (entry, suffix), (original, original_suffix) in zip(projected_drawings, portable_drawings):
        key = asset_hash(original["filepath"], original_suffix)
        if suffix != original_suffix or Path(entry["filepath"]).name != key + suffix:
            raise ValueError("Run drawing reference does not match the revision")
        if verify_drawings and file_hash(directory / "drawings" / (key + suffix)) != key:
            raise ValueError("Run drawing checksum mismatch")
        entry["filepath"] = original["filepath"]
    if configuration_bytes(projected) != configuration_bytes(portable):
        raise ValueError("Simulation configuration differs from the saved revision")
    checks = read_json(directory / "project_checks.json")
    if file_hash(directory / "project_checks.json") != manifest["checks_sha256"] or checks["config_sha256"] != manifest["checked_config_sha256"]:
        raise ValueError("Recorded project checks have changed")
    from visualiser.project_checks import config_fingerprint
    if checks["config_sha256"] != config_fingerprint(config):
        raise ValueError("Project checks do not apply to the frozen inputs")
    if any(f["severity"] == "error" for f in checks["findings"]):
        raise ValueError("Run inputs contain blocking findings")
    warnings = {f["id"] for f in checks["findings"] if f["severity"] == "warning"}
    if not warnings.issubset(checks["acknowledged_warning_ids"]):
        raise ValueError("Run warnings have not been acknowledged")
    if require_current_software and manifest["software"]["sha256"] != software_snapshot()["sha256"]:
        raise ValueError("Simulator software changed after the run was prepared")
    return manifest, config


def finish_run(directory, exit_code, *, cancelled=False, error=""):
    directory = Path(directory)
    manifest = read_json(directory / MANIFEST)
    manifest.update(status="cancelled" if cancelled else "failed", completed_at=timestamp(), exit_code=exit_code)
    if error:
        manifest["error"] = error
    if exit_code == 0 and not cancelled:
        try:
            validated, _ = validate_run_inputs(directory)
            evidence = read_json(directory / (OUTPUTS["steps_csv"] + ".run.json"))
            if (evidence.get("schema_version") != 1 or evidence.get("project_binding") != manifest["project_binding"] or
                    evidence.get("config_sha256") != manifest["config_object_sha256"] or
                    config_hash(evidence.get("frozen_inputs")) != manifest["config_object_sha256"] or
                    configuration_bytes(evidence.get("frozen_inputs")) != configuration_bytes(read_json(directory / "config.json")) or
                    evidence.get("software", {}).get("sha256") != manifest["software"]["sha256"] or
                    evidence.get("log_sha256") != file_hash(directory / OUTPUTS["steps_csv"]) or
                    evidence.get("run_status") != "finished"):
                raise ValueError("Simulation evidence does not match this prepared run")
            manifest.update(status="complete", simulation_run_id=evidence["run_id"],
                            completed_tasks=len(evidence["summary"]["completed_task_ids"]),
                            failed_tasks=len(evidence["summary"]["failed_task_ids"]))
        except Exception as exc:
            manifest["error"] = str(exc)
    write_json(directory / MANIFEST, manifest)
    return manifest


def inspect_run(directory, project, *, reference=None):
    """Validate relink candidates by identity AND saved revision content, never by name."""
    manifest, _ = validate_run_inputs(directory, verify_drawings=False)
    binding = manifest["project_binding"]
    revision = next((r for r in project.revisions if r["id"] == binding["revision_id"]), None)
    if binding["project_id"] != project.project_id or revision is None or revision["config"] != binding["revision_config_sha256"]:
        raise ValueError("Run does not belong to a revision in this project")
    if reference is not None:
        if (any(binding.get(key) != reference.get(key) for key in ('run_key', 'revision_id', 'revision_config_sha256'))
                or manifest.get('software', {}).get('sha256') != reference.get('software_sha256')):
            raise ValueError("Run folder does not match its saved run/revision/software identity")
    return manifest


def link_run(project, directory, *, expected_run_key=None):
    """Relink only a verified revision; optionally require the selected run ID."""
    manifest = inspect_run(directory, project)
    if expected_run_key is not None and manifest['run_key'] != expected_run_key:
        raise ValueError("Selected folder is a different run; the missing run link was not changed")
    project.remember_run(directory, manifest)
    return manifest


def execute(directory):
    directory = Path(directory).resolve()
    manifest, config = validate_run_inputs(directory, require_current_software=True)
    if manifest["status"] != "prepared":
        raise ValueError("This run has already started; prepare a new run instead of overwriting it")
    manifest.update(status="running", started_at=timestamp())
    write_json(directory / MANIFEST, manifest)
    from simulator import Simulation
    simulation = Simulation(config, verbose=True, verbose_csv_path=str(directory / OUTPUTS["steps_csv"]))
    simulation._evidence_project_binding = manifest["project_binding"]
    simulation.run()
    if software_snapshot()["sha256"] != manifest["software"]["sha256"]:
        raise ValueError("Simulator software changed during execution; results are incomplete")
    simulation.write_verbose_csv()
    simulation.write_visualiser_csv(str(directory / OUTPUTS["visualiser_csv"]))
    for method, key in (("write_failed_tasks_csv", "failed_tasks_csv"), ("write_transport_matrix_csv", "transport_matrix_csv"),
                        ("write_route_lengths_csv", "route_lengths_csv"), ("write_charger_estimate_csv", "charger_estimate_csv"),
                        ("write_scenario_impact_csv", "scenario_impact_csv")):
        getattr(simulation, method)(str(directory / OUTPUTS[key]))
    result = finish_run(directory, 0)
    if result["status"] != "complete":
        raise ValueError(result.get("error", "Run did not finish"))
    print(f"Run complete: {result['completed_tasks']} completed tasks, {result['failed_tasks']} failed tasks", flush=True)
    return simulation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    try:
        execute(args.directory)
    except Exception as exc:
        # An attempted replay must not relabel an already completed run.
        path = args.directory / MANIFEST
        if path.exists() and read_json(path).get("status") in ("prepared", "running"):
            finish_run(args.directory, 1, error=str(exc))
        raise


if __name__ == "__main__":
    main()
