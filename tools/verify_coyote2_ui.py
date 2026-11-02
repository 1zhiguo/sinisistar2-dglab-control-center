"""Real QML device picker/ready state with a loopback Coyote 2.0 APP."""
from pathlib import Path
import json,sys,tempfile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from PySide6.QtCore import QTimer,QUrl,qInstallMessageHandler
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from sinisistar_dglab.backend import Backend

def main():
    app=QGuiApplication([]);messages=[];qInstallMessageHandler(lambda k,c,m:messages.append(m))
    temp=tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp')
    b=Backend(offline=True,settings=Path(temp.name)/'settings.json');b._install_state['busy']=True;b.offline=False
    b.startMockBoth(coyote_type='COYOTE_020')
    engine=QQmlApplicationEngine();engine.rootContext().setContextProperty('backend',b)
    engine.load(QUrl.fromLocalFile(str(ROOT/'src/sinisistar_dglab/qml/ControlCenter.qml')))
    if not engine.rootObjects():b.shutdown();raise RuntimeError(messages)
    window=engine.rootObjects()[0];window.setProperty('pageIndex',1)
    out=ROOT/'artifacts/coyote2-validation';out.mkdir(parents=True,exist_ok=True)
    attempts=0
    def verify():
        nonlocal attempts
        attempts+=1
        if not b._armed or not b._ovc_armed:
            if attempts<80:QTimer.singleShot(50,verify);return
            print(json.dumps(dict(error='Coyote 2.0 UI fixture not ready',pulse=b._device_setup('pulse'))));app.exit(1);return
        try:
            results=[]
            for lang in ('zh-CN','en','ja'):
                b.setLanguage(lang);app.processEvents()
                pending=[window.contentItem()];items=[]
                while pending:
                    item=pending.pop();items.append(item);pending.extend(item.childItems())
                combo=next(i for i in items if i.objectName()=='pulseDeviceChoice' and i.property('visible'))
                model=combo.property('model');model=model.toVariant() if hasattr(model,'toVariant') else model
                assert len(model)==2 and '2.0' in model[1]['label'],model
                assert combo.property('currentIndex')==1
                assert b._device_setup('pulse')['canEnable'] and b._service.snapshot()['device_type']=='COYOTE_020'
                image=out/('devices-coyote2-'+lang+'.png');assert window.grabWindow().save(str(image))
                results.append(dict(language=lang,choices=model,screenshot=str(image)))
            errors=[m for m in messages if any(k in m for k in ('ReferenceError','TypeError','Cannot assign','Unable to assign','is not a type','Binding loop'))]
            assert not errors,errors
            report=dict(passed=True,hardware_connected=False,ui=results,qml_errors=errors)
            (out/'ui.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False));app.exit(0)
        except Exception as e:
            import traceback;traceback.print_exc();print(messages[-10:]);app.exit(1)
    QTimer.singleShot(200,verify);code=app.exec();b.shutdown();temp.cleanup();return code

if __name__=='__main__':raise SystemExit(main())
