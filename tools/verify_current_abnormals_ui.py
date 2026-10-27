"""Current-state UI verification: route labels, live freeze and stale masking."""
from pathlib import Path
import json,sys,tempfile,time,traceback
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from PySide6.QtCore import QMetaObject,QTimer,QUrl,qInstallMessageHandler
from PySide6.QtGui import QGuiApplication,QFont
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem,QQuickWindow
from sinisistar_dglab.backend import Backend

def main():
    app=QGuiApplication([]);app.setFont(QFont('Microsoft YaHei UI',10));messages=[]
    qInstallMessageHandler(lambda k,c,m:messages.append(m))
    temp=tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp');b=Backend(offline=True,settings=Path(temp.name)/'settings.json');b._timer.stop()
    b._sim_profile['abnormals']['Defilement'].update(enabled=True,pulse_channel='B',vibration_enabled=False)
    b._live=dict(live=True,valid=True,source='bepinex',session='ui-fixture',pid=123,player=456,sampled_at=time.monotonic(),sample_id=1,observer_version='0.3.0',hook_count=18,
                 hp={'current':80,'max':100},mp={'current':90,'max':100},paused=True,scene='Road_n1_0',
                 abnormals=[dict(name='InfertilityBlessing',level=1,type_raw=825765986,max_level=1,delete_timer=-1),
                            dict(name='Defilement',level=2,type_raw=960050227,max_level=10,delete_timer=12.5,remove_on_scene_change=True),
                            dict(name='FutureStatus',level=3,type_raw=-7)])
    engine=QQmlApplicationEngine();engine.rootContext().setContextProperty('backend',b);engine.load(QUrl.fromLocalFile(str(ROOT/'src/sinisistar_dglab/qml/ControlCenter.qml')))
    w=engine.rootObjects()[0];w.setProperty('pageIndex',5)
    def items():
        result=[];pending=[w.contentItem()]
        while pending:
            item=pending.pop();result.append(item);pending.extend(item.childItems())
        return result
    def array(item,name):
        value=item.property(name);return value.toVariant() if hasattr(value,'toVariant') else value
    def check():
        report={}
        try:
            b._live['sampled_at']=time.monotonic();b.changed.emit();app.processEvents()
            page=next(x for x in items() if x.objectName()=='eventDetectorPage')
            button=next(x for x in items() if x.objectName()=='currentAbnormalTab')
            assert QMetaObject.invokeMethod(button,'clicked');app.processEvents();assert page.property('mode')==3
            assert len(array(page,'currentAbnormals'))==3
            texts=[x.property('text') for x in items() if isinstance(x.property('text'),str)]
            for expected in ('不孕的加护','污秽','正面 Buff · 不参与联动','Pulse B  ·  负鼠关闭','本级计时 12.5 s · 已暂停','尚未配置联动'):
                assert any(expected in text for text in texts),expected
            assert w.grabWindow().save(str(ROOT/'artifacts/ui/current-abnormals-fixture.png'))
            assert QMetaObject.invokeMethod(page,'freezeDisplay')
            b._live['abnormals'][1]['level']=3;b._live['sampled_at']=time.monotonic();b.changed.emit();app.processEvents()
            assert array(page,'currentAbnormals')[1]['level']==3
            detector=w.findChild(QQuickWindow,'eventDetectorWindow');pending=[detector.contentItem()];detached=None
            while pending:
                candidate=pending.pop()
                if candidate.objectName()=='eventDetectorPage':detached=candidate;break
                pending.extend(candidate.childItems())
            assert detached is not None and detached.property('suspended')
            assert not array(detached,'eventRows') and not array(detached,'currentAbnormals')
            b.openEventDetector();app.processEvents();assert not detached.property('suspended')
            detached.setProperty('mode',3);assert QMetaObject.invokeMethod(detached,'freezeDisplay');app.processEvents()
            assert len(array(detached,'currentAbnormals'))==3
            detector.hide();app.processEvents();assert detached.property('suspended') and not array(detached,'eventRows')
            b._live['abnormals'][1]['level']=4;b._live['sampled_at']=time.monotonic();b.changed.emit()
            b.openEventDetector();app.processEvents()
            assert detached.property('mode')==3 and detached.property('frozen')
            assert array(detached,'currentAbnormals')[1]['level']==4
            detector.hide();app.processEvents()
            b._last=dict(b._live);b._live={'live':False};b.changed.emit();app.processEvents()
            assert b.state['abnormals'] and not array(page,'currentAbnormals')
            errors=[m for m in messages if 'file:///' in m or 'ReferenceError' in m or 'TypeError' in m];assert not errors,errors
            report=dict(passed=True,status_names_levels_timers_verified=True,positive_buff_excluded=True,route_flags_verified=True,unknown_status_retained=True,
                        record_freeze_keeps_current_status_live=True,hidden_detector_suspends_models=True,reopen_keeps_filters_and_freeze=True,
                        stale_history_not_shown_as_current=True,qml_errors=errors,hardware_connected=False)
        except Exception:report=dict(passed=False,error=traceback.format_exc(),messages=messages)
        (ROOT/'artifacts/ui/current-abnormals-interaction.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report));app.exit(0 if report['passed'] else 1)
    QTimer.singleShot(250,check);result=app.exec();b.shutdown();temp.cleanup();return result

if __name__=='__main__':raise SystemExit(main())
