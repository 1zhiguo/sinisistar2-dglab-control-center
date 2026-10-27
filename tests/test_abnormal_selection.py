"""Fixed per-kind, opt-in status feedback and selection contracts."""
from pathlib import Path
from copy import deepcopy
import tempfile,unittest
from PySide6.QtGui import QGuiApplication
from sinisistar_dglab.backend import Backend,WAVES,ROOT
from sinisistar_dglab.simulation import default_profile,initial_profile,sanitize_profile,Simulator
from sinisistar_dglab.quick_policy import apply_preset
from sinisistar_dglab.status_policy import STATUS_CATALOG,positive_status
from sinisistar_dglab.monitoring import status_label

def sample(items,**changes):
    s=dict(source='bepinex',live=True,valid=True,session='status',pid=1,player=2,scene_id=48,sample_id=1,sampled_at=10,
           hp=dict(current=100,max=100),mp=dict(current=100,max=100),time_scale=1,abnormals=items,bound=False,flow={})
    s.update(changes);return s

class StatusFeedback(unittest.TestCase):
    def test_factory_profiles_and_presets_start_with_all_statuses_off(self):
        for p in (default_profile(),initial_profile()):
            for name in ('low','medium','high'):
                q=apply_preset(p,name)
                self.assertFalse(any(r['enabled'] for r in q['abnormals'].values()))
                self.assertTrue(all(r['pulse_strength']==10 and r['pulse_level_step']==0 and r['vibration_strength']==0 and not r['vibration_enabled'] for r in q['abnormals'].values()))
    def test_levels_and_old_custom_strengths_cannot_raise_per_kind_or_drive_ovc(self):
        p=default_profile();p.update(pulse_cap_a=100,pulse_cap_b=100)
        for name in ('Poison','Slow','Defilement'):
            p['abnormals'][name].update(enabled=True,pulse_strength=99,pulse_level_step=30,pulse_gain=9,vibration_enabled=True,vibration_strength=200)
        for count in (1,2,3):
            items=[dict(name=n,level=99) for n in ('Poison','Slow','Defilement')[:count]]
            result=Simulator().evaluate(sample(items),p,WAVES,now=10)
            self.assertEqual(result['peaks']['pulseA'],10*count)
            self.assertEqual(result['peaks']['vibrationA'],0);self.assertEqual(result['peaks']['vibrationB'],0)
            self.assertTrue(all(r['pulse']==10 and r['vibration']==0 for r in result['active']))
    def test_distinct_types_add_only_on_their_selected_channels_and_deduplicate(self):
        p=default_profile();p.update(pulse_cap_a=100,pulse_cap_b=100)
        for name,channel in [('Poison','A'),('Slow','A'),('Defilement','B')]:p['abnormals'][name].update(enabled=True,pulse_channel=channel)
        items=[dict(name=n,level=1) for n in ('Poison','Slow','Defilement','Poison')]
        r=Simulator().evaluate(sample(items),p,WAVES,now=10)
        self.assertEqual(r['peaks']['pulseA'],20);self.assertEqual(r['peaks']['pulseB'],10)
        p['pulse_cap_a']=15;r=Simulator().evaluate(sample(items),p,WAVES,now=10)
        self.assertEqual(r['peaks']['pulseA'],15);self.assertTrue(r['clipped'])
    def test_different_status_waveforms_add_before_mixing_with_actions(self):
        p=default_profile();p.update(pulse_cap_a=100)
        p['abnormals']['Poison'].update(enabled=True,pulse_wave='half')
        p['abnormals']['Slow'].update(enabled=True,pulse_wave='full')
        p['rules']['grab_hold'].update(pulse_strength=2,pulse_wave='full')
        waves=WAVES+[dict(key='half',points=[.5]*16),dict(key='full',points=[1.]*16)]
        for mode,peak,value in [('priority',20,15),('max',20,15),('sum',22,17)]:
            p['mix']=mode;r=Simulator().evaluate(sample([dict(name='Poison',level=1),dict(name='Slow',level=1)],bound=True),p,waves,now=10)
            self.assertEqual(r['peaks']['pulseA'],peak);self.assertEqual(r['pulseA'],value)
    def test_old_profiles_disable_statuses_and_new_profiles_keep_explicit_opt_in(self):
        p=default_profile();p['abnormals']['Poison'].update(enabled=True,pulse_strength=80,vibration_enabled=True)
        p['version']=8;old=sanitize_profile(p);self.assertFalse(old['abnormals']['Poison']['enabled'])
        p['version']=9;new=sanitize_profile(p);self.assertTrue(new['abnormals']['Poison']['enabled'])
        self.assertEqual(new['abnormals']['Poison']['pulse_strength'],10);self.assertFalse(new['abnormals']['Poison']['vibration_enabled'])
        for name in ('low','medium','high'):self.assertTrue(apply_preset(new,name)['abnormals']['Poison']['enabled'])
    def test_all_70_types_have_chinese_labels_and_filter_metadata(self):
        self.assertEqual(len(STATUS_CATALOG),70)
        self.assertEqual(sum(r['translation_source']=='game' for r in STATUS_CATALOG.values()),38)
        self.assertEqual(sum(r['translation_source']=='internal' for r in STATUS_CATALOG.values()),32)
        for name,meta in STATUS_CATALOG.items():
            self.assertNotEqual(status_label(name),name);self.assertTrue(any('\u4e00'<=c<='\u9fff' for c in status_label(name)))
            self.assertTrue(meta['category']);self.assertTrue(meta['category_label'])

class StatusSelection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.qt=QGuiApplication.instance() or QGuiApplication([])
    def test_batch_is_scoped_positive_excluded_and_outputs_disarmed(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp') as temp:
            b=Backend(offline=True,settings=Path(temp)/'settings.json')
            try:
                events=deepcopy(b._sim_profile['rules']);b._armed=True;b._ovc_armed=True
                b.batchSetAbnormals(['Poison','Poison','Slow','InfertilityBlessing','unknown'],True)
                self.assertEqual({k for k,r in b._sim_profile['abnormals'].items() if r['enabled']},{'Poison','Slow'})
                self.assertEqual(events,b._sim_profile['rules']);self.assertFalse(b._armed);self.assertFalse(b._ovc_armed)
                b.batchSetAbnormals(['Poison'],False);self.assertFalse(b._sim_profile['abnormals']['Poison']['enabled']);self.assertTrue(b._sim_profile['abnormals']['Slow']['enabled'])
                other=Backend(offline=True,settings=b.settings)
                try:self.assertTrue(other._sim_profile['abnormals']['Slow']['enabled'])
                finally:other.shutdown()
            finally:b.shutdown()
    def test_individual_editor_cannot_change_fixed_values_but_keeps_wave_and_channel_options(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp') as temp:
            b=Backend(offline=True,settings=Path(temp)/'settings.json')
            try:
                i=next(i for i,r in enumerate(b.simulationAbnormals) if r['key']=='Poison')
                for field,value in [('pulse_strength',80),('pulse_level_step',20),('vibration_enabled',True),('vibration_strength',100)]:b.setSimulationRule('abnormals',i,field,value)
                row=b.simulationAbnormals[i];self.assertEqual(row['pulse_strength'],10);self.assertEqual(row['pulse_level_step'],0);self.assertFalse(row['vibration_enabled']);self.assertEqual(row['vibration_strength'],0)
                b.setSimulationRule('abnormals',i,'pulse_channel','B');self.assertEqual(b.simulationAbnormals[i]['pulse_channel'],'B')
            finally:b.shutdown()
