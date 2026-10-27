"""Development-only complete bundle audit, including enemy prefab references.

Reads local game packages. One decrypted temporary bundle exists at a time.
Never starts the game or devices, modifies game files, or writes a game save.
"""
from pathlib import Path
import collections,gzip,hashlib,json,os,re,struct,subprocess,sys,tempfile,time,traceback,gc
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.analysis/unitypy'))
import UnityPy
OUT=ROOT/'artifacts/research/monster-audit'
GAME=ROOT/'SiNiSistar2_v1_3_1/WIN/SiNiSistar2_Data/StreamingAssets/game_bin'

def ref(pointer):
    if not pointer:return None
    asset=pointer.assetsfile
    name=asset.name if pointer.m_FileID==0 else asset.externals[pointer.m_FileID-1].path.rsplit('/',1)[-1]
    return [name,pointer.m_PathID]

def scan(bundle,env,enemies):
    result=dict(bundle=bundle,assets=[],sprites=[],enemies=[],errors=[])
    objects=list(env.objects)
    for asset in env.assets:
        result['assets'].append(dict(name=asset.name,object_count=len(asset.objects)))
    for obj in objects:
        if obj.type.name=='Sprite':
            s=obj.read();result['sprites'].append(dict(asset=obj.assets_file.name,id=obj.path_id,name=s.m_Name,rect=[s.m_RD.textureRect.width,s.m_RD.textureRect.height]))
    def collect(root):
        records=[];clips=set();visited=set()
        def walk(transform,trail,active):
            identity=(transform.object_reader.assets_file.name,transform.object_reader.path_id)
            if identity in visited:return
            visited.add(identity);go=transform.m_GameObject.read();active=active and bool(go.m_IsActive)
            trail=trail+'/'+go.m_Name
            for entry in go.m_Component:
                component=entry.component.deref()
                if component.type.name=='SpriteRenderer':
                    renderer=component.read()
                    if renderer.m_Sprite:records.append(dict(sprite=ref(renderer.m_Sprite),node=trail,active=active and bool(renderer.m_Enabled)))
                elif component.type.name=='Animator':
                    animator=component.read()
                    if animator.m_Controller:
                        try:
                            controller=animator.m_Controller.read()
                            for clip in getattr(controller,'m_AnimationClips',[]):
                                if clip:clips.add(tuple(ref(clip)))
                        except Exception:pass
            for child in transform.m_Children:walk(child.read(),trail,active)
        for entry in root.m_Component:
            component=entry.component.deref()
            if component.type.name=='Transform':walk(component.read(),'',True)
        return records,[list(x) for x in sorted(clips)]
    for obj in objects:
        if obj.type.name!='MonoBehaviour':continue
        try:
            mb=obj.read(check_read=False);script=mb.m_Script.read()
            if script.m_ClassName not in enemies:continue
            go=mb.m_GameObject.read();renderers,clips=collect(go)
            result['enemies'].append(dict(class_name=script.m_ClassName,namespace=script.m_Namespace,asset=obj.assets_file.name,component_id=obj.path_id,go_id=mb.m_GameObject.m_PathID,go_name=go.m_Name,renderers=renderers,clips=clips))
        except Exception as exc:
            result['errors'].append(dict(type=obj.type.name,id=obj.path_id,error=type(exc).__name__+': '+str(exc)[:200]))
    return result

def main():
    OUT.mkdir(parents=True,exist_ok=True);(OUT/'bundles').mkdir(exist_ok=True)
    metadata=(ROOT/'.analysis/il2cpp-v1.3.1/dump.cs').read_text(encoding='utf8')
    bases={n:base for n,base in re.findall(r'^public (?:abstract )?class ([\w.]+)\s*:\s*([^\n{]+)',metadata,re.M)}
    enemies={'EnemyObject'}
    while True:
        found={n for n,base in bases.items() if any(re.match(re.escape(p)+r'(?:\W|$)',base) for p in enemies)}
        if found<=enemies:break
        enemies.update(found)
    manifest=json.loads((ROOT/'artifacts/research/monster-textures/bundle-manifest.json').read_text())
    names=sorted(v for _,v in manifest['AssetBundleNames'])
    start=time.monotonic();counts=collections.Counter();errors=[];classes=collections.Counter()
    with tempfile.TemporaryDirectory(prefix='audit-work-',dir=OUT) as directory:
        work=Path(directory).resolve();assert work.is_relative_to(OUT.resolve())
        request=work/'request.json'
        # Already audited bundles can be resumed without re-reading the full game.
        pending=[n for n in names if not (OUT/'bundles'/(n+'.json.gz')).exists()]
        request.write_text(json.dumps(dict(game=str(GAME),output=str(work),unique=str(ROOT/'artifacts/research/monster-textures/unique.bin'),bundles=pending)),encoding='utf8')
        helper=ROOT/'.analysis/audit-resource-stream.ps1'
        process=subprocess.Popen([str(Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'),'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(helper),'-Request',str(request)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf8',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            for line in process.stdout:
                name=line.strip()
                if name not in pending:raise RuntimeError('Unexpected resource helper output: '+name[:120])
                try:
                    env=UnityPy.load((work/name).read_bytes());record=scan(name,env,enemies)
                    (OUT/'bundles'/(name+'.json.gz')).write_bytes(gzip.compress(json.dumps(record,separators=(',',':')).encode(),mtime=0))
                    counts['scanned']+=1;counts['sprites']+=len(record['sprites']);counts['enemy_roots']+=len(record['enemies'])
                    classes.update(e['class_name'] for e in record['enemies']);del env;gc.collect()
                except Exception as exc:errors.append(dict(bundle=name,error=type(exc).__name__+': '+str(exc)))
                finally:
                    (work/name).unlink();process.stdin.write('next\n');process.stdin.flush()
                if counts['scanned']%75==0:print(json.dumps(dict(counts,total=len(names),seconds=round(time.monotonic()-start,1))),flush=True)
            code=process.wait(timeout=15)
            if code:raise RuntimeError(process.stderr.read()[-2000:])
        finally:
            if process.poll() is None:process.terminate();process.wait(timeout=10)
    records=[json.loads(gzip.decompress(path.read_bytes())) for path in (OUT/'bundles').glob('*.json.gz')]
    summary=dict(bundles_expected=len(names),bundles_scanned=len(records),bundle_failures=errors,
                 enemy_classes=sorted({e['class_name'] for r in records for e in r['enemies']}),
                 enemy_roots=sum(len(r['enemies']) for r in records),sprite_records=sum(len(r['sprites']) for r in records),
                 unresolved_references=sum(len(r['errors']) for r in records),seconds=round(time.monotonic()-start,2))
    (OUT/'scan-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
