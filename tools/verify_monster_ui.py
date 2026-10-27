"""Verify local catalog browsing without device services or production settings."""
from pathlib import Path
from copy import deepcopy
import json,sys,tempfile,traceback
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from PySide6.QtCore import QTimer,QUrl,QMetaObject,Q_ARG,qInstallMessageHandler
from PySide6.QtGui import QGuiApplication,QFont
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow,QQuickItem
from PySide6.QtTest import QTest
from sinisistar_dglab.backend import Backend
from sinisistar_dglab.monster_catalog import MonsterCatalog

app=QGuiApplication([]);app.setFont(QFont('Microsoft YaHei UI',10));messages=[]
qInstallMessageHandler(lambda kind,context,text:messages.append(text))
temp=tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp')
b=Backend(offline=True,settings=Path(temp.name)/'settings.json');b._timer.stop()
b.importMonsterPreviews((ROOT/'artifacts/monster-cache').as_uri())
engine=QQmlApplicationEngine();engine.rootContext().setContextProperty('backend',b)
engine.load(QUrl.fromLocalFile(str(ROOT/'src/sinisistar_dglab/qml/ControlCenter.qml')))
assert engine.rootObjects(),messages
w=engine.rootObjects()[0];w.setProperty('pageIndex',8)
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
def count():return find('monsterGrid').property('count')
def verify():
    try:
        page=find('monsterCatalogPage');assert count()==115
        assert b.monsterCatalogSummary['previews']==3571
        profile=deepcopy(b._sim_profile);b._armed=b._ovc_armed=True
        invoke('favoriteMonster','clicked');assert next(x for x in b.monsterCatalog if x['key']=='Zombie')['favorite']
        combo('monsterAvailability',3);assert count()==1
        combo('monsterAvailability',0)
        find('monsterSearch').setProperty('text','守墓人');app.processEvents();assert count()==1
        find('monsterSearch').setProperty('text','');combo('monsterAvailability',2);assert count()==4
        combo('monsterAvailability',4);assert 0<count()<115
        combo('monsterAvailability',0);combo('monsterActionFilter',5);assert 0<count()<115
        combo('monsterActionFilter',0);page.setProperty('selectedKey','Zombie');app.processEvents()
        assert find('monsterGroupChoice').property('count')>1
        combo('monsterGroupChoice',1);assert find('monsterFrameStrip').property('count')>0
        b._live=dict(live=True,valid=True,bound=True,binder='Zombie',sampled_at=__import__('time').monotonic())
        b.changed.emit();assert b.currentMonster=='Zombie'
        assert b._armed and b._ovc_armed and profile==b._sim_profile
        b._live={};b._armed=b._ovc_armed=False;b.changed.emit()
        find('monsterSearch').setProperty('text','no such monster');app.processEvents();assert count()==0
        find('monsterSearch').setProperty('text','');app.processEvents()
        find('monsterSearch').setProperty('text','猪');app.processEvents();assert count()==4
        page.setProperty('selectedKey','VillagerMiddleMale_A_Pig');app.processEvents();QTest.qWait(150)
        assert 'head_pig' in find('monsterGroupChoice').property('currentText')
        assert w.grabWindow().save(str(ROOT/'artifacts/ui/monster-catalog-pigs.png'))
        find('monsterSearch').setProperty('text','');app.processEvents()
        page.setProperty('selectedKey','Zombie');combo('monsterGroupChoice',0)
        QTest.qWait(500);assert w.grabWindow().save(str(ROOT/'artifacts/ui/monster-catalog.png'))
        w.setWidth(1140);w.setHeight(780);app.processEvents();QTest.qWait(350)
        assert w.grabWindow().save(str(ROOT/'artifacts/ui/monster-catalog-compact.png'))
        assert find('navigation_4').mapToScene(find('navigation_4').boundingRect().bottomRight()).y()<find('diagnosticNavSeparator').mapToScene(find('diagnosticNavSeparator').boundingRect().topLeft()).y()
        b._monsters=MonsterCatalog(Path(temp.name)/'clean-install');b.monsterCatalogChanged.emit();app.processEvents();QTest.qWait(100)
        assert b.monsterCatalogSummary['previews']==3571 and count()==115
        assert b.monsterCatalogSummary['local_previews']==0
        combo('monsterAvailability',1);assert count()==111
        combo('monsterAvailability',0)
        invoke('monsterOpenCg','clicked');assert w.property('pageIndex')==7
        errors=[m for m in messages if any(s in m for s in ('ReferenceError','TypeError','Binding loop','Cannot assign','Unable to assign','is not a type','Error decoding','Cannot open:'))]
        assert not errors,errors
        assert b._service is None and b._v4 is None
        report=dict(passed=True,groups=115,previews=3571,pig_search_results=4,favorites=True,search=True,missing_filter=True,part_filter=True,action_filter=True,empty_state=True,frame_selection=True,current_binder_name_match=True,output_unchanged=True,minimum_layout=True,clean_install_without_cache=True,packaged_previews=True,qml_errors=errors,device_services=False)
        (ROOT/'artifacts/ui/monster-catalog-validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
        print(json.dumps(report));app.exit(0)
    except Exception:traceback.print_exc();print(messages);app.exit(1)
QTimer.singleShot(800,verify)
result=app.exec();b.shutdown();w.close();engine.deleteLater();app.processEvents();temp.cleanup();raise SystemExit(result)
