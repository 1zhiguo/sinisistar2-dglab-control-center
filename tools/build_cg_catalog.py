"""Read serialized gallery references, not filename guesses or damage behavior."""
from pathlib import Path
import collections,hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.analysis/unitypy'));sys.path.insert(0,str(ROOT/'src'))
import UnityPy
from UnityPy.classes.PPtr import PPtr
from sinisistar_dglab.telemetry import TYPES,BUILD

def main():
    scenes={name:int(key) for key,name in TYPES['SceneID'].items()};rows=[];errors=[];bundles={}
    research=ROOT/'artifacts/research/monster-textures'
    scene_table=json.loads((research/'resource-name-table.json').read_text(encoding='utf-8'))['m_SceneAssetBundleInfoList']['m_AssetBundleInfoList']
    required={item['m_AssetBundleName'] for item in scene_table}
    missing=required-{p.name for p in (research/'decoded').iterdir() if p.is_file()}
    if missing:raise RuntimeError(f'{len(missing)} serialized scene bundles have not been decoded; refusing a partial CG catalog')
    paths=sorted((ROOT/'artifacts/research/monster-textures/decoded').iterdir())
    # Controllers often live in another scene bundle. Resolve by embedded CAB
    # identity, not by the encrypted/hashed bundle filename.
    cab_sources={};loaded=collections.OrderedDict()
    for path in paths:
        if not path.is_file():continue
        scan=UnityPy.load(path.read_bytes())
        for name in scan.cabs:cab_sources[name.lower()]=path
    def load(path):
        if path.name in loaded:loaded.move_to_end(path.name);return loaded[path.name]
        environment=UnityPy.load(path.read_bytes());original=environment.find_file
        def find(name):
            name=name.rsplit('/',1)[-1].lower()
            for key,value in environment.cabs.items():
                if key.lower()==name:return value
            source=cab_sources.get(name)
            if source:
                dependency=load(source)
                return next((v for k,v in dependency.cabs.items() if k.lower()==name),None)
            return original(name)
        environment.find_file=find;loaded[path.name]=environment
        if len(loaded)>16:loaded.popitem(last=False)
        return environment
    for index,path in enumerate(paths):
        if not path.is_file():continue
        env=load(path)
        for retry in range(4):
            try:containers=list(env.container);break
            except RuntimeError:
                if retry==3:raise
        scene_names=[Path(k).stem for k in containers if k.lower().endswith('.unity')]
        scene_ids=[scenes[n] for n in scene_names if n in scenes]
        def ptr(o,ref):return PPtr(**ref,assetsfile=o.assets_file).deref()
        def hierarchy(game):
            names=[];seen=set()
            while game and game.path_id not in seen and len(names)<40:
                seen.add(game.path_id);g=game.read();names.append(g.m_Name)
                transform=next(e.component.read() for e in g.m_Component if e.component.type.name in ('Transform','RectTransform'))
                game=transform.m_Father.read().m_GameObject.deref() if transform.m_Father else None
            return '/'.join(reversed(names))
        def signature(o,ref):
            if not ref or not ref.get('m_PathID'):return None
            target=ptr(o,ref);m=target.read(check_read=False)
            return dict(type=m.m_Script.read().m_ClassName,path=hierarchy(m.m_GameObject.deref()),path_id=target.path_id)
        first_row=len(rows);incoming=[];players=[];animation_actions=[]
        for obj in list(env.objects):
            if obj.type.name!='MonoBehaviour':continue
            try:
                mono=obj.read(check_read=False);kind=mono.m_Script.read().m_ClassName
                if kind in ('HierarchyEventPlayer','PlayableDirectorPlayer','EventLabelPlayer'):
                    players.append(dict(type=kind,path=hierarchy(mono.m_GameObject.deref())))
                if kind in ('AnimatorTriggerLabel','AnimatorTriggerAsyncLabel'):
                    label_path=hierarchy(mono.m_GameObject.deref())
                    for parameter in obj.read_typetree().get('m_Parameters') or []:
                        ref=parameter.get('m_Animator');name=parameter.get('m_PlayName')
                        if not ref or not ref.get('m_PathID') or not name:continue
                        target=ptr(obj,ref);anim=target.read()
                        animation_actions.append(dict(label=label_path,label_type=kind,state=name,layer=parameter.get('m_LayerIndex',0),
                            path=hierarchy(anim.m_GameObject.deref()),controller=anim.m_Controller.read().m_Name if anim.m_Controller else ''))
                if kind=='HierarchyEventPlayer':
                    tree=obj.read_typetree();ref=tree.get('m_DefaultNextEventPlayer')
                    if ref and ref.get('m_PathID'):
                        before=dict(type=kind,path=hierarchy(mono.m_GameObject.deref()),path_id=obj.path_id)
                        after=signature(obj,ref)
                        # An explicit wait -> CG link in the same sequence is
                        # part of that CG; unrelated siblings are never inferred.
                        if after and before['path'].rsplit('/',1)[0]==after['path'].rsplit('/',1)[0]:incoming.append((before,after))
                if kind not in ('GaSceneTakePlayer','GaEnemyTakePlayer','GaTakePlayer'):continue
                data=obj.read_typetree();owner=hierarchy(mono.m_GameObject.deref())
                bundles[path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
                for position,take in enumerate(data.get('m_TakeDataArray') or []):
                    key=hashlib.sha256(f'{path.name}:{obj.path_id}:{position}'.encode()).hexdigest()[:20]
                    row=dict(id=key,bundle=path.name,scene_ids=scene_ids,scene_names=scene_names,owner=owner,take=take.get('m_TakeName',''),
                        play_type=take.get('m_PlayType'),combat=bool(take.get('m_IsCombatEvent')),loop=bool(take.get('m_IsAnimatorLoop')),
                        queue=take.get('m_QueueArray') or [],events=[],animator=None,errors=[],runtime_verified=False)
                    refs=[('init',take.get('m_EventPlayerInit'))]+[('main',ref) for ref in take.get('m_EventPlayerArray') or []]
                    seen=set()
                    for role,ref in refs:
                        for _ in range(32):
                            if not ref or not ref.get('m_PathID') or (ref['m_FileID'],ref['m_PathID']) in seen:break
                            seen.add((ref['m_FileID'],ref['m_PathID']))
                            try:
                                sig=signature(obj,ref);sig['role']=role;row['events'].append(sig)
                                target=ptr(obj,ref);ref=target.read_typetree().get('m_DefaultNextEventPlayer');role='next'
                            except Exception as exc:row['errors'].append(type(exc).__name__);break
                    try:
                        ref=take.get('m_Animator')
                        if ref and ref.get('m_PathID'):
                            target=ptr(obj,ref);a=target.read()
                            row['animator']=dict(path=hierarchy(a.m_GameObject.deref()),controller=a.m_Controller.read().m_Name if a.m_Controller else '')
                    except Exception as exc:row['errors'].append('animator:'+type(exc).__name__)
                    rows.append(row)
            except Exception as exc:
                if 'kind' in locals() and kind in ('GaSceneTakePlayer','GaEnemyTakePlayer','GaTakePlayer'):errors.append(dict(bundle=path.name,error=str(exc)[:150]))
        for row in rows[first_row:]:
            linked={(e['type'],e['path']) for e in row['events'] if e['role']!='init'}
            for _ in range(32):
                added=[before for before,after in incoming if (after['type'],after['path']) in linked and (before['type'],before['path']) not in linked]
                if not added:break
                for before in added:
                    linked.add((before['type'],before['path']));row['events'].append(dict(before,role='serialized-predecessor'))
            # Expand the declared CG's actual animation commands. A different
            # real-game EventPlayer can share these exact actor/controller/state
            # references without sharing the gallery entry point.
            bindings={}
            for action in animation_actions:
                owners=[player for player in players if action['label'].startswith(player['path']+'/')]
                if not owners:continue
                owner=max(owners,key=lambda player:len(player['path']))
                if (owner['type'],owner['path']) not in linked:continue
                key=(action['controller'],action['path'],action['layer'])
                binding=bindings.setdefault(key,dict(controller=key[0],path=key[1],layer=key[2],states=[],labels=[]))
                if action['state'] not in binding['states']:binding['states'].append(action['state'])
                binding['labels'].append(dict(path=action['label'],type=action['label_type']))
            row['shared_animations']=list(bindings.values())
        if index%50==0:print(json.dumps(dict(scanned=index,total=len(paths),takes=len(rows))),flush=True)
    result=dict(schema=1,game_build=BUILD,source='serialized AnimationTakeData references and explicit same-sequence wait links',scanned_bundles=len(paths),scene_inventory_bundles=len(required),scene_inventory_missing=0,bundles=bundles,takes=rows,errors=errors)
    target=ROOT/'src/sinisistar_dglab/assets/cg-catalog.json';target.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print(json.dumps(dict(takes=len(rows),event=sum(r['play_type']==1 for r in rows),animator=sum(r['play_type']==0 for r in rows),
        scene_mapped=sum(bool(r['scene_ids']) for r in rows),errors=len(errors),bytes=target.stat().st_size)),flush=True)

if __name__=='__main__':main()
