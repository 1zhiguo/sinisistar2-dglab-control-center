from copy import deepcopy
from sinisistar_dglab.cg_playback import REGISTRY
from sinisistar_dglab.telemetry import BUILD

ROW=next(r for r in REGISTRY.rows.values() if r['take']=='BreastHaanja' and 7 in r['scene_ids'])
EVENT=next(e for e in ROW['events'] if e['role']=='main')

def event_state(now=10):
    return dict(source='bepinex',fingerprint=BUILD,session='cg-no-hp',pid=123,player=0,live=True,valid=False,
        sampled_at=now,sample_id=int(now*1000),scene_id=7,scene='Monastery',paused=False,loading=False,
        hp=dict(current=100,max=100),mp=dict(current=100,max=100),bound=False,abnormals=[],time_scale=1,event_playing=True,
        flow=dict(valid=True,playing=True,paused=False,type=EVENT['type'],name=EVENT['path'].split('/')[-1],run=1),
        cg_playback=dict(schema=1,available=True,hp_used=False,event=dict(object=888,playing=True,type=EVENT['type'],path=EVENT['path']),animators=[]))

def animator():
    return dict(available=True,active=True,object=4567,path='Root/Target/Enemy/CCP_Enemy/Enemy/Root',controller='Enemy',
                normalized_time=.3,length=2.,short_hash=123,full_hash=234,matched_names=['Hold_Loop'])
