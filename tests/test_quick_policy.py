import json,tempfile,time,unittest
from copy import deepcopy
from pathlib import Path
from PySide6.QtGui import QGuiApplication
from sinisistar_dglab.quick_policy import default_presets,sanitize_presets,apply_preset
from sinisistar_dglab.simulation import default_profile,sanitize_profile,Simulator
from sinisistar_dglab.backend import Backend,WAVES,ROOT

class QuickPolicy(unittest.TestCase):
    def test_calibrated_tiers_have_expected_caps_ranges_and_short_feedback(self):
        values=default_presets()
        for name,cap,grab,death,ovc_cap in [('low',30,25,30,30),('medium',60,45,55,60),('high',90,70,80,90)]:
            with self.subTest(name=name):
                p=apply_preset(default_profile(),name)
                self.assertEqual(p['pulse_cap_a'],cap);self.assertEqual(p['pulse_cap_b'],cap)
                self.assertEqual(p['vibration_cap_a'],ovc_cap);self.assertEqual(p['vibration_cap_b'],ovc_cap)
                self.assertEqual(p['rules']['grab_hold']['pulse_strength'],grab)
                self.assertEqual(p['rules']['defeat_hold']['pulse_strength_a'],death)
                self.assertEqual(p['abnormals']['Poison']['vibration_strength'],0)
                for key in ('hp_loss','grab_hp_loss','break'):self.assertEqual(p['rules'][key]['duration'],1.5)
                self.assertLessEqual(death,cap)
                self.assertLessEqual(values[name]['ovc_death_a'],values[name]['ovc_cap'])
    def test_calibrated_capture_is_linear_between_configured_endpoints(self):
        from sinisistar_dglab.simulation import demo_state
        for name in ('low','medium','high'):
            p=apply_preset(default_profile(),name);e=Simulator();v=default_presets()[name]
            for now,fraction in [(10,0),(12.5,.5),(15,1),(100,1)]:
                state=demo_state('idle',0,now);state.update(bound=True,binder='Zombie')
                r=e.evaluate(state,p,WAVES,now=now)
                for route,prefix in [('pulse','pulse'),('vibration','ovc')]:
                    expected=v[prefix+'_grab_start']+(v[prefix+'_grab']-v[prefix+'_grab_start'])*fraction
                    self.assertEqual(r['peaks'][route+'A'],expected)
    def test_legacy_max_flags_retire_and_custom_base_strengths_survive(self):
        p=sanitize_profile({'version':3,'rules':{'defeat_hold':{'pulse_max':True,'vibration_max':True,'pulse_strength':13,'vibration_strength':30}}})
        r=p['rules']['defeat_hold'];self.assertFalse(r['pulse_max']);self.assertFalse(r['vibration_max'])
        self.assertEqual(r['pulse_strength'],13);self.assertEqual(r['vibration_strength'],30)
        self.assertIsNone(r['pulse_strength_a'])
    def test_draft_limits_and_slots_are_independent(self):
        raw=default_presets();raw['low'].update(pulse_death_a=999,ovc_death_b=29,pulse_damage=float('nan'))
        p=sanitize_presets(raw);self.assertEqual(p['low']['pulse_death_a'],100);self.assertEqual(p['low']['ovc_death_b'],20)
        self.assertEqual(p['low']['pulse_damage'],20);self.assertEqual(p['medium'],default_presets()['medium'])
    def test_apply_preserves_waves_routing_switches_and_positive_filter(self):
        p=default_profile();p['rules']['hp_loss'].update(pulse_wave='ripple',pulse_channel='B',enabled=False)
        q=apply_preset(p,'low');self.assertEqual(q['rules']['hp_loss']['pulse_wave'],'ripple')
        self.assertEqual(q['rules']['hp_loss']['pulse_channel'],'B');self.assertFalse(q['rules']['hp_loss']['enabled'])
        self.assertEqual(q['rules']['hp_loss']['pulse_strength'],20);self.assertEqual(q['rules']['hp_loss']['pulse_gain'],0)
        self.assertFalse(q['abnormals']['InfertilityBlessing']['enabled']);self.assertEqual(q['pulse_stack_bonus'],10)
        self.assertEqual(p['rules']['hp_loss']['pulse_strength'],10)
    def test_death_only_does_not_touch_other_rules_or_status_strengths(self):
        p=default_profile();q=apply_preset(p,'high',death_only=True)
        self.assertEqual(q['abnormals'],p['abnormals']);self.assertEqual(q['rules']['hp_loss'],p['rules']['hp_loss'])
        self.assertEqual(q['rules']['defeat_hold']['pulse_strength_a'],80);self.assertEqual(q['rules']['defeat_hold']['vibration_strength_b'],80)

    def test_old_ovc_presets_upgrade_once_without_overwriting_custom_current_or_cg(self):
        p=apply_preset(default_profile(),'low');p['version']=10
        p['quick_presets']['medium'].update(ovc_cap=70,ovc_damage=90)
        p['rules']['hp_loss']['pulse_strength']=17
        p['rules']['grab_hold']['vibration_wave']='vib_beat'
        p['cg']['inherit_death']=False;p['cg']['rule']['vibration_strength_a']=110
        q=sanitize_profile(p)
        self.assertEqual(q['vibration_cap_a'],30)
        self.assertEqual(q['rules']['hp_loss']['vibration_strength'],20)
        self.assertEqual(q['rules']['hp_loss']['pulse_strength'],17)
        self.assertEqual(q['rules']['grab_hold']['vibration_wave'],'vib_beat')
        self.assertEqual(q['cg']['rule']['vibration_strength_a'],110)
        self.assertEqual(q['quick_presets']['medium']['ovc_cap'],60)
        q['quick_presets']['medium']['ovc_cap']=70
        self.assertEqual(sanitize_profile(q)['quick_presets']['medium']['ovc_cap'],70)
        p['quick_active_preset']='';p['vibration_cap_a']=120;p['rules']['hp_loss']['vibration_strength']=80
        custom=sanitize_profile(p)
        self.assertEqual(custom['vibration_cap_a'],120)
        self.assertEqual(custom['rules']['hp_loss']['vibration_strength'],80)
    def test_death_custom_strengths_own_channels_hold_and_stop_at_revival(self):
        p=default_profile();p['abnormals']['Poison']['enabled']=True;r=p['rules']['defeat_hold'];r.update(pulse_strength_a=8,pulse_strength_b=13,vibration_strength_a=30,vibration_strength_b=40,pulse_max=True,vibration_max=True)
        engine=Simulator();s=dict(source='bepinex',live=True,valid=True,session='x',pid=1,player=2,scene_id=48,sample_id=1,sampled_at=10,hp={'current':0,'max':100},mp={'current':100,'max':100},time_scale=1,abnormals=[dict(name='Poison',level=1)],bound=True)
        result=engine.evaluate(s,p,WAVES,now=10)
        for key,value in {'pulseA':8,'pulseB':13,'vibrationA':30,'vibrationB':40}.items():self.assertEqual(result['peaks'][key],value)
        s.update(sampled_at=120,sample_id=2);result=engine.evaluate(s,p,WAVES,now=120)
        self.assertEqual(result['peaks']['pulseB'],13)
        s.update(sampled_at=120.1,sample_id=3,bound=False,hp={'current':100,'max':100})
        result=engine.evaluate(s,p,WAVES,now=120.1)
        self.assertFalse(any(x['key']=='defeat_hold' for x in result['active']))
        self.assertEqual(result['peaks']['pulseA'],10);self.assertEqual(result['peaks']['pulseB'],0)

class QuickBackend(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.qt=QGuiApplication.instance() or QGuiApplication([])
    def test_fresh_defaults_and_preset_apply_update_both_software_limit_layers(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp') as temp:
            b=Backend(offline=True,settings=Path(temp)/'settings.json')
            try:
                self.assertEqual(b.quickPolicy['active'],'medium')
                self.assertEqual([c['limit'] for c in b.channels],[60,60])
                self.assertEqual(b.ovcLimits,dict(A=60,B=60))
                for name,cap,ovc_cap in [('low',30,30),('medium',60,60),('high',90,90)]:
                    b._armed=True;b._ovc_armed=True;b.applyQuickPreset(name)
                    self.assertEqual([c['limit'] for c in b.channels],[cap,cap])
                    self.assertEqual(b.ovcLimits,dict(A=ovc_cap,B=ovc_cap))
                    self.assertFalse(b._armed);self.assertFalse(b._ovc_armed)
                limits=deepcopy(b.channels);ovc=deepcopy(b.ovcLimits)
                b.applyQuickPreset('low',True)
                self.assertEqual(b.channels,limits);self.assertEqual(b.ovcLimits,ovc)
            finally:b.shutdown()
    def test_old_active_tier_updates_both_ovc_limits_and_persists(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp') as temp:
            path=Path(temp)/'settings.json';p=apply_preset(default_profile(),'low');p['version']=10
            p['vibration_cap_a']=p['vibration_cap_b']=90
            path.write_text(json.dumps(dict(simulation=p,ovc_limits=dict(A=90,B=90))),encoding='utf-8')
            b=Backend(offline=True,settings=path)
            try:
                self.assertEqual(b.ovcLimits,dict(A=30,B=30))
                self.assertEqual(b.quickPolicy['current']['ovc_cap'],30)
                self.assertFalse(b._armed);self.assertFalse(b._ovc_armed)
                b.save();saved=json.loads(path.read_text(encoding='utf-8'))
                self.assertEqual(saved['ovc_limits'],dict(A=30,B=30))
                self.assertEqual(saved['simulation']['version'],11)
            finally:b.shutdown()
    def test_shared_death_edit_is_atomic_draft_only_and_preserves_other_values(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp') as temp:
            b=Backend(offline=True,settings=Path(temp)/'settings.json')
            try:
                before=deepcopy(b._sim_profile['rules']);medium=deepcopy(b.quickPolicy['presets']['medium']);b._armed=True;b._ovc_armed=True
                b.setQuickDeathStrength('low','pulse',8);b.setQuickDeathStrength('low','ovc',39)
                low=b.quickPolicy['presets']['low']
                self.assertEqual((low['pulse_death_a'],low['pulse_death_b']),(8,8));self.assertEqual((low['ovc_death_a'],low['ovc_death_b']),(30,30))
                self.assertEqual(b._sim_profile['rules'],before);self.assertEqual(b.quickPolicy['presets']['medium'],medium)
                self.assertTrue(b._armed);self.assertTrue(b._ovc_armed)
                b.setQuickPresetValue('low','pulse_death_b',11);self.assertEqual(b.quickPolicy['presets']['low']['pulse_death_a'],8)
            finally:b.shutdown()
    def test_draft_does_not_send_apply_disarms_and_persists_separate_slots(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp') as temp:
            b=Backend(offline=True,settings=Path(temp)/'settings.json')
            try:
                b._armed=True;b._ovc_armed=True;old=deepcopy(b._sim_profile['rules'])
                b.setQuickPresetValue('low','pulse_death_a',7)
                self.assertEqual(b._sim_profile['rules'],old);self.assertTrue(b._armed);self.assertTrue(b._ovc_armed)
                b.applyQuickPreset('low',True);self.assertFalse(b._armed);self.assertFalse(b._ovc_armed)
                self.assertEqual(b.quickPolicy['death']['pulseA'],7)
                b.setDeathChannel('vibration','B',False);self.assertEqual(b.quickPolicy['ovcChannels'],'A')
                other=Backend(offline=True,settings=b.settings)
                try:
                    self.assertEqual(other.quickPolicy['death']['pulseA'],7)
                    self.assertEqual(other.quickPolicy['presets']['medium'],default_presets()['medium'])
                finally:other.shutdown()
            finally:b.shutdown()
