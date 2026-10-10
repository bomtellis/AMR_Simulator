"""Inventory all declared GUI commands, dialog classes and labelled controls."""
import ast
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def topic(text):
    t=text.lower()
    rules=[('Detailed and historical settings',('detailed','motion','kinematic')),
      ('Main chapters 1, 2',('tutorial','bubble','course tools','restart chapter')),
      ('Appearance and keyboard',('theme','font','appearance','focus canvas','text size','zoom')),
      ('Report options',('report','pdf','export','heatmap')),
      ('Relinking and evidence',('relink','evidence','investig','playback','timeline','review')),
      ('Recovery and run outcomes',('recovery','cancel','simulate','run','check','save','project')),
      ('Advanced demand',('generation','demand','task','category','scope','recurr')),
      ('Staff and people',('staff','people','shift','schedule','person')),
      ('Inventory and exchanges',('inventory','payload','bay','stock','exchange','wash','charg')),
      ('Batching and route restrictions',('batch','route','restriction','profile')),
      ('Main chapters 5, 6, 10, 11',('lift','planning','proposal','shaft')),
      ('Main chapters 1, 2, 3',('building','floor','door','corridor','snap','properties'))]
    return next((name for name,words in rules if any(w in t for w in words)),'Drawing tools and layers')

def build(output):
    rows=[]
    constructors={'QAction','QPushButton','QToolButton','QCheckBox','QLabel','addAction','addMenu','addTab','addRow','addItem','setWindowTitle','setToolTip','setAccessibleName','action','command'}
    for path in sorted((ROOT/'visualiser').glob('*.py')):
        tree=ast.parse(path.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            kind=None;text=None
            if isinstance(node,ast.ClassDef) and any(isinstance(b,ast.Name) and b.id in ('QDialog','QWidget','QMainWindow') for b in node.bases):kind='Workspace / dialog';text=node.name
            if isinstance(node,ast.Call):
                name=node.func.id if isinstance(node.func,ast.Name) else node.func.attr if isinstance(node.func,ast.Attribute) else ''
                if name in constructors:
                    values=[a.value for a in node.args if isinstance(a,ast.Constant) and isinstance(a.value,str)]
                    if values:kind=name;text=values[0]
            if kind and text:
                rows.append(dict(file=path.relative_to(ROOT).as_posix(),line=node.lineno,kind=kind,interface=text,lesson=topic(text)))
    output.mkdir(parents=True,exist_ok=True)
    (output/'coverage.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
    intro='# Complete interface coverage inventory\n\nEvery declared workspace, dialog, active command and labelled control is indexed below. '
    intro+='Runtime-generated objects (floors, locations, payloads, run rows and layer names) inherit the lesson of their containing control. '
    intro+='Menu actions built from data tables inherit their workspace lesson; use the contextual reference in that workspace. '
    intro+='Legacy standalone windows are included for compatibility. This inventory does not enable Detailed simulation or LTN testing.\n\n'
    intro+='For any field: use its visible label and tooltip, retain units, inspect validation feedback, and use Save/Cancel to commit or discard the whole dialog. '
    intro+='For list editors: select an item before Edit/Delete, use Add for a new object, and verify changes with Project checks and Demand preview. '
    intro+='For canvas commands: Escape cancels an unfinished gesture; selection alone leaves Properties collapsed; Undo/Redo verify committed edits. '
    intro+='For frozen evidence: select a registered run, investigate linked records, and keep original inputs when comparing variants. '
    intro+='Each optional lesson is available from Course tools > Additional lessons.\n\n'
    intro+='| Interface | Kind | Lesson / contextual reference | Source |\n|---|---|---|---|\n'
    for r in rows:
        values=[r['interface'].replace('|','/').replace('\n',' '),r['kind'],r['lesson'],f"{r['file']}:{r['line']}"]
        intro+='| '+' | '.join(values)+' |\n'
    (output/'COVERAGE.md').write_text(intro,encoding='utf-8')
    return len(rows)

if __name__=='__main__':print(build(ROOT/'docs/building-tutorial'))
