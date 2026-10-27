"""Sleeping BLE devices behind a live APP Socket; loopback only."""
import asyncio
from copy import deepcopy
import tempfile
import time
import unittest
from pathlib import Path

from PySide6.QtGui import QGuiApplication
from sinisistar_dglab.backend import Backend
from sinisistar_dglab.mock_v4 import MockV4App, mock_device
from sinisistar_dglab.telemetry import ROOT
from sinisistar_dglab.v4 import V4ConnectionService


class DelayedApp(MockV4App):
    def __init__(self):
        super().__init__()
        self.hold_catalog = self.hold_zero = False
        self.held = []

    async def send(self, data):
        request = next((r for r in reversed(self.records) if r.get('reqId') == data.get('reqId')), {})
        zero = (request.get('m') == 'device.op.clear' or
                (request.get('m') == 'device.op' and request['data'].get('t') == 7))
        if data.get('t') == 'resp' and ((self.hold_catalog and request.get('m') == 'devices.get') or
                                     (self.hold_zero and zero and request['data'].get('s') != 'coyote')):
            self.held.append(deepcopy(data))
        else:
            await super().send(data)

    async def release(self):
        packets, self.held = self.held, []
        for packet in packets:
            await super().send(packet)


class Recovery(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QGuiApplication.instance() or QGuiApplication([])

    async def asyncSetUp(self):
        asyncio.get_running_loop().set_debug(False)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp')
        self.b = Backend(offline=True, settings=Path(self.temp.name)/'settings.json')
        self.b._timer.stop()
        self.b.offline = False
        self.hub = V4ConnectionService(port=0, host='127.0.0.1', lan_ip='127.0.0.1')
        self.hub._hub._discovery_interval = .2
        self.hub.start()
        await self.until(lambda: self.hub.snapshot()['server_ready'])
        self.b._v4 = self.hub
        self.b._service = self.hub.channel('pulse')
        self.b._ovc_service = self.hub.channel('ovc')
        self.b._connection['pulse_backend'] = 'v4'
        self.app = DelayedApp()
        state = self.hub.snapshot()
        await self.app.connect(f"ws://127.0.0.1:{state['port']}/?tid={state['controller_id']}")
        await self.until(lambda: self.b._armed and self.b._ovc_armed)

    async def asyncTearDown(self):
        await asyncio.to_thread(self.hub.stop)
        await self.app.close()
        self.b._v4 = self.b._service = self.b._ovc_service = None
        self.b.shutdown()
        self.temp.cleanup()

    async def until(self, check, seconds=4):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if hasattr(self, 'b') and self.b._v4:
                self.b.tick()  # Includes the actual backend error/event consumer.
            if check():
                return
            await asyncio.sleep(.025)
        self.fail('Recovery did not settle')

    async def settle(self, seconds=.4):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.b.tick()
            await asyncio.sleep(.025)

    def ovc(self):
        return self.hub.channel('ovc').snapshot()

    async def silent_off(self):
        self.app.devices = [d for d in self.app.devices if d['type'] != 'OVC_1']
        await self.until(lambda: not self.ovc()['connected'])
        self.assertTrue(self.hub.snapshot()['app_connected'])
        self.assertTrue(self.hub.channel('pulse').snapshot()['connected'])
        self.assertTrue(self.b._ovc_armed)  # Intent retained, output guards closed.

    async def test_silent_poweroff_is_polled_and_new_slot_is_zeroed_before_recovery(self):
        await self.silent_off()
        since = time.monotonic()
        device = mock_device('OVC_1', 'ovc-reconnected')
        device['props'].update(intensityA=150, intensityB=120)
        self.app.hold_zero = True
        self.app.devices.append(device)
        await self.until(lambda: bool(self.app.held))
        self.assertFalse(self.ovc()['connected'])
        self.assertFalse(self.hub.channel('ovc').set_output_permission(True))
        self.app.hold_zero = False
        await self.app.release()
        await self.until(lambda: self.ovc()['connected'] and self.b._ovc_armed)
        self.assertEqual(self.ovc()['selected_slot_id'], 'ovc-reconnected')
        self.assertEqual((self.ovc()['strength_a'], self.ovc()['strength_b']), (0, 0))
        self.assertTrue(any(r['at'] >= since and r['m'] == 'device.op.clear' and
                            r['data']['s'] == 'ovc-reconnected' for r in self.app.records))
        self.assertFalse(self.app.pulses('ovc-reconnected'))  # No old frame replay.

    async def test_same_slot_ble_disconnect_keeps_identity_and_requires_new_zero(self):
        device = self.app.devices[1]
        device['props']['connectState'] = 'disconnected'
        device['slotState']['hasDevice'] = False
        await self.until(lambda: not self.ovc()['connected'])
        self.assertEqual(self.ovc()['selected_slot_id'], 'ovc')
        self.app.hold_zero = True
        device['props'].update(connectState='connected', intensityA=100)
        device['slotState']['hasDevice'] = True
        await self.until(lambda: bool(self.app.held))
        self.assertFalse(self.ovc()['connected'])
        self.app.hold_zero = False
        await self.app.release()
        await self.until(lambda: self.ovc()['connected'] and self.b._ovc_armed)
        self.assertEqual(self.ovc()['error'], '')

    async def test_slot_not_found_revokes_cached_ready_immediately_then_recovers(self):
        self.app.hold_catalog = True
        self.app.devices.pop()
        route = self.hub.channel('ovc').route
        # Inject a matching APP response through the real receive handler,
        # on its Socket loop. No physical device exists in this test.
        def reject():
            route._pending['gone'] = dict(client_id=self.app.client_id, method='device.op',
                safety=False, slot_id='ovc', generation=route._generation)
            self.hub._hub._handle_app_data(self.app.client_id, dict(t='resp', reqId='gone', error='slot_not_found'))
        route._loop.call_soon_threadsafe(reject)
        await self.until(lambda: not self.ovc()['connected'])
        self.assertFalse(next(d for d in self.hub.devices_snapshot() if d['slotId'] == 'ovc')['ready'])
        self.assertTrue(self.b._ovc_armed)
        self.app.devices.append(mock_device('OVC_1', 'ovc'))
        self.app.hold_catalog = False
        # Discard captured old reads; timeout schedules a new authoritative read.
        await self.app.release()
        await self.until(lambda: self.ovc()['connected'] and self.b._ovc_armed)
        self.assertEqual(self.ovc()['error'], '')

    async def test_manual_pause_is_preserved_for_same_and_new_slots(self):
        await self.silent_off()
        self.b.toggleOvcArm()
        self.assertFalse(self.b._ovc_armed)
        self.app.devices.append(mock_device('OVC_1', 'ovc-new'))
        await self.until(lambda: any(d['slotId'] == 'ovc-new' for d in self.hub.devices_snapshot()))
        await self.settle()
        self.assertFalse(self.b._ovc_armed)
        self.assertFalse(self.app.pulses('ovc-new'))

    async def test_emergency_is_not_undone_by_reconnect_or_unlock(self):
        await self.silent_off()
        self.b.emergencyStop()
        self.app.devices.append(mock_device('OVC_1', 'ovc-new'))
        await self.until(lambda: any(d['slotId'] == 'ovc-new' for d in self.hub.devices_snapshot()))
        self.b.unlock()
        await self.settle()
        self.assertFalse(self.b._ovc_armed)
        self.assertFalse(self.b._armed)
        self.assertFalse(self.app.pulses('ovc-new'))

    async def test_discovery_timeout_marks_status_unknown_with_socket_still_online(self):
        self.app.hold_catalog = True
        await self.until(lambda: not self.ovc()['connected'])
        self.assertTrue(self.hub.snapshot()['app_connected'])
        self.assertFalse(any(d['ready'] for d in self.hub.devices_snapshot()))
        self.app.hold_catalog = False
        await self.app.release()
        await self.until(lambda: self.ovc()['connected'], seconds=7)

    async def test_reconnect_zero_rejection_never_rearms_or_spins(self):
        await self.silent_off()
        self.app.reject_slot = 'ovc-new'
        self.app.devices.append(mock_device('OVC_1', 'ovc-new'))
        await self.until(lambda: self.ovc()['readiness_failed'])
        self.assertFalse(self.ovc()['connected'])
        self.assertFalse(self.b._ovc_armed)
        before = len([r for r in self.app.records if r['m'] == 'device.op'])
        await self.settle(.7)
        self.assertEqual(before, len([r for r in self.app.records if r['m'] == 'device.op']))
        self.app.reject_slot = ''
        self.b.retryDevice('ovc')
        await self.until(lambda: self.ovc()['connected'] and self.b._ovc_armed)

    async def test_delayed_cancel_from_old_generation_cannot_erase_recovered_ovc(self):
        route = self.hub.channel('ovc').route
        def stale_cancel():
            route._pending['late'] = dict(client_id=self.app.client_id, method='device.op',
                safety=False, slot_id='ovc', generation=route._generation-1, action_type=0, channel=0)
            self.hub._hub._handle_app_data(self.app.client_id, dict(t='resp', reqId='late',
                result=dict(reason='cancelled', slotId='ovc', type=0, channel=0)))
        route._loop.call_soon_threadsafe(stale_cancel)
        await self.settle()
        self.assertTrue(self.ovc()['connected'])
        self.assertTrue(self.b._ovc_armed)
        self.assertEqual(self.ovc()['selected_slot_id'], 'ovc')

    async def test_pre_failure_catalog_reply_cannot_restore_cached_ready(self):
        self.app.hold_catalog = True
        await self.until(lambda: bool(self.app.held))
        route = self.hub.channel('ovc').route
        def reject():
            route._pending['gone'] = dict(client_id=self.app.client_id, method='device.op',
                safety=False, slot_id='ovc', generation=route._generation)
            self.hub._hub._handle_app_data(self.app.client_id, dict(t='resp', reqId='gone', error='slot_not_found'))
        route._loop.call_soon_threadsafe(reject)
        await self.until(lambda: not self.ovc()['connected'])
        await self.app.release()  # Reply was constructed before slot_not_found.
        await self.settle(.15)
        self.assertFalse(self.ovc()['connected'])
        self.app.hold_catalog = False
        await self.app.release()
        await self.until(lambda: self.ovc()['connected'])

    async def test_output_ack_timeout_revokes_ready_without_stopping_the_other_role(self):
        self.app.hold_catalog = True
        route = self.hub.channel('ovc').route
        def expire():
            route._pending['timeout'] = dict(client_id=self.app.client_id, method='device.op',
                safety=False, slot_id='ovc', generation=route._generation, deadline=time.monotonic()-1)
            self.hub.channel('ovc').wake_output()
        route._loop.call_soon_threadsafe(expire)
        await self.until(lambda: not self.ovc()['connected'])
        self.assertTrue(self.hub.channel('pulse').snapshot()['connected'])
        self.assertEqual(self.ovc()['channel_a_reason'], 'device-unresponsive')
        self.assertTrue(self.b._ovc_armed)
        self.app.hold_catalog = False
        await self.app.release()
        await self.until(lambda: self.ovc()['connected'])

    async def test_current_cancel_triggers_resync_but_never_replays_old_output(self):
        self.app.hold_catalog = True
        route = self.hub.channel('ovc').route
        def cancel():
            route._pending['cancel'] = dict(client_id=self.app.client_id, method='device.op',
                safety=False, slot_id='ovc', generation=route._generation, action_type=0, channel=0)
            self.hub._hub._handle_app_data(self.app.client_id, dict(t='resp', reqId='cancel',
                result=dict(reason='cancelled', slotId='ovc', type=0, channel=0)))
        route._loop.call_soon_threadsafe(cancel)
        await self.until(lambda: not self.ovc()['connected'])
        self.assertTrue(self.b._ovc_armed)
        self.app.hold_catalog = False
        await self.app.release()
        await self.until(lambda: self.ovc()['connected'])
        self.assertFalse(self.app.pulses('ovc'))


if __name__ == '__main__':
    unittest.main()
