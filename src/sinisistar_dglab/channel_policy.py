"""Per-channel inclusion filter; it never enables a rule or changes its routing."""
MODES=('damage','cg','both')

def defaults():return {r:{c:'both' for c in 'AB'} for r in ('pulse','vibration')}

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
