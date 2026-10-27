"""Native QML preset editing/apply and navigation check, no device service."""
from pathlib import Path
from copy import deepcopy
import json,sys,tempfile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from PySide6.QtCore import QObject,QMetaObject,QTimer,QUrl,Q_ARG,qInstallMessageHandler
from PySide6.QtGui import QGuiApplication,QFont
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem,QQuickWindow
from sinisistar_dglab.backend import Backend

def main():
    app=QGuiApplication([]);app.setFont(QFont('Microsoft YaHei UI',10));messages=[]
    qInstallMessageHandler(lambda k,c,m:messages.append(m))
    temp=tempfile.TemporaryDirectory(dir=ROOT/'artifacts/test-temp')
    b=Backend(offline=True,settings=Path(temp.name)/'settings.json')
    engine=QQmlApplicationEngine();engine.rootContext().setContextProperty('backend',b)
    engine.load(QUrl.fromLocalFile(str(ROOT/'src/sinisistar_dglab/qml/ControlCenter.qml')))
    w=engine.rootObjects()[0];w.setProperty('pageIndex',2)
    def find(name):
        pending=[w.contentItem()]
        while pending:
            item=pending.pop()
            if item.objectName()==name:return item
            pending.extend(item.childItems())
        raise LookupError(name)
    def assert_accent(name,expected):
        assert find(name).property('accent').name()==expected,name
    def assert_route_accents(name,expected):
        pending=[find(name)];count=0
        while pending:
            item=pending.pop();color=item.property('accent')
            if hasattr(color,'name'):
                assert color.name()==expected,(name,item.objectName(),color.name());count+=1
            pending.extend(item.childItems())
        assert count>=5,(name,count)
    def verify():
        report={}
        try:
            assert QMetaObject.invokeMethod(find('choosePreset_low'),'clicked')
            app.processEvents();before=deepcopy(b._sim_profile['rules']);tiers=deepcopy(b.quickPolicy['presets'])
            assert b.quickPolicy['active']=='low'
            assert not find('quickCombatDisclosure').property('expanded')
            assert not find('quickAdvancedDisclosure').property('expanded')
            shared=find('sharedRange_pulse_death_a')
            assert QMetaObject.invokeMethod(shared,'edited',Q_ARG(float,3.),Q_ARG(float,8.))
            assert b.quickPolicy['active']=='' and b.quickPolicy['current']['pulse_death_b']==8
            assert b.quickPolicy['presets']==tiers
            assert QMetaObject.invokeMethod(find('choosePreset_high'),'clicked');app.processEvents()
            dialog=w.findChild(QObject,'replaceCustomPresetDialog');assert dialog.property('visible')
            assert b.quickPolicy['current']['pulse_death_b']==8
            assert QMetaObject.invokeMethod(find('cancelPresetReplace'),'clicked');app.processEvents()
            assert not dialog.property('visible') and b.quickPolicy['active']==''
            assert QMetaObject.invokeMethod(find('quickAdvancedDisclosure'),'clicked');app.processEvents()
            spin=find('presetRange_pulse_death_a')
            assert QMetaObject.invokeMethod(spin,'edited',Q_ARG(float,4.),Q_ARG(float,7.))
            assert b.quickPolicy['current']['pulse_death_a']==7 and b.quickPolicy['current']['pulse_death_b']==8
            for _ in range(2):assert QMetaObject.invokeMethod(find('quickAdvancedDisclosure'),'clicked');app.processEvents()
            mode=find('quickDeathMode');mode.setProperty('currentIndex',1)
            b._armed=True;b._ovc_armed=True
            assert QMetaObject.invokeMethod(mode,'activated',Q_ARG(int,1));app.processEvents()
            assert b.quickPolicy['deathMode']=='timed' and find('quickDeathSeconds').property('visible')
            assert not b._armed and not b._ovc_armed
            assert b._sim_profile['rules']['hp_loss']==before['hp_loss']
            scope=find('feedbackScope_pulseB');scope.setProperty('currentIndex',1)
            assert QMetaObject.invokeMethod(scope,'activated',Q_ARG(int,1));app.processEvents()
            assert b.simulationSettings['channel_feedback']['pulse']['B']=='cg'
            saved=json.loads(b.settings.read_text(encoding='utf-8'))['simulation']
            assert saved['quick_active_preset']=='' and saved['rules']['defeat_hold']['pulse_strength_a']==7
            assert w.grabWindow().save(str(ROOT/'artifacts/ui/quick-custom-confirm.png'))
            assert QMetaObject.invokeMethod(find('choosePreset_high'),'clicked');app.processEvents()
            assert dialog.property('visible')
            assert QMetaObject.invokeMethod(find('confirmPresetReplace'),'clicked');app.processEvents()
            assert b.quickPolicy['active']=='high' and b.quickPolicy['current']['pulse_cap']==90
            assert b.simulationSettings['channel_feedback']['pulse']['B']=='cg'
            b.editQuickValue('death_mode','timed')
            pages=[]
            for index in range(7):
                w.setProperty('pageIndex',index);app.processEvents()
                pages.append(index)
                if index==1:
                    for channel in 'AB':
                        assert_accent('setupChannel_ovc'+channel,'#c3a777')
                        assert_accent('setupChannel_pulse'+channel,'#c3a777')
                        assert_accent('setupLimit_ovc'+channel,'#c3a777')
                        assert_accent('setupLimit_pulse'+channel,'#c3a777')
                    assert_accent('setupArmOvc','#c3a777');assert_accent('setupArmPulse','#c3a777')
                if index==2:
                    for suffix in ('cap','damage','break'):
                        assert_accent('presetSlider_ovc_'+suffix,'#a69abb')
                        assert_accent('presetSlider_pulse_'+suffix,'#c3a777')
                    for channel in 'AB':
                        assert_accent('deathChannelToggle_vibration'+channel,'#a69abb')
                        assert_accent('deathChannelToggle_pulse'+channel,'#c3a777')
                if index==3:
                    for name in ('policySharedDisclosure','ruleDetails_pulse','ruleDetails_vibration','ruleTimingDisclosure'):
                        header=find(name);assert not header.property('expanded')
                        assert QMetaObject.invokeMethod(header,'clicked');assert header.property('expanded');app.processEvents()
                    assert_route_accents('ruleRoute_vibration','#a69abb')
                    assert_route_accents('ruleRoute_pulse','#c3a777')
                    assert not any(r['key'] in ('escape','hp0') for r in b.simulationEvents)
                    page=w.findChild(QObject,'feedbackPolicyPage')
                    page.setProperty('selected',next(i for i,r in enumerate(b.simulationEvents) if r['key']=='defeat_hold'));app.processEvents()
                    assert find('ruleDeathSeconds').property('visible')
                    assert QMetaObject.invokeMethod(find('ruleDeathSeconds'),'edited',Q_ARG(float,2.5))
                    assert b.quickPolicy['deathSeconds']==2.5
                    page.setProperty('selected',next(i for i,r in enumerate(b.simulationEvents) if r['key']=='break'));app.processEvents()
                    duration=find('ruleFeedbackDuration');assert duration.property('visible')
                    assert QMetaObject.invokeMethod(duration,'edited',Q_ARG(float,1.4))
                    assert b._sim_profile['rules']['break']['duration']==1.4
                    assert_route_accents('ruleRoute_vibration','#a69abb')
                if index==4:
                    assert_accent('waveRouteOvc','#a69abb');assert_accent('waveRoutePulse','#c3a777')
            w.setProperty('pageIndex',2);app.processEvents()
            assert len(b.quickPolicy['presets'])==3
            assert b.quickPolicy['presets']==tiers
            assert find('diagnosticNavSeparator').property('height')==1
            b.openHudSettings();app.processEvents()
            for channel in 'ab':
                assert_accent('hudOption_ovc_'+channel,'#a69abb')
                assert_accent('hudOption_pulse_'+channel,'#c3a777')
            dialog=w.findChild(QObject,'hudSettingsDialog');assert dialog and dialog.property('visible')
            assert QMetaObject.invokeMethod(dialog,'close');app.processEvents()
            errors=[m for m in messages if 'file:///' in m or 'ReferenceError' in m or 'TypeError' in m]
            assert not errors,errors
            report=dict(passed=True,pages_loaded=pages,custom_auto_save=True,confirm_before_overwrite=True,cancel_keeps_custom=True,confirmed_tier_restores_values=True,
                        edits_disarm_both=True,collapsed_by_default=True,shared_death_updates_both=True,independent_ab_preserved_when_folding=True,all_strategy_details_expand=True,double_thumb_ranges_wired=True,diagnostic_separator_present=True,clothing_duration_edit_verified=True,escape_feedback_removed=True,death_modes_and_duration_verified=True,ovc_controls_violet_and_pulse_gold=True,connection_controls_uniform_gold=True,channel_scope_persisted=True,hardware_connected=False,qml_errors=errors)
            assert w.grabWindow().save(str(ROOT/'artifacts/ui/quick-settings-interaction.png'))
        except Exception:
            import traceback
            report=dict(passed=False,error=traceback.format_exc(),messages=messages)
        (ROOT/'artifacts/ui/quick-settings-interaction.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report));app.exit(0 if report['passed'] else 1)
    QTimer.singleShot(400,verify);result=app.exec();b.shutdown();temp.cleanup();return result

if __name__=='__main__':raise SystemExit(main())
