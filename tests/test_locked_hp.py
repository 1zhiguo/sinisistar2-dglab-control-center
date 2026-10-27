"""Generic evidence must work without naming a CG and reject stale/foreign hits."""
from copy import deepcopy
from datetime import datetime,timezone,timedelta
import unittest
from sinisistar_dglab.locked_hp import LockedHpEvidence,locked_hp_penalty
from sinisistar_dglab.simulation import default_profile,death_penalty_stage,VIBRATION_WAVES
from sinisistar_dglab.backend import WAVES
from sinisistar_dglab.pulse import PulsePlanner,pulse_gate
from sinisistar_dglab.ovc_plan import OvcPlanner
from sinisistar_dglab.monitoring import EventMonitor

BASE=datetime(2026,10,26,tzinfo=timezone.utc)
def sample(t=0,**changes):
    s=dict(source='bepinex',live=True,valid=True,session='one-hp',pid=1,player=2,scene_id=991,scene='unknown-test-map',
        sampled_at=10+t,sample_id=int(t*100+1),utc=(BASE+timedelta(seconds=t)).isoformat(),paused=False,loading=False,
        time_scale=1,hp=dict(current=1,max=100),mp=dict(current=80,max=100),bound=False,abnormals=[],event_playing=True,
        flow=dict(valid=True,playing=True,paused=False,group='Unlisted',name='Unlisted',type='UnknownPlayer'))
    s.update(changes);return s
def hit(t=0,seq=1,**changes):
    e=dict(event_type='damage_callback',session='one-hp',pid=1,player=2,sequence=seq,
           utc=(BASE+timedelta(seconds=t)).isoformat(),before_hp=1,remain_hp=1,spend_hp=0,spend_mp=-1)
    e.update(changes);return e
def update(tracker,t,events=(),**changes):
    return tracker.update(sample(t,**changes),events,now=10+t,wall_now=BASE+timedelta(seconds=t))
def confirmed():
    tracker=LockedHpEvidence();update(tracker,0,[hit()]);return tracker,update(tracker,1,[hit(1,2)])

class LockedHp(unittest.TestCase):
    def test_real_struggle_without_damage_callbacks_uses_cg_and_stops_on_success(self):
        from sinisistar_dglab.cg_policy import make_cg
        from sinisistar_dglab.penalty_flows import current_penalty_class
        tracker=LockedHpEvidence();flow=dict(valid=True,playing=True,paused=True,group='BossEvent',name='Main',type='HierarchyEventPlayer')
        s=update(tracker,0,flow=flow,gacha=dict(active=True,value=0,threshold=20))
        self.assertEqual(current_penalty_class(s)[0],'struggle_penalty')
        self.assertEqual(s['feedback_evidence']['locked_hp_count'],0)
        profile=default_profile();profile['cg']=make_cg(profile['rules']['defeat_hold'],inherit=False)
        profile['cg']['rule'].update(pulse_start_strength_a=5,pulse_strength_a=15,pulse_ramp_seconds=2)
        planner=PulsePlanner();self.assertEqual(planner.update(s,profile,WAVES,now=10,enabled=True)['peaks']['pulseA'],5)
        failure=update(tracker,2,flow=dict(flow,name='Failuer'),gacha=dict(active=False,value=0,threshold=20))
        self.assertEqual(planner.update(failure,profile,WAVES,now=12,enabled=True)['peaks']['pulseA'],15)
        zero=update(tracker,3,flow=dict(flow,name='Failuer'),hp=dict(current=0,max=100))
        self.assertEqual(planner.update(zero,profile,WAVES,now=13,enabled=True)['peaks']['pulseA'],15)
        end=update(tracker,4,flow=dict(flow,name='Success'),hp=dict(current=55,max=100))
        self.assertFalse(locked_hp_penalty(end));self.assertIsNone(planner.update(end,profile,WAVES,now=14,enabled=True)['pulse_stream']['A'])

    def test_struggle_rejects_inactive_malformed_free_control_and_other_hp(self):
        flow=dict(valid=True,playing=True,name='Main',type='HierarchyEventPlayer')
        for changes in (dict(hp=dict(current=50,max=100)),dict(valid=False),dict(paused=True),dict(loading=True),
                        dict(sampled_at=0),dict(flow={}),dict(gacha=dict(active=True,value=0,threshold=0)),
                        dict(gacha=dict(active=False,value=20,threshold=20)),dict(gacha=dict(active=True,value=float('nan'),threshold=20))):
            case=dict(flow=flow,gacha=dict(active=True,value=0,threshold=20));case.update(changes)
            self.assertFalse(locked_hp_penalty(update(LockedHpEvidence(),0,**case)),changes)
    def test_two_callbacks_allow_unlisted_interaction_and_latch_without_repeated_hits(self):
        tracker=LockedHpEvidence();a=update(tracker,0,[hit()]);self.assertFalse(death_penalty_stage(a))
        a=update(tracker,5.5,[hit(5.5,2)]);self.assertTrue(locked_hp_penalty(a));self.assertEqual(pulse_gate(a,15.5),'')
        self.assertTrue(locked_hp_penalty(update(tracker,12)))

    def test_bare_one_hp_or_only_one_callback_never_authorizes(self):
        tracker=LockedHpEvidence()
        for t in (0,1):self.assertFalse(locked_hp_penalty(update(tracker,t,[hit(t,int(t)+1)],event_playing=False,flow={})))
        a=update(tracker,2,[hit(2,3)]);self.assertFalse(locked_hp_penalty(a))
        b=update(tracker,2.1);self.assertFalse(locked_hp_penalty(b));self.assertTrue(pulse_gate(b,12.1))

    def test_duplicates_burst_and_too_distant_callbacks_are_not_repeated_evidence(self):
        tracker=LockedHpEvidence();update(tracker,0,[hit()])
        self.assertFalse(locked_hp_penalty(update(tracker,.1,[hit(),hit(.1,2)])))
        self.assertFalse(locked_hp_penalty(update(tracker,9,[hit(9,3)])))
        self.assertTrue(locked_hp_penalty(update(tracker,10,[hit(10,4)])))

    def test_old_history_foreign_actor_and_mp_only_callbacks_do_not_count(self):
        invalid=[dict(history=True),dict(session='other'),dict(pid=7),dict(player=9),dict(event_type='flow_label_callback'),
                 dict(before_hp=2),dict(remain_hp=0),dict(spend_hp=-1),dict(before_hp=True),dict(utc='broken'),dict(utc=BASE.isoformat())]
        for changes in invalid:
            tracker=LockedHpEvidence();update(tracker,1,[hit(1)])
            self.assertFalse(locked_hp_penalty(update(tracker,2,[hit(2,2,**changes)])),changes)

    def test_cached_player_loading_gallery_and_stale_snapshots_cannot_trigger(self):
        for changes in (dict(valid=False,player=0),dict(loading=True),dict(scene='Gallery_test'),dict(sampled_at=0)):
            tracker=LockedHpEvidence();update(tracker,0,[hit()],**changes)
            self.assertFalse(locked_hp_penalty(update(tracker,1,[hit(1,2)],**changes)))

    def test_recovery_free_control_new_actor_and_new_scene_clear_confirmed_evidence(self):
        for changes in (dict(hp=dict(current=20,max=100)),dict(event_playing=False,flow={}),dict(player=3),dict(scene_id=992)):
            tracker,_=confirmed();self.assertFalse(locked_hp_penalty(update(tracker,2,**changes)),changes)

    def test_bound_without_event_player_also_works(self):
        tracker=LockedHpEvidence();update(tracker,0,[hit()],bound=True,event_playing=False,flow={})
        self.assertTrue(locked_hp_penalty(update(tracker,1,[hit(1,2)],bound=True,event_playing=False,flow={})))

    def test_timeline_wait_for_struggle_is_allowed_but_actual_game_pause_stops(self):
        tracker=LockedHpEvidence();f=sample()['flow'];f['paused']=True
        update(tracker,0,[hit()],flow=f,event_paused=True)
        s=update(tracker,1,[hit(1,2)],flow=f,event_paused=True)
        self.assertTrue(locked_hp_penalty(s));self.assertEqual(pulse_gate(s,11),'')
        self.assertIsNotNone(PulsePlanner().update(s,default_profile(),WAVES,now=11,enabled=True)['pulse_stream']['A'])
        s['paused']=True
        self.assertIsNone(PulsePlanner().update(s,default_profile(),WAVES,now=11,enabled=True)['pulse_stream']['A'])

    def test_both_planners_ramp_once_and_keep_progress_into_zero_hp(self):
        p=default_profile()
        for r in p['rules'].values():r['enabled']=False
        p['rules']['defeat_hold'].update(enabled=True,pulse_channel='AB',pulse_strength_a=30,pulse_strength_b=40,
            pulse_start_strength_a=10,pulse_start_strength_b=20,pulse_ramp_seconds=4,vibration_enabled=True,vibration_channel='AB',
            vibration_start_strength_a=20,vibration_start_strength_b=40,vibration_strength_a=100,vibration_strength_b=120,vibration_ramp_seconds=4)
        p.update(pulse_cap_a=60,pulse_cap_b=60,vibration_cap_a=150,vibration_cap_b=150)
        for planner,waves,route in ((PulsePlanner(),WAVES,'pulse'),(OvcPlanner(),VIBRATION_WAVES,'vibration')):
            tracker,a=confirmed();planner.update(a,p,waves,now=11,enabled=True)
            b=update(tracker,3,[hit(3,3)]);r=planner.update(b,p,waves,now=13,enabled=True)
            self.assertEqual(r[route+'_stream']['A']['peak'],20 if route=='pulse' else 60)
            z=update(tracker,5,hp=dict(current=0,max=100));r=planner.update(z,p,waves,now=15,enabled=True)
            self.assertEqual(r[route+'_stream']['B']['peak'],40 if route=='pulse' else 120)
            end=update(tracker,6,hp=dict(current=20,max=100),event_playing=False,flow={})
            self.assertIsNone(planner.update(end,p,waves,now=16,enabled=True)[route+'_stream']['A'])

    def test_timed_mode_does_not_restart_on_more_callbacks(self):
        tracker,a=confirmed();p=default_profile();p['rules']['defeat_hold'].update(death_mode='timed',death_seconds=1)
        planner=PulsePlanner();planner.update(a,p,WAVES,now=11,enabled=True)
        later=update(tracker,3,[hit(3,3)])
        self.assertIsNone(planner.update(later,p,WAVES,now=13,enabled=True)['pulse_stream']['A'])
        self.assertEqual(planner.engine.death_started_at,11)

    def test_pause_stale_time_stop_emergency_and_disabled_death_rule_remain_gated(self):
        tracker,a=confirmed();p=default_profile()
        for changes in (dict(paused=True),dict(sampled_at=0),dict(time_scale=0),dict(loading=True)):
            s=deepcopy(a);s.update(changes)
            self.assertIsNone(PulsePlanner().update(s,p,WAVES,now=11,enabled=True)['pulse_stream']['A'])
        self.assertIsNone(PulsePlanner().update(a,p,WAVES,now=11,enabled=True,emergency=True)['pulse_stream']['A'])
        p['rules']['defeat_hold']['enabled']=False
        self.assertIsNone(PulsePlanner().update(a,p,WAVES,now=11,enabled=True)['pulse_stream']['A'])

    def test_monitor_reports_entry_and_exit(self):
        tracker=LockedHpEvidence();m=EventMonitor();m.snapshot(update(tracker,0,[hit()]))
        self.assertIn('one_hp_penalty',[r['key'] for r in m.snapshot(update(tracker,1,[hit(1,2)]))])
        self.assertIn('one_hp_end',[r['key'] for r in m.snapshot(update(tracker,2,hp=dict(current=40,max=100)))])

if __name__=='__main__':unittest.main()
