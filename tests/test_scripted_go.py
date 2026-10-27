"""A playerless GO flow is its own evidence; cached HP alone remains blocked."""
from copy import deepcopy
import unittest
from sinisistar_dglab.scripted_go import scripted_go_penalty
from sinisistar_dglab.penalty_flows import current_penalty_class
from sinisistar_dglab.simulation import default_profile,VIBRATION_WAVES
from sinisistar_dglab.backend import WAVES
from sinisistar_dglab.pulse import PulsePlanner,pulse_gate
from sinisistar_dglab.ovc_plan import OvcPlanner
from sinisistar_dglab.monitoring import EventMonitor

def state(t=10,**changes):
    s=dict(source='bepinex',live=True,valid=False,player=0,pid=1,session='go-test',scene_id=4,scene='Road_2_1_GO',
        sampled_at=t,sample_id=int(t*100),paused=False,loading=False,time_scale=1,event_playing=True,
        hp=dict(current=1,max=110),abnormals=[dict(name='Poison',level=9)],
        flow=dict(valid=True,playing=True,paused=False,name='Main',group='Event',type='HierarchyEventPlayer'))
    s.update(changes);return s

class ScriptedGO(unittest.TestCase):
    def test_playerless_one_hp_go_flow_is_admitted(self):
        self.assertTrue(scripted_go_penalty(state()));self.assertEqual(pulse_gate(state(),10),'')
        self.assertEqual(current_penalty_class(state())[0],'scripted_go')

    def test_unknown_ordinary_gallery_inactive_and_cached_hp_only_remain_blocked(self):
        for changes in (dict(scene_id=3,scene='Road_2_1'),dict(scene='Gallery_test'),dict(scene_id=999),dict(flow={}),
                        dict(hp=dict(current=55,max=110)),dict(source='unknown'),dict(pid=0),dict(session=''),dict(loading=True)):
            s=state(**changes);self.assertFalse(scripted_go_penalty(s),changes);self.assertTrue(pulse_gate(s,10),changes)
        for field,value in [('playing',False),('valid',False),('name',''),('type','Unknown')]:
            s=state();s['flow'][field]=value;self.assertFalse(scripted_go_penalty(s));self.assertTrue(pulse_gate(s,10))

    def test_real_pause_stale_and_emergency_stop_while_timeline_wait_is_allowed(self):
        for changes in (dict(paused=True),dict(sampled_at=8),dict(loading=True)):
            self.assertTrue(pulse_gate(state(**changes),10))
        s=state(event_paused=True);s['flow']['paused']=True
        self.assertEqual(pulse_gate(s,10),'')
        self.assertIsNotNone(PulsePlanner().update(s,default_profile(),WAVES,now=10,enabled=True)['pulse_stream']['A'])
        self.assertIsNone(PulsePlanner().update(s,default_profile(),WAVES,now=10,enabled=True,emergency=True)['pulse_stream']['A'])

    def test_both_routes_ramp_during_cg_then_clear_on_flow_end(self):
        p=default_profile();p.update(pulse_cap_a=60,pulse_cap_b=60,vibration_cap_a=150,vibration_cap_b=150)
        p['rules']['defeat_hold'].update(pulse_channel='AB',pulse_start_strength_a=10,pulse_start_strength_b=20,pulse_strength_a=30,pulse_strength_b=40,pulse_ramp_seconds=4,
            vibration_enabled=True,vibration_channel='AB',vibration_start_strength_a=20,vibration_start_strength_b=40,vibration_strength_a=100,vibration_strength_b=120,vibration_ramp_seconds=4)
        for planner,waves,route in ((PulsePlanner(),WAVES,'pulse'),(OvcPlanner(),VIBRATION_WAVES,'vibration')):
            planner.update(state(),p,waves,now=10,enabled=True)
            mid=planner.update(state(12),p,waves,now=12,enabled=True)
            self.assertEqual(mid[route+'_stream']['A']['peak'],20 if route=='pulse' else 60)
            self.assertIn('独立战败',mid['active'][0]['detail'])
            self.assertIsNone(planner.update(state(13,flow={}),p,waves,now=13,enabled=True)[route+'_stream']['A'])

    def test_cached_abnormals_cannot_output_when_death_rule_disabled(self):
        p=default_profile();p['abnormals']['Poison']['enabled']=True;p['rules']['defeat_hold']['enabled']=False
        result=PulsePlanner().update(state(),p,WAVES,now=10,enabled=True)
        self.assertEqual(result['abnormal_count'],0);self.assertFalse(any(result['pulse_stream'].values()))

    def test_timed_mode_survives_go_map_change_without_restarting(self):
        p=default_profile();p['rules']['defeat_hold'].update(death_mode='timed',death_seconds=1)
        planner=PulsePlanner();planner.update(state(),p,WAVES,now=10,enabled=True)
        next_map=state(12,scene_id=29,scene='Dungeon_Swamp_Boss_GO1')
        self.assertIsNone(planner.update(next_map,p,WAVES,now=12,enabled=True)['pulse_stream']['A'])
        self.assertEqual(planner.engine.death_started_at,10)
        self.assertTrue(pulse_gate(state(),10,zero_hp_mode='stop'))

    def test_monitor_records_playerless_flow_entry_and_end(self):
        m=EventMonitor();self.assertEqual(m.snapshot(state())[0]['key'],'scripted_go')
        self.assertEqual(m.snapshot(state(11)),[])
        self.assertEqual(m.snapshot(None)[0]['key'],'scripted_go_end')

if __name__=='__main__':unittest.main()
