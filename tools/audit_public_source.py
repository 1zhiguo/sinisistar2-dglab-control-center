"""Verify exact publish payload without network access or reading credentials."""
from pathlib import Path
from collections import Counter
import hashlib,json,re

ROOT=Path(__file__).resolve().parents[1]/'public_repo/sinisistar2-source'
manifest=json.loads((ROOT/'PUBLIC_SOURCE_MANIFEST.json').read_text(encoding='utf-8'))
files=manifest['files'];issues=[]
for name,expected in files.items():
    path=ROOT/name
    if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:issues.append((name,'hash mismatch'))
    if any(p in {'.analysis','artifacts','.config','.git','SiNiSistar2_v1_3_1','monster-previews'} for p in path.relative_to(ROOT).parts):issues.append((name,'excluded directory'))
    if path.suffix.lower() in {'.dll','.exe','.zip','.log','.db','.sqlite','.pyc'}:issues.append((name,'excluded binary/runtime/log'))
    if path.suffix in {'.py','.js','.json','.mjs','.md','.qml','.ps1','.cmd','.cs'}:
        source=path.read_text(encoding='utf-8-sig')
        # Only report filenames; never print matched values.
        if re.search(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{30,}|AIza[0-9A-Za-z_-]{30,}',source):issues.append((name,'credential pattern'))
actual={p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.is_file() and not any(part in {'.git','__pycache__','artifacts'} for part in p.relative_to(ROOT).parts)}
if actual!=set(files)|{'PUBLIC_SOURCE_MANIFEST.json'}:issues.append(('manifest','unlisted files'))
report={'passed':not issues,'repository':'1zhiguo/sinisistar2-dglab-control-center','files':len(files),'bytes':sum((ROOT/p).stat().st_size for p in files),'extensions':dict(Counter(Path(p).suffix for p in files)),'excluded':['game installation','game-extracted PNG previews and sprites','runtime ZIPs and DLLs','settings and telemetry','credentials and logs'],'website_images':'five native software screenshots explicitly requested by the user, plus a product icon','issues':issues}
print(json.dumps(report,ensure_ascii=False))
raise SystemExit(0 if not issues else 1)
