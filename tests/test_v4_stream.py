"""Production V4 handshake/output using a loopback fake APP, no hardware."""
import asyncio,gc,json,queue,time,threading,unittest
from sinisistar_dglab.v4 import V4ConnectionService
from sinisistar_dglab.mock_v4 import MockV4App
from sinisistar_dglab._v4_protocol import DGLabV4Bridge

def frame(peak=20,hz=30):return dict(peak=peak,samples=[0,peak*.3,peak,peak*.5],frequencies=[hz]*4)

class V4Stream(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        asyncio.get_running_loop().set_debug(False)
        self.hub=V4ConnectionService(port=0,host='127.0.0.1',lan_ip='127.0.0.1');self.hub.start()
        await self.until(lambda:self.hub.snapshot()['server_ready'])
        state=self.hub.snapshot();self.app=await MockV4App().connect(f"ws://127.0.0.1:{state['port']}/?tid={state['controller_id']}")
        await self.until(lambda:len(self.hub.devices_snapshot())==2)
        self.pulse=self.hub.channel('pulse');self.ovc=self.hub.channel('ovc')
    async def asyncTearDown(self):
        await asyncio.to_thread(self.hub.stop);await self.app.close()
    async def until(self,fn,seconds=2):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            if fn():return
            await asyncio.sleep(.01)
        self.fail('V4 mock did not settle')
    async def select(self,role):
        slot='ovc' if role=='ovc' else 'coyote'
        self.assertTrue(self.hub.select_device(role,self.app.client_id,slot))
        await self.until(lambda:self.hub.channel(role).snapshot()['connected'])
    async def drive(self,seconds=.3,pulse=None,ovc=None):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            for service,value in ((self.pulse,pulse),(self.ovc,ovc)):
                if value:
                    self.assertTrue(service.set_output_permission(True,hard_limits={'A':200 if service is self.ovc else 100,'B':200 if service is self.ovc else 100}))
                    self.assertTrue(service.submit_plan({'A':frame(value),'B':None}))
            await asyncio.sleep(.065)
    async def test_handshake_requires_explicit_supported_route_selection(self):
        self.assertFalse(self.pulse.snapshot()['connected']);self.assertFalse(self.pulse.set_output_permission(True))
        self.assertFalse(self.hub.select_device('pulse',self.app.client_id,'ovc'))
        self.assertFalse(self.hub.select_device('ovc',self.app.client_id,'coyote'))
        await self.select('pulse');self.assertTrue(self.pulse.snapshot()['feedback_known'])
        self.assertFalse(self.app.pulses('coyote'))

    async def test_idle_routes_sleep_and_new_frame_wakes_without_poll_delay(self):
        before=[s._loop_passes for s in (self.pulse,self.ovc)]
        await asyncio.sleep(.35)
        self.assertTrue(all(s._loop_passes-n<=4 for s,n in zip((self.pulse,self.ovc),before)))
        await self.select('pulse')
        self.pulse.set_output_permission(True,hard_limits={'A':30,'B':30})
        self.pulse.submit_plan({'A':frame(15),'B':None})
        await self.until(lambda:bool(self.app.pulses('coyote')))
        # The original single-frame/no-repeat/expiry test covers the lease.
        self.assertEqual(len(self.app.pulses('coyote')),1)
    async def test_two_roles_send_independently_and_ovc_rounds_down_tens(self):
        await self.select('pulse');await self.select('ovc');await self.drive(pulse=13,ovc=39)
        self.assertTrue(self.app.pulses('coyote'));self.assertTrue(self.app.pulses('ovc'))
        self.assertEqual(self.app.strengths('coyote')[-1]['data']['v'],13)
        self.assertEqual(self.app.strengths('ovc')[-1]['data']['v'],30)
        self.assertTrue(all(r['data']['v'][0][:8]=='0A0A0A0A' for r in self.app.pulses('ovc')))
        self.assertTrue(all(r['data']['d']==100 and len(r['data']['v'])==1 for r in self.app.pulses('ovc')))
    async def test_a_single_frame_is_not_repeated_and_expires(self):
        await self.select('pulse');self.pulse.set_output_permission(True,hard_limits={'A':30,'B':30})
        self.pulse.submit_plan({'A':frame(12),'B':None});await asyncio.sleep(.4)
        self.assertEqual(len(self.app.pulses('coyote')),1);self.assertFalse(self.pulse.snapshot()['output_active'])
        self.assertTrue(any(r['m']=='device.op' and r['data']['t']==7 and r['data']['s']=='coyote' for r in self.app.records))
    async def test_stopping_pulse_does_not_clear_ovc(self):
        await self.select('pulse');await self.select('ovc');await self.drive(pulse=12,ovc=40)
        self.pulse.emergency_zero();since=time.monotonic();await self.drive(.35,ovc=40)
        self.assertTrue(self.app.pulses('ovc',since=since));self.assertFalse(self.app.pulses('coyote',since=since+.04))
        self.assertFalse(any(r['at']>since and r['m']=='device.op.clear' and r['data']['s']=='ovc' for r in self.app.records))
    async def test_accessory_missing_blocks_only_its_channel(self):
        await self.select('pulse');await self.select('ovc')
        await self.app.patch_slot('ovc',props={'channelAStatus':False})
        await asyncio.sleep(.05);await self.drive(pulse=12,ovc=40)
        self.assertFalse(self.app.pulses('ovc'));self.assertTrue(self.app.pulses('coyote'))
    async def test_invalid_plan_closes_permission_and_clears(self):
        await self.select('ovc');await self.drive(ovc=30)
        bad=frame(300);self.assertFalse(self.ovc.submit_plan({'A':bad,'B':None}))
        since=time.monotonic();await asyncio.sleep(.2)
        self.assertFalse(self.app.pulses('ovc',since=since+.02));self.assertFalse(self.ovc.snapshot()['output_active'])
    async def test_channel_stop_leaves_peer_channel_running(self):
        await self.select('ovc')
        for _ in range(4):
            self.ovc.set_output_permission(True,hard_limits={'A':80,'B':80})
            self.ovc.submit_plan({'A':frame(30),'B':frame(40)});await asyncio.sleep(.06)
        since=time.monotonic();self.ovc.stop_channel('A')
        for _ in range(4):
            self.ovc.set_output_permission(True,hard_limits={'A':80,'B':80})
            self.ovc.submit_plan({'A':None,'B':frame(40)});await asyncio.sleep(.06)
        self.assertFalse(self.app.pulses('ovc','A',since+.04));self.assertTrue(self.app.pulses('ovc','B',since))
    async def test_ovc_sub_ten_request_never_writes_nonzero_intensity(self):
        await self.select('ovc');await self.drive(ovc=9.99)
        self.assertFalse(self.app.strengths('ovc'));self.assertFalse(self.app.pulses('ovc'))
    async def test_device_cap_reduction_is_enforced(self):
        await self.select('ovc');await self.drive(ovc=80)
        await self.app.patch_slot('ovc',slotState={'channelA':{'intensityMax':35}})
        await self.drive(.4,ovc=80)
        self.assertEqual(self.app.strengths('ovc')[-1]['data']['v'],30)
    async def test_cap_reduction_does_not_require_or_repeat_a_new_wave_frame(self):
        await self.select('ovc');self.ovc.set_output_permission(True,hard_limits={'A':100,'B':100})
        self.ovc.submit_plan({'A':frame(80),'B':None});await self.until(lambda:len(self.app.pulses('ovc'))==1)
        await self.app.patch_slot('ovc',slotState={'channelA':{'intensityMax':25}})
        await self.until(lambda:self.app.strengths('ovc')[-1]['data']['v']==20)
        self.assertEqual(len(self.app.pulses('ovc')),1)
    async def test_rpc_waiting_for_shared_writer_lock_is_revoked_before_send(self):
        await self.select('pulse');loop=self.hub._hub._loop;ready=threading.Event();release={}
        async def hold():
            lock=self.hub._hub._rpc_send_locks[self.app.client_id]
            async with lock:
                release['event']=asyncio.Event();ready.set();await release['event'].wait()
        future=asyncio.run_coroutine_threadsafe(hold(),loop)
        await self.until(ready.is_set)
        self.pulse.set_output_permission(True,hard_limits={'A':40,'B':40})
        self.pulse.submit_plan({'A':frame(30),'B':None});await asyncio.sleep(.04)
        self.pulse.set_output_permission(False,'paused');loop.call_soon_threadsafe(release['event'].set)
        await asyncio.wrap_future(future);await asyncio.sleep(.16)
        self.assertFalse(self.app.strengths('coyote'));self.assertFalse(self.app.pulses('coyote'))
    async def test_ovc_failure_does_not_disconnect_electrical_route(self):
        await self.select('pulse');await self.select('ovc');self.app.reject_slot='ovc'
        # One OVC write rejected by APP; Coyote stays usable on the shared WS.
        self.ovc.set_output_permission(True,hard_limits={'A':50,'B':50});self.ovc.submit_plan({'A':frame(30),'B':None})
        await asyncio.sleep(.15);await self.drive(.25,pulse=11)
        self.assertTrue(self.pulse.snapshot()['connected']);self.assertTrue(self.app.pulses('coyote'))

    async def test_sleeping_ovc_catalog_refresh_does_not_interrupt_pulse_stream(self):
        self.hub._hub._discovery_interval=.2
        await self.select('pulse');await self.select('ovc')
        await self.drive(.3,pulse=12,ovc=40)
        since=time.monotonic();self.app.devices.pop()
        await self.drive(.9,pulse=12)
        self.assertTrue(self.hub.snapshot()['app_connected'])
        self.assertFalse(self.ovc.snapshot()['connected'])
        receipts=self.app.pulses('coyote',since=since)
        self.assertGreaterEqual(len(receipts),6)
        self.assertLess(max(b['at']-a['at'] for a,b in zip(receipts,receipts[1:])),.25)

class RpcFutureCleanup(unittest.IsolatedAsyncioTestCase):
    async def test_disconnect_during_failed_write_does_not_orphan_its_waiter(self):
        loop=asyncio.get_running_loop();reported=[];previous=loop.get_exception_handler()
        loop.set_exception_handler(lambda _loop,context:reported.append(context))
        route=DGLabV4Bridge(queue.Queue(),port=0,lan_ip='127.0.0.1')
        class Socket:
            async def send(self,raw):
                request=json.loads(raw)['data']
                route._finish_pending(request['reqId'],error=ConnectionError('APP disconnected'))
                raise ConnectionError('Socket write interrupted')
        route._clients['test-app']=Socket()
        try:
            with self.assertRaisesRegex(ConnectionError,'Socket write interrupted'):
                await route._rpc('device.op.clear',{'s':'test'},client_id='test-app',safety=True,wait=True)
            gc.collect();await asyncio.sleep(.01)
            self.assertFalse(route._pending)
            self.assertFalse([r for r in reported if 'exception was never retrieved' in r.get('message','')])
        finally:loop.set_exception_handler(previous)
    async def test_cleanup_does_not_swallow_an_awaited_app_rejection(self):
        route=DGLabV4Bridge(queue.Queue(),port=0,lan_ip='127.0.0.1')
        class Socket:
            async def send(self,raw):
                request=json.loads(raw)['data']
                route._finish_pending(request['reqId'],error=ValueError('APP rejected zero'))
        route._clients['test-app']=Socket()
        with self.assertRaisesRegex(ValueError,'APP rejected zero'):
            await route._rpc('device.op.clear',{'s':'test'},client_id='test-app',safety=True,wait=True)
        self.assertFalse(route._pending)
