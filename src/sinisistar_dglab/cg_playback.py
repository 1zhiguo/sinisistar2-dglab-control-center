"""HP-independent recognition from serialized CG references and live playback."""
from .game_builds import FINGERPRINTS
from pathlib import Path
import json,math,time,re
from .telemetry import BUILD

def canonical(path):return '/'.join(part.replace('(Clone)','').strip() for part in str(path or '').strip('/').split('/'))

def animator_anchor(path):
    path=canonical(path)
    for marker in ('CCP_Enemy/','CCP_Player/'):
        if marker in path:return path[path.index(marker):]
    return path

def distinctive_shared_state(name):
    # A normal idle/walk/hit pose in a dialogue is not sufficient CG evidence.
    short=str(name).rsplit('.',1)[-1]
    return bool(short and not re.fullmatch(r'(?:idle|walk|run|move|stand|wait|init|preview|attack|jump|fall|land|hit|damage|die|dead)(?:_?\d+)?',short,re.I))

class CgRegistry:
    def __init__(self,data=None):
        if data is None:
            try:data=json.loads((Path(__file__).parent/'assets/cg-catalog.json').read_text(encoding='utf-8'))
            except (OSError,ValueError):data={}
        self.rows={r['id']:r for r in data.get('takes',[]) if r.get('take') and r['take'].lower() not in ('init','preview')}
        self.events={};self.animators={};self.shared={}
        for key,row in self.rows.items():
            for event in row.get('events',[]):
                for scene in row.get('scene_ids',[]):
                    self.events.setdefault((scene,event['type'],canonical(event['path'])),set()).add(key)
            anim=row.get('animator') or {}
            if anim.get('path') and anim.get('controller'):
                for name in row.get('queue',[]):
                    self.animators.setdefault((anim['controller'],canonical(anim['path']),name),set()).add(key)
            for binding in row.get('shared_animations') or []:
                if not binding.get('controller') or not binding.get('path'):continue
                for state in binding.get('states') or []:
                    if distinctive_shared_state(state):
                        self.shared.setdefault((binding['controller'],state),[]).append((key,canonical(binding['path']),binding.get('layer',0)))
    def event_ids(self,scene,event):return self.events.get((scene,event.get('type'),canonical(event.get('path'))),set())
    def animator_ids(self,scene,anim):
        result=set();path=canonical(anim.get('path'))
        for name in anim.get('matched_names') or []:
            for (controller,expected,state),keys in self.animators.items():
                anchor=animator_anchor(expected)
                if controller!=anim.get('controller') or name!=state or not (path==expected or path.endswith('/'+expected) or anchor!=expected and path.endswith('/'+anchor)):continue
                result.update(k for k in keys if scene in self.rows[k]['scene_ids'] or anchor!=expected and all(n.startswith('Ga_') for n in self.rows[k].get('scene_names',[])))
        return result

    def shared_ids(self,scene,anim):
        result=set();path=canonical(anim.get('path'))
        for state in anim.get('matched_names') or []:
            if not isinstance(state,str):continue
            for key,expected,layer in self.shared.get((anim.get('controller'),state),[]):
                if type(anim.get('layer')) is not int or not 0<=anim['layer']<4 or layer>=0 and anim['layer']!=layer:continue
                anchor=animator_anchor(expected)
                same_actor=(path==expected or path.endswith('/'+expected)
                            or anchor!=expected and path.endswith('/'+anchor))
                scene_names=self.rows[key].get('scene_names',[])
                same_scene=(scene in self.rows[key]['scene_ids'] or anchor!=expected and bool(scene_names)
                            and all(n.startswith('Ga_') for n in scene_names))
                if same_actor and same_scene:result.add(key)
        return result

REGISTRY=CgRegistry()

def fresh(s,now):
    stamp=s.get('sampled_at')
    return bool(s.get('source')=='bepinex' and s.get('fingerprint') in FINGERPRINTS and s.get('live') is True
        and type(stamp) in (int,float) and math.isfinite(stamp) and 0<=now-stamp<.6
        and type(s.get('pid')) is int and s['pid']>0 and isinstance(s.get('session'),str) and s['session'])

def valid_animator(anim):
    return bool(isinstance(anim,dict) and anim.get('available') is True and anim.get('active') is True
        and type(anim.get('object')) is int and anim['object']>0 and anim.get('controller') and anim.get('path')
        and isinstance(anim.get('matched_names'),list) and any(isinstance(n,str) and n for n in anim['matched_names'])
        and type(anim.get('normalized_time')) in (int,float) and math.isfinite(anim['normalized_time']) and anim['normalized_time']>=0
        and type(anim.get('length')) in (int,float) and math.isfinite(anim['length']) and anim['length']>0)

def describe_game_cg(s,now=None,registry=None):
    now=time.monotonic() if now is None else now;registry=REGISTRY if registry is None else registry
    result=dict(recognized=False,ids=[],name='',kind='',reason='等待新鲜 CG 播放信号',hp_used=False)
    if not fresh(s,now):return result
    if str(s.get('scene','')).startswith(('Ga_','Gallery')):return dict(result,reason='图鉴使用独立播放识别')
    raw=s.get('cg_playback') or {}
    if raw.get('available') is not True or raw.get('schema')!=1:return dict(result,reason='需要观察插件 0.5.0 的 CG 播放字段')
    if s.get('loading'):return dict(result,reason='加载中')
    event=raw.get('event') or {};ids=set();kind='';identity=None
    shared_states=[]
    if (raw.get('shared_animation_schema')==1 and event.get('playing') is True and s.get('event_playing') is True
            and type(event.get('object')) is int and event['object']>0):
        for anim in raw.get('shared_animators') or []:
            if (not valid_animator(anim) or anim.get('source')!='active_event_receiver'
                    or type(anim.get('owner_event_object')) is not int or anim['owner_event_object']!=event['object']):continue
            matches=registry.shared_ids(s.get('scene_id'),anim)
            if matches:
                ids.update(matches);shared_states.extend(anim.get('matched_names') or [])
        if ids:kind='SharedAnimator';identity=(event['object'],tuple(sorted(ids)))
    if not ids and event.get('playing') is True and s.get('event_playing') is True and type(event.get('object')) is int and event['object']>0:
        ids=registry.event_ids(s.get('scene_id'),event)
        if ids:kind='EventPlayer';identity=(event['object'],canonical(event.get('path')))
    if not ids:
        for anim in raw.get('animators') or []:
            if not valid_animator(anim):continue
            matches=registry.animator_ids(s.get('scene_id'),anim)
            if not matches:continue
            # The same enemy controller also plays ordinary combat animations.
            # Require CG/interaction context independently of HP values.
            from .scripted_go import GO_SCENES
            exact=any(s.get('scene_id') in registry.rows[k].get('scene_ids',[]) for k in matches)
            context=s.get('bound') is True or (s.get('gacha') or {}).get('active') is True or s.get('scene_id') in GO_SCENES or exact and s.get('event_playing') is True
            if not context:result['reason']='动画已匹配 · 缺少实战演出 / 互动上下文';continue
            ids=matches;kind='Animator';identity=(anim['object'],tuple(anim['matched_names']));break
    if not ids:return dict(result,reason=result['reason'] if result['reason'].startswith('动画已匹配') else '当前播放器未匹配 CG 目录')
    names=sorted({registry.rows[k]['take'] for k in ids})
    return dict(result,recognized=True,ids=sorted(ids),name=' / '.join(names),kind=kind,reason='CG 播放已确认 · 不依赖 HP',
        identity=identity,paused=s.get('paused') is True,scene=s.get('scene_id'),
        evidence='shared_actor_controller_state' if kind=='SharedAnimator' else 'declared_playback_reference',animation_states=sorted(set(shared_states)))

class CgPlaybackClock:
    def __init__(self):self.reset()
    def reset(self):self.session=None;self.ids=set();self.age=0.;self.last_at=None;self.running=False;self.episode=0
    def update(self,s,info,now):
        session=(s.get('session'),s.get('pid'))
        if not info.get('recognized'):
            self.reset();return dict(ready=False,age=0.,reason=info.get('reason','等待 CG 播放'))
        ids=set(info['ids']);same=session==self.session and bool(ids&self.ids)
        if not same:self.age=0.;self.episode+=1;self.running=False
        paused=s.get('paused') is True
        if same and self.running and not paused and self.last_at is not None:self.age+=max(0,min(.6,now-self.last_at))
        self.session=session;self.ids=ids;self.last_at=now;self.running=not paused
        return dict(ready=not paused,age=self.age,reason='游戏已暂停' if paused else '',seed=str((session,sorted(ids),self.episode)))
