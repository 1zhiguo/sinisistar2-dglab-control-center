from pathlib import Path
import tempfile,unittest
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from sinisistar_dglab.backend import Backend,ROOT
from sinisistar_dglab.hotkeys import GlobalHotkeys,shortcut,normalize_shortcut,DEFAULT

class Api:
    def __init__(self):self.bindings={};self.calls=[]
    def register(self,ident,mods,vk):
        self.calls.append(('register',ident,mods,vk))
        if (mods,vk) in self.bindings.values():return '1409 · already registered'
        self.bindings[ident]=(mods,vk);return ''
    def unregister(self,ident):self.calls.append(('unregister',ident));self.bindings.pop(ident,None)

class Hotkeys(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QGuiApplication.instance() or QGuiApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp')
        self.b=Backend(offline=True,settings=Path(self.temp.name)/'settings.json');self.b._timer.stop();self.api=Api()
        self.m=GlobalHotkeys(self.app,self.b,self.api,install=False)
    def tearDown(self):self.b.shutdown();self.temp.cleanup()
    def test_single_keys_combinations_and_function_key_conversion(self):
        self.assertEqual(shortcut(Qt.Key_K),dict(sequence='K',modifiers=0,vk=75))
        self.assertEqual(shortcut(Qt.Key_F9,Qt.ControlModifier|Qt.ShiftModifier)['modifiers'],6)
        self.assertEqual(shortcut(Qt.Key_Space)['vk'],32)
        for n in range(24):self.assertEqual(shortcut(int(Qt.Key_F1)+n)['vk'],112+n)
        for key in (Qt.Key_Control,Qt.Key_Shift,Qt.Key_Alt):
            with self.assertRaises(ValueError):shortcut(key)
        self.assertEqual(normalize_shortcut(dict(sequence='',vk=1,modifiers=0)),DEFAULT)
    def test_recording_suspends_then_restores_old_key_and_does_not_trigger_stop(self):
        self.m.begin();self.assertFalse(self.m.registered)
        self.assertFalse(self.m.hud_registered)
        self.assertFalse(self.m.dispatch(0x312,self.m.ident));self.assertFalse(self.b._emergency)
        self.m.record(Qt.Key_Control,Qt.ControlModifier.value);self.assertTrue(self.m.capturing)
        self.m.record(Qt.Key_F8,Qt.ControlModifier.value)
        self.assertTrue(self.m.registered);self.assertFalse(self.m.capturing)
        self.assertEqual(self.m.candidate['sequence'],'Ctrl+F8');self.assertEqual(self.m.active,DEFAULT)
        self.m.begin();self.m.cancel();self.assertTrue(self.m.registered)
        self.assertTrue(self.m.hud_registered)
        self.m.begin();self.m.record(Qt.Key_F11,Qt.ControlModifier.value)
        self.assertFalse(self.m.apply());self.assertEqual(self.m.active,DEFAULT)
        self.assertTrue(self.m.registered and self.m.hud_registered)
    def test_conflict_keeps_old_shortcut_and_registration(self):
        old_id=self.m.ident;candidate=shortcut(Qt.Key_F8,Qt.AltModifier)
        self.api.bindings[9000]=(candidate['modifiers'],candidate['vk'])
        self.assertFalse(self.m.apply(candidate));self.assertTrue(self.m.registered)
        self.assertEqual(self.m.ident,old_id);self.assertEqual(self.m.active,DEFAULT)
        self.assertIn('1409',self.m.error)
        self.assertFalse(self.m.apply(shortcut(Qt.Key_F11,Qt.ControlModifier)))
        self.assertTrue(self.m.registered)
    def test_replacement_persists_and_dispatch_locks_both_outputs(self):
        old_id=self.m.ident;candidate=shortcut(Qt.Key_J,Qt.ControlModifier|Qt.AltModifier)
        self.assertTrue(self.m.apply(candidate));self.assertNotIn(old_id,self.api.bindings)
        self.assertEqual(self.b._emergency_shortcut,candidate)
        self.b._armed=self.b._ovc_armed=True
        self.assertTrue(self.m.dispatch(0x312,self.m.ident))
        self.assertTrue(self.b._emergency);self.assertFalse(self.b._armed or self.b._ovc_armed)
        other=Backend(offline=True,settings=self.b.settings);other._timer.stop()
        try:self.assertEqual(other._emergency_shortcut,candidate)
        finally:other.shutdown()
        self.b.unlock();self.assertFalse(self.b._armed or self.b._ovc_armed)
    def test_shutdown_releases_registered_keys_once(self):
        self.m.apply(shortcut(Qt.Key_F7));active_id=self.m.ident
        self.b.shutdown();calls=list(self.api.calls);self.b.shutdown()
        self.assertNotIn(active_id,self.api.bindings);self.assertNotIn(7163,self.api.bindings)
        self.assertEqual(calls,self.api.calls)
