"""Replay recorded observer files through generic evidence and both planners only.

No device transport is imported/created, and no game/plugin files are modified.
"""
from pathlib import Path
from datetime import datetime,timezone
import argparse,json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from sinisistar_dglab.locked_hp import LockedHpEvidence,locked_hp_penalty
from sinisistar_dglab.monitoring import parse_time
from sinisistar_dglab.simulation import default_profile,VIBRATION_WAVES
from sinisistar_dglab.backend import WAVES
from sinisistar_dglab.pulse import PulsePlanner
from sinisistar_dglab.ovc_plan import OvcPlanner
from sinisistar_dglab.penalty_flows import flow_classification
from sinisistar_dglab.scripted_go import scripted_go_penalty

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--capture-dir',type=Path,required=True);args=parser.parse_args()
    folder=args.capture_dir;states=[json.loads(x) for x in (folder/'states.jsonl').read_text(encoding='utf-8').splitlines()]
    callbacks=[json.loads(x) for x in (folder/'callbacks.jsonl').read_text(encoding='utf-8').splitlines()]
    if (folder/'prelude-callbacks.json').exists():callbacks+=json.loads((folder/'prelude-callbacks.json').read_text(encoding='utf-8'))
    callbacks=list({(e.get('session'),e.get('sequence')):e for e in callbacks}.values());callbacks.sort(key=lambda e:parse_time(e['utc']))
    profile=default_profile()
    for r in profile['rules'].values():r['enabled']=False
    profile['rules']['defeat_hold'].update(enabled=True,pulse_channel='AB',pulse_strength_a=30,pulse_strength_b=40,
        pulse_start_strength_a=10,pulse_start_strength_b=20,pulse_ramp_seconds=3,vibration_enabled=True,vibration_channel='AB',
        vibration_start_strength_a=30,vibration_start_strength_b=40,vibration_strength_a=90,vibration_strength_b=120,vibration_ramp_seconds=3)
    profile.update(pulse_cap_a=60,pulse_cap_b=60,vibration_cap_a=150,vibration_cap_b=150)
    tracker=LockedHpEvidence();pulse=PulsePlanner();ovc=OvcPlanner();cursor=0;edges=[];previous=False;active_frames=0;known=0;playerless_outputs=0;unverified_playerless_outputs=0
    for raw in states:
        wall=parse_time(raw['utc']);batch=[]
        while cursor<len(callbacks) and parse_time(callbacks[cursor]['utc'])<=wall:
            batch.append(callbacks[cursor]);cursor+=1
        now=raw['sampled_at'];s=tracker.update(raw,batch,now=now,wall_now=wall)
        active=locked_hp_penalty(s);f=s.get('flow') or {}
        if active!=previous:
            edges.append(dict(utc=s['utc'],active=active,hp=(s.get('hp') or {}).get('current'),scene=s.get('scene'),flow=f.get('name'),count=s['feedback_evidence']['locked_hp_count']))
        previous=active;active_frames+=active
        known+=bool(flow_classification(s.get('scene_id'),f)[0])
        pp=pulse.update(s,profile,WAVES,now=now,enabled=True);vp=ovc.update(s,profile,VIBRATION_WAVES,now=now,enabled=True)
        if not s.get('valid') and (any(pp['pulse_stream'].values()) or any(vp['vibration_stream'].values())):
            playerless_outputs+=1
            if not scripted_go_penalty(s):unverified_playerless_outputs+=1
        if active:
            assert pp['pulse_stream']['A'] is not None and vp['vibration_stream']['B'] is not None
        if (s.get('hp') or {}).get('current',0)>1:
            assert not any(pp['pulse_stream'].values()) and not any(vp['vibration_stream'].values())
    assert any(e['active'] for e in edges),'No 1-HP evidence found in this recording'
    assert not unverified_playerless_outputs
    result=dict(checked_utc=datetime.now(timezone.utc).isoformat(),passed=True,frames=len(states),active_frames=active_frames,edges=edges,
        known_flow_rule_matches=known,playerless_output_frames=playerless_outputs,unverified_playerless_output_frames=unverified_playerless_outputs,device_services_started=False,
        note='Replay covers live-player locked HP and playerless 1-HP GO scenes; other playerless snapshots remain blocked.')
    target=folder/'locked-hp-replay.json';target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False));print(target)
if __name__=='__main__':main()
