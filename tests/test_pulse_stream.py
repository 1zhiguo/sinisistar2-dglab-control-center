import asyncio,json,tempfile,time,unittest
from pathlib import Path
from sinisistar_dglab.dglab import ConnectionService,PLAN_LEASE_SECONDS,stream_frame
from sinisistar_dglab.mock_app import MockApp

def frame(peak=12,samples=None,hz=30):return dict(peak=peak,samples=samples if samples is not None else [peak]*4,frequencies=[hz]*4)

class Streams(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.service=ConnectionService(port=0,host='127.0.0.1',lan_ip='127.0.0.1',heartbeat_seconds=.1)
        self.service.start();await self.until(lambda:self.service.snapshot()['server_ready'])
        s=self.service.snapshot();self.url=f"ws://127.0.0.1:{s['port']}/{s['controller_id']}"
        self.app=await MockApp((40,45)).connect(self.url,s['controller_id'])
        await self.until(lambda:self.service.snapshot()['feedback_known'])
    async def asyncTearDown(self):
        await asyncio.to_thread(self.service.stop);await self.app.close()
    async def until(self,predicate,seconds=2):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            if predicate():return
            await asyncio.sleep(.01)
        self.fail('condition did not settle: '+str(self.service.snapshot()))
    def publish(self,a=None,b=None):
        self.assertTrue(self.service.set_output_permission(True,hard_limits={'A':20,'B':25}))
        self.assertTrue(self.service.submit_plan({'A':a,'B':b},generated_at=time.monotonic()))
    async def pump(self,a,b,duration=.4):
        end=time.monotonic()+duration
        while time.monotonic()<end:
            self.publish(a,b);await asyncio.sleep(.08)
    async def test_both_channels_have_independent_frequency_and_strength(self):
        await self.pump(frame(12,hz=50),frame(18,hz=20),.45)
        self.assertGreaterEqual(len(self.app.pulses('A')),3);self.assertGreaterEqual(len(self.app.pulses('B')),3)
        self.assertEqual(self.app.pulses('A')[-1]['frequency_bytes'],[20]*4)
        self.assertEqual(self.app.pulses('B')[-1]['frequency_bytes'],[50]*4)
        self.assertEqual(self.app.strengths,[12,18]);self.assertEqual(self.app.issues,[])
    async def test_stopping_a_does_not_zero_or_clear_b(self):
        await self.pump(frame(12),frame(18),.25);since=time.monotonic()
        await self.pump(None,frame(18),.4)
        self.assertTrue(self.app.pulses('B',since));self.assertFalse(self.app.pulses('A',since+.05))
        b_clears=[x for x in self.app.commands if x.get('channel')=='B' and x['at']>=since and (x['kind']=='clear' or x.get('strength')==0)]
        self.assertEqual(b_clears,[]);self.assertEqual(self.app.strengths,[0,18])
    async def test_a_updates_do_not_restart_b(self):
        await self.pump(frame(7),frame(15),.22);since=time.monotonic()
        await self.pump(frame(16,hz=80),frame(15),.35)
        self.assertEqual(self.app.strengths,[16,15])
        self.assertTrue(self.app.pulses('B',since))
        self.assertFalse(any(x['kind']=='clear' and x.get('channel')=='B' and x['at']>=since for x in self.app.commands))
    async def test_a_single_frame_is_not_repeated_and_expires(self):
        self.publish(frame(10),frame(11));await asyncio.sleep(PLAN_LEASE_SECONDS+.12)
        self.assertEqual(len(self.app.pulses('A')),1);self.assertEqual(len(self.app.pulses('B')),1)
        self.assertEqual(self.app.strengths,[0,0]);self.assertFalse(self.service.snapshot()['output_active'])
    async def test_permission_lease_expires_even_if_frames_are_submitted(self):
        self.publish(frame(10),frame(11))
        end=time.monotonic()+.85
        while time.monotonic()<end:
            self.service.submit_plan({'A':frame(10),'B':frame(11)},generated_at=time.monotonic());await asyncio.sleep(.08)
        self.assertEqual(self.app.strengths,[0,0]);self.assertFalse(self.service.snapshot()['output_allowed'])
    async def test_pause_revokes_pending_and_no_replay_on_resume(self):
        # Establish observable nonzero output first. Initial APP feedback is
        # already [0,0]; treating that startup value as a completed pause can
        # resume before pre-revoke bytes have even arrived at the APP.
        end=time.monotonic()+2
        while not (self.app.strengths==[10,11] and self.app.pulses('A') and self.app.pulses('B')):
            self.publish(frame(10),frame(11));await asyncio.sleep(.04)
            self.assertLess(time.monotonic(),end,'initial output did not reach the mock APP')
        cursor=len(self.app.commands)
        self.service.set_output_permission(False,'暂停')
        # V3 has no clear acknowledgment. The Mock APP observing both clears
        # is the deterministic ordered-WS barrier: every earlier wave was
        # consumed, and any genuine post-zero replay will still fail below.
        await self.until(lambda:self.app.strengths==[0,0] and
                         {r.get('channel') for r in self.app.commands[cursor:] if r['kind']=='clear'}=={'A','B'})
        # Windows monotonic timestamps can tie across the pause barrier. Check
        # receive order so a pre-pause packet with the same time is not replay.
        resumed_cursor=len(self.app.commands);self.service.set_output_permission(True)
        await asyncio.sleep(.17)
        self.assertFalse([r for r in self.app.commands[resumed_cursor:] if r.get('kind')=='pulse'])
    async def test_app_cap_decrease_only_changes_the_affected_channel(self):
        await self.pump(frame(18),frame(20),.25);await self.app.set_limits(5,45)
        await self.until(lambda:self.service.snapshot()['limit_a']==5);since=time.monotonic()
        await self.pump(frame(18),frame(20),.35)
        self.assertEqual(self.app.strengths,[5,20])
        self.assertTrue(all(x['strength']<=5 for x in self.app.pulses('A',since+.05)))
        self.assertFalse(any(x['kind']=='clear' and x.get('channel')=='B' and x['at']>=since for x in self.app.commands))
    async def test_invalid_or_stale_plan_fails_closed(self):
        await self.pump(frame(12),frame(14),.15)
        self.assertFalse(self.service.submit_plan({'A':frame(10,samples=[float('nan')]*4),'B':frame(10)},generated_at=time.monotonic()))
        await self.until(lambda:self.app.strengths==[0,0])
        self.assertFalse(self.service.submit_plan({'A':frame(10),'B':frame(10)},generated_at=time.monotonic()-1))
    async def test_replacement_app_does_not_inherit_old_frames(self):
        await self.pump(frame(9),frame(10),.18);await self.app.close()
        await self.until(lambda:not self.service.snapshot()['connected'])
        self.app=await MockApp().connect(self.url,self.service.snapshot()['controller_id'])
        await self.until(lambda:self.service.snapshot()['feedback_known']);self.service.set_output_permission(True)
        await asyncio.sleep(.18)
        self.assertFalse(self.app.pulses('A'));self.assertFalse(self.app.pulses('B'))
    async def test_quantized_absolute_samples_respect_final_strength(self):
        self.publish(frame(12,samples=[0,3,6,9]),None)
        await self.until(lambda:bool(self.app.pulses('A')))
        self.assertEqual(self.app.pulses('A')[0]['amplitudes'],[0,25,50,75])
    async def test_legacy_single_channel_api_does_not_cancel_other_channel(self):
        self.service.set_output_permission(True)
        self.assertTrue(self.service.play_feedback('A',7,.25,[1,1],30,20))
        self.assertTrue(self.service.play_feedback('B',9,.25,[1,1],30,20))
        await self.until(lambda:bool(self.app.pulses('A')) and bool(self.app.pulses('B')))
    async def test_streams_continue_beyond_old_five_second_effect_limit(self):
        await self.pump(frame(12),frame(18),5.4)
        first=min(x['at'] for x in self.app.pulses('A'))
        self.assertTrue(self.app.pulses('A',first+5));self.assertTrue(self.app.pulses('B',first+5))
        self.assertEqual(self.app.strengths,[12,18]);self.assertEqual(self.app.issues,[])
    async def test_immediate_revoke_and_new_lease_does_not_cancel_new_frames(self):
        await self.pump(frame(12),frame(18),.2)
        self.service.set_output_permission(False,'暂停后立即恢复')
        since=time.monotonic();await self.pump(frame(5),frame(6),.35)
        self.assertEqual(self.app.strengths,[5,6]);self.assertTrue(self.app.pulses('A',since+.1))
        late_zero=[r for r in self.app.commands if r['at']>since+.1 and r['kind']=='strength' and r['strength']==0]
        self.assertEqual(late_zero,[])
    async def test_frames_waiting_for_writer_lock_are_revoked_before_send(self):
        await self.service._command_lock.acquire()
        try:
            self.publish(frame(12),frame(18));await asyncio.sleep(.03)
            self.service.set_output_permission(False,'暂停撤销未发送帧')
        finally:self.service._command_lock.release()
        await asyncio.sleep(.12)
        self.assertFalse(self.app.pulses('A'));self.assertFalse(self.app.pulses('B'))

if __name__=='__main__':unittest.main()
