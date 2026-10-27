"""Per-channel inclusion filter; it never enables a rule or changes its routing."""
MODES=('damage','cg','both')

def defaults():return {r:{c:'both' for c in 'AB'} for r in ('pulse','vibration')}

def planner_copy(profile):
    """Copy only branches a route filter edits, preserving the source profile."""
    result=dict(profile)
    for group in ('rules','abnormals'):
        result[group]={key:dict(rule) for key,rule in profile[group].items()}
    if isinstance(profile.get('cg'),dict):
        result['cg']=dict(profile['cg'],rule=dict(profile['cg'].get('rule') or {}))
    return result

def sanitize(raw):
    result=defaults()
    if isinstance(raw,dict):
        for route in result:
            source=raw.get(route,{})
            if isinstance(source,dict):
                for channel in 'AB':
                    if source.get(channel) in MODES:result[route][channel]=source[channel]
    return result

def allows(profile,route,channel,rule_key):
    mode=profile.get('channel_feedback',{}).get(route,{}).get(channel,'both')
    cg=rule_key in ('defeat_hold','cg_hold')
    # The combat side includes damage, grabbing, clothing and enabled statuses.
    return mode=='both' or (mode=='cg' if cg else mode=='damage')
