"""Observed pigpen flow boundaries; unknown Continue players stay blocked."""
import tempfile,unittest
from pathlib import Path
from copy import deepcopy
from sinisistar_dglab.penalty_flows import current_penalty_class,recoverable_penalty
from sinisistar_dglab.simulation import default_profile,death_penalty_stage,VIBRATION_WAVES
from sinisistar_dglab.pulse import PulsePlanner,pulse_gate
from sinisistar_dglab.ovc_plan import OvcPlanner
from sinisistar_dglab.backend import WAVES
from sinisistar_dglab.monitoring import EventMonitor
from sinisistar_dglab.flows import FlowCatalog
from sinisistar_dglab.telemetry import ROOT

def state(now=10,name='StartGacha',**changes):
    s=dict(source='bepinex',live=True,valid=True,pid=1,player=2,session='pigpen-test',sample_id=int(now*100),sampled_at=now,
        scene_id=166,scene='Road_2_2_Livestock',paused=False,event_paused=False,time_scale=1,loading=False,bound=False,
        hp=dict(current=55,max=110),mp=dict(current=100,max=110),abnormals=[],event_playing=True,
        flow=dict(valid=True,playing=True,paused=False,group='Continue',name=name,type='HierarchyEventPlayer',run=4,
                  key='[166,"Continue","'+name+'","HierarchyEventPlayer"]'))
    s.update(changes);return s

class RecoverablePenalty(unittest.TestCase):
    def profile(self):
        p=default_profile()
        for r in p['rules'].values():r['enabled']=False
        r=p['rules']['defeat_hold'];r.update(enabled=True,pulse_strength_a=30,pulse_strength_b=40,pulse_start_strength_a=10,pulse_start_strength_b=20,
            pulse_ramp_seconds=4,pulse_channel='AB',vibration_enabled=True,vibration_channel='AB',vibration_strength_a=100,vibration_strength_b=120,
            vibration_start_strength_a=20,vibration_start_strength_b=40,vibration_ramp_seconds=4)
        p.update(pulse_cap_a=60,pulse_cap_b=60,vibration_cap_a=150,vibration_cap_b=150);return p
    def test_positive_hp_scripted_struggle_is_detected_without_fake_gameover(self):
        s=state();self.assertTrue(recoverable_penalty(s));self.assertTrue(death_penalty_stage(s))
        self.assertFalse(s['flow'].get('defeat_confirmed',False));self.assertEqual(pulse_gate(s,10),'')
    def test_wrong_scene_group_name_type_or_inactive_flow_cannot_authorize(self):
        for key,value in [('scene_id',28),('valid',False),('loading',True)]:
            s=state(**{key:value});self.assertFalse(recoverable_penalty(s))
        for key,value in [('group','BossAppear'),('name','TriggerEvent'),('type','EventLabelPlayer'),('playing',False),('valid',False)]:
            s=state();s['flow'][key]=value;self.assertFalse(recoverable_penalty(s));self.assertTrue(pulse_gate(s,10))
        s=state(scene_id=28);self.assertEqual(current_penalty_class(s)[0],'recoverable_candidate')
    def test_real_route_planners_ramp_linearly_on_both_channels_then_success_stops(self):
        p=self.profile()
        for planner,waves,route in [(PulsePlanner(),WAVES,'pulse'),(OvcPlanner(),VIBRATION_WAVES,'vibration')]:
            planner.update(state(10),p,waves,now=10,enabled=True)
            mid=planner.update(state(12),p,waves,now=12,enabled=True)
            self.assertEqual(mid[route+'_stream']['A']['peak'],20 if route=='pulse' else 60)
            self.assertEqual(mid[route+'_stream']['B']['peak'],30 if route=='pulse' else 80)
            self.assertIn('猪棚',mid['active'][0]['detail'])
            end=planner.update(state(13,name='Success'),p,waves,now=13,enabled=True)
            self.assertIsNone(end[route+'_stream']['A']);self.assertIsNone(end[route+'_stream']['B'])
    def test_success_with_zero_hp_is_not_another_death_punishment(self):
        s=state(name='Success',hp=dict(current=0,max=110))
        self.assertFalse(death_penalty_stage(s));self.assertTrue(pulse_gate(s,10))
    def test_pause_stale_and_emergency_still_stop_both_routes(self):
        for planner,waves,route in [(PulsePlanner(),WAVES,'pulse'),(OvcPlanner(),VIBRATION_WAVES,'vibration')]:
            for changes in [dict(paused=True),dict(sampled_at=8),dict(loading=True)]:
                r=planner.update(state(**changes),self.profile(),waves,now=10,enabled=True)
                self.assertIsNone(r[route+'_stream']['A'])
            r=planner.update(state(),self.profile(),waves,now=10,enabled=True,emergency=True)
            self.assertIsNone(r[route+'_stream']['A'])
    def test_timed_penalty_does_not_replay_in_same_struggle_and_new_episode_can_start(self):
        p=self.profile();p['rules']['defeat_hold'].update(death_mode='timed',death_seconds=1)
        planner=PulsePlanner();planner.update(state(10),p,WAVES,now=10,enabled=True)
        self.assertIsNone(planner.update(state(12),p,WAVES,now=12,enabled=True)['pulse_stream']['A'])
        planner.update(state(13,name='Success'),p,WAVES,now=13,enabled=True)
        self.assertIsNotNone(planner.update(state(14),p,WAVES,now=14,enabled=True)['pulse_stream']['A'])
    def test_whole_pigpen_chain_keeps_ramp_across_map_and_player_change(self):
        for planner,waves,route in [(PulsePlanner(),WAVES,'pulse'),(OvcPlanner(),VIBRATION_WAVES,'vibration')]:
            p=self.profile();planner.update(state(10),p,waves,now=10,enabled=True)
            for i,name in enumerate(('Failed Breast','Failed SuperBreast','ToGoScene'),1):
                result=planner.update(state(10+i,name=name),p,waves,now=10+i,enabled=True)
                self.assertIsNotNone(result[route+'_stream']['A'])
            loading=state(13.5,loading=True,valid=False,scene_id=167,player=0,flow={})
            result=planner.update(loading,p,waves,now=13.5,enabled=True)
            self.assertIsNone(result[route+'_stream']['A'])
            planner.reset()  # The production backend rebinds on map/player changes.
            main=state(14,scene_id=167,scene='Road_2_2_Livestock_go',player=9)
            main['flow'].update(group='Event',name='Main')
            result=planner.update(main,p,waves,now=14,enabled=True)
            self.assertEqual(result[route+'_stream']['A']['peak'],30 if route=='pulse' else 100)
            self.assertIn('CG',result['active'][0]['detail'])
            normal=state(15,scene_id=166,player=10,event_playing=False,flow={})
            result=planner.update(normal,p,waves,now=15,enabled=True)
            self.assertIsNone(result[route+'_stream']['A'])
            self.assertIsNone(planner.engine.death_started_at)

    def test_timed_mode_does_not_restart_in_later_failure_or_go_scene(self):
        p=self.profile();p['rules']['defeat_hold'].update(death_mode='timed',death_seconds=1)
        planner=PulsePlanner();planner.update(state(10),p,WAVES,now=10,enabled=True)
        self.assertIsNone(planner.update(state(12,name='Failed Breast'),p,WAVES,now=12,enabled=True)['pulse_stream']['A'])
        go=state(13,scene_id=167,player=9);go['flow'].update(group='Event',name='Main')
        self.assertIsNone(planner.update(go,p,WAVES,now=13,enabled=True)['pulse_stream']['A'])

    def test_enemy_death_other_map_or_unknown_go_player_never_grants_punishment(self):
        for s in (state(name='EnemyDeadForSuperBreast'),state(name='Failed Breast',scene_id=168),
                  state(name='Main',scene_id=167),state(name='Main',scene_id=167,flow=dict(valid=True,playing=True,group='Other',name='Main',type='HierarchyEventPlayer'))):
            self.assertFalse(recoverable_penalty(s));self.assertTrue(pulse_gate(s,10))
    def test_monitor_and_catalog_distinguish_verified_start_recovery_and_candidate(self):
        monitor=EventMonitor();monitor.snapshot(state(9,name='StartPoint'))
        self.assertIn('recoverable_penalty',[r['key'] for r in monitor.snapshot(state(10))])
        self.assertIn('recoverable_recovery',[r['key'] for r in monitor.snapshot(state(11,name='Success'))])
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp') as tmp:
            c=FlowCatalog(Path(tmp)/'flows.json');c.observe(state())
            self.assertEqual(c.rows()[0]['penalty_classification'],'recoverable_penalty')

if __name__=='__main__':unittest.main()
