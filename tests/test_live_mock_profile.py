"""The live mock mirrors user policies; it only substitutes the transport."""
from copy import deepcopy
from pathlib import Path
import runpy,tempfile,unittest
from PySide6.QtGui import QGuiApplication
from sinisistar_dglab.simulation import initial_profile,sanitize_profile
from sinisistar_dglab.backend import Backend

ROOT=Path(__file__).resolve().parents[1]
HELPERS=runpy.run_path(str(ROOT/'tools/live_game_mock_session.py'))

class LiveMockProfile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.qt=QGuiApplication.instance() or QGuiApplication([])
    def source(self):
        p=initial_profile();p['gallery']['rule'].update(enabled=True,vibration_channel='A')
        p['gallery']['pause_on_stop']=False;p['channel_feedback']['vibration']['B']='damage'
        p['gallery']['routes']['pulse']['A'].update(mode='fixed',wave='custom_test',ramp_seconds=17)
        return dict(simulation=p,channels=[dict(key='A',limit=37,frequency=31),dict(key='B',limit=42,frequency=26)],
            ovc_limits=dict(A=30,B=60),connections=dict(pulse_backend='v3',auto_enable=True,lan_ip='192.168.1.2'),
            custom_waves=[dict(key='custom_test',name='Saved wave',points=[.2]*16)])
    def test_gallery_mode_preserves_every_logical_policy_and_source(self):
        source=self.source();original=deepcopy(source);p=HELPERS['test_profile'](source,gallery=True)
        self.assertEqual(source,original);self.assertEqual(p['simulation'],sanitize_profile(source['simulation']))
        for key in ('channels','ovc_limits','custom_waves'):self.assertEqual(p[key],source[key])
        self.assertEqual(p['connections']['lan_ip'],'127.0.0.1');self.assertFalse(p['connections']['auto_enable'])
        self.assertFalse(p['simulation']['gallery']['pause_on_stop'])
        self.assertEqual(p['simulation']['gallery']['rule']['vibration_channel'],'A')
    def test_sync_replaces_custom_wave_keeps_services_and_disarms_before_restart(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp') as folder:
            b=Backend(offline=True,settings=Path(folder)/'settings.json');b._timer.stop()
            try:
                source=self.source();before=deepcopy(source)
                b._armed=b._ovc_armed=True;HELPERS['apply_user_policy'](b,source)
                self.assertFalse(b._armed or b._ovc_armed);self.assertEqual(source,before)
                self.assertEqual(b._sim_profile,sanitize_profile(source['simulation']))
                self.assertEqual(b.channels[0]['limit'],37);self.assertEqual(b.ovcLimits['A'],30)
                source['custom_waves'][0]['points']=[.8]*16
                HELPERS['apply_user_policy'](b,source)
                waves=[w for w in b.waves if w['key']=='custom_test']
                self.assertEqual(len(waves),1);self.assertEqual(waves[0]['points'],[.8]*16)
                self.assertIsNone(b._v4);self.assertIsNone(b._service);self.assertIsNone(b._ovc_service)
            finally:b.shutdown()
    def test_sync_watches_policies_and_ignores_connection_only_changes(self):
        source=self.source();digest=HELPERS['policy_hash'](source)
        source['connections']['lan_ip']='127.0.0.1'
        self.assertEqual(digest,HELPERS['policy_hash'](source))
        source['simulation']['gallery']['rule']['pulse_strength_a']=19
        self.assertNotEqual(digest,HELPERS['policy_hash'](source))
