import asyncio,json,socket,tempfile,time,unittest
from pathlib import Path
from PySide6.QtGui import QGuiApplication
from sinisistar_dglab.backend import Backend,ROOT
from test_v4_backend import Game
from test_gallery_output import state

class MainMockSession(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):cls.qt=QGuiApplication.instance() or QGuiApplication([])
    async def test_same_window_uses_saved_policy_records_packets_and_closes_cleanly(self):
        asyncio.get_running_loop().set_debug(False)
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp') as folder:
            b=Backend(offline=True,settings=Path(folder)/'settings.json');b._timer.stop()
            b._observer=Game();b._observer.s=state(time.monotonic());b.offline=False
            g=b._sim_profile['gallery'];g['rule'].update(enabled=True,pulse_channel='AB',vibration_channel='AB')
            g['rule'].update(pulse_strength_a=8,pulse_strength_b=12,pulse_start_strength_a=8,pulse_start_strength_b=12,
                vibration_strength_a=40,vibration_strength_b=60,vibration_start_strength_a=40,vibration_start_strength_b=60)
            connection=dict(b._connection);b.save();profile=json.loads(b.settings.read_text(encoding='utf-8'))['simulation']
            async def until(fn):
                end=time.monotonic()+4
                while time.monotonic()<end:
                    b.tick();await asyncio.sleep(.04)
                    if fn():return
                self.fail('Main-window mock did not settle: '+str(b.mockValidation))
            try:
                b._sim_running=True;b.startMockBoth();session=b._mock_session;hub=b._v4
                self.assertFalse(b._sim_running);self.assertTrue(hub.local_only)
                await until(lambda:all(b.mockValidation.get(k,0)>0 for k in ('pulsesA','pulsesB','ovcPulsesA','ovcPulsesB')))
                self.assertEqual(b._sim_profile,profile)
                b.save();self.assertEqual(json.loads(b.settings.read_text(encoding='utf-8'))['connections'],connection)
                self.assertEqual(json.loads((session.directory/'preset.json').read_text(encoding='utf-8'))['simulation'],profile)
                b.setCgOption('gallery/pulse:A','ramp_seconds',20)
                self.assertFalse(b._armed or b._ovc_armed)
                b.resumeMockBoth();await until(lambda:b._armed and b._ovc_armed)
                port=hub.snapshot()['port'];b.stopMockBoth()
                self.assertEqual(b._connection,connection);self.assertIsNone(b._mock_session)
                report=json.loads((session.directory/'summary.json').read_text(encoding='utf-8'))
                self.assertTrue(report['complete']);self.assertFalse(report['hardware_connected']);self.assertFalse(report['error'])
                commands=[json.loads(x)for x in (session.directory/'commands.jsonl').read_text(encoding='utf-8').splitlines()]
                for slot in ('coyote','ovc'):
                    for channel in (0,1):
                        ops=[x['data']for x in commands if x.get('m')=='device.op' and x['data']['s']==slot and x['data']['c']==channel]
                        self.assertEqual(ops[-1]['t'],7);self.assertEqual(ops[-1]['v'],0)
                with socket.socket()as sock:sock.bind(('127.0.0.1',port))
                b.startMockBoth();closing=b._mock_session
                await until(lambda:b.mockValidation.get('pulsesB',0)>0)
                closing_port=b._v4.snapshot()['port'];b.shutdown()
                final=json.loads((closing.directory/'summary.json').read_text(encoding='utf-8'))
                self.assertTrue(final['complete']);self.assertFalse(final['error'])
                self.assertFalse(closing._thread.is_alive())
                with socket.socket()as sock:sock.bind(('127.0.0.1',closing_port))
            finally:b.shutdown()
