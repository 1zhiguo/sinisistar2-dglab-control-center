"""Native read-only gallery panel check; isolated settings, no device service."""
from pathlib import Path
import json,sys,tempfile,time,traceback
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from PySide6.QtCore import QTimer,QUrl,qInstallMessageHandler
from PySide6.QtGui import QGuiApplication,QFont
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from sinisistar_dglab.backend import Backend

def main():
    app=QGuiApplication([]);app.setFont(QFont('Microsoft YaHei UI',10));messages=[]
    qInstallMessageHandler(lambda k,c,m:messages.append(m))
    temp=tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp')
    b=Backend(offline=True,settings=Path(temp.name)/'settings.json');b._timer.stop()
    b._live=dict(live=True,valid=False,source='bepinex',session='gallery-ui-test',pid=123,player=0,
        sampled_at=time.monotonic(),sample_id=1,scene_id=10,scene='Gallery',hp={'current':120,'max':120},
        gallery=dict(available=True,active=True,guide_available=True,guide_open=True,take_selected=True,take_player=123,take_data=456,
            enemy_id=28,selected_index_raw=1,take_name='Take1',play_type_raw=0,ui_paused=True,slow=False,dev_mode=True,ui_hidden=False),flow={})
    engine=QQmlApplicationEngine();engine.rootContext().setContextProperty('backend',b)
    engine.load(QUrl.fromLocalFile(str(ROOT/'src/sinisistar_dglab/qml/ControlCenter.qml')))
    w=engine.rootObjects()[0];w.setProperty('pageIndex',5)
    def texts():
        result=[];pending=[w.contentItem()]
        while pending:
            item=pending.pop();pending.extend(item.childItems());value=item.property('text')
            if isinstance(value,str):result.append(value)
        return result
    def check():
        try:
            b._live['sampled_at']=time.monotonic();b.changed.emit();app.processEvents()
            for expected in ('图鉴回放','Take1','怪物 #28','片段 [1]','Animator','Stop 已开启','DevMode 开启','图鉴独立反馈'):
                assert any(expected in t for t in texts()),expected
            assert b.state['galleryPlayback']['inGallery'] and not b.state['valid']
            assert not b.state['armed'] and not b.state['ovcArmed']
            assert w.grabWindow().save(str(ROOT/'artifacts/ui/gallery-readonly.png'))
            b._live['gallery'].update(guide_open=False,selected_index_raw=-1)
            b._live['sampled_at']=time.monotonic();b.changed.emit();app.processEvents()
            assert b.state['galleryPlayback']['phase']=='browsing'
            assert any('未选择 CG 片段' in t for t in texts())
            assert not any('已载入：Take1' in t for t in texts())
            b._live={'live':False};b.changed.emit();app.processEvents()
            assert not b.state['galleryPlayback']['dedicatedAvailable']
            errors=[m for m in messages if 'file:///' in m or 'ReferenceError' in m or 'TypeError' in m]
            assert not errors,errors
            report=dict(passed=True,missing_player_supported=True,dedicated_fields_visible=True,stale_fields_masked=True,hardware_connected=False,qml_errors=errors)
        except Exception:report=dict(passed=False,error=traceback.format_exc(),messages=messages)
        (ROOT/'artifacts/ui/gallery-readonly.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report));app.exit(0 if report['passed'] else 1)
    QTimer.singleShot(300,check);result=app.exec();b.shutdown();temp.cleanup();return result

if __name__=='__main__':raise SystemExit(main())
