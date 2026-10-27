from copy import deepcopy
from pathlib import Path
import tempfile,unittest
from PySide6.QtGui import QGuiApplication
from sinisistar_dglab.simulation import initial_profile,sanitize_profile
from sinisistar_dglab.quick_policy import apply_preset,default_presets
from sinisistar_dglab.backend import Backend,ROOT
from sinisistar_dglab.pulse import PulsePlanner
from test_gallery_output import profile,state,WAVES

class CgPresetSpeed(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.qt=QGuiApplication.instance() or QGuiApplication([])
    def test_tiers_update_both_cg_scopes_and_all_four_ranges_only(self):
        p=initial_profile();p['cg']['inherit_death']=False
        p['gallery']['routes']['pulse']['B'].update(mode='shuffle',ramp_seconds=123)
        original=deepcopy(p)
        for name in ('low','medium','high'):
            q=apply_preset(p,name);values=default_presets()[name]
            for scope in ('cg','gallery'):
                self.assertEqual(q[scope]['routes'],original[scope]['routes'])
                for route,prefix in (('pulse','pulse'),('vibration','ovc')):
                    self.assertEqual(q[scope]['rule'][route+'_channel'],original[scope]['rule'][route+'_channel'])
                    for c in 'ab':
                        self.assertEqual(q[scope]['rule'][route+'_strength_'+c],values[prefix+'_death_'+c])
                        self.assertEqual(q[scope]['rule'][route+'_start_strength_'+c],values[prefix+'_death_start_'+c])
            self.assertEqual(q['gallery']['rule']['enabled'],original['gallery']['rule']['enabled'])
        self.assertEqual(p,original)
    def test_death_only_keeps_independent_cg_and_gallery_intact(self):
        p=initial_profile();q=apply_preset(p,'low',death_only=True)
        self.assertEqual(q['cg'],p['cg']);self.assertEqual(q['gallery'],p['gallery'])
    def test_existing_named_preset_migrates_once_and_custom_ranges_survive(self):
        p=initial_profile();p.pop('feedback_preset_version');p['gallery']['rule']['pulse_strength_a']=49
        q=sanitize_profile(p);self.assertEqual(q['gallery']['rule']['pulse_strength_a'],55)
        q['gallery']['rule']['pulse_strength_a']=47
        self.assertEqual(sanitize_profile(q)['gallery']['rule']['pulse_strength_a'],47)
        p['quick_active_preset']='';self.assertEqual(sanitize_profile(p)['gallery']['rule']['pulse_strength_a'],49)
    def test_manual_range_and_speed_are_custom_capped_independent_and_persisted(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp') as folder:
            b=Backend(offline=True,settings=Path(folder)/'settings.json');b._timer.stop()
            try:
                b.applyQuickPreset('low');queue=deepcopy(b.gallerySettings['routes'])
                b.setCgStrengthRange('gallery/pulse','a',4,90)
                self.assertEqual(b.gallerySettings['rule']['pulse_strength_a'],30)
                self.assertEqual(b.quickPolicy['active'],'')
                b.setCgOption('gallery/pulse:A','ramp_seconds',15)
                self.assertEqual(b.gallerySettings['routes']['pulse']['A']['ramp_seconds'],15)
                self.assertEqual(b.gallerySettings['routes']['pulse']['B'],queue['pulse']['B'])
                b.applyQuickPreset('high')
                self.assertEqual(b.gallerySettings['rule']['pulse_strength_a'],80)
                self.assertEqual(b.gallerySettings['routes']['pulse']['A']['ramp_seconds'],15)
                other=Backend(offline=True,settings=b.settings);other._timer.stop()
                try:self.assertEqual(other.gallerySettings,b.gallerySettings)
                finally:other.shutdown()
            finally:b.shutdown()
    def test_cycle_ramp_speed_changes_peak_and_resets_without_altering_wave_queue(self):
        slow=profile();fast=deepcopy(slow)
        for p,seconds in ((slow,.8),(fast,.2)):
            opt=p['gallery']['routes']['pulse']['A']
            opt.update(mode='sequence',loop=True,ramp_scope='cycle',ramp_seconds=seconds,
                queue=[dict(wave='flat',seconds=.4,period=1.,scale=1),dict(wave='half',seconds=.4,period=1.,scale=1)])
        engines=[PulsePlanner(),PulsePlanner()];outputs=[]
        for engine,p in zip(engines,(slow,fast)):
            engine.update(state(10),p,WAVES,now=10,enabled=True)
            out=engine.update(state(10.2),p,WAVES,now=10.2,enabled=True);outputs.append(out)
            self.assertEqual(out['active'][0]['pulse_wave_A'],'flat')
            engine.update(state(10.6),p,WAVES,now=10.6,enabled=True)
            reset=engine.update(state(10.85),p,WAVES,now=10.85,enabled=True)
            self.assertLess(reset['peaks']['pulseA'],out['peaks']['pulseA'])
        self.assertGreater(outputs[1]['peaks']['pulseA'],outputs[0]['peaks']['pulseA'])
        self.assertEqual(outputs[1]['peaks']['pulseB'],outputs[0]['peaks']['pulseB'])
