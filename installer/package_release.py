"""Package a locally verified Windows build for manual GitHub release upload."""
from pathlib import Path
import argparse
import hashlib
import json
import platform
import re
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def package(version):
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?', version):
        raise ValueError('Use a version such as 0.1.0 or 0.1.0-rc.1.')
    build = ROOT / 'installer/build/releases' / version
    dist = build / 'dist/AMRSimulator'
    small = json.loads((build / 'smoke-small/smoke.json').read_text())
    course = json.loads((build / 'smoke-building/smoke.json').read_text())
    metadata = json.loads((dist / 'release-info.json').read_text())
    if small.get('status') != 'passed' or course.get('status') != 'passed':
        raise RuntimeError('Both freshly installed smoke checks must pass before packaging.')
    if not (build / 'installed').is_dir() or metadata['version'] != version:
        raise RuntimeError('Fresh installation or version information is missing.')
    software = metadata['software']['sha256']
    from amr_run_evidence import software_snapshot
    if software_snapshot()['sha256'] != software:
        raise RuntimeError('Application source changed after building; rebuild and reverify.')
    if any(check['software_sha256'] != software for check in (small, course)):
        raise RuntimeError('Installed and packaged application source fingerprints differ.')
    for path in dist.rglob('*'):
        if path.is_file():
            installed_path = build / 'installed' / path.relative_to(dist)
            if not installed_path.is_file() or digest(path) != digest(installed_path):
                raise RuntimeError(f'Installed payload differs: {path.relative_to(dist)}')
    setup = build / f'setup/AMR-Simulator-{version}-Windows-x64-Setup.exe'
    if not setup.is_file():
        raise FileNotFoundError(setup)
    source_checks = (build / 'source-checks.log').read_text(encoding='utf-8')
    match = re.search(r'Ran (\d+) tests in [\d.]+s\s+OK\s*$', source_checks)
    if not match:
        raise RuntimeError('Passing targeted source test evidence is missing.')
    assets = build / 'assets'
    assets.mkdir(exist_ok=True)
    shutil.copy2(setup, assets / setup.name)
    portable = assets / f'AMR-Simulator-{version}-Windows-x64-Portable.zip'
    with zipfile.ZipFile(portable, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(dist.rglob('*')):
            if path.is_file():
                archive.write(path, Path('AMRSimulator') / path.relative_to(dist))
    source = assets / f'AMR-Simulator-{version}-Source.zip'
    names = subprocess.check_output(['git', 'ls-files', '-z', '--cached', '--others',
                                     '--exclude-standard'], cwd=ROOT).decode().split('\0')
    source_files = {}
    with zipfile.ZipFile(source, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(set(names) - {''}):
            path = ROOT / name
            if path.is_file():
                source_files[name] = digest(path)
                archive.write(path, Path(f'AMR-Simulator-{version}') / name)
    for name, expected in metadata['software']['files'].items():
        if source_files.get(name) != expected:
            raise RuntimeError(f'Release source does not match the built application: {name}')
    for path in (portable, source):
        with zipfile.ZipFile(path) as archive:
            bad_file = archive.testzip()
            if bad_file:
                raise RuntimeError(f'Corrupt archive entry: {bad_file}')
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    status = subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).splitlines()
    manifest = dict(version=version, tag=version, base_commit=commit,
                    pending_source_changes=status, platform=platform.platform(),
                    python=sys.version, software_sha256=software, signed=False,
                    ltn_included=metadata['ltn_included'], source_files=source_files,
                    validation=dict(source_tests=dict(passed=int(match[1]),
                                                      log_sha256=digest(build / 'source-checks.log')),
                                    small_map=small, building_course=course),
                    files={p.name: dict(bytes=p.stat().st_size, sha256=digest(p))
                           for p in (assets / setup.name, portable, source)})
    (assets / 'release-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    shutil.copy2(ROOT / f'installer/RELEASE-{version}.md', assets / 'RELEASE-NOTES.md')
    checksum_files = sorted(p for p in assets.iterdir() if p.is_file() and p.name != 'SHA256SUMS.txt')
    (assets / 'SHA256SUMS.txt').write_text(
        ''.join(f'{digest(path)}  {path.name}\n' for path in checksum_files), encoding='utf-8')
    print(assets)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', required=True)
    package(parser.parse_args().version)
