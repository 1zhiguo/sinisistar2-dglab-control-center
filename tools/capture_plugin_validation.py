"""Time-bounded, read-only capture of one real plugin session; no device imports."""
from __future__ import annotations
import argparse,json,queue,sys,time
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from sinisistar_dglab.plugin_bridge import PluginObserver
from sinisistar_dglab.monitoring import EventMonitor
from sinisistar_dglab.telemetry import TYPES

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-dir',required=True,type=Path)
    parser.add_argument('--seconds',type=int,default=300)
    parser.add_argument('--output-dir',type=Path,help='Separate capture directory; leaves previous sessions intact')
    args=parser.parse_args();output=args.output_dir or ROOT/'artifacts/fresh-game-validation'
    output.mkdir(parents=True,exist_ok=True);stop=output/'stop-capture'
    stop.unlink(missing_ok=True)
    observer=PluginObserver(args.game_dir.resolve()/'BepInEx/plugins/SiNiSistarDGLab/telemetry')
    monitor=EventMonitor();started=time.monotonic();last=None;last_write=0.;frames=0;valid_frames=0;initial=None;latest=None;ranges={};sessions=set()
    def save(done=False):
        report=dict(started_utc=began,complete=done,elapsed_seconds=round(time.monotonic()-started,1),
                    directory=str(observer.directory),frames=frames,valid_frames=valid_frames,sessions=sorted(sessions),
                    initial=initial,latest=latest,ranges=ranges,event_counts=monitor.counts,event_rows=monitor.rows,
                    device_services_started=False,hardware_connected=False)
        path=output/'capture-summary.json';temp=path.with_suffix('.tmp')
        temp.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(path)
    began=datetime.now(timezone.utc).isoformat();observer.start()
    try:
        with (output/'states.jsonl').open('w',encoding='utf-8') as states,(output/'callbacks.jsonl').open('w',encoding='utf-8') as callbacks:
            while time.monotonic()-started<args.seconds and not stop.exists():
                state=observer.snapshot()
                if state.get('live') and state.get('session'):
                    monitor.begin_session(state['session']);sessions.add(state['session'])
                    identity=(state['session'],state['sample_id'])
                    if identity!=last:
                        last=identity;frames+=1;initial=initial or state;latest=state
                        states.write(json.dumps(state,ensure_ascii=False)+'\n');states.flush()
                        if state.get('valid'):
                            valid_frames+=1
                            for field in ('hp','mp','durability'):
                                value=(state.get(field) or {}).get('current')
                                if isinstance(value,int):
                                    pair=ranges.setdefault(field,[value,value]);pair[0]=min(pair[0],value);pair[1]=max(pair[1],value)
                        monitor.snapshot(state if state.get('valid') else None)
                while True:
                    try:event=observer.events.get_nowait()
                    except queue.Empty:break
                    callbacks.write(json.dumps(event,ensure_ascii=False)+'\n');callbacks.flush()
                    monitor.callback(event,TYPES['AbnormalType'])
                if time.monotonic()-last_write>=1:save();last_write=time.monotonic()
                time.sleep(.05)
    finally:observer.stop();save(True)
    print(json.dumps(dict(frames=frames,valid_frames=valid_frames,counts=monitor.counts)))

if __name__=='__main__':main()
