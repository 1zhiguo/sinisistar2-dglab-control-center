"""Native toolbar layout and settings-only simulation controls; isolated offline config."""
from pathlib import Path
from copy import deepcopy
import json,sys,tempfile,traceback
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from PySide6.QtCore import QObject,QTimer,QUrl,QMetaObject,Q_ARG,qInstallMessageHandler,Qt
from PySide6.QtGui import QGuiApplication,QFont
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest
from sinisistar_dglab.backend import Backend

def main():
    app=QGuiApplication([]);app.setFont(QFont('Microsoft YaHei UI',10));messages=[]
    qInstallMessageHandler(lambda k,c,m:messages.append(m))
    temp=tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp')
    b=Backend(offline=True,settings=Path(temp.name)/'settings.json');b._timer.stop()
    engine=QQmlApplicationEngine();engine.rootContext().setContextProperty('backend',b)
    engine.load(QUrl.fromLocalFile(str(ROOT/'src/sinisistar_dglab/qml/ControlCenter.qml')))
    if not engine.rootObjects():print(messages);return 1
    w=engine.rootObjects()[0]
    def items():
        pending=[w.contentItem()];out=[]
        while pending:
            item=pending.pop();out.append(item);pending.extend(item.childItems())
        return out
    def find(name):
        found=[x for x in items() if x.objectName()==name]
        return next((x for x in found if x.isVisible()),found[0] if found else w.findChild(QObject,name))
    def invoke(name,method,*args):assert QMetaObject.invokeMethod(find(name),method,*args),name;app.processEvents()
    def click(name):
        item=find(name);QTest.mouseClick(w,Qt.LeftButton,pos=item.mapToScene(item.boundingRect().center()).toPoint());app.processEvents()
    def verify():
        try:
            b.editQuickValue('pulse_cap',30);app.processEvents();assert find('topPulseCap').property('text')=='Pulse 30'
            b._sim_profile.update(pulse_cap_b=60,vibration_cap_a=90,vibration_cap_b=40);b.configChanged.emit();app.processEvents()
            assert find('topPulseCap').property('text')=='Pulse 30/60'
            assert find('topOvcCap').property('text')=='负鼠 90/40'
            before=deepcopy(b._sim_profile);layouts=[]
            names=('topHardLimits','openTutorialButton','topHudGroup','topPulseControl','topEmergencyStop','openAppSettings')
            for lang in ('zh-CN','en','ja'):
                b.setLanguage(lang)
                for width in (1440,1140):
                    w.resize(width,940 if width==1440 else 780);app.processEvents();QTest.qWait(200)
                    centers=[];end=0
                    for name in names:
                        item=find(name);pos=item.mapToScene(item.boundingRect().topLeft())
                        assert item.height()==44,(name,item.height())
                        assert pos.x()>=end and pos.x()+item.width()<=w.width(),(lang,width,name,'overlap')
                        centers.append(pos.y()+item.height()/2);end=pos.x()+item.width()
                    assert max(centers)-min(centers)<1,(lang,width,centers)
                    assert find('topPageTitle').width()>=150,(lang,width,find('topPageTitle').width())
                    hud=find('topHudSettings');assert abs(hud.mapToScene(hud.boundingRect().center()).y()-centers[0])<1
                    assert find('topEmergencyStop').property('ritualInk').name()=='#d66670'
                    assert w.grabWindow().save(str(ROOT/'artifacts/ui'/f'toolbar-{lang}-{width}.png'))
                    layouts.append(dict(language=lang,width=width,center_y=centers[0],title_width=find('topPageTitle').width()))
            b.setLanguage('zh-CN');w.resize(1440,940);app.processEvents()
            # These actions are no longer on any ordinary page.
            for page in range(9):
                w.setProperty('pageIndex',page);app.processEvents();QTest.qWait(25)
                assert not any(x.isVisible() and x.objectName() in ('mainMockStart','mainMockResume','mainMockStop','mainMockRecords','setupMockPulseButton','policyPreviewDisclosure') for x in items())
            click('openAppSettings');assert find('appSettingsMenu').property('visible')
            assert w.grabWindow().save(str(ROOT/'artifacts/ui/toolbar-settings-menu.png'))
            click('openSimulationSettings');assert find('simulationSettingsDialog').property('visible')
            assert find('mainMockStart').isVisible() and find('policyPreviewDisclosure').isVisible()
            assert w.grabWindow().save(str(ROOT/'artifacts/ui/simulation-settings.png'))
            invoke('policyPreviewDisclosure','clicked')
            find('simulationSampleChoice').setProperty('currentIndex',1);invoke('simulationSampleChoice','activated',Q_ARG(int,1))
            assert b.simulation['mode']=='grab_hp'
            invoke('toggleSimulationPreview','clicked');assert b.simulation['running']
            invoke('toggleSimulationPreview','clicked');assert not b.simulation['running']
            invoke('closeSimulationSettings','clicked')
            click('topHardLimits');assert w.property('pageIndex')==2
            click('topHudSettings');assert find('hudSettingsDialog').property('visible');invoke('hudSettingsDialog','close')
            assert b._sim_profile==before and not b._armed and not b._ovc_armed
            b._armed=b._ovc_armed=True;b.changed.emit();app.processEvents()
            click('topEmergencyStop');assert b._emergency and not b._armed and not b._ovc_armed
            assert b._service is None and b._v4 is None
            errors=[m for m in messages if any(k in m for k in ('ReferenceError','TypeError','Binding loop','Cannot assign','Unable to assign','is not a type','non-existent property'))]
            assert not errors,errors
            report=dict(passed=True,layouts=layouts,ab_caps_refresh=True,simulations_only_in_settings=True,emergency_button_locks_both=True,settings_dialogs_work=True,qml_errors=errors,hardware_connected=False)
        except Exception:report=dict(passed=False,error=traceback.format_exc(),messages=messages)
        (ROOT/'artifacts/ui/toolbar-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False));app.exit(0 if report['passed'] else 1)
    QTimer.singleShot(400,verify);result=app.exec();b.shutdown();temp.cleanup();return result

if __name__=='__main__':raise SystemExit(main())
