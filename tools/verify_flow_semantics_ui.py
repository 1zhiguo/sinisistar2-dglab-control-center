"""Native flow review UI against recorded catalog; no observer or device services."""
import json,sys,tempfile,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from PySide6.QtCore import QTimer,QUrl,qInstallMessageHandler
from PySide6.QtGui import QGuiApplication,QFont
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem,QQuickWindow
from PySide6.QtTest import QTest
from sinisistar_dglab.backend import Backend

app=QGuiApplication([]);app.setFont(QFont('Microsoft YaHei UI',10));messages=[]
qInstallMessageHandler(lambda kind,context,text:messages.append(text))
temp=tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp')
b=Backend(offline=True,settings=Path(temp.name)/'settings.json');b._timer.stop()
real_rows=json.loads((ROOT/'artifacts/observed-flows.json').read_text(encoding='utf-8'))
b._flows.items={r['key']:r for r in real_rows}
engine=QQmlApplicationEngine();engine.rootContext().setContextProperty('backend',b)
engine.load(QUrl.fromLocalFile(str(ROOT/'src/sinisistar_dglab/qml/ControlCenter.qml')))
assert engine.rootObjects(),messages
w=engine.rootObjects()[0];w.setProperty('pageIndex',6)
def find(name):
    pending=[w.contentItem()]
    while pending:
        item=pending.pop()
        if item.objectName()==name:return item
        pending.extend(item.childItems())
    raise LookupError(name)
def click(item):
    pos=item.mapToScene(item.boundingRect().center()).toPoint();QTest.mouseClick(w,__import__('PySide6.QtCore',fromlist=['Qt']).Qt.LeftButton,pos=pos);app.processEvents()
def verify():
    try:
        page=find('captureFlowCatalog');page.setProperty('catalogMode',2);app.processEvents()
        rows=page.property('rows').toVariant();assert any(r['key']=='scene:167' for r in rows)
        search=find('flowSemanticSearch');search.setProperty('text','猪棚');app.processEvents()
        rows=page.property('rows').toVariant();assert len(rows)>=3,[(r['key'],r['semantic_title']) for r in rows]
        count=len(rows);click(find('selectFilteredFlows'));assert len(page.property('checkedKeys').toVariant())==count
        click(find('reviewRampFlows'));assert all(r['review_decision']=='ramp' for r in page.property('rows').toVariant())
        page.setProperty('selectedKey','[166,"Continue","StartGacha","HierarchyEventPlayer"]');app.processEvents()
        QTest.qWait(250);assert w.grabWindow().save(str(ROOT/'artifacts/ui/flow-semantics-pigpen.png'))
        search.setProperty('text','');page.setProperty('catalogMode',1);app.processEvents()
        assert page.property('checkedKeys').toVariant()==['scene:167']
        search.setProperty('text','HoldCancel');app.processEvents()
        assert page.property('checkedKeys').toVariant()==[]
        rows=page.property('rows').toVariant();assert rows and all('HoldCancel' in r['semantic_symbols'] for r in rows)
        assert w.grabWindow().save(str(ROOT/'artifacts/ui/flow-semantics-static.png'))
        errors=[m for m in messages if any(k in m for k in ('ReferenceError','TypeError','Binding loop','Cannot assign','is not a type','Unable to assign'))]
        assert not errors,errors
        assert b._v4 is None and b._service is None and b._observer is None
        (ROOT/'artifacts/ui/flow-semantics-validation.json').write_text(json.dumps(dict(passed=True,runtime=len(real_rows),static_families=len(b._static_flows),scene_candidates=len(b._flow_scenes),hardware_connected=False),indent=2),encoding='utf-8')
        print('Flow semantics UI passed; no devices or game commands.');app.exit(0)
    except Exception:
        traceback.print_exc();print(messages);app.exit(1)
QTimer.singleShot(450,verify)
result=app.exec();b.shutdown();w.close();engine.deleteLater();app.processEvents();temp.cleanup();raise SystemExit(result)
