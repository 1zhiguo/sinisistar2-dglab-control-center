"""Inventory capture/penalty symbols in the supplied v1.3.1 metadata.

Reads existing local dump only. Never loads the game, plays an animation,
changes a save, or classifies a symbol as an individually verified CG.
"""
from pathlib import Path
import hashlib,json,re

ROOT=Path(__file__).resolve().parents[1]
SYMBOL=re.compile(r'Hold|Bind|Capture|Punish|Vore|Insert|Eat',re.I)

def inventory(text):
    entries={}
    pattern=re.compile(r'^public (class|enum) ([\w.]+)([^\n]*)\n\{(.*?)^\}',re.M|re.S)
    line=1;previous=0
    for match in pattern.finditer(text):
        line+=text.count('\n',previous,match.start());previous=match.start()
        kind,name,header,body=match.groups()
        entries[name]=dict(kind=kind,header=header,body=body,line=line)
    enum=entries.get('GalleryEnemyID',{}).get('body','')
    gallery=[dict(name=name,value=int(value)) for name,value in re.findall(r'public const GalleryEnemyID (\w+) = (-?\d+);',enum)]
    rows=[]
    for name,item in entries.items():
        if item['kind']!='class' or not re.search(r': EnemyObject\b|\bIGalleryEnableAttacker\b|\bIBinder\b',item['header']):continue
        if name in ('SiNiObject','Bind','GachaBind'):continue
        body=item['body']
        fields=sorted(set(field for field in re.findall(r'\b(m_Anim\w+|m_\w*Animator)\s*;',body) if SYMBOL.search(field)))
        tasks=sorted(set(task for task in re.findall(r'\b(Task\w+)\(',body) if SYMBOL.search(task)))
        states=[];animations=[]
        for suffix,target in (('.State',states),('.AnimName',animations)):
            nested=entries.get(name+suffix,{}).get('body','')
            target.extend(dict(name=n,value=int(v)) for n,v in re.findall(r'public const [\w.]+ (\w+) = (-?\d+);',nested) if SYMBOL.search(n))
        if not any((fields,tasks,states,animations)):continue
        normal=lambda value:re.sub(r'[^a-z0-9]','',value.lower().removeprefix('gaid_'))
        aliases=[g for g in gallery if normal(g['name'])==normal(name)]
        rows.append(dict(enemy=name,line=item['line'],states=states,animations=animations,animation_fields=fields,tasks=tasks,
                         gallery_aliases=aliases,runtime_verified=False,precise_cg_verified=False,
                         evidence='Static metadata symbols; candidate family, not a CG count'))
    return dict(schema=1,game_version='1.3.1',candidate_count=len(rows),gallery_symbol_count=len(gallery),
                gallery_distinct_ids=len({g['value'] for g in gallery}),gallery=gallery,candidates=sorted(rows,key=lambda r:r['enemy']),
                limitation='Names identify candidate enemy flow families only. Active animation/hash, variants, phases and duration require runtime observation.')

if __name__=='__main__':
    source=ROOT/'.analysis/il2cpp-v1.3.1/dump.cs'
    raw=source.read_bytes();result=inventory(raw.decode('utf-8'));result['source_sha256']=hashlib.sha256(raw).hexdigest()
    target=ROOT/'src/sinisistar_dglab/assets/capture-candidates.json'
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(candidates=result['candidate_count'],gallery_symbols=result['gallery_symbol_count'],gallery_ids=result['gallery_distinct_ids'],
                          zombie=next((r for r in result['candidates'] if r['enemy']=='Zombie'),None)),ensure_ascii=False))
