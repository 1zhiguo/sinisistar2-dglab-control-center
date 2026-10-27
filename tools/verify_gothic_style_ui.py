"""Visual QA of tier treatments, decorative patrol and rapid page transitions.

An isolated offline native window; no device service or real configuration edits.
"""
from pathlib import Path
from copy import deepcopy
import json,sys,tempfile,traceback
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from PySide6.QtCore import QObject,QTimer,QUrl,QMetaObject,Qt,qInstallMessageHandler
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
w=engine.rootObjects()[0]
def find(name):
    candidates=[];pending=[w.contentItem()]
    while pending:
        x=pending.pop()
        if x.objectName()==name and x not in candidates:candidates.append(x)
        pending.extend(x.childItems())
    # QObject descendants may include an old Loader item awaiting deletion.
    # Prefer the active visual tree during rapid navigation.
    if not candidates:candidates=w.findChildren(QObject,name)
    visible=[x for x in candidates if x.property('visible') is True]
    if visible:return visible[0]
    if candidates:return candidates[0]
    raise LookupError(name)
def image(name):assert w.grabWindow().save(str(ROOT/'artifacts/ui'/name))
def page(index):w.setProperty('pageIndex',index);app.processEvents()
def verify():
    try:
        before=deepcopy(b._sim_profile)
        switch=find('topHudToggle');assert switch.property('checked') and b.state['hud']
        QTest.mouseClick(w,Qt.LeftButton,pos=switch.mapToScene(switch.boundingRect().center()).toPoint());app.processEvents()
        assert not switch.property('checked') and not b.state['hud']
        QTest.mouseClick(w,Qt.LeftButton,pos=switch.mapToScene(switch.boundingRect().center()).toPoint());app.processEvents()
        assert switch.property('checked') and b.state['hud']
        assert find('overviewProtagonistName').property('text')=='莉莉娅'
        walker=find('liliaWalker');start=walker.property('travel');QTest.qWait(600)
        assert walker.property('travel')>start
        image('gothic-overview.png')
        walker.setProperty('paused',True);app.processEvents();frozen=walker.property('travel');QTest.qWait(180)
        assert walker.property('travel')==frozen
        walker.setProperty('paused',False);app.processEvents();QTest.qWait(160)
        assert walker.property('travel')>frozen
        assert b._sim_profile==before
        page(2)
        # Incubation can finish after a few display frames on a busy host.
        # Assert the actual transition rather than an arbitrary 50ms snapshot.
        deadline=__import__('time').monotonic()+2
        while not 0<find('animatedPageLoader').property('opacity')<1 and __import__('time').monotonic()<deadline:QTest.qWait(10)
        assert 0<find('animatedPageLoader').property('opacity')<1
        QTest.qWait(400);assert find('animatedPageLoader').property('opacity')==1
        inks={tier:find('choosePreset_'+tier).property('ritualInk').name() for tier in ('low','medium','high')}
        assert len(set(inks.values()))==3 and inks['high']=='#d66670'
        image('gothic-presets.png')
        assert QMetaObject.invokeMethod(find('choosePreset_high'),'clicked');app.processEvents();QTest.qWait(650)
        assert b.quickPolicy['active']=='high';assert find('choosePreset_high').property('primary')
        image('gothic-presets-high.png')
        saved=deepcopy(b._sim_profile)
        # Allow two display frames per input, still far faster than a human click.
        for i in (7,4,3,1,8,0,2,7,0):page(i);QTest.qWait(35)
        QTest.qWait(500);assert find('animatedPageLoader').property('opacity')==1
        walker=find('liliaWalker');assert walker.property('facingRight')
        QTest.qWait(6900);assert not walker.property('facingRight')
        image('gothic-overview-return.png')
        assert b._sim_profile==saved
        w.setWidth(1140);w.setHeight(780);app.processEvents();QTest.qWait(350)
        image('gothic-overview-compact.png')
        page(2);QTest.qWait(400);image('gothic-presets-compact.png')
        assert not b._armed and not b._ovc_armed and b._service is None and b._v4 is None
        errors=[m for m in messages if any(s in m for s in ('ReferenceError','TypeError','Binding loop','Cannot assign','Unable to assign','is not a type','Error decoding','Cannot open:','Cannot override','Cannot create delegate','context destroyed'))]
        assert not errors,errors
        result=dict(passed=True,tier_colors=inks,high_black_red=True,patrol_moves_and_turns=True,pause_resumes_without_reset=True,
            protagonist_name=True,page_entrance_animates=True,rapid_navigation_finishes=True,visuals_do_not_edit_strategy=True,
            minimum_window_checked=True,top_hud_toggle_wired=True,device_services_started=False,qml_errors=errors)
        (ROOT/'artifacts/ui/gothic-style-validation.json').write_text(json.dumps(result,indent=2),encoding='utf8')
        print(json.dumps(result));app.exit(0)
    except Exception:traceback.print_exc();print(messages);app.exit(1)
QTimer.singleShot(500,verify)
code=app.exec();b.shutdown();w.close();engine.deleteLater();app.processEvents();temp.cleanup();raise SystemExit(code)
