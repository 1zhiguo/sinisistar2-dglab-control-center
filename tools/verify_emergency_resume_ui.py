"""Real QML emergency/resume control, no device services."""
from pathlib import Path
import json,sys,tempfile,traceback
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from PySide6.QtCore import QTimer,QUrl,QMetaObject,qInstallMessageHandler
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest
from sinisistar_dglab.backend import Backend

def main():
    app=QGuiApplication([]);messages=[];qInstallMessageHandler(lambda k,c,m:messages.append(m))
    temp=tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp');b=Backend(offline=True,settings=Path(temp.name)/'settings.json');b._timer.stop()
    engine=QQmlApplicationEngine();engine.rootContext().setContextProperty('backend',b)
    engine.load(QUrl.fromLocalFile(str(ROOT/'src/sinisistar_dglab/qml/ControlCenter.qml')));w=engine.rootObjects()[0]
    def find(name):
        pending=[w.contentItem()]
        while pending:
            item=pending.pop();pending.extend(item.childItems())
            if item.objectName()==name:return item
        raise LookupError(name)
    def run():
        try:
            button=find('topEmergencyStop');assert button.property('text')=='紧急归零';assert button.property('danger')
            QMetaObject.invokeMethod(button,'clicked');app.processEvents();QTest.qWait(200)
            assert b._emergency;assert button.property('text')=='恢复输出';assert not button.property('danger')
            assert button.property('ritualInk').name()=='#a5b595'
            assert w.grabWindow().save(str(ROOT/'artifacts/ui/emergency-resume-green.png'))
            QMetaObject.invokeMethod(button,'clicked');app.processEvents();assert not b._emergency
            assert button.property('text')=='紧急归零';assert not b._armed and not b._ovc_armed
            errors=[m for m in messages if any(s in m for s in ('ReferenceError','TypeError','Binding loop','Cannot assign','Unable to assign','is not a type'))];assert not errors,errors
            report=dict(passed=True,red_stop=True,green_resume=True,cleared=True,hardware_connected=False,qml_errors=errors)
        except Exception:report=dict(passed=False,error=traceback.format_exc(),messages=messages)
        (ROOT/'artifacts/ui/emergency-resume-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report));app.exit(0 if report['passed'] else 1)
    QTimer.singleShot(700,run);code=app.exec();b.shutdown();return code
if __name__=='__main__':raise SystemExit(main())
