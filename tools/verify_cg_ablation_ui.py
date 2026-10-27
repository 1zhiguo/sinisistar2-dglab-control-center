"""Offline native UI check for ablation, coverage filters and persistence."""
from pathlib import Path
import json,sys,tempfile,traceback
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from PySide6.QtCore import QTimer,QUrl,QMetaObject,Q_ARG,qInstallMessageHandler
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest
from sinisistar_dglab.backend import Backend
from sinisistar_dglab.cg_playback import REGISTRY

def main():
    app=QGuiApplication([]);messages=[];qInstallMessageHandler(lambda k,c,m:messages.append(m))
    temp=tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp');settings=Path(temp.name)/'settings.json'
    b=Backend(offline=True,settings=settings,developer_tools=True);b._timer.stop();engine=QQmlApplicationEngine();engine.rootContext().setContextProperty('backend',b)
    engine.load(QUrl.fromLocalFile(str(ROOT/'src/sinisistar_dglab/qml/ControlCenter.qml')));w=engine.rootObjects()[0];w.setProperty('pageIndex',7)
    def find(name):
        pending=[w.contentItem()]
        while pending:
            item=pending.pop();pending.extend(item.childItems())
            if item.objectName()==name:return item
        raise LookupError(name)
    def run():
        try:
            b._armed=b._ovc_armed=True;combo=find('cgDetectionMode');combo.setProperty('currentIndex',1)
            assert QMetaObject.invokeMethod(combo,'activated',Q_ARG(int,1));app.processEvents()
            assert b._sim_profile['cg_detection_mode']=='playback_only' and not b._armed and not b._ovc_armed
            assert QMetaObject.invokeMethod(find('cgCoverageTab'),'clicked');app.processEvents();QTest.qWait(150)
            assert find('cgFeedbackPage').property('scope')=='coverage';assert len(b.cgCoverage)==len(REGISTRY.rows)
            assert find('cgCoverageList').property('count')==len(REGISTRY.rows)
            find('cgCoverageSearch').setProperty('text','BreastHaanja');app.processEvents();assert find('cgCoverageList').property('count')>=1
            b.exportCgCoverage();assert (settings.parent/'cg-coverage-export.json').is_file()
            other=Backend(offline=True,settings=settings);other._timer.stop()
            try:assert other._sim_profile['cg_detection_mode']=='playback_only'
            finally:other.shutdown()
            find('cgCoverageSearch').setProperty('text','');app.processEvents();QTest.qWait(100)
            assert w.grabWindow().save(str(ROOT/'artifacts/ui/cg-ablation-coverage.png'))
            errors=[m for m in messages if any(x in m for x in ('ReferenceError','TypeError','Binding loop','Cannot assign','Unable to assign','is not a type'))];assert not errors,errors
            report=dict(passed=True,catalog_rows=len(REGISTRY.rows),mode_persisted=True,changing_mode_disarms=True,coverage_search=True,export=True,hardware_connected=False,qml_errors=[])
        except Exception:report=dict(passed=False,error=traceback.format_exc(),messages=messages)
        (ROOT/'artifacts/ui/cg-ablation-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report));app.exit(0 if report['passed'] else 1)
    QTimer.singleShot(700,run);code=app.exec();b.shutdown();temp.cleanup();return code
if __name__=='__main__':raise SystemExit(main())
