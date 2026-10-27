"""Four-channel loopback APP and durable audit for the main control center."""
import asyncio,json,threading,time,uuid
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
from .mock_v4 import MockV4App

class MockSession:
    def __init__(self,hub,root):
        if not hub.local_only:raise ValueError('模拟 APP 仅允许本机回环连接')
        self.hub=hub;self.directory=Path(root)/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6])
        self.directory.mkdir(parents=True,exist_ok=False)
        self._stop=threading.Event();self._lock=threading.Lock();self._thread=None
        self._state=dict(running=False,connected=False,error='',commands=0,pulsesA=0,pulsesB=0,ovcPulsesA=0,ovcPulsesB=0,client_id='',receipts={})
        self._pipeline=(self.directory/'pipeline.jsonl').open('a',encoding='utf-8');self.frames=0;self._last_summary=0.;self._closed=False
        self.started=datetime.now(timezone.utc).isoformat();self._command_counts=Counter();self._compact_at=0.
    def snapshot(self):
        with self._lock:state=dict(self._state)
        return dict(state,directory=str(self.directory),frames=self.frames)
    def _change(self,**values):
        with self._lock:self._state.update(values)
    def start(self):
        self._change(running=True)
        self._thread=threading.Thread(target=lambda:asyncio.run(self._run()),daemon=True,name='MainWindowMockAPP');self._thread.start()
    async def _run(self):
        app=MockV4App();count=0;counts=Counter();receipts={}
        with (self.directory/'commands.jsonl').open('a',encoding='utf-8') as stream:
            def flush():
                nonlocal count
                records=list(app.records);app.records.clear()
                for row in records:
                    stream.write(json.dumps(dict(utc=datetime.now(timezone.utc).isoformat(),**row),ensure_ascii=False)+'\n')
                    d=row.get('data') or {}
                    if row.get('m')=='device.op':counts[(d.get('s'),d.get('c'),d.get('t'))]+=1
                    if row.get('m')=='device.op' and d.get('t')==0 and d.get('s') in ('coyote','ovc') and d.get('c') in (0,1):
                        key=('pulse' if d['s']=='coyote' else 'vibration')+('B' if d['c']==1 else 'A')
                        receipts[key]=dict(count=counts[(d['s'],d['c'],0)],at=row['at'],frame=(d.get('v') or [''])[0])
                count+=len(records);stream.flush()
                with self._lock:self._command_counts=counts.copy()
                self._change(commands=count,receipts=dict(receipts),pulsesA=counts[('coyote',0,0)],pulsesB=counts[('coyote',1,0)],
                    ovcPulsesA=counts[('ovc',0,0)],ovcPulsesB=counts[('ovc',1,0)])
            try:
                end=time.monotonic()+5
                while not self.hub.snapshot()['server_ready']:
                    if self._stop.is_set():return
                    if time.monotonic()>end:raise TimeoutError('本机模拟服务未就绪')
                    await asyncio.sleep(.03)
                h=self.hub.snapshot()
                await app.connect(f"ws://127.0.0.1:{h['port']}/?tid={h['controller_id']}")
                self._change(connected=True,client_id=app.client_id)
                while not self._stop.is_set() and app.reader and not app.reader.done():
                    flush();await asyncio.sleep(.1)
            except Exception as e:self._change(error=str(e))
            finally:
                await app.close();flush();self._change(running=False,connected=False)
    def profile(self,simulation,channels,ovc_limits):
        row=dict(utc=datetime.now(timezone.utc).isoformat(),simulation=simulation,channels=channels,ovc_limits=ovc_limits)
        (self.directory/'preset.json').write_text(json.dumps(row,ensure_ascii=False,indent=2),encoding='utf-8')
        with (self.directory/'preset-history.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
    def record(self,source,pulse,ovc,pulse_outputs,ovc_outputs,armed,ovc_armed,*,compact=False):
        if self._closed:return
        if compact:
            now=time.monotonic()
            if now-self._compact_at<1:return
            self._compact_at=now
            pulse={k:v for k,v in pulse.items() if k!='traces'};ovc={k:v for k,v in ovc.items() if k!='traces'}
        row=dict(utc=datetime.now(timezone.utc).isoformat(),at=time.monotonic(),source=source,pulse=pulse,ovc=ovc,
            pulse_outputs=pulse_outputs,ovc_outputs=ovc_outputs,armed=armed,ovc_armed=ovc_armed)
        self._pipeline.write(json.dumps(row,ensure_ascii=False)+'\n');self._pipeline.flush();self.frames+=1
        if time.monotonic()-self._last_summary>=1:self.summary();self._last_summary=time.monotonic()
    def summary(self,complete=False):
        with self._lock:counts={'/'.join(map(str,k)):v for k,v in self._command_counts.items()}
        row=dict(started_utc=self.started,complete=complete,transport='127.0.0.1 only',hardware_connected=False,
            same_window=True,policy_mode='current control-center preset',recording_limit_seconds=None,command_counts=counts,**self.snapshot())
        target=self.directory/'summary.json';tmp=target.with_suffix('.tmp');tmp.write_text(json.dumps(row,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(target)
    def stop(self):
        if self._closed:return
        self._stop.set()
        if self._thread:self._thread.join(3)
        self._pipeline.close();self._closed=True;self.summary(True)
