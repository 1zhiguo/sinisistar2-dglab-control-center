"""Extract GO-named SceneID candidates, retaining build evidence (not CG counts)."""
import hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def inventory(text):
    return [dict(scene=m[1],scene_id=int(m[2]),line=text.count('\n',0,m.start())+1)
            for m in re.finditer(r'public const SceneID (\w+) = (\d+);',text)
            if re.search(r'(?:^|_)go(?:\d+|_|$)',m[1],re.I)]
if __name__=='__main__':
    raw=(ROOT/'.analysis/il2cpp-v1.3.1/dump.cs').read_bytes()
    result=dict(game_version='1.3.1',source_sha256=hashlib.sha256(raw).hexdigest(),candidates=inventory(raw.decode('utf-8')))
    target=ROOT/'src/sinisistar_dglab/assets/flow-scene-candidates.json'
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Scene candidates:',len(result['candidates']))
