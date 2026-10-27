"""Read-only setup UI matrix. V3 QR uses a static documentation-address fixture."""
from pathlib import Path
import json,queue,sys,tempfile,traceback
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from PySide6.QtCore import QObject,QMetaObject,QTimer,QUrl,Q_ARG,qInstallMessageHandler
from PySide6.QtGui import QGuiApplication,QFont
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem,QQuickWindow
from sinisistar_dglab.backend import Backend

class StaticV3:
    def snapshot(self):return dict(server_ready=True,connected=False,feedback_known=False,local_only=False,port=10002,lan_ip='192.0.2.1')

def main():
    app=QGuiApplication([]);app.setFont(QFont('Microsoft YaHei UI',10));messages=[]
    qInstallMessageHandler(lambda k,c,m:messages.append(m))
    temp=tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp');b=Backend(offline=True,settings=Path(temp.name)/'settings.json');b._timer.stop()
    b._game_candidates=[dict(path=str(Path(temp.name)/'WIN'),name='v1.3.1 fixture',supported=True)]
    b._install_state.update(selectedPath=str(Path(temp.name)/'WIN'),valid=True,payloadReady=True,installedVersion='0.3.0')
    engine=QQmlApplicationEngine();engine.rootContext().setContextProperty('backend',b)
    engine.load(QUrl.fromLocalFile(str(ROOT/'src/sinisistar_dglab/qml/ControlCenter.qml')))
    w=engine.rootObjects()[0];w.setProperty('pageIndex',1);report={}
    def items():
        result=[];pending=[w.contentItem()]
        while pending:
            item=pending.pop();result.append(item);pending.extend(item.childItems())
        return result
    def find(name):return next(i for i in items() if i.objectName()==name)
    def fail():
        report.update(passed=False,error=traceback.format_exc(),messages=messages);finish()
    def finish():
        (ROOT/'artifacts/ui/setup-matrix.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report));app.exit(0 if report.get('passed') else 1)
    def first():
        try:
            assert find('installAndLaunchGameButton').isEnabled()
            assert not find('setupArmPulse').isEnabled() and not find('setupArmOvc').isEnabled()
            assert find('setupOvcReadyCard').isVisible()
            assert not find('connectionHelpDisclosure').property('expanded') and not find('gameDirectoryDisclosure').property('expanded')
            b._install_state['gameRunning']=True;b.installChanged.emit();app.processEvents()
            assert not find('installAndLaunchGameButton').isEnabled() and not find('installGamePluginButton').isEnabled()
            assert QMetaObject.invokeMethod(find('connectionHelpButton'),'clicked');assert find('connectionHelpDisclosure').property('expanded')
            combo=find('connectionProtocolChoice');combo.setProperty('currentIndex',0)
            assert QMetaObject.invokeMethod(combo,'activated',Q_ARG(int,0))
            b._service=StaticV3();b._qrurl='https://www.dungeon-lab.com/app-download.php#DGLAB-SOCKET#ws://192.0.2.1:10002/fixture'
            b.changed.emit();app.processEvents()
            guide_images=[i for i in items() if 'connection-guide/' in str(i.property('source'))]
            assert len(guide_images)==4 and all(i.property('loadStatus')==1 for i in guide_images)
            assert find('v3ConnectionGuide').isVisible()
            assert not find('setupOvcReadyCard').isVisible()
            assert find('setupPulseReadyCard').isVisible() and find('setupDeviceCards').property('columns')==1
            find('gamePluginPage').setProperty('protocol','v4');app.processEvents()
            assert find('setupOvcReadyCard').isVisible() and find('setupDeviceCards').property('columns')==2
            find('gamePluginPage').setProperty('protocol','v3');app.processEvents()
            assert w.grabWindow().save(str(ROOT/'artifacts/ui/setup-v3-fixture.png'))
            page=find('gamePluginPage');viewport=page.property('contentItem');guide=find('v3ConnectionGuide')
            viewport.setProperty('contentY',max(0,float(guide.property('y'))-12));app.processEvents()
            assert w.grabWindow().save(str(ROOT/'artifacts/ui/setup-v3-guide-fixture.png'))
            assert QMetaObject.invokeMethod(page,'openGuide',Q_ARG(int,0));app.processEvents()
            report.update(launch_enabled_when_ready=True,install_and_launch_disabled_while_game_running=True,
                          unpaired_output_disabled=True,advanced_collapsed_by_default=True,help_button_expands=True,
                          v3_guide_images_ready=4,static_v3_qr_fixture=True,v3_hides_ovc_and_expands_pulse=True,v4_restores_ovc=True)
            QTimer.singleShot(250,second)
        except Exception:fail()
    def second():
        try:
            dialogs=w.findChildren(QObject,'connectionGuideDialog');assert dialogs and dialogs[0].property('visible')
            assert w.grabWindow().save(str(ROOT/'artifacts/ui/setup-guide-expanded.png'))
            assert QMetaObject.invokeMethod(dialogs[0],'close')
            errors=[m for m in messages if 'file:///' in m or 'ReferenceError' in m or 'TypeError' in m];assert not errors,errors
            report.update(passed=True,guide_opens_full_size=True,qml_errors=errors,hardware_connected=False,device_services_started=False)
            finish()
        except Exception:fail()
    QTimer.singleShot(350,first);result=app.exec();b._service=None;b.shutdown();temp.cleanup();return result

if __name__=='__main__':raise SystemExit(main())
