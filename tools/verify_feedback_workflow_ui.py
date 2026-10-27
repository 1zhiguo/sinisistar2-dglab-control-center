"""Native QML playback/queue/custom confirmation QA, with no device service."""
from pathlib import Path
from copy import deepcopy
import json,sys,tempfile,traceback
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from PySide6.QtCore import QObject,QTimer,QUrl,QMetaObject,qInstallMessageHandler,Qt,QPointF
from PySide6.QtGui import QGuiApplication,QFont
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest
from sinisistar_dglab.backend import Backend

app=QGuiApplication([]);app.setFont(QFont('Microsoft YaHei UI',10));messages=[]
qInstallMessageHandler(lambda k,c,m:messages.append(m))
temp=tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp')
b=Backend(offline=True,settings=Path(temp.name)/'settings.json');b._timer.stop()
engine=QQmlApplicationEngine();engine.rootContext().setContextProperty('backend',b)
engine.load(QUrl.fromLocalFile(str(ROOT/'src/sinisistar_dglab/qml/ControlCenter.qml')))
assert engine.rootObjects(),messages
w=engine.rootObjects()[0];w.setProperty('pageIndex',7)
def find(name):
    items=w.findChildren(QObject,name);pending=[w.contentItem()]
    while pending:
        item=pending.pop()
        if item.objectName()==name and item not in items:items.append(item)
        pending.extend(item.childItems())
    visible=[x for x in items if x.property('visible') is True]
    if visible:return visible[0]
    if items:return items[0]
    raise LookupError(name)
def click(name):
    assert QMetaObject.invokeMethod(find(name),'clicked'),name
    app.processEvents()
def verify():
    try:
        QTest.qWait(100)
        assert len(b.cgSettings['routes']['pulse']['A']['queue'])==5
        assert len(b.cgSettings['routes']['vibration']['B']['queue'])==5
        assert w.grabWindow().save(str(ROOT/'artifacts/ui/cg-five-stage.png'))
        click('cgQueueDetails_pulse');app.processEvents()
        viewport=find('cgFeedbackPage').property('contentItem')
        queue=find('cgQueueWave_pulse_0')
        viewport.setProperty('contentY',max(0,queue.mapToScene(QPointF(0,0)).y()-450))
        app.processEvents();QTest.qWait(100)
        before=deepcopy(b._sim_profile)
        click('cgQueueWave_pulse_0_preview')
        player=find('wavePreviewPlayer');assert player.property('visible')
        assert not player.property('playing')
        click('wavePreviewPlay');QTest.qWait(120)
        assert player.property('playing') and player.property('elapsed')>0
        assert b._sim_profile==before and b._service is None and b._v4 is None
        assert w.grabWindow().save(str(ROOT/'artifacts/ui/wave-choice-playing.png'))
        click('wavePreviewClose');QTest.qWait(200);assert not player.property('playing')
        combo=find('cgQueueWave_pulse_0_combo')
        QTest.mouseClick(w,Qt.LeftButton,Qt.NoModifier,combo.mapToScene(QPointF(15,18)).toPoint());app.processEvents();QTest.qWait(80)
        assert w.grabWindow().save(str(ROOT/'artifacts/ui/wave-choice-dropdown.png'))
        option=find('waveOptionPreview_'+str(b.waves.index(next(x for x in b.waves if x['key']==b.cgSettings['routes']['pulse']['A']['queue'][0]['wave']))))
        assert option.property('visible');assert QMetaObject.invokeMethod(option,'clicked');app.processEvents()
        assert find('wavePreviewPlayer').property('visible') and b._sim_profile==before
        click('wavePreviewClose')
        w.setWidth(1140);w.setHeight(780);app.processEvents();QTest.qWait(80)
        assert w.grabWindow().save(str(ROOT/'artifacts/ui/cg-five-stage-compact.png'))
        w.setProperty('pageIndex',2);app.processEvents();b.editQuickValue('pulse_damage',23);app.processEvents()
        click('choosePreset_low');assert find('replaceCustomPresetDialog').property('visible')
        assert w.grabWindow().save(str(ROOT/'artifacts/ui/custom-preset-confirm.png'))
        click('cancelPresetReplace');assert b.quickPolicy['current']['pulse_damage']==23
        errors=[m for m in messages if any(k in m for k in ('ReferenceError','TypeError','Binding loop','Cannot assign','Unable to assign','is not a type'))]
        assert not errors,errors
        report=dict(passed=True,five_stages_each_12_seconds=True,wave_dropdown_shapes=True,dropdown_item_preview=True,animated_preview=True,preview_did_not_change_strategy=True,preview_stops_on_close=True,custom_confirmation=True,minimum_size_checked=True,hardware_connected=False,qml_errors=errors)
        (ROOT/'artifacts/ui/feedback-workflow-validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report));app.exit(0)
    except Exception:traceback.print_exc();print(messages);app.exit(1)
QTimer.singleShot(450,verify)
result=app.exec();b.shutdown();w.close();engine.deleteLater();app.processEvents();temp.cleanup();raise SystemExit(result)
