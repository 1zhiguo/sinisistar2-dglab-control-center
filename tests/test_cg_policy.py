"""CG strategy migration, independent routes, queue timing and real plan samples."""
from copy import deepcopy
from pathlib import Path
import tempfile,unittest
from PySide6.QtGui import QGuiApplication
from sinisistar_dglab.cg_policy import make_cg,effective_cg,select_wave,ramp_fraction
from sinisistar_dglab.simulation import default_profile,sanitize_profile,Simulator,VIBRATION_WAVES
from sinisistar_dglab.backend import Backend,WAVES
from sinisistar_dglab.pulse import PulsePlanner
from sinisistar_dglab.ovc_plan import OvcPlanner
from sinisistar_dglab.telemetry import ROOT

def state(t=10,**changes):
    s=dict(source='bepinex',live=True,valid=False,player=0,pid=1,session='cg-strategy',scene_id=4,scene='Road_2_1_GO',
        sampled_at=t,sample_id=int(t*100),paused=False,loading=False,time_scale=1,event_playing=True,hp=dict(current=1,max=110),abnormals=[],
        flow=dict(valid=True,playing=True,paused=False,name='Main',group='Event',type='HierarchyEventPlayer'))
    s.update(changes);return s

def profile():
    p=default_profile();p.update(pulse_cap_a=60,pulse_cap_b=60,vibration_cap_a=150,vibration_cap_b=150)
    p['cg']=make_cg(p['rules']['defeat_hold'],inherit=False)
    r=p['cg']['rule'];r.update(pulse_channel='AB',pulse_strength_a=30,pulse_strength_b=40,pulse_start_strength_a=10,pulse_start_strength_b=20,pulse_ramp_seconds=4,
        vibration_channel='AB',vibration_strength_a=100,vibration_strength_b=120,vibration_start_strength_a=20,vibration_start_strength_b=40,vibration_ramp_seconds=4)
    return p

class CgPolicy(unittest.TestCase):
    def test_split_defaults_loop_one_minute_with_distinct_ab_waves_and_preserved_strength(self):
        from sinisistar_dglab.simulation import initial_profile
        p=initial_profile();c=effective_cg(p)
        for route in ('pulse','vibration'):
            a,b=(c['routes'][route][ch] for ch in 'AB')
            self.assertEqual(a['mode'],'sequence');self.assertTrue(b['loop'])
            self.assertEqual(sum(x['seconds'] for x in a['queue']),60)
            self.assertEqual(sum(x['seconds'] for x in b['queue']),60)
            self.assertTrue(all(x['wave']!=y['wave'] for x,y in zip(a['queue'],b['queue'])))
            self.assertEqual(c['rule'][route+'_strength_a'],p['rules']['defeat_hold'][route+'_strength_a'])

    def test_split_channels_use_distinct_samples_frequency_and_independent_queue_end(self):
        p=profile();p['cg']=make_cg(p['cg']['rule'],inherit=False,split=True)
        a,b=(p['cg']['routes']['pulse'][ch] for ch in 'AB')
        a.update(mode='sequence',loop=False,end='stop',ramp_mode='constant',frequency=20,queue=[dict(wave='full',seconds=.15,period=1)])
        b.update(mode='fixed',wave='quarter',period=1,ramp_mode='constant',frequency=80)
        waves=WAVES+[dict(key='full',points=[1]*16),dict(key='quarter',points=[.25]*16)]
        planner=PulsePlanner();out=planner.update(state(),p,waves,now=10,enabled=True)
        self.assertEqual(out['pulse_stream']['A']['samples'],[30]*4)
        self.assertEqual(out['pulse_stream']['B']['samples'],[10]*4)
        self.assertEqual(out['pulse_stream']['A']['frequencies'],[20]*4)
        self.assertEqual(out['pulse_stream']['B']['frequencies'],[80]*4)
        out=planner.update(state(10.125),p,waves,now=10.125,enabled=True)
        self.assertEqual(out['pulse_stream']['A']['samples'],[30,0,0,0])
        self.assertEqual(out['pulse_stream']['B']['samples'],[10]*4)
        out=planner.update(state(10.3),p,waves,now=10.3,enabled=True)
        self.assertIsNone(out['pulse_stream']['A']);self.assertIsNotNone(out['pulse_stream']['B'])

    def test_legacy_custom_queue_migrates_to_a_without_aliasing_b(self):
        p=profile();p['cg']['routes']['pulse'].update(mode='shuffle',queue=[dict(wave='custom_a',seconds=7,period=2)])
        c=sanitize_profile(p)['cg'];self.assertEqual(c['version'],2)
        self.assertEqual(c['routes']['pulse']['A']['mode'],'shuffle')
        self.assertEqual(c['routes']['pulse']['A']['queue'][0]['wave'],'custom_a')
        b=deepcopy(c['routes']['pulse']['B']);c['routes']['pulse']['A']['queue'].clear()
        self.assertEqual(c['routes']['pulse']['B'],b)
    def test_old_configuration_inherits_current_death_parameters_without_drift(self):
        p=sanitize_profile(dict(version=9,rules=dict(defeat_hold=dict(pulse_strength_a=37,pulse_start_strength_a=11,pulse_wave='pulse',death_seconds=7)),
                                abnormals=dict(Poison=dict(enabled=True))))
        self.assertTrue(p['cg']['inherit_death']);self.assertEqual(effective_cg(p)['rule'],p['rules']['defeat_hold'])
        self.assertTrue(p['abnormals']['Poison']['enabled'])
        p['rules']['defeat_hold']['pulse_strength_a']=49;self.assertEqual(effective_cg(p)['rule']['pulse_strength_a'],49)

    def test_sequence_loop_once_hold_stop_and_fractional_boundaries(self):
        p=profile();r=p['cg']['rule'];o=p['cg']['routes']['pulse']
        o.update(mode='sequence',queue=[dict(wave='x',seconds=.1,period=1),dict(wave='y',seconds=.2,period=2)])
        self.assertEqual(select_wave(o,r,'pulse',.1,'s')[0],'y')
        self.assertEqual(select_wave(o,r,'pulse',.3,'s')[0],'x')
        o['loop']=False;self.assertEqual(select_wave(o,r,'pulse',2,'s')[0],'y')
        o['end']='stop';self.assertIsNone(select_wave(o,r,'pulse',2,'s'))
        o['queue']=[];self.assertIsNone(select_wave(o,r,'pulse',0,'s'))

    def test_shuffle_has_no_repeat_per_round_and_is_stable_between_frames(self):
        p=profile();r=p['cg']['rule'];o=p['cg']['routes']['pulse'];o.update(mode='shuffle',queue=[dict(wave=str(i),seconds=1,period=1) for i in range(6)])
        first=[select_wave(o,r,'pulse',i+.2,'seed')[0] for i in range(6)]
        self.assertEqual(set(first),set(map(str,range(6))))
        self.assertEqual(first,[select_wave(o,r,'pulse',i+.21,'seed')[0] for i in range(6)])
        self.assertEqual(len(set(select_wave(o,r,'pulse',6+i+.2,'seed')[0] for i in range(6))),6)

    def test_ramp_curves_are_bounded_monotone_with_expected_midpoints(self):
        for mode,mid in [('linear',.5),('ease_in',.25),('ease_out',.75),('steps',.4),('constant',1)]:
            self.assertAlmostEqual(ramp_fraction(2,4,mode,5),mid)
            values=[ramp_fraction(i,4,mode,5) for i in range(7)]
            self.assertEqual(values,sorted(values));self.assertTrue(all(0<=v<=1 for v in values))

    def test_queue_can_switch_within_a_transport_frame_and_routes_stay_independent(self):
        p=profile();p['cg']['routes']['pulse'].update(mode='sequence',ramp_mode='constant',queue=[dict(wave='full',seconds=.15,period=1),dict(wave='zero',seconds=.3,period=1)])
        waves=WAVES+[dict(key='full',points=[1]*16),dict(key='zero',points=[0]*16)]
        planner=PulsePlanner();planner.update(state(),p,waves,now=10,enabled=True)
        out=planner.update(state(10.125),p,waves,now=10.125,enabled=True)
        self.assertEqual(out['pulse_stream']['A']['samples'],[30,0,0,0]);self.assertFalse(any(out['vibration_stream'].values()))
        o=OvcPlanner().update(state(),p,VIBRATION_WAVES,now=10,enabled=True)
        self.assertFalse(any(o['pulse_stream'].values()));self.assertEqual(o['vibration_stream']['A']['peak'],20)

    def test_ramp_scope_can_restart_per_wave_or_cycle(self):
        p=profile();o=p['cg']['routes']['pulse'];o.update(mode='sequence',queue=[dict(wave='pulse',seconds=2,period=1),dict(wave='breath',seconds=2,period=1)])
        for scope,expected in [('episode',25),('wave',15),('cycle',25)]:
            o['ramp_scope']=scope;planner=PulsePlanner();planner.update(state(),p,WAVES,now=10,enabled=True)
            out=planner.update(state(13),p,WAVES,now=13,enabled=True);self.assertEqual(out['pulse_stream']['A']['peak'],expected)
        o['ramp_scope']='cycle';planner=PulsePlanner();planner.update(state(),p,WAVES,now=10,enabled=True)
        self.assertEqual(planner.update(state(14),p,WAVES,now=14,enabled=True)['pulse_stream']['A']['peak'],10)

    def test_cg_and_normal_death_switches_and_strengths_are_independent(self):
        p=profile();p['rules']['defeat_hold']['enabled']=False
        self.assertIsNotNone(PulsePlanner().update(state(),p,WAVES,now=10,enabled=True)['pulse_stream']['A'])
        normal=state(valid=True,player=2,scene_id=3,scene='Road_2_1',hp=dict(current=0,max=110),flow={},event_playing=False)
        self.assertIsNone(PulsePlanner().update(normal,p,WAVES,now=10,enabled=True)['pulse_stream']['A'])
        p['rules']['defeat_hold']['enabled']=True;p['cg']['rule']['enabled']=False
        self.assertIsNone(PulsePlanner().update(state(),p,WAVES,now=10,enabled=True)['pulse_stream']['A'])
        self.assertIsNotNone(PulsePlanner().update(normal,p,WAVES,now=10,enabled=True)['pulse_stream']['A'])

    def test_cg_timed_policy_and_pause_end_do_not_replay_or_leak(self):
        p=profile();p['cg']['rule'].update(death_mode='timed',death_seconds=1)
        planner=PulsePlanner();planner.update(state(),p,WAVES,now=10,enabled=True)
        self.assertIsNone(planner.update(state(12),p,WAVES,now=12,enabled=True)['pulse_stream']['A'])
        self.assertIn('CG 定时',planner.update(state(13),p,WAVES,now=13,enabled=True)['reason'])
        planner.update(state(14,flow={}),p,WAVES,now=14,enabled=True)
        # A brief absence of the player/flow may be an internal CG transition.
        planner.update(state(15,valid=True,player=2,scene_id=3,scene='Road_2_1',hp=dict(current=55,max=110),flow={},event_playing=False),p,WAVES,now=15,enabled=True)
        self.assertIsNotNone(planner.update(state(16),p,WAVES,now=16,enabled=True)['pulse_stream']['A'])
        self.assertIsNone(planner.update(state(17,paused=True),p,WAVES,now=17,enabled=True)['pulse_stream']['A'])

    def test_sanitization_caps_queues_periods_curves_and_long_cg_ramp(self):
        raw=profile();raw['cg']['rule']['pulse_ramp_seconds']=700
        raw['cg']['routes']['pulse'].update(mode='invalid',ramp_steps=999,queue=[dict(wave='pulse',seconds=float('nan'),period=-3)]*40)
        clean=sanitize_profile(raw)['cg'];self.assertEqual(clean['rule']['pulse_ramp_seconds'],700)
        self.assertEqual(len(clean['routes']['pulse']['A']['queue']),32);self.assertEqual(clean['routes']['pulse']['A']['ramp_steps'],20)
        self.assertEqual(clean['routes']['pulse']['A']['queue'][0]['period'],.1)

class CgBackend(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.qt=QGuiApplication.instance() or QGuiApplication([])
    def test_edit_detaches_migrates_saves_and_pauses_both_without_changing_death(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp') as tmp:
            b=Backend(offline=True,settings=Path(tmp)/'settings.json');b._timer.stop()
            try:
                death=deepcopy(b._sim_profile['rules']['defeat_hold']);b._armed=b._ovc_armed=True
                original_b=deepcopy(b.cgSettings['routes']['pulse']['B'])
                b.setCgStrengthRange('pulse','a',11,33);b.setCgOption('pulse:A','mode','shuffle');b.addCgQueue('pulse:A','pulse')
                for index in range(5,0,-1):b.moveCgQueue('pulse:A',index,-1)
                self.assertEqual(b.cgSettings['routes']['pulse']['A']['queue'][0]['wave'],'pulse')
                b.setCgQueue('pulse:A',0,'seconds',7);b.setCgRule('vibration_enabled',False)
                self.assertEqual(b.cgSettings['routes']['pulse']['B'],original_b)
                self.assertFalse(b._armed);self.assertFalse(b._ovc_armed);self.assertEqual(b._sim_profile['rules']['defeat_hold'],death)
                other=Backend(offline=True,settings=b.settings);other._timer.stop()
                try:
                    self.assertFalse(other.cgSettings['inherit_death']);self.assertEqual(other.cgSettings['rule']['pulse_strength_a'],33)
                    self.assertEqual(other.cgSettings['routes']['pulse']['A']['queue'][0]['seconds'],7)
                    self.assertEqual(other.cgSettings['routes']['pulse']['A']['mode'],'shuffle')
                    self.assertEqual(other.cgSettings['routes']['pulse']['B'],original_b)
                    self.assertFalse(other.cgSettings['rule']['vibration_enabled'])
                finally:other.shutdown()
                b.removeCgQueue('pulse',0);queue=deepcopy(b.cgSettings['routes']);b.copyDeathToCg()
                self.assertEqual(b.cgSettings['rule']['pulse_strength_a'],death['pulse_strength_a']);self.assertEqual(b.cgSettings['routes'],queue)
            finally:b.shutdown()

if __name__=='__main__':unittest.main()
