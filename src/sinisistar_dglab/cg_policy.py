"""Independent CG output selection. No transport or mutable random generator."""
from copy import deepcopy
import hashlib,math,json
from pathlib import Path

PROGRESSIVE_WAVES={
    'pulse':('official_breath','official_heartbeat','death_penalty','official_tide','death_ramp'),
    'vibration':('ovc_beat','ovc_soothe','vib_trapezoid','ovc_trapezoid','ovc_surf_wave')}
ALTERNATE_WAVES={
    'pulse':('official_ripple','official_bouncy','official_gradual','official_pulsating','official_heartbeat'),
    'vibration':('ovc_soothe','ovc_beat','ovc_surf_wave','vib_trapezoid','ovc_trapezoid')}
_FACTORY_CATALOGS={r:json.loads((Path(__file__).parent/'assets'/name).read_text(encoding='utf8'))
    for r,name in (('pulse','ricca-pulse-presets.json'),('vibration','ovc-presets.json'))}

def progressive_queue(route,catalog=None,channel='A'):
    """One minute, five existing rhythms, with explicit increasing amplitude weights."""
    waves={w['key']:w for w in (catalog if catalog is not None else _FACTORY_CATALOGS[route])}
    return [dict(wave=key,seconds=12.,period=waves.get(key,{}).get('native_period') or 2.,scale=scale)
            for key,scale in zip((ALTERNATE_WAVES if channel=='B' else PROGRESSIVE_WAVES)[route],(.35,.5,.65,.8,1.))]

def number(value,low,high,fallback):
    try:value=float(value)
    except (ValueError,TypeError):return fallback
    return max(low,min(high,value)) if math.isfinite(value) else fallback

def make_cg(death,*,inherit=True,split=False):
    rule=deepcopy(death);rule.update(key='cg_hold',name='CG 观看反馈',pulse_max=False,vibration_max=False)
    routes={r:dict(mode='fixed',loop=True,end='hold',ramp_mode='linear',ramp_scope='episode',ramp_steps=5,
                   queue=[dict(wave=rule[r+'_wave'],seconds=10.,period=rule[r+'_period'])]) for r in ('pulse','vibration')}
    if split:
        routes={r:{c:default_channel(r,c,rule) for c in 'AB'} for r in routes}
    return dict(version=2 if split else 1,inherit_death=inherit,same_hp_enabled=True,same_hp_timeout=3.,rule=rule,routes=routes)


def default_channel(route,channel,rule):
    queue=progressive_queue(route,channel=channel)
    return dict(mode='sequence',loop=True,end='hold',ramp_mode='linear',ramp_scope='cycle',ramp_steps=5,
        ramp_seconds=60.,wave=queue[0]['wave'],period=queue[0]['period'],frequency=rule['pulse_frequency'],queue=queue)


def channel_options(routes,route,channel):
    """Canonical A/B configuration, with support for unsaved legacy planners."""
    route_options=(routes or {}).get(route)
    if not isinstance(route_options,dict):return None
    return route_options.get(channel,route_options)


def sanitize_options(raw,default):
    target=deepcopy(default)
    if not isinstance(raw,dict):return target
    for key,allowed in [('mode',('fixed','sequence','shuffle')),('end',('hold','stop')),('ramp_mode',('linear','ease_in','ease_out','steps','constant')),('ramp_scope',('episode','cycle','wave'))]:
        if raw.get(key) in allowed:target[key]=raw[key]
    target['loop']=raw.get('loop',target['loop']) is True
    for key,low,high in [('ramp_steps',2,20),('ramp_seconds',.1,1800),('period',.1,60),('frequency',1,100)]:
        target[key]=number(raw.get(key,target[key]),low,high,target[key])
    target['ramp_steps']=int(target['ramp_steps'])
    if isinstance(raw.get('wave'),str):target['wave']=raw['wave'][:100]
    if isinstance(raw.get('queue'),list):
        target['queue']=[dict(wave=x['wave'][:100],seconds=number(x.get('seconds'),.1,600,10),period=number(x.get('period'),.1,60,2),scale=number(x.get('scale',1),0,1,1))
            for x in raw['queue'][:32] if isinstance(x,dict) and isinstance(x.get('wave'),str) and x['wave']]
    return target

def sanitize_cg(raw,death,sanitize_rule):
    c=make_cg(death,split=True)
    if not isinstance(raw,dict):return c
    c['inherit_death']=raw.get('inherit_death',True) is True
    c['same_hp_enabled']=raw.get('same_hp_enabled',True) is True
    c['same_hp_timeout']=number(raw.get('same_hp_timeout',3),.5,30,3)
    c['rule']=sanitize_rule(raw.get('rule'),c['rule']);c['rule'].update(key='cg_hold',name='CG 观看反馈',pulse_max=False,vibration_max=False)
    source=raw.get('rule') if isinstance(raw.get('rule'),dict) else {}
    for route in ('pulse','vibration'):
        key=route+'_ramp_seconds';c['rule'][key]=number(source.get(key,c['rule'][key]),.1,1800,c['rule'][key])
        r=(raw.get('routes') or {}).get(route,{}) if isinstance(raw.get('routes'),dict) else {}
        if not isinstance(r,dict):continue
        if raw.get('version')==2:
            for channel in 'AB':c['routes'][route][channel]=sanitize_options(r.get(channel),c['routes'][route][channel])
        elif r:
            # Keep a custom legacy A strategy; B starts with its own factory
            # loop. Old factory queues now play automatically without a loader.
            keys=[x.get('wave') for x in r.get('queue',[]) if isinstance(x,dict)]
            expected=c['routes'][route]['A']['queue']
            factory=(keys==list(PROGRESSIVE_WAVES[route]) and all(
                all(abs(number(x.get(k),0,600,-1)-y[k])<1e-6 for k in ('seconds','period','scale'))
                for x,y in zip(r['queue'],expected))) or (len(keys)<=1 and not any(str(k).startswith(('custom_','vib_custom_')) for k in keys))
            if str(c['rule'][route+'_wave']).startswith(('custom_','vib_custom_')):factory=False
            if not factory or r.get('mode') in ('sequence','shuffle'):
                source=dict(r,wave=c['rule'][route+'_wave'],period=c['rule'][route+'_period'],ramp_seconds=c['rule'][route+'_ramp_seconds'])
                c['routes'][route]['A']=sanitize_options(source,c['routes'][route]['A'])
    return c

def effective_cg(profile):
    raw=profile.get('cg') or {}
    if raw.get('inherit_death',True):
        c=deepcopy(raw) if raw.get('version')==2 else make_cg(profile['rules']['defeat_hold'])
        c['same_hp_enabled']=raw.get('same_hp_enabled',True) is True
        c['same_hp_timeout']=number(raw.get('same_hp_timeout',3),.5,30,3)
        c['rule']=deepcopy(profile['rules']['defeat_hold'])
        return c
    return deepcopy(raw)

def cg_stage(s):
    from .penalty_flows import recoverable_penalty
    from .same_hp import same_hp_flow
    f=s.get('flow') or {}
    return same_hp_flow(s,float('inf')) or recoverable_penalty(s) or (f.get('valid') is True and f.get('playing') is True and f.get('defeat_confirmed') is True)

def select_wave(options,rule,route,age,seed):
    """Return (wave key, period, local wave age, cycle age, description), or None.

    Shuffle is a deterministic permutation per CG/route/cycle. Every item plays
    once per round, so variable durations have a bounded, exact cycle length.
    """
    age=max(0,age)
    if options.get('mode','fixed')=='fixed':return options.get('wave',rule[route+'_wave']),options.get('period',rule[route+'_period']),age,age,''
    selected=select_queue_item(options,route,age,seed)
    if selected is None:return None
    item,index,local,within,cycle=selected
    return item['wave'],item['period'],local,within,f'队列 {index+1}/{len(options["queue"])} · 第 {cycle+1} 轮'

def select_queue_item(options,route,age,seed):
    age=max(0,age);queue=options.get('queue') or []
    if not queue:return None
    total=sum(x['seconds'] for x in queue);cycle=math.floor(age/total+1e-9) if options.get('loop',True) else 0
    within=max(0,age-cycle*total) if options.get('loop',True) else age
    order=list(range(len(queue)))
    if options.get('mode')=='shuffle':
        order.sort(key=lambda i:hashlib.sha256(f'{seed}|{route}|{cycle}|{i}'.encode()).digest())
    if within>=total:
        if options.get('end')=='stop':return None
        index=order[-1];item=queue[index];local=within-(total-item['seconds'])
    else:
        local=within;index=order[-1]
        for index in order:
            if local<queue[index]['seconds']-1e-9:break
            local=max(0,local-queue[index]['seconds'])
        item=queue[index]
    return item,index,local,within,cycle

def queue_scale(options,route,age,seed):
    if options.get('mode','fixed')=='fixed':return 1.
    selected=select_queue_item(options,route,age,seed)
    return number(selected[0].get('scale',1),0,1,1) if selected else 0.

def ramp_fraction(age,seconds,mode='linear',steps=5):
    if mode=='constant':return 1.
    x=max(0,min(1,age/max(.1,seconds)))
    if mode=='ease_in':return x*x
    if mode=='ease_out':return 1-(1-x)*(1-x)
    if mode=='steps':return math.floor(x*steps)/steps
    return x
