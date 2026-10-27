"""Generic same-HP scene evidence, independent from scene/CG names."""
from copy import deepcopy
from datetime import datetime,timezone,timedelta
from pathlib import Path
import tempfile,unittest
from PySide6.QtGui import QGuiApplication
from sinisistar_dglab.backend import Backend,WAVES,ROOT
from sinisistar_dglab.same_hp import SameHpFlowEvidence,same_hp_flow
from sinisistar_dglab.simulation import initial_profile,death_penalty_stage,VIBRATION_WAVES
from sinisistar_dglab.cg_policy import make_cg
from sinisistar_dglab.pulse import PulsePlanner
from sinisistar_dglab.ovc_plan import OvcPlanner
WALL=datetime(2026,10,26,tzinfo=timezone.utc)
def state(t=10,**changes):
    s=dict(source='bepinex',live=True,valid=True,player=123,pid=1,session='same-hp',scene_id=7,scene='Monastery',sampled_at=t,sample_id=int(t*100),
        hp=dict(current=110,max=110),mp=dict(current=100,max=110),abnormals=[],event_playing=True,paused=False,loading=False,time_scale=1,
        flow=dict(valid=True,playing=True,paused=False,name='Sequence',run=3))
    s.update(changes);return s

def event(t,seq=1,**changes):
    e=dict(event_type='damage_callback',session='same-hp',pid=1,player=123,sequence=seq,utc=(WALL+timedelta(seconds=t)).isoformat(),before_hp=110,remain_hp=110,spend_hp=-1,spend_mp=4)
    e.update(changes);return e

def update(tracker,t,callbacks=(),**changes):return tracker.update(state(t,**changes),callbacks,now=t,wall_now=WALL+timedelta(seconds=t))
def confirmed(t=10.5):
    e=SameHpFlowEvidence();update(e,10,[event(10)]);return e,update(e,t,[event(t,2)])
def profile():
    p=initial_profile();p['cg']=make_cg(p['rules']['defeat_hold'],inherit=False);p['cg']['same_hp_enabled']=True
    p['cg']['rule'].update(pulse_channel='AB',vibration_channel='AB',pulse_strength_a=20,pulse_strength_b=25,pulse_start_strength_a=10,pulse_start_strength_b=15,pulse_ramp_seconds=4,
        vibration_strength_a=60,vibration_strength_b=80,vibration_start_strength_a=20,vibration_start_strength_b=40,vibration_ramp_seconds=4)
    return p

class SameHpFlow(unittest.TestCase):
    def test_two_fresh_damage_notifications_confirm_without_requiring_hp_one(self):
        e=SameHpFlowEvidence();self.assertFalse(same_hp_flow(update(e,10,[event(10)])))
        s=update(e,10.5,[event(10.5,2)]);self.assertTrue(same_hp_flow(s));self.assertFalse(death_penalty_stage(s))
    def test_unchanged_snapshots_and_mp_deltas_do_not_count(self):
        e=SameHpFlowEvidence();update(e,10)
        self.assertFalse(same_hp_flow(update(e,11,mp=dict(current=60,max=110))))
    def test_notifications_outside_playing_scene_do_not_count(self):
        e=SameHpFlowEvidence()
        for t in (10,10.5):s=update(e,t,[event(t,int(t*10))],event_playing=False,flow={})
        self.assertFalse(same_hp_flow(s))
    def test_history_wrong_session_actor_scene_old_future_duplicate_and_tight_gap_rejected(self):
        for changes in ({'history':True},{'session':'old'},{'player':999},{'scene_id':8},{'before_hp':111},{'remain_hp':109},{'event_type':'abnormal_remove_callback'}):
            e=SameHpFlowEvidence();update(e,10,[event(10)]);s=update(e,10.5,[event(10.5,2,**changes)]);self.assertFalse(same_hp_flow(s),changes)
        for t in (8,12):
            e=SameHpFlowEvidence();update(e,10,[event(10)]);self.assertFalse(same_hp_flow(update(e,10.5,[event(t,2)])))
        e=SameHpFlowEvidence();update(e,10,[event(10)]);self.assertFalse(same_hp_flow(update(e,10.1,[event(10.1,2),event(10.1,2)])))
    def test_pause_load_gallery_and_invalid_actor_never_authorize(self):
        for changes in ({'paused':True},{'loading':True},{'scene':'Gallery_Monastery'},{'valid':False},{'player':0}):
            e=SameHpFlowEvidence();update(e,10,[event(10)],**changes);s=update(e,10.5,[event(10.5,2)],**changes);self.assertFalse(same_hp_flow(s))
    def test_flow_end_or_callback_timeout_stops_but_steady_callbacks_renew(self):
        e,s=confirmed();self.assertTrue(same_hp_flow(s))
        from sinisistar_dglab.monitoring import EventMonitor
        monitor=EventMonitor();monitor.snapshot(state(10))
        self.assertTrue(any(x['key']=='same_hp_start' for x in monitor.snapshot(s)))
        self.assertTrue(any(x['key']=='same_hp_end' for x in monitor.snapshot(None)))
        self.assertFalse(same_hp_flow(update(e,13.6)));self.assertTrue(same_hp_flow(update(e,13.6),5))
        self.assertTrue(same_hp_flow(update(e,13.7,[event(13.7,3)])))
        self.assertFalse(same_hp_flow(update(e,14,event_playing=False,flow={})))
    def test_unknown_generic_scene_and_missing_optional_player_name_are_supported(self):
        e=SameHpFlowEvidence()
        for t in (10,10.5):s=update(e,t,[event(t,int(t*100))],scene_id=312,scene='NewScene',flow={})
        self.assertTrue(same_hp_flow(s))
    def test_both_planners_use_cg_ranges_and_stop_when_evidence_expires(self):
        p=profile();e,s=confirmed()
        for planner,waves,route in ((PulsePlanner,WAVES,'pulse'),(OvcPlanner,VIBRATION_WAVES,'vibration')):
            x=planner();out=x.update(s,p,waves,now=10.5,enabled=True);self.assertIsNotNone(out[route+'_stream']['A'])
            out=x.update(update(e,14),p,waves,now=14,enabled=True);self.assertFalse(any(out[route+'_stream'].values()))
    def test_timed_mode_does_not_restart_while_callbacks_continue(self):
        p=profile();p['cg']['rule'].update(death_mode='timed',death_seconds=1);e,s=confirmed();x=PulsePlanner();x.update(s,p,WAVES,now=10.5,enabled=True)
        for seq,t in enumerate((11,12,13,14),3):
            s=update(e,t,[event(t,seq)]);out=x.update(s,p,WAVES,now=t,enabled=True)
            if t>=12:self.assertFalse(any(out['pulse_stream'].values()))
    def test_default_on_explicit_off_and_cg_side_channel_filter_remain_effective(self):
        e,s=confirmed();p=initial_profile();self.assertTrue(p['cg']['same_hp_enabled'])
        p['cg']['same_hp_enabled']=False
        self.assertFalse(any(PulsePlanner().update(s,p,WAVES,now=10.5,enabled=True)['pulse_stream'].values()))
        p=profile();p['channel_feedback']['pulse']={'A':'damage','B':'cg'};out=PulsePlanner().update(s,p,WAVES,now=10.5,enabled=True)
        self.assertIsNone(out['pulse_stream']['A']);self.assertIsNotNone(out['pulse_stream']['B'])

class SameHpSettings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.qt=QGuiApplication.instance() or QGuiApplication([])
    def test_save_and_disarm_preserve_death_and_limits(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp') as tmp:
            b=Backend(offline=True,settings=Path(tmp)/'settings.json');b._timer.stop()
            try:
                death=deepcopy(b._sim_profile['rules']['defeat_hold']);b._armed=b._ovc_armed=True
                b.setSameHpFeedbackEnabled(True);b.setSameHpTimeout(4)
                self.assertFalse(b._armed);self.assertFalse(b._ovc_armed);self.assertEqual(b._sim_profile['rules']['defeat_hold'],death)
                other=Backend(offline=True,settings=b.settings);other._timer.stop()
                try:self.assertTrue(other.cgSettings['same_hp_enabled']);self.assertEqual(other.cgSettings['same_hp_timeout'],4)
                finally:other.shutdown()
            finally:b.shutdown()
