"""Preview tests use explicit samples and fake time, never a device service."""
import json, tempfile, time, unittest
from copy import deepcopy
from pathlib import Path
from sinisistar_dglab.simulation import Simulator,default_profile,sanitize_profile,base_rule,demo_state,VIBRATION_WAVES
from sinisistar_dglab.backend import WAVES
from sinisistar_dglab.flows import FlowCatalog

def sample(now=10.,sid=1,**kw):
    s=demo_state('idle',0,now);s.update(session='test',pid=7,player=8,scene_id=43,scene='Monastery_Tutorial1',sample_id=sid)
    s.update(kw);return s

class Simulation(unittest.TestCase):
    def setUp(self):
        self.sim=Simulator();self.p=default_profile()
        from sinisistar_dglab.status_policy import positive_status
        for name,r in self.p['abnormals'].items():r['enabled']=not positive_status(name)
    def run_at(self,s,now=10.,**kw):return self.sim.evaluate(s,self.p,WAVES,now=now,**kw)
    def test_clothing_break_is_one_custom_duration_burst_not_a_state_hold(self):
        self.p['rules']['break']['duration']=.3
        self.run_at(sample())
        r=self.run_at(sample(10.1,2,broken=True),10.1,events=[dict(key='break')])
        self.assertEqual([x['key'] for x in r['active']],['break'])
        start=self.sim.bursts['break']['start']
        self.run_at(sample(10.2,3,broken=True),10.2,events=[dict(key='break')])
        self.assertEqual(self.sim.bursts['break']['start'],start)
        self.assertEqual(self.run_at(sample(10.41,4,broken=True),10.41)['active'],[])
        self.assertEqual(self.run_at(sample(10.5,5,broken=False),10.5)['active'],[])
        self.assertEqual([x['key'] for x in self.run_at(sample(10.6,6,broken=True),10.6)['active']],['break'])
    def test_already_broken_on_start_or_rebind_does_not_trigger(self):
        self.assertFalse(self.run_at(sample(broken=True))['active'])
        self.assertFalse(self.run_at(sample(10.1,2,player=9,broken=True),10.1)['active'])
    def test_break_during_pause_or_gap_is_not_replayed(self):
        self.run_at(sample())
        self.run_at(sample(10.1,2,broken=True,paused=True),10.1)
        self.assertFalse(self.run_at(sample(10.2,3,broken=True),10.2)['active'])
        self.run_at(sample(10.3,4,broken=False),10.3)
        self.assertFalse(self.run_at(sample(12.,5,broken=True),12.)['active'])
    def test_escape_is_observation_only_even_with_legacy_enabled_rule(self):
        old=default_profile();old['rules']['escape']=base_rule('escape','escape')
        self.assertNotIn('escape',sanitize_profile(old)['rules'])
        self.p=old
        self.assertFalse(self.run_at(sample(),events=[dict(key='escape')])['active'])
    def test_mp_loss_and_legacy_mp_events_never_trigger_either_route(self):
        for bound in (False,True):
            with self.subTest(bound=bound):
                self.sim.reset();self.p['rules']['grab_hold']['enabled']=False
                # Old enabled rules and injected events cannot restore MP feedback.
                for key in ('mp_loss','grab_mp_loss'):
                    self.p['rules'][key]=base_rule(key,key)
                self.run_at(sample(bound=bound))
                result=self.run_at(sample(10.1,2,bound=bound,mp={'current':20,'max':100}),10.1,
                                   events=[dict(key='mp_loss'),dict(key='grab_mp_loss')])
                self.assertFalse(result['active']);self.assertFalse(self.sim.bursts)
                self.assertTrue(all(result['peaks'][k]==0 for k in ('pulseA','pulseB','vibrationA','vibrationB')))
    def test_legacy_mp_rules_and_presets_are_removed_on_load_and_apply(self):
        old=default_profile();old['rules']['mp_loss']=base_rule('mp_loss','MP')
        old['rules']['grab_mp_loss']=base_rule('grab_mp_loss','MP')
        old['quick_presets']['high'].update(pulse_mp=100,ovc_mp=200)
        from sinisistar_dglab.quick_policy import apply_preset
        p=sanitize_profile(old)
        for name in ('low','medium','high'):
            result=apply_preset(p,name)
            self.assertNotIn('mp_loss',result['rules']);self.assertNotIn('grab_mp_loss',result['rules'])
            self.assertNotIn('pulse_mp',result['quick_presets'][name]);self.assertNotIn('ovc_mp',result['quick_presets'][name])
    def test_abnormal_holds_for_minutes_and_stops_on_removal(self):
        s=sample(abnormals=[{'name':'Poison','level':1}]);r=self.run_at(s)
        self.assertEqual(r['active'][0]['key'],'Poison')
        r=self.run_at(sample(600.,2,abnormals=s['abnormals']),600.)
        self.assertGreater(r['peaks']['pulseA'],0)
        self.assertEqual(self.run_at(sample(600.1,3),600.1)['peaks']['pulseA'],0)
    def test_levels_and_distinct_status_count_affect_both_routes(self):
        r=self.run_at(sample(abnormals=[{'name':'Defilement','level':3},{'name':'Poison','level':1}]))
        item=next(x for x in r['active'] if x['key']=='Defilement')
        self.assertEqual(item['pulse'],10);self.assertEqual(item['vibration'],0)
    def test_positive_blessing_cannot_participate_even_if_old_rule_enabled(self):
        s=sample(abnormals=[{'name':'InfertilityBlessing','level':1}])
        self.p['abnormals']['InfertilityBlessing'].update(enabled=True,pulse_enabled=True,vibration_enabled=True)
        self.assertEqual(self.run_at(s)['active'],[])
    def test_grab_resource_losses_choose_grab_rules_once(self):
        self.run_at(sample(bound=True))
        s=sample(10.1,2,bound=True,hp={'current':90,'max':100},mp={'current':80,'max':100})
        keys={x['key'] for x in self.run_at(s,10.1)['active']}
        self.assertIn('grab_hp_loss',keys);self.assertNotIn('grab_mp_loss',keys);self.assertNotIn('hp_loss',keys)
        start=self.sim.bursts['grab_hp_loss']['start'];self.run_at(s,10.2)
        self.assertEqual(self.sim.bursts['grab_hp_loss']['start'],start)
    def test_hp_and_mp_gain_and_actor_rebind_do_not_trigger_loss(self):
        self.run_at(sample(hp={'current':10,'max':100}))
        self.assertEqual(self.run_at(sample(10.1,2,hp={'current':100,'max':100}),10.1)['active'],[])
        self.assertEqual(self.run_at(sample(10.2,3,player=9,hp={'current':1,'max':100}),10.2)['active'],[])
    def test_pause_stale_loading_and_emergency_zero_all_routes(self):
        for changes,kwargs in [({'paused':True},{}),({'loading':True},{}),({'sampled_at':1.},{}),({},dict(emergency=True)),({},dict(enabled=False))]:
            with self.subTest(changes=changes,kwargs=kwargs):
                self.run_at(sample(bound=True))
                s=sample(10.1,2,bound=True);s.update(changes);r=self.run_at(s,10.1,**kwargs)
                self.assertEqual([r[k] for k in ('pulseA','pulseB','vibrationA','vibrationB')],[0]*4)
                self.assertFalse(self.sim.bursts)
    def test_previous_telemetry_gap_does_not_create_delayed_hit(self):
        self.run_at(sample())
        self.assertEqual(self.run_at(sample(12.,2,hp={'current':20,'max':100}),12.)['active'],[])
    def test_per_route_caps_and_sum_of_multiple_envelopes(self):
        self.p.update(mix='sum',pulse_cap_a=7,vibration_cap_a=9)
        r=self.run_at(sample(abnormals=[{'name':'Poison','level':10},{'name':'Slow','level':10}]))
        self.assertTrue(r['clipped']);self.assertEqual(r['peaks']['pulseA'],7);self.assertEqual(r['peaks']['vibrationA'],0)
        for i in range(1,30):
            r=self.run_at(sample(10+i*.1,i+1,abnormals=[{'name':'Poison','level':10},{'name':'Slow','level':10}]),10+i*.1)
            self.assertLessEqual(r['pulseA'],7);self.assertLessEqual(r['vibrationA'],9)
    def test_priority_and_channel_selection_are_independent(self):
        r=self.p['rules']['grab_hold'];r.update(pulse_channel='B',vibration_channel='A',priority=90)
        out=self.run_at(sample(bound=True,abnormals=[{'name':'Poison','level':10}]))
        self.assertEqual(out['selected']['pulseB'],['抓取期间']);self.assertEqual(out['selected']['vibrationA'],['抓取期间'])
        self.assertGreater(out['peaks']['pulseA'],0);self.assertEqual(out['peaks']['vibrationB'],0)
    def test_route_disabled_status_does_not_boost_that_route(self):
        self.p['abnormals']['Slow']['pulse_enabled']=False
        out=self.run_at(sample(abnormals=[{'name':'Slow','level':1},{'name':'Poison','level':1}]))
        self.assertEqual(next(r for r in out['active'] if r['key']=='Poison')['pulse'],10)
    def test_abnormal_baseline_is_ten_per_distinct_type_in_all_mix_modes(self):
        names=['Poison','Slow','Defilement'];self.p['pulse_cap_a']=100
        for mode in ('priority','max','sum'):
            self.p['mix']=mode
            for count in (1,2,3):
                s=sample(abnormals=[{'name':name,'level':9} for name in names[:count]])
                self.assertEqual(self.run_at(s)['peaks']['pulseA'],10*count)
        s=sample(abnormals=[{'name':'Poison','level':9},{'name':'Poison','level':9},{'name':'Slow','level':0}])
        self.assertEqual(self.run_at(s)['peaks']['pulseA'],10)
    def test_death_penalty_owns_its_channels_instead_of_mixing_the_status_wave(self):
        s=sample(bound=True,hp={'current':0,'max':100},abnormals=[{'name':'Poison','level':1},{'name':'Slow','level':1}])
        result=self.run_at(s)
        self.assertEqual(result['peaks']['pulseA'],20)
        self.assertEqual(result['selected']['pulseA'],[self.p['rules']['defeat_hold']['name']])
        self.assertIn('defeat_hold',[x['key'] for x in result['active']])
    def test_old_factory_status_defaults_upgrade_without_losing_custom_values(self):
        old={'version':1,'abnormals':{'Poison':{'pulse_strength':17,'pulse_level_step':4,'enabled':False},
                                     'Defilement':{'pulse_strength':6,'pulse_level_step':1},
                                     'InfertilityBlessing':{'enabled':False,'pulse_strength':6,'pulse_level_step':1}}}
        new=sanitize_profile(old)
        self.assertEqual(new['abnormals']['Defilement']['pulse_strength'],10)
        self.assertEqual(new['abnormals']['Defilement']['pulse_level_step'],0)
        self.assertEqual(new['abnormals']['Poison']['pulse_strength'],10)
        self.assertEqual(new['abnormals']['Poison']['pulse_level_step'],0)
        self.assertFalse(new['abnormals']['Poison']['enabled'])
        self.assertFalse(new['abnormals']['InfertilityBlessing']['enabled'])
    def test_unknown_pulse_wave_does_not_fall_back_to_another_wave(self):
        self.p['rules']['grab_hold']['pulse_wave']='nonexistent'
        r=self.run_at(sample(bound=True));self.assertEqual(r['peaks']['pulseA'],0);self.assertGreater(r['peaks']['vibrationA'],0)
    def test_history_events_never_trigger_bursts(self):
        self.p['rules']['enemy_hit']['enabled']=True
        self.assertEqual(self.run_at(sample(),events=[{'key':'enemy_hit','history':True}])['active'],[])
    def test_flow_identity_exact_label_and_time_window(self):
        rule=base_rule('flow1','阶段反馈');rule.update(label='Phase2',start=2,end=4)
        self.p['flows']=[rule]
        f=dict(valid=True,key='flow1',playing=True,paused=False,label='Phase2',timeline_time=3,run=1)
        self.assertEqual(self.run_at(sample(flow=f))['active'][0]['name'],'阶段反馈')
        for changes in ({'key':'other'},{'label':'Phase1'},{'timeline_time':4},{'paused':True}):
            ff=dict(f);ff.update(changes)
            self.assertEqual(self.run_at(sample(flow=ff))['active'],[])
    def test_zero_hp_without_flow_is_a_current_death_stage(self):
        self.assertEqual(self.run_at(sample(hp={'current':0,'max':100}))['active'][0]['key'],'defeat_hold')
        self.p['flows']=[base_rule('x','演出')]
        s=sample(valid=False,hp=None,flow=dict(valid=True,key='x',playing=True,paused=False,elapsed=2))
        self.assertTrue(self.run_at(s)['active'])
    def test_zero_hp_capture_is_explicitly_unconfirmed_and_configurable(self):
        s=sample(bound=True,hp={'current':0,'max':100},abnormals=[{'name':'Poison','level':1}])
        r=self.run_at(s);self.assertTrue(r['active']);self.assertIn('CG 未确认',r['reason'])
        self.p['zero_hp_mode']='stop';self.assertFalse(self.run_at(s)['active'])
        self.p['zero_hp_mode']='states';s['bound']=False
        self.assertIn('Poison',[x['key'] for x in self.run_at(s)['active']])
    def test_zero_hp_hold_is_independent_of_damage_bursts_and_ends_on_revival(self):
        self.p['rules']['defeat_hold'].update(pulse_channel='B',pulse_strength=13,pulse_wave='pulse',pulse_max=False)
        self.run_at(sample(bound=True))
        self.run_at(sample(10.1,2,bound=True,hp={'current':0,'max':100}),10.1)
        result=self.run_at(sample(150.,3,bound=True,hp={'current':0,'max':100}),150.)
        self.assertEqual([r['key'] for r in result['active']],['defeat_hold'])
        self.assertEqual(result['pulse_stream']['B']['peak'],13)
        result=self.run_at(sample(150.1,4,bound=True),150.1)
        self.assertNotIn('defeat_hold',[r['key'] for r in result['active']])
        self.assertIsNone(result['pulse_stream']['B'])
    def test_custom_vibration_wave_has_its_own_catalog(self):
        self.p['rules']['grab_hold']['vibration_wave']='vib_custom_a'
        r=self.run_at(sample(bound=True),vibration_waves=VIBRATION_WAVES+[dict(key='vib_custom_a',points=[1.]*16)])
        self.assertEqual(r['vibrationA'],15);self.assertNotEqual(r['pulseA'],15)
    def test_invalid_config_and_nonfinite_values_are_clamped(self):
        p=sanitize_profile({'mix':'bad','pulse_cap_a':float('inf'),'rules':{'grab_hold':{'duration':-10,'pulse_strength':999,'pulse_period':0}}})
        self.assertEqual(p['mix'],'priority');self.assertEqual(p['pulse_cap_a'],20);self.assertEqual(p['rules']['grab_hold']['pulse_strength'],100)
        self.assertEqual(p['rules']['grab_hold']['pulse_period'],.1)
    def test_localized_flow_key_survives_configuration_round_trip(self):
        key=json.dumps([43,'事件组'*40,'演出播放器'*30,'EventLabelPlayer'],ensure_ascii=True)
        self.assertGreater(len(key),600)
        profile=default_profile();profile['flows']=[base_rule(key,'中文演出')]
        reloaded=sanitize_profile(json.loads(json.dumps(profile)))
        self.assertEqual(reloaded['flows'][0]['key'],key)

TMP=Path(__file__).resolve().parents[1]/'artifacts/test-temp';TMP.mkdir(parents=True,exist_ok=True)
class CatalogAndBackend(unittest.TestCase):
    def test_catalog_retains_actual_labels_without_guessing_defeat(self):
        with tempfile.TemporaryDirectory(dir=TMP) as d:
            path=Path(d)/'flows.json';c=FlowCatalog(path)
            s=sample(flow=dict(valid=True,key='scene|player',name='Event001',playing=True,label='P1',run=1))
            self.assertTrue(c.observe(s));self.assertFalse(c.observe(s));self.assertFalse(c.rows()[0]['defeat_confirmed'])
            s['flow'].update(label='P2',defeat_confirmed=True);c.observe(s)
            self.assertEqual(FlowCatalog(path).rows()[0]['labels'],['P1','P2'])
    @classmethod
    def setUpClass(cls):
        from PySide6.QtGui import QGuiApplication
        cls.app=QGuiApplication.instance() or QGuiApplication([])
    def test_preview_stops_connection_and_cannot_arm_real_output(self):
        from sinisistar_dglab.backend import Backend
        with tempfile.TemporaryDirectory(dir=TMP) as d:
            b=Backend(offline=True,settings=Path(d)/'settings.json')
            try:
                b.batchSetAbnormals(['Poison'],True);b.simulationSource('abnormals');b.toggleSimulation();b.toggleArm();b.startConnection();b.tick()
                self.assertFalse(b.state['armed']);self.assertIsNone(b._service);self.assertTrue(b.simulation['active'])
                b.emergencyStop();self.assertFalse(b.simulation['running']);self.assertEqual(b.simulation['pulseA'],0)
            finally:b.shutdown()
    def test_simulation_and_custom_vibration_configuration_persist_separately(self):
        from sinisistar_dglab.backend import Backend
        with tempfile.TemporaryDirectory(dir=TMP) as d:
            path=Path(d)/'settings.json';b=Backend(offline=True,settings=path)
            try:
                b.setSimulationSetting('mix','sum');b.setSimulationRule('abnormals',0,'pulse_strength',11)
                b.editWaveRoute('vibration');b.editPoint(4,.4);b.saveWave('测试震动');key=b.selectedWave
                other=Backend(offline=True,settings=path)
                try:
                    self.assertEqual(other.simulationSettings['mix'],'sum');self.assertEqual(other.simulationAbnormals[0]['pulse_strength'],10)
                    self.assertTrue(any(w['key']==key for w in other.vibrationWaves));self.assertFalse(any(w['key']==key for w in other.waves))
                    self.assertFalse(other.simulation['running'])
                finally:other.shutdown()
            finally:b.shutdown()

if __name__=='__main__':unittest.main()
