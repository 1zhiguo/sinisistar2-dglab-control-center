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
    def test_config_defaults_enabled_and_independent_with_split_minute_defaults(self):
        p=initial_profile();c=p['gallery'];self.assertTrue(c['rule']['enabled']);self.assertTrue(c['pause_on_stop'])
        for route in ('pulse','vibration'):
            self.assertNotEqual(c['routes'][route]['A']['queue'],c['routes'][route]['B']['queue'])
            self.assertEqual(sum(x['seconds'] for x in c['routes'][route]['A']['queue']),60)
        c['rule']['enabled']=True;c['routes']['pulse']['A']['ramp_seconds']=1000
        migrated=sanitize_profile(p);self.assertEqual(migrated['gallery']['routes']['pulse']['A']['ramp_seconds'],1000)
        c['rule']['enabled']=False;self.assertFalse(sanitize_profile(p)['gallery']['rule']['enabled'])
        del p['gallery'];self.assertTrue(sanitize_profile(p)['gallery']['rule']['enabled'])

    def test_damage_only_ovc_reports_cg_filter_and_never_sends(self):
        p=profile();p['channel_feedback']['vibration']={'A':'damage','B':'damage'}
        engine=OvcPlanner();out=engine.update(state(10),p,WAVES,now=10,enabled=True)
        self.assertFalse(any(out['vibration_stream'].values()))
        self.assertIn('通道策略仅受伤',out['reason'])
        p['channel_feedback']['vibration']['A']='both'
        out=engine.update(state(10.2),p,WAVES,now=10.2,enabled=True)
        self.assertTrue(out['vibration_stream']['A']);self.assertIsNone(out['vibration_stream']['B'])
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

    def test_loaded_event_take_can_play_when_optional_flow_read_fails(self):
        p=profile();s=state(10);s.pop('flow')
        s['gallery']['take_player_type']='GaSceneTakePlayer'
        self.assertEqual(gallery_gate(s,10,p['gallery']),'')
        engine=PulsePlanner();first=engine.update(s,p,WAVES,now=10,enabled=True)
        self.assertTrue(first['pulse_stream']['A']);self.assertTrue(first['pulse_stream']['B'])
        s.update(sampled_at=10.4);later=engine.update(s,p,WAVES,now=10.4,enabled=True)
        self.assertGreater(later['peaks']['pulseA'],first['peaks']['pulseA'])
        for frame in (3,4,7,8,9):
            raw=state(10+frame/10,frame);raw.pop('flow');raw['gallery']['take_player_type']='GaSceneTakePlayer'
            expected=frame in (4,8)
            self.assertEqual(bool(engine.update(raw,p,WAVES,now=10+frame/10,enabled=True)['pulse_stream']['A']),expected,frame)

    def test_missing_flow_fallback_requires_every_live_take_signal(self):
        from sinisistar_dglab.gallery import describe_gallery
        p=profile();base=state(10);base.pop('flow');base['gallery']['take_player_type']='GaSceneTakePlayer'
        self.assertEqual(describe_gallery(base,10)['playbackEvidence'],'gallery_take_and_event_flag')
        for key,value in (('play_type_raw',0),('guide_open',False),('active',False),('take_selected',False),('enemy_id',None),
                          ('take_player',0),('take_data',0),('take_player_type','Unknown'),('take_name',''),('selected_index_raw',0),('selected_index_raw',999)):
            s=deepcopy(base);s['gallery'][key]=value
            self.assertTrue(gallery_gate(s,10,p['gallery']),(key,value))

        for key,value in (('event_playing',False),('loading',True),('sampled_at',0),('scene','Monastery'),('flow',dict(valid=False,playing=False))):
            s=deepcopy(base);s[key]=value
            self.assertTrue(gallery_gate(s,10,p['gallery']),(key,value))

    def test_actual_042_missing_flow_capture_does_not_require_player(self):
        from datetime import datetime
        from sinisistar_dglab.plugin_bridge import PluginObserver
        from sinisistar_dglab.gallery import describe_gallery
        raw=json.loads((Path(__file__).parent/'fixtures/gallery-0.4.2-missing-flow.json').read_text(encoding='utf-8'))
        s=PluginObserver.decode(raw,now=datetime.fromisoformat(raw['utc']));now=s['sampled_at'];p=profile()
        self.assertNotIn('flow',raw);self.assertEqual(s['player'],0);self.assertFalse(s['valid'])
        self.assertEqual(describe_gallery(s,now)['name'],'Load_2_0_GO')
        self.assertEqual(gallery_gate(s,now,p['gallery']),'')
        self.assertTrue(PulsePlanner().update(s,p,WAVES,now=now,enabled=True)['pulse_stream']['A'])
