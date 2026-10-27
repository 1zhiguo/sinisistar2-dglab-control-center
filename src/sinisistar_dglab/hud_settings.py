"""Display-only settings for one four-channel, player-facing output strip."""
from copy import deepcopy
import math

HUD_DEFAULTS=dict(version=3,enabled=True,scale=100,opacity=82,anchor='bottom_center',x=50,y=96,layout='player',hide_dialogue=True,
                  pulse_a=True,pulse_b=True,ovc_a=True,ovc_b=True,show_numbers=True,show_waveforms=True,
                  show_pulse=True,show_vibration=True,show_a=True,show_b=True,
                  show_resources=False,show_abnormals=False,show_capture=False,show_events=False)
ANCHORS=('auto','top_left','top_center','top_right','middle_left','middle_center','middle_right','bottom_left','bottom_center','bottom_right','custom')
CHANNELS=('pulse_a','pulse_b','ovc_a','ovc_b')

def sanitize_hud(raw):
    out=deepcopy(HUD_DEFAULTS)
    if not isinstance(raw,dict):return out
    if type(raw.get('enabled')) is bool:out['enabled']=raw['enabled']
    current=raw.get('version')==3
    previous=raw.get('version')==2
    for key,low,high in [('scale',70,150),('opacity',30,100)]:
        v=raw.get(key)
        if type(v) in (int,float) and math.isfinite(v):out[key]=round(max(low,min(high,v)))
    if current or previous:
        for key in ('x','y'):
            v=raw.get(key)
            if type(v) in (int,float) and math.isfinite(v):out[key]=round(max(0,min(100,v)))
        if raw.get('anchor') in ANCHORS:out['anchor']=raw['anchor']
        for key in ('show_numbers','show_waveforms','hide_dialogue'):
            if type(raw.get(key)) is bool:out[key]=raw[key]
    if current:
        for key in CHANNELS:
            if type(raw.get(key)) is bool:out[key]=raw[key]
    elif previous:
        out.update(pulse_a=raw.get('show_pulse') is not False and raw.get('show_a') is not False,
                   pulse_b=raw.get('show_pulse') is not False and raw.get('show_b') is not False,
                   ovc_a=raw.get('show_vibration') is not False and raw.get('show_a') is not False,
                   ovc_b=raw.get('show_vibration') is not False and raw.get('show_b') is not False)
    out.update(show_pulse=out['pulse_a'] or out['pulse_b'],show_vibration=out['ovc_a'] or out['ovc_b'],
               show_a=out['pulse_a'] or out['ovc_a'],show_b=out['pulse_b'] or out['ovc_b'])
    return out
