"""Measure portable storage using actual drawings without changing source inputs."""
import argparse
import json
from pathlib import Path
import time

from amr_project import Project, drawing_entries, digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = args.config.resolve()
    raw = source.read_bytes()
    config = json.loads(raw)
    args.output.mkdir(parents=True, exist_ok=True)
    destination = args.output / (source.stem + ".amrproj")
    project = Project()
    started = time.perf_counter()
    project.save(destination, config, base_dir=source.parent, label="Imported for storage verification")
    save_seconds = time.perf_counter() - started
    started = time.perf_counter()
    loaded = Project.open(destination)
    open_seconds = time.perf_counter() - started
    assert loaded.configuration() == project._pack_config(config, source.parent), "Configuration roundtrip differs"
    assert raw == source.read_bytes(), "Source changed during verification"
    report = {"source": str(source), "source_sha256": digest(raw), "source_json_bytes": len(raw),
              "archive_bytes": destination.stat().st_size, "unique_drawing_bytes": sum(map(len, loaded.assets.values())),
              "drawing_references": len(list(drawing_entries(config))), "unique_drawings": len(loaded.assets),
              "save_seconds": round(save_seconds, 3), "open_seconds": round(open_seconds, 3),
              "configuration_roundtrip_matches": True, "source_unchanged": True,
              "limitations": "One local timing sample; open excludes drawing rendering and editor construction."}
    (args.output / "storage.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
