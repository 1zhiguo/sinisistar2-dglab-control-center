"""Gallery-specific feedback uses real captured fields, independent of player HP."""
from copy import deepcopy
from pathlib import Path
import json,unittest
from sinisistar_dglab.simulation import initial_profile,sanitize_profile
from sinisistar_dglab.gallery_policy import GalleryClock,gallery_gate
from sinisistar_dglab.pulse import PulsePlanner
from sinisistar_dglab.ovc_plan import OvcPlanner

FIXTURE=json.loads((Path(__file__).parent/'fixtures/gallery-0.4.2.json').read_text(encoding='utf-8'))
WAVES=[dict(key='flat',points=[1,1]),dict(key='half',points=[.5,.5]),dict(key='quarter',points=[.25,.25])]

def profile():
    p=initial_profile();p.update(pulse_cap_a=50,pulse_cap_b=50,vibration_cap_a=90,vibration_cap_b=90)
    c=p['gallery'];c['rule'].update(enabled=True,pulse_channel='AB',vibration_channel='AB',pulse_strength_a=10,pulse_strength_b=20,
        pulse_start_strength_a=2,pulse_start_strength_b=4,vibration_strength_a=40,vibration_strength_b=60,
        vibration_start_strength_a=10,vibration_start_strength_b=20)
    for route in ('pulse','vibration'):
        for channel in 'AB':
            c['routes'][route][channel].update(mode='fixed',wave='flat' if channel=='A' else 'half',period=1.,ramp_seconds=1.,ramp_mode='linear',ramp_scope='episode')
    return p

def state(t,frame=2):
    s=deepcopy(FIXTURE[frame]);s.update(sampled_at=t,sample_id=int(t*1000));return s

class GalleryOutput(unittest.TestCase):
    def test_config_migrates_disabled_and_independent_with_split_minute_defaults(self):
        p=initial_profile();c=p['gallery'];self.assertFalse(c['rule']['enabled']);self.assertTrue(c['pause_on_stop'])
        for route in ('pulse','vibration'):
            self.assertNotEqual(c['routes'][route]['A']['queue'],c['routes'][route]['B']['queue'])
            self.assertEqual(sum(x['seconds'] for x in c['routes'][route]['A']['queue']),60)
        c['rule']['enabled']=True;c['routes']['pulse']['A']['ramp_seconds']=1000
        migrated=sanitize_profile(p);self.assertEqual(migrated['gallery']['routes']['pulse']['A']['ramp_seconds'],1000)
        del p['gallery'];self.assertFalse(sanitize_profile(p)['gallery']['rule']['enabled'])
    def test_both_adapters_ramp_without_valid_player_or_hp_damage(self):
        for cls,route in ((PulsePlanner,'pulse'),(OvcPlanner,'vibration')):
            planner=cls();p=profile()
            first=planner.update(state(10),p,WAVES,now=10,enabled=True)
            self.assertTrue(first[route+'_stream']['A']);self.assertFalse(first[('vibration' if route=='pulse' else 'pulse')+'_stream']['A'])
            for t in (10.2,10.4,10.6,10.8,11.):last=planner.update(state(t),p,WAVES,now=t,enabled=True)
            self.assertGreater(last['peaks'][route+'A'],first['peaks'][route+'A'])
            self.assertNotEqual(last['active'][0][route+'_wave_A'],last['active'][0][route+'_wave_B'])
    def test_switch_waits_for_new_take_then_restarts_both_clocks(self):
        c=GalleryClock();p=profile()['gallery'];self.assertTrue(c.update(state(10),p,10)['ready'])
        self.assertGreater(c.update(state(10.4),p,10.4)['age'],0)
        pending=c.update(state(10.5,3),p,10.5);self.assertFalse(pending['ready'])
        loaded=c.update(state(10.7,4),p,10.7);self.assertTrue(loaded['ready']);self.assertEqual(loaded['age'],0)
        s=state(10.9,4);s['player']=999;s['flow']['run']+=1
        self.assertGreater(c.update(s,p,10.9)['age'],0)
    def test_space_option_freezes_or_continues_without_reset(self):
        for stop in (True,False):
            c=GalleryClock();config=profile()['gallery'];config['pause_on_stop']=stop
            c.update(state(10,8),config,10);age=c.update(state(10.2,8),config,10.2)['age']
            paused=c.update(state(10.4,7),config,10.4)
            paused=c.update(state(10.6,7),config,10.6)
            self.assertEqual(paused['ready'],not stop)
            resumed=c.update(state(10.8,8),config,10.8)
            self.assertTrue(resumed['ready'])
            self.assertAlmostEqual(resumed['age'],age if stop else .8)
    def test_list_preview_internal_wait_stale_and_invalid_signals(self):
        c=GalleryClock();config=profile()['gallery'];c.update(state(10),config,10)
        s=state(10.1);s['flow']['paused']=True;s['event_paused']=True
        self.assertTrue(c.update(s,config,10.1)['ready'])
        for index in (9,1):self.assertFalse(c.update(state(10.2,index),config,10.2)['ready'])
        p=profile();engine=PulsePlanner()
        for changes in (dict(sampled_at=0),dict(source='external'),dict(session=''),dict(loading=True),dict(paused=True)):
            s=state(10);s.update(changes);self.assertFalse(engine.update(s,p,WAVES,now=10,enabled=True)['pulse_stream']['A'])
        s=state(10);s['gallery']['play_type_raw']=0
        self.assertTrue(gallery_gate(s,10,config))
    def test_independent_queue_boundaries_loop_stop_and_channel_filters(self):
        p=profile();c=p['gallery'];rule=c['rule']
        rule.update(pulse_start_strength_a=10,pulse_start_strength_b=20)
        a=c['routes']['pulse']['A'];a.update(mode='sequence',loop=False,end='stop',queue=[dict(wave='flat',seconds=.2,period=1.,scale=1)])
        b=c['routes']['pulse']['B'];b.update(mode='sequence',loop=True,queue=[dict(wave='half',seconds=.2,period=1.,scale=1),dict(wave='quarter',seconds=.2,period=1.,scale=1)])
        planner=PulsePlanner();first=planner.update(state(10),p,WAVES,now=10,enabled=True)
        after=planner.update(state(10.25),p,WAVES,now=10.25,enabled=True)
        self.assertIsNone(after['pulse_stream']['A']);self.assertTrue(after['pulse_stream']['B'])
        self.assertNotEqual(first['pulse_stream']['B']['samples'],after['pulse_stream']['B']['samples'])
        looped=planner.update(state(10.45),p,WAVES,now=10.45,enabled=True)
        self.assertEqual(first['pulse_stream']['B']['samples'],looped['pulse_stream']['B']['samples'])
        p['channel_feedback']['pulse']['B']='damage'
        self.assertIsNone(planner.update(state(10.5),p,WAVES,now=10.5,enabled=True)['pulse_stream']['B'])
    def test_emergency_permissions_caps_and_ordinary_rule_isolation(self):
        planner=PulsePlanner();p=profile();p['pulse_cap_a']=3
        p['rules']['defeat_hold'].update(pulse_strength=99)
        plan=planner.update(state(10),p,WAVES,now=10,enabled=True)
        plan=planner.update(state(10.5),p,WAVES,now=10.5,enabled=True)
        self.assertLessEqual(plan['pulse_stream']['A']['peak'],3)
        self.assertEqual([x['name'] for x in plan['active']],['图鉴回放反馈'])
        self.assertFalse(planner.update(state(10.6),p,WAVES,now=10.6,enabled=False)['pulse_stream']['A'])
        self.assertFalse(planner.update(state(10.7),p,WAVES,now=10.7,enabled=True,emergency=True)['pulse_stream']['A'])
