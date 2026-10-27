"""Offline real QML test for automatic current-CG detection and human marking."""
from pathlib import Path
import json,sys,tempfile,time,traceback,zipfile
from copy import deepcopy
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from PySide6.QtCore import QTimer,QUrl,QMetaObject,qInstallMessageHandler
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest
from sinisistar_dglab.backend import Backend

def main():
    app=QGuiApplication([]);messages=[];qInstallMessageHandler(lambda k,c,m:messages.append(m))
    temp=tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp');settings=Path(temp.name)/'settings.json'
    b=Backend(offline=True,developer_tools=True,settings=settings);b._timer.stop();b._sim_profile['cg_detection_mode']='playback_only'
    engine=QQmlApplicationEngine();engine.rootContext().setContextProperty('backend',b)
    engine.load(QUrl.fromLocalFile(str(ROOT/'src/sinisistar_dglab/qml/ControlCenter.qml')));w=engine.rootObjects()[0];w.setProperty('pageIndex',7)
    def find(name):
        pending=[w.contentItem()]
        while pending:
            item=pending.pop();pending.extend(item.childItems())
            if item.objectName()==name:return item
        raise LookupError(name)
    def click(name):assert QMetaObject.invokeMethod(find(name),'clicked');app.processEvents()
    raw=json.loads((ROOT/'tests/fixtures/gallery-0.5.0-bobel-session.json').read_text(encoding='utf-8'))
    def feed(enemy,index=1):
        s=deepcopy(raw);now=time.monotonic();s.update(live=True,sampled_at=now,scene='Gallery');s['gallery'].update(enemy_id=enemy,selected_index_raw=index,take_count=2)
        b._cg_batch.observe(s,{},{},{},{},{},'playback_only',now);s['sampled_at']=now+.5;b._cg_batch.observe(s,{},{},{},{},{},'playback_only',now+.5);b._refresh_batch();app.processEvents()
    def run():
        try:
            click('cgBatchTab');QTest.qWait(100);feed(61)
            assert '藤壶' in find('cgBatchCurrentTitle').property('text')
            click('cgBatchNo');assert b._cg_batch.data['cases']['gallery:61:1']['verdict']=='no'
            click('cgBatchDetails');notes=find('cgBatchNote');notes.forceActiveFocus();notes.setProperty('text','这段没有反馈');QTest.qWait(650)
            assert b._cg_batch.data['cases']['gallery:61:1']['note']=='这段没有反馈'
            feed(59);assert '米达斯' in find('cgBatchCurrentTitle').property('text');click('cgBatchYes')
            assert b._cg_batch.data['cases']['gallery:59:1']['verdict']=='yes';assert b._cg_batch.data['cases']['gallery:61:1']['verdict']=='no'
            b.exportCgBatch(False);export=Path(b.cgBatch['exportPath']);assert export.exists()
            with zipfile.ZipFile(export) as z:assert len(json.loads(z.read('report.json'))['visits'])==2
            QTest.qWait(200);assert w.grabWindow().save(str(ROOT/'artifacts/ui/cg-batch-test.png'))
            click('cgBatchFinish');assert b.cgBatch['status']=='finished'
            errors=[m for m in messages if any(s in m for s in ('ReferenceError','TypeError','Binding loop','Cannot assign','Unable to assign','is not a type'))];assert not errors,errors
            report=dict(passed=True,automatic_current_cg=True,yes_no_saved=True,follow_on_switch=True,notes_saved=True,zip_export=True,finish=True,hardware_connected=False,qml_errors=[])
        except Exception:report=dict(passed=False,error=traceback.format_exc(),messages=messages)
        (ROOT/'artifacts/ui/cg-batch-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report));app.exit(0 if report['passed'] else 1)
    QTimer.singleShot(700,run);code=app.exec();b.shutdown();temp.cleanup();return code
if __name__=='__main__':raise SystemExit(main())
