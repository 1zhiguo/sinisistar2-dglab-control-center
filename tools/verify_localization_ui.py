"""Three-language native UI, tutorial and key-recorder QA; no physical devices."""
from pathlib import Path
import json,re,sys,tempfile,traceback
from copy import deepcopy
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from PySide6.QtCore import QObject,QTimer,QUrl,QMetaObject,Q_ARG,qInstallMessageHandler,Qt,QPoint
from PySide6.QtGui import QGuiApplication,QFont
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest
from sinisistar_dglab.backend import Backend
from sinisistar_dglab.hotkeys import GlobalHotkeys

class Api:
    def __init__(self):self.bindings={}
    def register(self,ident,mods,vk):
        if (mods,vk) in self.bindings.values():return '1409 · already registered'
        self.bindings[ident]=(mods,vk);return ''
    def unregister(self,ident):self.bindings.pop(ident,None)

def main():
    app=QGuiApplication([]);app.setFont(QFont('Microsoft YaHei UI',10));messages=[]
    qInstallMessageHandler(lambda k,c,m:messages.append(m))
    temp=tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp')
    b=Backend(offline=True,settings=Path(temp.name)/'settings.json');b._timer.stop();manager=GlobalHotkeys(app,b,Api())
    engine=QQmlApplicationEngine();engine.rootContext().setContextProperty('backend',b)
    engine.load(QUrl.fromLocalFile(str(ROOT/'src/sinisistar_dglab/qml/ControlCenter.qml')))
    if not engine.rootObjects():print(messages);return 1
    w=engine.rootObjects()[0]
    def items():
        pending=[w.contentItem()];result=[]
        while pending:
            item=pending.pop();result.append(item);pending.extend(item.childItems())
        return result
    def find(name):
        candidates=[x for x in items() if x.objectName()==name]
        return next((x for x in candidates if x.property('visible')),candidates[0] if candidates else w.findChild(QObject,name))
    def invoke(name,method,*args):
        assert QMetaObject.invokeMethod(find(name),method,*args),name;app.processEvents()
    def click(name):
        item=find(name);pos=item.mapToScene(item.boundingRect().center())
        QTest.mouseClick(w,Qt.LeftButton,Qt.NoModifier,QPoint(round(pos.x()),round(pos.y())));app.processEvents()
    def verify():
        try:
            profile=deepcopy(b._sim_profile);b._armed=b._ovc_armed=True
            missing={};screens=[]
            for lang in ('en','ja','zh-CN'):
                b.setLanguage(lang);app.processEvents();QTest.qWait(30)
                assert b.language==lang and b._sim_profile==profile and b._armed and b._ovc_armed
                click('openAppSettings');assert find('appSettingsMenu').property('visible')
                assert find('languageChoice').property('currentIndex')==['zh-CN','ja','en'].index(lang)
                invoke('appSettingsMenu','close')
                for page in range(9):
                    w.setProperty('pageIndex',page);app.processEvents();QTest.qWait(25)
                    if lang=='en':
                        for x in items():
                            text=x.property('localizedText')
                            if x.property('visible') and isinstance(text,str) and re.search('[\u4e00-\u9fff]',text):missing[x.property('text')]=text
                            placeholder=x.property('placeholderText')
                            if x.property('visible') and isinstance(placeholder,str):
                                assert not re.search('[\u4e00-\u9fff]',placeholder),placeholder
                            if x.property('visible') and x.property('readOnly') and isinstance(placeholder,str):
                                value=x.property('text')
                                if value and not re.match(r'^[A-Za-z]:',value):
                                    assert not re.search('[\u4e00-\u9fff]',value),value
                w.setProperty('pageIndex',7);app.processEvents()
                find('cgFeedbackPage').setProperty('scope','gallery');app.processEvents();QTest.qWait(220)
                path=ROOT/'artifacts/ui'/('localization-'+lang+'.png');assert w.grabWindow().save(str(path));screens.append(str(path))
            b.setLanguage('en');app.processEvents()
            invoke('openTutorialButton','clicked');assert find('tutorialDialog').property('visible')
            QTest.qWait(250);assert w.property('pageIndex')==1
            assert w.grabWindow().save(str(ROOT/'artifacts/ui/tutorial-en.png'))
            invoke('tutorialNext','clicked');QTest.qWait(100);assert b.tutorialState['step']==1
            assert b._armed and b._ovc_armed and w.property('pageIndex')==1
            assert find('tutorialOpenPage') is None and find('tutorialSpotlight') is None
            assert w.grabWindow().save(str(ROOT/'artifacts/ui/tutorial-plugin-en.png'))
            invoke('tutorialClose','clicked')
            click('openAppSettings');click('openHotkeySettings');invoke('hotkeyRecord','clicked')
            assert manager.capturing and not manager.registered
            QTest.keyClick(w,Qt.Key_F9,Qt.ControlModifier|Qt.ShiftModifier);app.processEvents()
            assert b.hotkeySettings['candidate']['sequence']=='Ctrl+Shift+F9',b.hotkeySettings
            invoke('hotkeySave','clicked');assert b.hotkeySettings['sequence']=='Ctrl+Shift+F9'
            assert b.hotkeySettings['registered']
            QTest.qWait(120);assert w.grabWindow().save(str(ROOT/'artifacts/ui/hotkey-editor-en.png'))
            invoke('hotkeyClose','clicked')
            b.setLanguage('ja');other=Backend(offline=True,settings=b.settings);other._timer.stop()
            try:assert other.language=='ja' and other.hotkeySettings['sequence']=='Ctrl+Shift+F9' and other.tutorialState['step']==1
            finally:other.shutdown()
            invoke('openTutorialButton','clicked');QTest.qWait(100)
            assert find('tutorialDialog').property('step')==1
            for step in range(1,5):
                assert w.property('pageIndex')==b.tutorialSteps[step]['page']
                invoke('tutorialNext','clicked');QTest.qWait(100)
            assert b.tutorialState['step']==4 and b.tutorialState['completed']
            assert not find('tutorialDialog').property('visible') and b._armed and b._ovc_armed
            w.resize(1140,780);app.processEvents();QTest.qWait(200)
            assert w.grabWindow().save(str(ROOT/'artifacts/ui/localization-compact-ja.png'))
            # The five-step guide stays docked at one position, outside the page, in every language.
            tour=[]
            for lang in ('zh-CN','en','ja'):
                b.setLanguage(lang);invoke('openTutorialButton','clicked')
                position=None
                for step in range(5):
                    QTest.qWait(100);guide=find('tutorialDialog');expected=b.tutorialSteps[step]
                    assert w.property('pageIndex')==expected['page'],(lang,step)
                    pos=guide.mapToScene(guide.boundingRect().topLeft())
                    actual=(round(pos.x()),round(pos.y()),round(guide.width()),round(guide.height()))
                    if position is None:position=actual
                    assert actual==position,(lang,step,'guide moved',actual,position)
                    assert pos.x()>=224 and pos.y()>=0 and pos.x()+guide.width()<=w.width()+1 and pos.y()+guide.height()<=w.height()+1
                    loader=find('animatedPageLoader');page_bottom=loader.mapToScene(loader.boundingRect().bottomLeft()).y()
                    assert page_bottom<=pos.y(),(lang,step,'guide overlaps page')
                    body=find('tutorialBody');assert body.property('contentHeight')<=body.height()+1,(lang,step,'body clipped')
                    tour.append(dict(language=lang,step=step,page=w.property('pageIndex'),position=actual))
                    assert w.grabWindow().save(str(ROOT/'artifacts/ui'/f'tutorial-simple-{lang}-{step}.png'))
                    if step==4:
                        invoke('tutorialHudSettings','clicked')
                        assert find('hudSettingsDialog').property('visible') and b.hudAdjusting
                        invoke('hudSettingsDialog','close');assert not b.hudAdjusting
                    invoke('tutorialNext','clicked')
                assert not find('tutorialDialog').property('visible') and b.tutorialState['completed']
            assert b._sim_profile==profile and b._armed and b._ovc_armed
            errors=[m for m in messages if any(t in m for t in ('ReferenceError','TypeError','Binding loop','Cannot assign','Unable to assign','is not a type','non-existent property'))]
            assert not errors,errors
            assert not missing,missing
            report=dict(passed=True,all_pages_languages_loaded=True,language_does_not_change_strategy=True,tutorial_resumes=True,
                keyboard_combination_recorded=True,settings_persisted=True,english_missing=missing,qml_errors=errors,screenshots=screens,hardware_connected=False)
            report['guided_steps']=tour;report['fixed_position_no_highlight']=True;report['hud_settings_opens']=True;report['settings_menu_clickable']=True
        except Exception:report=dict(passed=False,error=traceback.format_exc(),messages=messages,english_missing=locals().get('missing',{}))
        (ROOT/'artifacts/ui/localization-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False));app.exit(0 if report['passed'] else 1)
    QTimer.singleShot(350,verify);result=app.exec();b.shutdown();temp.cleanup();return result

if __name__=='__main__':raise SystemExit(main())
