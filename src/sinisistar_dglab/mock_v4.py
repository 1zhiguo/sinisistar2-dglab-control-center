"""Loopback-only DG-LAB 4 APP fixture; contains no BLE/hardware access."""
import asyncio,json,time
from copy import deepcopy
from urllib.parse import urlsplit
import websockets

def mock_device(kind,slot):
    device=dict(slotId=slot,type=kind,name='模拟 '+('负鼠' if kind=='OVC_1' else '郊狼 V3'),
                props=dict(connectState='connected',intensityA=0,intensityB=0,channelAStatus=True if kind=='OVC_1' else 0,channelBStatus=True if kind=='OVC_1' else 0),
                slotState=dict(hasDevice=True,channelA=dict(isMuted=False,intensityMax=200 if kind=='OVC_1' else 100),
                               channelB=dict(isMuted=False,intensityMax=200 if kind=='OVC_1' else 100)))
    if kind=='OVC_1':
        for c in 'AB':device['slotState']['channel'+c].pop('intensityMax')
    return device

class MockV4App:
    def __init__(self):
        self.devices=[mock_device('COYOTE_030','coyote'),mock_device('OVC_1','ovc')]
        self.records=[];self.socket=None;self.reader=None;self.client_id='';self.reject_slot=''
    async def connect(self,url):
        if urlsplit(url).hostname not in ('127.0.0.1','localhost','::1'):raise ValueError('Mock APP only accepts loopback')
        self.socket=await websockets.connect(url)
        hello=json.loads(await self.socket.recv());attached=json.loads(await self.socket.recv())
        if hello.get('type')!='hello' or attached.get('type')!='controller_attached':raise ValueError('Unexpected V4 handshake')
        self.client_id=hello['clientId'];self.reader=asyncio.create_task(self._read());return self
    async def send(self,data):await self.socket.send(json.dumps(dict(type='message',data=data)))
    async def patch_slot(self,slot,**fields):
        from ._v4_protocol import _merge
        device=next((d for d in self.devices if d['slotId']==slot),None)
        if device is not None:_merge(device,fields)
        await self.send(dict(t='ev',ev='slots.patch',slots=[dict(slotId=slot,**fields)]))
    async def _read(self):
        try:
            async for raw in self.socket:
                outer=json.loads(raw)
                if outer.get('type')!='message':continue
                request=outer['data'];self.records.append(dict(at=time.monotonic(),**deepcopy(request)))
                method=request.get('m');data=request.get('data') or {}
                if method in ('device.op','device.op.clear') and not any(d['slotId']==data.get('s') for d in self.devices):
                    await self.send(dict(t='resp',reqId=request['reqId'],error='slot_not_found'));continue
                if data.get('s')==self.reject_slot and method=='device.op':
                    await self.send(dict(t='resp',reqId=request['reqId'],error='fixture rejected output'));continue
                if method=='devices.get':result=dict(devices=deepcopy(self.devices))
                elif method=='device.op':
                    result=dict(type=data['t'],slotId=data['s'],channel=data['c'],reason='completed')
                    if data['t'] in (4,7):
                        device=next(d for d in self.devices if d['slotId']==data['s'])
                        key='intensity'+('B' if data['c']==1 else 'A');device['props'][key]=data.get('v',0)
                        await self.patch_slot(data['s'],props={key:data.get('v',0)})
                else:result={}
                await self.send(dict(t='resp',reqId=request['reqId'],result=result))
        except websockets.ConnectionClosed:pass
    def pulses(self,slot,channel='A',since=0):
        return [r for r in self.records if r['at']>=since and r.get('m')=='device.op' and r['data'].get('s')==slot and
                r['data'].get('t')==0 and r['data'].get('c')==(1 if channel=='B' else 0)]
    def strengths(self,slot):
        return [r for r in self.records if r.get('m')=='device.op' and r['data'].get('s')==slot and r['data'].get('t')==4]
    async def close(self):
        if self.socket:await self.socket.close()
        if self.reader:await self.reader
