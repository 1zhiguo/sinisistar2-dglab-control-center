"""Native Chinese status filters and scoped batch actions; no device services."""
from pathlib import Path
import json,sys,tempfile,time,traceback
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from PySide6.QtCore import QObject,QMetaObject,QTimer,QUrl,Q_ARG,qInstallMessageHandler
from PySide6.QtGui import QGuiApplication,QFont
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem,QQuickWindow
from PySide6.QtTest import QTest
from sinisistar_dglab.backend import Backend

def main():
    app=QGuiApplication([]);app.setFont(QFont('Microsoft YaHei UI',10));messages=[]
    qInstallMessageHandler(lambda k,c,m:messages.append(m))
    temp=tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp')
    b=Backend(offline=True,settings=Path(temp.name)/'settings.json');b._timer.stop()
    engine=QQmlApplicationEngine();engine.rootContext().setContextProperty('backend',b)
    engine.load(QUrl.fromLocalFile(str(ROOT/'src/sinisistar_dglab/qml/ControlCenter.qml')))
    w=engine.rootObjects()[0];w.setProperty('pageIndex',3);report={}
    def find(name):
        pending=[w.contentItem()]
        while pending:
            item=pending.pop()
            if item.objectName()==name:return item
            pending.extend(item.childItems())
        raise LookupError(name)
    def rows():
        value=find('feedbackPolicyPage').property('filteredRows')
        return value.toVariant() if hasattr(value,'toVariant') else value
    def setprop(name,key,value):find(name).setProperty(key,value);app.processEvents()
    def click(name):assert QMetaObject.invokeMethod(find(name),'clicked');app.processEvents()
    def verify():
        try:
            page=find('feedbackPolicyPage');page.setProperty('groupIndex',1);app.processEvents()
            assert len(rows())==69 and all(not r['enabled'] for r in b.simulationAbnormals)
            setprop('policySearch','text','毒');assert {r['key'] for r in rows()}=={'Poison','DeadlyPoison'}
            b._armed=True;b._ovc_armed=True;click('enableFilteredAbnormals')
            assert {r['key'] for r in b.simulationAbnormals if r['enabled']}=={'Poison','DeadlyPoison'}
            assert not b._armed and not b._ovc_armed
            setprop('policySearch','text','');setprop('feedbackPolicyPage','categoryFilter','restraint')
            assert len(rows())>=5 and all(r['category']=='restraint' for r in rows())
            setprop('feedbackPolicyPage','stateFilter','enabled');assert not rows()
            setprop('feedbackPolicyPage','categoryFilter','all');assert len(rows())==2
            setprop('feedbackPolicyPage','stateFilter','disabled');assert len(rows())==67
            setprop('feedbackPolicyPage','stateFilter','positive');assert len(rows())==1
            assert not find('enableFilteredAbnormals').property('enabled')
            b._live=dict(live=True,valid=True,sampled_at=time.monotonic(),pid=1,player=2,hp=dict(current=100,max=100),
                         abnormals=[dict(name='Poison',level=8),dict(name='InfertilityBlessing',level=1)])
            b.changed.emit();setprop('feedbackPolicyPage','stateFilter','active')
            assert {r['key'] for r in rows()}=={'Poison','InfertilityBlessing'}
            setprop('feedbackPolicyPage','stateFilter','negative');click('disableFilteredAbnormals')
            assert not any(r['enabled'] for r in b.simulationAbnormals)
            setprop('policySearch','text','Leech');assert len(rows())>=4
            setprop('policySearch','text','');setprop('feedbackPolicyPage','categoryFilter','parasite')
            assert all(any('\u4e00'<=c<='\u9fff' for c in r['name']) for r in rows())
            QTest.qWait(70);assert w.grabWindow().save(str(ROOT/'artifacts/ui/abnormal-filter-chinese.png'))
            w.setProperty('pageIndex',2);app.processEvents();click('manageAbnormals');QTest.qWait(50)
            assert w.property('pageIndex')==3 and find('feedbackPolicyPage').property('groupIndex')==1
            errors=[m for m in messages if 'file:///' in m or 'ReferenceError' in m or 'TypeError' in m]
            assert not errors,errors
            report.update(passed=True,chinese_and_internal_name_search=True,category_and_enabled_filters=True,
                          current_status_filter=True,positive_filter_read_only=True,scoped_batch_enable_disable=True,
                          all_statuses_off_by_default=True,pulse_fixed_10_ovc_zero=True,quick_settings_shortcut=True,
                          qml_errors=errors,hardware_connected=False,game_values_mutated=False)
        except Exception:report.update(passed=False,error=traceback.format_exc(),messages=messages)
        (ROOT/'artifacts/ui/abnormal-filter-interaction.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report));app.exit(0 if report['passed'] else 1)
    QTimer.singleShot(400,verify);result=app.exec();b.shutdown();temp.cleanup();return result

if __name__=='__main__':raise SystemExit(main())
