import unittest,time,tempfile,json
from pathlib import Path
from datetime import datetime,timezone,timedelta
from copy import deepcopy
from sinisistar_dglab.events import EventDetector
from sinisistar_dglab.plugin_bridge import PluginObserver
from sinisistar_dglab.telemetry import BUILD
from sinisistar_dglab.dglab import ConnectionService,frequency_byte,envelope_frame

def state(hp=100,sample=1,**kw):
    d=dict(live=True,valid=True,pid=8,player=99,scene_id=25,hp={'current':hp,'max':100},paused=False,time_scale=1,sample_id=sample,sampled_at=time.monotonic(),bound=False,broken=False,abnormals=[],gacha=None);d.update(kw);return d

class Events(unittest.TestCase):
    def test_hp_and_healing(self):
        d=EventDetector();self.assertEqual(d.update(state()),[])
        self.assertEqual(d.update(state(80,2))[0]['key'],'damage')
        self.assertEqual(d.update(state(100,3))[0]['key'],'heal')
    def test_pause_discards_gap(self):
        d=EventDetector();d.update(state());self.assertEqual(d.update(state(80,2,paused=True)),[])
        self.assertEqual(d.update(state(60,3)),[])
    def test_reload_not_heal(self):
        d=EventDetector();d.update(state(0));self.assertEqual(d.update(state(100,2,player=101)),[])
    def test_dead_is_not_escape(self):
        d=EventDetector();d.update(state());d.update(state(100,2,bound=True,gacha={'value':0,'threshold':10}))
        es=d.update(state(0,3,bound=True,gacha={'value':0,'threshold':10}));self.assertIn('hp0',[e['key'] for e in es]);self.assertNotIn('escape',[e['key'] for e in es])
    def test_escape_requires_episode_threshold(self):
        d=EventDetector();d.update(state());d.update(state(90,2,bound=True,gacha={'value':0,'threshold':10}))
        es=d.update(state(90,3,bound=False,gacha={'value':11,'threshold':10}));self.assertIn('escape',[e['key'] for e in es])
        d.update(state(90,4,bound=True,gacha={'value':0,'threshold':10}))
        self.assertNotIn('escape',[e['key'] for e in d.update(state(90,5,bound=False,gacha={'value':0,'threshold':10}))])
    def test_stale_snapshot_resets(self):
        d=EventDetector();d.update(state());self.assertEqual(d.update(state(80,2,sampled_at=time.monotonic()-2)),[])
    def test_zero_and_duplicate_once(self):
        d=EventDetector();d.update(state(10));zero=state(0,2);self.assertEqual([x['key'] for x in d.update(zero)],['damage','hp0']);self.assertEqual(d.update(zero),[])

class Bridge(unittest.TestCase):
    def packet(self):return dict(schema=1,source='bepinex',fingerprint=BUILD,session='session',pid=1,sample_id=1,utc=datetime.now(timezone.utc).isoformat(),scene_id=25,valid=True,hp={'current':100,'max':100},mp=None,durability=None,abnormals=[])
    def test_real_schema(self):self.assertEqual(PluginObserver.decode(self.packet())['scene'],'Dungeon_Swamp1')
    def test_stale_denied(self):
        p=self.packet();p['utc']=(datetime.now(timezone.utc)-timedelta(seconds=2)).isoformat()
        with self.assertRaises(ValueError):PluginObserver.decode(p)
    def test_bad_fingerprint_denied(self):
        p=self.packet();p['fingerprint']='other'
        with self.assertRaises(ValueError):PluginObserver.decode(p)
    def test_invalid_hp_denied(self):
        p=self.packet();p['hp']['current']=1000
        with self.assertRaises(ValueError):PluginObserver.decode(p)
    def test_valid_player_without_hp_is_not_a_live_snapshot(self):
        p=self.packet();p['hp']=None
        with self.assertRaises(ValueError):PluginObserver.decode(p)
    def test_dotnet_seven_digit_timestamp(self):
        p=self.packet();p['utc']=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')+'0+00:00'
        self.assertTrue(PluginObserver.decode(p)['live'])

class Transport(unittest.TestCase):
    def test_no_pairing_no_output(self):
        c=ConnectionService(host='127.0.0.1',port=0)
        self.assertFalse(c.set_output_permission(True));self.assertFalse(c.play_feedback('A',5,1,[0,1,0],30,20))
    def test_watchdog_denies_expired_lease(self):
        c=ConnectionService(host='127.0.0.1',port=0);c._state.update(connected=True,feedback_known=True,limit_a=20,limit_b=20)
        self.assertTrue(c.set_output_permission(True));c._permission_at=time.monotonic()-1
        self.assertFalse(c.play_feedback('A',5,1,[0,1,0],30,20))
    def test_frequency_and_frame(self):
        self.assertEqual(frequency_byte(100),10);self.assertEqual(len(envelope_frame((0,1,0),30,0,1)),16)

TEST_TMP=Path(__file__).resolve().parents[1]/"artifacts/test-temp"
assert TEST_TMP.resolve().is_relative_to(Path(__file__).resolve().parents[1])
TEST_TMP.mkdir(parents=True,exist_ok=True)

class Settings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtGui import QGuiApplication
        cls.app=QGuiApplication.instance() or QGuiApplication([])
    def test_start_paused_no_server(self):
        from sinisistar_dglab.backend import Backend
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as temp:
            b=Backend(offline=True,settings=Path(temp)/'settings.json')
            try:
                self.assertFalse(b.state['armed']);self.assertFalse(b.state['serverReady']);self.assertFalse(b.state['outputActive'])
            finally:b.shutdown()
    def test_emergency_latches(self):
        from sinisistar_dglab.backend import Backend
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as temp:
            b=Backend(offline=True,settings=Path(temp)/'settings.json')
            try:
                b.toggleArm();b.emergencyStop();b.toggleArm();self.assertFalse(b.state['armed']);b.unlock();self.assertFalse(b.state['armed'])
            finally:b.shutdown()
    def test_wave_channel_rule_persistence(self):
        from sinisistar_dglab.backend import Backend
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as temp:
            path=Path(temp)/'settings.json';b=Backend(offline=True,settings=path)
            try:
                b.setChannel(0,'limit',13);b.setRule(0,'strength',12);b.editPoint(3,.37);b.saveWave('验证包络');key=b.selectedWave;b.setRule(0,'wave',key)
                other=Backend(offline=True,settings=path)
                try:self.assertEqual(other.channels[0]['limit'],13);self.assertEqual(other.rules[0]['wave'],key);self.assertAlmostEqual(other.waves[-1]['points'][3],.37)
                finally:other.shutdown()
            finally:b.shutdown()
    def test_config_cannot_raise_limits_above_range(self):
        from sinisistar_dglab.backend import Backend
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as temp:
            b=Backend(offline=True,settings=Path(temp)/'settings.json')
            try:
                b.setChannel(0,'limit',500);b.setRule(0,'duration',900);self.assertEqual(b.channels[0]['limit'],100);self.assertEqual(b.rules[0]['duration'],5)
            finally:b.shutdown()

if __name__=='__main__':unittest.main()
