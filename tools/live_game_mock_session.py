"""Authorized live game -> production Backend -> loopback V4 APP audit.

Uses an independent test profile and never starts a LAN/BLE connection.
Explicit --auto-arm authorizes only the fixture created in this process.
"""
from __future__ import annotations
import argparse,asyncio,hashlib,json,sys,threading,time,traceback
from collections import Counter
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))

def test_profile(source,*,gallery=False):
    from sinisistar_dglab.simulation import sanitize_profile
    # Mirror the user's current policies; isolate settings and the transport only.
    data=deepcopy(source);p=sanitize_profile(data.get('simulation',{}))
    # --gallery selects the editor only. Rules, filters, A/B routing, Space,
    # queues, ramp settings and all limits remain exactly the user's choices.
    data.update(simulation=p,connections=dict(data.get('connections',{}),pulse_backend='v4',lan_ip='127.0.0.1',auto_enable=False))
    return data

def policy_hash(data):
    fields=('simulation','rules','channels','custom_waves','custom_vibration_waves','ovc_limits')
    policy={k:data.get(k) for k in fields}
    return hashlib.sha256(json.dumps(policy,sort_keys=True,ensure_ascii=False).encode('utf-8')).hexdigest()

def apply_user_policy(backend,data):
    """Refresh the local fixture without replacing its observer or transport."""
    prepared=test_profile(data);prepared['game_directory']=str(backend._game_directory)
    backend._waves=[w for w in backend._waves if not w['key'].startswith('custom_')]
    backend._vibration_custom=[]
    backend._apply(prepared)
    backend._simulation_changed()

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--minutes',type=int,default=0,help='0 records until the test window closes or stop-session is created');parser.add_argument('--auto-arm',action='store_true');parser.add_argument('--page',type=int,default=1)
    parser.add_argument('--gallery',action='store_true',help='Open gallery settings without overriding the user policy')
    parser.add_argument('--follow-presets',action='store_true',help='Follow saved user policy changes in this loopback-only fixture')
    parser.add_argument('--output-dir',type=Path,help='Separate audit folder; must not contain an earlier session')
    args=parser.parse_args()
    from PySide6.QtCore import QTimer,QUrl,qInstallMessageHandler
    from PySide6.QtGui import QGuiApplication,QFont
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuick import QQuickItem,QQuickWindow
    from sinisistar_dglab.backend import Backend
    from sinisistar_dglab.v4 import V4ConnectionService
    from sinisistar_dglab.mock_v4 import MockV4App
    from sinisistar_dglab.hud_window import HudWindowController
    output=args.output_dir or ROOT/'artifacts/live-game-mock'
    if args.output_dir and any((output/name).exists() for name in ('pipeline.jsonl','commands.jsonl','summary.json')):raise ValueError('Choose a new output directory to preserve previous records')
    output.mkdir(parents=True,exist_ok=True)
    stop=output/'stop-session';stop.unlink(missing_ok=True)
    source_settings=ROOT/'artifacts/settings.json';original=source_settings.read_bytes()
    last_policy=policy_hash(json.loads(original));preset_syncs=0;last_policy_check=0.
    settings=output/'test-settings.json';settings.write_text(json.dumps(test_profile(json.loads(original),gallery=args.gallery),ensure_ascii=False,indent=2),encoding='utf-8')
    app=QGuiApplication([]);app.setFont(QFont('Microsoft YaHei UI',10));messages=[]
    qInstallMessageHandler(lambda k,c,m:messages.append(m))
    b=Backend(offline=False,settings=settings)
    engine=QQmlApplicationEngine();engine.rootContext().setContextProperty('backend',b)
    engine.load(QUrl.fromLocalFile(str(ROOT/'src/sinisistar_dglab/qml/ControlCenter.qml')))
    assert engine.rootObjects(),messages
    window=engine.rootObjects()[0];window.setTitle('SiNiSistar2 · 本机模拟 APP · 使用当前预设');window.setProperty('pageIndex',7 if args.gallery else max(0,min(8,args.page)))
    def select_gallery_page():
        if not args.gallery:return
        pending=[window.contentItem()]
        while pending:
            item=pending.pop();pending.extend(item.childItems())
            if item.objectName()=='cgFeedbackPage':item.setProperty('scope','gallery');return
    QTimer.singleShot(100,select_gallery_page)
    engine.load(QUrl.fromLocalFile(str(ROOT/'src/sinisistar_dglab/qml/Monitor.qml')))
    b._hud=True;hud=HudWindowController(b,engine.rootObjects()[1]);b.hudChanged.emit()
    hub=V4ConnectionService(port=0,host='127.0.0.1',lan_ip='127.0.0.1');assert hub.local_only
    b._v4=hub;b._service=hub.channel('pulse');b._ovc_service=hub.channel('ovc');b._connection['pulse_backend']='v4'
    loop=asyncio.new_event_loop();thread=threading.Thread(target=loop.run_forever,daemon=True);thread.start();hub.start()
    state={'phase':'server','future':None,'mock':None,'cursor':0,'records':0,'source_frames':0,'ready_at':None,'stopping_at':None,'last_active':0.,'error':''}
    began=time.monotonic();start_utc=datetime.now(timezone.utc).isoformat();counts=Counter();last_source=None;last_save=0.
    snapshots=(output/'pipeline.jsonl').open('w',encoding='utf-8');commands=(output/'commands.jsonl').open('w',encoding='utf-8')
    def flush_commands():
        mock=state['mock']
        if mock is None:return
        rows=list(mock.records)
        for row in rows[state['cursor']:]:
            commands.write(json.dumps(row,ensure_ascii=False)+'\n')
            data=row.get('data') or {}
            if row.get('m')=='device.op':counts[(data.get('s','?'),'B' if data.get('c')==1 else 'A',str(data.get('t')))]+=1
        state['cursor']=len(rows);commands.flush()
    def summary(complete=False):
        s=b.state
        report=dict(started_utc=start_utc,complete=complete,phase=state['phase'],error=state['error'],elapsed_seconds=round(time.monotonic()-began,1),
            transport='127.0.0.1 only',port=hub.snapshot()['port'],hardware_connected=False,original_settings_unchanged=(ROOT/'artifacts/settings.json').read_bytes()==original,
            profile=str(settings),gallery_test=args.gallery,gallery_policy=b.gallerySettings if args.gallery else None,
            policy_mode='saved user presets',follow_presets=args.follow_presets,preset_syncs=preset_syncs,source_policy_hash=last_policy,
            source_profile_written_by_test=False,recording_limit_seconds=args.minutes*60 if args.minutes>0 else None,
            source_frames=state['source_frames'],snapshots=state['records'],command_count=state['cursor'],
            command_counts={'/'.join(k):v for k,v in counts.items()},source=b._live,armed=s['armed'],ovc_armed=s['ovcArmed'],
            pulse_outputs=s['outputChannels'],ovc_outputs=s['ovcChannels'],pulse_reason=s['outputReason'],ovc_reason=s['ovcReason'],
            event_counts=b._monitor.counts,qml_errors=[m for m in messages if 'file:///' in m or 'ReferenceError' in m or 'TypeError' in m])
        target=output/'summary.json';temp=target.with_suffix('.tmp');temp.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(target)
    def stop_output():
        if state['phase']=='stopping':return
        b._armed=False;b._ovc_armed=False;b._reset_output();state['phase']='stopping';state['stopping_at']=time.monotonic()
    def tick():
        nonlocal last_source,last_save,last_policy,last_policy_check,preset_syncs
        try:
            now=time.monotonic();h=hub.snapshot()
            assert hub.local_only and b._service is hub.channel('pulse') and b._ovc_service is hub.channel('ovc'),'Fixture routing changed; ending test'
            if args.follow_presets and state['phase']=='capture' and now-last_policy_check>=.5:
                last_policy_check=now
                try:
                    current=json.loads(source_settings.read_text(encoding='utf-8'));digest=policy_hash(current)
                except (OSError,ValueError):current=None;digest=last_policy
                if digest!=last_policy:
                    armed=(b._armed,b._ovc_armed);apply_user_policy(b,current)
                    if args.auto_arm:
                        if armed[0]:b.toggleArm()
                        if armed[1]:b.toggleOvcArm()
                    last_policy=digest;preset_syncs+=1
                    with (output/'preset-history.jsonl').open('a',encoding='utf-8') as f:
                        f.write(json.dumps(dict(utc=datetime.now(timezone.utc).isoformat(),hash=digest,simulation=b._sim_profile,channels=b.channels,ovc_limits=b.ovcLimits),ensure_ascii=False)+'\n')
                    b.toast.emit('已同步你保存的预设 · 仅本机模拟 · 新策略从头开始')
            if state['phase']=='server' and h['server_ready']:
                state['future']=asyncio.run_coroutine_threadsafe(MockV4App().connect(f"ws://127.0.0.1:{h['port']}/?tid={h['controller_id']}"),loop);state['phase']='connect'
            if state['phase']=='connect' and state['future'].done():
                state['mock']=state['future'].result()
                if len(hub.devices_snapshot())==2:
                    b.selectV4Device('pulse',state['mock'].client_id,'coyote');b.selectV4Device('ovc',state['mock'].client_id,'ovc');state['phase']='baseline'
            if state['phase']=='baseline' and all(hub.channel(r).snapshot()['feedback_known'] for r in ('pulse','ovc')):
                assert {d['slotId'] for d in hub.devices_snapshot()}=={'coyote','ovc'}
                if args.auto_arm:
                    if not b._armed:b.toggleArm()
                    if not b._ovc_armed:b.toggleOvcArm()
                state.update(phase='capture',ready_at=now)
                (output/'ready.json').write_text(json.dumps(dict(ready=True,started_utc=start_utc,port=h['port'],local_only=True,
                    death_strengths=b.quickPolicy['death'],limits=dict(pulseA=b.channels[0]['limit'],pulseB=b.channels[1]['limit'],ovcA=b.ovcLimits['A'],ovcB=b.ovcLimits['B'])),indent=2),encoding='utf-8')
                b.toast.emit('仅本机模拟 APP · 真实游戏事件采集中 · 原策略未修改')
                select_gallery_page()
                print('Loopback Mock APP paired; live game output audit ready',flush=True)
            if state['ready_at'] is None and now-began>20:raise TimeoutError('Mock APP pairing did not become ready')
            if state['phase'] in ('capture','stopping'):
                s=b.state;source=b._live;identity=(source.get('session'),source.get('sample_id'))
                if identity!=last_source:last_source=identity;state['source_frames']+=1
                if s['armed'] or s['ovcArmed']:state['last_active']=now
                # Keep game evidence even while output is paused.
                row=dict(at=now,utc=datetime.now(timezone.utc).isoformat(),source=source,gallery=s['galleryPlayback'],pulse=b.pulsePlan,ovc=b.ovcPlan,
                         pulse_outputs=s['outputChannels'],ovc_outputs=s['ovcChannels'],armed=s['armed'],ovc_armed=s['ovcArmed'])
                snapshots.write(json.dumps(row,ensure_ascii=False)+'\n');snapshots.flush();state['records']+=1
                flush_commands()
                if stop.exists() or (args.minutes>0 and now-began>=max(1,min(30,args.minutes))*60):stop_output()
                if state['phase']=='stopping' and now-state['stopping_at']>.7:app.exit(0)
            if now-last_save>=1:summary();last_save=now
        except Exception:
            state['error']=traceback.format_exc();stop_output()
            if time.monotonic()-state['stopping_at']>.7:app.exit(1)
    b.exitRequested.connect(lambda:app.exit(0));app.aboutToQuit.connect(stop_output)
    timer=QTimer();timer.setInterval(100);timer.timeout.connect(tick);timer.start()
    result=app.exec();timer.stop();hud.shutdown();b.shutdown()
    if state['mock']:
        try:asyncio.run_coroutine_threadsafe(state['mock'].close(),loop).result(3)
        except Exception:pass
    flush_commands();summary(True);snapshots.close();commands.close();loop.call_soon_threadsafe(loop.stop);thread.join(2)
    print(json.dumps(dict(complete=True,error=state['error'],commands=state['cursor'])),flush=True)
    return result or (1 if state['error'] else 0)

if __name__=='__main__':raise SystemExit(main())
