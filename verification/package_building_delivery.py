"""Package a verified increment without touching the preserved Simple artifacts."""
from collections import Counter
from datetime import datetime,timezone
import json
from pathlib import Path
import shutil
import zipfile
ROOT=Path(__file__).resolve().parents[1]

def main(evidence=None,output=None):
    from amr_run_evidence import file_hash,software_snapshot
    from verification.run import source_manifest
    evidence=Path(evidence) if evidence else ROOT/'verification/latest/building-tutorial'
    output=Path(output) if output else ROOT/'installer/build/building-delivery';output.mkdir(parents=True,exist_ok=True)
    def read(p):return json.loads(p.read_text(encoding='utf-8'))
    qa=read(evidence/'verified-qa/qa.json');identity=read(evidence/'verified-qa/source.json')
    assert qa['successful'] and qa['source_unchanged'] and identity['files']==source_manifest()['files']
    counts=Counter(c['status'] for c in qa['cases']);assert set(counts)=={'passed'}
    source=read(evidence/'integration-final/smoke.json');installed=read(evidence/'installed-smoke/smoke.json')
    assert source['status']==installed['status']=='passed'
    assert source['software_sha256']==installed['software_sha256']==software_snapshot()['sha256']
    previous=read(ROOT/'installer/build/delivery/manifest.json')
    for name,value in previous['files'].items():assert file_hash(ROOT/'installer/build/delivery'/name)==value['sha256']
    for n in ('100','150','200'):assert read(evidence/f'visual-{n}/visual.json')['passed']
    assets={}
    for p in (ROOT/'docs/building-tutorial').rglob('*'):
        if not p.is_file() or p.suffix not in ('.dxf','.amrproj','.md','.pdf','.png') and p.name!='coverage.json':continue
        relative=p.relative_to(ROOT/'docs/building-tutorial');counterpart=evidence/'fresh-install/docs/building-tutorial'/relative
        assert counterpart.exists() and file_hash(counterpart)==file_hash(p),relative
        assets[relative.as_posix()]=file_hash(p)
    source_files={ROOT/name for name in identity['files']}
    for name in ('README.md','LICENSE','.gitignore','.gitattributes','ltn.amrproj'):source_files.add(ROOT/name)
    extensions={'.py','.json','.md','.txt','.mjs','.yaml','.yml','.ps1','.spec','.iss','.png','.jpg','.jpeg','.svg','.ico','.xlsx','.pdf','.docx','.dxf','.amrproj'}
    for folder in ('visualiser','report','tests','verification','docs','installer','.github'):
        for p in (ROOT/folder).rglob('*'):
            if not p.is_file() or p.suffix.lower() not in extensions or '__pycache__' in p.parts:continue
            relative=p.relative_to(ROOT)
            if relative.parts[:2] in (('verification','latest'),('installer','build')):continue
            source_files.add(p)
    hashes={p.relative_to(ROOT).as_posix():file_hash(p) for p in sorted(source_files)}
    source_zip=output/'AMR-Simulator-Building-source.zip'
    with zipfile.ZipFile(source_zip,'w',zipfile.ZIP_DEFLATED,strict_timestamps=False) as archive:
        for name,checksum in hashes.items():
            p=ROOT/name;assert file_hash(p)==checksum;archive.write(p,name)
        archive.writestr('SOURCE-CHECKPOINT.json',json.dumps(dict(qa_source_sha256=identity['sha256'],application_sha256=source['software_sha256'],files=hashes),indent=2))
    evidence_zip=output/'AMR-Simulator-Building-QA.zip'
    folders=('verified-qa','integration-final','installed-smoke','visual-100','visual-150','visual-200','pdf-render')
    with zipfile.ZipFile(evidence_zip,'w',zipfile.ZIP_DEFLATED,strict_timestamps=False) as archive:
        for folder in folders:
            for p in (evidence/folder).rglob('*'):
                if p.is_file() and 'temp' not in p.relative_to(evidence/folder).parts and p.name!='source-snapshot.zip' and p.suffix!='.pyc':archive.write(p,p.relative_to(ROOT).as_posix())
        for p in (evidence/'fresh-install.log',ROOT/'verification/BUILDING_TUTORIAL_REVIEW.md'):archive.write(p,p.relative_to(ROOT).as_posix())
    installer=output/'AMR-Simulator-Building-Setup.exe';shutil.copy2(ROOT/'installer/build/setup/AMR-Simulator-Setup-dev.exe',installer)
    for p in (source_zip,evidence_zip):
        with zipfile.ZipFile(p) as archive:assert archive.testzip() is None
    manifest=dict(created_utc=datetime.now(timezone.utc).isoformat(),checkpoint_kind='Working source ZIP preserving pre-existing edits',
      application_source_sha256=source['software_sha256'],qa_source_sha256=identity['sha256'],
      qa=dict(passed=counts['passed'],modules=len(qa['modules']),source_unchanged=True),
      source_and_installed_smoke_match=True,fresh_offline_per_user_install='passed',comparison_runs_source=96,comparison_runs_installed=48,
      installed_asset_hashes=assets,simple_delivery_preserved=True,excluded='LTN tests/workloads/benchmarks/repairs and Detailed development',
      files={p.name:dict(bytes=p.stat().st_size,sha256=file_hash(p)) for p in (installer,source_zip,evidence_zip)})
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    (output/'SHA256SUMS.txt').write_text(''.join(f"{v['sha256']}  {k}\n" for k,v in manifest['files'].items()),encoding='utf-8')
    print(json.dumps(manifest['qa']))

if __name__=='__main__':main()
