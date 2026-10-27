"""Read-only background journal for the real-APP CG test entry point.

Never consumes observer event queues, invokes Qt, or calls a device service.
The UI's existing diagnostics provide output status, not physical sensation proof.
"""
from datetime import datetime,timezone
from pathlib import Path
import json,threading,time,uuid


class LiveCgJournal:
    def __init__(self,observer,root):
        self.observer=observer;self.root=Path(root)
        self.directory=self.root/'sessions'/(datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6])
        self.directory.mkdir(parents=True,exist_ok=False)
        self.started_wall=time.time()
        self._stop=threading.Event();self._thread=None;self.error='';self.samples=0;self.controls=0

    def start(self):
        if self._thread:return
        self._thread=threading.Thread(target=self._run,name='CG Test Journal',daemon=True);self._thread.start()

    def close(self):
        self._stop.set()
        if self._thread:self._thread.join(1)

    def _run(self):
        sequence=None;last_control=None;control_at=0.;began=datetime.now(timezone.utc).isoformat()
        try:
            with (self.directory/'states.jsonl').open('w',encoding='utf-8') as states,(self.directory/'control.jsonl').open('w',encoding='utf-8') as control:
                while not self._stop.is_set():
                    state=self.observer.snapshot();key=(state.get('session'),state.get('sample_id'),state.get('live'),state.get('error'))
                    if key!=sequence:
                        states.write(json.dumps(state,ensure_ascii=False)+'\n');states.flush();self.samples+=1;sequence=key
                    now=time.monotonic()
                    if now-control_at>=1:
                        control_at=now
                        try:
                            path=self.root/'connection-diagnostics.json'
                            if path.stat().st_mtime>=self.started_wall:
                                data=json.loads(path.read_text(encoding='utf-8'))
                                if data.get('utc')!=last_control:
                                    control.write(json.dumps(data,ensure_ascii=False)+'\n');control.flush()
                                    self.controls+=1;last_control=data.get('utc')
                        except (OSError,ValueError):pass
                    self._stop.wait(.1)
        except Exception as error:self.error=str(error)
        finally:
            summary=dict(started_utc=began,ended_utc=datetime.now(timezone.utc).isoformat(),complete=self._stop.is_set(),
                samples=self.samples,control_samples=self.controls,error=self.error,device_services_started_by_recorder=False,
                consumes_event_queues=False,scope='Real game snapshots and controller status; no independent proof of physical output')
            try:(self.directory/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
            except OSError:pass
