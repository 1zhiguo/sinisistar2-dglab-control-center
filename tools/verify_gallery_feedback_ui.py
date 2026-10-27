"""Independent gallery editor and persistence; isolated offline backend only."""
from pathlib import Path
from copy import deepcopy
import json,sys,tempfile,traceback
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from PySide6.QtCore import QTimer,QUrl,QMetaObject,Q_ARG,qInstallMessageHandler
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
    original=deepcopy(b.cgSettings)
    engine=QQmlApplicationEngine();engine.rootContext().setContextProperty('backend',b)
    engine.load(QUrl.fromLocalFile(str(ROOT/'src/sinisistar_dglab/qml/ControlCenter.qml')))
    w=engine.rootObjects()[0];w.setProperty('pageIndex',7)
    def find(name):
        pending=[w.contentItem()]
        while pending:
            item=pending.pop()
            if item.objectName()==name:return item
            pending.extend(item.childItems())
        raise LookupError(name)
    def invoke(name,method,*args):
        assert QMetaObject.invokeMethod(find(name),method,*args),name
        app.processEvents()
    def combo(name,index):
        find(name).setProperty('currentIndex',index);invoke(name,'activated',Q_ARG(int,index))
    def toggle(name,checked):
        find(name).setProperty('checked',checked);invoke(name,'toggled')
    def verify():
        try:
            invoke('cgGalleryTab','clicked');assert find('cgFeedbackPage').property('scope')=='gallery'
            assert not b.gallerySettings['rule']['enabled'] and find('galleryPauseOnStop').property('checked')
            b._armed=b._ovc_armed=True;toggle('cgMasterEnabled',True)
            assert b.gallerySettings['rule']['enabled'] and not b._armed and not b._ovc_armed
            toggle('galleryPauseOnStop',False);assert not b.gallerySettings['pause_on_stop']
            combo('cgMode_pulse',0);combo('cgWave_pulse',1)
            invoke('cgRampSeconds_pulse','edited',Q_ARG(float,180))
            a=deepcopy(b.gallerySettings['routes']['pulse']['A'])
            invoke('cgChannelB_pulse','clicked');combo('cgMode_pulse',2)
            invoke('cgQueueDetails_pulse','clicked');invoke('cgQueueAdd_pulse','clicked')
            invoke('cgQueueSeconds_pulse_0','edited',Q_ARG(float,8.5))
            invoke('cgQueueUp_pulse_1','clicked');invoke('cgQueueRemove_pulse_1','clicked')
            assert b.gallerySettings['routes']['pulse']['A']==a
            assert b.gallerySettings['routes']['pulse']['B']['mode']=='shuffle'
            invoke('cgChannelB_vibration','clicked');combo('cgMode_vibration',1)
            invoke('cgAdvanced_vibration','clicked');combo('cgRampMode_vibration',3)
            combo('cgRampScope_vibration',1)
            b.setCgStrengthRange('gallery/vibration','b',20,60);app.processEvents()
            assert b.gallerySettings['rule']['vibration_strength_b']==60
            assert find('cgEnabled_vibration').property('accent').name()=='#a69abb'
            assert b.cgSettings==original
            snapshot=deepcopy(b.gallerySettings)
            other=Backend(offline=True,settings=b.settings);other._timer.stop()
            try:assert other.gallerySettings==snapshot and other.cgSettings==original
            finally:other.shutdown()
            assert b._service is None and b._v4 is None and b._ovc_service is None
            QTest.qWait(150);assert w.grabWindow().save(str(ROOT/'artifacts/ui/gallery-feedback.png'))
            w.resize(1140,780);app.processEvents();QTest.qWait(120)
            assert w.grabWindow().save(str(ROOT/'artifacts/ui/gallery-feedback-compact.png'))
            invoke('cgGameTab','clicked');assert b.cgSettings==original
            b.applyQuickPreset('low');app.processEvents()
            assert find('rangeSlider_cg_pulse_b').property('to')==30
            assert find('rangeSlider_cg_vibration_b').property('to')==30
            old_seconds=b.cgSettings['routes']['pulse']['B']['ramp_seconds']
            invoke('cgRampFaster_pulse','clicked')
            assert b.cgSettings['routes']['pulse']['B']['ramp_seconds']==old_seconds/2
            assert b.quickPolicy['active']==''
            invoke('cgRampSlower_pulse','clicked')
            assert b.cgSettings['routes']['pulse']['B']['ramp_seconds']==old_seconds
            invoke('cgGalleryTab','clicked');b.applyQuickPreset('high');app.processEvents()
            assert find('rangeSlider_cg_pulse_b').property('to')==90
            assert find('rangeSlider_cg_vibration_b').property('to')==90
            assert b.gallerySettings['rule']['pulse_strength_b']==80
            assert b.cgSettings['rule']['pulse_strength_b']==80
            for route in ('pulse','vibration'):
                slider=find('strengthRange_cg_'+route+'_b')
                assert slider.property('displayedLow')==60
                assert slider.property('displayedHigh')==80
            assert not b.mockValidation['active']
            invoke('openAppSettings','clicked');invoke('openSimulationSettings','clicked')
            assert find('mainMockStart').property('visible')
            invoke('closeSimulationSettings','clicked')
            w.resize(1440,940);app.processEvents();QTest.qWait(120)
            assert w.grabWindow().save(str(ROOT/'artifacts/ui/gallery-preset-speed.png'))
            errors=[m for m in messages if any(k in m for k in ('ReferenceError','TypeError','Binding loop','Cannot assign','Unable to assign','is not a type'))]
            assert not errors,errors
            report=dict(passed=True,independent_ab_editing=True,game_cg_unchanged=True,pause_option_persisted=True,
                queue_add_edit_move_remove=True,editing_disarms=True,persisted=True,preset_limits_follow_tier=True,
                ramp_speed_controls=True,mock_entry_in_settings=True,minimum_size_checked=True,hardware_connected=False,qml_errors=errors)
        except Exception:report=dict(passed=False,error=traceback.format_exc(),messages=messages)
        (ROOT/'artifacts/ui/gallery-feedback-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report));app.exit(0 if report['passed'] else 1)
    QTimer.singleShot(350,verify);result=app.exec();b.shutdown();temp.cleanup();return result

if __name__=='__main__':raise SystemExit(main())
