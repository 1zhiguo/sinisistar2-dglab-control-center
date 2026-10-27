"""Editable intensity presets. Applying them preserves waves and routing."""
from copy import deepcopy
import math
from .status_policy import positive_status,normalize_abnormal

PRESET_NAMES={'low':'低','medium':'中','high':'高'}

def sync_cg_strengths(profile,values):
    """Preset intensity only; preserve playback, queues, routing and switches."""
    for scope in ('cg','gallery'):
        rule=(profile.get(scope) or {}).get('rule')
        if not isinstance(rule,dict):continue
        for route,prefix in (('pulse','pulse'),('vibration','ovc')):
            rule[route+'_max']=False
            for channel in 'ab':
                rule[route+'_strength_'+channel]=values[prefix+'_death_'+channel]
                rule[route+'_start_strength_'+channel]=values[prefix+'_death_start_'+channel]
            rule[route+'_strength']=max(values[prefix+'_death_'+c] for c in 'ab')
            rule[route+'_start_strength']=min(values[prefix+'_death_start_'+c] for c in 'ab')

def current_values(profile):
    """Read the actual strategy, including custom edits made on other pages."""
    result={};rules=profile['rules'];death=rules['defeat_hold'];grab=rules['grab_hold']
    for route,prefix in (('pulse','pulse'),('vibration','ovc')):
        result[prefix+'_cap']=profile[route+'_cap_a']
        for field,key in (('damage','hp_loss'),('break','break'),('grab','grab_hold')):result[prefix+'_'+field]=rules[key][route+'_strength']
        result[prefix+'_grab_start']=grab[route+'_start_strength'] if grab[route+'_start_strength'] is not None else grab[route+'_strength']
        for channel in 'ab':
            high=death[route+'_strength_'+channel]
            if high is None:high=death[route+'_strength']
            low=death[route+'_start_strength_'+channel]
            if low is None:low=death[route+'_start_strength']
            result[prefix+'_death_'+channel]=high;result[prefix+'_death_start_'+channel]=min(high,high if low is None else low)
    result.update(grab_ramp_seconds=grab['pulse_ramp_seconds'],death_ramp_seconds=death['pulse_ramp_seconds'],
                  feedback_seconds=rules['hp_loss']['duration'],death_mode=death['death_mode'],death_seconds=death['death_seconds'])
    return result

def edit_current(profile,changes):
    """Apply only edited fields; preserve all other waves, routes and rule details."""
    result=deepcopy(profile);values=current_values(profile);values.update(changes)
    clean=sanitize_presets({'low':values})['low'];rules=result['rules'];death=rules['defeat_hold']
    for key in changes:
        if key not in clean:continue
        value=clean[key]
        if key in ('death_mode','death_seconds'):death[key]=value
        elif key=='feedback_seconds':
            for name in ('hp_loss','grab_hp_loss','break'):rules[name]['duration']=value
        elif key in ('grab_ramp_seconds','death_ramp_seconds'):
            rule=rules['grab_hold'] if key.startswith('grab') else death
            for route in ('pulse','vibration'):rule[route+'_ramp_seconds']=value
        else:
            prefix,field=key.split('_',1);route='vibration' if prefix=='ovc' else 'pulse'
            if field=='cap':
                for channel in 'ab':result[route+'_cap_'+channel]=value
            elif field in ('damage','break'):
                for name in (('hp_loss','grab_hp_loss') if field=='damage' else ('break',)):
                    rules[name][route+'_strength']=value;rules[name][route+'_gain']=0
            elif field in ('grab','grab_start'):rules['grab_hold'][route+('_strength' if field=='grab' else '_start_strength')]=value
            elif field.startswith('death_'):
                suffix=field[len('death_'):];death[route+('_start_strength_'+suffix[-1] if suffix.startswith('start_') else '_strength_'+suffix)]=value
    result['quick_active_preset']=''
    return result

def range_start(peak,ovc=False):
    return min(peak,max(10,int(peak/20)*10)) if ovc and peak>0 else int(peak/2)

def default_presets():
    # Each tier includes its own software limits and fixed / rising feedback.
    keys=('pulse_cap','pulse_damage','pulse_break','pulse_grab_start','pulse_grab','pulse_abnormal','pulse_stack_bonus','pulse_death_start','pulse_death',
          'ovc_cap','ovc_damage','ovc_break','ovc_grab_start','ovc_grab','ovc_abnormal','ovc_stack_bonus','ovc_death_start','ovc_death')
    values={
        'low':   (30,20,15,10,25,10,10,20,30, 30,20,10,10,20,0,0,20,30),
        'medium':(60,35,25,20,45,10,10,40,55, 60,40,20,20,50,0,0,40,60),
        'high':  (90,55,35,30,70,10,10,60,80, 90,50,40,40,70,0,0,60,80)}
    result={}
    for name,row in values.items():
        item=dict(zip(keys,row))
        for route in ('pulse','ovc'):
            value=item.pop(route+'_death');start=item.pop(route+'_death_start')
            for channel in 'ab':
                item[route+'_death_'+channel]=value
                item[route+'_death_start_'+channel]=start
        item.update(grab_ramp_seconds=5.,death_ramp_seconds=3.,feedback_seconds=1.5,death_mode='until_end',death_seconds=3.)
        result[name]=item
    return result

def needs_ovc_preset_upgrade(raw):
    return (isinstance(raw,dict) and isinstance(raw.get('quick_presets'),dict)
            and (type(raw.get('version')) is not int or raw['version']<11))


def upgrade_ovc_presets(profile):
    """Replace the old OVC tiers, preserving custom current strategies and CG."""
    for name,values in default_presets().items():
        profile['quick_presets'][name].update({k:v for k,v in values.items() if k.startswith('ovc_')})
    active=profile['quick_active_preset']
    if active:
        # Apply only OVC fields: Pulse, durations, waves and routing stay intact.
        updated=apply_preset(profile,active)
        for key in ('vibration_cap_a','vibration_cap_b'):profile[key]=updated[key]
        for name in ('hp_loss','grab_hp_loss','break','grab_hold','defeat_hold'):
            profile['rules'][name].update({k:v for k,v in updated['rules'][name].items()
                if k.startswith('vibration_') and ('strength' in k or k.endswith('_gain'))})


def sanitize_presets(raw):
    presets=default_presets()
    if not isinstance(raw,dict):return presets
    for name,defaults in presets.items():
        source=raw.get(name,{})
        if not isinstance(source,dict):continue
        for key,fallback in defaults.items():
            if key=='death_mode':
                defaults[key]=source.get(key) if source.get(key) in ('until_end','timed') else fallback
                continue
            try:value=float(source.get(key,fallback))
            except (TypeError,ValueError):continue
            if not math.isfinite(value):continue
            if key.endswith('ramp_seconds') or key in ('feedback_seconds','death_seconds'):
                defaults[key]=round(max(.1,min(30 if key=='feedback_seconds' else 120,value)),1);continue
            maximum=200 if key.startswith('ovc_') and not key.endswith('stack_bonus') else 100
            value=max(0,min(maximum,value));step=10 if key.startswith('ovc_') else 1
            defaults[key]=int(value//step*step)
        for route in ('pulse','ovc'):
            for low,high in [(route+'_grab_start',route+'_grab')]+[(route+'_death_start_'+c,route+'_death_'+c) for c in 'ab']:
                if low not in source:defaults[low]=range_start(defaults[high],route=='ovc')
                defaults[low]=min(defaults[low],defaults[high])
        defaults.update(pulse_abnormal=10,pulse_stack_bonus=10,ovc_abnormal=0,ovc_stack_bonus=0)
    return presets

def apply_preset(profile,name,*,death_only=False):
    if name not in PRESET_NAMES:raise ValueError('Unknown intensity preset')
    result=deepcopy(profile);values=sanitize_presets(profile.get('quick_presets'))[name]
    death=result['rules']['defeat_hold']
    death.update(death_mode=values['death_mode'],death_seconds=values['death_seconds'])
    for route,prefix in (('pulse','pulse'),('vibration','ovc')):
        death[route+'_max']=False
        for channel in 'ab':
            death[route+'_strength_'+channel]=values[prefix+'_death_'+channel]
            death[route+'_start_strength_'+channel]=values[prefix+'_death_start_'+channel]
        death[route+'_ramp_seconds']=values['death_ramp_seconds']
    if death_only:result['quick_active_preset']='';return result
    sync_cg_strengths(result,values)
    result['quick_active_preset']=name
    for route,prefix in (('pulse','pulse'),('vibration','ovc')):
        for key,value in (('hp_loss','damage'),('grab_hp_loss','damage'),('break','break'),('grab_hold','grab')):
            rule=result['rules'][key];rule[route+'_strength']=values[prefix+'_'+value];rule[route+'_gain']=0
        result['rules']['grab_hold'][route+'_start_strength']=values[prefix+'_grab_start']
        result['rules']['grab_hold'][route+'_ramp_seconds']=values['grab_ramp_seconds']
        result[route+'_stack_bonus']=values[prefix+'_stack_bonus']
        for channel in 'ab':result[route+'_cap_'+channel]=values[prefix+'_cap']
        for status,rule in result['abnormals'].items():
            if not positive_status(status):rule[route+'_strength']=values[prefix+'_abnormal']
    for key in ('hp_loss','grab_hp_loss','break'):result['rules'][key]['duration']=values['feedback_seconds']
    for rule in result['abnormals'].values():normalize_abnormal(rule)
    result['pulse_abnormal_base']=values['pulse_abnormal']
    return result
