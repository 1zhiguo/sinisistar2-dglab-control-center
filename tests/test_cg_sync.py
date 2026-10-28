"""One-shot game/gallery strategy sync; offline fixtures, no transport."""
from copy import deepcopy
from pathlib import Path
import tempfile,unittest
from PySide6.QtGui import QGuiApplication
from sinisistar_dglab.backend import Backend,ROOT

class CgSync(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.qt=QGuiApplication.instance() or QGuiApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp')
        self.b=Backend(offline=True,settings=Path(self.temp.name)/'settings.json');self.b._timer.stop()
    def tearDown(self):self.b.shutdown();self.temp.cleanup()
    def assert_outputs_equal(self,left,right):
        self.assertEqual(left['routes'],right['routes'])
        for field,value in left['rule'].items():
            if field.startswith(('pulse_','vibration_')):self.assertEqual(value,right['rule'][field],field)
    def test_game_to_gallery_copies_all_four_strategies_preserves_scope_and_saves(self):
        b=self.b
        for route in ('pulse','vibration'):
            b.setCgStrengthRange(route,'a',7,24);b.setCgStrengthRange(route,'b',12,35)
            b.setCgOption(route+':A','mode','shuffle');b.setCgOption(route+':B','ramp_seconds',125)
            b.setCgQueue(route+':B',1,'seconds',19)
        b.setCgRule('death_mode','timed');b.setCgRule('death_seconds',8)
        b.setGalleryPauseOnStop(False);b.setCgRule('gallery/enabled',False)
        source=deepcopy(b.cgSettings);death=deepcopy(b._sim_profile['rules']['defeat_hold'])
        caps={k:v for k,v in b._sim_profile.items() if '_cap_' in k}
        b._armed=b._ovc_armed=True;b.syncCgFeedback('cg')
        self.assert_outputs_equal(source,b.gallerySettings);self.assertEqual(b.cgSettings,source)
        self.assertFalse(b.gallerySettings['pause_on_stop']);self.assertFalse(b.gallerySettings['rule']['enabled'])
        self.assertEqual(b.gallerySettings['rule']['death_mode'],'until_end')
        self.assertEqual(b._sim_profile['rules']['defeat_hold'],death)
        self.assertEqual({k:v for k,v in b._sim_profile.items() if '_cap_' in k},caps)
        self.assertFalse(b._armed or b._ovc_armed);self.assertEqual(b.quickPolicy['active'],'')
        other=Backend(offline=True,settings=b.settings);other._timer.stop()
        try:self.assertEqual(other.gallerySettings,b.gallerySettings)
        finally:other.shutdown()
        b.setCgQueue('gallery/pulse:A',0,'seconds',37)
        self.assertEqual(b.cgSettings,source)
    def test_gallery_to_game_preserves_game_gates_and_detaches_inheritance(self):
        b=self.b;b.setSameHpFeedbackEnabled(False);b.setSameHpTimeout(9)
        b.setCgRule('enabled',False);b.setCgRule('death_mode','timed');b.setCgRule('death_seconds',7)
        b.setCgOption('gallery/pulse:B','mode','shuffle');b.setCgOption('gallery/vibration:A','ramp_mode','ease_in')
        b.setCgStrengthRange('gallery/vibration','b',20,45)
        source=deepcopy(b.gallerySettings);b.syncCgFeedback('gallery')
        self.assert_outputs_equal(source,b.cgSettings);self.assertEqual(b.gallerySettings,source)
        self.assertFalse(b.cgSettings['inherit_death']);self.assertFalse(b.cgSettings['same_hp_enabled'])
        self.assertEqual(b.cgSettings['same_hp_timeout'],9);self.assertFalse(b.cgSettings['rule']['enabled'])
        self.assertEqual(b.cgSettings['rule']['death_mode'],'timed');self.assertEqual(b.cgSettings['rule']['death_seconds'],7)
    def test_inherited_source_uses_effective_parameters_without_changing_source(self):
        b=self.b;self.assertTrue(b.cgSettings['inherit_death'])
        before=deepcopy(b._sim_profile['cg']);effective=b.cgSettings;b.syncCgFeedback('cg')
        self.assert_outputs_equal(effective,b.gallerySettings);self.assertEqual(b._sim_profile['cg'],before)
    def test_invalid_scope_is_noop(self):
        b=self.b;before=deepcopy(b._sim_profile);b._armed=b._ovc_armed=True
        b.syncCgFeedback('pulse');self.assertEqual(b._sim_profile,before);self.assertTrue(b._armed and b._ovc_armed)
