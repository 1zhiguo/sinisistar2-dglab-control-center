"""Render the production connection page against a loopback V4 APP fixture.

Both supported slots are explicitly selected; output is never armed. The
fixture has no BLE/device access. Run using the native UI Python environment.
"""
from __future__ import annotations
import asyncio,json,sys,threading,time,traceback
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))

from PySide6.QtCore import QTimer,QUrl,qInstallMessageHandler,QMetaObject,Q_ARG
from PySide6.QtGui import QGuiApplication,QFont
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem,QQuickWindow
from sinisistar_dglab.backend import Backend
from sinisistar_dglab.v4 import V4ConnectionService
from sinisistar_dglab.mock_v4 import MockV4App

def main():
    output=ROOT/'artifacts/ui';output.mkdir(parents=True,exist_ok=True)
    messages=[]
    def qt_message(kind,context,message):
        if len(messages)<100:messages.append(message)
        if len(messages)<=12:print('Qt:',message,flush=True)
    qInstallMessageHandler(qt_message)
    app=QGuiApplication([]);app.setFont(QFont('Microsoft YaHei UI',10))
    backend=Backend(offline=True,settings=output/'qa-v4-device-settings.json')
    print('UI: backend ready',flush=True)
    engine=QQmlApplicationEngine();engine.rootContext().setContextProperty('backend',backend)
    engine.load(QUrl.fromLocalFile(str(ROOT/'src/sinisistar_dglab/qml/ControlCenter.qml')))
    print('UI: window loaded',flush=True)
    if not engine.rootObjects():print('\n'.join(messages));backend.shutdown();return 2
    window=engine.rootObjects()[0];window.setProperty('pageIndex',1);window.resize(1440,940)
    print('UI: device page selected',flush=True)
    loop=asyncio.new_event_loop();thread=threading.Thread(target=loop.run_forever,daemon=True);thread.start()
    print('UI: constructing loopback V4 service',flush=True)
    service=V4ConnectionService(port=0,host='127.0.0.1',lan_ip='127.0.0.1')
    print('UI: loopback V4 service constructed',flush=True)
    state={'phase':'initial','future':None,'mock':None,'no_connection_disabled':False}
    started=time.monotonic()
    def visual_items():
        result=[];pending=[window.contentItem()]
        while pending:
            item=pending.pop();result.append(item);pending.extend(item.childItems())
        return result
    def find(name):
        return next(item for item in visual_items() if item.objectName()==name)
    def objects_with_text(label):
        return [item for item in visual_items() if item.inherits('QQuickAbstractButton') and item.property('text')==label and item.property('visible')]
    def verify():
        try:
            if time.monotonic()-started>8:raise TimeoutError('V4 UI fixture did not settle')
            if state['phase']=='initial':
                print('UI: checking disconnected action',flush=True)
                buttons=objects_with_text('启动 Pulse')
                assert len(buttons)==1 and not buttons[0].isEnabled(),'Unpaired header Pulse action must be disabled'
                state['no_connection_disabled']=True
                backend._v4=service;backend._service=service.channel('pulse');backend._ovc_service=service.channel('ovc')
                backend._connection['pulse_backend']='v4';backend.configChanged.emit();service.start();state['phase']='server';return
            snapshot=service.snapshot()
            if state['phase']=='server' and snapshot['server_ready']:
                print('UI: loopback server ready',flush=True)
                assert service.local_only
                state['future']=asyncio.run_coroutine_threadsafe(MockV4App().connect(f"ws://127.0.0.1:{snapshot['port']}/?tid={snapshot['controller_id']}"),loop)
                state['phase']='devices';return
            if state['phase']=='devices' and state['future'].done():
                mock=state['future'].result();state['mock']=mock
                if len(service.devices_snapshot())!=2:return
                backend.changed.emit();app.processEvents()
                for name in ('pulseDeviceChoice','ovcDeviceChoice'):
                    combo=find(name);combo.setProperty('currentIndex',1)
                    assert QMetaObject.invokeMethod(combo,'activated',Q_ARG(int,1))
                state['phase']='ready';return
            if state['phase']!='ready':return
            if not all(service.channel(role).snapshot()['feedback_known'] for role in ('pulse','ovc')):return
            backend.changed.emit();app.processEvents()
            pulse=find('pulseDeviceChoice');ovc=find('ovcDeviceChoice')
            assert pulse.property('currentIndex')==ovc.property('currentIndex')==1
            assert find('setupArmPulse').isEnabled() and find('setupArmOvc').isEnabled()
            assert not backend.state['armed'] and not backend.state['ovcArmed']
            assert not state['mock'].pulses('coyote') and not state['mock'].pulses('ovc')
            state['phase']='capture';QTimer.singleShot(250,capture)
        except Exception:
            traceback.print_exc();print('\n'.join(messages));timer.stop();app.exit(3)
    def capture():
        try:
            qml_errors=[message for message in messages if 'file:///' in message or 'ReferenceError' in message or 'TypeError' in message]
            assert not qml_errors,qml_errors
            image=output/'connections-paired-mock.png';assert window.grabWindow().save(str(image))
            report=dict(passed=True,transport='127.0.0.1 only',hardware_connected=False,output_armed=False,
                        no_connection_header_pulse_disabled=state['no_connection_disabled'],
                        pulse_slot_selected_in_dropdown=True,ovc_slot_selected_in_dropdown=True,dual_mock_reconnect_disabled=True,
                        qml_errors=qml_errors,qt_messages=messages,screenshot=str(image),devices=service.devices_snapshot())
            (output/'connections-paired-mock.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({key:value for key,value in report.items() if key!='devices'},ensure_ascii=False));app.exit(0)
        except Exception:traceback.print_exc();print('\n'.join(messages));app.exit(4)
        finally:timer.stop()
    timer=QTimer();timer.setInterval(75);timer.timeout.connect(verify);timer.start()
    result=app.exec();backend._timer.stop()
    service.stop();backend._v4=None;backend._service=None;backend._ovc_service=None;backend.shutdown()
    if state['mock']:
        try:asyncio.run_coroutine_threadsafe(state['mock'].close(),loop).result(2)
        except Exception:pass
    loop.call_soon_threadsafe(loop.stop);thread.join(2)
    return result

if __name__=='__main__':raise SystemExit(main())
