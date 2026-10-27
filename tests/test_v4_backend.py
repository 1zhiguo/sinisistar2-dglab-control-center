"""Synthetic game -> production Backend -> V4/OVC wire, loopback only."""
import asyncio,json,queue,tempfile,time,unittest
from copy import deepcopy
from pathlib import Path
from datetime import datetime,timezone
from PySide6.QtGui import QGuiApplication
from sinisistar_dglab.backend import Backend
from sinisistar_dglab.v4 import V4ConnectionService
from sinisistar_dglab.mock_v4 import MockV4App

ROOT=Path(__file__).resolve().parents[1]
TMP=ROOT/'artifacts/test-temp';TMP.mkdir(parents=True,exist_ok=True)
AUDIT=ROOT/'artifacts/v4-validation';AUDIT.mkdir(parents=True,exist_ok=True)

class Game:
    def __init__(self):
        self.events=queue.Queue();self.stale=False
        self.s=dict(source='bepinex',session='mock-game-v4',pid=123,player=456,scene_id=43,scene='Monastery_Tutorial1',valid=True,live=True,
                    sample_id=0,sampled_at=time.monotonic(),hp={'current':100,'max':100},mp={'current':100,'max':100},
                    time_scale=1,paused=False,loading=False,bound=False,broken=False,abnormals=[],event_playing=False,flow={})
    def snapshot(self):
        self.s.update(sample_id=self.s['sample_id']+1,sampled_at=time.monotonic()-(2 if self.stale else 0));return deepcopy(self.s)
    def recent_events(self,session):return []
    def stop(self):pass

class V4Backend(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):cls.qt=QGuiApplication.instance() or QGuiApplication([])
    async def asyncSetUp(self):
        asyncio.get_running_loop().set_debug(False)
        self.temp=tempfile.TemporaryDirectory(dir=TMP);self.b=Backend(offline=True,settings=Path(self.temp.name)/'settings.json');self.b._timer.stop()
        self.game=Game();self.b._observer=self.game
        for rule in self.b._sim_profile['rules'].values():
            rule['enabled']=False
            # Transport cases use fixed targets unless they explicitly set a ramp;
            # do not inherit the selected factory tier's rising endpoints.
            for route in ('pulse','vibration'):
                for suffix in ('start_strength','start_strength_a','start_strength_b'):rule[route+'_'+suffix]=None
        for rule in self.b._sim_profile['abnormals'].values():rule['enabled']=False
        # Cases below specify short, fixed/rising defeat targets explicitly;
        # the user-facing factory minute loop is verified in the split-CG case.
        from sinisistar_dglab.cg_policy import make_cg
        self.b._sim_profile['cg']=make_cg(self.b._sim_profile['rules']['defeat_hold'])
        self.hub=V4ConnectionService(port=0,host='127.0.0.1',lan_ip='127.0.0.1');self.hub.start()
        await self.until(lambda:self.hub.snapshot()['server_ready'])
        state=self.hub.snapshot();self.app=await MockV4App().connect(f"ws://127.0.0.1:{state['port']}/?tid={state['controller_id']}")
        await self.until(lambda:len(self.hub.devices_snapshot())==2)
        self.b._v4=self.hub;self.b._service=self.hub.channel('pulse');self.b._ovc_service=self.hub.channel('ovc');self.b._connection['pulse_backend']='v4'
        self.b._ovc_limits={'A':80,'B':90};self.b._sim_profile.update(vibration_cap_a=80,vibration_cap_b=90)
        for role,slot in (('pulse','coyote'),('ovc','ovc')):
            self.b.selectV4Device(role,self.app.client_id,slot)
            await self.until(lambda:self.hub.channel(role).snapshot()['connected'])
        self.b.toggleArm();self.b.toggleOvcArm()
    async def asyncTearDown(self):
        await asyncio.to_thread(self.hub.stop)
        self.b._v4=None;self.b._service=None;self.b._ovc_service=None;self.b.shutdown();await self.app.close()
        (AUDIT/(self._testMethodName+'.json')).write_text(json.dumps(dict(hardware_connected=False,transport='127.0.0.1 only',requests=self.app.records),ensure_ascii=False,indent=2),encoding='utf-8')
        self.temp.cleanup()
    async def until(self,fn,seconds=2):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            if fn():return
            await asyncio.sleep(.01)
        self.fail('V4 mock pipeline did not settle')
    async def drive(self,seconds=.3):
        end=time.monotonic()+seconds
        while time.monotonic()<end:self.b.tick();await asyncio.sleep(.065)
    def rule(self,key,pulse='A',electrical=10,vibration='A',ovc=30):
        self.b._sim_profile['rules'][key].update(enabled=True,pulse_enabled=True,vibration_enabled=True,pulse_channel=pulse,
            pulse_strength=electrical,pulse_gain=0,pulse_wave='pulse',pulse_period=.4,pulse_max=False,
            vibration_channel=vibration,vibration_strength=ovc,vibration_gain=0,vibration_wave='ovc_surf_wave',vibration_period=1.3,vibration_max=False,
            duration=1.,cooldown=0)
    def commanded(self,role):return [self.hub.channel(role).snapshot()['output_channels'][c]['strength'] for c in 'AB']
    async def until_outputs_acknowledged(self,pulse,ovc,*,since=None):
        """Wait for both independent socket workers and actual APP receipts.

        Fixed sleeps can end immediately after a host scheduling or catalog-I/O
        stall. Keep providing fresh game samples; do not relax production leases.
        """
        end=time.monotonic()+2
        while time.monotonic()<end:
            self.b.tick();await asyncio.sleep(.04)
            reported={d['slotId']:[d['props']['intensityA'],d['props']['intensityB']] for d in self.app.devices}
            matched=self.commanded('pulse')==pulse and self.commanded('ovc')==ovc and reported['coyote']==pulse and reported['ovc']==ovc
            streamed=since is None or all(len(self.app.pulses(slot,c,since))>=2 for slot,values in (('coyote',pulse),('ovc',ovc)) for c,value in zip('AB',values) if value>0)
            if matched and streamed:return
        self.fail('Expected four-channel output and Mock APP acknowledgement did not settle')
    def gallery_fixture(self,index):
        rows=json.loads((ROOT/'tests/fixtures/gallery-0.4.2.json').read_text(encoding='utf-8'))
        self.game.s=deepcopy(rows[index])
    def configure_gallery(self):
        from sinisistar_dglab.gallery_policy import make_gallery
        c=make_gallery(self.b._sim_profile['rules']['defeat_hold']);self.b._sim_profile['gallery']=c
        self.b._waves.extend([dict(key='custom_ga_flat',points=[1,1],name='Gallery flat'),dict(key='custom_ga_half',points=[.5,.5],name='Gallery half')])
        self.b._vibration_custom.extend([dict(key='vib_custom_ga_flat',points=[1,1],name='Gallery flat'),dict(key='vib_custom_ga_half',points=[.5,.5],name='Gallery half')])
        c['rule'].update(enabled=True,pulse_channel='AB',vibration_channel='AB',pulse_strength_a=8,pulse_strength_b=12,
            pulse_start_strength_a=2,pulse_start_strength_b=4,vibration_strength_a=30,vibration_strength_b=40,
            vibration_start_strength_a=10,vibration_start_strength_b=20)
        for route,prefix in (('pulse','custom_ga_'),('vibration','vib_custom_ga_')):
            for channel in 'AB':c['routes'][route][channel].update(mode='fixed',wave=prefix+('flat' if channel=='A' else 'half'),period=1.,ramp_seconds=.3,ramp_mode='linear',ramp_scope='episode')
        return c
    async def test_hp_ablation_event_playback_drives_four_channels_then_stops(self):
        from cg_fixture import event_state
        config=self.configure_gallery();self.b._sim_profile['cg']=deepcopy(config)
        self.b._sim_profile['cg_detection_mode']='playback_only';self.game.s=event_state(time.monotonic())
        since=time.monotonic();await self.drive(.55);await self.until_outputs_acknowledged([8,12],[30,40],since=since)
        self.assertFalse(self.b._pulse_plan['hp_used']);self.assertFalse(self.b._ovc_plan['hp_used'])
        for hp in (1,0):
            self.game.s['hp']['current']=hp;await self.drive(.2);await self.until_outputs_acknowledged([8,12],[30,40])
        self.game.s['cg_playback']['event']['playing']=False;self.game.s['bound']=True
        self.game.s['feedback_evidence']=dict(locked_hp_active=True)
        await self.drive(.4);await self.until_outputs_acknowledged([0,0],[0,0])
    async def test_hp_ablation_gallery_animator_and_take_session_reach_four_channels(self):
        from cg_fixture import animator
        self.configure_gallery();self.b._sim_profile['cg_detection_mode']='playback_only';self.gallery_fixture(2)
        self.game.s.update(hp=None,event_playing=False,flow={})
        self.game.s['gallery'].update(play_type_raw=0,animator=animator())
        since=time.monotonic();await self.drive(.6);await self.until_outputs_acknowledged([8,12],[30,40],since=since)
        self.game.s['gallery']['ui_paused']=True;await self.drive(.3);await self.until_outputs_acknowledged([0,0],[0,0])
        self.game.s['gallery'].update(ui_paused=False,animator={},take_object_active=True,take_token_active=True,owner_path='Root')
        since=time.monotonic();await self.drive(.4);await self.until_outputs_acknowledged([8,12],[30,40],since=since)
        self.game.s['gallery']['selected_index_raw']=-1;await self.drive(.3);await self.until_outputs_acknowledged([0,0],[0,0])
    async def test_gallery_real_fields_drive_four_channels_and_space_freezes_then_resumes(self):
        self.configure_gallery();self.gallery_fixture(2)
        self.assertFalse(self.game.s['valid'])
        since=time.monotonic();await self.drive(.6);await self.until_outputs_acknowledged([8,12],[30,40],since=since)
        for slot in ('coyote','ovc'):
            self.assertNotEqual(self.app.pulses(slot,'A')[-1]['data']['v'],self.app.pulses(slot,'B')[-1]['data']['v'])
        self.game.s['flow']['paused']=True;self.game.s['event_paused']=True
        await self.drive(.18);await self.until_outputs_acknowledged([8,12],[30,40])
        self.game.s['gallery']['ui_paused']=True
        await self.drive(.2);await self.until_outputs_acknowledged([0,0],[0,0])
        age=self.b._pulse_planner.engine.gallery_clock.age;since=time.monotonic()
        await self.drive(.25)
        self.assertAlmostEqual(self.b._pulse_planner.engine.gallery_clock.age,age)
        self.assertFalse(self.app.pulses('coyote',since=since));self.assertFalse(self.app.pulses('ovc',since=since))
        self.game.s['gallery']['ui_paused']=False
        await self.drive(.2);await self.until_outputs_acknowledged([8,12],[30,40])
        self.assertGreater(self.b._pulse_plan['gallery_age'],age)
        self.gallery_fixture(3) # New index, old loaded take: do not send it.
        await self.drive(.15);await self.until_outputs_acknowledged([0,0],[0,0])
        self.gallery_fixture(4);self.b.tick()
        self.assertEqual(self.b._pulse_plan['gallery_age'],0)
        self.assertEqual(self.b._ovc_plan['gallery_age'],0)
        await self.drive(.45);await self.until_outputs_acknowledged([8,12],[30,40])
        self.gallery_fixture(9);self.game.s['flow']=dict(valid=True,playing=True,name='Failure',type='HierarchyEventPlayer')
        await self.drive(.2);await self.until_outputs_acknowledged([0,0],[0,0])
        self.assertFalse(any(self.b._pulse_plan['pulse_stream'].values()))
    async def test_gallery_queues_and_space_continue_option_reach_mock_app_then_stale_stops(self):
        c=self.configure_gallery();c['pause_on_stop']=False;self.gallery_fixture(8);self.game.s['gallery']['ui_paused']=True
        for route,prefix in (('pulse','custom_ga_'),('vibration','vib_custom_ga_')):
            for channel in 'AB':
                c['rule'][route+'_start_strength_'+channel.lower()]=None
                c['rule'][route+'_start_strength']=None
                keys=['flat','half'] if channel=='A' else ['half','flat']
                c['routes'][route][channel].update(mode='sequence' if channel=='A' else 'shuffle',loop=True,ramp_mode='constant',
                    queue=[dict(wave=prefix+key,seconds=.2,period=1.,scale=1.) for key in keys])
        since=time.monotonic();await self.drive(.85);await self.until_outputs_acknowledged([8,12],[30,40],since=since)
        for slot in ('coyote','ovc'):
            for channel in 'AB':
                frames=self.app.pulses(slot,channel,since)
                self.assertGreaterEqual(len({json.dumps(x['data']['v']) for x in frames}),2)
        self.assertGreater(self.b._pulse_plan['gallery_age'],.5)
        self.game.stale=True;await self.drive(.2);await self.until_outputs_acknowledged([0,0],[0,0])
    async def test_timed_death_stops_both_routes_without_retriggering_in_same_cg(self):
        self.rule('defeat_hold',pulse='AB',electrical=7,vibration='AB',ovc=30)
        self.b._sim_profile['rules']['defeat_hold'].update(death_mode='timed',death_seconds=.6,
            pulse_strength_a=7,pulse_strength_b=7,vibration_strength_a=30,vibration_strength_b=30,
            pulse_start_strength_a=3,pulse_start_strength_b=3,vibration_start_strength_a=10,vibration_start_strength_b=10,
            pulse_ramp_seconds=.3,vibration_ramp_seconds=.3)
        await self.drive();self.game.s['hp']['current']=0;await self.drive(.22)
        self.assertTrue(self.app.pulses('coyote','A'));self.assertTrue(self.app.pulses('ovc','B'))
        await self.drive(.8);await self.until_outputs_acknowledged([0,0],[0,0])
        since=time.monotonic()
        self.game.s.update(event_playing=True,flow=dict(valid=True,playing=True,defeat_confirmed=True,key='death'))
        await self.drive(.4)
        self.assertFalse(self.app.pulses('coyote','A',since));self.assertFalse(self.app.pulses('ovc','B',since))
        self.game.s.update(hp=dict(current=100,max=100),event_playing=False,flow={});await self.drive(.2)
        self.game.s['hp']['current']=0;since=time.monotonic();await self.drive(.22)
        self.assertTrue(self.app.pulses('coyote','A',since));self.assertTrue(self.app.pulses('ovc','B',since))

    async def test_pigpen_positive_hp_struggle_ramps_both_routes_until_success(self):
        self.rule('defeat_hold',pulse='AB',electrical=10,vibration='AB',ovc=70)
        self.b._sim_profile['rules']['defeat_hold'].update(pulse_strength_a=8,pulse_strength_b=10,
            pulse_start_strength_a=2,pulse_start_strength_b=4,pulse_ramp_seconds=.4,
            vibration_strength_a=60,vibration_strength_b=70,vibration_start_strength_a=20,vibration_start_strength_b=30,
            vibration_ramp_seconds=.4,death_mode='until_end')
        self.game.s.update(scene_id=166,scene='Road_2_2_Livestock',hp=dict(current=55,max=110),event_playing=True,
            flow=dict(valid=True,playing=True,paused=False,group='Continue',name='StartGacha',type='HierarchyEventPlayer',run=7))
        await self.drive(.7);await self.until_outputs_acknowledged([8,10],[60,70])
        for name in ('Failed Breast','Failed SuperBreast','ToGoScene'):
            self.game.s['flow']['name']=name;await self.drive(.18)
            await self.until_outputs_acknowledged([8,10],[60,70])
        self.game.s.update(scene_id=167,scene='Road_2_2_Livestock_go',player=789)
        self.game.s['flow'].update(group='Event',name='Main')
        await self.drive(.25);await self.until_outputs_acknowledged([8,10],[60,70])
        self.game.s.update(scene_id=166,scene='Road_2_2_Livestock',player=456)
        self.game.s['flow']['group']='Continue'
        self.game.s['flow']['name']='Success'
        await self.drive(.25);await self.until_outputs_acknowledged([0,0],[0,0])
    async def test_generic_one_hp_damage_callbacks_drive_both_routes_without_named_cg(self):
        self.rule('defeat_hold',pulse='AB',electrical=10,vibration='AB',ovc=70)
        self.b._sim_profile['rules']['defeat_hold'].update(pulse_strength_a=8,pulse_strength_b=10,
            pulse_start_strength_a=2,pulse_start_strength_b=4,pulse_ramp_seconds=.3,
            vibration_strength_a=60,vibration_strength_b=70,vibration_start_strength_a=20,vibration_start_strength_b=30,
            vibration_ramp_seconds=.3,death_mode='until_end')
        self.game.s.update(scene_id=998,scene='Unlisted_Map',hp=dict(current=1,max=100),event_playing=True,
            flow=dict(valid=True,playing=True,paused=False,name='Unlisted_Player',group='Unlisted_Group',type='Unlisted_Type'))
        def damage(seq):
            return dict(event_type='damage_callback',session=self.game.s['session'],pid=self.game.s['pid'],player=self.game.s['player'],
                        before_hp=1,remain_hp=1,spend_hp=0,spend_mp=-1,sequence=seq,utc=datetime.now(timezone.utc).isoformat())
        self.game.events.put(damage(1));await self.drive(.28)
        self.assertEqual(self.commanded('pulse'),[0,0]);self.assertEqual(self.commanded('ovc'),[0,0])
        self.game.events.put(damage(2));await self.drive(.6)
        await self.until_outputs_acknowledged([8,10],[60,70])
        self.assertIn('1 HP',self.b.state['penaltyLabel']);self.assertEqual(self.b._monitor.counts.get('one_hp_penalty'),1)
        started=self.b._pulse_planner.engine.death_started_at
        self.game.events.put(damage(3));await self.drive(.2)
        self.assertEqual(self.b._pulse_planner.engine.death_started_at,started)
        self.game.s.update(hp=dict(current=40,max=100),event_playing=False,flow={})
        await self.drive(.25);await self.until_outputs_acknowledged([0,0],[0,0])
        self.assertEqual(self.b._monitor.counts.get('one_hp_end'),1)

    async def test_active_struggle_without_damage_callbacks_drives_cg_until_success(self):
        from sinisistar_dglab.cg_policy import make_cg
        cg=make_cg(self.b._sim_profile['rules']['defeat_hold'],inherit=False);self.b._sim_profile['cg']=cg
        cg['rule'].update(enabled=True,pulse_channel='AB',pulse_enabled=True,pulse_strength_a=8,pulse_strength_b=10,
            pulse_start_strength_a=2,pulse_start_strength_b=4,pulse_ramp_seconds=.3,
            vibration_channel='AB',vibration_enabled=True,vibration_strength_a=60,vibration_strength_b=70,
            vibration_start_strength_a=20,vibration_start_strength_b=30,vibration_ramp_seconds=.3,death_mode='until_end')
        self.game.s.update(hp=dict(current=1,max=110),event_playing=True,event_paused=True,
            flow=dict(valid=True,playing=True,paused=True,name='Main',group='BossEvent',type='HierarchyEventPlayer'),
            gacha=dict(active=True,value=0,threshold=20))
        await self.drive(.65);await self.until_outputs_acknowledged([8,10],[60,70])
        self.assertEqual(self.b.state['penaltyClassification'],'struggle_penalty')
        self.game.s['gacha']['active']=False;self.game.s['flow']['name']='Failuer'
        await self.drive(.25);await self.until_outputs_acknowledged([8,10],[60,70])
        self.game.s['hp']['current']=0;await self.drive(.25);await self.until_outputs_acknowledged([8,10],[60,70])
        self.game.s.update(hp=dict(current=55,max=110),event_playing=False,event_paused=False,flow={})
        await self.drive(.25);await self.until_outputs_acknowledged([0,0],[0,0])
    async def test_playerless_one_hp_go_cg_drives_both_routes_then_stops(self):
        self.rule('defeat_hold',pulse='AB',electrical=10,vibration='AB',ovc=70)
        self.b._sim_profile['rules']['defeat_hold'].update(pulse_strength_a=8,pulse_strength_b=10,
            pulse_start_strength_a=2,pulse_start_strength_b=4,pulse_ramp_seconds=.3,
            vibration_strength_a=60,vibration_strength_b=70,vibration_start_strength_a=20,vibration_start_strength_b=30,
            vibration_ramp_seconds=.3,death_mode='until_end')
        self.game.s.update(valid=False,player=0,scene_id=4,scene='Road_2_1_GO',hp=dict(current=1,max=110),event_playing=True,
            flow=dict(valid=True,playing=True,paused=False,name='Main',group='Event',type='HierarchyEventPlayer'))
        await self.drive(.7);await self.until_outputs_acknowledged([8,10],[60,70])
        self.assertFalse(self.b.state['valid']);self.assertIn('独立战败',self.b.state['penaltyLabel'])
        self.assertEqual(self.b.state['gameStatus'],'独立战败 CG');self.assertEqual(self.b.state['scene'],'Road_2_1_GO')
        self.assertEqual(self.b._monitor.counts.get('scripted_go'),1)
        self.game.s.update(flow={},event_playing=False)
        await self.drive(.25);await self.until_outputs_acknowledged([0,0],[0,0])
        self.game.s.update(scene_id=3,scene='Road_2_1',flow=dict(valid=True,playing=True,name='Main',type='HierarchyEventPlayer'))
        await self.drive(.2);await self.until_outputs_acknowledged([0,0],[0,0])
    async def test_independent_cg_queue_reaches_socket_and_stops_one_route_at_queue_end(self):
        from sinisistar_dglab.cg_policy import make_cg
        self.b._sim_profile['cg']=make_cg(self.b._sim_profile['rules']['defeat_hold'],inherit=False)
        cg=self.b._sim_profile['cg'];r=cg['rule']
        r.update(enabled=True,pulse_channel='AB',pulse_enabled=True,pulse_strength_a=8,pulse_strength_b=10,
                 vibration_enabled=True,vibration_channel='AB',vibration_strength_a=40,vibration_strength_b=60,
                 vibration_wave='vib_custom_cg_full',death_mode='until_end')
        for options in cg['routes'].values():options['ramp_mode']='constant'
        self.b._waves.extend([dict(key='custom_cg_full',name='full',points=[1.]*16),dict(key='custom_cg_half',name='half',points=[.5]*16)])
        self.b._vibration_custom.append(dict(key='vib_custom_cg_full',name='full',points=[1.]*16))
        cg['routes']['pulse'].update(mode='sequence',queue=[dict(wave='custom_cg_full',seconds=.4,period=1),dict(wave='custom_cg_half',seconds=.4,period=1)])
        self.game.s.update(valid=False,player=0,scene_id=4,scene='Road_2_1_GO',hp=dict(current=1,max=110),event_playing=True,
            flow=dict(valid=True,playing=True,paused=False,name='Main',group='Event',type='HierarchyEventPlayer'))
        await self.drive(1.3);await self.until_outputs_acknowledged([8,10],[40,60])
        frames=[frame for packet in self.app.pulses('coyote') for frame in packet['data']['v']]
        amplitudes={int(frame[i:i+2],16) for frame in frames for i in range(8,16,2)}
        self.assertIn(100,amplitudes);self.assertIn(50,amplitudes)
        cg['routes']['pulse'].update(loop=False,end='stop')
        await self.drive(.25);await self.until_outputs_acknowledged([0,0],[40,60])
        self.game.s.update(flow={},event_playing=False)
        await self.drive(.25);await self.until_outputs_acknowledged([0,0],[0,0])
    async def test_clothing_break_both_routes_stop_after_custom_duration(self):
        self.rule('break',pulse='A',electrical=7,vibration='B',ovc=30)
        self.b._sim_profile['rules']['break']['duration']=.6
        await self.drive();self.game.s['broken']=True;await self.drive(.22)
        self.assertEqual(self.commanded('pulse'),[7,0]);self.assertEqual(self.commanded('ovc'),[0,30])
        self.assertTrue(self.app.pulses('coyote','A'));self.assertTrue(self.app.pulses('ovc','B'))
        await self.drive(.8);self.assertEqual(self.commanded('pulse'),[0,0]);self.assertEqual(self.commanded('ovc'),[0,0])
        since=time.monotonic();await self.drive(.3)
        self.assertFalse(self.app.pulses('coyote','A',since));self.assertFalse(self.app.pulses('ovc','B',since))
    async def test_cg_queue_scale_and_opposite_channel_filters_reach_mock_app(self):
        from sinisistar_dglab.cg_policy import make_cg
        cg=make_cg(self.b._sim_profile['rules']['defeat_hold'],inherit=False);self.b._sim_profile['cg']=cg
        cg['rule'].update(enabled=True,pulse_enabled=True,vibration_enabled=True,pulse_channel='AB',vibration_channel='AB',
            pulse_strength_a=8,pulse_strength_b=10,vibration_strength_a=60,vibration_strength_b=70,death_mode='until_end')
        self.b._waves.append(dict(key='custom_scale_full',name='flat',points=[1.]*16))
        self.b._vibration_custom.append(dict(key='vib_custom_scale_full',name='flat',points=[1.]*16))
        for route,key in [('pulse','custom_scale_full'),('vibration','vib_custom_scale_full')]:
            cg['routes'][route].update(mode='sequence',ramp_mode='constant',queue=[dict(wave=key,seconds=12,period=1,scale=.5)])
        self.b._sim_profile['channel_feedback']={'pulse':{'A':'damage','B':'cg'},'vibration':{'A':'cg','B':'damage'}}
        self.game.s.update(valid=False,player=0,scene_id=4,scene='Road_2_1_GO',hp=dict(current=1,max=110),event_playing=True,
            flow=dict(valid=True,playing=True,paused=False,name='Main',group='Event',type='HierarchyEventPlayer'))
        await self.drive(.5);await self.until_outputs_acknowledged([0,10],[60,0])
        for slot,channel in [('coyote','B'),('ovc','A')]:
            frames=[f for packet in self.app.pulses(slot,channel) for f in packet['data']['v']]
            self.assertTrue(frames);self.assertTrue(all(f[8:]=='32323232' for f in frames))
        self.assertFalse(self.app.pulses('coyote','A'));self.assertFalse(self.app.pulses('ovc','B'))
        self.game.s['paused']=True;await self.drive(.25);await self.until_outputs_acknowledged([0,0],[0,0])

    async def test_split_cg_ab_fixed_and_random_queues_reach_app_independently(self):
        from sinisistar_dglab.cg_policy import make_cg
        cg=make_cg(self.b._sim_profile['rules']['defeat_hold'],inherit=False,split=True);self.b._sim_profile['cg']=cg
        cg['rule'].update(enabled=True,pulse_enabled=True,pulse_channel='AB',pulse_strength_a=8,pulse_strength_b=10,
            vibration_enabled=False,death_mode='until_end')
        self.b._waves.extend([dict(key='custom_full',name='full',points=[1.]*16),dict(key='custom_quarter',name='quarter',points=[.25]*16),dict(key='custom_half',name='half',points=[.5]*16)])
        cg['routes']['pulse']['A'].update(mode='fixed',wave='custom_full',period=1,frequency=20,ramp_mode='constant')
        cg['routes']['pulse']['B'].update(mode='shuffle',loop=True,frequency=80,ramp_mode='constant',queue=[
            dict(wave='custom_quarter',seconds=.2,period=1),dict(wave='custom_half',seconds=.2,period=1)])
        self.game.s.update(valid=False,player=0,scene_id=4,scene='Road_2_1_GO',hp=dict(current=1,max=110),event_playing=True,
            flow=dict(valid=True,playing=True,paused=False,name='Main',group='Event',type='HierarchyEventPlayer'))
        await self.drive(.8);await self.until_outputs_acknowledged([8,10],[0,0])
        a=[f for r in self.app.pulses('coyote','A') for f in r['data']['v']]
        b=[f for r in self.app.pulses('coyote','B') for f in r['data']['v']]
        self.assertTrue(a);self.assertTrue(b)
        self.assertTrue(all(f[8:]=='64646464' for f in a))
        self.assertEqual({f[:8] for f in a},{'32323232'})
        self.assertEqual({f[:8] for f in b},{'0C0C0C0C'})
        self.assertEqual({int(f[i:i+2],16) for f in b for i in range(8,16,2)},{25,50})

    async def test_same_hp_scene_callbacks_drive_cg_routes_then_timeout_and_end(self):
        from sinisistar_dglab.cg_policy import make_cg
        cg=make_cg(self.b._sim_profile['rules']['defeat_hold'],inherit=False);self.b._sim_profile['cg']=cg;cg.update(same_hp_enabled=True,same_hp_timeout=.6)
        cg['rule'].update(enabled=True,pulse_enabled=True,vibration_enabled=True,pulse_channel='AB',vibration_channel='AB',
            pulse_strength_a=8,pulse_strength_b=10,vibration_strength_a=60,vibration_strength_b=70,death_mode='until_end')
        for option in cg['routes'].values():option['ramp_mode']='constant'
        self.game.s.update(scene_id=7,scene='Monastery',hp=dict(current=110,max=110),event_playing=True,
            flow=dict(valid=True,playing=True,paused=False,name='Sequence',group='',type='HierarchyEventPlayer',run=2))
        await self.drive(.15);await self.until_outputs_acknowledged([0,0],[0,0])
        def emit(seq):
            self.game.events.put(dict(event_type='damage_callback',sequence=seq,session=self.game.s['session'],pid=self.game.s['pid'],player=self.game.s['player'],scene_id=7,
                before_hp=110,remain_hp=110,spend_hp=-1,spend_mp=4,utc=datetime.now(timezone.utc).isoformat()))
        emit(1);await self.drive(.25);emit(2);await self.drive(.2);await self.until_outputs_acknowledged([8,10],[60,70])
        await self.drive(.7);await self.until_outputs_acknowledged([0,0],[0,0])
        emit(3);await self.drive(.2);await self.until_outputs_acknowledged([8,10],[60,70])
        self.game.s.update(event_playing=False,flow={});await self.drive(.2);await self.until_outputs_acknowledged([0,0],[0,0])
        self.assertTrue(any(x['key']=='same_hp_start' for x in self.b._events))
        self.assertTrue(any(x['key']=='same_hp_end' for x in self.b._events))
    async def test_mp_consumption_stays_silent_and_hp_reaches_both_routes(self):
        self.rule('hp_loss',pulse='A',electrical=9,vibration='B',ovc=40)
        await self.drive();self.game.s['mp']['current']=80;await self.drive()
        self.assertEqual(self.commanded('pulse'),[0,0]);self.assertEqual(self.commanded('ovc'),[0,0])
        self.assertFalse(self.app.pulses('coyote','A'));self.assertFalse(self.app.pulses('ovc','B'))
        self.game.s['hp']['current']=90;await self.drive()
        self.assertEqual(self.commanded('pulse'),[9,0]);self.assertEqual(self.commanded('ovc'),[0,40])
        self.assertTrue(self.app.pulses('coyote','A'));self.assertTrue(self.app.pulses('ovc','B'))
    async def test_pausing_only_ovc_keeps_pulse_capture_stream_running(self):
        self.rule('grab_hold',pulse='B',electrical=6,vibration='A',ovc=30);self.game.s.update(bound=True,binder='Zombie')
        await self.drive();self.assertEqual(self.commanded('ovc'),[30,0]);since=time.monotonic()
        self.b.toggleOvcArm();await self.drive()
        self.assertEqual(self.commanded('pulse'),[0,6]);self.assertEqual(self.commanded('ovc'),[0,0])
        self.assertTrue(self.app.pulses('coyote','B',since));self.assertFalse(self.app.pulses('ovc','A',since+.05))
    async def test_positive_blessing_is_filtered_from_both_real_routes(self):
        for name in ('InfertilityBlessing','Poison'):
            self.b._sim_profile['abnormals'][name].update(enabled=True,pulse_enabled=True,vibration_enabled=True,
                pulse_strength=10,pulse_level_step=0,vibration_strength=20,vibration_level_step=0)
        self.game.s['abnormals']=[{'name':'InfertilityBlessing','level':1}];await self.drive()
        self.assertEqual(self.commanded('pulse'),[0,0]);self.assertEqual(self.commanded('ovc'),[0,0])
        self.game.s['abnormals'].append({'name':'Poison','level':1});await self.drive()
        self.assertEqual(self.commanded('pulse'),[10,0]);self.assertEqual(self.commanded('ovc'),[0,0])
    async def test_death_holds_custom_independent_strengths_then_ends_on_revival(self):
        self.b._sim_profile['rules']['defeat_hold'].update(enabled=True,pulse_strength_a=11,pulse_strength_b=17,vibration_strength_a=30,vibration_strength_b=60,pulse_max=True,vibration_max=True)
        self.game.s['hp']['current']=0
        since=time.monotonic()
        await self.drive(.5)
        await self.until_outputs_acknowledged([11,17],[30,60],since=since)
        self.assertEqual(self.commanded('pulse'),[11,17]);self.assertEqual(self.commanded('ovc'),[30,60])
        self.assertTrue(all(r['data']['v'][0][:8]=='0A0A0A0A' for r in self.app.pulses('ovc')))
        since=time.monotonic()
        self.game.s.update(bound=False,event_playing=True,flow={'playing':True,'valid':True,'key':'death','elapsed':2});await self.drive(.35)
        await self.until_outputs_acknowledged([11,17],[30,60],since=since)
        self.assertEqual(self.commanded('ovc'),[30,60])
        self.game.s.update(event_playing=False,flow={});self.game.s['hp']['current']=100;await self.drive(.2)
        await self.until_outputs_acknowledged([0,0],[0,0])
        self.assertEqual(self.commanded('pulse'),[0,0]);self.assertEqual(self.commanded('ovc'),[0,0])
    async def test_capture_strength_range_rises_on_both_real_routes_and_resets(self):
        self.rule('grab_hold',pulse='AB',electrical=12,vibration='AB',ovc=50)
        self.b._sim_profile['rules']['grab_hold'].update(pulse_start_strength=2,pulse_ramp_seconds=.8,vibration_start_strength=10,vibration_ramp_seconds=.8)
        self.game.s.update(bound=True,binder='Zombie');since=time.monotonic()
        await self.drive(1.15);await self.until_outputs_acknowledged([12,12],[50,50],since=since)
        for slot,low,high in (('coyote',2,12),('ovc',10,50)):
            for channel in (0,1):
                values=[r['data']['v'] for r in self.app.records if r['at']>=since and r.get('m')=='device.op' and r['data'].get('s')==slot and r['data'].get('c')==channel and r['data'].get('t')==4 and r['data'].get('v',0)>0]
                self.assertTrue(values);self.assertEqual(values,sorted(values));self.assertGreaterEqual(min(values),low);self.assertEqual(max(values),high)
                self.assertGreater(len(set(values)),1)
        self.game.s['bound']=False;await self.drive(.2);await self.until_outputs_acknowledged([0,0],[0,0])
    async def test_pause_and_stale_heartbeat_zero_both_routes(self):
        self.rule('grab_hold',ovc=40);self.game.s.update(bound=True,binder='Zombie');await self.drive()
        self.game.s['paused']=True;await self.drive(.2)
        self.assertEqual(self.commanded('pulse'),[0,0]);self.assertEqual(self.commanded('ovc'),[0,0])
        self.game.s['paused']=False;await self.drive();self.assertEqual(self.commanded('ovc'),[40,0])
        self.game.stale=True;await self.drive(.2)
        self.assertEqual(self.commanded('pulse'),[0,0]);self.assertEqual(self.commanded('ovc'),[0,0])
    async def test_ovc_selection_keeps_pulse_running_but_shared_policy_disarms_both(self):
        self.rule('grab_hold',ovc=40);self.game.s.update(bound=True,binder='Zombie');await self.drive()
        since=time.monotonic()
        self.b.selectV4Device('ovc',self.app.client_id,'ovc');await self.drive(.25)
        self.assertTrue(self.b.state['armed']);self.assertFalse(self.b.state['ovcArmed'])
        self.assertEqual(self.commanded('pulse'),[10,0]);self.assertEqual(self.commanded('ovc'),[0,0])
        self.assertTrue(self.app.pulses('coyote','A',since))
        self.b.toggleOvcArm();await self.drive()
        self.b.setOvcLimit('A',20);await self.drive(.2)
        self.assertFalse(self.b.state['armed']);self.assertFalse(self.b.state['ovcArmed'])
        self.assertEqual(self.commanded('pulse'),[0,0]);self.assertEqual(self.commanded('ovc'),[0,0])
    async def test_pulse_selection_keeps_ovc_running(self):
        self.rule('grab_hold',ovc=40);self.game.s.update(bound=True,binder='Zombie');await self.drive()
        since=time.monotonic()
        self.b.selectV4Device('pulse',self.app.client_id,'coyote');await self.drive(.25)
        self.assertFalse(self.b.state['armed']);self.assertTrue(self.b.state['ovcArmed'])
        self.assertEqual(self.commanded('pulse'),[0,0]);self.assertEqual(self.commanded('ovc'),[40,0])
        self.assertTrue(self.app.pulses('ovc','A',since))
    async def test_v3_pulse_can_share_game_feedback_with_independent_v4_ovc(self):
        from sinisistar_dglab.dglab import ConnectionService
        from sinisistar_dglab.mock_app import MockApp
        v3=ConnectionService(port=0,host='127.0.0.1',lan_ip='127.0.0.1');v3.start()
        await self.until(lambda:v3.snapshot()['server_ready'])
        s=v3.snapshot();phone=await MockApp((30,35)).connect(f"ws://127.0.0.1:{s['port']}/{s['controller_id']}",s['controller_id'])
        await self.until(lambda:v3.snapshot()['feedback_known'])
        self.b._service=v3;self.b._connection['pulse_backend']='v3'
        try:
            self.rule('grab_hold',electrical=11,ovc=40);self.game.s.update(bound=True,binder='Zombie');await self.drive(.35)
            self.assertEqual(phone.strengths,[11,0]);self.assertEqual(self.commanded('ovc'),[40,0])
            self.assertTrue(phone.pulses('A'));self.assertTrue(self.app.pulses('ovc'))
        finally:
            await asyncio.to_thread(v3.stop);await phone.close();self.b._service=self.hub.channel('pulse')
