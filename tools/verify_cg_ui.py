"""CG page interaction and persistence checks; inert offline backend only."""
from pathlib import Path
from copy import deepcopy
import json,sys,tempfile,traceback
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from PySide6.QtCore import QTimer,QUrl,QMetaObject,Q_ARG,qInstallMessageHandler,Qt
from PySide6.QtGui import QGuiApplication,QFont
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem,QQuickWindow
from PySide6.QtTest import QTest
from sinisistar_dglab.backend import Backend

app=QGuiApplication([]);app.setFont(QFont('Microsoft YaHei UI',10));messages=[]
qInstallMessageHandler(lambda kind,context,text:messages.append(text))
temp=tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp')
b=Backend(offline=True,settings=Path(temp.name)/'settings.json');b._timer.stop()
engine=QQmlApplicationEngine();engine.rootContext().setContextProperty('backend',b)
engine.load(QUrl.fromLocalFile(str(ROOT/'src/sinisistar_dglab/qml/ControlCenter.qml')))
assert engine.rootObjects(),messages
w=engine.rootObjects()[0];w.setProperty('pageIndex',7)
def find(name):
    pending=[w.contentItem()]
    while pending:
        x=pending.pop()
        if x.objectName()==name:return x
        pending.extend(x.childItems())
    raise LookupError(name)
def invoke(name,method,*args):
    assert QMetaObject.invokeMethod(find(name),method,*args),name
    app.processEvents()
def combo(name,index):
    find(name).setProperty('currentIndex',index);invoke(name,'activated',Q_ARG(int,index))
def verify():
    try:
        assert find('cgFeedbackPage');assert b.cgSettings['inherit_death']
        original=deepcopy(b._sim_profile['rules']['defeat_hold']);b._armed=b._ovc_armed=True
        find('cgSameHpEnabled').setProperty('checked',True);invoke('cgSameHpEnabled','toggled')
        assert b.cgSettings['same_hp_enabled'] and not b._armed and not b._ovc_armed
        assert not find('cgAdvanced_pulse').property('expanded')
        combo('cgMode_pulse',1);assert not b.cgSettings['inherit_death']
        assert not b._armed and not b._ovc_armed
        invoke('cgQueueDetails_pulse','clicked');invoke('cgQueueAdd_pulse','clicked');assert len(b.cgSettings['routes']['pulse']['A']['queue'])==6
        combo('cgQueueWave_pulse_1',2)
        invoke('cgQueueSeconds_pulse_1','edited',Q_ARG(float,7.5))
        invoke('cgQueueUp_pulse_1','clicked');assert b.cgSettings['routes']['pulse']['A']['queue'][0]['seconds']==7.5
        invoke('cgAdvanced_pulse','clicked');combo('cgRampMode_pulse',3)
        combo('cgRampScope_pulse',2)
        invoke('cgRampSeconds_pulse','edited',Q_ARG(float,180))
        invoke('cgChannelB_pulse','clicked');combo('cgMode_pulse',2);assert b.cgSettings['routes']['pulse']['A']['mode']=='sequence'
        assert b.cgSettings['routes']['pulse']['B']['mode']=='shuffle'
        combo('cgMode_vibration',2)
        invoke('cgQueueAdd_vibration','clicked')
        invoke('cgAdvanced_vibration','clicked');combo('cgRampMode_vibration',1)
        assert find('cgEnabled_vibration').property('accent').name()=='#a69abb'
        assert find('cgQueueLoop_vibration').property('accent').name()=='#a69abb'
        assert find('rangeSlider_cg_vibration_a').property('visible')
        assert b._sim_profile['rules']['defeat_hold']==original
        QTest.qWait(200);assert w.grabWindow().save(str(ROOT/'artifacts/ui/cg-feedback-queue.png'))
        other=Backend(offline=True,settings=b.settings);other._timer.stop()
        try:
            assert other.cgSettings['routes']['pulse']['A']['ramp_scope']=='wave'
            assert other.cgSettings['routes']['pulse']['A']['ramp_seconds']==180
            assert other.cgSettings['routes']['vibration']['A']['mode']=='shuffle'
        finally:other.shutdown()
        w.setWidth(1140);w.setHeight(780);app.processEvents();QTest.qWait(150)
        assert w.grabWindow().save(str(ROOT/'artifacts/ui/cg-feedback-compact.png'))
        assert find('navigation_7').mapToScene(find('navigation_7').boundingRect().bottomRight()).y()<find('diagnosticNavSeparator').mapToScene(find('diagnosticNavSeparator').boundingRect().topLeft()).y()
        errors=[m for m in messages if any(k in m for k in ('ReferenceError','TypeError','Binding loop','Cannot assign','Unable to assign','is not a type'))]
        assert not errors,errors
        assert b._service is None and b._v4 is None
        report=dict(passed=True,queue_add_move_edit=True,persisted=True,independent_from_death=True,editing_pauses_both=True,ovc_violet=True,advanced_collapsed_by_default=True,minimum_size_checked=True,hardware_connected=False,qml_errors=errors)
        (ROOT/'artifacts/ui/cg-feedback-validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report));app.exit(0)
    except Exception:traceback.print_exc();print(messages);app.exit(1)
QTimer.singleShot(450,verify)
result=app.exec();b.shutdown();w.close();engine.deleteLater();app.processEvents();temp.cleanup();raise SystemExit(result)
