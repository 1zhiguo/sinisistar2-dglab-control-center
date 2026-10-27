"""Display-only coverage journal. Recognition never reads this history."""
from datetime import datetime,timezone
from pathlib import Path
import json,time,hashlib
from copy import deepcopy
from . import cg_playback
from .gallery import describe_gallery
from .gallery_policy import GalleryClock

_GALLERY_ALIASES=json.loads((Path(__file__).parent/'assets/capture-candidates.json').read_text(encoding='utf-8'))['gallery']
_GALLERY_SCENES={r['value']:'Ga_'+r['name'].removeprefix('GaID_') for r in _GALLERY_ALIASES}

class CgCoverage:
    def __init__(self,path):
        self.path=Path(path);self.entries={};self.dirty=False;self.last_save=0.;self.identity=None;self.first_at=0.;self.gallery_clock=GalleryClock()
        try:self.entries=json.loads(self.path.read_text(encoding='utf-8')).get('entries',{})
        except (OSError,ValueError):pass
    def gallery_ids(self,g):
        return [key for key,row in cg_playback.REGISTRY.rows.items() if row['take']==g.get('take_name')
            and row.get('play_type')==g.get('play_type_raw') and (g.get('target_scene_id') in row.get('scene_ids',[])
                or g.get('target_scene_id')==-1 and _GALLERY_SCENES.get(g.get('enemy_id')) in row.get('scene_names',[]))
            and (not g.get('owner_path') or cg_playback.canonical(row['owner'])==cg_playback.canonical(g['owner_path']))]
    def observe(self,s,pulse,ovc,pulse_wire,ovc_wire,mode,now):
        if not cg_playback.fresh(s,now):self.identity=None;self.gallery_clock.reset();return
        gallery=describe_gallery(s,now);g=s.get('gallery') or {};info=cg_playback.describe_game_cg(s,now)
        if gallery['inGallery'] and gallery['selectionActive']:
            self.gallery_clock.update(s,dict(rule=dict(enabled=True),pause_on_stop=False),now)
            loaded=self.gallery_clock.take is not None
            matches=self.gallery_ids(g) if loaded else [];pending_key='gallery:'+str(g.get('enemy_id'))+':'+str(g.get('selected_index_raw'))
            key=matches[0] if len(matches)==1 else pending_key
            if key!=pending_key and pending_key in self.entries:
                prior=self.entries.pop(pending_key)
                if prior.get('name')==g.get('take_name'):
                    merged=dict(prior,**self.entries.get(key,{}));self.entries[key]=merged
            name=g.get('take_name') or '怪物 #'+str(g.get('enemy_id'))+' ['+str(g.get('selected_index_raw'))+']'
            identity=gallery['takeIdentity'] or gallery['selectionIdentity'];recognized=bool(gallery['playing'] and loaded);source='gallery'
            reason=gallery['label'];kind=gallery['playType']
        elif info['recognized']:
            matches=info['ids'];key=matches[0] if len(matches)==1 else 'game-family:'+hashlib.sha256(str(matches).encode()).hexdigest()[:12]
            name=info['name'];identity=(s.get('session'),s.get('pid'),tuple(matches));recognized=True;source='game';reason=info['reason'];kind=info['kind']
        else:self.identity=None;self.gallery_clock.reset();return
        if identity!=self.identity:self.identity=identity;self.first_at=now
        row=dict(self.entries.get(key) or {},name=name,kind=kind,last_source=source,last_mode=mode,reason=reason,
            last_seen=datetime.now(timezone.utc).isoformat(),catalog_ids=matches)
        if source=='gallery':row['gallery_seen']=True
        if recognized:row[source+'_recognized']=True
        proof=dict(utc=s.get('utc'),sample_id=s.get('sample_id'),gallery=deepcopy(g),cg_playback=deepcopy(s.get('cg_playback') or {}))
        proof_key=str((identity,recognized,g.get('take_source'),g.get('take_token_active'),g.get('owner_error'),
            (g.get('animator') or {}).get('error'),(s.get('cg_playback') or {}).get('error'),pulse.get('reason'),ovc.get('reason')))
        history=list(row.get('evidence',[]))
        if proof_key!=row.get('evidence_key') and len(history)<8:history.append(proof)
        row.update(evidence=history,evidence_key=proof_key,latest_evidence=proof,playback_evidence=gallery.get('playbackEvidence') if source=='gallery' else info.get('kind'))
        planned=set(row.get('planned',[]));sent=set(row.get('sent',[]))
        for route,plan,wire in (('pulse',pulse,pulse_wire),('vibration',ovc,ovc_wire)):
            current=set()
            if recognized and plan.get('hp_used') is False:
                for c,frame in plan.get(route+'_stream',{}).items():
                    if frame and frame.get('peak',0)>0:current.add(route+c)
                planned.update(current)
                if now-self.first_at>=.2:
                    sent.update(route+c for c,state in wire.items() if state.get('active') and route+c in current and (state.get('deadline') or 0)>now)
            row[route+'_reason']=plan.get('reason','')
        row.update(planned=sorted(planned),sent=sorted(sent));self.entries[key]=row;self.dirty=True
    def save(self,now=None,force=False):
        now=time.monotonic() if now is None else now
        if not self.dirty or not force and now-self.last_save<2:return False
        self.path.parent.mkdir(parents=True,exist_ok=True);temp=self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(self.report(),ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(self.path)
        self.last_save=now;self.dirty=False;return True
    def clear(self):self.entries={};self.identity=None;self.gallery_clock.reset();self.dirty=True;self.save(force=True)
    def report(self):return dict(schema=1,entries=self.entries,notes='目录引用、识别、生成波形和控制中心发送分别记录；图鉴通过不代表实战或实体体感通过。')
    def rows(self):
        rows=[]
        for key,static in cg_playback.REGISTRY.rows.items():
            live=self.entries.get(key,{})
            rows.append(dict(id=key,name=static['take'],kind='共享动画' if live.get('kind')=='SharedAnimator' else 'Animator' if static['play_type']==0 else 'EventPlayer',
                scenes=' / '.join(static.get('scene_names',[])),mapping='共享动画＋演出引用' if static.get('shared_animations') else '已有引用映射' if static.get('events') or static.get('animator') else '引用待补齐',
                stage='已发送' if live.get('sent') else '已生成波形' if live.get('planned') else '已识别' if live.get('gallery_recognized') or live.get('game_recognized') else '已选择 · 未确认' if live else '未测试',
                game='实战已识别' if live.get('game_recognized') else '实战待验证',gallery='图鉴已识别' if live.get('gallery_recognized') else '图鉴待验证',
                detail='；'.join(filter(None,(live.get('reason'),live.get('pulse_reason'),live.get('vibration_reason')))),
                channels=' / '.join(live.get('sent') or live.get('planned') or []),lastMode=live.get('last_mode','')))
        for key,live in self.entries.items():
            if key in cg_playback.REGISTRY.rows:continue
            rows.append(dict(id=key,name=live['name'],kind=live.get('kind',''),scenes='',mapping='动画族已识别 · 具体片段待映射' if key.startswith('game-family:') else '图鉴身份尚未唯一映射',stage='已发送' if live.get('sent') else '已识别' if live.get('gallery_recognized') or live.get('game_recognized') else '已选择 · 未确认',game='实战动画族已识别' if live.get('game_recognized') else '实战待验证',gallery='图鉴已识别' if live.get('gallery_recognized') else '图鉴待验证',detail=live.get('reason',''),channels=' / '.join(live.get('sent',[])),lastMode=live.get('last_mode','')))
        return rows
