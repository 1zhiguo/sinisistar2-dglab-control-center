"""Exercise the visible game/gallery sync buttons with an offline backend."""
from pathlib import Path
from copy import deepcopy
import json,sys,tempfile,traceback
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from PySide6.QtCore import QTimer,QUrl,QMetaObject,qInstallMessageHandler
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest
from sinisistar_dglab.backend import Backend

app=QGuiApplication([]);messages=[];qInstallMessageHandler(lambda k,c,m:messages.append(m))
temp=tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp')
b=Backend(offline=True,settings=Path(temp.name)/'settings.json');b._timer.stop();b._tutorial['seen']=True
engine=QQmlApplicationEngine();engine.rootContext().setContextProperty('backend',b)
engine.load(QUrl.fromLocalFile(str(ROOT/'src/sinisistar_dglab/qml/ControlCenter.qml')))
assert engine.rootObjects(),messages
window=engine.rootObjects()[0];window.setProperty('pageIndex',7)
out=ROOT/'artifacts/ui';out.mkdir(exist_ok=True)

def find(name):
    pending=[window.contentItem()]
    while pending:
        item=pending.pop()
        if item.objectName()==name:return item
        pending.extend(item.childItems())
    raise LookupError(name)

def verify():
    try:
        button=find('syncCgFeedback');assert button.property('visible') and button.property('enabled')
        assert button.property('text')=='同步到图鉴反馈'
        b.setCgOption('pulse:A','mode','shuffle');b.setCgOption('vibration:B','ramp_seconds',132)
        source=deepcopy(b.cgSettings);b._armed=b._ovc_armed=True
        assert QMetaObject.invokeMethod(button,'clicked');app.processEvents()
        assert b.gallerySettings['routes']==source['routes'];assert b.cgSettings==source
        assert not b._armed and not b._ovc_armed
        window.setWidth(1140);window.setHeight(780);QTest.qWait(100)
        assert window.grabWindow().save(str(out/'cg-sync-game.png'))
        assert QMetaObject.invokeMethod(find('cgGalleryTab'),'clicked');QTest.qWait(100)
        button=find('syncCgFeedback');assert button.property('text')=='同步到游戏 CG'
        b.setCgOption('gallery/pulse:B','ramp_scope','wave');source=deepcopy(b.gallerySettings)
        assert QMetaObject.invokeMethod(button,'clicked');app.processEvents()
        assert b.cgSettings['routes']==source['routes'];assert b.gallerySettings==source
        for lang in ('en','ja','zh-CN'):
            b.setLanguage(lang);QTest.qWait(100)
            assert button.property('contentItem').property('localizedText')==b.translate('同步到游戏 CG',lang)
        assert window.grabWindow().save(str(out/'cg-sync-gallery.png'))
        errors=[m for m in messages if any(k in m for k in ('ReferenceError','TypeError','Cannot assign','Unable to assign','Binding loop'))]
        assert not errors,errors
        assert b._service is None and b._v4 is None
        report=dict(passed=True,both_directions=True,source_unchanged=True,editing_pauses_both=True,localized=True,minimum_size_checked=True,hardware_connected=False,qml_errors=errors)
        (out/'cg-sync-validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report));app.exit(0)
    except Exception:traceback.print_exc();print(messages);app.exit(1)

QTimer.singleShot(400,verify)
code=app.exec();b.shutdown();window.close();engine.deleteLater();app.processEvents();temp.cleanup();raise SystemExit(code)
