"""Loopback-only DG-LAB APP simulator. It never connects to hardware."""
from __future__ import annotations
import asyncio,json,re,time
import threading
from pathlib import Path
from urllib.parse import urlsplit
import websockets

class MockApp:
    def __init__(self,limits=(50,50)):
        self.limits=list(limits);self.strengths=[0,0];self.commands=[];self.issues=[];self.started=time.monotonic()
        self.socket=None;self.reader=None;self.controller='';self.phone=''
    async def connect(self,url,controller):
        parsed=urlsplit(url)
        if parsed.scheme!='ws' or parsed.hostname not in ('127.0.0.1','::1','localhost'):raise ValueError('Mock APP accepts loopback only')
        self.controller=controller;self.socket=await websockets.connect(url)
        hello=json.loads(await self.socket.recv());self.phone=hello['clientId']
        await self.socket.send(json.dumps(dict(type='bind',clientId=controller,targetId=self.phone,message='DGLAB')))
        answer=json.loads(await self.socket.recv())
        if answer.get('message')!='200':raise RuntimeError('Mock pairing failed')
        await self.report();self.reader=asyncio.create_task(self._read());return self
    async def report(self):
        await self.socket.send(json.dumps(dict(type='msg',clientId=self.controller,targetId=self.phone,
                                              message='strength-'+'+'.join(map(str,self.strengths+self.limits)))))
    async def set_limits(self,a,b):
        self.limits=[a,b];self.strengths=[min(s,l) for s,l in zip(self.strengths,self.limits)];await self.report()
    async def _read(self):
        try:
            async for raw in self.socket:
                p=json.loads(raw)
                if p.get('type')!='msg':continue
                if p.get('clientId')!=self.controller or p.get('targetId')!=self.phone:self.issues.append('wrong identity');continue
                command=p.get('message','');row=dict(at=time.monotonic(),command=command)
                match=re.fullmatch(r'strength-([12])\+2\+(\d+)',command)
                if match:
                    idx=int(match[1])-1;strength=int(match[2]);row.update(channel='AB'[idx],kind='strength',strength=strength)
                    if not 0<=strength<=self.limits[idx]:self.issues.append('strength exceeds APP cap')
                    self.strengths[idx]=strength;self.commands.append(row);await self.report();continue
                match=re.fullmatch(r'clear-([12])',command)
                if match:row.update(channel='AB'[int(match[1])-1],kind='clear')
                elif command.startswith(('pulse-A:','pulse-B:')):
                    channel=command[6];frames=json.loads(command.split(':',1)[1]);row.update(channel=channel,kind='pulse',strength=self.strengths['AB'.index(channel)])
                    if len(frames)!=1:self.issues.append('more than one 100ms frame queued')
                    for frame in frames:
                        if not isinstance(frame,str) or not re.fullmatch('[0-9A-Fa-f]{16}',frame):self.issues.append('invalid frame');continue
                        freq=[int(frame[i:i+2],16) for i in range(0,8,2)];amp=[int(frame[i:i+2],16) for i in range(8,16,2)]
                        if not all(0<=a<=100 for a in amp) or not all(1<=f<=240 for f in freq):self.issues.append('invalid frame bytes')
                        row.update(frame=frame,amplitudes=amp,frequency_bytes=freq)
                else:self.issues.append('unknown command')
                self.commands.append(row)
        except websockets.ConnectionClosed:pass
    async def close(self):
        if self.socket:await self.socket.close()
        if self.reader:await self.reader
    def pulses(self,channel,since=0):return [r for r in self.commands if r.get('kind')=='pulse' and r.get('channel')==channel and r['at']>=since]

class MockAppRunner:
    """GUI helper with its own event loop, restricted to a local-only service."""
    def __init__(self,service,audit_path):
        self.service=service;self.audit_path=Path(audit_path);self._stop=threading.Event();self._thread=None
        self._lock=threading.Lock();self._state=dict(running=False,connected=False,commands=0,pulsesA=0,pulsesB=0,error='')
    def snapshot(self):
        with self._lock:return dict(self._state)
    def _change(self,**values):
        with self._lock:self._state.update(values)
    def start(self):
        if self._thread and self._thread.is_alive():return
        if self.service.snapshot().get('local_only') is not True:raise ValueError('Loopback service required')
        self._stop.clear();self._change(running=True,error='')
        self._thread=threading.Thread(target=lambda:asyncio.run(self._run()),name='SiNiSistarMockAPP',daemon=True);self._thread.start()
    def stop(self):
        self._stop.set()
        if self._thread and self._thread.is_alive():self._thread.join(2)
    async def _run(self):
        app=MockApp()
        try:
            end=time.monotonic()+3
            while not self._stop.is_set() and not self.service.snapshot()['server_ready']:
                if time.monotonic()>end:raise TimeoutError('本机测试服务未就绪')
                await asyncio.sleep(.03)
            if self._stop.is_set():return
            s=self.service.snapshot()
            await app.connect(f"ws://127.0.0.1:{s['port']}/{s['controller_id']}",s['controller_id']);self._change(connected=True)
            while not self._stop.is_set() and app.reader and not app.reader.done():
                self._change(commands=len(app.commands),pulsesA=len(app.pulses('A')),pulsesB=len(app.pulses('B')))
                await asyncio.sleep(.1)
        except Exception as e:self._change(error=str(e))
        finally:
            await app.close()
            self._change(running=False,connected=False,commands=len(app.commands),pulsesA=len(app.pulses('A')),pulsesB=len(app.pulses('B')))
            self.audit_path.parent.mkdir(parents=True,exist_ok=True)
            self.audit_path.write_text(json.dumps(dict(hardware_connected=False,transport='loopback Mock APP',commands=app.commands,issues=app.issues),ensure_ascii=False,indent=2),encoding='utf-8')
