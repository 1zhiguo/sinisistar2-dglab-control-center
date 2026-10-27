"""Discovery and actionable diagnostics, using loopback APPs only."""
import asyncio,json,tempfile,time,unittest
from copy import deepcopy
from pathlib import Path
from PySide6.QtGui import QGuiApplication
from sinisistar_dglab.backend import Backend
from sinisistar_dglab.device_setup import setup_status,app_error_hint
from sinisistar_dglab.mock_v4 import MockV4App,mock_device
from sinisistar_dglab.v4 import V4ConnectionService
from sinisistar_dglab._v4_protocol import channel_block_reason
from sinisistar_dglab.telemetry import ROOT

class Diagnostics(unittest.TestCase):
    def status(self,device,**changes):
        s=dict(protocol='v4',server_ready=True,selected_slot_id=device['slotId'],connected=True,feedback_known=True,
               limit_a=100,limit_b=100,channel_a_reason=channel_block_reason(device,'A'),channel_b_reason=channel_block_reason(device,'B'))
        s.update(changes)
        return setup_status('ovc' if device['type']=='OVC_1' else 'pulse',s,device=device,enabled=dict(A=True,B=True),caps=dict(A=60,B=60))
    def test_coyote_status_codes_do_not_conflate_block_and_damage_or_low_output(self):
        d=mock_device('COYOTE_030','coyote')
        for raw,code in [(0,''),(1,''),(2,''),(3,'channel-fault'),(4,'channel-blocked')]:
            d['props'].update(channelAStatus=raw,channelBStatus=raw);s=self.status(d)
            self.assertEqual(s['channels'][0]['code'],code)
            self.assertEqual(s['canEnable'],raw<3)
            if raw==4:self.assertIn('手动打开',s['reason'])
    def test_mute_accessory_and_partial_channel_readiness(self):
        d=mock_device('OVC_1','ovc');d['props']['channelAStatus']=False
        s=self.status(d);self.assertTrue(s['canEnable']);self.assertEqual(s['usableChannels'],'B')
        self.assertIn('配件',s['channels'][0]['hint'])
        d['slotState']['channelB']['isMuted']=True;s=self.status(d)
        self.assertFalse(s['canEnable']);self.assertIn('静音',s['reason'])
    def test_zero_caps_missing_feedback_and_app_error_are_actionable(self):
        d=mock_device('COYOTE_030','coyote')
        for changes,word in [(dict(limit_a=0,limit_b=0),'上限为零'),(dict(feedback_known=False),'强度'),(dict(readiness_failed=True),'归零'),(dict(error='slot_not_found'),'slot_not_found')]:
            s=self.status(d,**changes);self.assertFalse(s['canEnable']);self.assertIn(word,s['reason'])
        self.assertIn('重新连接',app_error_hint('slot_not_found'))
    def test_all_documented_rpc_errors_and_unknown_error_keep_help(self):
        for code in ['duplicate_request_id','invalid_params','slot_not_found','invalid_operate','method_not_found','internal_error','cancelled','new_app_error']:
            self.assertTrue(app_error_hint(code))
    def test_missing_controller_and_missing_accessory_have_explicit_disabled_labels(self):
        d=mock_device('OVC_1','ovc')
        s=self.status(d,selected_slot_id='',connected=False)
        self.assertIn('未接入负鼠设备，无法启用',s['reason']);self.assertEqual(s['buttonLabel'],'未接入设备')
        d['props'].update(channelAStatus=False,channelBStatus=False)
        s=self.status(d);self.assertIn('未接入振动配件，无法启用',s['reason'])
        self.assertEqual(s['buttonLabel'],'未接入振动配件');self.assertFalse(s['canEnable'])

class AutoDevices(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):cls.qt=QGuiApplication.instance() or QGuiApplication([])
    async def asyncSetUp(self):
        asyncio.get_running_loop().set_debug(False)
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp')
        self.b=Backend(offline=True,settings=Path(self.temp.name)/'settings.json');self.b._timer.stop();self.b.offline=False
        self.hub=V4ConnectionService(port=0,host='127.0.0.1',lan_ip='127.0.0.1');self.hub.start()
        await self.until(lambda:self.hub.snapshot()['server_ready'])
        self.app=MockV4App()
        self.b._v4=self.hub;self.b._service=self.hub.channel('pulse');self.b._ovc_service=self.hub.channel('ovc');self.b._connection['pulse_backend']='v4'
    async def asyncTearDown(self):
        await asyncio.to_thread(self.hub.stop);await self.app.close()
        self.b._v4=self.b._service=self.b._ovc_service=None;self.b.shutdown();self.temp.cleanup()
    async def until(self,fn,seconds=3):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            self.hub.snapshot();self.b._sync_auto_devices()
            if fn():return
            await asyncio.sleep(.025)
        self.fail('Auto device state did not settle')
    async def drive(self,seconds=.25):
        end=time.monotonic()+seconds
        while time.monotonic()<end:self.hub.snapshot();self.b._sync_auto_devices();await asyncio.sleep(.025)
    async def connect(self):
        s=self.hub.snapshot();await self.app.connect(f"ws://127.0.0.1:{s['port']}/?tid={s['controller_id']}")
    async def test_discovery_selects_and_enables_both_only_after_zero_baseline(self):
        await self.connect();await self.until(lambda:self.b._armed and self.b._ovc_armed)
        self.assertTrue(self.b._device_setup('pulse')['canEnable']);self.assertTrue(self.b._device_setup('ovc')['canEnable'])
        self.assertFalse(self.app.pulses('coyote'));self.assertFalse(self.app.pulses('ovc'))
        for slot in ('coyote','ovc'):
            self.assertTrue(any(r['m']=='device.op.clear' and r['data']['s']==slot for r in self.app.records))
        ovc=self.hub.channel('ovc');s=ovc.snapshot()
        self.assertTrue(s['feedback_known']);self.assertEqual(s['limit_a'],200);self.assertEqual(s['limit_source'],'device-range')
        self.assertNotIn('intensityMax',self.app.devices[1]['slotState']['channelA'])
        ovc.set_output_permission(True,hard_limits=dict(A=150,B=150))
        ovc.submit_plan(dict(A=dict(peak=90,samples=[0,30,90,45],frequencies=[30]*4),B=None))
        await self.until(lambda:bool(self.app.pulses('ovc')))
        self.assertEqual(self.app.strengths('ovc')[-1]['data']['v'],90)
    async def test_blocked_coyote_and_missing_ovc_accessory_wait_then_auto_enable(self):
        self.app.devices[0]['props'].update(channelAStatus=4,channelBStatus=4)
        self.app.devices[1]['props'].update(channelAStatus=False,channelBStatus=False)
        await self.connect();await self.until(lambda:len(self.b._auto_pending)==2);await self.drive()
        self.assertFalse(self.b._armed);self.assertFalse(self.b._ovc_armed)
        self.assertIn('屏蔽',self.b._device_setup('pulse')['reason'])
        self.assertIn('配件',self.b._device_setup('ovc')['reason'])
        await self.app.patch_slot('coyote',props=dict(channelAStatus=0))
        await self.app.patch_slot('ovc',props=dict(channelBStatus=True))
        await self.until(lambda:self.b._armed and self.b._ovc_armed)
        self.assertEqual(self.b._device_setup('pulse')['usableChannels'],'A')
        self.assertEqual(self.b._device_setup('ovc')['usableChannels'],'B')
    async def test_manual_pause_deselect_and_emergency_are_not_undone_by_updates(self):
        await self.connect();await self.until(lambda:self.b._armed and self.b._ovc_armed)
        self.b.toggleArm();self.b.selectV4Device('ovc','','')
        await self.app.patch_slot('coyote',props=dict(intensityA=0));await self.drive()
        self.assertFalse(self.b._armed);self.assertFalse(self.b._ovc_armed)
        self.b.emergencyStop();self.b.unlock();await self.drive()
        self.assertFalse(self.b._armed);self.assertFalse(self.b._ovc_armed)
    async def test_emergency_before_discovery_and_disabled_auto_never_arm(self):
        self.b.emergencyStop();await self.connect();await self.drive()
        self.assertFalse(self.b._armed);self.assertFalse(self.b._ovc_armed)
        self.b.unlock();await self.drive();self.assertFalse(self.b._armed)
    async def test_zero_rejection_exposes_app_error_without_disabling_other_role_and_retry_works(self):
        self.app.reject_slot='coyote';await self.connect()
        await self.until(lambda:bool(self.hub.channel('pulse').snapshot().get('error')) and self.b._ovc_armed)
        await self.drive();self.assertFalse(self.b._armed)
        self.assertIn('fixture rejected output',self.b._device_setup('pulse')['appError'])
        self.assertEqual(self.b._device_setup('ovc')['appError'],'')
        before=len(self.app.records);await self.drive()
        self.assertEqual(before,len(self.app.records))
        self.app.reject_slot='';self.b.retryDevice('pulse');await self.until(lambda:self.b._armed)
    async def test_new_device_does_not_steal_selected_route(self):
        await self.connect();await self.until(lambda:self.b._armed and self.b._ovc_armed)
        item=mock_device('COYOTE_030','second-coyote');self.app.devices.append(item)
        await self.app.send(dict(t='ev',ev='devices.patch',added=[item]));await self.drive()
        self.assertEqual(self.hub.channel('pulse').snapshot()['selected_slot_id'],'coyote')
    async def test_auto_can_be_disabled_and_offline_catalog_is_not_enabled(self):
        self.b._connection['auto_enable']=False;await self.connect();await self.drive()
        self.assertFalse(self.b._armed);self.assertFalse(self.b._ovc_armed)
        self.b._connection['auto_enable']=True;await self.until(lambda:self.b._armed and self.b._ovc_armed)

if __name__=='__main__':unittest.main()
