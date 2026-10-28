"""Native helper UI -> local IPC fixture; never mutates the real game."""
from pathlib import Path
from datetime import datetime,timezone
import json,sys,tempfile,traceback
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from PySide6.QtCore import QObject,QMetaObject,QTimer,QUrl,qInstallMessageHandler
from PySide6.QtGui import QGuiApplication,QFont
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem,QQuickWindow
from sinisistar_dglab.backend import Backend
from sinisistar_dglab.telemetry import BUILD,TYPES

def main():
    app=QGuiApplication([]);app.setFont(QFont('Microsoft YaHei UI',10));messages=[]
    qInstallMessageHandler(lambda k,c,m:messages.append(m))
    temp=tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp');folder=Path(temp.name)
    b=Backend(offline=True,settings=folder/'settings.json');b._timer.stop()
    b._game_directory=folder/'game';b._game_candidates=[dict(path=str(b._game_directory),supported=True)]
    ipc=b._game_directory/'BepInEx/plugins/SiNiSistarTrainer/ipc';ipc.mkdir(parents=True)
    data=dict(schema=1,source='bepinex-trainer',fingerprint=BUILD,session='a'*32,pid=123,player=456,
              valid=True,can_edit=True,hp=dict(current=80,max=100),mp=dict(current=70,max=100),attack_multiplier=1.,attack_available=True)
    ids={name:int(raw) for raw,name in TYPES['AbnormalType'].items()}
    data.update(version='0.2.1',attack_persistent=True,attack_level=2,status_removal_available=True,abnormals=[dict(type_raw=ids['Poison'],level=3),dict(type_raw=ids['Slow'],level=1),dict(type_raw=ids['InfertilityBlessing'],level=1)])
    engine=QQmlApplicationEngine();engine.rootContext().setContextProperty('backend',b)
    engine.load(QUrl.fromLocalFile(str(ROOT/'src/sinisistar_dglab/qml/ControlCenter.qml')))
    w=engine.rootObjects()[0];w.setProperty('pageIndex',1);report={};requests=[]
    def find(name):
        item=w.findChild(QObject,name)
        if item:return item
        pending=[w.contentItem()]
        while pending:
            item=pending.pop()
            if item.objectName()==name:return item
            pending.extend(item.childItems())
        raise LookupError(name)
    def publish():
        data['utc']=datetime.now(timezone.utc).isoformat();(ipc/'latest.json').write_text(json.dumps(data),encoding='utf-8')
        b._trainer.poll(ipc);b.changed.emit();app.processEvents()
    def click(name,attribute,mode,value):
        assert QMetaObject.invokeMethod(find(name),'clicked')
        c=json.loads((ipc/'command.json').read_text());requests.append(c)
        assert (c['attribute'],c['mode'],c['value'])==(attribute,mode,value),c
        assert not b._armed and not b._ovc_armed
        assert not find('trainerPlus_hp').property('enabled')
        before=data['attack_multiplier'] if attribute=='attack' else data[attribute]['current']
        after=1. if mode=='reset' else before+value if mode=='add' else value
        after=max(0,min(10 if attribute=='attack' else 100,after))
        if attribute=='attack':data['attack_multiplier']=after
        else:data[attribute]['current']=int(after)
        result={k:c[k] for k in ('id','session','pid','player','attribute')}
        result.update(ok=True,before=before,after=after if attribute=='attack' else int(after),max=100)
        (ipc/'result.json').write_text(json.dumps(result),encoding='utf-8');publish()
        assert not b.trainerState['pending'] and '游戏已确认' in b.trainerState['message']
    def verify():
        try:
            assert QMetaObject.invokeMethod(find('openAppSettings'),'clicked');app.processEvents()
            assert QMetaObject.invokeMethod(find('settingsMoreOptions'),'clicked');app.processEvents()
            assert QMetaObject.invokeMethod(find('openGameAssistance'),'clicked');app.processEvents()
            assert QMetaObject.invokeMethod(find('openGameTrainer'),'clicked');app.processEvents()
            assert find('trainerDialog').property('visible')
            assert not find('trainerPlus_hp').property('enabled')
            b.offline=False;publish();b._armed=True;b._ovc_armed=True
            assert 'Lv.2' in find('trainerGameAttackLevel').property('text')
            for field,step in [('hp',10),('mp',10),('attack',.25)]:
                assert find('trainerPlus_'+field).property('enabled')
                click('trainerMinus_'+field,field,'add',-step)
                click('trainerPlus_'+field,field,'add',step)
            for field,encoded,value in [('hp',42,42),('mp',33,33),('attack',50,.5)]:
                find('trainerTarget_'+field).setProperty('value',encoded)
                click('trainerSet_'+field,field,'set',value)
            click('trainerResetAttack','attack','reset',0)
            assert w.grabWindow().save(str(ROOT/'artifacts/ui/trainer-interaction-fixture.png'))
            assert QMetaObject.invokeMethod(find('trainerStatusesTab'),'clicked');app.processEvents()
            assert find('trainerDialog').property('tabIndex')==1 and len(b.trainerState['abnormals'])==3
            assert w.grabWindow().save(str(ROOT/'artifacts/ui/trainer-status-removal-fixture.png'))
            for name,attribute,mode,value in [('removeCurrentAbnormal_'+str(ids['Poison']),'abnormal','remove',ids['Poison']),('trainerClearNegative','abnormals','clear_negative',0)]:
                assert QMetaObject.invokeMethod(find(name),'clicked')
                c=json.loads((ipc/'command.json').read_text());requests.append(c)
                assert (c['attribute'],c['mode'],c['value'])==(attribute,mode,value)
                assert not find('trainerClearNegative').property('enabled')
                targets=[r['type_raw'] for r in data['abnormals'] if (r['type_raw']==value if attribute=='abnormal' else r['type_raw']!=ids['InfertilityBlessing'])]
                data['abnormals']=[r for r in data['abnormals'] if r['type_raw'] not in targets]
                result={k:c[k] for k in ('id','session','pid','player','attribute')};result.update(ok=True,before=len(targets),after=0,removed_types=targets)
                (ipc/'result.json').write_text(json.dumps(result),encoding='utf-8');publish()
            assert [r['type_raw'] for r in b.trainerState['abnormals']]==[ids['InfertilityBlessing']]
            assert not find('trainerClearNegative').property('enabled')
            assert find('removeCurrentAbnormal_'+str(ids['InfertilityBlessing'])).property('enabled')
            assert QMetaObject.invokeMethod(find('trainerDialog'),'close')
            errors=[m for m in messages if 'file:///' in m or 'ReferenceError' in m or 'TypeError' in m]
            assert not errors,errors
            report.update(passed=True,all_three_attributes_support_increase_decrease_and_set=True,
                          attack_reset_verified=True,game_attack_level_displayed_separately=True,request_count=len(requests),output_disarmed_before_each_change=True,
                          controls_disabled_while_waiting=True,game_reply_required_for_success=True,
                          individual_status_removal=True,bulk_negative_clear_preserves_blessing=True,
                          qml_errors=errors,live_game_mutated=False,hardware_connected=False)
        except Exception:report.update(passed=False,error=traceback.format_exc(),messages=messages)
        (ROOT/'artifacts/ui/trainer-interaction.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report));app.exit(0 if report['passed'] else 1)
    QTimer.singleShot(350,verify);result=app.exec();b.shutdown();temp.cleanup();return result

if __name__=='__main__':raise SystemExit(main())
