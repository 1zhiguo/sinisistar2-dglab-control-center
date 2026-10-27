"""Game snapshots -> production Backend -> real Socket -> loopback MockApp."""
import asyncio,json,queue,tempfile,time,unittest
from copy import deepcopy
from pathlib import Path
from PySide6.QtGui import QGuiApplication
from sinisistar_dglab.backend import Backend
from sinisistar_dglab.dglab import ConnectionService
from sinisistar_dglab.mock_app import MockApp
from sinisistar_dglab.simulation import default_profile

ROOT=Path(__file__).resolve().parents[1]
TMP=ROOT/'artifacts/test-temp';TMP.mkdir(parents=True,exist_ok=True)
AUDIT=ROOT/'artifacts/pulse-validation';AUDIT.mkdir(parents=True,exist_ok=True)

class Observer:
    def __init__(self):
        self.events=queue.Queue();self.stale=False
        self.s=dict(source='bepinex',session='mock-game',pid=123,player=456,scene_id=43,scene='Monastery_Tutorial1',valid=True,live=True,
                    sample_id=1,sampled_at=time.monotonic(),hp={'current':100,'max':100},mp={'current':100,'max':100},
                    time_scale=1,paused=False,loading=False,bound=False,broken=False,abnormals=[],event_playing=False,flow={})
    def snapshot(self):
        self.s['sample_id']+=1;self.s['sampled_at']=time.monotonic()-(2 if self.stale else 0)
        return deepcopy(self.s)
    def recent_events(self,session):return []
    def stop(self):pass

class Pipeline(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):cls.qt=QGuiApplication.instance() or QGuiApplication([])
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=TMP)
        self.b=Backend(offline=True,settings=Path(self.temp.name)/'settings.json');self.b._timer.stop()
        # Each pipeline case sets exact rule values, independently of user tiers.
        self.b._sim_profile=default_profile()
        self.obs=Observer();self.b._observer=self.obs
        for r in self.b._sim_profile['rules'].values():r['enabled']=False
        for r in self.b._sim_profile['abnormals'].values():r['enabled']=False
        self.service=ConnectionService(port=0,host='127.0.0.1',lan_ip='127.0.0.1',heartbeat_seconds=.1)
        self.b._service=self.service;self.service.start()
        await self.until(lambda:self.service.snapshot()['server_ready'])
        c=self.service.snapshot();self.url=f"ws://127.0.0.1:{c['port']}/{c['controller_id']}"
        self.app=await MockApp((30,35)).connect(self.url,c['controller_id'])
        await self.until(lambda:self.service.snapshot()['feedback_known'])
        self.b.toggleArm()
    async def asyncTearDown(self):
        # Let the mock client's event loop process shutdown while the Socket
        # thread finishes; do not block that event loop with a thread join.
        await asyncio.to_thread(self.service.stop);self.b.shutdown();await self.app.close()
        record=dict(test=self._testMethodName,transport='127.0.0.1 only',hardware_connected=False,
                    commands=self.app.commands,issues=self.app.issues,final_output=self.service.snapshot())
        (AUDIT/(self._testMethodName+'.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
        self.temp.cleanup()
    async def until(self,fn,seconds=2):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            if fn():return
            await asyncio.sleep(.01)
        self.fail('mock connection did not settle')
    def rule(self,key,channel='A',strength=10,priority=80):
        r=self.b._sim_profile['rules'][key]
        r.update(enabled=True,pulse_enabled=True,pulse_channel=channel,pulse_strength=strength,pulse_gain=0,
                 pulse_wave='pulse',pulse_period=.4,duration=.35,cooldown=0,priority=priority,pulse_max=False)
    async def drive(self,seconds=.22):
        end=time.monotonic()+seconds
        while time.monotonic()<end:self.b.tick();await asyncio.sleep(.07)
    async def test_clothing_break_sends_once_and_stops_while_still_broken(self):
        self.rule('break','A',7);self.b._sim_profile['rules']['break']['duration']=.3
        await self.drive();self.obs.s['broken']=True;await self.drive(.14)
        self.assertEqual(self.app.strengths,[7,0]);self.assertTrue(self.app.pulses('A'))
        await self.drive(.5);self.assertEqual(self.app.strengths,[0,0]);since=time.monotonic()
        await self.drive(.3);self.assertFalse(self.app.pulses('A',since))
        self.obs.s['broken']=False;await self.drive(.14);self.assertEqual(self.app.strengths,[0,0])
        self.obs.s['broken']=True;await self.drive(.14);self.assertEqual(self.app.strengths,[7,0])
    async def test_mp_loss_is_ignored_while_hp_damage_reaches_app(self):
        self.rule('hp_loss','A',9)
        await self.drive();self.assertFalse(self.app.pulses('A'));self.assertFalse(self.app.pulses('B'))
        self.obs.s['mp']['current']=85;await self.drive(.22)
        self.assertFalse(self.app.pulses('A'));self.assertFalse(self.app.pulses('B'))
        self.obs.s['hp']['current']=90
        await self.drive(.22)
        self.assertTrue(self.app.pulses('A'));self.assertFalse(self.app.pulses('B'))
        self.assertEqual(self.app.strengths,[9,0]);self.assertEqual(self.app.issues,[])
        await self.drive(.5);self.assertEqual(self.app.strengths,[0,0])
    async def test_grab_hold_and_hp_burst_continue_without_mp_trigger(self):
        self.rule('grab_hold','B',4,30);self.rule('grab_hp_loss','A',11)
        self.obs.s.update(bound=True,binder='Zombie');await self.drive(.22)
        self.assertEqual(self.app.strengths,[0,4]);since=time.monotonic()
        self.obs.s['hp']['current']=90;await self.drive(.14)
        self.assertEqual(self.app.strengths,[11,4])
        self.obs.s['mp']['current']=80;await self.drive(.14)
        self.assertEqual(self.app.strengths,[11,4])
        await self.drive(.5);self.assertEqual(self.app.strengths,[0,4])
        self.assertFalse(any(x['kind']=='clear' and x.get('channel')=='B' and x['at']>since for x in self.app.commands))
        self.obs.s['bound']=False;await self.drive(.18);self.assertEqual(self.app.strengths,[0,0])
    async def test_abnormal_level_updates_and_type_removal(self):
        for name,channel in [('Defilement','A'),('Poison','B')]:
            self.b._sim_profile['abnormals'][name].update(enabled=True,pulse_channel=channel,pulse_strength=5,pulse_level_step=2)
        self.obs.s['abnormals']=[{'name':'Defilement','level':1},{'name':'Poison','level':1}]
        await self.drive(.24);self.assertEqual(self.app.strengths,[10,10])
        self.obs.s['abnormals'][0]['level']=3;await self.drive(.2);self.assertEqual(self.app.strengths,[10,10])
        since=time.monotonic();self.obs.s['abnormals']=[{'name':'Poison','level':1}]
        await self.drive(.2);self.assertEqual(self.app.strengths,[0,10]);self.assertTrue(self.app.pulses('B',since))
        self.obs.s['abnormals']=[];await self.drive(.2);self.assertEqual(self.app.strengths,[0,0])
    async def test_abnormal_baseline_survives_death_hold_and_updates_by_distinct_type(self):
        self.rule('defeat_hold','A',10);self.obs.s.update(bound=True,binder='Zombie');self.obs.s['hp']['current']=0
        for name in ('InfertilityBlessing','Defilement'):self.b._sim_profile['abnormals'][name]['enabled']=True
        self.obs.s['abnormals']=[{'name':'InfertilityBlessing','level':1},{'name':'Defilement','level':2}]
        await self.drive(.24);self.assertEqual(self.app.strengths,[10,0])
        self.obs.s['abnormals'][1]['level']=5;await self.drive(.2);self.assertEqual(self.app.strengths,[10,0])
        self.obs.s['abnormals']=self.obs.s['abnormals'][:1];await self.drive(.2);self.assertEqual(self.app.strengths,[10,0])
        self.obs.s.update(bound=False);self.obs.s['hp']['current']=100
        await self.drive(.22);self.assertEqual(self.app.strengths,[0,0])
        self.obs.s['abnormals']=[];await self.drive(.18);self.assertEqual(self.app.strengths,[0,0])
    async def test_only_status_feedback_crosses_unclassified_cg_and_zero_hp(self):
        self.rule('hp_loss','B',15);self.rule('grab_hold','B',9)
        self.b._sim_profile['abnormals']['Poison']['enabled']=True
        self.obs.s['abnormals']=[{'name':'Poison','level':1}]
        self.obs.s.update(event_playing=True,flow={'playing':True,'valid':True,'key':'cg','elapsed':2})
        await self.drive(.24);self.assertEqual(self.app.strengths,[10,0])
        self.obs.s['hp']['current']=0;await self.drive(.24);self.assertEqual(self.app.strengths,[10,0])
        self.obs.s['abnormals']=[];await self.drive(.18);self.assertEqual(self.app.strengths,[0,0])
    async def test_status_fixed_value_cannot_be_overridden_and_kinds_add_on_the_wire(self):
        for name in ('Poison','Slow'):self.b._sim_profile['abnormals'][name]['enabled']=True
        self.b.setSimulationSetting('pulse_abnormal_base',14);self.b.setSimulationSetting('pulse_stack_bonus',3)
        self.obs.s['abnormals']=[{'name':'Poison','level':1},{'name':'Slow','level':1}]
        await self.drive(.25);self.assertEqual(self.app.strengths,[20,0])
    async def test_pause_and_stale_source_zero_and_do_not_replay_damage(self):
        self.rule('hp_loss','A',10);await self.drive();self.obs.s['hp']['current']=90;await self.drive(.12)
        self.obs.s['paused']=True;await self.drive(.14);self.assertEqual(self.app.strengths,[0,0])
        self.obs.s['paused']=False;since=time.monotonic();await self.drive(.22)
        self.assertFalse(self.app.pulses('A',since))
        self.obs.s['hp']['current']=80;await self.drive(.12);self.obs.stale=True;await self.drive(.15)
        self.assertEqual(self.app.strengths,[0,0])
    async def test_cg_and_unbound_zero_hp_are_blocked_even_with_enabled_flow_rules(self):
        self.rule('grab_hold','A',8);self.obs.s['bound']=True;await self.drive()
        self.assertTrue(self.app.pulses('A'))
        self.obs.s['flow']={'playing':True,'valid':True,'key':'cg','elapsed':2};self.obs.s['event_playing']=True
        await self.drive(.15);self.assertEqual(self.app.strengths,[0,0])
        self.obs.s.update(event_playing=False,flow={},bound=False);self.obs.s['hp']['current']=0
        since=time.monotonic();await self.drive(.2);self.assertFalse(self.app.pulses('A',since))
    async def test_zero_hp_capture_continues_without_hp_delta_until_release(self):
        self.rule('grab_hold','B',4,30);self.rule('defeat_hold','AB',12,60)
        self.obs.s.update(bound=True,binder='Zombie');await self.drive(.22)
        self.assertEqual(self.app.strengths,[0,4])
        self.obs.s['hp']['current']=0;await self.drive(.22)
        self.assertEqual(self.app.strengths,[12,12])
        # No further numeric HP loss or callback is required; the current
        # captive state keeps publishing new frames beyond a burst's duration.
        since=time.monotonic();await self.drive(1.3)
        self.assertTrue(self.app.pulses('A',since+1));self.assertTrue(self.app.pulses('B',since+1))
        self.assertEqual(self.app.strengths,[12,12]);self.assertEqual(self.app.issues,[])
        self.obs.s['bound']=False;await self.drive(.18)
        self.assertEqual(self.app.strengths,[12,12])
        self.obs.s['hp']['current']=100;await self.drive(.18)
        self.assertEqual(self.app.strengths,[0,0])
    async def test_zero_hp_capture_pause_resume_rebind_and_revival(self):
        self.rule('defeat_hold','AB',9);self.obs.s.update(bound=True,binder='Zombie');self.obs.s['hp']['current']=0
        await self.drive(.22);self.assertEqual(self.app.strengths,[9,9])
        self.obs.s['paused']=True;await self.drive(.16);self.assertEqual(self.app.strengths,[0,0])
        self.obs.s['paused']=False;await self.drive(.22);self.assertEqual(self.app.strengths,[9,9])
        self.obs.stale=True;await self.drive(.16);self.assertEqual(self.app.strengths,[0,0])
        self.obs.stale=False;await self.drive(.22);self.assertEqual(self.app.strengths,[9,9])
        self.obs.s['player']=999;self.obs.s['hp']['current']=100
        await self.drive(.22);self.assertEqual(self.app.strengths,[0,0])
    async def test_zero_hp_captive_player_with_flow_flag_only_uses_capture_rule(self):
        from sinisistar_dglab.simulation import base_rule
        self.rule('defeat_hold','B',8);self.obs.s.update(bound=True,event_playing=True,flow={'playing':True,'valid':True,'key':'cg','elapsed':2})
        self.obs.s['hp']['current']=0
        self.b._sim_profile['flows']=[base_rule('cg','CG rule',priority=100)]
        await self.drive(.24);self.assertEqual(self.app.strengths,[0,8])
        self.obs.s['flow']['paused']=True;await self.drive(.16);self.assertEqual(self.app.strengths,[0,0])
    async def test_zero_hp_stop_option_and_rule_disable_are_respected(self):
        self.rule('grab_hold','A',4);self.rule('defeat_hold','A',8)
        self.obs.s.update(bound=True);self.obs.s['hp']['current']=0
        self.b._sim_profile['zero_hp_mode']='stop';await self.drive(.24);self.assertEqual(self.app.strengths,[0,0])
        self.b._sim_profile['zero_hp_mode']='capture';await self.drive(.24);self.assertEqual(self.app.strengths,[8,0])
        self.b._sim_profile['rules']['defeat_hold']['enabled']=False;await self.drive(.18)
        self.assertEqual(self.app.strengths,[0,0])
    async def test_death_wave_loops_at_custom_channel_strengths_until_revival(self):
        self.b._sim_profile['rules']['defeat_hold'].update(enabled=True,pulse_strength_a=9,pulse_strength_b=14)
        self.b._channels[0]['limit']=13;self.b._channels[1]['limit']=17
        self.obs.s['hp']['current']=0;self.obs.s.update(bound=False,time_scale=0)
        await self.drive(1.9);self.assertEqual(self.app.strengths,[9,14])
        since=time.monotonic();self.obs.s.update(bound=False,event_playing=True,flow={'playing':True,'valid':True,'elapsed':2,'key':'death'})
        await self.drive(.3);self.assertTrue(self.app.pulses('A',since));self.assertTrue(self.app.pulses('B',since))
        allowed={0,11,26,29,44,58,60,67,76,81,83,89,92,93,94}
        for c in ('A','B'):
            for row in self.app.pulses(c):
                self.assertEqual(row['frequency_bytes'],[72]*4)
                self.assertTrue(set(row['amplitudes'])<=allowed)
        self.obs.s.update(event_playing=False,flow={},time_scale=1);self.obs.s['hp']['current']=100
        await self.drive(.2);self.assertEqual(self.app.strengths,[0,0]);self.assertEqual(self.app.issues,[])
    async def test_confirmed_defeat_cg_can_keep_death_after_hp_restored(self):
        self.b._sim_profile['rules']['defeat_hold']['enabled']=True
        self.obs.s.update(event_playing=True,flow={'playing':True,'valid':True,'defeat_confirmed':True,'key':'death','elapsed':2})
        await self.drive(.24);self.assertEqual(self.app.strengths,[20,20])
        self.obs.s.update(event_playing=False,flow={});await self.drive(.2);self.assertEqual(self.app.strengths,[0,0])
    async def test_cg_status_gate_discards_an_earlier_hit_burst(self):
        self.rule('hp_loss','B',15);await self.drive(.2)
        self.obs.s['hp']['current']=90;await self.drive(.1);self.assertEqual(self.app.strengths,[0,15])
        self.b._sim_profile['abnormals']['Poison']['enabled']=True
        self.obs.s.update(event_playing=True,flow={'playing':True,'valid':True,'key':'ordinary'},abnormals=[{'name':'Poison','level':1}])
        await self.drive(.15);self.assertEqual(self.app.strengths,[10,0])
    async def test_demo_or_non_loopback_route_cannot_publish(self):
        self.rule('grab_hold','A',8);self.obs.s['bound']=True;await self.drive()
        self.b.simulationSource('grab_hp');await self.drive(.2);self.assertEqual(self.app.strengths,[0,0])
        self.b.simulationSource('live');self.service._state['local_only']=False
        since=time.monotonic();await self.drive(.2);self.assertFalse(self.app.pulses('A',since))
    async def test_configuration_edit_disarms_and_emergency_clears_both(self):
        self.rule('grab_hold','AB',7);self.obs.s['bound']=True;await self.drive()
        self.b.setSimulationSetting('pulse_cap_a',3);await self.drive(.15)
        self.assertFalse(self.b.state['armed']);self.assertEqual(self.app.strengths,[0,0])
        self.b.toggleArm();await self.drive(.22);self.assertEqual(self.app.strengths,[3,7])
        self.b.emergencyStop();await self.drive(.15)
        self.assertEqual(self.app.strengths,[0,0]);self.assertFalse(self.b.state['armed'])
    async def test_rebind_does_not_turn_hp_reset_into_a_new_hit(self):
        self.rule('hp_loss','A',10);await self.drive();self.obs.s['hp']['current']=90;await self.drive(.12)
        self.obs.s['player']=999;self.obs.s['hp']['current']=50;since=time.monotonic();await self.drive(.3)
        self.assertFalse(self.app.pulses('A',since+.04));self.assertEqual(self.app.strengths,[0,0])
    async def test_channel_mute_does_not_interrupt_the_other_channel(self):
        self.rule('grab_hold','AB',7);self.obs.s['bound']=True;await self.drive(.24)
        self.b.setPulseChannelEnabled('A',False);since=time.monotonic();await self.drive(.24)
        self.assertEqual(self.app.strengths,[0,7]);self.assertTrue(self.app.pulses('B',since))
        self.assertFalse(any(r['kind']=='clear' and r.get('channel')=='B' and r['at']>since for r in self.app.commands))
        self.b.setPulseChannelEnabled('A',True);await self.drive(.2);self.assertEqual(self.app.strengths,[7,7])
    async def test_builtin_mock_runner_connects_without_arming_automatically(self):
        await self.app.close();await self.until(lambda:not self.service.snapshot()['connected'])
        self.b.offline=False;self.b.startMockPulse()
        await self.until(lambda:self.b.state['mockApp']['connected'] and self.service.snapshot()['feedback_known'])
        self.assertFalse(self.b.state['armed']);self.assertFalse(self.b.state['outputActive'])
        self.rule('grab_hold','B',6);self.obs.s['bound']=True;self.b.toggleArm();await self.drive(.35)
        self.assertGreater(self.b.state['mockApp']['pulsesB'],0);self.assertEqual(self.service.snapshot()['strength_b'],6)
    async def test_hud_display_edits_leave_pulse_streams_running(self):
        self.rule('grab_hold','AB',7);self.obs.s['bound']=True;await self.drive(.24)
        since=time.monotonic();self.b.setHudSetting('opacity',65);self.b.setHudSetting('layout','expanded');self.b.setHudAdjusting(True)
        await self.drive(.24)
        self.assertTrue(self.b.state['armed']);self.assertEqual(self.app.strengths,[7,7])
        self.assertTrue(self.app.pulses('A',since));self.assertTrue(self.app.pulses('B',since))
        self.assertFalse(any(r['kind']=='clear' and r['at']>since for r in self.app.commands))

if __name__=='__main__':unittest.main()
