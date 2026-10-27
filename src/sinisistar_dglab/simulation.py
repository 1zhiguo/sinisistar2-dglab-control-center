"""Pure preview planner. No device, network, input automation or hardware imports."""
from __future__ import annotations
from copy import deepcopy
import json, math, time
from pathlib import Path
from .monitoring import status_label
from .status_policy import positive_status,normalize_abnormal,ABNORMAL_PULSE
from .quick_policy import default_presets,sanitize_presets,needs_ovc_preset_upgrade,upgrade_ovc_presets
from .penalty_flows import recoverable_penalty,recoverable_recovery,current_penalty_class,pigpen_penalty_identity
from .locked_hp import locked_hp_penalty
from .scripted_go import scripted_go_penalty,scripted_go_identity,GO_SCENES
from .cg_policy import make_cg,sanitize_cg,effective_cg,cg_stage,select_wave,ramp_fraction,queue_scale,channel_options
from .channel_policy import defaults as channel_defaults,sanitize as sanitize_channels,allows as channel_allows
from .same_hp import same_hp_flow,same_hp_feedback
from .gallery_policy import make_gallery,sanitize_gallery,GalleryClock,is_gallery,gallery_gate

TYPES=json.loads((Path(__file__).parent/'assets/types.json').read_text(encoding='utf-8'))['AbnormalType']
VIBRATION_WAVES=[
    {'key':'vib_beat','name':'震动 · 节拍','points':[0,.33,.66,1,0,1,0,0]},
    {'key':'vib_surf','name':'震动 · 起伏','points':[.55,.7,.8,.9,.95,1,1,1,.95,.9,.8,.7,.55]},
    {'key':'vib_trapezoid','name':'震动 · 梯形','points':[0,.2,.4,.6,.8,1,1,1,1,.8,.6,.4,.2,0]},
    {'key':'vib_impact','name':'震动 · 短击','points':[1,1,0]},
]
VIBRATION_WAVES+=json.loads((Path(__file__).parent/'assets/ovc-presets.json').read_text(encoding='utf-8'))
# Vibration amplitudes follow the separate OVC envelope designs in the user's
# GPL-3.0 Ricca project; these are previews, not encoded Socket frames.
EVENT_NAMES={'grab_hold':'抓取期间','defeat_hold':'死亡惩罚（零血 / 战败）','grab_hp_loss':'抓取中 HP 下降',
             'hp_loss':'普通 HP 下降','enemy_hit':'击中敌人','enemy_kill':'击杀敌人',
             'break':'服装破损','event_hold':'未绑定演出（通用）'}

def number(v,lo,hi,default=0):
    try:v=float(v)
    except (TypeError,ValueError):return default
    return min(hi,max(lo,v)) if math.isfinite(v) else default

def base_rule(key,name,*,enabled=True,priority=30):
    return dict(key=key,name=name,enabled=enabled,priority=priority,duration=.8,cooldown=.25,
                pulse_enabled=True,pulse_channel='A',pulse_strength=6.,pulse_wave='breath',pulse_period=2.,pulse_level_step=1.,pulse_gain=0.,pulse_frequency=30.,
                vibration_enabled=True,vibration_channel='A',vibration_strength=20.,vibration_wave='vib_surf',vibration_period=2.,vibration_level_step=3.,vibration_gain=0.,
                pulse_max=False,vibration_max=False,pulse_strength_a=None,pulse_strength_b=None,
                vibration_strength_a=None,vibration_strength_b=None,
                pulse_start_strength=None,vibration_start_strength=None,
                pulse_start_strength_a=None,pulse_start_strength_b=None,vibration_start_strength_a=None,vibration_start_strength_b=None,
                pulse_ramp_seconds=5. if key=='grab_hold' else 10.,vibration_ramp_seconds=5. if key=='grab_hold' else 10.,death_mode='until_end',death_seconds=3.,label='',start=0.,end=0.)

def default_profile():
    rules={k:base_rule(k,n,enabled=k not in ('event_hold','enemy_hit','enemy_kill')) for k,n in EVENT_NAMES.items()}
    for k in ('hp_loss','grab_hp_loss'):
        rules[k].update(priority=80,pulse_strength=10.,pulse_wave='impact',pulse_period=.8,pulse_gain=.2,
                        vibration_strength=35.,vibration_wave='vib_impact',vibration_period=.4,vibration_gain=.5)
    rules['grab_hold'].update(priority=40,pulse_strength=5.,vibration_strength=15.)
    rules['break'].update(priority=70,pulse_wave='impact',pulse_period=.8,vibration_wave='vib_impact',vibration_period=.4)
    rules['defeat_hold'].update(priority=100,pulse_strength=20.,pulse_period=1.6,pulse_wave='death_ramp',pulse_channel='AB',pulse_max=False,
                                vibration_strength=40.,vibration_channel='AB',vibration_max=False,vibration_wave='ovc_trapezoid',vibration_period=2.)
    abnormal={name:base_rule(name,status_label(name),priority=20)
              for name in TYPES.values() if name!='None'}
    for rule in abnormal.values():rule['enabled']=False;normalize_abnormal(rule)
    return dict(version=11,feedback_preset_version=1,gallery=make_gallery(rules['defeat_hold']),channel_feedback=channel_defaults(),cg=make_cg(rules['defeat_hold']),mix='priority',zero_hp_mode='capture',quick_presets=default_presets(),quick_active_preset='',pulse_abnormal_base=10.,pulse_cap_a=20.,pulse_cap_b=20.,vibration_cap_a=50.,vibration_cap_b=50.,
                pulse_stack_bonus=10.,vibration_stack_bonus=0.,rules=rules,abnormals=abnormal,flows=[])

def initial_profile():
    """Fresh user configuration; schema defaults above also migrate older files."""
    from .quick_policy import apply_preset
    p=apply_preset(default_profile(),'medium');p['cg']=make_cg(p['rules']['defeat_hold'],split=True);p['gallery']=make_gallery(p['rules']['defeat_hold']);return p

def sanitize_rule(raw,default):
    r=deepcopy(default)
    if not isinstance(raw,dict):return r
    for k in ('enabled','pulse_enabled','vibration_enabled','pulse_max','vibration_max'):r[k]=raw.get(k,r[k]) is True
    r['death_mode']=raw.get('death_mode') if raw.get('death_mode') in ('until_end','timed') else r['death_mode']
    r['death_seconds']=number(raw.get('death_seconds',r['death_seconds']),.1,120,r['death_seconds'])
    for k,lo,hi in [('priority',0,100),('duration',.1,30),('cooldown',0,30),('start',0,86400),('end',0,86400),('pulse_frequency',1,100)]:
        r[k]=number(raw.get(k,r[k]),lo,hi,r[k])
    r['label']=str(raw.get('label',r['label']))[:180]
    for route in ('pulse','vibration'):
        for channel in 'ab':
            key=route+'_strength_'+channel;value=raw.get(key,r[key])
            r[key]=None if value is None else number(value,0,200 if route=='vibration' else 100,r[key] if r[key] is not None else r[route+'_strength'])
        for suffix in ('start_strength','start_strength_a','start_strength_b'):
            key=route+'_'+suffix;value=raw.get(key,r[key])
            r[key]=None if value is None else number(value,0,200 if route=='vibration' else 100,0)
        key=route+'_ramp_seconds';r[key]=number(raw.get(key,r[key]),.1,120,r[key])
        for suffix,lo,hi in [('strength',0,200 if route=='vibration' else 100),('period',.1,60),('level_step',0,30),('gain',0,10)]:
            k=route+'_'+suffix;r[k]=number(raw.get(k,r[k]),lo,hi,r[k])
        k=route+'_channel';r[k]=raw.get(k) if raw.get(k) in ('A','B','AB') else r[k]
        k=route+'_wave';r[k]=str(raw.get(k,r[k]))[:100]
    if r['key']=='defeat_hold':r.update(pulse_max=False,vibration_max=False)
    return r

def sanitize_profile(raw):
    p=default_profile()
    if not isinstance(raw,dict):p['cg']=make_cg(p['rules']['defeat_hold'],split=True);p['gallery']=make_gallery(p['rules']['defeat_hold']);return p
    p['quick_presets']=sanitize_presets(raw.get('quick_presets'))
    p['channel_feedback']=sanitize_channels(raw.get('channel_feedback'))
    p['quick_active_preset']=raw.get('quick_active_preset') if raw.get('quick_active_preset') in ('low','medium','high') else ''
    p['mix']=raw.get('mix') if raw.get('mix') in ('priority','max','sum') else p['mix']
    p['zero_hp_mode']=raw.get('zero_hp_mode') if raw.get('zero_hp_mode') in ('stop','capture','states') else p['zero_hp_mode']
    p['pulse_abnormal_base']=number(raw.get('pulse_abnormal_base',10),0,100,10)
    for route in ('pulse','vibration'):
        for suffix in ('cap_a','cap_b','stack_bonus'):
            k=route+'_'+suffix;p[k]=number(raw.get(k,p[k]),0,200 if route=='vibration' and suffix.startswith('cap_') else 100,p[k])
    for group in ('rules','abnormals'):
        if isinstance(raw.get(group),dict):
            for k,d in p[group].items():
                item=raw[group].get(k)
                if group=='abnormals' and raw.get('version',1)==1 and isinstance(item,dict):
                    item=deepcopy(item)
                    # Upgrade the old factory defaults; preserve individual
                    # non-default strengths and level adjustments.
                    if item.get('pulse_strength',6)==6:item['pulse_strength']=p['pulse_abnormal_base']
                    if item.get('pulse_level_step',1)==1:item['pulse_level_step']=0
                if group=='rules' and k=='defeat_hold' and raw.get('version',1) in (1,2) and isinstance(item,dict):
                    item=deepcopy(item)
                    if item.get('pulse_wave')=='breath' and item.get('pulse_strength')==10:
                        item.update(pulse_wave='death_ramp',pulse_period=1.6,pulse_channel='AB',priority=100)
                p[group][k]=sanitize_rule(item,d)
                if group=='abnormals':
                    normalize_abnormal(p[group][k])
                    if type(raw.get('version')) is not int or raw['version']<9:p[group][k]['enabled']=False
    p.update(pulse_abnormal_base=10.,pulse_stack_bonus=10.,vibration_stack_bonus=0.)
    p['cg']=sanitize_cg(raw.get('cg'),p['rules']['defeat_hold'],sanitize_rule)
    p['gallery']=sanitize_gallery(raw.get('gallery'),p['rules']['defeat_hold'],sanitize_rule)
    for r in raw.get('flows',[])[:150] if isinstance(raw.get('flows'),list) else []:
        if not isinstance(r,dict) or not isinstance(r.get('key'),str) or not r['key']:continue
        # Native JSON identity keys can contain escaped Unicode object names.
        # Keep their full identity rather than silently truncating at 600 chars.
        if len(r['key'])>4096:continue
        item=sanitize_rule(r,base_rule(r['key'],str(r.get('name','演出规则'))[:120],priority=60))
        p['flows'].append(item)
    if needs_ovc_preset_upgrade(raw):upgrade_ovc_presets(p)
    if raw.get('feedback_preset_version')!=1 and p['quick_active_preset']:
        from .quick_policy import sync_cg_strengths
        sync_cg_strengths(p,p['quick_presets'][p['quick_active_preset']])
    return p

def envelope(points,phase):
    if not points:return 0.
    x=(phase%1)*len(points);i=int(x);t=x-i
    return (points[i]*(1-t)+points[(i+1)%len(points)]*t)

def flow_key(s):return str((s.get('flow') or {}).get('key') or '')

def zero_hp_capture(s):
    """A current captive player at zero HP; never infer this from old damage."""
    hp=s.get('hp') or {}
    return (s.get('bound') is True and type(hp.get('current')) is int and hp['current']==0
            and type(hp.get('max')) is int and hp['max']>0)

def death_penalty_stage(s):
    hp=s.get('hp') or {};flow=s.get('flow') or {}
    if recoverable_recovery(s):return False
    return recoverable_penalty(s) or (type(hp.get('current')) is int and hp['current']==0 and type(hp.get('max')) is int and hp['max']>0) or (flow.get('playing') is True and flow.get('defeat_confirmed') is True)

def wave_samples(wave,age,period,frequency):
    frames=wave.get('frames') or []
    if frames:
        samples=[];frequencies=[]
        for q in range(4):
            index=int(((age+q*.025)%period)/period*len(frames)*4)%(len(frames)*4)
            data=bytes.fromhex(frames[index//4]);encoded=data[index%4]
            interval=encoded if encoded<=100 else 100+(encoded-100)*5 if encoded<=200 else 600+(encoded-200)*10
            frequencies.append(1000/interval);samples.append(data[4+index%4]/100)
        return samples,frequencies
    return [envelope(wave['points'],(age+q*.025)/period) for q in range(4)],[frequency]*4

def mix_parts(parts,mode,quarter=None):
    """Count the status baseline once and keep it under transient events."""
    if not parts:return 0.,0.,30.,[]
    death=[p for p in parts if p[8]]
    if death:
        chosen=max(death,key=lambda p:(p[0],p[1]));index=0 if quarter is None else quarter
        return chosen[1],chosen[2] if quarter is None else chosen[4][quarter],chosen[5][index],[chosen[3]]
    statuses=[p for p in parts if p[7]];others=[p for p in parts if not p[7]]
    order=(lambda p:(p[1],p[0])) if mode=='max' else (lambda p:(p[0],p[1]))
    chosen=others if mode=='sum' else [max(others,key=order)] if others else []
    if statuses:
        frequencies=[max(statuses,key=lambda p:p[4][q])[5][q] for q in range(4)]
        baseline=(max(p[0] for p in statuses),sum(p[1] for p in statuses),sum(p[2] for p in statuses),
                  '异常 / '+' + '.join(p[3] for p in statuses),[sum(p[4][q] for p in statuses) for q in range(4)],frequencies,
                  float('inf'),True,False)
        chosen=chosen+[baseline]
    if not chosen:return 0.,0.,30.,[]
    amplitude=lambda p:p[2] if quarter is None else p[4][quarter]
    dominant=max(chosen,key=lambda p:(amplitude(p),p[0],p[1]))
    combine=sum if mode=='sum' else max
    return combine(p[1] for p in chosen),combine(amplitude(p) for p in chosen),dominant[5][0 if quarter is None else quarter],[p[3] for p in chosen]

class Simulator:
    def __init__(self):self.gallery_clock=GalleryClock();self.reset()
    def reset(self,*,keep_death=False):
        if not keep_death:self.gallery_clock.reset()
        self.death_started_at=getattr(self,'death_started_at',None) if keep_death else None
        self.death_identity=getattr(self,'death_identity',None) if keep_death else None
        self.non_damage_started_at=getattr(self,'non_damage_started_at',None) if keep_death else None
        self.non_damage_identity=getattr(self,'non_damage_identity',None) if keep_death else None
        self.previous=None;self.identity=None;self.bursts={};self.cooldowns={};self.phases={};self.traces={k:[0.]*64 for k in ('pulseA','pulseB','vibrationA','vibrationB')}
    def sync_death(self,s,now):
        flow=s.get('flow') or {}
        if s.get('live') and 0<=now-s.get('sampled_at',0)<.6:
            info=dict(path=str((s.get('feedback_evidence') or {}).get('same_hp_episode'))) if same_hp_flow(s,float('inf')) else None
            identity=(s.get('session'),s.get('pid'),s.get('player'),s.get('scene_id'),flow.get('run'),info['path']) if info else None
            if not identity or identity!=self.non_damage_identity:self.non_damage_started_at=None
            self.non_damage_identity=identity
        if s.get('live') and 0<=now-s.get('sampled_at',0)<.6 and s.get('loading'):
            # No output while loading. Preserve this known cross-scene episode
            # only within its two maps and the same running game session.
            if self.death_identity==(s.get('session'),s.get('pid'),'pigpen-defeat') and s.get('scene_id') in (166,167):return
            if self.death_identity==(s.get('session'),s.get('pid'),'scripted-go') and s.get('scene_id') in GO_SCENES:return
            self.death_started_at=None;self.death_identity=None;return
        if not (s.get('live') and 0<=now-s.get('sampled_at',0)<.6 and (s.get('valid') or flow.get('valid') and flow.get('playing'))):return
        identity=pigpen_penalty_identity(s) or scripted_go_identity(s) or (s.get('session'),s.get('pid'),s.get('player'),s.get('scene_id'))
        if identity!=self.death_identity or not death_penalty_stage(s):self.death_started_at=None
        self.death_identity=identity
    def blank(self,reason='模拟未启动',source='实时只读'):
        return dict(pulseA=0.,pulseB=0.,vibrationA=0.,vibrationB=0.,pulse_stream={'A':None,'B':None},vibration_stream={'A':None,'B':None},generated_at=None,peaks={},selected={},active=[],reason=reason,source=source,
                    traces=deepcopy(self.traces),clipped=False,abnormal_count=0)
    def evaluate(self,s,profile,waves,*,now=None,enabled=True,emergency=False,events=(),demo=False,vibration_waves=None):
        now=time.monotonic() if now is None else now
        if is_gallery(s):return self.evaluate_gallery(s,profile,waves,now,enabled,emergency,vibration_waves=vibration_waves)
        self.gallery_clock.reset()
        self.sync_death(s,now)
        flow=s.get('flow') or {}
        fresh=bool(s.get('live') and 0<=now-s.get('sampled_at',0)<.6)
        valid=bool(fresh and (s.get('valid') or (flow.get('valid') and flow.get('playing'))))
        reason=('急停已锁定' if emergency else '模拟已暂停' if not enabled else '等待新鲜游戏数据' if not valid else
                '加载中' if s.get('loading') else '游戏已暂停' if s.get('paused') else
                '演出暂停' if flow.get('playing') and flow.get('paused') and not (locked_hp_penalty(s) or scripted_go_penalty(s) or same_hp_feedback(s,profile)) else
                'HP 归零 · 等待演出流程' if (s.get('hp') or {}).get('current')==0 and not flow.get('playing') and
                    profile['zero_hp_mode']=='stop' else
                '游戏时间停止' if not flow.get('playing') and not death_penalty_stage(s) and s.get('time_scale',1)<=0 else
                '回想模式不参与' if str(s.get('scene','')).startswith(('Ga_','Gallery')) else '')
        if reason:
            self.reset(keep_death=True);return self.blank(reason,'样例演示' if demo else '实时只读')
        identity=(s.get('session'),s.get('pid'),s.get('player'),s.get('scene_id'))
        if identity!=self.identity:self.reset(keep_death=True);self.identity=identity
        p=self.previous
        # Snapshot deltas are consumed once and never replayed after pause/rebind.
        if p and 0<=now-p.get('sampled_at',0)<.6 and s.get('sample_id')!=p.get('sample_id'):
            if p.get('broken') is False and s.get('broken') is True:
                self.trigger('break',0,profile,now)
            for resource,key in (('hp','hp_loss'),):
                a=p.get(resource) or {};b=s.get(resource) or {}
                if a.get('max')!=b.get('max'):continue
                old,new=a.get('current'),b.get('current')
                if isinstance(old,int) and isinstance(new,int) and old>new:
                    self.trigger(('grab_'+key) if s.get('bound') or p.get('bound') else key,old-new,profile,now)
        self.previous=deepcopy(s)
        for e in events:
            if not e.get('history') and e.get('key') in profile['rules'] and e['key'] not in ('hp_loss','mp_loss','break'):
                self.trigger(e['key'],0,profile,now)
        active=[]
        def hold(rule,token,detail='',level=1,stack=0,clock=None):
            if not rule.get('enabled'):return
            start=self.phases.setdefault(token,now)
            remaining=float('inf')
            if token.startswith('same_hp:'):
                if self.non_damage_started_at is None:self.non_damage_started_at=now
                start=self.non_damage_started_at
            if rule['key'] in ('defeat_hold','cg_hold') and recoverable_penalty(s):
                if self.death_started_at is None:self.death_started_at=now
                start=self.death_started_at
            if rule['key'] in ('defeat_hold','cg_hold') and rule.get('death_mode')=='timed':
                if not token.startswith('same_hp:'):
                    if self.death_started_at is None:self.death_started_at=now
                    start=self.death_started_at
                remaining=number(rule.get('death_seconds'),.1,120,3.)-(now-start)
                if remaining<=0:return
            active.append(dict(rule=rule,token=token,detail=detail,level=max(1,number(level,1,100,1)),stack=stack,
                               age=now-start if clock is None else clock,amount=0.,remaining=remaining))
        cg_config=effective_cg(profile) if cg_stage(s) else None
        penalty_rule=cg_config['rule'] if cg_config else profile['rules']['defeat_hold']
        if same_hp_feedback(s,profile) and not death_penalty_stage(s):
            info=dict(path='same_hp:'+str((s.get('feedback_evidence') or {}).get('same_hp_episode')),name='同值 HP 演出 · '+str(flow.get('name','')))
            rule=deepcopy(cg_config['rule']);rule.update(key='cg_hold',name='同值 HP 演出反馈')
            token='same_hp:'+str((flow.get('run'),info['path']))
            hold(rule,token,info['name'])
            if active and active[-1]['token']==token:active[-1]['cg_options']=cg_config['routes']
        elif death_penalty_stage(s) and profile['zero_hp_mode']!='stop':
            rule=penalty_rule
            detail=('固定 '+str(rule.get('death_seconds',3.))+' 秒') if rule.get('death_mode')=='timed' else '持续到挣脱 / 复活 / 演出结束'
            hold(rule,'defeat_capture',(current_penalty_class(s)[1] if recoverable_penalty(s) else s.get('binder') or flow.get('name') or '死亡阶段')+' · '+detail)
            if active and active[-1]['token']=='defeat_capture' and cg_config:
                active[-1]['cg_options']=cg_config['routes']
        elif s.get('bound') and (s.get('hp') or {}).get('current',0)>0:
            hold(profile['rules']['grab_hold'],'grab:'+str(s.get('binder') or ''),s.get('binder') or '未知敌人')
        statuses={x['name']:x for x in s.get('abnormals',[]) if s.get('valid') and not positive_status(x) and x.get('name') in profile['abnormals'] and profile['abnormals'][x['name']]['enabled'] and isinstance(x.get('level'),(int,float)) and x['level']>0}
        # State hold remains active until removed; no arbitrary duration timeout.
        for name,x in statuses.items():
            hold(profile['abnormals'][name],'status:'+name,'Lv.'+str(x.get('level')),x.get('level'),max(0,len(statuses)-1))
        if flow.get('playing') and not flow.get('paused'):
            clock=flow.get('timeline_time')
            if not isinstance(clock,(int,float)) or not math.isfinite(clock):clock=number(flow.get('elapsed'),0,86400)
            candidates=[r for r in profile['flows'] if r['key']==flow_key(s) and (not r['label'] or r['label']==flow.get('label'))
                        and clock>=r['start'] and (r['end']<=0 or clock<r['end'])]
            if not candidates and not any(r['key']==flow_key(s) for r in profile['flows']):candidates=[profile['rules']['event_hold']]
            for i,r in enumerate(candidates):hold(r,'flow:'+flow_key(s)+':'+str(flow.get('run',0))+':'+str(i),flow.get('label') or flow.get('name','演出'),clock=clock)
        for key,b in list(self.bursts.items()):
            if now>=b['until'] or not profile['rules'].get(key,{}).get('enabled'):del self.bursts[key];continue
            active.append(dict(rule=b['rule'],token=key,detail='单次事件',level=1,stack=0,age=now-b['start'],amount=b['amount']))
            active[-1]['remaining']=b['until']-now
        self.phases={k:v for k,v in self.phases.items() if any(a['token']==k for a in active)}
        return self.render(s,profile,waves,active,now,vibration_waves,demo,statuses,cg_config,penalty_rule)

    def render(self,s,profile,waves,active,now,vibration_waves=None,demo=False,statuses=(),cg_config=None,penalty_rule=None,gallery=False):
        catalogs={'pulse':{w['key']:w for w in waves},'vibration':{w['key']:w for w in (vibration_waves or VIBRATION_WAVES)}}
        result=self.blank('当前没有匹配规则','样例演示' if demo else '实时只读');result['abnormal_count']=len(statuses)
        contributions={k:[] for k in self.traces};display=[]
        for a in active:
            r=a['rule'];entry={'name':r['name'],'key':r['key'],'detail':a['detail'],'pulse':0.,'vibration':0.,'pulse_wave':r['pulse_wave'],'vibration_wave':r['vibration_wave'],'pulse_frequency':r['pulse_frequency']}
            for route in ('pulse','vibration'):
                if not r[route+'_enabled']:continue
                status=a['token'].startswith('status:')
                if status and route=='vibration':continue
                stack=max(0,sum(profile['abnormals'][name][route+'_enabled'] for name in statuses)-1) if a['token'].startswith('status:') else 0
                target=r[route+'_strength']+(a['level']-1)*r[route+'_level_step']+stack*profile[route+'_stack_bonus']+a['amount']*r[route+'_gain']
                target=number(target,0,200 if route=='vibration' else 100)
                if status:target=ABNORMAL_PULSE
                entry[route]=0
                for channel in ('A','B'):
                    if channel in r[route+'_channel'] and channel_allows(profile,route,channel,r['key']):
                        options=channel_options(a.get('cg_options'),route,channel)
                        seed=str((a['seed'],channel)) if a.get('seed') else str((s.get('session'),s.get('pid'),self.death_started_at,channel))
                        selected_wave=select_wave(options,r,route,a['age'],seed) if options else (r[route+'_wave'],r[route+'_period'],a['age'],a['age'],'')
                        if selected_wave is None:
                            entry['detail']+=' · '+route+channel+' 队列为空 / 单次已结束';continue
                        wave_key,period,wave_age,cycle_age,description=selected_wave
                        entry[route+'_wave_'+channel]=wave_key
                        if channel=='A' or 'A' not in r[route+'_channel']:entry[route+'_wave']=wave_key
                        if description:entry['detail']+=' · '+route+channel+' '+description
                        wave=catalogs[route].get(wave_key)
                        if not wave or not wave.get('points'):entry['detail']+=' · '+route+channel+' 波形不可用';continue
                        frequency=100 if route=='vibration' else options.get('frequency',r['pulse_frequency']) if options else r['pulse_frequency']
                        amplitudes,frequencies=wave_samples(wave,wave_age,period,frequency)
                        if options and options.get('mode')!='fixed':
                            # Resolve each channel's queue at every 25-ms boundary.
                            for quarter in range(4):
                                q=select_wave(options,r,route,a['age']+quarter*.025,seed)
                                qw=catalogs[route].get(q[0]) if q else None
                                if not qw or not qw.get('points'):amplitudes[quarter]=0.;continue
                                qa,qf=wave_samples(qw,q[2],q[1],frequency)
                                amplitudes[quarter]=qa[0]*queue_scale(options,route,a['age']+quarter*.025,seed);frequencies[quarter]=qf[0]
                        override=r.get(route+'_strength_'+channel.lower()) if r['key'] in ('defeat_hold','cg_hold') else None
                        cap_target=target if override is None else number(override,0,200 if route=='vibration' else 100)
                        if r['key'] in ('grab_hold','defeat_hold','cg_hold'):
                            low=r.get(route+'_start_strength_'+channel.lower()) if r['key'] in ('defeat_hold','cg_hold') else None
                            if low is None:low=r.get(route+'_start_strength')
                            if low is not None:
                                low=min(cap_target,number(low,0,200 if route=='vibration' else 100))
                                seconds=number(options.get('ramp_seconds',r.get(route+'_ramp_seconds')) if options else r.get(route+'_ramp_seconds'),.1,1800 if options else 120,10.)
                                ramp_age=wave_age if options and options.get('ramp_scope')=='wave' else cycle_age if options and options.get('ramp_scope')=='cycle' else a['age']
                                fraction=ramp_fraction(ramp_age,seconds,options.get('ramp_mode','linear'),options.get('ramp_steps',5)) if options else min(1,max(0,ramp_age/seconds))
                                cap_target=low+(cap_target-low)*fraction
                        # Descriptor samples are rounded to four decimals below;
                        # keep the peak on that same grid so full-amplitude
                        # samples can never round above a fractional ramp peak.
                        cap_target=round(cap_target,4)
                        entry[route]=max(entry[route],cap_target)
                        contributions[route+channel].append((r['priority'],cap_target,cap_target*amplitudes[0],r['name'],[cap_target*v for v in amplitudes],frequencies,a.get('remaining',float('inf')),route=='pulse' and a['token'].startswith('status:'),r['key'] in ('defeat_hold','cg_hold')))
            display.append(entry)
        for key,parts in contributions.items():
            route='pulse' if key.startswith('pulse') else 'vibration';cap=profile[route+'_cap_'+key[-1].lower()]
            peak,value,_,selected=mix_parts(parts,profile['mix'])
            result['selected'][key]=selected
            result['clipped']|=peak>cap
            result[key]=round(min(cap,value),2);result['peaks'][key]=round(min(cap,peak),2)
            if parts and cap>0:
                samples=[];frequencies=[];frame_peak=0.
                for q in range(4):
                    eligible=[part for part in parts if part[6]>q*.025]
                    if not eligible:samples.append(0.);frequencies.append(30.);continue
                    pk,v,freq,_=mix_parts(eligible,profile['mix'],q)
                    frame_peak=max(frame_peak,min(cap,pk));samples.append(round(min(cap,v),4));frequencies.append(freq)
                if frame_peak>0:result[route+'_stream'][key[-1]]=dict(peak=frame_peak,samples=samples,frequencies=frequencies)
            self.traces[key]=(self.traces[key]+[result[key]/100])[-64:]
        result.update(generated_at=now,active=display,traces=deepcopy(self.traces),reason=('匹配 '+str(len(display))+' 条规则'+(' · 已限幅' if result['clipped'] else '')) if display else '当前没有匹配规则')
        if not gallery and (s.get('hp') or {}).get('current')==0:
            result['reason']=('零血受制 · CG 未确认 · ' if zero_hp_capture(s) else '零血阶段 · CG 未确认 · ')+result['reason']
        if not gallery and death_penalty_stage(s) and penalty_rule.get('death_mode')=='timed' and self.death_started_at is not None and now-self.death_started_at>=penalty_rule['death_seconds']:
            result['reason']=('本次 CG 定时反馈已结束 · ' if cg_config and not cg_config.get('inherit_death',True) else '本次死亡定时惩罚已结束 · ')+result['reason']
        return result
    def evaluate_gallery(self,s,profile,waves,now,enabled,emergency,*,vibration_waves=None,route=None):
        config=profile.get('gallery') or {}
        episode=self.gallery_clock.update(s,config,now)
        gate=gallery_gate(s,now,config)
        reason='急停已锁定' if emergency else gate or ('图鉴输出已暂停' if not enabled else episode['reason'])
        if emergency:self.gallery_clock.reset()
        if reason or not episode['ready']:return self.blank(reason or episode['reason'],'图鉴独立反馈')
        rule=deepcopy(config['rule']);rule.update(key='cg_hold',name='图鉴回放反馈',death_mode='until_end')
        if route:rule[('vibration' if route=='pulse' else 'pulse')+'_enabled']=False
        active=[dict(rule=rule,token='gallery',detail=episode['name'],level=1,stack=0,amount=0.,age=episode['age'],
                     seed=episode['seed'],remaining=float('inf'),cg_options=config['routes'])]
        result=self.render(s,profile,waves,active,now,vibration_waves,gallery=True)
        result.update(source='图鉴独立反馈',gallery_age=episode['age'])
        return result

    def trigger(self,key,amount,profile,now):
        # Retired MP rules must stay inert even in unsanitized legacy profiles.
        if key in ('mp_loss','grab_mp_loss','escape','hp0'):return
        r=profile['rules'].get(key)
        if not r or not r['enabled'] or now<self.cooldowns.get(key,-1):return
        self.bursts[key]=dict(rule=deepcopy(r),amount=amount,start=now,until=now+r['duration'])
        self.cooldowns[key]=now+r['cooldown']

def demo_state(case,elapsed,now):
    s=dict(live=True,valid=True,sampled_at=now,session='demo',pid=-1,player=-1,scene_id=-1,scene='样例演示',sample_id=int(elapsed*10),
           hp={'current':100,'max':100},mp={'current':100,'max':100},paused=False,loading=False,bound=False,broken=False,abnormals=[],time_scale=1)
    if case in ('grab_hp','grab_mp'):
        s.update(bound=True,binder='演示敌人');s['hp' if case=='grab_hp' else 'mp']['current']=100-10*int((elapsed%10)/2)
    elif case=='abnormals':s['abnormals']=[{'name':'Defilement','level':3},{'name':'Poison','level':1},{'name':'Slow','level':2}]
    elif case=='flow':s['flow']=dict(valid=True,key='DEMO|flow',name='演出样例',playing=True,paused=False,run=1,label='阶段 '+str(1+int(elapsed/4)%3),timeline_time=elapsed%12,elapsed=elapsed)
    return s
