"""Local test copy: keep user strength/waves while excluding physical transports."""
from copy import deepcopy
from pathlib import Path
import json

def prepare_live(root):
    """Real APP test copy. Preserve policy/limits; never start a mock APP."""
    root=Path(root);source=root/'artifacts/settings.json';target=root/'artifacts/cg-live-ablation/settings.json'
    try:
        previous=Path(json.loads((root/'artifacts/cg-realplay-current.json').read_text(encoding='utf-8'))['directory']).resolve()
        if previous.is_relative_to((root/'artifacts').resolve()) and (previous/'settings.json').is_file():source=previous/'settings.json'
    except (OSError,ValueError,KeyError,TypeError):pass
    if target.is_file():source=target
    try:data=deepcopy(json.loads(source.read_text(encoding='utf-8')))
    except (OSError,ValueError):data={}
    from .simulation import sanitize_profile
    profile=sanitize_profile(data.get('simulation',{}));profile['cg_detection_mode']='playback_only'
    connection=dict(data.get('connections') or {})
    if connection.get('pulse_backend') not in ('v3','v4'):connection['pulse_backend']='v4'
    data.update(simulation=profile,connections=connection,tutorial=dict(version=2,step=4,seen=True,completed=True))
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    return target,connection['pulse_backend']

def prepare(root):
    root=Path(root);source=root/'artifacts/settings.json'
    target=root/'artifacts/cg-ablation/settings.json'
    try:
        rounds=target.parent/'cg-batch';key=json.loads((rounds/'current.json').read_text(encoding='utf-8'))['round']
        if isinstance(key,str) and Path(key).name==key and key not in ('.','..'):
            active=json.loads((rounds/key/'round.json').read_text(encoding='utf-8'))
            if active.get('status') in ('recording','paused') and target.is_file():source=target
    except (OSError,ValueError,KeyError,TypeError):pass
    try:data=json.loads(source.read_text(encoding='utf-8'))
    except (OSError,ValueError):data={}
    from .simulation import sanitize_profile
    data=deepcopy(data);p=sanitize_profile(data.get('simulation',{}));p['cg_detection_mode']='playback_only'
    p['gallery']['rule']['enabled']=True
    if p['cg'].get('inherit_death',True):p['rules']['defeat_hold']['enabled']=True
    else:p['cg']['rule']['enabled']=True
    p['channel_feedback']={r:{c:'both' for c in 'AB'} for r in ('pulse','vibration')}
    for rule in (p['gallery']['rule'],p['cg']['rule'] if not p['cg'].get('inherit_death',True) else p['rules']['defeat_hold']):
        rule.update(pulse_enabled=True,pulse_channel='AB',vibration_enabled=True,vibration_channel='AB')
    data.update(simulation=p,connections=dict(pulse_backend='mock',v3_port=0,v4_port=0,lan_ip='127.0.0.1',auto_enable=True),
        tutorial=dict(version=2,step=4,seen=True,completed=True))
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');return target
