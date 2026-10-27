"""Audit actual game-driven APP receipts alongside the live resource capture."""
from pathlib import Path
from collections import defaultdict,Counter
import argparse,json,statistics,html
parser=argparse.ArgumentParser();parser.add_argument('directory',type=Path);args=parser.parse_args();root=args.directory
events=[json.loads(line) for line in (root/'runtime-events.jsonl').read_text(encoding='utf-8').splitlines()]
streams=defaultdict(list);pipelines=defaultdict(list);game_events=Counter();profiles=[]
for r in events:
    d=r.get('data') or {};source=r.get('source','')
    if r.get('kind')=='profile_snapshot':profiles.append(source);continue
    if source.endswith('pipeline.jsonl'):pipelines[source.rsplit('\\',1)[0]].append(d)
    if 'telemetry' in source and isinstance(d,dict):game_events[d.get('event_type','unknown')]+=1
    if d.get('m')=='device.op' and (d.get('data') or {}).get('t')==0:
        op=d['data'];streams[(source.rsplit('\\',1)[0],op.get('s'),op.get('c'))].append(d)

def signature(p):
    s=p.get('source') or {};g=s.get('gallery') or {};flow=s.get('flow') or {}
    return (s.get('session'),s.get('pid'),s.get('scene_id'),g.get('enemy_id'),g.get('selected_index_raw'),g.get('take_name'),flow.get('key'),flow.get('run'))
def nearest(rows,t):return min(rows,key=lambda p:abs(p.get('at',0)-t)) if rows else {}
summary=dict(duration_seconds=json.loads((root/'metadata.json').read_text())['duration_seconds'],game_event_counts=dict(game_events),profiles=profiles,streams=[],cg_transitions=[])
for (session,slot,channel),items in streams.items():
    times=sorted(r['at'] for r in items);gaps=[(b-a)*1000 for a,b in zip(times,times[1:])];possible=[];transitions=[]
    route='pulse' if slot=='coyote' else 'ovc';stream='pulse_stream' if slot=='coyote' else 'vibration_stream';c='B' if channel else 'A'
    for a,b in zip(times,times[1:]):
        if b-a<=.25:continue
        pa=nearest(pipelines[session],a);pb=nearest(pipelines[session],b)
        reason_a=(pa.get(route) or {}).get('reason');reason_b=(pb.get(route) or {}).get('reason')
        wanted=lambda p:bool((p.get(route) or {}).get(stream,{}).get(c))
        stable=bool(pa and pb and signature(pa)==signature(pb) and wanted(pa) and wanted(pb) and not any(not wanted(p) for p in pipelines[session] if a<=p.get('at',0)<=b))
        row=dict(start_monotonic=a,end_monotonic=b,gap_ms=(b-a)*1000,reason_before=reason_a,reason_after=reason_b)
        (possible if stable else transitions).append(row)
    summary['streams'].append(dict(session=session,slot=slot,channel=c,received=len(items),first_monotonic=times[0],last_monotonic=times[-1],
        gap_median_ms=statistics.median(gaps) if gaps else None,gap_p95_ms=sorted(gaps)[int((len(gaps)-1)*.95)] if gaps else None,
        gap_max_ms=max(gaps,default=0),possible_steady_gaps=possible,transition_or_unconfirmed_gaps=transitions))
samples=[json.loads(line) for line in (root/'samples.jsonl').read_text(encoding='utf-8').splitlines()]
previous={};seen=set()
for row in samples:
    for name,ctx in row.get('context',{}).items():
        g=ctx.get('gallery') or {};cg=ctx.get('cg') or {}
        key=(ctx.get('scene'),g.get('enemyId'),g.get('selectedIndexRaw'),g.get('takeName'),g.get('phase'),tuple(cg.get('ids') or []))
        if previous.get(name)==key:continue
        previous[name]=key
        summary['cg_transitions'].append(dict(window=name,elapsed=row['elapsed'],utc=row['utc'],scene=ctx.get('scene'),gallery=g,cg=cg,
            pulse_reason=ctx.get('pulse_reason'),ovc_reason=ctx.get('ovc_reason'),pulse_armed=ctx.get('pulse_armed'),ovc_armed=ctx.get('ovc_armed')))
        if g.get('selectionActive'):seen.add((g.get('enemyId'),g.get('selectedIndexRaw')))
summary.update(numbered_gallery_cases=len(seen),received_wave_packets=sum(x['received'] for x in summary['streams']),
    possible_steady_gap_count=sum(len(x['possible_steady_gaps']) for x in summary['streams']),
    notes=['Only existing APP receipt journals and plugin journals are tailed; no output settings or device commands are changed.',
        'Steady-gap candidates use the existing 1Hz pipeline journal; transition attribution is approximate and is not a physical sensation measurement.',
        'No packets means that output was not exercised; it never means the continuity test passed.',
        'Idle/browsing time is included in the five-minute capture and is not counted as continuous-output test time.'])
(root/'waveform-audit.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in summary.items() if k not in ('streams','cg_transitions','profiles')},ensure_ascii=False))
