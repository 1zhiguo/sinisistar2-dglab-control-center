from copy import deepcopy
import tempfile,time,unittest
from pathlib import Path
from PySide6.QtGui import QGuiApplication
from sinisistar_dglab.simulation import default_profile,Simulator
from sinisistar_dglab.quick_policy import apply_preset,sanitize_presets
from sinisistar_dglab.backend import Backend,WAVES,ROOT

def sample(now,**changes):
    s=dict(source='bepinex',live=True,valid=True,session='ramp',pid=1,player=2,scene_id=48,sample_id=int(now*100),sampled_at=now,
           hp={'current':100,'max':100},mp={'current':100,'max':100},time_scale=1,paused=False,loading=False,bound=True,binder='Zombie',abnormals=[],flow={})
    s.update(changes);return s

class Ramps(unittest.TestCase):
    def setUp(self):self.p=default_profile();self.e=Simulator();self.p.update(pulse_cap_a=100,pulse_cap_b=100,vibration_cap_a=200,vibration_cap_b=200)
    def evaluate(self,now,**kw):return self.e.evaluate(sample(now,**kw),self.p,WAVES,now=now)
    def capture(self):
        self.p['rules']['grab_hold'].update(pulse_channel='AB',vibration_channel='AB',pulse_start_strength=2,pulse_strength=10,pulse_ramp_seconds=4,
            vibration_start_strength=10,vibration_strength=50,vibration_ramp_seconds=4)
    def test_timed_death_runs_once_across_zero_hp_and_cg_then_resets_after_revival(self):
        rule=self.p['rules']['defeat_hold']
        rule.update(death_mode='timed',death_seconds=3.,pulse_start_strength_a=4,pulse_strength_a=12,pulse_ramp_seconds=3.)
        zero=dict(hp={'current':0,'max':100})
        self.assertEqual(self.evaluate(10,**zero)['peaks']['pulseA'],4)
        self.assertEqual(self.evaluate(11.5,**zero)['peaks']['pulseA'],8)
        self.assertIsNone(self.evaluate(13,**zero)['pulse_stream']['A'])
        flow=dict(valid=True,playing=True,defeat_confirmed=True,key='death')
        self.assertIsNone(self.evaluate(14,flow=flow)['pulse_stream']['A'])
        self.assertIsNone(self.evaluate(100,**zero)['pulse_stream']['A'])
        self.evaluate(101,bound=False)
        self.assertEqual(self.evaluate(102,**zero)['peaks']['pulseA'],4)
    def test_timed_death_keeps_remaining_abnormal_baseline(self):
        self.p['rules']['defeat_hold'].update(death_mode='timed',death_seconds=3.)
        self.p['abnormals']['Poison'].update(enabled=True,pulse_strength=7,vibration_strength=20)
        state=dict(hp={'current':0,'max':100},abnormals=[dict(name='Poison',level=1)])
        self.evaluate(10,**state);r=self.evaluate(13,**state)
        self.assertEqual(r['peaks']['pulseA'],10);self.assertEqual(r['peaks']['vibrationA'],0)
        self.assertNotIn('defeat_hold',[x['key'] for x in r['active']])
    def test_timed_death_deadline_is_not_restarted_by_pause_stale_data_or_route_reset(self):
        from sinisistar_dglab.pulse import PulsePlanner
        from sinisistar_dglab.ovc_plan import OvcPlanner
        from sinisistar_dglab.simulation import VIBRATION_WAVES
        self.p['rules']['defeat_hold'].update(death_mode='timed',death_seconds=3.)
        for planner,waves,route in [(PulsePlanner(),WAVES,'pulse'),(OvcPlanner(),VIBRATION_WAVES,'vibration')]:
            with self.subTest(route=route):
                def update(now,**changes):
                    s=sample(now,hp={'current':0,'max':100});s.update(changes)
                    return planner.update(s,self.p,waves,now=now,enabled=True)
                self.assertIsNotNone(update(10)[route+'_stream']['A'])
                self.assertIsNone(update(11,paused=True)[route+'_stream']['A'])
                self.assertIsNone(update(12,sampled_at=1)[route+'_stream']['A'])
                planner.reset()
                self.assertIsNone(update(13.1)[route+'_stream']['A'])
                update(14,hp={'current':100,'max':100},bound=False)
                self.assertIsNotNone(update(15)[route+'_stream']['A'])
    def test_capture_rises_to_peak_then_holds_without_timeout(self):
        self.capture()
        for now,pulse,ovc in ((10,2,10),(12,6,30),(14,10,50),(60,10,50)):
            r=self.evaluate(now);self.assertEqual(r['peaks']['pulseA'],pulse);self.assertEqual(r['peaks']['pulseB'],pulse)
            self.assertEqual(r['peaks']['vibrationA'],ovc);self.assertEqual(r['peaks']['vibrationB'],ovc)
    def test_release_and_new_grab_restart_from_low(self):
        self.capture();self.evaluate(10);self.evaluate(14)
        r=self.evaluate(14.1,bound=False);self.assertIsNone(r['pulse_stream']['A'])
        self.assertEqual(self.evaluate(15)['peaks']['pulseA'],2)
        self.assertEqual(self.evaluate(16,binder='OtherEnemy')['peaks']['pulseA'],2)
    def test_fractional_ramp_samples_never_round_above_descriptor_peak(self):
        self.capture();self.p['rules']['grab_hold'].update(pulse_wave='flat',vibration_wave='vib_flat')
        self.e.evaluate(sample(10),self.p,WAVES+[dict(key='flat',points=[1.]*16)],now=10,vibration_waves=[dict(key='vib_flat',points=[1.]*16)])
        for n in range(1,90):
            now=10+n/137
            r=self.e.evaluate(sample(now),self.p,WAVES+[dict(key='flat',points=[1.]*16)],now=now,vibration_waves=[dict(key='vib_flat',points=[1.]*16)])
            for route in ('pulse','vibration'):
                for descriptor in r[route+'_stream'].values():self.assertTrue(all(0<=v<=descriptor['peak'] for v in descriptor['samples']))
    def test_death_independent_ranges_survive_cg_transition_and_stop_on_revival(self):
        self.p['rules']['defeat_hold'].update(pulse_start_strength_a=4,pulse_start_strength_b=6,pulse_strength_a=12,pulse_strength_b=18,pulse_ramp_seconds=4,
            vibration_start_strength_a=10,vibration_start_strength_b=20,vibration_strength_a=30,vibration_strength_b=60,vibration_ramp_seconds=4)
        zero={'hp':{'current':0,'max':100}}
        r=self.evaluate(10,**zero);self.assertEqual([r['peaks'][k] for k in ('pulseA','pulseB','vibrationA','vibrationB')],[4,6,10,20])
        r=self.evaluate(12,event_playing=True,flow={'valid':True,'playing':True,'key':'death'},**zero)
        self.assertEqual([r['peaks'][k] for k in ('pulseA','pulseB','vibrationA','vibrationB')],[8,12,20,40])
        r=self.evaluate(80,**zero);self.assertEqual(r['peaks']['pulseA'],12)
        r=self.evaluate(81,bound=False);self.assertFalse(any(x['key']=='defeat_hold' for x in r['active']))
        self.assertIsNone(r['pulse_stream']['A'])
        self.assertEqual(self.evaluate(82,**zero)['peaks']['pulseA'],4)
    def test_status_baseline_is_preserved_and_channel_caps_still_apply(self):
        self.capture();self.p['abnormals']['Poison'].update(enabled=True,pulse_strength=7);self.p.update(pulse_cap_a=8,vibration_cap_a=40)
        state={'abnormals':[{'name':'Poison','level':1}]}
        self.assertEqual(self.evaluate(10,**state)['peaks']['pulseA'],8)
        r=self.evaluate(15,**state);self.assertEqual(r['peaks']['pulseA'],8);self.assertEqual(r['peaks']['pulseB'],10);self.assertEqual(r['peaks']['vibrationA'],40)
    def test_pause_discards_phase_and_resumes_from_low(self):
        self.capture();self.evaluate(10);self.evaluate(14)
        self.assertIsNone(self.evaluate(15,paused=True)['pulse_stream']['A'])
        self.assertEqual(self.evaluate(16)['peaks']['pulseA'],2)
    def test_preset_migration_preserves_peak_and_orders_range(self):
        p=sanitize_presets({'low':{'pulse_grab':9,'pulse_death_a':7,'ovc_death_b':30,'pulse_grab_start':99,'death_ramp_seconds':0}})['low']
        self.assertEqual(p['pulse_grab'],9);self.assertEqual(p['pulse_grab_start'],9);self.assertEqual(p['pulse_death_a'],7)
        self.assertLessEqual(p['pulse_death_start_a'],7);self.assertEqual(p['death_ramp_seconds'],.1)
        q=apply_preset(self.p,'medium');self.assertEqual(q['rules']['grab_hold']['pulse_start_strength'],20)
        self.assertEqual(q['rules']['defeat_hold']['pulse_start_strength_a'],40)

class RangeBackend(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.qt=QGuiApplication.instance() or QGuiApplication([])
    def test_range_draft_is_atomic_and_apply_persists_ramp(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp') as temp:
            b=Backend(offline=True,settings=Path(temp)/'settings.json')
            try:
                old=deepcopy(b._sim_profile['rules']);b._armed=True;b._ovc_armed=True
                b.setQuickRange('low','pulse_death',3,9);b.setQuickRange('low','ovc_grab',15,49)
                draft=b.quickPolicy['presets']['low'];self.assertEqual((draft['pulse_death_start_a'],draft['pulse_death_start_b'],draft['pulse_death_a'],draft['pulse_death_b']),(3,3,9,9))
                self.assertEqual((draft['ovc_grab_start'],draft['ovc_grab']),(10,40));self.assertEqual(b._sim_profile['rules'],old);self.assertTrue(b._armed)
                b.applyQuickPreset('low');self.assertFalse(b._armed);self.assertFalse(b._ovc_armed)
                other=Backend(offline=True,settings=b.settings)
                try:self.assertEqual(other.quickPolicy['deathRanges']['pulseA']['low'],3);self.assertEqual(other.quickPolicy['death']['pulseA'],9)
                finally:other.shutdown()
            finally:b.shutdown()
