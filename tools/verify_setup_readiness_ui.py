"""Readiness decoration matrix using inert display fixtures, no transports."""
from pathlib import Path
import json,sys,tempfile,traceback
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from PySide6.QtCore import QTimer,QUrl,QMetaObject,qInstallMessageHandler
from PySide6.QtGui import QGuiApplication,QFont
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem,QQuickWindow
from PySide6.QtTest import QTest
from sinisistar_dglab.backend import Backend

class DisplayRoute:
    def __init__(self,slot):self.connected=False;self.slot=slot;self.code='';self.error=''
    def snapshot(self):
        return dict(server_ready=True,connected=self.connected,feedback_known=self.connected,
                    selected_client_id='display-fixture',selected_slot_id=self.slot,
                    lan_ip='192.0.2.1',port=9998,local_only=False,protocol='v4',limit_a=200 if self.slot=='ovc' else 100,
                    limit_b=200 if self.slot=='ovc' else 100,channel_a_reason=self.code,channel_b_reason=self.code,error=self.error)

class DisplayHub:
    def __init__(self,pulse,ovc):
        self.pulse=pulse;self.ovc=ovc;self.paired=False;self.blocked=False
    def devices_snapshot(self):
        return [dict(clientId='display-fixture',slotId=slot,type=kind,name=label,
                     channelAReason='bluetooth-not-connected' if self.blocked else '',
                     channelBReason='bluetooth-not-connected' if self.blocked else '')
                for slot,kind,label in [('coyote','COYOTE_030','模拟郊狼'),('ovc','OVC_1','模拟负鼠')]]
    def snapshot(self):
        return dict(server_ready=True,app_connected=self.paired,local_only=False,
                    lan_ip='192.0.2.1',port=9998,qr_url='',
                    coyote=self.pulse.snapshot(),ovc=self.ovc.snapshot())

def main():
    app=QGuiApplication([]);app.setFont(QFont('Microsoft YaHei UI',10));messages=[]
    qInstallMessageHandler(lambda k,c,m:messages.append(m))
    temp=tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp')
    b=Backend(offline=True,settings=Path(temp.name)/'settings.json');b._timer.stop()
    b._game_candidates=[dict(path='display-fixture',supported=True)]
    b._install_state.update(valid=True,payloadReady=True,installedVersion='0.3.0',selectedPath='显示验证 · 未操作真实游戏目录')
    pulse=DisplayRoute('coyote');ovc=DisplayRoute('ovc');hub=DisplayHub(pulse,ovc)
    b._service=pulse;b._ovc_service=ovc;b._v4=hub;b._connection['pulse_backend']='v4'
    engine=QQmlApplicationEngine();engine.rootContext().setContextProperty('backend',b)
    engine.load(QUrl.fromLocalFile(str(ROOT/'src/sinisistar_dglab/qml/ControlCenter.qml')))
    w=engine.rootObjects()[0];w.setProperty('pageIndex',1)
    report={};names=['setupGameReadyCard','setupConnectionReadyCard','setupPulseReadyCard','setupOvcReadyCard']
    def find(name):
        pending=[w.contentItem()]
        while pending:
            item=pending.pop()
            if item.objectName()==name:return item
            pending.extend(item.childItems())
        raise LookupError(name)
    def check(expected):
        b.installChanged.emit();b.configChanged.emit();b.changed.emit();app.processEvents()
        actual=[bool(find(name).property('ready')) for name in names]
        assert actual==expected,(actual,expected)
    def verify():
        try:
            check([False,False,False,False])
            b._install_state['gameRunning']=True;check([True,False,False,False])
            b._install_state.update(gameRunning=False,pluginOnline=True);check([True,False,False,False])
            b._install_state['pluginOnline']=False;check([False,False,False,False])
            hub.paired=True;check([False,True,False,False])
            b._armed=True;check([False,True,False,False])
            pulse.connected=True;check([False,True,True,False])
            ovc.connected=True;check([False,True,True,False])
            b._ovc_armed=True;b._install_state['gameRunning']=True;check([True,True,True,True])
            assert all(find(name).property('readyColor').name()=='#c3a777' for name in names)
            QTest.qWait(300)
            assert w.grabWindow().save(str(ROOT/'artifacts/ui/setup-gothic-ready-fixture.png'))
            b._pulse_channels={'A':False,'B':False};check([True,True,False,True])
            b._pulse_channels={'A':True,'B':True};hub.blocked=True;check([True,True,False,False])
            hub.blocked=False;b._emergency=True;check([True,True,False,False])
            b._emergency=False;b._armed=False;check([True,True,False,True])
            pulse.connected=False;ovc.connected=False;hub.paired=False;check([True,False,False,False])
            b._connection['pulse_backend']='v3';find('gamePluginPage').setProperty('protocol','v3')
            pulse.connected=True;b._armed=True;check([True,True,True,False])
            pulse.connected=False;check([True,False,False,False])
            b._install_state['gameRunning']=False;check([False,False,False,False]);QTest.qWait(300)
            assert all(float(find(name).property('glow'))==0 for name in names)
            assert w.grabWindow().save(str(ROOT/'artifacts/ui/setup-gothic-idle-fixture.png'))
            b._connection['pulse_backend']='v4';find('gamePluginPage').setProperty('protocol','v4');hub.paired=True
            pulse.code='channel-blocked';ovc.code='accessory-not-inserted';b._armed=b._ovc_armed=False
            check([False,True,False,False])
            assert '屏蔽' in find('setupReason_pulse').property('text')
            assert '配件' in find('setupReason_ovc').property('text')
            assert not find('setupArmPulse').property('enabled') and not find('setupArmOvc').property('enabled')
            hints=[];b.toast.connect(hints.append)
            assert QMetaObject.invokeMethod(find('explainDevice_pulse'),'clicked')
            assert hints and '手动打开' in hints[-1]
            assert w.grabWindow().save(str(ROOT/'artifacts/ui/setup-blocked-channel-help.png'))
            pulse.error='DG-LAB APP：slot_not_found';b.changed.emit();app.processEvents()
            assert 'slot_not_found' in find('setupReason_pulse').property('text')
            errors=[m for m in messages if 'file:///' in m or 'ReferenceError' in m or 'TypeError' in m]
            assert not errors,errors
            report.update(passed=True,game_running_and_plugin_online_checked=True,server_only_does_not_glow=True,
                          paired_but_unarmed_devices_do_not_glow=True,independent_pulse_ovc_checked=True,
                          unavailable_muted_disconnected_and_emergency_states_clear_glow=True,
                          v3_and_v4_checked=True,fade_out_completed=True,qml_errors=errors,
                          hardware_connected=False,device_services_started=False,display_fixtures_only=True,
                          blocked_channel_and_missing_accessory_help=True,disabled_button_reason_action=True,raw_app_error_visible=True)
        except Exception:report.update(passed=False,error=traceback.format_exc(),messages=messages)
        (ROOT/'artifacts/ui/setup-gothic-readiness.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report));app.exit(0 if report['passed'] else 1)
    QTimer.singleShot(350,verify);result=app.exec()
    b._service=None;b._ovc_service=None;b._v4=None;b.shutdown();temp.cleanup()
    return result

if __name__=='__main__':raise SystemExit(main())
