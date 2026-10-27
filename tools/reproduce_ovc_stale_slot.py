"""Offline regression: slot_not_found must revoke a cached device's readiness.

Uses the production V4 receive handler. The sole safety-zero coroutine is
replaced by a no-op; no WebSocket service, APP connection or device write exists.
"""
import asyncio,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from sinisistar_dglab.v4 import V4ConnectionService
from sinisistar_dglab.mock_v4 import mock_device

async def main():
    service=V4ConnectionService(port=0,host='127.0.0.1',lan_ip='127.0.0.1')
    hub=service._hub;hub._loop=asyncio.get_running_loop()
    hub._clients['offline-fixture-app']=object()
    hub._devices['offline-fixture-app']={'old-slot':mock_device('OVC_1','old-slot')}
    for child in hub._channels.values():child._attach(hub)
    route=service.channel('ovc').route
    route.selected_client_id=route.target_id='offline-fixture-app';route.selected_slot_id='old-slot';route.device_type='OVC_1'
    route.connected=route._baseline_ready=route._auto_enabled=True
    async def no_device_write():pass
    route._safe_zero_async=no_device_write
    hub._publish_devices()
    before=dict(connected=service.channel('ovc').snapshot()['connected'],listed=bool(service.devices_snapshot()),ready=service.devices_snapshot()[0]['ready'])
    route._pending['missing-slot']=dict(client_id='offline-fixture-app',method='device.op',safety=False,slot_id='old-slot',generation=route._generation)
    hub._handle_app_data('offline-fixture-app',dict(t='resp',reqId='missing-slot',error='slot_not_found'))
    state=service.snapshot()['ovc']
    after=dict(connected=state['connected'],listed=bool(service.devices_snapshot()),ready=service.devices_snapshot()[0]['ready'],error=state['error'],output_enabled=route._auto_enabled)
    await asyncio.sleep(0)
    result=dict(before=before,after=after,fixed=not after['connected'] and not after['ready'] and not after['output_enabled'],
        network_service_started=False,hardware_connected=False,device_writes=0,
        limitation='Verifies local invalidation after a negative RPC. It does not reproduce firmware auto-off or prove an APP Bluetooth bug.')
    out=ROOT/'artifacts/ovc-stale-slot-research';out.mkdir(exist_ok=True)
    (out/'local-reproduction-after.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
    assert result['fixed']

if __name__=='__main__':asyncio.run(main())
