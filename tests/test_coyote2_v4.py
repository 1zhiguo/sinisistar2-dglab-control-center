"""Coyote 2.0 -> real controller/V4 workers -> loopback APP. No BLE access."""
import asyncio,json,tempfile,time,unittest
from pathlib import Path
from PySide6.QtGui import QGuiApplication
from sinisistar_dglab.backend import Backend
from sinisistar_dglab.mock_v4 import MockV4App,mock_device
from sinisistar_dglab.v4 import V4ConnectionService
from sinisistar_dglab._v4_protocol import channel_block_reason
from sinisistar_dglab.telemetry import ROOT
from test_v4_backend import Game

class HeldZeroApp(MockV4App):
    def __init__(self):
        super().__init__(coyote_type='COYOTE_020');self.hold_zero=False;self.held=[]
    async def send(self,data):
        if self.hold_zero and data.get('t')=='resp' and (data.get('result') or {}).get('type')==7 and data['result'].get('slotId')=='coyote':
            self.held.append(data);return
        await super().send(data)
    async def release_zero(self):
        self.hold_zero=False;pending,self.held=self.held,[]
        for row in pending:await super().send(row)

class Coyote2(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):cls.qt=QGuiApplication.instance() or QGuiApplication([])
    async def asyncSetUp(self):
        asyncio.get_running_loop().set_debug(False)
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp')
        self.b=Backend(offline=True,settings=Path(self.temp.name)/'settings.json');self.b._timer.stop();self.b.offline=False
        self.game=Game();self.b._observer=self.game
        for channel in self.b._channels:channel['limit']=60
        self.b._sim_profile.update(pulse_cap_a=60,pulse_cap_b=60,vibration_cap_a=80,vibration_cap_b=80)
        self.b._ovc_limits={'A':80,'B':80}
        self.b._waves.append(dict(key='custom_coyote2_full',name='Full',points=[1.]*16))
        for rule in self.b._sim_profile['rules'].values():rule['enabled']=False
        rule=self.b._sim_profile['rules']['grab_hold']
        rule.update(enabled=True,pulse_enabled=True,pulse_channel='AB',pulse_strength=55,pulse_strength_a=45,pulse_strength_b=55,pulse_gain=0,pulse_wave='custom_coyote2_full',pulse_max=False,
                    vibration_enabled=True,vibration_channel='AB',vibration_strength=40,vibration_strength_a=30,vibration_strength_b=40,vibration_gain=0,vibration_wave='ovc_surf_wave',vibration_max=False)
        for route in ('pulse','vibration'):
            for suffix in ('start_strength','start_strength_a','start_strength_b'):rule[route+'_'+suffix]=None
        self.hub=V4ConnectionService(port=0,host='127.0.0.1',lan_ip='127.0.0.1');self.hub._hub._discovery_interval=.2;self.hub.start()
        self.b._v4=self.hub;self.b._service=self.hub.channel('pulse');self.b._ovc_service=self.hub.channel('ovc');self.b._connection['pulse_backend']='v4'
        self.app=HeldZeroApp();self.app.devices[0]['slotState']['channelA']['intensityMax']=40;self.app.devices[0]['slotState']['channelB']['intensityMax']=58
        await self.until(lambda:self.hub.snapshot()['server_ready'])
    async def asyncTearDown(self):
        await asyncio.to_thread(self.hub.stop);await self.app.close()
        out=ROOT/'artifacts/coyote2-validation';out.mkdir(parents=True,exist_ok=True)
        (out/(self._testMethodName+'.json')).write_text(json.dumps(dict(hardware_connected=False,requests=self.app.records),ensure_ascii=False,indent=2),encoding='utf-8')
        self.b._v4=self.b._service=self.b._ovc_service=None;self.b.shutdown();self.temp.cleanup()
    async def until(self,fn,seconds=3):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            self.b.tick()
            if fn():return
            await asyncio.sleep(.025)
        self.fail('Coyote 2.0 mock did not settle')
    async def drive(self,seconds=.3):
        end=time.monotonic()+seconds
        while time.monotonic()<end:self.b.tick();await asyncio.sleep(.025)
    async def connect(self):
        s=self.hub.snapshot();await self.app.connect(f"ws://127.0.0.1:{s['port']}/?tid={s['controller_id']}")
    def values(self,role):return [self.hub.channel(role).snapshot()['output_channels'][c]['strength'] for c in 'AB']
    async def running(self):
        await self.connect();await self.until(lambda:self.b._armed and self.b._ovc_armed)
        self.game.s.update(bound=True,binder='Fixture');await self.until(lambda:self.values('pulse')==[40,55] and self.values('ovc')==[40,40])
    async def test_discovery_and_zero_barrier_without_v3_circuit_status(self):
        self.app.hold_zero=True;await self.connect();await self.until(lambda:bool(self.app.held) and self.b._ovc_armed)
        self.assertFalse(self.b._armed);self.assertFalse(self.app.pulses('coyote'))
        await self.app.release_zero();await self.until(lambda:self.b._armed)
        row=next(d for d in self.b.v4Devices if d['type']=='COYOTE_020')
        self.assertTrue(row['pulseCompatible']);self.assertNotIn('channelAStatus',row['props'])
        status=self.b._device_setup('pulse');self.assertTrue(status['canEnable']);self.assertEqual(status['usableChannels'],'AB')
        self.assertTrue(all(r['rawStatus'] is None for r in status['channels']))
        self.assertTrue(any(r['m']=='device.op.clear' and r['data']['s']=='coyote' for r in self.app.records))
    async def test_ab_and_peer_ovc_stream_canonical_v3_frames_under_dynamic_limits(self):
        await self.running();await self.drive(.45)
        for c,cap in (('A',40),('B',58)):
            packets=self.app.pulses('coyote',c);self.assertGreaterEqual(len(packets),3)
            self.assertTrue(all(r['data'].get('ver')==3 and len(r['data']['v'][0])==16 and r['data']['d']==100 for r in packets))
            self.assertTrue(all(r['data']['v']<=cap and r['data']['d']==300 for r in self.app.strengths('coyote') if r['data']['c']==('AB'.index(c))))
        self.assertTrue(self.app.pulses('ovc','A'));self.assertTrue(self.app.pulses('ovc','B'))
        await self.app.patch_slot('coyote',slotState=dict(channelA=dict(intensityMax=12),channelB=dict(intensityMax=8)))
        await self.until(lambda:self.values('pulse')==[12,8]);await self.drive(.2)
        self.assertEqual(self.values('ovc'),[40,40])
        await self.app.patch_slot('coyote',slotState=dict(channelA=dict(intensityMax=0),channelB=dict(intensityMax=8)))
        await self.until(lambda:self.values('pulse')==[0,8])
    async def test_muting_then_unmuting_requires_new_baseline_and_manual_pause_stays_paused(self):
        await self.running();start=len(self.app.records)
        await self.app.patch_slot('coyote',slotState=dict(channelA=dict(isMuted=True),channelB=dict(isMuted=True)))
        await self.until(lambda:not self.hub.channel('pulse').snapshot()['connected']);await self.drive(.15)
        self.assertEqual(self.values('pulse'),[0,0]);self.assertEqual(self.values('ovc'),[40,40])
        await self.app.patch_slot('coyote',slotState=dict(channelA=dict(isMuted=False)))
        await self.until(lambda:self.hub.channel('pulse').snapshot()['connected'] and self.values('pulse')==[40,0])
        self.assertTrue(any(r['m']=='device.op.clear' and r['data']['s']=='coyote' for r in self.app.records[start:]))
        self.b.toggleArm();await self.app.patch_slot('coyote',slotState=dict(channelB=dict(isMuted=False)));await self.drive(.3)
        self.assertFalse(self.b._armed);self.assertEqual(self.values('pulse'),[0,0])
    async def test_bluetooth_recovery_rezeros_before_fresh_output(self):
        await self.running();await self.app.patch_slot('coyote',props=dict(connectState='disconnected'),slotState=dict(hasDevice=False))
        await self.until(lambda:not self.hub.channel('pulse').snapshot()['connected']);since=len(self.app.records)
        await self.app.patch_slot('coyote',props=dict(connectState='connected'),slotState=dict(hasDevice=True))
        await self.until(lambda:self.hub.channel('pulse').snapshot()['connected'] and self.values('pulse')==[40,55])
        rows=[r for r in self.app.records[since:] if (r.get('data') or {}).get('s')=='coyote']
        first=next(i for i,r in enumerate(rows) if r['m']=='device.op' and r['data']['t']==4 and r['data']['v']>0)
        self.assertTrue(any(r['m']=='device.op.clear' for r in rows[:first]))
        self.assertEqual({r['data']['c'] for r in rows[:first] if r['m']=='device.op' and r['data']['t']==7},{0,1})
    async def test_emergency_zeros_all_channels_and_unlock_does_not_arm(self):
        await self.running();self.b.emergencyStop();since=time.monotonic();await self.drive(.35)
        self.assertEqual(self.values('pulse'),[0,0]);self.assertEqual(self.values('ovc'),[0,0])
        self.assertFalse(self.app.pulses('coyote',since=since+.05));self.assertFalse(self.app.pulses('ovc',since=since+.05))
        for slot in ('coyote','ovc'):
            for channel in (0,1):
                rows=[r['data'] for r in self.app.records if r.get('m')=='device.op' and r['data']['s']==slot and r['data']['c']==channel]
                self.assertEqual((rows[-1]['t'],rows[-1]['v']),(7,0))
        self.b.unlock();await self.drive(.2);self.assertFalse(self.b._armed);self.assertFalse(self.b._ovc_armed)
    async def test_game_cg_independent_ab_queue_frequency_and_peer_ovc(self):
        from cg_fixture import event_state
        from sinisistar_dglab.cg_policy import make_cg
        cg=make_cg(self.b._sim_profile['rules']['defeat_hold'],inherit=False,split=True);self.b._sim_profile['cg']=cg
        self.b._sim_profile['cg_detection_mode']='playback_only'
        cg['rule'].update(enabled=True,pulse_enabled=True,pulse_channel='AB',pulse_strength_a=20,pulse_strength_b=25,
            vibration_enabled=True,vibration_channel='AB',vibration_strength_a=30,vibration_strength_b=50,death_mode='until_end')
        self.b._waves.append(dict(key='custom_coyote2_half',name='Half',points=[.5]*16))
        for route in cg['routes'].values():
            for option in route.values():option.update(ramp_mode='constant',mode='fixed',loop=True)
        cg['routes']['pulse']['A'].update(mode='sequence',frequency=20,queue=[dict(wave='custom_coyote2_full',seconds=.2,period=1),dict(wave='custom_coyote2_half',seconds=.2,period=1)])
        cg['routes']['pulse']['B'].update(mode='shuffle',frequency=60,queue=[dict(wave='custom_coyote2_half',seconds=.2,period=1),dict(wave='custom_coyote2_full',seconds=.2,period=1)])
        self.game.s=event_state();await self.connect();await self.until(lambda:self.b._armed and self.b._ovc_armed)
        await self.until(lambda:self.values('pulse')==[20,25] and self.values('ovc')==[30,50]);await self.drive(.65)
        a=self.app.pulses('coyote','A');b=self.app.pulses('coyote','B')
        self.assertGreaterEqual(len(a),4);self.assertGreaterEqual(len(b),4)
        self.assertEqual({r['data']['v'][0][:8] for r in a},{'32323232'})
        self.assertEqual({r['data']['v'][0][:8] for r in b},{'11111111'})
        self.game.s['event_playing']=False;self.game.s['cg_playback']['event']['playing']=False
        await self.until(lambda:self.values('pulse')==[0,0] and self.values('ovc')==[0,0])

    async def test_missing_app_limit_blocks_enable_instead_of_inventing_cap(self):
        self.app.devices[0]['slotState']['channelA'].pop('intensityMax');await self.connect();await self.drive(.3)
        self.assertFalse(self.b._armed);self.assertIn('上限',self.b._device_setup('pulse')['reason']);self.assertFalse(self.app.pulses('coyote'))
    async def test_unsupported_device_cannot_take_pulse_or_ovc_role(self):
        self.app.devices.append(mock_device('UNSUPPORTED','other'));await self.connect();await self.until(lambda:self.b._armed and self.b._ovc_armed)
        self.assertFalse(self.hub.select_device('pulse',self.app.client_id,'other'));self.assertFalse(self.hub.select_device('ovc',self.app.client_id,'coyote'))
        self.assertFalse(next(d for d in self.b.v4Devices if d['slotId']=='other')['pulseCompatible'])
        self.assertEqual(channel_block_reason(self.app.devices[-1],'A'),'unsupported-device')

if __name__=='__main__':unittest.main()
