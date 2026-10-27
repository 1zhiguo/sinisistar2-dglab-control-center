"""Replay actual local telemetry through generic evidence and pure planners.

Old files are explicit offline fixtures only: no device transport is imported.
"""
from pathlib import Path
import argparse,csv,json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from sinisistar_dglab.same_hp import SameHpFlowEvidence,same_hp_flow
from sinisistar_dglab.monitoring_time import parse_callback_time
from sinisistar_dglab.backend import WAVES
from sinisistar_dglab.simulation import initial_profile,VIBRATION_WAVES
from sinisistar_dglab.cg_policy import make_cg
from sinisistar_dglab.pulse import PulsePlanner
from sinisistar_dglab.ovc_plan import OvcPlanner

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--capture-dir',required=True,type=Path);args=ap.parse_args()
    folder=args.capture_dir;states=[json.loads(x) for x in (folder/'states.jsonl').read_text(encoding='utf8').splitlines()]
    callbacks=sorted([json.loads(x) for x in (folder/'callbacks.jsonl').read_text(encoding='utf8').splitlines()],key=lambda x:parse_callback_time(x['utc']))
    p=initial_profile()
    for r in p['rules'].values():r['enabled']=False
    for r in p['abnormals'].values():r['enabled']=False
    p['cg']=make_cg(p['rules']['defeat_hold'],inherit=False);p['cg'].update(same_hp_enabled=True,same_hp_timeout=3.)
    p['cg']['rule'].update(enabled=True,pulse_channel='AB',vibration_channel='AB',pulse_strength_a=20,pulse_strength_b=25,
        pulse_start_strength_a=10,pulse_start_strength_b=15,pulse_ramp_seconds=10,vibration_strength_a=60,vibration_strength_b=90,
        vibration_start_strength_a=20,vibration_start_strength_b=30,vibration_ramp_seconds=10,death_mode='until_end')
    tracker=SameHpFlowEvidence();pulse=PulsePlanner();ovc=OvcPlanner();cursor=0;last=False;edges=[];samples=[];active=0
    for raw in states:
        wall=parse_callback_time(raw['utc']);batch=[]
        while cursor<len(callbacks) and parse_callback_time(callbacks[cursor]['utc'])<=wall:batch.append(callbacks[cursor]);cursor+=1
        now=raw['sampled_at'];s=tracker.update(raw,batch,now=now,wall_now=wall)
        a=pulse.update(s,p,WAVES,now=now,enabled=True);b=ovc.update(s,p,VIBRATION_WAVES,now=now,enabled=True)
        matched=same_hp_flow(s);active+=int(matched)
        samples.append(dict(utc=raw['utc'],scene=raw.get('scene'),hp=(raw.get('hp') or {}).get('current'),playing=raw.get('event_playing'),
            evidence=matched,pulse_a=a['peaks'].get('pulseA',0),pulse_b=a['peaks'].get('pulseB',0),ovc_a=b['peaks'].get('vibrationA',0),ovc_b=b['peaks'].get('vibrationB',0)))
        if matched!=last:
            edges.append(dict(samples[-1],kind='start' if matched else 'end',count=s['feedback_evidence']['same_hp_count']));last=matched
    report=dict(capture=str(folder),frames=len(states),same_hp_frames=active,edges=edges,
        peak_pulse=max((max(x['pulse_a'],x['pulse_b']) for x in samples),default=0),
        peak_ovc=max((max(x['ovc_a'],x['ovc_b']) for x in samples),default=0),
        actual_damage_notifications=[{k:e.get(k) for k in ('utc','before_hp','remain_hp','spend_hp','spend_mp')} for e in callbacks if e.get('event_type')=='damage_callback'],
        profile='Isolated replay: generic CG enabled, timeout 3 s, all other sources disabled',device_services_started=False,hardware_connected=False)
    (folder/'same-hp-replay.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    with (folder/'same-hp-replay.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(samples[0]) if samples else ['utc']);writer.writeheader();writer.writerows(samples)
    print(json.dumps(report,ensure_ascii=True))
if __name__=='__main__':main()
